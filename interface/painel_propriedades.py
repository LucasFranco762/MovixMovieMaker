"""Painel contextual de propriedades (REQ-017, 19.4).

Flutua sobre a área do player (não redimensiona a janela), ancorado à esquerda.
Recolhe com animação para cima ao clicar fora ou após inatividade configurável,
mas nunca enquanto o usuário interage com seus controles.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QColorDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from core.tempo import formatar_timecode
from projetos.modelos import Clipe, Projeto

LARGURA = 300
ALTURA_MAX = 360


class PainelPropriedades(QFrame):
    """Filho do widget da área superior; posicionado manualmente (overlay)."""

    nome_alterado = pyqtSignal(str, str)         # clipe_id, novo nome
    cor_alterada = pyqtSignal(str, str)          # clipe_id, "#rrggbb" ou "" (padrão)
    volume_alterado = pyqtSignal(str, float)      # clipe_id, ganho de 0.0 a 2.0

    def __init__(self, parent: QWidget, inatividade_s: int) -> None:
        super().__init__(parent)
        self.setObjectName("painelPropriedades")
        self._clipe_ids: list[str] = []
        self._projeto: Projeto | None = None
        self._x = 8
        self._y = 8
        self._aberto = False
        self._anim: QPropertyAnimation | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._ao_expirar_inatividade)
        self.definir_inatividade(inatividade_s)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        topo = QHBoxLayout()
        self._titulo = QLabel("Propriedades")
        self._titulo.setObjectName("tituloPainel")
        fechar = QToolButton()
        fechar.setObjectName("semBorda")
        fechar.setText("✕")
        fechar.setToolTip("Recolher propriedades")
        fechar.clicked.connect(self.recolher)
        topo.addWidget(self._titulo, 1)
        topo.addWidget(fechar)
        lay.addLayout(topo)

        self._corpo = QWidget()
        form = QFormLayout(self._corpo)
        form.setContentsMargins(0, 6, 0, 0)
        self._nome = QLineEdit()
        self._nome.editingFinished.connect(self._aplicar_nome)
        self._inicio = QLabel("—")
        self._duracao = QLabel("—")
        self._entrada = QLabel("—")
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 200)
        self._volume.setValue(100)
        self._volume.setToolTip("0% silencia; 100% mantém o volume; até 200% amplifica")
        self._volume.sliderReleased.connect(self._aplicar_volume)
        self._botao_cor = QPushButton("Escolher cor…")
        self._botao_cor.clicked.connect(self._escolher_cor)
        self._botao_padrao = QPushButton("Usar cor padrão")
        self._botao_padrao.clicked.connect(lambda: self._emitir_cor(""))
        form.addRow("Nome", self._nome)
        form.addRow("Início", self._inicio)
        form.addRow("Duração", self._duracao)
        form.addRow("Entrada na mídia", self._entrada)
        form.addRow("Volume", self._volume)
        form.addRow("Cor do clipe", self._botao_cor)
        form.addRow("", self._botao_padrao)
        lay.addWidget(self._corpo)
        lay.addStretch(1)

        self.hide()
        QApplication.instance().installEventFilter(self)

    # ---- API ---------------------------------------------------------------------------------
    def definir_inatividade(self, segundos: int) -> None:
        self._timer.setInterval(max(1, segundos) * 1000)

    def esta_aberto(self) -> bool:
        return self._aberto

    def mostrar_para(self, projeto: Projeto, clipe_ids: list[str]) -> None:
        """Abre (ou atualiza) o painel para a seleção atual."""
        self._projeto, self._clipe_ids = projeto, list(clipe_ids)
        if not clipe_ids:
            self.recolher()
            return
        self._preencher()
        self._abrir()

    def atualizar(self, projeto: Projeto, clipe_ids: list[str]) -> None:
        """Atualiza o conteúdo se já estiver aberto; não reabre sozinho."""
        self._projeto, self._clipe_ids = projeto, list(clipe_ids)
        if not clipe_ids:
            self.recolher()
        elif self._aberto and not self._nome.hasFocus():
            self._preencher()

    # ---- conteúdo -----------------------------------------------------------------------------------
    def _clipe_unico(self) -> Clipe | None:
        if self._projeto is None or len(self._clipe_ids) != 1:
            return None
        try:
            return self._projeto.localizar_clipe(self._clipe_ids[0])[1]
        except KeyError:
            return None

    def _preencher(self) -> None:
        assert self._projeto is not None
        fps = self._projeto.config.fps
        n = len(self._clipe_ids)
        unico = self._clipe_unico()
        self._titulo.setText("Propriedades do clipe" if n == 1 else f"{n} clipes selecionados")
        self._nome.setEnabled(unico is not None)
        self._volume.setEnabled(unico is not None)
        if unico is not None:
            self._nome.setText(unico.nome)
            self._inicio.setText(formatar_timecode(unico.inicio, fps))
            self._duracao.setText(formatar_timecode(unico.duracao, fps))
            self._entrada.setText(formatar_timecode(unico.entrada, fps))
            self._volume.setValue(round(unico.volume * 100))
        else:
            self._nome.setText("")
            for r in (self._inicio, self._duracao, self._entrada):
                r.setText("—")

    def _aplicar_nome(self) -> None:
        unico = self._clipe_unico()
        if unico is not None and self._nome.text() != unico.nome:
            self.nome_alterado.emit(unico.id, self._nome.text())

    def _aplicar_volume(self) -> None:
        unico = self._clipe_unico()
        if unico is not None:
            self.volume_alterado.emit(unico.id, self._volume.value() / 100)

    def _escolher_cor(self) -> None:
        unico = self._clipe_unico()
        inicial = QColor(unico.cor_efetiva()) if unico else QColor("#3b82c4")
        cor = QColorDialog.getColor(inicial, self, "Cor do clipe")
        if cor.isValid():
            self._emitir_cor(cor.name())

    def _emitir_cor(self, cor: str) -> None:
        for cid in self._clipe_ids:
            self.cor_alterada.emit(cid, cor)

    # ---- abrir/recolher com animação --------------------------------------------------------------------
    def posicionar(self, x: int = 8, y: int = 8) -> None:
        """Chamado pela janela quando a área do player é redimensionada."""
        self._x, self._y = x, y
        if self._aberto and not self._animando():
            self.setGeometry(self._geometria_aberta())

    def _altura(self) -> int:
        pai = self.parentWidget()
        return min(ALTURA_MAX, max(160, (pai.height() if pai else ALTURA_MAX) - 16))

    def _geometria_aberta(self) -> QRect:
        return QRect(self._x, self._y, LARGURA, self._altura())

    def _geometria_recolhida(self) -> QRect:
        g = self._geometria_aberta()
        return QRect(g.x(), g.y(), g.width(), 0)       # recolhe para cima

    def _animando(self) -> bool:
        return self._anim is not None and self._anim.state() == QPropertyAnimation.State.Running

    def _animar(self, de: QRect, para: QRect, ao_terminar=None) -> None:
        if self._anim is not None:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.setStartValue(de)
        self._anim.setEndValue(para)
        if ao_terminar:
            self._anim.finished.connect(ao_terminar)
        self._anim.start()

    def _abrir(self) -> None:
        self._reiniciar_inatividade()
        if self._aberto:
            return
        self._aberto = True
        self.setGeometry(self._geometria_recolhida())
        self.show()
        self.raise_()
        self._animar(self._geometria_recolhida(), self._geometria_aberta())

    def recolher(self) -> None:
        if not self._aberto:
            return
        self._aberto = False
        self._timer.stop()
        self._animar(self.geometry(), self._geometria_recolhida(),
                     lambda: None if self._aberto else self.hide())

    # ---- inatividade e clique fora ------------------------------------------------------------------------------
    def _reiniciar_inatividade(self) -> None:
        if self._aberto:
            self._timer.start()

    def _usuario_interagindo(self) -> bool:
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return True                              # arrastando slider/botão
        foco = QApplication.focusWidget()
        return bool(foco and self.isAncestorOf(foco) and isinstance(foco, QLineEdit)) \
            or QApplication.activeModalWidget() is not None

    def _ao_expirar_inatividade(self) -> None:
        if self._usuario_interagindo():
            self._timer.start()                       # tenta de novo mais tarde
        else:
            self.recolher()

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:  # noqa: N802 (nome Qt)
        if not self._aberto:
            return False
        tipo = ev.type()
        if tipo == QEvent.Type.MouseButtonPress and isinstance(obj, QWidget):
            if not (obj is self or self.isAncestorOf(obj)) and not self._eh_clipe_ou_barra(obj):
                self.recolher()                      # clique fora
            else:
                self._reiniciar_inatividade()
        elif tipo in (QEvent.Type.MouseMove, QEvent.Type.KeyPress, QEvent.Type.Wheel) \
                and isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj)):
            self._reiniciar_inatividade()
        return False

    def _eh_clipe_ou_barra(self, obj: QWidget) -> bool:
        """Cliques na timeline mudam a seleção; quem decide recolher é a janela."""
        w: QWidget | None = obj
        while w is not None:
            if w.objectName() == "timelineRaiz":
                return True
            w = w.parentWidget()
        return False
