# app.py — Acessórias (v4.1)
# Fluxo guiado + Auto-detectar + leitura robusta + filtros globais (sidebar)
# Técnico/Legal (toggle), metas/semáforos, dashboards enxutos, Processos
# Correção: bloco "Riscos & Alertas" robusto + fix em up_obrig

import difflib
from datetime import date, datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ==============================
# Config do App
# ==============================
st.set_page_config(page_title="Acessórias — Diagnóstico", layout="wide")
st.title("📊 Acessórias — Diagnóstico (v4.1)")
st.caption("Fluxo: ① Dados & Mapeamento → ② Ajuste Filtros (sidebar) → ③ Dashboards → ④ Export/Drill-down.")

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
# Helpers de transformação
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

def s_dt_days(series):
    try:
        return series.dt.days
    except Exception:
        return pd.Series([pd.NA] * len(series), index=series.index if isinstance(series, pd.Series) else None)

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
    st.subheader(f"🧭 {title} — Mapeamento de Colunas")
    st.caption("Use **Auto-detectar** e ajuste manualmente onde precisar. Campos obrigatórios e opcionais abaixo.")
    st.dataframe(df.head(5))

    cols = list(df.columns)
    req_guess = guess_mapping(cols, required)
    opt_guess = guess_mapping(cols, optional)

    ctop1, ctop2 = st.columns(2)
    with ctop1:
        if st.button("🔍 Auto-detectar", key=f"auto_{key}"):
            st.session_state[f"map_req_{key}"] = req_guess
            st.session_state[f"map_opt_{key}"] = opt_guess
    with ctop2:
        if st.button("🗑️ Limpar", key=f"clear_{key}"):
            st.session_state[f"map_req_{key}"] = {t:"" for t in required}
            st.session_state[f"map_opt_{key}"] = {t:"" for t in optional}

    req_state = st.session_state.get(f"map_req_{key}") or req_guess
    opt_state = st.session_state.get(f"map_opt_{key}") or opt_guess

    st.markdown("**Obrigatórios**")
    req_cols = st.columns(3)
    mapped_req = {}
    for i, t in enumerate(required):
        with req_cols[i%3]:
            mapped_req[t] = st.selectbox(
                f"{t}", options=[""]+cols,
                index=([""]+cols).index(req_state.get(t,"")) if req_state.get(t,"") in ([""]+cols) else 0,
                key=f"{key}_req_{t}"
            )

    st.markdown("**Opcionais**")
    opt_cols = st.columns(3)
    mapped_opt = {}
    for i, t in enumerate(optional):
        with opt_cols[i%3]:
            mapped_opt[t] = st.selectbox(
                f"{t}", options=[""]+cols,
                index=([""]+cols).index(opt_state.get(t,"")) if opt_state.get(t,"") in ([""]+cols) else 0,
                key=f"{key}_opt_{t}"
            )

    missing = [t for t in required if not mapped_req.get(t)]
    if missing:
        st.warning(f"Mapeie os campos obrigatórios: {', '.join(missing)}")
    else:
        st.success("✅ Mapeamento completo")

    merged = mapped_req.copy(); merged.update({k:v for k,v in mapped_opt.items() if v})
    return merged

