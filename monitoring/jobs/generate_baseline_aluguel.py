"""
generate_baseline_aluguel.py
============================
Gera o baseline de drift do modelo de aluguel: as features exatamente como o
@champion as viu no treino (data_path e split logados no run do MLflow), em
data/processed/baseline_aluguel.parquet.

Chamado pelo promotor (src/models/promover_aluguel.py) sempre que um modelo novo
vira champion. Runs antigos sem data_path usam o dataset padrão do treino.

Uso:
    python monitoring/jobs/generate_baseline_aluguel.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

from sklearn.model_selection import train_test_split  # noqa: E402

from src.features.aluguel import NUM_FEATURES, prepare_dataset  # noqa: E402
from src.models.registro import cliente, versao_champion  # noqa: E402
from src.models.train_aluguel import DATA_PATH, MODEL_NAME, RANDOM_STATE, TEST_SIZE  # noqa: E402

OUTPUT_PATH = os.path.join(ROOT, "data/processed/baseline_aluguel.parquet")


def gerar_baseline() -> str:
    client = cliente()
    champion = versao_champion(MODEL_NAME, client)
    params = client.get_run(champion.run_id).data.params
    data_path = os.path.join(ROOT, params["data_path"]) if "data_path" in params else DATA_PATH

    print(f"📂 Baseline do {MODEL_NAME} v{champion.version}: {os.path.relpath(data_path, ROOT)}")
    df = prepare_dataset(data_path)
    X_train, _ = train_test_split(
        df[NUM_FEATURES],
        test_size=float(params.get("test_size", TEST_SIZE)),
        random_state=int(params.get("random_state", RANDOM_STATE)),
    )

    # Mesmos nomes que o Postgres devolve (identificadores sem aspas viram minúsculos)
    baseline = X_train.rename(columns=str.lower).astype(float).reset_index(drop=True)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    baseline.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Baseline salvo: {OUTPUT_PATH} — {baseline.shape[0]:,} linhas × {baseline.shape[1]} features")
    return OUTPUT_PATH


if __name__ == "__main__":
    gerar_baseline()
