# Project Charter - Painel ODS 6 (revisão do TP5)

**Autor:** Luis Claudio de Jesus · Projeto de Bloco: IA Aplicada (INFNET)

Histórico: versão inicial no TP1, revisada no TP3 (pergunta de negócio afiada) e no TP4 (escolha do modelo de linguagem, em `TP4_Luis_Claudio_de_Jesus.md`, item 1). Nesta revisão, fecho o ciclo: o objetivo do TP3 ("gerar o resumo de prioridades em texto com LLM") virou um assistente com memória, apoiado em análises feitas em Python.

| Campo | Conteúdo |
|---|---|
| **Nome** | Painel ODS 6 - água e esgoto por UF |
| **ODS atendido** | ODS 6 - Água potável e saneamento (metas 6.1 acesso à água, 6.2 esgotamento sanitário e 6.3 tratamento de efluentes). Ligação com o ODS 3 (meta 3.3, doenças transmitidas pela água), por isso trago internações e óbitos por doenças de veiculação hídrica. |
| **Ligação com ESG** | **S** (social): acesso a água e esgoto é condição de saúde e dignidade; **G** (governança): ajuda a decidir com critério explícito e auditável onde vai o recurso público e a acompanhar a meta legal de 2033; **E** (ambiental): esgoto sem coleta e sem tratamento vai para rios e solo. |
| **Por que esse ODS** | Em 2024, 34,2 milhões de pessoas no Brasil ainda não tinham acesso à água e, na média das UFs, 58,4% da população não tinha coleta de esgoto. É um problema concreto, medido e com dado público. |
| **Problema** | O recurso para saneamento é limitado e a escolha de onde investir costuma ser feita sem juntar, num lugar só, cobertura, tendência e efeito na saúde. Além disso, quem prepara o material para o gestor gasta tempo cruzando tabelas para responder perguntas simples ("e em 2010?", "e no estado vizinho?"). |
| **Pergunta de negócio** | Em quais UFs o investimento em água e esgoto deveria chegar primeiro, considerando cobertura atual, evolução desde 2010 e impacto na saúde? |
| **Objetivo** | Entregar um painel e uma API que mostrem, em poucos cliques, as UFs prioritárias e a justificativa com números, e um assistente que responda em português perguntas encadeadas sobre esses dados, sem inventar números. |
| **Dentro do escopo** | 27 UFs; indicadores de água, esgoto e saúde; série 2010-2024; projeção até a meta de 2033; índice de prioridade; notícias de meio ambiente e saúde com tema e resumo feitos por IA; assistente com memória da conversa; API de consulta. |
| **Fora do escopo** | Nível municipal; custo das obras e investimento já contratado; previsão com modelo estatístico (uso tendência linear); integração com sistemas oficiais; base de documentos longos para o assistente consultar (RAG). |
| **Usuário (quem usa)** | Analista de ONG ou de secretaria estadual/municipal que prepara material para decisão. |
| **Decisor (quem decide)** | Gestor público ou diretor da ONG que define onde o recurso vai primeiro. |
| **Stakeholders** | População das UFs com menor cobertura (beneficiária final); secretarias de saneamento e de saúde; companhias de saneamento; Instituto Trata Brasil e IBGE (fontes); órgãos de controle que acompanham o Marco Legal do Saneamento. |
| **Metodologia** | TDSP, com todas as etapas percorridas (tabela abaixo). |

## Como os dados, a IA e a engenharia de prompt resolvem o problema

O problema tem duas partes, e cada uma pede uma ferramenta diferente:

1. **Decidir a ordem das UFs** exige conta: tendência de 15 anos, projeção até 2033, normalização e pesos. Isso é determinístico e precisa ser auditável, então ficou em Python (`src/analise.py`). O resultado é o índice de prioridade e a lista de motivos de cada UF. Nenhuma parte da decisão depende do modelo de linguagem.
2. **Explicar e explorar a decisão** é linguagem: o analista quer perguntar "por que o Maranhão está em primeiro?", depois "e em 2010?", depois "e o Pará?". Aqui entra o modelo de linguagem, com **memória da conversa** para entender "ele", "lá" e "esse número".

