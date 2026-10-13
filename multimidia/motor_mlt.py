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
import tempfile
from pathlib import Path
from typing import Any

from core.constantes import (
    EFEITO_BRILHO,
    EFEITO_DESFOQUE,
    EFEITO_ESCALA_CINZA,
    EFEITO_INVERTER,
    EFEITO_SEPIA,
    NOMES_EFEITO,
    TIPO_LEGENDA,
    TIPO_TEXTO,
    TRANSICAO_DISSOLVER,
    TRANSICAO_IRIS_CIRCULAR,
    TRANSICAO_VARREDURA_DIAGONAL,
    TRANSICAO_VARREDURA_HORIZONTAL,
    TRANSICAO_VARREDURA_VERTICAL,
)
from core.excecoes import DependenciaAusenteError, ErroExportacao, ErroMultimidia
from multimidia.motor_base import FrameRGBA, MotorMultimidia
from projetos.modelos import Projeto

_log = logging.getLogger(__name__)

_NOMES_MODULO = ("mlt7", "mlt")      # MLT 7 usa 'mlt7'; versões antigas, 'mlt'

def _filtro_efeito(tipo: str, intensidade: int) -> tuple[str, dict[str, str]]:
    """Traduz a intensidade percentual em propriedades do filtro MLT."""
    fator = max(0.0, min(1.0, intensidade / 100))
    if tipo == EFEITO_ESCALA_CINZA:
        return "avfilter.hue", {"av.s": f"{1 - fator:.4f}"}
    if tipo == EFEITO_SEPIA:
        matriz_sepia = {
            "rr": .393, "rg": .769, "rb": .189,
            "gr": .349, "gg": .686, "gb": .168,
            "br": .272, "bg": .534, "bb": .131,
        }
        propriedades = {}
        for canal, alvo in matriz_sepia.items():
            identidade = 1.0 if canal[0] == canal[1] else 0.0
            propriedades[f"av.{canal}"] = f"{identidade + (alvo - identidade) * fator:.4f}"
        return "avfilter.colorchannelmixer", propriedades
    if tipo == EFEITO_INVERTER:
        expressao = f"val*{1 - fator:.4f}+(maxval-val)*{fator:.4f}"
        return "avfilter.lutrgb", {"av.r": expressao, "av.g": expressao, "av.b": expressao}
    if tipo == EFEITO_DESFOQUE:
        raio = 8 * fator
        return "box_blur", {
            "hradius": f"{raio:.2f}", "vradius": f"{raio:.2f}", "preserve_alpha": "1",
        }
    if tipo == EFEITO_BRILHO:
        return "brightness", {
            "level": f"{1 + .35 * fator:.4f}", "alpha": "1", "rgb_only": "1",
        }
    raise ValueError(f"Efeito visual desconhecido: {tipo!r}")


