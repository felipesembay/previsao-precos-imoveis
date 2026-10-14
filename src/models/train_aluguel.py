"""
Treinamento do modelo de aluguel (São Paulo capital) com MLflow tracking + Optuna.
Mesma estrutura de src/models/train.py (projeto de compra) e do notebook aluguel/06_modelagem.

Uso:
    cd /home/felipe/Projeto/Portfolio/Portfolio2/Regression_PriceHouse
    python -m src.models.train_aluguel
    python -m src.models.train_aluguel --dados data/interim/X.parquet --trials 100   # retreino (Airflow)

A versão nova entra no Model Registry sem alias; quem decide se ela vira
@champion é src/models/promover_aluguel.py.

O que o MLflow registra:
  - Parâmetros do Optuna (best_params)
  - Métricas em log (R², RMSE, MAE, MAPE) e em R$ (MAE, MAPE)
  - Artefatos: pipeline completo (preprocessor + modelo)
  - Model Registry: RentPriceModel_SP
"""

import argparse
import os
import sys

# Garantir que a raiz do projeto está no sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import mlflow
import mlflow.sklearn
import numpy as np
import optuna
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (mean_absolute_error,
                             mean_absolute_percentage_error,
                             mean_squared_error, r2_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor

from src.features.aluguel import CAT_FEATURES, NUM_FEATURES, TARGET, prepare_dataset
from src.preprocessing.clean import build_preprocessor

# ============================================================
# CONFIG
# ============================================================

DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "interim", "aluguel_sp_features.parquet"
)
EXPERIMENT_NAME = "aluguel_sp"
MODEL_NAME = "RentPriceModel_SP"
RANDOM_STATE = 42
N_TRIALS = 250
TEST_SIZE = 0.2
# n_jobs=-1 deixa o XGBoost ~30x mais lento nesta máquina (threads disputando núcleos)
N_JOBS = 8


# ============================================================
# MÉTRICAS
# ============================================================

def eval_metrics(y_true, y_pred) -> dict:
    """Métricas na escala do log (como no compra) e em R$ (exp)."""
    real, prev = np.exp(y_true), np.exp(y_pred)
    return {
        "r2": r2_score(y_true, y_pred),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": mean_absolute_error(y_true, y_pred),
        "mape": mean_absolute_percentage_error(y_true, y_pred),
        "mae_reais": mean_absolute_error(real, prev),
        "mape_reais": mean_absolute_percentage_error(real, prev),
    }


# ============================================================
# OPTUNA OBJECTIVE
# ============================================================

def make_objective(X_train, X_test, y_train, y_test):
    """Retorna a função objective para o Optuna."""

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 1.0),
            "random_state": RANDOM_STATE,
            "n_jobs": N_JOBS,
            "objective": "reg:squarederror",
        }

        pipe = Pipeline(steps=[
            ("preprocessor", build_preprocessor(NUM_FEATURES, CAT_FEATURES)),
            ("model", XGBRegressor(**params)),
        ])

        pipe.fit(X_train, y_train)
        preds = pipe.predict(X_test)
        return np.sqrt(mean_squared_error(y_test, preds))

    return objective


# ============================================================
# MAIN
# ============================================================

