"""
Memória da conversa do assistente.

O modelo não lembra de nada entre uma chamada e outra: a cada pergunta eu mando de
novo tudo o que ele precisa saber. Quem guarda a conversa é o painel
(st.session_state); a API também não guarda nada. Aqui fica a decisão do que mandar.

Estratégias (comparadas em src/avaliar_memoria.py):
- sem_memoria:  só a pergunta atual
- completa:     a conversa inteira (os tokens crescem a cada pergunta)
- janela:       só as últimas N trocas (tokens estáveis, mas esquece o começo)
- resumo:       janela + um resumo do que saiu dela, escrito pelo próprio modelo
- janela_notas: janela + notas que o Python anota sozinho (UFs citadas em ordem,
                assunto, região, ano). É a que o painel usa.

As notas não gastam chamada ao modelo: são extraídas com expressões regulares da
pergunta e da resposta.
"""
import re
import unicodedata

from src.dados import REGIOES, SIGLAS

ESTRATEGIAS = {
    "janela_notas": "Janela das últimas trocas + notas (recomendada)",
    "janela": "Só as últimas trocas",
    "completa": "Conversa inteira",
    "sem_memoria": "Sem memória (cada pergunta sozinha)",
    "resumo": "Janela + resumo escrito pelo modelo",
}
JANELA_PADRAO = 2   # trocas (pergunta + resposta) que vão inteiras para o modelo

NOMES_UF = {
    "AC": ["acre"], "AL": ["alagoas"], "AP": ["amapa"], "AM": ["amazonas"], "BA": ["bahia"],
    "CE": ["ceara"], "DF": ["distrito federal", "brasilia"], "ES": ["espirito santo"], "GO": ["goias"],
    "MA": ["maranhao"], "MT": ["mato grosso"], "MS": ["mato grosso do sul"], "MG": ["minas gerais", "minas"],
    "PB": ["paraiba"], "PR": ["parana"], "PE": ["pernambuco"], "PI": ["piaui"],
    "RJ": ["rio de janeiro"], "RN": ["rio grande do norte"], "RS": ["rio grande do sul"], "RO": ["rondonia"],
    "RR": ["roraima"], "SC": ["santa catarina"], "SP": ["sao paulo"], "SE": ["sergipe"], "TO": ["tocantins"],
    # "Pará" fica de fora daqui: sem acento vira "para", a preposição. Ele é tratado à parte, com acento.
}
NOME_OFICIAL = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}

# assunto -> palavras (sem acento). A ordem importa: "esgoto tratado" é tratamento, não coleta.
ASSUNTOS = [
    ("meta", r"\bmetas?\b|2033|\bmarco\b"),
    ("prioridade", r"priorid|investim|investir|\brecursos?\b|urgen"),
    ("obitos_vh", r"obitos?|mortes?|morre"),
    ("internacoes_10mil", r"internac|saude|doenca|hospita"),
    ("esgoto_tratado_pct", r"tratad|tratamento"),
    ("sem_esgoto_pct", r"esgoto|coleta"),
    ("sem_agua_pct", r"\bagua|abastec"),
]
NOME_ASSUNTO = {
    "meta": "metas de 2033", "prioridade": "prioridade de investimento", "obitos_vh": "óbitos",
    "internacoes_10mil": "internações (saúde)", "esgoto_tratado_pct": "tratamento de esgoto",
    "sem_esgoto_pct": "coleta de esgoto", "sem_agua_pct": "acesso à água",
}

NOME_UF_ITENS = list(NOMES_UF.items())
RE_SIGLA = re.compile(r"\b(" + "|".join(SIGLAS) + r")\b")
RE_PARA = re.compile(r"\bpará\b", re.IGNORECASE)
RE_ANO = re.compile(r"\b(20[0-3][0-9])\b")
RE_PRIMEIRO = re.compile(r"primeir[oa]\s+(estado|uf)|primeir[oa]\s+que\s+(eu\s+)?pergunt|in[ií]cio da conversa")
RE_COMPARAR = re.compile(r"anterior|compar|diferen|os dois|as duas|ambos|entre el[ae]s")
# palavras de comparação ("qual" sozinho não conta: "qual a parcela no Pará?" não pede ranking)
RE_RANKING = re.compile(r"\bquais\b|maior|menor|pior|melhor|\bmais\b|\bmenos\b|ranking|lider")


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def extrair(texto):
    """Encontra UFs (na ordem em que aparecem), regiões, assuntos e ano num texto."""
    achados = []                      # (posição, sigla)
    base = sem_acento(texto)
    mascara = list(base)

    # nomes mais longos primeiro: "mato grosso do sul" antes de "mato grosso"
    nomes = sorted(((n, s) for s, lista in NOME_UF_ITENS for n in lista), key=lambda par: -len(par[0]))
    for nome, sigla in nomes:
        for m in re.finditer(r"\b" + re.escape(nome) + r"\b", "".join(mascara)):
            achados.append((m.start(), sigla))
            mascara[m.start():m.end()] = "#" * (m.end() - m.start())
    for m in RE_PARA.finditer(texto):
        achados.append((m.start(), "PA"))
        mascara[m.start():m.end()] = "#" * (m.end() - m.start())
    for m in RE_SIGLA.finditer(texto):
        achados.append((m.start(), m.group(1)))

    ufs = list(dict.fromkeys(s for _, s in sorted(achados)))
    restante = "".join(mascara)       # sem os nomes de UF: "Rio Grande do Sul" não vira região Sul
    regioes = [r for r in REGIOES
               if re.search(r"\b" + sem_acento(r).replace("-", "[- ]") + r"\b", restante)]
    assuntos = [nome for nome, padrao in ASSUNTOS if re.search(padrao, base)]
    anos = [int(a) for a in RE_ANO.findall(texto) if 2010 <= int(a) <= 2024]
    return {"ufs": ufs, "regioes": regioes, "assuntos": assuntos, "ano": anos[-1] if anos else None}


