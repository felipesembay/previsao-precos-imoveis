"""
API REST para previsão de preços de imóveis.

Uso:
    cd /home/felipe/Projeto/Portfolio/Portfolio2/Regression_PriceHouse
    uvicorn api.main:app --reload --port 8000

Endpoints:
    GET  /           → Health check
    GET  /health     → Status + versão do modelo
    POST /predict    → Previsão de preço
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

import mlflow
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Adiciona o diretório raiz ao path para imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from src.models.predict import load_model, predict, predict_batch

# ============================================================
# Schema de entrada / saída
# ============================================================

class ImovelInput(BaseModel):
    """Dados de entrada para previsão."""

    quartos: int = Field(ge=0, le=20, description="Número de quartos")
    banheiros: int = Field(ge=0, le=20, description="Número de banheiros")
    vagas_garagem: int = Field(ge=0, le=20, default=0, description="Vagas de garagem")
    area_m2: float = Field(gt=0, le=10000, description="Área em m²")
    
    # Tipo de imóvel
    tipo_imovel_cat: str = Field(
        default="casa",
        description="Tipo do imóvel: casa, apartamento, comercial ou outros"
    )
    
    # É sobrado? (0 ou 1)
    is_sobrado: int = Field(default=0, ge=0, le=1, description="1 se for sobrado, 0 caso contrário")

    # Scores de proximidade (opcionais — usa 0.0 se não enviado)
    score_escola_privada: float = Field(default=0.0, ge=0)
    score_escola_publica: float = Field(default=0.0, ge=0)
    score_hospitais: float = Field(default=0.0, ge=0)
    score_mercado: float = Field(default=0.0, ge=0)
    score_farmacia: float = Field(default=0.0, ge=0)
    score_parque: float = Field(default=0.0, ge=0)
    score_seguranca: float = Field(default=0.0, ge=0)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "quartos": 3,
                    "banheiros": 2,
                    "vagas_garagem": 2,
                    "area_m2": 150.0,
                    "tipo_imovel_cat": "casa",
                    "is_sobrado": 0,
                    "score_escola_privada": 1.5,
                    "score_escola_publica": 0.8,
                    "score_hospitais": 0.6,
                    "score_mercado": 1.2,
                    "score_farmacia": 0.4,
                    "score_parque": 0.9,
                    "score_seguranca": 0.7,
                }
            ]
        }
    }


class PredictionOutput(BaseModel):
    """Resposta da previsão."""

    preco_estimado: float = Field(description="Preço estimado em R$")
    log_preco: float = Field(description="Log do preço estimado")
    moeda: str = "BRL"


class BatchInput(BaseModel):
    """Vários imóveis numa única requisição."""

    imoveis: list[ImovelInput] = Field(min_length=1, max_length=5000)


class BatchOutput(BaseModel):
    previsoes: list[PredictionOutput]


class HealthOutput(BaseModel):
    status: str
    model_name: str
    version: str


# ============================================================
# App
# ============================================================

# Variável global para o modelo
_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Carrega o modelo na inicialização da API."""
    global _model

    # Tracking URI absoluto — mlruns/ sempre na raiz do projeto
    _mlruns_dir = os.path.join(ROOT_DIR, "mlruns")
    mlflow.set_tracking_uri(f"file:{_mlruns_dir}")

    try:
        _model = load_model()
        print("✅ Modelo carregado com sucesso!")
    except Exception as e:
        print(f"⚠️  Erro ao carregar modelo do registry: {e}")
        print("   A API vai iniciar sem modelo. Treine primeiro com: python -m src.models.train")

    yield  # App rodando

    _model = None


app = FastAPI(
    title="API de Previsão de Preços de Imóveis",
    description="Previsão de preço de imóveis em Ponta Grossa/PR usando XGBoost + MLflow",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# Endpoints
# ============================================================

@app.get("/")
def root():
    return {"message": "API de Previsão de Preços de Imóveis — Ponta Grossa/PR"}


@app.get("/health", response_model=HealthOutput)
def health():
    return HealthOutput(
        status="ok" if _model is not None else "no_model",
        model_name="RealEstatePriceModel",
        version="1.0.0",
    )


@app.post("/predict", response_model=PredictionOutput)
def predict_price(imovel: ImovelInput):
    if _model is None:
        raise HTTPException(
            status_code=503,
            detail="Modelo não carregado. Treine primeiro com: python -m src.models.train",
        )

    try:
        data = imovel.model_dump()
        result = predict(_model, data)

        return PredictionOutput(
            preco_estimado=result["preco_estimado"],
            log_preco=result["log_preco"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict_batch", response_model=BatchOutput)
def predict_price_batch(lote: BatchInput):
    """Previsão em lote: uma chamada ao modelo para todos os imóveis (usada pelo batch_app)."""
    if _model is None:
        raise HTTPException(
            status_code=503,
            detail="Modelo não carregado. Treine primeiro com: python -m src.models.train",
        )

    try:
        resultados = predict_batch(_model, [i.model_dump() for i in lote.imoveis])
        return BatchOutput(previsoes=[PredictionOutput(**r) for r in resultados])

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
