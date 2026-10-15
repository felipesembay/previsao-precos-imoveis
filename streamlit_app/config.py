import os
import sys

from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "imoveis"),
    "charset": "utf8mb4",
}

# PostgreSQL: local ou Azure conforme BANCO_APP (src/config_banco.py)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.config_banco import config_banco  # noqa: E402

PG_CONFIG = config_banco()
