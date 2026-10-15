"""
Consultas do painel: modelos em produção, monitoramento, retreinos, mercado e infraestrutura.
Tudo vem das mesmas fontes do Grafana (Postgres do app, MLflow, Prometheus).
"""

import os
from datetime import datetime, timezone
from functools import lru_cache

import pandas as pd
import requests
import yaml

from src.inferencia import pacote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
LIMITE_HORAS = 750
LIMITE_ARMAZENAMENTO = 32 * 1024 ** 3
DRIFT_ATENCAO, DRIFT_CRITICO = 0.10, 0.30

with open(os.path.join(ROOT, "monitoring", "config", "features.yaml")) as f:
    _CONFIG = yaml.safe_load(f)
CONFIG_MONITORAMENTO = _CONFIG["modelos"]
JANELA_DIAS = _CONFIG["time_windows"]["current_days"]  # drift antigo não aparece como atual

TABELAS_CONTADAS = ["predicoes", "features_monitoramento", "predicoes_aluguel",
                    "features_monitoramento_aluguel", "metrics_monitoramento", "distribution_stats",
                    "retreinos_modelo", "pois"]

ACHADOS_ALUGUEL = [
    {"titulo": "Central não é o mesmo que nobre", "valor": "~4 km",
     "descricao": "O R$/m² não é máximo na Praça da Sé: o pico fica a cerca de 4 km, "
                  "no eixo Pinheiros–Vila Mariana–Itaim."},
    {"titulo": "Variação entre regiões", "valor": "5,2×",
     "descricao": "O R$/m² mediano da região mais cara é 5,2 vezes o da mais barata."},
    {"titulo": "Área tem retorno decrescente", "valor": "+6,3%",
     "descricao": "Cada 10% a mais de área eleva o aluguel em cerca de 6,3%."},
    {"titulo": "Metrô por perto", "valor": "+19%",
     "descricao": "Imóveis a até 300 m de uma estação custam ~19% mais que outros da mesma região; "
                  "o efeito cai para ~5% entre 1,5 e 2 km."},
    {"titulo": "Mobiliado", "valor": "+14%",
     "descricao": "Parece +42% na comparação simples; com mesmo tamanho e região, o efeito é de +14%."},
    {"titulo": "Custo total", "valor": "+23,6%",
     "descricao": "Condomínio, IPTU e taxas somam, na mediana, 23,6% sobre o aluguel."},
]


def _iso(ts) -> str:
    return pd.Timestamp(ts).tz_localize("UTC").isoformat() if pd.Timestamp(ts).tzinfo is None \
        else pd.Timestamp(ts).isoformat()


# ── Modelos ────────────────────────────────────────────────────────────────────
def modelos(servico_aluguel, servico_compra) -> list[dict]:
    """Modelos em produção (do MLflow localmente; do pacote de deploy na nuvem)."""
    def info(chave, nome, meta):
        return {"chave": chave, "nome": nome, "versao": f"v{meta['versao']}",
                "treinado_em": meta["treinado_em"], "n_treino": meta["n_treino"], "metricas": meta["metricas"]}

    return [info("aluguel", "RentPriceModel_SP", servico_aluguel.info()),
            info("compra", "RealEstatePriceModel", servico_compra.meta)]


# ── Monitoramento ──────────────────────────────────────────────────────────────
def _alertas_prometheus(nome_modelo: str) -> list[dict]:
    try:
        dados = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=3).json()["data"]["alerts"]
    except Exception:
        return []
    return [
        {"nome": a["labels"]["alertname"] + (f" ({a['labels']['feature']})" if "feature" in a["labels"] else ""),
         "severidade": a["labels"].get("severity", "warning"),
         "desde": a.get("activeAt", ""),
         "resumo": a.get("annotations", {}).get("summary", "")}
        for a in dados
        if a.get("state") == "firing" and a["labels"].get("modelo") == nome_modelo
    ]


