"""
Rotas que usam o modelo de linguagem local.

As funções são "def" comuns (não "async def") de propósito: o FastAPI roda cada
chamada numa thread separada, então enquanto o modelo pensa num texto as rotas de
dados continuam respondendo na hora.
"""
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import ValidationError

from api.erros import respostas_de_erro
from api.modelos import PedidoProcessamento, RespostaProcessamento, StatusModelo
from src.motor_llm import (
    MAX_TOKENS_ENTRADA,
    MODELO_PADRAO,
    TEMAS,
    TEMPO_LIMITE,
    ModeloIndisponivel,
    MotorLLM,
    RespostaInvalida,
)

roteador = APIRouter(tags=["Inteligência artificial"])

AVISO_CONFIANCA = "A confiança mostra o quanto o modelo preferiu esta opção às outras; não é a chance de estar certo."
AVISO_TRUNCADO = "O texto passou do limite do modelo e só o começo foi analisado."


def obter_motor(request: Request) -> MotorLLM:
    """Dependência: entrega o motor carregado na subida da API ou avisa que ele não está disponível."""
    motor = getattr(request.app.state, "motor", None)
    if motor is None:
        raise ModeloIndisponivel(getattr(request.app.state, "erro_modelo", None) or "modelo não carregado")
    return motor


@roteador.post(
    "/processar_texto",
    response_model=RespostaProcessamento,
    summary="Analisar um texto com o modelo de linguagem local",
    responses=respostas_de_erro(422, 500, 502, 503, 504),
)
def processar_texto(pedido: PedidoProcessamento, request: Request):
    """
    Recebe um texto e devolve a análise feita pelo modelo **rodando nesta máquina** (sem internet).

    - **tema**: em qual assunto de saneamento o texto se encaixa (abastecimento, qualidade, esgoto,
      saude, investimento ou outro), com a pontuação de cada um;
    - **sentimento**: positivo, negativo ou neutro;
    - **resumo**: até 3 frases.

    O texto precisa ter de 15 a 5.000 caracteres e pelo menos 3 palavras. Campos extras são recusados.
    """
    # o corpo já foi validado (422 vem antes); só agora confiro se o modelo está pronto (503)
    motor = obter_motor(request)
    saida = motor.processar(pedido.tipo_analise, pedido.texto)

    if pedido.tipo_analise == "tema":
        resultado = {"tipo": "tema", "categoria": saida["categoria"], "descricao": TEMAS.get(saida["categoria"], ""),
                     "confianca": saida["confianca"], "pontuacoes": saida["pontuacoes"]}
    elif pedido.tipo_analise == "sentimento":
        resultado = {"tipo": "sentimento", "sentimento": saida["categoria"],
                     "confianca": saida["confianca"], "pontuacoes": saida["pontuacoes"]}
    else:
        resultado = {"tipo": "resumo", "resumo": saida["resumo"], "frases": saida["frases"],
                     "tokens_gerados": saida["tokens_gerados"]}

    avisos = []
    if pedido.tipo_analise != "resumo":
        avisos.append(AVISO_CONFIANCA)
    if saida["texto_truncado"]:
        avisos.append(AVISO_TRUNCADO)

    # a saída do modelo passa pelo mesmo contrato da resposta; se vier algo fora da
    # lista de categorias ou um resumo vazio, descarto e devolvo 502 em vez de repassar lixo
    try:
        return RespostaProcessamento(
            tipo_analise=pedido.tipo_analise,
            texto_processado=pedido.texto,
            caracteres=len(pedido.texto),
            tokens_entrada=saida["tokens_entrada"],
            texto_truncado=saida["texto_truncado"],
            resultado=resultado,
            modelo=motor.info(),
            segundos=saida["segundos"],
            processado_em=datetime.now().replace(microsecond=0),
            aviso=" ".join(avisos) or None,
        )
    except ValidationError as erro:
        raise RespostaInvalida(str(erro)) from erro


@roteador.get("/modelo", response_model=StatusModelo, summary="Situação do modelo de linguagem")
def status_modelo(request: Request):
    """Mostra se o modelo está carregado, qual é, onde roda e, se não carregou, o motivo."""
    motor = getattr(request.app.state, "motor", None)
    base = {"analises": ["tema", "sentimento", "resumo"], "tempo_limite_s": TEMPO_LIMITE,
            "max_tokens_entrada": MAX_TOKENS_ENTRADA}
    if motor is None:
        nome = getattr(request.app.state, "nome_modelo", MODELO_PADRAO)
        return StatusModelo(carregado=False, nome=nome, erro=getattr(request.app.state, "erro_modelo", None), **base)
    return StatusModelo(carregado=True, **motor.info(), **base)
