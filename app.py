# app.py — Acessórias — Dashboard Claro (v2)
# - Auto-detectar mapeamento
# - Leitura robusta Excel/CSV
# - Base Técnico/Legal (toggle)
# - Metas e semáforos
# - Dashboards: Clientes, Departamentos, Colaboradores, Linha do Tempo
# - Drill-down + export CSV

import difflib
from datetime import date
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ==============================
# Configuração do app
# ==============================
st.set_page_config(page_title="Acessórias — Dashboard Claro (v2)", layout="wide")
st.title("📊 Acessórias — Dashboard Claro (v2)")
st.caption("Dashboards por Cliente, Departamento e Colaborador com metas, semáforos e drill-down. O botão **Auto-detectar** sugere o mapeamento automaticamente — você pode ajustar manualmente.")

# ==============================
# Leitura robusta de arquivos
# ==============================
def read_any_csv(uploaded_file) -> pd.DataFrame:
    """Lê CSV tentando múltiplas codificações e separadores."""
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
    # Último recurso: ignora linhas ruins
    try:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    except Exception as e2:
        st.error(f"Não consegui abrir o CSV. Último erro: {last_err}")
        raise

def try_read_excel(uploaded_file) -> pd.DataFrame:
    """Lê Excel com detecção de formato + fallbacks.
       .xlsx/.xlsm -> openpyxl | .xlsb -> pyxlsb | .xls -> xlrd (fallback openpyxl) | fallback: CSV
    """
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
        # muitos ".xls" são .xlsx renomeados
        df = _try(pd.read_excel, uploaded_file, engine="openpyxl", dtype=str)
        if df is not None: return df

    # Heurística (extensão errada)
    for eng in ("openpyxl", "pyxlsb", "xlrd"):
        df = _try(pd.read_excel, uploaded_file, engine=eng, dtype=str)
        if df is not None: return df

    # CSV renomeado
    uploaded_file.seek(0)
    return read_any_csv(uploaded_file)

# ==============================
# Helpers gerais
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
    st.caption("**Auto-detectar** procura no nomes das colunas aquilo que você precisa mapear. Depois você pode ajustar manualmente.")
    st.dataframe(df.head(5))

    cols = list(df.columns)
    req_guess = guess_mapping(cols, required)
    opt_guess = guess_mapping(cols, optional)

    ctop1, ctop2 = st.columns([1,1])
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
# Métricas de Entregas (técnico e legal)
# ==============================
def enrich_entregas(df_ent: pd.DataFrame) -> pd.DataFrame:
    if df_ent is None or df_ent.empty: return df_ent
    df = df_ent.copy()
    df = to_datetime_cols(df, ["data_vencimento","data_entrega","competencia","prazo_tecnico","data_legal"])
    if "status" in df.columns:
        df["status"] = df["status"].map(norm_status).fillna(df["status"])
    # Técnico
    df["no_prazo_tecnico"] = np.where(
        df.get("data_entrega").notna() & df.get("prazo_tecnico").notna() & (df["data_entrega"] <= df["prazo_tecnico"]),
        True,
        np.where(df.get("data_entrega").notna() & df.get("prazo_tecnico").notna(), False, np.nan)
    )
    df["antecipada_tecnico"] = np.where(
        df.get("data_entrega").notna() & df.get("prazo_tecnico").notna() & (df["data_entrega"] < df["prazo_tecnico"]),
        True, False
    )
    df["atraso_tecnico_dias"] = np.where(
        df.get("data_entrega").notna() & df.get("prazo_tecnico").notna(),
        s_dt_days(df["data_entrega"] - df["prazo_tecnico"]).clip(lower=0), np.nan
    )
    # Legal
    df["no_prazo_legal"] = np.where(
        df.get("data_entrega").notna() & df.get("data_legal").notna() & (df["data_entrega"] <= df["data_legal"]),
        True,
        np.where(df.get("data_entrega").notna() & df.get("data_legal").notna(), False, np.nan)
    )
    df["antecipada_legal"] = np.where(
        df.get("data_entrega").notna() & df.get("data_legal").notna() & (df["data_entrega"] < df["data_legal"]),
        True, False
    )
    df["atraso_legal_dias"] = np.where(
        df.get("data_entrega").notna() & df.get("data_legal").notna(),
        s_dt_days(df["data_entrega"] - df["data_legal"]).clip(lower=0), np.nan
    )
    return df

def get_basis_columns(basis: str):
    key = basis.lower()
    if key.startswith("t"):
        return dict(no_prazo="no_prazo_tecnico", atraso_dias="atraso_tecnico_dias", antecipada="antecipada_tecnico", label="% no prazo (técnico)")
    else:
        return dict(no_prazo="no_prazo_legal", atraso_dias="atraso_legal_dias", antecipada="antecipada_legal", label="% no prazo (legal)")

