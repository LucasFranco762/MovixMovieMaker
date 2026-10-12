"""Operações puras sobre clipes (sem interface, sem motor multimídia)."""
from __future__ import annotations

from core.excecoes import ErroEdicao
from projetos.modelos import Clipe, MidiaRef, novo_id


def criar_clipe(midia: MidiaRef, inicio: int, duracao_imagem: int = 150) -> Clipe:
    """Cria um clipe que usa a mídia inteira.

    Imagens não têm duração própria; ``duracao_imagem`` (frames) é usada.
    """
    duracao = midia.duracao_frames if midia.duracao_frames > 0 else duracao_imagem
    return Clipe(
        id=novo_id(), midia_id=midia.id, tipo=midia.tipo,
        inicio=inicio, duracao=duracao, entrada=0, nome=midia.nome,
    )


def validar_divisao(clipe: Clipe, frame: int) -> None:
    if not (clipe.inicio < frame < clipe.fim):
        raise ErroEdicao("O ponto de corte deve estar dentro do clipe (não nas extremidades).")


def calcular_divisao(clipe: Clipe, frame: int) -> tuple[int, int, int]:
    """Devolve (duracao_esquerda, inicio_direita_na_midia, duracao_direita)."""
    validar_divisao(clipe, frame)
    dur_esq = frame - clipe.inicio
    return dur_esq, clipe.entrada + dur_esq, clipe.duracao - dur_esq
