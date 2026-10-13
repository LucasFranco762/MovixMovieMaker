"""Painel das ferramentas selecionadas na barra lateral (REQ-017, 19.3)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtMultimedia import (
    QAudioInput, QMediaCaptureSession, QMediaDevices, QMediaFormat, QMediaRecorder,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSlider, QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from core.configuracoes import diretorio_dados_usuario
from core.constantes import (
    CATALOGO_EFEITOS, CATALOGO_TRANSICOES, ICONES_CATEGORIA, NOMES_EFEITO,
    NOMES_TRANSICAO, TIPO_AUDIO, TIPO_LEGENDA, TIPO_TEXTO,
)
from core.layouts import LAYOUTS
from core.tempo import formatar_timecode
from projetos.modelos import Projeto

TITULOS = {
    "midias": "Mídias", "transicoes": "Transições", "efeitos": "Efeitos",
    "textos": "Textos", "audio": "Áudio", "legendas": "Legendas", "ajustes": "Ajustes",
}
ETAPA_PENDENTE = {
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


class PaginaTransicoes(QWidget):
    """Catálogo e gerenciamento das transições aplicadas ao projeto."""

    aplicar_solicitado = pyqtSignal(str, float)  # tipo, duração em segundos
    remover_solicitado = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        explicacao = QLabel(
            "Selecione dois clipes consecutivos na mesma faixa de vídeo ou posicione "
            "o cursor exatamente no corte entre eles.")
        explicacao.setObjectName("suave")
        explicacao.setWordWrap(True)
        lay.addWidget(explicacao)

        lay.addWidget(QLabel("Tipo"))
        self._tipo = QComboBox()
        for tipo, nome, descricao in CATALOGO_TRANSICOES:
            self._tipo.addItem(f"⇄  {nome}", tipo)
            self._tipo.setItemData(self._tipo.count() - 1, descricao, Qt.ItemDataRole.ToolTipRole)
        self._tipo.currentIndexChanged.connect(self._atualizar_dica_tipo)
        self._atualizar_dica_tipo()
        lay.addWidget(self._tipo)

        lay.addWidget(QLabel("Duração"))
        self._duracao = QDoubleSpinBox()
        self._duracao.setRange(0.1, 5.0)
        self._duracao.setSingleStep(0.1)
        self._duracao.setDecimals(1)
        self._duracao.setValue(1.0)
        self._duracao.setSuffix(" s")
        self._duracao.setStyleSheet("color: black;")
        lay.addWidget(self._duracao)

        aplicar = QPushButton("⇄  Aplicar no corte")
        aplicar.setObjectName("primario")
        aplicar.clicked.connect(lambda: self.aplicar_solicitado.emit(
            self._tipo.currentData(), self._duracao.value()))
        lay.addWidget(aplicar)

        lay.addSpacing(10)
        lay.addWidget(QLabel("Transições aplicadas"))
        self._lista = QListWidget()
        self._lista.setToolTip("Transições existentes no projeto")
        self._lista.itemSelectionChanged.connect(self._atualizar_remover)
        lay.addWidget(self._lista, 1)
        self._remover = QPushButton("Remover transição selecionada")
        self._remover.setEnabled(False)
        self._remover.clicked.connect(self._emitir_remocao)
        lay.addWidget(self._remover)

    def atualizar(self, projeto: Projeto) -> None:
        selecionada = self._lista.currentItem()
        id_anterior = selecionada.data(Qt.ItemDataRole.UserRole) if selecionada else None
        self._lista.clear()
        fps = float(projeto.config.fps)
        for transicao in projeto.transicoes:
            try:
                _, origem = projeto.localizar_clipe(transicao.clipe_origem_id)
                _, destino = projeto.localizar_clipe(transicao.clipe_destino_id)
            except KeyError:
                continue
            item = QListWidgetItem(
                f"⇄  {origem.nome} → {destino.nome}\n"
                f"     {NOMES_TRANSICAO.get(transicao.tipo, transicao.tipo)} · "
                f"{transicao.duracao / fps:.1f} s")
            item.setData(Qt.ItemDataRole.UserRole, transicao.id)
            self._lista.addItem(item)
            if transicao.id == id_anterior:
                self._lista.setCurrentItem(item)
        self._atualizar_remover()

    def _atualizar_dica_tipo(self) -> None:
        dica = self._tipo.itemData(self._tipo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        self._tipo.setToolTip(dica or "")

    def _atualizar_remover(self) -> None:
        self._remover.setEnabled(self._lista.currentItem() is not None)

    def _emitir_remocao(self) -> None:
        item = self._lista.currentItem()
        if item is not None:
            self.remover_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))


class PaginaEfeitos(QWidget):
    """Catálogo de efeitos e efeitos aplicados ao clipe visual selecionado."""

    aplicar_solicitado = pyqtSignal(str, int)
    remover_solicitado = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._clipe_valido = False
        self._efeitos_aplicados: dict[str, int] = {}
        self._intensidades_catalogo = {tipo: 100 for tipo, _nome, _desc in CATALOGO_EFEITOS}

        explicacao = QLabel("Selecione um clipe de vídeo ou imagem na timeline.")
        explicacao.setObjectName("suave")
        explicacao.setWordWrap(True)
        lay.addWidget(explicacao)

        lay.addWidget(QLabel("Efeito"))
        self._tipo = QComboBox()
        for tipo, nome, descricao in CATALOGO_EFEITOS:
            self._tipo.addItem(f"✨  {nome}", tipo)
            self._tipo.setItemData(self._tipo.count() - 1, descricao, Qt.ItemDataRole.ToolTipRole)
        self._tipo.currentIndexChanged.connect(self._atualizar_descricao)
        lay.addWidget(self._tipo)

        self._rotulo_intensidade = QLabel("Intensidade: 100%")
        self._rotulo_intensidade.setObjectName("suave")
        lay.addWidget(self._rotulo_intensidade)
        linha_intensidade = QHBoxLayout()
        linha_intensidade.setSpacing(6)
        self._diminuir = QToolButton()
        self._diminuir.setText("−")
        self._diminuir.setToolTip("Reduzir intensidade")
        self._diminuir.setAutoRepeat(True)
        self._diminuir.setFixedWidth(32)
        self._diminuir.clicked.connect(lambda _=False: self._intensidade.setValue(
            self._intensidade.value() - self._intensidade.singleStep()))
        self._intensidade = QSlider(Qt.Orientation.Horizontal)
        self._intensidade.setRange(0, 100)
        self._intensidade.setSingleStep(5)
        self._intensidade.setPageStep(10)
        self._intensidade.setValue(100)
        self._intensidade.setToolTip("Intensidade do efeito, de 0% a 100%")
        self._aumentar = QToolButton()
        self._aumentar.setText("+")
        self._aumentar.setToolTip("Aumentar intensidade")
        self._aumentar.setAutoRepeat(True)
        self._aumentar.setFixedWidth(32)
        self._aumentar.clicked.connect(lambda _=False: self._intensidade.setValue(
            self._intensidade.value() + self._intensidade.singleStep()))
        linha_intensidade.addWidget(self._diminuir)
        linha_intensidade.addWidget(self._intensidade, 1)
        linha_intensidade.addWidget(self._aumentar)
        lay.addLayout(linha_intensidade)

        self._descricao = QLabel()
        self._descricao.setObjectName("suave")
        self._descricao.setWordWrap(True)
        lay.addWidget(self._descricao)

        self._aplicar = QPushButton("✨  Aplicar ao clipe")
        self._aplicar.setObjectName("primario")
        self._aplicar.clicked.connect(
            lambda: self.aplicar_solicitado.emit(
                self._tipo.currentData(), self._intensidade.value()))
        lay.addWidget(self._aplicar)

        self._estado = QLabel("Nenhum clipe selecionado.")
        self._estado.setObjectName("suave")
        self._estado.setWordWrap(True)
        lay.addWidget(self._estado)

        lay.addSpacing(10)
        lay.addWidget(QLabel("Efeitos aplicados"))
        self._lista = QListWidget()
        self._lista.itemSelectionChanged.connect(self._selecionar_efeito_aplicado)
        lay.addWidget(self._lista, 1)

        self._remover = QPushButton("Remover efeito selecionado")
        self._remover.clicked.connect(self._emitir_remocao)
        lay.addWidget(self._remover)
        self._intensidade.valueChanged.connect(self._ao_mudar_intensidade)
        self._atualizar_descricao()
        self._atualizar_botoes()

    def atualizar(self, projeto: Projeto, ids_selecionados: list[str]) -> None:
        tipo_anterior = None
        if self._lista.currentItem() is not None:
            tipo_anterior = self._lista.currentItem().data(Qt.ItemDataRole.UserRole)
        self._lista.clear()
        self._clipe_valido = False
        self._efeitos_aplicados.clear()

        if len(ids_selecionados) != 1:
            self._estado.setText("Selecione somente um clipe visual para aplicar efeitos.")
        else:
            try:
                faixa, clipe = projeto.localizar_clipe(ids_selecionados[0])
            except KeyError:
                self._estado.setText("O clipe selecionado não foi encontrado.")
            else:
                if faixa.tipo != "video":
                    self._estado.setText("O clipe selecionado é de áudio.")
                else:
                    self._clipe_valido = True
                    self._efeitos_aplicados = dict(clipe.efeitos)
                    self._estado.setText(f"Clipe selecionado: {clipe.nome}")
                    for tipo, intensidade in clipe.efeitos.items():
                        item = QListWidgetItem(
                            f"✨  {NOMES_EFEITO.get(tipo, tipo)} · {intensidade}%")
                        item.setData(Qt.ItemDataRole.UserRole, tipo)
                        self._lista.addItem(item)
                        if tipo == tipo_anterior:
                            self._lista.setCurrentItem(item)
        self._sincronizar_intensidade()
        self._atualizar_botoes()

    def _atualizar_descricao(self) -> None:
        descricao = self._tipo.itemData(
            self._tipo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        self._descricao.setText(descricao or "")
        self._tipo.setToolTip(descricao or "")
        self._sincronizar_intensidade()
        self._atualizar_botoes()

    def _sincronizar_intensidade(self) -> None:
        tipo = self._tipo.currentData()
        if tipo is None:
            return
        valor = self._efeitos_aplicados.get(
            tipo, self._intensidades_catalogo.get(tipo, 100))
        self._intensidade.setValue(valor)
        self._rotulo_intensidade.setText(f"Intensidade: {valor}%")

    def _ao_mudar_intensidade(self, valor: int) -> None:
        tipo = self._tipo.currentData()
        if tipo is not None:
            self._intensidades_catalogo[tipo] = valor
        self._rotulo_intensidade.setText(f"Intensidade: {valor}%")
        self._diminuir.setEnabled(valor > self._intensidade.minimum())
        self._aumentar.setEnabled(valor < self._intensidade.maximum())
        self._atualizar_botoes()

    def _selecionar_efeito_aplicado(self) -> None:
        item = self._lista.currentItem()
        if item is not None:
            indice = self._tipo.findData(item.data(Qt.ItemDataRole.UserRole))
            if indice >= 0:
                self._tipo.setCurrentIndex(indice)
        self._atualizar_botoes()

    def _atualizar_botoes(self) -> None:
        # O catálogo deve permanecer consultável mesmo sem um clipe na
        # timeline; somente as ações que alteram o projeto dependem da seleção.
        self._tipo.setEnabled(True)
        tipo = self._tipo.currentData()
        aplicada = self._efeitos_aplicados.get(tipo)
        intensidade = self._intensidade.value()
        if aplicada is None:
            self._aplicar.setText("✨  Aplicar ao clipe")
        elif aplicada == intensidade:
            self._aplicar.setText("✓  Intensidade aplicada")
        else:
            self._aplicar.setText("✨  Atualizar intensidade")
        self._aplicar.setEnabled(
            self._clipe_valido and (aplicada is None or aplicada != intensidade))
        self._remover.setEnabled(self._clipe_valido and self._lista.currentItem() is not None)

    def _emitir_remocao(self) -> None:
        item = self._lista.currentItem()
        if item is not None:
            self.remover_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))


class PaginaTextos(QWidget):
    """Cria e edita títulos independentes na timeline."""

    salvar_solicitado = pyqtSignal(object)
    remover_solicitado = pyqtSignal(str)
    selecionar_solicitado = pyqtSignal(str)

    POSICOES = (
        ("Superior esquerdo", "left", "top"),
        ("Superior central", "center", "top"),
        ("Superior direito", "right", "top"),
        ("Centro esquerdo", "left", "middle"),
        ("Centro", "center", "middle"),
        ("Centro direito", "right", "middle"),
        ("Inferior esquerdo", "left", "bottom"),
        ("Inferior central", "center", "bottom"),
        ("Inferior direito", "right", "bottom"),
    )

    def __init__(self) -> None:
        super().__init__()
        self._id_edicao: str | None = None
        self._cor_texto = "#ffffff"
        self._cor_fundo = "#00000000"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        explicacao = QLabel(
            "Crie um título na posição atual do cursor ou selecione um texto existente para editá-lo.")
        explicacao.setObjectName("suave")
        explicacao.setWordWrap(True)
        lay.addWidget(explicacao)

        lay.addWidget(QLabel("Conteúdo"))
        self._conteudo = QPlainTextEdit()
        self._conteudo.setPlaceholderText("Digite o texto que aparecerá no vídeo…")
        self._conteudo.setFixedHeight(68)
        lay.addWidget(self._conteudo)

        lay.addWidget(QLabel("Fonte"))
        self._fonte = QFontComboBox()
        self._fonte.setCurrentFont(self._fonte.font())
        lay.addWidget(self._fonte)

        linha_tamanho = QHBoxLayout()
        linha_tamanho.addWidget(QLabel("Tamanho"))
        self._tamanho = QSpinBox()
        self._tamanho.setRange(8, 300)
        self._tamanho.setValue(72)
        linha_tamanho.addWidget(self._tamanho, 1)
        linha_tamanho.addWidget(QLabel("Duração"))
        self._duracao = QDoubleSpinBox()
        self._duracao.setRange(0.1, 60.0)
        self._duracao.setValue(5.0)
        self._duracao.setSingleStep(0.5)
        self._duracao.setSuffix(" s")
        self._duracao.setStyleSheet("color: black;")
        linha_tamanho.addWidget(self._duracao, 1)
        lay.addLayout(linha_tamanho)

        lay.addWidget(QLabel("Posição"))
        self._posicao = QComboBox()
        for nome, horizontal, vertical in self.POSICOES:
            self._posicao.addItem(nome, (horizontal, vertical))
        self._posicao.setCurrentIndex(4)
        lay.addWidget(self._posicao)

        linha_cores = QHBoxLayout()
        self._btn_cor_texto = QPushButton("Cor do texto")
        self._btn_cor_texto.clicked.connect(lambda: self._escolher_cor(False))
        self._btn_cor_fundo = QPushButton("Cor de fundo")
        self._btn_cor_fundo.clicked.connect(lambda: self._escolher_cor(True))
        linha_cores.addWidget(self._btn_cor_texto)
        linha_cores.addWidget(self._btn_cor_fundo)
        lay.addLayout(linha_cores)
        self._atualizar_cores()

        linha_acoes = QHBoxLayout()
        self._salvar = QPushButton("＋  Adicionar texto")
        self._salvar.setObjectName("primario")
        self._salvar.clicked.connect(self._emitir_salvamento)
        self._novo = QPushButton("Novo")
        self._novo.clicked.connect(self._limpar_formulario)
        linha_acoes.addWidget(self._salvar, 1)
        linha_acoes.addWidget(self._novo)
        lay.addLayout(linha_acoes)

        lay.addWidget(QLabel("Textos do projeto"))
        self._lista = QListWidget()
        self._lista.itemSelectionChanged.connect(self._emitir_selecao)
        lay.addWidget(self._lista, 1)
        self._remover = QPushButton("Remover texto selecionado")
        self._remover.setEnabled(False)
        self._remover.clicked.connect(self._emitir_remocao)
        lay.addWidget(self._remover)

    def atualizar(self, projeto: Projeto, ids_selecionados: list[str]) -> None:
        textos = [c for f in projeto.faixas for c in f.clipes if c.tipo == TIPO_TEXTO]
        selecionado = next((c for c in textos if c.id in ids_selecionados), None)
        self._lista.blockSignals(True)
        self._lista.clear()
        for clipe in sorted(textos, key=lambda c: c.inicio):
            item = QListWidgetItem(f"T  {clipe.conteudo.replace(chr(10), ' ')[:50]}")
            item.setData(Qt.ItemDataRole.UserRole, clipe.id)
            self._lista.addItem(item)
            if selecionado is not None and clipe.id == selecionado.id:
                self._lista.setCurrentItem(item)
        self._lista.blockSignals(False)
        self._remover.setEnabled(selecionado is not None)
        if selecionado is not None and selecionado.id != self._id_edicao:
            self._carregar_clipe(selecionado, projeto)
        elif selecionado is None and self._id_edicao is not None:
            self._limpar_formulario()

    def _carregar_clipe(self, clipe, projeto: Projeto) -> None:
        self._id_edicao = clipe.id
        self._conteudo.setPlainText(clipe.conteudo)
        self._fonte.setCurrentText(clipe.familia_fonte)
        self._tamanho.setValue(clipe.tamanho_fonte)
        self._duracao.setValue(clipe.duracao / float(projeto.config.fps))
        indice = self._posicao.findData((clipe.alinhamento_h, clipe.alinhamento_v))
        self._posicao.setCurrentIndex(max(0, indice))
        self._cor_texto, self._cor_fundo = clipe.cor_texto, clipe.cor_fundo_texto
        self._atualizar_cores()
        self._salvar.setText("✓  Salvar alterações")

    def _limpar_formulario(self) -> None:
        self._id_edicao = None
        self._conteudo.clear()
        self._duracao.setValue(5.0)
        self._salvar.setText("＋  Adicionar texto")
        self._lista.clearSelection()
        self._remover.setEnabled(False)

    def _escolher_cor(self, fundo: bool) -> None:
        atual = self._cor_fundo if fundo else self._cor_texto
        cor = QColorDialog.getColor(
            QColor(atual), self, "Escolher cor",
            QColorDialog.ColorDialogOption.ShowAlphaChannel if fundo
            else QColorDialog.ColorDialogOption(0))
        if not cor.isValid():
            return
        valor = cor.name(QColor.NameFormat.HexArgb if fundo else QColor.NameFormat.HexRgb)
        if fundo:
            self._cor_fundo = valor
        else:
            self._cor_texto = valor
        self._atualizar_cores()

    def _atualizar_cores(self) -> None:
        self._btn_cor_texto.setStyleSheet(f"border-bottom: 4px solid {self._cor_texto};")
        fundo_visivel = self._cor_fundo[-6:] if len(self._cor_fundo) >= 7 else "#000000"
        self._btn_cor_fundo.setStyleSheet(f"border-bottom: 4px solid #{fundo_visivel};")

    def _emitir_salvamento(self) -> None:
        horizontal, vertical = self._posicao.currentData()
        self.salvar_solicitado.emit({
            "clipe_id": self._id_edicao,
            "tipo": TIPO_TEXTO,
            "conteudo": self._conteudo.toPlainText(),
            "duracao_segundos": self._duracao.value(),
            "familia_fonte": self._fonte.currentFont().family(),
            "tamanho_fonte": self._tamanho.value(),
            "cor_texto": self._cor_texto,
            "cor_fundo_texto": self._cor_fundo,
            "alinhamento_h": horizontal,
            "alinhamento_v": vertical,
        })

    def _emitir_selecao(self) -> None:
        item = self._lista.currentItem()
        self._remover.setEnabled(item is not None)
        if item is not None:
            self.selecionar_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))

    def _emitir_remocao(self) -> None:
        item = self._lista.currentItem()
        if item is not None:
            self.remover_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))


class PaginaAudio(QWidget):
    """Mixagem global, importação de áudio e gravação de voz pelo microfone."""

    importar_solicitado = pyqtSignal()
    mixagem_alterada = pyqtSignal(float, float)
    gravacao_concluida = pyqtSignal(str)
    erro = pyqtSignal(str)
    selecionar_solicitado = pyqtSignal(str)
    remover_solicitado = pyqtSignal(str)
    volume_clipe_alterado = pyqtSignal(str, float)

    def __init__(self) -> None:
        super().__init__()
        self._caminho_gravacao: Path | None = None
        self._gravando = False
        self._dispositivos = []
        self._clipe_audio_id: str | None = None
        self._atualizando_clipe = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        introducao = QLabel(
            "Combine o áudio original dos vídeos com música, narração ou qualquer outro áudio.")
        introducao.setObjectName("suave")
        introducao.setWordWrap(True)
        lay.addWidget(introducao)

        lay.addWidget(QLabel("Predefinição de mixagem"))
        self._modo = QComboBox()
        self._modo.addItem("Original + áudios adicionados", (100, 100))
        self._modo.addItem("Somente áudio original", (100, 0))
        self._modo.addItem("Somente áudios adicionados", (0, 100))
        self._modo.addItem("Personalizada", None)
        self._modo.currentIndexChanged.connect(self._aplicar_modo)
        lay.addWidget(self._modo)

        self._original, self._rotulo_original = self._criar_volume(lay, "Áudio original dos vídeos")
        self._adicionado, self._rotulo_adicionado = self._criar_volume(lay, "Música, voz e outros áudios")
        self._timer_mixagem = QTimer(self)
        self._timer_mixagem.setSingleShot(True)
        self._timer_mixagem.setInterval(160)
        self._timer_mixagem.timeout.connect(self._emitir_mixagem)
        for controle in (self._original, self._adicionado):
            controle.valueChanged.connect(self._atualizar_rotulos)
            controle.valueChanged.connect(lambda _=0: self._timer_mixagem.start())

        importar = QPushButton("＋  Adicionar arquivo de áudio…")
        importar.setObjectName("primario")
        importar.clicked.connect(self.importar_solicitado)
        lay.addWidget(importar)

        lay.addSpacing(8)
        lay.addWidget(QLabel("Áudios na timeline"))
        self._lista_clipes = QListWidget()
        self._lista_clipes.setMaximumHeight(120)
        self._lista_clipes.itemSelectionChanged.connect(self._selecionar_clipe_audio)
        lay.addWidget(self._lista_clipes)

        linha_volume = QHBoxLayout()
        linha_volume.addWidget(QLabel("Volume do clipe"), 1)
        self._rotulo_volume_clipe = QLabel("—")
        linha_volume.addWidget(self._rotulo_volume_clipe)
        lay.addLayout(linha_volume)
        self._volume_clipe = QSlider(Qt.Orientation.Horizontal)
        self._volume_clipe.setRange(0, 200)
        self._volume_clipe.setValue(100)
        self._volume_clipe.setEnabled(False)
        self._volume_clipe.valueChanged.connect(self._ao_volume_clipe)
        lay.addWidget(self._volume_clipe)
        self._timer_volume_clipe = QTimer(self)
        self._timer_volume_clipe.setSingleShot(True)
        self._timer_volume_clipe.setInterval(160)
        self._timer_volume_clipe.timeout.connect(self._emitir_volume_clipe)
        self._remover_clipe = QPushButton("Remover áudio selecionado")
        self._remover_clipe.setEnabled(False)
        self._remover_clipe.clicked.connect(self._emitir_remocao_audio)
        lay.addWidget(self._remover_clipe)

        lay.addSpacing(8)
        lay.addWidget(QLabel("Gravação de voz"))
        self._dispositivo = QComboBox()
        lay.addWidget(self._dispositivo)
        self._btn_gravar = QPushButton("●  Iniciar gravação")
        self._btn_gravar.clicked.connect(self._alternar_gravacao)
        lay.addWidget(self._btn_gravar)
        self._estado = QLabel("A gravação será adicionada na posição atual da timeline.")
        self._estado.setObjectName("suave")
        self._estado.setWordWrap(True)
        lay.addWidget(self._estado)
        lay.addStretch(1)

        self._dispositivos_midia = QMediaDevices(self)
        self._dispositivos_midia.audioInputsChanged.connect(self._carregar_dispositivos)
        self._entrada = QAudioInput(self)
        self._sessao = QMediaCaptureSession(self)
        self._gravador = QMediaRecorder(self)
        self._sessao.setAudioInput(self._entrada)
        self._sessao.setRecorder(self._gravador)
        self._gravador.durationChanged.connect(lambda duracao: self._ao_duracao(duracao))
        self._carregar_dispositivos()
        self.definir_mixagem(1.0, 1.0)

    @staticmethod
    def _criar_volume(lay: QVBoxLayout, titulo: str) -> tuple[QSlider, QLabel]:
        linha = QHBoxLayout()
        linha.addWidget(QLabel(titulo), 1)
        valor = QLabel("100%")
        linha.addWidget(valor)
        lay.addLayout(linha)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 200)
        slider.setValue(100)
        lay.addWidget(slider)
        return slider, valor

    def definir_mixagem(self, original: float, adicionado: float) -> None:
        self._timer_mixagem.stop()
        for controle, valor in (
            (self._original, round(original * 100)),
            (self._adicionado, round(adicionado * 100)),
        ):
            controle.blockSignals(True)
            controle.setValue(valor)
            controle.blockSignals(False)
        self._atualizar_rotulos()
        self._sincronizar_modo()

    def _aplicar_modo(self, indice: int) -> None:
        valores = self._modo.itemData(indice)
        if valores is None:
            return
        self._original.setValue(valores[0])
        self._adicionado.setValue(valores[1])
        self._timer_mixagem.stop()
        self._emitir_mixagem()

    def _atualizar_rotulos(self) -> None:
        self._rotulo_original.setText(f"{self._original.value()}%")
        self._rotulo_adicionado.setText(f"{self._adicionado.value()}%")

    def _sincronizar_modo(self) -> None:
        valores = (self._original.value(), self._adicionado.value())
        indice = next((i for i in range(3) if self._modo.itemData(i) == valores), 3)
        self._modo.blockSignals(True)
        self._modo.setCurrentIndex(indice)
        self._modo.blockSignals(False)

    def _emitir_mixagem(self) -> None:
        self._sincronizar_modo()
        self.mixagem_alterada.emit(self._original.value() / 100, self._adicionado.value() / 100)

    def atualizar(self, projeto: Projeto, ids_selecionados: list[str]) -> None:
        clipes = [c for f in projeto.faixas for c in f.clipes if c.tipo == TIPO_AUDIO]
        selecionado = next((c for c in clipes if c.id in ids_selecionados), None)
        self._lista_clipes.blockSignals(True)
        self._lista_clipes.clear()
        for clipe in sorted(clipes, key=lambda c: c.inicio):
            item = QListWidgetItem(f"♪  {clipe.nome}")
            item.setData(Qt.ItemDataRole.UserRole, clipe.id)
            self._lista_clipes.addItem(item)
            if selecionado is not None and clipe.id == selecionado.id:
                self._lista_clipes.setCurrentItem(item)
        self._lista_clipes.blockSignals(False)
        self._definir_clipe_audio(selecionado)

    def _definir_clipe_audio(self, clipe) -> None:
        self._timer_volume_clipe.stop()
        self._clipe_audio_id = clipe.id if clipe is not None else None
        self._atualizando_clipe = True
        self._volume_clipe.setValue(round(clipe.volume * 100) if clipe is not None else 100)
        self._atualizando_clipe = False
        self._volume_clipe.setEnabled(clipe is not None)
        self._remover_clipe.setEnabled(clipe is not None)
        self._rotulo_volume_clipe.setText(
            f"{self._volume_clipe.value()}%" if clipe is not None else "—")

    def _selecionar_clipe_audio(self) -> None:
        item = self._lista_clipes.currentItem()
        if item is not None:
            self.selecionar_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))

    def _ao_volume_clipe(self, valor: int) -> None:
        if self._clipe_audio_id is None:
            return
        self._rotulo_volume_clipe.setText(f"{valor}%")
        if not self._atualizando_clipe:
            self._timer_volume_clipe.start()

    def _emitir_volume_clipe(self) -> None:
        if self._clipe_audio_id is not None:
            self.volume_clipe_alterado.emit(
                self._clipe_audio_id, self._volume_clipe.value() / 100)

    def _emitir_remocao_audio(self) -> None:
        if self._clipe_audio_id is not None:
            self.remover_solicitado.emit(self._clipe_audio_id)

    def _carregar_dispositivos(self) -> None:
        atual = self._dispositivo.currentText()
        self._dispositivos = list(QMediaDevices.audioInputs())
        self._dispositivo.clear()
        for dispositivo in self._dispositivos:
            self._dispositivo.addItem(dispositivo.description())
        indice = self._dispositivo.findText(atual)
        if indice >= 0:
            self._dispositivo.setCurrentIndex(indice)
        self._btn_gravar.setEnabled(bool(self._dispositivos))
        if not self._dispositivos:
            self._estado.setText("Nenhum microfone foi encontrado.")

    def _alternar_gravacao(self) -> None:
        if self._gravando:
            self._parar_e_concluir()
            return
        indice = self._dispositivo.currentIndex()
        if not (0 <= indice < len(self._dispositivos)):
            self.erro.emit("Selecione um microfone antes de iniciar a gravação.")
            return
        pasta = diretorio_dados_usuario() / "gravacoes"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.erro.emit(f"Não foi possível criar a pasta de gravações: {exc}")
            return
        self._caminho_gravacao = pasta / f"narracao-{datetime.now():%Y%m%d-%H%M%S-%f}.wav"
        self._entrada.setDevice(self._dispositivos[indice])
        formato = QMediaFormat(QMediaFormat.FileFormat.Wave)
        formato.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        self._gravador.setMediaFormat(formato)
        self._gravador.setAudioSampleRate(48_000)
        self._gravador.setAudioChannelCount(1)
        self._gravador.setQuality(QMediaRecorder.Quality.HighQuality)
        self._gravador.setOutputLocation(QUrl.fromLocalFile(str(self._caminho_gravacao)))
        self._gravando = True
        self._btn_gravar.setText("■  Parar e adicionar à timeline")
        self._estado.setText("Gravando… 00:00")
        self._gravador.record()
        QTimer.singleShot(500, self._verificar_inicio_gravacao)

    def _verificar_inicio_gravacao(self) -> None:
        if not self._gravando:
            return
        if self._gravador.error() != QMediaRecorder.Error.NoError:
            self._falhar_gravacao(self._gravador.errorString())

    def _parar_e_concluir(self) -> None:
        if not self._gravando:
            return
        self._gravador.stop()
        self._gravando = False
        self._btn_gravar.setText("●  Iniciar gravação")
        caminho = self._caminho_gravacao
        self._caminho_gravacao = None
        self._estado.setText("Finalizando e analisando a gravação…")
        if caminho is not None:
            QTimer.singleShot(300, lambda c=caminho: self._concluir_gravacao(c))

    def _ao_duracao(self, milissegundos: int) -> None:
        if self._gravando:
            segundos = milissegundos // 1000
            self._estado.setText(f"Gravando… {segundos // 60:02d}:{segundos % 60:02d}")

    def _concluir_gravacao(self, caminho: Path) -> None:
        if caminho.is_file() and caminho.stat().st_size > 0:
            self._estado.setText("Gravação concluída e adicionada à timeline.")
            self.gravacao_concluida.emit(str(caminho))
        else:
            self._falhar_gravacao("O microfone não produziu um arquivo de áudio válido.")

    def _falhar_gravacao(self, mensagem: str) -> None:
        self._gravando = False
        self._btn_gravar.setText("●  Iniciar gravação")
        self._estado.setText("Não foi possível concluir a gravação.")
        if mensagem:
            self.erro.emit(f"Falha na gravação: {mensagem}")

    def parar_gravacao(self) -> None:
        if self._gravando:
            self._gravador.stop()
            self._gravando = False


class PaginaLegendas(QWidget):
    """Cria, edita, importa e exporta legendas sincronizadas."""

    salvar_solicitado = pyqtSignal(object)
    remover_solicitado = pyqtSignal(str)
    selecionar_solicitado = pyqtSignal(str)
    importar_solicitado = pyqtSignal()
    exportar_solicitado = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._id_edicao: str | None = None
        self._cor_texto = "#ffffff"
        self._cor_fundo = "#99000000"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        explicacao = QLabel(
            "Adicione uma legenda na posição atual do cursor ou importe um arquivo SubRip.")
        explicacao.setObjectName("suave")
        explicacao.setWordWrap(True)
        lay.addWidget(explicacao)

        linha_arquivo = QHBoxLayout()
        importar = QPushButton("Importar SRT…")
        importar.clicked.connect(self.importar_solicitado)
        exportar = QPushButton("Exportar SRT…")
        exportar.clicked.connect(self.exportar_solicitado)
        linha_arquivo.addWidget(importar)
        linha_arquivo.addWidget(exportar)
        lay.addLayout(linha_arquivo)

        lay.addWidget(QLabel("Texto da legenda"))
        self._conteudo = QPlainTextEdit()
        self._conteudo.setPlaceholderText("Digite a fala ou descrição…")
        self._conteudo.setFixedHeight(68)
        lay.addWidget(self._conteudo)

        linha_opcoes = QHBoxLayout()
        linha_opcoes.addWidget(QLabel("Tamanho"))
        self._tamanho = QSpinBox()
        self._tamanho.setRange(18, 120)
        self._tamanho.setValue(48)
        linha_opcoes.addWidget(self._tamanho, 1)
        linha_opcoes.addWidget(QLabel("Duração"))
        self._duracao = QDoubleSpinBox()
        self._duracao.setRange(0.1, 60.0)
        self._duracao.setValue(3.0)
        self._duracao.setSingleStep(0.1)
        self._duracao.setSuffix(" s")
        self._duracao.setStyleSheet("color: black;")
        linha_opcoes.addWidget(self._duracao, 1)
        lay.addLayout(linha_opcoes)

        linha_cores = QHBoxLayout()
        self._btn_cor_texto = QPushButton("Cor do texto")
        self._btn_cor_texto.clicked.connect(lambda: self._escolher_cor(False))
        self._btn_cor_fundo = QPushButton("Fundo")
        self._btn_cor_fundo.clicked.connect(lambda: self._escolher_cor(True))
        linha_cores.addWidget(self._btn_cor_texto)
        linha_cores.addWidget(self._btn_cor_fundo)
        lay.addLayout(linha_cores)
        self._atualizar_cores()

        linha_acoes = QHBoxLayout()
        self._salvar = QPushButton("＋  Adicionar legenda")
        self._salvar.setObjectName("primario")
        self._salvar.clicked.connect(self._emitir_salvamento)
        novo = QPushButton("Nova")
        novo.clicked.connect(self._limpar_formulario)
        linha_acoes.addWidget(self._salvar, 1)
        linha_acoes.addWidget(novo)
        lay.addLayout(linha_acoes)

        lay.addWidget(QLabel("Legendas do projeto"))
        self._lista = QListWidget()
        self._lista.itemSelectionChanged.connect(self._emitir_selecao)
        lay.addWidget(self._lista, 1)
        self._remover = QPushButton("Remover legenda selecionada")
        self._remover.setEnabled(False)
        self._remover.clicked.connect(self._emitir_remocao)
        lay.addWidget(self._remover)

    def atualizar(self, projeto: Projeto, ids_selecionados: list[str]) -> None:
        legendas = [c for f in projeto.faixas for c in f.clipes if c.tipo == TIPO_LEGENDA]
        selecionada = next((c for c in legendas if c.id in ids_selecionados), None)
        self._lista.blockSignals(True)
        self._lista.clear()
        for clipe in sorted(legendas, key=lambda c: c.inicio):
            tempo = formatar_timecode(clipe.inicio, projeto.config.fps)
            texto = clipe.conteudo.replace("\n", " ")[:42]
            item = QListWidgetItem(f"{tempo}  {texto}")
            item.setData(Qt.ItemDataRole.UserRole, clipe.id)
            self._lista.addItem(item)
            if selecionada is not None and clipe.id == selecionada.id:
                self._lista.setCurrentItem(item)
        self._lista.blockSignals(False)
        self._remover.setEnabled(selecionada is not None)
        if selecionada is not None and selecionada.id != self._id_edicao:
            self._carregar_clipe(selecionada, projeto)
        elif selecionada is None and self._id_edicao is not None:
            self._limpar_formulario()

    def _carregar_clipe(self, clipe, projeto: Projeto) -> None:
        self._id_edicao = clipe.id
        self._conteudo.setPlainText(clipe.conteudo)
        self._tamanho.setValue(clipe.tamanho_fonte)
        self._duracao.setValue(clipe.duracao / float(projeto.config.fps))
        self._cor_texto, self._cor_fundo = clipe.cor_texto, clipe.cor_fundo_texto
        self._atualizar_cores()
        self._salvar.setText("✓  Salvar alterações")

    def _limpar_formulario(self) -> None:
        self._id_edicao = None
        self._conteudo.clear()
        self._duracao.setValue(3.0)
        self._salvar.setText("＋  Adicionar legenda")
        self._lista.clearSelection()
        self._remover.setEnabled(False)

    def _escolher_cor(self, fundo: bool) -> None:
        atual = self._cor_fundo if fundo else self._cor_texto
        opcoes = (QColorDialog.ColorDialogOption.ShowAlphaChannel if fundo
                  else QColorDialog.ColorDialogOption(0))
        cor = QColorDialog.getColor(QColor(atual), self, "Escolher cor", opcoes)
        if cor.isValid():
            valor = cor.name(QColor.NameFormat.HexArgb if fundo else QColor.NameFormat.HexRgb)
            if fundo:
                self._cor_fundo = valor
            else:
                self._cor_texto = valor
            self._atualizar_cores()

    def _atualizar_cores(self) -> None:
        self._btn_cor_texto.setStyleSheet(f"border-bottom: 4px solid {self._cor_texto};")
        fundo = self._cor_fundo[-6:] if len(self._cor_fundo) >= 7 else "000000"
        self._btn_cor_fundo.setStyleSheet(f"border-bottom: 4px solid #{fundo};")

    def _emitir_salvamento(self) -> None:
        self.salvar_solicitado.emit({
            "clipe_id": self._id_edicao,
            "tipo": TIPO_LEGENDA,
            "conteudo": self._conteudo.toPlainText(),
            "duracao_segundos": self._duracao.value(),
            "familia_fonte": "Segoe UI",
            "tamanho_fonte": self._tamanho.value(),
            "cor_texto": self._cor_texto,
            "cor_fundo_texto": self._cor_fundo,
            "alinhamento_h": "center",
            "alinhamento_v": "bottom",
        })

    def _emitir_selecao(self) -> None:
        item = self._lista.currentItem()
        self._remover.setEnabled(item is not None)
        if item is not None:
            self.selecionar_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))

    def _emitir_remocao(self) -> None:
        item = self._lista.currentItem()
        if item is not None:
            self.remover_solicitado.emit(item.data(Qt.ItemDataRole.UserRole))


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
        self._spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._spin.valueChanged.connect(self.inatividade_alterada)
        self._spin.valueChanged.connect(self._atualizar_botoes_inatividade)

        linha_inatividade = QHBoxLayout()
        linha_inatividade.setSpacing(4)
        linha_inatividade.addWidget(self._spin, 1)
        setas = QVBoxLayout()
        setas.setContentsMargins(0, 0, 0, 0)
        setas.setSpacing(2)
        self._subir_inatividade = self._botao_passo(
            "▲", "Aumentar o tempo de inatividade", self._spin.stepUp)
        self._descer_inatividade = self._botao_passo(
            "▼", "Diminuir o tempo de inatividade", self._spin.stepDown)
        setas.addWidget(self._subir_inatividade)
        setas.addWidget(self._descer_inatividade)
        linha_inatividade.addLayout(setas)
        lay.addLayout(linha_inatividade)
        self._atualizar_botoes_inatividade()
        lay.addStretch(1)

    def selecionar_layout(self, layout_id: str) -> None:
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(self._combo.findData(layout_id))
        self._combo.blockSignals(False)
        self._atualizar_descricao()

    @staticmethod
    def _botao_passo(texto: str, dica: str, acao) -> QToolButton:
        botao = QToolButton()
        botao.setText(texto)
        botao.setToolTip(dica)
        botao.setAutoRepeat(True)
        botao.setAutoRepeatDelay(350)
        botao.setAutoRepeatInterval(80)
        botao.setFixedSize(32, 20)
        botao.clicked.connect(lambda _=False: acao())
        return botao

    def _atualizar_botoes_inatividade(self, _valor: int | None = None) -> None:
        self._subir_inatividade.setEnabled(self._spin.value() < self._spin.maximum())
        self._descer_inatividade.setEnabled(self._spin.value() > self._spin.minimum())

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
        self.transicoes = PaginaTransicoes()
        self.efeitos = PaginaEfeitos()
        self.textos = PaginaTextos()
        self.audio = PaginaAudio()
        self.legendas = PaginaLegendas()
        self.ajustes = PaginaAjustes(layout_atual, inatividade_s)
        self._indices: dict[str, int] = {}
        for id_ in TITULOS:
            if id_ == "midias":
                pagina: QWidget = self.midias
            elif id_ == "transicoes":
                pagina = self.transicoes
            elif id_ == "efeitos":
                pagina = self.efeitos
            elif id_ == "textos":
                pagina = self.textos
            elif id_ == "audio":
                pagina = self.audio
            elif id_ == "legendas":
                pagina = self.legendas
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