def global_filters(df: pd.DataFrame, who="global"):
    if df is None or df.empty: return df
    date_candidates = [c for c in df.columns if (pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in c for k in ["data","venc","entrega","competencia","legal","tecnico","técnico"]))]
    seen=set(); date_candidates=[x for x in date_candidates if not (x in seen or seen.add(x))]
    with st.expander("🎛️ Filtros Globais", expanded=True):
        col1,col2,col3 = st.columns(3)
        with col1:
            dcol = st.selectbox("Coluna de data para filtrar", ["<sem filtro>"] + date_candidates, index=1 if date_candidates else 0, key=f"dcol_{who}") if date_candidates else None
        with col2:
            di = st.date_input("De (data)", value=None, key=f"di_{who}") if dcol else None
        with col3:
            dfim = st.date_input("Até (data)", value=None, key=f"df_{who}") if dcol else None
        col4,col5,col6 = st.columns(3)
        with col4:
            emp_sel = st.multiselect("Clientes (empresa)", sorted(df.get("empresa", pd.Series(dtype=str)).dropna().unique().tolist())) if "empresa" in df.columns else []
        with col5:
            dep_sel = st.multiselect("Departamentos", sorted(df.get("departamento", pd.Series(dtype=str)).dropna().unique().tolist())) if "departamento" in df.columns else []
        with col6:
            colab_sel = st.multiselect("Colaboradores", sorted(df.get("responsavel_entrega", pd.Series(dtype=str)).dropna().unique().tolist())) if "responsavel_entrega" in df.columns else []
    mask = pd.Series(True, index=df.index)
    if dcol and dcol != "<sem filtro>":
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
    out = out.dropna(subset=["valor"])
    out = out.sort_values("valor", ascending=(how=="asc")).head(top)
    return out

# ==============================
# Sidebar — metas e base (técnico x legal)
# ==============================
with st.sidebar:
    st.header("⚙️ Configurações")
    basis = st.radio("Base dos KPIs", ["Técnico", "Legal"], index=0, horizontal=True)
    meta_ok = st.number_input("Meta OK (≥ %)", min_value=50.0, max_value=100.0, value=95.0, step=0.5)
    meta_atencao = st.number_input("Meta Atenção (≥ %)", min_value=0.0, max_value=100.0, value=85.0, step=0.5)
    st.caption("Semáforo: **Verde** ≥ OK | **Amarelo** ≥ Atenção | **Vermelho** < Atenção")
basis_cols = get_basis_columns(basis)

def badge_pct(v):
    if pd.isna(v): return "—"
    if v >= meta_ok: return f"🟢 {v:,.1f}%"
    if v >= meta_atencao: return f"🟡 {v:,.1f}%"
    return f"🔴 {v:,.1f}%"

# ==============================
# Abas
# ==============================
tabs = st.tabs(["🏠 Resumo", "👥 Clientes", "🏢 Departamentos", "🧑‍💼 Colaboradores", "📆 Linha do Tempo", "🗂️ Dados (Upload & Mapeamento)"])

# ==============================
# Aba: Dados (Upload & Mapeamento)
# ==============================
with tabs[5]:
    st.subheader("🗂️ Upload & Mapeamento")
    st.caption("Carregue os arquivos e mapeie as colunas. **Auto-detectar** sugere o mapeamento; ajuste se necessário.")
    colA, colB = st.columns(2)
    with colA:
        up_entregas = st.file_uploader("Gestão de Entregas (CSV)", type=["csv"], key="up_ent")
        up_solic    = st.file_uploader("Solicitações (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_sol")
    with colB:
        up_obrig    = st.file_uploader("Lista de Obrigações (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_obr")
        up_resp     = st.file_uploader("Responsáveis & Departamentos (XLS/XLSX/XLSM/XLSB/CSV)", type=["xls","xlsx","xlsm","xlsb","csv"], key="up_resp")

    for key in ["dfe","dfs","dfo","dfr"]:
        if key not in st.session_state: st.session_state[key] = None

    # Entregas
    if up_entregas:
        raw = read_any_csv(up_entregas); raw = normalize_headers(raw)
        required = ["empresa","obrigacao","data_vencimento","status"]
        optional = ["cnpj","departamento","responsavel_prazo","responsavel_entrega","competencia","data_entrega","protocolo","prazo_tecnico","data_legal"]
        m = mapping_wizard(raw, "Entregas", required, optional, "ent")
        dfe = raw.rename(columns=m)
        st.session_state["dfe"] = enrich_entregas(dfe)
        st.success("Entregas carregadas e enriquecidas.")

    # Solicitações
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

    # Obrigações (opcional / referência)
    if up_obrig:
        name = up_obrig.name.lower()
        raw = try_read_excel(up_obrig) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_obrig)
        raw = normalize_headers(raw)
        required = ["obrigacao","departamento"]
        optional = ["mini","empresa","responsavel","periodicidade","prazo_mensal","alerta_dias","observacao"]
        m = mapping_wizard(raw, "Lista de Obrigações", required, optional, "obr")
        dfo = raw.rename(columns=m)
        st.session_state["dfo"] = dfo
        st.info("Lista de Obrigações carregada. (Referência)")

    # Responsáveis (opcional / referência)
    if up_resp:
        name = up_resp.name.lower()
        raw = try_read_excel(up_resp) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_resp)
        raw = normalize_headers(raw)
        required = ["responsavel","departamento"]
        optional = ["email","cargo"]
        m = mapping_wizard(raw, "Responsáveis & Departamentos", required, optional, "resp")
        dfr = raw.rename(columns=m)
        st.session_state["dfr"] = dfr
        st.info("Responsáveis carregados.")

