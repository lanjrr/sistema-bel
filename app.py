import streamlit as st
import sqlite3
import pandas as pd
import io
from openpyxl.utils import get_column_letter

# ══════════════════════════════════════════════
# BANCO DE DADOS
# ══════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect('bel_global.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS modelos (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)')
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

# ══════════════════════════════════════════════
# CONFIGURAÇÃO GERAL
# ══════════════════════════════════════════════
st.set_page_config(page_title="Bel Traceability", layout="wide")

st.markdown("""
<style>
    /* ── Sidebar ── */
    [data-testid="stSidebar"] { background-color: #1a1a2e; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    [data-testid="stSidebar"] .stRadio > label {
        color: #cccccc !important; font-size: 11px;
        text-transform: uppercase; letter-spacing: 1px;
    }
    [data-testid="stSidebar"] .stSelectbox label { color: #cccccc !important; }

    /* ── Conteúdo principal ── */
    h1 { color: #ffffff !important; }
    h2 { color: #ffffff !important; border-bottom: 2px solid #e8e8e8; padding-bottom: 8px; }
    h3 { color: #ffffff !important; }

    /* ── Métricas ── */
    [data-testid="metric-container"] {
        background: #f8f9fa; border: 1px solid #e0e0e0;
        border-radius: 8px; padding: 12px;
    }

    /* ── Info box ── */
    .info-box {
        background: #f0f4ff; border-left: 4px solid #0066cc;
        border-radius: 4px; padding: 12px 16px; margin: 8px 0; font-size: 14px;
        color: #1a1a2e !important;
    }

    /* ── Zona de perigo — sem HTML wrapper, estilo via classe ── */
    .danger-section {
        border: 1px solid #ffcccc; border-radius: 8px;
        padding: 16px; margin-top: 8px; background: #fff3f3;
    }

    /* ── Títulos de seção dentro das tabs ── */
    .secao-titulo {
        font-size: 17px; font-weight: 600; color: #ffffff;
        margin-top: 8px; margin-bottom: 2px;
    }

    /* ── Bloco de modelo dentro do recebimento DI ── */
    .modelo-bloco {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 8px; padding: 16px; margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


def color_status(val):
    if val == 'Disponível': return 'color: #0066cc; font-weight: bold'
    if val == 'Finalizado':  return 'color: #007a33; font-weight: bold'
    return 'color: #cc6600; font-weight: bold'


def gerar_excel_calibrado(df: pd.DataFrame) -> bytes:
    """Gera Excel com colunas auto-ajustadas."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
        ws = writer.sheets['Dados']
        for i, col in enumerate(df.columns, 1):
            max_len = max(len(str(col)), df[col].astype(str).map(len).max() if not df.empty else 0)
            ws.column_dimensions[get_column_letter(i)].width = min(max_len + 4, 40)
    return buf.getvalue()


def gerar_template_calibracao() -> bytes:
    """Gera planilha template com colunas auto-ajustadas."""
    colunas = [
        "Serial_China", "Novo_Serial_Brasil", "Valor_Antes", "Valor_Depois",
        "Exc_Sup_Esq", "Exc_Sup_Dir", "Exc_Inf_Esq", "Exc_Inf_Dir",
        "Carga_Max", "Zero"
    ]
    df_t = pd.DataFrame(columns=colunas)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_t.to_excel(writer, index=False, sheet_name='Calibracao')
        ws = writer.sheets['Calibracao']
        for i, col in enumerate(colunas, 1):
            ws.column_dimensions[get_column_letter(i)].width = len(col) + 6
        # Formata cabeçalho em negrito
        from openpyxl.styles import Font, PatternFill, Alignment
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="1a1a2e")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center")
    return buf.getvalue()


# ══════════════════════════════════════════════
# MENU LATERAL
# ══════════════════════════════════════════════
st.sidebar.title("🌐 Bel Engineering")
st.sidebar.markdown("**Sistema de Rastreabilidade**")
st.sidebar.markdown("---")

