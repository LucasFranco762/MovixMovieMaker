"""Tela de abertura exibida enquanto o Movix Movie Maker é preparado."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

ATRASO_APOS_CARREGAMENTO_MS = 2_000


class TelaSplash(QSplashScreen):
    """Splash que não desaparece antes de a janela principal estar pronta."""

    def mousePressEvent(self, evento) -> None:  # noqa: N802 (nome Qt)
        evento.ignore()


def criar_splash(app: QApplication, caminho_logo: Path) -> TelaSplash | None:
    """Cria e exibe a splash proporcional à tela; retorna ``None`` sem imagem válida."""
    imagem = QPixmap(str(caminho_logo))
    if imagem.isNull():
        return None

    tela = app.primaryScreen()
    if tela is not None:
        area = tela.availableGeometry()
        largura_maxima = min(720, max(320, int(area.width() * 0.60)))
        altura_maxima = min(520, max(240, int(area.height() * 0.60)))
        imagem = imagem.scaled(
            largura_maxima,
            altura_maxima,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    flags = Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint
    splash = TelaSplash(imagem, flags)
    splash.show()
    app.processEvents()
    return splash
