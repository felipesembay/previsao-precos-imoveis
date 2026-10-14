"""
run_data_drift.py
=================
Job agendado (cron / Airflow) que:
  1. Carrega dados de referência (baseline parquet ou PostgreSQL)
  2. Carrega dados de produção recentes do PostgreSQL
  3. Calcula Data Drift com Evidently 0.7.x
  4. Persiste as métricas no PostgreSQL
  5. Salva relatório HTML para auditoria

Escala de drift_score (Evidently 0.7.x usa Wasserstein distance normed):
  - 0.0  = distribuições idênticas
  - 0.1+ = drift moderado   → warning
  - 0.3+ = drift significativo → critical
  O valor é armazenado direto: drift_score = wasserstein_distance (clipped a 1.0)

Uso:
    python monitoring/jobs/run_data_drift.py

Modo teste (sem PostgreSQL):
    DRIFT_DRY_RUN=1 python monitoring/jobs/run_data_drift.py
"""

import datetime
import os
import sys

import pandas as pd
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

from evidently import Dataset, Report
from evidently.presets import DataDriftPreset

from monitoring.db.postgres import (load_baseline_data, load_current_data,
                                 save_distribution_stats, save_metric)

# ── Configuração ──────────────────────────────────────────────────────────────
CONFIG_PATH      = os.path.join(os.path.dirname(__file__), "../config/features.yaml")
BASELINE_PARQUET = os.path.join(ROOT, "data/processed/baseline_monitoring.parquet")
REPORTS_DIR      = os.path.join(ROOT, "results/drift_reports")

os.makedirs(REPORTS_DIR, exist_ok=True)

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

MODEL_NAME    = config["model"]["name"]
MODEL_VERSION = config["model"]["version"]
BASELINE_DAYS = config["time_windows"]["baseline_days"]
CURRENT_DAYS  = config["time_windows"]["current_days"]
NUM_FEATURES  = config["features"]["numerical"]
# Wasserstein normed: alerta quando dist > wasserstein_threshold (default 0.1)
WASSERSTEIN_THRESHOLD = config.get("drift", {}).get("wasserstein_threshold", 0.1)

DRY_RUN  = os.getenv("DRIFT_DRY_RUN", "0") == "1"
# DRIFT_SEED=1 → usa parquet para baseline E current, mas salva no PostgreSQL
# útil para popular o banco na primeira execução (sem dados de produção ainda)
SEED_MODE = os.getenv("DRIFT_SEED", "0") == "1"

# ── Carregar dados ────────────────────────────────────────────────────────────
print("📂 Carregando dados de referência...")

if DRY_RUN or SEED_MODE:
    import numpy as np
    mode_label = "SEED (salva no PostgreSQL)" if SEED_MODE else "DRY RUN (sem PostgreSQL)"
    print(f"   [{mode_label}] Parquet como referência + ruído leve como current.")
    _raw = pd.read_parquet(BASELINE_PARQUET)
    baseline_df = _raw[NUM_FEATURES].dropna()
    current_df  = baseline_df.sample(min(300, len(baseline_df)), random_state=1).copy()
    current_df["area_m2"]       *= np.random.uniform(0.8, 1.2, len(current_df))
    current_df["score_mercado"]  *= np.random.uniform(1.0, 1.5, len(current_df))
else:
    baseline_db = load_baseline_data(BASELINE_DAYS)
    if baseline_db.empty:
        print("   ⚠️  Baseline PostgreSQL vazio — usando parquet.")
        _raw = pd.read_parquet(BASELINE_PARQUET)
        baseline_df = _raw[NUM_FEATURES].dropna()
    else:
        baseline_df = baseline_db[NUM_FEATURES].dropna()

    current_df = load_current_data(CURRENT_DAYS)
    if current_df.empty:
        raise ValueError(f"❌ Sem dados de produção nos últimos {CURRENT_DAYS} dias.")
    current_df = current_df[NUM_FEATURES].dropna()

print(f"   Referência: {len(baseline_df)} linhas | Atual: {len(current_df)} linhas")

# ── Calcular e salvar estatísticas de distribuição ───────────────────────────
print("📊 Calculando estatísticas de distribuição...")

def calc_stats(series: pd.Series) -> dict:
    """Calcula estatísticas descritivas de uma Series pandas"""
    # Garantir que é numérica e dropna
    series_clean = pd.to_numeric(series, errors='coerce').dropna()
    
    if len(series_clean) == 0:
        return {
            'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0,
            'p25': 0.0, 'p50': 0.0, 'p75': 0.0, 'count': 0
        }
    
    return {
        'mean': float(series_clean.mean()),
        'std': float(series_clean.std()),
        'min': float(series_clean.min()),
        'max': float(series_clean.max()),
        'p25': float(series_clean.quantile(0.25)),
        'p50': float(series_clean.quantile(0.50)),
        'p75': float(series_clean.quantile(0.75)),
        'count': int(len(series_clean))
    }

