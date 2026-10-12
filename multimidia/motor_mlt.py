"""Integração centralizada com o MLT Framework (REQ-004).

STATUS: IMPLEMENTADO, NÃO VALIDADO. Este módulo foi escrito sem acesso a um
MLT funcional (o ambiente de desenvolvimento não é o Windows de destino).
Os nomes de API seguem os bindings Python oficiais (``mlt7``). Valide com
``python ferramentas/prova_conceito.py`` no Windows antes de depender dele.

A composição é construída SEMPRE a partir do modelo ``Projeto`` — a mesma
construção serve para pré-visualização e exportação (REQ-004, 6.2).
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from core.excecoes import DependenciaAusenteError, ErroExportacao, ErroMultimidia
from multimidia.motor_base import FrameRGBA, MotorMultimidia
from projetos.modelos import Projeto

_log = logging.getLogger(__name__)

_NOMES_MODULO = ("mlt7", "mlt")      # MLT 7 usa 'mlt7'; versões antigas, 'mlt'


def importar_mlt() -> Any:
    erros = []
    for nome in _NOMES_MODULO:
        try:
            return importlib.import_module(nome)
        except ImportError as exc:
            erros.append(f"{nome}: {exc}")
    raise DependenciaAusenteError(
        "Os bindings Python do MLT não foram encontrados (" + "; ".join(erros) + "). "
        "Consulte docs/INSTALACAO_MLT_WINDOWS.md."
    )


class MotorMLT(MotorMultimidia):
    def __init__(self) -> None:
        self._mlt: Any = None
        self._perfil: Any = None
        self._tractor: Any = None
        self._consumidor: Any = None
        self._projeto: Projeto | None = None
        self._erro: str = ""
        try:
            self._mlt = importar_mlt()
            self._mlt.Factory.init()
        except (DependenciaAusenteError, Exception) as exc:  # noqa: BLE001 - registra e informa
            self._erro = str(exc)
            self._mlt = None
            _log.warning("MLT indisponível: %s", exc)

    def disponivel(self) -> bool:
        return self._mlt is not None

    def descricao(self) -> str:
        return "MLT pronto (não validado)" if self.disponivel() else f"MLT indisponível: {self._erro}"

    # ---- construção da composição ---------------------------------------------
    def _criar_perfil(self, projeto: Projeto) -> Any:
        c = projeto.config
        perfil = self._mlt.Profile()
        perfil.set_width(c.largura)
        perfil.set_height(c.altura)
        perfil.set_frame_rate(c.fps_num, c.fps_den)
        perfil.set_sample_aspect(1, 1)
        perfil.set_progressive(1)
        perfil.set_colorspace(709)
        return perfil

    def carregar(self, projeto: Projeto) -> None:
        if not self.disponivel():
            raise DependenciaAusenteError(self._erro)
        mlt = self._mlt
        self._projeto = projeto
        self._perfil = self._criar_perfil(projeto)
        tractor = mlt.Tractor(self._perfil)
        multitrack = tractor.multitrack()
        indice = 0
        for faixa in projeto.faixas:
            playlist = mlt.Playlist(self._perfil)
            cursor = 0
            for clipe in sorted(faixa.clipes, key=lambda c: c.inicio):
                if clipe.inicio > cursor:
                    playlist.blank(clipe.inicio - cursor - 1)   # blank(n) = n+1 frames
                midia = projeto.midias.get(clipe.midia_id)
                if midia is None:
                    raise ErroMultimidia(f"Mídia do clipe '{clipe.nome}' não está no projeto.")
                produtor = mlt.Producer(self._perfil, midia.caminho)
                if not produtor.is_valid():
                    raise ErroMultimidia(f"O MLT não conseguiu abrir '{midia.nome}'.")
                # in/out do MLT são inclusivos
                playlist.append(produtor, clipe.entrada, clipe.entrada + clipe.duracao - 1)
                cursor = clipe.fim
            multitrack.connect(playlist, indice)
            if faixa.tipo == "video" and not faixa.visivel:
                playlist.set("hide", 1)       # 1 = oculta vídeo
            if faixa.tipo == "audio" and faixa.silenciada:
                playlist.set("hide", 2)       # 2 = silencia áudio
            indice += 1
        self._tractor = tractor
        # Transições de composição entre faixas (mix/composite) serão adicionadas
        # na Etapa 5; hoje não há transições no modelo.

    # ---- pré-visualização --------------------------------------------------------
    def obter_frame(self, posicao: int) -> FrameRGBA | None:
        if self._tractor is None:
            return None
        mlt = self._mlt
        self._tractor.seek(posicao)
        frame = self._tractor.get_frame()
        largura = self._projeto.config.largura if self._projeto else 0
        altura = self._projeto.config.altura if self._projeto else 0
        # get_image devolve bytes RGBA no formato pedido; assinatura pode variar
        # entre versões dos bindings — validar na prova de conceito.
        imagem = frame.get_image(mlt.mlt_image_format.mlt_image_rgba, largura, altura)
        return FrameRGBA(largura, altura, bytes(imagem))

    # ---- exportação ---------------------------------------------------------------
    def exportar(self, destino: str, **opcoes: object) -> None:
        if self._tractor is None:
            raise ErroExportacao("Nenhuma composição carregada para exportar.")
        mlt = self._mlt
        consumidor = mlt.Consumer(self._perfil, "avformat", destino)
        if not consumidor.is_valid():
            raise ErroExportacao("O MLT não conseguiu criar o consumidor de exportação (avformat).")
        for chave, valor in opcoes.items():
            consumidor.set(chave, str(valor))
        consumidor.connect(self._tractor)
        consumidor.run()            # bloqueante: chamar SEMPRE fora da thread da interface
        consumidor.stop()

    def encerrar(self) -> None:
        self._tractor = None
        self._consumidor = None
        self._perfil = None
        if self._mlt is not None:
            try:
                self._mlt.Factory.close()
            except Exception:  # noqa: BLE001
                _log.exception("Erro ao encerrar a fábrica do MLT.")
