"""
Análise que responde à pergunta do projeto: em quais UFs o investimento em água e
esgoto deveria chegar primeiro, olhando cobertura atual, evolução desde 2010 e saúde.

Tudo aqui é conta feita no Python, sem modelo de linguagem. Os números que o
assistente do painel usa nas respostas saem daqui já prontos: o modelo só escreve
o texto (ver src/assistente.py).

- tendência: inclinação da reta (mínimos quadrados) de 2010 a 2024, em pontos
  percentuais por ano; olha a série inteira e não só o primeiro e o último ano;
- meta: Marco Legal do Saneamento (Lei 14.026/2020) - 99% da população com água e
  90% com coleta de esgoto até 2033; projeto em que ano cada UF chega lá no ritmo atual;
- índice de prioridade (0 a 100): junta cobertura, ritmo até a meta e saúde.
"""
import math

from src import dados

ANO_BASE = 2024
META_ANO = 2033
META_SEM_AGUA = 1.0      # 99% com água  -> no máximo 1% sem
META_SEM_ESGOTO = 10.0   # 90% com coleta -> no máximo 10% sem
LIMITE_ANOS = 100        # "mais de 100 anos" já é o mesmo que "não chega" para a decisão
SALTO_SUSPEITO = 10.0    # variação de um ano para o outro acima disso (p.p.) é marcada como quebra na série

PESOS_PADRAO = {"cobertura": 1 / 3, "ritmo": 1 / 3, "saude": 1 / 3}

COMPONENTES = {
    "cobertura": "Cobertura atual: parcela sem água e sem coleta de esgoto em 2024",
    "ritmo": "Ritmo até a meta de 2033: anos que faltam no ritmo de 2010-2024",
    "saude": "Saúde: internações por doenças de veiculação hídrica a cada 10 mil habitantes",
}


def tendencia(pontos):
    """[(ano, valor), ...] -> inclinação em p.p. por ano (negativa = melhora, porque é % SEM serviço)."""
    pontos = [(a, v) for a, v in pontos if v is not None]
    if len(pontos) < 3:
        return None
    n = len(pontos)
    media_x = sum(a for a, _ in pontos) / n
    media_y = sum(v for _, v in pontos) / n
    cima = sum((a - media_x) * (v - media_y) for a, v in pontos)
    baixo = sum((a - media_x) ** 2 for a, _ in pontos)
    return cima / baixo


def ano_da_meta(valor_atual, inclinacao, meta):
    """
    Em que ano a UF chega à meta mantendo o ritmo. Devolve (ano, situacao):
    - (2024, "cumpre") se já está dentro da meta;
    - (ano, "no_prazo" ou "atrasada") se chega até / depois de 2033;
    - (None, "nao_chega") se está parada, piorando ou levaria mais de 100 anos.
    """
    if valor_atual is None or inclinacao is None:
        return None, "sem_dado"
    if valor_atual <= meta:
        return ANO_BASE, "cumpre"
    if inclinacao >= 0:
        return None, "nao_chega"
    anos = (valor_atual - meta) / -inclinacao
    if anos > LIMITE_ANOS:
        return None, "nao_chega"
    ano = ANO_BASE + math.ceil(anos)
    return ano, "no_prazo" if ano <= META_ANO else "atrasada"


def quebras_na_serie(pontos):
    """Anos em que o valor saltou mais de SALTO_SUSPEITO p.p. em relação ao ano anterior."""
    ordenados = sorted((a, v) for a, v in pontos if v is not None)
    return [a2 for (a1, v1), (a2, v2) in zip(ordenados, ordenados[1:]) if abs(v2 - v1) > SALTO_SUSPEITO]


def _normalizar(valores):
    """Min-max entre as UFs: 0 = melhor situação, 1 = pior. Valor ausente vira None."""
    validos = [v for v in valores.values() if v is not None]
    menor, maior = min(validos), max(validos)
    faixa = (maior - menor) or 1
    return {k: (None if v is None else (v - menor) / faixa) for k, v in valores.items()}


def _anos_para_indice(ano, situacao):
    """Converte a projeção em 'anos que faltam' para entrar no índice (cumpre = 0, não chega = 100)."""
    if situacao == "cumpre":
        return 0
    if situacao == "nao_chega":
        return LIMITE_ANOS
    if ano is None:
        return None
    return ano - ANO_BASE


def perfis_das_ufs(saneamento=None, serie=None):
    """Um dicionário por UF com os indicadores de 2024, os de 2010, a tendência e a projeção da meta."""
    saneamento = saneamento if saneamento is not None else dados.carregar_saneamento()
    serie = serie if serie is not None else dados.carregar_serie()

    por_uf = {}
    for p in serie:
        por_uf.setdefault(p["sigla"], {}).setdefault(p["indicador"], []).append((p["ano"], p["valor"]))

    perfis = {}
    for linha in saneamento:
        sigla = linha["sigla"]
        pontos = por_uf.get(sigla, {})
        agua, esgoto, incid = pontos.get("POP_SEM_AG%", []), pontos.get("POP_SEM_ES%", []), pontos.get("INCIDE_VH", [])
        inc_agua, inc_esgoto = tendencia(agua), tendencia(esgoto)
        ano_agua, sit_agua = ano_da_meta(linha["sem_agua_pct"], inc_agua, META_SEM_AGUA)
        ano_esgoto, sit_esgoto = ano_da_meta(linha["sem_esgoto_pct"], inc_esgoto, META_SEM_ESGOTO)
        perfis[sigla] = {
            **linha,
            "serie": {"POP_SEM_AG%": dict(agua), "POP_SEM_ES%": dict(esgoto), "INCIDE_VH": dict(incid)},
            "sem_agua_2010": dict(agua).get(2010),
            "sem_esgoto_2010": dict(esgoto).get(2010),
            "internacoes_10mil_2010": dict(incid).get(2010),
            "tendencia_agua": inc_agua,
            "tendencia_esgoto": inc_esgoto,
            "tendencia_internacoes": tendencia(incid),
            "meta_agua_ano": ano_agua, "meta_agua_situacao": sit_agua,
            "meta_esgoto_ano": ano_esgoto, "meta_esgoto_situacao": sit_esgoto,
            "quebras": sorted(set(quebras_na_serie(agua) + quebras_na_serie(esgoto))),
        }
    return perfis


