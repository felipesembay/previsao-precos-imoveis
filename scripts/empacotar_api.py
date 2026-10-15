"""
Gera o pacote de deploy da API (deploy/api/pacote/), lido quando MODELOS_DIR está definido.

Contém só o necessário para servir previsões fora do ambiente local:
  - modelo @champion de aluguel e modelo de compra (joblib) + métricas (meta.json)
  - R$/m² por região (agregado; os anúncios coletados não entram no pacote)
  - custo extra (condomínio + IPTU) por bairro (agregado do notebook 01)

Rode de novo sempre que um retreino promover um novo @champion:
    python scripts/empacotar_api.py
"""

import json
import os
import shutil
import sys
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import joblib  # noqa: E402
import mlflow  # noqa: E402

from api import painel  # noqa: E402
from src.inferencia.aluguel import CUSTO_PATH, ServicoAluguel  # noqa: E402
from src.inferencia.compra import ServicoCompra  # noqa: E402

SAIDA = os.path.join(ROOT, "deploy", "api", "pacote")


def salvar(chave: str, modelo, meta: dict):
    pasta = os.path.join(SAIDA, chave)
    os.makedirs(pasta, exist_ok=True)
    joblib.dump(modelo, os.path.join(pasta, "model.joblib"), compress=3)
    with open(os.path.join(pasta, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"✅ {chave}: v{meta['versao']} → {pasta}")


def main():
    mlflow.set_tracking_uri(f"file:{os.path.join(ROOT, 'mlruns')}")
    shutil.rmtree(SAIDA, ignore_errors=True)
    os.makedirs(SAIDA)

    aluguel = ServicoAluguel()
    modelo, _, _ = aluguel.modelo()
    salvar("aluguel", modelo, aluguel.info())

    # O compra lê POIs do banco só ao prever; aqui basta o modelo e as métricas
    compra = ServicoCompra(conectar=None)
    salvar("compra", compra.modelo, compra.meta)

    with open(os.path.join(SAIDA, "regioes_aluguel.json"), "w") as f:
        json.dump(painel.regioes_aluguel(), f, ensure_ascii=False)
    shutil.copy(CUSTO_PATH, os.path.join(SAIDA, os.path.basename(CUSTO_PATH)))
    print(f"✅ regiões e custo extra → {SAIDA}")


if __name__ == "__main__":
    main()
