"""Gravação segura de projetos (REQ-014, 16.2).

- Escrita em arquivo temporário no mesmo diretório + ``os.replace`` (atômico).
- Antes de substituir um arquivo existente, uma cópia é guardada no histórico de
  versões, com nome único (nunca sobrescreve backup anterior).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from core.constantes import EXTENSAO_PROJETO, MAX_VERSOES_HISTORICO
from core.excecoes import ErroSalvamento, ProjetoInvalidoError
from projetos.modelos import Projeto

_log = logging.getLogger(__name__)


def diretorio_historico(arquivo: Path) -> Path:
    return arquivo.parent / f".{arquivo.stem}.historico"


def caminho_autossalvamento(arquivo: Path) -> Path:
    return arquivo.with_name(f".{arquivo.stem}.autosave{EXTENSAO_PROJETO}")


def gravar_atomicamente(projeto: Projeto, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(projeto.para_dict(), ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".tmp_", suffix=".mmtmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def salvar_projeto(projeto: Projeto, destino: Path, manter_historico: bool = True) -> None:
    """Salva o projeto. Levanta ``ErroSalvamento`` com mensagem em português."""
    destino = Path(destino)
    try:
        if manter_historico and destino.exists():
            _guardar_versao(destino)
        gravar_atomicamente(projeto, destino)
    except OSError as exc:
        _log.exception("Falha ao salvar %s", destino)
        raise ErroSalvamento(f"Não foi possível salvar o projeto em '{destino}': {exc}") from exc


def _guardar_versao(arquivo: Path) -> None:
    pasta = diretorio_historico(arquivo)
    pasta.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(arquivo, pasta / f"{arquivo.stem}-{carimbo}{EXTENSAO_PROJETO}")
    versoes = sorted(pasta.glob(f"*{EXTENSAO_PROJETO}"))
    for antiga in versoes[:-MAX_VERSOES_HISTORICO]:
        antiga.unlink(missing_ok=True)


def listar_versoes(arquivo: Path) -> list[Path]:
    pasta = diretorio_historico(Path(arquivo))
    return sorted(pasta.glob(f"*{EXTENSAO_PROJETO}"), reverse=True) if pasta.exists() else []


def carregar_projeto(origem: Path) -> Projeto:
    """Lê um projeto. Levanta ``ProjetoInvalidoError``/``ProjetoIncompativelError``."""
    try:
        texto = Path(origem).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjetoInvalidoError(f"Não foi possível ler '{origem}': {exc}") from exc
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ProjetoInvalidoError(f"O arquivo '{origem}' está corrompido: {exc}") from exc
    return Projeto.de_dict(dados)
