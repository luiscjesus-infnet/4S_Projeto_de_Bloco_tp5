# Data Summary Report - Painel ODS 6 (revisão do TP3)

**Autor:** Luis Claudio de Jesus · Projeto de Bloco: IA Aplicada (INFNET)

**Fontes de dados**

| # | Fonte | Técnica | Tipo de dado | Atualização | Permissão | Por que uso | Arquivo gerado |
|---|---|---|---|---|---|---|---|
| 1 | API do IBGE (localidades e agregados, tabela 6579) | `requests` | semiestruturado (JSON) | anual | API pública | sigla, região e população de cada UF; é a "chave" que liga as outras fontes | `ufs_ibge.json` |
| 2 | Painel Saneamento Brasil - "Por ano" | `requests` + BeautifulSoup | estruturado (tabela HTML estática) | anual | `robots.txt` permite tudo | foto mais recente (2024) de água, esgoto, saúde e renda por UF | `saneamento_uf.csv` |
| 3 | Painel Saneamento Brasil - "Por indicador" | **Selenium** | estruturado, mas gerado dinamicamente | anual | `robots.txt` permite tudo | série 2010-2024 para medir tendência | `serie_saneamento_uf.csv` |
| 4 | Agência Brasil - seções Meio Ambiente e Saúde | `requests` + BeautifulSoup | não estruturado (texto) | diária | `robots.txt` permite, com 10 s entre requisições; conteúdo Creative Commons | contexto atual e texto para resumo/sentimento com LLM | `noticias.csv` |
| 5 | Usuário do painel (upload de CSV) | `st.file_uploader` | estruturado (CSV) | quando o usuário envia | dado do próprio usuário, não é gravado | cruzar um dado local (ex.: investimento previsto) com os indicadores | não grava |
| 6 | Usuário da API (POST) | FastAPI | semiestruturado (JSON) | contínua | dado enviado voluntariamente, sem dado pessoal sensível | observações de campo que viram contexto para o LLM | `observacoes.csv` |

**Fontes avaliadas e descartadas**

- **Busca da EBC (`busca.ebc.com.br`)**: seria ótima para buscar "saneamento" direto, mas o `robots.txt` dela tem `Disallow: /`. Não usei.
- **Botão "Exportar" do Painel Saneamento**: devolveu erro 500 numa requisição direta, então não serve como arquivo pronto.

**Dicionário de dados**

`saneamento_uf.csv` (27 linhas, ano 2024) - combinado com o IBGE em `src/dados.py`

| Coluna | Tipo | Descrição | Mín. | Média | Máx. |
|---|---|---|---|---|---|
| sigla | texto | UF (vem do IBGE) | - | - | - |
| regiao | texto | região (vem do IBGE) | - | - | - |
| populacao | inteiro | população estimada 2025 (IBGE) | 738.772 (RR) | 7,9 mi | 46,1 mi (SP) |
| sem_agua_pct | decimal | % da população sem acesso à água | 2,5 (DF) | 21,6 | 55,7 (AC) |
| sem_esgoto_pct | decimal | % da população sem coleta de esgoto | 6,8 (SP) | 58,4 | 90,7 (AP) |
| esgoto_tratado_pct | decimal | esgoto tratado em relação à água consumida (%) | 12,2 (MA) | 40,1 | 90,6 (RR) |
| internacoes_vh | inteiro | internações por doenças de veiculação hídrica | 874 (RR) | 12.451 | 46.198 (MG) |
| obitos_vh | inteiro | óbitos por doenças de veiculação hídrica | 0 (DF) | 176 | 999 (SP) |
| internacoes_10mil | decimal | **calculado**: internações ÷ população × 10.000 | 5,9 (RN) | 16,9 | 48,6 (MA) |
| pessoas_sem_agua | inteiro | **calculado**: população × % sem água | 74.922 (DF) | 1,27 mi | 4,22 mi (PA) |
| receita_media_agua, renda_com_saneamento, renda_sem_saneamento | decimal | R$/m³ e R$/mês | - | - | - |
| fonte, coletado_em | texto | origem e data/hora da coleta | - | - | - |

`serie_saneamento_uf.csv` (1.215 linhas, formato "longo": uma linha por UF, ano e indicador, sem valores nulos)

| Coluna | Tipo | Descrição |
|---|---|---|
| uf_nome | texto | nome da UF como aparece no site |
| ano | inteiro | 2010 a 2024 |
| indicador | texto | `POP_SEM_AG%`, `POP_SEM_ES%` ou `INCIDE_VH` |
| indicador_nome | texto | nome completo lido do título da tabela |
| valor | decimal | valor do ano (média das UFs: sem água 26,3% em 2010 → 21,6% em 2024; sem esgoto 73,0% → 58,4%; incidência de internações 42,0 → 17,0) |
| fonte, coletado_em | texto | origem e data/hora |

`noticias.csv` (16 notícias, 15 a 19/10/2026, média de 416 palavras)

| Coluna | Tipo | Descrição |
|---|---|---|
| secao | texto | meio-ambiente ou saude |
| titulo, resumo, texto | texto | título, linha fina e corpo da notícia (texto limitado a 6.000 caracteres) |
| url | texto | link original (exigência da licença) |
| publicado_em | data/hora | data de publicação |
| palavras | inteiro | tamanho do texto |
| tema_ods6 | sim/não | marcação por palavras-chave (7 de 16 marcadas) |

`observacoes.csv`: `id`, `sigla`, `autor`, `tipo` (campo/correção/sugestão), `texto`, `enviado_em`.

**Qualidade e tratamento dos dados**

- Números do site vêm no formato brasileiro ("1.234,5%"); converto para decimal na coleta.
- Os nomes das UFs vêm com acento; para juntar com o IBGE comparo sem acento e em minúsculas.
- Saltos grandes em 2024 (Amapá de 59,9% para 28,7% sem água; Piauí de 32,2% para 7,7%) provavelmente refletem mudança na base de origem, não só obra nova. Deixei isso avisado no painel.
- A marcação `tema_ods6` por palavra-chave tem limite: na primeira versão "rio" marcava notícias sobre o Rio de Janeiro; tirei a palavra, mas ainda há casos discutíveis (a notícia da COP17 entra porque cita "água" uma vez). Esse é um dos motivos para usar LLM na próxima etapa.
- O HTML bruto (`data/raw`) fica só local para conferência; o que vai para o GitHub é o dado processado.
