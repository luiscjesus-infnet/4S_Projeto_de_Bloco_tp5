import streamlit as st

from src import dados
from src.comum import obter_noticias
from src.dados import contar_palavras

TEMAS_SANEAMENTO = {"abastecimento", "qualidade", "esgoto", "saude", "investimento"}

st.title("📰 Notícias")
st.caption("Notícias da Agência Brasil (meio ambiente e saúde) coletadas com BeautifulSoup, sob licença Creative Commons. "
           "Tema, sentimento e resumo foram feitos pelo modelo de linguagem local (src/classificar_noticias.py).")

noticias = obter_noticias()
if not noticias:
    st.error("Nenhuma notícia coletada ainda. Rode: python -m src.coleta_noticias")
    st.stop()

ia = {linha["url"]: linha for linha in dados.ler_csv(dados.PROCESSADOS / "noticias_ia.csv")}
for n in noticias:
    n.update({k: v for k, v in ia.get(n["url"], {}).items() if k != "url"})

with st.form("filtros_noticias"):
    c1, c2, c3 = st.columns([1, 1.3, 2])
    c1.selectbox("Seção", ["todas", "meio-ambiente", "saude"], key="secao_noticias")
    so_ods6 = c2.checkbox("Só água e saneamento (segundo o modelo)", value=False)
    termo = c3.text_input("Buscar palavra no título ou resumo", max_chars=40)
    st.form_submit_button("Filtrar")

filtradas = noticias
if st.session_state["secao_noticias"] != "todas":
    filtradas = [n for n in filtradas if n["secao"] == st.session_state["secao_noticias"]]
if so_ods6:
    filtradas = [n for n in filtradas if n.get("tema_ia") in TEMAS_SANEAMENTO]
if termo:
    filtradas = [n for n in filtradas if termo.lower() in (n["titulo"] + " " + n["resumo"]).lower()]

if not filtradas:
    st.warning("Nenhuma notícia com esses filtros. Tente outra palavra ou desmarque 'Só água e saneamento'.")
    st.stop()

com_ia = [n for n in filtradas if n.get("tema_ia")]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Notícias", len(filtradas))
c2.metric("Sobre saneamento (modelo)", sum(1 for n in com_ia if n["tema_ia"] in TEMAS_SANEAMENTO))
c3.metric("Ligadas ao ODS 6 (palavras-chave)", sum(1 for n in filtradas if n["tema_ods6"] == "sim"))
c4.metric("Palavras lidas", f"{sum(n['palavras'] for n in filtradas):,}".replace(",", "."))

if com_ia:
    st.subheader("Assunto das notícias: modelo x palavras-chave")
    contagem = {}
    for n in com_ia:
        contagem[n["tema_ia"]] = contagem.get(n["tema_ia"], 0) + 1
    g1, g2 = st.columns([1.3, 1])
    g1.bar_chart([{"tema": t, "notícias": q} for t, q in sorted(contagem.items(), key=lambda par: -par[1])],
                 x="tema", y="notícias", height=260, sort=False)
    divergentes = [n for n in com_ia if (n["tema_ods6"] == "sim") != (n["tema_ia"] in TEMAS_SANEAMENTO)]
    g2.markdown(
        f"A regra de palavras-chave do TP3 marca **{sum(1 for n in com_ia if n['tema_ods6'] == 'sim')}** destas "
        f"notícias como ligadas ao ODS 6; o modelo, que lê o sentido do texto, vê "
        f"**{sum(1 for n in com_ia if n['tema_ia'] in TEMAS_SANEAMENTO)}** sobre saneamento. "
        f"As duas discordam em **{len(divergentes)}** notícias."
    )
    g2.caption("Exemplo típico: notícia de chuva ou de biodiversidade cita \"água\" e a regra marca; "
               "o modelo classifica como \"outro\". O resultado também diz algo sobre a pauta: "
               "saneamento quase não aparece no noticiário coletado.")
    g2.caption("⚠️ O tema \"saude\" do modelo às vezes pega doenças que não têm a ver com água "
               "(o mesmo erro do benchmark do TP4). Abra a notícia para conferir.")

st.subheader("Termos mais frequentes (palavras com 4 letras ou mais)")
frequencia = contar_palavras([f"{n['titulo']} {n['resumo']} {n['texto']}" for n in filtradas])
st.bar_chart([{"termo": p, "vezes": q} for p, q in frequencia], x="termo", y="vezes", height=280, sort=False)

st.subheader("Notícias")
for n in filtradas:
    marca = "💧 " if n.get("tema_ia") in TEMAS_SANEAMENTO else ""
    with st.expander(f"{marca}{n['titulo']}  ·  {n['publicado_em'][:10]}"):
        if n.get("resumo_ia"):
            st.markdown(f"**Resumo feito pela IA:** {n['resumo_ia']}")
            st.caption(f"Tema: {n['tema_ia']} · sentimento: {n['sentimento_ia']} · "
                       "resumo automático: confira com o texto original")
        else:
            st.write(n["resumo"] or "(sem resumo)")
        st.caption(f"Seção: {n['secao']} · {n['palavras']} palavras · palavras-chave do TP3: {n['tema_ods6']}")
        st.link_button("Abrir na Agência Brasil", n["url"])