def main(data_path: str = DATA_PATH, n_trials: int = N_TRIALS) -> str:
    """Treina, registra no MLflow e devolve a versão criada no Model Registry."""
    data_path = os.path.abspath(data_path)

    # ---- 1. Preparar dados ----
    print(f"📦 Carregando e preparando dados: {data_path}")
    df = prepare_dataset(data_path)

    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    print(f"   Treino: {len(X_train)} | Teste: {len(X_test)}")

    # ---- 2. Optuna ----
    print(f"\n🔍 Iniciando otimização com Optuna ({n_trials} trials)...")

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(
        make_objective(X_train, X_test, y_train, y_test),
        n_trials=n_trials,
    )

    best_params = study.best_params
    print(f"   Melhor RMSE: {study.best_value:.4f}")
    print(f"   Melhores params: {best_params}")

    # ---- 3. Treinar modelo final ----
    print("\n🏗️  Treinando modelo final com melhores hiperparâmetros...")

    final_model = XGBRegressor(
        **best_params,
        random_state=RANDOM_STATE,
        n_jobs=N_JOBS,
        objective="reg:squarederror",
    )

    final_pipeline = Pipeline(steps=[
        ("preprocessor", build_preprocessor(NUM_FEATURES, CAT_FEATURES)),
        ("model", final_model),
    ])

    final_pipeline.fit(X_train, y_train)
    y_pred = final_pipeline.predict(X_test)
    metrics = eval_metrics(y_test, y_pred)

    print("\n📊 Métricas finais:")
    for k, v in metrics.items():
        print(f"   {k}: {v:.4f}")

    # ---- 4. Baseline (Regressão Linear) ----
    baseline_pipe = Pipeline(steps=[
        ("preprocessor", build_preprocessor(NUM_FEATURES, CAT_FEATURES)),
        ("model", LinearRegression()),
    ])
    baseline_pipe.fit(X_train, y_train)
    y_pred_base = baseline_pipe.predict(X_test)
    baseline_metrics = eval_metrics(y_test, y_pred_base)

    print("\n📏 Baseline (Linear Regression):")
    for k, v in baseline_metrics.items():
        print(f"   {k}: {v:.4f}")

    # ---- 5. MLflow Logging ----
    print(f"\n📝 Registrando no MLflow (experiment: {EXPERIMENT_NAME})...")

    # Tracking URI absoluto — mlruns/ sempre na raiz do projeto
    _mlruns_dir = os.path.join(_PROJECT_ROOT, "mlruns")
    mlflow.set_tracking_uri(f"file:{_mlruns_dir}")
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="xgboost_optuna_final") as run:

        # Parâmetros
        mlflow.log_params(best_params)
        mlflow.log_param("n_trials_optuna", n_trials)
        # Relativo à raiz: o promotor e o baseline de drift refazem o mesmo split a partir dele
        mlflow.log_param("data_path", os.path.relpath(data_path, _PROJECT_ROOT))
        mlflow.log_param("test_size", TEST_SIZE)
        mlflow.log_param("random_state", RANDOM_STATE)
        mlflow.log_param("num_features", NUM_FEATURES)
        mlflow.log_param("cat_features", CAT_FEATURES)
        mlflow.log_param("target", TARGET)
        mlflow.log_param("n_train", len(X_train))
        mlflow.log_param("n_test", len(X_test))

        # Métricas
        mlflow.log_metric("optuna_best_rmse", study.best_value)
        mlflow.log_metrics(metrics)
        mlflow.log_metrics({f"baseline_{k}": v for k, v in baseline_metrics.items()})

        # Pipeline completo (preprocessor + modelo)
        mlflow.sklearn.log_model(
            final_pipeline,
            artifact_path="model",
            registered_model_name=MODEL_NAME,
            input_example=X_test.head(5),
        )

        # Dataset info
        mlflow.log_param("dataset_rows", len(df))
        mlflow.log_param("dataset_cols", len(df.columns))

        run_id = run.info.run_id
        print(f"   Run ID: {run_id}")

    versao = mlflow.MlflowClient().search_model_versions(f"run_id='{run_id}'")[0].version
    print(f"\n✅ Modelo registrado como '{MODEL_NAME}' v{versao} no MLflow!")
    print("   Para ver a UI: mlflow ui --port 5000")
    return versao


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dados", default=DATA_PATH, help="parquet de features (saída do notebook 05 ou do pipeline)")
    parser.add_argument("--trials", type=int, default=N_TRIALS, help="trials do Optuna")
    args = parser.parse_args()
    main(args.dados, args.trials)
