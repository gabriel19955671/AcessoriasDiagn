# app.py — Acessórias (v4.2)
# Organização de filtros por aba (limpo e previsível)
# Sidebar: somente configurações gerais
# Abas: filtros locais (data + contexto), compactos e consistentes

import difflib
from datetime import datetime, date
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ==============================
# Config
# ==============================
st.set_page_config(page_title="Acessórias — Diagnóstico", layout="wide")
st.title("📊 Acessórias — Diagnóstico (v4.2)")
st.caption("Fluxo: ① Dados & Mapeamento → ② Ajuste filtros por aba → ③ Dashboards → ④ Export.")

# ==============================
# Leitura robusta (CSV/Excel)
# ==============================
def read_any_csv(uploaded_file) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1", "utf-16", "utf-16le", "utf-16be"]
    seps = [None, ";", ",", "|", "\t"]
    last_err = None
    for enc in encodings:
        for sep in seps:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, sep=sep, engine="python", encoding=enc, dtype=str)
            except Exception as e:
                last_err = e
                continue
    try:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    except Exception:
        st.error(f"Não consegui abrir o CSV. Último erro: {last_err}")
        raise

def try_read_excel(uploaded_file) -> pd.DataFrame:
    name = (getattr(uploaded_file, "name", "") or "").lower()

    def _try(fn, *a, **k):
        try:
            uploaded_file.seek(0)
            return fn(*a, **k)
        except Exception:
            return None

    if name.endswith((".xlsx", ".xlsm")):
        df = _try(pd.read_excel, uploaded_file, engine="openpyxl", dtype=str)
        if df is not None: return df
    if name.endswith(".xlsb"):
        df = _try(pd.read_excel, uploaded_file, engine="pyxlsb", dtype=str)
        if df is not None: return df
    if name.endswith(".xls"):
        df = _try(pd.read_excel, uploaded_file, engine="xlrd", dtype=str)
        if df is not None: return df
        df = _try(pd.read_excel, uploaded_file, engine="openpyxl", dtype=str)
        if df is not None: return df
    for eng in ("openpyxl", "pyxlsb", "xlrd"):
        df = _try(pd.read_excel, uploaded_file, engine=eng, dtype=str)
        if df is not None: return df

    uploaded_file.seek(0)
    return read_any_csv(uploaded_file)

