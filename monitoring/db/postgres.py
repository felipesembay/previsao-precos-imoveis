import os

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row

# Execução local: lê PG_* do mesmo .env das telas. No Docker, as variáveis vêm do compose.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_ROOT, "streamlit_app", ".env"))

PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", ""),
    "dbname": os.getenv("PG_DB", "imoveis"),
    "port": int(os.getenv("PG_PORT", 5432)),
}


def get_connection():
    return psycopg.connect(row_factory=dict_row, **PG_CONFIG)


def _read_sql(query: str, params=None) -> pd.DataFrame:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return pd.DataFrame(cursor.fetchall())


def load_janela(tabela: str, dias: int) -> pd.DataFrame:
    """Linhas de `tabela` criadas nos últimos `dias` dias (colunas em minúsculas, como no Postgres)."""
    query = sql.SQL("SELECT * FROM {} WHERE created_at >= NOW() - make_interval(days => %s)").format(
        sql.Identifier(tabela)
    )
    return _read_sql(query, (int(dias),))


def save_metric(
    metric_name: str,
    metric_value: float,
    feature_name: str,
    metric_type: str,
    modelo: str,
    versao_modelo: str
):
    query = """
        INSERT INTO metrics_monitoramento (
            metric_name,
            metric_value,
            feature_name,
            metric_type,
            modelo,
            versao_modelo
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query,
                (
                    metric_name,
                    float(metric_value),
                    feature_name,
                    metric_type,
                    modelo,
                    versao_modelo
                )
            )
        conn.commit()


def save_distribution_stats(
    feature_name: str,
    dataset_type: str,  # 'baseline' ou 'production'
    stats: dict,
    modelo: str,
    versao_modelo: str
):
    """
    Salva estatísticas descritivas de uma feature.

    Args:
        feature_name: nome da feature
        dataset_type: 'baseline' ou 'production'
        stats: dict com keys: mean, std, min, max, p25, p50, p75, count
        modelo: nome do modelo
        versao_modelo: versão do modelo
    """
    query = """
        INSERT INTO distribution_stats (
            feature_name,
            dataset_type,
            mean_value,
            std_value,
            min_value,
            max_value,
            p25_value,
            p50_value,
            p75_value,
            sample_count,
            modelo,
            versao_modelo
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    def _num(v):
        return None if v is None else float(v)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query,
                (
                    feature_name,
                    dataset_type,
                    _num(stats.get('mean')),
                    _num(stats.get('std')),
                    _num(stats.get('min')),
                    _num(stats.get('max')),
                    _num(stats.get('p25')),
                    _num(stats.get('p50')),
                    _num(stats.get('p75')),
                    None if stats.get('count') is None else int(stats.get('count')),
                    modelo,
                    versao_modelo
                )
            )
        conn.commit()


def save_retreino(r: dict):
    """Uma linha em retreinos_modelo por challenger avaliado (src/models/promover_aluguel.py)."""
    colunas = ["modelo", "versao_challenger", "versao_champion", "mape_challenger", "mape_champion",
               "mae_challenger", "mae_champion", "r2_challenger", "r2_champion", "n_teste",
               "dataset", "motivo", "promovido"]
    query = sql.SQL("INSERT INTO retreinos_modelo ({}) VALUES ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, colunas)),
        sql.SQL(", ").join(sql.Placeholder() * len(colunas)),
    )
    valores = [float(r[c]) if isinstance(r.get(c), float) else r.get(c) for c in colunas]
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, valores)
        conn.commit()


def ultimo_retreino(modelo: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM retreinos_modelo WHERE modelo = %s ORDER BY created_at DESC LIMIT 1", (modelo,)
            )
            return cursor.fetchone()
