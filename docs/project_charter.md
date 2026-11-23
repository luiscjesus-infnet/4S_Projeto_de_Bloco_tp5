# Project Charter - Painel ODS 6 (revisão do TP3)

**Autor:** Luis Claudio de Jesus · Projeto de Bloco: IA Aplicada (INFNET)

Pergunta de negócio e reavaliação do problema: ver item 1.1 de `TP3_Luis_Claudio_de_Jesus.md`.
Escolha do modelo de linguagem (TP4): ver item 1 de `TP4_Luis_Claudio_de_Jesus.md` - deixei essa decisão num documento à parte, com o benchmark completo.

| Campo | Conteúdo |
|---|---|
| **Nome** | Painel ODS 6 - água e esgoto por UF |
| **ODS atendido** | ODS 6 - Água potável e saneamento (metas 6.1 acesso à água, 6.2 esgotamento sanitário e 6.3 tratamento de efluentes). Ligação secundária com o ODS 3 (meta 3.3, doenças transmitidas pela água), por isso trago internações e óbitos por doenças de veiculação hídrica. |
| **Por que esse ODS** | Em 2024, cerca de 34 milhões de pessoas no Brasil ainda não tinham acesso à água e, na média das UFs, 58% da população não tinha coleta de esgoto. É um problema concreto, medido e com dado público. |
| **Problema** | O recurso para saneamento é limitado e a escolha de onde investir costuma ser feita sem juntar, num lugar só, cobertura, tendência e efeito na saúde. |
| **Pergunta de negócio** | Em quais UFs o investimento em água e esgoto deveria chegar primeiro, considerando cobertura atual, evolução desde 2010 e impacto na saúde? |
| **Objetivo** | Entregar um painel e uma API que mostrem, em poucos cliques, as UFs prioritárias e a justificativa com números, e que na próxima etapa gerem esse resumo em texto com LLM. |
| **Dentro do escopo** | 27 UFs; indicadores de água, esgoto e saúde; série 2010-2024; notícias recentes de meio ambiente e saúde; API de consulta e envio de observações. |
| **Fora do escopo** | Nível municipal (fica para depois, se houver tempo); previsão de investimento em reais; integração com sistemas oficiais. |
| **Usuário (quem usa)** | Analista de ONG ou de secretaria estadual/municipal que prepara material para decisão. |
| **Decisor (quem decide)** | Gestor público ou diretor da ONG que define onde o recurso vai primeiro. |
| **Stakeholders** | População das UFs com menor cobertura (beneficiária final); secretarias de saneamento e de saúde; companhias de saneamento; Instituto Trata Brasil e IBGE (fontes); órgãos de controle que acompanham o marco do saneamento. |
| **Metodologia** | TDSP. No TP3 estou entre *Data Acquisition & Understanding* (novas fontes, Selenium) e *Modeling* (ranking e preparação do corpus para LLM). O *Deployment* acontece em duas frentes: painel no Streamlit e API no FastAPI. |

**Metas e indicadores de sucesso (KPIs)**

| Meta (SMART) | Indicador | Situação no TP3 |
|---|---|---|
| Cobrir as 27 UFs com os indicadores de água, esgoto e saúde do ano mais recente até o TP3 | UFs com dado completo | 27 de 27 (2024) ✅ |
| Ter a série 2010-2024 de pelo menos 3 indicadores para todas as UFs até o TP3 | valores coletados | 1.215 de 1.215 (27 UFs × 15 anos × 3) ✅ |
| Usuário chegar ao ranking de prioridade em até 2 cliques a partir da página inicial | cliques | 1 clique (menu "Panorama por UF") ✅ |
| Disponibilizar os dados para outro sistema sem raspagem até o TP3 | rotas documentadas na API | 8 rotas (7 GET + 1 POST) ✅ |
| Atualizar todos os dados em menos de 5 minutos rodando os 3 coletores | tempo total | ~4 min (notícias ~3 min por causa do intervalo de 10 s pedido pelo site) ✅ |
| Gerar, no próximo TP, um resumo de prioridades em texto que o gestor leia em menos de 1 minuto | tamanho do texto / avaliação de 3 pessoas | parcial no TP4: resumo de notícias em até 3 frases já funciona; o relatório de prioridades fica para o TP5 |

