# app.py — Diagnóstico Acessórias (v5.0 simples)
# Suba a planilha → filtros claros por aba → dashboards objetivos
# Abas: Dados Brutos, KPIs, Departamentos, Responsáveis, Clientes, Processos

import difflib
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# =============================================================================
# Configuração
# =============================================================================
st.set_page_config(page_title="Diagnóstico Acessórias", layout="wide")
st.title("📊 Diagnóstico Acessórias — v5.0 (simples e objetivo)")
st.caption("Fluxo: ① Dados Brutos → ② KPIs & Dashboards por aba → ③ Exportar resultados")

# =============================================================================
# Leitura robusta de arquivos
# =============================================================================
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

def try_read_excel_or_csv(uploaded_file) -> pd.DataFrame:
    """Tenta Excel (vários engines) e cai para CSV (vários encodings)."""
    name = (getattr(uploaded_file, "name", "") or "").lower()

    def _try(fn, *a, **k):
        try:
            uploaded_file.seek(0)
            return fn(*a, **k)
        except Exception:
            return None

    # Excel
    if name.endswith((".xlsx", ".xlsm")):
        df = _try(pd.read_excel, uploaded_file, engine="openpyxl", dtype=str)
        if df is not None: return df
    if name.endswith(".xlsb"):
        df = _try(pd.read_excel, uploaded_file, engine="pyxlsb", dtype=str)
        if df is not None: return df
    if name.endswith(".xls"):
        # xlrd (xls antigo)
        df = _try(pd.read_excel, uploaded_file, engine="xlrd", dtype=str)
        if df is not None: return df
        # às vezes .xls abre com openpyxl (quando é na verdade xlsx renomeado)
        df = _try(pd.read_excel, uploaded_file, engine="openpyxl", dtype=str)
        if df is not None: return df
    # Tenta qualquer engine possível
    for eng in ("openpyxl", "pyxlsb", "xlrd"):
        df = _try(pd.read_excel, uploaded_file, engine=eng, dtype=str)
        if df is not None: return df

    # CSV robusto
    return read_any_csv(uploaded_file)