unidade = st.sidebar.selectbox(
    "Unidade Operacional",
    ["Brasil", "China (Factory)"],
    index=None,
    placeholder="Selecione a unidade..."
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
        "🔍 Consulta",
        "⚙️  Configurações",
    ])

    # ══════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════
    if menu == "📊 Dashboard":
        st.title("📊 Dashboard — Visão Geral")

        conn = sqlite3.connect('bel_global.db')
        df_all = pd.read_sql_query("SELECT status, modelo, di FROM producao", conn)
        conn.close()

        total       = len(df_all)
        disponiveis = len(df_all[df_all['status'] == 'Disponível'])
        finalizados = len(df_all[df_all['status'] == 'Finalizado'])
        em_prep     = total - disponiveis - finalizados

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Balanças", total)
        c2.metric("🔵 Disponíveis", disponiveis)
        c3.metric("🟠 Em Preparação", em_prep)
        c4.metric("🟢 Finalizadas", finalizados)

        if not df_all.empty:
            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Por Status")
                df_status = df_all['status'].value_counts().reset_index()
                df_status.columns = ['Status', 'Quantidade']
                st.dataframe(df_status, use_container_width=True, hide_index=True)

            with col2:
                st.subheader("Por Modelo")
                df_modelo = df_all['modelo'].value_counts().reset_index()
                df_modelo.columns = ['Modelo', 'Quantidade']
                st.dataframe(df_modelo, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Por DI")
            conn = sqlite3.connect('bel_global.db')
            df_di_dash = pd.read_sql_query("""
                SELECT di AS "DI",
                       COUNT(*) AS "Total",
                       SUM(CASE WHEN status='Disponível' THEN 1 ELSE 0 END) AS "Em Estoque",
                       SUM(CASE WHEN status='Finalizado' THEN 1 ELSE 0 END) AS "Finalizadas"
                FROM producao WHERE di IS NOT NULL AND di != ''
                GROUP BY di ORDER BY di DESC
            """, conn)
            conn.close()
            if not df_di_dash.empty:
                st.dataframe(df_di_dash, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado registrado ainda. Comece pela Gestão de Cadastros.")

    # ══════════════════════════════════════════
    # GESTÃO DE CADASTROS
    # ══════════════════════════════════════════
    elif menu == "📋 Gestão de Cadastros":
        st.title("📋 Gestão de Cadastros")

        tab_modelos, tab_clientes, tab_dis = st.tabs([
            "🏷️  Modelos",
            "👥 Clientes",
            "🚢 DIs / Recebimento",
        ])

        # ── MODELOS ───────────────────────────
        with tab_modelos:
            conn = sqlite3.connect('bel_global.db')
            df_mod = pd.read_sql_query("SELECT id, nome FROM modelos ORDER BY nome", conn)
            conn.close()

            st.markdown('<p class="secao-titulo">➕ Novo Modelo</p>', unsafe_allow_html=True)
            with st.form("form_novo_modelo", clear_on_submit=True):
                col_inp, col_btn = st.columns([3, 1])
                with col_inp:
                    novo_modelo = st.text_input("m", label_visibility="collapsed",
                                                placeholder="Nome do modelo (ex: M5-214Ai)").strip()
                with col_btn:
                    if st.form_submit_button("➕ Inserir", use_container_width=True) and novo_modelo:
                        try:
                            conn = sqlite3.connect('bel_global.db')
                            conn.execute("INSERT INTO modelos (nome) VALUES (?)", (novo_modelo,))
                            conn.commit()
                            st.success(f"Modelo '{novo_modelo}' cadastrado!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(f"Modelo '{novo_modelo}' já existe.")
                        finally:
                            conn.close()

            st.markdown("---")
            st.markdown('<p class="secao-titulo">📋 Modelos Cadastrados</p>', unsafe_allow_html=True)

            if df_mod.empty:
                st.info("Nenhum modelo cadastrado ainda.")
            else:
                col_lista, col_acao = st.columns([2, 1])
                with col_lista:
                    st.dataframe(df_mod[['nome']].rename(columns={'nome': 'Modelo'}),
                                 use_container_width=True, hide_index=True)
                with col_acao:
                    st.markdown("**Editar / Excluir**")
                    mod_id = st.selectbox("Selecione", df_mod['id'].tolist(),
                        format_func=lambda i: df_mod[df_mod['id']==i]['nome'].values[0],
                        index=None, placeholder="Escolha...", key="sel_mod")
                    if mod_id:
                        nome_mod = df_mod[df_mod['id']==mod_id]['nome'].values[0]
                        with st.form("form_edit_mod", clear_on_submit=False):
                            nn_mod = st.text_input("Nome", value=nome_mod)
                            b1, b2 = st.columns(2)
                            salvar_m  = b1.form_submit_button("💾 Salvar", use_container_width=True)
                            excluir_m = b2.form_submit_button("🗑️ Excluir", use_container_width=True)
                            if salvar_m and nn_mod.strip():
                                try:
                                    conn = sqlite3.connect('bel_global.db')
                                    conn.execute("UPDATE modelos SET nome=? WHERE id=?", (nn_mod.strip(), mod_id))
                                    conn.commit()
                                    st.success("Atualizado!")
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Nome já existe.")
                                finally:
                                    conn.close()
                            if excluir_m:
                                conn = sqlite3.connect('bel_global.db')
                                em_uso = conn.execute("SELECT COUNT(*) FROM producao WHERE modelo=?", (nome_mod,)).fetchone()[0]
                                conn.close()
                                if em_uso:
                                    st.error(f"Em uso por {em_uso} balança(s).")
                                else:
                                    conn = sqlite3.connect('bel_global.db')
                                    conn.execute("DELETE FROM modelos WHERE id=?", (mod_id,))
                                    conn.commit(); conn.close()
                                    st.success("Excluído.")
                                    st.rerun()

        # ── CLIENTES ──────────────────────────
        with tab_clientes:
            conn = sqlite3.connect('bel_global.db')
            df_cli = pd.read_sql_query("SELECT id, nome FROM clientes ORDER BY nome", conn)
            df_cli_cnt = pd.read_sql_query(
                "SELECT cliente, COUNT(*) as total FROM producao WHERE cliente IS NOT NULL AND cliente!='' GROUP BY cliente", conn)
            conn.close()

            st.markdown('<p class="secao-titulo">➕ Novo Cliente</p>', unsafe_allow_html=True)
            with st.form("form_novo_cli", clear_on_submit=True):
                col_inp, col_btn = st.columns([3, 1])
                with col_inp:
                    novo_cli = st.text_input("c", label_visibility="collapsed",
                                             placeholder="Nome do cliente").strip()
                with col_btn:
                    if st.form_submit_button("➕ Inserir", use_container_width=True) and novo_cli:
                        try:
                            conn = sqlite3.connect('bel_global.db')
                            conn.execute("INSERT INTO clientes (nome) VALUES (?)", (novo_cli,))
                            conn.commit()
                            st.success(f"Cliente '{novo_cli}' cadastrado!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(f"Cliente '{novo_cli}' já existe.")
                        finally:
                            conn.close()

            st.markdown("---")
            st.markdown('<p class="secao-titulo">📋 Clientes Cadastrados</p>', unsafe_allow_html=True)

            if df_cli.empty:
                st.info("Nenhum cliente cadastrado ainda.")
            else:
                col_lista, col_acao = st.columns([2, 1])
                with col_lista:
                    df_disp = df_cli.merge(df_cli_cnt, left_on='nome', right_on='cliente', how='left')
                    df_disp['total'] = df_disp['total'].fillna(0).astype(int)
                    st.dataframe(df_disp[['nome','total']].rename(
                        columns={'nome':'Cliente','total':'Balanças vinculadas'}),
                        use_container_width=True, hide_index=True)
                with col_acao:
                    st.markdown("**Editar / Excluir**")
                    cli_id = st.selectbox("Selecione", df_cli['id'].tolist(),
                        format_func=lambda i: df_cli[df_cli['id']==i]['nome'].values[0],
                        index=None, placeholder="Escolha...", key="sel_cli")
                    if cli_id:
                        nome_cli = df_cli[df_cli['id']==cli_id]['nome'].values[0]
                        with st.form("form_edit_cli", clear_on_submit=False):
                            nn_cli = st.text_input("Nome", value=nome_cli)
                            b1, b2 = st.columns(2)
                            salvar_c  = b1.form_submit_button("💾 Salvar", use_container_width=True)
                            excluir_c = b2.form_submit_button("🗑️ Excluir", use_container_width=True)
                            if salvar_c and nn_cli.strip():
                                try:
                                    conn = sqlite3.connect('bel_global.db')
                                    conn.execute("UPDATE clientes SET nome=? WHERE id=?", (nn_cli.strip(), cli_id))
                                    conn.execute("UPDATE producao SET cliente=? WHERE cliente=?", (nn_cli.strip(), nome_cli))
                                    conn.commit()
                                    st.success("Atualizado!")
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Nome já existe.")
                                finally:
                                    conn.close()
                            if excluir_c:
                                conn = sqlite3.connect('bel_global.db')
                                em_uso = conn.execute("SELECT COUNT(*) FROM producao WHERE cliente=?", (nome_cli,)).fetchone()[0]
                                conn.close()
                                if em_uso:
                                    st.error(f"Em uso por {em_uso} balança(s).")
                                else:
                                    conn = sqlite3.connect('bel_global.db')
                                    conn.execute("DELETE FROM clientes WHERE id=?", (cli_id,))
                                    conn.commit(); conn.close()
                                    st.success("Excluído.")
                                    st.rerun()

        # ── DIs / RECEBIMENTO ─────────────────
        with tab_dis:
            conn = sqlite3.connect('bel_global.db')
            lista_modelos = [m[0] for m in conn.execute("SELECT nome FROM modelos ORDER BY nome").fetchall()]
            conn.close()

            # ── Formulário de entrada ──────────
            st.markdown('<p class="secao-titulo">➕ Registrar Nova Entrada de Equipamentos</p>', unsafe_allow_html=True)

            if not lista_modelos:
                st.warning("Cadastre pelo menos um modelo na aba **🏷️ Modelos** antes de registrar uma DI.")
            else:
                # Cabeçalho da DI (fora do form, para poder usar session_state com blocos dinâmicos)
                col_di1, col_di2 = st.columns(2)
                with col_di1:
                    di_numero = st.text_input("Número da DI (ex: DI26034)", key="di_numero_input")
                with col_di2:
                    lote_nome = st.text_input("Lote Interno (ex: BEL26-005)", key="lote_input")

                st.markdown("---")
                st.markdown("**Modelos e Seriais desta DI**")
                st.markdown(
                    '<div class="info-box">Uma DI pode conter múltiplos modelos. Adicione um bloco por modelo.</div>',
                    unsafe_allow_html=True
                )

                # Controle de quantos blocos de modelo existem
                if 'num_blocos' not in st.session_state:
                    st.session_state.num_blocos = 1

                col_add, _ = st.columns([1, 3])
                with col_add:
                    if st.button("➕ Adicionar outro modelo", key="btn_add_bloco"):
                        st.session_state.num_blocos += 1
                        st.rerun()

                st.markdown("")

                # Renderiza os blocos
                blocos = []
                for i in range(st.session_state.num_blocos):
                    with st.container():
                        st.markdown(f'<div class="modelo-bloco">', unsafe_allow_html=True)
                        st.markdown(f"**Modelo {i+1}**")
                        col_m, col_rem = st.columns([4, 1])
                        with col_m:
                            mod_escolhido = st.selectbox(
                                f"Modelo", lista_modelos,
                                index=None, placeholder="Selecione o modelo...",
                                key=f"modelo_bloco_{i}"
                            )
                        with col_rem:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.session_state.num_blocos > 1:
                                if st.button("🗑️", key=f"rem_bloco_{i}", help="Remover este bloco"):
                                    st.session_state.num_blocos -= 1
                                    # Limpa as keys deste bloco
                                    for k in [f"modelo_bloco_{i}", f"seriais_bloco_{i}"]:
                                        if k in st.session_state:
                                            del st.session_state[k]
                                    st.rerun()

                        seriais_bloco = st.text_area(
                            f"Seriais do modelo acima (um por linha)",
                            height=120,
                            placeholder="Ex:\nCHBR2600101\nCHBR2600102",
                            key=f"seriais_bloco_{i}"
                        )
                        st.markdown('</div>', unsafe_allow_html=True)
                        blocos.append((mod_escolhido, seriais_bloco))

                st.markdown("")
                if st.button("📥 Dar Entrada no Estoque", type="primary", use_container_width=True):
                    di_val   = st.session_state.get("di_numero_input", "").strip()
                    lote_val = st.session_state.get("lote_input", "").strip()

                    # Validações
                    erros_val = []
                    if not lote_val:
                        erros_val.append("Lote Interno")
                    blocos_validos = [(m, s) for m, s in blocos if m and s and s.strip()]
                    if not blocos_validos:
                        erros_val.append("ao menos um modelo com seriais")

                    if erros_val:
                        st.error(f"Preencha: {', '.join(erros_val)}.")
                    else:
                        conn = sqlite3.connect('bel_global.db')
                        total_ok, total_dup = 0, []
                        for (modelo_v, seriais_v) in blocos_validos:
                            lista_sn = [s.strip() for s in seriais_v.split('\n') if s.strip()]
                            for sn in lista_sn:
                                try:
                                    conn.execute(
                                        'INSERT INTO producao (lote, di, modelo, serial_china, status) VALUES (?, ?, ?, ?, ?)',
                                        (lote_val, di_val, modelo_v, sn, "Disponível")
                                    )
                                    total_ok += 1
                                except sqlite3.IntegrityError:
                                    total_dup.append(sn)
                        conn.commit(); conn.close()

                        if total_ok:
                            st.success(f"✅ {total_ok} equipamento(s) registrado(s) como Disponível.")
                        if total_dup:
                            st.error(f"🚫 Seriais já existentes (ignorados): {', '.join(total_dup)}")

                        # Reset blocos
                        st.session_state.num_blocos = 1
                        st.rerun()

            st.markdown("---")

            # ── Resumo DIs ─────────────────────
            st.markdown('<p class="secao-titulo">📋 DIs Registradas</p>', unsafe_allow_html=True)

            conn = sqlite3.connect('bel_global.db')
            df_di_resumo = pd.read_sql_query("""
                SELECT
                    di                                                    AS "DI",
                    MIN(lote)                                             AS "Lote",
                    COUNT(*)                                              AS "Total",
                    SUM(CASE WHEN status='Disponível' THEN 1 ELSE 0 END) AS "Em Estoque",
                    SUM(CASE WHEN status='Finalizado' THEN 1 ELSE 0 END) AS "Finalizadas",
                    GROUP_CONCAT(DISTINCT modelo)                         AS "Modelos"
                FROM producao
                WHERE di IS NOT NULL AND di != ''
                GROUP BY di ORDER BY di DESC
            """, conn)
            conn.close()

            if df_di_resumo.empty:
                st.info("Nenhuma DI registrada ainda.")
            else:
                st.dataframe(df_di_resumo, use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown('<p class="secao-titulo">🔎 Detalhar uma DI</p>', unsafe_allow_html=True)

                di_escolhida = st.selectbox(
                    "Selecione a DI",
                    df_di_resumo['DI'].tolist(),
                    index=None, placeholder="Clique para escolher uma DI..."
                )

                if di_escolhida:
                    conn = sqlite3.connect('bel_global.db')
                    df_det = pd.read_sql_query("""
                        SELECT serial_china  AS "Serial China",
                               serial_brasil AS "Serial Brasil",
                               modelo        AS "Modelo",
                               lote          AS "Lote",
                               cliente       AS "Cliente",
                               pedido        AS "Pedido",
                               status        AS "Status"
                        FROM producao WHERE di=? ORDER BY modelo, serial_china
                    """, conn, params=(di_escolhida,))
                    conn.close()

                    st.markdown(f"**{len(df_det)} balança(s) na DI {di_escolhida}:**")
                    st.dataframe(df_det.style.map(color_status, subset=['Status']),
                                 use_container_width=True, hide_index=True)

                    st.download_button(
                        label=f"⬇️ Exportar DI {di_escolhida} para Excel",
                        data=gerar_excel_calibrado(df_det),
                        file_name=f"DI_{di_escolhida}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    # ══════════════════════════════════════════
    # BANCADA DE AFERIÇÃO
    # ══════════════════════════════════════════
    elif menu == "🔬 Bancada de Aferição":
        st.title("🔬 Bancada de Calibração")

        conn = sqlite3.connect('bel_global.db')
        lista_clientes = [c[0] for c in conn.execute("SELECT nome FROM clientes ORDER BY nome").fetchall()]
        conn.close()

        col1, col2 = st.columns(2)
        with col1:
            pedido_sel = st.text_input("Número do Pedido Comercial")
        with col2:
            cliente_sel = st.selectbox("Cliente Destino", lista_clientes,
                                       index=None, placeholder="Selecione o cliente...")

        st.markdown("---")
        st.subheader("1️⃣ Baixe o Template em Branco")
        st.markdown(
            '<div class="info-box">Preencha a planilha na bancada com os seriais e dados de calibração. Depois faça o upload abaixo.</div>',
            unsafe_allow_html=True
        )

        st.download_button(
            label="⬇️ Baixar Planilha de Calibração",
            data=gerar_template_calibracao(),
            file_name="Planilha_Afericao_Bel.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("---")
        st.subheader("2️⃣ Suba a Planilha Preenchida")
        arquivo = st.file_uploader("Arraste o arquivo Excel preenchido aqui", type=['xlsx'])

        if arquivo:
            df_importado = pd.read_excel(arquivo).dropna(how='all')
            st.write("Pré-visualização:")
            st.dataframe(df_importado, use_container_width=True)

            if st.button("💾 Validar e Salvar Lote de Calibração"):
                if not cliente_sel or not pedido_sel:
                    st.error("⚠️ Informe o Cliente e o Número do Pedido antes de salvar!")
                elif "Serial_China" not in df_importado.columns:
                    st.error("⚠️ Use o template correto baixado no passo 1.")
                else:
                    conn = sqlite3.connect('bel_global.db')
                    sucessos, erros = 0, []
                    for _, row in df_importado.iterrows():
                        sc = str(row["Serial_China"]).strip() if not pd.isna(row["Serial_China"]) else ""
                        if not sc:
                            continue
                        check = conn.execute(
                            "SELECT id FROM producao WHERE serial_china=? AND status='Disponível'", (sc,)
                        ).fetchone()
                        if check:
                            def s(col): return "" if pd.isna(row.get(col)) else str(row.get(col)).strip()
                            conn.execute('''UPDATE producao SET
                                cliente=?, pedido=?, serial_brasil=?,
                                valor_antes=?, valor_depois=?,
                                exc_se=?, exc_sd=?, exc_ie=?, exc_id=?,
                                carga_maxima=?, zero=?, status=?
                                WHERE serial_china=?''',
                                (cliente_sel, pedido_sel, s("Novo_Serial_Brasil"),
                                 s("Valor_Antes"), s("Valor_Depois"),
                                 s("Exc_Sup_Esq"), s("Exc_Sup_Dir"),
                                 s("Exc_Inf_Esq"), s("Exc_Inf_Dir"),
                                 s("Carga_Max"), s("Zero"),
                                 "Finalizado", sc))
                            sucessos += 1
                        else:
                            erros.append(sc)
                    conn.commit(); conn.close()
                    if sucessos:
                        st.success(f"✅ {sucessos} balança(s) calibrada(s) e vinculada(s) ao pedido {pedido_sel}!")
                    if erros:
                        st.warning(f"⚠️ Seriais não encontrados ou já finalizados: {', '.join(erros)}")

    # ══════════════════════════════════════════
    # CONSULTA
    # ══════════════════════════════════════════
    elif menu == "🔍 Consulta":
        st.title("🔍 Consulta e Inventário Global")

        busca = st.text_input("🔎 Buscar por Serial, Lote, DI, Pedido ou Cliente:")

        conn = sqlite3.connect('bel_global.db')
        query = '''SELECT di AS "DI", lote AS "Lote", modelo AS "Modelo",
                          cliente AS "Cliente", pedido AS "Pedido",
                          serial_china AS "Serial China", serial_brasil AS "Serial Brasil",
                          status AS "Status"
                   FROM producao'''
        if busca:
            query += f""" WHERE lote LIKE '%{busca}%' OR di LIKE '%{busca}%'
                           OR serial_china LIKE '%{busca}%' OR serial_brasil LIKE '%{busca}%'
                           OR cliente LIKE '%{busca}%' OR pedido LIKE '%{busca}%'"""
        query += " ORDER BY id DESC"

        df = pd.read_sql_query(query, conn)
        conn.close()

        if not df.empty:
            st.markdown(f"**{len(df)} registro(s) encontrado(s)**")
            st.dataframe(df.style.map(color_status, subset=['Status']),
                         use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Exportar para Excel",
                data=gerar_excel_calibrado(df),
                file_name="consulta_bel.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Nenhum registro encontrado.")

    # ══════════════════════════════════════════
    # CONFIGURAÇÕES
    # ══════════════════════════════════════════
    elif menu == "⚙️  Configurações":
        st.title("⚙️ Configurações do Sistema")
        st.markdown("---")
        st.subheader("⚠️ Zona de Manutenção")
        st.warning("Esta ação apaga **todos os dados** do sistema permanentemente e não pode ser desfeita.")
        confirmar = st.checkbox("Confirmo que desejo apagar todos os dados")
        if confirmar:
            if st.button("🚨 RESETAR SISTEMA", type="primary"):
                conn = sqlite3.connect('bel_global.db')
                conn.execute("DROP TABLE IF EXISTS modelos")
                conn.execute("DROP TABLE IF EXISTS clientes")
                conn.execute("DROP TABLE IF EXISTS producao")
                conn.commit(); conn.close()
                st.cache_data.clear()
                init_db()
                st.success("Banco de dados recriado do zero!")
                st.rerun()

# ══════════════════════════════════════════════
# CHINA
# ══════════════════════════════════════════════
elif unidade == "China (Factory)":
    st.title("🇨🇳 China Production Interface")
    st.info("Módulo em desenvolvimento para a fábrica.")

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
    2. **Bancada de Aferição** — Importe os dados técnicos de calibração via planilha
    3. **Consulta** — Pesquise qualquer balança por serial, lote, DI ou cliente
    4. **Dashboard** — Acompanhe o status geral do inventário

    """)
