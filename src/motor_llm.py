"""
Motor de linguagem do projeto: carrega um modelo local do HuggingFace (Transformers)
e faz as três análises que a API oferece, mais a conversa do assistente (TP5).

- tema: em qual assunto de saneamento o texto se encaixa (lista fechada)
- sentimento: tom do texto (positivo, negativo ou neutro)
- resumo: até 3 frases com o principal do texto
- responder: recebe as mensagens de uma conversa (sistema, usuário, assistente) e
  escreve a próxima resposta; quem monta essas mensagens é src/assistente.py

Para tema e sentimento eu não deixo o modelo escrever livremente. Monto o pedido,
rodo o modelo uma vez e olho só a probabilidade da primeira "palavra" de cada
categoria permitida. A maior vence. Assim a resposta sempre é uma categoria válida
e ainda ganho uma pontuação para cada uma (é o que aparece no gráfico do painel).

Tudo roda na máquina: o modelo é lido da pasta modelos/ com local_files_only=True,
então se o arquivo não estiver lá o carregamento falha em vez de ir buscar na internet.
"""
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TempoDoFuturoEsgotado
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PASTA_MODELOS = BASE / "modelos"

MODELO_PADRAO = "Qwen/Qwen2.5-1.5B-Instruct"

# modelos comparados no benchmark (src/benchmark_llm.py)
CANDIDATOS = {
    "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli": "encoder",
    "Qwen/Qwen2.5-0.5B-Instruct": "decoder",
    "Qwen/Qwen2.5-1.5B-Instruct": "decoder",
    "Qwen/Qwen2.5-3B-Instruct": "decoder",
}

TEMAS = {
    "abastecimento": "falta de água, água que não chega, rodízio, pressão baixa, caminhão-pipa, lugar sem rede de distribuição",
    "qualidade": "água suja, barrenta, com cheiro, cor ou gosto estranho, contaminação, análise da água, orientação para ferver",
    "esgoto": "esgoto a céu aberto, vazamento de esgoto, mau cheiro de esgoto, fossa, ligação das casas à rede, coleta e tratamento de esgoto",
    "saude": "doenças ligadas à água ou ao esgoto: diarreia, hepatite A, leptospirose, verminose, internações por essas causas",
    "investimento": "obras, licitações, contratos, concessões, dinheiro ou orçamento para água e esgoto, inauguração de estações",
    "outro": "o texto não trata de água encanada, esgoto nem de doenças causadas por eles (ex.: clima, ar, florestas, animais, remédios, hospitais, outras doenças)",
}

SENTIMENTOS = {
    "positivo": "conta uma melhora, uma solução, uma conquista ou uma boa notícia",
    "negativo": "conta um problema, uma piora, uma falha, um risco ou uma reclamação",
    "neutro": "só informa ou anuncia algo, sem tom claro de melhora ou de piora",
}

INSTRUCOES = {
    "tema": "Você classifica textos curtos em português e identifica se falam de água e saneamento no Brasil.",
    "sentimento": "Você identifica o tom de textos curtos em português.",
    "resumo": "Você resume textos em português de forma fiel, sem inventar informações.",
}

# limites pensados para uma máquina comum, só com CPU
MAX_TOKENS_ENTRADA = int(os.environ.get("LLM_MAX_TOKENS_ENTRADA", 1024))
MAX_TOKENS_RESUMO = int(os.environ.get("LLM_MAX_TOKENS_RESUMO", 160))
TEMPO_LIMITE = float(os.environ.get("LLM_TEMPO_LIMITE", 90))      # segundos por pedido
ESPERA_NA_FILA = float(os.environ.get("LLM_ESPERA_FILA", 5))      # segundos esperando o modelo ficar livre
MAX_TOKENS_CONVERSA = int(os.environ.get("LLM_MAX_TOKENS_CONVERSA", 4096))  # pedido inteiro da conversa
MAX_TOKENS_RESPOSTA = int(os.environ.get("LLM_MAX_TOKENS_RESPOSTA", 130))   # resposta do assistente (~3 frases)


# ----------------------------------------------------------------------------------
# Erros do motor. A API traduz cada um para o código HTTP certo (api/erros.py).
# ----------------------------------------------------------------------------------
class ErroDoMotor(Exception):
    """Base dos erros do motor."""


class ModeloNaoEncontrado(ErroDoMotor):
    """O modelo não está na pasta modelos/ (falta rodar o download)."""


class ModeloIndisponivel(ErroDoMotor):
    """O modelo não foi carregado (falhou na subida da API ou foi desligado)."""


class MotorOcupado(ErroDoMotor):
    """Outro pedido está usando o modelo e a espera passou do limite."""


class TempoEsgotado(ErroDoMotor):
    """O modelo demorou mais que o limite configurado."""


