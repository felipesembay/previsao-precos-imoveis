# Imagem enxuta da API para a nuvem (Render). Os modelos vêm do pacote em
# deploy/api/pacote (scripts/empacotar_api.py), não do MLflow.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MODELOS_DIR=/app/deploy/api/pacote \
    # xgboost com uma thread: a instância gratuita tem pouca CPU
    OMP_NUM_THREADS=1

WORKDIR /app
COPY deploy/api/requirements.txt deploy/api/requirements.txt
RUN pip install --no-cache-dir -r deploy/api/requirements.txt

# Código e dados necessários para servir (o resto do repositório fica fora)
COPY api/ api/
COPY src/ src/
COPY streamlit_app/db.py streamlit_app/config.py streamlit_app/
COPY monitoring/config/features.yaml monitoring/config/features.yaml
COPY data/raw/osm/ data/raw/osm/
COPY deploy/api/pacote/ deploy/api/pacote/

RUN useradd --create-home api && chown -R api /app
USER api

# O Render define PORT; localmente usa 8009
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8009} --proxy-headers --forwarded-allow-ips='*'"]
