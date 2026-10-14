# 🏡 Previsão de Preços de Imóveis — Venda (Ponta Grossa) e Aluguel (São Paulo)

Dois projetos **end-to-end de Ciência de Dados e MLOps** para precificação de imóveis, que compartilham a mesma base técnica: **coleta → geocoding → enriquecimento geoespacial (POIs) → EDA e inferência estatística → modelagem → versionamento (MLflow) → API / interface → monitoramento**.

| Projeto | Cidade | Alvo | Dados | Status |
|---|---|---|---|---|
| **Compra** | Ponta Grossa (PR) | preço de venda | anúncios ZAP Imóveis | ✅ Modelo, API, Streamlit e monitoramento |
| **Aluguel** | São Paulo (SP) — capital | aluguel mensal (`rent`) | ~30 mil anúncios de aluguel | ✅ EDA, inferência, modelo no MLflow · 🚧 interface e monitoramento |

---

## 📋 Índice

1. [Projeto Aluguel — São Paulo](#-projeto-aluguel--são-paulo)
2. [Projeto Compra — Ponta Grossa](#-projeto-compra--ponta-grossa)
3. [Arquitetura](#-arquitetura)
4. [Estrutura do Projeto](#-estrutura-do-projeto)
5. [Tecnologias](#-tecnologias)
6. [Instalação e Configuração](#-instalação-e-configuração)
7. [Como Executar](#-como-executar)
8. [API REST](#-api-rest)
9. [Monitoramento](#-monitoramento)
10. [Features e Scores de Localização](#-features-e-scores-de-localização)
11. [Roadmap](#-roadmap)

---

## 🏙️ Projeto Aluguel — São Paulo

Previsão do aluguel de imóveis residenciais na cidade de São Paulo. Antes do modelo, uma análise exploratória e de inferência estatística completa, para separar **associação** de **efeito controlado**.

### Notebooks (`notebooks/aluguel/`)

| Notebook | Conteúdo |
|---|---|
| `01_limpeza_eda.ipynb` | Escopo (SP capital), remoção de vazamento do alvo, duplicatas, regras de qualidade, EDA e tabela de custo extra (condomínio + IPTU) por bairro |
| `02_inferencia.ipynb` | 11 hipóteses: elasticidade da área, efeito do tipo, regiões, não linearidade da distância, mobília, pet; OLS com efeito fixo de região e erros agrupados |
| `03_poi_eda.ipynb` | 12 categorias de POIs do OpenStreetMap (escolas, hospitais, metrô, parques...), distâncias, acessibilidade e viés de cobertura do OSM |
| `04_poi_inferencia.ipynb` | Efeito de cada POI sem controle → controlando a planta → controlando planta e região; gradiente do metrô; validação cruzada espacial |
| `05_features.ipynb` | Feature engineering: polos de valor, coordenadas, vizinhança, conjuntos de features |
| `06_modelagem.ipynb` | Grade de modelos × scalers, SHAP, Optuna, avaliação no holdout (mesmo padrão do projeto de compra) |

### Principais achados

- 📍 **Central não é o mesmo que nobre:** o aluguel por m² não é máximo no marco zero (Praça da Sé); o pico fica a ~4 km, no eixo Pinheiros–Vila Mariana–Itaim. Entre regiões, o R$/m² varia 5,2×.
- 📐 **Elasticidade da área < 1:** +10% de área → +6,3% de aluguel.
- 🛋️ **Associação ≠ efeito:** mobiliado parece +42% e piscina +41%; controlando tamanho e região, ficam em +14% e +8%. Aceitar pet não altera o preço.
- 🏢 **Studio:** tem o maior R$/m², mas pelo tamanho, localização e mobília; em condições iguais sai ~4% mais barato que um apartamento.
- 🏫 **POIs refletem a região:** perto de escola pública −13% sem controle → ~−1% (não significativo) dentro da mesma região. O mesmo vale para farmácias, hospitais e mercados.
- 🚇 **Metrô é a exceção:** +19% a até 300 m da estação, decaindo para +5% a 1,5–2 km, comparando imóveis da mesma região.
- 💸 **Custo total:** condomínio + IPTU + taxas somam, na mediana, 23,6% sobre o aluguel (de ~18% a ~32% entre bairros).

### Modelo (MLflow: `RentPriceModel_SP`)

XGBoost otimizado com Optuna, 20 features numéricas (planta, atributos, scores de POI, distâncias ao centro e a polos de valor) + tipo do imóvel. A localização entra **só via geocoding** (lat/lon → POIs e distâncias), igual ao projeto de compra.

| Métrica (holdout, 20%) | XGBoost | Regressão linear |
|---|---|---|
| R² (log) | **0,875** | 0,784 |
| MAE (R$) | **R$ 904** | R$ 1.220 |
| MAPE (R$) | **18,5%** | 24,8% |

> O modelo prevê `log(aluguel)`; o valor em R$ é recuperado com `exp()`.

---

## 🏡 Projeto Compra — Ponta Grossa

Previsão do preço de venda de imóveis em Ponta Grossa (PR), com o ciclo completo em produção: API, interface, banco de dados e monitoramento de drift.

### Notebooks (`notebooks/compra/`)

| Notebook | Conteúdo |
|---|---|
| `Coleta_e_tratamento.ipynb` | Web scraping, limpeza e enriquecimento geoespacial |
| `EDA.ipynb` | Análise exploratória, scores de POI, ANOVA, VIF e regressão |
| `ML.ipynb`, `ML2.ipynb`, `ML3.ipynb` | Benchmark de modelos × scalers, SHAP, Optuna (XGBoost) |

### Modelo (MLflow: `RealEstatePriceModel_version2`)

| Métrica (holdout, escala log) | XGBoost | Regressão linear |
|---|---|---|
| R² | **0,847** | 0,660 |
| RMSE | **0,323** | 0,481 |
| MAE | **0,231** | 0,371 |

---

## 🧱 Arquitetura

```
Coleta (ZAP Imóveis / anúncios de aluguel)
        ↓
Geocoding (Google Maps API / OpenCage)
        ↓
Enriquecimento Geoespacial (OpenStreetMap: escolas, hospitais, metrô, parques...)
        ↓
EDA + Inferência Estatística (ANOVA, Kruskal-Wallis, OLS com efeito fixo)
        ↓
Feature Engineering (Scores de Proximidade, distâncias)
        ↓
Treinamento + Otimização (XGBoost + Optuna)
        ↓
Versionamento (MLflow Model Registry)
        ↓
        ├── API REST (FastAPI)
        └── Interface Web (Streamlit)
                ↓
        Banco de Dados (PostgreSQL)
                ↓
        Monitoramento de Data Drift (Evidently)
                ↓
        Observabilidade (Prometheus + Grafana)
```

---

## 📁 Estrutura do Projeto

```
previsao-precos-imoveis/
│
├── api/
│   └── main.py                    # FastAPI: /predict, /health (modelo de compra)
│
├── src/
│   ├── features/
│   │   ├── pipeline.py            # Features e scores de POI — compra
│   │   └── aluguel.py             # Features, scores e transformers — aluguel
│   ├── preprocessing/
│   │   └── clean.py               # QuantileClipper + ColumnTransformer (compartilhado)
│   ├── models/
│   │   ├── train.py               # Treino + MLflow — compra
│   │   ├── train_aluguel.py       # Treino + MLflow — aluguel
│   │   └── predict.py             # Carregamento do modelo e inferência
│   ├── geocoding/
│   │   └── geocode.py             # Geocoding (OpenCage)
│   └── scraping/                  # Coletores (ZAP Imóveis e aluguel)
│
├── notebooks/
│   ├── compra/                    # EDA e modelagem — Ponta Grossa
│   └── aluguel/                   # 01–06: EDA, inferência, POIs, features, modelagem — São Paulo
│
├── streamlit_app/                 # Interface web (geocoding + POIs + predição)
├── monitoring/                    # Drift (Evidently), PostgreSQL, Prometheus, Grafana
├── data/
│   ├── raw/osm/                   # POIs do OpenStreetMap
│   └── processed/                 # Dataset de compra + baseline de monitoramento
├── results/                       # Resultados de inferência, modelos e relatórios de drift
├── docs/                          # Documentação do scraping
├── roadmap-projetos-portfolio.md
├── requirements.txt
└── README.md
```

> Dados coletados de portais e seus derivados **não são versionados** (ver `.gitignore`). O MLflow (`mlruns/`) também fica só local.

---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Coleta | Selenium, BeautifulSoup4, Requests |
| Geoespacial | GeoPandas, Shapely, OSMnx, scikit-learn BallTree |
| Geocoding | Google Maps Geocoding API, OpenCage |
| Estatística | statsmodels, SciPy |
| ML / Modelagem | scikit-learn, XGBoost, LightGBM, SHAP, Optuna |
| Versionamento | MLflow (tracking + model registry) |
| API | FastAPI + Uvicorn |
| Interface | Streamlit |
| Banco de Dados | PostgreSQL 16 (local) → Azure Database for PostgreSQL |
| Monitoramento | Evidently 0.7.x |
| Observabilidade | Prometheus + Grafana |
| Containers | Docker + Docker Compose |

---

## ⚙️ Instalação e Configuração

### 1. Clonar o repositório

```bash
git clone https://github.com/felipesembay/previsao-precos-imoveis.git
cd previsao-precos-imoveis
```

### 2. Criar ambiente conda

```bash
conda create -n regression python=3.12
conda activate regression
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

Crie o arquivo `.env` na raiz (e/ou em `streamlit_app/.env`):

```env
# Geocoding
GEOCODING_MAPS=sua_chave_google_maps
OPENCAGE_API_KEY=sua_chave_opencage

# Banco de dados PostgreSQL (esquema: streamlit_app/db/schema_postgres.sql)
PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=senha_aqui
PG_DB=imoveis
```

---

## 🚀 Como Executar

> **Pré-requisito:** `conda activate regression`, a partir da raiz do projeto.

### 1️⃣ Treinar e registrar os modelos (MLflow)

```bash
python -m src.models.train          # compra  → RealEstatePriceModel_version2
python -m src.models.train_aluguel  # aluguel → RentPriceModel_SP

mlflow ui --port 5000               # http://localhost:5000
```

> O treino do aluguel lê `data/interim/aluguel_sp_features.parquet`, gerado pelos notebooks 01, 03 e 05.

### 2️⃣ API REST (FastAPI)

```bash
uvicorn api.main:app --reload --port 8009
```

- Swagger UI: [http://localhost:8009/docs](http://localhost:8009/docs)
- Health check: [http://localhost:8009/health](http://localhost:8009/health)

### 3️⃣ Interface Streamlit

```bash
cd streamlit_app
streamlit run app2.py        # predição individual
streamlit run batch_app.py   # predição em lote
```

O app executa o pipeline em tempo real: endereço → geocoding → POIs → scores → predição via API.

### 4️⃣ Stack de Monitoramento (Docker)

```bash
cd monitoring/docker
docker-compose up -d
```

| Serviço | URL |
|---|---|
| Grafana | [http://localhost:3002](http://localhost:3002) |
| Prometheus | [http://localhost:9090](http://localhost:9090) |
| Prometheus Exporter | [http://localhost:8007/metrics](http://localhost:8007/metrics) |

### 5️⃣ Calcular Data Drift

```bash
python monitoring/jobs/generate_baseline.py                  # baseline (primeira vez)
python monitoring/jobs/run_data_drift.py                     # dados de produção → PostgreSQL
DRIFT_SEED=1 python monitoring/jobs/run_data_drift.py        # seed inicial
DRIFT_DRY_RUN=1 python monitoring/jobs/run_data_drift.py     # apenas imprime
```

> Recomendação: agendar `run_data_drift.py` via cron ou Airflow a cada 6 h.

---

## 🔌 API REST

### `POST /predict` (modelo de compra)

**Request:**

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

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Health check simples |
| `GET` | `/health` | Status + versão do modelo carregado |
| `POST` | `/predict` | Previsão de preço |

> O endpoint do modelo de aluguel está no roadmap.

---

## 📊 Monitoramento

O monitoramento usa **Wasserstein distance (normed)** para detectar drift nas features de entrada:

| Faixa | Interpretação |
|---|---|
| `0.00 – 0.09` | ✅ Sem drift |
| `0.10 – 0.29` | ⚠️ Drift moderado — monitorar |
| `≥ 0.30` | 🔴 Drift crítico — avaliar retreinamento |

| Alerta | Condição | Severidade |
|---|---|---|
| `FeatureDriftHigh` | Wasserstein ≥ 0.10 por 5 min | Warning |
| `FeatureDriftCritical` | Wasserstein ≥ 0.30 por 5 min | Critical |
| `DatasetDriftDetected` | ≥ 50% das features com drift | Critical |
| `MajorityFeaturesDrifted` | `share_drifted_columns > 0.5` | Critical |
| `DriftJobStopped` | Sem coleta de métricas há mais de 2 h | Warning |

O dashboard **"Data Drift — Precificação de Imóveis"** é provisionado automaticamente no Grafana.

---

## 🧠 Features e Scores de Localização

Os dois modelos usam **scores de proximidade** que combinam a distância ao POI mais próximo e a quantidade no raio:

```
score = peso_dist × exp(−dist_mais_proximo / raio_decaimento) + peso_qtd × qtd_no_raio
```

| Score | POI | Compra | Aluguel |
|---|---|---|---|
| `score_escola_privada` | Escolas privadas | ✅ | ✅ |
| `score_escola_publica` | Escolas públicas | ✅ | ✅ |
| `score_hospitais` | Hospitais | ✅ | ✅ |
| `score_mercado` | Supermercados | ✅ | ✅ |
| `score_farmacia` | Farmácias | ✅ | ✅ |
| `score_parque` | Parques | ✅ | ✅ (só parques ≥ 1 ha) |
| `score_seguranca` | Delegacias | ✅ | ✅ |
| `score_metro` | Estações de metrô | — | ✅ |

**Estruturais:** área, quartos, banheiros, vagas, tipo do imóvel (compra: + `is_sobrado`; aluguel: + suítes, mobiliado, ar-condicionado, piscina, academia, varanda e distâncias ao centro e a polos de valor).

---

## 🗺️ Roadmap

- [x] Compra: modelo, API, Streamlit e monitoramento de drift
- [x] Aluguel: EDA, inferência estatística, POIs e modelo no MLflow
- [ ] Aluguel: interface Streamlit (com custo total estimado por bairro)
- [ ] Aluguel: API, monitoramento e governança reaproveitando a stack existente
- [ ] CI/CD (GitHub Actions), orquestração, Kubernetes, Terraform e teste A/B champion/challenger

Detalhes em [`roadmap-projetos-portfolio.md`](roadmap-projetos-portfolio.md).

---

## 👤 Autor

**Felipe Sembay**
Cientista de Dados | Machine Learning | MLOps

[![GitHub](https://img.shields.io/badge/GitHub-felipesembay-black?logo=github)](https://github.com/felipesembay)