# ==============================
# Enriquecimento de Entregas (à prova de coluna ausente)
# ==============================
def enrich_entregas(df_ent: pd.DataFrame) -> pd.DataFrame:
    if df_ent is None: return df_ent
    if df_ent.empty: return df_ent.copy()

    df = normalize_headers(df_ent.copy())

    # séries seguras
    de = pd.to_datetime(s_get(df, "data_entrega", default=pd.NaT), errors="coerce", dayfirst=True)
    pt = pd.to_datetime(s_get(df, "prazo_tecnico", default=pd.NaT), errors="coerce", dayfirst=True)
    dl = pd.to_datetime(s_get(df, "data_legal", default=pd.NaT), errors="coerce", dayfirst=True)
    dv = pd.to_datetime(s_get(df, "data_vencimento", default=pd.NaT), errors="coerce", dayfirst=True)
    cp = pd.to_datetime(s_get(df, "competencia", default=pd.NaT), errors="coerce", dayfirst=True)

    df["data_entrega"] = de
    df["prazo_tecnico"] = pt
    df["data_legal"] = dl
    df["data_vencimento"] = dv
    df["competencia"] = cp

    if "status" in df.columns:
        df["status"] = df["status"].map(norm_status).fillna(df["status"])

    # Técnico
    has_both_t = de.notna() & pt.notna()
    df["no_prazo_tecnico"]    = np.where(has_both_t & (de <= pt), True, np.where(has_both_t, False, np.nan))
    df["antecipada_tecnico"]  = has_both_t & (de < pt)
    df["atraso_tecnico_dias"] = np.where(has_both_t, (de - pt).dt.days.clip(lower=0), np.nan)

    # Legal
    has_both_l = de.notna() & dl.notna()
    df["no_prazo_legal"]      = np.where(has_both_l & (de <= dl), True, np.where(has_both_l, False, np.nan))
    df["antecipada_legal"]    = has_both_l & (de < dl)
    df["atraso_legal_dias"]   = np.where(has_both_l, (de - dl).dt.days.clip(lower=0), np.nan)

    return df

def get_basis_columns(basis: str):
    key = basis.lower()
    if key.startswith("t"):
        return dict(no_prazo="no_prazo_tecnico", atraso_dias="atraso_tecnico_dias", antecipada="antecipada_tecnico", label="% no prazo (técnico)")
    else:
        return dict(no_prazo="no_prazo_legal", atraso_dias="atraso_legal_dias", antecipada="antecipada_legal", label="% no prazo (legal)")

# ==============================
# Enriquecimento de Processos
# ==============================
def enrich_procs(dfp: pd.DataFrame) -> pd.DataFrame:
    if dfp is None: return dfp
    if dfp.empty: return dfp.copy()
    df = normalize_headers(dfp.copy())
    # datas
    ab = pd.to_datetime(s_get(df, "abertura", default=pd.NaT), errors="coerce", dayfirst=True)
    co = pd.to_datetime(s_get(df, "conclusao", default=pd.NaT), errors="coerce", dayfirst=True)
    pp = pd.to_datetime(s_get(df, "proximo_prazo", default=pd.NaT), errors="coerce", dayfirst=True)
    df["abertura"] = ab
    df["conclusao"] = co
    df["proximo_prazo"] = pp
    # lead time (concluídos) e aging (abertos)
    today = pd.to_datetime(datetime.now().date())
    df["lead_time_dias"] = np.where(co.notna() & ab.notna(), (co - ab).dt.days, np.nan)
    df["aging_dias"] = np.where(co.isna() & ab.notna(), (today - ab).dt.days, np.nan)
    # status simples
    if "status" not in df.columns:
        df["status"] = np.where(df["conclusao"].notna(), "Concluído", "Em andamento")
    return df

# ==============================
# Estado inicial
# ==============================
for k in ["dfe","dfs","dfo","dfr","dfp"]:
    if k not in st.session_state: st.session_state[k] = None

