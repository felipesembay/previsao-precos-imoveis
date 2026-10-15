"""
Inferência do modelo de aluguel (São Paulo) fora do Streamlit.

Mesmo caminho das telas: lat/lon → POIs do OSM → features (montar_entrada_modelo)
→ modelo @champion do MLflow. Também calcula o custo total pelo % de condomínio +
IPTU do bairro e lista os POIs próximos (para o mapa do frontend).
"""

import os
import threading
import time
import unicodedata

import numpy as np
import pandas as pd

from src.features.aluguel import (CAT_FEATURES, CRS_GEO, CRS_M, NUM_FEATURES,
                                  carregar_pois_sp, dentro_de_sp, montar_entrada_modelo)
from src.inferencia import pacote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL_NAME = "RentPriceModel_SP"
OSM_DIR = os.path.join(ROOT, "data", "raw", "osm")
CUSTO_PATH = os.path.join(ROOT, "data", "interim", "aluguel_custo_extra_bairro.parquet")

# Tipo enviado pela API → valor de `type` usado no treino
TIPOS_API = {
    "apartamento": "Apartamento",
    "studio": "StudioOuKitchenette",
    "casa": "Casa",
    "casa_condominio": "CasaCondominio",
}

# Categorias de POI mostradas no mapa: categoria do modelo → nome exposto pela API
CATEGORIAS_MAPA = {
    "metro": "metro", "trem": "trem", "escola_publica": "escola_publica",
    "escola_privada": "escola_privada", "hospital": "hospital", "farmacia": "farmacia",
    "supermercado": "mercado", "parque": "parque", "policia": "delegacia",
}
RAIO_MAPA_M = 1500
POR_CATEGORIA = 3

INTERVALO_CHAMPION_S = 60  # um retreino promovido entra sem reiniciar a API


# ============================================================
# Funções puras (também usadas pelas telas do Streamlit)
# ============================================================

def _normalizar(txt) -> str:
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return txt.lower().strip()


def custo_extra_do_bairro(bairro, tabela):
    """Procura o bairro (sem acento) na tabela; sem correspondência, usa a mediana da cidade."""
    cidade = tabela[tabela["fonte"] == "cidade"]
    padrao = cidade.iloc[0] if len(cidade) else tabela.median(numeric_only=True)

    if bairro:
        chave = _normalizar(bairro)
        for col in ["neighbourhood", "regionName"]:
            achou = tabela[tabela[col].map(_normalizar) == chave]
            if len(achou):
                return achou.iloc[0], f"{bairro} ({achou.iloc[0]['fonte']})"
    return padrao, "mediana da cidade"


def montar_registro(geo: dict, imovel: dict, entrada: pd.DataFrame, aluguel_predito: float,
                    aluguel_anuncio, pct_extra, versao_modelo, origem: str) -> dict:
    """Dicionário com as colunas de predicoes_aluguel."""
    erro_abs = erro_pct = None
    if aluguel_anuncio is not None and not pd.isna(aluguel_anuncio) and aluguel_anuncio > 0:
        erro_abs = abs(aluguel_predito - aluguel_anuncio)
        erro_pct = erro_abs / aluguel_anuncio
    else:
        aluguel_anuncio = None

    return {
        "endereco": geo.get("endereco_formatado"),
        "bairro": geo.get("bairro"),
        "latitude": geo["lat"],
        "longitude": geo["lng"],
        "tipo_imovel_cat": entrada["tipo_imovel_cat"].iloc[0],
        **{k: imovel[k] for k in ["area", "bedrooms", "bathrooms", "suites", "parkingSpaces", "mobiliado",
                                  "am_ar_condicionado", "inst_piscina", "inst_academia", "am_varanda"]},
        "aluguel_anuncio": aluguel_anuncio,
        "aluguel_predito": aluguel_predito,
        "pct_custo_extra": pct_extra,
        "custo_total_estimado": aluguel_predito * (1 + pct_extra) if pct_extra is not None else None,
        "erro_absoluto": erro_abs,
        "erro_percentual": erro_pct,
        "modelo": MODEL_NAME,
        "versao_modelo": str(versao_modelo),
        "origem": origem,
    }


def features_para_monitoramento(entrada: pd.DataFrame) -> dict:
    return {c: float(entrada[c].iloc[0]) for c in NUM_FEATURES}


def prever_aluguel(modelo, entrada: pd.DataFrame) -> np.ndarray:
    """Aluguel em R$ (o modelo prevê log do aluguel)."""
    return np.exp(modelo.predict(entrada[NUM_FEATURES + CAT_FEATURES]))


# ============================================================
# Serviço usado pela API
# ============================================================

