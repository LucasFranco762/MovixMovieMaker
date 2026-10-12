"""Estado de seleção de clipes (sem interface)."""
from __future__ import annotations

from projetos.modelos import Projeto


class Selecao:
    def __init__(self) -> None:
        self._ids: list[str] = []

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._ids)

    def definir(self, ids: list[str]) -> None:
        self._ids = list(dict.fromkeys(ids))

    def alternar(self, clipe_id: str) -> None:
        if clipe_id in self._ids:
            self._ids.remove(clipe_id)
        else:
            self._ids.append(clipe_id)

    def limpar(self) -> None:
        self._ids.clear()

    def __contains__(self, clipe_id: str) -> bool:
        return clipe_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def podar(self, projeto: Projeto) -> None:
        """Remove da seleção clipes que deixaram de existir (após excluir/desfazer)."""
        existentes = {c.id for f in projeto.faixas for c in f.clipes}
        self._ids = [i for i in self._ids if i in existentes]
