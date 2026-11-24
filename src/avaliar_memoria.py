"""
Avaliação da memória do assistente: a mesma conversa de 10 perguntas, com gabarito,
rodada com cada estratégia de memória. Mede acertos, tokens enviados ao modelo e tempo.

A conversa (data/avaliacao/conversa_teste.csv) foi montada para cobrar memória:
- perguntas que só fazem sentido com a anterior ("E sem coleta de esgoto?");
- perguntas que voltam ao começo ("Voltando ao primeiro estado que eu perguntei...").

Rodadas:
- 5 estratégias de memória com os fatos calculados no Python (src/memoria.py);
- a estratégia escolhida (janela + notas) recebendo a TABELA CRUA em vez dos fatos,
  para ver o efeito de deixar as contas para o modelo.

Usa o mesmo Assistente da API, então o que é medido aqui é o que roda no painel.

Rodar a partir da raiz do projeto (o modelo local precisa estar em modelos/):
    python -m src.avaliar_memoria                 # motor local (~25 min só em CPU)
    python -m src.avaliar_memoria --motor api     # serviço externo configurado no .env
    python -m src.avaliar_memoria --so-grafico    # refaz só os gráficos com o último resultado
    python -m src.avaliar_memoria --recontar      # confere de novo as respostas gravadas com o gabarito atual

Sobre o gabarito: conferi as 60 respostas da rodada final uma a uma e achei um furo na
pergunta 9 - ela conferia só o número (4,2 milhões) e aceitou "4,2 milhões... na Paraíba".
Passei a exigir também o Pará e recontei com --recontar (sem rodar o modelo de novo).
"""
import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

from src.config import carregar_env

carregar_env()
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src.assistente import Assistente, estado_vazio  # noqa: E402
from src.memoria import sem_acento  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
PASTA = BASE / "data" / "avaliacao"
ARQ_CONVERSA = PASTA / "conversa_teste.csv"
PASTA_IMG = BASE / "docs" / "img"

RODADAS = [
    ("sem_memoria", "fatos"),
    ("completa", "fatos"),
    ("janela", "fatos"),
    ("resumo", "fatos"),
    ("janela_notas", "fatos"),
    ("janela_notas", "tabela"),
]
NOMES = {
    ("sem_memoria", "fatos"): "sem memória",
    ("completa", "fatos"): "conversa inteira",
    ("janela", "fatos"): "janela de 2 trocas",
    ("resumo", "fatos"): "janela + resumo",
    ("janela_notas", "fatos"): "janela + notas",
    ("janela_notas", "tabela"): "janela + notas, tabela crua",
}


def acertou(resposta, esperado, nao_pode):
    """Todos os grupos de 'esperado' (separados por ;) precisam aparecer; 'nao_pode' não pode."""
    texto = sem_acento(resposta)
    grupos = [g for g in esperado.split(";") if g]
    ok = all(re.search(sem_acento(g), texto) for g in grupos)
    if nao_pode and re.search(sem_acento(nao_pode), texto):
        ok = False
    return ok


def rodar(motor, assistente, conversa, estrategia, contexto, janela=2):
    historico, estado, itens = [], estado_vazio(), []
    for linha in conversa:
        saida = assistente.responder(motor, linha["pergunta"], historico, estado,
                                     estrategia=estrategia, contexto=contexto, janela=janela)
        ok = acertou(saida["resposta"], linha["esperado"], linha["nao_pode"])
        itens.append({
            "rodada": NOMES[(estrategia, contexto)], "estrategia": estrategia, "contexto": contexto,
            "motor": saida["motor"]["nome"], "ordem": int(linha["ordem"]), "pergunta": linha["pergunta"],
            "depende_de": linha["depende_de"], "gabarito": linha["gabarito"], "resposta": saida["resposta"],
            "acertou": ok, "tokens_entrada": saida["tokens_entrada"], "tokens_saida": saida["tokens_saida"],
            "segundos": saida["segundos"], "segundos_resumo": saida["segundos_resumo"],
            "mensagens_enviadas": saida["mensagens_enviadas"], "fatos_usados": " ".join(saida["fatos_usados"]),
            "sem_origem": " ".join(saida["conferencia"]["sem_origem"]),
        })
        marca = "OK " if ok else "ERR"
        print(f"  {linha['ordem']:>2} {marca} {saida['tokens_entrada']:>5} tk {saida['segundos']:6.1f} s  "
              f"{saida['resposta'][:110]}", flush=True)
        historico += [{"role": "user", "content": linha["pergunta"]},
                      {"role": "assistant", "content": saida["resposta"]}]
        estado = saida["estado"]
    return itens


def resumir(itens):
    rodadas = {}
    for item in itens:
        rodadas.setdefault(item["rodada"], []).append(item)
    resumo = []
    for nome, lista in rodadas.items():
        tokens = [i["tokens_entrada"] for i in lista]
        resumo.append({
            "rodada": nome, "motor": lista[0]["motor"],
            "acertos": sum(i["acertou"] for i in lista), "perguntas": len(lista),
            "acertos_que_dependem_de_memoria": sum(i["acertou"] for i in lista if i["depende_de"] != "-"),
            "perguntas_que_dependem_de_memoria": sum(1 for i in lista if i["depende_de"] != "-"),
            "tokens_entrada_media": round(sum(tokens) / len(tokens)),
            "tokens_entrada_primeira": tokens[0], "tokens_entrada_ultima": tokens[-1],
            "segundos_total": round(sum(i["segundos"] for i in lista), 1),
            "segundos_resumindo": round(sum(i["segundos_resumo"] for i in lista), 1),
            "numeros_sem_origem": sum(1 for i in lista if i["sem_origem"]),
        })
    return resumo


