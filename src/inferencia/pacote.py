"""
Pacote de deploy da API: modelos e tabelas agregadas exportados do ambiente local.

Na nuvem (Render) não há MLflow nem os dados da coleta. A API carrega daqui:
    <MODELOS_DIR>/aluguel/model.joblib + meta.json
    <MODELOS_DIR>/compra/model.joblib  + meta.json
    <MODELOS_DIR>/regioes_aluguel.json

Gerado por scripts/empacotar_api.py a partir do @champion. Sem MODELOS_DIR, a API
usa o MLflow local (docker-compose), como antes.
"""

import json
import os

import joblib

PACOTE_DIR = os.getenv("MODELOS_DIR")


def ativo() -> bool:
    return bool(PACOTE_DIR)


def carregar_modelo(chave: str):
    """(pipeline sklearn, metadados) do modelo `chave` ("aluguel" ou "compra")."""
    pasta = os.path.join(PACOTE_DIR, chave)
    with open(os.path.join(pasta, "meta.json")) as f:
        meta = json.load(f)
    return joblib.load(os.path.join(pasta, "model.joblib")), meta


def ler_json(nome: str):
    with open(os.path.join(PACOTE_DIR, nome)) as f:
        return json.load(f)
