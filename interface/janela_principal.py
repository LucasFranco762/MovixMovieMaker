"""Janela principal: monta a interface e liga os componentes ao Controlador (REQ-017).

Contém apenas orquestração de interface; regras de edição ficam em ``editor`` e
persistência em ``projetos``.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QByteArray, QEvent, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget,
)

from core.configuracoes import diretorio_dados_usuario
from core.constantes import (
    EXTENSAO_PROJETO, EXTENSAO_PROJETO_FILTRO, EXTENSOES_AUDIO, EXTENSOES_IMAGEM,
    EXTENSOES_VIDEO, NOME_APLICATIVO,
)
from core.controlador import Controlador
from core.eventos import (
    MIDIAS_ALTERADAS, PROJETO_ALTERADO, PROJETO_CARREGADO, PROJETO_SALVO, SELECAO_ALTERADA,
)
from core.excecoes import ErroEdicao, ErroMovieMaker
from interface.cabecalho import Cabecalho
from interface.gerenciador_layouts import GerenciadorLayouts
from interface.menu_lateral import MenuLateral
from interface.painel_ferramentas import PainelFerramentas
from interface.painel_propriedades import PainelPropriedades
from interface.player import Player
from interface.tarefas import TarefaAnaliseMidias, TarefaExportacao
from interface.timeline import Timeline
from projetos import recuperacao

_log = logging.getLogger(__name__)

FILTRO_MIDIAS = "Mídias ({})".format(
    " ".join(f"*{e}" for e in EXTENSOES_VIDEO + EXTENSOES_IMAGEM + EXTENSOES_AUDIO))


class AreaPlayer(QWidget):
    """Contêiner do player; avisa quando é redimensionado (reposiciona o overlay)."""

    def __init__(self, ao_redimensionar) -> None:
        super().__init__()
        self._cb = ao_redimensionar

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._cb()


class JanelaPrincipal(QMainWindow):
    def __init__(self, controlador: Controlador, aviso_inicial: str = "") -> None:
        super().__init__()
        self.c = controlador
        self.config = controlador.config
        self._tarefas: list[TarefaAnaliseMidias] = []
        self._tarefa_exportacao: TarefaExportacao | None = None
        self._erros_importacao: list[str] = []
        self._modo_tela_cheia: str | None = None
        self._estado_antes_tc: dict = {}
        self._caminho_sem_titulo = diretorio_dados_usuario() / f"sem_titulo{EXTENSAO_PROJETO}"
        self.setWindowTitle(NOME_APLICATIVO)
        self.setMinimumSize(640, 420)
        self.resize(1360, 820)

        self._montar()
        self._conectar()
        self._criar_atalhos()
        self._atualizar_cabecalho()
        if aviso_inicial:
            self.statusBar().showMessage(aviso_inicial)
        self._restaurar_geometria()

    # ---- construção --------------------------------------------------------------------------
    def _montar(self) -> None:
        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        col = QVBoxLayout(raiz)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self.cabecalho = Cabecalho()
        col.addWidget(self.cabecalho)

        corpo = QHBoxLayout()
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        self.menu = MenuLateral()
        corpo.addWidget(self.menu)

        self.split_v = QSplitter(Qt.Orientation.Vertical)
        self.split_h = QSplitter(Qt.Orientation.Horizontal)
        layout_atual = self.config.obter("layout.atual")
        self.painel = PainelFerramentas(layout_atual, int(self.config.obter("interface.inatividade_propriedades_s")))
        self.area_player = AreaPlayer(self._reposicionar_propriedades)
        al = QVBoxLayout(self.area_player)
        al.setContentsMargins(0, 0, 0, 0)
        self.player = Player(self.c)
        al.addWidget(self.player)
        self.propriedades = PainelPropriedades(
            self.area_player, int(self.config.obter("interface.inatividade_propriedades_s")))

        self.split_h.addWidget(self.painel)
        self.split_h.addWidget(self.area_player)
        self.split_h.setCollapsible(1, False)
        self.timeline = Timeline(self.c)
        self.split_v.addWidget(self.split_h)
        self.split_v.addWidget(self.timeline)
        self.split_v.setCollapsible(0, False)
        corpo.addWidget(self.split_v, 1)
        col.addLayout(corpo, 1)

        self.layouts = GerenciadorLayouts(
            self.config, self.split_h, self.split_v, self.painel, self.area_player, self.timeline)
        self._sincronizar_menu_com_layout()

        # Timer de ocultação dos controles na tela cheia de reprodução
        self._timer_controles = QTimer(self)
        self._timer_controles.setSingleShot(True)
        self._timer_controles.setInterval(2500)
        self._timer_controles.timeout.connect(self._ocultar_controles_tela_cheia)
        self.area_player.setMouseTracking(True)
        self.player.area.setMouseTracking(True)
        self.player.area.installEventFilter(self)

        # Autossalvamento
        self._timer_auto = QTimer(self)
        self._timer_auto.setInterval(int(self.config.obter("projetos.autossalvamento_s")) * 1000)
        self._timer_auto.timeout.connect(self._autossalvar)
        self._timer_auto.start()

    def _conectar(self) -> None:
        self.cabecalho.acao.connect(self._acao_cabecalho)
        self.menu.categoria_clicada.connect(self._ao_clicar_categoria)
        self.painel.recolher_solicitado.connect(lambda: self._fechar_painel())
        self.painel.midias.importar_solicitado.connect(self.importar_midias)
        self.painel.midias.adicionar_solicitado.connect(self._adicionar_midia)
        self.painel.transicoes.aplicar_solicitado.connect(
            lambda tipo, duracao: self._tentar(lambda: self.c.aplicar_transicao(tipo, duracao)))
        self.painel.transicoes.remover_solicitado.connect(
            lambda transicao_id: self._tentar(lambda: self.c.remover_transicao(transicao_id)))
        self.painel.audio.importar_solicitado.connect(self._importar_audio)
        self.painel.audio.mixagem_alterada.connect(self.c.configurar_mixagem_audio)
        self.painel.audio.gravacao_concluida.connect(
            lambda caminho: self._iniciar_analise_midias([caminho], adicionar_na_timeline=True))
        self.painel.audio.erro.connect(self._mostrar_erro)
        self.painel.ajustes.layout_escolhido.connect(self._trocar_layout)
        self.painel.ajustes.inatividade_alterada.connect(self._alterar_inatividade)
        self.propriedades.nome_alterado.connect(lambda i, n: self._tentar(lambda: self.c.alterar_clipe(i, nome=n)))
        self.propriedades.cor_alterada.connect(lambda i, cor: self._tentar(lambda: self.c.alterar_clipe(i, cor=cor or None)))
        self.propriedades.volume_alterado.connect(
            lambda i, volume: self._tentar(lambda: self.c.alterar_clipe(i, volume=volume)))
        self.timeline.erro.connect(self._mostrar_erro)
        self.timeline.recolhida_alterada.connect(self.layouts.definir_timeline_recolhida)
        self.timeline.propriedades_solicitadas.connect(self._abrir_propriedades)
        self.player.fullscreen_solicitado.connect(lambda: self.alternar_tela_cheia("reproducao"))

        e = self.c.eventos
        for ev in (PROJETO_ALTERADO, PROJETO_CARREGADO, PROJETO_SALVO):
            e.assinar(ev, self._atualizar_cabecalho)
        e.assinar(PROJETO_CARREGADO, self._ao_projeto_carregado)
        e.assinar(MIDIAS_ALTERADAS, lambda: self.painel.midias.atualizar(self.c.projeto))
        e.assinar(PROJETO_ALTERADO, lambda: self.painel.midias.atualizar(self.c.projeto))
        e.assinar(SELECAO_ALTERADA, self._ao_selecao)
        e.assinar(PROJETO_ALTERADO, self._atualizar_audio)
        e.assinar(PROJETO_CARREGADO, self._atualizar_audio)
        e.assinar(PROJETO_ALTERADO, self._atualizar_transicoes)
        e.assinar(PROJETO_CARREGADO, self._atualizar_transicoes)
        self._atualizar_audio()
        self._atualizar_transicoes()

    def _criar_atalhos(self) -> None:
        def atalho(seq: str, fn) -> None:
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.triggered.connect(lambda _=False: fn())
            self.addAction(a)

        atalho("Ctrl+N", self.novo_projeto)
        atalho("Ctrl+O", self.abrir_projeto)
        atalho("Ctrl+S", self.salvar_projeto)
        atalho("Ctrl+Shift+S", self.salvar_projeto_como)
        atalho("Ctrl+I", self.importar_midias)
        atalho("Ctrl+Z", self.c.desfazer)
        atalho("Ctrl+Y", self.c.refazer)
        atalho("Ctrl+Shift+Z", self.c.refazer)
        atalho("S", lambda: self._tentar(self.c.dividir_selecionados_na_posicao))
        atalho("Delete", lambda: self._tentar(self.c.excluir_selecionados))
        atalho("Space", self.player.alternar_reproducao)
        atalho("Left", lambda: self.c.ir_para(self.c.posicao - 1))
        atalho("Right", lambda: self.c.ir_para(self.c.posicao + 1))
        atalho("Home", lambda: self.c.ir_para(0))
        atalho("End", lambda: self.c.ir_para(self.c.projeto.duracao_frames))
        atalho("F11", lambda: self.alternar_tela_cheia("reproducao"))
        atalho("Ctrl+F11", lambda: self.alternar_tela_cheia("interativa"))
        atalho("Esc", self._sair_tela_cheia)

    # ---- util ------------------------------------------------------------------------------------
    def _tentar(self, fn) -> None:
        try:
            fn()
        except ErroEdicao as exc:
            self._mostrar_erro(str(exc))

    def _mostrar_erro(self, texto: str) -> None:
        self.statusBar().showMessage(f"⚠ {texto}", 8000)

    def _atualizar_cabecalho(self) -> None:
        g = self.c.gerenciador
        self.cabecalho.definir_nome_projeto(g.caminho.stem if g.caminho else g.projeto.nome, g.modificado)
        self.cabecalho.habilitar("desfazer", self.c.historico.pode_desfazer())
        self.cabecalho.habilitar("refazer", self.c.historico.pode_refazer())
        motor_pronto = self.c.motor is not None and self.c.motor.disponivel()
        self.cabecalho.habilitar(
            "exportar", motor_pronto and self.c.projeto.duracao_frames > 0
            and self._tarefa_exportacao is None,
            "Exportar o vídeo com a mixagem de áudio" if motor_pronto
            else "A exportação requer o motor MLT")
        self.setWindowTitle(f"{g.caminho.stem if g.caminho else g.projeto.nome}{'*' if g.modificado else ''} — {NOME_APLICATIVO}")

    # ---- projeto ------------------------------------------------------------------------------------
    def _confirmar_descarte(self) -> bool:
        """True se pode prosseguir (salvou, descartou ou não havia alterações)."""
        if not self.c.gerenciador.modificado:
            return True
        r = QMessageBox.question(
            self, "Alterações não salvas", "O projeto tem alterações não salvas. Deseja salvá-las?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Save:
            return self.salvar_projeto()
        return True

    def novo_projeto(self) -> None:
        if self._confirmar_descarte():
            self.c.novo_projeto()

    def abrir_projeto(self) -> None:
        if not self._confirmar_descarte():
            return
        inicio = self.config.obter("diretorios.ultimo_projeto") or str(Path.home())
        arq, _ = QFileDialog.getOpenFileName(self, "Abrir projeto", inicio, EXTENSAO_PROJETO_FILTRO)
        if not arq:
            return
        self.config.definir("diretorios.ultimo_projeto", str(Path(arq).parent))
        self._abrir_caminho(Path(arq))

    def _abrir_caminho(self, caminho: Path) -> None:
        try:
            if recuperacao.existe_recuperacao(caminho):
                r = QMessageBox.question(
                    self, "Recuperação disponível",
                    "Foi encontrado um salvamento automático mais recente que o arquivo do projeto "
                    "(possível encerramento inesperado). Deseja recuperá-lo?")
                if r == QMessageBox.StandardButton.Yes:
                    self.c.adotar_projeto_recuperado(recuperacao.recuperar(caminho), caminho)
                    return
            self.c.abrir_projeto(caminho)
        except ErroMovieMaker as exc:
            _log.exception("Falha ao abrir %s", caminho)
            QMessageBox.critical(self, "Não foi possível abrir o projeto", str(exc))
            return
        self._oferecer_religacao()

    def _oferecer_religacao(self) -> None:
        ausentes = self.c.gerenciador.midias_ausentes()
        if not ausentes:
            return
        r = QMessageBox.warning(
            self, "Mídias ausentes",
            f"{len(ausentes)} mídia(s) do projeto não foram encontradas:\n\n"
            + "\n".join(f"• {m.nome}" for m in ausentes[:10]) + "\n\nDeseja localizá-las agora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        for m in ausentes:
            arq, _ = QFileDialog.getOpenFileName(self, f"Localizar '{m.nome}'", str(Path.home()), FILTRO_MIDIAS)
            if arq:
                self.c.gerenciador.religar_midia(m.id, arq)
        self.c.eventos.publicar(MIDIAS_ALTERADAS)
        self._atualizar_cabecalho()

    def salvar_projeto(self) -> bool:
        if self.c.gerenciador.caminho is None:
            return self.salvar_projeto_como()
        return self._salvar(None)

    def salvar_projeto_como(self) -> bool:
        inicio = self.config.obter("diretorios.ultimo_projeto") or str(Path.home())
        sugestao = str(Path(inicio) / f"{self.c.projeto.nome}{EXTENSAO_PROJETO}")
        arq, _ = QFileDialog.getSaveFileName(self, "Salvar projeto como", sugestao, EXTENSAO_PROJETO_FILTRO)
        if not arq:
            return False
        self.config.definir("diretorios.ultimo_projeto", str(Path(arq).parent))
        self.c.projeto.nome = Path(arq).stem
        return self._salvar(arq)

    def _salvar(self, caminho) -> bool:
        try:
            destino = self.c.salvar_projeto(caminho)
        except ErroMovieMaker as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
            return False
        recuperacao.descartar_autossalvamento(destino)
        self.statusBar().showMessage(f"Projeto salvo em {destino}", 5000)
        return True

    def _autossalvar(self) -> None:
        g = self.c.gerenciador
        if not g.modificado:
            return
        try:
            recuperacao.gravar_autossalvamento(g.projeto, g.caminho or self._caminho_sem_titulo)
        except Exception:  # noqa: BLE001 - autossalvamento nunca deve interromper o usuário
            _log.exception("Falha no autossalvamento.")

    def verificar_recuperacao_inicial(self) -> None:
        """Chamado após exibir a janela: oferece recuperar um projeto sem título."""
        try:
            if recuperacao.existe_recuperacao(self._caminho_sem_titulo):
                r = QMessageBox.question(
                    self, "Recuperar trabalho", "Foi encontrado um projeto não salvo da última sessão. Deseja recuperá-lo?")
                if r == QMessageBox.StandardButton.Yes:
                    self.c.adotar_projeto_recuperado(recuperacao.recuperar(self._caminho_sem_titulo), None)
                else:
                    recuperacao.descartar_autossalvamento(self._caminho_sem_titulo)
        except ErroMovieMaker as exc:
            _log.exception("Falha ao recuperar projeto")
            QMessageBox.warning(self, "Recuperação", str(exc))

    def _ao_projeto_carregado(self) -> None:
        self.painel.midias.atualizar(self.c.projeto)
        self.timeline.canvas.ajustar_ao_projeto()

    # ---- importação (thread separada) ---------------------------------------------------------------------
    def importar_midias(self) -> None:
        if self.c.ffmpeg is None:
            QMessageBox.warning(self, "FFmpeg ausente",
                                "O FFmpeg não foi encontrado, então não é possível analisar mídias.\n"
                                "Instale-o e defina MOVIEMAKER_FFMPEG_DIR ou adicione ao PATH.")
            return
        inicio = self.config.obter("diretorios.ultima_importacao") or str(Path.home())
        arquivos, _ = QFileDialog.getOpenFileNames(self, "Importar mídia", inicio, FILTRO_MIDIAS)
        if not arquivos:
            return
        self.config.definir("diretorios.ultima_importacao", str(Path(arquivos[0]).parent))
        self._iniciar_analise_midias(arquivos)

    def _iniciar_analise_midias(self, arquivos: list[str], adicionar_na_timeline: bool = False) -> None:
        if not arquivos:
            return
        if self.c.ffmpeg is None:
            self._mostrar_erro("FFmpeg ausente: não é possível analisar o áudio.")
            return
        tarefa = TarefaAnaliseMidias(self.c.ffmpeg, arquivos, self.c.projeto.config.fps, self)
        tarefa.midia_pronta.connect(
            lambda midia, auto=adicionar_na_timeline: self._registrar_midia_analisada(midia, auto))
        tarefa.falha.connect(self._erros_importacao.append)
        tarefa.finished.connect(lambda t=tarefa: self._fim_importacao(t))
        self._tarefas.append(tarefa)
        self.statusBar().showMessage(f"Analisando {len(arquivos)} arquivo(s)…")
        tarefa.start()

    def _registrar_midia_analisada(self, midia, adicionar_na_timeline: bool) -> None:
        self.c.registrar_midia(midia)
        if adicionar_na_timeline:
            self._tentar(lambda: self.c.adicionar_midia_na_timeline(
                midia.id, criar_faixa_se_necessario=True))

    def _importar_audio(self) -> None:
        if self.c.ffmpeg is None:
            QMessageBox.warning(self, "FFmpeg ausente", "O FFmpeg é necessário para importar áudio.")
            return
        inicio = self.config.obter("diretorios.ultima_importacao") or str(Path.home())
        filtro = "Arquivos de áudio ({})".format(" ".join(f"*{e}" for e in EXTENSOES_AUDIO))
        arquivos, _ = QFileDialog.getOpenFileNames(self, "Adicionar áudio", inicio, filtro)
        if arquivos:
            self.config.definir("diretorios.ultima_importacao", str(Path(arquivos[0]).parent))
            self._iniciar_analise_midias(arquivos, adicionar_na_timeline=True)

    def _fim_importacao(self, tarefa: TarefaAnaliseMidias) -> None:
        self._tarefas.remove(tarefa)
        tarefa.deleteLater()
        if self._tarefas:
            return
        self.statusBar().clearMessage()
        if self._erros_importacao:
            QMessageBox.warning(self, "Alguns arquivos não foram importados", "\n".join(self._erros_importacao))
            self._erros_importacao.clear()

    def _adicionar_midia(self, midia_id: str) -> None:
        self._tentar(lambda: self.c.adicionar_midia_na_timeline(midia_id))

    def _atualizar_audio(self) -> None:
        mixagem = self.c.projeto.mixagem_audio
        self.painel.audio.definir_mixagem(
            mixagem.volume_original, mixagem.volume_adicionado)

    def _atualizar_transicoes(self) -> None:
        self.painel.transicoes.atualizar(self.c.projeto)

    # ---- painéis ---------------------------------------------------------------------------------------------
    def _sincronizar_menu_com_layout(self) -> None:
        e = self.layouts.estado
        self.painel.mostrar_categoria(e.categoria_ativa)
        self.menu.marcar(e.categoria_ativa if e.painel_aberto else None)
        self.painel.ajustes.selecionar_layout(self.layouts.layout_id)

    def _ao_clicar_categoria(self, categoria: str) -> None:
        e = self.layouts.estado
        if self.painel.isVisible() and e.categoria_ativa == categoria:
            self._fechar_painel()
            return
        self.painel.mostrar_categoria(categoria)
        self.layouts.definir_painel_aberto(True, categoria)
        self.menu.marcar(categoria)
        self.layouts.adaptado and self._mostrar_erro("Janela estreita: aumente-a para exibir o painel lateral.")

    def _fechar_painel(self) -> None:
        self.layouts.definir_painel_aberto(False)
        self.menu.marcar(None)

    def _trocar_layout(self, layout_id: str) -> None:
        self.layouts.aplicar(layout_id)          # não fecha projeto nem descarta alterações
        self._sincronizar_menu_com_layout()

    def _alterar_inatividade(self, segundos: int) -> None:
        self.config.definir("interface.inatividade_propriedades_s", segundos)
        self.propriedades.definir_inatividade(segundos)

    def _reposicionar_propriedades(self) -> None:
        self.propriedades.posicionar(10, 10)

    def _ao_selecao(self) -> None:
        ids = list(self.c.selecao.ids)
        if ids:
            self.propriedades.mostrar_para(self.c.projeto, ids)
        else:
            self.propriedades.atualizar(self.c.projeto, [])

    def _abrir_propriedades(self) -> None:
        self.propriedades.mostrar_para(self.c.projeto, list(self.c.selecao.ids))

    def _acao_cabecalho(self, id_: str) -> None:
        {
            "novo": self.novo_projeto,
            "abrir": self.abrir_projeto,
            "salvar": self.salvar_projeto,
            "importar": self.importar_midias,
            "desfazer": self.c.desfazer,
            "refazer": self.c.refazer,
            "configuracoes": lambda: self._ao_clicar_categoria("ajustes"),
            "exportar": self.exportar_video,
        }[id_]()

    def exportar_video(self) -> None:
        if self._tarefa_exportacao is not None:
            return
        if self.c.motor is None or not self.c.motor.disponivel():
            QMessageBox.warning(self, "Exportação indisponível", "A exportação requer o motor MLT.")
            return
        inicio = self.config.obter("diretorios.ultima_exportacao") or str(Path.home())
        sugestao = str(Path(inicio) / f"{self.c.projeto.nome}.mp4")
        destino, _ = QFileDialog.getSaveFileName(self, "Exportar vídeo", sugestao, "Vídeo MP4 (*.mp4)")
        if not destino:
            return
        if not destino.lower().endswith(".mp4"):
            destino += ".mp4"
        self.config.definir("diretorios.ultima_exportacao", str(Path(destino).parent))
        self.player.pausar()
        opcoes = {"vcodec": "libx264", "acodec": "aac", "preset": "medium", "crf": 18,
                   "ar": self.c.projeto.config.taxa_amostragem,
                   "ac": self.c.projeto.config.canais}
        tarefa = TarefaExportacao(self.c.motor, destino, opcoes, self)
        tarefa.sucesso.connect(self._exportacao_concluida)
        tarefa.falha.connect(self._exportacao_falhou)
        tarefa.finished.connect(lambda: tarefa.deleteLater())
        self._tarefa_exportacao = tarefa
        self.statusBar().showMessage("Exportando vídeo e mixando o áudio…")
        self._atualizar_cabecalho()
        tarefa.start()

    def _exportacao_concluida(self, destino: str) -> None:
        self._tarefa_exportacao = None
        self.statusBar().showMessage(f"Vídeo exportado para {destino}", 8000)
        self._atualizar_cabecalho()

    def _exportacao_falhou(self, mensagem: str) -> None:
        self._tarefa_exportacao = None
        QMessageBox.critical(self, "Falha na exportação", mensagem)
        self._atualizar_cabecalho()

    # ---- tela cheia (19.13) ------------------------------------------------------------------------------------------
    def alternar_tela_cheia(self, modo: str) -> None:
        if self._modo_tela_cheia == modo:
            self._sair_tela_cheia()
        elif self._modo_tela_cheia is None:
            self._entrar_tela_cheia(modo)

    def _entrar_tela_cheia(self, modo: str) -> None:
        self._estado_antes_tc = {
            "maximizada": self.isMaximized(),
            "cabecalho": self.cabecalho.isVisible(), "menu": self.menu.isVisible(),
            "painel": self.painel.isVisible(), "timeline": self.timeline.isVisible(),
            "status": self.statusBar().isVisible(),
        }
        self._modo_tela_cheia = modo
        self.cabecalho.hide()
        self.menu.hide()
        self.painel.hide()
        self.statusBar().hide()
        if modo == "reproducao":
            self.timeline.hide()
            self.player.controles.show()
            self._timer_controles.start()
        self.showFullScreen()

    def _sair_tela_cheia(self) -> None:
        if self._modo_tela_cheia is None:
            return
        s = self._estado_antes_tc
        self._modo_tela_cheia = None
        self._timer_controles.stop()
        self.player.controles.show()
        self.cabecalho.setVisible(s["cabecalho"])
        self.menu.setVisible(s["menu"])
        self.timeline.setVisible(s["timeline"])
        self.statusBar().setVisible(s["status"])
        self.painel.setVisible(s["painel"])
        self.showMaximized() if s["maximizada"] else self.showNormal()
        self.layouts.reaplicar_estado()           # restaura o layout principal sem perda de estado

    def _ocultar_controles_tela_cheia(self) -> None:
        if self._modo_tela_cheia == "reproducao":
            self.player.controles.hide()

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if self._modo_tela_cheia == "reproducao" and ev.type() == QEvent.Type.MouseMove:
            self.player.controles.show()
            self._timer_controles.start()
        return super().eventFilter(obj, ev)

    # ---- janela -----------------------------------------------------------------------------------------------------------
    def mostrar(self) -> None:
        self.showMaximized()
        self.layouts.reaplicar_estado()
        QTimer.singleShot(200, self.verificar_recuperacao_inicial)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        if hasattr(self, "layouts") and self._modo_tela_cheia is None:
            self.layouts.adaptar_ao_tamanho(self.width())

    def _restaurar_geometria(self) -> None:
        hexa = self.config.obter("interface.geometria_janela")
        if hexa:
            try:
                self.restoreGeometry(QByteArray.fromHex(hexa.encode("ascii")))
            except Exception:  # noqa: BLE001 - geometria inválida usa o tamanho padrão
                _log.warning("Geometria da janela inválida; usando padrão.")

    def closeEvent(self, ev) -> None:  # noqa: N802
        if not self._confirmar_descarte():
            ev.ignore()
            return
        for t in list(self._tarefas):
            t.requestInterruption()
            t.wait(3000)
        self.painel.audio.parar_gravacao()
        if self._tarefa_exportacao is not None and self._tarefa_exportacao.isRunning():
            QMessageBox.information(
                self, "Exportação em andamento", "Aguarde a exportação terminar antes de fechar o programa.")
            ev.ignore()
            return
        try:
            if self._modo_tela_cheia is None:
                self.config.definir("interface.geometria_janela", bytes(self.saveGeometry().toHex()).decode("ascii"))
            self.layouts.salvar()
            recuperacao.descartar_autossalvamento(self._caminho_sem_titulo)
            if self.c.gerenciador.caminho:
                recuperacao.descartar_autossalvamento(self.c.gerenciador.caminho)
        except Exception:  # noqa: BLE001 - não impedir o fechamento
            _log.exception("Erro ao finalizar a janela.")
        self.c.encerrar()
        ev.accept()
