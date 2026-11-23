import streamlit as st

from src import preparo_llm
from src.comum import para_csv

st.title("🤖 Preparação para IA com LLM")
st.markdown(
    """
Nesta etapa ainda não há modelo conectado. O que esta página mostra é **como os dados já
estão organizados** para que, no próximo TP, eu só precise ligar um LLM:

| Uso planejado | Dado que já tenho | Entrega para o usuário |
|---|---|---|
| Resumo automático | texto completo das notícias | 3 frases por notícia, foco em água e saúde |
| Classificação de sentimento | notícias marcadas como ODS 6 | positivo / negativo / neutro sobre saneamento |
| Perguntas e respostas | fichas em texto das 27 UFs | "Qual estado do Nordeste piorou no esgoto?" |
| Geração de relatório | ranking + série + observações | parágrafo pronto para o gestor |
"""
)

documentos = preparo_llm.montar_corpus()
if not documentos:
    st.warning("Sem dados processados para montar o material de IA.")
    st.stop()

tipos = {}
for d in documentos:
    tipos.setdefault(d["tipo"], []).append(d)

c1, c2, c3 = st.columns(3)
c1.metric("Fichas de UF", len(tipos.get("ficha_uf", [])))
c2.metric("Notícias", len(tipos.get("noticia", [])))
c3.metric("Tokens aproximados", f"{sum(d['tokens_aprox'] for d in documentos):,}".replace(",", "."))

st.subheader("Exemplo de ficha (é isso que o modelo vai ler)")
fichas = tipos.get("ficha_uf", [])
escolhida = st.selectbox("UF", [f["sigla"] for f in fichas], index=[f["sigla"] for f in fichas].index("MA"))
ficha = next(f for f in fichas if f["sigla"] == escolhida)
st.info(ficha["texto"])

st.subheader("Pedidos (prompts) já desenhados")
nome = st.radio("Tarefa", list(preparo_llm.PROMPTS_PLANEJADOS), horizontal=True)
exemplo = preparo_llm.PROMPTS_PLANEJADOS[nome].format(
    texto="<texto da notícia>", contexto=ficha["texto"], pergunta="<pergunta do usuário>"
)
st.code(exemplo, language="text")

st.subheader("Baixar o material preparado")
linhas = [{k: v for k, v in d.items()} for d in documentos]
st.download_button("📥 corpus_llm.csv", para_csv(linhas), file_name="corpus_llm.csv", mime="text/csv")
st.caption("A versão em JSONL (um documento por linha) é gerada com: python -m src.preparo_llm")