**Riscos e mitigação**

| Risco | Impacto | Mitigação |
|---|---|---|
| Site muda o HTML e o scraping para de funcionar | coleta quebra | coleta separada do painel; o painel lê o CSV já salvo; coletores avisam quando a tabela não tem 27 UFs |
| Selenium lento ou bloqueado | série desatualizada | espera explícita com condição clara (27 UFs); nova tentativa automática; paginação escondida do site anotada como plano B |
| API do IBGE fora do ar | painel sem população | cópia local em `ufs_ibge.json` e aviso da origem na barra lateral |
| Mudança de método na fonte (saltos em 2024 em AP e PI) | leitura errada de "melhora" | aviso na página de evolução; análise pela tendência, não por um ano isolado |
| Notícia marcada errada como "ligada ao ODS 6" | ruído na análise | regra revisada (tirei "rio") e classificação com LLM planejada para substituir a regra |
| Chave de API do LLM vazar no GitHub | custo e segurança | `.env` e `.streamlit/secrets.toml` já estão no `.gitignore` |
| Uso indevido de conteúdo raspado | questão legal | só fontes que o `robots.txt` permite; Agência Brasil é Creative Commons e guardo o link de cada notícia; HTML bruto não vai para o Git |

**Cronograma**

| Etapa | Entrega | Status |
|---|---|---|
| TP1 | problema, ODS, Charter inicial, demo Streamlit, amostra do IBGE | entregue |
| TP2 | interatividade, scraping com BeautifulSoup, cache, upload/download | entregue |
| TP3 | multipáginas, Selenium, FastAPI, documentação revisada, plano de LLM | entregue |
| TP4 | LLM local na API e no painel: tema, sentimento e resumo (`POST /processar_texto`) | entregue |
| TP5 | perguntas e respostas com memória da conversa e relatório de prioridades | próxima etapa |
| Final (dez/2026) | projeto completo + apresentação | - |

**Estrutura de pastas (alinhada ao TDSP)**

```
4S_Projeto_de_Bloco_tp3/
├── app.py                      # roteador do Streamlit (menu e estado comum)
├── paginas/                    # uma análise por arquivo
│   ├── inicio.py
│   ├── panorama.py
│   ├── evolucao.py
│   ├── noticias.py
│   ├── api_projeto.py
│   ├── arquivos.py
│   └── preparacao_ia.py
├── api/
│   └── main.py                 # API FastAPI
├── src/                        # código de apoio (não é interface)
│   ├── coleta_dinamica.py      # Selenium  -> serie_saneamento_uf.csv
│   ├── coleta_painel.py        # BeautifulSoup -> saneamento_uf.csv
│   ├── coleta_noticias.py      # BeautifulSoup -> noticias.csv
│   ├── ibge.py                 # API do IBGE -> ufs_ibge.json
│   ├── dados.py                # leitura dos processados (usada pelo painel e pela API)
│   ├── comum.py                # cache, estado da sessão, formatação
│   ├── cliente_api.py          # painel -> API
│   ├── validacao.py            # validação dos uploads
│   └── preparo_llm.py          # corpus e prompts para a próxima etapa
├── data/
│   ├── raw/                    # HTML bruto das coletas (fora do Git)
│   └── processed/              # CSV/JSON que o painel e a API leem
├── docs/                       # este documento, Charter e Data Summary
├── requirements.txt            # o que o painel precisa (vai para a nuvem)
├── requirements-coleta.txt     # + BeautifulSoup e Selenium (só local)
└── requirements-api.txt        # + FastAPI e Uvicorn
```