A engenharia de prompt é o que liga as duas partes. Em vez de mandar a tabela para o modelo e torcer para ele calcular certo, o Python escreve os **fatos já calculados** em frases curtas, escolhe só os que interessam à pergunta e monta um pedido com instruções claras ("use só os fatos", "não faça contas", "diga a UF e o ano", "se não estiver nos fatos, diga que o painel não tem esse dado"). Medi o efeito disso: com a mesma memória, o modelo acertou 8 de 10 perguntas recebendo os fatos e 0 de 10 recebendo a tabela crua (item 2.8 do documento do TP5).

Por que isso importa em Ciência de Dados: o modelo de linguagem é a última camada, não a primeira. A qualidade da resposta depende da coleta (dados reais e atualizáveis), do tratamento (UFs casadas, números convertidos, saltos suspeitos marcados) e da análise. O modelo só torna o resultado acessível a quem não vai abrir uma planilha.

## Metas e indicadores de sucesso (KPIs)

| Meta (SMART) | Indicador | Situação |
|---|---|---|
| Cobrir as 27 UFs com os indicadores de água, esgoto e saúde do ano mais recente até o TP3 | UFs com dado completo | 27 de 27 (2024) ✅ |
| Ter a série 2010-2024 de pelo menos 3 indicadores para todas as UFs até o TP3 | valores coletados | 1.215 de 1.215 ✅ |
| Usuário chegar ao ranking de prioridade em até 2 cliques a partir da página inicial | cliques | 1 clique (card "A resposta curta" ou menu "Prioridades de investimento") ✅ |
| Disponibilizar os dados para outro sistema sem raspagem | rotas documentadas na API | 13 rotas, todas com response model ✅ |
| Gerar um resumo de prioridades que o gestor leia em menos de 1 minuto (TP5) | tamanho do texto | 3 UFs com até 3 motivos cada na página inicial; resposta do assistente limitada a 3 frases ✅ |
| Assistente acertar pelo menos 8 de 10 perguntas encadeadas na conversa de teste (TP5) | acertos com gabarito | 8 de 10 com o modelo local ✅ |
| Tamanho do pedido ao modelo não crescer com a conversa (TP5) | tokens na 10ª pergunta / 1ª pergunta | 907 → 1.094 tokens (1,2×); na conversa inteira, 907 → 1.327 (1,5×) e subindo ✅ |
| Resposta do assistente em até 30 s numa máquina comum, só CPU (TP5) | mediana de segundos por resposta | 11,6 s ✅ |
| Toda notícia coletada com tema e resumo automáticos (TP5) | notícias processadas / coletadas | 40 de 40 ✅ |

## Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Site muda o HTML e o scraping para de funcionar | coleta quebra | coleta separada do painel; o painel lê o CSV já salvo; coletores avisam quando a tabela não tem 27 UFs |
| API do IBGE fora do ar | painel sem população | cópia local em `ufs_ibge.json` e aviso da origem na barra lateral |
| Mudança de método na fonte (saltos de mais de 10 pontos, ex.: AP e PI em 2024) | leitura errada de "melhora" | tendência pela reta de 15 anos (não só 2 pontos); salto marcado automaticamente e avisado na ficha que o assistente lê |
| **Modelo inventar ou trocar números** (TP5) | gestor decide com número errado | números calculados no Python e entregues prontos; instrução para não fazer contas; resposta cortada em 3 frases; **conferência automática**: número da resposta que não está nos dados vira aviso na tela |
| **Conversa longa pesar ou confundir o modelo** (TP5) | lentidão e erro | memória "janela + notas": só as 2 últimas trocas vão inteiras; o resto vira notas de poucas linhas; corte automático acima de 4.096 tokens |
| **Serviço externo de IA fora do ar ou no limite de uso (429)** (TP5) | assistente parado | modelo local é o padrão; 429 vira 503 com `Retry-After`; o painel mostra os dois motores e o motivo de quem estiver indisponível |
| **Dado sair da máquina ao usar API externa** (TP5) | privacidade | só indicadores públicos e a pergunta vão no pedido; observações enviadas por usuários não entram; chave só no `.env` (fora do Git) |
| Índice de prioridade ser lido como verdade absoluta | decisão sem contexto | pesos ajustáveis na tela, comparação com os pesos iguais e texto explicando o que o índice não considera (custo, capacidade de execução) |
| Uso indevido de conteúdo raspado | questão legal | só fontes que o `robots.txt` permite; Agência Brasil é Creative Commons e guardo o link de cada notícia; HTML bruto não vai para o Git |

