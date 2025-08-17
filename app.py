
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Dashboard de Diagnóstico", layout="wide")

st.title("📊 Dashboard de Diagnóstico")

# Upload
uploaded_file = st.file_uploader("Carregar base de dados (Excel ou CSV)", type=["xlsx", "xls", "csv"])

def read_any_file(file):
    if file.name.endswith(".csv"):
        try:
            return pd.read_csv(file, sep=";", encoding="utf-8", dtype=str)
        except:
            return pd.read_csv(file, sep=";", encoding="latin1", dtype=str)
    else:
        return pd.read_excel(file, engine="openpyxl", dtype=str)

if uploaded_file:
    df = read_any_file(uploaded_file)
    st.subheader("Prévia dos dados")
    st.dataframe(df.head(50))

    # Conversão de datas
    for col in df.columns:
        if "data" in col.lower() or "prazo" in col.lower():
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Ranking - Departamentos mais atrasados
    if "departamento" in df.columns and "prazo_tecnico" in df.columns and "data_conclusao" in df.columns:
        df["atraso"] = (df["data_conclusao"] - df["prazo_tecnico"]).dt.days
        atraso_dep = df.groupby("departamento")["atraso"].mean().reset_index()
        atraso_dep = atraso_dep.sort_values(by="atraso", ascending=False)
        fig = px.bar(atraso_dep, x="departamento", y="atraso", title="Média de Atrasos por Departamento")
        st.plotly_chart(fig, use_container_width=True)

    # Ranking - Clientes mais solicitantes
    if "cliente" in df.columns:
        solicit = df["cliente"].value_counts().reset_index()
        solicit.columns = ["cliente", "qtd"]
        fig2 = px.bar(solicit.head(10), x="cliente", y="qtd", title="Top 10 Clientes com Mais Solicitações")
        st.plotly_chart(fig2, use_container_width=True)

    # Ranking - Colaboradores que mais entregam
    if "colaborador" in df.columns:
        colab = df["colaborador"].value_counts().reset_index()
        colab.columns = ["colaborador", "qtd"]
        fig3 = px.bar(colab.head(10), x="colaborador", y="qtd", title="Top 10 Colaboradores por Entregas")
        st.plotly_chart(fig3, use_container_width=True)

    # Ranking - Obrigações antecipadas
    if "prazo_tecnico" in df.columns and "data_conclusao" in df.columns:
        df["adiantamento"] = (df["prazo_tecnico"] - df["data_conclusao"]).dt.days
        antecipadas = df[df["adiantamento"] > 0]
        if "cliente" in antecipadas.columns:
            antecip_clientes = antecipadas.groupby("cliente").size().reset_index(name="qtd")
            fig4 = px.bar(antecip_clientes.head(10), x="cliente", y="qtd", title="Top 10 Clientes com Mais Entregas Antecipadas")
            st.plotly_chart(fig4, use_container_width=True)
