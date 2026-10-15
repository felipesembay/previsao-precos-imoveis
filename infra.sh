#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Inicialização da infraestrutura local (docker-compose.yml na raiz)
#
#   ./infra.sh up                 sobe todos os serviços (build da imagem na 1ª vez)
#   ./infra.sh down               para todos os serviços (dados ficam nos volumes)
#   ./infra.sh restart [serviço]  reinicia tudo ou um serviço
#   ./infra.sh status             estado dos containers e URLs
#   ./infra.sh logs <serviço>     acompanha os logs (ex.: streamlit, api, mlflow)
#   ./infra.sh build              reconstrói as imagens (após mudar dependências)
#   ./infra.sh migrar-dados       copia o banco `imoveis` do Postgres antigo para o novo
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")"
export PWD="$(pwd)"
# Containers do app e do Airflow rodam com o usuário do host; o Airflow precisa do grupo do socket do Docker
export HOST_UID="$(id -u)" HOST_GID="$(id -g)" DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
ENV_FILE="streamlit_app/.env"
COMPOSE=(docker-compose --env-file "$ENV_FILE" -f docker-compose.yml)

# Postgres de onde os dados atuais são copiados (migração MySQL → Postgres feita antes)
PG_ANTIGO="datastacktrendsanalyzer-postgres-1"

[[ -f "$ENV_FILE" ]] || { echo "❌ $ENV_FILE não encontrado (precisa de PG_USER, PG_PASSWORD, GEOCODING_MAPS)"; exit 1; }

urls() {
    cat <<EOF

  Streamlit   http://localhost:${STREAMLIT_PORT:-8502}
  API         http://localhost:8009/docs
  MLflow      http://localhost:5000
  Metabase    http://localhost:${METABASE_PORT:-3003}
  Grafana     http://localhost:3002   (admin / admin)
  Prometheus  http://localhost:9090
  Alertmanager http://localhost:9093  (e-mail: SMTP_USER/SMTP_PASSWORD/ALERT_EMAIL no .env)
  Airflow     http://localhost:${AIRFLOW_PORT:-8080}   (admin / admin)
  Postgres    localhost:5433          (banco imoveis)
EOF
}

# Containers com o mesmo nome criados pelo compose antigo (monitoring/docker) impedem o `up`
remover_containers_antigos() {
    for nome in drift_exporter prometheus grafana; do
        projeto=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$nome" 2>/dev/null || true)
        if [[ -n "$projeto" && "$projeto" != "imoveis" ]]; then
            echo "↻ removendo container antigo $nome (projeto '$projeto')"
            docker rm -f "$nome" >/dev/null
        fi
    done
}

case "${1:-}" in
    up)
        remover_containers_antigos
        # Segredo do JWT entre os componentes do Airflow (gerado uma vez, fica só no .env local)
        grep -q "^AIRFLOW_JWT_SECRET=" "$ENV_FILE" || echo "AIRFLOW_JWT_SECRET=$(openssl rand -hex 32)" >> "$ENV_FILE"
        mkdir -p airflow/logs
        docker rm -f imoveis_drift_job >/dev/null 2>&1 || true   # substituído pela DAG monitoramento_modelos
        "${COMPOSE[@]}" up -d --build
        urls
        ;;
    down)
        "${COMPOSE[@]}" down
        ;;
    restart)
        "${COMPOSE[@]}" restart ${2:-}
        ;;
    status)
        "${COMPOSE[@]}" ps
        urls
        ;;
    logs)
        "${COMPOSE[@]}" logs -f --tail 100 "${2:?informe o serviço: postgres, mlflow, api, streamlit, metabase, grafana...}"
        ;;
    build)
        "${COMPOSE[@]}" build
        ;;
    migrar-dados)
        set -a; source "$ENV_FILE"; set +a
        destino=$("${COMPOSE[@]}" ps -q postgres)
        [[ -n "$destino" ]] || { echo "❌ Suba o Postgres antes: ./infra.sh up"; exit 1; }
        existentes=$(docker exec "$destino" psql -U "$PG_USER" -d imoveis -Atc "SELECT COUNT(*) FROM predicoes")
        if [[ "$existentes" != "0" ]]; then
            echo "⚠️  O banco novo já tem $existentes previsões de compra. Nada foi copiado."; exit 1
        fi
        echo "📦 Copiando dados de $PG_ANTIGO → imoveis_postgres ..."
        docker exec "$PG_ANTIGO" pg_dump -U "$PG_USER" -d imoveis --data-only --no-owner \
            | docker exec -i "$destino" psql -q -U "$PG_USER" -d imoveis -v ON_ERROR_STOP=1
        docker exec "$destino" psql -U "$PG_USER" -d imoveis -c \
            "SELECT 'predicoes' tabela, COUNT(*) FROM predicoes UNION ALL
             SELECT 'pois', COUNT(*) FROM pois UNION ALL
             SELECT 'metrics_monitoramento', COUNT(*) FROM metrics_monitoramento"
        echo "✅ Dados copiados. Para scripts rodando fora do Docker, use PG_HOST=localhost e PG_PORT=5433 no $ENV_FILE."
        ;;
    *)
        sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
