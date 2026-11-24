"""
API do Painel ODS 6 - dados de saneamento por UF, análise de texto com modelo de
linguagem e assistente com memória da conversa.

Rodar a partir da raiz do projeto (para o Python achar a pasta src):
    uvicorn api.main:app

Documentação interativa (gerada pelo FastAPI): http://127.0.0.1:8000/docs

Variáveis de ambiente (todas opcionais; podem ficar no arquivo .env):
    MODELO_LLM          modelo do HuggingFace já baixado em modelos/ (padrão: Qwen/Qwen2.5-1.5B-Instruct)
    LLM_DISPOSITIVO     auto | cpu | cuda (padrão: auto -> usa GPU NVIDIA se o PyTorch enxergar uma)
    LLM_PRECISAO        float32 | bfloat16 | float16 (padrão: float32, o mais rápido em CPU)
    LLM_DESLIGADO       1 para subir a API sem o modelo local
    LLM_TEMPO_LIMITE    segundos por análise antes de devolver 504 (padrão: 90)
    MOTOR_PADRAO        local | api - motor do assistente quando o pedido não escolhe (padrão: local)
    LLM_API_URL, LLM_API_CHAVE, LLM_API_MODELO   serviço externo compatível com o formato da OpenAI
"""
import os

from src.config import carregar_env

# o .env é lido antes de tudo; a chave fica lá e nunca no código
carregar_env()

# garante que o Transformers nunca vai à internet: o modelo local tem que estar no disco.
# (o motor via API usa requests direto, então estas travas não atrapalham ele)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.erros import registrar_tratadores
from api.modelos import Raiz
from api.rotas import assistente as rotas_assistente
from api.rotas import dados as rotas_dados
from api.rotas import llm as rotas_llm
from src.assistente import Assistente
from src.motor_api import MotorAPI
from src.motor_llm import BASE, MODELO_PADRAO, MotorLLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Roda uma vez, quando a API sobe. Aqui ficam prontos:
    - os "motores" do assistente: o modelo local (sai do disco e vai para a memória) e o
      cliente do serviço externo (só lê a configuração; não faz nenhuma chamada agora);
    - o assistente, com os fatos já calculados a partir dos dados processados.
    Se um motor falhar, a API sobe do mesmo jeito: só ele fica indisponível e o motivo
    aparece em GET /motores.
    """
    app.state.motor = None
    app.state.erro_modelo = None
    app.state.nome_modelo = os.environ.get("MODELO_LLM", MODELO_PADRAO)
    app.state.motores = {"local": None, "api": None}
    app.state.erros_motor = {"local": None, "api": None}
    app.state.nomes_motor = {"local": app.state.nome_modelo, "api": os.environ.get("LLM_API_MODELO", "-")}
    app.state.motor_preferido = os.environ.get("MOTOR_PADRAO", "local")

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
        except Exception as erro:  # a API sobe mesmo assim; só o que depende do modelo fica indisponível
            app.state.erro_modelo = f"{type(erro).__name__}: {erro}".replace(str(BASE), ".")
            log.error("Modelo não carregou: %s", app.state.erro_modelo)
    app.state.motores["local"] = app.state.motor
    app.state.erros_motor["local"] = app.state.erro_modelo

    motor_api = MotorAPI()
    app.state.motores["api"] = motor_api
    if not motor_api.configurado:
        app.state.erros_motor["api"] = motor_api.motivo_nao_configurado()
        log.info("Motor via API não configurado (%s). O assistente usa o modelo local.", app.state.erros_motor["api"])
    else:
        log.info("Motor via API configurado: %s em %s", motor_api.nome, motor_api.descricao()["onde_roda"])

    app.state.assistente = Assistente()
    yield
    app.state.motor = None
    app.state.motores = {"local": None, "api": None}


app = FastAPI(
    title="API do Painel ODS 6 - Saneamento por UF",
    description=(
        "Dados de água, esgoto e saúde por UF coletados pelo projeto (Painel Saneamento Brasil, "
        "IBGE e Agência Brasil), índice de prioridade para investimento, análise de texto com um "
        "modelo de linguagem local e um **assistente com memória da conversa** (`POST /conversar`), "
        "que pode usar o modelo local ou um serviço externo de IA. Todos os erros seguem o mesmo "
        "formato: `status`, `erro`, `mensagem`, `dica`."
    ),
    version="3.0.0",
    lifespan=lifespan,
)
registrar_tratadores(app)
app.include_router(rotas_dados.roteador)
app.include_router(rotas_llm.roteador)
app.include_router(rotas_assistente.roteador)


@app.get("/", response_model=Raiz, tags=["Informações"], summary="O que a API faz")
def raiz():
    """Mostra o que a API faz, quais motores de IA estão prontos e quais rotas existem."""
    return {
        "mensagem": "API do Painel ODS 6 - Saneamento por UF",
        "documentacao": "/docs",
        "modelo_carregado": app.state.motor is not None,
        "motores_disponiveis": [t for t, m in app.state.motores.items() if m is not None and not app.state.erros_motor[t]],
        "rotas": [
            "GET /fontes",
            "GET /saneamento",
            "GET /saneamento/ranking",
            "GET /saneamento/{sigla}",
            "GET /prioridades",
            "GET /serie/{sigla}",
            "GET /noticias",
            "GET /observacoes",
            "POST /observacoes",
            "POST /processar_texto",
            "GET /modelo",
            "POST /conversar",
            "GET /motores",
        ],
    }