# ==============================
# Dados em sessão
# ==============================
dfe = st.session_state.get("dfe")  # entregas enriquecidas
dfs = st.session_state.get("dfs")  # solicitações

# ==============================
# Aba: Resumo
# ==============================
with tabs[0]:
    st.subheader("🔎 Resumo Executivo")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** em '🗂️ Dados' para ver o resumo.")
    else:
        dfg = global_filters(dfe, who="home")
        total = len(dfg)
        pct_prazo = float((dfg[get_basis_columns(basis)["no_prazo"]].mean()*100)) if get_basis_columns(basis)["no_prazo"] in dfg.columns else np.nan
        pct_atraso = 100 - pct_prazo if not np.isnan(pct_prazo) else np.nan
        antec = int(dfg[get_basis_columns(basis)["antecipada"]].sum()) if get_basis_columns(basis)["antecipada"] in dfg.columns else 0
        soli_total = len(dfs) if isinstance(dfs, pd.DataFrame) else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric(get_basis_columns(basis)["label"], f"{pct_prazo:,.1f}%".replace(",","."))  # valor numérico limpo
        c2.metric("% atraso (base)", f"{pct_atraso:,.1f}%".replace(",","."))
        c3.metric("Entregas antecipadas (base)", f"{antec:,}".replace(",","."))
        c4.metric("Solicitações (total)", f"{soli_total:,}".replace(",","."))

        st.markdown(f"#### 🏆 Top 10 Departamentos — {get_basis_columns(basis)['label']}")
        rdep = ranking(dfg, "departamento", "pct_no_prazo", get_basis_columns(basis), how="desc", top=10) if "departamento" in dfg.columns else pd.DataFrame()
        st.dataframe(rdep)
        if not rdep.empty:
            st.plotly_chart(px.bar(rdep, x="departamento", y="valor", title=get_basis_columns(basis)["label"]+" — Departamentos"), use_container_width=True)
            escolha = st.selectbox("🔎 Ver detalhes do departamento", ["<selecione>"] + rdep["departamento"].tolist(), key="det_dep_home")
            if escolha and escolha != "<selecione>":
                det = dfg[dfg["departamento"] == escolha].copy()
                st.dataframe(det)
                st.download_button("⬇️ Baixar detalhes (CSV)", det.to_csv(index=False).encode("utf-8"), f"detalhes_{escolha}_departamento.csv", "text/csv")

