"""Padrão Command para edição não destrutiva com desfazer/refazer (REQ-008).

Cada comando altera somente o modelo ``Projeto``; os arquivos de mídia originais
nunca são tocados. Os comandos validam antes de alterar, de modo que uma
operação inválida não deixa o modelo em estado parcial.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any

from core.constantes import LIMITE_HISTORICO_COMANDOS
from core.excecoes import ErroEdicao
from editor.clipes import calcular_divisao
from editor.faixas import exigir_faixa_editavel, exigir_posicao_livre
from projetos.modelos import Clipe, Faixa, Projeto, novo_id


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
    CAMPOS = ("nome", "cor", "bloqueada", "visivel", "silenciada")

    def __init__(self, faixa_id: str, **alteracoes: Any) -> None:
        invalidos = set(alteracoes) - set(self.CAMPOS)
        if invalidos:
            raise ErroEdicao(f"Propriedades de faixa inválidas: {sorted(invalidos)}")
        self.faixa_id = faixa_id
        self.novos = alteracoes
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
        exigir_faixa_editavel(faixa)
        dur_esq, entrada_dir, dur_dir = calcular_divisao(clipe, self.frame)
        self._faixa_id, self._duracao_original = faixa.id, clipe.duracao
        direita = replace(clipe, id=self.novo_clipe_id, inicio=self.frame,
                          duracao=dur_dir, entrada=entrada_dir)
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
    """Altera propriedades não temporais do clipe (nome, cor)."""
    descricao = "Alterar clipe"
    CAMPOS = ("nome", "cor")

    def __init__(self, clipe_id: str, **alteracoes: Any) -> None:
        invalidos = set(alteracoes) - set(self.CAMPOS)
        if invalidos:
            raise ErroEdicao(f"Propriedades de clipe inválidas: {sorted(invalidos)}")
        self.clipe_id = clipe_id
        self.novos = alteracoes
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
