"""
API do Painel ODS 6 - dados de saneamento por UF + análise de texto com modelo de linguagem local.

Rodar a partir da raiz do projeto (para o Python achar a pasta src):
    uvicorn api.main:app

Documentação interativa (gerada pelo FastAPI): http://127.0.0.1:8000/docs

Variáveis de ambiente (todas opcionais):
    MODELO_LLM          modelo do HuggingFace já baixado em modelos/ (padrão: Qwen/Qwen2.5-1.5B-Instruct)
    LLM_DISPOSITIVO     auto | cpu | cuda (padrão: auto -> usa GPU NVIDIA se o PyTorch enxergar uma)
    LLM_PRECISAO        float32 | bfloat16 | float16 (padrão: float32, o mais rápido em CPU)
    LLM_DESLIGADO       1 para subir a API sem o modelo (só as rotas de dados)
    LLM_TEMPO_LIMITE    segundos por análise antes de devolver 504 (padrão: 90)
"""
import os

# garante que o Transformers nunca vai à internet: o modelo tem que estar no disco
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.erros import registrar_tratadores
from api.modelos import Raiz
from api.rotas import dados as rotas_dados
from api.rotas import llm as rotas_llm
from src.motor_llm import BASE, MODELO_PADRAO, MotorLLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Tudo antes do yield roda uma vez, quando a API sobe: é aqui que o modelo sai do disco
    e vai para a memória. Assim cada pedido usa o modelo já carregado, em vez de carregar
    de novo a cada chamada. Depois do yield, roda quando a API é desligada.
    """
    app.state.motor = None
    app.state.erro_modelo = None
    app.state.nome_modelo = os.environ.get("MODELO_LLM", MODELO_PADRAO)

    if os.environ.get("LLM_DESLIGADO") == "1":
        app.state.erro_modelo = "Modelo desligado pela variável LLM_DESLIGADO=1."
        log.warning(app.state.erro_modelo)
    else:
        try:
            app.state.motor = MotorLLM(
                nome=app.state.nome_modelo,
                dispositivo=os.environ.get("LLM_DISPOSITIVO", "auto"),
                precisao=os.environ.get("LLM_PRECISAO", "float32"),
            )
            info = app.state.motor.info()
            log.info("Modelo %s carregado em %s s (%s, %s).", info["nome"], info["segundos_carregando"],
                     info["dispositivo"], info["precisao"])
        except Exception as erro:  # a API sobe mesmo assim; só a rota do modelo fica indisponível
            # o motivo aparece em GET /modelo; tiro as pastas da máquina da mensagem
            app.state.erro_modelo = f"{type(erro).__name__}: {erro}".replace(str(BASE), ".")
            log.error("Modelo não carregou: %s", app.state.erro_modelo)
    yield
    app.state.motor = None


app = FastAPI(
    title="API do Painel ODS 6 - Saneamento por UF",
    description=(
        "Dados de água, esgoto e saúde por UF coletados pelo projeto (Painel Saneamento Brasil, "
        "IBGE e Agência Brasil) e análise de texto com um modelo de linguagem que roda localmente "
        "(HuggingFace Transformers, sem serviço externo). Todos os erros seguem o mesmo formato: "
        "`status`, `erro`, `mensagem`, `dica`."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
registrar_tratadores(app)
app.include_router(rotas_dados.roteador)
app.include_router(rotas_llm.roteador)


@app.get("/", response_model=Raiz, tags=["Informações"], summary="O que a API faz")
def raiz():
    """Mostra o que a API faz, se o modelo está pronto e quais rotas existem."""
    return {
        "mensagem": "API do Painel ODS 6 - Saneamento por UF",
        "documentacao": "/docs",
        "modelo_carregado": app.state.motor is not None,
        "rotas": [
            "GET /fontes",
            "GET /saneamento",
            "GET /saneamento/ranking",
            "GET /saneamento/{sigla}",
            "GET /serie/{sigla}",
            "GET /noticias",
            "GET /observacoes",
            "POST /observacoes",
            "POST /processar_texto",
            "GET /modelo",
        ],
    }
