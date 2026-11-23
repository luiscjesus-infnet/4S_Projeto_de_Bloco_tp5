"""
Modelos (Pydantic) de tudo que entra e sai da API.

Ficam num arquivo só para servirem de "contrato": quem consome a API olha aqui (ou
no /docs, que é gerado a partir daqui) e sabe exatamente o formato de cada resposta.
Toda rota declara o seu response_model, então o FastAPI confere a resposta antes de
enviar: se faltar campo ou vier tipo errado, o erro aparece do meu lado, não no cliente.
"""
import re
from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.motor_llm import SENTIMENTOS, TEMAS

# ------------------------------------------------------------------ listas fechadas
Sigla = Literal[
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
Regiao = Literal["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]
Indicador = Literal[
    "sem_agua_pct", "sem_esgoto_pct", "esgoto_tratado_pct", "internacoes_vh", "obitos_vh",
    "internacoes_10mil", "pessoas_sem_agua", "receita_media_agua",
    "renda_com_saneamento", "renda_sem_saneamento",
]
IndicadorSerie = Literal["POP_SEM_AG%", "POP_SEM_ES%", "INCIDE_VH"]

TipoAnalise = Literal["tema", "sentimento", "resumo"]
Tema = Literal["abastecimento", "qualidade", "esgoto", "saude", "investimento", "outro"]
Sentimento = Literal["positivo", "negativo", "neutro"]

# se alguém mudar as categorias do motor e esquecer daqui, a API nem sobe
assert set(Tema.__args__) == set(TEMAS), "Tema (API) e TEMAS (motor) estão diferentes"
assert set(Sentimento.__args__) == set(SENTIMENTOS), "Sentimento (API) e SENTIMENTOS (motor) estão diferentes"


# ------------------------------------------------------------------ erro padrão
class Erro(BaseModel):
    """Formato único de erro em toda a API."""
    status: int = Field(description="Código HTTP")
    erro: str = Field(description="Código curto do problema, bom para o programa cliente tratar")
    mensagem: str = Field(description="Explicação para o usuário")
    dica: Optional[str] = Field(default=None, description="O que fazer para resolver")
    detalhes: Optional[list[dict]] = Field(default=None, description="Campos com problema (só nos erros 422)")

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "status": 503, "erro": "modelo_indisponivel",
        "mensagem": "O modelo de linguagem não está carregado, então esta análise não pode ser feita agora.",
        "dica": "Rode python -m src.baixar_modelo e reinicie a API. As outras rotas continuam funcionando.",
        "detalhes": None,
    }]})


# ------------------------------------------------------------------ processamento de texto (LLM)
class PedidoProcessamento(BaseModel):
    """Corpo do POST /processar_texto."""
    model_config = ConfigDict(
        extra="forbid",               # campo a mais é recusado (evita dado pessoal entrar sem querer)
        str_strip_whitespace=True,    # espaços nas pontas não contam no tamanho
        json_schema_extra={"examples": [{
            "texto": "Tem esgoto correndo a céu aberto na rua principal do bairro, bem na frente da creche.",
            "tipo_analise": "tema",
        }]},
    )

    texto: str = Field(min_length=15, max_length=5000, description="Texto a analisar (15 a 5.000 caracteres)")
    tipo_analise: TipoAnalise = Field(
        default="tema",
        description="tema = assunto de saneamento; sentimento = tom do texto; resumo = até 3 frases",
    )

    @field_validator("texto")
    @classmethod
    def precisa_ter_palavras(cls, valor):
        if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", valor)) < 3:
            raise ValueError("o texto precisa ter pelo menos 3 palavras")
        return valor


class InfoModelo(BaseModel):
    nome: str = Field(description="Modelo do HuggingFace usado")
    dispositivo: Literal["cpu", "cuda"]
    precisao: str = Field(description="Tipo numérico dos pesos (float32, bfloat16...)")


class ResultadoTema(BaseModel):
    tipo: Literal["tema"] = "tema"
    categoria: Tema
    descricao: str = Field(description="O que a categoria cobre")
    confianca: float = Field(ge=0, le=1, description="Pontuação da categoria escolhida (não é chance de acerto)")
    pontuacoes: dict[Tema, float] = Field(description="Pontuação de todas as categorias (somam 1)")


class ResultadoSentimento(BaseModel):
    tipo: Literal["sentimento"] = "sentimento"
    sentimento: Sentimento
    confianca: float = Field(ge=0, le=1, description="Pontuação do tom escolhido (não é chance de acerto)")
    pontuacoes: dict[Sentimento, float]


class ResultadoResumo(BaseModel):
    tipo: Literal["resumo"] = "resumo"
    resumo: str = Field(min_length=10, max_length=1200)
    frases: int = Field(ge=1)
    tokens_gerados: int = Field(ge=1)


Resultado = Annotated[Union[ResultadoTema, ResultadoSentimento, ResultadoResumo], Field(discriminator="tipo")]


