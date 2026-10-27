"""
Inferência do modelo de compra (cidades com POIs na tabela `pois`) fora do Streamlit.

Mesmo cálculo da tela de compra em lote (streamlit_app/batch_app.py): POIs da tabela
`pois` do banco → distâncias e contagens (BallTree haversine) → scores → modelo.
"""

import threading
import time
import unicodedata

import numpy as np
from sklearn.neighbors import BallTree

from src.inferencia import pacote
from src.models.predict import predict

MODEL_NAME = "RealEstatePriceModel"
EXPERIMENTO = "price_house_ponta_grossa_version2"   # o mesmo de src.models.predict.load_model
VERSAO = "2.0.0"           # rótulo gravado em `predicoes` pelas telas de compra
TIPOS = ["casa", "apartamento", "comercial"]
RAIO_TERRA_M = 6_371_000

RAIOS_M = {"hospital": 1000, "mercado": 500, "farmacia": 300, "escola": 500, "parque": 1000, "policia": 500}
PLURAL = {"hospital": "hospitais", "mercado": "mercados", "farmacia": "farmacias",
          "escola": "escolas", "parque": "parques", "policia": "policia"}
CATEGORIAS_MAPA = {"escola": "escola", "hospital": "hospital", "farmacia": "farmacia",
                   "mercado": "mercado", "parque": "parque", "policia": "delegacia"}
RAIO_MAPA_M = 1500
POR_CATEGORIA = 3
RECARGA_POIS_S = 3600


def _norm(texto) -> str:
    """Minúsculas e sem acentos, para casar nomes de cidade do geocoding com o banco."""
    sem = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sem.lower().split())


def calcular_features_poi(lat: float, lon: float, pois_por_tipo: dict) -> dict:
    imovel = np.radians([[lat, lon]])
    features = {}
    for tipo, raio in RAIOS_M.items():
        plural = PLURAL[tipo]
        coords = pois_por_tipo.get(tipo, [])
        if not coords:
            features[f"dist_{plural}_mais_proximo"] = 99_999.0
            features[f"qtd_{plural}_{raio}m"] = 0
            continue
        tree = BallTree(np.radians([(c["lat"], c["lon"]) for c in coords]), metric="haversine")
        dist, _ = tree.query(imovel, k=1)
        features[f"dist_{plural}_mais_proximo"] = float(dist[0, 0] * RAIO_TERRA_M)
        features[f"qtd_{plural}_{raio}m"] = int(tree.query_radius(imovel, r=raio / RAIO_TERRA_M, count_only=True)[0])
    return features


def calcular_scores(f: dict) -> dict:
    return {
        "score_escola_privada": 1.2 * np.exp(-f["dist_escolas_mais_proximo"] / 600) + 0.6 * f["qtd_escolas_500m"],
        "score_escola_publica": 0.6 * np.exp(-f["dist_escolas_mais_proximo"] / 600) + 0.2 * f["qtd_escolas_500m"],
        "score_hospitais": 0.8 * np.exp(-f["dist_hospitais_mais_proximo"] / 1200) + 0.4 * f["qtd_hospitais_1000m"],
        "score_mercado": 1.0 * np.exp(-f["dist_mercados_mais_proximo"] / 400) + 0.4 * f["qtd_mercados_500m"],
        "score_farmacia": 0.6 * np.exp(-f["dist_farmacias_mais_proximo"] / 300) + 0.2 * f["qtd_farmacias_300m"],
        "score_parque": 1.2 * np.exp(-f["dist_parques_mais_proximo"] / 1200) + 0.8 * f["qtd_parques_1000m"],
        "score_seguranca": 1.0 * np.exp(-f["dist_policia_mais_proximo"] / 1500) + 0.3 * f["qtd_policia_500m"],
    }


def _haversine_m(lat, lon, lats, lons):
    lat, lon, lats, lons = map(np.radians, (lat, lon, np.asarray(lats), np.asarray(lons)))
    a = np.sin((lats - lat) / 2) ** 2 + np.cos(lat) * np.cos(lats) * np.sin((lons - lon) / 2) ** 2
    return 2 * RAIO_TERRA_M * np.arcsin(np.sqrt(a))


