"""
Migra o banco `imoveis` do MySQL (container mysql_oltp) para o PostgreSQL.

Uso (a partir da raiz do projeto):
    python scripts/migrar_mysql_para_postgres.py              # destino precisa estar vazio
    python scripts/migrar_mysql_para_postgres.py --sobrescrever  # apaga os dados do destino e copia de novo

Conexões: DB_* (MySQL) e PG_* (PostgreSQL) do streamlit_app/.env, via streamlit_app/config.py.
Para migrar para o Azure depois, basta apontar PG_* para o servidor do Azure e rodar de novo.
"""

import argparse
import os
import sys

import psycopg
import pymysql

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "streamlit_app"))
from config import DB_CONFIG, PG_CONFIG  # noqa: E402

SCHEMA = os.path.join(ROOT, "streamlit_app", "db", "schema_postgres.sql")

# Ordem respeita as chaves estrangeiras (pais antes dos filhos)
TABELAS = [
    "predicoes",
    "features_monitoramento",
    "predicoes_aluguel",
    "features_monitoramento_aluguel",
    "metrics_monitoramento",
    "pois",
    "city_metadata",
]
BOOLEANAS = {"city_metadata": {"pois_loaded"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sobrescrever", action="store_true", help="apaga os dados do destino antes de copiar")
    args = parser.parse_args()

    origem = pymysql.connect(**DB_CONFIG)
    destino = psycopg.connect(**PG_CONFIG)
    print(f"Origem : MySQL {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"Destino: PostgreSQL {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}\n")

    with destino.cursor() as cur:
        cur.execute(open(SCHEMA, encoding="utf-8").read())

        ocupadas = []
        for t in TABELAS:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            if cur.fetchone()[0]:
                ocupadas.append(t)
        if ocupadas and not args.sobrescrever:
            sys.exit(f"Destino já tem dados em {ocupadas}. Use --sobrescrever para copiar de novo.")
        if ocupadas:
            cur.execute(f"TRUNCATE {', '.join(TABELAS)} RESTART IDENTITY CASCADE")

    resumo = []
    with origem.cursor() as src, destino.cursor() as cur:
        for t in TABELAS:
            src.execute(f"SELECT * FROM `{t}`")
            colunas = [d[0] for d in src.description]
            linhas = src.fetchall()

            booleanas = BOOLEANAS.get(t, set())
            if booleanas:
                idx = [i for i, c in enumerate(colunas) if c in booleanas]
                linhas = [tuple(bool(v) if i in idx and v is not None else v for i, v in enumerate(l)) for l in linhas]

            if linhas:
                cols_sql = ", ".join(colunas)          # sem aspas: parkingSpaces -> parkingspaces
                marcadores = ", ".join(["%s"] * len(colunas))
                cur.executemany(f"INSERT INTO {t} ({cols_sql}) VALUES ({marcadores})", linhas)

                # Ids foram copiados explicitamente: o contador precisa continuar depois do maior id
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT MAX(id) FROM {t}))")

            cur.execute(f"SELECT COUNT(*) FROM {t}")
            resumo.append((t, len(linhas), cur.fetchone()[0]))

    destino.commit()
    origem.close()
    destino.close()

    print(f"{'tabela':<32}{'MySQL':>8}{'Postgres':>10}")
    for t, n_src, n_dst in resumo:
        print(f"{t:<32}{n_src:>8}{n_dst:>10}{'' if n_src == n_dst else '  ⚠️ diferente'}")
    print("\n✅ Migração concluída" if all(a == b for _, a, b in resumo) else "\n⚠️ Contagens diferentes — verificar")


if __name__ == "__main__":
    main()
