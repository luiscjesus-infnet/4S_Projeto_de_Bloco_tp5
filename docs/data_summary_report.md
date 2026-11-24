# Data Summary Report - Painel ODS 6 (revisão do TP5)

**Autor:** Luis Claudio de Jesus · Projeto de Bloco: IA Aplicada (INFNET)

Esta revisão acrescenta ao relatório do TP3 o que o projeto passou a fazer com os dados: as análises derivadas (tendência, meta de 2033, índice de prioridade), os dados produzidos pela IA (tema, sentimento e resumo das notícias), os fatos que o assistente lê e os dados de avaliação.

## 1. Fontes de dados

| # | Fonte | Técnica | Tipo de dado | Atualização | Permissão | Por que uso | Arquivo gerado |
|---|---|---|---|---|---|---|---|
| 1 | API do IBGE (localidades e agregados, tabela 6579) | `requests` (API REST) | semiestruturado (JSON) | anual | API pública | sigla, região e população de cada UF; é a "chave" que liga as outras fontes | `ufs_ibge.json` |
| 2 | Painel Saneamento Brasil - "Por ano" | `requests` + BeautifulSoup | estruturado (tabela HTML estática) | anual | `robots.txt` permite tudo | foto mais recente (2024) de água, esgoto, saúde e renda por UF | `saneamento_uf.csv` |
| 3 | Painel Saneamento Brasil - "Por indicador" | Selenium | estruturado, gerado dinamicamente | anual | `robots.txt` permite tudo | série 2010-2024 para medir tendência e projetar a meta | `serie_saneamento_uf.csv` |
| 4 | Agência Brasil - seções Meio Ambiente e Saúde | `requests` + BeautifulSoup | não estruturado (texto) | diária (base acumulada desde o TP5) | `robots.txt` permite, com 10 s entre requisições; conteúdo Creative Commons | contexto atual; matéria-prima para tema, sentimento e resumo com IA | `noticias.csv` |
| 5 | Usuário do painel (upload de CSV) | `st.file_uploader` | estruturado (CSV) | quando o usuário envia | dado do próprio usuário, não é gravado | cruzar um dado local com os indicadores | não grava |
| 6 | Usuário da API (POST) | FastAPI | semiestruturado (JSON) | contínua | enviado voluntariamente, sem dado pessoal sensível | observações de campo | `observacoes.csv` |
| 7 | Lei 14.026/2020 (Marco Legal do Saneamento) | leitura do texto da lei | referência (2 números) | - | lei pública | metas de 2033: 99% com água e 90% com coleta de esgoto | constantes em `src/analise.py` |

## 2. Como os dados coletados foram integrados e usados

O caminho é sempre o mesmo: **coleta grava em `data/` → `src/dados.py` lê e junta → `src/analise.py` calcula → painel, API e IA consomem**. O painel e a API nunca raspam nada na hora; a IA nunca recebe dado cru.

| Dado coletado | Tratamento e junção | O que passou a gerar | Onde aparece |
|---|---|---|---|
| UFs e população (API do IBGE) | nome da UF comparado sem acento e em minúsculas com as outras fontes; cópia local se a API cair | sigla, região, **pessoas sem água** (população × %) e **internações por 10 mil** | todas as páginas; `/saneamento`; fichas do assistente |
| Indicadores de 2024 (BeautifulSoup) | números "1.234,5%" convertidos para decimal; junção com o IBGE | ranking por indicador; componente **cobertura** e **saúde** do índice | Panorama, Prioridades, `/saneamento/ranking`, `/prioridades`, assistente |
| Série 2010-2024 (Selenium) | formato longo (UF, ano, indicador, valor); 1.215 valores sem nulos | **tendência** (reta de 15 anos), **ano projetado para a meta de 2033**, componente **ritmo** do índice e marcação de saltos suspeitos | Evolução, Prioridades, `/serie/{sigla}`, fichas do assistente |
| Notícias (BeautifulSoup) | texto limpo, limite de 6.000 caracteres, base acumulada sem repetir link | **tema, sentimento e resumo feitos pelo modelo local**; comparação com a regra de palavras-chave do TP3 | Notícias, `/noticias`, Análise de texto com IA |
| Observações (POST) | validadas pela API (UF, tipo, tamanho) | texto que pode ser analisado pelo modelo | API do projeto, Análise de texto com IA |
| Todas as anteriores | `src/fatos.py` escreve os números em frases curtas | **fatos** que o assistente lê (visão geral, ficha da UF, ranking, regiões) | Assistente do painel, `/conversar` |

Evolução ao longo dos TPs: no TP1 só havia uma amostra do IBGE; no TP2 entrou o scraping de manchetes; no TP3, a série com Selenium, o texto completo das notícias e a API; no TP4, o modelo local passou a ler as notícias; no TP5 os dados viraram decisão (índice e metas) e conversa (assistente).

## 3. Dicionário de dados

### 3.1 Dados coletados

`saneamento_uf.csv` (27 linhas, ano 2024) - combinado com o IBGE em `src/dados.py`

| Coluna | Tipo | Descrição | Mín. | Média | Máx. |
|---|---|---|---|---|---|
| sigla, regiao | texto | UF e região (vêm do IBGE) | - | - | - |
| populacao | inteiro | população estimada 2025 (IBGE) | 738.772 (RR) | 7,9 mi | 46,1 mi (SP) |
| sem_agua_pct | decimal | % da população sem acesso à água | 2,5 (DF) | 21,6 | 55,7 (AC) |
| sem_esgoto_pct | decimal | % da população sem coleta de esgoto | 6,8 (SP) | 58,4 | 90,7 (AP) |
| esgoto_tratado_pct | decimal | esgoto tratado em relação à água consumida (%) | 12,2 (MA) | 40,1 | 90,6 (RR) |
| internacoes_vh, obitos_vh | inteiro | internações e óbitos por doenças de veiculação hídrica | - | - | - |
| internacoes_10mil | decimal | **calculado**: internações ÷ população × 10.000 | 5,9 (RN) | 16,9 | 48,6 (MA) |
| pessoas_sem_agua | inteiro | **calculado**: população × % sem água | 74.922 (DF) | 1,27 mi | 4,22 mi (PA) |
| receita_media_agua, renda_com/sem_saneamento | decimal | R$/m³ e R$/mês | - | - | - |
| fonte, coletado_em | texto | origem e data/hora da coleta | - | - | - |

