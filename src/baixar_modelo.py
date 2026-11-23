"""
Baixa os modelos do HuggingFace para a pasta modelos/ do projeto.

Fica separado da aplicação pelo mesmo motivo da coleta de dados: baixar leva tempo
(alguns GB) e só precisa acontecer uma vez. Depois disso a API carrega o modelo
direto do disco, sem internet.

A pasta modelos/ está no .gitignore (os arquivos têm vários GB). Quem clonar o
repositório roda este script antes de subir a API.

Rodar a partir da raiz do projeto:
    python -m src.baixar_modelo                      # só o modelo usado pela API
    python -m src.baixar_modelo --todos              # também os candidatos do benchmark
    python -m src.baixar_modelo Qwen/Qwen2.5-0.5B-Instruct
"""
import sys
import time

from huggingface_hub import snapshot_download

from src.motor_llm import CANDIDATOS, MODELO_PADRAO, pasta_do_modelo

# só o que o Transformers precisa para carregar o modelo em PyTorch
ARQUIVOS_NECESSARIOS = ["*.json", "*.safetensors", "*.model", "*.txt", "*.py"]


def tamanho_em_gb(pasta):
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) / 1024**3


def baixar(nome):
    destino = pasta_do_modelo(nome)
    inicio = time.perf_counter()
    print(f"Baixando {nome} para {destino} ...")
    snapshot_download(repo_id=nome, local_dir=destino, allow_patterns=ARQUIVOS_NECESSARIOS)
    print(f"[OK] {nome}: {tamanho_em_gb(destino):.2f} GB em {time.perf_counter() - inicio:.0f} s")


if __name__ == "__main__":
    argumentos = sys.argv[1:]
    if "--todos" in argumentos:
        nomes = list(CANDIDATOS)
    elif argumentos:
        nomes = argumentos
    else:
        nomes = [MODELO_PADRAO]
    for nome in nomes:
        baixar(nome)
