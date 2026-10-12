"""
App Principal - Plataforma Unificada de Precificação Imobiliária
==================================================================
Integra três módulos principais:
  1. Predição Individual (app2.py) - Análise de imóvel único
  2. Predição em Lote (batch_app.py) - Processamento de múltiplos imóveis
  3. Gerenciador de POIs (poi_manager.py) - Administração de pontos de interesse
"""

import os
import sys

import streamlit as st

# Adicionar diretório streamlit_app ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "streamlit_app"))

# ==========================================
# Configuração Global da Página
# ==========================================
st.set_page_config(
    page_title="🏠 Plataforma de Precificação Imobiliária",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CSS Customizado
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] { 
        font-family: 'Inter', sans-serif; 
    }
    
    .main { 
        background: #0f1117; 
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1d27 0%, #0f1117 100%);
        border-right: 1px solid #2d3147;
    }
    
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 {
        color: #e5e7eb;
        font-size: 1.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
        padding-bottom: 1rem;
        border-bottom: 2px solid #6366f1;
    }
    
    /* Radio buttons na sidebar */
    [data-testid="stSidebar"] .stRadio > label {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(139, 92, 246, 0.05));
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 8px;
        border: 1px solid transparent;
        transition: all 0.3s ease;
    }
    
    [data-testid="stSidebar"] .stRadio > label:hover {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15));
        border-color: #6366f1;
        transform: translateX(4px);
    }
    
    [data-testid="stSidebar"] .stRadio > label > div[data-testid="stMarkdownContainer"] {
        font-size: 1rem;
        font-weight: 500;
    }
    
    /* Estilo para as tabs (usadas internamente no poi_manager) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background: linear-gradient(135deg, #1a1d27, #232733);
        padding: 12px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 12px 28px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.95rem;
        color: #9ca3af;
        transition: all 0.3s ease;
        border: 1px solid transparent;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        color: #e5e7eb;
        background: rgba(99, 102, 241, 0.1);
        border-color: #6366f1;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        border-color: #6366f1;
    }
    
    /* Header principal */
    .main-header {
        text-align: center;
        padding: 2rem 0 1rem 0;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.1));
        border-radius: 12px;
        margin-bottom: 2rem;
        border: 1px solid rgba(99, 102, 241, 0.2);
    }
    
    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    .main-subtitle {
        color: #9ca3af;
        font-size: 1rem;
        font-weight: 400;
    }
    
    /* Info box na sidebar */
    .sidebar-info {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.1));
        border-left: 3px solid #6366f1;
        border-radius: 0 8px 8px 0;
        padding: 12px;
        margin: 16px 0;
        font-size: 0.85rem;
        color: #9ca3af;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# Sidebar - Menu de Navegação
# ==========================================
with st.sidebar:
    st.markdown("# 🏠 Menu")
    
    pagina_selecionada = st.radio(
        "Navegação",
        [
            "🏡 Predição Individual",
            "📦 Predição em Lote",
            "📍 Gerenciador de POIs"
        ],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    st.markdown("""
    <div class="sidebar-info">
        <strong>💡 Dica:</strong><br>
        Use o menu acima para navegar entre os diferentes módulos da plataforma.
    </div>
    """, unsafe_allow_html=True)
    
    # Informações sobre o módulo selecionado
    if pagina_selecionada == "🏡 Predição Individual":
        st.markdown("""
        **Predição Individual**
        
        Análise detalhada de um único imóvel com:
        - Geocoding automático
        - Análise de POIs próximos
        - Cálculo de scores
        - Predição de preço
        """)
    elif pagina_selecionada == "📦 Predição em Lote":
        st.markdown("""
        **Predição em Lote**
        
        Processe múltiplos imóveis:
        - Upload CSV/XLSX
        - Processamento em massa
        - Exportação de resultados
        - Salvamento no banco
        """)
    elif pagina_selecionada == "📍 Gerenciador de POIs":
        st.markdown("""
        **Gerenciador de POIs**
        
        Administre pontos de interesse:
        - Buscar via OSMnx
        - Migrar cache para banco
        - Gerenciar cidades
        - Estatísticas completas
        """)
    
    st.markdown("---")
    
    # Rodapé da sidebar
    st.markdown("""
    <div style="text-align: center; font-size: 0.75rem; color: #6b7280; margin-top: 2rem;">
        <p><strong>Sistema de Precificação</strong></p>
        <p>ML • OSMnx • MLflow</p>
        <p style="margin-top: 0.5rem;">v2.0.0</p>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# Header Principal
# ==========================================
st.markdown("""
<div class="main-header">
    <div class="main-title">🏠 Plataforma de Precificação Imobiliária</div>
    <div class="main-subtitle">Sistema completo de análise e predição de valores de imóveis</div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# Renderizar módulo selecionado
# ==========================================
import importlib.util

if pagina_selecionada == "🏡 Predição Individual":
    try:
        spec = importlib.util.spec_from_file_location(
            "app2_module",
            os.path.join(os.path.dirname(__file__), "streamlit_app", "app2.py")
        )
        app2_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app2_module)
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar módulo de Predição Individual: {str(e)}")
        st.exception(e)

elif pagina_selecionada == "📦 Predição em Lote":
    try:
        spec = importlib.util.spec_from_file_location(
            "batch_app_module",
            os.path.join(os.path.dirname(__file__), "streamlit_app", "batch_app.py")
        )
        batch_app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(batch_app_module)
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar módulo de Predição em Lote: {str(e)}")
        st.exception(e)

elif pagina_selecionada == "📍 Gerenciador de POIs":
    try:
        spec = importlib.util.spec_from_file_location(
            "poi_manager_module",
            os.path.join(os.path.dirname(__file__), "streamlit_app", "poi_manager.py")
        )
        poi_manager_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(poi_manager_module)
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar módulo de Gerenciador de POIs: {str(e)}")
        st.exception(e)

