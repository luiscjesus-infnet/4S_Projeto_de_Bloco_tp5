"""
Funções usadas por várias páginas do painel Streamlit.

- leituras de dados com cache (são da aplicação inteira, então ficam em st.cache_data);
- estado da sessão (o que é de cada usuário fica em st.session_state);
- formatação de números no padrão brasileiro.
"""
import csv
import io

import streamlit as st

from src import dados, ibge

# filtros que eu quero que continuem valendo quando o usuário troca de página
CHAVES_PERSISTENTES = ["regioes", "indicador_panorama", "ufs_comparadas", "indicador_serie", "secao_noticias"]


def inicializar_estado():
    """
    Roda no app.py antes de qualquer página. Assim, quem abre o link direto de uma
    página (sem passar pelo início) também encontra o estado pronto.
    """
    padroes = {
        "regioes": list(dados.REGIOES),
        "indicador_panorama": "sem_agua_pct",
        "ufs_comparadas": ["MA", "PA", "SP"],
        "indicador_serie": "POP_SEM_AG%",
        "secao_noticias": "todas",
        "observacoes_enviadas": 0,
    }
    for chave, valor in padroes.items():
        st.session_state.setdefault(chave, valor)


def preservar_filtros():
    """
    O Streamlit apaga do session_state as chaves de widgets que não estão na tela.
    Regravar o valor nele mesmo faz o filtro sobreviver à troca de página.
    """
    for chave in CHAVES_PERSISTENTES:
        if chave in st.session_state:
            st.session_state[chave] = st.session_state[chave]


@st.cache_data(ttl=3600, show_spinner="Consultando a API do IBGE...")
def obter_ufs():
    return ibge.carregar_ufs()


@st.cache_data(ttl=3600)
def obter_saneamento():
    ufs, _ = obter_ufs()
    return dados.carregar_saneamento(ufs)


@st.cache_data(ttl=3600)
def obter_serie():
    ufs, _ = obter_ufs()
    return dados.carregar_serie(ufs)


@st.cache_data(ttl=3600)
def obter_noticias():
    return dados.carregar_noticias()


@st.cache_resource(ttl=3600)
def obter_base_fatos():
    """Perfis das UFs, tendência, metas e índice de prioridade (src/analise.py e src/fatos.py)."""
    from src.fatos import BaseDeFatos

    return BaseDeFatos()


def texto_meta(ano, situacao):
    """Situação da meta de 2033 numa expressão curta para tabela."""
    if situacao == "cumpre":
        return "já cumpre"
    if situacao == "nao_chega":
        return "não chega no ritmo atual"
    if situacao == "no_prazo":
        return f"{ano} (no prazo)"
    if situacao == "atrasada":
        return f"{ano} (+{ano - 2033} anos)"
    return "-"


def fmt(valor, casas=1, sufixo=""):
    if valor is None:
        return "-"
    texto = f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return texto + sufixo


def para_csv(linhas):
    """Lista de dicionários -> bytes de um CSV (para o botão de download)."""
    if not linhas:
        return b""
    # junto as colunas de todas as linhas, porque nem todo registro tem os mesmos campos
    colunas = list(dict.fromkeys(chave for linha in linhas for chave in linha))
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, fieldnames=colunas, restval="")
    escritor.writeheader()
    escritor.writerows(linhas)
    return saida.getvalue().encode("utf-8-sig")
