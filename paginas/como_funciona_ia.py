"""
Como a IA funciona no projeto: onde o modelo entra, o caminho de uma pergunta, o que
ele lê e como eu medi a memória do assistente.
"""
import streamlit as st

from src import dados
from src.assistente import INSTRUCOES_FATOS
from src.comum import obter_base_fatos

ARQ_POR_PERGUNTA = dados.BASE / "data" / "avaliacao" / "memoria_por_pergunta.csv"
ARQ_RESULTADO = dados.BASE / "data" / "avaliacao" / "memoria_resultado.csv"

st.title("🔍 Como a IA funciona aqui")
st.markdown(
    "A IA entra em dois pontos do projeto, sempre **depois** da coleta e do tratamento dos dados. "
    "A regra que segui: **conta e regra ficam no Python; o modelo de linguagem só lê e escreve texto.**"
)
st.table([
    {"Onde": "Assistente do painel", "O que o modelo faz": "responde perguntas com memória da conversa",
     "O que ele recebe": "instruções + fatos calculados + notas + 2 últimas trocas",
     "Modelo": "Qwen2.5-1.5B local (ou serviço externo pelo .env)"},
    {"Onde": "Notícias", "O que o modelo faz": "tema, sentimento e resumo de cada notícia (em lote)",
     "O que ele recebe": "título e texto da notícia coletada", "Modelo": "Qwen2.5-1.5B local"},
    {"Onde": "Análise de texto com IA", "O que o modelo faz": "tema, sentimento ou resumo de um texto avulso",
     "O que ele recebe": "texto digitado, notícia ou observação", "Modelo": "Qwen2.5-1.5B local"},
])

st.subheader("O caminho de uma pergunta")
_, coluna_diagrama, _ = st.columns([1, 2, 1])
coluna_diagrama.graphviz_chart(
    """
digraph {
  rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.35;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", color="#2a78d6", fontname="Helvetica", fontsize=11];
  edge [color="#555555", fontname="Helvetica", fontsize=9];
  painel [label="Painel\\n(guarda histórico\\ne notas na sessão)"];
  api [label="API\\nPOST /conversar\\n(não guarda nada)"];
  fatos [label="Seleção de fatos\\n(Python: UFs, assunto,\\nano, região)", fillcolor="#e9f6ee", color="#3fa66b"];
  pedido [label="Pedido ao modelo\\ninstruções + fatos +\\nnotas + 2 últimas trocas"];
  modelo [label="Modelo de linguagem\\nlocal ou serviço externo", fillcolor="#fdf1e3", color="#e0a526"];
  confere [label="Conferência\\ndos números\\n(Python)", fillcolor="#e9f6ee", color="#3fa66b"];
  painel -> api [label="pergunta + histórico + notas"];
  api -> fatos -> pedido -> modelo -> confere;
  confere -> painel [label="resposta + notas atualizadas"];
}
"""
)
st.caption("Verde = Python (determinístico). Laranja = modelo de linguagem. O modelo não lembra de nada entre "
           "uma pergunta e outra: quem lembra é o painel, que reenvia o que importa a cada pergunta.")

st.subheader("O que o modelo lê")
base = obter_base_fatos()
c1, c2 = st.columns([1, 1.4])
with c1:
    st.markdown("**Instruções (papel de sistema)**")
    st.info(INSTRUCOES_FATOS)
    st.markdown("**Visão geral (vai em toda pergunta)**")
    st.text(base.bloco_brasil())
with c2:
    siglas = [l["sigla"] for l in base.prioridade]
    escolhida = st.selectbox("Ficha de uma UF (vai quando a UF está na pergunta ou nas notas)", siglas,
                             format_func=lambda s: f"{base.nome_uf(s)} ({s})")
    st.text(base.ficha_uf(escolhida))
st.caption("Todos esses números foram calculados no Python a partir dos dados coletados (src/analise.py e "
           "src/fatos.py). Mandar a tabela inteira a cada pergunta seria mais caro e, como mostra a avaliação "
           "abaixo, o modelo pequeno erra quando precisa fazer as contas sozinho.")

st.subheader("Avaliação da memória")
por_pergunta = dados.ler_csv(ARQ_POR_PERGUNTA)
resultado = dados.ler_csv(ARQ_RESULTADO)
if not por_pergunta:
    st.info("A avaliação ainda não foi rodada. Na raiz do projeto: `python -m src.avaliar_memoria`.")
    st.stop()

st.markdown(
    "A mesma conversa de 10 perguntas, com gabarito, foi feita com cada jeito de lembrar. Várias perguntas só "
    "fazem sentido com a anterior (\"E sem coleta de esgoto?\") e as duas últimas voltam ao primeiro estado "
    "citado. O roteiro está em `data/avaliacao/conversa_teste.csv` e o código em `src/avaliar_memoria.py`."
)
st.dataframe(
    [{"jeito de lembrar": r["rodada"], "acertos": f"{r['acertos']}/{r['perguntas']}",
      "acertos nas que dependem da conversa": f"{r['acertos_que_dependem_de_memoria']}/{r['perguntas_que_dependem_de_memoria']}",
      "tokens por pergunta (média)": int(r["tokens_entrada_media"]),
      "tokens na 10ª pergunta": int(r["tokens_entrada_ultima"]),
      "tempo total (s)": float(r["segundos_total"])} for r in resultado],
    hide_index=True, width="stretch",
)
grafico = [{"pergunta": int(i["ordem"]), "tokens": int(i["tokens_entrada"]), "jeito de lembrar": i["rodada"]}
           for i in por_pergunta if i["contexto"] == "fatos"]
st.markdown("**Tokens enviados ao modelo a cada pergunta**")
st.line_chart(grafico, x="pergunta", y="tokens", color="jeito de lembrar", height=320)

with st.expander("Ver as respostas de cada rodada"):
    rodadas = list(dict.fromkeys(i["rodada"] for i in por_pergunta))
    rodada = st.selectbox("Rodada", rodadas, index=rodadas.index("janela + notas") if "janela + notas" in rodadas else 0)
    st.dataframe(
        [{"nº": int(i["ordem"]), "pergunta": i["pergunta"], "resposta": i["resposta"],
          "certo?": "✅" if i["acertou"] == "True" else "❌", "gabarito": i["gabarito"]}
         for i in por_pergunta if i["rodada"] == rodada],
        hide_index=True, width="stretch",
        column_config={"resposta": st.column_config.TextColumn(width="large")},
    )
st.caption(f"Modelo: {por_pergunta[0]['motor']}, rodando em CPU. Resultado completo em "
           "data/avaliacao/memoria_por_pergunta.csv.")
