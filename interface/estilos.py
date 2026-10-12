"""Tema escuro moderno (QSS) e comportamentos visuais globais da interface."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractButton, QApplication

COR_FUNDO = "#16181d"
COR_PAINEL = "#1e2128"
COR_PAINEL_ALT = "#252a33"
COR_BORDA = "#323844"
COR_TEXTO = "#e4e7ec"
COR_TEXTO_SUAVE = "#9aa3b2"
COR_DESTAQUE = "#4f8cff"
COR_PERIGO = "#e5534b"
COR_CURSOR = "#ff4d4d"


class FiltroCursorBotoes(QObject):
    """Usa a mão em todos os botões clicáveis, inclusive os criados depois."""

    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802 (nome Qt)
        if isinstance(objeto, QAbstractButton) and evento.type() in (
            QEvent.Type.Enter,
            QEvent.Type.EnabledChange,
        ):
            cursor = (
                Qt.CursorShape.PointingHandCursor
                if objeto.isEnabled()
                else Qt.CursorShape.ArrowCursor
            )
            objeto.setCursor(cursor)
        return False


def instalar_cursor_botoes(app: QApplication) -> FiltroCursorBotoes:
    """Instala e devolve o filtro; a referência deve viver enquanto o app existir."""
    filtro = FiltroCursorBotoes(app)
    app.installEventFilter(filtro)
    return filtro

QSS = f"""
* {{ font-family: "Segoe UI", "Noto Sans", sans-serif; font-size: 13px; color: {COR_TEXTO}; }}
QMainWindow, QWidget#raiz {{ background: {COR_FUNDO}; }}
QToolTip {{ background: {COR_PAINEL_ALT}; color: {COR_TEXTO}; border: 1px solid {COR_BORDA}; padding: 4px; }}

QFrame#cabecalho {{ background: {COR_PAINEL}; border-bottom: 1px solid {COR_BORDA}; }}
QLabel#tituloApp {{ font-weight: 700; font-size: 14px; }}
QLabel#nomeProjeto {{ color: {COR_TEXTO_SUAVE}; }}

QFrame#menuLateral {{ background: {COR_PAINEL}; border-right: 1px solid {COR_BORDA}; }}
QToolButton#itemMenu {{ border: none; border-radius: 8px; padding: 8px 2px; color: {COR_TEXTO_SUAVE}; }}
QToolButton#itemMenu:hover {{ background: {COR_PAINEL_ALT}; color: {COR_TEXTO}; }}
QToolButton#itemMenu:checked {{ background: {COR_PAINEL_ALT}; color: {COR_DESTAQUE}; }}

QFrame#painelFerramentas, QFrame#painelPropriedades {{ background: {COR_PAINEL}; border: 1px solid {COR_BORDA}; }}
QFrame#painelPropriedades {{ border-radius: 10px; }}
QLabel#tituloPainel {{ font-weight: 600; font-size: 14px; }}
QLabel#suave {{ color: {COR_TEXTO_SUAVE}; }}

QPushButton, QToolButton {{ background: {COR_PAINEL_ALT}; border: 1px solid {COR_BORDA}; border-radius: 6px; padding: 5px 10px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {COR_DESTAQUE}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5d6573; background: {COR_PAINEL}; }}
QPushButton#primario, QToolButton#primario {{ background: {COR_DESTAQUE}; border-color: {COR_DESTAQUE}; color: white; font-weight: 600; }}
QToolButton:checked {{ background: #2d4a80; border-color: {COR_DESTAQUE}; }}
QToolButton#semBorda {{ border: none; background: transparent; }}

QListWidget, QLineEdit, QSpinBox, QComboBox {{ background: {COR_FUNDO}; border: 1px solid {COR_BORDA}; border-radius: 6px; padding: 4px; }}
QListWidget::item {{ padding: 5px; border-radius: 4px; }}
QListWidget::item:selected {{ background: #2d4a80; }}

QSplitter::handle {{ background: {COR_BORDA}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical {{ height: 3px; }}

QSlider::groove:horizontal {{ height: 4px; background: {COR_BORDA}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {COR_DESTAQUE}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QScrollBar:horizontal {{ height: 12px; background: {COR_PAINEL}; }}
QScrollBar:vertical {{ width: 12px; background: {COR_PAINEL}; }}
QScrollBar::handle {{ background: {COR_BORDA}; border-radius: 5px; min-width: 24px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QFrame#barraTimeline, QFrame#barraContextual {{ background: {COR_PAINEL}; border-bottom: 1px solid {COR_BORDA}; }}
QFrame#barraContextual {{ background: {COR_PAINEL_ALT}; }}
QFrame#controlesPlayer {{ background: {COR_PAINEL}; border-top: 1px solid {COR_BORDA}; }}
"""
