"""Painel de ferramentas à direita da barra lateral (REQ-017, 19.3).

Funcionais: Mídias, Transições, Áudio e Ajustes. As demais categorias são
mostradas como "ainda não implementadas" — não há controles decorativos.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtMultimedia import (
    QAudioInput, QMediaCaptureSession, QMediaDevices, QMediaFormat, QMediaRecorder,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSlider, QSpinBox, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from core.configuracoes import diretorio_dados_usuario
from core.constantes import ICONES_CATEGORIA, TRANSICAO_DISSOLVER
from core.layouts import LAYOUTS
from projetos.modelos import Projeto

TITULOS = {
    "midias": "Mídias", "transicoes": "Transições", "efeitos": "Efeitos",
    "textos": "Textos", "audio": "Áudio", "legendas": "Legendas", "ajustes": "Ajustes",
}
ETAPA_PENDENTE = {
    "efeitos": "Efeitos visuais serão implementados na Etapa 5.",
    "textos": "Textos e títulos serão implementados na Etapa 5.",
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
        self._tipo.addItem("⇄  Dissolver", TRANSICAO_DISSOLVER)
        self._tipo.setToolTip("Mistura gradualmente a imagem do primeiro clipe com a do segundo")
        lay.addWidget(self._tipo)

        lay.addWidget(QLabel("Duração"))
        self._duracao = QDoubleSpinBox()
        self._duracao.setRange(0.1, 5.0)
        self._duracao.setSingleStep(0.1)
        self._duracao.setDecimals(1)
        self._duracao.setValue(1.0)
        self._duracao.setSuffix(" s")
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
                f"     Dissolver · {transicao.duracao / fps:.1f} s")
            item.setData(Qt.ItemDataRole.UserRole, transicao.id)
            self._lista.addItem(item)
            if transicao.id == id_anterior:
                self._lista.setCurrentItem(item)
        self._atualizar_remover()

    def _atualizar_remover(self) -> None:
        self._remover.setEnabled(self._lista.currentItem() is not None)

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

    def __init__(self) -> None:
        super().__init__()
        self._caminho_gravacao: Path | None = None
        self._gravando = False
        self._dispositivos = []

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
        for controle in (self._original, self._adicionado):
            controle.valueChanged.connect(self._atualizar_rotulos)
            controle.sliderReleased.connect(self._emitir_mixagem)

        importar = QPushButton("＋  Adicionar arquivo de áudio…")
        importar.setObjectName("primario")
        importar.clicked.connect(self.importar_solicitado)
        lay.addWidget(importar)

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
        self.audio = PaginaAudio()
        self.ajustes = PaginaAjustes(layout_atual, inatividade_s)
        self._indices: dict[str, int] = {}
        for id_ in TITULOS:
            if id_ == "midias":
                pagina: QWidget = self.midias
            elif id_ == "transicoes":
                pagina = self.transicoes
            elif id_ == "audio":
                pagina = self.audio
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
