"""
Fatos em texto para o assistente do painel.

O modelo de linguagem não recebe a tabela crua: recebe frases curtas com os números
já calculados (src/analise.py). Assim ele não precisa fazer conta, que é onde modelo
pequeno mais erra, e o pedido fica menor.

Como são 27 UFs x 15 anos x vários indicadores, não cabe tudo em cada pergunta.
O assistente escolhe os blocos que interessam (src/assistente.py):
- bloco_brasil: sempre vai (visão geral + as 5 UFs prioritárias);
- ficha_uf: só das UFs da pergunta e das que estão nas notas da conversa;
- bloco_ranking: quando a pergunta pede "maior", "pior", "quais UFs"...;
- bloco_regioes: quando a pergunta fala de região.
"""
from src import analise, dados

NOMES_ASSUNTO = {
    "sem_agua_pct": "parcela da população sem acesso à água",
    "sem_esgoto_pct": "parcela da população sem coleta de esgoto",
    "esgoto_tratado_pct": "esgoto tratado em relação à água consumida",
    "internacoes_10mil": "internações por doenças de veiculação hídrica a cada 10 mil habitantes",
    "obitos_vh": "óbitos por doenças de veiculação hídrica",
    "pessoas_sem_agua": "pessoas sem acesso à água",
}
UNIDADE = {"sem_agua_pct": "%", "sem_esgoto_pct": "%", "esgoto_tratado_pct": "%",
           "internacoes_10mil": "", "obitos_vh": "", "pessoas_sem_agua": ""}
CASAS = {"obitos_vh": 0, "pessoas_sem_agua": 0}


def fmt(valor, casas=1, sufixo=""):
    if valor is None:
        return "sem dado"
    texto = f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return texto + sufixo


def fmt_pessoas(valor):
    if valor is None:
        return "sem dado"
    if valor >= 1_000_000:
        return f"{fmt(valor / 1_000_000)} milhões de pessoas"
    return f"{fmt(valor / 1000, 0)} mil pessoas"


def frase_ritmo(inclinacao):
    """Inclinação em p.p./ano -> frase. Lembrando: o indicador é % SEM o serviço, então cair é bom."""
    if inclinacao is None:
        return "sem série suficiente"
    if abs(inclinacao) < 0.05:
        return "praticamente parada"
    if inclinacao < 0:
        return f"cai {fmt(-inclinacao, 2)} ponto percentual por ano (melhora)"
    return f"sobe {fmt(inclinacao, 2)} ponto percentual por ano (piora)"


def frase_meta(ano, situacao):
    if situacao == "cumpre":
        return "já cumpre a meta"
    if situacao == "nao_chega":
        return "no ritmo atual não chega à meta (levaria mais de 100 anos ou está piorando)"
    if situacao == "sem_dado":
        return "sem dado para projetar"
    if situacao == "no_prazo":
        return f"chega à meta em {ano}, dentro do prazo de 2033"
    return f"só chega à meta em {ano}, depois do prazo de 2033"


