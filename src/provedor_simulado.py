"""
Provedor simulado de IA, só para teste.

Imita a rota POST /v1/chat/completions de um serviço compatível com a OpenAI. Serve
para testar o tratamento de erros do motor via API (src/motor_api.py) sem chave, sem
internet e sem gastar cota. O comportamento é escolhido por uma marca na pergunta:

    [429]    limite de pedidos, com Retry-After: 7
    [401]    chave recusada
    [500]    erro do lado do serviço
    [vazio]  200, mas sem texto e com finish_reason "length" (o caso do modelo que só "pensou")
    [lento]  demora 5 s (para testar o tempo limite com LLM_API_TEMPO_LIMITE=2)
    sem marca: responde normalmente, citando um número que está nos fatos

Subir (num terminal separado):
    uvicorn src.provedor_simulado:app --port 8099
e a API do projeto apontando para ele:
    set LLM_API_URL=http://127.0.0.1:8099/v1
    set LLM_API_CHAVE=chave-de-teste
    set LLM_API_MODELO=simulado
    uvicorn api.main:app
"""
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Provedor simulado (teste)")


@app.post("/v1/chat/completions")
async def completar(request: Request):
    corpo = await request.json()
    mensagens = corpo.get("messages", [])
    pergunta = next((m["content"] for m in reversed(mensagens) if m["role"] == "user"), "")
    sistema = mensagens[0]["content"] if mensagens and mensagens[0]["role"] == "system" else ""
    entrada = sum(len(m["content"]) for m in mensagens) // 4

    if "[429]" in pergunta:
        return JSONResponse({"error": {"message": "Rate limit exceeded: free-models-per-min"}}, status_code=429,
                            headers={"Retry-After": "7"})
    if "[401]" in pergunta:
        return JSONResponse({"error": {"message": "No auth credentials found"}}, status_code=401)
    if "[500]" in pergunta:
        return JSONResponse({"error": {"message": "Upstream error"}}, status_code=500)
    if "[lento]" in pergunta:
        time.sleep(5)
    if "[vazio]" in pergunta:
        return {"model": corpo.get("model"), "choices": [{"message": {"role": "assistant", "content": ""},
                "finish_reason": "length"}], "usage": {"prompt_tokens": entrada, "completion_tokens": corpo.get("max_tokens", 0)}}

    numero = re.search(r"\d+,\d", sistema)
    texto = (f"Resposta simulada a \"{pergunta[:60]}\": recebi {len(mensagens)} mensagens"
             + (f" e o primeiro número dos fatos é {numero.group()}." if numero else "."))
    return {"model": corpo.get("model"), "choices": [{"message": {"role": "assistant", "content": texto},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": entrada, "completion_tokens": len(texto) // 4}}