class RespostaProcessamento(BaseModel):
    """Resposta do POST /processar_texto."""
    tipo_analise: TipoAnalise
    texto_processado: str = Field(description="Texto que foi para o modelo, já sem espaços sobrando")
    caracteres: int
    tokens_entrada: int = Field(description="Tamanho do texto em tokens do modelo")
    texto_truncado: bool = Field(description="True se o texto passou do limite e só o começo foi analisado")
    resultado: Resultado
    modelo: InfoModelo
    segundos: float = Field(description="Tempo gasto pelo modelo")
    processado_em: datetime
    aviso: Optional[str] = None

    @model_validator(mode="after")
    def tipo_bate_com_resultado(self):
        if self.resultado.tipo != self.tipo_analise:
            raise ValueError(f"pedido de '{self.tipo_analise}', mas o resultado é de '{self.resultado.tipo}'")
        return self

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "tipo_analise": "tema",
        "texto_processado": "Tem esgoto correndo a céu aberto na rua principal do bairro, bem na frente da creche.",
        "caracteres": 86, "tokens_entrada": 21, "texto_truncado": False,
        "resultado": {"tipo": "tema", "categoria": "esgoto",
                      "descricao": TEMAS["esgoto"], "confianca": 0.97,
                      "pontuacoes": {"esgoto": 0.97, "saude": 0.01, "outro": 0.01, "qualidade": 0.005,
                                     "abastecimento": 0.003, "investimento": 0.002}},
        "modelo": {"nome": "Qwen/Qwen2.5-1.5B-Instruct", "dispositivo": "cpu", "precisao": "float32"},
        "segundos": 1.9, "processado_em": "2026-11-16T21:40:00",
        "aviso": None,
    }]})


class StatusModelo(BaseModel):
    """Resposta do GET /modelo."""
    carregado: bool
    nome: str
    dispositivo: Optional[str] = None
    precisao: Optional[str] = None
    parametros_milhoes: Optional[int] = None
    segundos_carregando: Optional[float] = None
    analises: list[TipoAnalise]
    tempo_limite_s: float
    max_tokens_entrada: int
    erro: Optional[str] = Field(default=None, description="Por que o modelo não carregou (se for o caso)")


# ------------------------------------------------------------------ rotas de dados (vieram do TP3)
class Raiz(BaseModel):
    mensagem: str
    documentacao: str
    modelo_carregado: bool
    rotas: list[str]


class Fonte(BaseModel):
    conjunto: str
    arquivo: str
    tecnica: str
    linhas: int
    atualizado_em: Optional[str] = None


class LinhaSaneamento(BaseModel):
    sigla: str
    uf_nome: str
    regiao: str
    ano: Optional[int] = None
    populacao: Optional[int] = None
    sem_agua_pct: Optional[float] = None
    sem_esgoto_pct: Optional[float] = None
    esgoto_tratado_pct: Optional[float] = None
    internacoes_vh: Optional[float] = None
    obitos_vh: Optional[float] = None
    internacoes_10mil: Optional[float] = None
    pessoas_sem_agua: Optional[int] = None
    receita_media_agua: Optional[float] = None
    renda_com_saneamento: Optional[float] = None
    renda_sem_saneamento: Optional[float] = None


class ListaSaneamento(BaseModel):
    total: int
    ordenado_por: Indicador
    dados: list[LinhaSaneamento]


class PosicaoRanking(BaseModel):
    posicao: int
    sigla: str
    uf_nome: str
    valor: Optional[float] = None


class Ranking(BaseModel):
    indicador: Indicador
    descricao: str
    ranking: list[PosicaoRanking]


class PontoSerie(BaseModel):
    ano: int
    valor: Optional[float] = None


class Serie(BaseModel):
    sigla: Sigla
    indicador: IndicadorSerie
    descricao: str
    pontos: list[PontoSerie]


class Noticia(BaseModel):
    secao: str
    titulo: str
    url: str
    publicado_em: Optional[str] = None
    resumo: Optional[str] = None
    tema_ods6: Optional[str] = None
    texto: Optional[str] = None


class ListaNoticias(BaseModel):
    total: int
    noticias: list[Noticia]


class NovaObservacao(BaseModel):
    """Corpo do POST /observacoes."""
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{
            "sigla": "MA",
            "autor": "Técnica da ONG",
            "tipo": "campo",
            "texto": "Bairros da periferia de São Luís seguem com abastecimento em dias alternados.",
        }]},
    )

    sigla: Sigla = Field(description="UF a que a observação se refere")
    autor: str = Field(min_length=2, max_length=60, description="Nome de quem envia")
    tipo: Literal["campo", "correcao", "sugestao"] = Field(
        default="campo", description="campo = informação local; correcao = dado errado; sugestao = ideia"
    )
    texto: str = Field(min_length=10, max_length=600, description="Conteúdo da observação")


class Observacao(BaseModel):
    id: int
    sigla: Sigla
    autor: str
    tipo: Literal["campo", "correcao", "sugestao"]
    texto: str
    enviado_em: str


class ListaObservacoes(BaseModel):
    total: int
    observacoes: list[Observacao]


class ObservacaoCriada(BaseModel):
    mensagem: str
    observacao: Observacao
