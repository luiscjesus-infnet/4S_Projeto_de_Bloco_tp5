"""
Validação "na borda" dos arquivos que o usuário envia pelo painel.
O arquivo só entra na aplicação se estiver no formato esperado; se não estiver,
explico o motivo em vez de deixar a página quebrar.

Formato esperado: CSV com as colunas  sigla  e  valor  (e opcionalmente  descricao).
"""
import csv
import io

from src.dados import SIGLAS

COLUNAS_OBRIGATORIAS = {"sigla", "valor"}
CODIFICACOES = ["utf-8-sig", "utf-8", "latin-1"]  # latin-1 por último porque quase nunca falha


def _decodificar(conteudo):
    for codificacao in CODIFICACOES:
        try:
            return conteudo.decode(codificacao), codificacao
        except UnicodeDecodeError:
            continue
    return None, None


def _numero(texto):
    texto = (texto or "").strip().replace(".", "").replace(",", ".") if "," in (texto or "") else (texto or "").strip()
    try:
        return float(texto)
    except ValueError:
        return None


def ler_csv_enviado(conteudo):
    """Recebe os bytes do arquivo. Devolve (linhas_validas, avisos, erro)."""
    if not conteudo:
        return [], [], "O arquivo está vazio."

    texto, codificacao = _decodificar(conteudo)
    if texto is None:
        return [], [], "Não consegui ler o arquivo. Ele é mesmo um CSV de texto?"

    primeira_linha = texto.splitlines()[0] if texto.splitlines() else ""
    separador = ";" if primeira_linha.count(";") > primeira_linha.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=separador)
    if leitor.fieldnames is None:
        return [], [], "O arquivo não tem cabeçalho."

    colunas = {c.strip().lower() for c in leitor.fieldnames if c}
    faltando = COLUNAS_OBRIGATORIAS - colunas
    if faltando:
        return [], [], f"Faltam as colunas obrigatórias: {', '.join(sorted(faltando))}."

    validas, avisos = [], []
    for numero_linha, linha in enumerate(leitor, start=2):
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
        sigla = linha.get("sigla", "").upper()
        valor = _numero(linha.get("valor"))
        if sigla not in SIGLAS:
            avisos.append(f"Linha {numero_linha}: sigla '{sigla}' não é uma UF válida (ignorada).")
            continue
        if valor is None:
            avisos.append(f"Linha {numero_linha}: valor '{linha.get('valor')}' não é número (ignorada).")
            continue
        validas.append({"sigla": sigla, "valor": valor, "descricao": linha.get("descricao", "")})

    if not validas:
        return [], avisos, "O arquivo tem cabeçalho, mas nenhuma linha válida."
    avisos.insert(0, f"Arquivo lido como {codificacao}, separador '{separador}'.")
    return validas, avisos, None
