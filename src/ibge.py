"""
Dados das UFs vindos da API pública do IBGE (fonte usada desde o TP1).

- localidades: id, sigla, nome e região de cada UF;
- agregados (tabela 6579): população estimada por UF.

Se a API estiver fora do ar, uso a última cópia salva em data/processed/ufs_ibge.json
e aviso de onde o dado veio, em vez de deixar o painel quebrar.
"""
import json
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "processed" / "ufs_ibge.json"

URL_UFS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
URL_POP = "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/{ano}/variaveis/9324"
ANOS_POPULACAO = ["2025", "2024"]


def _buscar_populacao():
    for ano in ANOS_POPULACAO:
        resposta = requests.get(URL_POP.format(ano=ano), params={"localidades": "N3[all]"}, timeout=20)
        if resposta.status_code != 200:
            continue
        series = resposta.json()[0]["resultados"][0]["series"]
        populacao = {int(s["localidade"]["id"]): int(s["serie"][ano]) for s in series if s["serie"].get(ano)}
        if populacao:
            return ano, populacao
    return None, {}


def buscar_ufs_na_api():
    resposta = requests.get(URL_UFS, params={"orderBy": "nome"}, timeout=20)
    resposta.raise_for_status()
    ano_pop, populacao = _buscar_populacao()

    ufs = []
    for item in resposta.json():
        ufs.append({
            "id_ibge": int(item["id"]),
            "sigla": item["sigla"],
            "uf_nome": item["nome"],
            "regiao": item["regiao"]["nome"],
            "populacao": populacao.get(int(item["id"])),
            "ano_populacao": ano_pop,
        })
    return ufs


def carregar_ufs():
    """Devolve (lista de UFs, texto com a origem do dado)."""
    try:
        ufs = buscar_ufs_na_api()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(ufs, ensure_ascii=False, indent=2), encoding="utf-8")
        return ufs, "API do IBGE (ao vivo)"
    except (requests.RequestException, KeyError, IndexError, ValueError):
        if CACHE.exists():
            return json.loads(CACHE.read_text(encoding="utf-8")), "cópia local do IBGE (API indisponível)"
        return [], "sem dados do IBGE (API indisponível e sem cópia local)"


if __name__ == "__main__":
    dados, origem = carregar_ufs()
    print(origem, "-", len(dados), "UFs")
    print(dados[:2])
