import streamlit as st

from src.comum import obter_noticias
from src.dados import contar_palavras

st.title("📰 Notícias e termos mais citados")
st.caption("Notícias da Agência Brasil (meio ambiente e saúde) coletadas com BeautifulSoup. Conteúdo sob licença Creative Commons.")

noticias = obter_noticias()
if not noticias:
    st.error("Nenhuma notícia coletada ainda. Rode: python -m src.coleta_noticias")
    st.stop()

with st.form("filtros_noticias"):
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.selectbox("Seção", ["todas", "meio-ambiente", "saude"], key="secao_noticias")
    so_ods6 = c2.checkbox("Só água e saneamento", value=False)
    termo = c3.text_input("Buscar palavra no título ou resumo", max_chars=40)
    st.form_submit_button("Filtrar")

filtradas = noticias
if st.session_state["secao_noticias"] != "todas":
    filtradas = [n for n in filtradas if n["secao"] == st.session_state["secao_noticias"]]
if so_ods6:
    filtradas = [n for n in filtradas if n["tema_ods6"] == "sim"]
if termo:
    filtradas = [n for n in filtradas if termo.lower() in (n["titulo"] + " " + n["resumo"]).lower()]

if not filtradas:
    st.warning("Nenhuma notícia com esses filtros. Tente outra palavra ou desmarque 'Só água e saneamento'.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Notícias", len(filtradas))
c2.metric("Ligadas ao ODS 6", sum(1 for n in filtradas if n["tema_ods6"] == "sim"))
c3.metric("Palavras lidas", f"{sum(n['palavras'] for n in filtradas):,}".replace(",", "."))

st.subheader("Termos mais frequentes (palavras com 4 letras ou mais)")
frequencia = contar_palavras([f"{n['titulo']} {n['resumo']} {n['texto']}" for n in filtradas])
st.bar_chart([{"termo": p, "vezes": q} for p, q in frequencia], x="termo", y="vezes", height=320, sort=False)

st.subheader("Notícias")
for n in filtradas:
    marca = "💧 " if n["tema_ods6"] == "sim" else ""
    with st.expander(f"{marca}{n['titulo']}  ·  {n['publicado_em'][:10]}"):
        st.write(n["resumo"] or "(sem resumo)")
        st.caption(f"Seção: {n['secao']} · {n['palavras']} palavras")
        st.link_button("Abrir na Agência Brasil", n["url"])
