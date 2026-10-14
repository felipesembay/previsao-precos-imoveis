"""
App Streamlit — Previsão de Aluguel em São Paulo (capital)
Pipeline: Endereço → Google Geocoding → POIs (OSM local) → Scores → Modelo do MLflow (RentPriceModel_SP) → PostgreSQL

As features são calculadas com as mesmas funções do treino (src/features/aluguel.py).
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from aluguel_core import (GOOGLE_API_KEY, MODEL_NAME, TIPOS, carregar_custo_extra,
                          carregar_modelo, carregar_pois, custo_extra_do_bairro,
                          features_para_monitoramento, geocode_google, montar_registro,
                          prever_aluguel)
from db import salvar_features_monitoramento_aluguel, salvar_predicao_aluguel

from src.features.aluguel import (CAT_FEATURES, NUM_FEATURES, dentro_de_sp,
                                  montar_entrada_modelo)

if not GOOGLE_API_KEY:
    st.error("❌ Chave GEOCODING_MAPS não encontrada no .env")
    st.stop()

# ==========================================
# Interface Principal
# ==========================================
st.caption("🔮 Endereço → Google Maps → POIs (OpenStreetMap) → Modelo de aluguel (MLflow)")

with st.spinner("Carregando modelo e POIs de São Paulo..."):
    modelo, versao_modelo, metricas = carregar_modelo()
    pois = carregar_pois()
    tabela_custo = carregar_custo_extra()

st.info(f"🤖 Modelo **{MODEL_NAME}** v{versao_modelo} · R² {metricas.get('r2', 0):.3f} · "
        f"erro médio R$ {metricas.get('mae_reais', 0):,.0f} · MAPE {metricas.get('mape_reais', 0):.1%}")

st.subheader("📍 Endereço")
endereco = st.text_input(
        "Endereço completo",
        placeholder="Rua dos Pinheiros, 500, Pinheiros, São Paulo, SP",
        help="O modelo cobre apenas a cidade de São Paulo (capital)"
    )

# Formulário
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🏠 Características")
    tipo_label = st.selectbox("Tipo de imóvel", list(TIPOS))
    area = st.number_input("Área (m²)", min_value=12, max_value=1000, value=60, step=5)
    quartos = st.number_input("Quartos", min_value=0, value=2, step=1)
    banheiros = st.number_input("Banheiros", min_value=1, value=1, step=1)
    suites = st.number_input("Suítes", min_value=0, value=0, step=1)
    vagas = st.number_input("Vagas de garagem", min_value=0, value=1, step=1)

with col2:
    st.subheader("✨ Atributos")
    mobiliado = st.checkbox("Mobiliado")
    ar_cond = st.checkbox("Ar-condicionado")
    varanda = st.checkbox("Varanda")
    piscina = st.checkbox("Piscina no condomínio")
    academia = st.checkbox("Academia no condomínio")
    aluguel_anuncio = st.number_input("Aluguel do anúncio (opcional)", min_value=0, value=0, step=100)

if st.button("🚀 Calcular Previsão", type="primary", use_container_width=True):
    if not endereco.strip():
        st.error("❌ Por favor, insira um endereço válido")
        st.stop()

    # 1. GEOCODING
    with st.spinner("🌍 Geocodificando endereço..."):
        geo = geocode_google(endereco)

    if not geo:
        st.error("❌ Endereço não encontrado. Verifique a grafia.")
        st.stop()

    if not dentro_de_sp(geo["lat"], geo["lng"]):
        st.error("❌ O endereço está fora da cidade de São Paulo. O modelo foi treinado apenas com a capital.")
        st.stop()

    st.success(f"✅ {geo['endereco_formatado']}")
    st.map(pd.DataFrame({'lat': [geo["lat"]], 'lon': [geo["lng"]]}))

    # 2. FEATURES (mesmas funções do treino)
    imovel = {
        "type": TIPOS[tipo_label],
        "area": float(area),
        "bedrooms": int(quartos),
        "bathrooms": int(banheiros),
        "suites": int(suites),
        "parkingSpaces": int(vagas),
        "mobiliado": int(mobiliado),
        "am_ar_condicionado": int(ar_cond),
        "inst_piscina": int(piscina),
        "inst_academia": int(academia),
        "am_varanda": int(varanda),
    }
    with st.spinner("📍 Calculando distâncias aos POIs..."):
        entrada = montar_entrada_modelo(geo["lat"], geo["lng"], imovel, pois)

    # Distâncias mais relevantes (metrô foi o POI com maior efeito na inferência)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🚇 Metrô mais próximo", f"{entrada['dist_metro'].iloc[0]:,.0f} m")
    col2.metric("🏫 Escola privada", f"{entrada['dist_escola_privada'].iloc[0]:,.0f} m")
    col3.metric("🛒 Supermercado", f"{entrada['dist_supermercado'].iloc[0]:,.0f} m")
    col4.metric("🏢 Polo de emprego", f"{entrada['dist_polo_km'].iloc[0]:,.1f} km")

    with st.expander("🔍 Ver features enviadas ao modelo"):
        st.dataframe(entrada[NUM_FEATURES + CAT_FEATURES].T.rename(columns={0: "valor"}))

    # 3. PREVISÃO
    with st.spinner("🤖 Fazendo predição..."):
        try:
            aluguel = float(prever_aluguel(modelo, entrada)[0])
            mape = metricas.get("mape_reais", 0)

            st.success(f"#### 💰 Aluguel estimado: R$ {aluguel:,.2f} / mês")
            st.caption(f"Faixa típica de erro do modelo (±{mape:.0%}): "
                       f"R$ {aluguel * (1 - mape):,.0f} – R$ {aluguel * (1 + mape):,.0f}")

            # Custo total = aluguel × (1 + % extra do bairro)
            pct = None
            if tabela_custo is not None:
                custo, origem = custo_extra_do_bairro(geo.get("bairro"), tabela_custo)
                pct = float(custo["pct_extra_mediana"])
                st.info(f"""
    🧾 **Custo total estimado (aluguel + condomínio + IPTU + taxas): R$ {aluguel * (1 + pct):,.2f} / mês**
    - Custo extra típico: {pct:.1%} sobre o aluguel (faixa P25–P75: {custo['pct_extra_p25']:.0%} a {custo['pct_extra_p75']:.0%})
    - Referência: {origem}
    """)
            else:
                st.warning("Tabela de custo extra não encontrada (rode o notebook 01_limpeza_eda).")

            registro = montar_registro(geo, imovel, entrada, aluguel,
                                       float(aluguel_anuncio) if aluguel_anuncio > 0 else None,
                                       pct, versao_modelo, origem="individual")

            if registro["erro_absoluto"] is not None:
                st.info(f"""
    📉 **Comparação com o anúncio**
    - Erro absoluto: R$ {registro['erro_absoluto']:,.2f}
    - Erro percentual: {registro['erro_percentual'] * 100:.2f}%
    """)

            # 4. Salvar no banco
            with st.spinner("💾 Salvando predição no banco de dados..."):
                try:
                    predicao_id = salvar_predicao_aluguel(registro)
                    salvar_features_monitoramento_aluguel(predicao_id, features_para_monitoramento(entrada))
                    st.success("✅ Predição salva no banco de dados!")
                except Exception as e:
                    st.warning(f"⚠️ Previsão feita, mas não foi salva no banco: {e}")

        except Exception as e:
            st.error(f"❌ Erro na predição: {str(e)}")
            st.exception(e)

# Rodapé
st.markdown("---")
st.caption("✅ Cobertura: cidade de São Paulo (capital) · POIs do OpenStreetMap · Modelo versionado no MLflow")
