import streamlit as st

from src import dados
from src.comum import fmt, obter_base_fatos, obter_noticias, obter_saneamento

st.title("💧 Painel ODS 6 - Água e esgoto por UF")
st.markdown(
    """
**Pergunta que o painel responde:** *em quais estados o investimento em água e esgoto
deveria chegar primeiro, considerando a cobertura atual, a evolução desde 2010 e o impacto na saúde?*

Feito para o analista de uma ONG ou secretaria que precisa levar ao gestor uma lista curta e
justificada de prioridades, alinhada ao **ODS 6** (água potável e saneamento) e à meta do
**Marco Legal do Saneamento** (99% com água e 90% com esgoto até 2033).
"""
)

linhas = obter_saneamento()
if not linhas:
    st.error("Os dados processados não foram encontrados em data/processed. Rode as coletas (veja o README).")
    st.stop()

base = obter_base_fatos()
b = base.brasil
ano = linhas[0]["ano"]

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Pessoas sem acesso à água ({ano})", fmt(b["pessoas_sem_agua"] / 1_000_000, 1, " mi"))
c2.metric("Média das UFs sem coleta de esgoto", fmt(b["media_sem_esgoto"], 1, "%"),
          f"{fmt(b['media_sem_esgoto'] - b['media_sem_esgoto_2010'], 1)} p.p. desde 2010", delta_color="inverse")
c3.metric("UFs que chegam à meta de água até 2033", f"{b['chegam_meta_agua']} de 27")
c4.metric("UFs que chegam à meta de esgoto até 2033", f"{b['chegam_meta_esgoto']} de 27")

# ---------------------------------------------------------------- resposta curta
st.subheader("A resposta curta")
colunas = st.columns(3)
for coluna, l in zip(colunas, base.prioridade[:3]):
    with coluna.container(border=True):
        st.markdown(f"**{l['posicao']}º {l['uf_nome']}** · índice {fmt(l['indice'])}")
        for motivo in base.motivos(l["sigla"])[:3]:
            st.caption(f"• {motivo}")
c_a, c_b = st.columns(2)
c_a.page_link("paginas/prioridades.py", label="Ver o ranking completo e mudar os pesos", icon="🎯")
c_b.page_link("paginas/assistente.py", label="Perguntar ao assistente (ele lembra da conversa)", icon="💬")

# ---------------------------------------------------------------- ciclo de ciência de dados
st.subheader("Do dado à decisão: as etapas do projeto")
fontes = {f["arquivo"]: f for f in dados.info_fontes()}
noticias = obter_noticias()
analisadas = dados.ler_csv(dados.PROCESSADOS / "noticias_ia.csv")
serie = fontes.get("serie_saneamento_uf.csv", {})
etapas = [
    ("1. Coleta", f"{fontes.get('saneamento_uf.csv', {}).get('linhas', 0)} UFs (BeautifulSoup) · "
                  f"{serie.get('linhas', 0)} valores de 2010-2024 (Selenium) · população (API do IBGE) · "
                  f"{len(noticias)} notícias (BeautifulSoup)"),
    ("2. Processamento", "números no formato brasileiro convertidos, nomes de UF casados sem acento, "
                         "pessoas sem água e internações por 10 mil calculadas, saltos suspeitos marcados"),
    ("3. Análise", "tendência 2010-2024, ano projetado para a meta de 2033 e índice de prioridade "
                   "(cobertura, ritmo e saúde), tudo em Python"),
    ("4. IA", f"assistente com memória da conversa e {len(analisadas)} notícias com tema, sentimento e "
              "resumo feitos por um modelo de linguagem que roda nesta máquina"),
    ("5. Apresentação", "este painel (10 páginas) e uma API com 13 rotas para outros sistemas"),
]
colunas = st.columns(5)
for coluna, (titulo, texto) in zip(colunas, etapas):
    with coluna.container(border=True, height=230):
        st.markdown(f"**{titulo}**")
        st.caption(texto)

st.subheader("Para onde ir")
st.page_link("paginas/panorama.py", label="Comparar todas as UFs num indicador", icon="📊")
st.page_link("paginas/evolucao.py", label="Ver se a situação melhorou desde 2010", icon="📈")
st.page_link("paginas/noticias.py", label="Ler as notícias (com resumo feito pela IA)", icon="📰")
st.page_link("paginas/como_funciona_ia.py", label="Entender como a IA chega às respostas", icon="🔍")

with st.expander("Iniciativas e referências"):
    st.markdown(
        """
- [Painel Saneamento Brasil - Instituto Trata Brasil](https://www.painelsaneamento.org.br)
- [ODS 6 - Água potável e saneamento (ONU Brasil)](https://brasil.un.org/pt-br/sdgs/6)
- [Lei 14.026/2020 - Marco Legal do Saneamento](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14026.htm)
- [API de localidades e agregados do IBGE](https://servicodados.ibge.gov.br/api/docs)
- [Agência Brasil - Meio Ambiente](https://agenciabrasil.ebc.com.br/meio-ambiente)
"""
    )
