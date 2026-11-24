"""
Preparação dos dados para a próxima etapa (uso de LLM).

Aqui ainda não chamo nenhum modelo. O que faço é deixar os dados no formato que
um LLM consome bem: textos curtos, em português, com a fonte junto, um por linha
num arquivo JSONL (data/processed/corpus_llm.jsonl).

Três tipos de documento:
- ficha da UF: os números do painel escritos em frases (para perguntas e respostas
  e para gerar relatórios);
- notícia: título, resumo e texto (para resumo automático e classificação de sentimento);
- observação: o que os usuários mandaram pelo POST da API (contexto de campo).

Rodar a partir da raiz do projeto:
    python -m src.preparo_llm
"""
import json
from pathlib import Path

from src import dados

ARQ_CORPUS = dados.PROCESSADOS / "corpus_llm.jsonl"

# modelos de pedido que pretendo usar na próxima etapa
PROMPTS_PLANEJADOS = {
    "resumo_noticia": (
        "Resuma a notícia abaixo em até 3 frases, em português simples, destacando "
        "o que ela tem a ver com água, esgoto ou saúde. Se não tiver relação, diga isso.\n\n{texto}"
    ),
    "sentimento_noticia": (
        "Classifique o tom da notícia em relação ao saneamento como POSITIVO, NEGATIVO ou NEUTRO "
        "e explique em uma frase. Responda em JSON com as chaves 'sentimento' e 'motivo'.\n\n{texto}"
    ),
    "pergunta_resposta": (
        "Use somente as fichas abaixo para responder. Se a resposta não estiver nelas, diga que não sabe. "
        "Diga a UF e o ano de cada número.\n\nFichas:\n{contexto}\n\nPergunta: {pergunta}"
    ),
    "relatorio_prioridades": (
        "Com base nas fichas abaixo, escreva um parágrafo para um gestor público explicando quais "
        "3 UFs deveriam receber investimento em saneamento primeiro e por quê.\n\n{contexto}"
    ),
}


def estimar_tokens(texto):
    """Conta aproximada (cerca de 4 caracteres por token) só para planejar custo e tamanho."""
    return max(1, len(texto) // 4)


def _fmt(valor, sufixo="", casas=1):
    if valor is None:
        return "sem dado"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".") + sufixo


def ficha_uf(linha, serie_uf):
    pontos = {(p["indicador"], p["ano"]): p["valor"] for p in serie_uf}
    agua_2010, agua_2024 = pontos.get(("POP_SEM_AG%", 2010)), pontos.get(("POP_SEM_AG%", 2024))
    esgoto_2010, esgoto_2024 = pontos.get(("POP_SEM_ES%", 2010)), pontos.get(("POP_SEM_ES%", 2024))
    return (
        f"{linha['uf_nome']} ({linha['sigla']}), região {linha['regiao']}. "
        f"Em {linha['ano']}, {_fmt(linha['sem_agua_pct'], '%')} da população não tinha acesso à água "
        f"(cerca de {_fmt((linha['pessoas_sem_agua'] or 0) / 1000)} mil pessoas) e "
        f"{_fmt(linha['sem_esgoto_pct'], '%')} não tinha coleta de esgoto. "
        f"Só {_fmt(linha['esgoto_tratado_pct'], '%')} do esgoto era tratado em relação à água consumida. "
        f"Foram {_fmt(linha['internacoes_vh'], casas=0)} internações e {_fmt(linha['obitos_vh'], casas=0)} óbitos por doenças "
        f"de veiculação hídrica ({_fmt(linha['internacoes_10mil'])} internações a cada 10 mil habitantes). "
        f"Entre 2010 e 2024, a parcela sem água foi de {_fmt(agua_2010, '%')} para {_fmt(agua_2024, '%')} "
        f"e a parcela sem esgoto foi de {_fmt(esgoto_2010, '%')} para {_fmt(esgoto_2024, '%')}. "
        f"Fonte: Painel Saneamento Brasil (Instituto Trata Brasil) e IBGE."
    )


def montar_corpus():
    serie = dados.carregar_serie()
    documentos = []

    for linha in dados.carregar_saneamento():
        texto = ficha_uf(linha, [p for p in serie if p["sigla"] == linha["sigla"]])
        documentos.append({"id": f"uf-{linha['sigla']}", "tipo": "ficha_uf", "sigla": linha["sigla"],
                           "texto": texto, "tokens_aprox": estimar_tokens(texto)})

    for i, n in enumerate(dados.carregar_noticias(), start=1):
        texto = f"{n['titulo']}. {n['resumo']} {n['texto']}".strip()
        documentos.append({"id": f"noticia-{i}", "tipo": "noticia", "secao": n["secao"],
                           "tema_ods6": n["tema_ods6"], "url": n["url"], "publicado_em": n["publicado_em"],
                           "texto": texto, "tokens_aprox": estimar_tokens(texto)})

    for o in dados.ler_observacoes():
        texto = f"Observação ({o['tipo']}) sobre {o['sigla']}, enviada em {o['enviado_em']}: {o['texto']}"
        documentos.append({"id": f"obs-{o['id']}", "tipo": "observacao", "sigla": o["sigla"],
                           "texto": texto, "tokens_aprox": estimar_tokens(texto)})
    return documentos


def salvar_corpus(documentos):
    with open(ARQ_CORPUS, "w", encoding="utf-8") as arquivo:
        for doc in documentos:
            arquivo.write(json.dumps(doc, ensure_ascii=False) + "\n")
    return ARQ_CORPUS


if __name__ == "__main__":
    docs = montar_corpus()
    caminho = salvar_corpus(docs)
    total = sum(d["tokens_aprox"] for d in docs)
    print(f"{len(docs)} documentos ({total} tokens aproximados) gravados em {caminho}")
