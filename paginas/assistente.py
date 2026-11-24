"""
Assistente do painel: conversa sobre os dados com memória.

Quem lembra a conversa é esta página (st.session_state). A cada pergunta ela manda à
API o histórico e as notas, e guarda o que volta. Sem o session_state, o Streamlit
roda o arquivo de novo a cada clique e a conversa sumiria da tela e da memória.
"""
import streamlit as st

from src import cliente_api
from src.memoria import NOME_ASSUNTO, NOME_OFICIAL

SUGESTOES = [
    "Quais UFs deveriam receber investimento primeiro e por quê?",
    "Qual a parcela da população sem água no Pará?",
    "No ritmo atual, quais UFs chegam à meta de esgoto até 2033?",
    "Qual região tem a pior média de coleta de esgoto?",
]
NOME_MOTOR = {"local": "Modelo local", "api": "Serviço externo"}

# ---------------------------------------------------------------- estado da conversa (por usuário)
st.session_state.setdefault("chat_mensagens", [])    # o que aparece na tela (com as medidas de cada resposta)
st.session_state.setdefault("chat_notas", None)      # notas devolvidas pela API na última resposta
st.session_state.setdefault("chat_pendente", None)   # pergunta vinda de um botão de sugestão


def nova_conversa():
    st.session_state["chat_mensagens"] = []
    st.session_state["chat_notas"] = None


def usar_sugestao(texto):
    st.session_state["chat_pendente"] = texto


st.title("💬 Assistente do painel")
st.caption(
    "Pergunte sobre água, esgoto, saúde, metas de 2033 e prioridade de investimento por UF. "
    "O assistente responde só com os dados do painel e lembra da conversa: dá para perguntar "
    "\"e em 2010?\" ou \"voltando ao primeiro estado...\"."
)

status, erro = cliente_api.motores()
if erro:
    st.error(erro)
    st.info("O assistente depende da API do projeto. Na raiz do projeto: `uvicorn api.main:app`. "
            "As outras páginas do painel continuam funcionando.")
    st.stop()

disponiveis = [m for m in status["motores"] if m["disponivel"]]
if not disponiveis:
    st.warning("A API está no ar, mas nenhum motor de IA está pronto.")
    for m in status["motores"]:
        st.caption(f"{NOME_MOTOR[m['tipo']]}: {m['motivo']}")
    st.stop()

# ---------------------------------------------------------------- opções (barra lateral)
with st.sidebar:
    st.markdown("**Assistente**")
    tipos = [m["tipo"] for m in disponiveis]
    rotulos = {m["tipo"]: f"{NOME_MOTOR[m['tipo']]} - {m['nome']}" for m in disponiveis}
    padrao = tipos.index(status["padrao"]) if status["padrao"] in tipos else 0
    motor = st.radio("Motor de IA", tipos, index=padrao, format_func=rotulos.get, key="chat_motor")
    indisponiveis = [m for m in status["motores"] if not m["disponivel"]]
    for m in indisponiveis:
        st.caption(f"{NOME_MOTOR[m['tipo']]} indisponível: {m['motivo']}")
    with st.expander("Memória (avançado)"):
        estrategias = status["estrategias"]
        memoria = st.selectbox("Como lembrar a conversa", list(estrategias), format_func=estrategias.get,
                               key="chat_memoria")
        st.caption("A recomendada manda ao modelo as 2 últimas trocas e as notas da conversa. "
                   "As outras existem para comparar (ver a página Como a IA funciona).")
    st.button("🧹 Nova conversa", on_click=nova_conversa, width="stretch")

col_chat, col_memoria = st.columns([2.4, 1], gap="large")

# ---------------------------------------------------------------- conversa
pergunta = st.chat_input("Escreva sua pergunta sobre os dados do painel")
if st.session_state["chat_pendente"]:
    pergunta = st.session_state["chat_pendente"]
    st.session_state["chat_pendente"] = None