# ==============================
# Sidebar — Fluxo + Config + Filtros
# ==============================
with st.sidebar:
    st.header("🧭 Fluxo")
    st.markdown("1) **Dados & Mapeamento**\n2) **Ajuste Filtros**\n3) **Dashboards**")
    st.divider()

    st.header("⚙️ Configurações")
    basis = st.radio("Base dos KPIs", ["Técnico", "Legal"], index=0, horizontal=True)
    meta_ok = st.number_input("Meta OK (≥ %)", min_value=50.0, max_value=100.0, value=95.0, step=0.5)
    meta_atencao = st.number_input("Meta Atenção (≥ %)", min_value=0.0, max_value=100.0, value=85.0, step=0.5)
    st.caption("Semáforo: 🟢 ≥ OK | 🟡 ≥ Atenção | 🔴 < Atenção")
    basis_cols = get_basis_columns(basis)
    st.divider()

    # Filtros globais (aplicados às Entregas)
    st.header("🎛️ Filtros Globais (Entregas)")
    dfe_tmp = st.session_state["dfe"]
    if isinstance(dfe_tmp, pd.DataFrame) and not dfe_tmp.empty:
        dfc = dfe_tmp
        date_candidates = [c for c in dfc.columns if (pd.api.types.is_datetime64_any_dtype(dfc[c]) or any(k in c for k in ["data","venc","entrega","competencia","legal","tecnico","técnico"]))]
        seen=set(); date_candidates=[x for x in date_candidates if not (x in seen or seen.add(x))]
        dcol = st.selectbox("Coluna de data", ["<sem filtro>"] + date_candidates, index=1 if date_candidates else 0, key="dcol_global") if date_candidates else "<sem filtro>"
        di = st.date_input("De (data)", value=None, key="di_global") if dcol and dcol != "<sem filtro>" else None
        dfim = st.date_input("Até (data)", value=None, key="df_global") if dcol and dcol != "<sem filtro>" else None
        emp_sel = st.multiselect("Clientes", sorted(dfc.get("empresa", pd.Series(dtype=str)).dropna().unique().tolist())) if "empresa" in dfc.columns else []
        dep_sel = st.multiselect("Departamentos", sorted(dfc.get("departamento", pd.Series(dtype=str)).dropna().unique().tolist())) if "departamento" in dfc.columns else []
        colab_sel = st.multiselect("Colaboradores", sorted(dfc.get("responsavel_entrega", pd.Series(dtype=str)).dropna().unique().tolist())) if "responsavel_entrega" in dfc.columns else []

        st.session_state["flt_dcol"] = dcol
        st.session_state["flt_di"] = di
        st.session_state["flt_df"] = dfim
        st.session_state["flt_emp"] = emp_sel
        st.session_state["flt_dep"] = dep_sel
        st.session_state["flt_col"] = colab_sel
    else:
        st.info("Carregue **Entregas** para habilitar filtros.")

def apply_global_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df
    dcol = st.session_state.get("flt_dcol", "<sem filtro>")
    di = st.session_state.get("flt_di", None)
    dfim = st.session_state.get("flt_df", None)
    emp_sel = st.session_state.get("flt_emp", [])
    dep_sel = st.session_state.get("flt_dep", [])
    colab_sel = st.session_state.get("flt_col", [])

    mask = pd.Series(True, index=df.index)
    if dcol and dcol != "<sem filtro>" and dcol in df.columns:
        dts = pd.to_datetime(df[dcol], errors="coerce")
        if di:   mask &= dts.dt.date >= di
        if dfim: mask &= dts.dt.date <= dfim
    if "empresa" in df.columns and emp_sel: mask &= df["empresa"].isin(emp_sel)
    if "departamento" in df.columns and dep_sel: mask &= df["departamento"].isin(dep_sel)
    if "responsavel_entrega" in df.columns and colab_sel: mask &= df["responsavel_entrega"].isin(colab_sel)
    return df[mask].copy()

