"""
Batch App — Predição em Lote de Aluguel (São Paulo capital)
Suporta dois formatos:
  1. Formato Template (download na própria tela) — colunas em português
  2. Formato Scraping (anúncios coletados: type, area, bedrooms, ..., location) — detecção automática
Pipeline: Upload → Tratamento → Geocoding → POIs de SP → Features → Predição (MLflow) → Banco
"""

import ast
import os
import sys
import time
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from aluguel_core import (GOOGLE_API_KEY, MODEL_NAME, TIPOS, carregar_custo_extra,
                          carregar_modelo, carregar_pois, custo_extra_do_bairro,
                          features_para_monitoramento, geocode_google, montar_registro,
                          prever_aluguel)
from db import salvar_features_monitoramento_aluguel, salvar_predicao_aluguel

from src.features.aluguel import dentro_de_sp, montar_entrada_modelo

# ─────────────────────────────────────────────────────────────
# FORMATO TEMPLATE (preenchido pelo usuário)
# ─────────────────────────────────────────────────────────────
COLUNAS_TEMPLATE = [
    "endereco", "tipo_imovel", "area_m2", "quartos", "banheiros", "suites", "vagas_garagem",
    "mobiliado", "ar_condicionado", "piscina", "academia", "varanda", "aluguel_anuncio",
]
OBRIGATORIAS_TEMPLATE = {"endereco", "tipo_imovel", "area_m2", "quartos", "banheiros"}

# Texto livre do tipo → valor de `type` usado no treino
TIPO_ALIASES = {
    "studio": "StudioOuKitchenette", "kitnet": "StudioOuKitchenette", "kitchenette": "StudioOuKitchenette",
    "casa em condominio": "CasaCondominio", "casa em condomínio": "CasaCondominio",
    "casa de condominio": "CasaCondominio", "casacondominio": "CasaCondominio",
    "apartamento": "Apartamento", "apto": "Apartamento", "flat": "Apartamento", "cobertura": "Apartamento",
    "casa": "Casa", "sobrado": "Casa",
}

# ─────────────────────────────────────────────────────────────
# FORMATO SCRAPING (anúncios de aluguel coletados)
# ─────────────────────────────────────────────────────────────
COLUNAS_SCRAPING = {"type", "area", "bedrooms", "bathrooms", "rent"}


def is_formato_scraping(df: pd.DataFrame) -> bool:
    return COLUNAS_SCRAPING.issubset(set(df.columns))


def normalizar_tipo(valor) -> str:
    """'Apartamento', 'studio', 'Casa em condomínio'... → Apartamento / StudioOuKitchenette / Casa / CasaCondominio."""
    if pd.isna(valor):
        return None
    t = str(valor).strip()
    if t in TIPOS.values():
        return t
    if t in TIPOS:
        return TIPOS[t]
    t = t.lower()
    for alias, tipo in TIPO_ALIASES.items():     # aliases mais específicos primeiro
        if alias in t:
            return tipo
    return None


def para_binario(serie: pd.Series) -> pd.Series:
    """1/0, sim/não, true/false, x → 1 ou 0."""
    s = serie.astype(str).str.strip().str.lower()
    return s.isin(["1", "1.0", "sim", "s", "true", "verdadeiro", "x", "yes"]).astype(int)


