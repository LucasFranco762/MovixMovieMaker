"""Interface abstrata do motor de composição/reprodução.

A interface depende apenas desta abstração. A única implementação prevista é
``MotorMLT`` (REQ-004); não há motor substituto silencioso. Se o MLT estiver
indisponível, o aplicativo informa isso e mantém a edição do modelo funcionando.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from projetos.modelos import Projeto


@dataclass(frozen=True)
class FrameRGBA:
    largura: int
    altura: int
    dados: bytes          # RGBA, largura*altura*4 bytes


class MotorMultimidia(ABC):
    @abstractmethod
    def disponivel(self) -> bool: ...

    @abstractmethod
    def descricao(self) -> str:
        """Texto curto (pt-BR) sobre o estado do motor, para a interface."""

    @abstractmethod
    def carregar(self, projeto: Projeto) -> None:
        """Reconstrói a composição a partir do modelo (fonte única de verdade)."""

    @abstractmethod
    def obter_frame(self, posicao: int) -> FrameRGBA | None: ...

    def iniciar_audio_preview(self, posicao: int) -> bool:
        """Inicia o áudio da composição. Retorna ``False`` se não houver suporte."""
        return False

    def parar_audio_preview(self) -> None:
        """Interrompe o áudio de pré-visualização, quando disponível."""

    def posicao_audio_preview(self) -> int | None:
        """Posição conduzida pelo áudio ou ``None`` quando ele não está ativo."""
        return None

    @abstractmethod
    def exportar(self, destino: str, **opcoes: object) -> None: ...

    @abstractmethod
    def encerrar(self) -> None: ...
