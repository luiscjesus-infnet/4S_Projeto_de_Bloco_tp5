"""
Processamento das notícias coletadas com o modelo de linguagem local (em lote).

No TP4 o painel analisava uma notícia por vez, quando a pessoa clicava. Aqui o mesmo
motor passa por todas as notícias da base e grava o resultado, para o painel mostrar
sem esperar o modelo:
- tema (abastecimento, qualidade, esgoto, saude, investimento ou outro) e sentimento,
  a partir do título + linha fina (o mesmo recorte do banco de provas do TP4);
- resumo de até 3 frases, a partir do texto inteiro.

Igual à coleta, roda fora do painel e só processa o que ainda não foi processado
(compara pelo link), então pode ser repetido depois de cada coleta.

Rodar a partir da raiz do projeto:
    python -m src.classificar_noticias
"""
import csv
import os
from datetime import datetime

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src import dados  # noqa: E402
from src.motor_llm import ErroDoMotor, MotorLLM  # noqa: E402

ARQ_SAIDA = dados.PROCESSADOS / "noticias_ia.csv"
CAMPOS = ["url", "tema_ia", "confianca_tema", "sentimento_ia", "confianca_sentimento", "resumo_ia",
          "segundos", "modelo", "processado_em"]


def main():
    noticias = dados.carregar_noticias()
    feitas = {linha["url"]: linha for linha in dados.ler_csv(ARQ_SAIDA)}
    pendentes = [n for n in noticias if n["url"] not in feitas]
    print(f"{len(noticias)} notícias na base; {len(pendentes)} ainda sem análise.")
    if not pendentes:
        return

    motor = MotorLLM(dispositivo=os.environ.get("LLM_DISPOSITIVO", "auto"))
    for i, n in enumerate(pendentes, start=1):
        curto = f"{n['titulo']}. {n['resumo']}".strip()
        completo = f"{n['titulo']}. {n['texto']}".strip()
        try:
            tema = motor.processar("tema", curto)
            sentimento = motor.processar("sentimento", curto)
            resumo = motor.processar("resumo", completo)
        except ErroDoMotor as erro:
            print(f"  [ERRO] {n['titulo'][:60]}: {erro}")
            continue
        feitas[n["url"]] = {
            "url": n["url"],
            "tema_ia": tema["categoria"], "confianca_tema": tema["confianca"],
            "sentimento_ia": sentimento["categoria"], "confianca_sentimento": sentimento["confianca"],
            "resumo_ia": resumo["resumo"],
            "segundos": round(tema["segundos"] + sentimento["segundos"] + resumo["segundos"], 1),
            "modelo": motor.nome,
            "processado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        print(f"  {i:>2}/{len(pendentes)} {tema['categoria']:<13} {sentimento['categoria']:<9} "
              f"{feitas[n['url']]['segundos']:>5} s  {n['titulo'][:60]}", flush=True)

    with open(ARQ_SAIDA, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        escritor.writeheader()
        escritor.writerows(feitas.values())
    print(f"{len(feitas)} notícias analisadas em {ARQ_SAIDA}")


if __name__ == "__main__":
    main()
