"""
Funções compartilhadas pelas telas de aluguel (app_aluguel.py e batch_app_aluguel.py).
Geocoding Google · modelo do MLflow · POIs de SP · custo extra por bairro · registro para o banco.
"""

import os
import sys

import mlflow
import mlflow.sklearn
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from mlflow import MlflowClient

# Raiz do projeto no path (para importar src/ e o QuantileClipper do pipeline salvo)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.features.aluguel import carregar_pois_sp  # noqa: E402
from src.models.registro import cliente, versao_champion  # noqa: E402
# Funções puras compartilhadas com a API REST
from src.inferencia.aluguel import (custo_extra_do_bairro, features_para_monitoramento,  # noqa: E402,F401
                                    montar_registro, prever_aluguel)

MODEL_NAME = "RentPriceModel_SP"
OSM_DIR = os.path.join(ROOT, "data", "raw", "osm")
CUSTO_PATH = os.path.join(ROOT, "data", "interim", "aluguel_custo_extra_bairro.parquet")

load_dotenv()
load_dotenv(os.path.join(ROOT, ".env"))
GOOGLE_API_KEY = os.getenv("GEOCODING_MAPS")

# Rótulo da tela → valor de `type` usado no treino
TIPOS = {
    "Apartamento": "Apartamento",
    "Studio / Kitnet": "StudioOuKitchenette",
    "Casa": "Casa",
    "Casa em condomínio": "CasaCondominio",
}


# ==========================================
# Google Geocoding
# ==========================================
@st.cache_data(show_spinner=False)
def geocode_google(endereco: str):
    """Geocoding com Google Maps API (inclui o bairro, usado no custo total)"""
    if not GOOGLE_API_KEY:
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": endereco, "key": GOOGLE_API_KEY, "region": "br", "language": "pt-BR"}
    try:
        data = requests.get(url, params=params, timeout=10).json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        result = data["results"][0]
        location = result["geometry"]["location"]
        bairro = None
        for comp in result.get("address_components", []):
            if {"sublocality_level_1", "sublocality", "neighborhood"} & set(comp["types"]):
                bairro = comp["long_name"]
                break
        return {
            "lat": location["lat"],
            "lng": location["lng"],
            "endereco_formatado": result["formatted_address"],
            "bairro": bairro,
        }
    except Exception:
        return None


# ==========================================
# Recursos carregados uma vez
# ==========================================
@st.cache_resource
def _carregar_versao(versao: str):
    return mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{versao}")


@st.cache_data(ttl=60, show_spinner=False)
def _champion():
    """Versão @champion (consultada a cada minuto: um retreino promovido entra sem reiniciar a tela)."""
    v = versao_champion(MODEL_NAME, cliente())
    return v.version, MlflowClient().get_run(v.run_id).data.metrics


def carregar_modelo():
    """Modelo @champion do MLflow + métricas do run que o gerou."""
    versao, metricas = _champion()
    return _carregar_versao(versao), versao, metricas


@st.cache_resource
def carregar_pois():
    return carregar_pois_sp(OSM_DIR)


@st.cache_data
def carregar_custo_extra():
    """Tabela do notebook 01: % de condomínio + IPTU + taxas sobre o aluguel, por bairro."""
    if not os.path.exists(CUSTO_PATH):
        return None
    return pd.read_parquet(CUSTO_PATH)