def mostrar_medidas(info):
    partes = [f"⏱ {info['segundos']:.1f} s".replace(".", ","),
              f"{info['tokens_entrada']} tokens lidos pelo modelo",
              f"{NOME_MOTOR[info['motor']['tipo']].lower()}"]
    st.caption(" · ".join(partes))
    if info.get("aviso"):
        st.caption(f"⚠️ {info['aviso']}")
    with st.expander("O que o modelo leu para responder"):
        st.caption(f"Fatos escolhidos: {', '.join(info['fatos_usados'])} · falas anteriores enviadas: "
                   f"{info['mensagens_enviadas']}")
        for m in info.get("pedido") or []:
            st.markdown(f"**{m['role']}**")
            st.text(m["content"])


with col_chat:
    if not st.session_state["chat_mensagens"] and not pergunta:
        st.markdown("**Sugestões para começar:**")
        for i, texto in enumerate(SUGESTOES):
            st.button(texto, key=f"sugestao_{i}", on_click=usar_sugestao, args=(texto,))

    for msg in st.session_state["chat_mensagens"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("info"):
                mostrar_medidas(msg["info"])

    if pergunta:
        with st.chat_message("user"):
            st.markdown(pergunta)
        with st.chat_message("assistant"):
            espera = "alguns segundos" if motor == "api" else "de 10 a 40 segundos no modelo local"
            with st.spinner(f"Consultando os dados e escrevendo a resposta ({espera})..."):
                resposta, erro = cliente_api.conversar(
                    pergunta, st.session_state["chat_mensagens"], st.session_state["chat_notas"],
                    memoria=memoria, motor=motor,
                )
            if erro:
                # a pergunta não entra no histórico: a pessoa pode tentar de novo
                st.error(erro)
            else:
                st.markdown(resposta["resposta"])
                mostrar_medidas(resposta)
                st.session_state["chat_mensagens"] += [
                    {"role": "user", "content": pergunta},
                    {"role": "assistant", "content": resposta["resposta"], "info": resposta},
                ]
                st.session_state["chat_notas"] = resposta["notas"]

    if st.session_state["chat_mensagens"]:
        st.caption("As respostas são escritas por um modelo de linguagem a partir dos números do painel, que são "
                   "calculados no Python. Mesmo assim ele pode errar: confira em \"O que o modelo leu\" ou na "
                   "página Prioridades antes de usar um número numa decisão.")

# ---------------------------------------------------------------- o que está na memória
with col_memoria:
    st.markdown("##### 🧠 O que o assistente lembra")
    notas = st.session_state["chat_notas"]
    if not notas:
        st.caption("Nada ainda. As notas aparecem depois da primeira resposta.")
    else:
        if notas["ufs_citadas"]:
            st.markdown("**UFs que você perguntou, na ordem**")
            st.write(" → ".join(f"{i}. {NOME_OFICIAL[s]}" for i, s in enumerate(notas["ufs_citadas"], start=1)))
        if notas.get("assunto"):
            st.markdown(f"**Assunto:** {NOME_ASSUNTO.get(notas['assunto'], notas['assunto'])}")
        if notas.get("regiao"):
            st.markdown(f"**Região:** {notas['regiao']}")
        if notas.get("ano"):
            st.markdown(f"**Ano citado:** {notas['ano']}")
        st.caption("Estas notas são anotadas pelo próprio painel (sem gastar o modelo) e vão junto com "
                   "as 2 últimas trocas. Por isso o assistente lembra do começo da conversa sem reenviar tudo.")

    medidas = [m["info"] for m in st.session_state["chat_mensagens"] if m.get("info")]
    if medidas:
        st.markdown("**Tokens lidos pelo modelo a cada pergunta**")
        st.bar_chart([{"pergunta": f"{i}ª", "tokens": m["tokens_entrada"]} for i, m in enumerate(medidas, start=1)],
                     x="pergunta", y="tokens", height=180, sort=False)
        tempo = sum(m["segundos"] for m in medidas)
        st.caption(f"{len(medidas)} respostas · {tempo:.0f} s no total".replace(".", ","))
