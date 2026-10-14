"""
run_data_drift.py
=================
Job agendado (DAG monitoramento_modelos do Airflow, de hora em hora) que, para cada
modelo de monitoring/config/features.yaml (compra e aluguel):
  1. Carrega o baseline (features do treino, parquet)
  2. Carrega as features de produção dos últimos N dias do PostgreSQL
  3. Calcula Data Drift com Evidently 0.7.x e salva estatísticas de distribuição
  4. Calcula o desempenho real (MAE, MAPE, viés) nas previsões com valor de anúncio
  5. Persiste tudo em metrics_monitoramento / distribution_stats e salva HTML

Um modelo sem dados recentes é pulado com aviso — não interrompe os demais.

Escala de drift_score (Evidently 0.7.x usa Wasserstein distance normed):
  - 0.0  = distribuições idênticas
  - 0.1+ = drift moderado   → warning
  - 0.3+ = drift significativo → critical

Uso:
    python monitoring/jobs/run_data_drift.py              # todos os modelos
    python monitoring/jobs/run_data_drift.py aluguel      # só um modelo

Modos de teste:
    DRIFT_DRY_RUN=1  → calcula e imprime, sem gravar no PostgreSQL
    DRIFT_SEED=1     → usa amostra do baseline (com ruído) como produção e grava
"""

import datetime
import os
import sys
import warnings

import numpy as np
import pandas as pd
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

# Features constantes na amostra atual geram divisão por zero dentro do Evidently (inofensivo)
warnings.filterwarnings("ignore", category=RuntimeWarning)

from evidently import Dataset, Report  # noqa: E402
from evidently.presets import DataDriftPreset  # noqa: E402

from monitoring.db.postgres import load_janela, save_distribution_stats, save_metric  # noqa: E402

