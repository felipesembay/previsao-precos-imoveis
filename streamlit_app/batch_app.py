"""
Batch App — Predição em Lote de Preços de Imóveis
Suporta dois formatos:
  1. Formato Scraping (padrão do ZAP Imóveis) — detecção automática
  2. Formato Genérico — mapeamento manual de colunas
Pipeline: Upload → Tratamento → Geocoding → POIs por cidade → Scores → Predição → Banco
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import numpy as np
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from sklearn.neighbors import BallTree

sys.path.insert(0, os.path.dirname(__file__))
from db import get_connection as _pg_connection
from db import salvar_lote_compra

from api import API_HEALTH_URL, prever_precos_lote

try:
    import osmnx as ox
    OSMNX_AVAILABLE = True
except ImportError:
    OSMNX_AVAILABLE = False

load_dotenv()
GOOGLE_API_KEY = os.getenv("GEOCODING_MAPS")

# ─────────────────────────────────────────────────────────────
# Configuração da página
# ─────────────────────────────────────────────────────────────
# st.set_page_config() - Desabilitado quando usado via general.py
# st.set_page_config(
#     page_title="📦 Predição em Lote",
#     page_icon="📦",
#     layout="wide",
#     initial_sidebar_state="collapsed",
# )


# ─────────────────────────────────────────────────────────────
# Banco (PostgreSQL)
# ─────────────────────────────────────────────────────────────
def get_connection():
    """PostgreSQL (PG_* no .env), linhas como dict — mesmo comportamento do antigo DictCursor."""
    return _pg_connection(dict_rows=True)


# ─────────────────────────────────────────────────────────────
# TRATAMENTO DO FORMATO DE SCRAPING (Coleta_e_tratamento.ipynb)
# ─────────────────────────────────────────────────────────────
COLUNAS_SCRAPING = {"preco", "rua", "endereco", "quartos", "banheiros", "area_m2", "cidade", "estado"}


def is_formato_scraping(df: pd.DataFrame) -> bool:
    """Detecta se o arquivo vem do scraper do ZAP Imóveis."""
    return COLUNAS_SCRAPING.issubset(set(df.columns.str.lower().str.strip()))


def limpar_preco(serie: pd.Series) -> pd.Series:
    """'R$ 1.380.000' → 1380000.0"""
    return (
        serie.astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
        .pipe(pd.to_numeric, errors="coerce")
    )


def extrair_vagas(serie: pd.Series) -> pd.Series:
    """Extrai nº de vagas da descrição textual do imóvel."""
    return (
        serie.str.extract(r"(\d+)\s+vagas?", expand=False)
        .astype(float)
        .fillna(0)
        .astype(int)
    )


def extrair_bairro(serie: pd.Series) -> pd.Series:
    """Extrai bairro da descrição: '...em Boqueirão, Guarapuava'"""
    return (
        serie.str.extract(r"em\s*([^,]+)", expand=False)
        .str.replace(r"^Imóvel\s+", "", regex=True)
        .str.strip()
    )


def extrair_tipo_texto(serie: pd.Series) -> pd.Series:
    """Extrai tipo da descrição: 'Casa para comprar...' → 'Casa'"""
    return (
        serie.str.extract(r"^(.*?)\s+para\s+(?:comprar|alugar)", expand=False)
        .str.strip()
    )


def classificar_tipo_imovel(tipo) -> str:
    """Normaliza tipo para: casa, apartamento, comercial, terreno, outros."""
    if pd.isna(tipo):
        return "outros"
    t = str(tipo).lower()
    if any(x in t for x in ["terreno", "lote", "chácara", "fazenda", "sítio", "sitio"]):
        return "terreno"
    if any(x in t for x in ["apartamento", "cobertura", "duplex", "flat", "kitnet", "studio"]):
        return "apartamento"
    if any(x in t for x in ["sobrado", "casa de condomínio", "casa condominio", "vila"]):
        return "casa"
    if "casa" in t:
        return "casa"
    if any(x in t for x in ["comercial", "loja", "box", "galpão", "galpao",
                              "depósito", "deposito", "sala", "conjunto", "prédio",
                              "edificio", "edifício", "escritório", "escritorio"]):
        return "comercial"
    return "outros"


def construir_endereco_geocoding(row) -> str:
    """
    Monta o endereço para geocoding seguindo o mesmo padrão do notebook:
    '{rua}, {bairro}, {cidade}, {estado}, Brasil'
    """
    partes = []
    rua    = str(row.get("rua",    "")).strip()
    bairro = str(row.get("bairro", "")).strip()
    cidade = str(row.get("cidade", "")).strip().title()
    estado = str(row.get("estado", "")).strip().upper()

    if rua    and rua    not in ("nan", "None", ""):
        partes.append(rua)
    if bairro and bairro not in ("nan", "None", ""):
        partes.append(bairro)
    if cidade:
        partes.append(cidade)
    if estado:
        partes.append(estado)
    partes.append("Brasil")
    return ", ".join(partes)


def tratar_scraping(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica o pipeline completo de tratamento do Coleta_e_tratamento.ipynb.
    """
    df = df.copy()

    # 1) Limpar preço
    df["preco_anuncio"] = limpar_preco(df["preco"])

    # 2) Remover aluguéis
    if "link" in df.columns:
        df = df[~df["link"].astype(str).str.contains("/aluguel-", na=False)]
    df = df[df["preco_anuncio"] >= 10_000]

    # 3) Extrair campos da descrição textual
    df["vagas_garagem"] = extrair_vagas(df["endereco"])
    df["bairro"]        = extrair_bairro(df["endereco"])
    df["tipo_imovel"]   = extrair_tipo_texto(df["endereco"])

    # 4) Classificar tipo e derivar is_sobrado
    df["tipo_imovel_cat"] = df["tipo_imovel"].apply(classificar_tipo_imovel)
    df["is_sobrado"] = (
        df["tipo_imovel"].str.lower().str.contains("sobrado", na=False).astype(int)
    )

    # 5) Garantir campos numéricos
    df["area_m2"]   = pd.to_numeric(df["area_m2"],   errors="coerce")
    df["quartos"]   = pd.to_numeric(df["quartos"],   errors="coerce").fillna(0).astype(int)
    df["banheiros"] = pd.to_numeric(df["banheiros"], errors="coerce").fillna(0).astype(int)

    # 6) Montar endereço para geocoding (rua + bairro + cidade + estado + Brasil)
    df["endereco_geo"] = df.apply(construir_endereco_geocoding, axis=1)

    # 7) Normalizar cidade/estado
    df["cidade_norm"] = df["cidade"].astype(str).str.strip().str.title()
    df["estado_norm"] = df["estado"].astype(str).str.strip().str.upper()

    # 8) Filtros de qualidade (mesmos do ML2.ipynb)
    df = df.dropna(subset=["area_m2"])
    df = df[df["area_m2"] > 0]
    df = df[df["area_m2"] < 10_000]
    df = df[df["tipo_imovel_cat"].isin(["casa", "apartamento", "comercial"])]

    # 9) Remover duplicatas por link
    if "link" in df.columns:
        df = df.drop_duplicates(subset=["link"])

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# TRATAMENTO DO FORMATO GENÉRICO (upload manual)
# ─────────────────────────────────────────────────────────────
CAMPOS_ALIASES = {
    "endereco":      ["endereco", "endereço", "address", "logradouro", "rua"],
    "area_m2":       ["area_m2", "area", "área", "metragem", "metros", "m2"],
    "quartos":       ["quartos", "dormitorios", "dormitórios", "quarto", "bedrooms"],
    "banheiros":     ["banheiros", "banheiro", "wc", "bathrooms"],
    "vagas_garagem": ["vagas_garagem", "vagas", "garagem", "garage"],
    "tipo_imovel":   ["tipo_imovel", "tipo_imóvel", "tipo", "tipo_imovel_cat"],
    "preco":         ["preco", "preço", "price", "valor", "preco_anuncio"],
}


