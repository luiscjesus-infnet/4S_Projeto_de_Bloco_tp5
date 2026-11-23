"""
Rotas de dados (vieram do TP3). No TP4 ganharam response_model e erros no formato padrão.
Elas não dependem do modelo de linguagem: continuam funcionando mesmo se ele não carregar.
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.erros import respostas_de_erro
from api.modelos import (
    Fonte,
    Indicador,
    IndicadorSerie,
    LinhaSaneamento,
    ListaNoticias,
    ListaObservacoes,
    ListaSaneamento,
    NovaObservacao,
    ObservacaoCriada,
    Ranking,
    Regiao,
    Serie,
    Sigla,
)
from src import dados

roteador = APIRouter()


@roteador.get("/fontes", response_model=list[Fonte], tags=["Informações"], summary="Origem dos dados")
def fontes():
    """De onde vem cada conjunto de dados, quantas linhas tem e quando foi atualizado."""
    return dados.info_fontes()


@roteador.get("/saneamento", response_model=ListaSaneamento, tags=["Saneamento"],
              summary="Indicadores de todas as UFs", responses=respostas_de_erro(422))
def listar_saneamento(
    regiao: Optional[Regiao] = Query(default=None, description="Filtra por região"),
    ordenar_por: Indicador = Query(default="sem_agua_pct", description="Indicador usado na ordenação"),
):
    """Indicadores do ano mais recente para todas as UFs (ou só de uma região)."""
    linhas = dados.carregar_saneamento()
    if regiao:
        linhas = [l for l in linhas if l["regiao"] == regiao]
    ordenado = dados.ranking(linhas, ordenar_por, limite=len(linhas))
    return {"total": len(ordenado), "ordenado_por": ordenar_por, "dados": ordenado}


# rota fixa declarada ANTES da rota com {sigla}; se fosse depois, "ranking" seria lido como sigla
@roteador.get("/saneamento/ranking", response_model=Ranking, tags=["Saneamento"],
              summary="UFs em pior situação", responses=respostas_de_erro(422))
def ranking_prioridade(
    indicador: Indicador = Query(default="sem_agua_pct"),
    limite: int = Query(default=5, ge=1, le=27, description="Quantas UFs devolver"),
):
    """UFs em pior situação no indicador escolhido (as candidatas a receber investimento primeiro)."""
    linhas = dados.carregar_saneamento()
    return {
        "indicador": indicador,
        "descricao": dados.INDICADORES[indicador],
        "ranking": [
            {"posicao": i + 1, "sigla": l["sigla"], "uf_nome": l["uf_nome"], "valor": l[indicador]}
            for i, l in enumerate(dados.ranking(linhas, indicador, limite))
        ],
    }


@roteador.get("/saneamento/{sigla}", response_model=LinhaSaneamento, tags=["Saneamento"],
              summary="Indicadores de uma UF", responses=respostas_de_erro(404, 422))
def detalhe_uf(sigla: Sigla):
    """Todos os indicadores de uma UF no ano mais recente."""
    for linha in dados.carregar_saneamento():
        if linha["sigla"] == sigla:
            return linha
    raise HTTPException(status_code=404, detail=f"Sem dados de saneamento para {sigla}.")


@roteador.get("/serie/{sigla}", response_model=Serie, tags=["Série histórica"],
              summary="Evolução 2010-2024 de uma UF", responses=respostas_de_erro(404, 422))
def serie_uf(
    sigla: Sigla,
    indicador: IndicadorSerie = Query(default="POP_SEM_AG%"),
    desde: int = Query(default=2010, ge=2010, le=2024),
    ate: int = Query(default=2024, ge=2010, le=2024),
):
    """Evolução anual de um indicador para a UF (dados coletados com Selenium)."""
    if desde > ate:
        raise HTTPException(status_code=422, detail="'desde' não pode ser maior que 'ate'.")
    pontos = dados.filtrar_serie(dados.carregar_serie(), sigla=sigla, indicador=indicador, desde=desde, ate=ate)
    if not pontos:
        raise HTTPException(status_code=404, detail="Nenhum valor encontrado para esse filtro.")
    return {
        "sigla": sigla,
        "indicador": indicador,
        "descricao": dados.INDICADORES_SERIE[indicador],
        "pontos": [{"ano": p["ano"], "valor": p["valor"]} for p in pontos],
    }


@roteador.get("/noticias", response_model=ListaNoticias, tags=["Notícias"],
              summary="Notícias coletadas", responses=respostas_de_erro(422))
def listar_noticias(
    tema_ods6: Optional[Literal["sim", "nao"]] = Query(default=None, description="Só notícias ligadas a água/saneamento"),
    secao: Optional[Literal["meio-ambiente", "saude"]] = None,
    limite: int = Query(default=10, ge=1, le=50),
    incluir_texto: bool = Query(default=False, description="Devolve também o texto completo"),
):
    """Notícias coletadas da Agência Brasil (conteúdo Creative Commons, sempre com o link de origem)."""
    noticias = dados.carregar_noticias()
    if tema_ods6:
        noticias = [n for n in noticias if n["tema_ods6"] == tema_ods6]
    if secao:
        noticias = [n for n in noticias if n["secao"] == secao]
    campos = ["secao", "titulo", "url", "publicado_em", "resumo", "tema_ods6"] + (["texto"] if incluir_texto else [])
    return {"total": len(noticias[:limite]), "noticias": [{c: n.get(c) for c in campos} for n in noticias[:limite]]}


@roteador.get("/observacoes", response_model=ListaObservacoes, tags=["Observações"],
              summary="Observações enviadas", responses=respostas_de_erro(422))
def listar_observacoes(sigla: Optional[Sigla] = None):
    """Observações enviadas por usuários (o que chega pelo POST)."""
    obs = dados.ler_observacoes()
    if sigla:
        obs = [o for o in obs if o["sigla"] == sigla]
    return {"total": len(obs), "observacoes": obs}


@roteador.post("/observacoes", status_code=201, response_model=ObservacaoCriada, tags=["Observações"],
               summary="Enviar uma observação", responses=respostas_de_erro(422))
def criar_observacao(nova: NovaObservacao):
    """
    Recebe uma observação sobre uma UF (informação de campo, correção ou sugestão) e grava
    em data/processed/observacoes.csv. O texto pode depois ser analisado em POST /processar_texto.
    """
    registro = dados.salvar_observacao(nova.sigla, nova.autor, nova.tipo, nova.texto)
    return {"mensagem": "Observação registrada.", "observacao": registro}