# ==============================
# Helpers / Normalização
# ==============================
def normalize_headers(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def to_datetime_cols(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    return df

def s_get(df, col, default=None):
    if isinstance(df, pd.DataFrame) and col in df.columns:
        return df[col]
    if default is None:
        return pd.Series([pd.NA] * (len(df) if isinstance(df, pd.DataFrame) else 0))
    return pd.Series([default] * (len(df) if isinstance(df, pd.DataFrame) else 0))

def norm_status(x: str):
    if not isinstance(x, str): return x
    s = x.strip().lower()
    map_ = {
        "concluida":"Concluída","concluída":"Concluída","concluido":"Concluída","concluído":"Concluída",
        "finalizado":"Concluída","feito":"Concluída",
        "pendente":"Pendente","em aberto":"Pendente","aberto":"Pendente","em andamento":"Pendente"
    }
    return map_.get(s, x)

def guess_mapping(df_cols, targets):
    guesses = {}
    for t in targets:
        if t in df_cols:
            guesses[t] = t
            continue
        best = difflib.get_close_matches(t, df_cols, n=1, cutoff=0.6)
        guesses[t] = best[0] if best else ""
    return guesses

def mapping_wizard(df, title, required, optional, key):
    st.subheader(f"🧭 {title} — Mapeamento")
    st.caption("Use **Auto-detectar** e ajuste manualmente. Campos obrigatórios e opcionais abaixo.")
    st.dataframe(df.head(5))

    cols = list(df.columns)
    req_guess = guess_mapping(cols, required)
    opt_guess = guess_mapping(cols, optional)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔍 Auto-detectar", key=f"auto_{key}"):
            st.session_state[f"map_req_{key}"] = req_guess
            st.session_state[f"map_opt_{key}"] = opt_guess
    with c2:
        if st.button("🗑️ Limpar", key=f"clear_{key}"):
            st.session_state[f"map_req_{key}"] = {t:"" for t in required}
            st.session_state[f"map_opt_{key}"] = {t:"" for t in optional}

    req_state = st.session_state.get(f"map_req_{key}") or req_guess
    opt_state = st.session_state.get(f"map_opt_{key}") or opt_guess

    st.markdown("**Obrigatórios**")
    cols_req = st.columns(3)
    mapped_req = {}
    for i, t in enumerate(required):
        with cols_req[i%3]:
            mapped_req[t] = st.selectbox(
                f"{t}", options=[""]+cols,
                index=([""]+cols).index(req_state.get(t,"")) if req_state.get(t,"") in ([""]+cols) else 0,
                key=f"{key}_req_{t}"
            )

    st.markdown("**Opcionais**")
    cols_opt = st.columns(3)
    mapped_opt = {}
    for i, t in enumerate(optional):
        with cols_opt[i%3]:
            mapped_opt[t] = st.selectbox(
                f"{t}", options=[""]+cols,
                index=([""]+cols).index(opt_state.get(t,"")) if opt_state.get(t,"") in ([""]+cols) else 0,
                key=f"{key}_opt_{t}"
            )

    missing = [t for t in required if not mapped_req.get(t)]
    if missing: st.warning(f"Mapeie os campos: {', '.join(missing)}")
    else: st.success("✅ Mapeamento completo")

    merged = mapped_req.copy(); merged.update({k:v for k,v in mapped_opt.items() if v})
    return merged

# ==============================
# Enriquecimento (Entregas/Processos)
# ==============================
def enrich_entregas(df_ent: pd.DataFrame) -> pd.DataFrame:
    if df_ent is None: return df_ent
    if df_ent.empty: return df_ent.copy()

    df = normalize_headers(df_ent.copy())

    de = pd.to_datetime(s_get(df, "data_entrega", default=pd.NaT), errors="coerce", dayfirst=True)
    pt = pd.to_datetime(s_get(df, "prazo_tecnico", default=pd.NaT), errors="coerce", dayfirst=True)
    dl = pd.to_datetime(s_get(df, "data_legal", default=pd.NaT), errors="coerce", dayfirst=True)
    dv = pd.to_datetime(s_get(df, "data_vencimento", default=pd.NaT), errors="coerce", dayfirst=True)
    cp = pd.to_datetime(s_get(df, "competencia", default=pd.NaT), errors="coerce", dayfirst=True)

    df["data_entrega"]    = de
    df["prazo_tecnico"]   = pt
    df["data_legal"]      = dl
    df["data_vencimento"] = dv
    df["competencia"]     = cp

    if "status" in df.columns:
        df["status"] = df["status"].map(norm_status).fillna(df["status"])

    has_both_t = de.notna() & pt.notna()
    df["no_prazo_tecnico"]     = np.where(has_both_t & (de <= pt), True, np.where(has_both_t, False, np.nan))
    df["antecipada_tecnico"]   = has_both_t & (de < pt)
    df["atraso_tecnico_dias"]  = np.where(has_both_t, (de - pt).dt.days.clip(lower=0), np.nan)

    has_both_l = de.notna() & dl.notna()
    df["no_prazo_legal"]       = np.where(has_both_l & (de <= dl), True, np.where(has_both_l, False, np.nan))
    df["antecipada_legal"]     = has_both_l & (de < dl)
    df["atraso_legal_dias"]    = np.where(has_both_l, (de - dl).dt.days.clip(lower=0), np.nan)

    return df

def get_basis_columns(basis: str):
    key = basis.lower()
    if key.startswith("t"):
        return dict(no_prazo="no_prazo_tecnico", atraso_dias="atraso_tecnico_dias", antecipada="antecipada_tecnico", label="% no prazo (técnico)")
    else:
        return dict(no_prazo="no_prazo_legal", atraso_dias="atraso_legal_dias", antecipada="antecipada_legal", label="% no prazo (legal)")

def enrich_procs(dfp: pd.DataFrame) -> pd.DataFrame:
    if dfp is None: return dfp
    if dfp.empty: return dfp.copy()
    df = normalize_headers(dfp.copy())
    ab = pd.to_datetime(s_get(df, "abertura", default=pd.NaT), errors="coerce", dayfirst=True)
    co = pd.to_datetime(s_get(df, "conclusao", default=pd.NaT), errors="coerce", dayfirst=True)
    pp = pd.to_datetime(s_get(df, "proximo_prazo", default=pd.NaT), errors="coerce", dayfirst=True)
    df["abertura"] = ab; df["conclusao"] = co; df["proximo_prazo"] = pp
    today = pd.to_datetime(datetime.now().date())
    df["lead_time_dias"] = np.where(co.notna() & ab.notna(), (co - ab).dt.days, np.nan)
    df["aging_dias"]     = np.where(co.isna() & ab.notna(), (today - ab).dt.days, np.nan)
    if "status" not in df.columns:
        df["status"] = np.where(df["conclusao"].notna(), "Concluído", "Em andamento")
    return df

# ==============================
# Sessão
# ==============================
for k in ["dfe","dfs","dfo","dfr","dfp"]:
    if k not in st.session_state: st.session_state[k] = None

# ==============================
# Sidebar — Somente Config geral
# ==============================
with st.sidebar:
    st.header("⚙️ Configurações")
    basis = st.radio("Base dos KPIs", ["Técnico", "Legal"], index=0, horizontal=True)
    meta_ok = st.number_input("Meta OK (≥ %)", min_value=50.0, max_value=100.0, value=95.0, step=0.5)
    meta_atencao = st.number_input("Meta Atenção (≥ %)", min_value=0.0, max_value=100.0, value=85.0, step=0.5)
    st.caption("Semáforo: 🟢 ≥ OK | 🟡 ≥ Atenção | 🔴 < Atenção")
    st.markdown("---")
    st.markdown("**1)** Carregue os dados em **🗂️ Dados & Mapeamento**.\n**2)** Use os **filtros no topo de cada aba**.")

# ==============================
# Filtros locais — componentes reutilizáveis
# ==============================
def find_date_candidates(df: pd.DataFrame):
    cands = []
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in c for k in ["data","venc","entrega","competencia","legal","tecnico","técnico"]):
            cands.append(c)
    # manter ordem de aparição
    seen = set(); out = []
    for c in cands:
        if c not in seen:
            out.append(c); seen.add(c)
    return out

def filter_card(df: pd.DataFrame, key: str, context_filters=("empresa","departamento","responsavel_entrega")):
    """Desenha um card compacto de filtros e retorna o df filtrado + dict com seleções."""
    if df is None or df.empty: 
        st.info("Carregue dados para habilitar filtros desta aba.")
        return df, {}

    with st.container(border=True):
        b1, b2, b3, b4 = st.columns([1.1, 1, 1, 1])
        # coluna de data
        date_cols = find_date_candidates(df)
        with b1:
            dcol = st.selectbox("Coluna de data", ["<sem filtro>"] + date_cols, key=f"dcol_{key}")
        with b2:
            di = st.date_input("De", value=None, key=f"di_{key}") if dcol and dcol!="<sem filtro>" else None
        with b3:
            dfim = st.date_input("Até", value=None, key=f"df_{key}") if dcol and dcol!="<sem filtro>" else None
        with b4:
            topn = st.number_input("Top N (rankings)", min_value=5, max_value=50, value=10, step=1, key=f"topn_{key}")

        with st.expander("Filtros avançados"):
            cols = st.columns(3)
            sel = {}
            for i, c in enumerate(context_filters):
                if c in df.columns:
                    with cols[i%3]:
                        sel[c] = st.multiselect(c.capitalize(), sorted(df[c].dropna().astype(str).unique().tolist()), key=f"{c}_{key}")
                else:
                    sel[c] = []

        # aplica filtros
        mask = pd.Series(True, index=df.index)
        if dcol and dcol!="<sem filtro>" and dcol in df.columns:
            dts = pd.to_datetime(df[dcol], errors="coerce")
            if di:   mask &= dts.dt.date >= di
            if dfim: mask &= dts.dt.date <= dfim
        for c, v in sel.items():
            if c in df.columns and v:
                mask &= df[c].astype(str).isin(v)

        return df[mask].copy(), {"dcol": dcol, "di": di, "df": dfim, "topn": topn, **sel}

def ranking(df, group_col, metric_cols, how="desc", top=10):
    """metric_cols: dict com chaves possíveis: no_prazo (bool/0-1), atraso_dias (num), antecipada (bool)"""
    if df is None or df.empty or group_col not in df.columns:
        return pd.DataFrame(columns=[group_col, "valor"])
    if "no_prazo" in metric_cols and metric_cols["no_prazo"] in df.columns:
        s = df.groupby(group_col)[metric_cols["no_prazo"]].mean()*100
    elif "qtd" in metric_cols and metric_cols["qtd"]:
        s = df.groupby(group_col).size()
    elif "antecipada" in metric_cols and metric_cols["antecipada"] in df.columns:
        s = df.groupby(group_col)[metric_cols["antecipada"]].sum()
    elif "atraso_dias" in metric_cols and metric_cols["atraso_dias"] in df.columns:
        s = df.groupby(group_col)[metric_cols["atraso_dias"]].mean()
    else:
        return pd.DataFrame(columns=[group_col, "valor"])
    out = s.reset_index(name="valor").replace({np.inf: np.nan, -np.inf: np.nan})
    out = out.dropna(subset=["valor"]).sort_values("valor", ascending=(how=="asc")).head(top)
    return out

# ==============================
# Abas
# ==============================
tabs = st.tabs([
    "🏁 Resumo Executivo",
    "👥 Clientes",
    "🏢 Departamentos",
    "🧑‍💼 Colaboradores",
    "📆 Linha do Tempo",
    "📦 SLA & Backlog",
    "🧰 Capacidade & Carga",
    "🚨 Riscos & Alertas",
    "🔄 Processos",
    "🗂️ Dados & Mapeamento",
    "🧪 Qualidade & Dicionário"
])

# ==============================
# 🗂️ Dados & Mapeamento
# ==============================
with tabs[9]:
    st.subheader("1) Carregue e mapeie os dados")
    cA, cB = st.columns(2)
    with cA:
        up_ent = st.file_uploader("Gestão de Entregas (CSV)", type=["csv"], key="up_ent")
        up_sol = st.file_uploader("Solicitações (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_sol")
        up_prc = st.file_uploader("Gestão de Processos (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_prc")
    with cB:
        up_obr = st.file_uploader("Lista de Obrigações (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_obr")
        up_rsp = st.file_uploader("Responsáveis & Departamentos (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_rsp")

    # ENTREGAS
    if up_ent:
        raw = read_any_csv(up_ent); raw = normalize_headers(raw)
        req = ["empresa","obrigacao","data_vencimento","status"]
        opt = ["cnpj","departamento","responsavel_prazo","responsavel_entrega","competencia","data_entrega","protocolo","prazo_tecnico","data_legal"]
        m = mapping_wizard(raw, "Entregas", req, opt, "ent")
        st.session_state["dfe"] = enrich_entregas(raw.rename(columns=m))
        st.success("Entregas carregadas e enriquecidas.")

    # SOLICITAÇÕES
    if up_sol:
        name = up_sol.name.lower()
        raw = try_read_excel(up_sol) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_sol)
        raw = normalize_headers(raw)
        req = ["id","assunto","empresa","status"]
        opt = ["prioridade","responsavel","abertura","prazo","ultima_atualizacao","conclusao"]
        m = mapping_wizard(raw, "Solicitações", req, opt, "sol")
        dfs = raw.rename(columns=m)
        st.session_state["dfs"] = to_datetime_cols(dfs, ["abertura","prazo","ultima_atualizacao","conclusao"])
        st.success("Solicitações carregadas.")

    # PROCESSOS
    if up_prc:
        name = up_prc.name.lower()
        raw = try_read_excel(up_prc) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_prc)
        raw = normalize_headers(raw)
        req = ["id","processo","empresa","status"]
        opt = ["etapa_atual","responsavel","abertura","conclusao","proximo_prazo","departamento"]
        m = mapping_wizard(raw, "Gestão de Processos", req, opt, "prc")
        st.session_state["dfp"] = enrich_procs(raw.rename(columns=m))
        st.success("Processos carregados e enriquecidos.")

    # OBRIGAÇÕES (ref)
    if up_obr:
        name = up_obr.name.lower()
        raw = try_read_excel(up_obr) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_obr)
        raw = normalize_headers(raw)
        req = ["obrigacao","departamento"]
        opt = ["mini","empresa","responsavel","periodicidade","prazo_mensal","alerta_dias","observacao"]
        m = mapping_wizard(raw, "Lista de Obrigações", req, opt, "obr")
        st.session_state["dfo"] = raw.rename(columns=m)
        st.info("Lista de Obrigações carregada (referência).")

    # RESPONSÁVEIS (ref)
    if up_rsp:
        name = up_rsp.name.lower()
        raw = try_read_excel(up_rsp) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_rsp)
        raw = normalize_headers(raw)
        req = ["responsavel","departamento"]
        opt = ["email","cargo"]
        m = mapping_wizard(raw, "Responsáveis & Departamentos", req, opt, "rsp")
        st.session_state["dfr"] = raw.rename(columns=m)
        st.info("Responsáveis carregados (referência).")