class SemMemoria(ErroDoMotor):
    """Faltou memória para rodar o modelo."""


class RespostaInvalida(ErroDoMotor):
    """O modelo devolveu algo fora do formato esperado."""


# erros que só acontecem quando o modelo é chamado por um serviço externo (src/motor_api.py)
class MotorNaoConfigurado(ErroDoMotor):
    """Falta a chave ou o nome do modelo no .env."""


class ChaveRecusada(ErroDoMotor):
    """O serviço respondeu 401/403: chave errada, vencida ou sem permissão para o modelo."""


class LimiteDoServico(ErroDoMotor):
    """O serviço respondeu 429: passou do limite de pedidos (comum nos modelos gratuitos)."""

    def __init__(self, mensagem, espera=None):
        super().__init__(mensagem)
        self.espera = espera


class ServicoExternoFalhou(ErroDoMotor):
    """O serviço caiu, não respondeu ou devolveu erro do lado dele (5xx, modelo inexistente)."""


def pasta_do_modelo(nome):
    """Qwen/Qwen2.5-1.5B-Instruct -> modelos/Qwen__Qwen2.5-1.5B-Instruct"""
    return PASTA_MODELOS / nome.replace("/", "__")


def escolher_dispositivo(preferencia="auto"):
    import torch

    if preferencia == "cuda" or (preferencia == "auto" and torch.cuda.is_available()):
        return "cuda"
    return "cpu"


def montar_lista(opcoes, com_definicoes):
    if com_definicoes:
        return "\n".join(f"- {nome}: {definicao}" for nome, definicao in opcoes.items())
    return ", ".join(opcoes)


def montar_mensagens(tarefa, texto, com_definicoes=True):
    """Mensagens no formato de chat (papel de sistema + papel de usuário)."""
    if tarefa == "tema":
        pedido = f"Categorias possíveis:\n{montar_lista(TEMAS, com_definicoes)}\n\nTexto: \"{texto}\"\n\n"
        if com_definicoes:
            pedido += (
                "Muitos textos não falam de saneamento. Se o texto não trata de abastecimento de água, "
                "qualidade da água, esgoto, doenças causadas por água ou esgoto, ou dinheiro e obras de "
                "saneamento, a resposta é outro.\n"
            )
        pedido += "Responda apenas com o nome de uma categoria, sem explicar."
    elif tarefa == "sentimento":
        pedido = (
            f"Tons possíveis:\n{montar_lista(SENTIMENTOS, com_definicoes)}\n\n"
            f'Texto: "{texto}"\n\n'
            "Responda apenas com uma palavra: positivo, negativo ou neutro."
        )
    elif tarefa == "resumo":
        pedido = (
            "Resuma o texto abaixo em no máximo 3 frases curtas. Mantenha nomes, lugares e números "
            "exatamente como estão no texto e não acrescente nada que não esteja nele.\n\n"
            f"Texto:\n{texto}"
        )
    else:
        raise ValueError(f"Tarefa desconhecida: {tarefa}")
    return [{"role": "system", "content": INSTRUCOES[tarefa]}, {"role": "user", "content": pedido}]


