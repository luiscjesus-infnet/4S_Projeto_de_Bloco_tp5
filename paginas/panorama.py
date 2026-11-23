import streamlit as st

from src.comum import fmt, obter_saneamento, para_csv
from src.dados import INDICADORES, PIOR_QUANDO_MAIOR, REGIOES, ranking

st.title("📊 Panorama por UF")
st.caption("Indicadores do ano mais recente do Painel Saneamento Brasil, cruzados com a população do IBGE.")

linhas = obter_saneamento()

with st.sidebar.form("filtros_panorama"):
    st.markdown("**Filtros do panorama**")
    st.multiselect("Regiões", REGIOES, key="regioes")
    st.selectbox("Indicador", list(INDICADORES), format_func=INDICADORES.get, key="indicador_panorama")
    quantidade = st.slider("Quantas UFs no gráfico", 5, 27, 10)
    st.form_submit_button("Aplicar filtros")

indicador = st.session_state["indicador_panorama"]
filtradas = [l for l in linhas if l["regiao"] in st.session_state["regioes"] and l.get(indicador) is not None]

if not filtradas:
    st.warning("Nenhuma UF atende aos filtros. Selecione pelo menos uma região.")
    st.stop()

ordenadas = ranking(filtradas, indicador, limite=len(filtradas))
sentido = "pior → melhor" if indicador in PIOR_QUANDO_MAIOR else "maior → menor"

c1, c2, c3 = st.columns(3)
c1.metric("UFs exibidas", len(filtradas))
c2.metric("Pior posição", f"{ordenadas[0]['sigla']} - {fmt(ordenadas[0][indicador])}")
c3.metric("Média simples", fmt(sum(l[indicador] for l in filtradas) / len(filtradas)))

st.subheader(f"{INDICADORES[indicador]} ({sentido})")
st.bar_chart(
    [{"UF": l["sigla"], "valor": l[indicador]} for l in ordenadas[:quantidade]],
    x="UF", y="valor", height=380, sort=False,
)

st.subheader("Tabela das UFs filtradas")
colunas = ["sigla", "uf_nome", "regiao", "populacao", "sem_agua_pct", "sem_esgoto_pct",
           "esgoto_tratado_pct", "internacoes_10mil", "pessoas_sem_agua"]
tabela = [{c: l[c] for c in colunas} for l in ordenadas]
st.dataframe(tabela, hide_index=True, width="stretch")

st.download_button("📥 Baixar esta tabela (CSV)", para_csv(tabela), file_name="panorama_filtrado.csv", mime="text/csv")