class ServicoAluguel:
    """Carrega POIs e a tabela de custo uma vez; o modelo segue o @champion."""

    def __init__(self):
        self.pois = carregar_pois_sp(OSM_DIR)
        custo = os.path.join(pacote.PACOTE_DIR, os.path.basename(CUSTO_PATH)) if pacote.ativo() else CUSTO_PATH
        self.custo = pd.read_parquet(custo) if os.path.exists(custo) else None
        # Ponto representativo de cada POI em lat/lon, para desenhar no mapa
        self.pontos = {
            cat: g.geometry.representative_point().to_crs(CRS_GEO)
            for cat, g in self.pois.items() if cat in CATEGORIAS_MAPA
        }
        self._lock = threading.Lock()
        self._versao = None
        self._modelo = None
        self._mae_log = None
        self._info = {}
        self._checado_em = 0.0

    def _carregar_pacote(self):
        self._modelo, meta = pacote.carregar_modelo("aluguel")
        self._versao, self._mae_log, self._info = meta["versao"], meta["mae_log"], meta

    def _carregar_mlflow(self):
        import mlflow.sklearn
        from datetime import datetime, timezone

        from src.models.registro import cliente, versao_champion

        client = cliente()
        v = versao_champion(MODEL_NAME, client)
        if v.version == self._versao:
            return
        run = client.get_run(v.run_id)
        m = run.data.metrics
        self._modelo = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{v.version}")
        self._versao, self._mae_log = v.version, m["mae"]
        self._info = {
            "versao": v.version,
            "mae_log": m["mae"],
            "treinado_em": datetime.fromtimestamp(run.info.start_time / 1000, timezone.utc).isoformat(),
            "n_treino": int(run.data.params.get("n_train", 0)) or None,
            "metricas": {"r2": m["r2"], "mae_reais": m.get("mae_reais"), "mape": m.get("mape_reais")},
        }

    def modelo(self):
        """
        (modelo, versão, MAE em log) do @champion. No modo pacote (nuvem) é fixo; com MLflow
        é conferido a cada minuto, então um retreino promovido entra sem reiniciar a API.
        """
        with self._lock:
            if pacote.ativo():
                if self._modelo is None:
                    self._carregar_pacote()
            elif time.time() - self._checado_em > INTERVALO_CHAMPION_S:
                self._carregar_mlflow()
                self._checado_em = time.time()
            return self._modelo, self._versao, self._mae_log

    def info(self) -> dict:
        """Versão, data de treino, tamanho do treino e métricas do modelo em produção."""
        self.modelo()
        return self._info

    def pois_proximos(self, lat: float, lon: float) -> list[dict]:
        """Até 3 POIs por categoria num raio de 1,5 km (sempre ao menos o mais próximo)."""
        import geopandas as gpd
        from shapely.geometry import Point

        ponto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_GEO).to_crs(CRS_M).iloc[0]
        saida = []
        for cat, g in self.pois.items():
            if cat not in CATEGORIAS_MAPA or g.empty:
                continue
            dist = g.geometry.distance(ponto).to_numpy()
            ordem = np.argsort(dist)
            escolhidos = [i for i in ordem[:POR_CATEGORIA] if dist[i] <= RAIO_MAPA_M] or [ordem[0]]
            for i in escolhidos:
                p = self.pontos[cat].iloc[i]
                nome = g["name"].iloc[i]
                saida.append({
                    "categoria": CATEGORIAS_MAPA[cat],
                    "nome": None if pd.isna(nome) or not str(nome).strip() else str(nome),
                    "lat": round(p.y, 6),
                    "lon": round(p.x, 6),
                    "distancia_m": round(float(dist[i])),
                })
        return sorted(saida, key=lambda d: d["distancia_m"])

    def prever(self, geo: dict, req: dict) -> tuple[dict, dict]:
        """
        ``geo``: saída do geocoding; ``req``: campos do POST /aluguel/prever.
        Devolve (resposta da API, registro para predicoes_aluguel + features).
        """
        if not dentro_de_sp(geo["lat"], geo["lon"]):
            raise ValueError("O endereço fica fora da cidade de São Paulo (o modelo cobre só a capital).")

        imovel = {
            "type": TIPOS_API[req["tipo"]],
            "area": float(req["area"]),
            "bedrooms": int(req["quartos"]),
            "bathrooms": int(req["banheiros"]),
            "suites": int(req["suites"]),
            "parkingSpaces": int(req["vagas"]),
            "mobiliado": int(req["mobiliado"]),
            "am_ar_condicionado": int(req["ar_condicionado"]),
            "inst_piscina": int(req["piscina"]),
            "inst_academia": int(req["academia"]),
            "am_varanda": int(req["varanda"]),
        }
        modelo, versao, mae_log = self.modelo()
        entrada = montar_entrada_modelo(geo["lat"], geo["lon"], imovel, self.pois)
        estimado = float(prever_aluguel(modelo, entrada)[0])
        faixa = {"min": round(estimado * np.exp(-mae_log), 2), "max": round(estimado * np.exp(mae_log), 2)}

        pct = None
        if self.custo is not None:
            pct = float(custo_extra_do_bairro(geo.get("bairro"), self.custo)[0]["pct_extra_mediana"])

        anunciado = req.get("aluguel_anunciado")
        comparacao = None
        if anunciado:
            classe = "abaixo" if anunciado < faixa["min"] else ("acima" if anunciado > faixa["max"] else "dentro")
            comparacao = {"aluguel_anunciado": anunciado,
                          "diferenca_pct": round(anunciado / estimado - 1, 4), "classificacao": classe}

        resposta = {
            "aluguel_estimado": round(estimado, 2),
            "faixa": faixa,
            "custo_extra_pct": pct,
            "custo_total_estimado": round(estimado * (1 + pct), 2) if pct is not None else None,
            "bairro": geo.get("bairro"),
            "localizacao": {"lat": geo["lat"], "lon": geo["lon"], "endereco_formatado": geo["endereco_formatado"]},
            "pois_proximos": self.pois_proximos(geo["lat"], geo["lon"]),
            "comparacao": comparacao,
            "modelo": {"nome": MODEL_NAME, "versao": f"v{versao}"},
        }
        geo_registro = {**geo, "lng": geo["lon"]}
        registro = montar_registro(geo_registro, imovel, entrada, estimado, anunciado, pct, versao, origem="api")
        return resposta, {"registro": registro, "features": features_para_monitoramento(entrada)}
