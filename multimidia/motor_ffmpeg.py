"""Integração centralizada com o FFmpeg/FFprobe (REQ-004, 20.4).

Usa os executáveis ``ffmpeg`` e ``ffprobe`` por subprocesso (sem shell), o que
também evita travar a interface quando chamado fora da thread principal.
No Windows, procura primeiro em ``MOVIEMAKER_FFMPEG_DIR`` e em
``ferramentas/ffmpeg/bin`` e depois no PATH.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.excecoes import DependenciaAusenteError, MidiaInvalidaError, ErroMultimidia

_log = logging.getLogger(__name__)

_RAIZ = Path(__file__).resolve().parent.parent


def _flags_subprocesso() -> int:
    # Evita abrir janela de console no Windows.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def localizar_executavel(nome: str) -> str | None:
    sufixo = ".exe" if sys.platform == "win32" else ""
    candidatos: list[Path] = []
    env = os.environ.get("MOVIEMAKER_FFMPEG_DIR")
    if env:
        candidatos.append(Path(env) / f"{nome}{sufixo}")
    candidatos.append(_RAIZ / "ferramentas" / "ffmpeg" / "bin" / f"{nome}{sufixo}")
    for c in candidatos:
        if c.is_file():
            return str(c)
    return shutil.which(nome)


class MotorFFmpeg:
    def __init__(self, ffmpeg: str | None = None, ffprobe: str | None = None) -> None:
        self.ffmpeg = ffmpeg or localizar_executavel("ffmpeg")
        self.ffprobe = ffprobe or localizar_executavel("ffprobe")
        if not self.ffmpeg:
            raise DependenciaAusenteError(
                "FFmpeg não encontrado. Instale-o e adicione ao PATH, ou defina "
                "MOVIEMAKER_FFMPEG_DIR com a pasta que contém ffmpeg.exe."
            )
        if not self.ffprobe:
            raise DependenciaAusenteError("FFprobe não encontrado (acompanha o FFmpeg).")

    # ---- execução ------------------------------------------------------------
    def _executar(self, args: list[str], timeout: float = 60) -> str:
        try:
            r = subprocess.run(
                args, capture_output=True, timeout=timeout, creationflags=_flags_subprocesso(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ErroMultimidia(f"Tempo esgotado ao executar {Path(args[0]).name}.") from exc
        except OSError as exc:
            raise DependenciaAusenteError(f"Não foi possível executar {args[0]}: {exc}") from exc
        saida = r.stdout.decode("utf-8", errors="replace")
        if r.returncode != 0:
            erro = r.stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise ErroMultimidia(erro[-1] if erro else f"{Path(args[0]).name} falhou ({r.returncode}).")
        return saida

    # ---- informações do ambiente --------------------------------------------
    def versao(self) -> str:
        primeira = self._executar([self.ffmpeg, "-version"]).splitlines()
        return primeira[0] if primeira else "desconhecida"

    def listar_encoders(self) -> set[str]:
        """Nomes de encoders disponíveis neste FFmpeg (ex.: libx264, h264_nvenc)."""
        saida = self._executar([self.ffmpeg, "-hide_banner", "-encoders"])
        nomes: set[str] = set()
        for linha in saida.splitlines():
            partes = linha.split()
            if len(partes) >= 2 and len(partes[0]) == 6 and partes[0][0] in "VAS":
                nomes.add(partes[1])
        return nomes

    def listar_aceleracoes(self) -> list[str]:
        saida = self._executar([self.ffmpeg, "-hide_banner", "-hwaccels"])
        linhas = saida.splitlines()
        return [l.strip() for l in linhas[1:] if l.strip()]

    # ---- análise de arquivos -------------------------------------------------
    def sondar(self, caminho: str | Path) -> dict[str, Any]:
        """Executa o ffprobe e devolve o JSON (format + streams)."""
        caminho = Path(caminho)
        if not caminho.is_file():
            raise MidiaInvalidaError(f"Arquivo não encontrado: {caminho}")
        try:
            saida = self._executar(
                [self.ffprobe, "-v", "error", "-print_format", "json",
                 "-show_format", "-show_streams", str(caminho)]
            )
        except ErroMultimidia as exc:
            raise MidiaInvalidaError(f"Não foi possível ler a mídia '{caminho.name}': {exc}") from exc
        try:
            return json.loads(saida)
        except json.JSONDecodeError as exc:
            raise MidiaInvalidaError(f"Resposta inválida do ffprobe para '{caminho.name}'.") from exc

    def gerar_miniatura(self, caminho: str | Path, destino: str | Path,
                        instante_s: float = 0.0, largura: int = 160) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        self._executar(
            [self.ffmpeg, "-y", "-v", "error", "-ss", f"{instante_s:.3f}", "-i", str(caminho),
             "-frames:v", "1", "-vf", f"scale={largura}:-2", str(destino)],
            timeout=60,
        )
        if not destino.is_file():
            raise MidiaInvalidaError(f"Não foi possível gerar miniatura de '{Path(caminho).name}'.")
        return destino
