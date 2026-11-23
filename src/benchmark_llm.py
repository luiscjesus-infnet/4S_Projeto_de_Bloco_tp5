"""
Benchmark dos modelos candidatos no MEU caso de uso e na MINHA máquina.

Para cada modelo mede:
- acerto de tema e de sentimento no banco de provas (data/avaliacao/banco_de_provas.csv,
  48 textos rotulados à mão: 16 notícias reais coletadas no TP3 + 32 relatos de campo);
- tempo por texto (mediana), tempo para carregar, memória RAM no pico e espaço em disco;
- nos modelos que geram texto, o tempo para resumir 3 notícias completas.

Cada modelo roda num processo separado, para a memória de um não contaminar a medida do outro.

Rodar a partir da raiz do projeto (depois de python -m src.baixar_modelo --todos):
    python -m src.benchmark_llm
"""
import csv
import gc
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from src import dados
from src.motor_llm import CANDIDATOS, MODELO_PADRAO, SENTIMENTOS, TEMAS, pasta_do_modelo

PASTA = dados.BASE / "data" / "avaliacao"
ARQ_BANCO = PASTA / "banco_de_provas.csv"
ARQ_RESUMO = PASTA / "resultado_benchmark.csv"
ARQ_ITENS = PASTA / "resultado_por_item.csv"
ARQ_EXTRAS = PASTA / "resultado_extras.json"

# rótulos que o modelo zero-shot (encoder) compara com o texto
ROTULOS_ZERO_SHOT_TEMA = {
    "abastecimento": "falta de água ou abastecimento de água",
    "qualidade": "qualidade da água",
    "esgoto": "esgoto",
    "saude": "doenças causadas por água contaminada",
    "investimento": "obras e investimentos em saneamento",
    "outro": "outro assunto, sem relação com água ou esgoto",
}
ROTULOS_ZERO_SHOT_SENTIMENTO = {
    "positivo": "uma notícia boa ou uma melhora",
    "negativo": "um problema ou uma notícia ruim",
    "neutro": "uma informação neutra",
}
NOTICIAS_PARA_RESUMO = [3, 6, 13]  # posições (1..16) em noticias.csv com texto mais longo e ligado ao tema


