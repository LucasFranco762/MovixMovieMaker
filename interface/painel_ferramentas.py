"""Painel de ferramentas à direita da barra lateral (REQ-017, 19.3).

Funcional nesta etapa: Mídias (biblioteca básica) e Ajustes (layout e tempo de
inatividade do painel de propriedades). As demais categorias são mostradas como
"ainda não implementadas" — não há controles decorativos.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from core.constantes import ICONES_CATEGORIA
from core.layouts import LAYOUTS
from projetos.modelos import Projeto

TITULOS = {
    "midias": "Mídias", "transicoes": "Transições", "efeitos": "Efeitos",
    "textos": "Textos", "audio": "Áudio", "legendas": "Legendas", "ajustes": "Ajustes",
}
ETAPA_PENDENTE = {
    "transicoes": "Transições serão implementadas na Etapa 5.",
    "efeitos": "Efeitos visuais serão implementados na Etapa 5.",
    "textos": "Textos e títulos serão implementados na Etapa 5.",
    "audio": "Edição e mixagem de áudio serão implementadas na Etapa 5.",
    "legendas": "Legendas serão implementadas na Etapa 5.",
}


class PaginaMidias(QWidget):
    importar_solicitado = pyqtSignal()
    adicionar_solicitado = pyqtSignal(str)       # id da mídia

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Pesquisar mídias…")
        self._busca.textChanged.connect(self._filtrar)
        botao = QPushButton("⬇  Importar mídia…")
        botao.setObjectName("primario")
        botao.clicked.connect(self.importar_solicitado)
        self._lista = QListWidget()
        self._lista.setToolTip("Clique duas vezes para adicionar à timeline na posição do cursor")
        self._lista.itemDoubleClicked.connect(
            lambda it: self.adicionar_solicitado.emit(it.data(Qt.ItemDataRole.UserRole)))
        self._vazio = QLabel("Nenhuma mídia importada.")
        self._vazio.setObjectName("suave")
        lay.addWidget(botao)
        lay.addWidget(self._busca)
        lay.addWidget(self._lista, 1)
        lay.addWidget(self._vazio)

    def atualizar(self, projeto: Projeto) -> None:
        self._lista.clear()
        for m in projeto.midias.values():
            ausente = not Path(m.caminho).is_file()
            item = QListWidgetItem(f"{ICONES_CATEGORIA.get(m.tipo, '?')}  {m.nome}"
                                   + ("   ⚠ arquivo ausente" if ausente else ""))
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            item.setToolTip(m.caminho)
            self._lista.addItem(item)
        self._vazio.setVisible(self._lista.count() == 0)
        self._filtrar(self._busca.text())

    def _filtrar(self, texto: str) -> None:
        t = texto.strip().lower()
        for i in range(self._lista.count()):
            item = self._lista.item(i)
            item.setHidden(bool(t) and t not in item.text().lower())


class PaginaAjustes(QWidget):
    layout_escolhido = pyqtSignal(str)
    inatividade_alterada = pyqtSignal(int)

    def __init__(self, layout_atual: str, inatividade_s: int) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Layout"))
        self._combo = QComboBox()
        for d in LAYOUTS.values():
            self._combo.addItem(d.nome, d.id)
        self._combo.setCurrentIndex(self._combo.findData(layout_atual))
        self._combo.currentIndexChanged.connect(
            lambda _: self.layout_escolhido.emit(self._combo.currentData()))
        self._descricao = QLabel()
        self._descricao.setObjectName("suave")
        self._descricao.setWordWrap(True)
        self._combo.currentIndexChanged.connect(self._atualizar_descricao)
        self._atualizar_descricao()
        lay.addWidget(self._combo)
        lay.addWidget(self._descricao)

        lay.addSpacing(12)
        lay.addWidget(QLabel("Recolher propriedades após inatividade (segundos)"))
        self._spin = QSpinBox()
        self._spin.setRange(2, 120)
        self._spin.setValue(inatividade_s)
        self._spin.valueChanged.connect(self.inatividade_alterada)
        lay.addWidget(self._spin)
        lay.addStretch(1)

    def selecionar_layout(self, layout_id: str) -> None:
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(self._combo.findData(layout_id))
        self._combo.blockSignals(False)
        self._atualizar_descricao()

    def _atualizar_descricao(self) -> None:
        d = LAYOUTS.get(self._combo.currentData())
        self._descricao.setText(d.descricao if d else "")


class PainelFerramentas(QFrame):
    recolher_solicitado = pyqtSignal()

    def __init__(self, layout_atual: str, inatividade_s: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("painelFerramentas")
        self.setMinimumWidth(200)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)

        topo = QHBoxLayout()
        self._titulo = QLabel("Mídias")
        self._titulo.setObjectName("tituloPainel")
        fechar = QToolButton()
        fechar.setObjectName("semBorda")
        fechar.setText("«")
        fechar.setToolTip("Recolher painel")
        fechar.clicked.connect(self.recolher_solicitado)
        topo.addWidget(self._titulo, 1)
        topo.addWidget(fechar)
        lay.addLayout(topo)

        self._pilha = QStackedWidget()
        self.midias = PaginaMidias()
        self.ajustes = PaginaAjustes(layout_atual, inatividade_s)
        self._indices: dict[str, int] = {}
        for id_ in TITULOS:
            if id_ == "midias":
                pagina: QWidget = self.midias
            elif id_ == "ajustes":
                pagina = self.ajustes
            else:
                pagina = QWidget()
                pl = QVBoxLayout(pagina)
                msg = QLabel(ETAPA_PENDENTE[id_])
                msg.setObjectName("suave")
                msg.setWordWrap(True)
                pl.addWidget(msg)
                pl.addStretch(1)
            self._indices[id_] = self._pilha.addWidget(pagina)
        lay.addWidget(self._pilha, 1)

    def mostrar_categoria(self, categoria: str) -> None:
        self._titulo.setText(TITULOS[categoria])
        self._pilha.setCurrentIndex(self._indices[categoria])