# ==============================
# Aba: Clientes
# ==============================
with tabs[1]:
    st.subheader("👥 Clientes — Rankings rápidos")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** em '🗂️ Dados'.")
    else:
        dfg = global_filters(dfe, who="cli")
        col1,col2 = st.columns(2)
        with col1:
            st.markdown("##### Clientes com mais **tarefas** (Entregas)")
            r1 = ranking(dfg, "empresa", "qtd_tarefas", get_basis_columns(basis), top=10)
            st.dataframe(r1)
            if not r1.empty:
                st.plotly_chart(px.bar(r1, x="empresa", y="valor", title="Tarefas por Cliente (Entregas)"), use_container_width=True)
            sel1 = st.selectbox("🔎 Detalhar cliente (tarefas)", ["<selecione>"] + r1["empresa"].tolist() if not r1.empty else ["<selecione>"], key="cli_r1")
            if sel1 and sel1 != "<selecione>":
                det = dfg[dfg["empresa"] == sel1].copy()
                st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_tarefas_{sel1}.csv", "text/csv")
        with col2:
            st.markdown(f"##### Clientes com mais **entregas antecipadas** ({basis})")
            r2 = ranking(dfg, "empresa", "qtd_antecipadas", get_basis_columns(basis), top=10)
            st.dataframe(r2)
            if not r2.empty:
                st.plotly_chart(px.bar(r2, x="empresa", y="valor", title=f"Antecipadas ({basis}) por Cliente"), use_container_width=True)
            sel2 = st.selectbox("🔎 Detalhar cliente (antecipadas)", ["<selecione>"] + r2["empresa"].tolist() if not r2.empty else ["<selecione>"], key="cli_r2")
            if sel2 and sel2 != "<selecione>":
                det = dfg[(dfg["empresa"] == sel2) & (dfg[get_basis_columns(basis)["antecipada"]] == True)].copy()
                st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_antecipadas_{sel2}.csv", "text/csv")

        # NOVO: clientes que mais solicitam (com base nas Solicitações)
        st.markdown("##### Clientes com mais **solicitações**")
        if isinstance(dfs, pd.DataFrame) and "empresa" in dfs.columns:
            dsol = dfs.copy()
            top_solic = dsol["empresa"].value_counts().reset_index()
            top_solic.columns = ["empresa","solicitacoes"]
            top_solic = top_solic.head(10)
            st.dataframe(top_solic)
            if not top_solic.empty:
                st.plotly_chart(px.bar(top_solic, x="empresa", y="solicitacoes", title="Top 10 Clientes por Solicitações"), use_container_width=True)
            sel4 = st.selectbox("🔎 Detalhar cliente (solicitações)", ["<selecione>"] + top_solic["empresa"].tolist() if not top_solic.empty else ["<selecione>"], key="cli_r4")
            if sel4 and sel4 != "<selecione>":
                dets = dsol[dsol["empresa"] == sel4].copy()
                st.dataframe(dets); st.download_button("⬇️ CSV", dets.to_csv(index=False).encode("utf-8"), f"detalhe_solicitacoes_{sel4}.csv", "text/csv")
        else:
            st.info("Para ver 'clientes que mais solicitam', carregue **Solicitações** em '🗂️ Dados'.")

        st.markdown(f"##### Clientes com **melhor {get_basis_columns(basis)['label']}**")
        r3 = ranking(dfg, "empresa", "pct_no_prazo", get_basis_columns(basis), top=10)
        st.dataframe(r3)
        if not r3.empty:
            st.plotly_chart(px.bar(r3, x="empresa", y="valor", title=get_basis_columns(basis)["label"]+" — Clientes"), use_container_width=True)
        sel3 = st.selectbox("🔎 Detalhar cliente (no prazo)", ["<selecione>"] + r3["empresa"].tolist() if not r3.empty else ["<selecione>"], key="cli_r3")
        if sel3 and sel3 != "<selecione>":
            det = dfg[dfg["empresa"] == sel3].copy()
            st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_prazo_{sel3}.csv", "text/csv")

# ==============================
# Aba: Departamentos
# ==============================
with tabs[2]:
    st.subheader(f"🏢 Departamentos — {get_basis_columns(basis)['label']} e atraso médio")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** em '🗂️ Dados'.")
    else:
        dfg = global_filters(dfe, who="dep")
        col1,col2 = st.columns(2)
        with col1:
            st.markdown(f"##### {get_basis_columns(basis)['label']} — Ranking")
            r1 = ranking(dfg, "departamento", "pct_no_prazo", get_basis_columns(basis), top=10)
            st.dataframe(r1)
            if not r1.empty:
                st.plotly_chart(px.bar(r1, x="departamento", y="valor", title=get_basis_columns(basis)['label']+" — Departamentos"), use_container_width=True)
            sd1 = st.selectbox("🔎 Detalhar departamento (prazo)", ["<selecione>"] + r1["departamento"].tolist() if not r1.empty else ["<selecione>"], key="dep_r1")
            if sd1 and sd1 != "<selecione>":
                det = dfg[dfg["departamento"] == sd1].copy()
                st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_dep_prazo_{sd1}.csv", "text/csv")
        with col2:
            st.markdown("##### Atraso médio (dias) — Ranking")
            r2 = ranking(dfg, "departamento", "atraso_medio", get_basis_columns(basis), how="asc", top=10)  # menor = melhor
            st.dataframe(r2)
            if not r2.empty:
                st.plotly_chart(px.bar(r2, x="departamento", y="valor", title="Atraso médio (dias) — Departamentos"), use_container_width=True)
            sd2 = st.selectbox("🔎 Detalhar departamento (atraso médio)", ["<selecione>"] + r2["departamento"].tolist() if not r2.empty else ["<selecione>"], key="dep_r2")
            if sd2 and sd2 != "<selecione>":
                det = dfg[dfg["departamento"] == sd2].copy()
                st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_dep_atraso_{sd2}.csv", "text/csv")