class BaseDeFatos:
    """Carrega os dados uma vez e monta os blocos de texto que vão para o modelo."""

    def __init__(self, perfis=None):
        self.perfis = perfis or analise.perfis_das_ufs()
        self.prioridade = analise.indice_prioridade(self.perfis)
        self.pos_prioridade = {l["sigla"]: l for l in self.prioridade}
        self.brasil = analise.resumo_brasil(self.perfis)
        self.regioes = analise.resumo_regioes(self.perfis)
        self.posicoes = {
            chave: analise.posicoes(self.perfis, chave, pior_quando_maior=chave != "esgoto_tratado_pct")
            for chave in NOMES_ASSUNTO
        }
        self.ano = next(iter(self.perfis.values()))["ano"]

    # ------------------------------------------------------------------ blocos
    def bloco_brasil(self):
        b = self.brasil
        top = "; ".join(
            f"{l['posicao']}º {l['uf_nome']} ({l['sigla']}) {fmt(l['indice'])}" for l in self.prioridade[:5]
        )
        ultimo = self.prioridade[-1]
        return (
            f"Fonte: Painel Saneamento Brasil (Instituto Trata Brasil), dados de {self.ano}, e população do IBGE. "
            f"Brasil em {self.ano}: {fmt_pessoas(b['pessoas_sem_agua'])} sem acesso à água "
            f"({fmt(b['sem_agua_pct_pop'], 1, '%')} da população). "
            f"Média das 27 UFs: {fmt(b['media_sem_agua'], 1, '%')} sem água (em 2010 eram {fmt(b['media_sem_agua_2010'], 1, '%')}) "
            f"e {fmt(b['media_sem_esgoto'], 1, '%')} sem coleta de esgoto (em 2010 eram {fmt(b['media_sem_esgoto_2010'], 1, '%')}).\n"
            f"Meta do Marco Legal do Saneamento para 2033: 99% da população com água e 90% com coleta de esgoto. "
            f"No ritmo de 2010 a 2024, só {b['chegam_meta_agua']} das 27 UFs chegam à meta de água até 2033 "
            f"e só {b['chegam_meta_esgoto']} chegam à de esgoto.\n"
            f"Índice de prioridade para investimento (0 a 100; junta cobertura atual, ritmo até a meta e internações, "
            f"com pesos iguais): {top}. Menor prioridade: {ultimo['uf_nome']} ({ultimo['sigla']}) {fmt(ultimo['indice'])}."
        )

    def ficha_uf(self, sigla, ano=None):
        # um indicador por linha, com 2010 e 2024 lado a lado: quando os anos ficavam em frases
        # separadas, o modelo pequeno às vezes trocava o número de um ano pelo do outro
        p = self.perfis[sigla]
        pr = self.pos_prioridade[sigla]
        pos = {chave: self.posicoes[chave].get(sigla) for chave in self.posicoes}
        a = p["ano"]
        texto = (
            f"{p['uf_nome']} ({sigla}), região {p['regiao']}. "
            f"Prioridade para investimento: {pr['posicao']}º de 27 (índice {fmt(pr['indice'])} de 100).\n"
            f"- Sem acesso à água: {fmt(p['sem_agua_pct'], 1, '%')} da população em {a} ({pos['sem_agua_pct']}º pior de 27; "
            f"{fmt_pessoas(p['pessoas_sem_agua'])}); era {fmt(p['sem_agua_2010'], 1, '%')} em 2010; "
            f"{frase_ritmo(p['tendencia_agua'])}; meta de 2033: {frase_meta(p['meta_agua_ano'], p['meta_agua_situacao'])}.\n"
            f"- Sem coleta de esgoto: {fmt(p['sem_esgoto_pct'], 1, '%')} da população em {a} ({pos['sem_esgoto_pct']}º pior); "
            f"era {fmt(p['sem_esgoto_2010'], 1, '%')} em 2010; {frase_ritmo(p['tendencia_esgoto'])}; "
            f"meta de 2033: {frase_meta(p['meta_esgoto_ano'], p['meta_esgoto_situacao'])}.\n"
            f"- Esgoto tratado: {fmt(p['esgoto_tratado_pct'], 1, '%')} em {a} ({pos['esgoto_tratado_pct']}º pior).\n"
            f"- Saúde (internações por doenças de veiculação hídrica): {fmt(p['internacoes_10mil'])} a cada 10 mil habitantes "
            f"em {a} ({pos['internacoes_10mil']}º pior); eram {fmt(p['internacoes_10mil_2010'])} em 2010. "
            f"Óbitos por essas doenças em {a}: {fmt(p['obitos_vh'], 0)}."
        )
        motivos = self.motivos(sigla)
        if motivos:
            texto += f"\nPor que está nessa posição de prioridade: {'; '.join(motivos)}."
        if ano and ano not in (2010, p["ano"]) and 2010 <= ano <= 2024:
            s = p["serie"]
            texto += (
                f"\n- Em {ano}: {fmt(s['POP_SEM_AG%'].get(ano), 1, '%')} sem água, "
                f"{fmt(s['POP_SEM_ES%'].get(ano), 1, '%')} sem esgoto e "
                f"{fmt(s['INCIDE_VH'].get(ano))} internações a cada 10 mil habitantes."
            )
        if p["quebras"]:
            anos = ", ".join(str(a) for a in p["quebras"])
            texto += f"\nAtenção: a série tem salto de mais de 10 pontos em {anos}, que pode ser mudança na base da fonte."
        return texto

    def motivos(self, sigla):
        """
        Por que a UF está onde está no índice, em frases curtas. É regra fixa no Python:
        pontos em que ela está entre as 5 piores do país e a situação das metas.
        """
        p = self.perfis[sigla]
        motivos = []
        destaques = [("internacoes_10mil", "internações por doenças de veiculação hídrica", "", " a cada 10 mil hab."),
                     ("sem_agua_pct", "parcela sem água", "%", ""),
                     ("sem_esgoto_pct", "parcela sem coleta de esgoto", "%", "")]
        for chave, nome, unidade, extra in destaques:
            posicao = self.posicoes[chave].get(sigla)
            if posicao and posicao <= 5:
                motivos.append(f"{posicao}º pior do país em {nome} ({fmt(p[chave], 1, unidade)}{extra})")
        if p["tendencia_agua"] is not None and p["tendencia_agua"] >= 0.05:
            motivos.append("o acesso à água piorou de 2010 a 2024")
        situacoes = (p["meta_agua_situacao"], p["meta_esgoto_situacao"])
        if situacoes == ("nao_chega", "nao_chega"):
            motivos.append("não chega a nenhuma das duas metas de 2033 no ritmo atual")
        elif "nao_chega" in situacoes:
            qual = "água" if situacoes[0] == "nao_chega" else "esgoto"
            motivos.append(f"não chega à meta de {qual} no ritmo atual")
        if not motivos and self.pos_prioridade[sigla]["posicao"] > 20:
            motivos.append("cobertura e ritmo melhores que a maioria das UFs")
        return motivos

    def bloco_ranking(self, assunto, quantidade=5):
        if assunto == "prioridade":
            itens = "; ".join(f"{l['posicao']}º {l['uf_nome']} ({l['sigla']}) {fmt(l['indice'])}"
                              for l in self.prioridade[:quantidade])
            fim = "; ".join(f"{l['sigla']} {fmt(l['indice'])}" for l in self.prioridade[-3:])
            return f"Ranking do índice de prioridade: {itens}. As 3 de menor prioridade: {fim}."
        if assunto == "meta":
            no_prazo_agua = [s for s, p in self.perfis.items() if p["meta_agua_situacao"] in ("cumpre", "no_prazo")]
            no_prazo_esgoto = [s for s, p in self.perfis.items() if p["meta_esgoto_situacao"] in ("cumpre", "no_prazo")]
            nao_chegam = [s for s, p in self.perfis.items()
                          if p["meta_agua_situacao"] == "nao_chega" and p["meta_esgoto_situacao"] == "nao_chega"]
            return (
                f"UFs que chegam à meta de água até 2033 no ritmo atual: {', '.join(sorted(no_prazo_agua)) or 'nenhuma'}. "
                f"UFs que chegam à meta de esgoto até 2033: {', '.join(sorted(no_prazo_esgoto)) or 'nenhuma'}. "
                f"UFs que não chegam a nenhuma das duas metas no ritmo atual: {', '.join(sorted(nao_chegam))}."
            )
        if assunto not in NOMES_ASSUNTO:
            return ""
        pior_primeiro = assunto != "esgoto_tratado_pct"
        validos = [(s, p[assunto]) for s, p in self.perfis.items() if p.get(assunto) is not None]
        ordenados = sorted(validos, key=lambda par: par[1], reverse=pior_primeiro)
        casas, unidade = CASAS.get(assunto, 1), UNIDADE[assunto]
        piores = "; ".join(f"{i}º {self.perfis[s]['uf_nome']} ({s}) {fmt(v, casas, unidade)}"
                           for i, (s, v) in enumerate(ordenados[:quantidade], start=1))
        melhores = "; ".join(f"{self.perfis[s]['uf_nome']} ({s}) {fmt(v, casas, unidade)}" for s, v in ordenados[-3:][::-1])
        return f"Piores em {NOMES_ASSUNTO[assunto]} ({self.ano}): {piores}. As 3 melhores: {melhores}."

    def bloco_regioes(self, regiao=None):
        linhas = sorted(self.regioes, key=lambda r: -r["sem_esgoto_pct"])
        comparacao = "; ".join(
            f"{r['regiao']} {fmt(r['sem_agua_pct'], 1, '%')} sem água e {fmt(r['sem_esgoto_pct'], 1, '%')} sem esgoto"
            for r in linhas
        )
        texto = f"Média das UFs de cada região em {self.ano} (da pior para a melhor em esgoto): {comparacao}."
        if regiao:
            r = next((x for x in self.regioes if x["regiao"] == regiao), None)
            if r:
                da_regiao = [l for l in self.prioridade if l["regiao"] == regiao]
                ordem = ", ".join(f"{l['sigla']} ({l['posicao']}º)" for l in da_regiao)
                texto += (
                    f"\nRegião {regiao} ({', '.join(r['ufs'])}): em 2010 a média era {fmt(r['sem_agua_2010'], 1, '%')} sem água "
                    f"e {fmt(r['sem_esgoto_2010'], 1, '%')} sem esgoto; hoje {fmt_pessoas(r['pessoas_sem_agua'])} sem água; "
                    f"{fmt(r['internacoes_10mil'])} internações a cada 10 mil habitantes (média). "
                    f"UFs da região na ordem de prioridade nacional: {ordem}."
                )
        return texto

    # ------------------------------------------------------------------ para comparação
    def tabela_crua(self):
        """
        A tabela como ela é (sem nada calculado), no formato CSV. Uso só para comparar com
        os fatos na avaliação (src/avaliar_memoria.py): é o que o modelo receberia se eu
        mandasse os dados "do jeito que estão".
        """
        colunas = ["sigla", "uf_nome", "regiao", "sem_agua_pct", "sem_esgoto_pct", "esgoto_tratado_pct",
                   "internacoes_vh", "obitos_vh", "populacao"]
        linhas = [",".join(colunas) + ",sem_agua_2010,sem_esgoto_2010"]
        for s in sorted(self.perfis):
            p = self.perfis[s]
            valores = [str(p[c]) for c in colunas] + [str(p["sem_agua_2010"]), str(p["sem_esgoto_2010"])]
            linhas.append(",".join(valores))
        return (f"Dados de {self.ano} por UF (Painel Saneamento Brasil e IBGE). Meta de 2033: 99% com água e 90% com "
                "coleta de esgoto.\n" + "\n".join(linhas))

    def nome_uf(self, sigla):
        return self.perfis[sigla]["uf_nome"]

    def siglas(self):
        return list(dados.SIGLAS)
