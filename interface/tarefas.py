"""Tarefas em segundo plano (REQ-003): a interface nunca bloqueia em E/S pesada.

O worker só ANALISA os arquivos (ffprobe). Quem altera o modelo é a thread
principal, ao receber o sinal ``midia_pronta`` — o modelo não é thread-safe.
"""
from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from multimidia.metadados import analisar_midia
from multimidia.motor_ffmpeg import MotorFFmpeg

_log = logging.getLogger(__name__)


class TarefaAnaliseMidias(QThread):
    midia_pronta = pyqtSignal(object)        # MidiaRef
    falha = pyqtSignal(str)                  # mensagem em pt-BR

    def __init__(self, ffmpeg: MotorFFmpeg, caminhos: list[str], fps: Fraction, parent=None) -> None:
        super().__init__(parent)
        self._ffmpeg = ffmpeg
        self._caminhos = list(caminhos)
        self._fps = fps

    def run(self) -> None:
        for caminho in self._caminhos:
            if self.isInterruptionRequested():
                return
            try:
                self.midia_pronta.emit(analisar_midia(self._ffmpeg, caminho, self._fps))
            except Exception as exc:  # noqa: BLE001 - reportado ao usuário, segue com os demais
                _log.warning("Falha ao analisar %s: %s", caminho, exc)
                self.falha.emit(f"{Path(caminho).name}: {exc}")
