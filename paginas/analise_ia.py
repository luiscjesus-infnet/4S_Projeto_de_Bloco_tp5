import streamlit as st

from src import cliente_api, dados
from src.comum import obter_noticias

TIPOS = {"tema": "Tema de saneamento", "sentimento": "Sentimento", "resumo": "Resumo (até 3 frases)"}

st.title("🧠 Análise de texto com IA")
st.markdown(
    "O texto vai para a **API do projeto** (`POST /processar_texto`), que usa um modelo de linguagem "
    "**rodando nesta máquina**, sem serviço externo. O painel nunca fala direto com o modelo."
)

status, erro = cliente_api.status_modelo()
if erro:
    st.error(erro)
    st.info("Para subir a API, na raiz do projeto: `uvicorn api.main:app`. As outras páginas continuam funcionando.")
    st.stop()
if status["carregado"]:
    st.success(
        f"Modelo pronto: **{status['nome']}** · {status['dispositivo'].upper()} · "
        f"{status['parametros_milhoes']} milhões de parâmetros · carregado em {status['segundos_carregando']} s"
    )
else:
    st.warning(f"A API está no ar, mas o modelo não carregou. Motivo: {status['erro']}")
    st.caption("Se você enviar um texto assim mesmo, vai ver a mensagem de erro que a API devolve (503).")

# ---------------------------------------------------------------- escolha do texto
origem = st.radio("De onde vem o texto?", ["Escrever", "Notícia coletada", "Observação enviada"], horizontal=True)
texto_inicial = ""
if origem == "Notícia coletada":
    noticias = obter_noticias()
    escolhida = st.selectbox("Notícia", noticias, format_func=lambda n: f"[{n['secao']}] {n['titulo']}")
    texto_inicial = f"{escolhida['titulo']}. {escolhida['texto']}" if escolhida else ""
    if escolhida:
        st.caption(f"Fonte: [{escolhida['url']}]({escolhida['url']}) · marcação por palavras-chave do TP3: "
                   f"tema_ods6 = **{escolhida['tema_ods6']}**")
elif origem == "Observação enviada":
    observacoes = dados.ler_observacoes()
    if observacoes:
        obs = st.selectbox("Observação", observacoes, format_func=lambda o: f"#{o['id']} {o['sigla']} - {o['texto'][:60]}")
        texto_inicial = obs["texto"] if obs else ""
    else:
        st.info("Nenhuma observação enviada ainda. Use a página API do projeto para enviar uma.")

with st.form("analise_ia"):
    texto = st.text_area("Texto (15 a 5.000 caracteres)", value=texto_inicial, height=180, max_chars=5000)
    tipo = st.radio("Análise", list(TIPOS), format_func=TIPOS.get, horizontal=True)
    enviar = st.form_submit_button("Analisar com o modelo local", type="primary")

if tipo == "resumo":
    st.caption("O resumo é a análise mais demorada em CPU (cerca de 15 a 40 s para uma notícia inteira).")

# ---------------------------------------------------------------- resultado
if enviar:
    with st.spinner("O modelo está analisando o texto..."):
        resposta, erro = cliente_api.processar_texto(texto, tipo)
    if erro:
        st.error(erro)
    else:
        resultado = resposta["resultado"]
        st.session_state.setdefault("analises_ia", []).insert(0, {
            "análise": TIPOS[resposta["tipo_analise"]],
            "resultado": resultado.get("categoria") or resultado.get("sentimento") or resultado.get("resumo"),
            "segundos": resposta["segundos"],
            "texto": resposta["texto_processado"][:80],
        })

        if resultado["tipo"] == "resumo":
            st.subheader("Resumo")
            st.info(resultado["resumo"])
            st.caption("Confira com o texto original: um modelo pequeno pode trocar ou inventar detalhes.")
        else:
            nome = resultado.get("categoria") or resultado.get("sentimento")
            c1, c2 = st.columns([1, 2])
            c1.metric("Tema" if resultado["tipo"] == "tema" else "Sentimento", nome)
            c1.metric("Confiança do modelo", f"{resultado['confianca']:.0%}")
            if resultado.get("descricao"):
                c1.caption(resultado["descricao"])
            linhas = [{"opção": k, "pontuação": v} for k, v in resultado["pontuacoes"].items()]
            c2.bar_chart(linhas, x="opção", y="pontuação", horizontal=True, height=230)

        st.caption(
            f"{resposta['segundos']} s · {resposta['tokens_entrada']} tokens de entrada · "
            f"{resposta['modelo']['nome']} ({resposta['modelo']['dispositivo']}, {resposta['modelo']['precisao']})"
        )
        if resposta.get("aviso"):
            st.caption(f"ℹ️ {resposta['aviso']}")
        with st.expander("Ver o JSON devolvido pela API"):
            st.json(resposta)

if st.session_state.get("analises_ia"):
    st.divider()
    st.markdown("**Análises desta sessão**")
    st.dataframe(st.session_state["analises_ia"][:10], hide_index=True, width="stretch")
