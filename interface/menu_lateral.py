"""Barra vertical fixa de ícones (REQ-017, 19.3)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout

CATEGORIAS = (
    ("midias", "🎞", "Mídias"),
    ("transicoes", "⇄", "Transições"),
    ("efeitos", "✨", "Efeitos"),
    ("textos", "T", "Textos"),
    ("audio", "♪", "Áudio"),
    ("legendas", "≡", "Legendas"),
    ("ajustes", "⚙", "Ajustes"),
)


class MenuLateral(QFrame):
    """Emite ``categoria_clicada`` a cada clique; a janela decide abrir/alternar o painel."""

    categoria_clicada = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("menuLateral")
        self.setFixedWidth(88)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(4)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(False)       # permite desmarcar todos ao recolher o painel
        self._botoes: dict[str, QToolButton] = {}
        for id_, glifo, nome in CATEGORIAS:
            b = QToolButton()
            b.setObjectName("itemMenu")
            b.setCheckable(True)
            b.setText(f"{glifo}\n{nome}")
            b.setToolTip(nome)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.setFixedSize(76, 54)
            b.clicked.connect(lambda _=False, i=id_: self.categoria_clicada.emit(i))
            self._grupo.addButton(b)
            self._botoes[id_] = b
            lay.addWidget(b)
        lay.addStretch(1)

    def marcar(self, categoria: str | None) -> None:
        """Marca visualmente a categoria ativa (None = nenhuma)."""
        for id_, b in self._botoes.items():
            b.setChecked(id_ == categoria)
