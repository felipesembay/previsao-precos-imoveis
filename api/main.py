"""
API REST da plataforma de previsão de preços de imóveis (aluguel SP + compra Ponta Grossa).

Uso:
    uvicorn api.main:app --reload --port 8009        (no Docker: serviço `api`)
    Documentação interativa: http://localhost:8009/docs

Endpoints do frontend:
    POST /aluguel/prever            endereço + imóvel → aluguel, faixa, custo total, POIs próximos
    POST /aluguel/prever-lote       CSV (campo "arquivo") → uma previsão por linha
    POST /compra/prever             endereço + imóvel → preço de venda (Ponta Grossa)
    GET  /modelos                   modelos em produção e métricas
    GET  /monitoramento/{modelo}    MAPE ao longo do tempo, drift por feature, alertas ativos
    GET  /retreinos                 histórico champion × challenger
    GET  /mercado/aluguel/regioes   R$/m² por região de São Paulo
    GET  /mercado/aluguel/achados   achados da análise
    GET  /infra/uso                 horas e armazenamento do Azure, inserções

Endpoints antigos (usados pelo Streamlit de compra):
    GET /health · POST /predict · POST /predict_batch
"""

import io
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import mlflow
import pandas as pd
import psycopg
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, ValidationError

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "streamlit_app"))  # funções de gravação do db.py

from api import esquemas as E  # noqa: E402
from api import painel  # noqa: E402
from src.config_banco import config_banco  # noqa: E402
from src.inferencia.aluguel import ServicoAluguel  # noqa: E402
from src.inferencia.compra import MODEL_NAME as COMPRA_MODELO  # noqa: E402
from src.inferencia.compra import VERSAO as COMPRA_VERSAO  # noqa: E402
from src.inferencia.compra import ServicoCompra  # noqa: E402
from src.inferencia.geocoding import geocode  # noqa: E402
from src.models.predict import predict, predict_batch  # noqa: E402

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [API] %(levelname)s %(message)s")

MAX_LINHAS_LOTE = 200          # cada linha consome uma chamada paga de geocoding
THREADS_GEOCODING = 8

# Origens do frontend: Lovable (preview e publicado) e localhost; CORS_ORIGINS acrescenta outras
CORS_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https://([a-z0-9-]+\.)*(lovable\.app|lovableproject\.com|lovable\.dev)|http://(localhost|127\.0\.0\.1)(:\d+)?",
)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

servicos: dict = {}


def conectar():
    """Conexão com o banco do app (local ou Azure, conforme BANCO_APP)."""
    return psycopg.connect(row_factory=dict_row, **config_banco())


@asynccontextmanager
async def lifespan(app: FastAPI):
    mlflow.set_tracking_uri(f"file:{os.path.join(ROOT_DIR, 'mlruns')}")
    for chave, fabrica in (("aluguel", ServicoAluguel), ("compra", lambda: ServicoCompra(conectar))):
        try:
            servicos[chave] = fabrica()
            log.info("Serviço %s carregado", chave)
        except Exception as exc:
            log.error("Serviço %s indisponível: %s", chave, exc)
    if "aluguel" in servicos:
        servicos["aluguel"].modelo()  # carrega o @champion já na subida
    yield
    servicos.clear()