# Bases em sessão
dfe = st.session_state.get("dfe")
dfs = st.session_state.get("dfs")
dfp = st.session_state.get("dfp")

def require_entregas(tab):
    if dfe is None or (isinstance(dfe, pd.DataFrame) and dfe.empty):
        with tab:
            st.info("Carregue **Entregas** em '🗂️ Dados & Mapeamento'.")
        return True
    return False

# ==============================
# 🏁 Resumo Executivo (sem filtros locais; é síntese geral)
# ==============================
with tabs[0]:
    st.subheader("📌 KPIs Gerais")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** para ver os KPIs.")
    else:
        b = get_basis_columns(basis)
        pct_prazo = float((dfe[b["no_prazo"]].mean()*100)) if b["no_prazo"] in dfe.columns else np.nan
        atraso_med = float(dfe[b["atraso_dias"]].mean()) if b["atraso_dias"] in dfe.columns else np.nan
        antecip = int(dfe[b["antecipada"]].sum()) if b["antecipada"] in dfe.columns else 0
        total = len(dfe)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric(b["label"], f"{pct_prazo:,.1f}%".replace(",",".")) 
        c2.metric("Atraso médio (dias)", f"{atraso_med:,.1f}".replace(",",".")) 
        c3.metric("Entregas antecipadas", f"{antecip:,}".replace(",",".")) 
        c4.metric("Tarefas (base)", f"{total:,}".replace(",","."))

    st.subheader("🧩 Processos (se fornecidos)")
    if dfp is None or dfp.empty:
        st.info("Carregue **Gestão de Processos** para ver estes KPIs.")
    else:
        lead_med = float(dfp["lead_time_dias"].mean()) if "lead_time_dias" in dfp.columns else np.nan
        aging_med = float(dfp["aging_dias"].mean()) if "aging_dias" in dfp.columns else np.nan
        em_and = int((dfp["status"]=="Em andamento").sum()) if "status" in dfp.columns else 0
        concl = int((dfp["status"]=="Concluído").sum()) if "status" in dfp.columns else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Lead time médio (dias)", f"{lead_med:,.1f}".replace(",",".")) 
        c2.metric("Aging médio (dias)", f"{aging_med:,.1f}".replace(",",".")) 
        c3.metric("Em andamento", f"{em_and:,}".replace(",",".")) 
        c4.metric("Concluídos", f"{concl:,}".replace(",",".")) 

