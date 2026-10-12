"""Conversão do resultado do ffprobe em ``MidiaRef`` do projeto."""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from core.constantes import (
    EXTENSOES_AUDIO, EXTENSOES_IMAGEM, EXTENSOES_VIDEO,
    TIPO_AUDIO, TIPO_IMAGEM, TIPO_VIDEO,
)
from core.excecoes import MidiaInvalidaError
from core.tempo import segundos_para_frames
from multimidia.motor_ffmpeg import MotorFFmpeg
from projetos.modelos import MidiaRef, novo_id


def extensoes_suportadas() -> tuple[str, ...]:
    return EXTENSOES_VIDEO + EXTENSOES_IMAGEM + EXTENSOES_AUDIO


def interpretar_taxa(texto: str | None) -> Fraction | None:
    """Converte '30000/1001' ou '25' em Fraction; None se inválida/zero."""
    if not texto:
        return None
    try:
        valor = Fraction(texto)
    except (ValueError, ZeroDivisionError):
        return None
    return valor if valor > 0 else None


def _eh_capa(stream: dict[str, Any]) -> bool:
    return bool(stream.get("disposition", {}).get("attached_pic"))


def montar_midia(info: dict[str, Any], caminho: Path, fps_projeto: Fraction) -> MidiaRef:
    """Cria o ``MidiaRef`` a partir do JSON do ffprobe (função pura, testável)."""
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and not _eh_capa(s)), None)
    imagem_ou_capa = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    ext = caminho.suffix.lower()

    if ext in EXTENSOES_IMAGEM and imagem_ou_capa is not None:
        tipo, base = TIPO_IMAGEM, imagem_ou_capa
    elif video is not None:
        tipo, base = TIPO_VIDEO, video
    elif audio is not None:
        tipo, base = TIPO_AUDIO, audio
    else:
        raise MidiaInvalidaError(f"'{caminho.name}' não contém vídeo, imagem nem áudio reconhecível.")

    duracao_s: float | None = None
    for fonte in (info.get("format", {}), base):
        try:
            d = float(fonte.get("duration"))
            if d > 0:
                duracao_s = d
                break
        except (TypeError, ValueError):
            continue

    duracao_frames = 0
    if tipo != TIPO_IMAGEM:
        if duracao_s is None:
            raise MidiaInvalidaError(f"Não foi possível determinar a duração de '{caminho.name}'.")
        duracao_frames = max(1, segundos_para_frames(duracao_s, fps_projeto))

    return MidiaRef(
        id=novo_id(),
        caminho=str(caminho),
        tipo=tipo,
        nome=caminho.name,
        duracao_frames=duracao_frames,
        largura=int(base.get("width") or 0) if tipo != TIPO_AUDIO else 0,
        altura=int(base.get("height") or 0) if tipo != TIPO_AUDIO else 0,
        tem_audio=audio is not None,
        tem_video=tipo in (TIPO_VIDEO, TIPO_IMAGEM),
    )


def analisar_midia(motor: MotorFFmpeg, caminho: str | Path, fps_projeto: Fraction) -> MidiaRef:
    caminho = Path(caminho)
    if caminho.suffix.lower() not in extensoes_suportadas():
        raise MidiaInvalidaError(f"Formato não previsto: '{caminho.suffix}'.")
    return montar_midia(motor.sondar(caminho), caminho, fps_projeto)
