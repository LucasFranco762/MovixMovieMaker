"""Configuração de logging local (arquivo rotativo + console)."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from core.constantes import NOME_APLICATIVO

_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configurado = False


def configurar_logging(diretorio_logs: Path, nivel: int = logging.INFO) -> Path:
    """Configura o logging raiz e devolve o caminho do arquivo de log.

    Pode ser chamada mais de uma vez; apenas a primeira chamada tem efeito.
    """
    global _configurado
    diretorio_logs.mkdir(parents=True, exist_ok=True)
    arquivo = diretorio_logs / "movie_maker.log"
    if _configurado:
        return arquivo

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    formato = logging.Formatter(_FORMATO)

    arq = logging.handlers.RotatingFileHandler(
        arquivo, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    arq.setFormatter(formato)
    raiz.addHandler(arq)

    console = logging.StreamHandler()
    console.setFormatter(formato)
    raiz.addHandler(console)

    _configurado = True
    logging.getLogger(NOME_APLICATIVO).info("Logging iniciado em %s", arquivo)
    return arquivo
