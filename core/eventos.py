"""Barramento de eventos simples, independente de Qt (testável sem interface).

A interface pode conectar os eventos a sinais Qt na camada ``interface``.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

_log = logging.getLogger(__name__)

Assinante = Callable[..., None]


class BarramentoEventos:
    """Publicação/assinatura síncrona por nome de evento."""

    def __init__(self) -> None:
        self._assinantes: dict[str, list[Assinante]] = defaultdict(list)

    def assinar(self, evento: str, assinante: Assinante) -> None:
        if assinante not in self._assinantes[evento]:
            self._assinantes[evento].append(assinante)

    def cancelar(self, evento: str, assinante: Assinante) -> None:
        if assinante in self._assinantes.get(evento, []):
            self._assinantes[evento].remove(assinante)

    def publicar(self, evento: str, *args: Any, **kwargs: Any) -> None:
        for assinante in list(self._assinantes.get(evento, [])):
            try:
                assinante(*args, **kwargs)
            except Exception:  # noqa: BLE001 - um assinante não derruba os demais
                _log.exception("Erro no assinante do evento '%s'", evento)


# Nomes de eventos usados pelo aplicativo
PROJETO_ALTERADO = "projeto_alterado"      # modelo mudou (edição, undo/redo)
PROJETO_CARREGADO = "projeto_carregado"    # novo/abrir
PROJETO_SALVO = "projeto_salvo"
SELECAO_ALTERADA = "selecao_alterada"
POSICAO_ALTERADA = "posicao_alterada"      # cursor de reprodução (frames)
MIDIAS_ALTERADAS = "midias_alteradas"
