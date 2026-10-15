"""Esquemas da API usada pelo frontend (contrato combinado com a UI)."""

from typing import Literal

from pydantic import BaseModel, Field

TipoImovel = Literal["apartamento", "studio", "casa", "casa_condominio"]


# ── Previsão ───────────────────────────────────────────────────────────────────
class Localizacao(BaseModel):
    lat: float
    lon: float
    endereco_formatado: str


class PoiProximo(BaseModel):
    categoria: str
    nome: str | None
    lat: float
    lon: float
    distancia_m: int


class Faixa(BaseModel):
    min: float
    max: float


class ModeloUsado(BaseModel):
    nome: str
    versao: str


class AluguelRequest(BaseModel):
    endereco: str = Field(min_length=5, max_length=300)
    tipo: TipoImovel
    area: float = Field(gt=10, le=1000, description="m²")
    quartos: int = Field(ge=0, le=10)
    banheiros: int = Field(ge=1, le=10)
    suites: int = Field(default=0, ge=0, le=10)
    vagas: int = Field(default=0, ge=0, le=10)
    mobiliado: bool = False
    ar_condicionado: bool = False
    piscina: bool = False
    academia: bool = False
    varanda: bool = False
    aluguel_anunciado: float | None = Field(default=None, gt=0)

    model_config = {"json_schema_extra": {"examples": [{
        "endereco": "Rua Augusta, 1500, São Paulo - SP", "tipo": "apartamento", "area": 65,
        "quartos": 2, "banheiros": 2, "suites": 1, "vagas": 1, "mobiliado": False,
        "ar_condicionado": True, "piscina": True, "academia": True, "varanda": True,
        "aluguel_anunciado": 4200,
    }]}}


class Comparacao(BaseModel):
    aluguel_anunciado: float
    diferenca_pct: float
    classificacao: Literal["abaixo", "dentro", "acima"]


class AluguelResponse(BaseModel):
    aluguel_estimado: float
    faixa: Faixa
    custo_extra_pct: float | None
    custo_total_estimado: float | None
    bairro: str | None
    localizacao: Localizacao
    pois_proximos: list[PoiProximo]
    comparacao: Comparacao | None
    modelo: ModeloUsado


class CompraRequest(BaseModel):
    endereco: str = Field(min_length=5, max_length=300)
    area: float = Field(gt=10, le=10000, description="m²")
    quartos: int = Field(ge=0, le=20)
    banheiros: int = Field(ge=0, le=20)
    vagas: int = Field(default=0, ge=0, le=20)
    tipo: Literal["casa", "apartamento", "comercial"] = "casa"
    sobrado: bool = False
    preco_anunciado: float | None = Field(default=None, gt=0)

    model_config = {"json_schema_extra": {"examples": [{
        "endereco": "Rua XV de Novembro, 500, Ponta Grossa - PR", "area": 120, "quartos": 3,
        "banheiros": 2, "vagas": 2, "tipo": "casa", "sobrado": False,
    }]}}


class CompraResponse(BaseModel):
    preco_estimado: float
    faixa: Faixa
    localizacao: Localizacao
    pois_proximos: list[PoiProximo]
    modelo: ModeloUsado


class LoteResponse(BaseModel):
    linhas: list[dict]


# ── Painel (modelos, monitoramento, mercado, infraestrutura) ───────────────────
class MetricasModelo(BaseModel):
    r2: float
    mae_reais: float | None
    mape: float | None


class InfoModelo(BaseModel):
    chave: Literal["aluguel", "compra"]
    nome: str
    versao: str
    treinado_em: str
    n_treino: int | None
    metricas: MetricasModelo


class ModelosResponse(BaseModel):
    modelos: list[InfoModelo]


class PontoMape(BaseModel):
    data: str
    mape: float


class DriftFeature(BaseModel):
    feature: str
    score: float
    status: Literal["ok", "atencao", "critico"]


class Alerta(BaseModel):
    nome: str
    severidade: str
    desde: str
    resumo: str


class MonitoramentoResponse(BaseModel):
    mape_serie: list[PontoMape]
    mape_limite: float
    drift: list[DriftFeature]
    n_amostras: int
    alertas: list[Alerta]


class Retreino(BaseModel):
    data: str
    versao_challenger: str
    versao_champion: str | None
    mape_challenger: float
    mape_champion: float | None
    promovido: bool
    motivo: str


class RetreinosResponse(BaseModel):
    retreinos: list[Retreino]


class Regiao(BaseModel):
    nome: str
    lat: float
    lon: float
    n_anuncios: int
    aluguel_m2_mediano: float
    aluguel_mediano: float


class RegioesResponse(BaseModel):
    regioes: list[Regiao]


class Achado(BaseModel):
    titulo: str
    valor: str
    descricao: str


class AchadosResponse(BaseModel):
    achados: list[Achado]


class InfraResponse(BaseModel):
    horas_mes: float | None
    horas_limite: int
    banco_bytes: int
    banco_limite_bytes: int
    insercoes_24h: int
    previsoes_total: int
