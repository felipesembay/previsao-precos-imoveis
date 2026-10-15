"""Limite de requisições por IP para os endpoints que consomem geocoding (API pública)."""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

POR_MINUTO = int(os.getenv("LIMITE_PREVISOES_MINUTO", "15"))
_janelas: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def ip_cliente(request: Request) -> str:
    # Atrás do proxy do Render, o IP real vem no X-Forwarded-For
    encaminhado = request.headers.get("x-forwarded-for")
    return encaminhado.split(",")[0].strip() if encaminhado else (request.client.host if request.client else "?")


def limitar_por_ip(request: Request, custo: int = 1):
    """Janela deslizante de 60 s; `custo` > 1 para o lote (uma unidade por linha, até o limite)."""
    agora = time.monotonic()
    ip = ip_cliente(request)
    with _lock:
        janela = _janelas[ip]
        while janela and agora - janela[0] > 60:
            janela.popleft()
        if len(janela) + min(custo, POR_MINUTO) > POR_MINUTO:
            raise HTTPException(429, "Muitas consultas seguidas. Aguarde um minuto e tente de novo.")
        janela.extend([agora] * min(custo, POR_MINUTO))