# =============================================================================
# Normalização & Enriquecimento
# =============================================================================
def normalize_headers(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def to_datetime_safe(s):
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def s_get(df, candidates, default=np.nan):
    """Devolve a 1ª coluna existente entre candidates (string ou lista)."""
    if isinstance(candidates, str):
        return df[candidates] if candidates in df.columns else pd.Series(default, index=df.index)
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series(default, index=df.index)

def norm_status(x):
    if not isinstance(x, str): return x
    s = x.strip().lower()
    m = {
        "concluida":"Concluída","concluída":"Concluída","concluido":"Concluída","concluído":"Concluída",
        "finalizado":"Concluída","feito":"Concluída",
        "pendente":"Pendente","em aberto":"Pendente","aberto":"Pendente","em andamento":"Pendente"
    }
    return m.get(s, x)

def canonicalize_entregas(df: pd.DataFrame) -> pd.DataFrame:
    """Cria colunas canônicas para a análise: empresa, dep, colaborador."""
    if df is None or df.empty: return df
    df = df.copy()
    if "empresa" not in df.columns:
        df["empresa"] = s_get(df, ["empresa","cliente","razao_social","razão_social"], default=np.nan)
    if "dep" not in df.columns:
        df["dep"] = s_get(df, ["departamento","setor","area","área"], default=np.nan)
    if "colaborador" not in df.columns:
        df["colaborador"] = s_get(df, ["responsavel_entrega","responsável_entrega","responsavel","responsável"], default=np.nan)
    return df

def enrich_entregas(df_ent: pd.DataFrame) -> pd.DataFrame:
    if df_ent is None or df_ent.empty: return df_ent
    df = normalize_headers(df_ent.copy())

    # Datas principais
    df["data_entrega"]    = to_datetime_safe(s_get(df, "data_entrega", np.nan))
    df["prazo_tecnico"]   = to_datetime_safe(s_get(df, "prazo_tecnico", np.nan))
    df["data_legal"]      = to_datetime_safe(s_get(df, "data_legal", np.nan))
    df["data_vencimento"] = to_datetime_safe(s_get(df, "data_vencimento", np.nan))
    df["competencia"]     = to_datetime_safe(s_get(df, "competencia", np.nan))

    if "status" in df.columns:
        df["status"] = df["status"].map(norm_status).fillna(df["status"])

    de, pt, dl = df["data_entrega"], df["prazo_tecnico"], df["data_legal"]

    # Métricas base Técnico
    has_t = de.notna() & pt.notna()
    df["no_prazo_tecnico"]    = np.where(has_t & (de <= pt), True, np.where(has_t, False, np.nan))
    df["antecipada_tecnico"]  = has_t & (de < pt)
    df["atraso_tecnico_dias"] = np.where(has_t, (de - pt).dt.days.clip(lower=0), np.nan)

    # Métricas base Legal
    has_l = de.notna() & dl.notna()
    df["no_prazo_legal"]      = np.where(has_l & (de <= dl), True, np.where(has_l, False, np.nan))
    df["antecipada_legal"]    = has_l & (de < dl)
    df["atraso_legal_dias"]   = np.where(has_l, (de - dl).dt.days.clip(lower=0), np.nan)

    return canonicalize_entregas(df)

def enrich_procs(dfp: pd.DataFrame) -> pd.DataFrame:
    if dfp is None or dfp.empty: return dfp
    df = normalize_headers(dfp.copy())
    df["abertura"]      = to_datetime_safe(s_get(df, "abertura", np.nan))
    df["conclusao"]     = to_datetime_safe(s_get(df, "conclusao", np.nan))
    df["proximo_prazo"] = to_datetime_safe(s_get(df, "proximo_prazo", np.nan))
    today = pd.to_datetime(datetime.now().date())
    df["lead_time_dias"] = np.where(df["conclusao"].notna() & df["abertura"].notna(), (df["conclusao"] - df["abertura"]).dt.days, np.nan)
    df["aging_dias"]     = np.where(df["conclusao"].isna() & df["abertura"].notna(), (today - df["abertura"]).dt.days, np.nan)
    if "status" not in df.columns:
        df["status"] = np.where(df["conclusao"].notna(), "Concluído", "Em andamento")
    if "empresa" not in df.columns:
        df["empresa"] = s_get(df, ["empresa","cliente","razao_social","razão_social"], default=np.nan)
    if "dep" not in df.columns:
        df["dep"] = s_get(df, ["departamento","setor","area","área"], default=np.nan)
    if "colaborador" not in df.columns:
        df["colaborador"] = s_get(df, ["responsavel","responsável"], default=np.nan)
    return df

def get_basis(basis: str):
    k = (basis or "Técnico").lower()
    if k.startswith("t"):
        return dict(no_prazo="no_prazo_tecnico", atraso="atraso_tecnico_dias", antecipada="antecipada_tecnico", label="% no prazo (técnico)")
    return dict(no_prazo="no_prazo_legal", atraso="atraso_legal_dias", antecipada="antecipada_legal", label="% no prazo (legal)")

# =============================================================================
# Sessão
# =============================================================================
for k in ["dfe", "dfp"]:
    if k not in st.session_state: st.session_state[k] = None

# =============================================================================
# Sidebar — Config simples
# =============================================================================
with st.sidebar:
    st.header("⚙️ Configuração geral")
    basis = st.radio("Base de análise", ["Técnico", "Legal"], horizontal=True, index=0)
    meta_ok = st.number_input("Meta de % no prazo (OK)", min_value=50.0, max_value=100.0, value=95.0, step=0.5)
    st.caption("Usada no ranking de risco.")
    st.divider()
    st.caption("Dica: Carregue a planilha em **Dados Brutos** e use os filtros no topo de cada aba.")

# =============================================================================
# Componentes de filtro (por aba)
# =============================================================================
def date_candidates(df: pd.DataFrame):
    keys = ["competencia","data_vencimento","data_entrega","data_legal","prazo_tecnico","abertura","conclusao"]
    cands = [c for c in keys if c in df.columns]
    # inclui qualquer outra coluna datetime
    for c in df.columns:
        if c not in cands and pd.api.types.is_datetime64_any_dtype(df[c]):
            cands.append(c)
    return cands

def filter_panel(df: pd.DataFrame, key: str, show_cols=("empresa","dep","colaborador"), default_date=None):
    """Retorna df filtrado + dict seleções. Filtros compactos e claros."""
    if df is None or df.empty:
        st.info("Carregue a base em **Dados Brutos**.")
        return df, {}
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
        with c1:
            dcols = date_candidates(df)
            default_idx = 0
            if default_date and default_date in dcols:
                default_idx = dcols.index(default_date)
            dcol = st.selectbox("Coluna de data", ["<sem filtro>"] + dcols, index=(default_idx+1 if dcols else 0), key=f"dcol_{key}")
        with c2:
            di = st.date_input("De", value=None, key=f"di_{key}") if dcol and dcol != "<sem filtro>" else None
        with c3:
            dfim = st.date_input("Até", value=None, key=f"df_{key}") if dcol and dcol != "<sem filtro>" else None
        with c4:
            topn = st.number_input("Top N", min_value=5, max_value=50, value=10, step=1, key=f"topn_{key}")

        with st.expander("Filtros avançados"):
            cols = st.columns(3)
            sel = {}
            for i, c in enumerate(show_cols):
                if c in df.columns:
                    label = "Departamento" if c=="dep" else ("Responsável" if c=="colaborador" else "Cliente")
                    with cols[i%3]:
                        sel[c] = st.multiselect(label, sorted(df[c].dropna().astype(str).unique().tolist()), key=f"{c}_{key}")
                else:
                    sel[c] = []

        # aplicar filtros
        mask = pd.Series(True, index=df.index)
        if dcol and dcol != "<sem filtro>" and dcol in df.columns:
            dts = pd.to_datetime(df[dcol], errors="coerce")
            if di:   mask &= dts.dt.date >= di
            if dfim: mask &= dts.dt.date <= dfim
        for c, v in sel.items():
            if v and c in df.columns:
                mask &= df[c].astype(str).isin(v)

        fdf = df[mask].copy()
        # botão limpar
        st.caption(f"Linhas após filtro: **{len(fdf):,}**".replace(",", "."))
        return fdf, {"dcol": dcol, "di": di, "df": dfim, "topn": topn, **sel}

def safe_metric(value, fmt="num"):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    if fmt == "pct":
        return f"{value:,.1f}%".replace(",", ".")
    if fmt == "num1":
        return f"{value:,.1f}".replace(",", ".")
    return f"{int(value):,}".replace(",", ".")

def ranking(df, group_col, metric, top=10, asc=False):
    """metric: dict keys -> 'no_prazo' | 'qtd' | 'antecipada' | 'atraso' (nome da coluna)"""
    if df is None or df.empty or group_col not in df.columns:
        return pd.DataFrame(columns=[group_col, "valor"])
    if metric.get("qtd"):
        s = df.groupby(group_col).size()
    elif "no_prazo" in metric and metric["no_prazo"] in df.columns:
        s = df.groupby(group_col)[metric["no_prazo"]].mean() * 100
    elif "antecipada" in metric and metric["antecipada"] in df.columns:
        s = df.groupby(group_col)[metric["antecipada"]].sum()
    elif "atraso" in metric and metric["atraso"] in df.columns:
        s = df.groupby(group_col)[metric["atraso"]].mean()
    else:
        return pd.DataFrame(columns=[group_col, "valor"])
    out = s.reset_index(name="valor").replace({np.inf: np.nan, -np.inf: np.nan})
    out = out.dropna(subset=["valor"]).sort_values("valor", ascending=asc).head(top)
    return out

# =============================================================================
# Tabs
# =============================================================================
tabs = st.tabs([
    "🗂️ Dados Brutos",
    "🏁 KPIs Gerais",
    "🏢 Departamentos",
    "🧑‍💼 Responsáveis",
    "👥 Clientes",
    "🔄 Processos"
])

# =============================================================================
# Aba 1 — Dados Brutos
# =============================================================================
with tabs[0]:
    st.subheader("1) Envie suas bases")
    c1, c2 = st.columns(2)
    with c1:
        up_ent = st.file_uploader("Gestão de Entregas (CSV/Excel)", type=["csv","xls","xlsx","xlsm","xlsb"], key="up_ent")
    with c2:
        up_prc = st.file_uploader("Gestão de Processos (opcional) (CSV/Excel)", type=["csv","xls","xlsx","xlsm","xlsb"], key="up_prc")

    if up_ent:
        raw = try_read_excel_or_csv(up_ent)
        dfe = enrich_entregas(raw)
        st.session_state["dfe"] = dfe
        st.success(f"Entregas carregadas: {len(dfe):,}".replace(",", "."))
    if up_prc:
        rawp = try_read_excel_or_csv(up_prc)
        dfp = enrich_procs(rawp)
        st.session_state["dfp"] = dfp
        st.info(f"Processos carregados: {len(dfp):,}".replace(",", "."))

    dfe = st.session_state.get("dfe")
    dfp = st.session_state.get("dfp")

    st.markdown("### Visualização rápida")
    if dfe is not None and not dfe.empty:
        df_show, _ = filter_panel(dfe, key="raw", show_cols=("empresa","dep","colaborador"), default_date="competencia")
        st.dataframe(df_show)  # mostra tudo (pode ser grande)
        st.download_button("⬇️ Baixar (CSV filtrado)", df_show.to_csv(index=False).encode("utf-8"), "entregas_filtrado.csv", "text/csv")
    else:
        st.info("Envie a base de **Entregas** para visualizar.")

    if dfp is not None and not dfp.empty:
        with st.expander("Ver tabela de Processos"):
            st.dataframe(dfp)
            st.download_button("⬇️ Baixar Processos (CSV)", dfp.to_csv(index=False).encode("utf-8"), "processos.csv", "text/csv")

# =============================================================================
# Aba 2 — KPIs Gerais
# =============================================================================
with tabs[1]:
    st.subheader("2) KPIs Gerais")
    dfe = st.session_state.get("dfe")
    if dfe is None or dfe.empty:
        st.info("Envie a base em **Dados Brutos**.")
    else:
        b = get_basis(basis)
        dfg, sel = filter_panel(dfe, key="kpi", show_cols=("empresa","dep","colaborador"), default_date="competencia")

        total = len(dfg)
        pct_prazo = dfg[b["no_prazo"]].mean()*100 if b["no_prazo"] in dfg.columns else np.nan
        atraso_med = dfg[b["atraso"]].mean() if b["atraso"] in dfg.columns else np.nan
        antecip = dfg[b["antecipada"]].sum() if b["antecipada"] in dfg.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(b["label"], safe_metric(pct_prazo, "pct"))
        c2.metric("Atraso médio (dias)", safe_metric(atraso_med, "num1"))
        c3.metric("Entregas antecipadas", safe_metric(antecip))
        c4.metric("Tarefas (base)", safe_metric(total))

        # Linha do tempo (mês)
        base_col = "competencia" if "competencia" in dfg.columns else ("data_vencimento" if "data_vencimento" in dfg.columns else "data_entrega")
        if base_col in dfg.columns and b["no_prazo"] in dfg.columns:
            tmp = dfg.copy()
            tmp["mes"] = pd.to_datetime(tmp[base_col], errors="coerce").dt.to_period("M").astype(str)
            tmp["no_prazo_flag"] = tmp[b["no_prazo"]].astype(float)
            g = tmp.groupby("mes").agg(pct=("no_prazo_flag","mean"), tarefas=("no_prazo_flag","size")).reset_index()
            g["pct_%"] = (g["pct"]*100).round(1)
            g = g.sort_values("mes")
            st.plotly_chart(px.line(g, x="mes", y="pct_%", title=f"{b['label']} por mês"), use_container_width=True)

        # Distribuição de atraso (apenas fora do prazo)
        if b["atraso"] in dfg.columns:
            late = dfg[dfg[b["atraso"]].fillna(0) > 0].copy()
            if not late.empty:
                bins = [-0.1,2,5,10,10000]; labels = ["1-2","3-5","6-10",">10"]
                late["faixa"] = pd.cut(late[b["atraso"]], bins=bins, labels=labels)
                dist = late["faixa"].value_counts().reindex(labels).fillna(0).reset_index()
                dist.columns = ["faixa","qtd"]
                st.plotly_chart(px.bar(dist, x="faixa", y="qtd", title="Atraso — distribuição (dias)"), use_container_width=True)

# =============================================================================
# Aba 3 — Departamentos
# =============================================================================
with tabs[2]:
    st.subheader("3) Departamentos")
    dfe = st.session_state.get("dfe")
    if dfe is None or dfe.empty:
        st.info("Envie a base em **Dados Brutos**.")
    else:
        b = get_basis(basis)
        dfg, sel = filter_panel(dfe, key="dep", show_cols=("dep","empresa"), default_date="competencia")
        topn = sel.get("topn", 10)

        r_qtd = ranking(dfg, "dep", {"qtd": True}, top=topn)
        r_prazo = ranking(dfg, "dep", {"no_prazo": b["no_prazo"]}, top=topn)
        r_atraso = ranking(dfg, "dep", {"atraso": b["atraso"]}, top=topn, asc=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Mais tarefas**")
            st.dataframe(r_qtd)
            if not r_qtd.empty:
                st.plotly_chart(px.bar(r_qtd, x="dep", y="valor", title="Tarefas por departamento"), use_container_width=True)
        with col2:
            st.markdown(f"**{b['label']} (Top {topn})**")
            st.dataframe(r_prazo)
            if not r_prazo.empty:
                st.plotly_chart(px.bar(r_prazo, x="dep", y="valor", title=b["label"]), use_container_width=True)

        st.markdown("**Atraso médio (menor é melhor)**")
        st.dataframe(r_atraso)
        if not r_atraso.empty:
            st.plotly_chart(px.bar(r_atraso, x="dep", y="valor", title="Atraso médio (dias)"), use_container_width=True)

# =============================================================================
# Aba 4 — Responsáveis
# =============================================================================
with tabs[3]:
    st.subheader("4) Responsáveis")
    dfe = st.session_state.get("dfe")
    if dfe is None or dfe.empty:
        st.info("Envie a base em **Dados Brutos**.")
    else:
        b = get_basis(basis)
        dfg, sel = filter_panel(dfe, key="col", show_cols=("colaborador","dep","empresa"), default_date="competencia")
        if "colaborador" not in dfg.columns or dfg["colaborador"].isna().all():
            st.info("Não encontrei coluna de responsável. Tente nomear como 'responsavel' ou 'responsavel_entrega'.")
        else:
            topn = sel.get("topn", 10)
            r_qtd = ranking(dfg, "colaborador", {"qtd": True}, top=topn)
            r_prazo = ranking(dfg, "colaborador", {"no_prazo": b["no_prazo"]}, top=topn)
            r_antec = ranking(dfg, "colaborador", {"antecipada": b["antecipada"]}, top=topn)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Volume de tarefas**")
                st.dataframe(r_qtd)
                if not r_qtd.empty:
                    st.plotly_chart(px.bar(r_qtd, x="colaborador", y="valor", title="Volume"), use_container_width=True)
            with c2:
                st.markdown(f"**{b['label']}**")
                st.dataframe(r_prazo)
                if not r_prazo.empty:
                    st.plotly_chart(px.bar(r_prazo, x="colaborador", y="valor", title=b["label"]), use_container_width=True)

            st.markdown("**Entregas antecipadas**")
            st.dataframe(r_antec)
            if not r_antec.empty:
                st.plotly_chart(px.bar(r_antec, x="colaborador", y="valor", title="Antecipadas"), use_container_width=True)

# =============================================================================
# Aba 5 — Clientes
# =============================================================================
with tabs[4]:
    st.subheader("5) Clientes")
    dfe = st.session_state.get("dfe")
    if dfe is None or dfe.empty:
        st.info("Envie a base em **Dados Brutos**.")
    else:
        b = get_basis(basis)
        dfg, sel = filter_panel(dfe, key="cli", show_cols=("empresa","dep"), default_date="competencia")
        topn = sel.get("topn", 10)

        r_qtd = ranking(dfg, "empresa", {"qtd": True}, top=topn)
        r_prazo = ranking(dfg, "empresa", {"no_prazo": b["no_prazo"]}, top=topn)
        r_antec = ranking(dfg, "empresa", {"antecipada": b["antecipada"]}, top=topn)

        # atrasadas (contagem)
        if b["atraso"] in dfg.columns:
            atrasadas = dfg[dfg[b["atraso"]].fillna(0) > 0].groupby("empresa").size().reset_index(name="valor").sort_values("valor", ascending=False).head(topn)
        else:
            atrasadas = pd.DataFrame(columns=["empresa","valor"])

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Mais tarefas**")
            st.dataframe(r_qtd)
            if not r_qtd.empty:
                st.plotly_chart(px.bar(r_qtd, x="empresa", y="valor", title="Tarefas por cliente"), use_container_width=True)
        with c2:
            st.markdown(f"**{b['label']}**")
            st.dataframe(r_prazo)
            if not r_prazo.empty:
                st.plotly_chart(px.bar(r_prazo, x="empresa", y="valor", title=b["label"]), use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Entregas antecipadas**")
            st.dataframe(r_antec)
            if not r_antec.empty:
                st.plotly_chart(px.bar(r_antec, x="empresa", y="valor", title="Antecipadas"), use_container_width=True)
        with c4:
            st.markdown("**Entregas atrasadas (qtd)**")
            st.dataframe(atrasadas)
            if not atrasadas.empty:
                st.plotly_chart(px.bar(atrasadas, x="empresa", y="valor", title="Atrasadas (qtd)"), use_container_width=True)

# =============================================================================
# Aba 6 — Processos (opcional)
# =============================================================================
with tabs[5]:
    st.subheader("6) Processos (se enviado)")
    dfp = st.session_state.get("dfp")
    if dfp is None or dfp.empty:
        st.info("Envie a base de **Processos** em Dados Brutos para ver esta aba.")
    else:
        dfp_f, sel = filter_panel(dfp, key="proc", show_cols=("empresa","dep","colaborador"), default_date="abertura")
        lead_med = dfp_f["lead_time_dias"].mean() if "lead_time_dias" in dfp_f.columns else np.nan
        aging_med = dfp_f["aging_dias"].mean() if "aging_dias" in dfp_f.columns else np.nan
        em_and = int((dfp_f["status"]=="Em andamento").sum()) if "status" in dfp_f.columns else 0
        concl = int((dfp_f["status"]=="Concluído").sum()) if "status" in dfp_f.columns else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Lead time médio (dias)", safe_metric(lead_med, "num1"))
        m2.metric("Aging médio (dias)", safe_metric(aging_med, "num1"))
        m3.metric("Em andamento", safe_metric(em_and))
        m4.metric("Concluídos", safe_metric(concl))

        if "etapa_atual" in dfp_f.columns:
            funil = dfp_f["etapa_atual"].value_counts().reset_index()
            funil.columns = ["etapa","qtd"]
            st.plotly_chart(px.bar(funil, x="etapa", y="qtd", title="Funil por etapa"), use_container_width=True)

        if "etapa_atual" in dfp_f.columns and "aging_dias" in dfp_f.columns:
            garg = dfp_f.groupby("etapa_atual")["aging_dias"].mean().reset_index().dropna().sort_values("aging_dias", ascending=False)
            st.plotly_chart(px.bar(garg, x="etapa_atual", y="aging_dias", title="Gargalos (aging médio)"), use_container_width=True)

        if "colaborador" in dfp_f.columns and "lead_time_dias" in dfp_f.columns:
            prod = dfp_f[dfp_f["status"]=="Concluído"].groupby("colaborador")["lead_time_dias"].mean().reset_index().dropna().sort_values("lead_time_dias")
            n = sel.get("topn", 10)
            st.plotly_chart(px.bar(prod.head(n), x="colaborador", y="lead_time_dias", title="Produtividade (menor lead time)"), use_container_width=True)

        with st.expander("Ver tabela (Processos filtrados)"):
            st.dataframe(dfp_f)
            st.download_button("⬇️ Baixar Processos filtrados (CSV)", dfp_f.to_csv(index=False).encode("utf-8"), "processos_filtrado.csv", "text/csv")
