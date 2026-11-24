"""
Assistente do painel: perguntas e respostas sobre os dados, com memória da conversa.

Fluxo de uma pergunta:
1. o painel manda a pergunta, o histórico e as notas (quem guarda é a sessão do painel);
2. escolho os fatos que interessam (src/fatos.py) - números já calculados no Python;
3. monto as mensagens: instruções + fatos + notas (papel "system"), a janela da
   conversa (papéis "user" e "assistant") e a pergunta nova ("user");
4. o motor (local ou API) escreve a resposta;
5. confiro se cada número da resposta aparece no que o modelo leu e atualizo as notas.

O mesmo código atende a API (POST /conversar) e a avaliação (src/avaliar_memoria.py),
então o que eu medi é exatamente o que roda no painel.
"""
import re
import time

from src import memoria
from src.fatos import BaseDeFatos

INSTRUCOES_FATOS = (
    "Você é o assistente do Painel ODS 6, que mostra o acesso à água e ao esgoto nas UFs do Brasil. "
    "Responda em português, em no máximo 3 frases curtas, usando só os fatos abaixo. "
    "Comece pela resposta direta, com o nome da UF, e justifique com até dois números dos fatos. "
    "Não faça contas: os números já estão calculados; copie-os como estão, com o ano. "
    "Se a pergunta se referir a algo dito antes (ela, esse estado, e em 2010?), use a conversa e as notas. "
    "Se a resposta não estiver nos fatos, diga que o painel não tem esse dado."
)
INSTRUCOES_TABELA = (
    "Você é o assistente do Painel ODS 6, que mostra o acesso à água e ao esgoto nas UFs do Brasil. "
    "Responda em português, em no máximo 3 frases curtas, usando só a tabela abaixo. "
    "Se a pergunta se referir a algo dito antes, use a conversa. "
    "Se a resposta não estiver na tabela, diga que o painel não tem esse dado."
)
INSTRUCOES_RESUMO = "Você resume conversas em português, de forma fiel e curta."

RE_REGIAO = re.compile(r"\bregi(ao|oes)\b")
RE_NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")
MAX_FRASES = 3


def limitar_frases(texto, cortada):
    """
    O modelo nem sempre respeita o "no máximo 3 frases", e é justamente no excesso que
    ele mais inventa. Fico com as 3 primeiras; se a geração parou no meio de uma frase,
    descarto o pedaço solto.
    """
    frases = [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]
    if cortada and len(frases) > 1 and not re.search(r"[.!?]$", frases[-1]):
        frases = frases[:-1]
    return " ".join(frases[:MAX_FRASES]), max(len(frases) - MAX_FRASES, 0)


def estado_vazio():
    """O que o painel guarda entre uma pergunta e outra, além do histórico visível."""
    return {"notas": memoria.notas_vazias(), "resumo": "", "resumido_ate": 0}


def _numero(texto):
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", texto):
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return round(float(texto), 2)
    except ValueError:
        return None


def conferir_numeros(resposta, lido):
    """
    Números da resposta que não aparecem em nada do que o modelo recebeu. Não bloqueia
    a resposta: vira um aviso no painel ("confira este número"). Números até 10 ficam de
    fora (posições, quantidade de frases, "3 UFs").
    """
    conhecidos = {_numero(n) for n in RE_NUMERO.findall(lido)}
    citados = [n for n in RE_NUMERO.findall(resposta) if (_numero(n) or 0) > 10]
    sem_origem = [n for n in citados if _numero(n) not in conhecidos]
    return {"numeros_citados": len(citados), "sem_origem": list(dict.fromkeys(sem_origem))}


