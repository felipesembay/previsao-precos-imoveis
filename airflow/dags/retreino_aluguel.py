"""
Retreino automático do modelo de aluguel (RentPriceModel_SP).

Roda todo dia e só segue adiante se algum gatilho disparar:
  - **desempenho**: MAPE real acima do limite (com ≥ 10 previsões com valor de anúncio)
  - **drift**: ≥ 50% das features com drift (com ≥ 30 amostras na janela)
  - **idade**: último champion promovido há mais de 30 dias (o mercado de aluguel muda)
  - **manual**: trigger com `forcar = true`

Depois de um retreino há 7 dias de carência, para não retreinar todo dia enquanto
as métricas da janela ainda refletem o modelo antigo (`respeitar_carencia = false`
avalia os gatilhos mesmo assim — útil para testar).

Fluxo: extrair (API QuintoAndar) → preparar (limpeza + POIs + features) →
treinar (Optuna + MLflow, versão sem alias) → promover (champion × challenger
no mesmo holdout; vira @champion só se tiver MAPE menor).
"""

import pendulum
from airflow.sdk import Param, dag, get_current_context, task

from comum import consultar, tarefa_docker

MODELO = "RentPriceModel_SP"

# Mesmos critérios dos alertas do Prometheus (monitoring/docker/alerts.yml)
MIN_COM_VALOR_REAL = 10
LIMITE_SHARE_DRIFT = 0.5
MIN_AMOSTRAS_DRIFT = 30
MAX_IDADE_DIAS = 30
CARENCIA_DIAS = 7
JANELA_METRICAS_HORAS = 48

CARIMBO = "{{ dag_run.run_after.strftime('%Y%m%d_%H%M') }}"
RAW = f"data/raw/quintoandar/quintoandar_sp_{CARIMBO}.parquet"
FEATURES = f"data/interim/aluguel_sp_features_{CARIMBO}.parquet"


@dag(
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    params={
        "forcar": Param(False, type="boolean", description="Retreina mesmo sem gatilho e ignora a carência"),
        "n_trials": Param(250, type="integer", minimum=1, description="Trials do Optuna"),
        "respeitar_carencia": Param(True, type="boolean",
                                    description="Desligue para avaliar os gatilhos durante a carência"),
    },
    tags=["retreino", "aluguel"],
    doc_md=__doc__,
)
def retreino_aluguel():

    @task.short_circuit
    def avaliar_gatilhos() -> str | bool:
        """Devolve os motivos do retreino (vão para retreinos_modelo) ou False para parar a DAG."""
        params = get_current_context()["params"]
        if params["forcar"]:
            return "manual"

        ultimo = consultar(
            """SELECT EXTRACT(EPOCH FROM NOW() - created_at) / 86400 AS dias FROM retreinos_modelo
               WHERE modelo = %s ORDER BY created_at DESC LIMIT 1""", (MODELO,))
        if ultimo and ultimo[0]["dias"] < CARENCIA_DIAS and params["respeitar_carencia"]:
            print(f"Último retreino há {ultimo[0]['dias']:.1f} dias (carência de {CARENCIA_DIAS}). Nada a fazer.")
            return False

        m = {r["metric_name"]: r["metric_value"] for r in consultar(
            """SELECT DISTINCT ON (metric_name) metric_name, metric_value FROM metrics_monitoramento
               WHERE modelo = %s AND feature_name = 'dataset'
                 AND created_at >= NOW() - make_interval(hours => %s)
               ORDER BY metric_name, created_at DESC""", (MODELO, JANELA_METRICAS_HORAS))}
        print(f"Métricas recentes: {m}")

        motivos = []
        if m.get("n_com_valor_real", 0) >= MIN_COM_VALOR_REAL and m.get("mape", 0) > m.get("mape_limite", 1):
            motivos.append(f"desempenho: MAPE {m['mape']:.1%} > limite {m['mape_limite']:.0%}")
        if m.get("n_amostras_atual", 0) >= MIN_AMOSTRAS_DRIFT and m.get("share_drifted_columns", 0) >= LIMITE_SHARE_DRIFT:
            motivos.append(f"drift: {m['share_drifted_columns']:.0%} das features")

        promovido = consultar(
            """SELECT EXTRACT(EPOCH FROM NOW() - MAX(created_at)) / 86400 AS dias FROM retreinos_modelo
               WHERE modelo = %s AND promovido""", (MODELO,))[0]["dias"]
        if promovido is None:
            motivos.append("idade: modelo inicial, sem retreino registrado")
        elif promovido > MAX_IDADE_DIAS:
            motivos.append(f"idade: champion promovido há {promovido:.0f} dias")

        print(f"Gatilhos: {motivos or 'nenhum'}")
        return "; ".join(motivos) or False

    gatilhos = avaliar_gatilhos()

    extrair = tarefa_docker(
        "extrair_quintoandar",
        ["python", "-m", "src.scraping.quintoandar.client", "--saida", RAW],
        retries=2, retry_delay=pendulum.duration(minutes=10),
    )
    preparar = tarefa_docker(
        "preparar_dados",
        ["python", "-m", "src.preprocessing.aluguel", "--raw", RAW, "--saida", FEATURES],
    )
    treinar = tarefa_docker(
        "treinar_challenger",
        ["python", "-m", "src.models.train_aluguel", "--dados", FEATURES, "--trials", "{{ params.n_trials }}"],
    )
    promover = tarefa_docker(
        "avaliar_e_promover",
        ["python", "-m", "src.models.promover_aluguel", "--dataset", FEATURES,
         "--motivo", "{{ ti.xcom_pull(task_ids='avaliar_gatilhos') }}"],
    )

    gatilhos >> extrair >> preparar >> treinar >> promover


retreino_aluguel()
