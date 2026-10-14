"""
POI Manager — Gerenciamento de Pontos de Interesse
====================================================
Permite:
  1. Migrar POIs do cache OSM (arquivos JSON) para o banco de dados
  2. Buscar novos POIs via OSMnx (como no notebook) e salvar no banco
  3. Visualizar e gerenciar as cidades já cadastradas no banco
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_connection as _pg_connection

try:
    import osmnx as ox
    OSMNX_AVAILABLE = True
except ImportError:
    OSMNX_AVAILABLE = False

load_dotenv()

CACHE_DIR = Path(__file__).parent / "cache"

# ─────────────────────────────────────────────────────────────
# Configuração da página
# ─────────────────────────────────────────────────────────────
# st.set_page_config() - Desabilitado quando usado via general.py
# st.set_page_config(
#     page_title="📍 Gerenciador de POIs",
#     page_icon="📍",
#     layout="wide",
#     initial_sidebar_state="collapsed",
# )

# ─────────────────────────────────────────────────────────────
# CSS personalizado
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main { background: #0f1117; }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #1a1d27;
        padding: 8px;
        border-radius: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 24px;
        border-radius: 8px;
        font-weight: 500;
        font-size: 0.9rem;
        color: #9ca3af;
        transition: all 0.2s;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        color: white !important;
    }

    .stat-card {
        background: linear-gradient(135deg, #1a1d27, #232733);
        border: 1px solid #2d3147;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        transition: transform 0.2s, border-color 0.2s;
    }
    .stat-card:hover {
        transform: translateY(-2px);
        border-color: #6366f1;
    }
    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stat-label {
        color: #9ca3af;
        font-size: 0.85rem;
        margin-top: 4px;
    }

    .poi-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 2px;
    }
    .info-box {
        background: #1e2130;
        border-left: 4px solid #6366f1;
        border-radius: 0 8px 8px 0;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 0.9rem;
        color: #d1d5db;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Banco (PostgreSQL) helpers
# ─────────────────────────────────────────────────────────────
def get_connection():
    """PostgreSQL (PG_* no .env), linhas como dict — mesmo comportamento do antigo DictCursor."""
    return _pg_connection(dict_rows=True)


def salvar_pois_db(pois_list: list, cidade: str, estado: str, substituir: bool = True):
    """Salva lista de POIs no banco. Se substituir=True, apaga os existentes por tipo."""
    if not pois_list:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if substituir:
            tipos = list({p["tipo_poi"] for p in pois_list})
            for tipo in tipos:
                cursor.execute(
                    "DELETE FROM pois WHERE cidade = %s AND tipo_poi = %s",
                    (cidade, tipo),
                )
        cursor.executemany(
            "INSERT INTO pois (nome, tipo_poi, latitude, longitude, cidade, estado, fonte) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    p.get("nome", p["tipo_poi"]),
                    p["tipo_poi"],
                    p["lat"],
                    p["lng"],
                    cidade,
                    estado,
                    p.get("fonte", "osm"),
                )
                for p in pois_list
            ],
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


@st.cache_data(ttl=30, show_spinner=False)
def listar_cidades_db():
    """Retorna DataFrame com cidades cadastradas e contagem de POIs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            cidade,
            estado,
            COUNT(*) AS total_pois,
            COUNT(DISTINCT tipo_poi) AS tipos_distintos,
            STRING_AGG(DISTINCT tipo_poi, ', ' ORDER BY tipo_poi) AS tipos,
            MAX(created_at) AS ultima_atualizacao
        FROM pois
        GROUP BY cidade, estado
        ORDER BY total_pois DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(rows)


@st.cache_data(ttl=30, show_spinner=False)
def contar_pois_total():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM pois")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row["total"] if row else 0


