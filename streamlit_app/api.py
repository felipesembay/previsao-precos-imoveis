import requests

API_URL = "http://localhost:8009/predict"
API_BATCH_URL = "http://localhost:8009/predict_batch"


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
