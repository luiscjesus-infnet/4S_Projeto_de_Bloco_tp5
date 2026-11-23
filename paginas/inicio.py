import streamlit as st

from src.comum import fmt, obter_saneamento
from src.dados import ranking

st.title("💧 Painel ODS 6 - Água e esgoto por UF")
st.markdown(
    """
**Pergunta que o painel responde:** *em quais estados o investimento em água e esgoto
deveria chegar primeiro, considerando a cobertura atual, a evolução desde 2010 e o impacto na saúde?*

O painel junta dados de cobertura de água e esgoto, a evolução desde 2010 e o reflexo
na saúde (internações por doenças de veiculação hídrica), além de notícias recentes sobre
o tema. Ele foi pensado para o analista de uma ONG ou secretaria que precisa levar ao
gestor uma lista curta e justificada de prioridades.
"""
)

linhas = obter_saneamento()
if not linhas:
    st.error("Os dados processados não foram encontrados em data/processed. Rode as coletas (veja o README).")
    st.stop()

ano = linhas[0]["ano"]
populacao_total = sum(l["populacao"] or 0 for l in linhas)
sem_agua_total = sum(l["pessoas_sem_agua"] or 0 for l in linhas)

c1, c2, c3 = st.columns(3)
c1.metric("UFs com dados", len(linhas))
c2.metric(f"Pessoas sem acesso à água ({ano})", fmt(sem_agua_total / 1_000_000, 1, " mi"))
c3.metric("Parcela da população sem água", fmt(sem_agua_total / populacao_total * 100, 1, "%"))

st.subheader("As 5 UFs em pior situação")
col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**Sem acesso à água (%)**")
    for i, l in enumerate(ranking(linhas, "sem_agua_pct", 5), start=1):
        st.write(f"{i}. {l['uf_nome']} ({l['sigla']}) - {fmt(l['sem_agua_pct'])}%")
with col_b:
    st.markdown("**Sem coleta de esgoto (%)**")
    for i, l in enumerate(ranking(linhas, "sem_esgoto_pct", 5), start=1):
        st.write(f"{i}. {l['uf_nome']} ({l['sigla']}) - {fmt(l['sem_esgoto_pct'])}%")

st.subheader("Para onde ir")
st.page_link("paginas/panorama.py", label="Comparar todas as UFs e montar um ranking", icon="📊")
st.page_link("paginas/evolucao.py", label="Ver se a situação melhorou desde 2010", icon="📈")
st.page_link("paginas/noticias.py", label="Ler o que a imprensa está falando", icon="📰")
st.page_link("paginas/api_projeto.py", label="Consultar os dados pela API e enviar observações", icon="🔌")

with st.expander("Iniciativas e referências"):
    st.markdown(
        """
- [Painel Saneamento Brasil - Instituto Trata Brasil](https://www.painelsaneamento.org.br)
- [ODS 6 - Água potável e saneamento (ONU Brasil)](https://brasil.un.org/pt-br/sdgs/6)
- [API de localidades e agregados do IBGE](https://servicodados.ibge.gov.br/api/docs)
- [Agência Brasil - Meio Ambiente](https://agenciabrasil.ebc.com.br/meio-ambiente)
"""
    )
