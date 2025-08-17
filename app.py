import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ==============================
# Funções utilitárias para leitura
# ==============================

def read_any_csv(uploaded_file) -> pd.DataFrame:
    """
    Lê CSV tentando múltiplas codificações e separadores.
    Tenta: utf-8, utf-8-sig, latin1, cp1252, iso-8859-1, utf-16(le/be).
    Tenta também separadores: auto, ; , , | e TAB.
    """
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
    # Último recurso: abre ignorando linhas ruins
    try:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    except Exception as e2:
        st.error(f"Não consegui abrir o CSV. Último erro: {last_err}")
        raise

def try_read_excel(uploaded_file) -> pd.DataFrame:
    """
    Lê Excel com detecção de formato e fallbacks:
    - .xlsx / .xlsm -> engine=openpyxl
    - .xlsb         -> engine=pyxlsb
    - .xls (antigo) -> engine=xlrd (fallback para openpyxl)
    - Se tudo falhar: tenta CSV via read_any_csv (multi-encoding)
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
        # alguns .xls são na prática .xlsx renomeado
        df = _try(pd.read_excel, uploaded_file, engine="openpyxl", dtype=str)
        if df is not None: return df

    # Heurística caso a extensão esteja errada
    for eng in ("openpyxl", "pyxlsb", "xlrd"):
        df = _try(pd.read_excel, uploaded_file, engine=eng, dtype=str)
        if df is not None: return df

    # Último recurso: talvez seja CSV renomeado
    uploaded_file.seek(0)
    return read_any_csv(uploaded_file)

# ==============================
# App
# ==============================

st.set_page_config(page_title="Diagnóstico Acessórias", layout="wide")

st.title("📊 Diagnóstico Acessórias")

st.sidebar.header("Upload de arquivos")
up_resp = st.sidebar.file_uploader("Upload de Responsáveis (.xls/.xlsx/.csv)", type=["xls", "xlsx", "xlsm", "xlsb", "csv"])
up_solic = st.sidebar.file_uploader("Upload de Solicitações (.xls/.xlsx/.csv)", type=["xls", "xlsx", "xlsm", "xlsb", "csv"])
up_obrig = st.sidebar.file_uploader("Upload de Obrigações (.xls/.xlsx/.csv)", type=["xls", "xlsx", "xlsm", "xlsb", "csv"])
up_proc = st.sidebar.file_uploader("Upload de Processos (.xls/.xlsx/.csv)", type=["xls", "xlsx", "xlsm", "xlsb", "csv"])

dfs = {}

if up_resp:
    name = up_resp.name.lower()
    dfs["responsaveis"] = try_read_excel(up_resp) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_resp)

if up_solic:
    name = up_solic.name.lower()
    dfs["solicitacoes"] = try_read_excel(up_solic) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_solic)

if up_obrig:
    name = up_obrig.name.lower()
    dfs["obrigacoes"] = try_read_excel(up_obrig) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_obrig)

if up_proc:
    name = up_proc.name.lower()
    dfs["processos"] = try_read_excel(up_proc) if name.endswith(('.xls', '.xlsx', '.xlsm', '.xlsb')) else read_any_csv(up_proc)

# Exemplo: mostrar shapes carregados
for k, df in dfs.items():
    st.write(f"### {k.capitalize()}")
    st.write(df.shape)
    st.dataframe(df.head(50))
