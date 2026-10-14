"""
Peças compartilhadas pelas DAGs.

O Airflow só orquestra: cada etapa de ML roda num container da imagem do projeto
(imoveis-app:dev, a mesma das telas e da API), com o repositório montado no mesmo
caminho absoluto do host — assim os caminhos gravados em mlruns/ continuam válidos
e o treino usa exatamente as mesmas versões de bibliotecas do serving.
"""

import os

import psycopg
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount
from psycopg.rows import dict_row

PROJETO_DIR = os.environ["PROJETO_DIR"]
IMAGEM_APP = "imoveis-app:dev"
REDE = "imoveis_imoveis"

PG = {
    "host": "postgres",
    "port": 5432,
    "dbname": os.getenv("PG_DB", "imoveis"),
    "user": os.environ["PG_USER"],
    "password": os.environ["PG_PASSWORD"],
}


def tarefa_docker(task_id: str, command: list[str], **kwargs) -> DockerOperator:
    """Roda ``command`` na imagem do projeto, dentro da rede do compose (acessa o Postgres)."""
    return DockerOperator(
        task_id=task_id,
        image=IMAGEM_APP,
        command=command,
        docker_url="unix://var/run/docker.sock",
        network_mode=REDE,
        mounts=[Mount(source=PROJETO_DIR, target=PROJETO_DIR, type="bind")],
        working_dir=PROJETO_DIR,
        # Mesmo usuário do host: arquivos criados em mlruns/ e data/ não ficam como root
        user=f"{os.getenv('HOST_UID', '1000')}:{os.getenv('HOST_GID', '1000')}",
        environment={
            "PG_HOST": "postgres",
            "PG_PORT": "5432",
            "PG_DB": PG["dbname"],
            "PG_USER": PG["user"],
            "HOME": "/tmp",
            "USER": "airflow",                # o UID do host não existe no /etc/passwd da imagem
            "GIT_PYTHON_REFRESH": "quiet",    # imagem sem git: o MLflow só não registra o SHA
            "PYTHONUNBUFFERED": "1",
        },
        private_environment={"PG_PASSWORD": PG["password"]},
        auto_remove="success",
        mount_tmp_dir=False,
        **kwargs,
    )


def consultar(query: str, params=None) -> list[dict]:
    with psycopg.connect(row_factory=dict_row, **PG) as conn:
        return conn.execute(query, params).fetchall()