# ==============================
# Aba: Colaboradores
# ==============================
with tabs[3]:
    st.subheader(f"🧑‍💼 Colaboradores — {get_basis_columns(basis)['label']}, volume e antecipadas")
    if dfe is None or dfe.empty or "responsavel_entrega" not in dfe.columns:
        st.info("Carregue **Entregas** e mapeie **responsavel_entrega** em '🗂️ Dados'.")
    else:
        dfg = global_filters(dfe, who="col")
        col1,col2 = st.columns(2)
        with col1:
            st.markdown(f"##### {get_basis_columns(basis)['label']} — Ranking")
            r1 = ranking(dfg, "responsavel_entrega", "pct_no_prazo", get_basis_columns(basis), top=10)
            st.dataframe(r1)
            if not r1.empty:
                st.plotly_chart(px.bar(r1, x="responsavel_entrega", y="valor", title=get_basis_columns(basis)['label']+" — Colaboradores"), use_container_width=True)
            sc1 = st.selectbox("🔎 Detalhar colaborador (prazo)", ["<selecione>"] + r1["responsavel_entrega"].tolist() if not r1.empty else ["<selecione>"], key="col_r1")
            if sc1 and sc1 != "<selecione>":
                det = dfg[dfg["responsavel_entrega"] == sc1].copy()
                st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_col_prazo_{sc1}.csv", "text/csv")
        with col2:
            st.markdown("##### Volume de tarefas — Ranking")
            r2 = ranking(dfg, "responsavel_entrega", "qtd_tarefas", get_basis_columns(basis), top=10)
            st.dataframe(r2)
            if not r2.empty:
                st.plotly_chart(px.bar(r2, x="responsavel_entrega", y="valor", title="Volume de tarefas — Colaboradores"), use_container_width=True)
            sc2 = st.selectbox("🔎 Detalhar colaborador (volume)", ["<selecione>"] + r2["responsavel_entrega"].tolist() if not r2.empty else ["<selecione>"], key="col_r2")
            if sc2 and sc2 != "<selecione>":
                det = dfg[dfg["responsavel_entrega"] == sc2].copy()
                st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_col_volume_{sc2}.csv", "text/csv")

        st.markdown(f"##### Entregas **antecipadas** ({basis}) — Ranking")
        r3 = ranking(dfg, "responsavel_entrega", "qtd_antecipadas", get_basis_columns(basis), top=10)
        st.dataframe(r3)
        if not r3.empty:
            st.plotly_chart(px.bar(r3, x="responsavel_entrega", y="valor", title=f"Antecipadas ({basis}) — Colaboradores"), use_container_width=True)
        sc3 = st.selectbox("🔎 Detalhar colaborador (antecipadas)", ["<selecione>"] + r3["responsavel_entrega"].tolist() if not r3.empty else ["<selecione>"], key="col_r3")
        if sc3 and sc3 != "<selecione>":
            det = dfg[(dfg["responsavel_entrega"] == sc3) & (dfg[get_basis_columns(basis)["antecipada"]] == True)].copy()
            st.dataframe(det); st.download_button("⬇️ CSV", det.to_csv(index=False).encode("utf-8"), f"detalhe_col_antecipadas_{sc3}.csv", "text/csv")

# ==============================
# Aba: Linha do Tempo (mensal)
# ==============================
with tabs[4]:
    st.subheader(f"📆 Linha do Tempo — {get_basis_columns(basis)['label']} por mês")
    if dfe is None or dfe.empty:
        st.info("Carregue **Entregas** em '🗂️ Dados'.")
    else:
        df = dfe.copy()
        # competência mensal segura
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
        df["no_prazo_flag"] = df[get_basis_columns(basis)["no_prazo"]].astype("float")
        g = df.groupby("mes").agg(no_prazo=("no_prazo_flag","mean"), tarefas=("no_prazo_flag","size")).reset_index()
        g["no_prazo_%"] = g["no_prazo"] * 100
        st.dataframe(g[["mes","tarefas","no_prazo_%"]].sort_values("mes"))
        try:
            st.plotly_chart(px.bar(g, x="mes", y="no_prazo_%", title=get_basis_columns(basis)['label']+" por mês"), use_container_width=True)
        except Exception:
            pass
