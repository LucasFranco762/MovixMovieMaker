"""Leitura e escrita do formato SubRip (SRT)."""
from __future__ import annotations

import re
from fractions import Fraction

_TEMPO = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})$")


def _milissegundos(valor: str) -> int:
    encontrado = _TEMPO.match(valor.strip())
    if not encontrado:
        raise ValueError(f"Tempo de legenda inválido: {valor!r}")
    horas, minutos, segundos, milesimos = map(int, encontrado.groups())
    if minutos >= 60 or segundos >= 60:
        raise ValueError(f"Tempo de legenda inválido: {valor!r}")
    return ((horas * 60 + minutos) * 60 + segundos) * 1000 + milesimos


def interpretar_srt(texto: str) -> list[tuple[int, int, str]]:
    """Retorna ``(início_ms, fim_ms, conteúdo)`` para cada bloco válido."""
    blocos = re.split(r"\r?\n\s*\r?\n", texto.strip()) if texto.strip() else []
    resultado: list[tuple[int, int, str]] = []
    for numero, bloco in enumerate(blocos, 1):
        linhas = bloco.replace("\r", "").split("\n")
        if linhas and linhas[0].strip().isdigit():
            linhas.pop(0)
        if len(linhas) < 2 or "-->" not in linhas[0]:
            raise ValueError(f"Bloco {numero} do SRT não possui intervalo de tempo válido.")
        inicio_txt, fim_txt = linhas.pop(0).split("-->", 1)
        inicio, fim = _milissegundos(inicio_txt), _milissegundos(fim_txt.split()[0])
        conteudo = "\n".join(linhas).strip()
        if fim <= inicio or not conteudo:
            raise ValueError(f"Bloco {numero} do SRT possui duração ou texto inválido.")
        resultado.append((inicio, fim, conteudo))
    return resultado


def _formatar_ms(valor: int) -> str:
    horas, resto = divmod(max(0, valor), 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    segundos, milesimos = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d},{milesimos:03d}"


def gerar_srt(legendas, fps: Fraction) -> str:
    blocos = []
    for indice, legenda in enumerate(sorted(legendas, key=lambda c: c.inicio), 1):
        inicio = round(legenda.inicio * 1000 / float(fps))
        fim = round(legenda.fim * 1000 / float(fps))
        blocos.append(
            f"{indice}\n{_formatar_ms(inicio)} --> {_formatar_ms(fim)}\n{legenda.conteudo}")
    return "\n\n".join(blocos) + ("\n" if blocos else "")
