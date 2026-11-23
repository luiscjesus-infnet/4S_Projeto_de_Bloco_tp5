"""
Coleta de notícias da Agência Brasil (páginas estáticas) com requests + BeautifulSoup.

Evolução do TP2: antes eu guardava só a manchete num TXT. Agora entro em cada
notícia e guardo data, resumo e texto, porque esse texto é a matéria-prima da
próxima etapa (resumos, classificação de sentimento e perguntas com LLM).

Regras que sigo:
- robots.txt do site permite as seções de notícia e pede 10 s entre requisições;
- o conteúdo é Creative Commons (pode ser reproduzido citando a fonte),
  por isso guardo o link original de cada notícia;
- o HTML bruto fica em data/raw (não vai para o Git); só o CSV processado sobe.

Rodar a partir da raiz do projeto:
    python -m src.coleta_noticias
"""
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent.parent
PASTA_BRUTOS = BASE / "data" / "raw"
ARQUIVO_SAIDA = BASE / "data" / "processed" / "noticias.csv"

SITE = "https://agenciabrasil.ebc.com.br"
SECOES = ["meio-ambiente", "saude"]
MAX_POR_SECAO = 8
AGENTE = "PainelODS6-TP3/1.0 (trabalho academico INFNET)"

# palavras que ligam a notícia ao ODS 6 (água e saneamento).
# Tirei "rio" da lista porque casava com "Rio de Janeiro" e marcava notícia errada.
TERMOS_ODS6 = re.compile(
    r"\b(água|aguas|águas|saneamento|esgoto|abastecimento|chuva|chuvas|seca|estiagem|"
    r"enchente|enchentes|inundaç\w+|hídric\w+|reservatório\w*|diarreia|"
    r"leptospirose|dengue|cólera|potável)\b",
    re.IGNORECASE,
)


def ler_robots():
    resposta = requests.get(SITE + "/robots.txt", headers={"User-Agent": AGENTE}, timeout=20)
    resposta.raise_for_status()
    regras = robotparser.RobotFileParser()
    regras.parse(resposta.text.splitlines())
    return regras


def baixar(url):
    resposta = requests.get(url, headers={"User-Agent": AGENTE}, timeout=30)
    resposta.raise_for_status()
    resposta.encoding = resposta.encoding or "utf-8"
    return resposta.text


def limpar(texto):
    """Tira espaços duplicados e caracteres invisíveis que vêm do HTML."""
    texto = texto.replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def links_da_secao(html, secao):
    sopa = BeautifulSoup(html, "html.parser")
    vistos, links = set(), []
    for a in sopa.find_all("a", href=True):
        href = a["href"]
        if f"/{secao}/noticia/" not in href:
            continue
        url = href if href.startswith("http") else SITE + href
        if url not in vistos:
            vistos.add(url)
            links.append(url)
    return links


def ler_noticia(html, url, secao):
    sopa = BeautifulSoup(html, "html.parser")
    titulo = sopa.find("h1")
    data = sopa.find("meta", attrs={"property": "article:published_time"})
    resumo = sopa.find("meta", attrs={"name": "description"})
    corpo = sopa.find("div", class_="conteudo-noticia")
    paragrafos = [limpar(p.get_text(" ")) for p in corpo.find_all("p")] if corpo else []
    texto = " ".join(p for p in paragrafos if p)

    titulo = limpar(titulo.get_text(" ")) if titulo else ""
    resumo = limpar(resumo["content"]) if resumo and resumo.get("content") else ""
    return {
        "secao": secao,
        "titulo": titulo,
        "url": url,
        "publicado_em": data["content"][:16].replace("T", " ") if data and data.get("content") else "",
        "resumo": resumo,
        "texto": texto[:6000],
        "palavras": len(texto.split()),
        "tema_ods6": "sim" if TERMOS_ODS6.search(f"{titulo} {resumo} {texto}") else "nao",
    }


def main():
    PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_SAIDA.parent.mkdir(parents=True, exist_ok=True)

    regras = ler_robots()
    pausa = regras.crawl_delay(AGENTE) or 10
    print(f"Crawl-delay informado pelo site: {pausa} s")

    noticias = []
    for secao in SECOES:
        url_secao = f"{SITE}/{secao}"
        if not regras.can_fetch(AGENTE, url_secao):
            print(f"[PULEI] robots.txt não permite {url_secao}")
            continue
        html = baixar(url_secao)
        (PASTA_BRUTOS / f"snapshot_{secao}.html").write_text(html, encoding="utf-8")
        links = links_da_secao(html, secao)[:MAX_POR_SECAO]
        print(f"{secao}: {len(links)} notícias para abrir")

        for url in links:
            time.sleep(pausa)
            try:
                noticia = ler_noticia(baixar(url), url, secao)
            except requests.RequestException as erro:
                print(f"[ERRO] {url}: {erro}")
                continue
            if noticia["titulo"]:
                noticias.append(noticia)
                print(f"  ok - {noticia['titulo'][:70]}")
        time.sleep(pausa)

    if not noticias:
        print("Nenhuma notícia coletada; mantive o CSV anterior.")
        return

    coletado_em = datetime.now().strftime("%Y-%m-%d %H:%M")
    campos = ["secao", "titulo", "url", "publicado_em", "resumo", "texto", "palavras", "tema_ods6", "fonte", "coletado_em"]
    with open(ARQUIVO_SAIDA, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        for n in noticias:
            escritor.writerow({**n, "fonte": "Agência Brasil (CC BY)", "coletado_em": coletado_em})
    print(f"{len(noticias)} notícias gravadas em {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