def ranking(df, group_col, metric, basis_cols, how="desc", top=10):
    if df is None or df.empty or group_col not in df.columns:
        return pd.DataFrame(columns=[group_col, "valor"])
    if metric == "pct_no_prazo":
        s = df.groupby(group_col)[basis_cols["no_prazo"]].mean()*100
    elif metric == "qtd_tarefas":
        s = df.groupby(group_col).size()
    elif metric == "qtd_antecipadas":
        s = df.groupby(group_col)[basis_cols["antecipada"]].sum()
    elif metric == "atraso_medio":
        s = df.groupby(group_col)[basis_cols["atraso_dias"]].mean()
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
# Aba: Dados & Mapeamento (final da lista para orientar o fluxo)
# ==============================
with tabs[9]:
    st.subheader("🗂️ 1) Carregue e mapeie os dados")
    colA, colB = st.columns(2)
    with colA:
        up_entregas = st.file_uploader("Gestão de Entregas (CSV)", type=["csv"], key="up_ent")
        up_solic    = st.file_uploader("Solicitações (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_sol")
        up_procs    = st.file_uploader("Gestão de Processos (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_procs")
    with colB:
        up_obrig    = st.file_uploader("Lista de Obrigações (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_obr")
        up_resp     = st.file_uploader("Responsáveis & Departamentos (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_resp")

    # ENTREGAS
    if up_entregas:
        raw = read_any_csv(up_entregas); raw = normalize_headers(raw)
        required = ["empresa","obrigacao","data_vencimento","status"]
        optional = ["cnpj","departamento","responsavel_prazo","responsavel_entrega","competencia","data_entrega","protocolo","prazo_tecnico","data_legal"]
        m = mapping_wizard(raw, "Entregas", required, optional, "ent")
        dfe = raw.rename(columns=m)
        st.session_state["dfe"] = enrich_entregas(dfe)
        st.success("Entregas carregadas e enriquecidas.")

    # SOLICITAÇÕES
    if up_solic:
        name = up_solic.name.lower()
        raw = try_read_excel(up_solic) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_solic)
        raw = normalize_headers(raw)
        required = ["id","assunto","empresa","status"]
        optional = ["prioridade","responsavel","abertura","prazo","ultima_atualizacao","conclusao"]
        m = mapping_wizard(raw, "Solicitações", required, optional, "sol")
        dfs = raw.rename(columns=m)
        dfs = to_datetime_cols(dfs, ["abertura","prazo","ultima_atualizacao","conclusao"])
        st.session_state["dfs"] = dfs
        st.success("Solicitações carregadas.")

    # PROCESSOS
    if up_procs:
        name = up_procs.name.lower()
        raw = try_read_excel(up_procs) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_procs)
        raw = normalize_headers(raw)
        required = ["id","processo","empresa","status"]
        optional = ["etapa_atual","responsavel","abertura","conclusao","proximo_prazo","departamento"]
        m = mapping_wizard(raw, "Gestão de Processos", required, optional, "proc")
        dfp = raw.rename(columns=m)
        st.session_state["dfp"] = enrich_procs(dfp)
        st.success("Processos carregados e enriquecidos.")

    # OBRIGAÇÕES (referência)
    if up_obrig:
        name = up_obrig.name.lower()
        raw = try_read_excel(up_obrig) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_obrig)
        raw = normalize_headers(raw)
        required = ["obrigacao","departamento"]
        optional = ["mini","empresa","responsavel","periodicidade","prazo_mensal","alerta_dias","observacao"]
        m = mapping_wizard(raw, "Lista de Obrigações", required, optional, "obr")
        dfo = raw.rename(columns=m)
        st.session_state["dfo"] = dfo
        st.info("Lista de Obrigações carregada (referência).")

    # RESPONSÁVEIS (referência)
    if up_resp:
        name = up_resp.name.lower()
        raw = try_read_excel(up_resp) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_resp)
        raw = normalize_headers(raw)
        required = ["responsavel","departamento"]
        optional = ["email","cargo"]
        m = mapping_wizard(raw, "Responsáveis & Departamentos", required, optional, "resp")
        dfr = raw.rename(columns=m)
        st.session_state["dfr"] = dfr
        st.info("Responsáveis carregados (referência).")

# ==============================
# Dados em sessão
# ==============================
dfe = st.session_state.get("dfe")  # entregas (enriquecidas)
dfs = st.session_state.get("dfs")  # solicitações
dfp = st.session_state.get("dfp")  # processos (enriquecidos)

def require_entregas(tab_container):
    if dfe is None or (isinstance(dfe, pd.DataFrame) and dfe.empty):
        with tab_container:
            st.info("Carregue **Entregas** em '🗂️ Dados & Mapeamento' para habilitar.")
        return True
    return False

