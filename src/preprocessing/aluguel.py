"""
Pipeline de dados do modelo de aluguel em script (usado pelo retreino no Airflow).

Reproduz, sem a parte exploratória, o que os notebooks fazem para chegar em
data/interim/aluguel_sp_features.parquet:
  01_limpeza_eda  → limpar()             filtros e remoção de duplicatas/outliers
  03_poi_eda      → adicionar_pois()     dist_<cat>, qtd_<cat>_500m, qtd_<cat>_1km
  05_features     → adicionar_features() mobiliado, dist_centro_km, dist_polo_km

Só as colunas que o modelo de produção usa são criadas (NUM_FEATURES de
src/features/aluguel.py); o resto do notebook é análise.

Uso:
    python -m src.preprocessing.aluguel --raw data/raw/quintoandar/X.parquet --saida data/interim/Y.parquet
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.features.aluguel import (CENTRO, CRS_GEO, CRS_M, LIMITES_SP,  # noqa: E402
                                  NUM_FEATURES, POLOS, carregar_pois_sp,
                                  haversine_km, prepare_dataset)

OSM_DIR = os.path.join(_ROOT, "data", "raw", "osm")

CHAVE_DUP = ["lat", "lon", "area", "bedrooms", "bathrooms", "parkingSpaces", "rent", "iptuPlusCondominium"]

# Flags de amenities/instalações usadas pelo modelo: coluna → valor na lista da API
FLAGS = {
    "am_ar_condicionado": ("amenities", "AR_CONDICIONADO"),
    "am_varanda": ("amenities", "VARANDA"),
    "inst_piscina": ("installations", "PISCINA"),
    "inst_academia": ("installations", "ACADEMIA"),
}

MIN_LINHAS = 5_000  # abaixo disso a extração provavelmente falhou


# ============================================================
# 1. Limpeza (notebook 01)
# ============================================================

def limpar(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[raw["city"] == "São Paulo"].copy()
    df = df[df["forRent"].astype(bool)].copy()

    df["lat"] = df["location"].str["lat"]
    df["lon"] = df["location"].str["lon"]
    df["type"] = df["type"].astype("string").str.strip()
    df["isFurnished"] = df["isFurnished"].astype("boolean")
    for col in ["bathrooms", "bedrooms", "suites", "parkingSpaces"]:
        df[col] = df[col].astype("Int64")

    df = df[df["lat"].between(*LIMITES_SP["lat"]) & df["lon"].between(*LIMITES_SP["lon"])].copy()
    df = df.drop_duplicates(subset=CHAVE_DUP, keep="first").copy()

    df = df.dropna(subset=["area", "bedrooms", "bathrooms"]).copy()
    df = df[df["area"].between(12, 1000)].copy()
    df = df[df["bathrooms"] >= 1].copy()
    df = df[(df["bedrooms"] >= 1) | (df["type"] == "StudioOuKitchenette")].copy()

    df["rent_m2"] = df["rent"] / df["area"]
    lo, hi = df["rent_m2"].quantile([0.005, 0.995])
    df = df[df["rent_m2"].between(lo, hi)].copy()

    for col, (origem, valor) in FLAGS.items():
        df[col] = df[origem].map(lambda x, v=valor: int(x is not None and v in list(x)))

    df["log_rent"] = np.log(df["rent"])
    df["dist_centro_km"] = haversine_km(df["lat"], df["lon"], *CENTRO)

    # Mesmas checagens do fim do notebook 01
    df = df[df["rent"].between(500, 35_000)]
    assert df["id"].is_unique
    assert df[["lat", "lon"]].notna().all().all()

    colunas = ["id", "type", "area", "bathrooms", "bedrooms", "suites", "parkingSpaces", "rent",
               "isFurnished", "lat", "lon", "rent_m2", "log_rent", "dist_centro_km", *FLAGS]
    return df[colunas].reset_index(drop=True)


# ============================================================
# 2. POIs (notebook 03)
# ============================================================

def adicionar_pois(df: pd.DataFrame, pois: dict) -> pd.DataFrame:
    import geopandas as gpd

    imoveis = gpd.GeoDataFrame(geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_GEO).to_crs(CRS_M)
    n = len(imoveis)
    out = {}
    for nome, g in pois.items():
        near = gpd.sjoin_nearest(imoveis, g[["geometry"]], how="left", distance_col="d")
        out[f"dist_{nome}"] = near.groupby(level=0)["d"].min().to_numpy()

        i_im, i_poi = g.sindex.query(imoveis.geometry, predicate="dwithin", distance=1000)
        d = imoveis.geometry.values[i_im].distance(g.geometry.values[i_poi])
        out[f"qtd_{nome}_500m"] = np.bincount(i_im[d <= 500], minlength=n)
        out[f"qtd_{nome}_1km"] = np.bincount(i_im, minlength=n)
    return pd.concat([df, pd.DataFrame(out, index=df.index)], axis=1)


# ============================================================
# 3. Features do modelo (notebook 05)
# ============================================================

def adicionar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mobiliado"] = df["isFurnished"].fillna(False).astype(int)
    df["dist_polo_km"] = np.min([haversine_km(df["lat"], df["lon"], *p) for p in POLOS.values()], axis=0)
    return df


def preparar(raw_path: str, saida: str) -> str:
    raw = pd.read_parquet(raw_path)
    print(f"📂 Bruto: {raw_path} → {len(raw):,} anúncios")

    df = limpar(raw)
    print(f"🧹 Após limpeza: {len(df):,}")
    if len(df) < MIN_LINHAS:
        raise ValueError(f"Só {len(df)} anúncios após a limpeza (mínimo {MIN_LINHAS}); extração suspeita")

    df = adicionar_features(adicionar_pois(df, carregar_pois_sp(OSM_DIR)))

    os.makedirs(os.path.dirname(saida), exist_ok=True)
    df.to_parquet(saida, index=False)

    # Validação final: o dataset precisa servir para o treino sem nulos nas features
    pronto = prepare_dataset(saida)
    nulos = pronto[NUM_FEATURES].isna().sum()
    nulos = nulos[(nulos > 0) & ~nulos.index.isin(["suites", "parkingSpaces"])]
    if len(nulos):
        raise ValueError(f"Features com nulos: {nulos.to_dict()}")

    print(f"✅ {saida} — {df.shape[0]:,} linhas × {df.shape[1]} colunas")
    return saida


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()
    preparar(args.raw, args.saida)
