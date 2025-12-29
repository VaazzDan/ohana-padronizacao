import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
from unidecode import unidecode
import re
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Ohana Soluções Empresariais", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS & ESTILO (Identidade Visual) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:ital,wght@0,200..900;1,200..900&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0');

        html, body, [class*="css"] {
            font-family: 'Source Sans 3', sans-serif !important;
        }

        h1, h2, h3 {
            color: #67bed9 !important;
            font-weight: 700 !important;
        }
        
        .material-symbols-outlined {
            vertical-align: middle;
            font-size: 1.2em;
            color: #67bed9;
        }

        div.stButton > button {
            background-color: #ea5382 !important;
            color: white !important;
            border-radius: 8px !important;
            border: none !important;
            font-weight: 600 !important;
            transition: all 0.3s ease;
        }
        div.stButton > button:hover {
            background-color: #d64570 !important;
            transform: scale(1.02);
        }

        /* Destaque para a coluna de status na tabela */
        td {
            vertical-align: middle !important;
        }

        [data-testid="stSidebar"] { border-right: 1px solid #333; }
        [data-testid="stMetricValue"] { color: #ea5382 !important; }
        [data-testid="stMetricLabel"] { color: #67bed9 !important; }
    </style>
""", unsafe_allow_html=True)

# --- LOGO ---
LOGO_URL = "https://i.ibb.co/67RjdFyj/backgroud-png.png"
st.logo(LOGO_URL, icon_image=LOGO_URL)

# ==============================================================================
# LÓGICA DE NEGÓCIO (BACKEND)
# ==============================================================================

def extrair_id(texto):
    if pd.isna(texto): return None
    texto = str(texto).strip()
    match = re.match(r'^(\d+)', texto)
    if match: return match.group(1)
    return None

def limpar_ruido_direita(texto):
    if pd.isna(texto): return ""
    texto = str(texto)
    texto_limpo = re.sub(r'\s+[\d\.,]+$', '', texto)
    texto_limpo = re.sub(r'\s+[-–]\s*$', '', texto_limpo)
    return texto_limpo.strip()

def limpar_visual_padrao(texto):
    if pd.isna(texto): return ""
    texto = str(texto)
    texto = unidecode(texto) 
    texto = re.sub(r'[^a-zA-Z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def limpar_para_fuzzy(texto):
    return limpar_visual_padrao(texto).lower()

def contar_palavras(texto):
    if not texto: return 0
    return len(texto.split())

def verificar_seguranca_match(nome_origem, nome_alvo, id_origem, id_alvo):
    if id_origem and id_alvo and id_origem == id_alvo: return True
    if id_origem and id_alvo and id_origem != id_alvo: return False
    
    palavras_origem = contar_palavras(nome_origem)
    palavras_alvo = contar_palavras(nome_alvo)
    
    if palavras_origem <= 2 and palavras_alvo > palavras_origem: return False
    return True

@st.cache_data
def processar_coluna_unica(df, col_alvo, corte):
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
    col_status = "Status_Auditoria"
    
    # Aplica o Mapeamento
    df_out[col_nova] = df_out[col_alvo].map(mapa_resultado)
    
    # --- NOVA LÓGICA DE AUDITORIA ---
    # Compara a string original com a nova. Se diferir, marca como ALTERADO.
    df_out[col_status] = df_out.apply(
        lambda row: 'ALTERADO' if str(row[col_alvo]) != str(row[col_nova]) else 'ORIGINAL',
        axis=1
    )
    
    return df_out, col_nova, col_status

@st.cache_data
def processar_duas_colunas(df, col_suja, col_ref, corte):
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
    col_status = "Status_Auditoria"

    df_out[col_nova] = df_out[col_suja].map(mapa_resultado)
    
    # --- NOVA LÓGICA DE AUDITORIA ---
    df_out[col_status] = df_out.apply(
        lambda row: 'ALTERADO' if str(row[col_suja]) != str(row[col_nova]) else 'ORIGINAL',
        axis=1
    )
    
    return df_out, col_nova, col_status

# --- 3. INTERFACE (FRONTEND) ---

st.markdown("""
<h1>
    <span class="material-symbols-outlined">dataset_linked</span> 
    Padronização/De-Para - Ohana
</h1>
<p style='color: #67bed9; font-size: 1.1em;'>Ferramenta de Padronização e Enriquecimento de Dados</p>
<hr style='border: 1px solid #333;'>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("<h3><span class='material-symbols-outlined'>settings</span> Configuração</h3>", unsafe_allow_html=True)
    
    modo = st.radio(
        "Modo de Operação:",
        ("Padronizar (1 Coluna)", 
         "De-Para (2 Colunas)"),
        index=0
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    corte = st.slider("Sensibilidade da IA (%)", 50, 100, 70)
    
    st.info("Regras Ativas: Limpeza de sufixo, ID Soberano, Trava Anti-Homônimo.")

# Upload
uploaded_file = st.file_uploader("Arraste sua planilha aqui", type=["xlsx", "xls", "csv"])

if uploaded_file:
    try:
        df = None
        
        # Leitura Inteligente com Suporte a Abas
        if uploaded_file.name.endswith(('.xlsx', '.xls')):
            excel_file = pd.ExcelFile(uploaded_file)
            sheet_names = excel_file.sheet_names
            
            if len(sheet_names) > 1:
                st.markdown("<h3><span class='material-symbols-outlined'>tab</span> Seleção de Aba</h3>", unsafe_allow_html=True)
                selected_sheet = st.selectbox("Este arquivo possui múltiplas abas. Qual deseja utilizar?", sheet_names)
                df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
                st.markdown(f"<p style='color:#ea5382; font-size:0.9em;'>Trabalhando na aba: <b>{selected_sheet}</b></p>", unsafe_allow_html=True)
                st.markdown("<hr style='border: 1px dashed #333;'>", unsafe_allow_html=True)
            else:
                df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file)

        if df is not None:
            st.markdown("<h3><span class='material-symbols-outlined'>table_chart</span> Seleção de Colunas</h3>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            
            if "1 Coluna" in modo:
                col_alvo = col1.selectbox("Selecione a Coluna para Padronizar:", df.columns)
                texto_botao = "Iniciar Padronização"
            else:
                col_suja = col1.selectbox("Coluna Entrada (Suja):", df.columns, index=0)
                index_ref = 1 if len(df.columns) > 1 else 0
                col_ref = col2.selectbox("Coluna Referência (Oficial):", df.columns, index=index_ref)
                texto_botao = "Iniciar De-Para"

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button(texto_botao, type="primary", use_container_width=True):
                with st.spinner("Processando..."):
                    
                    if "1 Coluna" in modo:
                        # Agora retorna 3 valores: df, nome da coluna nova e nome da coluna de status
                        df_res, col_nova, col_status = processar_coluna_unica(df, col_alvo, corte)
                        col_analise = col_alvo
                    else:
                        df_res, col_nova, col_status = processar_duas_colunas(df, col_suja, col_ref, corte)
                        col_analise = col_suja

                    # --- Resultados ---
                    st.markdown("<h3><span class='material-symbols-outlined'>check_circle</span> Resultados</h3>", unsafe_allow_html=True)
                    
                    # Filtra apenas o que é "ALTERADO" para contar a taxa
                    qtd_total = len(df)
                    qtd_mudou = len(df_res[df_res[col_status] == 'ALTERADO'])
                    taxa = (qtd_mudou / qtd_total) * 100 if qtd_total > 0 else 0
                    
                    m1, m2, m3 = st.columns(3)
                    m1.markdown(f"**Linhas Totais**<br><span style='font-size: 2em; color:#ea5382'>{qtd_total}</span>", unsafe_allow_html=True)
                    m2.markdown(f"**Alteradas**<br><span style='font-size: 2em; color:#ea5382'>{qtd_mudou}</span>", unsafe_allow_html=True)
                    m3.markdown(f"**Taxa**<br><span style='font-size: 2em; color:#ea5382'>{taxa:.1f}%</span>", unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Mostra a tabela apenas com as colunas relevantes para o usuário entender o que aconteceu
                    # Mostramos: Coluna Original | Coluna Nova | Status
                    if qtd_mudou > 0:
                        df_visual = df_res[df_res[col_status] == 'ALTERADO'][[col_analise, col_nova, col_status]].head(100)
                        st.dataframe(df_visual, use_container_width=True, height=400)
                    else:
                        st.warning("Nenhuma alteração foi realizada. Todos os dados já estavam no padrão ou não houve match seguro.")
                    
                    # Download
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_res.to_excel(writer, index=False)
                    data = output.getvalue()
                    
                    st.download_button(
                        label="Baixar Resultado (Excel)",
                        data=data,
                        file_name="resultado_padronizado_auditado.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

    except Exception as e:
        st.error(f"Erro ao processar: {e}")

elif not uploaded_file:
    st.markdown("""
    <div style='text-align: center; padding: 50px; opacity: 0.6;'>
        <span class="material-symbols-outlined" style="font-size: 4em; color: #67bed9;">cloud_upload</span>
        <h3 style="color: #67bed9;">Aguardando Arquivo</h3>
        <p>Faça o upload da sua planilha acima para começar.</p>
    </div>
    """, unsafe_allow_html=True)