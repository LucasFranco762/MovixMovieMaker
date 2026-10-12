"""Regras de validação e operações de faixas (sem interface)."""
from __future__ import annotations

from core.constantes import FAIXA_AUDIO, FAIXA_VIDEO
from core.excecoes import ErroEdicao
from projetos.modelos import Faixa, Projeto, novo_id


def exigir_faixa_editavel(faixa: Faixa) -> None:
    if faixa.bloqueada:
        raise ErroEdicao(f"A faixa '{faixa.nome}' está bloqueada.")


def encontrar_sobreposicao(faixa: Faixa, inicio: int, duracao: int,
                           ignorar: frozenset[str] = frozenset()) -> str | None:
    """Devolve o id do primeiro clipe que colide com [inicio, inicio+duracao)."""
    fim = inicio + duracao
    for c in faixa.clipes:
        if c.id in ignorar:
            continue
        if inicio < c.fim and c.inicio < fim:
            return c.id
    return None


def exigir_posicao_livre(faixa: Faixa, inicio: int, duracao: int,
                         ignorar: frozenset[str] = frozenset()) -> None:
    if inicio < 0:
        raise ErroEdicao("O clipe não pode começar antes do frame 0.")
    if duracao <= 0:
        raise ErroEdicao("A duração do clipe deve ser de pelo menos 1 frame.")
    if encontrar_sobreposicao(faixa, inicio, duracao, ignorar) is not None:
        raise ErroEdicao(
            f"Já existe um clipe nessa posição da faixa '{faixa.nome}'. "
            "Use outra faixa para sobrepor vídeos."
        )


def proximo_nome_faixa(projeto: Projeto, tipo: str) -> str:
    base = "Vídeo" if tipo == FAIXA_VIDEO else "Áudio"
    n = sum(1 for f in projeto.faixas if f.tipo == tipo) + 1
    return f"{base} {n}"


def criar_faixa(projeto: Projeto, tipo: str) -> Faixa:
    if tipo not in (FAIXA_VIDEO, FAIXA_AUDIO):
        raise ErroEdicao(f"Tipo de faixa inválido: {tipo!r}.")
    return Faixa(novo_id(), proximo_nome_faixa(projeto, tipo), tipo)
