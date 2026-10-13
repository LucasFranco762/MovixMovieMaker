"""Controlador central: une modelo, comandos, projeto e motor, sem depender de Qt.

A interface chama métodos deste controlador e escuta eventos do barramento.
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.configuracoes import Configuracoes
from core.constantes import FAIXA_VIDEO, TIPOS_EFEITO, TIPO_LEGENDA, TIPO_TEXTO
from core.eventos import (
    BarramentoEventos, MIDIAS_ALTERADAS, POSICAO_ALTERADA, PROJETO_ALTERADO,
    PROJETO_CARREGADO, PROJETO_SALVO, SELECAO_ALTERADA,
)
from core.excecoes import ErroEdicao
from editor.clipes import criar_clipe
from editor.comandos import (
    AdicionarClipe, AdicionarFaixa, AdicionarTransicao, AlterarClipe, AlterarElementoTexto, AlterarFaixa,
    AlterarMixagemAudio, Comando, DividirClipe, HistoricoComandos, MoverClipe,
    RemoverClipe, RemoverTransicao,
)
from editor.faixas import criar_faixa, encontrar_sobreposicao
from editor.legendas import gerar_srt, interpretar_srt
from editor.selecao import Selecao
from multimidia.metadados import analisar_midia
from multimidia.motor_base import MotorMultimidia
from multimidia.motor_ffmpeg import MotorFFmpeg
from projetos.gerenciamento import GerenciadorProjetos
from projetos.modelos import Clipe, Faixa, MidiaRef, Projeto, Transicao, novo_id

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

    def adicionar_midia_na_timeline(self, midia_id: str, inicio: int | None = None,
                                    criar_faixa_se_necessario: bool = False) -> None:
        midia = self.projeto.midias[midia_id]
        inicio = self.posicao if inicio is None else inicio
        for faixa in self.projeto.faixas:
            if faixa.aceita(midia.tipo) and not faixa.bloqueada:
                try:
                    self.executar(AdicionarClipe(faixa.id, criar_clipe(midia, inicio)))
                    return
                except ErroEdicao:
                    continue            # tenta a próxima faixa compatível
        if criar_faixa_se_necessario:
            tipo_faixa = "audio" if midia.tipo == "audio" else "video"
            faixa = criar_faixa(self.projeto, tipo_faixa)
            self.executar(AdicionarFaixa(faixa))
            self.executar(AdicionarClipe(faixa.id, criar_clipe(midia, inicio)))
            return
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

    def remover_clipe(self, clipe_id: str) -> None:
        self.executar(RemoverClipe(clipe_id))

    def mover_clipe(self, clipe_id: str, novo_inicio: int, faixa_id: str | None = None) -> None:
        self.executar(MoverClipe(clipe_id, novo_inicio, faixa_id))

    def alterar_clipe(self, clipe_id: str, **alteracoes: object) -> None:
        self.executar(AlterarClipe(clipe_id, **alteracoes))

    def alterar_faixa(self, faixa_id: str, **alteracoes: object) -> None:
        self.executar(AlterarFaixa(faixa_id, **alteracoes))

    def salvar_elemento_texto(self, tipo: str, conteudo: str, duracao_segundos: float,
                              familia_fonte: str, tamanho_fonte: int, cor_texto: str,
                              cor_fundo_texto: str, alinhamento_h: str,
                              alinhamento_v: str, clipe_id: str | None = None,
                              inicio_frame: int | None = None) -> Clipe:
        if tipo not in (TIPO_TEXTO, TIPO_LEGENDA):
            raise ErroEdicao(f"Tipo de elemento textual inválido: {tipo!r}.")
        conteudo = conteudo.strip()
        if not conteudo:
            raise ErroEdicao("Digite o conteúdo do texto.")
        duracao = max(1, round(float(duracao_segundos) * float(self.projeto.config.fps)))
        propriedades = dict(
            conteudo=conteudo, duracao=duracao, familia_fonte=familia_fonte or "Segoe UI",
            tamanho_fonte=tamanho_fonte, cor_texto=cor_texto,
            cor_fundo_texto=cor_fundo_texto, alinhamento_h=alinhamento_h,
            alinhamento_v=alinhamento_v,
        )
        if clipe_id is not None:
            self.executar(AlterarElementoTexto(clipe_id, **propriedades))
            return self.projeto.localizar_clipe(clipe_id)[1]

        clipe = Clipe(
            id=novo_id(), midia_id="", tipo=tipo,
            inicio=self.posicao if inicio_frame is None else max(0, int(inicio_frame)),
            nome=conteudo[:40],
            **propriedades,
        )
        # Textos ficam em faixas próprias de sobreposição. Isso preserva a faixa
        # de vídeo principal mesmo quando o usuário cria a legenda antes de
        # importar o primeiro vídeo.
        faixa = next((f for f in reversed(self.projeto.faixas)
                      if f.tipo == FAIXA_VIDEO and not f.bloqueada and f.clipes
                      and all(item.tipo == tipo for item in f.clipes)
                      and encontrar_sobreposicao(f, clipe.inicio, clipe.duracao) is None), None)
        if faixa is None:
            faixa = criar_faixa(self.projeto, FAIXA_VIDEO)
            faixa.nome = "Textos" if tipo == TIPO_TEXTO else "Legendas"
            self.executar(AdicionarFaixa(faixa))
        self.executar(AdicionarClipe(faixa.id, clipe))
        self.selecionar([clipe.id])
        return clipe

    def remover_elemento_texto(self, clipe_id: str) -> None:
        _, clipe = self.projeto.localizar_clipe(clipe_id)
        if clipe.tipo not in (TIPO_TEXTO, TIPO_LEGENDA):
            raise ErroEdicao("O item escolhido não é um texto ou legenda.")
        self.executar(RemoverClipe(clipe_id))

    def importar_legendas_srt(self, caminho: str | Path) -> int:
        try:
            blocos = interpretar_srt(Path(caminho).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ErroEdicao(f"Não foi possível importar as legendas: {exc}") from exc
        fps = float(self.projeto.config.fps)
        for inicio_ms, fim_ms, conteudo in blocos:
            self.salvar_elemento_texto(
                tipo=TIPO_LEGENDA, conteudo=conteudo,
                duracao_segundos=(fim_ms - inicio_ms) / 1000,
                familia_fonte="Segoe UI", tamanho_fonte=48,
                cor_texto="#ffffff", cor_fundo_texto="#99000000",
                alinhamento_h="center", alinhamento_v="bottom",
                inicio_frame=round(inicio_ms * fps / 1000),
            )
        return len(blocos)

    def exportar_legendas_srt(self, caminho: str | Path) -> int:
        legendas = [c for f in self.projeto.faixas for c in f.clipes
                    if c.tipo == TIPO_LEGENDA]
        try:
            Path(caminho).write_text(
                gerar_srt(legendas, self.projeto.config.fps), encoding="utf-8-sig")
        except OSError as exc:
            raise ErroEdicao(f"Não foi possível exportar as legendas: {exc}") from exc
        return len(legendas)

    def configurar_mixagem_audio(self, volume_original: float, volume_adicionado: float) -> None:
        atual = self.projeto.mixagem_audio
        original = max(0.0, min(2.0, float(volume_original)))
        adicionado = max(0.0, min(2.0, float(volume_adicionado)))
        if (original, adicionado) != (atual.volume_original, atual.volume_adicionado):
            self.executar(AlterarMixagemAudio(
                volume_original=original, volume_adicionado=adicionado))

    def aplicar_efeito(self, tipo: str, intensidade: int = 100) -> None:
        if tipo not in TIPOS_EFEITO:
            raise ErroEdicao(f"Efeito visual desconhecido: {tipo!r}.")
        intensidade = max(0, min(100, int(intensidade)))
        clipe = self._clipe_visual_selecionado()
        efeitos = dict(clipe.efeitos)
        if efeitos.get(tipo) == intensidade:
            raise ErroEdicao("Esse efeito já está aplicado com essa intensidade.")
        efeitos[tipo] = intensidade
        self.executar(AlterarClipe(clipe.id, efeitos=efeitos))

    def remover_efeito(self, tipo: str) -> None:
        clipe = self._clipe_visual_selecionado()
        if tipo not in clipe.efeitos:
            raise ErroEdicao("O efeito selecionado não está aplicado a este clipe.")
        efeitos = dict(clipe.efeitos)
        del efeitos[tipo]
        self.executar(AlterarClipe(clipe.id, efeitos=efeitos))

    def _clipe_visual_selecionado(self) -> Clipe:
        if len(self.selecao.ids) != 1:
            raise ErroEdicao("Selecione somente um clipe visual para editar seus efeitos.")
        try:
            faixa, clipe = self.projeto.localizar_clipe(self.selecao.ids[0])
        except KeyError as exc:
            raise ErroEdicao("O clipe selecionado não foi encontrado.") from exc
        if faixa.tipo != "video":
            raise ErroEdicao("Efeitos visuais não podem ser aplicados a clipes de áudio.")
        return clipe

    def aplicar_transicao(self, tipo: str, duracao_segundos: float) -> Transicao:
        faixa, origem, destino = self._clipes_para_transicao()
        duracao = max(1, round(float(duracao_segundos) * float(self.projeto.config.fps)))
        transicao = Transicao(
            id=novo_id(), faixa_id=faixa.id,
            clipe_origem_id=origem.id, clipe_destino_id=destino.id,
            tipo=tipo, duracao=duracao,
        )
        self.executar(AdicionarTransicao(transicao))
        return transicao

    def remover_transicao(self, transicao_id: str) -> None:
        self.executar(RemoverTransicao(transicao_id))

    def _clipes_para_transicao(self) -> tuple[Faixa, Clipe, Clipe]:
        selecionados: list[tuple[Faixa, Clipe]] = []
        for clipe_id in self.selecao.ids:
            try:
                selecionados.append(self.projeto.localizar_clipe(clipe_id))
            except KeyError:
                continue
        if len(selecionados) == 2:
            if selecionados[0][0].id != selecionados[1][0].id:
                raise ErroEdicao("Os dois clipes selecionados precisam estar na mesma faixa.")
            faixa = selecionados[0][0]
            clipes = sorted((selecionados[0][1], selecionados[1][1]), key=lambda c: c.inicio)
            return faixa, clipes[0], clipes[1]
        if len(selecionados) > 2:
            raise ErroEdicao("Selecione somente os dois clipes que receberão a transição.")

        for faixa in self.projeto.faixas:
            if faixa.tipo != "video":
                continue
            clipes = sorted(faixa.clipes, key=lambda c: c.inicio)
            for origem, destino in zip(clipes, clipes[1:]):
                if origem.fim == self.posicao == destino.inicio:
                    return faixa, origem, destino
        raise ErroEdicao(
            "Selecione dois clipes de vídeo consecutivos ou posicione o cursor exatamente no corte.")

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
