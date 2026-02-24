import streamlit as st
import sqlite3
import pandas as pd
import io

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('bel_global.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS modelos (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)')
    
    # Substituímos 'excentricidade' pelas 4 posições do prato
    c.execute('''CREATE TABLE IF NOT EXISTS producao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  lote TEXT, di TEXT, modelo TEXT, cliente TEXT,
                  serial_china TEXT UNIQUE, serial_brasil TEXT, 
                  pedido TEXT, valor_antes TEXT, valor_depois TEXT, 
                  exc_se TEXT, exc_sd TEXT, exc_ie TEXT, exc_id TEXT, 
                  carga_maxima TEXT, zero TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- INTERFACE ---
st.set_page_config(page_title="Bel Traceability", layout="wide")

def color_status(val):
    if val == 'Disponível': return 'color: #0000FF; font-weight: bold'
    if val == 'Finalizado': return 'color: #008000; font-weight: bold'
    return 'color: #FFA500; font-weight: bold'

st.sidebar.title("🌐 Sistema Global Bel")
unidade = st.sidebar.selectbox("Selecione a Unidade", ["Brasil", "China (Factory)"], index=None)

if unidade == "Brasil":
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Navegação Brasil", [
        "Consulta", 
        "1. Recebimento (Estoque)", 
        "2. Bancada de Aferição", 
        "Configurações"
    ])

    # --- ABA: CONFIGURAÇÕES ---
    if menu == "Configurações":
        st.header("⚙️ Configurações de Cadastro")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Cadastrar Novo Modelo")
            with st.form("form_modelo", clear_on_submit=True):
                novo_modelo = st.text_input("Nome do Modelo").strip()
                if st.form_submit_button("Salvar Modelo") and novo_modelo:
                    try:
                        conn = sqlite3.connect('bel_global.db')
                        conn.execute("INSERT INTO modelos (nome) VALUES (?)", (novo_modelo,))
                        conn.commit()
                        st.success(f"Modelo '{novo_modelo}' registrado!")
                    except: st.error("Modelo já existe!")
                    finally: conn.close()
        with col2:
            st.subheader("Cadastrar Novo Cliente")
            with st.form("form_cliente", clear_on_submit=True):
                novo_cliente = st.text_input("Nome do Cliente").strip()
                if st.form_submit_button("Salvar Cliente") and novo_cliente:
                    try:
                        conn = sqlite3.connect('bel_global.db')
                        conn.execute("INSERT INTO clientes (nome) VALUES (?)", (novo_cliente,))
                        conn.commit()
                        st.success(f"Cliente '{novo_cliente}' registrado!")
                    except: st.error("Cliente já existe!")
                    finally: conn.close()
        
        st.markdown("---")
        st.subheader("⚠️ Zona de Manutenção")
        if st.button("🚨 RESETAR SISTEMA"):
            conn = sqlite3.connect('bel_global.db')
            conn.execute("DROP TABLE IF EXISTS modelos")
            conn.execute("DROP TABLE IF EXISTS clientes")
            conn.execute("DROP TABLE IF EXISTS producao")
            conn.commit()
            conn.close()
            st.cache_data.clear()
            st.success("Banco de dados recriado com as novas colunas de excentricidade!")
            st.rerun()

    # --- ABA: RECEBIMENTO ---
    elif menu == "1. Recebimento (Estoque)":
        st.header("📦 Entrada de Equipamentos")
        conn = sqlite3.connect('bel_global.db')
        lista_modelos = [m[0] for m in conn.execute("SELECT nome FROM modelos").fetchall()]
        conn.close()

        with st.form("form_recebimento", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                di_numero = st.text_input("Número da DI")
                lote_nome = st.text_input("Lote Interno")
            with col2:
                modelo_sel = st.selectbox("Modelo", lista_modelos, index=None)
            seriais = st.text_area("Seriais da China (um por linha)")
            
            if st.form_submit_button("Dar Entrada"):
                if not modelo_sel or not lote_nome or not seriais:
                    st.error("Preencha DI, Lote, Modelo e Seriais.")
                else:
                    lista_seriais = [s.strip() for s in seriais.split('\n') if s.strip()]
                    conn = sqlite3.connect('bel_global.db')
                    sucessos = 0
                    for sn in lista_seriais:
                        try:
                            conn.execute('''INSERT INTO producao (lote, di, modelo, serial_china, status) 
                                            VALUES (?, ?, ?, ?, ?)''', (lote_nome, di_numero, modelo_sel, sn, "Disponível"))
                            sucessos += 1
                        except: pass
                    conn.commit()
                    conn.close()
                    st.success(f"✅ {sucessos} equipamentos registrados no estoque.")

    # --- ABA: BANCADA DE AFERIÇÃO ---
    elif menu == "2. Bancada de Aferição":
        st.header("🔬 Bancada de Calibração")
        
        conn = sqlite3.connect('bel_global.db')
        lista_clientes = [c[0] for c in conn.execute("SELECT nome FROM clientes").fetchall()]
        conn.close()

        col1, col2 = st.columns(2)
        with col1: pedido_sel = st.text_input("Número do Pedido Comercial")
        with col2: cliente_sel = st.selectbox("Cliente Destino", lista_clientes, index=None)

        st.markdown("---")
        st.write("### 1️⃣ Baixe o Template em Branco")
        
        # O Template agora possui as 4 colunas de Excentricidade
        df_template = pd.DataFrame(columns=[
            "Serial_China", "Novo_Serial_Brasil", "Valor_Antes", "Valor_Depois", 
            "Exc_Sup_Esq", "Exc_Sup_Dir", "Exc_Inf_Esq", "Exc_Inf_Dir", 
            "Carga_Max", "Zero"
        ])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_template.to_excel(writer, index=False, sheet_name='Calibracao')
        
        st.download_button(
            label="⬇️ Baixar Planilha de Calibração",
            data=buffer.getvalue(),
            file_name="Planilha_Afericao_Bel.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.markdown("---")
        st.write("### 2️⃣ Suba a Planilha Preenchida")
        arquivo_importacao = st.file_uploader("Arraste seu arquivo Excel preenchido aqui", type=['xlsx'])
        
        if arquivo_importacao:
            df_importado = pd.read_excel(arquivo_importacao)
            df_importado = df_importado.dropna(how='all')
            
            st.write("Pré-visualização dos dados lidos:")
            st.dataframe(df_importado, use_container_width=True)
            
            if st.button("💾 Validar e Salvar Lote de Calibração"):
                if not cliente_sel or not pedido_sel:
                    st.error("⚠️ Informe o Cliente e o Número do Pedido no topo da página!")
                elif "Serial_China" not in df_importado.columns:
                    st.error("⚠️ Use o template correto baixado no passo 1.")
                else:
                    conn = sqlite3.connect('bel_global.db')
                    sucessos = 0
                    erros = []
                    
                    for index, row in df_importado.iterrows():
                        serial_china = str(row["Serial_China"]).strip() if not pd.isna(row["Serial_China"]) else ""
                        if not serial_china: continue 
                            
                        check = conn.execute("SELECT id FROM producao WHERE serial_china=? AND status='Disponível'", (serial_china,)).fetchone()
                        
                        if check:
                            serial_br = "" if pd.isna(row.get("Novo_Serial_Brasil")) else str(row.get("Novo_Serial_Brasil")).strip()
                            v_antes = "" if pd.isna(row.get("Valor_Antes")) else str(row.get("Valor_Antes")).strip()
                            v_depois = "" if pd.isna(row.get("Valor_Depois")) else str(row.get("Valor_Depois")).strip()
                            e_se = "" if pd.isna(row.get("Exc_Sup_Esq")) else str(row.get("Exc_Sup_Esq")).strip()
                            e_sd = "" if pd.isna(row.get("Exc_Sup_Dir")) else str(row.get("Exc_Sup_Dir")).strip()
                            e_ie = "" if pd.isna(row.get("Exc_Inf_Esq")) else str(row.get("Exc_Inf_Esq")).strip()
                            e_id = "" if pd.isna(row.get("Exc_Inf_Dir")) else str(row.get("Exc_Inf_Dir")).strip()
                            c_max = "" if pd.isna(row.get("Carga_Max")) else str(row.get("Carga_Max")).strip()
                            zero = "" if pd.isna(row.get("Zero")) else str(row.get("Zero")).strip()
                            
                            conn.execute('''UPDATE producao SET 
                                            cliente=?, pedido=?, serial_brasil=?, 
                                            valor_antes=?, valor_depois=?, 
                                            exc_se=?, exc_sd=?, exc_ie=?, exc_id=?, 
                                            carga_maxima=?, zero=?, status=?
                                            WHERE serial_china=?''',
                                         (cliente_sel, pedido_sel, serial_br,
                                          v_antes, v_depois, e_se, e_sd, e_ie, e_id, 
                                          c_max, zero, "Finalizado", serial_china))
                            sucessos += 1
                        else:
                            erros.append(serial_china)
                            
                    conn.commit()
                    conn.close()
                    
                    if sucessos > 0:
                        st.success(f"✅ {sucessos} balanças foram calibradas e vinculadas ao pedido {pedido_sel}!")
                    if erros:
                        st.warning(f"⚠️ Seriais não encontrados no estoque ou já finalizados: {', '.join(erros)}")

    # --- ABA: CONSULTA ---
    elif menu == "Consulta":
        st.header("🔍 Consulta e Inventário")
        busca = st.text_input("Buscar por Serial, Lote, Pedido ou Cliente:")
        conn = sqlite3.connect('bel_global.db')
        # A consulta agora puxa as 4 colunas de excentricidade
        query = '''SELECT di, lote, modelo, cliente, pedido, serial_china, serial_brasil, 
                   valor_antes, valor_depois, exc_se, exc_sd, exc_ie, exc_id, carga_maxima, zero, status 
                   FROM producao'''
        if busca:
            query += f" WHERE lote LIKE '%{busca}%' OR serial_china LIKE '%{busca}%' OR serial_brasil LIKE '%{busca}%' OR cliente LIKE '%{busca}%' OR pedido LIKE '%{busca}%'"
        df = pd.read_sql_query(query, conn)
        conn.close()
        st.dataframe(df.style.map(color_status, subset=['status']), use_container_width=True)

elif unidade == "China (Factory)":
    st.title("🇨🇳 China Production Interface")
    st.info("Módulo para entrada de dados.")
else:
    st.sidebar.info("👆 Selecione uma unidade.")