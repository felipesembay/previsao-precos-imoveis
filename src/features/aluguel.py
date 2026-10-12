"""
Feature engineering do modelo de aluguel (São Paulo capital, dados QuintoAndar).

Usado pelos notebooks 05_features e 06_modelagem e, depois, pelo pipeline de
treino/serving. Os transformers ficam aqui (e não no notebook) para que o modelo
salvo em pickle consiga importá-los.

Duas camadas:
1. ``criar_features``: transformações linha a linha, sem aprendizado
   (não olham o alvo, então podem ser aplicadas antes do split).
2. Transformers sklearn que aprendem com o treino (``KNNTargetEncoder``,
   ``QuantileClipper``) e entram dentro do Pipeline, para não vazar o alvo.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.neighbors import BallTree
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, TargetEncoder

RAIO_TERRA_KM = 6371.0

# Marco zero e polos de emprego/valor (coordenadas aproximadas)
CENTRO = (-23.5503, -46.6340)  # Praça da Sé
POLOS = {
    "faria_lima": (-23.5845, -46.6830),
    "paulista": (-23.5614, -46.6559),
    "berrini": (-23.6090, -46.6950),
}

CATS_POI = [
    "escola_publica", "escola_privada", "ensino_superior", "hospital",
    "farmacia", "supermercado", "conveniencia", "policia",
    "metro", "trem", "parque", "praca",
]

TARGET = "log_rent"

# ============================================================
# 0. Modelo de produção (mesmo padrão de compra/ML3 e do notebook 06)
# ============================================================

# Localização entra só via geocoding (lat/lon -> POIs e distâncias), como no projeto de compra
NUM_FEATURES = [
    "bedrooms", "bathrooms", "parkingSpaces", "area", "suites",
    "score_escola_privada", "score_escola_publica",
    "score_hospitais", "score_mercado",
    "score_farmacia", "score_parque", "score_seguranca", "score_metro",
    "mobiliado", "am_ar_condicionado", "inst_piscina", "inst_academia", "am_varanda",
    "dist_centro_km", "dist_polo_km",
]
CAT_FEATURES = ["tipo_imovel_cat"]

MAPA_TIPO = {
    "Apartamento": "apartamento",
    "StudioOuKitchenette": "studio",
    "Casa": "casa",
    "CasaCondominio": "casa_condominio",
}


def add_poi_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Scores de proximidade: mesma fórmula do projeto de compra (src/features/pipeline.py)."""
    df = df.copy()
    df["score_escola_privada"] = 1.2 * np.exp(-df["dist_escola_privada"] / 600) + 0.6 * df["qtd_escola_privada_500m"]
    df["score_escola_publica"] = 0.6 * np.exp(-df["dist_escola_publica"] / 600) + 0.2 * df["qtd_escola_publica_500m"]
    df["score_hospitais"] = 0.8 * np.exp(-df["dist_hospital"] / 1200) + 0.4 * df["qtd_hospital_1km"]
    df["score_mercado"] = 1.0 * np.exp(-df["dist_supermercado"] / 400) + 0.4 * df["qtd_supermercado_500m"]
    # contagem em 300 m não existe na base do aluguel -> usa 500 m
    df["score_farmacia"] = 0.6 * np.exp(-df["dist_farmacia"] / 300) + 0.2 * df["qtd_farmacia_500m"]
    df["score_parque"] = 1.2 * np.exp(-df["dist_parque"] / 1200) + 0.8 * df["qtd_parque_1km"]
    df["score_seguranca"] = 1.0 * np.exp(-df["dist_policia"] / 1500) + 0.3 * df["qtd_policia_500m"]
    df["score_educacao"] = df["score_escola_privada"] - 0.2 * df["score_escola_publica"]
    df["score_metro"] = 1.0 * np.exp(-df["dist_metro"] / 800) + 0.3 * df["qtd_metro_1km"]
    return df


def prepare_dataset(path) -> pd.DataFrame:
    """Lê aluguel_sp_features.parquet (notebook 05) e devolve o DataFrame pronto para treinar."""
    df = pd.read_parquet(path)
    df = add_poi_scores(df)
    df["tipo_imovel_cat"] = df["type"].map(MAPA_TIPO)
    df[TARGET] = np.log(df["rent"].clip(lower=1))
    return df


# ============================================================
# 1. Features determinísticas (linha a linha)
# ============================================================