def monitoramento(conectar, chave: str, versao: str) -> dict:
    cfg = CONFIG_MONITORAMENTO[chave]
    nome = cfg["name"]
    with conectar() as conn:
        serie = conn.execute(
            """SELECT created_at, metric_value FROM metrics_monitoramento
               WHERE modelo = %s AND versao_modelo = %s AND metric_name = 'mape'
                 AND metric_value <> 'NaN'::float AND created_at >= NOW() - INTERVAL '30 days'
               ORDER BY created_at""", (nome, versao)).fetchall()
        drift = conn.execute(
            """SELECT DISTINCT ON (feature_name) feature_name, metric_value FROM metrics_monitoramento
               WHERE modelo = %s AND metric_name = 'data_drift'
                 AND created_at >= NOW() - make_interval(days => %s)
               ORDER BY feature_name, created_at DESC""", (nome, JANELA_DIAS)).fetchall()
        n = conn.execute(
            """SELECT metric_value FROM metrics_monitoramento
               WHERE modelo = %s AND metric_name = 'n_amostras_atual'
                 AND created_at >= NOW() - make_interval(days => %s)
               ORDER BY created_at DESC LIMIT 1""", (nome, JANELA_DIAS)).fetchone()

    def status(score):
        return "critico" if score >= DRIFT_CRITICO else ("atencao" if score >= DRIFT_ATENCAO else "ok")

    return {
        "mape_serie": [{"data": _iso(r["created_at"]), "mape": r["metric_value"]} for r in serie],
        "mape_limite": cfg["mape_limite"],
        "drift": sorted(({"feature": r["feature_name"], "score": r["metric_value"],
                          "status": status(r["metric_value"])} for r in drift),
                        key=lambda d: -d["score"]),
        "n_amostras": int(n["metric_value"]) if n else 0,
        "alertas": _alertas_prometheus(nome),
    }


# ── Retreinos ──────────────────────────────────────────────────────────────────
def retreinos(conectar) -> list[dict]:
    with conectar() as conn:
        linhas = conn.execute("SELECT * FROM retreinos_modelo ORDER BY created_at DESC").fetchall()
    return [{
        "data": _iso(r["created_at"]),
        "versao_challenger": f"v{r['versao_challenger']}",
        "versao_champion": f"v{r['versao_champion']}" if r["versao_champion"] else None,
        "mape_challenger": r["mape_challenger"],
        "mape_champion": r["mape_champion"],
        "promovido": r["promovido"],
        "motivo": r["motivo"] or "",
    } for r in linhas]


# ── Mercado ────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def regioes_aluguel() -> list[dict]:
    """R$/m² por região (base limpa do notebook 01), regiões com ≥ 30 anúncios."""
    if pacote.ativo():  # na nuvem: agregado já calculado (os anúncios não vão para o deploy)
        return pacote.ler_json("regioes_aluguel.json")
    df = pd.read_parquet(os.path.join(ROOT, "data", "interim", "aluguel_sp_clean.parquet"),
                         columns=["regionName", "lat", "lon", "rent", "rent_m2"])
    g = (df.groupby("regionName")
           .agg(n=("rent", "size"), lat=("lat", "median"), lon=("lon", "median"),
                m2=("rent_m2", "median"), rent=("rent", "median"))
           .query("n >= 30").sort_values("m2", ascending=False))
    return [{"nome": nome, "lat": round(r.lat, 6), "lon": round(r.lon, 6), "n_anuncios": int(r.n),
             "aluguel_m2_mediano": round(r.m2, 2), "aluguel_mediano": round(r.rent, 2)}
            for nome, r in g.iterrows()]


# ── Infraestrutura ─────────────────────────────────────────────────────────────
def uso_infra(conectar) -> dict:
    with conectar() as conn:
        tamanho = conn.execute("SELECT pg_database_size(current_database()) AS b").fetchone()["b"]
        insercoes = previsoes = 0
        for t in TABELAS_CONTADAS:
            r = conn.execute(f"""SELECT COUNT(*) AS total,
                                        COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS dia
                                 FROM {t}""").fetchone()
            insercoes += r["dia"]
            if t in ("predicoes", "predicoes_aluguel"):
                previsoes += r["total"]

    horas = None
    criado = os.getenv("AZURE_PG_CRIADO_EM")
    if os.getenv("BANCO_APP", "local").lower() == "azure" and criado:
        agora = datetime.now(timezone.utc)
        inicio = max(datetime.fromisoformat(criado.replace("Z", "+00:00")),
                     agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        horas = round((agora - inicio).total_seconds() / 3600, 2)

    return {"horas_mes": horas, "horas_limite": LIMITE_HORAS, "banco_bytes": int(tamanho),
            "banco_limite_bytes": LIMITE_ARMAZENAMENTO, "insercoes_24h": int(insercoes),
            "previsoes_total": int(previsoes)}