def notas_vazias():
    return {"ufs_citadas": [], "ufs_resposta": [], "assunto": None, "regiao": None, "ano": None}


def atualizar_notas(notas, pergunta, resposta):
    """Anota o que apareceu na pergunta e na resposta. Não chama o modelo."""
    notas = {**notas_vazias(), **(notas or {})}
    da_pergunta = extrair(pergunta)
    da_resposta = extrair(resposta or "")
    citadas = list(notas["ufs_citadas"])
    for sigla in da_pergunta["ufs"]:
        if sigla not in citadas:
            citadas.append(sigla)
    return {
        "ufs_citadas": citadas[-8:],
        "ufs_resposta": da_resposta["ufs"][:5],
        "assunto": (da_pergunta["assuntos"] or [notas["assunto"]])[0],
        "regiao": (da_pergunta["regioes"] or [notas["regiao"]])[0],
        "ano": da_pergunta["ano"] or notas["ano"],
    }


def texto_das_notas(notas):
    if not notas or not any(notas.values()):
        return ""
    partes = []
    if notas.get("ufs_citadas"):
        lista = ", ".join(f"{i}º {NOME_OFICIAL[s]} ({s})" for i, s in enumerate(notas["ufs_citadas"], start=1))
        partes.append(f"UFs que a pessoa perguntou, na ordem: {lista}.")
    if notas.get("ufs_resposta"):
        partes.append("UFs citadas na última resposta, na ordem: "
                      + ", ".join(f"{NOME_OFICIAL[s]} ({s})" for s in notas["ufs_resposta"]) + ".")
    if notas.get("assunto"):
        partes.append(f"Assunto da última pergunta: {NOME_ASSUNTO.get(notas['assunto'], notas['assunto'])}.")
    if notas.get("regiao"):
        partes.append(f"Região citada: {notas['regiao']}.")
    if notas.get("ano"):
        partes.append(f"Ano citado: {notas['ano']}.")
    return "Notas da conversa (anotadas pelo painel): " + " ".join(partes)


def ufs_em_foco(pergunta, notas, limite=3):
    """
    Quais UFs precisam de ficha nesta pergunta: as da própria pergunta; se não tiver
    nenhuma, a da pergunta anterior ou a primeira da última resposta ("e por que ela?");
    se a pessoa voltar ao começo ("o primeiro estado que perguntei"), a primeira anotada.
    """
    notas = notas or notas_vazias()
    achados = extrair(pergunta)
    base = sem_acento(pergunta)
    foco = list(achados["ufs"])
    citadas, resposta = notas.get("ufs_citadas", []), notas.get("ufs_resposta", [])
    if RE_PRIMEIRO.search(base) and citadas:
        foco.insert(0, citadas[0])
    if not foco:
        # uma só: a UF da última resposta ou, se ela não citou nenhuma, a última perguntada.
        # Mandar as duas (1ª rodada da avaliação) aumentava o pedido e confundia o modelo.
        if resposta:
            foco.append(resposta[0])
        elif citadas:
            foco.append(citadas[-1])
    if RE_COMPARAR.search(base):
        foco.extend(reversed(citadas[-2:]))
    return list(dict.fromkeys(foco))[:limite]


def historico_para_envio(historico, estrategia, janela=JANELA_PADRAO):
    """Quais mensagens antigas vão para o modelo junto com a pergunta atual."""
    historico = [m for m in (historico or []) if m.get("role") in ("user", "assistant")]
    if estrategia == "sem_memoria":
        return []
    if estrategia == "completa":
        return historico
    return historico[-2 * janela:] if janela > 0 else []