`serie_saneamento_uf.csv` (1.215 linhas: 27 UFs × 15 anos × 3 indicadores): `uf_nome`, `ano` (2010 a 2024), `indicador` (`POP_SEM_AG%`, `POP_SEM_ES%`, `INCIDE_VH`), `indicador_nome`, `valor`, `fonte`, `coletado_em`. Média das UFs: sem água 26,3% (2010) → 21,6% (2024); sem esgoto 73,0% → 58,4%; internações por 10 mil 42,0 → 17,0.

`noticias.csv` (40 notícias, publicadas de 15/10 a 23/11/2026, coletadas em 19/10 e 23/11/2026, média de 427 palavras): `secao`, `titulo`, `resumo`, `texto` (até 6.000 caracteres), `url`, `publicado_em`, `palavras`, `tema_ods6` (regra de palavras-chave do TP3), `fonte`, `coletado_em`.

`observacoes.csv`: `id`, `sigla`, `autor`, `tipo` (campo/correção/sugestão), `texto`, `enviado_em`.

### 3.2 Dados derivados pela análise (TP5, calculados em `src/analise.py`, não gravados)

| Campo | Como é calculado | Mín. | Média | Máx. |
|---|---|---|---|---|
| tendencia_agua | inclinação da reta 2010-2024 da % sem água (p.p. por ano; negativo = melhora) | -1,15 (PI) | -0,27 | +0,62 (AC) |
| tendencia_esgoto | idem para a % sem coleta de esgoto | -4,17 (RR) | -1,08 | +0,05 (AC) |
| tendencia_internacoes | idem para internações por 10 mil | -5,40 (PI) | -1,81 | +0,86 (DF) |
| meta_agua_ano / situação | ano em que a % sem água chega a 1% mantendo a tendência | 2 UFs no prazo, 13 atrasadas, 12 não chegam | | |
| meta_esgoto_ano / situação | ano em que a % sem esgoto chega a 10% | 2 já cumprem, 2 no prazo, 13 atrasadas, 10 não chegam | | |
| quebras | anos com salto de mais de 10 p.p. em relação ao ano anterior | 13 UFs com pelo menos um salto (ex.: AP 2022 e 2024, PI 2024) | | |
| indice (prioridade) | média ponderada de cobertura, ritmo e saúde, cada um normalizado de 0 a 100 entre as UFs | 6,8 (SP) | 44,5 | 96,3 (MA) |

### 3.3 Dados produzidos pela IA e pela avaliação (TP5)

| Arquivo | Conteúdo | Como é gerado |
|---|---|---|
| `data/processed/noticias_ia.csv` | `url`, `tema_ia`, `confianca_tema`, `sentimento_ia`, `confianca_sentimento`, `resumo_ia`, `segundos`, `modelo`, `processado_em` (40 linhas) | `python -m src.classificar_noticias` (modelo local, em lote) |
| `data/avaliacao/conversa_teste.csv` | 10 perguntas encadeadas, de que pergunta cada uma depende, gabarito e expressão para conferir | escrito por mim, com os valores conferidos nos dados |
| `data/avaliacao/memoria_por_pergunta.csv` | resposta, acerto, tokens, tempo e fatos usados para cada pergunta de cada rodada (60 linhas) | `python -m src.avaliar_memoria` |
| `data/avaliacao/memoria_resultado.csv` | resumo por estratégia de memória | idem |

Os **fatos** que o assistente lê não são gravados: são montados a cada pergunta a partir dos dados acima (`src/fatos.py`). Tamanho aproximado: visão geral ~185 tokens, ficha de uma UF ~230 tokens; a tabela crua equivalente tem ~510 tokens, mas sem nenhuma conta feita.

## 4. Qualidade e tratamento dos dados

- Números do site vêm no formato brasileiro ("1.234,5%"); converto para decimal na coleta.
- Os nomes das UFs vêm com acento; para juntar com o IBGE comparo sem acento e em minúsculas.
- **Saltos na série**: 13 UFs têm pelo menos um ano com variação de mais de 10 pontos (ex.: Amapá de 59,9% para 28,7% sem água em 2024; Piauí de 32,2% para 7,7%). Provavelmente é mudança na base de origem, não só obra nova. Por isso a tendência usa a reta dos 15 anos e não só o primeiro e o último ano, e a ficha da UF avisa o salto.
- **Internações calculadas x da fonte**: a taxa que calculo com a população do IBGE (2025) difere da taxa da série da fonte (`INCIDE_VH`) só na segunda casa decimal (ex.: MA 48,58 x 48,62).
- **Tendência linear é uma simplificação**: obra de saneamento não acontece em ritmo constante. Uso a projeção para comparar UFs entre si ("no ritmo atual"), não como previsão de ano exato.
- **Notícias**: a regra de palavras-chave do TP3 marca como "ODS 6" notícias que só citam água; o modelo local corrige boa parte disso, mas também erra (benchmark do TP4: 41 de 48 temas). No painel, o resumo da IA aparece com o aviso "confira com o texto original".
- O HTML bruto (`data/raw`) fica só local para conferência; o que vai para o GitHub é o dado processado.
