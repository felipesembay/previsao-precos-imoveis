"""
Conexão com o banco `imoveis`, em um lugar só (telas, API, monitoramento, scripts).

BANCO_APP no streamlit_app/.env escolhe onde ficam os dados do app:
  local  Postgres do docker-compose (PG_*; dentro dos containers PG_HOST=postgres)
  azure  Azure Database for PostgreSQL criado pelo Terraform (AZURE_PG_*), com SSL

Os metadados do Airflow e do Metabase ficam sempre no Postgres local.
Nos containers, mudar BANCO_APP exige recriá-los: ./infra.sh up
"""

import os

from dotenv import load_dotenv

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Execução fora do Docker: lê o .env das telas. Variáveis já definidas (compose) têm prioridade.
load_dotenv(os.path.join(_ROOT, "streamlit_app", ".env"))


def config_banco(banco: str | None = None) -> dict:
    """Parâmetros do psycopg.connect para o banco escolhido (padrão: BANCO_APP)."""
    banco = (banco or os.getenv("BANCO_APP", "local")).strip().lower()
    if banco == "azure":
        return {
            "host": os.environ["AZURE_PG_HOST"],
            "port": 5432,
            "user": os.environ["AZURE_PG_USER"],
            "password": os.environ["AZURE_PG_PASSWORD"],
            "dbname": os.getenv("AZURE_PG_DB", "imoveis"),
            "sslmode": "require",
            "connect_timeout": 10,
        }
    if banco != "local":
        raise ValueError(f"BANCO_APP inválido: {banco!r} (use local ou azure)")
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", 5432)),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
        "dbname": os.getenv("PG_DB", "imoveis"),
    }