def tratar_template(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    for col in COLUNAS_TEMPLATE:
        if col not in df.columns:
            df[col] = np.nan

    out = pd.DataFrame()
    out["endereco_geo"] = df["endereco"].astype(str).str.strip()
    out["type"] = df["tipo_imovel"].apply(normalizar_tipo)
    out["area"] = pd.to_numeric(df["area_m2"], errors="coerce")
    out["bedrooms"] = pd.to_numeric(df["quartos"], errors="coerce").fillna(0).astype(int)
    out["bathrooms"] = pd.to_numeric(df["banheiros"], errors="coerce").fillna(1).astype(int)
    out["suites"] = pd.to_numeric(df["suites"], errors="coerce").fillna(0).astype(int)
    out["parkingSpaces"] = pd.to_numeric(df["vagas_garagem"], errors="coerce").fillna(0).astype(int)
    out["mobiliado"] = para_binario(df["mobiliado"])
    out["am_ar_condicionado"] = para_binario(df["ar_condicionado"])
    out["inst_piscina"] = para_binario(df["piscina"])
    out["inst_academia"] = para_binario(df["academia"])
    out["am_varanda"] = para_binario(df["varanda"])
    out["aluguel_anuncio"] = pd.to_numeric(df["aluguel_anuncio"], errors="coerce")
    out["lat"] = np.nan
    out["lng"] = np.nan
    return out


def _coord(valor, chave):
    if isinstance(valor, str):
        valor = ast.literal_eval(valor)
    return valor.get(chave) if isinstance(valor, dict) else np.nan


def _col(df: pd.DataFrame, nome: str, padrao) -> pd.Series:
    """Coluna do arquivo, ou uma série com o valor padrão se ela não existir."""
    return df[nome] if nome in df.columns else pd.Series(padrao, index=df.index)


def tratar_scraping(df: pd.DataFrame) -> pd.DataFrame:
    """Anúncios coletados: já trazem coordenadas (location) e listas de amenities/installations."""
    df = df.copy()
    if "city" in df.columns:
        df = df[df["city"] == "São Paulo"]

    amen = df["amenities"].astype(str) if "amenities" in df.columns else pd.Series("", index=df.index)
    inst = df["installations"].astype(str) if "installations" in df.columns else pd.Series("", index=df.index)

    out = pd.DataFrame(index=df.index)
    out["endereco_geo"] = (_col(df, "address", "").astype(str) + ", "
                           + _col(df, "neighbourhood", "").astype(str) + ", São Paulo, SP")
    out["type"] = df["type"].apply(normalizar_tipo)
    out["area"] = pd.to_numeric(df["area"], errors="coerce")
    out["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce").fillna(0).astype(int)
    out["bathrooms"] = pd.to_numeric(df["bathrooms"], errors="coerce").fillna(1).astype(int)
    out["suites"] = pd.to_numeric(_col(df, "suites", 0), errors="coerce").fillna(0).astype(int)
    out["parkingSpaces"] = pd.to_numeric(_col(df, "parkingSpaces", 0), errors="coerce").fillna(0).astype(int)
    out["mobiliado"] = para_binario(_col(df, "isFurnished", 0))
    out["am_ar_condicionado"] = amen.str.contains("AR_CONDICIONADO").astype(int)
    out["am_varanda"] = amen.str.contains("VARANDA").astype(int)
    out["inst_piscina"] = inst.str.contains("PISCINA").astype(int)
    out["inst_academia"] = inst.str.contains("ACADEMIA").astype(int)
    out["aluguel_anuncio"] = pd.to_numeric(df["rent"], errors="coerce")
    if "location" in df.columns:
        out["lat"] = df["location"].apply(_coord, chave="lat")
        out["lng"] = df["location"].apply(_coord, chave="lon")
    else:
        out["lat"] = pd.to_numeric(_col(df, "lat", np.nan), errors="coerce")
        out["lng"] = pd.to_numeric(_col(df, "lon", np.nan), errors="coerce")
    return out.reset_index(drop=True)


def filtrar_validos(df: pd.DataFrame) -> pd.DataFrame:
    """Mesmas faixas do treino (notebook 01)."""
    df = df.dropna(subset=["area", "type"])
    df = df[df["area"].between(12, 1000)]
    df = df[df["bathrooms"] >= 1]
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────
COLS_IMOVEL = ["type", "area", "bedrooms", "bathrooms", "suites", "parkingSpaces", "mobiliado",
               "am_ar_condicionado", "inst_piscina", "inst_academia", "am_varanda"]


def rodar_pipeline(df_trat: pd.DataFrame, salvar_db: bool, progress_bar, status_text, log_container):
    resultados, erros = [], []
    total = len(df_trat)

    modelo, versao_modelo, _ = carregar_modelo()
    pois = carregar_pois()
    tabela_custo = carregar_custo_extra()

    # ── ETAPA 1: GEOCODING (só onde não há coordenadas) ───────
    status_text.markdown("**[1/4] Geocodificando endereços…**")
    geos = []
    cache_geo = {}
    for i, row in df_trat.iterrows():
        if pd.notna(row["lat"]) and pd.notna(row["lng"]):
            geos.append({"lat": row["lat"], "lng": row["lng"], "endereco_formatado": row["endereco_geo"], "bairro": None})
        else:
            end = row["endereco_geo"]
            if end not in cache_geo:
                cache_geo[end] = geocode_google(end)
                time.sleep(0.05)
            geos.append(cache_geo[end])
        progress_bar.progress(int((i + 1) / total * 25), text=f"Geocoding {i+1}/{total}")
    df_trat["_geo"] = geos

    sem_geo = df_trat["_geo"].isna()
    for i in df_trat.index[sem_geo]:
        erros.append({"linha": i + 1, "endereco": df_trat.at[i, "endereco_geo"], "erro": "endereço não encontrado"})
    fora_sp = df_trat["_geo"].apply(lambda g: g is not None and not dentro_de_sp(g["lat"], g["lng"]))
    for i in df_trat.index[fora_sp]:
        erros.append({"linha": i + 1, "endereco": df_trat.at[i, "endereco_geo"], "erro": "fora da cidade de São Paulo"})
    if sem_geo.sum() or fora_sp.sum():
        log_container.warning(f"⚠️ {int(sem_geo.sum())} não geocodificado(s) e {int(fora_sp.sum())} fora de SP — ignorados.")
    df_ok = df_trat[~sem_geo & ~fora_sp]

    # ── ETAPA 2 e 3: POIs e FEATURES (mesmas funções do treino) ─
    status_text.markdown("**[2/4] Calculando distâncias aos POIs e features…**")
    entradas = []
    for n, (i, row) in enumerate(df_ok.iterrows()):
        imovel = {c: row[c] for c in COLS_IMOVEL}
        entradas.append(montar_entrada_modelo(row["_geo"]["lat"], row["_geo"]["lng"], imovel, pois).assign(_linha=i))
        progress_bar.progress(25 + int((n + 1) / max(len(df_ok), 1) * 40), text=f"Features {n+1}/{len(df_ok)}")

    if not entradas:
        return pd.DataFrame(), erros
    entrada = pd.concat(entradas, ignore_index=True)

    # ── ETAPA 4: PREDIÇÃO + BANCO ─────────────────────────────
    status_text.markdown("**[3/4] Realizando predições…**")
    entrada["aluguel_predito"] = prever_aluguel(modelo, entrada)

    status_text.markdown("**[4/4] Custo total e gravação no banco…**")
    for n, r in entrada.iterrows():
        i = r["_linha"]
        row = df_ok.loc[i]
        geo = row["_geo"]
        pct = None
        if tabela_custo is not None:
            custo, _ = custo_extra_do_bairro(geo.get("bairro"), tabela_custo)
            pct = float(custo["pct_extra_mediana"])

        imovel = {c: row[c] for c in COLS_IMOVEL}
        linha_entrada = entrada.iloc[[n]]
        registro = montar_registro(geo, imovel, linha_entrada, float(r["aluguel_predito"]),
                                   row["aluguel_anuncio"], pct, versao_modelo, origem="lote")

        predicao_id = None
        if salvar_db:
            try:
                predicao_id = salvar_predicao_aluguel(registro)
                salvar_features_monitoramento_aluguel(predicao_id, features_para_monitoramento(linha_entrada))
            except Exception as e:
                erros.append({"linha": i + 1, "endereco": row["endereco_geo"], "erro": f"DB: {e}"})

        resultados.append({
            **registro,
            "dist_metro_m": round(float(r["dist_metro"]), 0),
            "dist_polo_km": round(float(r["dist_polo_km"]), 2),
            "score_metro": round(float(r["score_metro"]), 3),
            "predicao_id": predicao_id,
        })
        progress_bar.progress(65 + int((n + 1) / len(entrada) * 35), text=f"Predição {n+1}/{len(entrada)}")

    return pd.DataFrame(resultados), erros


# ═══════════════════════════════════════════════════════════════
# INTERFACE
# ═══════════════════════════════════════════════════════════════
st.title("📦 Predição em Lote — Aluguel São Paulo")
st.caption(
    "Use o template abaixo (colunas em português) ou um arquivo de anúncios coletados "
    "(type, area, bedrooms, bathrooms, rent, location) — detecção automática."
)

if not GOOGLE_API_KEY:
    st.error("❌ Chave `GEOCODING_MAPS` não encontrada no `.env`. Geocoding indisponível.")

# ── Configurações ───────────────────────────────────────────────
with st.expander("⚙️ Configurações", expanded=False):
    salvar_db = st.checkbox("💾 Salvar no banco de dados", value=True)
    try:
        _, versao_info, metricas_info = carregar_modelo()
        st.success(f"✅ Modelo {MODEL_NAME} v{versao_info} carregado do MLflow · "
                   f"MAPE {metricas_info.get('mape_reais', 0):.1%}")
    except Exception as e:
        st.error(f"❌ Modelo não encontrado no MLflow — rode `python -m src.models.train_aluguel`.\n\n{e}")

# ── Template de download ─────────────────────────────────────────
with st.expander("📥 Baixar template CSV (aluguel)"):
    st.markdown(
        "Preencha uma linha por imóvel. Obrigatórias: **endereco, tipo_imovel, area_m2, quartos, banheiros**. "
        "`tipo_imovel`: Apartamento, Studio, Casa ou Casa em condomínio. "
        "Atributos (`mobiliado`, `ar_condicionado`, `piscina`, `academia`, `varanda`): 1/0 ou sim/não. "
        "`aluguel_anuncio` é opcional — se preenchido, calcula o erro da previsão."
    )
    template_df = pd.DataFrame({
        "endereco": ["Rua dos Pinheiros, 500, Pinheiros, São Paulo, SP",
                     "Rua Vergueiro, 3000, Vila Mariana, São Paulo, SP",
                     "Avenida Itaquera, 4000, Itaquera, São Paulo, SP"],
        "tipo_imovel": ["Apartamento", "Studio", "Casa"],
        "area_m2": [70, 28, 120],
        "quartos": [2, 1, 3],
        "banheiros": [2, 1, 2],
        "suites": [1, 0, 1],
        "vagas_garagem": [1, 0, 2],
        "mobiliado": ["não", "sim", "não"],
        "ar_condicionado": ["sim", "sim", "não"],
        "piscina": ["sim", "não", "não"],
        "academia": ["sim", "sim", "não"],
        "varanda": ["sim", "não", "não"],
        "aluguel_anuncio": [5200, 2500, None],
    })
    st.dataframe(template_df, width='stretch', height=170)
    st.download_button(
        "⬇️ Baixar template_aluguel.csv",
        template_df.to_csv(index=False).encode("utf-8"),
        "template_aluguel.csv", "text/csv",
    )

# ── Upload ───────────────────────────────────────────────────────
st.subheader("📂 Upload do arquivo")
col_up1, col_up2 = st.columns([3, 1])
with col_up1:
    uploaded_file = st.file_uploader("Selecione CSV ou XLSX", type=["csv", "xlsx"], key="upload_aluguel")
with col_up2:
    separador = st.selectbox("Separador CSV", [",", ";", "|", "\\t"], index=0, key="sep_aluguel")

if uploaded_file is None:
    st.info("⬆️ Faça o upload de um arquivo CSV ou XLSX para iniciar.")
    st.stop()

# ── Leitura ──────────────────────────────────────────────────────
try:
    if uploaded_file.name.endswith(".xlsx"):
        df_raw = pd.read_excel(uploaded_file)
    else:
        sep = "\t" if separador == "\\t" else separador
        df_raw = pd.read_csv(uploaded_file, sep=sep)
except Exception as e:
    st.error(f"❌ Erro ao ler arquivo: {e}")
    st.stop()

st.success(f"✅ Arquivo carregado: **{len(df_raw)} linhas** × **{len(df_raw.columns)} colunas**")

with st.expander("👁️ Preview dos dados brutos", expanded=True):
    st.dataframe(df_raw.head(10), width='stretch', height=200)

# ── Detecção de formato e tratamento ────────────────────────────
st.subheader("🔍 Formato detectado")

if is_formato_scraping(df_raw):
    st.success("✅ **Formato Scraping (anúncios de aluguel)** — usa as coordenadas do arquivo, sem geocoding.")
    df_trat = tratar_scraping(df_raw)
else:
    faltando = OBRIGATORIAS_TEMPLATE - set(df_raw.columns.str.strip().str.lower())
    if faltando:
        st.error(f"❌ Colunas obrigatórias ausentes: {', '.join(sorted(faltando))}. Use o template acima.")
        st.stop()
    st.success("✅ **Formato Template** — endereços serão geocodificados (Google Maps).")
    df_trat = tratar_template(df_raw)

tipo_invalido = df_trat["type"].isna().sum()
df_trat = filtrar_validos(df_trat)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Registros brutos", len(df_raw))
c2.metric("Após tratamento", len(df_trat))
c3.metric("Descartados", len(df_raw) - len(df_trat))
c4.metric("Por tipo", " | ".join(f"{k}: {v}" for k, v in df_trat["type"].value_counts().to_dict().items()))
if tipo_invalido:
    st.caption(f"⚠️ {tipo_invalido} linha(s) com tipo de imóvel não reconhecido foram descartadas.")

with st.expander("🔬 Preview do tratamento aplicado"):
    st.dataframe(df_trat.head(15), width='stretch', height=200)

if len(df_trat) == 0:
    st.error("❌ Nenhum registro válido encontrado. Verifique o arquivo (área entre 12 e 1.000 m², banheiros ≥ 1).")
    st.stop()

# ── Botão de execução ────────────────────────────────────────────
st.markdown("---")
col_b1, col_b2 = st.columns([3, 1])
with col_b1:
    executar = st.button(
        f"🚀 Executar pipeline completo ({len(df_trat)} imóveis)",
        type="primary",
        width='stretch',
        key="executar_aluguel",
    )
with col_b2:
    st.caption("⏱️ ~1 s por imóvel com geocoding")

if not executar:
    st.stop()

# ── Execução ─────────────────────────────────────────────────────
st.markdown("---")
st.subheader("⚙️ Pipeline em execução…")
progress_bar = st.progress(0, text="Iniciando…")
status_text = st.empty()
log_container = st.container()

df_res, erros = rodar_pipeline(df_trat, salvar_db, progress_bar, status_text, log_container)

progress_bar.progress(100, text="✅ Concluído!")
status_text.empty()

if df_res.empty:
    st.error("❌ Nenhuma previsão foi gerada.")
    if erros:
        st.dataframe(pd.DataFrame(erros), width='content')
    st.stop()

# ── Resultados ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("📊 Resultados")

ok = df_res["aluguel_predito"].notna().sum()
tem_erro = df_res["erro_percentual"].notna().any()

c1, c2, c3, c4 = st.columns(4)
c1.metric("✅ Predições", f"{ok} / {len(df_trat)}")
c2.metric("❌ Erros", len(erros))
c3.metric("💰 Aluguel médio", f"R$ {df_res['aluguel_predito'].mean():,.0f}")
c4.metric("📉 MAPE médio", f"{df_res['erro_percentual'].mean():.1%}" if tem_erro else "—")

cols_tabela = [
    "endereco", "tipo_imovel_cat", "area", "bedrooms", "bathrooms", "parkingSpaces",
    "dist_metro_m", "aluguel_anuncio", "aluguel_predito", "custo_total_estimado",
    "erro_absoluto", "erro_percentual",
]
st.dataframe(
    df_res[cols_tabela].style.format({
        "area": "{:.0f} m²",
        "dist_metro_m": "{:,.0f} m",
        "aluguel_anuncio": "R$ {:,.0f}",
        "aluguel_predito": "R$ {:,.0f}",
        "custo_total_estimado": "R$ {:,.0f}",
        "erro_absoluto": "R$ {:,.0f}",
        "erro_percentual": "{:.1%}",
    }, na_rep="—"),
    width='stretch',
    height=440,
)

if erros:
    with st.expander(f"⚠️ {len(erros)} erro(s) durante o processamento"):
        st.dataframe(pd.DataFrame(erros), width='content')

# ── Exportar ──────────────────────────────────────────────────────
st.markdown("---")
st.subheader("💾 Exportar resultados")
col_dl1, col_dl2 = st.columns(2)

with col_dl1:
    st.download_button(
        "⬇️ Baixar CSV completo",
        df_res.to_csv(index=False).encode("utf-8"),
        "predicoes_aluguel_lote.csv", "text/csv",
        width='content',
    )
with col_dl2:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_res.to_excel(writer, sheet_name="Predições", index=False)
        if erros:
            pd.DataFrame(erros).to_excel(writer, sheet_name="Erros", index=False)
    st.download_button(
        "⬇️ Baixar XLSX completo",
        buf.getvalue(),
        "predicoes_aluguel_lote.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='content',
    )

if salvar_db and ok:
    st.success(f"✅ {ok} predições salvas no banco de dados.")
