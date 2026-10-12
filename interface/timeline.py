"""Timeline inferior (REQ-006, REQ-017 19.6–19.9).

Desenha o modelo real do projeto (faixas e clipes). Implementado: régua, cursor,
zoom, rolagem, seleção (Ctrl alterna), mover um clipe arrastando (inclusive entre
faixas compatíveis) com snapping opcional, bloquear/ocultar/silenciar faixas,
criar faixas, dividir no cursor, excluir, barra fixa e barra contextual.

Ainda não implementado: arrastar mídia da biblioteca, mover vários clipes juntos,
agrupar, ripple, redimensionar bordas do clipe, renomear/reordenar faixas, barra
contextual flutuando junto ao clipe (hoje é uma barra fixa sob a barra principal).
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QColorDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollBar, QToolButton,
    QVBoxLayout, QWidget,
)

from core.constantes import FAIXA_AUDIO, ICONES_CATEGORIA
from core.controlador import Controlador
from core.eventos import (
    MIDIAS_ALTERADAS, POSICAO_ALTERADA, PROJETO_ALTERADO, PROJETO_CARREGADO, SELECAO_ALTERADA,
)
from core.excecoes import ErroEdicao
from core.tempo import fps_nominal, formatar_timecode
from interface import estilos

_log = logging.getLogger(__name__)

ALTURA_REGUA = 26
ALTURA_FAIXA = 46
LARGURA_CABECALHO = 140
TOLERANCIA_SNAP_PX = 8
PPF_MIN, PPF_MAX = 0.02, 40.0


class CanvasTimeline(QWidget):
    erro = pyqtSignal(str)
    limites_alteradas = pyqtSignal()

    def __init__(self, controlador: Controlador) -> None:
        super().__init__()
        self._c = controlador
        self.setMinimumHeight(ALTURA_REGUA + ALTURA_FAIXA)
        self.setMouseTracking(False)
        self.ppf = 2.0                     # pixels por frame
        self.scroll_x = 0
        self.scroll_y = 0
        self.snapping = True
        self._scrub = False
        self._press: dict | None = None    # estado do arrasto de clipe
        self._fantasma: tuple[int, int] | None = None   # (inicio, indice_faixa)

    # ---- geometria -----------------------------------------------------------------------
    def x_de_frame(self, frame: float) -> float:
        return LARGURA_CABECALHO + frame * self.ppf - self.scroll_x

    def frame_de_x(self, x: float) -> int:
        return int(round((x - LARGURA_CABECALHO + self.scroll_x) / self.ppf))

    def y_da_faixa(self, indice: int) -> int:
        return ALTURA_REGUA + indice * ALTURA_FAIXA - self.scroll_y

    def indice_faixa_em(self, y: float) -> int | None:
        if y < ALTURA_REGUA:
            return None
        i = int((y + self.scroll_y - ALTURA_REGUA) // ALTURA_FAIXA)
        return i if 0 <= i < len(self._c.projeto.faixas) else None

    def limites(self) -> tuple[int, int]:
        """(máximo de scroll_x, máximo de scroll_y) em pixels."""
        proj = self._c.projeto
        conteudo_x = int((proj.duracao_frames + 300) * self.ppf)
        conteudo_y = len(proj.faixas) * ALTURA_FAIXA
        return (max(0, conteudo_x - (self.width() - LARGURA_CABECALHO)),
                max(0, conteudo_y - (self.height() - ALTURA_REGUA)))

    def definir_scroll(self, x: int | None = None, y: int | None = None) -> None:
        mx, my = self.limites()
        if x is not None:
            self.scroll_x = max(0, min(int(x), mx))
        if y is not None:
            self.scroll_y = max(0, min(int(y), my))
        self.update()
        self.limites_alteradas.emit()

    def zoom(self, fator: float, ancora_x: float | None = None) -> None:
        ancora_x = LARGURA_CABECALHO + (self.width() - LARGURA_CABECALHO) / 2 if ancora_x is None else ancora_x
        frame_ancora = (ancora_x - LARGURA_CABECALHO + self.scroll_x) / self.ppf
        self.ppf = max(PPF_MIN, min(PPF_MAX, self.ppf * fator))
        self.scroll_x = max(0, int(frame_ancora * self.ppf - (ancora_x - LARGURA_CABECALHO)))
        self.definir_scroll(self.scroll_x)

    def ajustar_ao_projeto(self) -> None:
        dur = max(self._c.projeto.duracao_frames, 1)
        util = max(100, self.width() - LARGURA_CABECALHO - 40)
        self.ppf = max(PPF_MIN, min(PPF_MAX, util / dur))
        self.definir_scroll(0, 0)

    def seguir_cursor(self) -> None:
        x = self.x_de_frame(self._c.posicao)
        if x < LARGURA_CABECALHO or x > self.width() - 20:
            self.definir_scroll(int(self._c.posicao * self.ppf - (self.width() - LARGURA_CABECALHO) * 0.25))

    # ---- pintura --------------------------------------------------------------------------------
    def paintEvent(self, _evento) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), QColor(estilos.COR_FUNDO))
        proj = self._c.projeto
        w, h = self.width(), self.height()

        # Conteúdo (à direita do cabeçalho)
        p.save()
        p.setClipRect(QRect(LARGURA_CABECALHO, 0, w - LARGURA_CABECALHO, h))
        for i, faixa in enumerate(proj.faixas):
            y = self.y_da_faixa(i)
            fundo = QColor(estilos.COR_PAINEL if i % 2 == 0 else "#1a1d23")
            if faixa.cor:
                fundo = QColor(faixa.cor); fundo.setAlpha(40)
            p.fillRect(QRect(LARGURA_CABECALHO, y, w, ALTURA_FAIXA), fundo)
            p.setPen(QColor(estilos.COR_BORDA))
            p.drawLine(LARGURA_CABECALHO, y + ALTURA_FAIXA - 1, w, y + ALTURA_FAIXA - 1)
            for clipe in faixa.clipes:
                self._pintar_clipe(p, faixa, clipe, y)
            for transicao in proj.transicoes:
                if transicao.faixa_id == faixa.id:
                    self._pintar_transicao(p, transicao, y)
        if self._fantasma is not None and self._press is not None:
            ini, idx = self._fantasma
            clipe = self._press["clipe"]
            r = QRectF(self.x_de_frame(ini), self.y_da_faixa(idx) + 3, clipe.duracao * self.ppf, ALTURA_FAIXA - 7)
            cor = QColor(clipe.cor_efetiva()); cor.setAlpha(110)
            p.fillRect(r, cor)
            p.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
            p.drawRect(r)
        p.restore()

        self._pintar_regua(p)

        # Cabeçalhos de faixa (fixos à esquerda)
        p.fillRect(QRect(0, ALTURA_REGUA, LARGURA_CABECALHO, h), QColor(estilos.COR_PAINEL))
        fonte = p.font()
        for i, faixa in enumerate(proj.faixas):
            y = self.y_da_faixa(i)
            if y + ALTURA_FAIXA < ALTURA_REGUA or y > h:
                continue
            p.setPen(QColor(estilos.COR_BORDA))
            p.drawLine(0, y + ALTURA_FAIXA - 1, LARGURA_CABECALHO, y + ALTURA_FAIXA - 1)
            if faixa.cor:
                p.fillRect(QRect(0, y, 4, ALTURA_FAIXA - 1), QColor(faixa.cor))
            p.setPen(QColor(estilos.COR_TEXTO))
            p.setFont(fonte)
            p.drawText(QRect(10, y, LARGURA_CABECALHO - 64, ALTURA_FAIXA),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self._elidir(faixa.nome, p, LARGURA_CABECALHO - 70))
            r_trava, r_estado = self._retangulos_botoes(i)
            p.setPen(QColor(estilos.COR_PERIGO if faixa.bloqueada else estilos.COR_TEXTO_SUAVE))
            p.drawText(r_trava, Qt.AlignmentFlag.AlignCenter, "🔒" if faixa.bloqueada else "🔓")
            if faixa.tipo == FAIXA_AUDIO:
                glifo, ativo = ("🔇", faixa.silenciada)
            else:
                glifo, ativo = ("🚫", not faixa.visivel)
            p.setPen(QColor(estilos.COR_PERIGO if ativo else estilos.COR_TEXTO_SUAVE))
            p.drawText(r_estado, Qt.AlignmentFlag.AlignCenter, glifo if ativo else ("🔈" if faixa.tipo == FAIXA_AUDIO else "👁"))
        p.fillRect(QRect(0, 0, LARGURA_CABECALHO, ALTURA_REGUA), QColor(estilos.COR_PAINEL_ALT))

        # Cursor de reprodução
        x = self.x_de_frame(self._c.posicao)
        if LARGURA_CABECALHO <= x <= w:
            p.setPen(QPen(QColor(estilos.COR_CURSOR), 2))
            p.drawLine(int(x), 0, int(x), h)
            p.setBrush(QColor(estilos.COR_CURSOR))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([QPointF(x - 6, 0), QPointF(x + 6, 0), QPointF(x, 10)]))
        p.end()

    @staticmethod
    def _elidir(texto: str, p: QPainter, largura: int) -> str:
        return p.fontMetrics().elidedText(texto, Qt.TextElideMode.ElideRight, largura)

    def _retangulos_botoes(self, indice: int) -> tuple[QRect, QRect]:
        y = self.y_da_faixa(indice) + (ALTURA_FAIXA - 22) // 2
        return (QRect(LARGURA_CABECALHO - 52, y, 24, 22), QRect(LARGURA_CABECALHO - 26, y, 24, 22))

    def _pintar_regua(self, p: QPainter) -> None:
        w = self.width()
        proj = self._c.projeto
        fps = proj.config.fps
        p.save()
        p.setClipRect(QRect(LARGURA_CABECALHO, 0, w - LARGURA_CABECALHO, ALTURA_REGUA))
        p.fillRect(QRect(LARGURA_CABECALHO, 0, w, ALTURA_REGUA), QColor(estilos.COR_PAINEL_ALT))
        nominal = fps_nominal(fps)
        candidatos = sorted({1, 2, 5, 10, 15} | {nominal * k for k in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600)})
        passo = next((c for c in candidatos if c * self.ppf >= 90), candidatos[-1])
        primeiro = max(0, self.frame_de_x(LARGURA_CABECALHO) // passo * passo)
        ultimo = self.frame_de_x(w) + passo
        p.setPen(QColor(estilos.COR_TEXTO_SUAVE))
        fonte = QFont(p.font()); fonte.setPointSize(8); p.setFont(fonte)
        for f in range(primeiro, ultimo, passo):
            x = int(self.x_de_frame(f))
            p.drawLine(x, ALTURA_REGUA - 10, x, ALTURA_REGUA)
            p.drawText(x + 3, 12, formatar_timecode(f, fps))
        p.restore()
        p.setPen(QColor(estilos.COR_BORDA))
        p.drawLine(0, ALTURA_REGUA - 1, w, ALTURA_REGUA - 1)

    def _pintar_clipe(self, p: QPainter, faixa, clipe, y: int) -> None:
        x0 = self.x_de_frame(clipe.inicio)
        largura = max(2.0, clipe.duracao * self.ppf)
        if x0 + largura < LARGURA_CABECALHO or x0 > self.width():
            return
        r = QRectF(x0, y + 3, largura, ALTURA_FAIXA - 7)
        cor = QColor(clipe.cor_efetiva())
        if faixa.bloqueada:
            cor = cor.darker(160)
        if self._press is not None and self._press["ativo"] and self._press["clipe"].id == clipe.id:
            cor.setAlpha(80)
        p.fillRect(r, cor)
        selecionado = clipe.id in self._c.selecao
        p.setPen(QPen(QColor("#ffffff") if selecionado else cor.darker(130), 2 if selecionado else 1))
        p.drawRect(r)
        if largura > 22:
            p.setPen(QColor("#ffffff"))
            texto = f"{ICONES_CATEGORIA.get(clipe.tipo, '?')} {clipe.nome}"
            p.drawText(r.adjusted(5, 0, -3, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self._elidir(texto, p, int(largura) - 8))

    def _pintar_transicao(self, p: QPainter, transicao, y: int) -> None:
        try:
            _, destino = self._c.projeto.localizar_clipe(transicao.clipe_destino_id)
        except KeyError:
            return
        x0 = self.x_de_frame(destino.inicio)
        largura = max(6.0, transicao.duracao * self.ppf)
        if x0 + largura < LARGURA_CABECALHO or x0 > self.width():
            return
        r = QRectF(x0, y + 4, largura, ALTURA_FAIXA - 9)
        gradiente = QLinearGradient(r.topLeft(), r.topRight())
        gradiente.setColorAt(0.0, QColor(112, 78, 190, 205))
        gradiente.setColorAt(0.5, QColor(151, 111, 232, 225))
        gradiente.setColorAt(1.0, QColor(73, 118, 201, 205))
        p.fillRect(r, gradiente)
        p.setPen(QPen(QColor("#e7dcff"), 1))
        p.drawRect(r)
        p.drawLine(r.topLeft(), r.bottomRight())
        p.drawLine(r.bottomLeft(), r.topRight())
        if largura >= 26:
            p.setPen(QColor("#ffffff"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "⇄")

    # ---- busca ---------------------------------------------------------------------------------------
    def _clipe_em(self, x: float, y: float):
        idx = self.indice_faixa_em(y)
        if idx is None or x < LARGURA_CABECALHO:
            return None
        faixa = self._c.projeto.faixas[idx]
        frame = self.frame_de_x(x)
        for c in faixa.clipes:
            if c.inicio <= frame < c.fim:
                return idx, faixa, c
        return None

    # ---- mouse ------------------------------------------------------------------------------------------
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()
        x, y = pos.x(), pos.y()
        if y < ALTURA_REGUA and x >= LARGURA_CABECALHO:
            self._scrub = True
            self._c.ir_para(max(0, self.frame_de_x(x)))
            return
        if x < LARGURA_CABECALHO:
            self._clique_cabecalho(x, y)
            return
        achado = self._clipe_em(x, y)
        ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if achado is None:
            if not ctrl:
                self._c.selecionar([])
            return
        idx, faixa, clipe = achado
        if ctrl:
            self._c.selecao.alternar(clipe.id)
            self._c.selecionar(list(self._c.selecao.ids))
        elif clipe.id not in self._c.selecao:
            self._c.selecionar([clipe.id])
        self._press = {"clipe": clipe, "idx": idx, "x0": x, "ativo": False,
                       "desloc": self.frame_de_x(x) - clipe.inicio}

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        pos = ev.position()
        if self._scrub:
            self._c.ir_para(max(0, self.frame_de_x(pos.x())))
            return
        pr = self._press
        if pr is None:
            return
        if not pr["ativo"] and abs(pos.x() - pr["x0"]) < 4:
            return
        if len(self._c.selecao) > 1:
            return                                    # mover vários clipes: Etapa 4
        pr["ativo"] = True
        clipe = pr["clipe"]
        inicio = max(0, self.frame_de_x(pos.x()) - pr["desloc"])
        if self.snapping:
            inicio = self._aplicar_snap(inicio, clipe)
        idx = self.indice_faixa_em(pos.y())
        self._fantasma = (inicio, pr["idx"] if idx is None else idx)
        self.update()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        self._scrub = False
        pr, fantasma = self._press, self._fantasma
        self._press = None
        self._fantasma = None
        if pr is not None and pr["ativo"] and fantasma is not None:
            inicio, idx = fantasma
            faixa_dest = self._c.projeto.faixas[idx]
            try:
                self._c.mover_clipe(pr["clipe"].id, inicio, faixa_dest.id)
            except ErroEdicao as exc:
                self.erro.emit(str(exc))
        self.update()

    def _aplicar_snap(self, inicio: int, clipe) -> int:
        tol = max(1, int(TOLERANCIA_SNAP_PX / self.ppf))
        alvos = {0, self._c.posicao}
        for f in self._c.projeto.faixas:
            for c in f.clipes:
                if c.id != clipe.id:
                    alvos.update((c.inicio, c.fim))
        melhor, dist = inicio, tol + 1
        for alvo in alvos:
            for borda, ajuste in ((inicio, alvo - inicio), (inicio + clipe.duracao, alvo - inicio - clipe.duracao)):
                if abs(borda - alvo) <= tol and abs(borda - alvo) < dist:
                    melhor, dist = inicio + ajuste, abs(borda - alvo)
        return max(0, melhor)

    def _clique_cabecalho(self, x: float, y: float) -> None:
        idx = self.indice_faixa_em(y)
        if idx is None:
            return
        faixa = self._c.projeto.faixas[idx]
        r_trava, r_estado = self._retangulos_botoes(idx)
        try:
            if r_trava.contains(int(x), int(y)):
                self._c.alterar_faixa(faixa.id, bloqueada=not faixa.bloqueada)
            elif r_estado.contains(int(x), int(y)):
                if faixa.tipo == FAIXA_AUDIO:
                    self._c.alterar_faixa(faixa.id, silenciada=not faixa.silenciada)
                else:
                    self._c.alterar_faixa(faixa.id, visivel=not faixa.visivel)
        except ErroEdicao as exc:
            self.erro.emit(str(exc))

    def wheelEvent(self, ev) -> None:  # noqa: N802
        d = ev.angleDelta()
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.25 if d.y() > 0 else 0.8, ev.position().x())
        elif ev.modifiers() & Qt.KeyboardModifier.ShiftModifier or d.x() != 0:
            delta = d.x() or d.y()
            self.definir_scroll(x=self.scroll_x - delta)
        else:
            self.definir_scroll(y=self.scroll_y - d.y() // 2)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self.limites_alteradas.emit()


class Timeline(QFrame):
    """Contêiner: barra fixa, barra contextual, canvas e barras de rolagem."""

    recolhida_alterada = pyqtSignal(bool)
    propriedades_solicitadas = pyqtSignal()
    erro = pyqtSignal(str)

    def __init__(self, controlador: Controlador, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineRaiz")
        self._c = controlador
        self._recolhida = False
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # --- barra fixa ---------------------------------------------------------------------
        self._barra = QFrame()
        self._barra.setObjectName("barraTimeline")
        bl = QHBoxLayout(self._barra)
        bl.setContentsMargins(8, 4, 8, 4)
        self._btn_dividir = self._btn("✂", "Dividir clipes selecionados no cursor (S)", self._dividir)
        self._btn_snap = self._btn("🧲", "Snapping: encaixar nas bordas dos clipes e no cursor", self._alternar_snap, True)
        self._btn_snap.setChecked(True)
        self._btn_snap.setText("🧲 Snapping")
        for b in (
            self._btn("↖", "Ferramenta de seleção (única disponível nesta etapa)",
                      lambda: self._btns_primeiro.setChecked(True), True),
            self._btn_dividir, self._btn_snap,
            self._btn("＋🎞", "Adicionar faixa de vídeo", lambda: self._faixa("video")),
            self._btn("＋♪", "Adicionar faixa de áudio", lambda: self._faixa("audio")),
            self._btn("−", "Reduzir zoom (Ctrl+roda do mouse)", lambda: self.canvas.zoom(0.8)),
            self._btn("＋", "Ampliar zoom (Ctrl+roda do mouse)", lambda: self.canvas.zoom(1.25)),
            self._btn("↔", "Ajustar o projeto à largura", lambda: self.canvas.ajustar_ao_projeto()),
        ):
            bl.addWidget(b)
        self._btns_primeiro = bl.itemAt(0).widget()
        self._btns_primeiro.setChecked(True)
        bl.addStretch(1)
        self._btn_recolher = self._btn("⌄", "Recolher timeline", self.alternar_recolhida)
        bl.addWidget(self._btn_recolher)
        raiz.addWidget(self._barra)

        # --- barra contextual ------------------------------------------------------------------
        self._ctx = QFrame()
        self._ctx.setObjectName("barraContextual")
        cl = QHBoxLayout(self._ctx)
        cl.setContentsMargins(8, 3, 8, 3)
        self._rotulo_ctx = QLabel()
        cl.addWidget(self._rotulo_ctx)
        self._ctx_dividir = self._btn("✂ Dividir", "Dividir no cursor", self._dividir)
        self._ctx_excluir = self._btn("🗑 Excluir", "Excluir clipes selecionados (Delete)", self._excluir)
        self._ctx_props = self._btn("⚙ Propriedades", "Abrir propriedades dos clipes selecionados",
                                    self.propriedades_solicitadas.emit)
        for b in (self._ctx_dividir, self._ctx_excluir, self._ctx_props):
            cl.addWidget(b)
        cl.addStretch(1)
        self._ctx.hide()
        raiz.addWidget(self._ctx)

        # --- corpo: canvas + barras ----------------------------------------------------------------
        self._corpo = QWidget()
        g = QGridLayout(self._corpo)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(0)
        self.canvas = CanvasTimeline(controlador)
        self._hbar = QScrollBar(Qt.Orientation.Horizontal)
        self._vbar = QScrollBar(Qt.Orientation.Vertical)
        g.addWidget(self.canvas, 0, 0)
        g.addWidget(self._vbar, 0, 1)
        g.addWidget(self._hbar, 1, 0)
        raiz.addWidget(self._corpo, 1)

        self._hbar.valueChanged.connect(lambda v: self.canvas.definir_scroll(x=v))
        self._vbar.valueChanged.connect(lambda v: self.canvas.definir_scroll(y=v))
        self.canvas.limites_alteradas.connect(self._sincronizar_barras)
        self.canvas.erro.connect(self.erro)

        e = controlador.eventos
        e.assinar(PROJETO_ALTERADO, self._ao_modelo)
        e.assinar(PROJETO_CARREGADO, self._ao_modelo)
        e.assinar(MIDIAS_ALTERADAS, self._ao_modelo)
        e.assinar(SELECAO_ALTERADA, self._ao_selecao)
        e.assinar(POSICAO_ALTERADA, self._ao_posicao)
        self._ao_selecao()

    # ---- util --------------------------------------------------------------------------------------
    def _btn(self, texto: str, dica: str, fn, checkable: bool = False) -> QToolButton:
        b = QToolButton()
        b.setText(texto)
        b.setToolTip(dica)
        b.setCheckable(checkable)
        b.clicked.connect(lambda _=False: fn())
        return b

    def _executar(self, fn) -> None:
        try:
            fn()
        except ErroEdicao as exc:
            self.erro.emit(str(exc))

    # ---- ações ------------------------------------------------------------------------------------
    def _dividir(self) -> None:
        self._executar(self._c.dividir_selecionados_na_posicao)

    def _excluir(self) -> None:
        self._executar(self._c.excluir_selecionados)

    def _faixa(self, tipo: str) -> None:
        self._executar(lambda: self._c.adicionar_faixa(tipo))

    def _alternar_snap(self) -> None:
        self.canvas.snapping = self._btn_snap.isChecked()

    # ---- recolher -------------------------------------------------------------------------------------
    def esta_recolhida(self) -> bool:
        return self._recolhida

    def definir_recolhida(self, recolhida: bool, emitir: bool = False) -> None:
        self._recolhida = recolhida
        self._corpo.setVisible(not recolhida)
        self._btn_recolher.setText("⌃" if recolhida else "⌄")
        self._btn_recolher.setToolTip("Expandir timeline" if recolhida else "Recolher timeline")
        if recolhida:
            self.setMaximumHeight(self._barra.sizeHint().height() + 2)
            self._ctx.hide()                      # barra contextual some com a timeline recolhida
        else:
            self.setMaximumHeight(16_777_215)
            self._ao_selecao()
        if emitir:
            self.recolhida_alterada.emit(recolhida)

    def alternar_recolhida(self) -> None:
        self.definir_recolhida(not self._recolhida, emitir=True)

    def altura_barra(self) -> int:
        return self._barra.sizeHint().height() + 2

    # ---- sincronização com o modelo ------------------------------------------------------------------------
    def _ao_modelo(self) -> None:
        self.canvas.update()
        self._sincronizar_barras()

    def _ao_posicao(self, _frame: int) -> None:
        self.canvas.seguir_cursor()
        self.canvas.update()

    def _ao_selecao(self) -> None:
        n = len(self._c.selecao)
        self.canvas.update()
        if n == 0 or self._recolhida:
            self._ctx.hide()
            return
        self._rotulo_ctx.setText("1 clipe selecionado" if n == 1 else f"{n} clipes selecionados")
        # Mostra apenas ações válidas para TODOS os selecionados (mistura áudio/vídeo incluída)
        self._ctx_dividir.setVisible(True)
        self._ctx_excluir.setVisible(True)
        self._ctx_props.setVisible(True)
        self._ctx.show()

    def _sincronizar_barras(self) -> None:
        mx, my = self.canvas.limites()
        w = self.canvas.width() - LARGURA_CABECALHO
        for barra, maximo, pagina, valor in (
            (self._hbar, mx, max(1, w), self.canvas.scroll_x),
            (self._vbar, my, max(1, self.canvas.height() - ALTURA_REGUA), self.canvas.scroll_y),
        ):
            barra.blockSignals(True)
            barra.setRange(0, maximo)
            barra.setPageStep(pagina)
            barra.setValue(valor)
            barra.blockSignals(False)
        self._vbar.setVisible(my > 0)