# ==============================
# 🏁 Resumo Executivo
# ==============================
with tabs[0]:
    st.subheader("📌 KPIs Gerais")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** para ver os KPIs.")
    else:
        dfg = apply_global_filters(dfe)
        b = get_basis_columns(basis)
        pct_prazo = float((dfg[b["no_prazo"]].mean()*100)) if b["no_prazo"] in dfg.columns else np.nan
        atraso_med = float(dfg[b["atraso_dias"]].mean()) if b["atraso_dias"] in dfg.columns else np.nan
        antecip = int(dfg[b["antecipada"]].sum()) if b["antecipada"] in dfg.columns else 0
        total = len(dfg)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric(b["label"], f"{pct_prazo:,.1f}%".replace(",","."))     # cumprimento
        c2.metric("Atraso médio (dias)", f"{atraso_med:,.1f}".replace(",","."))  # severidade
        c3.metric("Entregas antecipadas", f"{antecip:,}".replace(",","."))      # eficiência
        c4.metric("Tarefas (base)", f"{total:,}".replace(",","."))

    st.subheader("🧩 Processos (se fornecidos)")
    if dfp is None or dfp.empty:
        st.info("Carregue **Gestão de Processos** para ver estes KPIs.")
    else:
        dfpp = dfp.copy()
        lead_med = float(dfpp["lead_time_dias"].mean()) if "lead_time_dias" in dfpp.columns else np.nan
        aging_med = float(dfpp["aging_dias"].mean()) if "aging_dias" in dfpp.columns else np.nan
        em_andamento = int((dfpp["status"]=="Em andamento").sum()) if "status" in dfpp.columns else 0
        concl = int((dfpp["status"]=="Concluído").sum()) if "status" in dfpp.columns else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Lead time médio (dias)", f"{lead_med:,.1f}".replace(",","."))    # tempo processo
        c2.metric("Aging médio (dias)", f"{aging_med:,.1f}".replace(",","."))       # fila atual
        c3.metric("Em andamento", f"{em_andamento:,}".replace(",","."))             # WIP
        c4.metric("Concluídos", f"{concl:,}".replace(",","."))

# ==============================
# 👥 Clientes
# ==============================
if not require_entregas(tabs[1]):
    with tabs[1]:
        dfg = apply_global_filters(dfe); b = get_basis_columns(basis)
        col1,col2 = st.columns(2)
        with col1:
            st.markdown("**Mais tarefas (Entregas)**")
            r1 = ranking(dfg, "empresa", "qtd_tarefas", b, top=10)
            st.dataframe(r1)
            if not r1.empty: st.plotly_chart(px.bar(r1, x="empresa", y="valor", title="Tarefas por Cliente"), use_container_width=True)
        with col2:
            st.markdown(f"**Mais entregas antecipadas ({basis})**")
            r2 = ranking(dfg, "empresa", "qtd_antecipadas", b, top=10)
            st.dataframe(r2)
            if not r2.empty: st.plotly_chart(px.bar(r2, x="empresa", y="valor", title=f"Antecipadas ({basis})"), use_container_width=True)

        st.markdown(f"**Melhor {b['label']}**")
        r3 = ranking(dfg, "empresa", "pct_no_prazo", b, top=10)
        st.dataframe(r3)
        if not r3.empty: st.plotly_chart(px.bar(r3, x="empresa", y="valor", title=b['label']), use_container_width=True)

# ==============================
# 🏢 Departamentos
# ==============================
if not require_entregas(tabs[2]):
    with tabs[2]:
        dfg = apply_global_filters(dfe); b = get_basis_columns(basis)
        col1,col2 = st.columns(2)
        with col1:
            st.markdown(f"**{b['label']} — Ranking**")
            r1 = ranking(dfg, "departamento", "pct_no_prazo", b, top=10)
            st.dataframe(r1)
            if not r1.empty: st.plotly_chart(px.bar(r1, x="departamento", y="valor", title=b['label']), use_container_width=True)
        with col2:
            st.markdown("**Atraso médio (dias)**")
            r2 = ranking(dfg, "departamento", "atraso_medio", b, how="asc", top=10)
            st.dataframe(r2)
            if not r2.empty: st.plotly_chart(px.bar(r2, x="departamento", y="valor", title="Atraso médio (dias)"), use_container_width=True)

