import os

import requests

# No docker-compose: API_BASE_URL=http://api:8009. Fora do Docker: localhost.
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8009")
API_URL = f"{API_BASE_URL}/predict"
API_BATCH_URL = f"{API_BASE_URL}/predict_batch"
API_HEALTH_URL = f"{API_BASE_URL}/health"


def prever_preco(payload):
    response = requests.post(API_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def prever_precos_lote(payloads, tamanho_lote=500):
    """Uma requisição por bloco de até `tamanho_lote` imóveis (em vez de uma por imóvel)."""
    previsoes = []
    for i in range(0, len(payloads), tamanho_lote):
        response = requests.post(API_BATCH_URL, json={"imoveis": payloads[i:i + tamanho_lote]}, timeout=120)
        response.raise_for_status()
        previsoes.extend(response.json()["previsoes"])
    return previsoes
