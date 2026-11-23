"""
Coleta da série histórica (2010 em diante) de indicadores de saneamento por UF,
no Painel Saneamento Brasil (Instituto Trata Brasil), página "Por Indicador".

Por que aqui eu precisei do Selenium:
- a tabela só aparece depois de escolher Grupo > Subgrupo > Indicador, e cada
  caixa de seleção é preenchida por uma requisição assíncrona (AJAX);
- o HTML que chega no requests traz só as 15 primeiras linhas; o restante entra
  por rolagem infinita, também via AJAX;
- o botão "Exportar" da página devolveu erro 500 quando testei.

Rodar a partir da raiz do projeto (fora do app, porque é uma coleta lenta):
    python -m src.coleta_dinamica
"""
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from urllib import robotparser

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = Path(__file__).resolve().parent.parent
ARQUIVO_SAIDA = BASE / "data" / "processed" / "serie_saneamento_uf.csv"

SITE = "https://www.painelsaneamento.org.br"
PAGINA = SITE + "/explore/indicador"
AGENTE = "PainelODS6-TP3/1.0 (trabalho academico INFNET)"

# 26 estados + DF. É esse número que me diz que a tabela terminou de carregar as UFs.
TOTAL_UFS = 27

# código do indicador no site -> (grupo, subgrupo) do formulário em cascata
INDICADORES = {
    "POP_SEM_AG%": ("1", "11"),
    "POP_SEM_ES%": ("1", "11"),
    "INCIDE_VH": ("2", "21"),
}


def pode_coletar(url):
    # baixo o robots.txt com requests porque o read() padrão usa um agente que o site bloqueia
    resposta = requests.get(SITE + "/robots.txt", headers={"User-Agent": AGENTE}, timeout=20)
    resposta.raise_for_status()
    regras = robotparser.RobotFileParser()
    regras.parse(resposta.text.splitlines())
    return regras.can_fetch(AGENTE, url)


def abrir_navegador(visivel=False):
    opcoes = webdriver.ChromeOptions()
    if not visivel:
        opcoes.add_argument("--headless=new")
    opcoes.add_argument("--window-size=1366,900")
    opcoes.add_argument(f"--user-agent={AGENTE}")
    return webdriver.Chrome(options=opcoes)


def esperar_opcao(espera, id_select, valor):
    """Espera o AJAX do site colocar a opção desejada dentro do select."""
    seletor = f"#{id_select} option[value='{valor}']"
    espera.until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))


def ajax_terminou(navegador):
    """
    O HTML inicial já vem com todas as opções; se eu escolher o subgrupo antes da
    resposta do AJAX do grupo, essa resposta chega depois e apaga a minha escolha.
    Por isso espero não haver nenhuma requisição do jQuery em andamento.
    """
    return navegador.execute_script("return window.jQuery ? jQuery.active === 0 : true;")


def escolher(navegador, id_select, valor):
    """
    O select original fica escondido atrás de um componente visual do site,
    então o clique direto falha. Defino o valor e disparo o evento "change",
    que é exatamente o que o componente faz quando o usuário escolhe uma opção.
    """
    campo = navegador.find_element(By.ID, id_select)
    navegador.execute_script(
        "arguments[0].value = arguments[1];"
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
        campo, valor,
    )


def linhas_de_uf(navegador):
    linhas = navegador.find_elements(By.CSS_SELECTOR, "#explore-indicador-wrapper table tbody tr")
    return [l for l in linhas if l.find_elements(By.XPATH, ".//span[@class='type' and normalize-space()='UF']")]


def tabela_com_todas_ufs(navegador):
    """Condição da espera explícita: só devolve as linhas quando as 27 UFs chegaram."""
    linhas = linhas_de_uf(navegador)
    if len(linhas) >= TOTAL_UFS:
        return linhas
    # ainda faltam UFs: desço a página para disparar a rolagem infinita
    navegador.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    return False


