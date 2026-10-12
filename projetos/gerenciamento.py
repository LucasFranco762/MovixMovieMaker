"""Ciclo de vida do projeto aberto: novo, abrir, salvar, mídias ausentes."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from core.configuracoes import Configuracoes
from core.constantes import EXTENSAO_PROJETO
from projetos.modelos import MidiaRef, Projeto
from projetos.salvamento import carregar_projeto, salvar_projeto

_log = logging.getLogger(__name__)


class GerenciadorProjetos:
    def __init__(self, config: Configuracoes) -> None:
        self._config = config
        self.projeto: Projeto = Projeto.novo()
        self.caminho: Path | None = None
        self.modificado: bool = False

    # ---- ciclo de vida ----------------------------------------------------------
    def novo(self, nome: str = "Projeto sem título") -> Projeto:
        self.projeto = Projeto.novo(nome)
        self.caminho = None
        self.modificado = False
        return self.projeto

    def abrir(self, caminho: str | Path) -> Projeto:
        caminho = Path(caminho)
        self.projeto = carregar_projeto(caminho)       # pode levantar erro tratável
        self.caminho = caminho
        self.modificado = False
        self._resolver_caminhos_relativos()
        self._config.registrar_projeto_recente(str(caminho))
        return self.projeto

    def salvar(self, caminho: str | Path | None = None) -> Path:
        destino = Path(caminho) if caminho else self.caminho
        if destino is None:
            raise ValueError("Informe o caminho para salvar um projeto novo.")
        if destino.suffix.lower() != EXTENSAO_PROJETO:
            destino = destino.with_suffix(EXTENSAO_PROJETO)
        self._atualizar_caminhos_relativos(destino)
        salvar_projeto(self.projeto, destino)
        self.caminho = destino
        self.modificado = False
        self._config.registrar_projeto_recente(str(destino))
        return destino

    # ---- mídias -------------------------------------------------------------------
    def midias_ausentes(self) -> list[MidiaRef]:
        return [m for m in self.projeto.midias.values() if not Path(m.caminho).is_file()]

    def religar_midia(self, midia_id: str, novo_caminho: str | Path) -> None:
        midia = self.projeto.midias[midia_id]
        midia.caminho = str(novo_caminho)
        midia.caminho_relativo = None
        self.modificado = True

    def _atualizar_caminhos_relativos(self, destino: Path) -> None:
        base = destino.parent.resolve()
        for m in self.projeto.midias.values():
            try:
                m.caminho_relativo = os.path.relpath(Path(m.caminho).resolve(), base)
            except ValueError:      # outro drive no Windows: não há caminho relativo
                m.caminho_relativo = None

    def _resolver_caminhos_relativos(self) -> None:
        """Se o caminho absoluto sumiu mas o relativo existe, usa o relativo."""
        if self.caminho is None:
            return
        base = self.caminho.parent
        for m in self.projeto.midias.values():
            if not Path(m.caminho).is_file() and m.caminho_relativo:
                candidato = (base / m.caminho_relativo).resolve()
                if candidato.is_file():
                    m.caminho = str(candidato)
