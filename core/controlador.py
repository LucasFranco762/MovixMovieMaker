"""Controlador central: une modelo, comandos, projeto e motor, sem depender de Qt.

A interface chama métodos deste controlador e escuta eventos do barramento.
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.configuracoes import Configuracoes
from core.eventos import (
    BarramentoEventos, MIDIAS_ALTERADAS, POSICAO_ALTERADA, PROJETO_ALTERADO,
    PROJETO_CARREGADO, PROJETO_SALVO, SELECAO_ALTERADA,
)
from core.excecoes import ErroEdicao
from editor.clipes import criar_clipe
from editor.comandos import (
    AdicionarClipe, AdicionarFaixa, AlterarClipe, AlterarFaixa, Comando,
    DividirClipe, HistoricoComandos, MoverClipe, RemoverClipe,
)
from editor.faixas import criar_faixa
from editor.selecao import Selecao
from multimidia.metadados import analisar_midia
from multimidia.motor_base import MotorMultimidia
from multimidia.motor_ffmpeg import MotorFFmpeg
from projetos.gerenciamento import GerenciadorProjetos
from projetos.modelos import MidiaRef, Projeto

_log = logging.getLogger(__name__)


class Controlador:
    def __init__(self, config: Configuracoes, motor: MotorMultimidia | None = None,
                 ffmpeg: MotorFFmpeg | None = None) -> None:
        self.config = config
        self.eventos = BarramentoEventos()
        self.gerenciador = GerenciadorProjetos(config)
        self.historico = HistoricoComandos()
        self.selecao = Selecao()
        self.motor = motor
        self.ffmpeg = ffmpeg
        self.posicao = 0                      # cursor de reprodução, em frames

    @property
    def projeto(self) -> Projeto:
        return self.gerenciador.projeto

    # ---- projeto ----------------------------------------------------------------------
    def novo_projeto(self) -> None:
        self.gerenciador.novo()
        self._reiniciar_estado()

    def abrir_projeto(self, caminho: str | Path) -> None:
        self.gerenciador.abrir(caminho)
        self._reiniciar_estado()

    def adotar_projeto_recuperado(self, projeto: Projeto, caminho: Path | None) -> None:
        """Substitui o projeto aberto por um recuperado de autossalvamento (marcado como modificado)."""
        self.gerenciador.projeto = projeto
        self.gerenciador.caminho = caminho
        self._reiniciar_estado()
        self.gerenciador.modificado = True

    def salvar_projeto(self, caminho: str | Path | None = None) -> Path:
        destino = self.gerenciador.salvar(caminho)
        self.eventos.publicar(PROJETO_SALVO, destino)
        return destino

    def _reiniciar_estado(self) -> None:
        self.historico.limpar()
        self.selecao.limpar()
        self.posicao = 0
        self._recarregar_motor()
        self.eventos.publicar(PROJETO_CARREGADO)

    def _recarregar_motor(self) -> None:
        if self.motor is not None and self.motor.disponivel():
            try:
                self.motor.carregar(self.projeto)
            except Exception:  # noqa: BLE001 - falha do motor não pode derrubar a edição
                _log.exception("Falha ao carregar a composição no motor.")

    # ---- edição -------------------------------------------------------------------------
    def executar(self, comando: Comando) -> None:
        """Executa um comando validado, atualiza estado e notifica a interface."""
        self.historico.executar(self.projeto, comando)    # ErroEdicao se inválido
        self._apos_alteracao()

    def desfazer(self) -> None:
        if self.historico.desfazer(self.projeto):
            self._apos_alteracao()

    def refazer(self) -> None:
        if self.historico.refazer(self.projeto):
            self._apos_alteracao()

    def _apos_alteracao(self) -> None:
        self.gerenciador.modificado = True
        self.selecao.podar(self.projeto)
        self._recarregar_motor()
        self.eventos.publicar(PROJETO_ALTERADO)
        self.eventos.publicar(SELECAO_ALTERADA)

    # ---- operações de alto nível ---------------------------------------------------------------
    def importar_midias(self, caminhos: list[str]) -> list[str]:
        """Importa arquivos para a biblioteca. Devolve mensagens de erro (pt-BR)."""
        erros: list[str] = []
        if self.ffmpeg is None:
            return ["FFmpeg não está disponível; não é possível analisar as mídias."]
        for c in caminhos:
            try:
                midia = analisar_midia(self.ffmpeg, c, self.projeto.config.fps)
            except Exception as exc:  # noqa: BLE001 - mostra ao usuário e segue com os demais
                _log.warning("Falha ao importar %s: %s", c, exc)
                erros.append(f"{Path(c).name}: {exc}")
                continue
            self.registrar_midia(midia, notificar=False)
        self.eventos.publicar(MIDIAS_ALTERADAS)
        return erros

    def registrar_midia(self, midia: MidiaRef, notificar: bool = True) -> None:
        """Adiciona uma mídia já analisada à biblioteca (chamar na thread principal)."""
        self.projeto.midias[midia.id] = midia
        self.gerenciador.modificado = True
        if notificar:
            self.eventos.publicar(MIDIAS_ALTERADAS)

    def adicionar_midia_na_timeline(self, midia_id: str, inicio: int | None = None) -> None:
        midia = self.projeto.midias[midia_id]
        inicio = self.posicao if inicio is None else inicio
        for faixa in self.projeto.faixas:
            if faixa.aceita(midia.tipo) and not faixa.bloqueada:
                try:
                    self.executar(AdicionarClipe(faixa.id, criar_clipe(midia, inicio)))
                    return
                except ErroEdicao:
                    continue            # tenta a próxima faixa compatível
        raise ErroEdicao("Nenhuma faixa compatível e livre nessa posição. Crie uma nova faixa.")

    def adicionar_faixa(self, tipo: str) -> None:
        self.executar(AdicionarFaixa(criar_faixa(self.projeto, tipo)))

    def dividir_selecionados_na_posicao(self) -> int:
        """Divide no cursor os clipes selecionados que o cruzam. Devolve quantos."""
        n = 0
        for clipe_id in list(self.selecao.ids):
            _, clipe = self.projeto.localizar_clipe(clipe_id)
            if clipe.inicio < self.posicao < clipe.fim:
                self.executar(DividirClipe(clipe_id, self.posicao))
                n += 1
        if n == 0:
            raise ErroEdicao("Selecione um clipe e posicione o cursor sobre ele para dividir.")
        return n

    def excluir_selecionados(self) -> None:
        for clipe_id in list(self.selecao.ids):
            self.executar(RemoverClipe(clipe_id))

    def mover_clipe(self, clipe_id: str, novo_inicio: int, faixa_id: str | None = None) -> None:
        self.executar(MoverClipe(clipe_id, novo_inicio, faixa_id))

    def alterar_clipe(self, clipe_id: str, **alteracoes: object) -> None:
        self.executar(AlterarClipe(clipe_id, **alteracoes))

    def alterar_faixa(self, faixa_id: str, **alteracoes: object) -> None:
        self.executar(AlterarFaixa(faixa_id, **alteracoes))

    # ---- navegação ---------------------------------------------------------------------------------
    def ir_para(self, frame: int) -> None:
        self.posicao = max(0, min(frame, max(0, self.projeto.duracao_frames)))
        self.eventos.publicar(POSICAO_ALTERADA, self.posicao)

    def selecionar(self, ids: list[str]) -> None:
        self.selecao.definir(ids)
        self.eventos.publicar(SELECAO_ALTERADA)

    def encerrar(self) -> None:
        if self.motor is not None:
            self.motor.encerrar()
        self.config.salvar()