# ==============================
# 🧑‍💼 Colaboradores
# ==============================
if not require_entregas(tabs[3]):
    with tabs[3]:
        dfg = apply_global_filters(dfe); b = get_basis_columns(basis)
        if "responsavel_entrega" not in dfg.columns:
            st.info("Mapeie **responsavel_entrega** para ver rankings de colaboradores.")
        else:
            col1,col2 = st.columns(2)
            with col1:
                st.markdown(f"**{b['label']} — Ranking**")
                r1 = ranking(dfg, "responsavel_entrega", "pct_no_prazo", b, top=10)
                st.dataframe(r1)
                if not r1.empty: st.plotly_chart(px.bar(r1, x="responsavel_entrega", y="valor", title=b['label']), use_container_width=True)
            with col2:
                st.markdown("**Volume de tarefas**")
                r2 = ranking(dfg, "responsavel_entrega", "qtd_tarefas", b, top=10)
                st.dataframe(r2)
                if not r2.empty: st.plotly_chart(px.bar(r2, x="responsavel_entrega", y="valor", title="Volume"), use_container_width=True)

            st.markdown(f"**Antecipadas ({basis})**")
            r3 = ranking(dfg, "responsavel_entrega", "qtd_antecipadas", b, top=10)
            st.dataframe(r3)
            if not r3.empty: st.plotly_chart(px.bar(r3, x="responsavel_entrega", y="valor", title="Antecipadas"), use_container_width=True)

# ==============================
# 📆 Linha do Tempo (com média móvel)
# ==============================
if not require_entregas(tabs[4]):
    with tabs[4]:
        df = apply_global_filters(dfe); b = get_basis_columns(basis)
        # base mês
        mes_series = None
        for base_col in ["competencia","data_vencimento","data_entrega"]:
            if base_col in df.columns:
                try:
                    mes_series = pd.to_datetime(df[base_col], errors="coerce").dt.to_period("M").astype(str)
                    break
                except Exception:
                    pass
        if mes_series is None:
            mes_series = pd.Series([pd.Timestamp.today().to_period("M").strftime("%Y-%m")]*len(df), index=df.index)
        df["mes"] = mes_series
        df["no_prazo_flag"] = df[b["no_prazo"]].astype("float")
        g = df.groupby("mes").agg(no_prazo=("no_prazo_flag","mean"), tarefas=("no_prazo_flag","size")).reset_index()
        g["no_prazo_%"] = (g["no_prazo"] * 100).round(2)
        # média móvel 3M
        g = g.sort_values("mes")
        g["MM3_%"] = g["no_prazo_%"].rolling(3).mean().round(2)
        st.dataframe(g[["mes","tarefas","no_prazo_%","MM3_%"]])
        try:
            fig = px.line(g, x="mes", y=["no_prazo_%","MM3_%"], title=f"{b['label']} por mês (c/ MM3)")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass

# ==============================
# 📦 SLA & Backlog (enxuto)
# ==============================
if not require_entregas(tabs[5]):
    with tabs[5]:
        dfg = apply_global_filters(dfe); b = get_basis_columns(basis)
        st.markdown("**SLA por Cliente (Top 10)**")
        sla = ranking(dfg, "empresa", "pct_no_prazo", b, top=10)
        st.dataframe(sla)
        if not sla.empty: st.plotly_chart(px.bar(sla, x="empresa", y="valor", title=b["label"]), use_container_width=True)

        st.markdown("**Backlog por faixa de atraso (apenas concluídas fora do prazo)**")
        if b["atraso_dias"] in dfg.columns:
            late = dfg[dfg[b["atraso_dias"]].fillna(0) > 0].copy()
            bins = [-0.1,2,5,10,10000]
            labels = ["1-2","3-5","6-10",">10"]
            late["bucket_atraso"] = pd.cut(late[b["atraso_dias"]], bins=bins, labels=labels)
            agg = late["bucket_atraso"].value_counts().reindex(labels).fillna(0).reset_index()
            agg.columns = ["faixa","qtd"]
            st.dataframe(agg)
            st.plotly_chart(px.bar(agg, x="faixa", y="qtd", title="Distribuição de atraso (dias)"), use_container_width=True)
        else:
            st.info("Mapeie datas para calcular atraso.")

