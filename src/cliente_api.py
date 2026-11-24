"""
Cliente que o painel Streamlit usa para conversar com a API FastAPI do projeto.

Se a API não estiver rodando (por exemplo, no Streamlit Cloud, onde só o painel
fica no ar), as funções devolvem o erro em vez de quebrar a página.
"""
import os

import requests

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
TEMPO_LIMITE = 5


def consultar(rota, parametros=None):
    """Devolve (dados, erro). Só um dos dois vem preenchido."""
    try:
        resposta = requests.get(f"{API_URL}{rota}", params=parametros, timeout=TEMPO_LIMITE)
        resposta.raise_for_status()
        return resposta.json(), None
    except requests.ConnectionError:
        return None, f"A API não respondeu em {API_URL}. Ela está rodando?"
    except requests.HTTPError as erro:
        return None, f"A API recusou o pedido ({erro.response.status_code}): {erro.response.text[:200]}"
    except requests.RequestException as erro:
        return None, f"Falha ao consultar a API: {erro}"


def enviar_observacao(sigla, autor, tipo, texto):
    try:
        resposta = requests.post(
            f"{API_URL}/observacoes",
            json={"sigla": sigla, "autor": autor, "tipo": tipo, "texto": texto},
            timeout=TEMPO_LIMITE,
        )
        if resposta.status_code >= 400:
            # desde o TP4 os erros da API vêm no formato próprio (status, erro, mensagem, dica)
            return None, _mensagem_de_erro(resposta)
        return resposta.json(), None
    except requests.ConnectionError:
        return None, f"A API não respondeu em {API_URL}. Ela está rodando?"
    except requests.RequestException as erro:
        return None, f"Falha ao enviar para a API: {erro}"


def api_no_ar():
    dados, erro = consultar("/")
    return erro is None


# o modelo roda em CPU: um resumo de notícia longa pode levar algumas dezenas de segundos.
# Espero um pouco mais que o limite da própria API (90 s), para receber o 504 dela em vez
# de desistir antes.
TEMPO_LIMITE_LLM = 120


def _mensagem_de_erro(resposta):
    """Monta a frase para o usuário a partir do erro padrão da API (status, erro, mensagem, dica)."""
    try:
        corpo = resposta.json()
    except ValueError:
        return f"A API respondeu com erro {resposta.status_code}."
    mensagem = corpo.get("mensagem") or f"Erro {resposta.status_code}"
    if corpo.get("dica"):
        mensagem += f" {corpo['dica']}"
    return f"({resposta.status_code}) {mensagem}"


def processar_texto(texto, tipo_analise):
    """POST /processar_texto. Devolve (resultado, erro); só um dos dois vem preenchido."""
    try:
        resposta = requests.post(
            f"{API_URL}/processar_texto",
            json={"texto": texto, "tipo_analise": tipo_analise},
            timeout=TEMPO_LIMITE_LLM,
        )
    except requests.ConnectionError:
        return None, f"A API não respondeu em {API_URL}. Ela está rodando?"
    except requests.Timeout:
        return None, f"A API não respondeu em {TEMPO_LIMITE_LLM} s. Tente um texto menor."
    except requests.RequestException as erro:
        return None, f"Falha ao falar com a API: {erro}"
    if resposta.status_code != 200:
        return None, _mensagem_de_erro(resposta)
    return resposta.json(), None


def status_modelo():
    """GET /modelo: se o modelo carregou, qual é e onde roda."""
    return consultar("/modelo")


# ---------------------------------------------------------------- assistente (TP5)
# o modelo local em CPU leva de 10 a 40 s por resposta; espero um pouco mais que o
# limite da API (90 s) para receber o 504 dela em vez de desistir antes
TEMPO_LIMITE_CONVERSA = 120
MAX_FALAS = 40   # mesmo limite da API


def motores():
    """GET /motores: quais motores de IA o assistente pode usar agora."""
    return consultar("/motores")


def conversar(pergunta, historico, notas=None, memoria="janela_notas", motor=None):
    """
    POST /conversar. O histórico e as notas vêm do st.session_state do painel: é o painel
    que lembra a conversa, a API não guarda nada. Devolve (resposta, erro).
    """
    falas = [{"role": m["role"], "content": m["content"]} for m in historico][-MAX_FALAS:]
    corpo = {"pergunta": pergunta, "historico": falas, "notas": notas, "memoria": memoria,
             "motor": motor, "mostrar_pedido": True}
    try:
        resposta = requests.post(f"{API_URL}/conversar", json=corpo, timeout=TEMPO_LIMITE_CONVERSA)
    except requests.ConnectionError:
        return None, f"A API não respondeu em {API_URL}. Ela está rodando?"
    except requests.Timeout:
        return None, f"A API não respondeu em {TEMPO_LIMITE_CONVERSA} s. Tente de novo ou troque o motor."
    except requests.RequestException as erro:
        return None, f"Falha ao falar com a API: {erro}"
    if resposta.status_code != 200:
        return None, _mensagem_de_erro(resposta)
    return resposta.json(), None
