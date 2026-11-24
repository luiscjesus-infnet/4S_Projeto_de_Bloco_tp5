"""
Leitura do arquivo .env (chave da API e configurações).

Fiz à mão para não acrescentar mais uma biblioteca: cada linha NOME=valor vira uma
variável de ambiente, a não ser que ela já exista (o que vem do sistema vale mais).
O .env está no .gitignore: a chave nunca vai para o GitHub. O modelo de arquivo,
sem chave nenhuma, é o .env.exemplo.
"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def carregar_env(caminho=BASE / ".env"):
    if not caminho.exists():
        return False
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        os.environ.setdefault(nome.strip(), valor.strip().strip('"').strip("'"))
    return True
