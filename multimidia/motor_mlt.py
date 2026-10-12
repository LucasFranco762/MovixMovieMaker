"""Integração centralizada com o MLT Framework (REQ-004).

STATUS: IMPLEMENTADO E VALIDADO no Windows com MLT 7.40.0 e Python 3.13.
Os bindings oficiais ``mlt7`` foram compilados via SWIG para a venv do projeto.

A composição é construída SEMPRE a partir do modelo ``Projeto`` — a mesma
construção serve para pré-visualização e exportação (REQ-004, 6.2).
"""
from __future__ import annotations

import importlib
import logging
import math
import os
from pathlib import Path
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


def inicializar_mlt(mlt: Any) -> None:
    """Inicializa a fábrica usando explicitamente o repositório no Windows."""
    repositorio = os.environ.get("MLT_REPOSITORY", "").strip()
    if repositorio and Path(repositorio).is_dir():
        mlt.Factory.init(repositorio)
    else:
        mlt.Factory.init()


def formato_imagem_rgba(mlt: Any) -> Any:
    """Retorna o enum RGBA nas formas usadas por bindings MLT antigos e atuais."""
    enum = getattr(mlt, "mlt_image_format", None)
    return getattr(enum, "mlt_image_rgba", None) if enum is not None else mlt.mlt_image_rgba


class MotorMLT(MotorMultimidia):
    def __init__(self) -> None:
        self._mlt: Any = None
        self._perfil: Any = None
        self._tractor: Any = None
        self._consumidor: Any = None
        self._transicoes: list[Any] = []
        self._projeto: Projeto | None = None
        self._erro: str = ""
        try:
            self._mlt = importar_mlt()
            inicializar_mlt(self._mlt)
        except (DependenciaAusenteError, Exception) as exc:  # noqa: BLE001 - registra e informa
            self._erro = str(exc)
            self._mlt = None
            _log.warning("MLT indisponível: %s", exc)

    def disponivel(self) -> bool:
        return self._mlt is not None

    def descricao(self) -> str:
        return "MLT pronto" if self.disponivel() else f"MLT indisponível: {self._erro}"

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
        self._transicoes = []
        for faixa in projeto.faixas:
            playlist = mlt.Playlist(self._perfil)
            cursor = 0
            indices_clipes: dict[str, int] = {}
            for clipe in sorted(faixa.clipes, key=lambda c: c.inicio):
                if clipe.inicio > cursor:
                    playlist.blank(clipe.inicio - cursor - 1)   # blank(n) = n+1 frames
                midia = projeto.midias.get(clipe.midia_id)
                if midia is None:
                    raise ErroMultimidia(f"Mídia do clipe '{clipe.nome}' não está no projeto.")
                produtor = mlt.Producer(self._perfil, midia.caminho)
                if not produtor.is_valid():
                    raise ErroMultimidia(f"O MLT não conseguiu abrir '{midia.nome}'.")
                if midia.tem_audio:
                    if midia.tipo == "video":
                        ganho = projeto.mixagem_audio.volume_original * clipe.volume
                    else:
                        ganho = projeto.mixagem_audio.volume_adicionado * faixa.volume * clipe.volume
                    filtro_volume = mlt.Filter(self._perfil, "volume")
                    if filtro_volume.is_valid():
                        # O parâmetro atual do MLT é expresso em dB, enquanto a
                        # interface usa ganho linear (100% = 1.0).
                        nivel_db = -100.0 if ganho <= 0 else 20.0 * math.log10(ganho)
                        filtro_volume.set("level", f"{nivel_db:.4f}")
                        produtor.attach(filtro_volume)
                # in/out do MLT são inclusivos
                indices_clipes[clipe.id] = playlist.count()
                playlist.append(produtor, clipe.entrada, clipe.entrada + clipe.duracao - 1)
                cursor = clipe.fim

            transicoes_faixa = [t for t in projeto.transicoes if t.faixa_id == faixa.id]
            transicoes_faixa.sort(
                key=lambda t: indices_clipes.get(t.clipe_origem_id, -1), reverse=True)
            for transicao_modelo in transicoes_faixa:
                indice_clipe = indices_clipes.get(transicao_modelo.clipe_origem_id)
                if indice_clipe is None:
                    raise ErroMultimidia("A transição referencia um clipe ausente da composição.")
                transicao_mlt = mlt.Transition(self._perfil, "luma")
                if not transicao_mlt.is_valid():
                    raise ErroMultimidia("O MLT não disponibilizou a transição 'luma'.")
                resultado = playlist.mix(indice_clipe, transicao_modelo.duracao, transicao_mlt)
                if resultado != 0:
                    raise ErroMultimidia("O MLT não conseguiu aplicar a transição entre os clipes.")
                self._transicoes.append(transicao_mlt)
            multitrack.connect(playlist, indice)
            ocultar = 0
            if faixa.tipo == "video" and not faixa.visivel:
                ocultar |= 1                  # 1 = oculta vídeo
            if faixa.tipo == "video" and projeto.mixagem_audio.volume_original <= 0:
                ocultar |= 2                  # preserva vídeo, remove exatamente seu áudio
            if faixa.tipo == "audio" and (
                    faixa.silenciada or faixa.volume <= 0
                    or projeto.mixagem_audio.volume_adicionado <= 0):
                ocultar |= 2                  # 2 = silencia áudio
            if ocultar:
                playlist.set("hide", ocultar)
            indice += 1
        self._tractor = tractor
        # Combina simultaneamente o som original dos vídeos com música, voz e
        # quaisquer outras faixas de áudio adicionadas pelo usuário.
        for faixa_indice in range(1, indice):
            transicao = mlt.Transition(self._perfil, "mix")
            if transicao.is_valid():
                transicao.set("always_active", "1")
                transicao.set("sum", "1")
                tractor.plant_transition(transicao, 0, faixa_indice)
                self._transicoes.append(transicao)

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
        imagem = frame.get_image(formato_imagem_rgba(mlt), largura, altura)
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
        self._transicoes = []
        self._perfil = None
        if self._mlt is not None:
            try:
                self._mlt.Factory.close()
            except Exception:  # noqa: BLE001
                _log.exception("Erro ao encerrar a fábrica do MLT.")