def ler_banco():
    with open(ARQ_BANCO, newline="", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def memoria_pico_gb():
    import psutil

    info = psutil.Process().memory_info()
    pico = getattr(info, "peak_wset", None) or info.rss  # peak_wset existe no Windows
    return round(pico / 1024**3, 2)


def tamanho_disco_gb(nome):
    pasta = pasta_do_modelo(nome)
    pesos = [f for f in pasta.rglob("*") if f.is_file() and f.suffix in (".safetensors", ".bin")]
    return round(sum(f.stat().st_size for f in pesos) / 1024**3, 2)


def maquina():
    import psutil
    import torch
    import transformers

    return {
        "sistema": f"{platform.system()} {platform.release()}",
        "processador": platform.processor(),
        "nucleos_fisicos": psutil.cpu_count(logical=False),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "threads_torch": torch.get_num_threads(),
        "gpu_usada": torch.cuda.is_available(),
    }


# ---------------------------------------------------------------- avaliação de um modelo
def avaliar_encoder(nome, banco):
    from transformers import pipeline

    inicio = time.perf_counter()
    classificador = pipeline("zero-shot-classification", model=str(pasta_do_modelo(nome)), device="cpu")
    carga = time.perf_counter() - inicio

    itens = []
    for tarefa, rotulos, modelo_frase in [
        ("tema", ROTULOS_ZERO_SHOT_TEMA, "Este texto é sobre {}."),
        ("sentimento", ROTULOS_ZERO_SHOT_SENTIMENTO, "Este texto conta {}."),
    ]:
        de_volta = {frase: chave for chave, frase in rotulos.items()}
        for linha in banco:
            t0 = time.perf_counter()
            saida = classificador(linha["texto"], candidate_labels=list(rotulos.values()), hypothesis_template=modelo_frase)
            previsto = de_volta[saida["labels"][0]]
            itens.append({"tarefa": tarefa, "variante": "zero-shot", "id": linha["id"], "esperado": linha[tarefa],
                          "previsto": previsto, "segundos": round(time.perf_counter() - t0, 3)})
    return carga, itens, []


def avaliar_decoder(nome, banco, variantes):
    from src.motor_llm import MotorLLM

    inicio = time.perf_counter()
    motor = MotorLLM(nome, dispositivo="cpu", precisao="float32")
    carga = time.perf_counter() - inicio

    itens = []
    for com_definicoes in variantes:
        variante = "prompt com definições" if com_definicoes else "prompt simples"
        for tarefa in ("tema", "sentimento"):
            for linha in banco:
                t0 = time.perf_counter()
                saida = motor._executar(tarefa, linha["texto"], com_definicoes)
                itens.append({"tarefa": tarefa, "variante": variante, "id": linha["id"], "esperado": linha[tarefa],
                              "previsto": saida["categoria"], "segundos": round(time.perf_counter() - t0, 3)})

    noticias = dados.carregar_noticias()
    resumos = []
    for posicao in NOTICIAS_PARA_RESUMO:
        n = noticias[posicao - 1]
        t0 = time.perf_counter()
        saida = motor._executar("resumo", f"{n['titulo']}. {n['texto']}")
        resumos.append({"noticia": n["titulo"], "segundos": round(time.perf_counter() - t0, 1),
                        "tokens_gerados": saida["tokens_gerados"], "resumo": saida["resumo"]})
    return carga, itens, resumos


def rodar_um_modelo(nome, saida_json):
    """Executado num processo filho: avalia um modelo e grava o resultado em JSON."""
    banco = ler_banco()
    if CANDIDATOS[nome] == "encoder":
        carga, itens, resumos = avaliar_encoder(nome, banco)
    else:
        # o prompt simples só no modelo principal, para ver o efeito do prompt sem esperar horas
        variantes = [True, False] if nome == MODELO_PADRAO else [True]
        carga, itens, resumos = avaliar_decoder(nome, banco, variantes)
    resultado = {"modelo": nome, "familia": CANDIDATOS[nome], "carga_s": round(carga, 1),
                 "memoria_pico_gb": memoria_pico_gb(), "disco_gb": tamanho_disco_gb(nome),
                 "itens": itens, "resumos": resumos}
    Path(saida_json).write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- testes extras no modelo escolhido
def extras_modelo_escolhido(saida_json):
    """Precisão numérica (float32 x float16 x bfloat16) e saída livre x saída restrita."""
    import torch

    from src.motor_llm import MotorLLM, montar_mensagens

    banco = ler_banco()
    extras = {"precisao": [], "saida_livre": {}}

    amostra = banco[16:22]  # 6 relatos de campo
    for precisao in ("float32", "bfloat16", "float16"):
        motor = MotorLLM(MODELO_PADRAO, dispositivo="cpu", precisao=precisao)
        tempos, acertos = [], 0
        for linha in amostra:
            t0 = time.perf_counter()
            saida = motor._executar("tema", linha["texto"])
            tempos.append(time.perf_counter() - t0)
            acertos += saida["categoria"] == linha["tema"]
        extras["precisao"].append({"precisao": precisao, "itens": len(amostra), "acertos": acertos,
                                   "segundos_por_texto": round(statistics.median(tempos), 2)})
        del motor
        gc.collect()

    # o que acontece se eu deixar o modelo escrever a resposta livremente?
    motor = MotorLLM(MODELO_PADRAO, dispositivo="cpu", precisao="float32")
    fora_da_lista, acertos, exemplos = 0, 0, []
    for linha in banco:
        prompt = motor.tokenizer.apply_chat_template(
            montar_mensagens("tema", linha["texto"]), add_generation_prompt=True, tokenize=False)
        entrada = motor.tokenizer(prompt, return_tensors="pt")
        with torch.inference_mode():
            gerado = motor.modelo.generate(**entrada, max_new_tokens=8, do_sample=False,
                                           pad_token_id=motor.tokenizer.eos_token_id)
        texto = motor.tokenizer.decode(gerado[0, entrada["input_ids"].shape[1]:], skip_special_tokens=True)
        # acento e maiúscula não contam como erro ("Saúde" vale como saude)
        resposta = dados._sem_acento(texto.strip().strip(".\"'"))
        if resposta not in TEMAS:
            fora_da_lista += 1
            exemplos.append({"id": linha["id"], "resposta_do_modelo": texto.strip()})
        acertos += resposta == linha["tema"]
    extras["saida_livre"] = {"itens": len(banco), "fora_da_lista": fora_da_lista, "acertos": acertos,
                             "exemplos_fora_da_lista": exemplos[:8]}
    Path(saida_json).write_text(json.dumps(extras, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- orquestração
def resumir(resultados):
    linhas = []
    for r in resultados:
        variantes = sorted({i["variante"] for i in r["itens"]})
        for variante in variantes:
            linha = {"modelo": r["modelo"], "familia": r["familia"], "variante": variante}
            for tarefa in ("tema", "sentimento"):
                sel = [i for i in r["itens"] if i["variante"] == variante and i["tarefa"] == tarefa]
                linha[f"acerto_{tarefa}"] = sum(i["previsto"] == i["esperado"] for i in sel)
                linha[f"s_por_texto_{tarefa}"] = round(statistics.median(i["segundos"] for i in sel), 2)
            linha["itens"] = len([i for i in r["itens"] if i["variante"] == variante and i["tarefa"] == "tema"])
            linha["carga_s"] = r["carga_s"]
            linha["memoria_pico_gb"] = r["memoria_pico_gb"]
            linha["disco_gb"] = r["disco_gb"]
            linha["resumo_s_medio"] = (round(statistics.mean(x["segundos"] for x in r["resumos"]), 1)
                                       if r["resumos"] else "")
            linhas.append(linha)
    return linhas


def gravar_csv(caminho, linhas):
    with open(caminho, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)


TEMPORARIA = PASTA / "_parciais"


def principal(modelos, com_extras):
    """Avalia os modelos pedidos (cada um vira um JSON parcial) e consolida tudo o que já existe."""
    TEMPORARIA.mkdir(exist_ok=True)
    for nome in modelos:
        if not (pasta_do_modelo(nome) / "config.json").exists():
            print(f"[PULEI] {nome}: não está em modelos/ (rode python -m src.baixar_modelo --todos)")
            continue
        destino = TEMPORARIA / (nome.replace("/", "__") + ".json")
        print(f"Avaliando {nome} ...", flush=True)
        t0 = time.perf_counter()
        subprocess.run([sys.executable, "-m", "src.benchmark_llm", "--um", nome, str(destino)], check=True)
        print(f"   pronto em {time.perf_counter() - t0:.0f} s", flush=True)

    if com_extras:
        print("Testes extras no modelo escolhido ...", flush=True)
        subprocess.run([sys.executable, "-m", "src.benchmark_llm", "--extras", str(TEMPORARIA / "extras.json")],
                       check=True)

    # consolida na ordem da lista de candidatos
    resultados = []
    for nome in CANDIDATOS:
        parcial = TEMPORARIA / (nome.replace("/", "__") + ".json")
        if parcial.exists():
            resultados.append(json.loads(parcial.read_text(encoding="utf-8")))
    resumo = resumir(resultados)
    gravar_csv(ARQ_RESUMO, resumo)
    gravar_csv(ARQ_ITENS, [{"modelo": r["modelo"], **i} for r in resultados for i in r["itens"]])

    arquivo_extras = TEMPORARIA / "extras.json"
    extras = json.loads(arquivo_extras.read_text(encoding="utf-8")) if arquivo_extras.exists() else {}
    extras["maquina"] = maquina()
    extras["resumos"] = {r["modelo"]: r["resumos"] for r in resultados if r["resumos"]}
    ARQ_EXTRAS.write_text(json.dumps(extras, ensure_ascii=False, indent=2), encoding="utf-8")

    for linha in resumo:
        print(linha)
    print(json.dumps({k: v for k, v in extras.items() if k != "resumos"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    if len(sys.argv) >= 4 and sys.argv[1] == "--um":
        rodar_um_modelo(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--extras":
        extras_modelo_escolhido(sys.argv[2])
    else:
        argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
        principal(argumentos or list(CANDIDATOS), com_extras="--extras" in sys.argv[1:] or not argumentos)
