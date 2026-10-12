# 🏡 Previsão de Preços de Imóveis — Ponta Grossa (PR)

Projeto **end-to-end de Ciência de Dados e Engenharia de Machine Learning** para previsão de preços de imóveis em Ponta Grossa (PR). Cobre todo o ciclo de vida do modelo: **coleta de dados → feature engineering geoespacial → modelagem → versionamento → deploy → monitoramento**.

---

## 📋 Índice

1. [Visão Geral](#-visão-geral)
2. [Arquitetura](#-arquitetura)
3. [Estrutura do Projeto](#-estrutura-do-projeto)
4. [Tecnologias](#-tecnologias)
5. [Instalação e Configuração](#-instalação-e-configuração)
6. [Como Executar](#-como-executar)
7. [API REST](#-api-rest)
8. [Notebooks](#-notebooks)
9. [Monitoramento](#-monitoramento)
10. [Métricas do Modelo](#-métricas-do-modelo)
11. [Features Utilizadas](#-features-utilizadas)

---

## 🎯 Visão Geral

O objetivo é construir um modelo de regressão capaz de estimar o preço de imóveis com base em:

- Características estruturais (área, quartos, banheiros, vagas)
- Contexto urbano e infraestrutura local (hospitais, mercados, escolas, parques)
- Indicadores de segurança e serviços essenciais

O foco vai além da acurácia: **reprodutibilidade, rastreabilidade e prontidão para produção (MLOps)**.

---

## 🧱 Arquitetura

```
Web Scraping (ZAP Imóveis)
        ↓
Geocoding (Google Maps API)
        ↓
Enriquecimento Geoespacial (OSMnx / OpenStreetMap)
        ↓
Feature Engineering (Scores de Proximidade)
        ↓
Treinamento + Otimização (XGBoost + Optuna)
        ↓
Versionamento (MLflow Model Registry)
        ↓
        ├── API REST (FastAPI)
        └── Interface Web (Streamlit)
                ↓
        Banco de Dados (MySQL)
                ↓
        Monitoramento de Data Drift (Evidently)
                ↓
        Observabilidade (Prometheus + Grafana)
```

---

## 📁 Estrutura do Projeto

```
Regression_PriceHouse/
│
├── api/                          # API REST (FastAPI)
│   └── main.py                   # Endpoints /predict, /health
│
├── src/                          # Módulos de ciência de dados
│   ├── features.py               # Feature engineering
│   ├── geocoding.py              # Geocoding com Google Maps API
│   ├── modelo.py                 # Definição do pipeline do modelo
│   ├── predict.py                # Inferência / carregamento do modelo
│   ├── preprocessing.py          # Pré-processamento dos dados
│   ├── scraper_robusto.py        # Web scraper (ZAP Imóveis)
│   └── train.py                  # Treinamento e registro (MLflow)
│
├── notebooks/                    # Análise exploratória e modelagem
│   ├── Coleta_e_tratamento.ipynb # Coleta e tratamento dos dados
│   ├── EDA.ipynb                 # Análise exploratória
│   ├── ML.ipynb                  # Modelagem v1
│   └── ML2.ipynb                 # Modelagem v2 (XGBoost + Optuna + SHAP)
│
├── streamlit_app/                # Interface web (Streamlit)
│   ├── app2.py                   # App principal (geocoding dinâmico)
│   ├── batch_app.py              # App para predição em lote
│   ├── api.py                    # Cliente da API REST
│   ├── db.py                     # Persistência no MySQL
│   └── config.py                 # Configurações do app
│
├── monitoring/                   # MLOps — Monitoramento
│   ├── config/
│   │   └── features.yaml         # Features monitoradas + thresholds
│   ├── db/
│   │   ├── mysql.py              # Conexão e queries MySQL
│   │   └── conf.sql              # Schema do banco de dados
│   ├── jobs/
│   │   ├── generate_baseline.py  # Gera baseline de referência (parquet)
│   │   └── run_data_drift.py     # Calcula data drift (Evidently)
│   ├── exporters/
│   │   └── prometheus_exporter.py # Expõe métricas para Prometheus
│   └── docker/
│       ├── docker-compose.yml    # Stack: MySQL + Exporter + Prometheus + Grafana
│       ├── Dockerfile.exporter   # Imagem do exporter Python
│       ├── prometheus.yml        # Config do Prometheus (scrape)
│       ├── alerts.yml            # Regras de alerta (Wasserstein threshold)
│       └── grafana/
│           ├── provisioning/     # Datasource + Dashboard auto-provisionados
│           └── dashboards/
│               └── drift_dashboard.json
│
├── data/
│   ├── raw/                      # Dados brutos (não versionados)
│   ├── pre/                      # POIs processados (escolas, hospitais, etc.)
│   └── processed/
│       ├── complete.csv          # Dataset completo com POIs
│       └── baseline_monitoring.parquet  # Baseline para monitoramento
│
├── mlruns/                       # Experimentos MLflow
├── results/
│   └── drift_reports/            # Relatórios HTML do Evidently
├── requirements.txt
└── README.md
```

---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Coleta | Selenium, BeautifulSoup4, Requests |
| Geoespacial | OSMnx, Shapely, GeoPy |
| Geocoding | Google Maps Geocoding API |
| ML / Modelagem | Scikit-learn, XGBoost, SHAP, Optuna |
| Versionamento | MLflow (tracking + model registry) |
| API | FastAPI + Uvicorn |
| Interface | Streamlit |
| Banco de Dados | MySQL 8.0 |
| Monitoramento | Evidently 0.7.x |
| Observabilidade | Prometheus + Grafana |
| Containers | Docker + Docker Compose |

---

## ⚙️ Instalação e Configuração

### 1. Clonar o repositório

```bash
git clone https://github.com/felipesembay/Price_house_ponta_grossa.git
cd Price_house_ponta_grossa
```

### 2. Criar ambiente conda

```bash
conda create -n regression python=3.12
conda activate regression
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

Crie o arquivo `streamlit_app/.env`:

```env
# Google Maps Geocoding API
GEOCODING_MAPS=sua_chave_aqui

# Banco de dados MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=senha_aqui
DB_NAME=imoveis
```

---

## 🚀 Como Executar

> **Pré-requisito:** ativar o ambiente conda antes de qualquer serviço.
>
> ```bash
> conda activate regression
> ```

---

### 1️⃣ API REST (FastAPI)

```bash
# A partir da raiz do projeto
uvicorn api.main:app --reload --port 8009
```

- Swagger UI: [http://localhost:8009/docs](http://localhost:8009/docs)
- ReDoc: [http://localhost:8009/redoc](http://localhost:8009/redoc)
- Health check: [http://localhost:8009/health](http://localhost:8009/health)

---

### 2️⃣ Interface Streamlit

```bash
cd streamlit_app
streamlit run app2.py
```

Acesse em: [http://localhost:8501](http://localhost:8501)

O app realiza o pipeline completo em tempo real:
1. Endereço → Google Geocoding
2. Coordenadas → POIs via OpenStreetMap
3. POIs → Scores de proximidade
4. Features + Scores → Predição via API

Para predição em lote:

```bash
streamlit run batch_app.py
```

---

### 3️⃣ MLflow (rastreamento de experimentos)

```bash
# A partir da raiz do projeto
mlflow ui --port 5000
```

Acesse em: [http://localhost:5000](http://localhost:5000)

Para treinar e registrar um novo modelo:

```bash
python src/models/train.py
```

---

### 4️⃣ Stack de Monitoramento (Docker)

```bash
cd monitoring/docker
docker-compose up -d
```

Serviços disponíveis após o start:

| Serviço | URL | Credenciais |
|---|---|---|
| Grafana | [http://localhost:3002](http://localhost:3002) | admin / admin |
| Prometheus | [http://localhost:9090](http://localhost:9090) | — |
| Prometheus Exporter | [http://localhost:8007/metrics](http://localhost:8007/metrics) | — |
| MySQL | localhost:3307 | root / airflow |

Para parar:

```bash
docker-compose down
```

---

### 5️⃣ Calcular Data Drift

**Gerar o baseline** (necessário apenas na primeira vez):

```bash
python monitoring/jobs/generate_baseline.py
```

**Rodar o job de drift** (dados de produção → MySQL):

```bash
# Modo produção (requer predições no MySQL)
MYSQL_PORT=3307 python monitoring/jobs/run_data_drift.py

# Modo seed — popula o MySQL com baseline (primeira execução)
MYSQL_PORT=3307 DRIFT_SEED=1 python monitoring/jobs/run_data_drift.py

# Dry run — apenas imprime, sem salvar
DRIFT_DRY_RUN=1 python monitoring/jobs/run_data_drift.py
```

> **Recomendação:** agendar `run_data_drift.py` via cron ou Airflow com intervalo de 6h.

Exemplo de crontab (a cada 6 horas):

```cron
0 */6 * * * cd /caminho/do/projeto && MYSQL_PORT=3307 conda run -n regression python monitoring/jobs/run_data_drift.py >> results/drift.log 2>&1
```

---

## 🔌 API REST

### Endpoint principal: `POST /predict`

**Request body:**

```json
{
  "area_m2": 150.0,
  "quartos": 3,
  "banheiros": 2,
  "vagas_garagem": 2,
  "tipo_imovel_cat": "casa",
  "is_sobrado": 0,
  "score_escola_privada": 0.85,
  "score_escola_publica": 0.42,
  "score_hospitais": 0.63,
  "score_mercado": 0.31,
  "score_farmacia": 0.18,
  "score_parque": 1.20,
  "score_seguranca": 0.47
}
```

**Response:**

```json
{
  "preco_estimado": 580000.0,
  "log_preco": 13.271,
  "modelo": "RealEstatePriceModel",
  "versao": "2.0.0"
}
```

**Outros endpoints:**

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Health check simples |
| `GET` | `/health` | Status + versão do modelo carregado |
| `POST` | `/predict` | Previsão de preço |

---

## 📓 Notebooks

| Notebook | Descrição |
|---|---|
| `Coleta_e_tratamento.ipynb` | Web scraping, limpeza e enriquecimento geoespacial |
| `EDA.ipynb` | Análise exploratória, distribuições, correlações, mapas |
| `ML.ipynb` | Benchmarking de modelos (baseline) |
| `ML2.ipynb` | Pipeline final: XGBoost + Optuna + SHAP values |

---

## 📊 Monitoramento

### Métricas de Data Drift (Evidently + Prometheus)

O monitoramento usa **Wasserstein distance (normed)** para detectar drift nas features de entrada:

| Faixa | Interpretação |
|---|---|
| `0.00 – 0.09` | ✅ Sem drift — distribuição estável |
| `0.10 – 0.29` | ⚠️ Drift moderado — monitorar |
| `≥ 0.30` | 🔴 Drift crítico — avaliar retreinamento |

### Alertas configurados (Grafana / Prometheus)

| Alerta | Condição | Severidade |
|---|---|---|
| `FeatureDriftHigh` | Wasserstein ≥ 0.10 por 5 min | Warning |
| `FeatureDriftCritical` | Wasserstein ≥ 0.30 por 5 min | Critical |
| `DatasetDriftDetected` | ≥ 50% das features driftadas | Critical |
| `MajorityFeaturesDrifted` | `share_drifted_columns > 0.5` | Critical |
| `DriftJobStopped` | Sem coleta de métricas há mais de 2 horas | Warning |

### Dashboard Grafana

O dashboard **"Data Drift — Precificação de Imóveis"** é provisionado automaticamente e inclui:

- Cards de status (dataset drift, % de features driftadas, última atualização)
- Bargauge com scores por feature (colorido por threshold)
- Timeseries de evolução do drift ao longo do tempo
- Tabela ranqueada das features com maior drift

---

## 📈 Métricas do Modelo

Resultados do modelo final (XGBoost otimizado com Optuna):

| Métrica | Valor |
|---|---|
| R² | ~0.87 |
| RMSE (log) | ~0.33 |
| MAE (log) | ~0.23 |
| MAPE | ~17% |

> O modelo prediz `log(preço)` e o valor real é recuperado com `exp(log_preço)`.

---

## 🧠 Features Utilizadas

### Estruturais

| Feature | Descrição |
|---|---|
| `area_m2` | Área total do imóvel em m² |
| `quartos` | Número de quartos |
| `banheiros` | Número de banheiros |
| `vagas_garagem` | Vagas de garagem |
| `is_sobrado` | 1 para sobrado, 0 para outros |
| `tipo_imovel_cat` | Categoria: casa, apartamento, comercial |

### Scores de Localização

Os scores são calculados combinando **distância ao POI mais próximo** e **quantidade no raio definido**:

| Score | POI | Raio de Contagem |
|---|---|---|
| `score_escola_privada` | Escolas privadas | 500 m |
| `score_escola_publica` | Escolas públicas | 500 m |
| `score_hospitais` | Hospitais | 1.000 m |
| `score_mercado` | Supermercados | 500 m |
| `score_farmacia` | Farmácias | 300 m |
| `score_parque` | Parques e praças | 1.000 m |
| `score_seguranca` | Delegacias / corpo de bombeiros | 500 m |

**Fórmula geral:**

```
score = peso_dist × exp(-dist_mais_proximo / raio_decaimento)
      + peso_qtd  × qtd_no_raio
```

---

## 👤 Autor

**Felipe Sembay**  
Cientista de Dados | Machine Learning | MLOps

[![GitHub](https://img.shields.io/badge/GitHub-felipesembay-black?logo=github)](https://github.com/felipesembay)

---

*Última atualização: 26 de Fevereiro de 2026*


