"""
Extração de anúncios de aluguel do QuintoAndar (São Paulo) pela API de busca do site.
Mesma lógica do notebook aluguel/quintoandar_extration.ipynb ("RODAR ESSE SCRIPT ABAIXO"):
grade de viewports de 0,04° sobre a capital, 100 anúncios por página.

Uso:
    python -m src.scraping.quintoandar.client                 # salva em data/raw/quintoandar/
    python -m src.scraping.quintoandar.client --saida X.parquet
"""

import argparse
import datetime
import os
import time

import numpy as np
import pandas as pd
import requests

URL = "https://apigw.prod.quintoandar.com.br/house-listing-search/v2/search/list"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://www.quintoandar.com.br",
}

# Bounding box da região de São Paulo
LAT_MIN, LAT_MAX = -23.85, -23.35
LON_MIN, LON_MAX = -46.85, -46.35
STEP = 0.04
PAGE_SIZE = 100
PAUSA_S = 0.7

FIELDS = [
    "id", "rent", "totalCost", "iptuPlusCondominium", "salePrice",
    "area", "bedrooms", "bathrooms", "parkingSpaces", "suites",
    "neighbourhood", "city", "regionName", "address", "location",
    "type", "forRent", "forSale",
    "isFurnished", "isPrimaryMarket",
    "amenities", "installations",
    "listingTags", "categories",
    "visitStatus",
    "imageList", "coverImage",
    "yield", "yieldStrategy",
    "shortRentDescription",
    "activeSpecialConditions",
]

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RAW_DIR = os.path.join(ROOT, "data", "raw", "quintoandar")


def _payload(north, south, east, west, offset):
    return {
        "context": {"mapShowing": True, "listShowing": True},
        "filters": {
            "businessContext": "RENT",
            "location": {
                "coordinate": {"lat": (north + south) / 2, "lng": (east + west) / 2},
                "viewport": {"north": north, "south": south, "east": east, "west": west},
                "countryCode": "BR",
            },
        },
        "pagination": {"pageSize": PAGE_SIZE, "offset": offset},
        "slug": "sao-paulo-sp-brasil",
        "fields": FIELDS,
    }


def _post(session, payload, tentativas=4):
    """POST com retentativa para 429/5xx/erro de rede. Devolve None em erro definitivo (ex.: 400)."""
    for i in range(tentativas):
        try:
            r = session.post(URL, headers=HEADERS, json=payload, timeout=30)
        except requests.RequestException as exc:
            print(f"   rede: {exc} (tentativa {i + 1})")
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code != 429 and r.status_code < 500:
                # 400 "Pagination exceeds the maximum limit": fim do viewport
                return None
            print(f"   HTTP {r.status_code} (tentativa {i + 1})")
        time.sleep(2 ** (i + 1))
    raise RuntimeError("API do QuintoAndar indisponível após várias tentativas")


def extrair() -> pd.DataFrame:
    latitudes = np.arange(LAT_MIN, LAT_MAX, STEP)
    longitudes = np.arange(LON_MIN, LON_MAX, STEP)
    print(f"Total de áreas: {len(latitudes) * len(longitudes)}")

    all_data = []
    with requests.Session() as session:
        for lat in latitudes:
            for lon in longitudes:
                north, south, east, west = lat + STEP, lat, lon + STEP, lon
                offset = 0
                while True:
                    data = _post(session, _payload(north, south, east, west, offset))
                    listings = (data or {}).get("hits", {}).get("hits", [])
                    if not listings:
                        break
                    for item in listings:
                        source = item.get("_source", {})
                        source["lat_viewport"] = (north + south) / 2
                        source["lon_viewport"] = (east + west) / 2
                        all_data.append(source)
                    offset += PAGE_SIZE
                    time.sleep(PAUSA_S)
            print(f"   lat {lat:.2f}: {len(all_data):,} imóveis coletados")

    df = pd.DataFrame(all_data).drop_duplicates(subset="id")
    print(f"Total (sem duplicatas): {len(df):,}")
    return df


def main(saida: str | None = None) -> str:
    saida = saida or os.path.join(RAW_DIR, f"quintoandar_sp_{datetime.date.today():%Y%m%d}.parquet")
    df = extrair()
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    df.to_parquet(saida, index=False)
    print(f"✅ {saida}")
    return saida


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--saida", help="caminho do parquet de saída")
    main(parser.parse_args().saida)
