import psycopg
from config import PG_CONFIG
from psycopg.rows import dict_row, tuple_row


def get_connection(dict_rows: bool = False):
    """Cria conexão com o PostgreSQL usando configuração centralizada (PG_* no .env)"""
    return psycopg.connect(**PG_CONFIG, row_factory=dict_row if dict_rows else tuple_row)


# def salvar_predicao(dados, preco_predito, modelo, versao, erro_abs=None, erro_pct=None):
#     conn = get_connection()
#     cursor = conn.cursor()

#     query = """
#     INSERT INTO predicoes (
#         area_m2, endereco, banheiros, quartos, vagas_garagem,
#         tipo_imovel_cat, is_sobrado,
#         score_escola_privada, score_escola_publica, score_farmacia,
#         score_hospitais, score_mercado, score_parque, score_seguranca,
#         preco_anuncio, preco_predito, erro_absoluto, erro_percentual,
#         modelo, versao_modelo
#     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#     """

#     values = (
#         dados["area_m2"],
#         dados.get("endereco", "N/A"),
#         dados["banheiros"],
#         dados["quartos"],
#         dados["vagas_garagem"],
#         dados.get("tipo_imovel_cat", "casa"),
#         dados.get("is_sobrado", 0),
#         dados["score_escola_privada"],
#         dados["score_escola_publica"],
#         dados["score_farmacia"],
#         dados["score_hospitais"],
#         dados["score_mercado"],
#         dados["score_parque"],
#         dados["score_seguranca"],
#         dados.get("preco_anuncio"),
#         preco_predito,
#         erro_abs,
#         erro_pct,
#         modelo,
#         versao
#     )

#     cursor.execute(query, values)
#     conn.commit()

#     cursor.close()
#     conn.close()


