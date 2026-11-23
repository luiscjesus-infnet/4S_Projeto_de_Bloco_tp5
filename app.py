"""
Painel ODS 6 - Saneamento por UF.

Este arquivo é só o "roteador": monta o menu, prepara o estado da sessão e chama a
página escolhida. Cada análise mora no seu próprio arquivo dentro de paginas/.

Rodar a partir da raiz do projeto:
    streamlit run app.py
"""
import streamlit as st

from src.comum import inicializar_estado, obter_ufs, preservar_filtros
from src.dados import info_fontes

st.set_page_config(page_title="Painel ODS 6 - Saneamento", page_icon="💧", layout="wide")

# tudo que fica antes do pg.run() roda em qualquer página
inicializar_estado()
preservar_filtros()

paginas = {
    "Painel": [
        st.Page("paginas/inicio.py", title="Início", icon="🏠", default=True),
        st.Page("paginas/panorama.py", title="Panorama por UF", icon="📊"),
        st.Page("paginas/evolucao.py", title="Evolução 2010-2024", icon="📈"),
        st.Page("paginas/noticias.py", title="Notícias e termos", icon="📰"),
    ],
    "Dados": [
        st.Page("paginas/api_projeto.py", title="API do projeto", icon="🔌"),
        st.Page("paginas/arquivos.py", title="Enviar e baixar arquivos", icon="📂"),
    ],
    "Inteligência artificial": [
        st.Page("paginas/analise_ia.py", title="Análise de texto com IA", icon="🧠"),
        st.Page("paginas/preparacao_ia.py", title="Dados preparados para IA", icon="🤖"),
    ],
}

pg = st.navigation(paginas)

# rodapé da barra lateral, igual em todas as páginas
_, origem_ibge = obter_ufs()
with st.sidebar:
    st.divider()
    st.caption("**Fontes:** Painel Saneamento Brasil (Instituto Trata Brasil), IBGE e Agência Brasil.")
    st.caption(f"Dados das UFs: {origem_ibge}.")
    atualizacao = [f["atualizado_em"] for f in info_fontes() if f["tecnica"] == "Selenium"]
    if atualizacao and atualizacao[0]:
        st.caption(f"Última coleta da série histórica: {atualizacao[0]}.")
    st.caption("Projeto de Bloco - INFNET - TP4")

pg.run()
