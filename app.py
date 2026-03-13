import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
import io
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment

# ══════════════════════════════════════════════
# BANCO DE DADOS — SUPABASE / POSTGRESQL
# ══════════════════════════════════════════════
def get_conn():
    url = st.secrets["DATABASE_URL"]
    return psycopg2.connect(url, sslmode="require", connect_timeout=10)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS modelos
                 (id SERIAL PRIMARY KEY, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes
                 (id SERIAL PRIMARY KEY, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS producao
                 (id SERIAL PRIMARY KEY,
                  di TEXT, modelo TEXT, cliente TEXT,
                  serial_china TEXT UNIQUE, serial_brasil TEXT,
                  pedido TEXT, valor_antes TEXT, valor_depois TEXT,
                  exc_se TEXT, exc_sd TEXT, exc_ie TEXT, exc_id TEXT,
                  carga_maxima TEXT, zero TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()


def query_df(sql, params=None):
    """Executa SELECT e retorna DataFrame."""
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df

def execute(sql, params=None):
    """Executa INSERT/UPDATE/DELETE."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(sql, params or ())
    conn.commit()
    conn.close()

def executemany_safe(rows_sql, rows_data):
    """
    Executa múltiplos INSERTs retornando (ok, duplicados).
    rows_sql: string SQL com %s
    rows_data: lista de tuplas
    """
    conn = get_conn()
    c = conn.cursor()
    ok, dup = 0, []
    for data in rows_data:
        try:
            c.execute(rows_sql, data)
            conn.commit()
            ok += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            dup.append(data[3])  # serial_china é o 4º campo
    conn.close()
    return ok, dup

# ══════════════════════════════════════════════
# CONFIGURAÇÃO GERAL
# ══════════════════════════════════════════════
st.set_page_config(page_title="Bel Traceability", layout="wide")

st.markdown("""
<style>
    [data-testid="stSidebar"] { background-color: #1a1a2e; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    [data-testid="stSidebar"] .stRadio > label {
        color: #cccccc !important; font-size: 11px;
        text-transform: uppercase; letter-spacing: 1px;
    }
    h1 { color: #ffffff !important; }
    h2 { color: #ffffff !important; border-bottom: 2px solid #333; padding-bottom: 8px; }
    h3 { color: #ffffff !important; }
    [data-testid="metric-container"] {
        background: #1e2a3a; border: 1px solid #2d4060;
        border-radius: 8px; padding: 12px;
    }
    .info-box {
        background: #1e2a3a; border-left: 4px solid #0066cc;
        border-radius: 4px; padding: 12px 16px; margin: 8px 0;
        font-size: 14px; color: #ffffff !important;
    }
    .secao-titulo {
        font-size: 17px; font-weight: 600; color: #ffffff;
        margin-top: 8px; margin-bottom: 2px;
    }
    .detalhe-serial-br { font-size: 26px; color: #4da6ff; font-weight: 700; }
    .detalhe-serial-china { font-size: 14px; color: #aaaaaa; margin-top: 4px; }
    .detalhe-label { font-size: 11px; color: #aaaaaa; text-transform: uppercase; letter-spacing: 1px; }
    .badge-disponivel  { background:#0066cc; color:#fff; padding:4px 12px; border-radius:12px; font-size:13px; }
    .badge-pronta      { background:#7b2d8b; color:#fff; padding:4px 12px; border-radius:12px; font-size:13px; }
    .badge-finalizado  { background:#007a33; color:#fff; padding:4px 12px; border-radius:12px; font-size:13px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════
def color_status(val):
    if val == 'Disponível':     return 'color: #4da6ff; font-weight: bold'
    if val == 'Finalizado':     return 'color: #00cc66; font-weight: bold'
    if val == 'Pronta Entrega': return 'color: #cc88ff; font-weight: bold'
    return 'color: #ffaa44; font-weight: bold'

def estilizar_excel(ws, df):
    for i, col in enumerate(df.columns, 1):
        max_len = max(len(str(col)),
                      df[col].astype(str).map(len).max() if not df.empty else 0)
        ws.column_dimensions[get_column_letter(i)].width = min(max_len + 4, 40)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1a1a2e")
        cell.alignment = Alignment(horizontal="center")

def gerar_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
        estilizar_excel(writer.sheets['Dados'], df)
    return buf.getvalue()

def gerar_planilha_afericao(df_sel: pd.DataFrame) -> bytes:
    colunas_vazias = [
        "Novo_Serial_Brasil", "Valor_Antes", "Valor_Depois",
        "Exc_Sup_Esq", "Exc_Sup_Dir", "Exc_Inf_Esq", "Exc_Inf_Dir",
        "Carga_Max", "Zero"
    ]
    df_out = df_sel[["Serial_China", "Modelo", "DI"]].copy()
    for col in colunas_vazias:
        df_out[col] = ""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_out.to_excel(writer, index=False, sheet_name='Calibracao')
        ws = writer.sheets['Calibracao']
        estilizar_excel(ws, df_out)
        fill_pre = PatternFill("solid", fgColor="dce8f5")
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=3):
            for cell in row:
                cell.fill = fill_pre
    return buf.getvalue()


# ══════════════════════════════════════════════
# MENU LATERAL
# ══════════════════════════════════════════════
st.sidebar.title("🌐 Bel Engineering")
st.sidebar.markdown("**Sistema de Rastreabilidade**")
st.sidebar.markdown("---")

unidade = st.sidebar.selectbox(
    "Unidade Operacional", ["Brasil", "China (Factory)"],
    index=None, placeholder="Selecione a unidade..."
)

# ══════════════════════════════════════════════
# BRASIL
# ══════════════════════════════════════════════
if unidade == "Brasil":
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Navegação", [
        "📊 Dashboard",
        "📋 Gestão de Cadastros",
        "🔬 Bancada de Aferição",
        "📦 Pronta Entrega",
        "🔍 Consulta",
        "⚙️  Configurações",
    ])

    # ══════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════
    if menu == "📊 Dashboard":
        st.title("📊 Dashboard — Visão Geral")

        df_all = query_df("SELECT status, modelo, di FROM producao")

        total  = len(df_all)
        disp   = len(df_all[df_all['status'] == 'Disponível'])
        pronta = len(df_all[df_all['status'] == 'Pronta Entrega'])
        final  = len(df_all[df_all['status'] == 'Finalizado'])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Balanças", total)
        c2.metric("🔵 Disponíveis", disp)
        c3.metric("🟣 Pronta Entrega", pronta)
        c4.metric("🟢 Finalizadas", final)

        if not df_all.empty:
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Por Status")
                df_s = df_all['status'].value_counts().reset_index()
                df_s.columns = ['Status', 'Quantidade']
                st.dataframe(df_s, use_container_width=True, hide_index=True)
            with col2:
                st.subheader("Por Modelo")
                df_m = df_all['modelo'].value_counts().reset_index()
                df_m.columns = ['Modelo', 'Quantidade']
                st.dataframe(df_m, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Por DI")
            df_di = query_df("""
                SELECT di AS "DI", COUNT(*) AS "Total",
                       SUM(CASE WHEN status='Disponível'     THEN 1 ELSE 0 END) AS "Disponíveis",
                       SUM(CASE WHEN status='Pronta Entrega' THEN 1 ELSE 0 END) AS "Pronta Entrega",
                       SUM(CASE WHEN status='Finalizado'     THEN 1 ELSE 0 END) AS "Finalizadas",
                       STRING_AGG(DISTINCT modelo, ', ') AS "Modelos"
                FROM producao WHERE di IS NOT NULL AND di != ''
                GROUP BY di ORDER BY di DESC
            """)
            if not df_di.empty:
                st.dataframe(df_di, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado registrado ainda.")

    # ══════════════════════════════════════════
    # GESTÃO DE CADASTROS
    # ══════════════════════════════════════════
    elif menu == "📋 Gestão de Cadastros":
        st.title("📋 Gestão de Cadastros")

        tab_modelos, tab_clientes, tab_dis = st.tabs([
            "🏷️  Modelos", "👥 Clientes", "🚢 DIs / Recebimento"
        ])

        # ── MODELOS ───────────────────────────
        with tab_modelos:
            df_mod = query_df("SELECT id, nome FROM modelos ORDER BY nome")

            st.markdown('<p class="secao-titulo">➕ Novo Modelo</p>', unsafe_allow_html=True)
            with st.form("form_novo_modelo", clear_on_submit=True):
                ci, cb = st.columns([3, 1])
                novo_mod = ci.text_input("m", label_visibility="collapsed",
                                          placeholder="Nome do modelo (ex: M5-224)").strip()
                if cb.form_submit_button("➕ Inserir", use_container_width=True) and novo_mod:
                    try:
                        execute("INSERT INTO modelos (nome) VALUES (%s)", (novo_mod,))
                        st.success(f"Modelo '{novo_mod}' cadastrado!")
                        st.rerun()
                    except Exception:
                        st.error("Modelo já existe.")

            st.markdown("---")
            st.markdown('<p class="secao-titulo">📋 Modelos Cadastrados</p>', unsafe_allow_html=True)

            if df_mod.empty:
                st.info("Nenhum modelo cadastrado ainda.")
            else:
                cl, ca = st.columns([2, 1])
                with cl:
                    st.dataframe(df_mod[['nome']].rename(columns={'nome': 'Modelo'}),
                                 use_container_width=True, hide_index=True)
                with ca:
                    st.markdown("**Editar / Excluir**")
                    mid = st.selectbox("sel", df_mod['id'].tolist(),
                        format_func=lambda i: df_mod[df_mod['id']==i]['nome'].values[0],
                        index=None, placeholder="Escolha...", key="sel_mod",
                        label_visibility="collapsed")
                    if mid:
                        nm = df_mod[df_mod['id']==mid]['nome'].values[0]
                        with st.form("form_edit_mod"):
                            nn = st.text_input("Nome", value=nm)
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("💾 Salvar", use_container_width=True):
                                try:
                                    execute("UPDATE modelos SET nome=%s WHERE id=%s", (nn.strip(), mid))
                                    st.success("Atualizado!")
                                    st.rerun()
                                except Exception:
                                    st.error("Nome já existe.")
                            if b2.form_submit_button("🗑️ Excluir", use_container_width=True):
                                em_uso = query_df(
                                    "SELECT COUNT(*) as n FROM producao WHERE modelo=%s", params=(nm,)
                                )['n'].values[0]
                                if em_uso:
                                    st.error(f"Em uso por {em_uso} balança(s).")
                                else:
                                    execute("DELETE FROM modelos WHERE id=%s", (mid,))
                                    st.success("Excluído.")
                                    st.rerun()

        # ── CLIENTES ──────────────────────────
        with tab_clientes:
            df_cli     = query_df("SELECT id, nome FROM clientes ORDER BY nome")
            df_cli_cnt = query_df(
                "SELECT cliente, COUNT(*) as total FROM producao WHERE cliente IS NOT NULL AND cliente!='' GROUP BY cliente")

            st.markdown('<p class="secao-titulo">➕ Novo Cliente</p>', unsafe_allow_html=True)
            with st.form("form_novo_cli", clear_on_submit=True):
                ci, cb = st.columns([3, 1])
                novo_cli = ci.text_input("c", label_visibility="collapsed",
                                          placeholder="Nome do cliente").strip()
                if cb.form_submit_button("➕ Inserir", use_container_width=True) and novo_cli:
                    try:
                        execute("INSERT INTO clientes (nome) VALUES (%s)", (novo_cli,))
                        st.success(f"Cliente '{novo_cli}' cadastrado!")
                        st.rerun()
                    except Exception:
                        st.error("Cliente já existe.")

            st.markdown("---")
            st.markdown('<p class="secao-titulo">📋 Clientes Cadastrados</p>', unsafe_allow_html=True)

            if df_cli.empty:
                st.info("Nenhum cliente cadastrado ainda.")
            else:
                cl, ca = st.columns([2, 1])
                with cl:
                    df_d = df_cli.merge(df_cli_cnt, left_on='nome', right_on='cliente', how='left')
                    df_d['total'] = df_d['total'].fillna(0).astype(int)
                    st.dataframe(df_d[['nome','total']].rename(
                        columns={'nome':'Cliente','total':'Balanças vinculadas'}),
                        use_container_width=True, hide_index=True)
                with ca:
                    st.markdown("**Editar / Excluir**")
                    cid = st.selectbox("sel", df_cli['id'].tolist(),
                        format_func=lambda i: df_cli[df_cli['id']==i]['nome'].values[0],
                        index=None, placeholder="Escolha...", key="sel_cli",
                        label_visibility="collapsed")
                    if cid:
                        nc = df_cli[df_cli['id']==cid]['nome'].values[0]
                        with st.form("form_edit_cli"):
                            nn = st.text_input("Nome", value=nc)
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("💾 Salvar", use_container_width=True):
                                try:
                                    execute("UPDATE clientes SET nome=%s WHERE id=%s", (nn.strip(), cid))
                                    execute("UPDATE producao SET cliente=%s WHERE cliente=%s", (nn.strip(), nc))
                                    st.success("Atualizado!")
                                    st.rerun()
                                except Exception:
                                    st.error("Nome já existe.")
                            if b2.form_submit_button("🗑️ Excluir", use_container_width=True):
                                em_uso = query_df(
                                    "SELECT COUNT(*) as n FROM producao WHERE cliente=%s", params=(nc,)
                                )['n'].values[0]
                                if em_uso:
                                    st.error(f"Em uso por {em_uso} balança(s).")
                                else:
                                    execute("DELETE FROM clientes WHERE id=%s", (cid,))
                                    st.success("Excluído.")
                                    st.rerun()

        # ── DIs / RECEBIMENTO ─────────────────
        with tab_dis:
            lista_modelos = query_df("SELECT nome FROM modelos ORDER BY nome")['nome'].tolist()

            st.markdown('<p class="secao-titulo">➕ Registrar Nova Entrada de Equipamentos</p>',
                        unsafe_allow_html=True)

            if not lista_modelos:
                st.warning("Cadastre pelo menos um modelo na aba **🏷️ Modelos** antes de registrar uma DI.")
            else:
                di_numero = st.text_input("Número da DI (ex: DI26034)", key="di_input")

                st.markdown("---")
                st.markdown("**Modelos e Seriais desta DI**")
                st.markdown(
                    '<div class="info-box">Uma DI pode conter múltiplos modelos. Adicione um bloco por modelo.</div>',
                    unsafe_allow_html=True)

                if 'num_blocos' not in st.session_state:
                    st.session_state.num_blocos = 1

                if st.button("➕ Adicionar outro modelo"):
                    st.session_state.num_blocos += 1
                    st.rerun()

                blocos = []
                for i in range(st.session_state.num_blocos):
                    st.markdown(f"**Modelo {i+1}**")
                    cm, cr = st.columns([4, 1])
                    with cm:
                        mod_b = st.selectbox("Modelo", lista_modelos,
                            index=None, placeholder="Selecione o modelo...",
                            key=f"mod_bloco_{i}")
                    with cr:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.session_state.num_blocos > 1:
                            if st.button("🗑️", key=f"rem_{i}"):
                                st.session_state.num_blocos -= 1
                                st.rerun()
                    sn_b = st.text_area("Seriais (um por linha)", height=110,
                        placeholder="Ex:\n2600101\n2600102", key=f"sn_bloco_{i}")
                    blocos.append((mod_b, sn_b))
                    st.markdown("---")

                if st.button("📥 Dar Entrada no Estoque", type="primary", use_container_width=True):
                    di_v    = st.session_state.get("di_input", "").strip()
                    validos = [(m, s) for m, s in blocos if m and s and s.strip()]

                    if not validos:
                        st.error("Preencha ao menos um modelo com seriais.")
                    else:
                        rows = []
                        for mod_v, sn_v in validos:
                            for sn in [x.strip() for x in sn_v.split('\n') if x.strip()]:
                                rows.append((di_v, mod_v, sn, "Disponível"))

                        ok, dup = executemany_safe(
                            "INSERT INTO producao (di, modelo, serial_china, status) VALUES (%s, %s, %s, %s)",
                            rows
                        )
                        if ok:  st.success(f"✅ {ok} equipamento(s) registrado(s) como Disponível.")
                        if dup: st.error(f"🚫 Duplicados ignorados: {', '.join(dup)}")
                        st.session_state.num_blocos = 1
                        st.rerun()

            st.markdown("---")
            st.markdown('<p class="secao-titulo">📋 DIs Registradas</p>', unsafe_allow_html=True)

            df_di_res = query_df("""
                SELECT di AS "DI", COUNT(*) AS "Total",
                       SUM(CASE WHEN status='Disponível'     THEN 1 ELSE 0 END) AS "Disponíveis",
                       SUM(CASE WHEN status='Pronta Entrega' THEN 1 ELSE 0 END) AS "Pronta Entrega",
                       SUM(CASE WHEN status='Finalizado'     THEN 1 ELSE 0 END) AS "Finalizadas",
                       STRING_AGG(DISTINCT modelo, ', ') AS "Modelos"
                FROM producao WHERE di IS NOT NULL AND di != ''
                GROUP BY di ORDER BY di DESC
            """)

            if df_di_res.empty:
                st.info("Nenhuma DI registrada ainda.")
            else:
                st.dataframe(df_di_res, use_container_width=True, hide_index=True)
                st.markdown("---")
                st.markdown('<p class="secao-titulo">🔎 Detalhar uma DI</p>', unsafe_allow_html=True)
                di_esc = st.selectbox("Selecione a DI", df_di_res['DI'].tolist(),
                    index=None, placeholder="Escolha uma DI...")
                if di_esc:
                    df_det = query_df("""
                        SELECT serial_china AS "Serial China", serial_brasil AS "Serial Brasil",
                               modelo AS "Modelo", cliente AS "Cliente",
                               pedido AS "Pedido", status AS "Status"
                        FROM producao WHERE di=%s ORDER BY modelo, serial_china
                    """, params=(di_esc,))
                    st.markdown(f"**{len(df_det)} balança(s) na DI {di_esc}:**")
                    st.dataframe(df_det.style.map(color_status, subset=['Status']),
                                 use_container_width=True, hide_index=True)
                    st.download_button(f"⬇️ Exportar DI {di_esc}",
                        data=gerar_excel(df_det), file_name=f"DI_{di_esc}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ══════════════════════════════════════════
    # BANCADA DE AFERIÇÃO
    # ══════════════════════════════════════════
    elif menu == "🔬 Bancada de Aferição":
        st.title("🔬 Bancada de Calibração")

        lista_clientes = query_df("SELECT nome FROM clientes ORDER BY nome")['nome'].tolist()
        df_disp = query_df("""
            SELECT id, serial_china AS "Serial_China", modelo AS "Modelo", di AS "DI"
            FROM producao WHERE status='Disponível'
            ORDER BY di, modelo, serial_china
        """)

        if df_disp.empty:
            st.warning("Não há balanças disponíveis no estoque no momento.")
        else:
            st.subheader("1️⃣ Selecione as Balanças a Aferir")

            dis_disp = ["Todas as DIs"] + sorted(df_disp['DI'].dropna().unique().tolist())
            filtro_di = st.selectbox("Filtrar por DI (opcional):", dis_disp, index=0)

            df_filtrada = df_disp if filtro_di == "Todas as DIs" else df_disp[df_disp['DI'] == filtro_di]

            st.markdown(f"**{len(df_filtrada)} balança(s) disponível(is):**")
            st.dataframe(df_filtrada[['Serial_China','Modelo','DI']].rename(
                columns={'Serial_China':'Serial China'}),
                use_container_width=True, hide_index=True)

            st.markdown("---")
            selecionadas = st.multiselect(
                "Selecione os seriais que pegou do estoque:",
                df_filtrada['Serial_China'].tolist(),
                placeholder="Digite ou clique para selecionar...")

            if selecionadas:
                df_sel = df_filtrada[df_filtrada['Serial_China'].isin(selecionadas)].copy()

                st.markdown("---")
                st.subheader("2️⃣ Destino das Balanças")
                destino = st.radio("", ["Vincular a Cliente", "Pronta Entrega"],
                                   horizontal=True, label_visibility="collapsed")

                if destino == "Vincular a Cliente":
                    col1, col2 = st.columns(2)
                    pedido_sel  = col1.text_input("Número do Pedido Comercial")
                    cliente_sel = col2.selectbox("Cliente Destino", lista_clientes,
                        index=None, placeholder="Selecione o cliente...")
                    status_destino = "Finalizado"
                else:
                    st.markdown(
                        '<div class="info-box">As balanças serão marcadas como <strong>Pronta Entrega</strong>. '
                        'O cliente e pedido poderão ser vinculados depois na aba 📦 Pronta Entrega.</div>',
                        unsafe_allow_html=True)
                    pedido_sel = cliente_sel = ""
                    status_destino = "Pronta Entrega"

                st.markdown("---")
                st.subheader("3️⃣ Baixe a Planilha Pré-Preenchida")
                st.markdown(
                    '<div class="info-box">A planilha já vem com <strong>Serial China</strong>, '
                    '<strong>Modelo</strong> e <strong>DI</strong> preenchidos. '
                    'Preencha apenas os dados de calibração e o Serial Brasil na bancada.</div>',
                    unsafe_allow_html=True)
                st.download_button(
                    label=f"⬇️ Baixar Planilha ({len(selecionadas)} balança(s))",
                    data=gerar_planilha_afericao(df_sel),
                    file_name="Afericao_Bel.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                st.markdown("---")
                st.subheader("4️⃣ Suba a Planilha Preenchida")
                arquivo = st.file_uploader("Arraste o arquivo Excel preenchido aqui", type=['xlsx'])

                if arquivo:
                    df_imp = pd.read_excel(arquivo).dropna(how='all')
                    st.write("Pré-visualização:")
                    st.dataframe(df_imp, use_container_width=True)

                    if st.button("💾 Validar e Salvar", type="primary"):
                        if destino == "Vincular a Cliente" and (not cliente_sel or not pedido_sel):
                            st.error("⚠️ Informe o Cliente e o Pedido antes de salvar.")
                        elif "Serial_China" not in df_imp.columns:
                            st.error("⚠️ Use o template gerado no passo 3.")
                        else:
                            conn = get_conn()
                            cur  = conn.cursor()
                            ok, erros = 0, []
                            for _, row in df_imp.iterrows():
                                sc = str(row["Serial_China"]).strip() if not pd.isna(row.get("Serial_China")) else ""
                                if not sc: continue
                                cur.execute(
                                    "SELECT id FROM producao WHERE serial_china=%s AND status='Disponível'", (sc,))
                                check = cur.fetchone()
                                if check:
                                    def s(col): return "" if pd.isna(row.get(col)) else str(row.get(col)).strip()
                                    cur.execute('''UPDATE producao SET
                                        cliente=%s, pedido=%s, serial_brasil=%s,
                                        valor_antes=%s, valor_depois=%s,
                                        exc_se=%s, exc_sd=%s, exc_ie=%s, exc_id=%s,
                                        carga_maxima=%s, zero=%s, status=%s
                                        WHERE serial_china=%s''',
                                        (cliente_sel, pedido_sel, s("Novo_Serial_Brasil"),
                                         s("Valor_Antes"), s("Valor_Depois"),
                                         s("Exc_Sup_Esq"), s("Exc_Sup_Dir"),
                                         s("Exc_Inf_Esq"), s("Exc_Inf_Dir"),
                                         s("Carga_Max"), s("Zero"),
                                         status_destino, sc))
                                    ok += 1
                                else:
                                    erros.append(sc)
                            conn.commit(); conn.close()
                            if ok:    st.success(f"✅ {ok} balança(s) salvas com status '{status_destino}'!")
                            if erros: st.warning(f"⚠️ Não encontrados ou já finalizados: {', '.join(erros)}")
            else:
                st.markdown("---")
                st.info("Selecione ao menos uma balança acima para continuar.")

    # ══════════════════════════════════════════
    # PRONTA ENTREGA
    # ══════════════════════════════════════════
    elif menu == "📦 Pronta Entrega":
        st.title("📦 Pronta Entrega — Vincular Cliente")

        lista_clientes = query_df("SELECT nome FROM clientes ORDER BY nome")['nome'].tolist()
        df_pe = query_df("""
            SELECT id, serial_china AS "Serial China", serial_brasil AS "Serial Brasil",
                   modelo AS "Modelo", di AS "DI"
            FROM producao WHERE status='Pronta Entrega'
            ORDER BY modelo, serial_brasil
        """)

        if df_pe.empty:
            st.info("Nenhuma balança em Pronta Entrega no momento.")
        else:
            st.markdown(f"**{len(df_pe)} balança(s) disponível(is) para venda:**")
            st.dataframe(df_pe.drop(columns=['id']), use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Vincular ao Cliente")

            opcoes = df_pe.apply(
                lambda r: f"{r['Serial Brasil'] or r['Serial China']}  |  {r['Modelo']}  |  DI: {r['DI'] or '—'}",
                axis=1).tolist()
            ids_map = dict(zip(opcoes, df_pe['id'].tolist()))

            selecionadas = st.multiselect("Selecione as balanças a vincular:",
                opcoes, placeholder="Clique para selecionar...")

            col1, col2 = st.columns(2)
            pedido_pe  = col1.text_input("Número do Pedido Comercial", key="pedido_pe")
            cliente_pe = col2.selectbox("Cliente", lista_clientes,
                index=None, placeholder="Selecione o cliente...", key="cliente_pe")

            if selecionadas:
                st.markdown(f"**{len(selecionadas)} balança(s) selecionada(s)**")

            if st.button("✅ Confirmar Venda", type="primary", disabled=not selecionadas):
                if not cliente_pe or not pedido_pe:
                    st.error("Informe o Cliente e o Número do Pedido.")
                else:
                    conn = get_conn()
                    cur  = conn.cursor()
                    for rid in [ids_map[s] for s in selecionadas]:
                        cur.execute(
                            "UPDATE producao SET cliente=%s, pedido=%s, status='Finalizado' WHERE id=%s",
                            (cliente_pe, pedido_pe, rid))
                    conn.commit(); conn.close()
                    st.success(f"✅ {len(selecionadas)} balança(s) vinculada(s) ao cliente {cliente_pe}!")
                    st.rerun()

    # ══════════════════════════════════════════
    # CONSULTA + DETALHE
    # ══════════════════════════════════════════
    elif menu == "🔍 Consulta":
        st.title("🔍 Consulta e Inventário Global")

        if 'detalhe_id' in st.session_state and st.session_state.detalhe_id:
            row = query_df("""
                SELECT serial_china, serial_brasil, di, modelo, cliente, pedido,
                       valor_antes, valor_depois, exc_se, exc_sd, exc_ie, exc_id,
                       carga_maxima, zero, status
                FROM producao WHERE id=%s
            """, params=(st.session_state.detalhe_id,))

            if not row.empty:
                r = row.iloc[0]
                if st.button("← Voltar para a Consulta"):
                    st.session_state.detalhe_id = None
                    st.rerun()

                st.markdown("---")
                st.markdown(f"""
                <div style="margin-bottom:20px;">
                    <div class="detalhe-label">Serial Brasil (Inmetro)</div>
                    <div class="detalhe-serial-br">{r.serial_brasil or '—'}</div>
                    <div class="detalhe-serial-china">🇨🇳 Serial China: <strong>{r.serial_china or '—'}</strong></div>
                </div>
                """, unsafe_allow_html=True)

                badge_map = {'Disponível':'badge-disponivel','Pronta Entrega':'badge-pronta','Finalizado':'badge-finalizado'}
                st.markdown(f'<span class="{badge_map.get(r.status, "badge-disponivel")}">{r.status}</span>',
                            unsafe_allow_html=True)
                st.markdown("---")

                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**Modelo**\n\n{r.modelo or '—'}")
                col2.markdown(f"**DI**\n\n{r.di or '—'}")
                col3.markdown(f"**Cliente**\n\n{r.cliente or '—'}")
                st.markdown(f"**Pedido:** {r.pedido or '—'}")

                if any([r.valor_antes, r.valor_depois, r.exc_se, r.exc_sd, r.exc_ie, r.exc_id, r.carga_maxima, r.zero]):
                    st.markdown("---")
                    st.subheader("📐 Dados de Calibração")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Valor Antes", r.valor_antes or "—")
                    c2.metric("Valor Depois", r.valor_depois or "—")
                    c3.metric("Carga Máx", r.carga_maxima or "—")
                    st.markdown("**Excentricidade (4 cantos):**")
                    ce1, ce2, ce3, ce4 = st.columns(4)
                    ce1.metric("Sup. Esq", r.exc_se or "—")
                    ce2.metric("Sup. Dir", r.exc_sd or "—")
                    ce3.metric("Inf. Esq", r.exc_ie or "—")
                    ce4.metric("Inf. Dir", r.exc_id or "—")
                    st.metric("Zero", r.zero or "—")
        else:
            busca = st.text_input("🔎 Buscar por Serial China, Serial Brasil, DI, Pedido ou Cliente:")

            where = ""
            params = None
            if busca:
                where = """ WHERE di ILIKE %s OR serial_china ILIKE %s
                             OR serial_brasil ILIKE %s OR cliente ILIKE %s OR pedido ILIKE %s"""
                p = f"%{busca}%"
                params = (p, p, p, p, p)

            df = query_df(f"""
                SELECT id, di AS "DI", modelo AS "Modelo", cliente AS "Cliente",
                       pedido AS "Pedido", serial_china AS "Serial China",
                       serial_brasil AS "Serial Brasil", status AS "Status"
                FROM producao {where} ORDER BY id DESC
            """, params=params)

            if not df.empty:
                st.markdown(f"**{len(df)} registro(s) encontrado(s)**")
                st.dataframe(df.drop(columns=['id']).style.map(color_status, subset=['Status']),
                             use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown("**Ver detalhe de uma balança:**")
                opcoes_det = df.apply(
                    lambda r: f"{r['Serial Brasil'] or r['Serial China']}  |  {r['Modelo']}  |  {r['Status']}",
                    axis=1).tolist()

                sel = st.selectbox("Selecione", range(len(opcoes_det)),
                    format_func=lambda i: opcoes_det[i],
                    index=None, placeholder="Escolha para ver o detalhe...")

                if sel is not None:
                    st.session_state.detalhe_id = df['id'].tolist()[sel]
                    st.rerun()

                st.download_button("⬇️ Exportar para Excel",
                    data=gerar_excel(df.drop(columns=['id'])),
                    file_name="consulta_bel.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.info("Nenhum registro encontrado.")

    # ══════════════════════════════════════════
    # CONFIGURAÇÕES
    # ══════════════════════════════════════════
    elif menu == "⚙️  Configurações":
        st.title("⚙️ Configurações do Sistema")

        st.markdown("---")
        st.subheader("⚠️ Zona de Manutenção")
        st.warning("Esta ação apaga **todos os dados** permanentemente e não pode ser desfeita.")
        if st.checkbox("Confirmo que desejo apagar todos os dados"):
            if st.button("🚨 RESETAR SISTEMA", type="primary"):
                conn = get_conn()
                c = conn.cursor()
                c.execute("DROP TABLE IF EXISTS modelos CASCADE")
                c.execute("DROP TABLE IF EXISTS clientes CASCADE")
                c.execute("DROP TABLE IF EXISTS producao CASCADE")
                conn.commit(); conn.close()
                init_db()
                st.success("Banco de dados recriado do zero!")
                st.rerun()

# ══════════════════════════════════════════════
# CHINA
# ══════════════════════════════════════════════
elif unidade == "China (Factory)":
    st.title("🇨🇳 China Production Interface")
    st.info("Módulo em desenvolvimento.")

# ══════════════════════════════════════════════
# TELA INICIAL
# ══════════════════════════════════════════════
else:
    st.sidebar.info("👆 Selecione uma unidade para começar.")
    st.title("🔬 Bel Engineering — Traceability System")
    st.markdown("""
    ### Bem-vindo ao Sistema de Rastreabilidade Global

    Selecione a unidade operacional no menu lateral para acessar as ferramentas.

    ---
    **Fluxo operacional:**
    1. **Gestão de Cadastros** — Cadastre modelos, clientes e registre a entrada das DIs
    2. **Bancada de Aferição** — Selecione as balanças, baixe a planilha pré-preenchida, preencha na bancada e importe
    3. **Pronta Entrega** — Vincule clientes às balanças em estoque quando a venda acontecer
    4. **Consulta** — Pesquise qualquer balança e veja rastreabilidade completa China → Brasil
    5. **Dashboard** — Acompanhe o status geral do inventário
    """)
