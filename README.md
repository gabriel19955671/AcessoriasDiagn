
# Acessórias — Dashboard Único (Streamlit)

Este pacote reúne tudo em **um único app** (`app.py`) e dispensa PDF.

## Como rodar
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Fluxo de uso
1. Vá carregando cada planilha na **sidebar**.
2. Faça o **mapeamento** com o Wizard (obrigatórios/opcionais).
3. Aplique os **filtros** (empresa, departamento, responsável, status e **qual coluna de data** usar).
4. Analise:
   - Entregas: KPIs + **prazo técnico vs entrega**, **data legal**, rankings e download CSV.
   - Comparativo: **conformidade** por departamento e **heatmaps** Empresa × Mês.
   - Relatórios: resumo analítico com parâmetros (em Markdown).

## Dicas
- Se sua coluna de data não for reconhecida automaticamente, escolha ela no seletor “**Coluna de data para filtrar**”.
- Para ver o comparativo, mapeie em *Entregas* as colunas `data_entrega` + `prazo_tecnico` e/ou `data_legal`.