for feature in NUM_FEATURES:
    if feature in baseline_df.columns and feature in current_df.columns:
        baseline_stats = calc_stats(baseline_df[feature])
        current_stats = calc_stats(current_df[feature])
        
        if not DRY_RUN or SEED_MODE:
            save_distribution_stats(feature, 'baseline', baseline_stats, MODEL_NAME, MODEL_VERSION)
            save_distribution_stats(feature, 'production', current_stats, MODEL_NAME, MODEL_VERSION)

print(f"   Estatísticas salvas para {len(NUM_FEATURES)} features")

# ── Relatório Evidently 0.7.x ─────────────────────────────────────────────────
print("🔍 Calculando Data Drift com Evidently 0.7.x ...")

report   = Report(metrics=[DataDriftPreset()])
snapshot = report.run(
    reference_data=Dataset.from_pandas(baseline_df),
    current_data=Dataset.from_pandas(current_df),
)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
html_path = os.path.join(REPORTS_DIR, f"drift_report_{timestamp}.html")
try:
    snapshot.save_html(html_path)
    print(f"   HTML: {html_path}")
except Exception as e:
    print(f"   ⚠️  HTML não salvo: {e}")

# ── Extrair métricas ──────────────────────────────────────────────────────────
# Evidently 0.7.x — estrutura do snapshot.dict():
#   DriftedColumnsCount → value = {"count": int, "share": float}
#   ValueDrift(column=X) → value = Wasserstein distance (normed)
#                          config.threshold = limiar de detecção (default ~0.1)

snap_dict        = snapshot.dict()
drifted_features = []
all_drift_scores = {}
dataset_drifted  = False
share_drifted    = 0.0

for entry in snap_dict.get("metrics", []):
    m_name = entry.get("metric_name", "")
    value  = entry.get("value")
    cfg    = entry.get("config", {})

    # ── DriftedColumnsCount ────────────────────────────────────────────────
    if "DriftedColumnsCount" in m_name and isinstance(value, dict):
        share_drifted   = float(value.get("share", 0.0))
        drifted_count   = int(value.get("count", 0))
        dataset_drifted = share_drifted >= 0.5

        if not DRY_RUN or SEED_MODE:
            save_metric("dataset_drift_detected", float(dataset_drifted),
                        "dataset", "drift", MODEL_NAME, MODEL_VERSION)
            save_metric("share_drifted_columns", round(share_drifted, 4),
                        "dataset", "drift", MODEL_NAME, MODEL_VERSION)

        print(f"\n📊 Dataset drift: {dataset_drifted} "
              f"({share_drifted:.1%} — {drifted_count} features)")

    # ── ValueDrift por feature (Wasserstein distance normed) ──────────────
    elif "ValueDrift" in m_name and isinstance(value, (int, float)):
        feature_name    = cfg.get("column", m_name)
        raw_score       = float(value)
        threshold       = float(cfg.get("threshold", WASSERSTEIN_THRESHOLD))

        # Wasserstein normed: normalmente 0–1, mas pode ser > 1 em outliers
        drift_score     = min(round(raw_score, 6), 1.0)
        feature_drifted = raw_score >= threshold

        all_drift_scores[feature_name] = drift_score
        if feature_drifted:
            drifted_features.append(feature_name)

        if not DRY_RUN or SEED_MODE:
            save_metric("data_drift", drift_score,
                        feature_name, "drift", MODEL_NAME, MODEL_VERSION)

# ── Resumo ────────────────────────────────────────────────────────────────────
print("\n─────────────────────────────────────────────────────────────────")
print(f"{'Feature':<30} {'Wasserstein Dist':>18} {'Drifted':>8}")
print("─────────────────────────────────────────────────────────────────")
for feat, ds in sorted(all_drift_scores.items(), key=lambda x: -x[1]):
    flag = "⚠️ " if feat in drifted_features else "  "
    print(f"{flag}{feat:<28} {ds:>18.4f}  {'YES' if feat in drifted_features else 'no'}")
print("─────────────────────────────────────────────────────────────────")
print(f"\nFeatures com drift ({len(drifted_features)}): {drifted_features}")
mode_desc = "DRY_RUN (sem salvar)" if DRY_RUN else ("SEED (parquet → PostgreSQL)" if SEED_MODE else "salvo no PostgreSQL")
print(f"\n✅ Data Drift {mode_desc} com sucesso.")
print(f"\n✅ Data Drift {mode_desc} com sucesso.")