def indice_prioridade(perfis, pesos=None):
    """
    Índice de 0 a 100 (maior = deveria receber investimento antes). Cada componente é
    normalizado entre as 27 UFs (0 = melhor, 1 = pior) e entra com o seu peso.
    Devolve a lista ordenada da maior para a menor prioridade, já com a posição.
    """
    pesos = pesos or PESOS_PADRAO
    soma = sum(pesos.values()) or 1
    pesos = {k: v / soma for k, v in pesos.items()}

    sem_agua = _normalizar({s: p["sem_agua_pct"] for s, p in perfis.items()})
    sem_esgoto = _normalizar({s: p["sem_esgoto_pct"] for s, p in perfis.items()})
    anos_agua = _normalizar({s: _anos_para_indice(p["meta_agua_ano"], p["meta_agua_situacao"]) for s, p in perfis.items()})
    anos_esgoto = _normalizar({s: _anos_para_indice(p["meta_esgoto_ano"], p["meta_esgoto_situacao"]) for s, p in perfis.items()})
    saude = _normalizar({s: p["internacoes_10mil"] for s, p in perfis.items()})

    def media(*valores):
        validos = [v for v in valores if v is not None]
        return sum(validos) / len(validos) if validos else 0

    linhas = []
    for sigla, p in perfis.items():
        componentes = {
            "cobertura": media(sem_agua[sigla], sem_esgoto[sigla]),
            "ritmo": media(anos_agua[sigla], anos_esgoto[sigla]),
            "saude": saude[sigla] or 0,
        }
        indice = 100 * sum(pesos[k] * componentes[k] for k in pesos)
        linhas.append({"sigla": sigla, "uf_nome": p["uf_nome"], "regiao": p["regiao"],
                       "indice": round(indice, 1),
                       **{f"comp_{k}": round(100 * v, 1) for k, v in componentes.items()}})
    linhas.sort(key=lambda l: -l["indice"])
    for posicao, linha in enumerate(linhas, start=1):
        linha["posicao"] = posicao
    return linhas


def posicoes(perfis, chave, pior_quando_maior=True):
    """Posição de cada UF num indicador (1 = pior situação)."""
    validos = [(s, p[chave]) for s, p in perfis.items() if p.get(chave) is not None]
    ordenados = sorted(validos, key=lambda par: par[1], reverse=pior_quando_maior)
    return {s: i for i, (s, _) in enumerate(ordenados, start=1)}


def resumo_regioes(perfis):
    """Média simples das UFs de cada região (mesma regra das médias do painel)."""
    regioes = {}
    for p in perfis.values():
        regioes.setdefault(p["regiao"], []).append(p)
    resumo = []
    for nome in dados.REGIOES:
        ufs = regioes.get(nome, [])
        if not ufs:
            continue

        def media(chave):
            valores = [u[chave] for u in ufs if u.get(chave) is not None]
            return sum(valores) / len(valores) if valores else None

        resumo.append({
            "regiao": nome, "ufs": sorted(u["sigla"] for u in ufs),
            "sem_agua_pct": media("sem_agua_pct"), "sem_esgoto_pct": media("sem_esgoto_pct"),
            "esgoto_tratado_pct": media("esgoto_tratado_pct"), "internacoes_10mil": media("internacoes_10mil"),
            "sem_agua_2010": media("sem_agua_2010"), "sem_esgoto_2010": media("sem_esgoto_2010"),
            "pessoas_sem_agua": sum(u["pessoas_sem_agua"] or 0 for u in ufs),
        })
    return resumo


def resumo_brasil(perfis):
    total_pop = sum(p["populacao"] or 0 for p in perfis.values())
    sem_agua = sum(p["pessoas_sem_agua"] or 0 for p in perfis.values())
    n = len(perfis)
    return {
        "ufs": n,
        "populacao": total_pop,
        "pessoas_sem_agua": sem_agua,
        "sem_agua_pct_pop": 100 * sem_agua / total_pop if total_pop else None,
        "media_sem_esgoto": sum(p["sem_esgoto_pct"] for p in perfis.values()) / n,
        "media_sem_agua": sum(p["sem_agua_pct"] for p in perfis.values()) / n,
        "media_sem_esgoto_2010": sum(p["sem_esgoto_2010"] or 0 for p in perfis.values()) / n,
        "media_sem_agua_2010": sum(p["sem_agua_2010"] or 0 for p in perfis.values()) / n,
        "chegam_meta_agua": sum(1 for p in perfis.values() if p["meta_agua_situacao"] in ("cumpre", "no_prazo")),
        "chegam_meta_esgoto": sum(1 for p in perfis.values() if p["meta_esgoto_situacao"] in ("cumpre", "no_prazo")),
    }
