
import difflib
from datetime import date
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ===================== Setup =====================
st.set_page_config(page_title="Acessórias — Dashboard Único", layout="wide")
st.title("📊 Acessórias — Dashboard Único")
st.caption("Upload por cliente → mapeie colunas → filtre por período → calcule métricas (prazo técnico/legal) → gere relatórios.")

# ===================== Helpers (null-safe) =====================
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

def read_any_csv(uploaded_file) -> pd.DataFrame:
    try:
        return pd.read_csv(uploaded_file, sep=None, engine="python")
    except Exception:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, sep=";", engine="python", encoding="utf-8", dtype=str)

def try_read_excel(uploaded_file) -> pd.DataFrame:
    try:
        return pd.read_excel(uploaded_file, dtype=str)
    except Exception:
        try:
            return pd.read_excel(uploaded_file, engine="xlrd", dtype=str)
        except Exception as e:
            st.error(f"Não consegui ler o arquivo Excel: {e}")
            raise

def normalize_headers(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def to_datetime_cols(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    return df

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
            guesses[t] = t; continue
        best = difflib.get_close_matches(t, df_cols, n=1, cutoff=0.6)
        guesses[t] = best[0] if best else ""
    return guesses

def mapping_wizard(df, title, required, optional, key):
    st.subheader(f"🧭 {title} — Mapeamento de Colunas")
    st.caption("Use **Auto-detectar** para sugestões; ajuste manual se precisar.")
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
        if st.button("🗑️ Limpar mapeamento", key=f"clear_{key}"):
            st.session_state[f"map_req_{key}"] = {t:"" for t in required}
            st.session_state[f"map_opt_{key}"] = {t:"" for t in optional}

    req_state = st.session_state.get(f"map_req_{key}") or req_guess
    opt_state = st.session_state.get(f"map_opt_{key}") or opt_guess

    st.markdown("**Obrigatórios**")
    req_cols = st.columns(3)
    mapped_req = {}
    for i, t in enumerate(required):
        with req_cols[i%3]:
            mapped_req[t] = st.selectbox(f"{t}", options=[""]+cols, index=([""]+cols).index(req_state.get(t,"")) if req_state.get(t,"") in ([""]+cols) else 0, key=f"{key}_req_{t}")

    st.markdown("**Opcionais**")
    opt_cols = st.columns(3)
    mapped_opt = {}
    for i, t in enumerate(optional):
        with opt_cols[i%3]:
            mapped_opt[t] = st.selectbox(f"{t}", options=[""]+cols, index=([""]+cols).index(opt_state.get(t,"")) if opt_state.get(t,"") in ([""]+cols) else 0, key=f"{key}_opt_{t}")

    missing = [t for t in required if not mapped_req.get(t)]
    if missing:
        st.warning(f"Mapeie os campos obrigatórios: {', '.join(missing)}")
    else:
        st.success("✅ Mapeamento mínimo completo")

    merged = mapped_req.copy(); merged.update({k:v for k,v in mapped_opt.items() if v})
    return merged

def apply_mapping(df: pd.DataFrame, mapping: dict):
    return df.rename(columns=mapping)

def filter_panel(df, defaults=None, who="ent"):
    if df is None or len(df)==0:
        st.info("Nenhum dado para filtrar ainda."); return df
    defaults = defaults or {}
    emp = sorted(df.get("empresa", pd.Series(dtype=str)).dropna().unique().tolist()) if "empresa" in df.columns else []
    dep = sorted(df.get("departamento", pd.Series(dtype=str)).dropna().unique().tolist()) if "departamento" in df.columns else []
    res_cols = [c for c in ["responsavel","responsavel_entrega","responsavel_prazo"] if c in df.columns]
    res = sorted(pd.concat([df[c] for c in res_cols], axis=0).dropna().unique().tolist()) if res_cols else []
    status_vals = sorted(df.get("status", pd.Series(dtype=str)).dropna().unique().tolist()) if "status" in df.columns else []

    date_candidates = []
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in c for k in ["data","venc","entrega","abertura","conclus","competencia","inicio","legal","tecnico","técnico"]):
            date_candidates.append(c)
    seen=set(); date_candidates=[x for x in date_candidates if not (x in seen or seen.add(x))]

    with st.expander("🎛️ Filtros", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            emp_sel = st.multiselect("Empresas", emp, default=emp if not defaults.get("emp") else defaults["emp"], key=f"emp_{who}")
        with c2:
            dep_sel = st.multiselect("Departamentos", dep, default=dep if not defaults.get("dep") else defaults["dep"], key=f"dep_{who}")
        with c3:
            res_sel = st.multiselect("Responsáveis", res, default=res if not defaults.get("res") else defaults["res"], key=f"res_{who}")
        with c4:
            stt_sel = st.multiselect("Status", status_vals, default=status_vals, key=f"stt_{who}")
        dcol = None
        if date_candidates:
            dcol = st.selectbox("Coluna de data para filtrar", options=["<sem filtro de data>"]+date_candidates, index=0, key=f"dcol_{who}")
            if dcol == "<sem filtro de data>": dcol = None
        di = dfim = None
        if dcol:
            from_d, to_d = st.columns(2)
            with from_d: di = st.date_input("Data inicial", value=None, key=f"di_{who}")
            with to_d:  dfim = st.date_input("Data final", value=None, key=f"df_{who}")

    mask = pd.Series(True, index=df.index)
    if emp: mask &= df["empresa"].isin(emp_sel)
    if dep: mask &= df["departamento"].isin(dep_sel)
    if res_cols and res_sel:
        mask &= df[res_cols].apply(lambda r: any([(x in res_sel) for x in r.values if pd.notna(x)]), axis=1)
    if status_vals: mask &= df["status"].isin(stt_sel)
    if dcol:
        col_dt = pd.to_datetime(df[dcol], errors="coerce")
        if di:   mask &= col_dt.dt.date >= di
        if dfim: mask &= col_dt.dt.date <= dfim

    return df[mask].copy()

# ===================== Session =====================
for key in ["dfe","dfs","dfo","dfp","dfr"]:
    if key not in st.session_state: st.session_state[key] = None

# ===================== Sidebar uploads =====================
with st.sidebar:
    st.header("📂 Upload por cliente")
    up_entregas = st.file_uploader("Gestão de Entregas (CSV)", type=["csv"])
    up_solic    = st.file_uploader("Solicitações (XLSX/CSV)", type=["xlsx","csv"])
    up_obrig    = st.file_uploader("Obrigações (XLSX/CSV)", type=["xlsx","csv"])
    up_proc     = st.file_uploader("Gestão de Processos (XLSX/CSV)", type=["xlsx","csv"])
    up_resp     = st.file_uploader("Responsáveis & Departamentos (XLS/XLSX/CSV)", type=["xls","xlsx","csv"])
    st.caption("Carregue, mapeie e analise.")

tabs = st.tabs(["🏠 Resumo", "🧾 Entregas", "📨 Solicitações", "📅 Obrigações", "⚙️ Processos", "📊 Comparativo Técnico vs Legal", "📝 Relatórios", "👤 Responsáveis"])

# ===================== ENTREGAS =====================
with tabs[1]:
    if up_entregas:
        raw = read_any_csv(up_entregas)
        raw = normalize_headers(raw)
        required = ["empresa","obrigacao","data_vencimento","status"]
        optional = ["cnpj","departamento","responsavel_prazo","responsavel_entrega","competencia","data_entrega","protocolo","prazo_tecnico","data_legal"]
        mapping = mapping_wizard(raw, "Entregas", required, optional, "ent")
        ent = apply_mapping(raw, mapping)
        ent = to_datetime_cols(ent, ["data_vencimento","data_entrega","competencia","prazo_tecnico","data_legal"])
        if "status" in ent.columns:
            ent["status"] = ent["status"].map(norm_status).fillna(ent["status"])
        today = pd.to_datetime(date.today())
        ent["atrasada_concluida"] = np.where(
            s_get(ent,"status").astype(str).str.lower().eq("concluída") & s_get(ent,"data_entrega").notna() & (s_get(ent,"data_entrega") > s_get(ent,"data_vencimento")),
            True, False
        )
        ent["atrasada_pendente"] = np.where(
            ~s_get(ent,"status").astype(str).str.lower().eq("concluída") & s_get(ent,"data_vencimento").notna() & (today > s_get(ent,"data_vencimento")),
            True, False
        )
        ent["pontual"] = np.where(
            s_get(ent,"status").astype(str).str.lower().eq("concluída") & s_get(ent,"data_entrega").notna() & (s_get(ent,"data_entrega") <= s_get(ent,"data_vencimento")),
            True, False
        )
        ent["dias_atraso"] = np.where(
            s_get(ent,"status").astype(str).str.lower().eq("concluída") & s_get(ent,"data_entrega").notna(),
            s_dt_days(s_get(ent,"data_entrega") - s_get(ent,"data_vencimento")).clip(lower=0),
            np.where(
                ~s_get(ent,"status").astype(str).str.lower().eq("concluída") & s_get(ent,"data_vencimento").notna(),
                s_dt_days(pd.to_datetime(today) - s_get(ent,"data_vencimento")).clip(lower=0),
                np.nan
            )
        )
        # --- Prazo técnico e Data legal ---
        ent["delta_tecnico_dias"] = np.where(
            s_get(ent,"data_entrega").notna() & s_get(ent,"prazo_tecnico").notna(),
            s_dt_days(s_get(ent,"data_entrega") - s_get(ent,"prazo_tecnico")),
            np.nan
        )
        ent["atraso_tecnico_dias"] = np.where(pd.notna(ent["delta_tecnico_dias"]), ent["delta_tecnico_dias"].clip(lower=0), np.nan)
        ent["delta_legal_dias"] = np.where(
            s_get(ent,"data_entrega").notna() & s_get(ent,"data_legal").notna(),
            s_dt_days(s_get(ent,"data_entrega") - s_get(ent,"data_legal")),
            np.nan
        )
        ent["atraso_legal_dias"] = np.where(pd.notna(ent["delta_legal_dias"]), ent["delta_legal_dias"].clip(lower=0), np.nan)

        dfe = filter_panel(ent, who="ent")
        st.session_state["dfe"] = dfe

        total = len(dfe); concl = int(s_get(dfe,"status").astype(str).str.lower().eq("concluída").sum()); pend = total - concl
        atrasos = int((s_get(dfe,"atrasada_concluida").fillna(False) | s_get(dfe,"atrasada_pendente").fillna(False)).sum())
        k1,k2,k3,k4,k5 = st.columns(5)
        k1.metric("Total", f"{total:,}".replace(",","."))
        k2.metric("Concluídas", f"{concl:,}".replace(",","."))
        k3.metric("Pendentes", f"{pend:,}".replace(",","."))
        k4.metric("Atrasadas (legal)", f"{atrasos:,}".replace(",","."))
        med_tecnico = float(np.nanmean(s_get(dfe, 'atraso_tecnico_dias'))) if 'atraso_tecnico_dias' in dfe.columns else float('nan')
        k5.metric("Atraso técnico médio (dias)", f"{med_tecnico:,.1f}".replace(",","."))

        st.markdown("#### ⚙️ Filtros e Rankings — Atraso Técnico")
        only_tec_late = st.checkbox("Mostrar apenas entregues **depois** do prazo técnico", value=True)
        dims = []
        if "departamento" in dfe.columns: dims.append("departamento")
        if "empresa" in dfe.columns: dims.append("empresa")
        if "responsavel_entrega" in dfe.columns: dims.append("responsavel_entrega")
        if not dims: dims = ["empresa"]
        dim = st.selectbox("Agrupar por", options=dims, index=0)
        metrica = st.selectbox("Métrica", options=["Quantidade de atrasos técnicos","Atraso técnico médio (dias)","Soma de atraso técnico (dias)"], index=0)

        df_tec = dfe.copy()
        if "prazo_tecnico" in df_tec.columns and "data_entrega" in df_tec.columns:
            df_tec = df_tec[df_tec["prazo_tecnico"].notna() & df_tec["data_entrega"].notna()]
        if only_tec_late and "atraso_tecnico_dias" in df_tec.columns:
            df_tec = df_tec[df_tec["atraso_tecnico_dias"].fillna(0) > 0]

        if dim in df_tec.columns and not df_tec.empty:
            if metrica == "Quantidade de atrasos técnicos":
                agg = df_tec.groupby(dim).agg(valor=("atraso_tecnico_dias", lambda s: (s.fillna(0) > 0).sum()))
            elif metrica == "Atraso técnico médio (dias)":
                agg = df_tec.groupby(dim).agg(valor=("atraso_tecnico_dias", "mean"))
            else:
                agg = df_tec.groupby(dim).agg(valor=("atraso_tecnico_dias", "sum"))
            agg = agg.reset_index().sort_values("valor", ascending=False)
            st.dataframe(agg)
            try:
                st.plotly_chart(px.bar(agg.head(20), x=dim, y="valor", title=f"Ranking — {metrica}"), use_container_width=True)
            except Exception: pass
            st.download_button("⬇️ Exportar ranking (CSV)", agg.to_csv(index=False).encode("utf-8"), "ranking_atraso_tecnico.csv", "text/csv")
        else:
            st.info("Sem dados suficientes para ranking de atraso técnico.")

        st.markdown("#### Detalhe (todas as linhas)")
        show_cols = [c for c in ["empresa","obrigacao","departamento","responsavel_entrega","competencia","data_vencimento","data_entrega","status","dias_atraso","prazo_tecnico","data_legal","delta_tecnico_dias","atraso_tecnico_dias","delta_legal_dias","atraso_legal_dias","protocolo"] if c in dfe.columns]
        st.dataframe(dfe[show_cols] if show_cols else dfe)
        st.caption(f"Linhas exibidas: {len(dfe):,}".replace(",","."))
        st.download_button("⬇️ Baixar CSV filtrado (Entregas)", dfe.to_csv(index=False).encode("utf-8"), "entregas_filtrado.csv", "text/csv")
    else:
        st.info("Envie **Gestão de Entregas** (CSV) para começar.")

# ===================== SOLICITAÇÕES =====================
with tabs[2]:
    if up_solic:
        raw = try_read_excel(up_solic) if up_solic.name.lower().endswith(".xlsx") else read_any_csv(up_solic)
        raw = normalize_headers(raw)
        required = ["id","assunto","empresa","status"]
        optional = ["prioridade","responsavel","abertura","prazo","ultima_atualizacao","conclusao"]
        mapping = mapping_wizard(raw, "Solicitações", required, optional, "sol")
        sol = apply_mapping(raw, mapping)
        sol = to_datetime_cols(sol, ["abertura","prazo","ultima_atualizacao","conclusao"])
        if "status" in sol.columns:
            sol["status"] = sol["status"].map(norm_status).fillna(sol["status"])
        today = pd.to_datetime(date.today())
        sol["tempo_ate_conclusao_dias"] = np.where(
            s_get(sol,"conclusao").notna() & s_get(sol,"abertura").notna(),
            s_dt_days(s_get(sol,"conclusao") - s_get(sol,"abertura")),
            np.nan
        )
        sol["aberta_ha_dias"] = np.where(
            s_get(sol,"conclusao").isna() & s_get(sol,"abertura").notna(),
            s_dt_days(pd.to_datetime(today) - s_get(sol,"abertura")),
            np.nan
        )
        dfs = filter_panel(sol, who="sol")
        st.session_state["dfs"] = dfs
        total = len(dfs); concl = int(s_get(dfs,"status").astype(str).str.lower().eq("concluída").sum()); abertas = total - concl
        k1,k2,k3 = st.columns(3)
        k1.metric("Total", f"{total:,}".replace(",","."))
        k2.metric("Abertas", f"{abertas:,}".replace(",","."))
        k3.metric("SLA médio (dias)", f"{float(np.nanmean(s_get(dfs,'tempo_ate_conclusao_dias'))):,.1f}".replace(",","."))
        st.dataframe(dfs); st.caption(f"Linhas exibidas: {len(dfs):,}".replace(",",".")); st.download_button("⬇️ Baixar CSV filtrado (Solicitações)", dfs.to_csv(index=False).encode("utf-8"), "solicitacoes_filtrado.csv", "text/csv")
    else:
        st.info("Envie **Solicitações**.")

# ===================== OBRIGAÇÕES =====================
with tabs[3]:
    if up_obrig:
        raw = try_read_excel(up_obrig) if up_obrig.name.lower().endswith(".xlsx") else read_any_csv(up_obrig)
        raw = normalize_headers(raw)
        required = ["obrigacao","departamento"]
        optional = ["mini","responsavel","periodicidade","prazo_mensal","alerta_dias"]
        mapping = mapping_wizard(raw, "Obrigações", required, optional, "obr")
        obr = apply_mapping(raw, mapping)
        dfo = filter_panel(obr, who="obr")
        st.session_state["dfo"] = dfo
        if {"departamento","obrigacao"}.issubset(dfo.columns):
            try:
                st.plotly_chart(px.treemap(dfo, path=["departamento","obrigacao"], title="Impacto por Departamento e Obrigação"), use_container_width=True)
            except Exception:
                st.dataframe(dfo.groupby(["departamento","obrigacao"]).size().reset_index(name="qtd"))
        st.dataframe(dfo); st.caption(f"Linhas exibidas: {len(dfo):,}".replace(",",".")); st.download_button("⬇️ Baixar CSV filtrado (Obrigações)", dfo.to_csv(index=False).encode("utf-8"), "obrigacoes_filtrado.csv", "text/csv")
    else:
        st.info("Envie **Obrigações**.")

# ===================== PROCESSOS =====================
with tabs[4]:
    if up_proc:
        raw = try_read_excel(up_proc) if up_proc.name.lower().endswith(".xlsx") else read_any_csv(up_proc)
        raw = normalize_headers(raw)
        required = ["id_processo","processo","empresa","status"]
        optional = ["departamento","responsavel","inicio","conclusao","progresso"]
        mapping = mapping_wizard(raw, "Processos", required, optional, "pro")
        pro = apply_mapping(raw, mapping)
        pro = to_datetime_cols(pro, ["inicio","conclusao"])
        if "status" in pro.columns:
            pro["status"] = pro["status"].map(norm_status).fillna(pro["status"])
        dfp = filter_panel(pro, who="pro")
        st.session_state["dfp"] = dfp
        total = len(dfp); concl = int(s_get(dfp,"status").astype(str).str.lower().eq("concluída").sum()); em_and = total - concl
        k1,k2,k3 = st.columns(3)
        k1.metric("Processos", f"{total:,}".replace(",","."))
        k2.metric("Concluídos", f"{concl:,}".replace(",","."))
        if {"inicio","conclusao"}.issubset(dfp.columns):
            dur = s_dt_days(s_get(dfp,"conclusao") - s_get(dfp,"inicio"))
            k3.metric("Duração média (dias)", f"{float(np.nanmean(dur)):,.1f}".replace(",","."))
        st.dataframe(dfp); st.caption(f"Linhas exibidas: {len(dfp):,}".replace(",",".")); st.download_button("⬇️ Baixar CSV filtrado (Processos)", dfp.to_csv(index=False).encode("utf-8"), "processos_filtrado.csv", "text/csv")
    else:
        st.info("Envie **Gestão de Processos**.")

# ===================== COMPARATIVO TÉCNICO vs LEGAL =====================
with tabs[5]:
    st.subheader("📊 Comparativo Técnico vs Legal")
    st.caption("Diferença entre **prazo técnico** e **data legal** versus **data de conclusão**; conformidade e heatmaps.")
    dfe = st.session_state.get("dfe")
    if isinstance(dfe, pd.DataFrame) and not dfe.empty:
        dfc = dfe.copy()
        has_tecnico = ("prazo_tecnico" in dfc.columns) and ("data_entrega" in dfc.columns)
        has_legal = ("data_legal" in dfc.columns) and ("data_entrega" in dfc.columns)
        # mês seguro
        mes_series = None
        for base_col in ["competencia","data_vencimento","data_entrega"]:
            if base_col in dfc.columns:
                try:
                    mes_series = pd.to_datetime(dfc[base_col], errors="coerce").dt.to_period("M").astype(str); break
                except Exception: pass
        if mes_series is None:
            mes_series = pd.Series([pd.Timestamp.today().to_period("M").strftime("%Y-%m")]*len(dfc), index=dfc.index)
        dfc["mes"] = mes_series
        # flags
        dfc["late_tecnico"] = np.where(has_tecnico, s_get(dfc,"atraso_tecnico_dias").fillna(0) > 0, pd.NA)
        dfc["late_legal"]   = np.where(has_legal,   s_get(dfc,"atraso_legal_dias").fillna(0) > 0, pd.NA)
        # filtros locais
        with st.expander("🎛️ Filtros (Comparativo)", expanded=True):
            emp = sorted(s_get(dfc,"empresa").dropna().unique().tolist()) if "empresa" in dfc.columns else []
            dep = sorted(s_get(dfc,"departamento").dropna().unique().tolist()) if "departamento" in dfc.columns else []
            c1, c2 = st.columns(2)
            with c1: emp_sel = st.multiselect("Empresas", emp, default=emp)
            with c2: dep_sel = st.multiselect("Departamentos", dep, default=dep)
        mask = pd.Series(True, index=dfc.index)
        if "empresa" in dfc.columns and emp_sel: mask &= dfc["empresa"].isin(emp_sel)
        if "departamento" in dfc.columns and dep_sel: mask &= dfc["departamento"].isin(dep_sel)
        dfc = dfc[mask].copy()
        # conformidade
        st.markdown("### ✅ Conformidade por Departamento")
        if "departamento" in dfc.columns:
            cc1, cc2 = st.columns(2)
            with cc1:
                if has_tecnico:
                    base_t = dfc[dfc["late_tecnico"].notna()]
                    conf_t = base_t.groupby("departamento")["late_tecnico"].apply(lambda s: (1 - s.mean())*100 if len(s)>0 else np.nan).reset_index(name="conformidade_tecnica_%")
                    st.dataframe(conf_t.sort_values("conformidade_tecnica_%", ascending=False))
                else:
                    st.info("Mapeie **prazo_tecnico** + **data_entrega** em Entregas.")
            with cc2:
                if has_legal:
                    base_l = dfc[dfc["late_legal"].notna()]
                    conf_l = base_l.groupby("departamento")["late_legal"].apply(lambda s: (1 - s.mean())*100 if len(s)>0 else np.nan).reset_index(name="conformidade_legal_%")
                    st.dataframe(conf_l.sort_values("conformidade_legal_%", ascending=False))
                else:
                    st.info("Mapeie **data_legal** + **data_entrega** em Entregas.")
        # heatmaps
        st.markdown("---"); st.markdown("### 🔥 Heatmaps de Atrasos (%%) — Empresa × Mês")
        if "empresa" in dfc.columns and "mes" in dfc.columns:
            if has_tecnico:
                base_t = dfc[dfc["late_tecnico"].notna()]
                if not base_t.empty:
                    pt = base_t.pivot_table(index="empresa", columns="mes", values="late_tecnico", aggfunc="mean") * 100
                    try: st.plotly_chart(px.imshow(pt, aspect="auto", title="% Atraso Técnico — Empresa x Mês", labels=dict(color="%")), use_container_width=True)
                    except Exception: st.dataframe(pt.round(1))
            else: st.info("Mapeie **prazo_tecnico** + **data_entrega** para heatmap técnico.")
            if has_legal:
                base_l = dfc[dfc["late_legal"].notna()]
                if not base_l.empty:
                    pl = base_l.pivot_table(index="empresa", columns="mes", values="late_legal", aggfunc="mean") * 100
                    try: st.plotly_chart(px.imshow(pl, aspect="auto", title="% Atraso Legal — Empresa x Mês", labels=dict(color="%")), use_container_width=True)
                    except Exception: st.dataframe(pl.round(1))
            else: st.info("Mapeie **data_legal** + **data_entrega** para heatmap legal.")
        else:
            st.info("Para heatmaps, é necessário ter **empresa** e uma coluna de data/competência.")
        # exports
        st.markdown("---"); st.markdown("### 📑 Exports (comparativo)")
        if has_tecnico and "departamento" in dfc.columns:
            sum_t = dfc[dfc["late_tecnico"].notna()].groupby("departamento").agg(
                atrasos_tecnicos=("late_tecnico", "sum"),
                total_comparavel=("late_tecnico", "size"),
                conformidade_tecnica_pct=("late_tecnico", lambda s: (1 - s.mean())*100)
            ).reset_index().sort_values("conformidade_tecnica_pct", ascending=False)
            st.download_button("⬇️ CSV — Resumo Técnico por Departamento", sum_t.to_csv(index=False).encode("utf-8"), "resumo_tecnico_departamento.csv", "text/csv")
        if has_legal and "departamento" in dfc.columns:
            sum_l = dfc[dfc["late_legal"].notna()].groupby("departamento").agg(
                atrasos_legais=("late_legal", "sum"),
                total_comparavel=("late_legal", "size"),
                conformidade_legal_pct=("late_legal", lambda s: (1 - s.mean())*100)
            ).reset_index().sort_values("conformidade_legal_pct", ascending=False)
            st.download_button("⬇️ CSV — Resumo Legal por Departamento", sum_l.to_csv(index=False).encode("utf-8"), "resumo_legal_departamento.csv", "text/csv")
    else:
        st.info("Carregue e mapeie dados em **🧾 Entregas** para ver o comparativo.")

# ===================== RELATÓRIOS =====================
with tabs[6]:
    st.subheader("📝 Relatórios — Ajuste & Geração de Resumo Analítico")
    c1, c2, c3 = st.columns(3)
    with c1:
        dias_em_risco = st.number_input("Entregas: 'em risco' quando faltam ≤ (dias)", min_value=0, max_value=10, value=2)
        considerar_ultimos = st.number_input("Ranking de atrasos: últimos (dias)", min_value=7, max_value=120, value=30)
    with c2:
        sla_alerta = st.number_input("Solicitações: críticas a partir de (dias abertos)", min_value=1, max_value=60, value=14)
        sem_update_alerta = st.number_input("Solicitações: prioridade ALTA sem atualização ≥ (dias)", min_value=1, max_value=30, value=3)
    with c3:
        proc_dias_alerta = st.number_input("Processos: em andamento crítico ≥ (dias)", min_value=7, max_value=180, value=30)

    st.markdown("---")
    gerar = st.button("Gerar relatório agora")
    if gerar:
        hoje = pd.to_datetime(date.today())
        linhas = []

        # Entregas
        if isinstance(st.session_state.get("dfe"), pd.DataFrame):
            dfe = st.session_state["dfe"].copy()
            if "data_vencimento" in dfe.columns:
                dfe["em_risco"] = np.where(
                    (s_get(dfe,"status").astype(str).str.lower()!="concluída") & s_get(dfe,"data_vencimento").notna() & ((s_get(dfe,"data_vencimento") - hoje).dt.days.between(0, dias_em_risco)),
                    True, False
                )
                dfe["atrasada_pendente"] = np.where(
                    (s_get(dfe,"status").astype(str).str.lower()!="concluída") & s_get(dfe,"data_vencimento").notna() & (hoje > s_get(dfe,"data_vencimento")),
                    True, False
                )
                dfe["atrasada_concluida"] = np.where(
                    (s_get(dfe,"status").astype(str).str.lower()=="concluída") & s_get(dfe,"data_entrega").notna() & (s_get(dfe,"data_entrega") > s_get(dfe,"data_vencimento")),
                    True, False
                )
                total = len(dfe)
                concluidas = int((s_get(dfe,"status").astype(str).str.lower()=="concluída").sum())
                pendentes = total - concluidas
                atrasadas = int((dfe["atrasada_concluida"] | dfe["atrasada_pendente"]).sum())
                em_risco_qtd = int(dfe["em_risco"].sum())
                cutoff = hoje - pd.Timedelta(days=considerar_ultimos)
                recent = dfe[s_get(dfe,"data_vencimento") >= cutoff]
                rank_emp = pd.DataFrame()
                if not recent.empty:
                    late_recent = recent[(recent["atrasada_concluida"]) | (recent["atrasada_pendente"])]
                    if not late_recent.empty and "empresa" in late_recent.columns:
                        rank_emp = late_recent.groupby("empresa").size().reset_index(name=f"atrasos_{considerar_ultimos}d").sort_values(f"atrasos_{considerar_ultimos}d", ascending=False).head(5)
                linhas += [
                    f"### Entregas",
                    f"- Total: **{total}** | Concluídas: **{concluidas}** | Pendentes: **{pendentes}**",
                    f"- Atrasadas (inclui pendentes vencidas): **{atrasadas}**",
                    f"- Em risco (vencem em ≤ {dias_em_risco} dias): **{em_risco_qtd}**",
                ]
                if not rank_emp.empty:
                    top_lines = "\n".join([f"  - {r['empresa']}: {int(r[f'atrasos_{considerar_ultimos}d'])} atrasos" for _,r in rank_emp.iterrows()])
                    linhas += [f"- TOP atrasos (últimos {considerar_ultimos} dias):\n{top_lines}"]

        # Solicitações
        if isinstance(st.session_state.get("dfs"), pd.DataFrame):
            dfs = st.session_state["dfs"].copy()
            hoje = pd.to_datetime(date.today())
            if "aberta_ha_dias" not in dfs.columns and "abertura" in dfs.columns:
                dfs["aberta_ha_dias"] = np.where(s_get(dfs,"conclusao").isna() & s_get(dfs,"abertura").notna(), s_dt_days(hoje - s_get(dfs,"abertura")), np.nan)
            long_open = dfs[(s_get(dfs,"conclusao").isna()) & (s_get(dfs,"aberta_ha_dias").fillna(0) >= sla_alerta)] if "aberta_ha_dias" in dfs.columns else pd.DataFrame()
            sem_upd = pd.DataFrame()
            if {"prioridade","ultima_atualizacao","conclusao"}.issubset(dfs.columns):
                sem_upd = dfs[(dfs["conclusao"].isna()) & (dfs["prioridade"].str.contains("alta", case=False, na=False)) & ((hoje - dfs["ultima_atualizacao"]).dt.days >= sem_update_alerta)]
            total_s = len(dfs); abertas = int(s_get(dfs,"conclusao").isna().sum() if "conclusao" in dfs.columns else total_s)
            linhas += [
                f"### Solicitações",
                f"- Total: **{total_s}** | Abertas: **{abertas}**",
                f"- Críticas: Abertas ≥ {sla_alerta} dias: **{len(long_open)}** | Alta sem atualização ≥ {sem_update_alerta} dias: **{len(sem_upd)}**",
            ]

        # Processos
        if isinstance(st.session_state.get("dfp"), pd.DataFrame):
            dfp = st.session_state["dfp"].copy()
            hoje = pd.to_datetime(date.today())
            crit = pd.DataFrame()
            if {"inicio","conclusao","status"}.issubset(dfp.columns):
                dur = np.where(dfp["conclusao"].notna(), (dfp["conclusao"] - dfp["inicio"]).dt.days, (hoje - dfp["inicio"]).dt.days)
                dfp["duracao_dias"] = dur
                crit = dfp[(dfp.get("status","").str.lower()!="concluída") & (dfp["duracao_dias"] >= proc_dias_alerta)]
            linhas += [
                f"### Processos",
                f"- Total: **{len(dfp)}**",
                f"- Em andamento ≥ {proc_dias_alerta} dias: **{len(crit)}**",
            ]

        if not linhas:
            st.warning("Nenhum dataset carregado para gerar relatório.")
        else:
            md = "# Resumo Analítico\n\n" + "\n".join(linhas)
            st.markdown(md)
            st.download_button("⬇️ Baixar relatório (.md)", md.encode("utf-8"), "relatorio_resumo.md", "text/markdown")

# ===================== RESPONSÁVEIS =====================
with tabs[7]:
    if up_resp:
        raw = try_read_excel(up_resp) if up_resp.name.lower().endswith((".xls",".xlsx")) else read_any_csv(up_resp)
        raw = normalize_headers(raw)
        required = ["responsavel","departamento"]
        optional = ["email","cargo"]
        mapping = mapping_wizard(raw, "Responsáveis & Departamentos", required, optional, "resp")
        resp = apply_mapping(raw, mapping)
        dfr = filter_panel(resp, who="resp")
        st.session_state["dfr"] = dfr
        st.dataframe(dfr); st.caption(f"Linhas exibidas: {len(dfr):,}".replace(",",".")); st.download_button("⬇️ Baixar CSV filtrado (Responsáveis)", dfr.to_csv(index=False).encode("utf-8"), "responsaveis_filtrado.csv", "text/csv")
    else:
        st.info("Envie **Responsáveis & Departamentos**.")

# ===================== RESUMO (home) =====================
with tabs[0]:
    st.subheader("🔎 KPIs Gerais")
    c1,c2,c3 = st.columns(3)
    if isinstance(st.session_state.get("dfe"), pd.DataFrame):
        dfe = st.session_state["dfe"]; total = len(dfe)
        atrasos = int((s_get(dfe,'atrasada_concluida').fillna(False) | s_get(dfe,'atrasada_pendente').fillna(False)).sum())
        c1.metric("Entregas (total | atrasadas legais)", f"{total:,}".replace(",","."), f"{atrasos:,}".replace(",","."))
    else: c1.metric("Entregas (total | atrasadas legais)", "—")
    if isinstance(st.session_state.get("dfs"), pd.DataFrame):
        dfs = st.session_state["dfs"]; total = len(dfs); abertas = int(s_get(dfs,"conclusao").isna().sum() if "conclusao" in dfs.columns else total)
        c2.metric("Solicitações (total | abertas)", f"{total:,}".replace(",","."), f"{abertas:,}".replace(",","."))
    else: c2.metric("Solicitações (total | abertas)", "—")
    if isinstance(st.session_state.get("dfp"), pd.DataFrame):
        dfp = st.session_state["dfp"]; total = len(dfp); c3.metric("Processos (total)", f"{total:,}".replace(",","."))
    else: c3.metric("Processos (total)", "—")
