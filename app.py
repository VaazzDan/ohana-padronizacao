import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
from unidecode import unidecode
import re
import io

# --- CONFIGURAÇÃO INICIAL E VISUAL ---
st.set_page_config(
    page_title="Ohana Soluções Empresariais", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ADICIONANDO A LOGO DA EMPRESA ---
# A logo aparecerá no topo da barra lateral esquerda.
LOGO_URL = "https://i.ibb.co/67RjdFyj/backgroud-png.png"
st.logo(LOGO_URL, icon_image=LOGO_URL)

# --- INJEÇÃO DE CSS PERSONALIZADO (OPCIONAL PARA REFINAMENTO) ---
# Este bloco ajusta pequenos detalhes visuais para ficar mais elegante
st.markdown("""
    <style>
        /* Ajusta o título principal para ficar mais destacado */
        h1 {
            color: #00A3E0; /* Usando a mesma cor primária do tema */
            font-weight: 700;
        }
        /* Deixa os botões primários um pouco mais robustos */
        div.stButton > button:first-child {
            font-weight: bold;
            border-radius: 8px;
        }
        /* Estiliza as caixas de métricas */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem;
            color: #00A3E0;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# DAQUI PARA BAIXO É O MESMO CÓDIGO LÓGICO QUE JÁ DEFINIMOS
# ==============================================================================

# --- 1. FUNÇÕES DE LIMPEZA E REGRAS DE NEGÓCIO ---

def extrair_id(texto):
    """Extrai ID numérico do início da string (ex: '123 - Nome')."""
    if pd.isna(texto): return None
    texto = str(texto).strip()
    match = re.match(r'^(\d+)', texto)
    if match: return match.group(1)
    return None

def limpar_ruido_direita(texto):
    """Remove números, datas e valores soltos no final da string."""
    if pd.isna(texto): return ""
    texto = str(texto)
    texto_limpo = re.sub(r'\s+[\d\.,]+$', '', texto)
    texto_limpo = re.sub(r'\s+[-–]\s*$', '', texto_limpo)
    return texto_limpo.strip()

def limpar_visual_padrao(texto):
    """Aplica a padronização visual exigida: Remove acentos e especiais."""
    if pd.isna(texto): return ""
    texto = str(texto)
    texto = unidecode(texto) 
    texto = re.sub(r'[^a-zA-Z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def limpar_para_fuzzy(texto):
    """Limpeza agressiva apenas para o cálculo matemático."""
    return limpar_visual_padrao(texto).lower()

def contar_palavras(texto):
    if not texto: return 0
    return len(texto.split())

def verificar_seguranca_match(nome_origem, nome_alvo, id_origem, id_alvo):
    """Regra 'Maria Clara' e ID Soberano."""
    if id_origem and id_alvo and id_origem == id_alvo:
        return True
    if id_origem and id_alvo and id_origem != id_alvo:
        return False
    
    palavras_origem = contar_palavras(nome_origem)
    palavras_alvo = contar_palavras(nome_alvo)
    
    if palavras_origem <= 2 and palavras_alvo > palavras_origem:
        return False
        
    return True

# --- 2. MOTORES DE PROCESSAMENTO ---

@st.cache_data
def processar_coluna_unica(df, col_alvo, corte):
    """MODO 1: Agrupamento interno (Deduplicação)"""
    valores_unicos = df[col_alvo].value_counts().index.tolist()
    mapa_resultado = {}
    ids_registrados = {}     
    padroes_registrados = [] 
    
    progresso = st.progress(0)
    total = len(valores_unicos)
    
    for i, item_original in enumerate(valores_unicos):
        if i % (max(1, total // 20)) == 0: progresso.progress(i/total)
        
        id_item = extrair_id(item_original)
        nome_sem_ruido = limpar_ruido_direita(item_original)
        nome_visual_limpo = limpar_visual_padrao(nome_sem_ruido)
        nome_fuzzy = limpar_para_fuzzy(nome_visual_limpo)
        
        match_encontrado = None

        if id_item and id_item in ids_registrados:
            match_encontrado = ids_registrados[id_item]
        
        if not match_encontrado and padroes_registrados:
            candidatos_fuzzy = [p[0] for p in padroes_registrados]
            melhor_match = process.extractOne(nome_fuzzy, candidatos_fuzzy, scorer=fuzz.WRatio, score_cutoff=corte)
            
            if melhor_match:
                index = melhor_match[2]
                padrao_tupla = padroes_registrados[index]
                candidato_visual = padrao_tupla[1]
                id_candidato = extrair_id(candidato_visual)
                
                if verificar_seguranca_match(nome_visual_limpo, candidato_visual, id_item, id_candidato):
                    match_encontrado = candidato_visual

        if match_encontrado:
            mapa_resultado[item_original] = match_encontrado
        else:
            novo_padrao = nome_visual_limpo
            padroes_registrados.append((nome_fuzzy, novo_padrao))
            if id_item: ids_registrados[id_item] = novo_padrao
            mapa_resultado[item_original] = novo_padrao

    progresso.empty()
    df_out = df.copy()
    col_nova = f"{col_alvo}_Padronizado"
    df_out[col_nova] = df_out[col_alvo].map(mapa_resultado)
    return df_out, col_nova

@st.cache_data
def processar_duas_colunas(df, col_suja, col_ref, corte):
    """MODO 2: Comparação com Referência (De-Para)"""
    ref_unicos = df[col_ref].dropna().unique().tolist()
    banco_ref = []
    mapa_ref_id = {}
    
    for r in ref_unicos:
        ref_visual = limpar_visual_padrao(r)
        ref_fuzzy = limpar_para_fuzzy(ref_visual)
        ref_id = extrair_id(r)
        banco_ref.append((ref_fuzzy, ref_visual, ref_id))
        if ref_id: mapa_ref_id[ref_id] = ref_visual

    mapa_resultado = {}
    lista_suja = df[col_suja].unique().tolist()
    
    progresso = st.progress(0)
    total = len(lista_suja)
    
    for i, item_sujo in enumerate(lista_suja):
        if i % (max(1, total // 20)) == 0: progresso.progress(i/total)
        
        id_sujo = extrair_id(item_sujo)
        nome_sem_ruido = limpar_ruido_direita(item_sujo)
        nome_visual_limpo = limpar_visual_padrao(nome_sem_ruido)
        nome_fuzzy = limpar_para_fuzzy(nome_visual_limpo)
        
        match_final = None

        if id_sujo and id_sujo in mapa_ref_id:
            match_final = mapa_ref_id[id_sujo]
            
        if not match_final:
            candidatos_fuzzy = [b[0] for b in banco_ref]
            melhor = process.extractOne(nome_fuzzy, candidatos_fuzzy, scorer=fuzz.WRatio, score_cutoff=corte)
            
            if melhor:
                idx = melhor[2]
                candidato_ref_visual = banco_ref[idx][1]
                candidato_ref_id = banco_ref[idx][2]
                
                if verificar_seguranca_match(nome_visual_limpo, candidato_ref_visual, id_sujo, candidato_ref_id):
                    match_final = candidato_ref_visual
        
        if match_final:
            mapa_resultado[item_sujo] = match_final
        else:
            mapa_resultado[item_sujo] = nome_visual_limpo

    progresso.empty()
    df_out = df.copy()
    col_nova = "DePara_Resultado"
    df_out[col_nova] = df_out[col_suja].map(mapa_resultado)
    return df_out, col_nova

# --- 3. INTERFACE (STREAMLIT) ---

st.title("🛡️Padronizador/De-Para - Ohana")
st.markdown("---")

# Sidebar com opções
with st.sidebar:
    st.header("Configurações da Operação")
    modo = st.radio(
        "Modo de Operação:",
        ("Modo 1: Padronizar uma Coluna (Deduplicação)", 
         "Modo 2: Comparar com Referência (De-Para)"),
        index=0
    )
    
    st.markdown("---")
    corte = st.slider("Sensibilidade da IA (%)", 50, 100, 70, help="Quanto maior, mais rigoroso o agrupamento.")
    st.info("""
    **Regras de Negócio Ativas:**
    1. **Limpeza:** Remove acentos e caracteres especiais.
    2. **ID Soberano:** IDs iguais forçam o agrupamento.
    3. **Trava de Segurança:** Nomes curtos não são agrupados com nomes longos sem ID.
    """)

arquivo = st.file_uploader("📂 Arraste sua planilha aqui (Excel/CSV)", type=["xlsx", "xls", "csv"])

if arquivo:
    try:
        if arquivo.name.endswith('.csv'):
            df = pd.read_csv(arquivo)
        else:
            df = pd.read_excel(arquivo)
        
        st.write("### Seleção de Dados")
        col1, col2 = st.columns(2)
        
        if "Modo 1" in modo:
            col_alvo = col1.selectbox("Selecione a Coluna para Padronizar:", df.columns)
            botao_texto = "Executar Padronização (Modo 1)"
                    
        else: # Modo 2
            col_suja = col1.selectbox("Coluna 'Suja' (Entrada):", df.columns, index=0)
            col_ref = col2.selectbox("Coluna 'Referência' (Oficial):", df.columns, index=1 if len(df.columns)>1 else 0)
            botao_texto = "Executar De-Para (Modo 2)"

        st.markdown("<br>", unsafe_allow_html=True) # Espaço extra

        if st.button(botao_texto, type="primary", use_container_width=True):
            with st.spinner("Processando dados e aplicando regras de negócio..."):
                
                if "Modo 1" in modo:
                    df_res, col_nova = processar_coluna_unica(df, col_alvo, corte)
                    col_analise = col_alvo
                else:
                    df_res, col_nova = processar_duas_colunas(df, col_suja, col_ref, corte)
                    col_analise = col_suja

                # --- RESULTADOS ---
                st.success("Processamento Finalizado com Sucesso!")
                
                mask_mudou = df_res[col_analise] != df_res[col_nova]
                df_mudou = df_res[mask_mudou][[col_analise, col_nova]].drop_duplicates()
                
                qtd_total = len(df)
                qtd_mudou = len(df_res[mask_mudou])
                taxa = (qtd_mudou / qtd_total) * 100 if qtd_total > 0 else 0
                
                # Métricas estilizadas pelo CSS
                m1, m2, m3 = st.columns(3)
                m1.metric("Linhas Totais", qtd_total)
                m2.metric("Linhas Alteradas", qtd_mudou)
                m3.metric("Taxa de Atuação", f"{taxa:.1f}%")
                
                st.subheader("🔎 Verificação das Alterações Realizadas")
                if not df_mudou.empty:
                    st.dataframe(df_mudou, use_container_width=True, height=400)
                else:
                    st.warning("Nenhuma alteração significativa foi necessária. Os dados foram apenas limpos.")
                
                # Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_res.to_excel(writer, index=False)
                data = output.getvalue()
                
                st.download_button(
                    label="📥 Baixar Planilha Pronta (Excel)",
                    data=data,
                    file_name="resultado_padronizado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True
                )

    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
elif not arquivo:
    # Tela inicial de boas-vindas quando não há arquivo
    st.markdown("""
    <div style='text-align: center; padding: 50px; opacity: 0.7;'>
        <h2>Aguardando Arquivo...</h2>
        <p>Faça o upload de uma planilha acima para começar o tratamento de dados.</p>
    </div>
    """, unsafe_allow_html=True)