# ==============================
# 👥 Clientes (filtros locais)
# ==============================
if not require_entregas(tabs[1]):
    with tabs[1]:
        dfg, sel = filter_card(dfe, key="cli", context_filters=("empresa","departamento"))
        b = get_basis_columns(basis)
        topn = sel.get("topn", 10)

        st.markdown("**Mais tarefas (Entregas)**")
        r1 = ranking(dfg, "empresa", {"qtd": True}, top=topn)
        st.dataframe(r1)
        if not r1.empty: st.plotly_chart(px.bar(r1, x="empresa", y="valor", title="Tarefas por Cliente"), use_container_width=True)

        st.markdown(f"**Mais entregas antecipadas ({basis})**")
        r2 = ranking(dfg, "empresa", {"antecipada": b["antecipada"]}, top=topn)
        st.dataframe(r2)
        if not r2.empty: st.plotly_chart(px.bar(r2, x="empresa", y="valor", title=f"Antecipadas ({basis})"), use_container_width=True)

        st.markdown(f"**Melhor {b['label']}**")
        r3 = ranking(dfg, "empresa", {"no_prazo": b["no_prazo"]}, top=topn)
        st.dataframe(r3)
        if not r3.empty: st.plotly_chart(px.bar(r3, x="empresa", y="valor", title=b['label']), use_container_width=True)

