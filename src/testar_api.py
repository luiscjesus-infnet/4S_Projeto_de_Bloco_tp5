"""
Roteiro de testes da API com o modelo rodando.

Faz pela linha de comando o mesmo que eu faço no /docs com o "Try it out", e mais duas
coisas que no navegador ficam difíceis: cronometrar várias chamadas seguidas e disparar
um pedido enquanto o modelo está ocupado com outro.

Subir a API num terminal (na raiz do projeto):
    uvicorn api.main:app
e, em outro terminal:
    python -m src.testar_api
"""
import os
import threading
import time

import requests

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
RELATO = "Tem esgoto correndo a céu aberto na rua principal do bairro, bem na frente da creche."
conferidos = []


def chamar(metodo, rota, **kwargs):
    inicio = time.perf_counter()
    resposta = requests.request(metodo, f"{API}{rota}", timeout=150, **kwargs)
    return resposta, time.perf_counter() - inicio


def conferir(titulo, resposta, segundos, esperado):
    corpo = resposta.json()
    if resposta.status_code == 200 and "resultado" in corpo:
        r = corpo["resultado"]
        detalhe = r.get("categoria") or r.get("sentimento") or r.get("resumo", "")[:90]
    else:
        detalhe = corpo.get("erro") or corpo.get("mensagem") or ""
    situacao = "OK" if resposta.status_code == esperado else f"DIFERENTE (esperava {esperado})"
    conferidos.append(resposta.status_code == esperado)
    print(f"  {titulo:<42} {resposta.status_code}  {segundos:6.2f} s  {situacao:<8} {detalhe}")


def processar(texto, tipo="tema", **extras):
    return chamar("POST", "/processar_texto", json={"texto": texto, "tipo_analise": tipo, **extras})


print(f"API em {API}\n")

print("1) Situação do modelo")
resposta, segundos = chamar("GET", "/modelo")
modelo = resposta.json()
print(f"  carregado={modelo['carregado']}  {modelo['nome']}  {modelo['dispositivo']}  "
      f"{modelo['precisao']}  carregou em {modelo['segundos_carregando']} s\n")

print("2) Cronômetro: o mesmo relato 3 vezes em cada análise")
for tipo in ("tema", "sentimento"):
    for vez in range(1, 4):
        conferir(f"{tipo}, chamada {vez}", *processar(RELATO, tipo), esperado=200)
noticias = requests.get(f"{API}/noticias", params={"incluir_texto": True, "limite": 16}, timeout=10).json()["noticias"]
cop = noticias[3]
conferir("tema da notícia da COP17 (esperado: outro)", *processar(f"{cop['titulo']}. {cop['resumo']}"), esperado=200)
desmatamento = noticias[6]
conferir("resumo de notícia inteira", *processar(f"{desmatamento['titulo']}. {desmatamento['texto']}", "resumo"),
         esperado=200)
print()

print("3) Entradas inválidas (esperado: 422 com a explicação)")
conferir("texto curto", *processar("curto"), esperado=422)
conferir("só números", *processar("12345 67890 12345 67890"), esperado=422)
conferir("texto com 5.001 caracteres", *processar("palavra " * 625 + "x"), esperado=422)
conferir("análise que não existe", *processar(RELATO, "traducao"), esperado=422)
conferir("campo a mais (cpf)", *processar(RELATO, cpf="123.456.789-00"), esperado=422)
conferir("corpo vazio", *chamar("POST", "/processar_texto", json={}), esperado=422)
print()

print("4) Rotas de dados (não dependem do modelo)")
conferir("ranking", *chamar("GET", "/saneamento/ranking", params={"limite": 3}), esperado=200)
conferir("UF que não existe (XX)", *chamar("GET", "/saneamento/XX"), esperado=422)
conferir("série com desde > ate", *chamar("GET", "/serie/MA", params={"desde": 2020, "ate": 2010}), esperado=422)
conferir("rota que não existe", *chamar("GET", "/nao-existe"), esperado=404)
print()

print("5) Dois pedidos ao mesmo tempo")
longo = noticias[12]
resultado_longo = {}


def resumo_longo():
    resultado_longo["resposta"] = processar(f"{longo['titulo']}. {longo['texto']}", "resumo")


tarefa = threading.Thread(target=resumo_longo)
tarefa.start()
time.sleep(2)  # dá tempo de o resumo começar
conferir("GET durante o resumo (deve responder já)", *chamar("GET", "/saneamento/ranking"), esperado=200)
resposta, segundos = processar(RELATO)
conferir("tema durante o resumo (modelo ocupado)", resposta, segundos, esperado=503)
print(f"  {'':<42} Retry-After: {resposta.headers.get('Retry-After')}")
tarefa.join()
conferir("o resumo que estava rodando", *resultado_longo["resposta"], esperado=200)

print(f"\n{sum(conferidos)} de {len(conferidos)} chamadas com o código esperado.")
