"""Cabeçalho fixo e adaptativo (REQ-017, 19.2).

Largura ampla: ícones + texto. Média: só ícones. Estreita: comandos secundários
vão para o menu de opções adicionais ("⋯"). Comandos principais sempre visíveis.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMenu, QSizePolicy, QToolButton,
)

from core.constantes import ARQUIVO_LOGO, NOME_APLICATIVO


@dataclass(frozen=True)
class AcaoCabecalho:
    id: str
    glifo: str
    texto: str
    dica: str
    principal: bool          # principais nunca vão para o menu de excesso


ACOES = (
    AcaoCabecalho("novo", "＋", "Novo", "Novo projeto (Ctrl+N)", False),
    AcaoCabecalho("abrir", "📂", "Abrir", "Abrir projeto (Ctrl+O)", False),
    AcaoCabecalho("salvar", "💾", "Salvar", "Salvar projeto (Ctrl+S)", True),
    AcaoCabecalho("importar", "⬇", "Importar mídia", "Importar mídia (Ctrl+I)", True),
    AcaoCabecalho("desfazer", "↶", "Desfazer", "Desfazer (Ctrl+Z)", True),
    AcaoCabecalho("refazer", "↷", "Refazer", "Refazer (Ctrl+Y)", True),
    AcaoCabecalho("configuracoes", "⚙", "Configurações", "Configurações e layout", False),
    AcaoCabecalho("exportar", "⬆", "Exportar vídeo", "Exportar vídeo", True),
)

LARGURA_COM_TEXTO = 1180
LARGURA_SO_ICONES = 760       # abaixo disso, secundários vão para o menu "⋯"


class Cabecalho(QFrame):
    acao = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cabecalho")
        self.setFixedHeight(56)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(6)

        self._logo = QLabel()
        self._logo.setFixedSize(58, 42)
        self._logo.setToolTip(NOME_APLICATIVO)
        pixmap = QPixmap(str(Path(__file__).resolve().parent.parent / ARQUIVO_LOGO))
        if not pixmap.isNull():
            self._logo.setPixmap(pixmap.scaled(
                self._logo.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        lay.addWidget(self._logo)

        self._titulo = QLabel(NOME_APLICATIVO)
        self._titulo.setObjectName("tituloApp")
        self._nome_projeto = QLabel("Projeto sem título")
        self._nome_projeto.setObjectName("nomeProjeto")
        self._nome_projeto.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._nome_projeto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._titulo)
        lay.addWidget(self._nome_projeto, 1)

        self._botoes: dict[str, QToolButton] = {}
        for a in ACOES:
            b = QToolButton()
            b.setObjectName("itemCabecalho")
            b.setProperty("destaque", a.id == "exportar")
            b.setToolTip(a.dica)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self._aplicar_sombra_glass(b)
            b.clicked.connect(lambda _=False, i=a.id: self.acao.emit(i))
            self._botoes[a.id] = b
            lay.addWidget(b)

        self._mais = QToolButton()
        self._mais.setObjectName("itemCabecalho")
        self._mais.setText("⋯")
        self._mais.setToolTip("Mais opções")
        self._aplicar_sombra_glass(self._mais)
        self._mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu_mais = QMenu(self._mais)
        self._mais.setMenu(self._menu_mais)
        lay.addWidget(self._mais)
        self._atualizar_modo()

    @staticmethod
    def _aplicar_sombra_glass(botao: QToolButton) -> None:
        """Aplica a sombra individual que completa a superfície glass do botão."""
        sombra = QGraphicsDropShadowEffect(botao)
        sombra.setBlurRadius(16)
        sombra.setOffset(0, 3)
        sombra.setColor(QColor(0, 0, 0, 105))
        botao.setGraphicsEffect(sombra)

    # ---- API --------------------------------------------------------------------------
    def definir_nome_projeto(self, nome: str, modificado: bool) -> None:
        self._nome_projeto.setText(f"{nome}{' •' if modificado else ''}")

    def habilitar(self, acao_id: str, habilitada: bool, dica: str | None = None) -> None:
        self._botoes[acao_id].setEnabled(habilitada)
        if dica is not None:
            self._botoes[acao_id].setToolTip(dica)

    # ---- adaptação ---------------------------------------------------------------------
    def resizeEvent(self, evento) -> None:  # noqa: N802 (nome Qt)
        super().resizeEvent(evento)
        self._atualizar_modo()

    def _atualizar_modo(self) -> None:
        largura = self.width()
        com_texto = largura >= LARGURA_COM_TEXTO
        estreito = largura < LARGURA_SO_ICONES
        self._menu_mais.clear()
        tem_excesso = False
        for a in ACOES:
            b = self._botoes[a.id]
            b.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon if com_texto
                else Qt.ToolButtonStyle.ToolButtonTextOnly
            )
            b.setText(f"{a.glifo}  {a.texto}" if com_texto else a.glifo)
            if estreito and not a.principal:
                b.setVisible(False)
                acao = self._menu_mais.addAction(f"{a.glifo}  {a.texto}")
                acao.triggered.connect(lambda _=False, i=a.id: self.acao.emit(i))
                tem_excesso = True
            else:
                b.setVisible(True)
        self._mais.setVisible(tem_excesso)
        self._titulo.setText(NOME_APLICATIVO if largura >= 560 else "Movix")