# ==============================
# 🏢 Departamentos (filtros locais)
# ==============================
if not require_entregas(tabs[2]):
    with tabs[2]:
        dfg, sel = filter_card(dfe, key="dep", context_filters=("departamento","empresa"))
        b = get_basis_columns(basis); topn = sel.get("topn", 10)

        st.markdown(f"**{b['label']} — Ranking**")
        r1 = ranking(dfg, "departamento", {"no_prazo": b["no_prazo"]}, top=topn)
        st.dataframe(r1)
        if not r1.empty: st.plotly_chart(px.bar(r1, x="departamento", y="valor", title=b['label']), use_container_width=True)

        st.markdown("**Atraso médio (dias)**")
        r2 = ranking(dfg, "departamento", {"atraso_dias": b["atraso_dias"]}, how="asc", top=topn)
        st.dataframe(r2)
        if not r2.empty: st.plotly_chart(px.bar(r2, x="departamento", y="valor", title="Atraso médio (dias)"), use_container_width=True)

# ==============================
# 🧑‍💼 Colaboradores (filtros locais)
# ==============================
if not require_entregas(tabs[3]):
    with tabs[3]:
        dfg, sel = filter_card(dfe, key="col", context_filters=("responsavel_entrega","departamento","empresa"))
        b = get_basis_columns(basis); topn = sel.get("topn", 10)

        if "responsavel_entrega" not in dfg.columns:
            st.info("Mapeie **responsavel_entrega** em '🗂️ Dados & Mapeamento'.")
        else:
            st.markdown(f"**{b['label']} — Ranking**")
            r1 = ranking(dfg, "responsavel_entrega", {"no_prazo": b["no_prazo"]}, top=topn)
            st.dataframe(r1)
            if not r1.empty: st.plotly_chart(px.bar(r1, x="responsavel_entrega", y="valor", title=b['label']), use_container_width=True)

            st.markdown("**Volume de tarefas**")
            r2 = ranking(dfg, "responsavel_entrega", {"qtd": True}, top=topn)
            st.dataframe(r2)
            if not r2.empty: st.plotly_chart(px.bar(r2, x="responsavel_entrega", y="valor", title="Volume"), use_container_width=True)

            st.markdown(f"**Antecipadas ({basis})**")
            r3 = ranking(dfg, "responsavel_entrega", {"antecipada": b["antecipada"]}, top=topn)
            st.dataframe(r3)
            if not r3.empty: st.plotly_chart(px.bar(r3, x="responsavel_entrega", y="valor", title="Antecipadas"), use_container_width=True)