def salvar_predicao(dados, preco_predito, modelo, versao, erro_abs=None, erro_pct=None):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO predicoes (
    area_m2,
    endereco,
    banheiros,
    quartos,
    vagas_garagem,
    tipo_imovel_cat,
    is_sobrado,
    score_escola_privada,
    score_escola_publica,
    score_farmacia,
    score_hospitais,
    score_mercado,
    score_parque,
    score_seguranca,
    preco_anuncio,
    preco_predito,
    erro_absoluto,
    erro_percentual,
    modelo,
    versao_modelo
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id
"""

    values = (
    dados["area_m2"],
    dados.get("endereco"),
    dados["banheiros"],
    dados["quartos"],
    dados["vagas_garagem"],
    dados["tipo_imovel_cat"],
    dados.get("is_sobrado", 0),
    dados["score_escola_privada"],
    dados["score_escola_publica"],
    dados["score_farmacia"],
    dados["score_hospitais"],
    dados["score_mercado"],
    dados["score_parque"],
    dados["score_seguranca"],
    dados.get("preco_anuncio"),
    preco_predito,
    erro_abs,
    erro_pct,
    modelo,
    versao
)

    cursor.execute(query, [_valor_sql(v) for v in values])
    predicao_id = cursor.fetchone()[0]  # 👈 ponto chave (Postgres: RETURNING id)
    conn.commit()

    cursor.close()
    conn.close()

    return predicao_id


def salvar_features_monitoramento(predicao_id, area_m2, scores):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO features_monitoramento (
        predicao_id,
        area_m2,
        score_escola_privada,
        score_escola_publica,
        score_farmacia,
        score_hospitais,
        score_mercado,
        score_parque,
        score_seguranca
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        predicao_id,
        area_m2,
        scores["score_escola_privada"],
        scores["score_escola_publica"],
        scores["score_farmacia"],
        scores["score_hospitais"],
        scores["score_mercado"],
        scores["score_parque"],
        scores["score_seguranca"]
    )

    cursor.execute(query, [_valor_sql(v) for v in values])
    conn.commit()

    cursor.close()
    conn.close()

def salvar_lote_compra(itens: list) -> list:
    """
    Grava várias previsões de compra numa única conexão/transação.
    Cada item: {"dados": ..., "preco_predito", "modelo", "versao", "erro_abs", "erro_pct", "scores": {...}}
    Mesmas colunas de salvar_predicao + salvar_features_monitoramento. Retorna os ids.
    """
    conn = get_connection()
    cursor = conn.cursor()

    q_pred = """
    INSERT INTO predicoes (
        area_m2, endereco, banheiros, quartos, vagas_garagem, tipo_imovel_cat, is_sobrado,
        score_escola_privada, score_escola_publica, score_farmacia, score_hospitais,
        score_mercado, score_parque, score_seguranca,
        preco_anuncio, preco_predito, erro_absoluto, erro_percentual, modelo, versao_modelo
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    q_feat = """
    INSERT INTO features_monitoramento (
        predicao_id, area_m2, score_escola_privada, score_escola_publica, score_farmacia,
        score_hospitais, score_mercado, score_parque, score_seguranca
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    ids = []
    try:
        for item in itens:
            d, sc = item["dados"], item["scores"]
            cursor.execute(q_pred, [_valor_sql(v) for v in (
                d["area_m2"], d.get("endereco"), d["banheiros"], d["quartos"], d["vagas_garagem"],
                d["tipo_imovel_cat"], d.get("is_sobrado", 0),
                d["score_escola_privada"], d["score_escola_publica"], d["score_farmacia"],
                d["score_hospitais"], d["score_mercado"], d["score_parque"], d["score_seguranca"],
                d.get("preco_anuncio"), item["preco_predito"], item["erro_abs"], item["erro_pct"],
                item["modelo"], item["versao"],
            )])
            predicao_id = cursor.fetchone()[0]
            cursor.execute(q_feat, [_valor_sql(v) for v in (
                predicao_id, d["area_m2"], sc["score_escola_privada"], sc["score_escola_publica"],
                sc["score_farmacia"], sc["score_hospitais"], sc["score_mercado"],
                sc["score_parque"], sc["score_seguranca"],
            )])
            ids.append(predicao_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return ids


# ============================================================
# Projeto aluguel (São Paulo) — tabelas em db/conf_aluguel.sql
# ============================================================

COLS_PREDICAO_ALUGUEL = [
    "endereco", "bairro", "latitude", "longitude",
    "tipo_imovel_cat", "area", "bedrooms", "bathrooms", "suites", "parkingSpaces",
    "mobiliado", "am_ar_condicionado", "inst_piscina", "inst_academia", "am_varanda",
    "aluguel_anuncio", "aluguel_predito", "pct_custo_extra", "custo_total_estimado",
    "erro_absoluto", "erro_percentual", "modelo", "versao_modelo", "origem",
]


def _valor_sql(v):
    """numpy/pandas → tipos nativos (o driver não aceita np.int64); NaN → NULL."""
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v != v:
        return None
    return v


def salvar_predicao_aluguel(dados: dict) -> int:
    """Insere uma previsão de aluguel. ``dados`` usa as chaves de COLS_PREDICAO_ALUGUEL."""
    conn = get_connection()
    cursor = conn.cursor()

    colunas = ", ".join(COLS_PREDICAO_ALUGUEL)
    marcadores = ", ".join(["%s"] * len(COLS_PREDICAO_ALUGUEL))
    query = f"INSERT INTO predicoes_aluguel ({colunas}) VALUES ({marcadores}) RETURNING id"

    cursor.execute(query, [_valor_sql(dados.get(c)) for c in COLS_PREDICAO_ALUGUEL])
    predicao_id = cursor.fetchone()[0]
    conn.commit()

    cursor.close()
    conn.close()

    return predicao_id


def salvar_features_monitoramento_aluguel(predicao_id: int, features: dict):
    """Grava as features numéricas que entraram no modelo (NUM_FEATURES)."""
    conn = get_connection()
    cursor = conn.cursor()

    nomes = list(features)
    query = (
        f"INSERT INTO features_monitoramento_aluguel (predicao_id, {', '.join(nomes)}) "
        f"VALUES (%s, {', '.join(['%s'] * len(nomes))})"
    )

    cursor.execute(query, [predicao_id, *[_valor_sql(float(features[n])) for n in nomes]])
    conn.commit()

    cursor.close()
    conn.close()
