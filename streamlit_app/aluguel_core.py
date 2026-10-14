"""
Funções compartilhadas pelas telas de aluguel (app_aluguel.py e batch_app_aluguel.py).
Geocoding Google · modelo do MLflow · POIs de SP · custo extra por bairro · registro para o banco.
"""

import os
import sys
import unicodedata

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from mlflow import MlflowClient

# Raiz do projeto no path (para importar src/ e o QuantileClipper do pipeline salvo)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.features.aluguel import NUM_FEATURES, carregar_pois_sp  # noqa: E402
from src.models.registro import cliente, versao_champion  # noqa: E402

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


def _normalizar(txt) -> str:
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return txt.lower().strip()


def custo_extra_do_bairro(bairro, tabela):
    """Procura o bairro (sem acento) na tabela; sem correspondência, usa a mediana da cidade."""
    cidade = tabela[tabela["fonte"] == "cidade"]
    padrao = cidade.iloc[0] if len(cidade) else tabela.median(numeric_only=True)

    if bairro:
        chave = _normalizar(bairro)
        for col in ["neighbourhood", "regionName"]:
            achou = tabela[tabela[col].map(_normalizar) == chave]
            if len(achou):
                return achou.iloc[0], f"{bairro} ({achou.iloc[0]['fonte']})"
    return padrao, "mediana da cidade"


# ==========================================
# Registro para o banco
# ==========================================
def montar_registro(geo: dict, imovel: dict, entrada: pd.DataFrame, aluguel_predito: float,
                    aluguel_anuncio, pct_extra, versao_modelo, origem: str) -> dict:
    """Dicionário com as colunas de predicoes_aluguel (ver db/conf_aluguel.sql)."""
    erro_abs = erro_pct = None
    if aluguel_anuncio is not None and not pd.isna(aluguel_anuncio) and aluguel_anuncio > 0:
        erro_abs = abs(aluguel_predito - aluguel_anuncio)
        erro_pct = erro_abs / aluguel_anuncio
    else:
        aluguel_anuncio = None

    return {
        "endereco": geo.get("endereco_formatado"),
        "bairro": geo.get("bairro"),
        "latitude": geo["lat"],
        "longitude": geo["lng"],
        "tipo_imovel_cat": entrada["tipo_imovel_cat"].iloc[0],
        **{k: imovel[k] for k in ["area", "bedrooms", "bathrooms", "suites", "parkingSpaces", "mobiliado",
                                  "am_ar_condicionado", "inst_piscina", "inst_academia", "am_varanda"]},
        "aluguel_anuncio": aluguel_anuncio,
        "aluguel_predito": aluguel_predito,
        "pct_custo_extra": pct_extra,
        "custo_total_estimado": aluguel_predito * (1 + pct_extra) if pct_extra is not None else None,
        "erro_absoluto": erro_abs,
        "erro_percentual": erro_pct,
        "modelo": MODEL_NAME,
        "versao_modelo": str(versao_modelo),
        "origem": origem,
    }


def features_para_monitoramento(entrada: pd.DataFrame) -> dict:
    return {c: float(entrada[c].iloc[0]) for c in NUM_FEATURES}


def prever_aluguel(modelo, entrada: pd.DataFrame) -> np.ndarray:
    """Aluguel em R$ (o modelo prevê log do aluguel)."""
    from src.features.aluguel import CAT_FEATURES
    return np.exp(modelo.predict(entrada[NUM_FEATURES + CAT_FEATURES]))