## Cronograma

| Etapa | Entrega | Status |
|---|---|---|
| TP1 | problema, ODS, Charter inicial, demo Streamlit, amostra do IBGE | entregue |
| TP2 | interatividade, scraping com BeautifulSoup, cache, upload/download | entregue |
| TP3 | multipáginas, Selenium, FastAPI, documentação revisada, plano de LLM | entregue |
| TP4 | LLM local na API e no painel: tema, sentimento e resumo (`POST /processar_texto`) | entregue |
| TP5 | índice de prioridade e metas de 2033; assistente com memória (`POST /conversar`); notícias com IA; painel final | entregue |
| Final (dez/2026) | projeto completo + apresentação | em preparação |

## Etapas do TDSP neste projeto

| Etapa do TDSP | O que fiz | Onde está |
|---|---|---|
| Business Understanding | pergunta de negócio, público, ODS, KPIs, riscos | este Charter |
| Data Acquisition & Understanding | API do IBGE, BeautifulSoup, Selenium; tratamento e dicionário de dados | `src/coleta_*.py`, `src/ibge.py`, `src/dados.py`, Data Summary Report |
| Modeling | tendência, projeção da meta, índice de prioridade; modelo de linguagem escolhido por benchmark (TP4) e memória escolhida por avaliação (TP5) | `src/analise.py`, `src/benchmark_llm.py`, `src/avaliar_memoria.py`, `data/avaliacao/` |
| Deployment | painel Streamlit (10 páginas) e API FastAPI (13 rotas), modelo local ou serviço externo | `app.py`, `paginas/`, `api/` |
| Customer Acceptance | conferência com a rubrica, testes da API e da conversa, limites assumidos | documento do TP5 (itens 2.8, 2.10 e 4) |

## Estrutura de pastas

```
4S_Projeto_de_Bloco_tp5/
├── app.py                      # roteador do Streamlit (menu e estado comum)
├── paginas/                    # inicio, prioridades, panorama, evolucao, noticias,
│                               # assistente, analise_ia, como_funciona_ia, api_projeto, arquivos
├── api/
│   ├── main.py                 # cria a API e prepara motores e assistente (lifespan)
│   ├── modelos.py              # contratos Pydantic
│   ├── erros.py                # erro -> código HTTP + mensagem
│   └── rotas/                  # dados.py, llm.py (TP4), assistente.py (TP5)
├── src/
│   ├── coleta_*.py, ibge.py    # coletas (BeautifulSoup, Selenium, API do IBGE)
│   ├── dados.py, comum.py      # leitura dos processados, cache e estado
│   ├── analise.py              # tendência, meta de 2033, índice de prioridade
│   ├── fatos.py                # números em frases para o modelo
│   ├── memoria.py              # notas e estratégias de memória
│   ├── assistente.py           # monta o pedido, chama o motor, confere números
│   ├── motor_llm.py            # modelo local
│   ├── motor_api.py            # serviço externo compatível com a OpenAI
│   ├── classificar_noticias.py # tema, sentimento e resumo em lote
│   └── avaliar_memoria.py, testar_api.py, provedor_simulado.py, benchmark_llm.py
├── data/
│   ├── raw/                    # HTML bruto das coletas (fora do Git)
│   ├── processed/              # CSV/JSON que o painel e a API leem
│   └── avaliacao/              # banco de provas (TP4), conversa de teste e resultados (TP5)
├── docs/                       # documentos dos TPs, este Charter e o Data Summary Report
├── .env.exemplo                # modelo de configuração do serviço externo (sem chave)
└── requirements*.txt
```