class Assistente:
    def __init__(self, base=None):
        self.base = base or BaseDeFatos()

    # ------------------------------------------------------------------ fatos
    def selecionar_fatos(self, pergunta, notas):
        """Blocos de fatos para esta pergunta: [(id, texto), ...]."""
        achados = memoria.extrair(pergunta)
        texto = memoria.sem_acento(pergunta)
        notas = notas or memoria.notas_vazias()
        assunto = (achados["assuntos"] or [notas.get("assunto")])[0]
        regiao = (achados["regioes"] or [None])[0]
        ano = achados["ano"] or notas.get("ano")

        foco = memoria.ufs_em_foco(pergunta, notas)
        blocos = [("brasil", self.base.bloco_brasil())]
        if regiao or RE_REGIAO.search(texto):
            blocos.append((f"regioes{'_' + regiao if regiao else ''}", self.base.bloco_regioes(regiao)))
            # pergunta de região sem UF: a ficha da UF lembrada só atrapalha (na 1ª rodada o modelo
            # respondia "Nordeste" porque a ficha do Maranhão, da pergunta anterior, ia junto)
            if not achados["ufs"]:
                foco = []
        # ranking só quando a pergunta compara ("qual", "maior", "pior"...) ou não tem UF nenhuma em foco.
        # Na 1ª rodada da avaliação ele ia junto em "quantas pessoas estão sem água lá?" e o modelo
        # respondia com a 1ª do ranking (Acre) em vez da UF lembrada (Pará).
        quer_ranking = bool(memoria.RE_RANKING.search(texto)) or not foco
        if assunto and assunto != "prioridade" and quer_ranking:
            blocos.append((f"ranking_{assunto}", self.base.bloco_ranking(assunto)))
        for sigla in foco:
            blocos.append((f"uf_{sigla}", self.base.ficha_uf(sigla, ano=ano)))
        return blocos

    # ------------------------------------------------------------------ pedido
    def montar_mensagens(self, pergunta, historico, estado, estrategia="janela_notas", contexto="fatos",
                         janela=memoria.JANELA_PADRAO):
        estado = {**estado_vazio(), **(estado or {})}
        anteriores = memoria.historico_para_envio(historico, estrategia, janela)

        if estrategia == "janela_notas":
            notas = estado["notas"]                 # notas da conversa inteira, guardadas pelo painel
        else:
            notas = memoria.notas_vazias()          # só o que o modelo vai ver (janela ou conversa inteira)
            if estrategia == "resumo" and estado["resumo"]:
                notas = memoria.atualizar_notas(notas, estado["resumo"], "")   # UFs que ficaram no resumo
            for i in range(0, len(anteriores) - 1, 2):
                notas = memoria.atualizar_notas(notas, anteriores[i]["content"], anteriores[i + 1]["content"])

        if contexto == "tabela":
            blocos = [("tabela_crua", self.base.tabela_crua())]
            sistema = INSTRUCOES_TABELA + "\n\nTabela:\n" + blocos[0][1]
        else:
            blocos = self.selecionar_fatos(pergunta, notas)
            sistema = INSTRUCOES_FATOS
            if estrategia == "resumo" and estado["resumo"]:
                sistema += "\n\nResumo do começo da conversa: " + estado["resumo"]
            if estrategia == "janela_notas":
                texto_notas = memoria.texto_das_notas(notas)
                if texto_notas:
                    sistema += "\n\n" + texto_notas
            sistema += "\n\nFatos:\n" + "\n\n".join(texto for _, texto in blocos)

        mensagens = [{"role": "system", "content": sistema}]
        mensagens += [{"role": m["role"], "content": m["content"]} for m in anteriores]
        mensagens.append({"role": "user", "content": pergunta})
        return mensagens, [b for b, _ in blocos], len(anteriores)

    # ------------------------------------------------------------------ memória por resumo
    def _resumir_o_que_saiu(self, motor, historico, estado, janela):
        """Estratégia 'resumo': quando mensagens saem da janela, o próprio modelo resume."""
        limite = max(len(historico) - 2 * janela, 0)
        if limite <= estado["resumido_ate"]:
            return estado, 0.0, 0
        trecho = historico[estado["resumido_ate"]:limite]
        conversa = "\n".join(f"{'Pessoa' if m['role'] == 'user' else 'Assistente'}: {m['content']}" for m in trecho)
        pedido = (
            (f"Resumo anterior: {estado['resumo']}\n\n" if estado["resumo"] else "")
            + f"Trecho novo da conversa:\n{conversa}\n\n"
            "Escreva um resumo de no máximo 3 frases do que a pessoa perguntou e do que o assistente respondeu, "
            "na ordem em que aconteceu, mantendo os nomes dos estados e os números citados."
        )
        inicio = time.perf_counter()
        saida = motor.responder([{"role": "system", "content": INSTRUCOES_RESUMO},
                                 {"role": "user", "content": pedido}], 160)
        novo = {**estado, "resumo": saida["texto"], "resumido_ate": limite}
        return novo, time.perf_counter() - inicio, saida["tokens_entrada"]

    # ------------------------------------------------------------------ porta de entrada
    def responder(self, motor, pergunta, historico=None, estado=None, estrategia="janela_notas",
                  contexto="fatos", janela=memoria.JANELA_PADRAO, max_novos=None):
        historico = list(historico or [])
        estado = {**estado_vazio(), **(estado or {})}
        segundos_resumo, tokens_resumo = 0.0, 0
        if estrategia == "resumo":
            estado, segundos_resumo, tokens_resumo = self._resumir_o_que_saiu(motor, historico, estado, janela)

        mensagens, fatos_usados, enviadas = self.montar_mensagens(pergunta, historico, estado, estrategia,
                                                                  contexto, janela)
        aviso = None
        # o modelo local tem limite de tamanho; se a conversa inteira passar, saem as trocas mais antigas
        if getattr(motor, "tipo", "") == "local":
            from src.motor_llm import MAX_TOKENS_CONVERSA
            while len(mensagens) > 3 and motor.contar_tokens(mensagens) > MAX_TOKENS_CONVERSA:
                del mensagens[1:3]
                enviadas -= 2
                aviso = "A conversa ficou longa e as trocas mais antigas não foram enviadas ao modelo."

        inicio = time.perf_counter()
        saida = motor.responder(mensagens, max_novos) if max_novos else motor.responder(mensagens)
        segundos = saida.get("segundos") or round(time.perf_counter() - inicio, 2)
        texto_bruto = re.sub(r"\s+", " ", saida["texto"]).strip()
        texto, frases_cortadas = limitar_frases(texto_bruto, saida.get("cortada"))
        if not texto:
            texto = texto_bruto

        lido = "\n".join(m["content"] for m in mensagens)
        conferencia = conferir_numeros(texto, lido)
        if conferencia["sem_origem"]:
            aviso = ((aviso + " ") if aviso else "") + (
                "Confira: " + ", ".join(conferencia["sem_origem"])
                + (" não aparece" if len(conferencia["sem_origem"]) == 1 else " não aparecem")
                + " nos dados que o modelo recebeu."
            )

        estado["notas"] = memoria.atualizar_notas(estado["notas"], pergunta, texto)
        return {
            "resposta": texto,
            "estrategia": estrategia,
            "contexto": contexto,
            "motor": motor.descricao(),
            "tokens_entrada": saida["tokens_entrada"],
            "tokens_saida": saida["tokens_saida"],
            "segundos": round(segundos + segundos_resumo, 2),
            "segundos_resumo": round(segundos_resumo, 2),
            "tokens_resumo": tokens_resumo,
            "mensagens_enviadas": enviadas,
            "fatos_usados": fatos_usados,
            "frases_cortadas": frases_cortadas,
            "conferencia": conferencia,
            "estado": estado,
            "aviso": aviso,
            "pedido": mensagens,
        }