# ==============================
# 📆 Linha do Tempo (filtros locais)
# ==============================
if not require_entregas(tabs[4]):
    with tabs[4]:
        df, sel = filter_card(dfe, key="time", context_filters=("empresa","departamento"))
        b = get_basis_columns(basis)

        # base mês
        base_col = None
        for bc in ["competencia","data_vencimento","data_entrega"]:
            if bc in df.columns: base_col = bc; break
        if base_col is None:
            st.info("Mapeie alguma coluna de data (ex.: competencia, data_vencimento, data_entrega).")
        else:
            df["mes"] = pd.to_datetime(df[base_col], errors="coerce").dt.to_period("M").astype(str)
            df["no_prazo_flag"] = df[b["no_prazo"]].astype("float") if b["no_prazo"] in df.columns else np.nan
            g = df.groupby("mes").agg(no_prazo=("no_prazo_flag","mean"), tarefas=("no_prazo_flag","size")).reset_index()
            g["no_prazo_%"] = (g["no_prazo"]*100).round(2)
            g = g.sort_values("mes")
            g["MM3_%"] = g["no_prazo_%"].rolling(3).mean().round(2)
            st.dataframe(g[["mes","tarefas","no_prazo_%","MM3_%"]])
            if not g.empty:
                st.plotly_chart(px.line(g, x="mes", y=["no_prazo_%","MM3_%"], title=f"{b['label']} por mês (MM3)"), use_container_width=True)

