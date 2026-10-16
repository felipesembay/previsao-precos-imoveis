"""Geocoding com a Google Maps API (chave GEOCODING_MAPS no streamlit_app/.env)."""

import datetime
import os
import threading
from functools import lru_cache

import requests
from dotenv import load_dotenv

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_ROOT, "streamlit_app", ".env"))

URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Teto de chamadas pagas ao Google por dia (a API é pública; o cache não conta)
LIMITE_DIA = int(os.getenv("LIMITE_GEOCODING_DIA", "300"))
_uso = {"dia": None, "chamadas": 0}
_lock = threading.Lock()


class LimiteGeocodingExcedido(RuntimeError):
    pass


def _registrar_chamada():
    with _lock:
        hoje = datetime.date.today()
        if _uso["dia"] != hoje:
            _uso.update(dia=hoje, chamadas=0)
        if _uso["chamadas"] >= LIMITE_DIA:
            raise LimiteGeocodingExcedido(f"Limite diário de {LIMITE_DIA} consultas de endereço atingido")
        _uso["chamadas"] += 1


@lru_cache(maxsize=2048)
def geocode(endereco: str) -> dict | None:
    """lat, lon, endereço formatado, bairro, cidade e UF; None se não encontrar."""
    # Tolera a chave colada com aspas/espaços no painel do provedor (erro comum ao copiar do .env)
    chave = (os.getenv("GEOCODING_MAPS") or "").strip().strip("\"'").strip()
    if not chave:
        raise RuntimeError("GEOCODING_MAPS não configurada no .env")
    _registrar_chamada()
    params = {"address": endereco, "key": chave, "region": "br", "language": "pt-BR"}
    data = requests.get(URL, params=params, timeout=10).json()
    status = data.get("status")
    if status == "ZERO_RESULTS" or (status == "OK" and not data.get("results")):
        return None  # endereço não existe: cacheado como None
    if status != "OK":
        # Chave inválida, cota, etc.: erro de configuração, não "endereço não encontrado" (e não vai para o cache)
        raise RuntimeError(f"Geocoding {status}: {data.get('error_message', '')}")

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
