# Imagem de dependências das aplicações (API FastAPI + Streamlit).
# Desenvolvimento local: o código NÃO é copiado — o docker-compose monta a pasta do projeto
# no mesmo caminho absoluto do host, para os caminhos gravados no mlruns/ continuarem válidos.
# (Na fase de CI/CD/nuvem, esta imagem passa a fazer COPY do código.)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY docker/requirements-app.txt /tmp/requirements-app.txt
RUN pip install -r /tmp/requirements-app.txt
