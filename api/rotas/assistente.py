"""
Rotas do assistente do painel (TP5): perguntas e respostas sobre os dados, com memória.

A API não guarda a conversa. Quem guarda é o painel: a cada pergunta ele manda o
histórico e as notas, e recebe de volta a resposta e as notas atualizadas. Assim a
API continua simples, várias pessoas podem conversar ao mesmo tempo sem uma ver a
conversa da outra e nenhuma conversa fica gravada no servidor.

"def" e não "async def" pelo mesmo motivo do TP4: o modelo demora alguns segundos e
as outras rotas não podem ficar esperando.
"""
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import ValidationError

from api.erros import respostas_de_erro
from api.modelos import ListaMotores, PedidoConversa, RespostaConversa
from src.memoria import ESTRATEGIAS
from src.motor_llm import ModeloIndisponivel, MotorNaoConfigurado, RespostaInvalida

roteador = APIRouter(tags=["Assistente com memória"])


def motor_padrao(app):
    """O motor local, se carregou; senão o da API, se estiver configurado."""
    for tipo in (app.state.motor_preferido, "local", "api"):
        if app.state.motores.get(tipo) is not None and not app.state.erros_motor.get(tipo):
            return tipo
    return None


def obter_motor_conversa(request: Request, tipo):
    app = request.app
    tipo = tipo or motor_padrao(app) or app.state.motor_preferido
    motor = app.state.motores.get(tipo)
    erro = app.state.erros_motor.get(tipo)
    if tipo == "api" and (motor is None or not motor.configurado):
        raise MotorNaoConfigurado(erro or "motor via API não configurado")
    if motor is None or erro:
        raise ModeloIndisponivel(erro or "modelo não carregado")
    return motor


@roteador.post(
    "/conversar",
    response_model=RespostaConversa,
    response_model_exclude_none=False,
    summary="Perguntar ao assistente do painel (com memória da conversa)",
    responses=respostas_de_erro(422, 500, 502, 503, 504),
)
def conversar(pedido: PedidoConversa, request: Request):
    """
    Responde perguntas sobre os dados do painel (água, esgoto, saúde, metas de 2033 e prioridade
    de investimento por UF), levando em conta a conversa anterior.

    - os números vêm de **fatos calculados no Python** a partir dos dados coletados; o modelo só escreve o texto;
    - **memoria** define o que vai da conversa para o modelo (padrão: últimas 2 trocas + notas);
    - **motor**: `local` (modelo nesta máquina) ou `api` (serviço externo configurado no `.env`);
    - a resposta traz as **notas atualizadas**: o painel guarda e manda de volta na próxima pergunta;
    - `conferencia.sem_origem` lista números da resposta que não estão nos dados enviados (sinal para conferir).
    """
    motor = obter_motor_conversa(request, pedido.motor)
    assistente = request.app.state.assistente
    estado = {"notas": pedido.notas.model_dump() if pedido.notas else None}
    saida = assistente.responder(
        motor, pedido.pergunta,
        historico=[m.model_dump() for m in pedido.historico],
        estado=estado, estrategia=pedido.memoria, janela=pedido.janela,
    )
    # a resposta do modelo passa pelo contrato antes de sair (texto vazio ou gigante vira 502)
    try:
        return RespostaConversa(
            resposta=saida["resposta"],
            memoria=pedido.memoria,
            motor=saida["motor"],
            notas=saida["estado"]["notas"],
            tokens_entrada=saida["tokens_entrada"],
            tokens_saida=saida["tokens_saida"],
            segundos=saida["segundos"],
            mensagens_enviadas=saida["mensagens_enviadas"],
            fatos_usados=saida["fatos_usados"],
            conferencia=saida["conferencia"],
            respondido_em=datetime.now().replace(microsecond=0),
            aviso=saida["aviso"],
            pedido=saida["pedido"] if pedido.mostrar_pedido else None,
        )
    except ValidationError as erro:
        raise RespostaInvalida(str(erro)) from erro


@roteador.get("/motores", response_model=ListaMotores, summary="Motores de IA disponíveis para o assistente")
def listar_motores(request: Request):
    """Mostra se o modelo local e o serviço externo estão prontos e, se não estiverem, o motivo."""
    app = request.app
    motores = []
    for tipo in ("local", "api"):
        motor = app.state.motores.get(tipo)
        erro = app.state.erros_motor.get(tipo)
        descricao = motor.descricao() if motor is not None else {"nome": app.state.nomes_motor.get(tipo, "-")}
        motores.append({"tipo": tipo, "disponivel": motor is not None and not erro,
                        "nome": descricao["nome"], "onde_roda": descricao.get("onde_roda"), "motivo": erro})
    return {"padrao": motor_padrao(app), "motores": motores,
            "estrategias": {k: v for k, v in ESTRATEGIAS.items() if k != "resumo"}}