# ==============================
# 📦 SLA & Backlog (filtros locais)
# ==============================
if not require_entregas(tabs[5]):
    with tabs[5]:
        dfg, sel = filter_card(dfe, key="sla", context_filters=("empresa","departamento"))
        b = get_basis_columns(basis); topn = sel.get("topn", 10)

        st.markdown("**SLA por Cliente**")
        sla = ranking(dfg, "empresa", {"no_prazo": b["no_prazo"]}, top=topn)
        st.dataframe(sla)
        if not sla.empty: st.plotly_chart(px.bar(sla, x="empresa", y="valor", title=b["label"]), use_container_width=True)

        st.markdown("**Backlog por faixa de atraso (concluídas fora do prazo)**")
        if b["atraso_dias"] in dfg.columns:
            late = dfg[dfg[b["atraso_dias"]].fillna(0) > 0].copy()
            bins = [-0.1,2,5,10,10000]; labels = ["1-2","3-5","6-10",">10"]
            late["bucket_atraso"] = pd.cut(late[b["atraso_dias"]], bins=bins, labels=labels)
            agg = late["bucket_atraso"].value_counts().reindex(labels).fillna(0).reset_index()
            agg.columns = ["faixa","qtd"]
            st.dataframe(agg)
            st.plotly_chart(px.bar(agg, x="faixa", y="qtd", title="Distribuição de atraso (dias)"), use_container_width=True)
        else:
            st.info("Mapeie **prazo/entrega** para calcular atraso.")

# ==============================
# 🧰 Capacidade & Carga (filtros locais)
# ==============================
if not require_entregas(tabs[6]):
    with tabs[6]:
        dfg, sel = filter_card(dfe, key="cap", context_filters=("responsavel_entrega","departamento","empresa"))
        cap_sem = st.number_input("Capacidade por colaborador/semana (estimada)", min_value=1, max_value=500, value=25, step=1, key="cap_val")
        if "responsavel_entrega" not in dfg.columns:
            st.info("Mapeie **responsavel_entrega**.")
        else:
            if "data_entrega" in dfg.columns:
                dt = pd.to_datetime(dfg["data_entrega"], errors="coerce")
                cutoff = pd.Timestamp.today() - pd.Timedelta(days=28)
                base = dfg[dt >= cutoff]
                carga = base.groupby("responsavel_entrega").size().reset_index(name="tarefas_4s")
                carga["utilizacao_vs_cap_%"] = (carga["tarefas_4s"] / (cap_sem*4) * 100).round(1)
                st.dataframe(carga.sort_values("utilizacao_vs_cap_%", ascending=False))
                st.plotly_chart(px.bar(carga.sort_values("utilizacao_vs_cap_%", ascending=False),
                                       x="responsavel_entrega", y="utilizacao_vs_cap_%",
                                       title="Utilização vs capacidade (últimas 4 semanas, %)"),
                                use_container_width=True)
            else:
                st.info("Necessário **data_entrega** para medir carga recente.")

# ==============================
# 🚨 Riscos & Alertas (filtros locais simples)
# ==============================
if not require_entregas(tabs[7]):
    with tabs[7]:
        dfg, sel = filter_card(dfe, key="risk", context_filters=("empresa","departamento"))
        b = get_basis_columns(basis)

        if "empresa" not in dfg.columns:
            st.info("Mapeie **empresa** para analisar riscos.")
        else:
            dfg2 = dfg.copy()
            dfg2["_no_prazo"] = dfg2[b["no_prazo"]].astype(float) if b["no_prazo"] in dfg2.columns else np.nan
            dfg2["_atraso"]   = dfg2[b["atraso_dias"]].astype(float) if b["atraso_dias"] in dfg2.columns else np.nan
            dfg2["_resp_nan"] = dfg2["responsavel_entrega"].isna().astype(float) if "responsavel_entrega" in dfg2.columns else np.nan
            dfg2["_pt_nan"]   = pd.to_datetime(dfg2["prazo_tecnico"], errors="coerce").isna().astype(float) if "prazo_tecnico" in dfg2.columns else np.nan

            g = dfg2.groupby("empresa").agg(
                pct=("_no_prazo","mean"),
                atraso=("_atraso","mean"),
                sem_resp=("_resp_nan","mean"),
                sem_pt=("_pt_nan","mean")
            ).reset_index()
            g["pct"] = (g["pct"]*100).round(2)
            for c in ["sem_resp","sem_pt"]:
                if g[c].isna().all(): g[c] = 0.0
            g["sem_resp"] = (g["sem_resp"]*100).round(1)
            g["sem_pt"]   = (g["sem_pt"]*100).round(1)

            g["score_risco"] = (
                np.maximum(0, meta_ok - g["pct"]) * 0.5 +
                np.maximum(0, g["atraso"] - 5) * 5 +
                g["sem_pt"] * 0.2 +
                g["sem_resp"] * 0.3
            ).round(1)

            riscos = g.sort_values("score_risco", ascending=False)
            st.markdown("**Ranking de Riscos por Cliente**")
            st.dataframe(riscos[["empresa","pct","atraso","sem_pt","sem_resp","score_risco"]].rename(columns={"pct": get_basis_columns(basis)["label"], "atraso":"atraso_medio"}))
            if not riscos.empty:
                st.plotly_chart(px.bar(riscos.head(10), x="empresa", y="score_risco", title="Top 10 riscos (clientes)"), use_container_width=True)
        st.caption("Regras: abaixo da meta, atraso médio >5d, sem prazo técnico, sem responsável.")