def deletar_pois_cidade(cidade: str, estado: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if estado:
        cursor.execute("DELETE FROM pois WHERE cidade = %s AND estado = %s", (cidade, estado))
    else:
        cursor.execute("DELETE FROM pois WHERE cidade = %s", (cidade,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected


# ─────────────────────────────────────────────────────────────
# Mapeamento OSM → tipo_poi (mesmo padrão do batch_app)
# ─────────────────────────────────────────────────────────────
OSM_TIPO_MAP = {
    # amenity
    "hospital": "hospital",
    "clinic": "hospital",
    "pharmacy": "farmacia",
    "school": "escola",
    "college": "escola",
    "university": "escola",
    "police": "policia",
    "fire_station": "policia",
    "park": "parque",       # amenity=park (raro, mas existe)
    # shop
    "supermarket": "mercado",
    "convenience": "mercado",
    # leisure
    "park": "parque",
    "garden": "parque",
    "nature_reserve": "parque",
}

TIPOS_VALIDOS = {"mercado", "farmacia", "escola", "hospital", "parque", "policia"}

EMOJI_TIPO = {
    "mercado":  "🛒",
    "farmacia": "💊",
    "escola":   "🏫",
    "hospital": "🏥",
    "parque":   "🌳",
    "policia":  "🚔",
}

OSM_CONFIGS = {
    "hospital": {"amenity": "hospital"},
    "mercado":  {"shop": ["supermarket", "convenience"]},
    "farmacia": {"amenity": "pharmacy"},
    "escola":   {"amenity": ["school", "college", "university"]},
    "parque":   {"leisure": ["park", "garden"]},
    "policia":  {"amenity": ["police", "fire_station"]},
}


def inferir_tipo_poi(tags: dict):
    """Infere o tipo_poi a partir das tags OSM do elemento."""
    amenity = tags.get("amenity", "")
    shop    = tags.get("shop", "")
    leisure = tags.get("leisure", "")

    if amenity in OSM_TIPO_MAP:
        return OSM_TIPO_MAP[amenity]
    if shop in OSM_TIPO_MAP:
        return OSM_TIPO_MAP[shop]
    if leisure in ("park", "garden", "nature_reserve"):
        return "parque"
    return None


def processar_json_osm(caminho: Path) -> list[dict]:
    """
    Lê um arquivo JSON do cache OSMnx/Overpass e retorna lista de POIs
    com campos: nome, tipo_poi, lat, lng.
    Apenas elementos com tags OSM válidas são incluídos.
    """
    try:
        with open(caminho, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    elements = data.get("elements", [])
    pois = []

    for el in elements:
        tags = el.get("tags", {})
        if not tags:
            continue

        tipo = inferir_tipo_poi(tags)
        if tipo not in TIPOS_VALIDOS:
            continue

        # Coordenadas
        lat = el.get("lat")
        lng = el.get("lon")

        # Elementos do tipo "way" ou "relation" têm centro calculado
        if lat is None and "center" in el:
            lat = el["center"].get("lat")
            lng = el["center"].get("lon")

        if lat is None or lng is None:
            continue

        nome = tags.get("name") or tipo
        pois.append({
            "nome":     nome,
            "tipo_poi": tipo,
            "lat":      float(lat),
            "lng":      float(lng),
            "fonte":    "osm_cache",
        })

    return pois


# ─────────────────────────────────────────────────────────────
# OSMNX — Extração direta (como no notebook)
# ─────────────────────────────────────────────────────────────
def extrair_pois_osmnx(cidade: str, estado: str, tipos_selecionados: list,
                       progress_cb=None) -> list[dict]:
    """Extrai POIs via OSMnx para a cidade informada (mesmo padrão do notebook)."""
    if not OSMNX_AVAILABLE:
        return []

    ox.settings.use_cache   = True
    ox.settings.log_console = False
    place_query = f"{cidade}, {estado}, Brasil"
    todos_pois  = []

    for i, tipo in enumerate(tipos_selecionados):
        if progress_cb:
            progress_cb(i, len(tipos_selecionados), tipo)
        tags = OSM_CONFIGS.get(tipo, {})
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
                nome = str(row.get("name", tipo) or tipo)
                todos_pois.append({
                    "nome":     nome,
                    "tipo_poi": tipo,
                    "lat":      float(geom.y),
                    "lng":      float(geom.x),
                    "fonte":    "osmnx",
                })
        except Exception as e:
            st.warning(f"⚠️ Não foi possível extrair **{tipo}** de **{cidade}**: {e}")

    return todos_pois


# ═══════════════════════════════════════════════════════════════
# INTERFACE PRINCIPAL
# ═══════════════════════════════════════════════════════════════
st.title("📍 Gerenciador de POIs")
st.caption("Gerencie os Pontos de Interesse usados na precificação de imóveis")

# ── Métricas rápidas ──────────────────────────────────────────
try:
    df_cidades = listar_cidades_db()
    total_pois   = int(df_cidades["total_pois"].sum()) if not df_cidades.empty else 0
    total_cidades = len(df_cidades)
    total_tipos  = len(TIPOS_VALIDOS)
except Exception:
    df_cidades   = pd.DataFrame()
    total_pois   = 0
    total_cidades = 0
    total_tipos  = len(TIPOS_VALIDOS)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{total_pois:,}</div>
        <div class="stat-label">POIs no banco</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{total_cidades}</div>
        <div class="stat-label">Cidades cadastradas</div>
    </div>""", unsafe_allow_html=True)
with c3:
    arquivos_cache = list(CACHE_DIR.glob("*.json"))
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{len(arquivos_cache)}</div>
        <div class="stat-label">Arquivos no cache</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{total_tipos}</div>
        <div class="stat-label">Tipos de POI</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Abas ──────────────────────────────────────────────────────
tab_buscar, tab_cache, tab_gerenciar = st.tabs([
    "🌐 Buscar POIs (OSMnx)",
    "📦 Migrar Cache → Banco",
    "🗺️ Cidades Cadastradas",
])


# ═══════════════════════════════════════════════════════════════
# ABA 1 — BUSCAR POIs VIA OSMNX (fluxo principal do notebook)
# ═══════════════════════════════════════════════════════════════
with tab_buscar:
    st.subheader("🌐 Buscar e salvar POIs via OpenStreetMap")
    st.markdown("""
    <div class="info-box">
        🚀 Use esta aba para baixar POIs de uma nova cidade diretamente do OpenStreetMap 
        via <strong>OSMnx</strong> e salvá-los no banco de dados. Isso é o que o fluxo do 
        notebook fazia — e depois a precificação em lote vai consumir do banco, sem precisar 
        chamar o OSMnx toda hora.
    </div>
    """, unsafe_allow_html=True)

    if not OSMNX_AVAILABLE:
        st.error("❌ **OSMnx não está instalado.** Execute: `pip install osmnx`")
    else:
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            cidade_busca = st.text_input(
                "🏙️ Cidade",
                placeholder="Ex: Ponta Grossa",
                help="Nome exato da cidade como aparece no OpenStreetMap",
            )
        with col_f2:
            estado_busca = st.text_input(
                "🗺️ Estado (sigla)",
                placeholder="Ex: PR",
                max_chars=2,
                help="Sigla do estado (UF). Ex: PR, SP, MG",
            ).upper().strip()

        st.markdown("**📌 Tipos de POI a buscar:**")
        cols_tipos = st.columns(6)
        tipos_selecionados = []
        for i, tipo in enumerate(sorted(TIPOS_VALIDOS)):
            with cols_tipos[i]:
                emoji = EMOJI_TIPO.get(tipo, "📍")
                if st.checkbox(f"{emoji} {tipo.capitalize()}", value=True, key=f"chk_osm_{tipo}"):
                    tipos_selecionados.append(tipo)

        col_opt1, col_opt2 = st.columns([2, 1])
        with col_opt1:
            substituir_osm = st.checkbox(
                "🔄 Substituir POIs existentes da cidade (por tipo)",
                value=True,
                help="Se marcado, apaga os POIs do mesmo tipo antes de inserir os novos.",
            )

        executar_osm = st.button(
            "🚀 Buscar e salvar POIs",
            type="primary",
            disabled=not cidade_busca or not estado_busca or not tipos_selecionados,
        )

        if executar_osm:
            if not cidade_busca:
                st.error("❌ Informe o nome da cidade.")
            elif not estado_busca:
                st.error("❌ Informe a sigla do estado.")
            elif not tipos_selecionados:
                st.error("❌ Selecione ao menos um tipo de POI.")
            else:
                cidade_fmt = cidade_busca.strip().title()
                estado_fmt = estado_busca.strip().upper()

                st.info(f"🔍 Buscando POIs em **{cidade_fmt} — {estado_fmt}**…")
                progress_bar   = st.progress(0, text="Iniciando busca…")
                status_place   = st.empty()
                log_place      = st.container()

                def progress_cb(idx, total, tipo_atual):
                    pct = int((idx / total) * 100)
                    progress_bar.progress(pct, text=f"Extraindo {EMOJI_TIPO.get(tipo_atual, '📍')} **{tipo_atual}**… ({idx+1}/{total})")
                    status_place.caption(f"↳ Consultando OpenStreetMap para: **{tipo_atual}**")

                t0      = time.time()
                pois    = extrair_pois_osmnx(cidade_fmt, estado_fmt, tipos_selecionados, progress_cb)
                elapsed = time.time() - t0

                progress_bar.progress(100, text="✅ Busca concluída!")
                status_place.empty()

                if not pois:
                    st.warning("⚠️ Nenhum POI encontrado. Verifique o nome da cidade e tente novamente.")
                else:
                    # Estatísticas
                    df_preview = pd.DataFrame(pois)
                    contagem   = df_preview["tipo_poi"].value_counts().to_dict()

                    st.success(f"✅ **{len(pois)} POIs** encontrados em {elapsed:.1f}s")

                    c_stats = st.columns(len(contagem))
                    for i, (tipo, cnt) in enumerate(sorted(contagem.items())):
                        c_stats[i].metric(f"{EMOJI_TIPO.get(tipo,'📍')} {tipo.capitalize()}", cnt)

                    with st.expander("👁️ Preview dos POIs encontrados", expanded=False):
                        st.dataframe(
                            df_preview[["tipo_poi", "nome", "lat", "lng"]].head(50),
                            use_container_width=True, height=300,
                        )

                    # Salvar no banco
                    with st.spinner("💾 Salvando no banco de dados…"):
                        try:
                            salvar_pois_db(pois, cidade_fmt, estado_fmt, substituir=substituir_osm)
                            st.success(f"✅ **{len(pois)} POIs** salvos no banco para **{cidade_fmt} — {estado_fmt}**!")
                            st.balloons()
                            # Limpar cache do listar_cidades_db
                            listar_cidades_db.clear()
                        except Exception as e:
                            st.error(f"❌ Erro ao salvar no banco: {e}")


# ═══════════════════════════════════════════════════════════════
# ABA 2 — MIGRAR CACHE → BANCO
# ═══════════════════════════════════════════════════════════════
with tab_cache:
    st.subheader("📦 Migrar arquivos de cache OSM para o banco de dados")
    st.markdown("""
    <div class="info-box">
        📂 Os arquivos JSON na pasta <code>cache/</code> são respostas cacheadas do 
        <strong>Overpass API</strong> (formato OSMnx). Esta aba analisa esses arquivos, 
        extrai os POIs válidos e permite migrá-los para o banco de dados.
        <br><br>
        Como os nomes dos arquivos são hashes, você precisa informar a <strong>cidade</strong> 
        e o <strong>estado</strong> correspondentes antes de importar.
    </div>
    """, unsafe_allow_html=True)

    if not CACHE_DIR.exists() or not arquivos_cache:
        st.warning("📭 Pasta `cache/` vazia ou não encontrada.")
    else:
        # ── Análise rápida do cache ──────────────────────────────
        with st.expander("🔬 Analisar arquivos do cache", expanded=True):
            if st.button("🔍 Analisar cache agora", key="btn_analisar"):
                progress_analise = st.progress(0, text="Analisando arquivos…")
                resultados_analise = []

                for i, arq in enumerate(arquivos_cache):
                    pois_arq = processar_json_osm(arq)
                    if pois_arq:
                        contagem_tipos = {}
                        for p in pois_arq:
                            contagem_tipos[p["tipo_poi"]] = contagem_tipos.get(p["tipo_poi"], 0) + 1
                        resultados_analise.append({
                            "arquivo":     arq.name[:20] + "…",
                            "total_pois":  len(pois_arq),
                            "tipos":       ", ".join(f"{EMOJI_TIPO.get(t,'')} {t}({n})"
                                                     for t, n in sorted(contagem_tipos.items())),
                            "tamanho_kb":  round(arq.stat().st_size / 1024, 1),
                            "_path":       str(arq),
                        })
                    progress_analise.progress(
                        int((i + 1) / len(arquivos_cache) * 100),
                        text=f"Analisando… {i+1}/{len(arquivos_cache)}",
                    )

                progress_analise.empty()

                if resultados_analise:
                    df_analise = pd.DataFrame(resultados_analise).drop(columns=["_path"])
                    st.success(f"✅ **{len(resultados_analise)}** arquivos com POIs válidos "
                               f"(de {len(arquivos_cache)} no total)")
                    st.dataframe(df_analise, use_container_width=True, height=300)
                    st.session_state["cache_analisado"] = resultados_analise
                else:
                    st.warning("⚠️ Nenhum arquivo com POIs válidos encontrado.")

        st.markdown("---")

        # ── Formulário de importação ─────────────────────────────
        st.subheader("📥 Importar todos os POIs do cache")

        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            cidade_cache = st.text_input(
                "🏙️ Cidade dos POIs no cache",
                placeholder="Ex: Ponta Grossa",
                key="cidade_cache",
                help="Informe a cidade à qual os arquivos de cache correspondem",
            )
        with col_c2:
            estado_cache = st.text_input(
                "🗺️ Estado (sigla)",
                placeholder="Ex: PR",
                max_chars=2,
                key="estado_cache",
            ).upper().strip()

        col_opt_c1, col_opt_c2 = st.columns(2)
        with col_opt_c1:
            substituir_cache = st.checkbox(
                "🔄 Substituir POIs existentes da cidade (por tipo)",
                value=True,
                key="sub_cache",
            )
        with col_opt_c2:
            somente_com_nome = st.checkbox(
                "🏷️ Incluir apenas POIs com nome definido",
                value=False,
                help="Se marcado, ignora POIs sem campo 'name' no OSM",
                key="somente_nome",
            )

        st.markdown("**📌 Filtrar tipos a importar:**")
        cols_tipos_cache = st.columns(6)
        tipos_cache = []
        for i, tipo in enumerate(sorted(TIPOS_VALIDOS)):
            with cols_tipos_cache[i]:
                emoji = EMOJI_TIPO.get(tipo, "📍")
                if st.checkbox(f"{emoji} {tipo.capitalize()}", value=True, key=f"chk_cache_{tipo}"):
                    tipos_cache.append(tipo)

        importar_cache = st.button(
            f"📥 Importar POIs do cache ({len(arquivos_cache)} arquivos)",
            type="primary",
            disabled=not cidade_cache or not estado_cache,
        )

        if importar_cache:
            if not cidade_cache:
                st.error("❌ Informe o nome da cidade.")
            elif not estado_cache:
                st.error("❌ Informe a sigla do estado.")
            else:
                cidade_fmt   = cidade_cache.strip().title()
                estado_fmt   = estado_cache.strip().upper()
                progress_imp = st.progress(0, text="Processando arquivos…")
                status_imp   = st.empty()
                log_imp      = st.container()

                todos_pois = []
                for i, arq in enumerate(arquivos_cache):
                    pois_arq = processar_json_osm(arq)

                    # Filtrar por tipo selecionado
                    pois_arq = [p for p in pois_arq if p["tipo_poi"] in tipos_cache]

                    # Filtrar por nome se solicitado
                    if somente_com_nome:
                        pois_arq = [p for p in pois_arq if p["nome"] != p["tipo_poi"]]

                    todos_pois.extend(pois_arq)
                    progress_imp.progress(
                        int((i + 1) / len(arquivos_cache) * 100),
                        text=f"Processando {i+1}/{len(arquivos_cache)} arquivos…",
                    )

                progress_imp.progress(100, text="✅ Processamento concluído!")
                status_imp.empty()

                if not todos_pois:
                    st.warning("⚠️ Nenhum POI válido encontrado nos arquivos de cache com os filtros aplicados.")
                else:
                    # Remover duplicatas (mesma lat/lng)
                    df_pois = pd.DataFrame(todos_pois)
                    df_pois = df_pois.drop_duplicates(subset=["tipo_poi", "lat", "lng"])
                    todos_pois_dedup = df_pois.to_dict("records")

                    contagem = df_pois["tipo_poi"].value_counts().to_dict()
                    st.info(f"📊 **{len(todos_pois_dedup)} POIs únicos** extraídos do cache "
                            f"(de {len(todos_pois)} brutos antes da deduplicação)")

                    c_stats = st.columns(min(len(contagem), 6))
                    for i, (tipo, cnt) in enumerate(sorted(contagem.items())):
                        if i < 6:
                            c_stats[i].metric(f"{EMOJI_TIPO.get(tipo,'📍')} {tipo.capitalize()}", cnt)

                    with st.expander("👁️ Preview dos POIs a importar", expanded=False):
                        st.dataframe(
                            df_pois[["tipo_poi", "nome", "lat", "lng"]].head(100),
                            use_container_width=True, height=300,
                        )

                    with st.spinner(f"💾 Salvando {len(todos_pois_dedup)} POIs no banco…"):
                        try:
                            salvar_pois_db(todos_pois_dedup, cidade_fmt, estado_fmt,
                                           substituir=substituir_cache)
                            st.success(
                                f"✅ **{len(todos_pois_dedup)} POIs** importados com sucesso "
                                f"para **{cidade_fmt} — {estado_fmt}**!"
                            )
                            st.balloons()
                            listar_cidades_db.clear()
                        except Exception as e:
                            st.error(f"❌ Erro ao salvar no banco: {e}")


# ═══════════════════════════════════════════════════════════════
# ABA 3 — CIDADES CADASTRADAS
# ═══════════════════════════════════════════════════════════════
with tab_gerenciar:
    st.subheader("🗺️ Cidades com POIs cadastrados no banco")

    col_ref = st.columns([4, 1])[1]
    with col_ref:
        if st.button("🔄 Atualizar", key="btn_refresh"):
            listar_cidades_db.clear()
            st.rerun()

    try:
        df_cidades_atual = listar_cidades_db()
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao banco: {e}")
        st.stop()

    if df_cidades_atual.empty:
        st.info("📭 Nenhuma cidade cadastrada ainda. Use as abas acima para adicionar POIs.")
    else:
        # Cards por cidade
        for _, cidade_row in df_cidades_atual.iterrows():
            with st.container():
                col_info, col_tipos, col_acao = st.columns([3, 4, 1])

                with col_info:
                    st.markdown(f"### 🏙️ {cidade_row['cidade']}")
                    st.caption(
                        f"**Estado:** {cidade_row.get('estado', '—')}  |  "
                        f"**Última atualização:** {str(cidade_row.get('ultima_atualizacao', '—'))[:16]}"
                    )

                with col_tipos:
                    st.metric("Total de POIs", f"{int(cidade_row['total_pois']):,}")
                    tipos_str = str(cidade_row.get("tipos", ""))
                    badges = ""
                    for tipo in tipos_str.split(", "):
                        tipo = tipo.strip()
                        if tipo:
                            badges += f"<span class='poi-badge' style='background:#1e2a50;color:#818cf8;'>{EMOJI_TIPO.get(tipo,'📍')} {tipo}</span>"
                    if badges:
                        st.markdown(badges, unsafe_allow_html=True)

                with col_acao:
                    st.markdown("<br>", unsafe_allow_html=True)
                    with st.popover("🗑️ Excluir"):
                        st.warning(f"Excluir **todos os POIs** de **{cidade_row['cidade']}**?")
                        if st.button(
                            "✅ Confirmar exclusão",
                            key=f"del_{cidade_row['cidade']}",
                            type="primary",
                        ):
                            removed = deletar_pois_cidade(
                                cidade_row["cidade"],
                                cidade_row.get("estado"),
                            )
                            st.success(f"✅ {removed} POIs removidos.")
                            listar_cidades_db.clear()
                            st.rerun()

                st.divider()

        # Tabela resumo
        with st.expander("📊 Tabela resumida de todas as cidades"):
            st.dataframe(
                df_cidades_atual[[
                    "cidade", "estado", "total_pois", "tipos_distintos", "tipos", "ultima_atualizacao"
                ]].rename(columns={
                    "cidade":             "Cidade",
                    "estado":             "UF",
                    "total_pois":         "Total POIs",
                    "tipos_distintos":    "Tipos",
                    "tipos":              "Categorias",
                    "ultima_atualizacao": "Última Atualização",
                }),
                use_container_width=True,
                hide_index=True,
            )

        # Download do inventário
        st.markdown("---")
        csv_inventario = df_cidades_atual.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Baixar inventário de POIs (CSV)",
            csv_inventario,
            "inventario_pois.csv",
            "text/csv",
        )