app = FastAPI(
    title="API — Previsão de Preços de Imóveis",
    description="Aluguel em São Paulo e venda em Ponta Grossa/PR: previsão, monitoramento e mercado.",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_REGEX,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _servico(chave: str):
    if chave not in servicos:
        raise HTTPException(503, f"Modelo de {chave} indisponível no momento.")
    return servicos[chave]


def _geocodificar(endereco: str) -> dict:
    try:
        geo = geocode(endereco)
    except Exception as exc:
        log.error("Geocoding falhou: %s", exc)
        raise HTTPException(502, "Serviço de geocoding indisponível.")
    if geo is None:
        raise HTTPException(422, "Endereço não encontrado. Confira a grafia e inclua número e cidade.")
    return geo


# ── Gravação no banco (em segundo plano: não atrasa a resposta) ────────────────
def _salvar_aluguel(dados: dict):
    from db import salvar_features_monitoramento_aluguel, salvar_predicao_aluguel
    try:
        pid = salvar_predicao_aluguel(dados["registro"])
        salvar_features_monitoramento_aluguel(pid, dados["features"])
    except Exception as exc:
        log.error("Falha ao gravar previsão de aluguel: %s", exc)


def _salvar_compra(dados: dict):
    from db import salvar_features_monitoramento, salvar_predicao
    try:
        anuncio, preco = dados["dados"].get("preco_anuncio"), dados["preco"]
        erro_abs = abs(preco - anuncio) if anuncio else None
        pid = salvar_predicao(dados["dados"], preco, COMPRA_MODELO, COMPRA_VERSAO,
                              erro_abs, erro_abs / anuncio if anuncio else None)
        salvar_features_monitoramento(pid, dados["dados"]["area_m2"], dados["scores"])
    except Exception as exc:
        log.error("Falha ao gravar previsão de compra: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# Previsão
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/aluguel/prever", response_model=E.AluguelResponse, tags=["previsão"])
def prever_aluguel(req: E.AluguelRequest, tarefas: BackgroundTasks):
    servico = _servico("aluguel")
    geo = _geocodificar(req.endereco)
    try:
        resposta, gravar = servico.prever(geo, req.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    tarefas.add_task(_salvar_aluguel, gravar)
    return resposta


@app.post("/aluguel/prever-lote", response_model=E.LoteResponse, tags=["previsão"])
async def prever_aluguel_lote(tarefas: BackgroundTasks, arquivo: UploadFile = File(...)):
    """CSV com as colunas do POST /aluguel/prever (uma linha por imóvel, até 200)."""
    servico = _servico("aluguel")
    try:
        df = pd.read_csv(io.BytesIO(await arquivo.read()), sep=None, engine="python")
    except Exception:
        raise HTTPException(400, "Não consegui ler o CSV. Use o modelo de colunas do /docs.")
    if len(df) > MAX_LINHAS_LOTE:
        raise HTTPException(413, f"Máximo de {MAX_LINHAS_LOTE} linhas por lote.")
    df.columns = [c.strip().lower() for c in df.columns]
    linhas = df.astype(object).where(df.notna(), None).to_dict("records")

    def processar(linha):
        try:
            req = E.AluguelRequest(**{k: v for k, v in linha.items() if v is not None})
        except ValidationError as exc:
            erro = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            return {**linha, "aluguel_estimado": None, "erro": erro}
        try:
            geo = geocode(req.endereco)
            if geo is None:
                return {**linha, "aluguel_estimado": None, "erro": "endereço não encontrado"}
            resposta, gravar = servico.prever(geo, req.model_dump())
        except Exception as exc:
            return {**linha, "aluguel_estimado": None, "erro": str(exc)}
        gravar["registro"]["origem"] = "api_lote"
        tarefas.add_task(_salvar_aluguel, gravar)
        return {**req.model_dump(), "aluguel_estimado": resposta["aluguel_estimado"], "erro": None}

    with ThreadPoolExecutor(THREADS_GEOCODING) as pool:
        return {"linhas": list(pool.map(processar, linhas))}


@app.post("/compra/prever", response_model=E.CompraResponse, tags=["previsão"])
def prever_compra(req: E.CompraRequest, tarefas: BackgroundTasks):
    servico = _servico("compra")
    geo = _geocodificar(req.endereco)
    try:
        resposta, gravar = servico.prever(geo, req.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    tarefas.add_task(_salvar_compra, gravar)
    return resposta


# ══════════════════════════════════════════════════════════════════════════════
# Painel
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/modelos", response_model=E.ModelosResponse, tags=["painel"])
def listar_modelos():
    return {"modelos": painel.modelos(_servico("aluguel"), _servico("compra"))}


@app.get("/monitoramento/{modelo}", response_model=E.MonitoramentoResponse, tags=["painel"])
def ver_monitoramento(modelo: str):
    if modelo not in painel.CONFIG_MONITORAMENTO:
        raise HTTPException(404, "Use aluguel ou compra.")
    versao = f"v{_servico('aluguel').modelo()[1]}" if modelo == "aluguel" else "v2"
    return painel.monitoramento(conectar, modelo, versao)


@app.get("/retreinos", response_model=E.RetreinosResponse, tags=["painel"])
def listar_retreinos():
    return {"retreinos": painel.retreinos(conectar)}


@app.get("/mercado/aluguel/regioes", response_model=E.RegioesResponse, tags=["mercado"])
def regioes_aluguel():
    return {"regioes": painel.regioes_aluguel()}


@app.get("/mercado/aluguel/achados", response_model=E.AchadosResponse, tags=["mercado"])
def achados_aluguel():
    return {"achados": painel.ACHADOS_ALUGUEL}


@app.get("/infra/uso", response_model=E.InfraResponse, tags=["painel"])
def uso_infra():
    return painel.uso_infra(conectar)


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints antigos (Streamlit de compra) — recebem os scores já calculados
# ══════════════════════════════════════════════════════════════════════════════
class ImovelInput(BaseModel):
    quartos: int = Field(ge=0, le=20)
    banheiros: int = Field(ge=0, le=20)
    vagas_garagem: int = Field(ge=0, le=20, default=0)
    area_m2: float = Field(gt=0, le=10000)
    tipo_imovel_cat: str = "casa"
    is_sobrado: int = Field(default=0, ge=0, le=1)
    score_escola_privada: float = Field(default=0.0, ge=0)
    score_escola_publica: float = Field(default=0.0, ge=0)
    score_hospitais: float = Field(default=0.0, ge=0)
    score_mercado: float = Field(default=0.0, ge=0)
    score_farmacia: float = Field(default=0.0, ge=0)
    score_parque: float = Field(default=0.0, ge=0)
    score_seguranca: float = Field(default=0.0, ge=0)


class PredictionOutput(BaseModel):
    preco_estimado: float
    log_preco: float
    moeda: str = "BRL"


class BatchInput(BaseModel):
    imoveis: list[ImovelInput] = Field(min_length=1, max_length=5000)


@app.get("/", tags=["status"])
def root():
    return {"mensagem": "API de previsão de preços de imóveis", "docs": "/docs"}


@app.get("/health", tags=["status"])
def health():
    return {"status": "ok" if servicos else "sem_modelos", "modelos": sorted(servicos)}


@app.post("/predict", response_model=PredictionOutput, tags=["legado"])
def predict_price(imovel: ImovelInput):
    return predict(_servico("compra").modelo, imovel.model_dump())


@app.post("/predict_batch", tags=["legado"])
def predict_price_batch(lote: BatchInput):
    resultados = predict_batch(_servico("compra").modelo, [i.model_dump() for i in lote.imoveis])
    return {"previsoes": [PredictionOutput(**r) for r in resultados]}