# ==============================
# 🔄 Processos (filtros locais)
# ==============================
with tabs[8]:
    if dfp is None or dfp.empty:
        st.info("Carregue **Gestão de Processos** em '🗂️ Dados & Mapeamento'.")
    else:
        df, sel = filter_card(dfp, key="proc", context_filters=("empresa","departamento","responsavel"))
        # KPIs
        lead_med = float(df["lead_time_dias"].mean()) if "lead_time_dias" in df.columns else np.nan
        aging_med = float(df["aging_dias"].mean()) if "aging_dias" in df.columns else np.nan
        em_and = int((df["status"]=="Em andamento").sum()) if "status" in df.columns else 0
        concl = int((df["status"]=="Concluído").sum()) if "status" in df.columns else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Lead time médio (dias)", f"{lead_med:,.1f}".replace(",",".")) 
        c2.metric("Aging médio (dias)", f"{aging_med:,.1f}".replace(",",".")) 
        c3.metric("Em andamento", f"{em_and:,}".replace(",",".")) 
        c4.metric("Concluídos", f"{concl:,}".replace(",",".")) 

        # Funil por etapa
        if "etapa_atual" in df.columns:
            funil = df["etapa_atual"].value_counts().reset_index()
            funil.columns = ["etapa","qtd"]
            st.plotly_chart(px.bar(funil, x="etapa", y="qtd", title="Funil por etapa"), use_container_width=True)
            st.dataframe(funil)

        # Gargalos (aging por etapa)
        if "etapa_atual" in df.columns and "aging_dias" in df.columns:
            garg = df.groupby("etapa_atual")["aging_dias"].mean().reset_index().dropna()
            garg = garg.sort_values("aging_dias", ascending=False)
            st.plotly_chart(px.bar(garg, x="etapa_atual", y="aging_dias", title="Gargalo (aging médio por etapa)"), use_container_width=True)
            st.dataframe(garg)

        # Produtividade (lead time médio concluído)
        if "responsavel" in df.columns and "lead_time_dias" in df.columns:
            prod = df[df["status"]=="Concluído"].groupby("responsavel")["lead_time_dias"].mean().reset_index().dropna()
            prod = prod.sort_values("lead_time_dias")
            st.plotly_chart(px.bar(prod.head(sel.get("topn",10)), x="responsavel", y="lead_time_dias", title="Produtividade (menor lead time)"), use_container_width=True)
            st.dataframe(prod.head(sel.get("topn",10)))

# ==============================
# 🧪 Qualidade & Dicionário (sem filtros)
# ==============================
with tabs[10]:
    st.subheader("🧪 Qualidade dos Dados & Dicionário")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** para validar mapeamento e qualidade.")
    else:
        df = dfe.copy()
        st.markdown("**Colunas (Entregas):**")
        st.write(sorted(df.columns.tolist()))
        chk = ["empresa","obrigacao","departamento","responsavel_entrega","data_entrega","prazo_tecnico","data_legal","status"]
        miss = [c for c in chk if c not in df.columns]
        if miss: st.warning(f"⚠️ Colunas úteis ausentes: {', '.join(miss)}.")
        else: st.success("✅ Conjunto de colunas essenciais disponível.")
        st.markdown("**Nulos por coluna (top 15):**")
        nulls = df.isna().mean().sort_values(ascending=False).head(15).reset_index()
        nulls.columns = ["coluna","% nulos"]; nulls["% nulos"] = (nulls["% nulos"]*100).round(1)
        st.dataframe(nulls)
        st.markdown("**Amostra (50 primeiras):**")
        st.dataframe(df.head(50))
        st.download_button("⬇️ Exportar base completa (CSV)", df.to_csv(index=False).encode("utf-8"), "base_completa.csv", "text/csv")
