import streamlit as st

from src import dados
from src.comum import fmt, obter_noticias, obter_saneamento, obter_serie, para_csv
from src.validacao import ler_csv_enviado

st.title("📂 Enviar e baixar arquivos")

st.subheader("1. Comparar um dado seu com o painel")
st.markdown(
    "Envie um CSV com as colunas **sigla** e **valor** (opcional: **descricao**). "
    "Exemplo: investimento previsto por UF, número de obras, metas locais."
)
modelo = "sigla;valor;descricao\nMA;120,5;investimento previsto (R$ mi)\nPA;98;investimento previsto (R$ mi)\n"
st.download_button("Baixar modelo de CSV", modelo.encode("utf-8-sig"), file_name="modelo_envio.csv", mime="text/csv")

enviado = st.file_uploader("Seu arquivo CSV", type=["csv"])
if enviado is not None:
    linhas, avisos, erro = ler_csv_enviado(enviado.getvalue())
    if erro:
        st.error(erro)
    else:
        for aviso in avisos:
            st.caption(aviso)
        indicador = st.selectbox("Cruzar com qual indicador do painel?", list(dados.INDICADORES),
                                 format_func=dados.INDICADORES.get)
        por_sigla = {l["sigla"]: l for l in obter_saneamento()}
        cruzado = [
            {
                "sigla": l["sigla"],
                "seu_valor": l["valor"],
                "descricao": l["descricao"],
                indicador: por_sigla.get(l["sigla"], {}).get(indicador),
            }
            for l in linhas
        ]
        st.dataframe(cruzado, hide_index=True, width="stretch")
        st.scatter_chart(cruzado, x=indicador, y="seu_valor", height=300)
        st.download_button("📥 Baixar o cruzamento", para_csv(cruzado), file_name="cruzamento.csv", mime="text/csv")

st.divider()
st.subheader("2. Baixar os dados do projeto")
st.caption("Cada arquivo traz a coluna de fonte para quem receber saber de onde o dado veio.")

c1, c2, c3 = st.columns(3)
saneamento = obter_saneamento()
c1.download_button(f"Indicadores por UF ({len(saneamento)} linhas)",
                   para_csv([{**l, "fonte": "Painel Saneamento Brasil + IBGE"} for l in saneamento]),
                   file_name="saneamento_uf.csv", mime="text/csv")
serie = obter_serie()
c2.download_button(f"Série 2010-2024 ({len(serie)} linhas)",
                   para_csv([{**s, "fonte": "Painel Saneamento Brasil (Selenium)"} for s in serie]),
                   file_name="serie_saneamento_uf.csv", mime="text/csv")
noticias = obter_noticias()
c3.download_button(f"Notícias ({len(noticias)} linhas)",
                   para_csv([{k: v for k, v in n.items() if k != "texto"} for n in noticias]),
                   file_name="noticias.csv", mime="text/csv")

total_mb = sum(len(para_csv(x)) for x in (saneamento, serie, noticias)) / 1024 / 1024
st.caption(f"Tamanho total aproximado: {fmt(total_mb, 2)} MB")
