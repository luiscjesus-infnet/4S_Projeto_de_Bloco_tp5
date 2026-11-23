"""
Camada de leitura dos dados processados (pasta data/processed).

Tanto o painel Streamlit quanto a API FastAPI usam estas funções. Assim os dois
leem exatamente os mesmos arquivos e a regra de negócio fica num lugar só.
Uso só listas e dicionários do Python; não precisei de pandas aqui.
"""
import csv
import json
import threading
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROCESSADOS = BASE / "data" / "processed"

ARQ_SANEAMENTO = PROCESSADOS / "saneamento_uf.csv"
ARQ_SERIE = PROCESSADOS / "serie_saneamento_uf.csv"
ARQ_NOTICIAS = PROCESSADOS / "noticias.csv"
ARQ_UFS = PROCESSADOS / "ufs_ibge.json"
ARQ_OBSERVACOES = PROCESSADOS / "observacoes.csv"
_trava_observacoes = threading.Lock()

SIGLAS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]

INDICADORES = {
    "sem_agua_pct": "População sem acesso à água (%)",
    "sem_esgoto_pct": "População sem coleta de esgoto (%)",
    "esgoto_tratado_pct": "Esgoto tratado em relação à água consumida (%)",
    "internacoes_vh": "Internações por doenças de veiculação hídrica",
    "obitos_vh": "Óbitos por doenças de veiculação hídrica",
    "internacoes_10mil": "Internações por veiculação hídrica a cada 10 mil hab.",
    "pessoas_sem_agua": "Pessoas sem acesso à água (estimativa)",
    "receita_media_agua": "Receita média de água (R$/m³)",
    "renda_com_saneamento": "Renda média de quem tem saneamento (R$/mês)",
    "renda_sem_saneamento": "Renda média de quem não tem saneamento (R$/mês)",
}

# indicadores em que valor maior significa situação pior (para montar o ranking de prioridade)
PIOR_QUANDO_MAIOR = {"sem_agua_pct", "sem_esgoto_pct", "internacoes_vh", "obitos_vh",
                     "internacoes_10mil", "pessoas_sem_agua"}

INDICADORES_SERIE = {
    "POP_SEM_AG%": "População sem acesso à água (%)",
    "POP_SEM_ES%": "População sem coleta de esgoto (%)",
    "INCIDE_VH": "Incidência de internações por veiculação hídrica",
}

STOPWORDS = set("""
para pela pelo pelas pelos como mais menos sobre entre após antes desde até também
ainda quando onde porque mesmo cada todo toda todos todas este esta isso essa esse
estes essas esses aquele aquela será foram está estão sendo seja pode podem deve
devem fazer feito disse diz afirmou segundo outros outras outro outra muito muitos
apenas além durante contra brasil agência anos dois três quatro cinco ministério
governo federal nesta neste nessa nesse desta deste dessa desse qual quais seus suas
""".split())


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _numero(valor):
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def ler_csv(caminho):
    if not caminho.exists():
        return []
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def carregar_ufs():
    if not ARQ_UFS.exists():
        return []
    return json.loads(ARQ_UFS.read_text(encoding="utf-8"))


def _indice_ufs(ufs):
    return {_sem_acento(u["uf_nome"]): u for u in ufs}


def carregar_saneamento(ufs=None):
    """Indicadores do ano mais recente por UF, já com sigla, região e população do IBGE."""
    indice = _indice_ufs(ufs if ufs is not None else carregar_ufs())
    linhas = []
    for linha in ler_csv(ARQ_SANEAMENTO):
        uf = indice.get(_sem_acento(linha["uf_nome"]), {})
        registro = {
            "sigla": uf.get("sigla", ""),
            "uf_nome": linha["uf_nome"],
            "regiao": uf.get("regiao", ""),
            "ano": int(linha["ano"]) if linha["ano"] else None,
            "populacao": uf.get("populacao"),
        }
        for chave in ("sem_agua_pct", "sem_esgoto_pct", "receita_media_agua", "esgoto_tratado_pct",
                      "internacoes_vh", "obitos_vh", "renda_com_saneamento", "renda_sem_saneamento"):
            registro[chave] = _numero(linha.get(chave))

        pop = registro["populacao"]
        registro["pessoas_sem_agua"] = (
            round(pop * registro["sem_agua_pct"] / 100) if pop and registro["sem_agua_pct"] is not None else None
        )
        registro["internacoes_10mil"] = (
            round(registro["internacoes_vh"] / pop * 10000, 2) if pop and registro["internacoes_vh"] is not None else None
        )
        linhas.append(registro)
    return linhas


