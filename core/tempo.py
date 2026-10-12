"""Cálculo temporal por frames (REQ-006).

Toda a posição/duração no modelo é armazenada em frames inteiros, o que evita
erros acumulados de arredondamento. O FPS é uma fração exata (ex.: 30000/1001).
Conversões para segundos usam ``Fraction``.
"""
from __future__ import annotations

import re
from fractions import Fraction

_TIMECODE = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2}):(\d{1,2})$")


def criar_fps(numerador: int, denominador: int = 1) -> Fraction:
    if numerador <= 0 or denominador <= 0:
        raise ValueError("FPS deve ter numerador e denominador positivos.")
    return Fraction(numerador, denominador)


def frames_para_segundos(frames: int, fps: Fraction) -> Fraction:
    return Fraction(frames) / fps


def segundos_para_frames(segundos: float | Fraction, fps: Fraction, modo: str = "arredondar") -> int:
    """Converte segundos em frames. ``modo``: 'arredondar', 'piso' ou 'teto'."""
    valor = Fraction(segundos).limit_denominator(1_000_000) * fps
    if modo == "piso":
        return int(valor // 1)
    if modo == "teto":
        return int(-((-valor) // 1))
    # arredondamento para o mais próximo (metade para cima)
    return int((valor * 2 + 1) // 2)


def fps_nominal(fps: Fraction) -> int:
    """FPS inteiro usado na contagem de frames do timecode (sem drop-frame)."""
    return max(1, int(round(float(fps))))


def formatar_timecode(frames: int, fps: Fraction) -> str:
    """Formata ``frames`` como HH:MM:SS:FF (sem drop-frame)."""
    if frames < 0:
        return "-" + formatar_timecode(-frames, fps)
    base = fps_nominal(fps)
    ff = frames % base
    total_s = frames // base
    return f"{total_s // 3600:02d}:{(total_s // 60) % 60:02d}:{total_s % 60:02d}:{ff:02d}"


def interpretar_timecode(texto: str, fps: Fraction) -> int:
    """Converte HH:MM:SS:FF em frames. Levanta ValueError se inválido."""
    m = _TIMECODE.match(texto.strip())
    if not m:
        raise ValueError(f"Timecode inválido: {texto!r} (use HH:MM:SS:FF).")
    h, mi, s, ff = (int(g) for g in m.groups())
    base = fps_nominal(fps)
    if mi > 59 or s > 59 or ff >= base:
        raise ValueError(f"Timecode fora do intervalo: {texto!r}.")
    return ((h * 3600 + mi * 60 + s) * base) + ff
