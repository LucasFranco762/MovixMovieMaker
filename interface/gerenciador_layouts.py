"""Aplica e persiste os três layouts na janela (REQ-017, 19.10–19.12).

Regra central: somente ações do USUÁRIO (arrastar divisores, recolher/expandir)
gravam preferências. Adaptações temporárias (janela pequena, tela cheia,
aplicação programática de um layout) usam ``_suspenso`` e não gravam nada.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QSplitter, QWidget

from core import layouts
from core.configuracoes import Configuracoes
from core.layouts import EstadoLayout
from interface.timeline import Timeline

_log = logging.getLogger(__name__)

LARGURA_MIN_JANELA_PARA_PAINEL = 900     # abaixo disso o painel recolhe (temporário)


class GerenciadorLayouts:
    def __init__(self, config: Configuracoes, split_horizontal: QSplitter, split_vertical: QSplitter,
                 painel: QWidget, player: QWidget, timeline: Timeline) -> None:
        self._config = config
        self._sh, self._sv = split_horizontal, split_vertical
        self._painel, self._player, self._timeline = painel, player, timeline
        self.layout_id: str = config.obter("layout.atual")
        if self.layout_id not in layouts.LAYOUTS:
            self.layout_id = "classico"
        self.estado: EstadoLayout = layouts.carregar_estado(config, self.layout_id)
        self._suspenso = 0
        self._adaptado = False
        self._sh.splitterMoved.connect(self._ao_mover_divisor)
        self._sv.splitterMoved.connect(self._ao_mover_divisor)

    # ---- aplicar ---------------------------------------------------------------------------------
    def aplicar(self, layout_id: str, lembrar: bool = True) -> None:
        """Troca de layout imediatamente, sem fechar projeto nem descartar alterações."""
        if layout_id not in layouts.LAYOUTS:
            raise KeyError(layout_id)
        self.layout_id = layout_id
        self.estado = layouts.carregar_estado(self._config, layout_id)
        if lembrar:
            self._config.definir("layout.atual", layout_id)
        self.reaplicar_estado()

    def reaplicar_estado(self) -> None:
        self._suspenso += 1
        try:
            e = self.estado
            self._painel.setVisible(e.painel_aberto)
            self._timeline.definir_recolhida(e.timeline_recolhida)
            self._ajustar_tamanhos()
        finally:
            self._suspenso -= 1
        QTimer.singleShot(0, self._ajustar_tamanhos_adiado)   # após a janela ter tamanho real

    def _ajustar_tamanhos_adiado(self) -> None:
        self._suspenso += 1
        try:
            self._ajustar_tamanhos()
        finally:
            self._suspenso -= 1

    def _ajustar_tamanhos(self) -> None:
        e = self.estado
        total_v = max(self._sv.height(), 1)
        altura_tl = self._timeline.altura_barra() if e.timeline_recolhida else min(e.altura_timeline, total_v - 120)
        self._sv.setSizes([max(total_v - altura_tl, 120), max(altura_tl, 1)])
        total_h = max(self._sh.width(), 1)
        if self._painel.isVisible():
            largura = min(e.largura_painel, max(total_h - 240, 160))
            self._sh.setSizes([largura, max(total_h - largura, 240)])
        else:
            self._sh.setSizes([0, total_h])

    # ---- ações do usuário (persistem) -------------------------------------------------------------------
    def _ao_mover_divisor(self, *_args) -> None:
        if self._suspenso or self._adaptado:
            return
        if self._painel.isVisible():
            self.estado.largura_painel = max(160, self._sh.sizes()[0])
        if not self._timeline.esta_recolhida():
            self.estado.altura_timeline = max(80, self._sv.sizes()[1])    # mantém a altura anterior se recolhida
        self.salvar()

    def definir_painel_aberto(self, aberto: bool, categoria: str | None = None) -> None:
        self.estado.painel_aberto = aberto
        if categoria:
            self.estado.categoria_ativa = categoria
        self._painel.setVisible(aberto)
        self._suspenso += 1
        try:
            self._ajustar_tamanhos()
        finally:
            self._suspenso -= 1
        self.salvar()

    def definir_timeline_recolhida(self, recolhida: bool) -> None:
        """Chamado após o usuário recolher/expandir; restaura a altura anterior ao expandir."""
        self.estado.timeline_recolhida = recolhida
        self._suspenso += 1
        try:
            self._ajustar_tamanhos()
        finally:
            self._suspenso -= 1
        self.salvar()

    def salvar(self) -> None:
        try:
            layouts.salvar_estado(self._config, self.layout_id, self.estado)
        except Exception:  # noqa: BLE001 - falha ao salvar preferências não pode derrubar a UI
            _log.exception("Não foi possível salvar o estado do layout '%s'.", self.layout_id)

    # ---- adaptação temporária (19.12) -----------------------------------------------------------------------
    def adaptar_ao_tamanho(self, largura_janela: int) -> None:
        """Recolhe o painel em janelas estreitas SEM alterar o estado persistente."""
        deve_ocultar = largura_janela < LARGURA_MIN_JANELA_PARA_PAINEL
        if deve_ocultar and not self._adaptado:
            self._adaptado = True
            self._painel.setVisible(False)
        elif not deve_ocultar and self._adaptado:
            self._adaptado = False
            self._painel.setVisible(self.estado.painel_aberto)
            self._suspenso += 1
            try:
                self._ajustar_tamanhos()
            finally:
                self._suspenso -= 1

    @property
    def adaptado(self) -> bool:
        return self._adaptado