def carregar_serie(ufs=None):
    indice = _indice_ufs(ufs if ufs is not None else carregar_ufs())
    serie = []
    for linha in ler_csv(ARQ_SERIE):
        uf = indice.get(_sem_acento(linha["uf_nome"]), {})
        serie.append({
            "sigla": uf.get("sigla", ""),
            "uf_nome": linha["uf_nome"],
            "regiao": uf.get("regiao", ""),
            "ano": int(linha["ano"]),
            "indicador": linha["indicador"],
            "indicador_nome": linha["indicador_nome"],
            "valor": _numero(linha["valor"]),
        })
    return serie


def carregar_noticias():
    noticias = ler_csv(ARQ_NOTICIAS)
    for n in noticias:
        n["palavras"] = int(n.get("palavras") or 0)
    return noticias


def ranking(linhas, indicador, limite=5):
    """Ordena as UFs da pior para a melhor situação no indicador escolhido."""
    validas = [l for l in linhas if l.get(indicador) is not None]
    pior_primeiro = indicador in PIOR_QUANDO_MAIOR
    return sorted(validas, key=lambda l: l[indicador], reverse=pior_primeiro)[:limite]


def filtrar_serie(serie, sigla=None, indicador=None, desde=None, ate=None):
    resultado = serie
    if sigla:
        resultado = [s for s in resultado if s["sigla"] == sigla]
    if indicador:
        resultado = [s for s in resultado if s["indicador"] == indicador]
    if desde:
        resultado = [s for s in resultado if s["ano"] >= desde]
    if ate:
        resultado = [s for s in resultado if s["ano"] <= ate]
    return sorted(resultado, key=lambda s: (s["sigla"], s["indicador"], s["ano"]))


def contar_palavras(textos, minimo_letras=4, quantidade=15):
    contagem = Counter()
    for texto in textos:
        for palavra in texto.lower().split():
            palavra = palavra.strip(".,;:!?\"'()[]“”‘’-–—")
            if len(palavra) >= minimo_letras and palavra.isalpha() and palavra not in STOPWORDS:
                contagem[palavra] += 1
    return contagem.most_common(quantidade)


def info_fontes():
    """Resumo de cada arquivo processado: origem, quantidade de linhas e data da coleta."""
    fontes = []
    for nome, caminho, tecnica in [
        ("Indicadores de saneamento por UF (ano mais recente)", ARQ_SANEAMENTO, "requests + BeautifulSoup"),
        ("Série histórica de saneamento por UF", ARQ_SERIE, "Selenium"),
        ("Notícias de meio ambiente e saúde", ARQ_NOTICIAS, "requests + BeautifulSoup"),
        ("Observações enviadas pela API", ARQ_OBSERVACOES, "POST na API do projeto"),
    ]:
        linhas = ler_csv(caminho)
        coletado = linhas[-1].get("coletado_em") or linhas[-1].get("enviado_em") if linhas else None
        fontes.append({"conjunto": nome, "arquivo": caminho.name, "tecnica": tecnica,
                       "linhas": len(linhas), "atualizado_em": coletado})
    ufs = carregar_ufs()
    fontes.append({"conjunto": "UFs, regiões e população", "arquivo": ARQ_UFS.name,
                   "tecnica": "API do IBGE", "linhas": len(ufs),
                   "atualizado_em": f"população {ufs[0]['ano_populacao']}" if ufs else None})
    return fontes


def ler_observacoes():
    return ler_csv(ARQ_OBSERVACOES)


def salvar_observacao(sigla, autor, tipo, texto):
    """
    Grava uma observação nova no fim do CSV (cria o arquivo se não existir).
    A trava evita que dois envios ao mesmo tempo recebam o mesmo id.
    """
    campos = ["id", "sigla", "autor", "tipo", "texto", "enviado_em"]
    with _trava_observacoes:
        existentes = ler_observacoes()
        registro = {
            "id": len(existentes) + 1,
            "sigla": sigla,
            "autor": autor.strip(),
            "tipo": tipo,
            "texto": texto.strip(),
            "enviado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        novo = not ARQ_OBSERVACOES.exists()
        ARQ_OBSERVACOES.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQ_OBSERVACOES, "a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos)
            if novo:
                escritor.writeheader()
            escritor.writerow(registro)
    return registro
