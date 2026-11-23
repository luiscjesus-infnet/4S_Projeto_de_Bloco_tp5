import streamlit as st

from src.comum import fmt, obter_serie
from src.dados import INDICADORES_SERIE, SIGLAS

st.title("📈 Evolução 2010-2024")
st.caption("Série histórica coletada com Selenium na página dinâmica 'Por Indicador' do Painel Saneamento Brasil.")

serie = obter_serie()
if not serie:
    st.error("A série histórica ainda não foi coletada. Rode: python -m src.coleta_dinamica")
    st.stop()

c1, c2 = st.columns([1, 2])
c1.selectbox("Indicador", list(INDICADORES_SERIE), format_func=INDICADORES_SERIE.get, key="indicador_serie")
# a lista de UFs comparadas fica no session_state e continua lá quando o usuário troca de página
c2.multiselect("UFs para comparar (até 6)", SIGLAS, max_selections=6, key="ufs_comparadas")

indicador = st.session_state["indicador_serie"]
ufs = st.session_state["ufs_comparadas"]

if not ufs:
    st.info("Escolha pelo menos uma UF para ver a evolução.")
    st.stop()

pontos = [p for p in serie if p["indicador"] == indicador and p["sigla"] in ufs and p["valor"] is not None]
grafico = [{"ano": str(p["ano"]), "UF": p["sigla"], "valor": p["valor"]} for p in pontos]
st.line_chart(grafico, x="ano", y="valor", color="UF", height=400)

st.subheader("O que mudou de 2010 para 2024")
colunas = st.columns(len(ufs))
for coluna, sigla in zip(colunas, ufs):
    da_uf = {p["ano"]: p["valor"] for p in pontos if p["sigla"] == sigla}
    inicio, fim = da_uf.get(2010), da_uf.get(2024)
    if inicio is None or fim is None:
        coluna.metric(sigla, "sem dado")
        continue
    # para os três indicadores, cair é bom; por isso uso delta_color="inverse"
    coluna.metric(sigla, fmt(fim), delta=fmt(fim - inicio), delta_color="inverse")

st.caption(
    "Os três indicadores são do tipo 'quanto menor, melhor'. Seta verde para baixo = melhora. "
    "Saltos muito grandes de um ano para o outro (Amapá e Piauí em 2024, por exemplo) podem refletir "
    "mudança na base de origem dos dados e não só obra nova; por isso olho a tendência, não um ano isolado."
)