def graficos(itens, sufixo):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cores = {"sem memória": "#9aa0a6", "conversa inteira": "#d6542a", "janela de 2 trocas": "#e0a526",
             "janela + resumo": "#7d5ba6", "janela + notas": "#2a78d6", "janela + notas, tabela crua": "#3fa66b"}
    rodadas = {}
    for i in itens:
        rodadas.setdefault(i["rodada"], []).append(i)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.35, 1]})
    for nome, lista in rodadas.items():
        if "tabela" in nome:
            continue
        ax1.plot([i["ordem"] for i in lista], [i["tokens_entrada"] for i in lista], marker="o", ms=4,
                 lw=2.2 if nome == "janela + notas" else 1.4, color=cores.get(nome), label=nome)
    ax1.set_xlabel("pergunta da conversa")
    ax1.set_ylabel("tokens enviados ao modelo")
    ax1.set_title("Tamanho do pedido a cada pergunta")
    ax1.set_xticks(range(1, 11))
    ax1.grid(alpha=0.25)
    ax1.legend(fontsize=8, frameon=False)

    nomes = list(rodadas)
    acertos = [sum(i["acertou"] for i in rodadas[n]) for n in nomes]
    barras = ax2.barh(nomes, acertos, color=[cores.get(n, "#888") for n in nomes])
    for barra, valor in zip(barras, acertos):
        ax2.text(valor + 0.1, barra.get_y() + barra.get_height() / 2, f"{valor}/10", va="center", fontsize=9)
    ax2.set_xlim(0, 11)
    ax2.invert_yaxis()
    ax2.set_title("Acertos na conversa de 10 perguntas")
    ax2.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    destino = PASTA_IMG / f"avaliacao_memoria{sufixo}.png"
    fig.savefig(destino, dpi=130)
    print("gráfico:", destino)


def salvar(itens, resumo, sufixo):
    with open(PASTA / f"memoria_por_pergunta{sufixo}.csv", "w", newline="", encoding="utf-8") as arq:
        escritor = csv.DictWriter(arq, fieldnames=list(itens[0]))
        escritor.writeheader()
        escritor.writerows(itens)
    with open(PASTA / f"memoria_resultado{sufixo}.csv", "w", newline="", encoding="utf-8") as arq:
        escritor = csv.DictWriter(arq, fieldnames=list(resumo[0]))
        escritor.writeheader()
        escritor.writerows(resumo)


def ler_itens(sufixo):
    with open(PASTA / f"memoria_por_pergunta{sufixo}.csv", encoding="utf-8") as arq:
        itens = list(csv.DictReader(arq))
    for i in itens:
        for campo in ("ordem", "tokens_entrada", "tokens_saida", "mensagens_enviadas"):
            i[campo] = int(i[campo])
        for campo in ("segundos", "segundos_resumo"):
            i[campo] = float(i[campo])
        i["acertou"] = i["acertou"] == "True"
    return itens


def recontar(itens, conversa):
    """Confere de novo as respostas gravadas com o gabarito atual (não chama o modelo)."""
    gabarito = {int(l["ordem"]): l for l in conversa}
    mudaram = []
    for i in itens:
        linha = gabarito[i["ordem"]]
        novo = acertou(i["resposta"], linha["esperado"], linha["nao_pode"])
        if novo != i["acertou"]:
            mudaram.append(f"  {i['rodada']}, pergunta {i['ordem']}: {i['acertou']} -> {novo} | {i['resposta'][:90]}")
        i["acertou"], i["gabarito"] = novo, linha["gabarito"]
    print("\n".join(mudaram) or "  nenhuma resposta mudou de situação")
    return itens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motor", choices=["local", "api"], default="local")
    parser.add_argument("--so-grafico", action="store_true")
    parser.add_argument("--recontar", action="store_true")
    args = parser.parse_args()
    sufixo = "" if args.motor == "local" else "_api"

    with open(ARQ_CONVERSA, encoding="utf-8") as arq:
        conversa = list(csv.DictReader(arq))

    if args.so_grafico or args.recontar:
        itens = ler_itens(sufixo)
        if args.recontar:
            itens = recontar(itens, conversa)
            resumo = resumir(itens)
            salvar(itens, resumo, sufixo)
            print(json.dumps(resumo, ensure_ascii=False, indent=1))
        graficos(itens, sufixo)
        return
    if args.motor == "local":
        from src.motor_llm import MotorLLM
        motor = MotorLLM(dispositivo=os.environ.get("LLM_DISPOSITIVO", "auto"))
    else:
        from src.motor_api import MotorAPI
        motor = MotorAPI()
    assistente = Assistente()

    itens = []
    inicio = time.perf_counter()
    for estrategia, contexto in RODADAS:
        print(f"\n== {NOMES[(estrategia, contexto)]} ({motor.descricao()['nome']})", flush=True)
        itens += rodar(motor, assistente, conversa, estrategia, contexto)
    resumo = resumir(itens)
    salvar(itens, resumo, sufixo)
    print(f"\nTempo total: {(time.perf_counter() - inicio) / 60:.1f} min")
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    graficos(itens, sufixo)


if __name__ == "__main__":
    main()
