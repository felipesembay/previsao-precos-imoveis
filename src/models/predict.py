"""
Inferência do modelo registrado no MLflow.

Uso standalone (qualquer diretório):
    python -m src.models.predict
    cd src && python predict.py

Uso programático:
    from src.models.predict import load_model, predict
    model = load_model()
    resultado = predict(model, dados_dict)
"""

import os
import sys

# ============================================================
# Garantir que a raiz do projeto está no sys.path
# (necessário para desserializar o pipeline com imports de src)
# ============================================================

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd

from src.features.pipeline import CAT_FEATURES, NUM_FEATURES

# ============================================================
# Carregar modelo do MLflow
# ============================================================

def load_model(
    model_name: str = "RealEstatePriceModel",
    stage: str = None,
    run_id: str = None,
    model_path: str = None,
):
    """
    Carrega o pipeline (preprocessor + modelo) do MLflow.

    Prioridade:
      1. model_path  — caminho direto (ex: "mlruns/.../artifacts/model")
      2. run_id      — carrega de um run específico
      3. Busca automática pelo último run do experiment
    """

    if model_path:
        return mlflow.sklearn.load_model(model_path)

    if run_id:
        return mlflow.sklearn.load_model(f"runs:/{run_id}/model")

    experiment = mlflow.get_experiment_by_name("price_house_ponta_grossa_version2")
    if experiment is None:
        raise RuntimeError(
            "Experiment 'price_house_ponta_grossa_version2' não encontrado. "
            "Treine primeiro com: python -m src.models.train"
        )

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
        max_results=1,
    )

    if runs.empty:
        raise RuntimeError("Nenhum run encontrado. Treine primeiro.")

    best_run_id = runs.iloc[0]["run_id"]
    print(f"🔎 Carregando run: {best_run_id}")

    return mlflow.sklearn.load_model(f"runs:/{best_run_id}/model")


# ============================================================
# Predição
# ============================================================

def _preparar_entrada(df_input: pd.DataFrame) -> pd.DataFrame:
    """Garante as colunas esperadas pelo pipeline, na ordem do treino."""
    df_input = df_input.copy()

    # Garantias mínimas para novas features
    if "is_sobrado" not in df_input.columns:
        df_input["is_sobrado"] = 0

    if "tipo_imovel_cat" not in df_input.columns:
        df_input["tipo_imovel_cat"] = "outros"

    features = NUM_FEATURES + CAT_FEATURES

    for col in features:
        if col not in df_input.columns:
            df_input[col] = np.nan

    return df_input[features]


def predict(pipeline, data: dict) -> dict:
    """
    Recebe um dicionário com os dados de um imóvel e retorna
    o preço previsto (em reais) e o log_preco.

    Exemplo de `data`:
    {
        "quartos": 3,
        "banheiros": 2,
        "vagas_garagem": 1,
        "area_m2": 120,
        "score_escola_privada": 1.5,
        "score_escola_publica": 0.8,
        "score_hospitais": 0.6,
        "score_mercado": 1.2,
        "score_farmacia": 0.4,
        "score_parque": 0.9,
        "score_seguranca": 0.7,
        "tipo_imovel_cat": "casa",
        "is_sobrado": 0
    }
    """
    return predict_batch(pipeline, [data])[0]


def predict_batch(pipeline, dados: list) -> list:
    """Mesma lógica de `predict`, para vários imóveis numa única chamada ao modelo."""
    df_input = _preparar_entrada(pd.DataFrame(dados))
    log_precos = pipeline.predict(df_input)

    return [
        {"log_preco": float(lp), "preco_estimado": round(float(np.exp(lp)), 2)}
        for lp in log_precos
    ]


# ============================================================
# CLI
# ============================================================

def main():
    """Exemplo de uso via CLI."""

    # Tracking URI absoluto — mlruns/ sempre na raiz do projeto
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    _mlruns_dir = os.path.join(_project_root, "mlruns")
    mlflow.set_tracking_uri(f"file:{_mlruns_dir}")

    print("🔄 Carregando modelo do MLflow...")
    model = load_model()
    print("✅ Modelo carregado!\n")

    exemplo = {
        "quartos": 3,
        "banheiros": 2,
        "vagas_garagem": 2,
        "area_m2": 150,
        "score_escola_privada": 1.5,
        "score_escola_publica": 0.8,
        "score_hospitais": 0.6,
        "score_mercado": 1.2,
        "score_farmacia": 0.4,
        "score_parque": 0.9,
        "score_seguranca": 0.7,
        "tipo_imovel_cat": "casa",
        "is_sobrado": 0,
    }

    resultado = predict(model, exemplo)

    print("🏠 Dados do imóvel:")
    for k, v in exemplo.items():
        print(f"   {k}: {v}")

    print(f"\n💰 Preço estimado: R$ {resultado['preco_estimado']:,.2f}")
    print(f"   log(preço): {resultado['log_preco']:.4f}")


if __name__ == "__main__":
    main()