def haversine_km(lat, lon, lat0, lon0):
    lat, lon, lat0, lon0 = map(np.radians, (lat, lon, lat0, lon0))
    a = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat) * np.cos(lat0) * np.sin((lon - lon0) / 2) ** 2
    return 2 * RAIO_TERRA_KM * np.arcsin(np.sqrt(a))


def criar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria as features que não dependem do alvo. Espera as colunas do notebook 03."""
    df = df.copy()

    # Planta
    df["log_area"] = np.log(df["area"])
    quartos = df["bedrooms"].clip(lower=1)
    df["area_por_quarto"] = df["area"] / quartos
    df["banheiros_por_quarto"] = df["bathrooms"] / quartos
    df["mobiliado"] = df["isFurnished"].fillna(False).astype(int)
    df["log_condominio"] = np.log1p(df["iptuPlusCondominium"])

    # Localização (regiões raras são tratadas pelos encoders: min_frequency / suavização)
    df["regiao"] = df["regionName"].astype(str)
    df["dist_centro_km"] = haversine_km(df["lat"], df["lon"], *CENTRO)
    for nome, (lat0, lon0) in POLOS.items():
        df[f"dist_{nome}_km"] = haversine_km(df["lat"], df["lon"], lat0, lon0)
    df["dist_polo_km"] = df[[f"dist_{n}_km" for n in POLOS]].min(axis=1)
    # Coordenadas rotacionadas: ajudam árvores a cortar o mapa em diagonais
    for ang in (15, 30, 45, 60):
        t = np.radians(ang)
        df[f"rot{ang}_x"] = df["lon"] * np.cos(t) - df["lat"] * np.sin(t)
        df[f"rot{ang}_y"] = df["lon"] * np.sin(t) + df["lat"] * np.cos(t)

    # POIs (distância e acessibilidade em log)
    for c in CATS_POI:
        df[f"logdist_{c}"] = np.log(df[f"dist_{c}"] + 50)
        df[f"logacess_{c}"] = np.log1p(df[f"acess_{c}"])
    df["dist_transporte"] = df[["dist_metro", "dist_trem"]].min(axis=1)
    df["logdist_transporte"] = np.log(df["dist_transporte"] + 50)

    return df


# ============================================================
# 2. Transformers que aprendem com o treino
# ============================================================

class KNNTargetEncoder(BaseEstimator, TransformerMixin):
    """
    Preço da vizinhança: média e mediana de log(R$/m²) dos k anúncios de treino
    mais próximos, mais a distância média até eles (densidade de oferta).

    Espera as colunas ``lat``, ``lon`` e ``log_area``; ``y`` é log(rent), e o
    encoder converte para log(R$/m²) = y − log_area.

    No ``fit_transform`` (treino) o próprio anúncio é excluído dos vizinhos;
    sem isso a feature contém o alvo da linha e o modelo "cola".
    """

    def __init__(self, k: int = 15):
        self.k = k

    def _coords(self, X):
        X = pd.DataFrame(X, columns=["lat", "lon", "log_area"]) if not isinstance(X, pd.DataFrame) else X
        return np.radians(X[["lat", "lon"]].to_numpy(dtype=float)), X["log_area"].to_numpy(dtype=float)

    def fit(self, X, y):
        coords, log_area = self._coords(X)
        self.tree_ = BallTree(coords, metric="haversine")
        self.valores_ = np.asarray(y, dtype=float) - log_area
        self.n_features_in_ = 3
        return self

    def _agregar(self, dist, ind):
        v = self.valores_[ind]
        return np.column_stack([v.mean(axis=1), np.median(v, axis=1), dist.mean(axis=1) * RAIO_TERRA_KM])

    def transform(self, X):
        coords, _ = self._coords(X)
        dist, ind = self.tree_.query(coords, k=self.k)
        return self._agregar(dist, ind)

    def fit_transform(self, X, y=None, **fit_params):
        self.fit(X, y)
        coords, _ = self._coords(X)
        dist, ind = self.tree_.query(coords, k=self.k + 1)
        # Remove o próprio ponto (pode não estar na coluna 0 se houver coordenadas repetidas)
        proprio = ind == np.arange(len(ind))[:, None]
        sem_proprio = ~proprio
        sem_proprio[~proprio.any(axis=1), -1] = False  # se o próprio não apareceu, descarta o mais distante
        ind = ind[sem_proprio].reshape(len(ind), self.k)
        dist = dist[sem_proprio].reshape(len(dist), self.k)
        return self._agregar(dist, ind)

    def get_feature_names_out(self, input_features=None):
        return np.array([f"knn{self.k}_logm2_media", f"knn{self.k}_logm2_mediana", f"knn{self.k}_dist_km"])


class QuantileClipper(BaseEstimator, TransformerMixin):
    """Limita cada coluna aos quantis do treino (mesmo transformer dos notebooks de compra)."""

    def __init__(self, lower: float = 0.01, upper: float = 0.99):
        self.lower = lower
        self.upper = upper

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.q_low_ = X.quantile(self.lower).to_numpy()
        self.q_high_ = X.quantile(self.upper).to_numpy()
        self.n_features_in_ = X.shape[1]
        return self

    def transform(self, X):
        return np.clip(np.asarray(X, dtype=float), self.q_low_, self.q_high_)

    def get_feature_names_out(self, input_features=None):
        return np.asarray(input_features) if input_features is not None else None


# ============================================================
# 3. Conjuntos de features
# ============================================================

PLANTA = ["log_area", "bedrooms", "bathrooms", "suites", "parkingSpaces",
          "area_por_quarto", "banheiros_por_quarto"]
ATRIBUTOS = ["mobiliado", "n_amenities", "n_instalacoes", "cond_exclusividade", "cond_negociado"]
LOCAL = ["lat", "lon", "dist_centro_km", "dist_polo_km",
         *[f"dist_{n}_km" for n in POLOS],
         *[f"rot{a}_{e}" for a in (15, 30, 45, 60) for e in ("x", "y")]]
POI = ([f"logdist_{c}" for c in CATS_POI] + [f"logacess_{c}" for c in CATS_POI]
       + ["logdist_transporte", "pct_escola_privada_1km"])
CONDOMINIO = ["log_condominio"]


def colunas_amenities(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c.startswith(("am_", "inst_"))]


def conjuntos_features(df: pd.DataFrame) -> dict:
    """
    Conjuntos cumulativos usados na grade do notebook 06.
    ``num``: numéricas; ``cat``: categóricas; ``knn``: usa o KNNTargetEncoder.
    """
    amen = colunas_amenities(df)
    base = PLANTA + ATRIBUTOS + amen
    return {
        "S1 · imóvel": {"num": base, "cat": ["type"], "knn": False},
        "S2 · + localização": {"num": base + LOCAL, "cat": ["type", "regiao"], "knn": False},
        "S3 · + POIs": {"num": base + LOCAL + POI, "cat": ["type", "regiao"], "knn": False},
        "S4 · + vizinhança": {"num": base + LOCAL + POI, "cat": ["type", "regiao"], "knn": True},
        "S5 · + condomínio": {"num": base + LOCAL + POI + CONDOMINIO, "cat": ["type", "regiao"], "knn": True},
    }


def montar_preprocessador(fs: dict, linear: bool, k_vizinhos: int = 15) -> ColumnTransformer:
    """
    Pré-processamento de um conjunto de features.

    - Modelos lineares: imputação + clip de quantis + padronização; região em one-hot (efeito fixo).
    - Árvores: numéricas sem escala; região via TargetEncoder (com cross-fitting interno do sklearn).
    """
    if linear:
        num = Pipeline([("imp", SimpleImputer(strategy="median")),
                        ("clip", QuantileClipper(0.01, 0.99)),
                        ("esc", StandardScaler())])
    else:
        num = SimpleImputer(strategy="median", keep_empty_features=True)

    partes = [("num", num, fs["num"]),
              ("tipo", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["type"])]
    if "regiao" in fs["cat"]:
        reg = (OneHotEncoder(handle_unknown="ignore", sparse_output=False, min_frequency=30) if linear
               else TargetEncoder(target_type="continuous", random_state=42))
        partes.append(("regiao", reg, ["regiao"]))
    if fs["knn"]:
        knn = KNNTargetEncoder(k=k_vizinhos)
        partes.append(("knn", Pipeline([("knn", knn), ("esc", StandardScaler())]) if linear else knn,
                       ["lat", "lon", "log_area"]))
    ct = ColumnTransformer(partes, verbose_feature_names_out=False)
    return ct.set_output(transform="pandas")


def colunas_entrada(fs: dict) -> list:
    """Colunas brutas que o pré-processador de um conjunto precisa receber."""
    cols = fs["num"] + fs["cat"] + (["lat", "lon", "log_area"] if fs["knn"] else [])
    return list(dict.fromkeys(cols))
