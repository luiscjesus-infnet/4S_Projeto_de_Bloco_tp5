# Painel ODS 6 - água e esgoto por UF

Projeto de Bloco: Inteligência Artificial Aplicada (INFNET) - TP4
Autor: Luis Claudio de Jesus

**Pergunta que o projeto responde:** em quais UFs o investimento em água e esgoto deveria chegar primeiro, considerando a cobertura atual, a evolução desde 2010 e o impacto na saúde?

- Painel em Streamlit com 8 páginas e menu de navegação
- API em FastAPI com consultas (GET), envio de observações (POST) e **análise de texto com modelo de linguagem local** (POST `/processar_texto`)
- Modelo **Qwen2.5-1.5B-Instruct** rodando na própria máquina com HuggingFace Transformers, sem serviço externo nem chave de API
- Coleta com API do IBGE, BeautifulSoup (páginas estáticas) e Selenium (página dinâmica)

A documentação completa do TP4 (respostas dos itens 1 a 4, com o benchmark que justificou a escolha do modelo) está em [`docs/TP4_Luis_Claudio_de_Jesus.md`](docs/TP4_Luis_Claudio_de_Jesus.md). A do TP3 continua em [`docs/TP3_Luis_Claudio_de_Jesus.md`](docs/TP3_Luis_Claudio_de_Jesus.md).

## Estrutura

```
app.py                  roteador do Streamlit (menu, estado comum, rodapé)
paginas/                uma página por análise (analise_ia.py é a nova do TP4)
api/main.py             cria a API, carrega o modelo uma vez (lifespan) e registra rotas e erros
api/modelos.py          modelos Pydantic de entrada, saída e erro (response models)
api/erros.py            tratamento de erros: cada falha vira um código HTTP e uma mensagem clara
api/rotas/              rotas de dados (TP3) e rotas do modelo de linguagem (TP4)
src/motor_llm.py        carrega o modelo local e faz tema, sentimento e resumo
src/baixar_modelo.py    baixa o modelo do HuggingFace para modelos/ (uma vez só)
src/benchmark_llm.py    compara os modelos candidatos no banco de provas
src/testar_api.py       roteiro de testes com a API rodando (cronômetro, erros, pedidos simultâneos)
src/                    coleta, leitura de dados, validação, cliente da API, preparo para LLM
data/avaliacao/         banco de provas rotulado e resultados do benchmark
data/processed/         arquivos que o painel e a API leem
modelos/                pesos dos modelos (fora do Git, vários GB)
docs/                   documentação do TP3 e do TP4, Project Charter e Data Summary Report
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
uvicorn api.main:app                # http://127.0.0.1:8000/docs  (sobe em ~10 s carregando o modelo)
streamlit run app.py                # http://localhost:8501  -> menu "Análise de texto com IA"
```

Testes e benchmark:

```
python -m src.testar_api            # com a API rodando: 21 chamadas cronometradas e conferidas
python -m src.baixar_modelo --todos # baixa também os outros candidatos (~8 GB)
python -m src.benchmark_llm         # refaz a comparação (~40 min só em CPU)
```

Máquina com pouca memória (8 GB): `set LLM_PRECISAO=bfloat16` antes do `uvicorn` usa metade da memória, mas cada análise fica bem mais lenta (ver item 1.6 do documento). Não recomendo o modelo de 0.5B: ele cabe, mas acertou só 8 de 48 temas no meu teste.
Sem o modelo, a API sobe do mesmo jeito: só a rota `/processar_texto` responde 503 e as outras funcionam.

## Rotas da API

| Método | Rota | Para que serve |
|---|---|---|
| GET | `/` | descrição, situação do modelo e lista de rotas |
| GET | `/fontes` | origem, técnica, linhas e data de cada conjunto de dados |
| GET | `/saneamento` | indicadores de todas as UFs (filtro por região, ordenação) |
| GET | `/saneamento/ranking` | UFs em pior situação num indicador |
| GET | `/saneamento/{sigla}` | indicadores de uma UF |
| GET | `/serie/{sigla}` | evolução 2010-2024 de um indicador |
| GET | `/noticias` | notícias coletadas (filtros por tema e seção) |
| GET | `/observacoes` | observações enviadas |
| POST | `/observacoes` | envia uma observação sobre uma UF |
| **POST** | **`/processar_texto`** | **tema, sentimento ou resumo de um texto com o modelo local** |
| **GET** | **`/modelo`** | **se o modelo carregou, qual é, onde roda e o motivo de falha** |

## Fontes

- [Painel Saneamento Brasil](https://www.painelsaneamento.org.br) - Instituto Trata Brasil (`robots.txt` permite a coleta)
- [API de serviços de dados do IBGE](https://servicodados.ibge.gov.br/api/docs)
- [Agência Brasil](https://agenciabrasil.ebc.com.br) - conteúdo sob licença Creative Commons, sempre com o link da notícia original
- [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) - modelo de linguagem (licença Apache 2.0)