# ==============================
# 🧰 Capacidade & Carga (simples)
# ==============================
if not require_entregas(tabs[6]):
    with tabs[6]:
        dfg = apply_global_filters(dfe)
        cap_sem = st.number_input("Capacidade por colaborador/semana (estimada)", min_value=1, max_value=500, value=25, step=1)
        if "responsavel_entrega" not in dfg.columns:
            st.info("Mapeie **responsavel_entrega**.")
        else:
            # carga por colaborador (últimas 4 semanas com base em data_entrega)
            if "data_entrega" in dfg.columns:
                dt = pd.to_datetime(dfg["data_entrega"], errors="coerce")
                cutoff = pd.Timestamp.today() - pd.Timedelta(days=28)
                base = dfg[dt >= cutoff]
                carga = base.groupby("responsavel_entrega").size().reset_index(name="tarefas_4s")
                carga["utilizacao_vs_cap"] = (carga["tarefas_4s"] / (cap_sem*4) * 100).round(1)
                st.dataframe(carga.sort_values("utilizacao_vs_cap", ascending=False))
                st.plotly_chart(px.bar(carga.sort_values("utilizacao_vs_cap", ascending=False),
                                       x="responsavel_entrega", y="utilizacao_vs_cap",
                                       title="Utilização vs capacidade (últimas 4 semanas, %)"),
                                use_container_width=True)
            else:
                st.info("Necessário **data_entrega** para medir carga recente.")

# ==============================
# 🚨 Riscos & Alertas (regras robustas)
# ==============================
if not require_entregas(tabs[7]):
    with tabs[7]:
        dfg = apply_global_filters(dfe)
        b = get_basis_columns(basis)

        if "empresa" not in dfg.columns:
            st.info("Para analisar riscos por cliente, mapeie a coluna **empresa** em '🗂️ Dados & Mapeamento'.")
        else:
            # Colunas auxiliares sempre presentes (evita KeyError no agg)
            dfg2 = dfg.copy()

            dfg2["_no_prazo"] = (
                dfg2[b["no_prazo"]].astype(float)
                if b["no_prazo"] in dfg2.columns else np.nan
            )
            dfg2["_atraso"] = (
                dfg2[b["atraso_dias"]].astype(float)
                if b["atraso_dias"] in dfg2.columns else np.nan
            )

            if "responsavel_entrega" in dfg2.columns:
                dfg2["_resp_nan"] = dfg2["responsavel_entrega"].isna().astype(float)
            else:
                dfg2["_resp_nan"] = np.nan  # não avalia se não houver coluna

            if "prazo_tecnico" in dfg2.columns:
                dfg2["_pt_nan"] = pd.to_datetime(dfg2["prazo_tecnico"], errors="coerce").isna().astype(float)
            else:
                dfg2["_pt_nan"] = np.nan  # não avalia se não houver coluna

            g_cli = dfg2.groupby("empresa").agg(
                pct=("_no_prazo", "mean"),
                atraso=("_atraso", "mean"),
                sem_resp=("_resp_nan", "mean"),
                sem_pt=("_pt_nan", "mean")
            ).reset_index()

            g_cli["pct"] = (g_cli["pct"] * 100).round(2)

            # Se a coluna inteira era NaN (não existia), zera para não punir
            for c in ["sem_resp", "sem_pt"]:
                if g_cli[c].isna().all():
                    g_cli[c] = 0.0

            g_cli["sem_resp"] = (g_cli["sem_resp"] * 100).round(1)
            g_cli["sem_pt"]   = (g_cli["sem_pt"]   * 100).round(1)

            # usa meta_ok da sidebar
            _meta_ok = meta_ok
            g_cli["score_risco"] = (
                np.maximum(0, _meta_ok - g_cli["pct"]) * 0.5 +     # quanto abaixo da meta
                np.maximum(0, g_cli["atraso"] - 5) * 5 +           # severidade > 5 dias
                g_cli["sem_pt"] * 0.2 +                            # % sem prazo técnico
                g_cli["sem_resp"] * 0.3                            # % sem responsável
            ).round(1)

            riscos = g_cli.sort_values("score_risco", ascending=False)

            st.markdown("**Ranking de Riscos por Cliente**")
            st.dataframe(
                riscos[["empresa","pct","atraso","sem_pt","sem_resp","score_risco"]]
                    .rename(columns={"pct": b["label"], "atraso": "atraso_medio"})
            )

            if not riscos.empty:
                st.plotly_chart(
                    px.bar(riscos.head(10), x="empresa", y="score_risco", title="Top 10 riscos (clientes)"),
                    use_container_width=True
                )
            else:
                st.success("Nenhum risco relevante pelas regras atuais.")

        st.caption("Regras: (i) abaixo da meta de % no prazo, (ii) atraso médio > 5 dias, (iii) sem prazo técnico, (iv) sem responsável.")

