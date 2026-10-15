"""
prometheus_exporter.py
======================
Serviço que expõe métricas de monitoramento do modelo na porta 8007.
O Prometheus faz scrape periodicamente deste endpoint.

Métricas expostas:
  - feature_drift_score{feature, modelo, versao}  → drift score por feature
  - dataset_drift_detected{modelo, versao}         → 1.0 se dataset driftou
  - share_drifted_columns{modelo, versao}          → proporção de features driftadas
  - last_drift_run_timestamp                       → unix timestamp da última execução

Uso:
    python monitoring/exporters/prometheus_exporter.py
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

from prometheus_client import Gauge, start_http_server
from psycopg import sql

from monitoring.db.postgres import get_connection as _pg_connection

# ─── Configurações ────────────────────────────────────────────────────────────
PORT           = int(os.getenv("EXPORTER_PORT", 8007))
POLL_INTERVAL  = int(os.getenv("EXPORTER_POLL_SECONDS", 60))   # segundos entre coletas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXPORTER] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ─── Definição das métricas Prometheus ───────────────────────────────────────
feature_drift_gauge = Gauge(
    "feature_drift_score",
    "Drift score por feature (Evidently KS / PSI)",
    ["feature", "modelo", "versao"],
)

dataset_drift_gauge = Gauge(
    "dataset_drift_detected",
    "1.0 se o dataset inteiro driftou, 0.0 caso contrário",
    ["modelo", "versao"],
)

share_drifted_gauge = Gauge(
    "share_drifted_columns",
    "Proporção de features com drift detectado",
    ["modelo", "versao"],
)

last_run_gauge = Gauge(
    "last_drift_run_timestamp",
    "Unix timestamp da última vez que o job de drift foi executado",
)

# ── Métricas de distribuição (baseline vs production) ────────────────────────
distribution_mean_gauge = Gauge(
    "feature_distribution_mean",
    "Média da distribuição de uma feature",
    ["feature", "dataset_type", "modelo", "versao"],
)

distribution_std_gauge = Gauge(
    "feature_distribution_std",
    "Desvio padrão da distribuição de uma feature",
    ["feature", "dataset_type", "modelo", "versao"],
)

distribution_median_gauge = Gauge(
    "feature_distribution_median",
    "Mediana (p50) da distribuição de uma feature",
    ["feature", "dataset_type", "modelo", "versao"],
)

distribution_min_gauge = Gauge(
    "feature_distribution_min",
    "Valor mínimo da distribuição de uma feature",
    ["feature", "dataset_type", "modelo", "versao"],
)

distribution_max_gauge = Gauge(
    "feature_distribution_max",
    "Valor máximo da distribuição de uma feature",
    ["feature", "dataset_type", "modelo", "versao"],
)


# ── Desempenho real do modelo (previsões com valor de anúncio) ───────────────
performance_gauge = Gauge(
    "model_performance",
    "Desempenho do modelo na janela recente: mape, mdape, mae_reais, vies_mediano, "
    "mape_limite, n_previsoes, n_com_valor_real, n_amostras_atual",
    ["metrica", "modelo", "versao"],
)


# ── Uso do banco (contador de inserções e limites do plano gratuito do Azure) ──
banco_linhas_gauge = Gauge("banco_linhas", "Linhas por tabela do banco do app", ["tabela"])
banco_insercoes_24h_gauge = Gauge("banco_insercoes_24h", "Linhas inseridas nas últimas 24 h", ["tabela"])
banco_tamanho_gauge = Gauge("banco_tamanho_bytes", "Tamanho do banco do app em bytes")
banco_limite_gauge = Gauge("banco_limite_bytes", "Armazenamento do plano gratuito (32 GB)")
azure_horas_gauge = Gauge(
    "azure_horas_mes_max",
    "Horas do servidor no mês, supondo ligado desde a criação (teto conservador)",
)
azure_horas_limite_gauge = Gauge("azure_horas_limite", "Horas gratuitas de B1ms por mês")

TABELAS_BANCO = [
    "predicoes", "features_monitoramento", "predicoes_aluguel", "features_monitoramento_aluguel",
    "metrics_monitoramento", "distribution_stats", "retreinos_modelo", "pois",
]
LIMITE_ARMAZENAMENTO = 32 * 1024 ** 3
LIMITE_HORAS = 750


def coletar_uso_banco() -> None:
    """Contador de inserções e consumo frente aos limites gratuitos do Azure."""
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for tabela in TABELAS_BANCO:
                    cur.execute(
                        sql.SQL("SELECT COUNT(*) AS total, COUNT(*) FILTER "
                                "(WHERE created_at >= NOW() - INTERVAL '24 hours') AS dia FROM {}"
                                ).format(sql.Identifier(tabela))
                    )
                    r = cur.fetchone()
                    banco_linhas_gauge.labels(tabela=tabela).set(r["total"])
                    banco_insercoes_24h_gauge.labels(tabela=tabela).set(r["dia"])
                cur.execute("SELECT pg_database_size(current_database()) AS bytes")
                banco_tamanho_gauge.set(cur.fetchone()["bytes"])
        banco_limite_gauge.set(LIMITE_ARMAZENAMENTO)

        criado = os.getenv("AZURE_PG_CRIADO_EM")
        if os.getenv("BANCO_APP", "local").lower() == "azure" and criado:
            agora = datetime.now(timezone.utc)
            inicio = max(datetime.fromisoformat(criado.replace("Z", "+00:00")),
                         agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
            azure_horas_gauge.set((agora - inicio).total_seconds() / 3600)
            azure_horas_limite_gauge.set(LIMITE_HORAS)
        log.info("Uso do banco coletado (%d tabelas).", len(TABELAS_BANCO))
    except Exception as exc:
        log.error("Erro ao coletar uso do banco: %s", exc)


# ─── Lógica de coleta ─────────────────────────────────────────────────────────
def _get_connection():
    return _pg_connection()   # PostgreSQL, linhas como dict


def collect_and_expose() -> None:
    """
    Lê as métricas mais recentes de `metrics_monitoramento` e atualiza
    os gauges do Prometheus.
    """
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                # ── Feature drift (última leitura por feature/modelo/versão) ──
                cur.execute(
                    """
                    SELECT m.feature_name, m.metric_name, m.metric_value,
                           m.modelo, m.versao_modelo, m.created_at AS ts
                    FROM metrics_monitoramento m
                    INNER JOIN (
                        SELECT feature_name, metric_name, modelo, versao_modelo,
                               MAX(created_at) AS max_ts
                        FROM metrics_monitoramento
                        WHERE metric_name IN (
                            'data_drift', 'dataset_drift_detected', 'share_drifted_columns'
                        )
                        GROUP BY feature_name, metric_name, modelo, versao_modelo
                    ) latest
                        ON  COALESCE(m.feature_name, '')  = COALESCE(latest.feature_name, '')
                        AND m.metric_name                 = latest.metric_name
                        AND COALESCE(m.modelo, '')        = COALESCE(latest.modelo, '')
                        AND COALESCE(m.versao_modelo, '') = COALESCE(latest.versao_modelo, '')
                        AND m.created_at                  = latest.max_ts
                    WHERE m.metric_name IN (
                        'data_drift', 'dataset_drift_detected', 'share_drifted_columns'
                    )
                    ORDER BY m.created_at DESC
                    LIMIT 500
                    """
                )
                rows = cur.fetchall()

        last_ts = None

        for row in rows:
            modelo  = row["modelo"] or "unknown"
            versao  = row["versao_modelo"] or "unknown"
            val     = float(row["metric_value"])
            ts      = row["ts"]

            if last_ts is None or (ts and ts > last_ts):
                last_ts = ts

            if row["metric_name"] == "data_drift":
                feature_drift_gauge.labels(
                    feature=row["feature_name"],
                    modelo=modelo,
                    versao=versao,
                ).set(val)

            elif row["metric_name"] == "dataset_drift_detected":
                dataset_drift_gauge.labels(modelo=modelo, versao=versao).set(val)

            elif row["metric_name"] == "share_drifted_columns":
                share_drifted_gauge.labels(modelo=modelo, versao=versao).set(val)

        if last_ts is not None:
            last_run_gauge.set(last_ts.timestamp() if hasattr(last_ts, "timestamp") else float(last_ts))

        log.info("Métricas de drift coletadas: %d registros.", len(rows))

        # ── Estatísticas de distribuição (latest por feature/tipo/modelo) ────
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT d.feature_name, d.dataset_type, d.mean_value,
                               d.std_value, d.min_value, d.max_value, d.p50_value,
                               d.modelo, d.versao_modelo
                        FROM distribution_stats d
                        INNER JOIN (
                            SELECT feature_name, dataset_type, modelo, versao_modelo,
                                   MAX(created_at) AS max_ts
                            FROM distribution_stats
                            GROUP BY feature_name, dataset_type, modelo, versao_modelo
                        ) latest
                            ON  d.feature_name    = latest.feature_name
                            AND d.dataset_type    = latest.dataset_type
                            AND COALESCE(d.modelo, '') = COALESCE(latest.modelo, '')
                            AND COALESCE(d.versao_modelo, '') = COALESCE(latest.versao_modelo, '')
                            AND d.created_at      = latest.max_ts
                        ORDER BY d.created_at DESC
                        LIMIT 500
                        """
                    )
                    dist_rows = cur.fetchall()

            for row in dist_rows:
                feature = row["feature_name"]
                dtype = row["dataset_type"]
                modelo = row["modelo"] or "unknown"
                versao = row["versao_modelo"] or "unknown"

                if row["mean_value"] is not None:
                    distribution_mean_gauge.labels(
                        feature=feature, dataset_type=dtype, modelo=modelo, versao=versao
                    ).set(float(row["mean_value"]))
                
                if row["std_value"] is not None:
                    distribution_std_gauge.labels(
                        feature=feature, dataset_type=dtype, modelo=modelo, versao=versao
                    ).set(float(row["std_value"]))
                
                if row["p50_value"] is not None:
                    distribution_median_gauge.labels(
                        feature=feature, dataset_type=dtype, modelo=modelo, versao=versao
                    ).set(float(row["p50_value"]))
                
                if row["min_value"] is not None:
                    distribution_min_gauge.labels(
                        feature=feature, dataset_type=dtype, modelo=modelo, versao=versao
                    ).set(float(row["min_value"]))
                
                if row["max_value"] is not None:
                    distribution_max_gauge.labels(
                        feature=feature, dataset_type=dtype, modelo=modelo, versao=versao
                    ).set(float(row["max_value"]))

            log.info("Estatísticas de distribuição coletadas: %d registros.", len(dist_rows))
        
        except Exception as exc_dist:
            log.error("Erro ao coletar estatísticas de distribuição: %s", exc_dist)

        # ── Desempenho (última leitura por métrica/modelo/versão) ────────────
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT DISTINCT ON (metric_name, modelo, versao_modelo)
                               metric_name, metric_value, modelo, versao_modelo
                        FROM metrics_monitoramento
                        WHERE metric_type = 'performance' OR metric_name = 'n_amostras_atual'
                        ORDER BY metric_name, modelo, versao_modelo, created_at DESC
                        """
                    )
                    perf_rows = cur.fetchall()

            for row in perf_rows:
                performance_gauge.labels(
                    metrica=row["metric_name"],
                    modelo=row["modelo"] or "unknown",
                    versao=row["versao_modelo"] or "unknown",
                ).set(float(row["metric_value"]))

            log.info("Métricas de desempenho coletadas: %d registros.", len(perf_rows))

        except Exception as exc_perf:
            log.error("Erro ao coletar métricas de desempenho: %s", exc_perf)

    except Exception as exc:
        log.error("Erro ao coletar métricas do PostgreSQL: %s", exc)


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Iniciando Prometheus Exporter na porta %d ...", PORT)
    start_http_server(PORT)
    log.info("Endpoint disponível em http://0.0.0.0:%d/metrics", PORT)

    while True:
        collect_and_expose()
        coletar_uso_banco()
        time.sleep(POLL_INTERVAL)
