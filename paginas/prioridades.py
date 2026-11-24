import streamlit as st

from src import analise
from src.comum import fmt, obter_base_fatos, para_csv, texto_meta

st.title("🎯 Prioridades de investimento")
st.markdown(
    "Esta página responde à pergunta do projeto juntando os três critérios num **índice de 0 a 100** "
    "(quanto maior, antes a UF deveria receber investimento em água e esgoto):"
)
c1, c2, c3 = st.columns(3)
c1.info("**Cobertura atual**  \nparcela sem água e sem coleta de esgoto em 2024")
c2.info("**Ritmo até a meta**  \nanos que faltam para 99% com água e 90% com esgoto (Marco Legal, 2033), no ritmo de 2010-2024")
c3.info("**Saúde**  \ninternações por doenças de veiculação hídrica a cada 10 mil habitantes")

base = obter_base_fatos()

with st.sidebar.form("pesos_prioridade"):
    st.markdown("**Pesos do índice**")
    st.caption("Iguais por padrão. Mude para ver se o ranking se mantém.")
    peso_cob = st.slider("Cobertura atual", 0, 10, 5)
    peso_rit = st.slider("Ritmo até a meta", 0, 10, 5)
    peso_sau = st.slider("Saúde", 0, 10, 5)
    st.form_submit_button("Recalcular")

if peso_cob + peso_rit + peso_sau == 0:
    st.warning("Pelo menos um peso precisa ser maior que zero.")
    st.stop()

pesos = {"cobertura": peso_cob, "ritmo": peso_rit, "saude": peso_sau}
ranking = analise.indice_prioridade(base.perfis, pesos)
soma = sum(pesos.values())
padrao = {l["sigla"]: l["posicao"] for l in base.prioridade}

topo = ranking[0]
b = base.brasil
m1, m2, m3 = st.columns(3)
m1.metric("1ª prioridade", f"{topo['uf_nome']} ({topo['sigla']})", f"índice {fmt(topo['indice'])}", delta_color="off")
m2.metric("UFs que chegam à meta de água até 2033", f"{b['chegam_meta_agua']} de 27")
m3.metric("UFs que chegam à meta de esgoto até 2033", f"{b['chegam_meta_esgoto']} de 27")

st.subheader("As UFs na ordem de prioridade")
quantas = st.slider("Quantas UFs mostrar", 5, 27, 10, key="quantas_prioridade")
partes = []
nomes = {"cobertura": "Cobertura atual", "ritmo": "Ritmo até a meta", "saude": "Saúde"}
for l in ranking[:quantas]:
    for chave, nome in nomes.items():
        partes.append({"UF": f"{l['posicao']:02d} {l['sigla']}", "componente": nome,
                       "pontos": round(l[f"comp_{chave}"] * pesos[chave] / soma, 1)})
st.bar_chart(partes, x="UF", y="pontos", color="componente", horizontal=True, sort=False, height=28 * quantas + 80)
st.caption("Cada barra é o índice da UF; as cores mostram quanto cada critério contribuiu, já com os pesos.")

st.subheader("Tabela completa")
linhas = []
for l in ranking:
    p = base.perfis[l["sigla"]]
    mudou = padrao[l["sigla"]] - l["posicao"]
    linhas.append({
        "posição": l["posicao"],
        "UF": f"{l['uf_nome']} ({l['sigla']})",
        "índice": l["indice"],
        "vs. pesos iguais": "=" if mudou == 0 else (f"▲ {mudou}" if mudou > 0 else f"▼ {-mudou}"),
        "sem água 2024 (%)": p["sem_agua_pct"],
        "sem esgoto 2024 (%)": p["sem_esgoto_pct"],
        "internações /10 mil": p["internacoes_10mil"],
        "meta de água": texto_meta(p["meta_agua_ano"], p["meta_agua_situacao"]),
        "meta de esgoto": texto_meta(p["meta_esgoto_ano"], p["meta_esgoto_situacao"]),
        "por quê": "; ".join(base.motivos(l["sigla"])),
    })
st.dataframe(
    linhas, hide_index=True, width="stretch", height=420,
    column_config={"índice": st.column_config.ProgressColumn("índice", min_value=0, max_value=100, format="%.1f"),
                   "por quê": st.column_config.TextColumn("por quê", width="large")},
)
st.download_button("📥 Baixar o ranking (CSV)", para_csv(linhas), file_name="prioridades.csv", mime="text/csv")

with st.expander("Como o índice é calculado (e o que ele não diz)"):
    st.markdown(
        f"""
- Cada critério é normalizado entre as 27 UFs: 0 = melhor situação, 100 = pior. O índice é a média
  ponderada dos três (pesos atuais: cobertura {fmt(100 * peso_cob / soma, 0)}%, ritmo {fmt(100 * peso_rit / soma, 0)}%,
  saúde {fmt(100 * peso_sau / soma, 0)}%).
- **Ritmo**: inclinação da reta de 2010 a 2024 (mínimos quadrados), e não só o primeiro e o último ano.
  Com ela projeto o ano em que a UF chega a 99% com água e 90% com esgoto. Quem está parado, piorando
  ou levaria mais de 100 anos conta como "não chega".
- **Cuidado**: algumas séries têm saltos de mais de 10 pontos de um ano para o outro (ex.: Amapá e Piauí
  em 2024), que podem ser mudança na base da fonte e não obra nova. Essas UFs estão marcadas na ficha
  que o assistente lê.
- O índice ordena **necessidade**. Ele não considera custo da obra, capacidade de execução do estado nem
  investimento já contratado; esses pontos entram na conversa com o gestor.
"""
    )

st.page_link("paginas/assistente.py", label="Perguntar ao assistente por que uma UF está nessa posição", icon="💬")
