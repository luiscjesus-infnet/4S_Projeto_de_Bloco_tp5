"""
Coleta da tabela "Explore por ano" do Painel Saneamento Brasil (Instituto Trata Brasil)
com requests + BeautifulSoup.

Essa página é estática: a tabela completa já vem no HTML que o servidor devolve.
Então aqui não faz sentido usar Selenium (seria mais lento e mais pesado).
Pego só as linhas de UF, com 8 indicadores do ano mais recente.

Rodar a partir da raiz do projeto:
    python -m src.coleta_painel
"""
import csv
import re
from datetime import datetime
from pathlib import Path
from urllib import robotparser

import requests
from bs4 import BeautifulSoup, SoupStrainer

BASE = Path(__file__).resolve().parent.parent
PASTA_BRUTOS = BASE / "data" / "raw"
ARQUIVO_SAIDA = BASE / "data" / "processed" / "saneamento_uf.csv"

SITE = "https://www.painelsaneamento.org.br"
PAGINA = SITE + "/explore/ano"
AGENTE = "PainelODS6-TP3/1.0 (trabalho academico INFNET)"

# trecho do título da coluna no site -> nome curto que uso no projeto
COLUNAS = [
    (r"sem acesso à água", "sem_agua_pct"),
    (r"sem coleta de esgoto", "sem_esgoto_pct"),
    (r"receita média de água", "receita_media_agua"),
    (r"esgoto tratado", "esgoto_tratado_pct"),
    (r"internações", "internacoes_vh"),
    (r"óbitos", "obitos_vh"),
    (r"renda das pessoas com saneamento", "renda_com_saneamento"),
    (r"renda das pessoas sem saneamento", "renda_sem_saneamento"),
]


def pode_coletar():
    resposta = requests.get(SITE + "/robots.txt", headers={"User-Agent": AGENTE}, timeout=20)
    resposta.raise_for_status()
    regras = robotparser.RobotFileParser()
    regras.parse(resposta.text.splitlines())
    return regras.can_fetch(AGENTE, PAGINA)


def numero_br(texto):
    texto = texto.replace("%", "").replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(texto)
    except ValueError:
        return None


def nome_curto(titulo):
    titulo = titulo.lower()
    for padrao, nome in COLUNAS:
        if re.search(padrao, titulo):
            return nome
    return None


def main():
    if not pode_coletar():
        print("robots.txt não permite essa página. Parando.")
        return

    resposta = requests.get(PAGINA, headers={"User-Agent": AGENTE}, timeout=60)
    resposta.raise_for_status()
    resposta.encoding = "utf-8"
    PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)
    (PASTA_BRUTOS / "snapshot_painel_ano.html").write_text(resposta.text, encoding="utf-8")

    # a página tem mais de 10 MB (todos os municípios); leio só o select do ano e a tabela
    so_o_que_interessa = SoupStrainer(["select", "table"])
    sopa = BeautifulSoup(resposta.text, "html.parser", parse_only=so_o_que_interessa)

    ano_opcao = sopa.select_one("#se-a option[selected]")
    ano = ano_opcao.get_text(strip=True) if ano_opcao else ""

    tabela = sopa.find("table")
    if tabela is None:
        print("Tabela não encontrada: a estrutura da página pode ter mudado.")
        return

    cabecalho = [nome_curto(td.get_text(" ", strip=True)) for td in tabela.select("tr.table-simple--header td")[1:]]

    linhas = []
    for tr in tabela.select("tr.table-simple--row"):
        tipo = tr.select_one("span.type")
        if not tipo or tipo.get_text(strip=True) != "UF":
            continue
        registro = {"uf_nome": tr.select_one("span.name").get_text(strip=True), "ano": ano}
        for coluna, td in zip(cabecalho, tr.find_all("td")[1:]):
            if coluna:
                registro[coluna] = numero_br(td.get_text(strip=True))
        linhas.append(registro)

    if len(linhas) != 27:
        print(f"[AVISO] Esperava 27 UFs e encontrei {len(linhas)}. Confira a página.")

    coletado_em = datetime.now().strftime("%Y-%m-%d %H:%M")
    campos = ["uf_nome", "ano"] + [nome for _, nome in COLUNAS] + ["fonte", "coletado_em"]
    ARQUIVO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_SAIDA, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        for r in linhas:
            escritor.writerow({**r, "fonte": "Painel Saneamento Brasil (BeautifulSoup)", "coletado_em": coletado_em})
    print(f"{len(linhas)} UFs do ano {ano} gravadas em {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