# ==============================
# 🔄 Processos (funil/gargalo/lead time)
# ==============================
with tabs[8]:
    st.subheader("🔄 Processos")
    if dfp is None or dfp.empty:
        st.info("Carregue **Gestão de Processos** em '🗂️ Dados & Mapeamento'.")
    else:
        df = dfp.copy()
        # filtros simples (processos)
        col1,col2,col3 = st.columns(3)
        with col1:
            emp_p = st.multiselect("Clientes", sorted(df.get("empresa", pd.Series(dtype=str)).dropna().unique().tolist())) if "empresa" in df.columns else []
        with col2:
            dep_p = st.multiselect("Departamentos", sorted(df.get("departamento", pd.Series(dtype=str)).dropna().unique().tolist())) if "departamento" in df.columns else []
        with col3:
            resp_p = st.multiselect("Responsáveis", sorted(df.get("responsavel", pd.Series(dtype=str)).dropna().unique().tolist())) if "responsavel" in df.columns else []

        mask = pd.Series(True, index=df.index)
        if "empresa" in df.columns and emp_p: mask &= df["empresa"].isin(emp_p)
        if "departamento" in df.columns and dep_p: mask &= df["departamento"].isin(dep_p)
        if "responsavel" in df.columns and resp_p: mask &= df["responsavel"].isin(resp_p)
        df = df[mask].copy()

        # KPIs rápidos
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

        # Gargalos: etapa com maior aging médio
        if "etapa_atual" in df.columns and "aging_dias" in df.columns:
            garg = df.groupby("etapa_atual")["aging_dias"].mean().reset_index().dropna()
            garg = garg.sort_values("aging_dias", ascending=False)
            st.plotly_chart(px.bar(garg, x="etapa_atual", y="aging_dias", title="Gargalo (aging médio por etapa)"),
                            use_container_width=True)
            st.dataframe(garg)

        # Produtividade por responsável (lead time concluído)
        if "responsavel" in df.columns and "lead_time_dias" in df.columns:
            prod = df[df["status"]=="Concluído"].groupby("responsavel")["lead_time_dias"].mean().reset_index().dropna()
            prod = prod.sort_values("lead_time_dias")
            st.plotly_chart(px.bar(prod.head(10), x="responsavel", y="lead_time_dias", title="Produtividade (menor lead time)"),
                            use_container_width=True)
            st.dataframe(prod.head(10))

# ==============================
# 🧪 Qualidade & Dicionário
# ==============================
with tabs[10]:
    st.subheader("🧪 Qualidade dos Dados & Dicionário")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** para validar mapeamento e qualidade.")
    else:
        df = dfe.copy()
        st.markdown("**Colunas presentes (Entregas):**")
        st.write(sorted(df.columns.tolist()))
        chk_cols = ["empresa","obrigacao","departamento","responsavel_entrega","data_entrega","prazo_tecnico","data_legal","status"]
        miss = [c for c in chk_cols if c not in df.columns]
        if miss:
            st.warning(f"⚠️ Colunas úteis ausentes: {', '.join(miss)}.")
        else:
            st.success("✅ Conjunto de colunas essenciais disponível.")
        st.markdown("**Nulos por coluna (top 15):**")
        nulls = df.isna().mean().sort_values(ascending=False).head(15).reset_index()
        nulls.columns = ["coluna","% nulos"]; nulls["% nulos"] = (nulls["% nulos"]*100).round(1)
        st.dataframe(nulls)
        st.markdown("**Amostra (50 primeiras):**")
        st.dataframe(df.head(50))
        st.download_button("⬇️ Exportar base filtrada (CSV)", apply_global_filters(df).to_csv(index=False).encode("utf-8"), "base_filtrada.csv", "text/csv")
