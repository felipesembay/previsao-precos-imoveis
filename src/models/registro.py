"""
Acesso ao Model Registry do MLflow (store em arquivos ./mlruns).

O modelo em produção é o que tem o alias @champion. Versões treinadas antes do
alias existir não têm alias: nesse caso vale a última versão registrada.
"""

import os

import mlflow
from mlflow import MlflowClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ALIAS_CHAMPION = "champion"


def cliente() -> MlflowClient:
    mlflow.set_tracking_uri(f"file:{os.path.join(ROOT, 'mlruns')}")
    return MlflowClient()


def versao_champion(nome: str, client: MlflowClient | None = None, excluir: str | None = None):
    """
    ModelVersion do @champion (ou a última versão, se nenhuma tiver o alias).
    ``excluir``: versão ignorada no fallback (o challenger recém-registrado). None se não houver.
    """
    client = client or cliente()
    try:
        return client.get_model_version_by_alias(nome, ALIAS_CHAMPION)
    except mlflow.exceptions.MlflowException:
        versoes = [v for v in client.search_model_versions(f"name='{nome}'") if v.version != excluir]
        return max(versoes, key=lambda v: int(v.version)) if versoes else None