class ServicoCompra:
    """Modelo carregado uma vez; POIs de todas as cidades lidos do banco e recarregados a cada hora."""

    def __init__(self, conectar):
        self._conectar = conectar          # função que abre conexão (dict_row) com o banco do app
        if pacote.ativo():
            self.modelo, self.meta = pacote.carregar_modelo("compra")
        else:
            self.modelo, self.meta = self._carregar_mlflow()
        self.mae_log = float(self.meta["mae_log"])
        self._cidades = None
        self._pois_em = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def _carregar_mlflow():
        import mlflow
        import pandas as pd

        from src.models.predict import load_model

        exp = mlflow.get_experiment_by_name(EXPERIMENTO)
        run = mlflow.search_runs([exp.experiment_id], order_by=["start_time DESC"], max_results=1).iloc[0]
        meta = {
            "versao": "2",
            "mae_log": float(run["metrics.mae"]),
            "treinado_em": pd.Timestamp(run["start_time"]).isoformat(),
            "n_treino": int(run.get("params.n_train") or 0) or None,
            # O treino do compra só registrou métricas em escala log
            "metricas": {"r2": float(run["metrics.r2"]), "mae_reais": None, "mape": None},
        }
        return load_model(), meta

    def _recarregar(self):
        """Lê todas as cidades da tabela `pois` (qualquer cidade cadastrada vira atendida)."""
        with self._conectar() as conn:
            linhas = conn.execute(
                "SELECT cidade, estado, tipo_poi, nome, latitude, longitude FROM pois"
            ).fetchall()
        cidades: dict = {}
        for r in linhas:
            if r["tipo_poi"] not in RAIOS_M:
                continue
            chave = (_norm(r["cidade"]), (r["estado"] or "").strip().upper())
            c = cidades.setdefault(chave, {"cidade": (r["cidade"] or "").strip(), "uf": chave[1],
                                           "pois": {t: [] for t in RAIOS_M}})
            nome = (r["nome"] or "").strip()
            c["pois"][r["tipo_poi"]].append({"nome": None if nome.lower() in ("", "nan", "none") else nome,
                                             "lat": float(r["latitude"]), "lon": float(r["longitude"])})
        self._cidades, self._pois_em = cidades, time.time()

    def _cidades_atuais(self) -> dict:
        with self._lock:
            if self._cidades is None or time.time() - self._pois_em > RECARGA_POIS_S:
                self._recarregar()
            return self._cidades

    def cidades(self) -> list[dict]:
        """Cidades com POIs cadastrados, em ordem alfabética."""
        return sorted(({"cidade": c["cidade"], "uf": c["uf"]} for c in self._cidades_atuais().values()),
                      key=lambda d: (d["cidade"], d["uf"]))

    def pois(self, geo: dict) -> dict | None:
        """POIs da cidade do endereço geocodificado; None se a cidade não está cadastrada."""
        cidades = self._cidades_atuais()
        nome, uf = _norm(geo.get("cidade")), (geo.get("uf") or "").strip().upper()
        c = cidades.get((nome, uf))
        if c is None:  # UF ausente/divergente no geocoding: aceita se o nome for único
            candidatas = [v for (n, _), v in cidades.items() if n == nome]
            c = candidatas[0] if len(candidatas) == 1 else None
        return c["pois"] if c else None

    def pois_proximos(self, lat: float, lon: float, pois: dict) -> list[dict]:
        saida = []
        for tipo, lista in pois.items():
            if not lista:
                continue
            dist = _haversine_m(lat, lon, [p["lat"] for p in lista], [p["lon"] for p in lista])
            ordem = np.argsort(dist)
            escolhidos = [i for i in ordem[:POR_CATEGORIA] if dist[i] <= RAIO_MAPA_M] or [ordem[0]]
            for i in escolhidos:
                p = lista[i]
                saida.append({"categoria": CATEGORIAS_MAPA[tipo], "nome": p["nome"] or None,
                              "lat": p["lat"], "lon": p["lon"], "distancia_m": round(float(dist[i]))})
        return sorted(saida, key=lambda d: d["distancia_m"])

    def prever(self, geo: dict, req: dict) -> tuple[dict, dict]:
        """Devolve (resposta da API, dados para salvar em `predicoes`)."""
        pois = self.pois(geo)
        if pois is None:
            atendidas = ", ".join(f"{c['cidade']}/{c['uf']}" for c in self.cidades())
            raise ValueError(f"Sem POIs cadastrados para {geo.get('cidade')}. Cidades atendidas: {atendidas}.")

        scores = calcular_scores(calcular_features_poi(geo["lat"], geo["lon"], pois))
        dados = {
            "area_m2": float(req["area"]),
            "endereco": geo["endereco_formatado"],
            "quartos": int(req["quartos"]),
            "banheiros": int(req["banheiros"]),
            "vagas_garagem": int(req["vagas"]),
            "tipo_imovel_cat": req.get("tipo") or "casa",
            "is_sobrado": int(bool(req.get("sobrado"))),
            "preco_anuncio": req.get("preco_anunciado"),
            **{k: float(v) for k, v in scores.items()},
        }
        estimado = predict(self.modelo, dados)["preco_estimado"]

        resposta = {
            "preco_estimado": round(estimado, 2),
            "faixa": {"min": round(estimado * np.exp(-self.mae_log), 2),
                      "max": round(estimado * np.exp(self.mae_log), 2)},
            "localizacao": {"lat": geo["lat"], "lon": geo["lon"], "endereco_formatado": geo["endereco_formatado"]},
            "pois_proximos": self.pois_proximos(geo["lat"], geo["lon"], pois),
            "modelo": {"nome": MODEL_NAME, "versao": VERSAO},
        }
        return resposta, {"dados": dados, "scores": scores, "preco": estimado}