class MotorLLM:
    """Guarda o modelo carregado na memória e atende um pedido por vez."""

    def __init__(self, nome=MODELO_PADRAO, dispositivo="auto", precisao="float32"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.nome = nome
        self.pasta = pasta_do_modelo(nome)
        if not (self.pasta / "config.json").exists():
            # caminho relativo: a mensagem chega ao usuário e não deve expor pastas da máquina
            relativo = self.pasta.relative_to(BASE).as_posix()
            raise ModeloNaoEncontrado(
                f"O modelo {nome} não está em {relativo}/. Rode: python -m src.baixar_modelo {nome}"
            )

        self.dispositivo = escolher_dispositivo(dispositivo)
        self.precisao = precisao
        inicio = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(self.pasta, local_files_only=True)
        self.modelo = AutoModelForCausalLM.from_pretrained(
            self.pasta, local_files_only=True, dtype=getattr(torch, precisao)
        ).to(self.dispositivo)
        self.modelo.eval()
        self.segundos_carregando = round(time.perf_counter() - inicio, 1)
        self.parametros = sum(p.numel() for p in self.modelo.parameters())

        # uma trava: o mesmo modelo não atende dois pedidos ao mesmo tempo
        self._trava = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm")
        self._ids_tema = self._primeiros_tokens(TEMAS)
        self._ids_sentimento = self._primeiros_tokens(SENTIMENTOS)

    # ------------------------------------------------------------------ preparação
    def _primeiros_tokens(self, opcoes):
        """
        Para cada categoria, a sequência de tokens do nome escrito em minúsculas e com
        inicial maiúscula ("esgoto" -> es + goto; "Esgoto" -> E + sgoto). A pontuação usa a
        palavra inteira, não só o primeiro pedaço: "es" é um pedaço muito comum em português
        e, sozinho, dava vantagem falsa para "esgoto".
        """
        return {
            nome: [self.tokenizer.encode(v, add_special_tokens=False) for v in dict.fromkeys((nome, nome.capitalize()))]
            for nome in opcoes
        }

    def _entrada(self, tarefa, texto, com_definicoes=True):
        """Corta textos longos antes de montar o pedido, para caber no limite de tokens."""
        ids_texto = self.tokenizer.encode(texto, add_special_tokens=False)
        truncado = len(ids_texto) > MAX_TOKENS_ENTRADA
        if truncado:
            texto = self.tokenizer.decode(ids_texto[:MAX_TOKENS_ENTRADA])
        mensagens = montar_mensagens(tarefa, texto, com_definicoes)
        prompt = self.tokenizer.apply_chat_template(mensagens, add_generation_prompt=True, tokenize=False)
        entrada = self.tokenizer(prompt, return_tensors="pt").to(self.dispositivo)
        return entrada, truncado, len(ids_texto)

    # ------------------------------------------------------------------ análises
    def _classificar(self, tarefa, texto, com_definicoes=True):
        import torch

        ids_por_opcao = self._ids_tema if tarefa == "tema" else self._ids_sentimento
        entrada, truncado, tokens = self._entrada(tarefa, texto, com_definicoes)
        sequencias = [seq for variantes in ids_por_opcao.values() for seq in variantes]
        with torch.inference_mode():
            # 1) o pedido passa pelo modelo uma vez; guardo o cache (o "rascunho" interno dele)
            saida = self.modelo(**entrada, use_cache=True)
            cache = saida.past_key_values
            log_primeiro = torch.log_softmax(saida.logits[0, -1].float(), dim=-1)
            # 2) todas as respostas possíveis entram juntas, num lote, reaproveitando o cache
            maior = max(len(s) for s in sequencias)
            vazio = self.tokenizer.pad_token_id or self.tokenizer.eos_token_id
            ids = torch.tensor([s + [vazio] * (maior - len(s)) for s in sequencias], device=self.dispositivo)
            mascara = torch.tensor([[1] * len(s) + [0] * (maior - len(s)) for s in sequencias], device=self.dispositivo)
            mascara = torch.cat([entrada["attention_mask"].repeat(len(sequencias), 1), mascara], dim=1)
            cache.batch_repeat_interleave(len(sequencias))
            log_resto = torch.log_softmax(
                self.modelo(input_ids=ids, attention_mask=mascara, past_key_values=cache).logits.float(), dim=-1)
        # 3) pontuação de cada resposta = soma do log da probabilidade de cada pedaço da palavra
        pontos_seq = []
        for i, seq in enumerate(sequencias):
            total = log_primeiro[seq[0]]
            for j in range(1, len(seq)):
                total = total + log_resto[i, j - 1, seq[j]]
            pontos_seq.append(total)
        brutas, posicao = {}, 0
        for nome, variantes in ids_por_opcao.items():
            brutas[nome] = torch.logsumexp(torch.stack(pontos_seq[posicao:posicao + len(variantes)]), dim=0)
            posicao += len(variantes)
        # normalizo só entre as categorias permitidas (somam 1)
        normalizadas = torch.softmax(torch.stack(list(brutas.values())), dim=0).tolist()
        pontuacoes = {nome: round(p, 4) for nome, p in zip(brutas, normalizadas)}
        escolhida = max(pontuacoes, key=pontuacoes.get)
        return {
            "categoria": escolhida,
            "confianca": pontuacoes[escolhida],
            "pontuacoes": dict(sorted(pontuacoes.items(), key=lambda par: -par[1])),
            "texto_truncado": truncado,
            "tokens_entrada": tokens,
        }

    def _resumir(self, texto):
        import torch

        entrada, truncado, tokens = self._entrada("resumo", texto)
        with torch.inference_mode():
            saida = self.modelo.generate(
                **entrada,
                max_new_tokens=MAX_TOKENS_RESUMO,
                do_sample=False,
                repetition_penalty=1.05,
                max_time=TEMPO_LIMITE,          # o próprio generate para se passar do limite
                pad_token_id=self.tokenizer.eos_token_id,
            )
        novos = saida[0, entrada["input_ids"].shape[1]:]
        resumo = self.tokenizer.decode(novos, skip_special_tokens=True).strip()
        resumo = re.sub(r"\s+", " ", resumo)
        # o modelo nem sempre respeita o "no máximo 3 frases"; corto o excesso aqui
        frases = [f for f in re.split(r"(?<=[.!?])\s+", resumo) if f]
        resumo = " ".join(frases[:3])
        if len(resumo) < 10:
            raise RespostaInvalida("O modelo devolveu um resumo vazio ou curto demais.")
        return {
            "resumo": resumo,
            "frases": min(len(frases), 3),
            "frases_cortadas": max(len(frases) - 3, 0),
            "texto_truncado": truncado,
            "tokens_entrada": tokens,
            "tokens_gerados": int(novos.shape[0]),
        }

    def _executar(self, tarefa, texto, com_definicoes=True):
        if tarefa == "resumo":
            return self._resumir(texto)
        return self._classificar(tarefa, texto, com_definicoes)

    def contar_tokens(self, mensagens):
        prompt = self.tokenizer.apply_chat_template(mensagens, add_generation_prompt=True, tokenize=False)
        return len(self.tokenizer.encode(prompt, add_special_tokens=False))

    def _gerar_resposta(self, mensagens, max_novos):
        """Conversa: o modelo lê as mensagens (sistema + conversa + pergunta) e escreve a próxima."""
        import torch

        prompt = self.tokenizer.apply_chat_template(mensagens, add_generation_prompt=True, tokenize=False)
        entrada = self.tokenizer(prompt, return_tensors="pt").to(self.dispositivo)
        tokens_entrada = int(entrada["input_ids"].shape[1])
        with torch.inference_mode():
            saida = self.modelo.generate(
                **entrada,
                max_new_tokens=max_novos,
                do_sample=False,                # mesma pergunta, mesma resposta (dá para repetir o teste)
                repetition_penalty=1.05,
                max_time=TEMPO_LIMITE,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        novos = saida[0, tokens_entrada:]
        texto = self.tokenizer.decode(novos, skip_special_tokens=True).strip()
        if len(texto) < 2:
            raise RespostaInvalida("O modelo devolveu uma resposta vazia.")
        return {"texto": texto, "tokens_entrada": tokens_entrada, "tokens_saida": int(novos.shape[0]),
                "cortada": int(novos.shape[0]) >= max_novos}

    # ------------------------------------------------------------------ portas de entrada
    def processar(self, tarefa, texto, com_definicoes=True):
        """Tema, sentimento ou resumo de um texto (rota POST /processar_texto)."""
        return self._com_limites(self._executar, tarefa, texto, com_definicoes)

    def responder(self, mensagens, max_novos=MAX_TOKENS_RESPOSTA):
        """Próxima resposta de uma conversa (rota POST /conversar). Mesma fila e mesmo tempo limite."""
        return self._com_limites(self._gerar_resposta, mensagens, max_novos)

    def _com_limites(self, funcao, *argumentos):
        """
        Roda a tarefa respeitando dois limites:
        - fila: se outro pedido estiver usando o modelo por mais de ESPERA_NA_FILA s -> MotorOcupado
        - tempo: se a tarefa passar de TEMPO_LIMITE s -> TempoEsgotado
        """
        import torch

        if not self._trava.acquire(timeout=ESPERA_NA_FILA):
            raise MotorOcupado("O modelo está ocupado com outro pedido.")
        futuro = None
        try:
            inicio = time.perf_counter()
            futuro = self._executor.submit(funcao, *argumentos)
            resultado = futuro.result(timeout=TEMPO_LIMITE)
            resultado["segundos"] = round(time.perf_counter() - inicio, 2)
            return resultado
        except TempoDoFuturoEsgotado:
            raise TempoEsgotado(f"A análise passou de {TEMPO_LIMITE:.0f} s.") from None
        except (torch.OutOfMemoryError, MemoryError) as erro:
            raise SemMemoria(str(erro)) from erro
        except RuntimeError as erro:
            # em CPU a falta de memória chega como RuntimeError("... not enough memory ...")
            if "memory" in str(erro).lower():
                raise SemMemoria(str(erro)) from erro
            raise
        finally:
            if futuro is not None and not futuro.done():
                # a thread do modelo não pode ser interrompida no meio; a trava só é
                # liberada quando ela terminar, para o próximo pedido não disputar o modelo
                futuro.add_done_callback(lambda _: self._trava.release())
            else:
                self._trava.release()

    def info(self):
        return {
            "nome": self.nome,
            "dispositivo": self.dispositivo,
            "precisao": self.precisao,
            "parametros_milhoes": round(self.parametros / 1e6),
            "segundos_carregando": self.segundos_carregando,
        }

    # identificação usada pelo assistente (mesmo formato do motor via API)
    tipo = "local"

    def descricao(self):
        return {"tipo": "local", "nome": self.nome, "onde_roda": f"nesta máquina ({self.dispositivo}, {self.precisao})"}
