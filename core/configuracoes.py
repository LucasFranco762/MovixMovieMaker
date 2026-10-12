"""Configurações persistentes do aplicativo (preferências globais).

Decisão técnica: o armazenamento usa um arquivo JSON no diretório de dados do
usuário (``%APPDATA%\\MovieMaker`` no Windows), com escrita atômica. Isso mantém
as configurações testáveis sem Qt e sem exigir privilégios administrativos.
Os dados específicos de cada projeto NÃO são guardados aqui (ficam no .mmproj).
Se for desejável usar QSettings no futuro, basta implementar a mesma interface
``ArmazenamentoConfiguracoes`` e injetar em ``Configuracoes``.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Protocol

from core.constantes import (
    INATIVIDADE_PROPRIEDADES_PADRAO_S,
    LAYOUT_PADRAO,
    MAX_PROJETOS_RECENTES,
    NOME_APLICATIVO,
)
from core.excecoes import ErroConfiguracao

_log = logging.getLogger(__name__)

PADROES: dict[str, Any] = {
    "layout.atual": LAYOUT_PADRAO,
    "interface.inatividade_propriedades_s": INATIVIDADE_PROPRIEDADES_PADRAO_S,
    "interface.geometria_janela": None,
    "diretorios.ultima_importacao": "",
    "diretorios.ultimo_projeto": "",
    "diretorios.ultima_exportacao": "",
    "projetos.recentes": [],
    "projetos.autossalvamento_s": 120,
}


def diretorio_dados_usuario() -> Path:
    """Diretório gravável pelo usuário comum, sem privilégios de administrador."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:  # apenas para desenvolvimento/testes; o alvo do produto é Windows
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / NOME_APLICATIVO.replace(" ", "")


class ArmazenamentoConfiguracoes(Protocol):
    def carregar(self) -> dict[str, Any]: ...
    def salvar(self, dados: dict[str, Any]) -> None: ...


class ArmazenamentoJson:
    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo

    def carregar(self) -> dict[str, Any]:
        if not self.arquivo.exists():
            return {}
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Arquivo corrompido: preserva uma cópia e recomeça com padrões.
            _log.warning("Configurações ilegíveis (%s); usando padrões.", exc)
            try:
                self.arquivo.replace(self.arquivo.with_suffix(".corrompido"))
            except OSError:
                _log.exception("Não foi possível preservar o arquivo corrompido.")
            return {}
        return dados if isinstance(dados, dict) else {}

    def salvar(self, dados: dict[str, Any]) -> None:
        try:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.arquivo.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.arquivo)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise ErroConfiguracao(f"Não foi possível salvar as configurações: {exc}") from exc


class Configuracoes:
    """Acesso por chave (``'layout.atual'``) a preferências persistentes."""

    def __init__(self, armazenamento: ArmazenamentoConfiguracoes) -> None:
        self._armazenamento = armazenamento
        self._dados: dict[str, Any] = armazenamento.carregar()

    def obter(self, chave: str, padrao: Any = None) -> Any:
        if chave in self._dados:
            return self._dados[chave]
        if padrao is not None:
            return padrao
        return PADROES.get(chave)

    def definir(self, chave: str, valor: Any, salvar: bool = True) -> None:
        self._dados[chave] = valor
        if salvar:
            self.salvar()

    def salvar(self) -> None:
        self._armazenamento.salvar(self._dados)

    # --- projetos recentes -------------------------------------------------
    def projetos_recentes(self) -> list[str]:
        return list(self.obter("projetos.recentes", []))

    def registrar_projeto_recente(self, caminho: str) -> None:
        lista = [c for c in self.projetos_recentes() if c != caminho]
        lista.insert(0, caminho)
        self.definir("projetos.recentes", lista[:MAX_PROJETOS_RECENTES])


def criar_configuracoes_padrao() -> Configuracoes:
    return Configuracoes(ArmazenamentoJson(diretorio_dados_usuario() / "configuracoes.json"))
