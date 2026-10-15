"""Geocoding com a Google Maps API (chave GEOCODING_MAPS no streamlit_app/.env)."""

import os
from functools import lru_cache

import requests
from dotenv import load_dotenv

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_ROOT, "streamlit_app", ".env"))

URL = "https://maps.googleapis.com/maps/api/geocode/json"


@lru_cache(maxsize=2048)
def geocode(endereco: str) -> dict | None:
    """lat, lon, endereço formatado, bairro, cidade e UF; None se não encontrar."""
    chave = os.getenv("GEOCODING_MAPS")
    if not chave:
        raise RuntimeError("GEOCODING_MAPS não configurada no .env")
    params = {"address": endereco, "key": chave, "region": "br", "language": "pt-BR"}
    data = requests.get(URL, params=params, timeout=10).json()
    if data.get("status") != "OK" or not data.get("results"):
        return None

    resultado = data["results"][0]
    local = resultado["geometry"]["location"]
    partes = {}
    for comp in resultado.get("address_components", []):
        for tipo in comp["types"]:
            partes.setdefault(tipo, comp)
    bairro = next((partes[t]["long_name"] for t in ("sublocality_level_1", "sublocality", "neighborhood")
                   if t in partes), None)
    return {
        "lat": local["lat"],
        "lon": local["lng"],
        "endereco_formatado": resultado["formatted_address"],
        "bairro": bairro,
        "cidade": partes.get("administrative_area_level_2", {}).get("long_name"),
        "uf": partes.get("administrative_area_level_1", {}).get("short_name"),
    }
