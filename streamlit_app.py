"""
🤖 AGENTE RAG - NETPROJECT
Sistema Inteligente com Arquitetura RAG Completa
Baseado em: Rev_F_Projeto_Aplicado_RAG_COMPLETO.ipynb

Desenvolvido por: Daniel Bittencourt
TCC Pós-Graduação em IA e Big Data
"""

import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# ============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================================

st.set_page_config(
    page_title="Agente RAG - NetProject",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CSS CUSTOMIZADO
# ============================================================================

st.markdown("""
<style>
    /* Gradiente de fundo */
    .main {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Cards brancos */
    .stApp {
        background: white;
        border-radius: 20px;
        padding: 20px;
        margin: 10px;
    }
    
    /* Títulos */
    h1 {
        color: #667eea;
        text-align: center;
        font-size: 2.5em;
        margin-bottom: 10px;
    }
    
    h2 {
        color: #764ba2;
        border-bottom: 3px solid #667eea;
        padding-bottom: 10px;
    }
    
    h3 {
        color: #667eea;
    }
    
    /* Métricas */
    [data-testid="stMetricValue"] {
        font-size: 2em;
        color: #667eea;
        font-weight: bold;
    }
    
    /* Botões */
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 10px 20px;
        font-weight: bold;
        width: 100%;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    
    /* Mensagens do chat */
    .user-message {
        background: linear-gradient(135deg, #e3f2fd 0%, #d1e8f8 100%);
        border-left: 4px solid #2196f3;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    
    .assistant-message {
        background: linear-gradient(135deg, #f3e5f5 0%, #e8d5f0 100%);
        border-left: 4px solid #9c27b0;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    
    /* Dataframes */
    .dataframe {
        border-radius: 10px;
        overflow: hidden;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# FUNÇÕES DE CONEXÃO E CACHE
# ============================================================================

@st.cache_resource
def conectar_mysql():
    """Conecta ao banco MySQL (com cache para reutilizar conexão)"""
    try:
        conn = mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            port=st.secrets["mysql"]["port"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"]
        )
        return conn
    except Exception as e:
        st.error(f"❌ Erro ao conectar: {str(e)}")
        return None

@st.cache_data(ttl=300)  # Cache por 5 minutos
def executar_query(_conn, query):
    """Executa query e retorna DataFrame (com cache)"""
    try:
        df = pd.read_sql(query, _conn)
        return df
    except Exception as e:
        st.error(f"❌ Erro na query: {str(e)}")
        return None

# ============================================================================
# CAMADA 1: INTENÇÕES (do notebook)
# ============================================================================

INTENCOES = {
    'PROJETOS_ATRASADOS': {
        'palavras': ['atrasado', 'atrasados', 'atraso', 'pendente', 'vencido'],
        'peso': 3
    },
    'CONSULTA_PROJETO': {
        'palavras': ['projeto', 'status', 'situação', 'andamento'],
        'peso': 1
    },
    'CONSULTA_RECEITA': {
        'palavras': ['receita', 'faturamento', 'valor', 'quanto'],
        'peso': 2
    },
    'CONSULTA_FATURA': {
        'palavras': ['fatura', 'pagamento', 'pago', 'programado'],
        'peso': 2
    },
    'CONSULTA_ALOCACAO': {
        'palavras': ['alocação', 'equipe', 'time', 'quem está', 'pessoas', 'alocado', 'trabalha'],
        'peso': 2
    }
}

# ============================================================================
# CAMADA 2: INTERPRETAÇÃO NLP (do notebook)
# ============================================================================

def detectar_intencao(pergunta):
    """Detecta a intenção da pergunta"""
    pergunta_lower = pergunta.lower()
    scores = {}
    
    for intencao, config in INTENCOES.items():
        score = 0
        for palavra in config['palavras']:
            if palavra in pergunta_lower:
                score += config['peso']
        scores[intencao] = score
    
    if max(scores.values()) == 0:
        return None
    
    return max(scores, key=scores.get)

def extrair_codigo_projeto(pergunta):
    """Extrai código do projeto da pergunta"""
    import re
    match = re.search(r'\b(\d{4,6})\b', pergunta)
    return int(match.group(1)) if match else None

def interpretar_pergunta(pergunta):
    """Interpreta a pergunta completa"""
    return {
        'intencao': detectar_intencao(pergunta),
        'cod_projeto': extrair_codigo_projeto(pergunta),
        'pergunta_original': pergunta
    }

# ============================================================================
# CAMADA 3: EXECUÇÃO (RETRIEVAL - do notebook)
# ============================================================================

def get_projetos_atrasados(conn):
    """Busca projetos atrasados REAIS do banco"""
    query = """
    SELECT 
        p.cod_projeto,
        p.nom_projeto,
        u.nom_usuario as responsavel,
        p.dth_prevista as data_prevista,
        DATEDIFF(NOW(), p.dth_prevista) as dias_atraso,
        COALESCE(SUM(r.total_valor_bruto), 0) as receita_total
    FROM projeto p
    LEFT JOIN usuario u ON p.cod_responsavel = u.cod_usuario
    LEFT JOIN receita r ON p.cod_projeto = r.cod_projeto
    WHERE p.dth_prevista < NOW()
      AND p.flg_status = 1
    GROUP BY p.cod_projeto, p.nom_projeto, u.nom_usuario, p.dth_prevista
    HAVING dias_atraso > 0
    ORDER BY dias_atraso DESC
    LIMIT 10
    """
    return executar_query(conn, query)

def get_projeto_detalhes(conn, cod_projeto):
    """Busca detalhes de um projeto específico"""
    query = f"""
    SELECT 
        p.cod_projeto,
        p.nom_projeto,
        u.nom_usuario as responsavel,
        p.dth_inicio,
        p.dth_prevista,
        p.flg_status,
        DATEDIFF(NOW(), p.dth_prevista) as dias_atraso,
        COALESCE(SUM(r.total_valor_bruto), 0) as receita_total,
        COALESCE(SUM(rp.vlr_bruto), 0) as receita_faturada
    FROM projeto p
    LEFT JOIN usuario u ON p.cod_responsavel = u.cod_usuario
    LEFT JOIN receita r ON p.cod_projeto = r.cod_projeto
    LEFT JOIN receita_pagamento rp ON r.cod_receita = rp.cod_receita 
        AND rp.flg_status_fatura IN ('Pago', 'Programado')
    WHERE p.cod_projeto = {cod_projeto}
    GROUP BY p.cod_projeto, p.nom_projeto, u.nom_usuario, p.dth_inicio, p.dth_prevista, p.flg_status
    """
    return executar_query(conn, query)

def get_receita_total(conn):
    """Busca receita total de todos os projetos"""
    query = """
    SELECT 
        COUNT(DISTINCT p.cod_projeto) as total_projetos,
        COALESCE(SUM(r.total_valor_bruto), 0) as receita_total,
        COALESCE(AVG(r.total_valor_bruto), 0) as receita_media
    FROM projeto p
    LEFT JOIN receita r ON p.cod_projeto = r.cod_projeto
    WHERE p.flg_status = 1
    """
    return executar_query(conn, query)

def get_receita_projeto(conn, cod_projeto):
    """Busca receita de um projeto específico"""
    query = f"""
    SELECT 
        p.cod_projeto,
        p.nom_projeto,
        COALESCE(SUM(r.total_valor_bruto), 0) as receita_total,
        COALESCE(SUM(CASE WHEN rp.flg_status_fatura = 'Pago' THEN rp.vlr_bruto ELSE 0 END), 0) as receita_paga,
        COALESCE(SUM(CASE WHEN rp.flg_status_fatura = 'Programado' THEN rp.vlr_bruto ELSE 0 END), 0) as receita_programada
    FROM projeto p
    LEFT JOIN receita r ON p.cod_projeto = r.cod_projeto
    LEFT JOIN receita_pagamento rp ON r.cod_receita = rp.cod_receita
    WHERE p.cod_projeto = {cod_projeto}
    GROUP BY p.cod_projeto, p.nom_projeto
    """
    return executar_query(conn, query)

def get_alocacoes_projeto(conn, cod_projeto):
    """Busca alocações de um projeto específico"""
    query = f"""
    SELECT 
        u.nom_usuario,
        SUM(ra.num_horas_aloc) as horas_alocadas,
        SUM(ra.num_horas_trab) as horas_trabalhadas
    FROM DWDT_RECURSO_ALOCACAO ra
    JOIN usuario u ON ra.cod_usuario = u.cod_usuario
    WHERE ra.cod_projeto = {cod_projeto}
    GROUP BY u.nom_usuario
    ORDER BY horas_alocadas DESC
    """
    return executar_query(conn, query)

def get_faturas_projeto(conn, cod_projeto):
    """Busca faturas de um projeto"""
    query = f"""
    SELECT 
        rp.dsc_receita_pagamento as descricao,
        rp.vlr_bruto as valor,
        rp.dth_faturamento as data_faturamento,
        rp.flg_status_fatura as status
    FROM receita_pagamento rp
    JOIN receita r ON rp.cod_receita = r.cod_receita
    WHERE r.cod_projeto = {cod_projeto}
    ORDER BY rp.dth_faturamento DESC
    """
    return executar_query(conn, query)

def executar_consulta(conn, interpretacao):
    """Executa consulta baseada na interpretação"""
    intencao = interpretacao['intencao']
    cod_projeto = interpretacao['cod_projeto']
    
    if intencao == 'PROJETOS_ATRASADOS':
        return {'sucesso': True, 'dados': get_projetos_atrasados(conn)}
    
    elif intencao == 'CONSULTA_PROJETO':
        if not cod_projeto:
            return {'sucesso': False, 'erro': 'Código do projeto não especificado'}
        df = get_projeto_detalhes(conn, cod_projeto)
        return {'sucesso': True, 'dados': df} if df is not None and len(df) > 0 else {'sucesso': False, 'erro': 'Projeto não encontrado'}
    
    elif intencao == 'CONSULTA_RECEITA':
        if cod_projeto:
            df = get_receita_projeto(conn, cod_projeto)
            return {'sucesso': True, 'dados': df} if df is not None and len(df) > 0 else {'sucesso': False, 'erro': 'Projeto não encontrado'}
        else:
            return {'sucesso': True, 'dados': get_receita_total(conn)}
    
    elif intencao == 'CONSULTA_ALOCACAO':
        if not cod_projeto:
            return {'sucesso': False, 'erro': 'Código do projeto não especificado'}
        df = get_alocacoes_projeto(conn, cod_projeto)
        return {'sucesso': True, 'dados': df} if df is not None and len(df) > 0 else {'sucesso': False, 'erro': 'Sem alocações'}
    
    elif intencao == 'CONSULTA_FATURA':
        if not cod_projeto:
            return {'sucesso': False, 'erro': 'Código do projeto não especificado'}
        df = get_faturas_projeto(conn, cod_projeto)
        return {'sucesso': True, 'dados': df} if df is not None and len(df) > 0 else {'sucesso': False, 'erro': 'Sem faturas'}
    
    return {'sucesso': False, 'erro': 'Intenção não reconhecida'}

# ============================================================================
# CAMADA 4: GERAÇÃO (GENERATION - do notebook)
# ============================================================================

def gerar_resposta(interpretacao, resultado):
    """Gera resposta formatada"""
    if not resultado['sucesso']:
        st.error(f"⚠️ {resultado['erro']}")
        return
    
    intencao = interpretacao['intencao']
    dados = resultado['dados']
    
    if intencao == 'PROJETOS_ATRASADOS':
        st.subheader("📊 Projetos Atrasados")
        st.write(f"Encontrados **{len(dados)}** projetos atrasados:")
        
        for _, proj in dados.iterrows():
            with st.expander(f"🔴 {proj['nom_projeto']} - {proj['dias_atraso']} dias de atraso"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Código", f"{proj['cod_projeto']}")
                col2.metric("Dias de Atraso", f"{proj['dias_atraso']}")
                col3.metric("Receita", f"R$ {proj['receita_total']:,.2f}")
                st.write(f"**Responsável:** {proj['responsavel']}")
                st.write(f"**Previsão:** {proj['data_prevista']}")
    
    elif intencao == 'CONSULTA_PROJETO':
        proj = dados.iloc[0]
        st.subheader(f"📋 Projeto {proj['cod_projeto']}: {proj['nom_projeto']}")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Código", proj['cod_projeto'])
        col2.metric("Dias Atraso", proj['dias_atraso'] if proj['dias_atraso'] > 0 else 0)
        col3.metric("Receita Total", f"R$ {proj['receita_total']:,.2f}")
        col4.metric("Faturado", f"R$ {proj['receita_faturada']:,.2f}")
        
        st.write(f"**Responsável:** {proj['responsavel']}")
        st.write(f"**Início:** {proj['dth_inicio']}")
        st.write(f"**Previsão:** {proj['dth_prevista']}")
        
        if proj['dias_atraso'] > 0:
            st.warning(f"⚠️ Projeto atrasado em {proj['dias_atraso']} dias")
        else:
            st.success("✅ Projeto no prazo")
    
    elif intencao == 'CONSULTA_RECEITA':
        if 'receita_total' in dados.columns and 'total_projetos' in dados.columns:
            # Receita geral
            st.subheader("💰 Receita Total - Todos os Projetos")
            rec = dados.iloc[0]
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Receita Total", f"R$ {rec['receita_total']:,.2f}")
            col2.metric("Total de Projetos", f"{rec['total_projetos']}")
            col3.metric("Média por Projeto", f"R$ {rec['receita_media']:,.2f}")
        else:
            # Receita de projeto específico
            proj = dados.iloc[0]
            st.subheader(f"💰 Receita do Projeto {proj['cod_projeto']}")
            st.write(f"**Projeto:** {proj['nom_projeto']}")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total", f"R$ {proj['receita_total']:,.2f}")
            col2.metric("Pago", f"R$ {proj['receita_paga']:,.2f}")
            col3.metric("Programado", f"R$ {proj['receita_programada']:,.2f}")
            
            # Gráfico
            fig = go.Figure(data=[go.Pie(
                labels=['Pago', 'Programado', 'Pendente'],
                values=[
                    proj['receita_paga'],
                    proj['receita_programada'],
                    max(0, proj['receita_total'] - proj['receita_paga'] - proj['receita_programada'])
                ],
                marker_colors=['#28a745', '#ffc107', '#dc3545']
            )])
            fig.update_layout(title="Distribuição da Receita")
            st.plotly_chart(fig, use_container_width=True)
    
    elif intencao == 'CONSULTA_ALOCACAO':
        st.subheader(f"👥 Equipe Alocada - Projeto {interpretacao['cod_projeto']}")
        st.write(f"**{len(dados)}** pessoas alocadas:")
        
        # Tabela
        st.dataframe(dados, use_container_width=True)
        
        # Gráfico
        fig = px.bar(dados, x='nom_usuario', y=['horas_alocadas', 'horas_trabalhadas'],
                     title="Horas por Pessoa",
                     labels={'nom_usuario': 'Pessoa', 'value': 'Horas'},
                     barmode='group')
        st.plotly_chart(fig, use_container_width=True)
    
    elif intencao == 'CONSULTA_FATURA':
        st.subheader(f"🧾 Faturas - Projeto {interpretacao['cod_projeto']}")
        st.write(f"**{len(dados)}** faturas encontradas:")
        
        # Agrupar por status
        por_status = dados.groupby('status')['valor'].agg(['count', 'sum']).reset_index()
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Resumo por Status:**")
            st.dataframe(por_status, use_container_width=True)
        
        with col2:
            fig = px.pie(por_status, values='sum', names='status', 
                        title='Valor Total por Status')
            st.plotly_chart(fig, use_container_width=True)
        
        # Lista completa
        with st.expander("Ver todas as faturas"):
            st.dataframe(dados, use_container_width=True)

# ============================================================================
# INTERFACE PRINCIPAL
# ============================================================================

def main():
    # Header
    st.markdown("<h1>🤖 Agente RAG - NetProject</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666; font-size: 1.2em;'>Sistema Inteligente com Arquitetura RAG | Dados REAIS do MySQL</p>", unsafe_allow_html=True)
    
    # Badges
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown("**📊 RAG Architecture**")
    col2.markdown("**🧠 NLP Processing**")
    col3.markdown("**🗄️ MySQL Backend**")
    col4.markdown("**🎓 TCC Pós-Graduação**")
    
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.markdown("### 🔐 Conexão")
        
        # Tentar conectar
        conn = conectar_mysql()
        
        if conn:
            st.success("✅ Conectado ao MySQL")
            
            # Estatísticas gerais
            st.markdown("### 📊 Estatísticas")
            
            try:
                df_stats = executar_query(conn, """
                    SELECT 
                        COUNT(DISTINCT p.cod_projeto) as projetos,
                        COUNT(DISTINCT u.cod_usuario) as usuarios,
                        COALESCE(SUM(r.total_valor_bruto), 0) as receita
                    FROM projeto p
                    LEFT JOIN usuario u ON p.cod_responsavel = u.cod_usuario
                    LEFT JOIN receita r ON p.cod_projeto = r.cod_projeto
                    WHERE p.flg_status = 1
                """)
                
                if df_stats is not None and len(df_stats) > 0:
                    stats = df_stats.iloc[0]
                    st.metric("Projetos Ativos", f"{stats['projetos']}")
                    st.metric("Usuários", f"{stats['usuarios']}")
                    st.metric("Receita Total", f"R$ {stats['receita']:,.2f}")
            except:
                pass
            
            st.markdown("---")
            st.markdown("### ℹ️ Sobre")
            st.markdown("""
            Este sistema utiliza:
            - **RAG Architecture**
            - **NLP** para intenções
            - **MySQL** real
            - **Streamlit** web
            
            Baseado no notebook:
            `Rev_F_Projeto_Aplicado_RAG_COMPLETO.ipynb`
            """)
            
        else:
            st.error("❌ Não conectado")
            st.info("Configure as credenciais MySQL em `.streamlit/secrets.toml`")
    
    # Área principal
    if conn:
        # Tabs
        tab1, tab2 = st.tabs(["💬 Chat RAG", "📊 Dashboards"])
        
        with tab1:
            st.subheader("Faça perguntas sobre os projetos")
            
            # Exemplos
            st.markdown("**💡 Exemplos de perguntas:**")
            col1, col2, col3 = st.columns(3)
            
            if col1.button("📊 Projetos Atrasados"):
                st.session_state.pergunta = "Quais projetos estão atrasados?"
            if col2.button("💰 Receita Total"):
                st.session_state.pergunta = "Qual a receita total?"
            if col3.button("📋 Status Projeto"):
                st.session_state.pergunta = "Status do projeto 34749"
            
            # Input
            pergunta = st.text_input(
                "Digite sua pergunta:",
                value=st.session_state.get('pergunta', ''),
                placeholder="Ex: Quais projetos estão atrasados?"
            )
            
            if st.button("🚀 Enviar", use_container_width=True):
                if pergunta:
                    with st.spinner("🤖 Processando..."):
                        # Fluxo RAG completo
                        interpretacao = interpretar_pergunta(pergunta)
                        
                        if interpretacao['intencao']:
                            st.info(f"🧠 **Intenção detectada:** {interpretacao['intencao']}")
                            
                            resultado = executar_consulta(conn, interpretacao)
                            gerar_resposta(interpretacao, resultado)
                        else:
                            st.warning("🤔 Não consegui entender a pergunta. Tente reformular.")
                else:
                    st.warning("⚠️ Digite uma pergunta!")
        
        with tab2:
            st.subheader("📊 Dashboards Gerais")
            
            # Dashboard de projetos atrasados
            df_atrasados = get_projetos_atrasados(conn)
            if df_atrasados is not None and len(df_atrasados) > 0:
                st.markdown("### 🔴 Top 10 Projetos Mais Atrasados")
                
                fig = px.bar(df_atrasados, 
                            x='nom_projeto', 
                            y='dias_atraso',
                            title='Projetos por Dias de Atraso',
                            labels={'nom_projeto': 'Projeto', 'dias_atraso': 'Dias de Atraso'},
                            color='dias_atraso',
                            color_continuous_scale='Reds')
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            
            # Dashboard de receitas
            df_receita = get_receita_total(conn)
            if df_receita is not None and len(df_receita) > 0:
                st.markdown("### 💰 Visão Geral de Receitas")
                
                col1, col2, col3 = st.columns(3)
                rec = df_receita.iloc[0]
                col1.metric("Total de Projetos", f"{rec['total_projetos']}")
                col2.metric("Receita Total", f"R$ {rec['receita_total']:,.2f}")
                col3.metric("Média por Projeto", f"R$ {rec['receita_media']:,.2f}")
    
    else:
        st.error("❌ Não foi possível conectar ao banco de dados")
        st.info("Verifique as credenciais em `.streamlit/secrets.toml`")

# ============================================================================
# EXECUTAR
# ============================================================================

if __name__ == "__main__":
    # Inicializar session state
    if 'pergunta' not in st.session_state:
        st.session_state.pergunta = ''
    
    main()