def _criar_mapa_luma(tipo: str, tamanho: int = 256) -> bytes:
    """Cria um mapa PGM que o transition_luma do MLT usa como máscara."""
    if tamanho < 2:
        raise ValueError("O mapa luma precisa ter ao menos 2 pixels por lado.")
    ultimo = tamanho - 1
    centro = tamanho // 2
    distancia_maxima = math.hypot(max(centro, ultimo - centro),
                                  max(centro, ultimo - centro))
    pixels = bytearray()
    for y in range(tamanho):
        for x in range(tamanho):
            if tipo == TRANSICAO_VARREDURA_HORIZONTAL:
                valor = round(255 * x / ultimo)
            elif tipo == TRANSICAO_VARREDURA_VERTICAL:
                valor = round(255 * y / ultimo)
            elif tipo == TRANSICAO_VARREDURA_DIAGONAL:
                valor = round(255 * (x + y) / (2 * ultimo))
            elif tipo == TRANSICAO_IRIS_CIRCULAR:
                valor = round(255 * math.hypot(x - centro, y - centro) / distancia_maxima)
            else:
                raise ValueError(f"Transição sem mapa luma: {tipo!r}")
            pixels.append(max(0, min(255, valor)))
    return f"P5\n{tamanho} {tamanho}\n255\n".encode("ascii") + pixels


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
    def __init__(self, _fecha_factory: bool = True) -> None:
        self._mlt: Any = None
        self._perfil: Any = None
        self._tractor: Any = None
        self._consumidor: Any = None
        self._consumidor_audio: Any = None
        self._motor_audio: MotorMLT | None = None
        self._fecha_factory = _fecha_factory
        self._transicoes: list[Any] = []
        self._filtros: list[Any] = []
        self._diretorio_lumas: tempfile.TemporaryDirectory | None = None
        self._projeto: Projeto | None = None
        self._erro: str = ""
        try:
            self._mlt = importar_mlt()
            inicializar_mlt(self._mlt)
        except (DependenciaAusenteError, Exception) as exc:  # noqa: BLE001 - registra e informa
            self._erro = str(exc)
            self._mlt = None
            _log.warning("MLT indisponível: %s", exc)

    def _recurso_luma(self, tipo: str) -> str:
        if self._diretorio_lumas is None:
            self._diretorio_lumas = tempfile.TemporaryDirectory(prefix="movix-lumas-")
        caminho = Path(self._diretorio_lumas.name) / f"{tipo}.pgm"
        if not caminho.is_file():
            caminho.write_bytes(_criar_mapa_luma(tipo))
        return str(caminho)

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
        self.parar_audio_preview()
        mlt = self._mlt
        self._projeto = projeto
        self._perfil = self._criar_perfil(projeto)
        tractor = mlt.Tractor(self._perfil)
        multitrack = tractor.multitrack()
        indice = 0
        indices_video: list[int] = []
        self._transicoes = []
        self._filtros = []
        for faixa in projeto.faixas:
            playlist = mlt.Playlist(self._perfil)
            cursor = 0
            indices_clipes: dict[str, int] = {}
            for clipe in sorted(faixa.clipes, key=lambda c: c.inicio):
                if clipe.inicio > cursor:
                    playlist.blank(clipe.inicio - cursor - 1)   # blank(n) = n+1 frames
                midia = projeto.midias.get(clipe.midia_id)
                if clipe.tipo in (TIPO_TEXTO, TIPO_LEGENDA):
                    produtor = mlt.Producer(self._perfil, "color:0x00000000")
                    produtor.set("length", clipe.duracao)
                    produtor.set("out", clipe.duracao - 1)
                    filtro_texto = mlt.Filter(self._perfil, "dynamictext")
                    if not filtro_texto.is_valid():
                        raise ErroMultimidia(
                            "O MLT não disponibilizou o renderizador de texto 'dynamictext'.")
                    for chave, valor in {
                        "argument": clipe.conteudo,
                        "geometry": "0%/0%:100%x100%:100",
                        "family": clipe.familia_fonte,
                        "size": str(clipe.tamanho_fonte),
                        "fgcolour": clipe.cor_texto,
                        "bgcolour": clipe.cor_fundo_texto,
                        "olcolour": "#000000",
                        "outline": "2",
                        "halign": clipe.alinhamento_h,
                        "valign": clipe.alinhamento_v,
                    }.items():
                        filtro_texto.set(chave, valor)
                    produtor.attach(filtro_texto)
                    self._filtros.append(filtro_texto)
                    entrada_produtor = 0
                else:
                    if midia is None:
                        raise ErroMultimidia(f"Mídia do clipe '{clipe.nome}' não está no projeto.")
                    produtor = mlt.Producer(self._perfil, midia.caminho)
                    entrada_produtor = clipe.entrada
                if not produtor.is_valid():
                    nome = midia.nome if midia is not None else clipe.nome
                    raise ErroMultimidia(f"O MLT não conseguiu abrir '{nome}'.")
                if midia is not None and midia.tem_audio:
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
                        self._filtros.append(filtro_volume)
                for tipo_efeito, intensidade in clipe.efeitos.items():
                    if intensidade <= 0:
                        continue
                    servico, propriedades = _filtro_efeito(tipo_efeito, intensidade)
                    filtro_efeito = mlt.Filter(self._perfil, servico)
                    if not filtro_efeito.is_valid():
                        nome = NOMES_EFEITO.get(tipo_efeito, tipo_efeito)
                        raise ErroMultimidia(f"O MLT não disponibilizou o efeito '{nome}'.")
                    for chave, valor in propriedades.items():
                        filtro_efeito.set(chave, valor)
                    produtor.attach(filtro_efeito)
                    self._filtros.append(filtro_efeito)
                # in/out do MLT são inclusivos
                indices_clipes[clipe.id] = playlist.count()
                playlist.append(produtor, entrada_produtor, entrada_produtor + clipe.duracao - 1)
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
                if transicao_modelo.tipo != TRANSICAO_DISSOLVER:
                    transicao_mlt.set("resource", self._recurso_luma(transicao_modelo.tipo))
                    transicao_mlt.set("softness", "0.15")
                resultado = playlist.mix(indice_clipe, transicao_modelo.duracao, transicao_mlt)
                if resultado != 0:
                    raise ErroMultimidia("O MLT não conseguiu aplicar a transição entre os clipes.")
                self._transicoes.append(transicao_mlt)
            multitrack.connect(playlist, indice)
            if faixa.tipo == "video":
                indices_video.append(indice)
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
        for faixa_indice in indices_video[1:]:
            composicao = mlt.Transition(self._perfil, "composite")
            if not composicao.is_valid():
                raise ErroMultimidia(
                    "O MLT não disponibilizou a composição de textos 'composite'.")
            composicao.set("always_active", "1")
            composicao.set("progressive", "1")
            composicao.set("geometry", "0%/0%:100%x100%:100")
            tractor.plant_transition(composicao, indices_video[0], faixa_indice)
            self._transicoes.append(composicao)

        # A saída de áudio usa uma composição independente para que o consumidor
        # SDL não dispute quadros com a pré-visualização de imagem da interface.
        if self._motor_audio is not None:
            self._motor_audio.carregar(projeto)

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

    # ---- áudio de pré-visualização ------------------------------------------------------
    def iniciar_audio_preview(self, posicao: int) -> bool:
        if self._projeto is None or self._tractor is None:
            return False
        self.parar_audio_preview()
        if self._motor_audio is None:
            self._motor_audio = MotorMLT(_fecha_factory=False)
            if not self._motor_audio.disponivel():
                self._motor_audio = None
                return False
            self._motor_audio.carregar(self._projeto)
        motor_audio = self._motor_audio
        motor_audio._tractor.seek(max(0, int(posicao)))
        consumidor = None
        servico = ""
        for candidato in ("rtaudio", "sdl2_audio"):
            tentativa = self._mlt.Consumer(motor_audio._perfil, candidato)
            if tentativa.is_valid():
                consumidor, servico = tentativa, candidato
                break
        if consumidor is None:
            _log.error("Nenhum consumidor de áudio MLT está disponível para a pré-visualização.")
            return False
        consumidor.set("video_off", "1")
        consumidor.set("real_time", "1")
        consumidor.set("audio_buffer", "512")
        consumidor.connect(motor_audio._tractor)
        if consumidor.start() != 0:
            _log.error("O consumidor MLT '%s' não conseguiu abrir a saída de áudio.", servico)
            consumidor.stop()
            return False
        self._consumidor_audio = consumidor
        _log.info("Pré-visualização de áudio iniciada com o consumidor MLT '%s'.", servico)
        return True

    def parar_audio_preview(self) -> None:
        if self._consumidor_audio is not None:
            try:
                self._consumidor_audio.stop()
            except Exception:  # noqa: BLE001 - encerramento deve ser tolerante
                _log.exception("Erro ao interromper a pré-visualização de áudio.")
            self._consumidor_audio = None

    def posicao_audio_preview(self) -> int | None:
        if self._consumidor_audio is None or self._consumidor_audio.is_stopped():
            return None
        return int(self._consumidor_audio.position())

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
        self.parar_audio_preview()
        if self._motor_audio is not None:
            self._motor_audio.encerrar()
            self._motor_audio = None
        self._tractor = None
        self._consumidor = None
        self._transicoes = []
        self._filtros = []
        self._perfil = None
        if self._mlt is not None and self._fecha_factory:
            try:
                self._mlt.Factory.close()
            except Exception:  # noqa: BLE001
                _log.exception("Erro ao encerrar a fábrica do MLT.")
        if self._diretorio_lumas is not None:
            self._diretorio_lumas.cleanup()
            self._diretorio_lumas = None
