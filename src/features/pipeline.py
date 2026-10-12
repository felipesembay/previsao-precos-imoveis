"""
Feature Engineering para o projeto de precificação de imóveis.
Extrai scores de proximidade a POIs e cria variáveis derivadas.

Adaptado do notebook EDA.ipynb — lógica 100% preservada.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

# ============================================================
# 1. Scores de proximidade (mesma fórmula do EDA.ipynb)
# ============================================================

def add_poi_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cria os scores de proximidade a POIs.
    Espera que as colunas dist_* e qtd_* já existam no DataFrame.
    """
    df = df.copy()

    df["score_escola_privada"] = (
        1.2 * np.exp(-df["dist_escolas_privadas_mais_proximo"] / 600)
        + 0.6 * df["qtd_escolas_privadas_500m"]
    )

    df["score_escola_publica"] = (
        0.6 * np.exp(-df["dist_escola_publicas_mais_proximo"] / 600)
        + 0.2 * df["qtd_escola_publicas_500m"]
    )

    df["score_hospitais"] = (
        0.8 * np.exp(-df["dist_hospital_mais_proximo"] / 1200)
        + 0.4 * df["qtd_hospital_1000m"]
    )

    df["score_mercado"] = (
        1.0 * np.exp(-df["dist_mercado_mais_proximo"] / 400)
        + 0.4 * df["qtd_mercado_500m"]
    )

    df["score_farmacia"] = (
        0.6 * np.exp(-df["dist_farmacia_mais_proximo"] / 300)
        + 0.2 * df["qtd_farmacia_300m"]
    )

    df["score_parque"] = (
        1.2 * np.exp(-df["dist_parque_mais_proximo"] / 1200)
        + 0.8 * df["qtd_parque_1000m"]
    )

    df["score_seguranca"] = (
        1.0 * np.exp(-df["dist_policia_mais_proximo"] / 1500)
        + 0.3 * df["qtd_policia_500m"]
    )

    df["score_educacao"] = (
        df["score_escola_privada"]
        - 0.2 * df["score_escola_publica"]
    )

    return df


# ============================================================
# 2. Classificação de tipo de imóvel (do EDA.ipynb)
# ============================================================

def classificar_tipo_imovel(tipo: str) -> str:
    if pd.isna(tipo):
        return "outros"

    tipo = str(tipo).lower()

    if "terreno" in tipo or "lote" in tipo:
        return "terreno"
    if any(x in tipo for x in ["apartamento", "cobertura", "duplex", "flat", "kitnet"]):
        return "apartamento"
    if any(x in tipo for x in ["casa", "sobrado", "vila"]):
        return "casa"
    if any(x in tipo for x in ["comercial", "loja", "box", "galpão", "deposito", "depósito", "sala", "conjunto"]):
        return "comercial"
    if "prédio" in tipo or "edificio" in tipo or "edifício" in tipo:
        return "predio"

    return "outros"

# ============================================================
# É sobrado?
def add_is_sobrado(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_sobrado"] = (
        df["tipo_imovel"]
        .str.lower()
        .str.contains("sobrado", na=False)
        .astype(int)
    )
    return df


# ============================================================
# 3. Faixa de área (do ML.ipynb)
# ============================================================

AREA_BINS = [0, 50, 80, 120, 200, 400, float("inf")]
AREA_LABELS = ["Até 50", "50–80", "80–120", "120–200", "200–400", "400+"]


def add_faixa_area(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["faixa_area"] = pd.cut(
        df["area_m2"], bins=AREA_BINS, labels=AREA_LABELS
    )
    return df


# ============================================================
# 4. Pipeline completo de feature engineering
# ============================================================

def prepare_dataset(
    path: str,
    tipos_validos: list = None,
) -> pd.DataFrame:
    """
    Lê o complete.csv e devolve o DataFrame pronto para treinar.
    Reproduz exatamente o que os notebooks faziam.
    """
    if tipos_validos is None:
        tipos_validos = ["casa", "apartamento", "comercial"]

    df = pd.read_csv(path)

    # Remover coluna index se existir
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    # Scores de POI
    df = add_poi_scores(df)

    # Classificar tipo
    df["tipo_imovel_cat"] = df["tipo_imovel"].apply(classificar_tipo_imovel)

    # Filtrar tipos válidos
    df = df[df["tipo_imovel_cat"].isin(tipos_validos)].copy()
    
    # É sobrado?
    df = add_is_sobrado(df)

    # Faixa de área
    df = add_faixa_area(df)

    # Target em log
    df["log_preco"] = np.log(df["preco"].clip(lower=1))

    # Preencher NaN numéricos com mediana
    cols_numericas = df.select_dtypes(include=["float64", "int64"]).columns
    df[cols_numericas] = df[cols_numericas].apply(lambda x: x.fillna(x.median()))

    return df


# ============================================================
# 5. Definição das features (centralizado)
# ============================================================

NUM_FEATURES = [
    "quartos",
    "banheiros",
    "vagas_garagem",
    "area_m2",
    "score_escola_privada",
    "score_escola_publica",
    "score_hospitais",
    "score_mercado",
    "score_farmacia",
    "score_parque",
    "score_seguranca", 
    "is_sobrado"
]

CAT_FEATURES = ["tipo_imovel_cat"]

TARGET = "log_preco"