def numero_br(texto):
    """'1.234,5%' -> 1234.5 ; '-' ou vazio -> None"""
    texto = texto.replace("%", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(texto)
    except ValueError:
        return None


def pagina_pronta(navegador):
    """
    O site usa um carregador do Cloudflare que só libera os eventos dos selects
    depois que todos os scripts rodam. Antes disso, escolher uma opção não faz nada.
    """
    return navegador.execute_script(
        "if (document.readyState !== 'complete') return false;"
        "if (window.__cfRLUnblockHandlers === undefined) return true;"
        "return window.__cfRLUnblockHandlers === true;"
    )


def coletar_indicador(navegador, codigo, grupo, subgrupo):
    espera = WebDriverWait(navegador, 30, poll_frequency=0.25)
    navegador.get(PAGINA)
    espera.until(pagina_pronta)

    esperar_opcao(espera, "se-g", grupo)
    escolher(navegador, "se-g", grupo)
    espera.until(ajax_terminou)  # o site recarrega subgrupos e indicadores do grupo

    esperar_opcao(espera, "se-s", subgrupo)
    escolher(navegador, "se-s", subgrupo)
    espera.until(ajax_terminou)  # agora recarrega só os indicadores do subgrupo

    esperar_opcao(espera, "se-id", codigo)
    escolher(navegador, "se-id", codigo)  # aqui o próprio site envia o formulário

    espera.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#explore-indicador-wrapper table tbody tr")))
    titulo = navegador.find_element(By.CSS_SELECTOR, ".table-simple--title .title").text
    nome_indicador = titulo.split(" - ", 1)[-1].strip()

    # a rolagem infinita pode demorar: dou até 60 s, checando 4 vezes por segundo
    espera_longa = WebDriverWait(navegador, 60, poll_frequency=0.25)
    linhas = espera_longa.until(tabela_com_todas_ufs)

    cabecalho = navegador.find_elements(By.CSS_SELECTOR, "#explore-indicador-wrapper table tr.table-simple--header td")
    anos = [c.text.strip() for c in cabecalho[1:]]

    registros = []
    for linha in linhas[:TOTAL_UFS]:
        celulas = linha.find_elements(By.TAG_NAME, "td")
        uf = celulas[0].find_element(By.CSS_SELECTOR, "span.name").text.strip()
        for ano, celula in zip(anos, celulas[1:]):
            if not re.fullmatch(r"\d{4}", ano):
                continue
            registros.append({
                "uf_nome": uf,
                "ano": int(ano),
                "indicador": codigo,
                "indicador_nome": nome_indicador,
                "valor": numero_br(celula.text),
            })
    return registros


def salvar_csv(registros):
    ARQUIVO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    coletado_em = datetime.now().strftime("%Y-%m-%d %H:%M")
    campos = ["uf_nome", "ano", "indicador", "indicador_nome", "valor", "fonte", "coletado_em"]
    with open(ARQUIVO_SAIDA, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        for r in registros:
            escritor.writerow({**r, "fonte": "Painel Saneamento Brasil (Selenium)", "coletado_em": coletado_em})


def main():
    if not pode_coletar(PAGINA):
        print("O robots.txt não permite coletar essa página. Parando.")
        return

    navegador = abrir_navegador()
    todos = []
    try:
        for codigo, (grupo, subgrupo) in INDICADORES.items():
            inicio = time.perf_counter()
            registros = None
            for tentativa in (1, 2):
                try:
                    registros = coletar_indicador(navegador, codigo, grupo, subgrupo)
                    break
                except TimeoutException:
                    print(f"[AVISO] {codigo}: tentativa {tentativa} estourou o tempo.")
            if registros is None:
                # prefiro saber que falhou do que gravar uma tabela pela metade
                print(f"[ERRO] {codigo}: a tabela não ficou completa a tempo. Indicador ignorado.")
                continue
            ufs = {r["uf_nome"] for r in registros}
            print(f"[OK] {codigo}: {len(registros)} valores, {len(ufs)} UFs, {time.perf_counter() - inicio:.1f} s")
            todos.extend(registros)
            time.sleep(2)  # intervalo educado entre um indicador e outro
    finally:
        navegador.quit()

    if todos:
        salvar_csv(todos)
        print(f"Arquivo gravado em {ARQUIVO_SAIDA}")
    else:
        print("Nada foi coletado; o CSV anterior foi mantido.")


if __name__ == "__main__":
    main()
