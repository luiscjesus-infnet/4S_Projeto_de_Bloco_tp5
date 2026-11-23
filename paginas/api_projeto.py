import streamlit as st

from src import cliente_api
from src.dados import INDICADORES, SIGLAS

st.title("🔌 API do projeto (FastAPI)")
st.markdown(
    "Esta página não lê os arquivos direto: ela conversa com a **API do projeto** por HTTP, "
    "do mesmo jeito que outro sistema (de uma secretaria, por exemplo) faria."
)

no_ar = cliente_api.api_no_ar()
if no_ar:
    st.success(f"API respondendo em {cliente_api.API_URL} · documentação em {cliente_api.API_URL}/docs")
else:
    st.error(
        f"A API não está respondendo em {cliente_api.API_URL}. Para subir localmente, na raiz do projeto:\n\n"
        "`uvicorn api.main:app --reload`"
    )
    st.info("No Streamlit Cloud só o painel fica publicado; as demais páginas continuam funcionando com os arquivos locais.")
    st.stop()

aba_consulta, aba_envio, aba_fontes = st.tabs(["Consultar (GET)", "Enviar observação (POST)", "Fontes"])

with aba_consulta:
    c1, c2 = st.columns([2, 1])
    indicador = c1.selectbox("Indicador do ranking", list(INDICADORES), format_func=INDICADORES.get)
    limite = c2.number_input("Quantas UFs", min_value=1, max_value=27, value=5, step=1)
    resposta, erro = cliente_api.consultar("/saneamento/ranking", {"indicador": indicador, "limite": int(limite)})
    if erro:
        st.error(erro)
    else:
        st.caption(f"GET {cliente_api.API_URL}/saneamento/ranking?indicador={indicador}&limite={int(limite)}")
        st.dataframe(resposta["ranking"], hide_index=True, width="stretch")
        with st.expander("Ver o JSON devolvido pela API"):
            st.json(resposta)

    st.divider()
    sigla = st.selectbox("Série histórica de uma UF", SIGLAS, index=SIGLAS.index("MA"))
    serie, erro = cliente_api.consultar(f"/serie/{sigla}", {"indicador": "POP_SEM_ES%"})
    if erro:
        st.error(erro)
    else:
        st.caption(f"GET {cliente_api.API_URL}/serie/{sigla}?indicador=POP_SEM_ES%")
        st.line_chart(serie["pontos"], x="ano", y="valor", height=250)

with aba_envio:
    st.markdown("Quem está em campo pode registrar uma observação sobre uma UF. Ela é gravada pela API.")
    with st.form("nova_observacao", clear_on_submit=True):
        c1, c2 = st.columns(2)
        uf = c1.selectbox("UF", SIGLAS)
        tipo = c2.radio("Tipo", ["campo", "correcao", "sugestao"], horizontal=True)
        autor = st.text_input("Seu nome", max_chars=60)
        texto = st.text_area("Observação (mínimo 10 caracteres)", max_chars=600)
        enviar = st.form_submit_button("Enviar para a API")
    if enviar:
        resposta, erro = cliente_api.enviar_observacao(uf, autor, tipo, texto)
        if erro:
            st.error(erro)
        else:
            st.session_state["observacoes_enviadas"] += 1
            st.success(f"Observação nº {resposta['observacao']['id']} registrada.")

    lista, erro = cliente_api.consultar("/observacoes")
    if lista and lista["total"]:
        st.caption(f"{lista['total']} observação(ões) na API · {st.session_state['observacoes_enviadas']} enviada(s) nesta sessão")
        st.dataframe(lista["observacoes"], hide_index=True, width="stretch")

with aba_fontes:
    fontes, erro = cliente_api.consultar("/fontes")
    if erro:
        st.error(erro)
    else:
        st.dataframe(fontes, hide_index=True, width="stretch")
