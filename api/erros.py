"""
Tratamento de erros da API.

Ideia: todo erro sai no mesmo formato (modelo Erro em api/modelos.py), com um código
curto para o programa cliente e uma mensagem + dica para a pessoa. Nada de rastro
de exceção do Python indo para o usuário; o detalhe técnico fica só no log da API.

Tabela de cenários -> código HTTP:
    texto ou parâmetro inválido ..................... 422 (validação)
    recurso não encontrado .......................... 404
    modelo não baixado / não carregado .............. 503
    modelo ocupado com outro pedido ................. 503 + Retry-After
    faltou memória para rodar o modelo .............. 503
    modelo passou do tempo limite ................... 504
    modelo devolveu algo fora do formato ............ 502
    qualquer outra falha inesperada ................. 500

Erros novos do TP5 (motor que chama um serviço externo de IA):
    motor via API sem chave/modelo no .env .......... 503
    chave recusada pelo serviço (401/403) ........... 503
    serviço limitou os pedidos (429) ................ 503 + Retry-After
    serviço caiu ou respondeu erro (5xx) ............ 502
    serviço passou do tempo limite .................. 504
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.motor_llm import (
    ChaveRecusada,
    ErroDoMotor,
    LimiteDoServico,
    ModeloIndisponivel,
    ModeloNaoEncontrado,
    MotorNaoConfigurado,
    MotorOcupado,
    RespostaInvalida,
    SemMemoria,
    ServicoExternoFalhou,
    TempoEsgotado,
)

log = logging.getLogger("api")

# erro do motor -> (status, código curto, mensagem, dica)
MAPA_ERROS_MOTOR = {
    ModeloNaoEncontrado: (
        503, "modelo_nao_encontrado",
        "O modelo de linguagem não foi encontrado nesta máquina.",
        "Rode python -m src.baixar_modelo e reinicie a API. As outras rotas continuam funcionando.",
    ),
    ModeloIndisponivel: (
        503, "modelo_indisponivel",
        "O modelo de linguagem não está carregado, então esta análise não pode ser feita agora.",
        "Veja o motivo em GET /modelo. As rotas de dados continuam funcionando normalmente.",
    ),
    MotorOcupado: (
        503, "modelo_ocupado",
        "O modelo está terminando outro pedido.",
        "Tente de novo em alguns segundos.",
    ),
    SemMemoria: (
        503, "sem_memoria",
        "Faltou memória na máquina para rodar o modelo.",
        "Feche outros programas ou use um modelo menor (variável MODELO_LLM, ex.: Qwen/Qwen2.5-0.5B-Instruct).",
    ),
    TempoEsgotado: (
        504, "tempo_esgotado",
        "O modelo demorou mais que o limite para responder.",
        "Envie um texto menor ou tente de novo. Resumos de textos longos são os mais demorados.",
    ),
    RespostaInvalida: (
        502, "resposta_invalida_do_modelo",
        "O modelo respondeu, mas a resposta veio fora do formato esperado e foi descartada.",
        "Tente de novo; se repetir, reformule o texto.",
    ),
    MotorNaoConfigurado: (
        503, "motor_api_nao_configurado",
        "O motor que usa um serviço externo de IA não está configurado.",
        "Copie .env.exemplo para .env, preencha LLM_API_CHAVE e LLM_API_MODELO e reinicie a API. "
        "O motor local continua disponível.",
    ),
    ChaveRecusada: (
        503, "chave_recusada",
        "O serviço externo de IA recusou a chave de API.",
        "Confira LLM_API_CHAVE no .env e se a chave tem acesso ao modelo escolhido. O motor local continua disponível.",
    ),
    LimiteDoServico: (
        503, "limite_do_servico",
        "O serviço externo de IA limitou os pedidos (limite de uso do plano).",
        "Espere alguns segundos e tente de novo, ou use o motor local.",
    ),
    ServicoExternoFalhou: (
        502, "servico_externo_falhou",
        "O serviço externo de IA falhou ao responder.",
        "Tente de novo em instantes ou use o motor local.",
    ),
}

# erros em que o motivo exato ajuda quem está usando (vai em "detalhes")
COM_MOTIVO = (ModeloIndisponivel, MotorNaoConfigurado, RespostaInvalida, ServicoExternoFalhou, TempoEsgotado)

# tradução das mensagens de validação mais comuns do Pydantic
TRADUCOES = {
    "string_too_short": "texto curto demais (mínimo de {min_length} caracteres)",
    "string_too_long": "texto longo demais (máximo de {max_length} caracteres)",
    "missing": "campo obrigatório não enviado",
    "extra_forbidden": "campo não permitido nesta rota",
    "literal_error": "valor não aceito; use um destes: {expected}",
    "int_parsing": "precisa ser um número inteiro",
    "less_than_equal": "precisa ser no máximo {le}",
    "greater_than_equal": "precisa ser no mínimo {ge}",
    "json_invalid": "o corpo enviado não é um JSON válido",
    "model_attributes_type": "o corpo precisa ser um objeto JSON",
    "dict_type": "o corpo precisa ser um objeto JSON",
}


def resposta_erro(status, erro, mensagem, dica=None, detalhes=None, headers=None):
    corpo = {"status": status, "erro": erro, "mensagem": mensagem, "dica": dica, "detalhes": detalhes}
    return JSONResponse(status_code=status, content=corpo, headers=headers)


def _valor_recebido(item):
    # campo proibido pode ser justamente um dado pessoal (CPF, telefone): não devolvo o valor
    if item["type"] in ("missing", "extra_forbidden"):
        return None
    valor = item.get("input")
    if isinstance(valor, (str, int, float, bool, type(None), list, dict)):
        return valor
    return str(valor)


def _traduzir(item):
    modelo = TRADUCOES.get(item["type"])
    contexto = item.get("ctx") or {}
    if modelo:
        try:
            return modelo.format(**contexto).replace(" or ", " ou ")
        except (KeyError, IndexError):
            pass
    if item["type"] == "value_error":
        return str(contexto.get("error", item["msg"]))
    return item["msg"]


def registrar_tratadores(app: FastAPI):
    @app.exception_handler(ErroDoMotor)
    async def erro_do_motor(request: Request, exc: ErroDoMotor):
        status, codigo, mensagem, dica = MAPA_ERROS_MOTOR.get(
            type(exc), (500, "erro_no_modelo", "Falha ao usar o modelo de linguagem.", None)
        )
        headers = None
        if isinstance(exc, MotorOcupado):
            headers = {"Retry-After": "10"}
        elif isinstance(exc, LimiteDoServico):
            headers = {"Retry-After": str(exc.espera or 30)}
        detalhes = [{"motivo": str(exc)}] if isinstance(exc, COM_MOTIVO) and str(exc) else None
        log.warning("%s %s -> %s (%s)", request.method, request.url.path, status, exc)
        return resposta_erro(status, codigo, mensagem, dica, detalhes=detalhes, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def erro_de_validacao(request: Request, exc: RequestValidationError):
        detalhes = [
            {"campo": ".".join(str(p) for p in item["loc"] if p not in ("body", "path", "query")) or "corpo",
             "problema": _traduzir(item),
             "recebido": _valor_recebido(item)}
            for item in exc.errors()
        ]
        resumo = "; ".join(f"{d['campo']}: {d['problema']}" for d in detalhes)
        return resposta_erro(422, "dados_invalidos", f"Dados recusados - {resumo}",
                             "Confira os campos em /docs.", detalhes=detalhes)

    @app.exception_handler(StarletteHTTPException)
    async def erro_http(request: Request, exc: StarletteHTTPException):
        codigos = {404: "nao_encontrado", 405: "metodo_nao_permitido", 422: "dados_invalidos"}
        mensagem = exc.detail if isinstance(exc.detail, str) else "Pedido não atendido."
        if exc.status_code == 404 and mensagem == "Not Found":
            mensagem = f"A rota {request.url.path} não existe."
        dica = "Veja as rotas disponíveis em /docs." if exc.status_code in (404, 405) else None
        return resposta_erro(exc.status_code, codigos.get(exc.status_code, "erro_http"), mensagem, dica,
                             headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, exc: Exception):
        # o rastro completo vai para o log; o usuário recebe só uma mensagem clara
        log.exception("Erro inesperado em %s %s", request.method, request.url.path)
        return resposta_erro(500, "erro_interno",
                             "Aconteceu um erro inesperado ao processar o pedido.",
                             "Tente de novo. Se continuar, avise o responsável pela API.")


# documentação das respostas de erro de cada rota (aparece no /docs com um exemplo para cada código)
EXEMPLOS_DE_ERRO = {
    404: ("Não encontrado", "nao_encontrado", "Sem dados de saneamento para AC.", None),
    422: ("Dados inválidos", "dados_invalidos",
          "Dados recusados - texto: texto curto demais (mínimo de 15 caracteres)", "Confira os campos em /docs."),
    500: ("Erro inesperado", "erro_interno", "Aconteceu um erro inesperado ao processar o pedido.",
          "Tente de novo. Se continuar, avise o responsável pela API."),
    502: ("Resposta do modelo fora do formato", "resposta_invalida_do_modelo",
          MAPA_ERROS_MOTOR[RespostaInvalida][2], MAPA_ERROS_MOTOR[RespostaInvalida][3]),
    503: ("Modelo indisponível, ocupado ou sem memória", "modelo_indisponivel",
          MAPA_ERROS_MOTOR[ModeloIndisponivel][2], MAPA_ERROS_MOTOR[ModeloIndisponivel][3]),
    504: ("Modelo passou do tempo limite", "tempo_esgotado",
          MAPA_ERROS_MOTOR[TempoEsgotado][2], MAPA_ERROS_MOTOR[TempoEsgotado][3]),
}


def respostas_de_erro(*codigos):
    from api.modelos import Erro

    respostas = {}
    for codigo in codigos:
        descricao, erro, mensagem, dica = EXEMPLOS_DE_ERRO[codigo]
        exemplo = {"status": codigo, "erro": erro, "mensagem": mensagem, "dica": dica, "detalhes": None}
        respostas[codigo] = {"model": Erro, "description": descricao,
                             "content": {"application/json": {"example": exemplo}}}
    return respostas