# ── Configuração ──────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/features.yaml")
REPORTS_DIR = os.path.join(ROOT, "results/drift_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

CURRENT_DAYS = config["time_windows"]["current_days"]
WASSERSTEIN_THRESHOLD = config.get("drift", {}).get("wasserstein_threshold", 0.1)
MIN_AMOSTRAS = config.get("drift", {}).get("min_amostras_confiavel", 30)

DRY_RUN = os.getenv("DRIFT_DRY_RUN", "0") == "1"
SEED_MODE = os.getenv("DRIFT_SEED", "0") == "1"
SALVAR = not DRY_RUN


def versao_do_modelo(cfg: dict) -> str:
    """Versão fixa do YAML ou a do @champion no MLflow (ex.: 'v1')."""
    if not cfg.get("mlflow_model"):
        return cfg.get("version", "unknown")
    try:
        from src.models.registro import versao_champion

        return f"v{versao_champion(cfg['mlflow_model']).version}"
    except Exception as exc:
        print(f"   ⚠️  Versão não encontrada no MLflow ({exc}); usando '{cfg.get('version', 'unknown')}'")
        return cfg.get("version", "unknown")


def calc_stats(series: pd.Series) -> dict:
    """Estatísticas descritivas de uma Series pandas."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "count": 0}
    return {
        "mean": float(s.mean()), "std": float(s.std()) if len(s) > 1 else 0.0,
        "min": float(s.min()), "max": float(s.max()),
        "p25": float(s.quantile(0.25)), "p50": float(s.quantile(0.50)), "p75": float(s.quantile(0.75)),
        "count": int(len(s)),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Desempenho (erro real nas previsões com valor de anúncio)
# ══════════════════════════════════════════════════════════════════════════════
def calcular_desempenho(cfg: dict, nome: str, versao: str):
    preds = load_janela(cfg["tabela_predicoes"], CURRENT_DAYS)
    if cfg.get("mlflow_model") and not preds.empty:
        # Só as previsões do champion atual: após um retreino, o erro do modelo antigo não conta
        preds = preds[preds["versao_modelo"].astype(str) == versao.lstrip("v")]
    n_previsoes = len(preds)
    metricas = {"n_previsoes": float(n_previsoes), "mape_limite": float(cfg["mape_limite"])}

    if n_previsoes:
        real = pd.to_numeric(preds[cfg["coluna_real"]], errors="coerce")
        prev = pd.to_numeric(preds[cfg["coluna_predita"]], errors="coerce")
        ok = real.notna() & prev.notna() & (real > 0)
        real, prev = real[ok], prev[ok]
        metricas["n_com_valor_real"] = float(len(real))
        if len(real):
            erro_pct = (prev - real).abs() / real
            metricas.update({
                "mae_reais": float((prev - real).abs().mean()),
                "mape": float(erro_pct.mean()),
                "mdape": float(erro_pct.median()),
                "vies_mediano": float((prev / real - 1).median()),   # > 0: modelo superestima
            })
    else:
        metricas["n_com_valor_real"] = 0.0

    print(f"   📏 Desempenho ({CURRENT_DAYS} dias): {n_previsoes} previsões, "
          f"{int(metricas['n_com_valor_real'])} com valor real", end="")
    if "mape" in metricas:
        alerta = " ⚠️ ACIMA DO LIMITE" if metricas["mape"] > cfg["mape_limite"] else ""
        print(f" | MAE R$ {metricas['mae_reais']:,.0f} | MAPE {metricas['mape']:.1%} "
              f"(limite {cfg['mape_limite']:.0%}){alerta}")
    else:
        print(" | sem valor real para medir erro")

    if SALVAR:
        for metrica, valor in metricas.items():
            save_metric(metrica, valor, "dataset", "performance", nome, versao)


# ══════════════════════════════════════════════════════════════════════════════
# Drift das features de entrada
# ══════════════════════════════════════════════════════════════════════════════
def calcular_drift(cfg: dict, chave: str, nome: str, versao: str):
    features = cfg["features"]
    baseline_df = pd.read_parquet(os.path.join(ROOT, cfg["baseline_parquet"]))
    baseline_df.columns = baseline_df.columns.str.lower()
    baseline_df = baseline_df[features].astype(float).dropna()

    if SEED_MODE:
        current_df = baseline_df.sample(min(300, len(baseline_df)), random_state=1).copy()
        current_df[features[0]] *= np.random.uniform(0.8, 1.2, len(current_df))
    else:
        atual = load_janela(cfg["tabela_features"], CURRENT_DAYS)
        if atual.empty:
            print(f"   ⏭️  Sem dados de produção nos últimos {CURRENT_DAYS} dias — drift não calculado.")
            return
        current_df = atual[features].astype(float).dropna()

    n_atual = len(current_df)
    aviso = f"  ⚠️ amostra pequena (< {MIN_AMOSTRAS}): drift indicativo" if n_atual < MIN_AMOSTRAS else ""
    print(f"   Referência: {len(baseline_df):,} linhas | Atual: {n_atual} linhas{aviso}")

    for feature in features:
        if SALVAR:
            save_distribution_stats(feature, "baseline", calc_stats(baseline_df[feature]), nome, versao)
            save_distribution_stats(feature, "production", calc_stats(current_df[feature]), nome, versao)

    report = Report(metrics=[DataDriftPreset()])
    snapshot = report.run(
        reference_data=Dataset.from_pandas(baseline_df),
        current_data=Dataset.from_pandas(current_df),
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = os.path.join(REPORTS_DIR, f"drift_report_{chave}_{timestamp}.html")
    try:
        snapshot.save_html(html_path)
    except Exception as e:
        print(f"   ⚠️  HTML não salvo: {e}")

    # Evidently 0.7.x — estrutura do snapshot.dict():
    #   DriftedColumnsCount → value = {"count": int, "share": float}
    #   ValueDrift(column=X) → value = distância (Wasserstein normed p/ numéricas)
    drifted, scores = [], {}
    for entry in snapshot.dict().get("metrics", []):
        m_name, value, mcfg = entry.get("metric_name", ""), entry.get("value"), entry.get("config", {})

        if "DriftedColumnsCount" in m_name and isinstance(value, dict):
            share = float(value.get("share", 0.0))
            if SALVAR:
                save_metric("dataset_drift_detected", float(share >= 0.5), "dataset", "drift", nome, versao)
                save_metric("share_drifted_columns", round(share, 4), "dataset", "drift", nome, versao)
                save_metric("n_amostras_atual", float(n_atual), "dataset", "drift", nome, versao)
            print(f"   📊 Dataset drift: {share >= 0.5} ({share:.1%} — {int(value.get('count', 0))} features)")

        elif "ValueDrift" in m_name and isinstance(value, (int, float)):
            feature = mcfg.get("column", m_name)
            raw = float(value)
            score = min(round(raw, 6), 1.0)
            scores[feature] = score
            if raw >= float(mcfg.get("threshold", WASSERSTEIN_THRESHOLD)):
                drifted.append(feature)
            if SALVAR:
                save_metric("data_drift", score, feature, "drift", nome, versao)

    print(f"   {'Feature':<26}{'Drift':>10}")
    for feat, sc in sorted(scores.items(), key=lambda x: -x[1])[:8]:
        print(f"   {'⚠️ ' if feat in drifted else '  '}{feat:<24}{sc:>10.4f}")
    print(f"   Features com drift ({len(drifted)}): {drifted}  |  HTML: {os.path.basename(html_path)}")


# ══════════════════════════════════════════════════════════════════════════════
def main():
    selecionados = sys.argv[1:] or list(config["modelos"])
    modo = "DRY RUN (sem gravar)" if DRY_RUN else ("SEED" if SEED_MODE else "produção → PostgreSQL")
    print(f"🔍 Monitoramento [{modo}] — janela de {CURRENT_DAYS} dias — modelos: {selecionados}")

    falhas = []
    for chave in selecionados:
        cfg = config["modelos"][chave]
        versao = versao_do_modelo(cfg)
        print(f"\n━━ {chave}: {cfg['name']} ({versao}) ━━")
        try:
            calcular_drift(cfg, chave, cfg["name"], versao)
            if not SEED_MODE:
                calcular_desempenho(cfg, cfg["name"], versao)
        except Exception as exc:
            falhas.append(chave)
            print(f"   ❌ Erro no modelo {chave}: {exc}")

    print(f"\n{'✅ Monitoramento concluído' if not falhas else f'⚠️ Concluído com falhas em: {falhas}'}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
