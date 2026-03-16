import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
import io
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# ══════════════════════════════════════════════
# BANCO DE DADOS
# ══════════════════════════════════════════════
def get_conn():
    url = st.secrets["DATABASE_URL"]
    return psycopg2.connect(url, sslmode="require", connect_timeout=10)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS modelos (id SERIAL PRIMARY KEY, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (id SERIAL PRIMARY KEY, nome TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS producao
                 (id SERIAL PRIMARY KEY,
                  di TEXT, modelo TEXT, modelo_original TEXT, cliente TEXT,
                  serial_china TEXT UNIQUE, serial_brasil TEXT,
                  pedido TEXT, valor_antes TEXT, valor_depois TEXT,
                  exc_se TEXT, exc_sd TEXT, exc_ie TEXT, exc_id TEXT,
                  carga_maxima TEXT, zero TEXT, numero_lacre TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

def query_df(sql, params=None):
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df

def execute(sql, params=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(sql, params or ())
    conn.commit()
    conn.close()

def executemany_safe(rows_sql, rows_data, serial_idx=2):
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
            dup.append(data[serial_idx])
    conn.close()
    return ok, dup

def parsear_seriais(texto: str) -> list:
    import re
    tokens = re.split(r'[\n\r,;\t ]+', texto.strip())
    return [t.strip() for t in tokens if t.strip()]

# ══════════════════════════════════════════════
# CHIPS CLICÁVEIS POR MODELO
# ══════════════════════════════════════════════
def chips_selecao(df_disp: pd.DataFrame, key: str) -> list:
    state_key = f"chips_sel_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = set()

    selecionados = st.session_state[state_key]
    # Remove seriais que não estão mais no df (ex: após filtro de DI)
    seriais_validos = set(df_disp['Serial_China'].tolist())
    st.session_state[state_key] = selecionados & seriais_validos
    selecionados = st.session_state[state_key]

    modelos = sorted(df_disp['Modelo'].unique().tolist())
    total_disp = len(df_disp)
    total_sel  = len(selecionados)

    st.markdown(f"**{total_disp} balança(s) disponível(is) — {total_sel} selecionada(s)**")

    col_a, col_b, _ = st.columns([1.2, 1.2, 5])
    if col_a.button("✅ Selecionar tudo", key=f"sel_all_{key}"):
        st.session_state[state_key] = set(df_disp['Serial_China'].tolist())
        st.rerun()
    if col_b.button("❌ Limpar seleção", key=f"clr_all_{key}"):
        st.session_state[state_key] = set()
        st.rerun()

    for modelo in modelos:
        seriais = df_disp[df_disp['Modelo'] == modelo]['Serial_China'].tolist()
        sel_modelo = [s for s in seriais if s in selecionados]
        st.markdown(
            f"<div style='margin-top:14px; margin-bottom:6px; font-size:14px; font-weight:700;'>"
            f"📦 {modelo} "
            f"<span style='font-weight:400; font-size:12px; opacity:0.6;'>"
            f"({len(sel_modelo)}/{len(seriais)} selecionadas)</span></div>",
            unsafe_allow_html=True)

        cols_por_linha = 8
        for i in range(0, len(seriais), cols_por_linha):
            grupo = seriais[i:i+cols_por_linha]
            cols  = st.columns(len(grupo))
            for j, sn in enumerate(grupo):
                is_sel   = sn in selecionados
                label    = f"✓ {sn}" if is_sel else sn
                btn_type = "primary" if is_sel else "secondary"
                if cols[j].button(label, key=f"chip_{key}_{sn}",
                                  type=btn_type, use_container_width=True):
                    if is_sel:
                        st.session_state[state_key].discard(sn)
                    else:
                        st.session_state[state_key].add(sn)
                    st.rerun()

    return list(st.session_state[state_key])

# ══════════════════════════════════════════════
# GERAÇÃO DE PDF
# ══════════════════════════════════════════════
def gerar_pdf_relatorio(row) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    cor_bel  = colors.HexColor('#1a1a2e')
    cor_azul = colors.HexColor('#0066cc')

    s_titulo = ParagraphStyle('t', fontSize=18, textColor=cor_bel,
                              fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=4)
    s_sub    = ParagraphStyle('s', fontSize=10, textColor=colors.grey,
                              alignment=TA_CENTER, spaceAfter=2)
    s_secao  = ParagraphStyle('sec', fontSize=11, textColor=cor_azul,
                              fontName='Helvetica-Bold', spaceBefore=14, spaceAfter=6)
    s_rodape = ParagraphStyle('r', fontSize=8, textColor=colors.grey, alignment=TA_CENTER)

    def t_info(dados):
        t = Table(dados, colWidths=[4.5*cm, 5.5*cm, 4.5*cm, 5.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f0f4ff')),
            ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f0f4ff')),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        return t

    def t_dados(dados, hcor):
        t = Table(dados, colWidths=[5*cm, 5*cm, 5*cm, 5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), hcor),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#f8f9fa')),
        ]))
        return t

    el = []
    el.append(Paragraph("BEL EQUIPAMENTOS ANALÍTICOS LTDA", s_titulo))
    el.append(Paragraph("Rua Alferes José Caetano, 1572 — Piracicaba / SP", s_sub))
    el.append(Paragraph("INMETRO/DIMEL nº 0008/2018", s_sub))
    el.append(Spacer(1, 0.3*cm))
    el.append(HRFlowable(width="100%", thickness=2, color=cor_bel))
    el.append(Spacer(1, 0.3*cm))
    el.append(Paragraph("RELATÓRIO DE AFERIÇÃO", s_titulo))
    el.append(Spacer(1, 0.4*cm))

    el.append(Paragraph("Identificação do Equipamento", s_secao))
    el.append(t_info([
        ["Serial Brasil (Inmetro)", row.get('serial_brasil') or '—',
         "Serial China (Fábrica)",  row.get('serial_china') or '—'],
        ["Modelo Final", row.get('modelo') or '—',
         "Modelo Original", row.get('modelo_original') or '(sem transformação)'],
        ["DI", row.get('di') or '—',
         "Nº do Lacre", row.get('numero_lacre') or '—'],
    ]))

    el.append(Paragraph("Destino Comercial", s_secao))
    el.append(t_info([
        ["Cliente", row.get('cliente') or '—', "Pedido", row.get('pedido') or '—'],
    ]))

    el.append(Paragraph("Dados de Calibração", s_secao))
    el.append(t_dados([
        ["Indicação Antes", "Indicação Depois", "Carga Máxima", "Zero"],
        [row.get('valor_antes') or '—', row.get('valor_depois') or '—',
         row.get('carga_maxima') or '—', row.get('zero') or '—'],
    ], cor_bel))

    el.append(Paragraph("Teste de Excentricidade (4 cantos)", s_secao))
    el.append(t_dados([
        ["Sup. Esquerdo", "Sup. Direito", "Inf. Esquerdo", "Inf. Direito"],
        [row.get('exc_se') or '—', row.get('exc_sd') or '—',
         row.get('exc_ie') or '—', row.get('exc_id') or '—'],
    ], colors.HexColor('#2d4060')))

    el.append(Spacer(1, 1*cm))
    el.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cccccc')))
    el.append(Spacer(1, 0.3*cm))
    el.append(Paragraph(
        "Documento gerado pelo Sistema de Rastreabilidade — Bel Equipamentos Analíticos Ltda",
        s_rodape))

    doc.build(el)
    return buf.getvalue()

# ══════════════════════════════════════════════
# EXCEL HELPERS
# ══════════════════════════════════════════════
def estilizar_excel(ws, df):
    for i, col in enumerate(df.columns, 1):
        max_len = max(len(str(col)), df[col].astype(str).map(len).max() if not df.empty else 0)
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
    df_out = df_sel[["Serial_China", "Modelo", "DI"]].copy()
    for col in ["Novo_Serial_Brasil","Numero_Lacre","Valor_Antes","Valor_Depois",
                "Exc_Sup_Esq","Exc_Sup_Dir","Exc_Inf_Esq","Exc_Inf_Dir","Carga_Max","Zero"]:
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
# CONFIG STREAMLIT
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
    h2 { border-bottom: 2px solid rgba(128,128,128,0.3); padding-bottom: 8px; }
    [data-testid="metric-container"] {
        border: 1px solid rgba(128,128,128,0.3); border-radius: 8px; padding: 12px;
    }
    .info-box {
        background: rgba(0,102,204,0.1); border-left: 4px solid #0066cc;
        border-radius: 4px; padding: 12px 16px; margin: 8px 0; font-size: 14px;
    }
    .secao-titulo { font-size: 17px; font-weight: 600; margin-top: 8px; margin-bottom: 2px; }
    .detalhe-serial-br    { font-size: 26px; color: #4da6ff; font-weight: 700; }
    .detalhe-serial-china { font-size: 14px; color: #888; margin-top: 4px; }
    .detalhe-label        { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
    .badge-disponivel { background:#0066cc; color:#fff; padding:4px 12px; border-radius:12px; font-size:13px; }
    .badge-pronta     { background:#7b2d8b; color:#fff; padding:4px 12px; border-radius:12px; font-size:13px; }
    .badge-finalizado { background:#007a33; color:#fff; padding:4px 12px; border-radius:12px; font-size:13px; }
</style>
""", unsafe_allow_html=True)

def color_status(val):
    if val == 'Disponível':     return 'color: #0066cc; font-weight: bold'
    if val == 'Finalizado':     return 'color: #007a33; font-weight: bold'
    if val == 'Pronta Entrega': return 'color: #7b2d8b; font-weight: bold'
    return 'color: #cc6600; font-weight: bold'

# ══════════════════════════════════════════════
# MENU LATERAL
# ══════════════════════════════════════════════
st.sidebar.title("🌐 Bel Engineering")
st.sidebar.markdown("**Sistema de Rastreabilidade**")
st.sidebar.markdown("---")
unidade = st.sidebar.selectbox("Unidade Operacional", ["Brasil", "China (Factory)"],
    index=None, placeholder="Selecione a unidade...")

if unidade == "Brasil":
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Navegação", [
        "📊 Dashboard", "📋 Gestão de Cadastros", "🔬 Bancada de Aferição",
        "📦 Pronta Entrega", "🔍 Consulta", "⚙️  Configurações",
    ])

    # ══════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════
    if menu == "📊 Dashboard":
        st.title("📊 Dashboard — Visão Geral")
        df_all = query_df("SELECT status, modelo, di FROM producao")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total", len(df_all))
        c2.metric("🔵 Disponíveis",   len(df_all[df_all['status']=='Disponível']))
        c3.metric("🟣 Pronta Entrega",len(df_all[df_all['status']=='Pronta Entrega']))
        c4.metric("🟢 Finalizadas",   len(df_all[df_all['status']=='Finalizado']))
        if not df_all.empty:
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Por Status")
                df_s = df_all['status'].value_counts().reset_index()
                df_s.columns = ['Status','Quantidade']
                st.dataframe(df_s, use_container_width=True, hide_index=True)
            with col2:
                st.subheader("Por Modelo")
                df_m = df_all['modelo'].value_counts().reset_index()
                df_m.columns = ['Modelo','Quantidade']
                st.dataframe(df_m, use_container_width=True, hide_index=True)
            st.markdown("---")
            st.subheader("Por DI")
            df_di = query_df("""
                SELECT di AS "DI", COUNT(*) AS "Total",
                       SUM(CASE WHEN status='Disponível'     THEN 1 ELSE 0 END) AS "Disponíveis",
                       SUM(CASE WHEN status='Pronta Entrega' THEN 1 ELSE 0 END) AS "Pronta Entrega",
                       SUM(CASE WHEN status='Finalizado'     THEN 1 ELSE 0 END) AS "Finalizadas",
                       STRING_AGG(DISTINCT modelo, ', ') AS "Modelos"
                FROM producao WHERE di IS NOT NULL AND di!='' GROUP BY di ORDER BY di DESC
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
        tab_mod, tab_cli, tab_dis = st.tabs(["🏷️  Modelos","👥 Clientes","🚢 DIs / Recebimento"])

        with tab_mod:
            df_mod = query_df("SELECT id, nome FROM modelos ORDER BY nome")
            st.markdown('<p class="secao-titulo">➕ Novo Modelo</p>', unsafe_allow_html=True)
            with st.form("form_mod", clear_on_submit=True):
                ci, cb = st.columns([3,1])
                nm_new = ci.text_input("m", label_visibility="collapsed", placeholder="Nome do modelo").strip()
                if cb.form_submit_button("➕ Inserir", use_container_width=True) and nm_new:
                    try:
                        execute("INSERT INTO modelos (nome) VALUES (%s)", (nm_new,))
                        st.success(f"Modelo '{nm_new}' cadastrado!")
                        st.rerun()
                    except Exception:
                        st.error("Modelo já existe.")
            st.markdown("---")
            if df_mod.empty:
                st.info("Nenhum modelo cadastrado ainda.")
            else:
                cl, ca = st.columns([2,1])
                with cl:
                    st.dataframe(df_mod[['nome']].rename(columns={'nome':'Modelo'}),
                                 use_container_width=True, hide_index=True)
                with ca:
                    st.markdown("**Editar / Excluir**")
                    mid = st.selectbox("s", df_mod['id'].tolist(),
                        format_func=lambda i: df_mod[df_mod['id']==i]['nome'].values[0],
                        index=None, placeholder="Escolha...", key="sel_mod", label_visibility="collapsed")
                    if mid:
                        nm = df_mod[df_mod['id']==mid]['nome'].values[0]
                        with st.form("form_edit_mod"):
                            nn = st.text_input("Nome", value=nm)
                            b1,b2 = st.columns(2)
                            if b1.form_submit_button("💾 Salvar", use_container_width=True):
                                try:
                                    execute("UPDATE modelos SET nome=%s WHERE id=%s", (nn.strip(), mid))
                                    st.success("Atualizado!")
                                    st.rerun()
                                except Exception:
                                    st.error("Nome já existe.")
                            if b2.form_submit_button("🗑️ Excluir", use_container_width=True):
                                n = query_df("SELECT COUNT(*) as n FROM producao WHERE modelo=%s", (nm,))['n'].values[0]
                                if n:
                                    st.error(f"Em uso por {n} balança(s).")
                                else:
                                    execute("DELETE FROM modelos WHERE id=%s", (mid,))
                                    st.success("Excluído.")
                                    st.rerun()

        with tab_cli:
            df_cli = query_df("SELECT id, nome FROM clientes ORDER BY nome")
            df_cnt = query_df("SELECT cliente, COUNT(*) as total FROM producao WHERE cliente IS NOT NULL AND cliente!='' GROUP BY cliente")
            st.markdown('<p class="secao-titulo">➕ Novo Cliente</p>', unsafe_allow_html=True)
            with st.form("form_cli", clear_on_submit=True):
                ci, cb = st.columns([3,1])
                nc_new = ci.text_input("c", label_visibility="collapsed", placeholder="Nome do cliente").strip()
                if cb.form_submit_button("➕ Inserir", use_container_width=True) and nc_new:
                    try:
                        execute("INSERT INTO clientes (nome) VALUES (%s)", (nc_new,))
                        st.success(f"Cliente '{nc_new}' cadastrado!")
                        st.rerun()
                    except Exception:
                        st.error("Cliente já existe.")
            st.markdown("---")
            if df_cli.empty:
                st.info("Nenhum cliente cadastrado ainda.")
            else:
                cl, ca = st.columns([2,1])
                with cl:
                    df_d = df_cli.merge(df_cnt, left_on='nome', right_on='cliente', how='left')
                    df_d['total'] = df_d['total'].fillna(0).astype(int)
                    st.dataframe(df_d[['nome','total']].rename(columns={'nome':'Cliente','total':'Balanças'}),
                                 use_container_width=True, hide_index=True)
                with ca:
                    st.markdown("**Editar / Excluir**")
                    cid = st.selectbox("s", df_cli['id'].tolist(),
                        format_func=lambda i: df_cli[df_cli['id']==i]['nome'].values[0],
                        index=None, placeholder="Escolha...", key="sel_cli", label_visibility="collapsed")
                    if cid:
                        nc = df_cli[df_cli['id']==cid]['nome'].values[0]
                        with st.form("form_edit_cli"):
                            nn = st.text_input("Nome", value=nc)
                            b1,b2 = st.columns(2)
                            if b1.form_submit_button("💾 Salvar", use_container_width=True):
                                try:
                                    execute("UPDATE clientes SET nome=%s WHERE id=%s", (nn.strip(), cid))
                                    execute("UPDATE producao SET cliente=%s WHERE cliente=%s", (nn.strip(), nc))
                                    st.success("Atualizado!")
                                    st.rerun()
                                except Exception:
                                    st.error("Nome já existe.")
                            if b2.form_submit_button("🗑️ Excluir", use_container_width=True):
                                n = query_df("SELECT COUNT(*) as n FROM producao WHERE cliente=%s", (nc,))['n'].values[0]
                                if n:
                                    st.error(f"Em uso por {n} balança(s).")
                                else:
                                    execute("DELETE FROM clientes WHERE id=%s", (cid,))
                                    st.success("Excluído.")
                                    st.rerun()

        with tab_dis:
            lista_mod = query_df("SELECT nome FROM modelos ORDER BY nome")['nome'].tolist()
            st.markdown('<p class="secao-titulo">➕ Registrar Nova Entrada</p>', unsafe_allow_html=True)
            if not lista_mod:
                st.warning("Cadastre pelo menos um modelo antes de registrar uma DI.")
            else:
                di_num = st.text_input("Número da DI (ex: DI26034)", key="di_input")
                st.markdown("---")
                if 'num_blocos' not in st.session_state:
                    st.session_state.num_blocos = 1
                if st.button("➕ Adicionar outro modelo"):
                    st.session_state.num_blocos += 1
                    st.rerun()
                blocos = []
                for i in range(st.session_state.num_blocos):
                    st.markdown(f"**Modelo {i+1}**")
                    cm_c, cr_c = st.columns([4,1])
                    mod_b = cm_c.selectbox("Modelo", lista_mod, index=None,
                        placeholder="Selecione...", key=f"mod_bloco_{i}")
                    with cr_c:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.session_state.num_blocos > 1:
                            if st.button("🗑️", key=f"rem_{i}"):
                                st.session_state.num_blocos -= 1
                                st.rerun()
                    sn_b = st.text_area("Seriais (um por linha ou separados por espaço/vírgula)",
                        height=110, key=f"sn_bloco_{i}")
                    if sn_b and sn_b.strip():
                        st.caption(f"{len(parsear_seriais(sn_b))} serial(is) detectado(s)")
                    blocos.append((mod_b, sn_b))
                    st.markdown("---")
                if st.button("📥 Dar Entrada no Estoque", type="primary", use_container_width=True):
                    di_v = st.session_state.get("di_input","").strip()
                    validos = [(m,s) for m,s in blocos if m and s and s.strip()]
                    if not validos:
                        st.error("Preencha ao menos um modelo com seriais.")
                    else:
                        rows = [(di_v, m, sn, "Disponível") for m,sv in validos for sn in parsear_seriais(sv)]
                        ok, dup = executemany_safe(
                            "INSERT INTO producao (di,modelo,serial_china,status) VALUES (%s,%s,%s,%s)",
                            rows, serial_idx=2)
                        if ok:  st.success(f"✅ {ok} equipamento(s) registrado(s).")
                        if dup: st.error(f"🚫 Duplicados: {', '.join(dup)}")
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
                FROM producao WHERE di IS NOT NULL AND di!='' GROUP BY di ORDER BY di DESC
            """)
            if df_di_res.empty:
                st.info("Nenhuma DI registrada ainda.")
            else:
                st.dataframe(df_di_res, use_container_width=True, hide_index=True)
                st.markdown("---")
                di_esc = st.selectbox("Detalhar DI:", df_di_res['DI'].tolist(),
                    index=None, placeholder="Escolha uma DI...")
                if di_esc:
                    df_det = query_df("""
                        SELECT serial_china AS "Serial China", serial_brasil AS "Serial Brasil",
                               modelo AS "Modelo", modelo_original AS "Modelo Original",
                               cliente AS "Cliente", pedido AS "Pedido", status AS "Status"
                        FROM producao WHERE di=%s ORDER BY modelo, serial_china
                    """, params=(di_esc,))
                    st.markdown(f"**{len(df_det)} balança(s):**")
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
        lista_clientes  = query_df("SELECT nome FROM clientes ORDER BY nome")['nome'].tolist()
        lista_todos_mod = query_df("SELECT nome FROM modelos ORDER BY nome")['nome'].tolist()
        df_disp = query_df("""
            SELECT id, serial_china AS "Serial_China", modelo AS "Modelo", di AS "DI"
            FROM producao WHERE status='Disponível' ORDER BY modelo, serial_china
        """)

        if df_disp.empty:
            st.warning("Não há balanças disponíveis no estoque.")
        else:
            st.subheader("1️⃣ Selecione as Balanças a Aferir")
            dis_disp  = ["Todas as DIs"] + sorted(df_disp['DI'].dropna().unique().tolist())
            filtro_di = st.selectbox("Filtrar por DI (opcional):", dis_disp, index=0)
            df_filt   = df_disp if filtro_di=="Todas as DIs" else df_disp[df_disp['DI']==filtro_di]

            selecionadas = chips_selecao(df_filt, key="bancada")

            if selecionadas:
                df_sel = df_filt[df_filt['Serial_China'].isin(selecionadas)].copy()

                # Passo 2: Transformação
                st.markdown("---")
                st.subheader("2️⃣ Verificar / Transformar Modelos")
                st.markdown('<div class="info-box">Se alguma balança será aferida com modelo diferente, selecione o novo modelo. Deixe "(manter original)" para não transformar.</div>', unsafe_allow_html=True)
                transformacoes = {}
                for _, row in df_sel.iterrows():
                    c1,c2,c3,c4 = st.columns([2,2,0.4,2])
                    c1.markdown(f"**`{row['Serial_China']}`**")
                    c2.markdown(f"Atual: **{row['Modelo']}**")
                    c3.markdown("→")
                    nm = c4.selectbox("n", ["(manter original)"]+lista_todos_mod,
                        index=0, key=f"transf_{row['Serial_China']}", label_visibility="collapsed")
                    if nm != "(manter original)":
                        transformacoes[row['Serial_China']] = nm
                if transformacoes:
                    st.markdown("**Transformações:**")
                    for sn,nm in transformacoes.items():
                        mo = df_sel[df_sel['Serial_China']==sn]['Modelo'].values[0]
                        st.markdown(f"- `{sn}`: {mo} → **{nm}**")

                # Passo 3: Destino
                st.markdown("---")
                st.subheader("3️⃣ Destino das Balanças")
                destino = st.radio("", ["Vincular a Cliente","Pronta Entrega"],
                    horizontal=True, label_visibility="collapsed")
                if destino == "Vincular a Cliente":
                    cc1, cc2 = st.columns(2)
                    pedido_sel  = cc1.text_input("Número do Pedido")
                    cliente_sel = cc2.selectbox("Cliente", lista_clientes,
                        index=None, placeholder="Selecione...")
                    status_dest = "Finalizado"
                else:
                    st.markdown('<div class="info-box">Balanças marcadas como <strong>Pronta Entrega</strong>. Cliente e pedido vinculados depois.</div>', unsafe_allow_html=True)
                    pedido_sel = cliente_sel = ""
                    status_dest = "Pronta Entrega"

                # Passo 4: Planilha
                st.markdown("---")
                st.subheader("4️⃣ Baixe a Planilha Pré-Preenchida")
                df_plan = df_sel.copy()
                for sn,nm in transformacoes.items():
                    df_plan.loc[df_plan['Serial_China']==sn,'Modelo'] = nm
                st.markdown('<div class="info-box">Planilha com <strong>Serial China</strong>, <strong>Modelo</strong> e <strong>DI</strong> já preenchidos. Preencha os dados de calibração, Serial Brasil e Número do Lacre na bancada.</div>', unsafe_allow_html=True)
                st.download_button(f"⬇️ Baixar Planilha ({len(selecionadas)} balança(s))",
                    data=gerar_planilha_afericao(df_plan), file_name="Afericao_Bel.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                # Passo 5: Upload
                st.markdown("---")
                st.subheader("5️⃣ Suba a Planilha Preenchida")
                arquivo = st.file_uploader("Arraste o Excel preenchido aqui", type=['xlsx'])
                if arquivo:
                    df_imp = pd.read_excel(arquivo).dropna(how='all')
                    st.dataframe(df_imp, use_container_width=True)
                    if st.button("💾 Validar e Salvar", type="primary"):
                        if destino=="Vincular a Cliente" and (not cliente_sel or not pedido_sel):
                            st.error("⚠️ Informe o Cliente e o Pedido.")
                        elif "Serial_China" not in df_imp.columns:
                            st.error("⚠️ Use o template gerado no passo 4.")
                        else:
                            conn = get_conn(); cur = conn.cursor()
                            ok, erros = 0, []
                            for _, row in df_imp.iterrows():
                                sc = str(row["Serial_China"]).strip() if not pd.isna(row.get("Serial_China")) else ""
                                if not sc: continue
                                cur.execute("SELECT id,modelo FROM producao WHERE serial_china=%s AND status='Disponível'", (sc,))
                                check = cur.fetchone()
                                if check:
                                    rid, mod_at = check
                                    def s(col): return "" if pd.isna(row.get(col)) else str(row.get(col)).strip()
                                    mf = s("Modelo") or mod_at
                                    mo = mod_at if mf != mod_at else None
                                    cur.execute('''UPDATE producao SET
                                        cliente=%s,pedido=%s,serial_brasil=%s,
                                        modelo=%s,modelo_original=%s,
                                        valor_antes=%s,valor_depois=%s,
                                        exc_se=%s,exc_sd=%s,exc_ie=%s,exc_id=%s,
                                        carga_maxima=%s,zero=%s,numero_lacre=%s,status=%s
                                        WHERE serial_china=%s''',
                                        (cliente_sel,pedido_sel,s("Novo_Serial_Brasil"),
                                         mf,mo,s("Valor_Antes"),s("Valor_Depois"),
                                         s("Exc_Sup_Esq"),s("Exc_Sup_Dir"),
                                         s("Exc_Inf_Esq"),s("Exc_Inf_Dir"),
                                         s("Carga_Max"),s("Zero"),s("Numero_Lacre"),
                                         status_dest,sc))
                                    ok += 1
                                else:
                                    erros.append(sc)
                            conn.commit(); conn.close()
                            if ok:    st.success(f"✅ {ok} balança(s) salvas!")
                            if erros: st.warning(f"⚠️ Não encontrados: {', '.join(erros)}")
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
            FROM producao WHERE status='Pronta Entrega' ORDER BY modelo, serial_brasil
        """)
        if df_pe.empty:
            st.info("Nenhuma balança em Pronta Entrega.")
        else:
            st.markdown(f"**{len(df_pe)} balança(s) disponível(is) para venda:**")
            st.dataframe(df_pe.drop(columns=['id']), use_container_width=True, hide_index=True)
            st.markdown("---")
            st.subheader("Vincular ao Cliente")
            opcoes  = df_pe.apply(lambda r: f"{r['Serial Brasil'] or r['Serial China']}  |  {r['Modelo']}  |  DI: {r['DI'] or '—'}", axis=1).tolist()
            ids_map = dict(zip(opcoes, df_pe['id'].tolist()))
            sel_pe  = st.multiselect("Selecione as balanças:", opcoes, placeholder="Clique para selecionar...")
            cc1,cc2 = st.columns(2)
            ped_pe  = cc1.text_input("Número do Pedido", key="pedido_pe")
            cli_pe  = cc2.selectbox("Cliente", lista_clientes, index=None, placeholder="Selecione...", key="cliente_pe")
            if sel_pe:
                st.markdown(f"**{len(sel_pe)} selecionada(s)**")
            if st.button("✅ Confirmar Venda", type="primary", disabled=not sel_pe):
                if not cli_pe or not ped_pe:
                    st.error("Informe o Cliente e o Pedido.")
                else:
                    conn = get_conn(); cur = conn.cursor()
                    for rid in [ids_map[s] for s in sel_pe]:
                        cur.execute("UPDATE producao SET cliente=%s,pedido=%s,status='Finalizado' WHERE id=%s",
                            (cli_pe, ped_pe, rid))
                    conn.commit(); conn.close()
                    st.success(f"✅ {len(sel_pe)} balança(s) vinculada(s) ao cliente {cli_pe}!")
                    st.rerun()

    # ══════════════════════════════════════════
    # CONSULTA
    # ══════════════════════════════════════════
    elif menu == "🔍 Consulta":
        st.title("🔍 Consulta e Inventário Global")

        if 'detalhe_id' in st.session_state and st.session_state.detalhe_id:
            row_df = query_df("""
                SELECT serial_china,serial_brasil,di,modelo,modelo_original,
                       cliente,pedido,valor_antes,valor_depois,
                       exc_se,exc_sd,exc_ie,exc_id,
                       carga_maxima,zero,numero_lacre,status
                FROM producao WHERE id=%s
            """, params=(st.session_state.detalhe_id,))
            if not row_df.empty:
                r = row_df.iloc[0].to_dict()
                cb, cp = st.columns([1,1])
                if cb.button("← Voltar"):
                    st.session_state.detalhe_id = None
                    st.rerun()
                if r['status'] in ('Finalizado','Pronta Entrega'):
                    sn = r.get('serial_brasil') or r.get('serial_china') or 'relatorio'
                    cp.download_button("📄 Baixar Relatório PDF",
                        data=gerar_pdf_relatorio(r),
                        file_name=f"Relatorio_{sn}.pdf",
                        mime="application/pdf", type="primary")
                st.markdown("---")
                st.markdown(f"""
                <div style="margin-bottom:20px;">
                    <div class="detalhe-label">Serial Brasil (Inmetro)</div>
                    <div class="detalhe-serial-br">{r.get('serial_brasil') or '—'}</div>
                    <div class="detalhe-serial-china">🇨🇳 Serial China: <strong>{r.get('serial_china') or '—'}</strong></div>
                </div>""", unsafe_allow_html=True)
                badge_map = {'Disponível':'badge-disponivel','Pronta Entrega':'badge-pronta','Finalizado':'badge-finalizado'}
                st.markdown(f'<span class="{badge_map.get(r["status"],"badge-disponivel")}">{r["status"]}</span>', unsafe_allow_html=True)
                st.markdown("---")
                c1,c2,c3,c4 = st.columns(4)
                c1.markdown(f"**Modelo Final**\n\n{r.get('modelo') or '—'}")
                c2.markdown(f"**Modelo Original**\n\n{r.get('modelo_original') or '(sem transformação)'}")
                c3.markdown(f"**DI**\n\n{r.get('di') or '—'}")
                c4.markdown(f"**Nº Lacre**\n\n{r.get('numero_lacre') or '—'}")
                c5,c6 = st.columns(2)
                c5.markdown(f"**Cliente**\n\n{r.get('cliente') or '—'}")
                c6.markdown(f"**Pedido**\n\n{r.get('pedido') or '—'}")
                if any([r.get(k) for k in ['valor_antes','valor_depois','exc_se','exc_sd','exc_ie','exc_id','carga_maxima','zero']]):
                    st.markdown("---")
                    st.subheader("📐 Dados de Calibração")
                    m1,m2,m3 = st.columns(3)
                    m1.metric("Valor Antes",  r.get('valor_antes')   or "—")
                    m2.metric("Valor Depois", r.get('valor_depois')  or "—")
                    m3.metric("Carga Máx",    r.get('carga_maxima')  or "—")
                    st.markdown("**Excentricidade:**")
                    e1,e2,e3,e4 = st.columns(4)
                    e1.metric("Sup. Esq", r.get('exc_se') or "—")
                    e2.metric("Sup. Dir", r.get('exc_sd') or "—")
                    e3.metric("Inf. Esq", r.get('exc_ie') or "—")
                    e4.metric("Inf. Dir", r.get('exc_id') or "—")
                    st.metric("Zero", r.get('zero') or "—")
        else:
            busca = st.text_input("🔎 Buscar por Serial, DI, Pedido, Cliente ou Modelo:")
            where, params = "", None
            if busca:
                where  = " WHERE di ILIKE %s OR serial_china ILIKE %s OR serial_brasil ILIKE %s OR cliente ILIKE %s OR pedido ILIKE %s OR modelo ILIKE %s"
                p      = f"%{busca}%"
                params = (p,p,p,p,p,p)
            df = query_df(f"""
                SELECT id, di AS "DI", modelo AS "Modelo", modelo_original AS "Modelo Original",
                       cliente AS "Cliente", pedido AS "Pedido",
                       serial_china AS "Serial China", serial_brasil AS "Serial Brasil",
                       numero_lacre AS "Nº Lacre", status AS "Status"
                FROM producao {where} ORDER BY id DESC
            """, params=params)
            if not df.empty:
                st.markdown(f"**{len(df)} registro(s)**")
                st.dataframe(df.drop(columns=['id']).style.map(color_status, subset=['Status']),
                             use_container_width=True, hide_index=True)
                st.markdown("---")
                opts = df.apply(lambda r: f"{r['Serial Brasil'] or r['Serial China']}  |  {r['Modelo']}  |  {r['Status']}", axis=1).tolist()
                sel  = st.selectbox("Ver detalhe:", range(len(opts)),
                    format_func=lambda i: opts[i], index=None, placeholder="Escolha...")
                if sel is not None:
                    st.session_state.detalhe_id = df['id'].tolist()[sel]
                    st.rerun()
                st.download_button("⬇️ Exportar Excel",
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
        st.warning("Esta ação apaga **todos os dados** permanentemente.")
        if st.checkbox("Confirmo que desejo apagar todos os dados"):
            if st.button("🚨 RESETAR SISTEMA", type="primary"):
                conn = get_conn(); c = conn.cursor()
                c.execute("DROP TABLE IF EXISTS modelos CASCADE")
                c.execute("DROP TABLE IF EXISTS clientes CASCADE")
                c.execute("DROP TABLE IF EXISTS producao CASCADE")
                conn.commit(); conn.close()
                init_db()
                st.success("Banco de dados recriado!")
                st.rerun()

elif unidade == "China (Factory)":
    st.title("🇨🇳 China Production Interface")
    st.info("Módulo em desenvolvimento.")

else:
    st.sidebar.info("👆 Selecione uma unidade para começar.")
    st.title("🔬 Bel Engineering — Traceability System")
    st.markdown("""
    ### Bem-vindo ao Sistema de Rastreabilidade Global
    Selecione a unidade operacional no menu lateral para acessar as ferramentas.
    ---
    **Fluxo operacional:**
    1. **Gestão de Cadastros** — Modelos, clientes e entrada de DIs
    2. **Bancada de Aferição** — Selecione balanças por modelo, transforme se necessário, baixe a planilha e importe
    3. **Pronta Entrega** — Vincule clientes quando a venda acontecer
    4. **Consulta** — Pesquise qualquer balança e gere o relatório PDF
    5. **Dashboard** — Visão geral do inventário
    """)
