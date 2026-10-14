"""
generate_baseline_aluguel.py
============================
Gera o baseline de drift do modelo de aluguel: as features exatamente como o modelo
as viu no treino (mesmo split de src/models/train_aluguel.py), em
data/processed/baseline_aluguel.parquet.

Uso:
    python monitoring/jobs/generate_baseline_aluguel.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

from sklearn.model_selection import train_test_split  # noqa: E402

from src.features.aluguel import NUM_FEATURES, prepare_dataset  # noqa: E402
from src.models.train_aluguel import DATA_PATH, RANDOM_STATE, TEST_SIZE  # noqa: E402

OUTPUT_PATH = os.path.join(ROOT, "data/processed/baseline_aluguel.parquet")

print("📂 Carregando dados de treino do aluguel ...")
df = prepare_dataset(DATA_PATH)

X_train, _ = train_test_split(df[NUM_FEATURES], test_size=TEST_SIZE, random_state=RANDOM_STATE)

# Mesmos nomes que o Postgres devolve (identificadores sem aspas viram minúsculos)
baseline = X_train.rename(columns=str.lower).astype(float).reset_index(drop=True)

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
baseline.to_parquet(OUTPUT_PATH, index=False)
print(f"✅ Baseline salvo: {OUTPUT_PATH} — {baseline.shape[0]:,} linhas × {baseline.shape[1]} features")
