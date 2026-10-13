"""Padrão Command para edição não destrutiva com desfazer/refazer (REQ-008).

Cada comando altera somente o modelo ``Projeto``; os arquivos de mídia originais
nunca são tocados. Os comandos validam antes de alterar, de modo que uma
operação inválida não deixa o modelo em estado parcial.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any

from core.constantes import (
    FAIXA_VIDEO, LIMITE_HISTORICO_COMANDOS, TIPOS_EFEITO, TIPO_LEGENDA, TIPO_TEXTO,
)
from core.excecoes import ErroEdicao
from editor.clipes import calcular_divisao
from editor.faixas import exigir_faixa_editavel, exigir_posicao_livre
from projetos.modelos import Clipe, Faixa, Projeto, Transicao, novo_id


class Comando(ABC):
    descricao: str = "Operação"

    @abstractmethod
    def executar(self, projeto: Projeto) -> None: ...

    @abstractmethod
    def desfazer(self, projeto: Projeto) -> None: ...


class HistoricoComandos:
    def __init__(self, limite: int = LIMITE_HISTORICO_COMANDOS) -> None:
        self._desfazer: list[Comando] = []
        self._refazer: list[Comando] = []
        self._limite = limite

    def executar(self, projeto: Projeto, comando: Comando) -> None:
        comando.executar(projeto)       # se falhar, nada é registrado
        self._desfazer.append(comando)
        if len(self._desfazer) > self._limite:
            self._desfazer.pop(0)
        self._refazer.clear()

    def pode_desfazer(self) -> bool:
        return bool(self._desfazer)

    def pode_refazer(self) -> bool:
        return bool(self._refazer)

    def desfazer(self, projeto: Projeto) -> Comando | None:
        if not self._desfazer:
            return None
        cmd = self._desfazer.pop()
        cmd.desfazer(projeto)
        self._refazer.append(cmd)
        return cmd

    def refazer(self, projeto: Projeto) -> Comando | None:
        if not self._refazer:
            return None
        cmd = self._refazer.pop()
        cmd.executar(projeto)
        self._desfazer.append(cmd)
        return cmd

    def limpar(self) -> None:
        self._desfazer.clear()
        self._refazer.clear()


# ---------------------------------------------------------------- faixas
class AdicionarFaixa(Comando):
    descricao = "Adicionar faixa"

    def __init__(self, faixa: Faixa) -> None:
        self.faixa = faixa

    def executar(self, projeto: Projeto) -> None:
        projeto.faixas.append(self.faixa)

    def desfazer(self, projeto: Projeto) -> None:
        projeto.faixas.remove(self.faixa)


class AlterarFaixa(Comando):
    """Altera nome, cor, bloqueio, visibilidade ou silenciamento de uma faixa."""
    descricao = "Alterar faixa"
    CAMPOS = ("nome", "cor", "bloqueada", "visivel", "silenciada", "volume")

    def __init__(self, faixa_id: str, **alteracoes: Any) -> None:
        invalidos = set(alteracoes) - set(self.CAMPOS)
        if invalidos:
            raise ErroEdicao(f"Propriedades de faixa inválidas: {sorted(invalidos)}")
        self.faixa_id = faixa_id
        self.novos = dict(alteracoes)
        if "volume" in self.novos:
            self.novos["volume"] = max(0.0, min(2.0, float(self.novos["volume"])))
        self.antigos: dict[str, Any] = {}

    def executar(self, projeto: Projeto) -> None:
        faixa = projeto.faixa_por_id(self.faixa_id)
        self.antigos = {k: getattr(faixa, k) for k in self.novos}
        for k, v in self.novos.items():
            setattr(faixa, k, v)

    def desfazer(self, projeto: Projeto) -> None:
        faixa = projeto.faixa_por_id(self.faixa_id)
        for k, v in self.antigos.items():
            setattr(faixa, k, v)


# ---------------------------------------------------------------- clipes
class AdicionarClipe(Comando):
    descricao = "Adicionar clipe"

    def __init__(self, faixa_id: str, clipe: Clipe) -> None:
        self.faixa_id = faixa_id
        self.clipe = clipe

    def executar(self, projeto: Projeto) -> None:
        faixa = projeto.faixa_por_id(self.faixa_id)
        exigir_faixa_editavel(faixa)
        if not faixa.aceita(self.clipe.tipo):
            raise ErroEdicao(f"A faixa '{faixa.nome}' não aceita clipes do tipo '{self.clipe.tipo}'.")
        exigir_posicao_livre(faixa, self.clipe.inicio, self.clipe.duracao)
        faixa.clipes.append(self.clipe)
        faixa.clipes.sort(key=lambda c: c.inicio)

    def desfazer(self, projeto: Projeto) -> None:
        projeto.faixa_por_id(self.faixa_id).clipes.remove(self.clipe)


class RemoverClipe(Comando):
    descricao = "Excluir clipe"

    def __init__(self, clipe_id: str) -> None:
        self.clipe_id = clipe_id
        self._faixa_id = ""
        self._clipe: Clipe | None = None

    def executar(self, projeto: Projeto) -> None:
        faixa, clipe = projeto.localizar_clipe(self.clipe_id)
        exigir_faixa_editavel(faixa)
        if projeto.transicoes_do_clipe(clipe.id):
            raise ErroEdicao("Remova a transição ligada ao clipe antes de excluí-lo.")
        self._faixa_id, self._clipe = faixa.id, clipe
        faixa.clipes.remove(clipe)

    def desfazer(self, projeto: Projeto) -> None:
        assert self._clipe is not None
        faixa = projeto.faixa_por_id(self._faixa_id)
        faixa.clipes.append(self._clipe)
        faixa.clipes.sort(key=lambda c: c.inicio)


class MoverClipe(Comando):
    descricao = "Mover clipe"

    def __init__(self, clipe_id: str, novo_inicio: int, faixa_destino_id: str | None = None) -> None:
        self.clipe_id = clipe_id
        self.novo_inicio = novo_inicio
        self.faixa_destino_id = faixa_destino_id
        self._origem_id = ""
        self._inicio_antigo = 0

    def executar(self, projeto: Projeto) -> None:
        origem, clipe = projeto.localizar_clipe(self.clipe_id)
        if projeto.transicoes_do_clipe(clipe.id):
            raise ErroEdicao("Remova a transição ligada ao clipe antes de movê-lo.")
        destino = projeto.faixa_por_id(self.faixa_destino_id) if self.faixa_destino_id else origem
        exigir_faixa_editavel(origem)
        exigir_faixa_editavel(destino)
        if not destino.aceita(clipe.tipo):
            raise ErroEdicao(f"A faixa '{destino.nome}' não aceita clipes do tipo '{clipe.tipo}'.")
        exigir_posicao_livre(destino, self.novo_inicio, clipe.duracao, frozenset({clipe.id}))
        self._origem_id, self._inicio_antigo = origem.id, clipe.inicio
        origem.clipes.remove(clipe)
        clipe.inicio = self.novo_inicio
        destino.clipes.append(clipe)
        destino.clipes.sort(key=lambda c: c.inicio)

    def desfazer(self, projeto: Projeto) -> None:
        destino, clipe = projeto.localizar_clipe(self.clipe_id)
        origem = projeto.faixa_por_id(self._origem_id)
        destino.clipes.remove(clipe)
        clipe.inicio = self._inicio_antigo
        origem.clipes.append(clipe)
        origem.clipes.sort(key=lambda c: c.inicio)


class DividirClipe(Comando):
    descricao = "Dividir clipe"

    def __init__(self, clipe_id: str, frame: int) -> None:
        self.clipe_id = clipe_id
        self.frame = frame
        self.novo_clipe_id = novo_id()      # fixo, para o refazer reproduzir o mesmo id
        self._duracao_original = 0
        self._faixa_id = ""

    def executar(self, projeto: Projeto) -> None:
        faixa, clipe = projeto.localizar_clipe(self.clipe_id)
        if projeto.transicoes_do_clipe(clipe.id):
            raise ErroEdicao("Remova a transição ligada ao clipe antes de dividi-lo.")
        exigir_faixa_editavel(faixa)
        dur_esq, entrada_dir, dur_dir = calcular_divisao(clipe, self.frame)
        self._faixa_id, self._duracao_original = faixa.id, clipe.duracao
        direita = replace(clipe, id=self.novo_clipe_id, inicio=self.frame,
                          duracao=dur_dir, entrada=entrada_dir, efeitos=dict(clipe.efeitos))
        clipe.duracao = dur_esq
        faixa.clipes.append(direita)
        faixa.clipes.sort(key=lambda c: c.inicio)

    def desfazer(self, projeto: Projeto) -> None:
        faixa = projeto.faixa_por_id(self._faixa_id)
        _, direita = projeto.localizar_clipe(self.novo_clipe_id)
        faixa.clipes.remove(direita)
        _, esquerda = projeto.localizar_clipe(self.clipe_id)
        esquerda.duracao = self._duracao_original


class AlterarClipe(Comando):
    """Altera propriedades não temporais do clipe."""
    descricao = "Alterar clipe"
    CAMPOS = ("nome", "cor", "volume", "efeitos")

    def __init__(self, clipe_id: str, **alteracoes: Any) -> None:
        invalidos = set(alteracoes) - set(self.CAMPOS)
        if invalidos:
            raise ErroEdicao(f"Propriedades de clipe inválidas: {sorted(invalidos)}")
        self.clipe_id = clipe_id
        self.novos = dict(alteracoes)
        if "volume" in self.novos:
            self.novos["volume"] = max(0.0, min(2.0, float(self.novos["volume"])))
        if "efeitos" in self.novos:
            if not isinstance(self.novos["efeitos"], dict):
                raise ErroEdicao("A lista de efeitos do clipe é inválida.")
            self.novos["efeitos"] = {
                tipo: int(intensidade)
                for tipo, intensidade in self.novos["efeitos"].items()
            }
            desconhecidos = set(self.novos["efeitos"]) - set(TIPOS_EFEITO)
            intensidades = self.novos["efeitos"].values()
            if desconhecidos or any(not 0 <= valor <= 100 for valor in intensidades):
                raise ErroEdicao("A lista de efeitos do clipe é inválida.")
        self.antigos: dict[str, Any] = {}

    def executar(self, projeto: Projeto) -> None:
        _, clipe = projeto.localizar_clipe(self.clipe_id)
        self.antigos = {k: getattr(clipe, k) for k in self.novos}
        for k, v in self.novos.items():
            setattr(clipe, k, v)

    def desfazer(self, projeto: Projeto) -> None:
        _, clipe = projeto.localizar_clipe(self.clipe_id)
        for k, v in self.antigos.items():
            setattr(clipe, k, v)


class AlterarElementoTexto(Comando):
    """Altera conteúdo, estilo ou duração de um texto/legenda."""

    descricao = "Alterar texto"
    CAMPOS = (
        "conteudo", "duracao", "familia_fonte", "tamanho_fonte", "cor_texto",
        "cor_fundo_texto", "alinhamento_h", "alinhamento_v",
    )

    def __init__(self, clipe_id: str, **alteracoes: Any) -> None:
        invalidos = set(alteracoes) - set(self.CAMPOS)
        if invalidos:
            raise ErroEdicao(f"Propriedades de texto inválidas: {sorted(invalidos)}")
        if "conteudo" in alteracoes and not str(alteracoes["conteudo"]).strip():
            raise ErroEdicao("Digite o conteúdo do texto.")
        self.clipe_id = clipe_id
        self.novos = dict(alteracoes)
        if "duracao" in self.novos:
            self.novos["duracao"] = int(self.novos["duracao"])
        if "tamanho_fonte" in self.novos:
            self.novos["tamanho_fonte"] = max(8, min(300, int(self.novos["tamanho_fonte"])))
        self.antigos: dict[str, Any] = {}

    def executar(self, projeto: Projeto) -> None:
        faixa, clipe = projeto.localizar_clipe(self.clipe_id)
        if clipe.tipo not in (TIPO_TEXTO, TIPO_LEGENDA):
            raise ErroEdicao("O clipe selecionado não é um texto ou legenda.")
        exigir_faixa_editavel(faixa)
        duracao = self.novos.get("duracao", clipe.duracao)
        exigir_posicao_livre(faixa, clipe.inicio, duracao, frozenset({clipe.id}))
        self.antigos = {campo: getattr(clipe, campo) for campo in self.novos}
        for campo, valor in self.novos.items():
            setattr(clipe, campo, valor)

    def desfazer(self, projeto: Projeto) -> None:
        _, clipe = projeto.localizar_clipe(self.clipe_id)
        for campo, valor in self.antigos.items():
            setattr(clipe, campo, valor)


class AlterarMixagemAudio(Comando):
    """Altera o balanço global de áudio com suporte a desfazer/refazer."""

    descricao = "Alterar mixagem de áudio"
    CAMPOS = ("volume_original", "volume_adicionado")

    def __init__(self, **alteracoes: Any) -> None:
        invalidos = set(alteracoes) - set(self.CAMPOS)
        if invalidos:
            raise ErroEdicao(f"Propriedades de mixagem inválidas: {sorted(invalidos)}")
        self.novos = {k: max(0.0, min(2.0, float(v))) for k, v in alteracoes.items()}
        self.antigos: dict[str, float] = {}

    def executar(self, projeto: Projeto) -> None:
        self.antigos = {k: getattr(projeto.mixagem_audio, k) for k in self.novos}
        for k, v in self.novos.items():
            setattr(projeto.mixagem_audio, k, v)

    def desfazer(self, projeto: Projeto) -> None:
        for k, v in self.antigos.items():
            setattr(projeto.mixagem_audio, k, v)


# ---------------------------------------------------------------- transições
class AdicionarTransicao(Comando):
    descricao = "Adicionar transição"

    def __init__(self, transicao: Transicao) -> None:
        self.transicao = transicao
        self._posicoes: dict[str, int] = {}

    def executar(self, projeto: Projeto) -> None:
        faixa = projeto.faixa_por_id(self.transicao.faixa_id)
        exigir_faixa_editavel(faixa)
        if faixa.tipo != FAIXA_VIDEO:
            raise ErroEdicao("Transições visuais só podem ser aplicadas em faixas de vídeo.")
        try:
            indice_a = next(i for i, c in enumerate(faixa.clipes)
                            if c.id == self.transicao.clipe_origem_id)
            indice_b = next(i for i, c in enumerate(faixa.clipes)
                            if c.id == self.transicao.clipe_destino_id)
        except StopIteration as exc:
            raise ErroEdicao("Os clipes da transição não foram encontrados na faixa.") from exc
        if indice_b != indice_a + 1:
            raise ErroEdicao("Selecione dois clipes consecutivos da mesma faixa.")
        origem, destino = faixa.clipes[indice_a], faixa.clipes[indice_b]
        if any(t.clipe_origem_id == origem.id and t.clipe_destino_id == destino.id
               for t in projeto.transicoes):
            raise ErroEdicao("Já existe uma transição entre esses clipes.")
        if origem.fim != destino.inicio:
            raise ErroEdicao("Os clipes precisam estar unidos, sem espaço entre eles.")
        limite = min(origem.duracao, destino.duracao) // 2
        if self.transicao.duracao > limite:
            raise ErroEdicao(
                f"A transição pode ter no máximo {limite} frame(s) para estes clipes.")
        afetados = faixa.clipes[indice_b:]
        self._posicoes = {c.id: c.inicio for c in afetados}
        for clipe in afetados:
            clipe.inicio -= self.transicao.duracao
        projeto.transicoes.append(self.transicao)

    def desfazer(self, projeto: Projeto) -> None:
        projeto.transicoes.remove(self.transicao)
        faixa = projeto.faixa_por_id(self.transicao.faixa_id)
        for clipe in faixa.clipes:
            if clipe.id in self._posicoes:
                clipe.inicio = self._posicoes[clipe.id]


class RemoverTransicao(Comando):
    descricao = "Remover transição"

    def __init__(self, transicao_id: str) -> None:
        self.transicao_id = transicao_id
        self._transicao: Transicao | None = None
        self._posicoes: dict[str, int] = {}

    def executar(self, projeto: Projeto) -> None:
        transicao = projeto.transicao_por_id(self.transicao_id)
        faixa = projeto.faixa_por_id(transicao.faixa_id)
        exigir_faixa_editavel(faixa)
        indice = next((i for i, c in enumerate(faixa.clipes)
                       if c.id == transicao.clipe_destino_id), None)
        if indice is None:
            raise ErroEdicao("O clipe de destino da transição não foi encontrado.")
        afetados = faixa.clipes[indice:]
        self._transicao = transicao
        self._posicoes = {c.id: c.inicio for c in afetados}
        for clipe in afetados:
            clipe.inicio += transicao.duracao
        projeto.transicoes.remove(transicao)

    def desfazer(self, projeto: Projeto) -> None:
        assert self._transicao is not None
        faixa = projeto.faixa_por_id(self._transicao.faixa_id)
        for clipe in faixa.clipes:
            if clipe.id in self._posicoes:
                clipe.inicio = self._posicoes[clipe.id]
        projeto.transicoes.append(self._transicao)