def detectar_colunas(df_cols: list) -> dict:
    cols_lower = {c.lower().strip(): c for c in df_cols}
    mapeamento = {}
    for campo, aliases in CAMPOS_ALIASES.items():
        for alias in aliases:
            if alias in cols_lower and campo not in mapeamento:
                mapeamento[campo] = cols_lower[alias]
    return mapeamento


def tratar_generico(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    out = pd.DataFrame()
    out["endereco"]        = df[col_map["endereco"]].astype(str).str.strip()
    out["area_m2"]         = pd.to_numeric(df[col_map["area_m2"]], errors="coerce")
    out["quartos"]         = pd.to_numeric(df[col_map["quartos"]],   errors="coerce").fillna(0).astype(int)
    out["banheiros"]       = pd.to_numeric(df[col_map["banheiros"]], errors="coerce").fillna(0).astype(int)
    out["vagas_garagem"]   = pd.to_numeric(df[col_map["vagas_garagem"]], errors="coerce").fillna(0).astype(int)
    tipo_raw               = df[col_map["tipo_imovel"]].astype(str) if "tipo_imovel" in col_map else pd.Series(["casa"] * len(df))
    out["tipo_imovel"]     = tipo_raw
    out["tipo_imovel_cat"] = tipo_raw.apply(classificar_tipo_imovel)
    out["is_sobrado"]      = tipo_raw.str.lower().str.contains("sobrado", na=False).astype(int)
    out["preco_anuncio"]   = pd.to_numeric(df[col_map["preco"]], errors="coerce") if "preco" in col_map else np.nan
    out["endereco_geo"]    = out["endereco"]
    out["bairro"]          = ""
    out["cidade_norm"]     = ""
    out["estado_norm"]     = ""
    out = out.dropna(subset=["area_m2"])
    out = out[out["area_m2"] > 0]
    out = out[out["tipo_imovel_cat"].isin(["casa", "apartamento", "comercial"])]
    return out.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# GEOCODING — Google Maps
# ─────────────────────────────────────────────────────────────
CACHE_GEO_PATH = os.path.join(os.path.dirname(__file__), "..", "cache", "geocoding", "compra_google_cache.json")


def carregar_cache_geo() -> dict:
    """Endereços já geocodificados em execuções anteriores (evita pagar o Google de novo)."""
    try:
        with open(CACHE_GEO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar_cache_geo(cache: dict):
    os.makedirs(os.path.dirname(CACHE_GEO_PATH), exist_ok=True)
    with open(CACHE_GEO_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def geocode_google(endereco: str):
    if not GOOGLE_API_KEY:
        return None
    url    = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": endereco, "key": GOOGLE_API_KEY, "region": "br", "language": "pt-BR"}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        result   = data["results"][0]
        location = result["geometry"]["location"]
        cidade, estado = "", ""
        for comp in result.get("address_components", []):
            types = comp.get("types", [])
            if "administrative_area_level_2" in types:
                cidade = comp.get("long_name", "")
            if "administrative_area_level_1" in types:
                estado = comp.get("short_name", "")
        return {
            "lat": location["lat"],
            "lng": location["lng"],
            "endereco_formatado": result.get("formatted_address", endereco),
            "cidade": cidade,
            "estado": estado,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# POIs — BANCO DE DADOS
# ─────────────────────────────────────────────────────────────
TIPOS_POI = ["mercado", "farmacia", "escola", "hospital", "parque", "policia"]

OSM_CONFIGS = {
    "hospital": {"amenity": "hospital"},
    "mercado":  {"shop": ["supermarket", "convenience"]},
    "farmacia": {"amenity": "pharmacy"},
    "escola":   {"amenity": ["school", "college", "university"]},
    "parque":   {"leisure": ["park", "garden"]},
    "policia":  {"amenity": ["police", "fire_station"]},
}


def get_pois_from_db(cidade: str, estado: str = None) -> dict:
    conn   = get_connection()
    cursor = conn.cursor()
    query  = "SELECT tipo_poi, latitude, longitude FROM pois WHERE cidade = %s"
    params = [cidade]
    if estado:
        query += " AND estado = %s"
        params.append(estado)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    result = {t: [] for t in TIPOS_POI}
    for row in rows:
        result[row["tipo_poi"]].append((float(row["latitude"]), float(row["longitude"])))
    return result


def contar_pois_cidade(cidade: str, estado: str = None) -> int:
    conn   = get_connection()
    cursor = conn.cursor()
    query  = "SELECT COUNT(*) as total FROM pois WHERE cidade = %s"
    params = [cidade]
    if estado:
        query += " AND estado = %s"
        params.append(estado)
    cursor.execute(query, params)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row["total"] if row else 0


def salvar_pois_db(pois_list: list, cidade: str, estado: str):
    if not pois_list:
        return
    conn   = get_connection()
    cursor = conn.cursor()
    tipos  = list({p["tipo_poi"] for p in pois_list})
    for tipo in tipos:
        cursor.execute("DELETE FROM pois WHERE cidade = %s AND tipo_poi = %s", (cidade, tipo))
    cursor.executemany(
        "INSERT INTO pois (nome, tipo_poi, latitude, longitude, cidade, estado, fonte) "
        "VALUES (%s,%s,%s,%s,%s,%s,'osm')",
        [(p["nome"], p["tipo_poi"], p["lat"], p["lng"], cidade, estado) for p in pois_list],
    )
    conn.commit()
    cursor.close()
    conn.close()


def extrair_pois_osmnx(cidade: str, estado: str, status_placeholder=None) -> dict:
    if not OSMNX_AVAILABLE:
        st.warning("⚠️ OSMnx não disponível.")
        return {t: [] for t in TIPOS_POI}
    ox.settings.use_cache   = True
    ox.settings.log_console = False
    place_query = f"{cidade}, {estado}, Brasil" if estado else f"{cidade}, Brasil"
    todos_pois, result = [], {t: [] for t in TIPOS_POI}
    for tipo, tags in OSM_CONFIGS.items():
        if status_placeholder:
            status_placeholder.caption(f"   ↳ extraindo **{tipo}s** de **{cidade}**…")
        try:
            gdf = ox.features_from_place(place_query, tags=tags)
            if gdf is None or gdf.empty:
                continue
            gdf = gdf.copy()
            gdf["geometry"] = gdf["geometry"].apply(
                lambda g: g.centroid if g.geom_type != "Point" else g
            )
            for _, row in gdf.iterrows():
                geom = row["geometry"]
                lat, lng = geom.y, geom.x
                nome = str(row.get("name", tipo) or tipo)
                todos_pois.append({"nome": nome, "tipo_poi": tipo, "lat": lat, "lng": lng})
                result[tipo].append((lat, lng))
        except Exception as e:
            st.warning(f"⚠️ Não foi possível extrair {tipo} de {cidade}: {e}")
    salvar_pois_db(todos_pois, cidade, estado)
    return result


def garantir_pois_cidade(cidade: str, estado: str, status_placeholder=None) -> dict:
    """Verifica banco; extrai via OSMnx se necessário."""
    if contar_pois_cidade(cidade, estado) >= 10:
        return get_pois_from_db(cidade, estado)
    return extrair_pois_osmnx(cidade, estado, status_placeholder)


# ─────────────────────────────────────────────────────────────
# FEATURES POI — BallTree (haversine)
# ─────────────────────────────────────────────────────────────
RAIOS_M = {"hospital": 1000, "mercado": 500, "farmacia": 300,
           "escola": 500, "parque": 1000, "policia": 500}
PLURAL  = {"hospital": "hospitais", "mercado": "mercados", "farmacia": "farmacias",
           "escola": "escolas", "parque": "parques", "policia": "policia"}


def calcular_features_poi(lat: float, lng: float, pois_por_tipo: dict) -> dict:
    imovel_rad = np.radians([[lat, lng]])
    features   = {}
    for tipo, coords_list in pois_por_tipo.items():
        plural = PLURAL[tipo]
        raio   = RAIOS_M[tipo]
        if not coords_list:
            features[f"dist_{plural}_mais_proximo"] = 99_999.0
            features[f"qtd_{plural}_{raio}m"]       = 0
            continue
        coords = np.radians([(c[0], c[1]) for c in coords_list])
        tree   = BallTree(coords, metric="haversine")
        dist, _ = tree.query(imovel_rad, k=1)
        features[f"dist_{plural}_mais_proximo"] = float(dist[0, 0] * 6_371_000)
        count = tree.query_radius(imovel_rad, r=raio / 6_371_000, count_only=True)[0]
        features[f"qtd_{plural}_{raio}m"] = int(count)
    return features


def calcular_scores(f: dict) -> dict:
    return {
        "score_escola_privada": round(
            1.2 * np.exp(-f["dist_escolas_mais_proximo"] / 600) +
            0.6 * f["qtd_escolas_500m"], 4),
        "score_escola_publica": round(
            0.6 * np.exp(-f["dist_escolas_mais_proximo"] / 600) +
            0.2 * f["qtd_escolas_500m"], 4),
        "score_hospitais": round(
            0.8 * np.exp(-f["dist_hospitais_mais_proximo"] / 1200) +
            0.4 * f["qtd_hospitais_1000m"], 4),
        "score_mercado": round(
            1.0 * np.exp(-f["dist_mercados_mais_proximo"] / 400) +
            0.4 * f["qtd_mercados_500m"], 4),
        "score_farmacia": round(
            0.6 * np.exp(-f["dist_farmacias_mais_proximo"] / 300) +
            0.2 * f["qtd_farmacias_300m"], 4),
        "score_parque": round(
            1.2 * np.exp(-f["dist_parques_mais_proximo"] / 1200) +
            0.8 * f["qtd_parques_1000m"], 4),
        "score_seguranca": round(
            1.0 * np.exp(-f["dist_policia_mais_proximo"] / 1500) +
            0.3 * f["qtd_policia_500m"], 4),
    }


# ─────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────
def rodar_pipeline(df_trat: pd.DataFrame, salvar_db: bool,
                   progress_bar, status_text, log_container):
    resultados, erros = [], []
    total = len(df_trat)

    # ── ETAPA 1: GEOCODING ────────────────────────────────────
    status_text.markdown("**[1/4] Geocodificando endereços…**")
    cache_geo = carregar_cache_geo()
    pendentes = [e for e in df_trat["endereco_geo"].unique() if e not in cache_geo]
    if len(pendentes) < df_trat["endereco_geo"].nunique():
        log_container.caption(f"   ♻️ {df_trat['endereco_geo'].nunique() - len(pendentes)} endereço(s) já estavam no cache")

    # Chamadas ao Google em paralelo (8 por vez), em vez de uma a uma com pausa
    if pendentes:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futuros = {pool.submit(geocode_google, e): e for e in pendentes}
            for n, fut in enumerate(as_completed(futuros), start=1):
                geo = fut.result()
                if geo is not None:          # não guarda falhas: tenta de novo na próxima execução
                    cache_geo[futuros[fut]] = geo
                progress_bar.progress(int(n / len(pendentes) * 25), text=f"Geocoding {n}/{len(pendentes)}")
        salvar_cache_geo(cache_geo)

    df_trat["_geo"] = df_trat["endereco_geo"].map(cache_geo)
    sem_geo = df_trat["_geo"].isna().sum()
    if sem_geo > 0:
        log_container.warning(f"⚠️ {sem_geo} endereço(s) não geocodificado(s) — ignorados.")
    df_trat = df_trat[df_trat["_geo"].notna()].copy()

    df_trat["lat"]          = df_trat["_geo"].apply(lambda g: g["lat"])
    df_trat["lng"]          = df_trat["_geo"].apply(lambda g: g["lng"])
    df_trat["endereco_fmt"] = df_trat["_geo"].apply(lambda g: g.get("endereco_formatado", ""))
    df_trat["cidade_geo"]   = df_trat["_geo"].apply(lambda g: g.get("cidade", ""))
    df_trat["estado_geo"]   = df_trat["_geo"].apply(lambda g: g.get("estado", ""))

    # Prioriza cidade/estado que vieram do scraping; fallback para o Google
    df_trat["cidade_final"] = df_trat["cidade_norm"].where(
        df_trat["cidade_norm"].astype(str).str.strip() != "", df_trat["cidade_geo"]
    )
    df_trat["estado_final"] = df_trat["estado_norm"].where(
        df_trat["estado_norm"].astype(str).str.strip() != "", df_trat["estado_geo"]
    )

    # ── ETAPA 2: POIs POR CIDADE ──────────────────────────────
    status_text.markdown("**[2/4] Carregando POIs por cidade…**")
    cidades_unicas = (
        df_trat[["cidade_final", "estado_final"]].drop_duplicates().to_dict("records")
    )
    cache_pois = {}
    for j, c in enumerate(cidades_unicas):
        cidade, estado = c["cidade_final"], c["estado_final"]
        chave = f"{cidade}|{estado}"
        pct   = 25 + int((j + 1) / len(cidades_unicas) * 25)
        progress_bar.progress(pct, text=f"POIs: {cidade} ({j+1}/{len(cidades_unicas)})")
        cache_pois[chave] = garantir_pois_cidade(cidade, estado, status_text)
        n = sum(len(v) for v in cache_pois[chave].values())
        log_container.caption(f"   ✅ {cidade}: {n} POIs carregados")

    # ── ETAPA 3: FEATURES E SCORES ────────────────────────────
    status_text.markdown("**[3/4] Calculando features e scores…**")
    for i, row in df_trat.iterrows():
        chave     = f"{row['cidade_final']}|{row['estado_final']}"
        pois_city = cache_pois.get(chave, {t: [] for t in TIPOS_POI})
        f         = calcular_features_poi(row["lat"], row["lng"], pois_city)
        scores    = calcular_scores(f)
        for k, v in scores.items():
            df_trat.at[i, k] = v
        progress_bar.progress(50 + int((i + 1) / len(df_trat) * 25),
                              text=f"Features {i+1}/{len(df_trat)}")

    # ── ETAPA 4: PREDIÇÃO ─────────────────────────────────────
    status_text.markdown("**[4/4] Realizando predições…**")
    payloads = [{
        "area_m2":              float(row["area_m2"]),
        "quartos":              int(row["quartos"]),
        "banheiros":            int(row["banheiros"]),
        "vagas_garagem":        int(row["vagas_garagem"]),
        "tipo_imovel_cat":      row["tipo_imovel_cat"],
        "is_sobrado":           int(row["is_sobrado"]),
        "score_escola_privada": float(row["score_escola_privada"]),
        "score_escola_publica": float(row["score_escola_publica"]),
        "score_hospitais":      float(row["score_hospitais"]),
        "score_mercado":        float(row["score_mercado"]),
        "score_farmacia":       float(row["score_farmacia"]),
        "score_parque":         float(row["score_parque"]),
        "score_seguranca":      float(row["score_seguranca"]),
    } for _, row in df_trat.iterrows()]

    # Uma requisição para o lote inteiro (antes: uma por imóvel)
    try:
        previsoes = prever_precos_lote(payloads)
    except Exception as e:
        previsoes = [None] * len(payloads)
        erros.append({"linha": "todas", "endereco": "", "erro": f"API: {e}"})
    progress_bar.progress(90, text="Predições concluídas")

    modelo, versao = "RealEstatePriceModel", "2.0.0"
    itens_db = []
    for (i, row), payload, prev in zip(df_trat.iterrows(), payloads, previsoes):
        preco_predito = prev["preco_estimado"] if prev else None

        preco_anuncio  = row.get("preco_anuncio")
        nan_anuncio    = preco_anuncio is None or (
            isinstance(preco_anuncio, float) and np.isnan(preco_anuncio)
        )
        erro_abs, erro_pct = None, None
        if preco_predito and not nan_anuncio and float(preco_anuncio) > 0:
            erro_abs = abs(preco_predito - float(preco_anuncio))
            erro_pct = erro_abs / float(preco_anuncio)      # fração, igual à tela individual

        if salvar_db and preco_predito:
            itens_db.append({
                "dados": {
                    **payload,
                    "endereco":      row.get("endereco_fmt") or row.get("endereco_geo", ""),
                    "preco_anuncio": float(preco_anuncio) if not nan_anuncio else None,
                },
                "preco_predito": preco_predito, "modelo": modelo, "versao": versao,
                "erro_abs": erro_abs, "erro_pct": erro_pct,
                "scores": {k: float(row[k]) for k in [
                    "score_escola_privada", "score_escola_publica", "score_farmacia",
                    "score_hospitais", "score_mercado", "score_parque", "score_seguranca",
                ]},
            })

        resultados.append({
            "endereco":             row.get("endereco_fmt") or row.get("endereco_geo", ""),
            "bairro":               row.get("bairro", ""),
            "cidade":               row["cidade_final"],
            "estado":               row["estado_final"],
            "tipo_imovel":          row.get("tipo_imovel", ""),
            "tipo_imovel_cat":      row["tipo_imovel_cat"],
            "is_sobrado":           int(row["is_sobrado"]),
            "area_m2":              row["area_m2"],
            "quartos":              int(row["quartos"]),
            "banheiros":            int(row["banheiros"]),
            "vagas_garagem":        int(row["vagas_garagem"]),
            "score_escola_privada": round(float(row["score_escola_privada"]), 3),
            "score_escola_publica": round(float(row["score_escola_publica"]), 3),
            "score_hospitais":      round(float(row["score_hospitais"]), 3),
            "score_mercado":        round(float(row["score_mercado"]), 3),
            "score_farmacia":       round(float(row["score_farmacia"]), 3),
            "score_parque":         round(float(row["score_parque"]), 3),
            "score_seguranca":      round(float(row["score_seguranca"]), 3),
            "preco_anuncio":        float(preco_anuncio) if not nan_anuncio else None,
            "preco_predito":        preco_predito,
            "erro_absoluto":        round(erro_abs, 2) if erro_abs else None,
            "erro_percentual_pct":  round(erro_pct * 100, 2) if erro_pct else None,
            "modelo":               modelo,
            "versao":               versao,
            "predicao_id":          None,
        })

    # Banco: uma conexão e um commit para o lote
    if itens_db:
        status_text.markdown("**💾 Salvando no banco de dados…**")
        try:
            ids = iter(salvar_lote_compra(itens_db))
            for r in resultados:
                if r["preco_predito"]:
                    r["predicao_id"] = next(ids)
        except Exception as e:
            erros.append({"linha": "todas", "endereco": "", "erro": f"DB: {e}"})
    progress_bar.progress(100, text="Concluído")

    return pd.DataFrame(resultados), erros


# ═══════════════════════════════════════════════════════════════
# INTERFACE
# ═══════════════════════════════════════════════════════════════
st.title("📦 Predição em Lote — Imóveis")
st.caption(
    "Suporta o formato do scraper ZAP Imóveis (detecção automática) "
    "ou qualquer CSV/XLSX com mapeamento manual de colunas."
)

if not GOOGLE_API_KEY:
    st.error("❌ Chave `GEOCODING_MAPS` não encontrada no `.env`. Geocoding indisponível.")

# ── Sidebar ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configurações")
    salvar_db = st.checkbox("💾 Salvar no banco de dados", value=True)
    st.markdown("---")
    st.markdown("**Formato auto-detectado (scraper ZAP)**")
    st.code("preco, rua, endereco, quartos,\nbanheiros, area_m2, cidade, estado", language="text")
    st.markdown("---")
    try:
        r = requests.get(API_HEALTH_URL, timeout=2)
        st.success(f"✅ API: {r.json().get('status', 'ok')}")
    except Exception:
        st.error("❌ API offline — inicie com:\n`uvicorn api.main:app --port 8009`")

# ── Template de download ─────────────────────────────────────────
with st.expander("📥 Baixar template CSV (formato scraper)"):
    st.markdown(
        "O template abaixo é o padrão gerado pelo `scraper_robusto.py`. "
        "As colunas **vagas_garagem** e **tipo_imovel** são extraídas automaticamente "
        "do campo `endereco` — não precisam estar no arquivo."
    )
    template_df = pd.DataFrame({
        "preco":       ["R$ 450.000", "R$ 280.000", "R$ 641.000"],
        "rua":         ["Rua das Flores", "Rua XV de Novembro", "Rua Senador Pinheiro Machado"],
        "endereco":    [
            "Casa para comprar com 120 m², 3 quartos, 2 banheiros, 2 vagas em Centro, Ponta Grossa",
            "Casa para comprar com 90 m², 2 quartos, 1 banheiro, 1 vaga em Boqueirão, Ponta Grossa",
            "Apartamento para comprar com 123 m², 3 quartos, 2 banheiros, 2 vagas em Centro, Ponta Grossa",
        ],
        "quartos":     [3, 2, 3],
        "banheiros":   [2, 1, 2],
        "area_m2":     [120.0, 90.0, 123.0],
        "link":        ["https://zapimoveis.com.br/...", "https://zapimoveis.com.br/...",
                        "https://zapimoveis.com.br/..."],
        "cidade":      ["ponta grossa", "ponta grossa", "ponta grossa"],
        "estado":      ["pr", "pr", "pr"],
        "data_coleta": ["2026-02-27", "2026-02-27", "2026-02-27"],
    })
    st.dataframe(template_df, width='stretch', height=200)
    st.download_button(
        "⬇️ Baixar template.csv",
        template_df.to_csv(index=False).encode("utf-8"),
        "template_scraper.csv", "text/csv",
    )

# ── Upload ───────────────────────────────────────────────────────
st.subheader("📂 Upload do arquivo")
col_up1, col_up2 = st.columns([3, 1])
with col_up1:
    uploaded_file = st.file_uploader("Selecione CSV ou XLSX", type=["csv", "xlsx"])
with col_up2:
    separador = st.selectbox("Separador CSV", [",", ";", "|", "\\t"], index=0)

if uploaded_file is None:
    st.info("⬆️ Faça o upload de um arquivo CSV ou XLSX para iniciar.")
    st.stop()

# ── Leitura ──────────────────────────────────────────────────────
try:
    if uploaded_file.name.endswith(".xlsx"):
        df_raw = pd.read_excel(uploaded_file)
    else:
        sep    = "\t" if separador == "\\t" else separador
        df_raw = pd.read_csv(uploaded_file, sep=sep)
except Exception as e:
    st.error(f"❌ Erro ao ler arquivo: {e}")
    st.stop()

st.success(f"✅ Arquivo carregado: **{len(df_raw)} linhas** × **{len(df_raw.columns)} colunas**")

with st.expander("👁️ Preview dos dados brutos", expanded=True):
    st.dataframe(df_raw.head(10), width='stretch', height=200)

# ── Detecção de formato e tratamento ────────────────────────────
formato_scraping = is_formato_scraping(df_raw)
st.subheader("🔍 Formato detectado")

if formato_scraping:
    st.success("✅ **Formato Scraping (ZAP Imóveis)** — tratamento automático ativado.")

    df_trat = tratar_scraping(df_raw)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros brutos",    len(df_raw))
    c2.metric("Após tratamento",     len(df_trat))
    c3.metric("Descartados",         len(df_raw) - len(df_trat))
    tipo_counts = df_trat["tipo_imovel_cat"].value_counts().to_dict()
    c4.metric("Por tipo",            " | ".join(f"{k}: {v}" for k, v in tipo_counts.items()))

    with st.expander("🔬 Preview do tratamento aplicado"):
        st.dataframe(
            df_trat[[
                "endereco_geo", "tipo_imovel", "tipo_imovel_cat", "is_sobrado",
                "area_m2", "quartos", "banheiros", "vagas_garagem",
                "cidade_norm", "estado_norm", "preco_anuncio",
            ]].head(15),
            width='stretch', height=200,
        )

else:
    st.warning("⚠️ **Formato Genérico** — faça o mapeamento manual das colunas abaixo.")
    auto_map = detectar_colunas(df_raw.columns.tolist())
    opcoes   = ["(não disponível)"] + df_raw.columns.tolist()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        col_endereco = st.selectbox("📍 Endereço *", opcoes,
                                     index=opcoes.index(auto_map.get("endereco", "(não disponível)")))
        col_area     = st.selectbox("📐 Área (m²) *", opcoes,
                                     index=opcoes.index(auto_map.get("area_m2", "(não disponível)")))
    with c2:
        col_quartos  = st.selectbox("🛏️ Quartos *", opcoes,
                                     index=opcoes.index(auto_map.get("quartos", "(não disponível)")))
        col_banhos   = st.selectbox("🚿 Banheiros *", opcoes,
                                     index=opcoes.index(auto_map.get("banheiros", "(não disponível)")))
    with c3:
        col_vagas    = st.selectbox("🚗 Vagas *", opcoes,
                                     index=opcoes.index(auto_map.get("vagas_garagem", "(não disponível)")))
        col_tipo     = st.selectbox("🏠 Tipo imóvel *", opcoes,
                                     index=opcoes.index(auto_map.get("tipo_imovel", "(não disponível)")))
    with c4:
        col_preco    = st.selectbox("💰 Preço anúncio", opcoes,
                                     index=opcoes.index(auto_map.get("preco", "(não disponível)")))

    campos_obrig = {
        "endereco": col_endereco, "area_m2": col_area, "quartos": col_quartos,
        "banheiros": col_banhos, "vagas_garagem": col_vagas, "tipo_imovel": col_tipo,
    }
    faltando = [k for k, v in campos_obrig.items() if v == "(não disponível)"]
    if faltando:
        st.error(f"❌ Campos obrigatórios não mapeados: {', '.join(faltando)}")
        st.stop()

    col_map_final = {**campos_obrig}
    if col_preco != "(não disponível)":
        col_map_final["preco"] = col_preco

    df_trat = tratar_generico(df_raw, col_map_final)
    st.info(f"Registros válidos após tratamento: **{len(df_trat)}**")

if len(df_trat) == 0:
    st.error("❌ Nenhum registro válido encontrado. Verifique o arquivo e os filtros.")
    st.stop()

# ── Botão de execução ────────────────────────────────────────────
st.markdown("---")
col_b1, col_b2 = st.columns([3, 1])
with col_b1:
    executar = st.button(
        f"🚀 Executar pipeline completo ({len(df_trat)} imóveis)",
        type="primary",
        width='stretch',
    )
with col_b2:
    st.caption("⏱️ ~1–3s por imóvel (Google API)")

if not executar:
    st.stop()

# ── Execução ─────────────────────────────────────────────────────
st.markdown("---")
st.subheader("⚙️ Pipeline em execução…")
progress_bar  = st.progress(0, text="Iniciando…")
status_text   = st.empty()
log_container = st.container()

df_res, erros = rodar_pipeline(
    df_trat, salvar_db, progress_bar, status_text, log_container
)

progress_bar.progress(100, text="✅ Concluído!")
status_text.empty()

# ── Resultados ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("📊 Resultados")

ok       = df_res["preco_predito"].notna().sum()
tem_mape = df_res["erro_percentual_pct"].notna().any()

c1, c2, c3, c4 = st.columns(4)
c1.metric("✅ Predições",      f"{ok} / {len(df_res)}")
c2.metric("❌ Erros",          len(erros))
c3.metric("💰 Preço médio",    f"R$ {df_res['preco_predito'].mean():,.0f}" if ok else "—")
c4.metric("📉 MAPE médio",
          f"{df_res['erro_percentual_pct'].mean():.1f}%" if tem_mape else "—")

# Tabela principal
cols_tabela = [
    "endereco", "bairro", "cidade", "tipo_imovel_cat",
    "area_m2", "quartos", "banheiros", "vagas_garagem",
    "preco_anuncio", "preco_predito",
    "erro_absoluto", "erro_percentual_pct",
]
st.dataframe(
    df_res[cols_tabela].style.format({
        "preco_anuncio":       "R$ {:,.0f}",
        "preco_predito":       "R$ {:,.0f}",
        "erro_absoluto":       "R$ {:,.0f}",
        "erro_percentual_pct": "{:.1f}%",
        "area_m2":             "{:.0f} m²",
    }, na_rep="—"),
    width='stretch',
    height=440,
)

if erros:
    with st.expander(f"⚠️ {len(erros)} erro(s) durante o processamento"):
        st.dataframe(pd.DataFrame(erros), width='content')

with st.expander("🗺️ Scores de localização calculados"):
    st.dataframe(
        df_res[[
            "endereco", "cidade",
            "score_escola_privada", "score_escola_publica",
            "score_hospitais", "score_mercado",
            "score_farmacia", "score_parque", "score_seguranca",
        ]],
        width='content',
    )

# ── Exportar ──────────────────────────────────────────────────────
st.markdown("---")
st.subheader("💾 Exportar resultados")
col_dl1, col_dl2 = st.columns(2)

with col_dl1:
    st.download_button(
        "⬇️ Baixar CSV completo",
        df_res.to_csv(index=False).encode("utf-8"),
        "predicoes_lote.csv", "text/csv",
        width='content',
    )
with col_dl2:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_res.to_excel(writer, sheet_name="Predições", index=False)
        df_res[[
            "endereco", "cidade",
            "score_escola_privada", "score_escola_publica",
            "score_hospitais", "score_mercado",
            "score_farmacia", "score_parque", "score_seguranca",
        ]].to_excel(writer, sheet_name="Scores", index=False)
    st.download_button(
        "⬇️ Baixar XLSX completo",
        buf.getvalue(),
        "predicoes_lote.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='content',
    )

if salvar_db and ok:
    st.success(f"✅ {ok} predições salvas no banco de dados.")
