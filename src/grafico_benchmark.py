"""
Gráfico do benchmark: acerto x tempo por texto, com o tamanho da bolha igual à memória usada.

Rodar depois do benchmark, a partir da raiz do projeto:
    python -m src.grafico_benchmark
"""
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src import dados
from src.benchmark_llm import ARQ_RESUMO

SAIDA = dados.BASE / "docs" / "img" / "benchmark_modelos.png"
CORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # ordem fixa: um modelo, uma cor
TINTA, TINTA_SECUNDARIA, GRADE = "#1f1f1e", "#5f5e58", "#e4e3df"
NOMES_CURTOS = {
    "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli": "mDeBERTa-v3 (zero-shot)",
    "Qwen/Qwen2.5-0.5B-Instruct": "Qwen2.5-0.5B",
    "Qwen/Qwen2.5-1.5B-Instruct": "Qwen2.5-1.5B",
    "Qwen/Qwen2.5-3B-Instruct": "Qwen2.5-3B",
}


def principal():
    with open(ARQ_RESUMO, newline="", encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    modelos = list(dict.fromkeys(l["modelo"] for l in linhas))
    cor = {m: CORES[i % len(CORES)] for i, m in enumerate(modelos)}

    fig, ax = plt.subplots(figsize=(8.5, 5), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for linha in linhas:
        x = float(linha["s_por_texto_tema"])
        y = 100 * int(linha["acerto_tema"]) / int(linha["itens"])
        tamanho = 120 * float(linha["memoria_pico_gb"])
        simples = linha["variante"] == "prompt simples"
        ax.scatter(x, y, s=tamanho, color="#fcfcfb" if simples else cor[linha["modelo"]],
                   edgecolor=cor[linha["modelo"]], linewidth=2, alpha=0.9, zorder=3)
        rotulo = f"{NOMES_CURTOS.get(linha['modelo'], linha['modelo'])}"
        if linha["familia"] == "decoder":
            rotulo += " · simples" if simples else " · c/ definições"
        rotulo += f"\n{y:.0f}% · {linha['memoria_pico_gb'].replace('.', ',')} GB RAM"
        raio = tamanho ** 0.5 / 2  # raio da bolha em pontos, para o texto não encostar nela
        ax.annotate(rotulo, (x, y), xytext=(raio + 6, 0), textcoords="offset points", fontsize=8,
                    color=TINTA, va="center")

    ax.set_xlabel("segundos por texto (mediana, só CPU)", color=TINTA_SECUNDARIA)
    ax.set_ylabel("acerto do tema no banco de provas (%)", color=TINTA_SECUNDARIA)
    ax.set_ylim(0, 105)
    ax.set_xlim(left=0, right=ax.get_xlim()[1] * 1.45)
    ax.grid(color=GRADE, linewidth=0.8, zorder=0)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.tick_params(colors=TINTA_SECUNDARIA, labelsize=8)
    ax.set_title("Acerto x tempo por texto (bolha = memória RAM no pico; vazada = prompt simples)",
                 fontsize=10, color=TINTA, loc="left")
    fig.tight_layout()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA, facecolor=fig.get_facecolor())
    print(f"Gráfico gravado em {SAIDA}")


if __name__ == "__main__":
    principal()
