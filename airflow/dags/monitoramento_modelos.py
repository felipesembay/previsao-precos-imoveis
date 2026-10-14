"""
Monitoramento de hora em hora: drift das features e desempenho real dos modelos
de compra e aluguel (monitoring/jobs/run_data_drift.py → metrics_monitoramento).
As métricas seguem para o Prometheus/Grafana pelo exporter.
"""

import pendulum
from airflow.sdk import dag

from comum import tarefa_docker


@dag(
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=5)},
    tags=["monitoramento", "compra", "aluguel"],
    doc_md=__doc__,
)
def monitoramento_modelos():
    tarefa_docker("drift_e_desempenho", ["python", "monitoring/jobs/run_data_drift.py"])


monitoramento_modelos()
