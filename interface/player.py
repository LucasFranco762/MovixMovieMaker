"""Player central com pré-visualização de imagem e áudio da timeline (REQ-007)."""
from __future__ import annotations

import logging

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from core.controlador import Controlador
from core.eventos import POSICAO_ALTERADA, PROJETO_ALTERADO, PROJETO_CARREGADO
from core.tempo import formatar_timecode

_log = logging.getLogger(__name__)


class AreaVideo(QWidget):
    """Desenha o quadro respeitando a proporção do vídeo do projeto."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(240, 135)
        self._imagem: QImage | None = None
        self._proporcao = 16 / 9
        self._mensagem = ""

    def definir_proporcao(self, largura: int, altura: int) -> None:
        self._proporcao = largura / altura if altura else 16 / 9
        self.update()

    def definir_imagem(self, imagem: QImage | None) -> None:
        self._imagem = imagem
        self.update()

    def definir_mensagem(self, texto: str) -> None:
        self._mensagem = texto
        self.update()

    def retangulo_video(self) -> QRectF:
        w, h = self.width(), self.height()
        if w / max(h, 1) > self._proporcao:
            vh, vw = h, h * self._proporcao
        else:
            vw, vh = w, w / self._proporcao
        return QRectF((w - vw) / 2, (h - vh) / 2, vw, vh)

    def paintEvent(self, _evento) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b0c0f"))
        r = self.retangulo_video()
        p.fillRect(r, QColor("#000000"))
        if self._imagem is not None:
            p.drawImage(r, self._imagem)
        elif self._mensagem:
            p.setPen(QColor("#7d8696"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._mensagem)
        p.end()


class Player(QFrame):
    fullscreen_solicitado = pyqtSignal()

    def __init__(self, controlador: Controlador, parent=None) -> None:
        super().__init__(parent)
        self._c = controlador
        self._tocando = False
        self._atualizando = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._avancar_reproducao)
        self._atualizando_pelo_audio = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.area = AreaVideo()
        lay.addWidget(self.area, 1)

        self.controles = QFrame()
        self.controles.setObjectName("controlesPlayer")
        cl = QVBoxLayout(self.controles)
        cl.setContentsMargins(10, 4, 10, 6)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setToolTip("Navegar pela composição")
        self._slider.valueChanged.connect(self._ao_mover_slider)
        cl.addWidget(self._slider)

        linha = QHBoxLayout()
        self._tempo = QLabel("00:00:00:00 / 00:00:00:00")
        self._tempo.setToolTip("Posição atual / duração")
        linha.addWidget(self._tempo)
        linha.addStretch(1)
        for glifo, dica, fn in (
            ("⏮", "Ir para o início (Home)", lambda: self._c.ir_para(0)),
            ("◀", "Voltar 1 frame (←)", lambda: self._c.ir_para(self._c.posicao - 1)),
        ):
            linha.addWidget(self._botao(glifo, dica, fn))
        self._btn_play = self._botao("▶", "Reproduzir/Pausar (Espaço)", self.alternar_reproducao)
        linha.addWidget(self._btn_play)
        linha.addWidget(self._botao("⏹", "Parar", self.parar))
        for glifo, dica, fn in (
            ("▶", "Avançar 1 frame (→)", lambda: self._c.ir_para(self._c.posicao + 1)),
            ("⏭", "Ir para o fim (End)", lambda: self._c.ir_para(self._c.projeto.duracao_frames)),
        ):
            linha.addWidget(self._botao(glifo, dica, fn))
        linha.addStretch(1)
        self._btn_tela_cheia = self._botao("⛶", "Tela cheia (F11)", self.fullscreen_solicitado.emit)
        linha.addWidget(self._btn_tela_cheia)
        cl.addLayout(linha)
        lay.addWidget(self.controles)

        controlador.eventos.assinar(POSICAO_ALTERADA, self._ao_posicao)
        controlador.eventos.assinar(PROJETO_ALTERADO, self._ao_projeto)
        controlador.eventos.assinar(PROJETO_CARREGADO, self._ao_projeto)
        self._ao_projeto()

    def _botao(self, glifo: str, dica: str, fn) -> QToolButton:
        b = QToolButton()
        b.setText(glifo)
        b.setToolTip(dica)
        b.clicked.connect(lambda _=False: fn())
        return b

    # ---- reprodução ----------------------------------------------------------------------------
    def alternar_reproducao(self) -> None:
        if self._tocando:
            self._pausar()
        else:
            if self._c.posicao >= self._c.projeto.duracao_frames:
                self._c.ir_para(0)
            self._tocando = True
            self._btn_play.setText("⏸")
            fps = float(self._c.projeto.config.fps)
            self._timer.start(max(1, int(1000 / fps)))
            self._iniciar_audio(self._c.posicao)

    def _pausar(self) -> None:
        self._tocando = False
        self._timer.stop()
        self._btn_play.setText("▶")
        motor = self._c.motor
        if motor is not None:
            motor.parar_audio_preview()

    def pausar(self) -> None:
        """Pausa sem alterar a posição atual (usado antes da exportação)."""
        self._pausar()

    def parar(self) -> None:
        self._pausar()
        self._c.ir_para(0)

    def _avancar_reproducao(self) -> None:
        if self._c.posicao >= self._c.projeto.duracao_frames:
            self._pausar()
            return
        motor = self._c.motor
        posicao_audio = motor.posicao_audio_preview() if motor is not None else None
        destino = self._c.posicao + 1 if posicao_audio is None else posicao_audio
        if destino != self._c.posicao:
            self._atualizando_pelo_audio = True
            try:
                self._c.ir_para(destino)
            finally:
                self._atualizando_pelo_audio = False

    # ---- sincronização com o modelo -----------------------------------------------------------------
    def _ao_projeto(self) -> None:
        cfg = self._c.projeto.config
        self.area.definir_proporcao(cfg.largura, cfg.altura)
        self._atualizando = True
        self._slider.setRange(0, max(0, self._c.projeto.duracao_frames))
        self._atualizando = False
        motor = self._c.motor
        if motor is None or not motor.disponivel():
            self.area.definir_mensagem(
                "Pré-visualização indisponível: motor MLT não encontrado.\n"
                "A edição da timeline continua funcionando.")
        else:
            self.area.definir_mensagem("")
        self._ao_posicao(self._c.posicao)

    def _ao_posicao(self, frame: int) -> None:
        proj = self._c.projeto
        self._atualizando = True
        self._slider.setValue(frame)
        self._atualizando = False
        self._tempo.setText(
            f"{formatar_timecode(frame, proj.config.fps)} / "
            f"{formatar_timecode(proj.duracao_frames, proj.config.fps)}")
        self._desenhar_quadro(frame)
        if self._tocando and not self._atualizando_pelo_audio:
            motor = self._c.motor
            posicao_audio = motor.posicao_audio_preview() if motor is not None else None
            if posicao_audio is None or abs(posicao_audio - frame) > 2:
                self._iniciar_audio(frame)

    def _ao_mover_slider(self, valor: int) -> None:
        if not self._atualizando:
            self._c.ir_para(valor)

    def _desenhar_quadro(self, frame: int) -> None:
        motor = self._c.motor
        if motor is None or not motor.disponivel() or self._c.projeto.duracao_frames == 0:
            self.area.definir_imagem(None)
            return
        try:
            quadro = motor.obter_frame(frame)
        except Exception:  # noqa: BLE001 - falha de um quadro não pode derrubar a interface
            _log.exception("Falha ao obter o quadro %s", frame)
            self._pausar()
            self.area.definir_mensagem("Erro ao obter o quadro. Veja o log para detalhes.")
            self.area.definir_imagem(None)
            return
        if quadro is None:
            self.area.definir_imagem(None)
            return
        img = QImage(quadro.dados, quadro.largura, quadro.altura, quadro.largura * 4,
                     QImage.Format.Format_RGBA8888).copy()
        self.area.definir_imagem(img)

    def _iniciar_audio(self, frame: int) -> None:
        motor = self._c.motor
        if motor is not None and not motor.iniciar_audio_preview(frame):
            _log.error("O motor multimídia não conseguiu iniciar o áudio da pré-visualização.")
