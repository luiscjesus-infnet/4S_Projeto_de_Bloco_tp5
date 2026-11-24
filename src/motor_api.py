"""
Motor que chama um modelo de linguagem por API, como alternativa ao modelo local.

Uso o formato de chat da OpenAI (POST {url}/chat/completions), que virou padrão:
o mesmo código atende OpenRouter, OpenAI, Google Gemini e outros serviços compatíveis.
Muda só o endereço, a chave e o nome do modelo, que ficam no .env (nunca no código).

Fiz com requests, sem SDK, porque a chamada é um POST simples e assim eu controlo
cada erro. Os erros viram as mesmas exceções do motor local (src/motor_llm.py), e a
API do projeto traduz cada uma para o código HTTP certo (api/erros.py).

Cuidados que um serviço externo pede e o modelo local não:
- 429 (limite de pedidos): comum nos modelos gratuitos; repasso o tempo de espera;
- resposta 200 com texto vazio: modelos que "pensam" antes de responder podem gastar
  todo o limite de tokens raciocinando; aviso para aumentar LLM_API_MAX_TOKENS;
- privacidade: o que vai no pedido sai da máquina. No assistente vão só indicadores
  públicos e a pergunta; as observações enviadas pelos usuários não entram.
"""
import os
import time
from urllib.parse import urlparse

import requests

from src.motor_llm import (
    ChaveRecusada,
    LimiteDoServico,
    MotorNaoConfigurado,
    RespostaInvalida,
    ServicoExternoFalhou,
    TempoEsgotado,
)

URL_PADRAO = "https://openrouter.ai/api/v1"


class MotorAPI:
    tipo = "api"

    def __init__(self, url=None, chave=None, modelo=None, max_tokens=None, tempo_limite=None):
        self.url = (url or os.environ.get("LLM_API_URL") or URL_PADRAO).rstrip("/")
        # aceito também os nomes de variável mais comuns, para quem já tem a chave no .env
        self._chave = (chave or os.environ.get("LLM_API_CHAVE") or os.environ.get("OPENROUTER_API_KEY")
                       or os.environ.get("OPENAI_API_KEY") or "")
        self.nome = modelo or os.environ.get("LLM_API_MODELO", "")
        self.max_tokens = int(max_tokens or os.environ.get("LLM_API_MAX_TOKENS", 1500))
        self.tempo_limite = float(tempo_limite or os.environ.get("LLM_API_TEMPO_LIMITE", 60))
        self._sessao = requests.Session()

    @property
    def configurado(self):
        return bool(self._chave and self.nome)

    def motivo_nao_configurado(self):
        faltando = [n for n, v in (("LLM_API_CHAVE", self._chave), ("LLM_API_MODELO", self.nome)) if not v]
        return f"Falta {' e '.join(faltando)} no arquivo .env (veja o modelo em .env.exemplo)."

    def descricao(self):
        # nunca devolvo a chave; só o servidor, para saber para onde os dados vão
        return {"tipo": "api", "nome": self.nome or "(não definido)", "onde_roda": f"serviço externo ({urlparse(self.url).netloc})"}

    def responder(self, mensagens, max_novos=None):
        if not self.configurado:
            raise MotorNaoConfigurado(self.motivo_nao_configurado())
        corpo = {
            "model": self.nome,
            "messages": mensagens,
            "max_tokens": max(int(max_novos or 0), self.max_tokens),
            "temperature": 0,
        }
        inicio = time.perf_counter()
        try:
            resposta = self._sessao.post(
                f"{self.url}/chat/completions",
                json=corpo,
                headers={"Authorization": f"Bearer {self._chave}", "X-Title": "Painel ODS 6"},
                timeout=self.tempo_limite,
            )
        except requests.Timeout:
            raise TempoEsgotado(f"O serviço externo não respondeu em {self.tempo_limite:.0f} s.") from None
        except requests.ConnectionError as erro:
            raise ServicoExternoFalhou(f"Sem conexão com {urlparse(self.url).netloc}: {type(erro).__name__}") from None
        segundos = round(time.perf_counter() - inicio, 2)

        if resposta.status_code in (401, 403):
            raise ChaveRecusada(f"O serviço recusou a chave ({resposta.status_code}).")
        if resposta.status_code == 429:
            espera = resposta.headers.get("Retry-After")
            raise LimiteDoServico("O serviço externo limitou os pedidos (429).",
                                  espera=int(espera) if espera and espera.isdigit() else None)
        if resposta.status_code >= 400:
            raise ServicoExternoFalhou(f"O serviço respondeu {resposta.status_code}: {_mensagem(resposta)}")

        try:
            dados = resposta.json()
            escolha = dados["choices"][0]
            texto = (escolha.get("message") or {}).get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise RespostaInvalida("O serviço respondeu 200, mas fora do formato de chat esperado.") from None
        if dados.get("error"):
            raise ServicoExternoFalhou(f"O serviço devolveu erro dentro da resposta: {dados['error']}")

        texto = texto.strip()
        motivo_fim = escolha.get("finish_reason")
        if not texto:
            if motivo_fim == "length":
                raise RespostaInvalida(
                    "Resposta vazia: o limite de tokens acabou antes do texto (modelos que raciocinam gastam "
                    "tokens pensando). Aumente LLM_API_MAX_TOKENS no .env."
                )
            raise RespostaInvalida("O serviço respondeu 200, mas sem texto.")

        uso = dados.get("usage") or {}
        return {
            "texto": texto,
            "tokens_entrada": int(uso.get("prompt_tokens") or 0),
            "tokens_saida": int(uso.get("completion_tokens") or 0),
            "cortada": motivo_fim == "length",
            "segundos": segundos,
            "modelo_servico": dados.get("model") or self.nome,
        }


def _mensagem(resposta):
    try:
        corpo = resposta.json()
        erro = corpo.get("error")
        if isinstance(erro, dict):
            return str(erro.get("message", erro))[:200]
        return str(erro or corpo)[:200]
    except ValueError:
        return resposta.text[:200]
