# Painel ODS 6 - água e esgoto por UF

Projeto de Bloco: Inteligência Artificial Aplicada (INFNET) - TP5 (versão final do projeto)
Autor: Luis Claudio de Jesus

**Pergunta que o projeto responde:** em quais UFs o investimento em água e esgoto deveria chegar primeiro, considerando a cobertura atual, a evolução desde 2010 e o impacto na saúde?

- **Coleta**: API do IBGE, BeautifulSoup (páginas estáticas) e Selenium (página dinâmica)
- **Análise** em Python: tendência 2010-2024, ano projetado para a meta do Marco Legal do Saneamento (2033) e índice de prioridade por UF
- **IA**: assistente com **memória da conversa** (Opção 1 do TP5) e tema, sentimento e resumo das notícias, com o modelo **Qwen2.5-1.5B-Instruct rodando na própria máquina**; o assistente também pode usar um serviço externo compatível com a OpenAI (chave no `.env`)
- **Apresentação**: painel Streamlit com 10 páginas e API FastAPI com 13 rotas

A documentação do TP5 (tarefas 1 a 4, avaliação da memória e argumentação) está em [`docs/TP5_Luis_Claudio_de_Jesus.md`](docs/TP5_Luis_Claudio_de_Jesus.md). Os artefatos do TDSP estão em [`docs/project_charter.md`](docs/project_charter.md) e [`docs/data_summary_report.md`](docs/data_summary_report.md). As entregas anteriores continuam em `docs/TP3_...md` e `docs/TP4_...md`.

## Estrutura

```
app.py                  roteador do Streamlit (menu, estado comum, rodapé)
paginas/                uma página por análise (assistente.py, prioridades.py e como_funciona_ia.py são do TP5)
api/main.py             cria a API e prepara os motores de IA e o assistente uma vez (lifespan)
api/modelos.py          modelos Pydantic de entrada, saída e erro
api/erros.py            cada falha vira um código HTTP e uma mensagem clara
api/rotas/              dados, análise de texto (TP4) e assistente com memória (TP5)
src/analise.py          tendência, meta de 2033 e índice de prioridade (só Python)
src/fatos.py            os números em frases curtas, que é o que o modelo lê
src/memoria.py          notas da conversa e estratégias de memória
src/assistente.py       escolhe os fatos, monta o pedido, chama o motor e confere os números
src/motor_llm.py        modelo local (HuggingFace Transformers)
src/motor_api.py        serviço externo compatível com a OpenAI (requests)
src/avaliar_memoria.py  conversa de 10 perguntas com gabarito para cada estratégia de memória
src/classificar_noticias.py  tema, sentimento e resumo das notícias em lote
src/provedor_simulado.py     serviço de IA de mentira para testar os erros do motor via API
src/                    coletas, leitura de dados, cliente da API, testes
data/processed/         arquivos que o painel e a API leem
data/avaliacao/         banco de provas (TP4), conversa de teste e resultados (TP5)
modelos/                pesos dos modelos (fora do Git, vários GB)
docs/                   documentação dos TPs, Project Charter e Data Summary Report
```

## Como rodar

Python 3.11 ou mais novo (usei 3.14). Na raiz do projeto:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements-coleta.txt -r requirements-llm.txt
python -m src.baixar_modelo          # baixa o Qwen2.5-1.5B-Instruct (~3 GB) para modelos/
```

API (terminal 1) e painel (terminal 2):

```
uvicorn api.main:app                # http://127.0.0.1:8000/docs
streamlit run app.py                # http://localhost:8501  -> menu "Assistente do painel"
```

**Serviço externo de IA (opcional):** copie `.env.exemplo` para `.env`, preencha `LLM_API_CHAVE` e `LLM_API_MODELO` (e `LLM_API_URL`, se não for o OpenRouter) e reinicie a API. O painel passa a oferecer os dois motores. Sem `.env`, tudo funciona com o modelo local. O `.env` está no `.gitignore`.

Atualizar os dados e refazer as análises (opcional):

```
python -m src.coleta_painel          # indicadores por UF (BeautifulSoup)
python -m src.coleta_dinamica        # série 2010-2024 (Selenium)
python -m src.coleta_noticias        # notícias (acumula, 10 s entre páginas)
python -m src.classificar_noticias   # tema, sentimento e resumo das notícias novas
python -m src.avaliar_memoria        # avaliação da memória (~20 min em CPU)
python -m src.testar_api             # com a API rodando
```

## Rotas da API

| Método | Rota | Para que serve |
|---|---|---|
| GET | `/` | descrição, motores prontos e lista de rotas |
| GET | `/fontes` | origem, técnica, linhas e data de cada conjunto de dados |
| GET | `/saneamento` | indicadores de todas as UFs (filtro por região, ordenação) |
| GET | `/saneamento/ranking` | UFs em pior situação num indicador |
| GET | `/saneamento/{sigla}` | indicadores de uma UF |
| GET | **`/prioridades`** | **índice de prioridade com pesos ajustáveis, metas de 2033 e motivos** |
| GET | `/serie/{sigla}` | evolução 2010-2024 de um indicador |
| GET | `/noticias` | notícias coletadas |
| GET/POST | `/observacoes` | observações enviadas por usuários |
| POST | `/processar_texto` | tema, sentimento ou resumo de um texto com o modelo local |
| GET | `/modelo` | situação do modelo local |
| POST | **`/conversar`** | **assistente com memória: pergunta + histórico + notas -> resposta + notas atualizadas** |
| GET | **`/motores`** | **motores de IA prontos (local e serviço externo) e o motivo de quem não está** |

## Fontes

- [Painel Saneamento Brasil](https://www.painelsaneamento.org.br) - Instituto Trata Brasil (`robots.txt` permite a coleta)
- [API de serviços de dados do IBGE](https://servicodados.ibge.gov.br/api/docs)
- [Agência Brasil](https://agenciabrasil.ebc.com.br) - conteúdo sob licença Creative Commons, sempre com o link da notícia original
- [Lei 14.026/2020 - Marco Legal do Saneamento](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14026.htm) - metas de 2033
- [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) - modelo de linguagem (licença Apache 2.0)
