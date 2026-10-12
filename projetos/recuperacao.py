"""Salvamento automático e recuperação após falhas (REQ-014)."""
from __future__ import annotations

import logging
from pathlib import Path

from projetos.modelos import Projeto
from projetos.salvamento import carregar_projeto, caminho_autossalvamento, gravar_atomicamente

_log = logging.getLogger(__name__)


def gravar_autossalvamento(projeto: Projeto, arquivo_projeto: Path) -> Path:
    destino = caminho_autossalvamento(arquivo_projeto)
    gravar_atomicamente(projeto, destino)
    return destino


def existe_recuperacao(arquivo_projeto: Path) -> bool:
    """True se há autossalvamento mais novo que o arquivo do projeto."""
    auto = caminho_autossalvamento(arquivo_projeto)
    if not auto.exists():
        return False
    if not arquivo_projeto.exists():
        return True
    return auto.stat().st_mtime > arquivo_projeto.stat().st_mtime


def recuperar(arquivo_projeto: Path) -> Projeto:
    return carregar_projeto(caminho_autossalvamento(arquivo_projeto))


def descartar_autossalvamento(arquivo_projeto: Path) -> None:
    caminho_autossalvamento(arquivo_projeto).unlink(missing_ok=True)
