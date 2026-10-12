"""Definições puras (sem Qt) dos três layouts e persistência individual.

REQ-017 (19.10 e 19.11): cada layout mantém suas próprias dimensões e estados.
Adaptações temporárias por redimensionamento da janela NÃO passam por aqui, para
não sobrescrever preferências persistentes (19.12).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from core.configuracoes import Configuracoes
from core.constantes import LAYOUT_CLASSICO, LAYOUT_EDICAO_AVANCADA, LAYOUT_FOCO_VIDEO


@dataclass
class EstadoLayout:
    largura_painel: int = 280
    painel_aberto: bool = True
    categoria_ativa: str = "midias"
    altura_timeline: int = 260
    timeline_recolhida: bool = False


@dataclass(frozen=True)
class DefinicaoLayout:
    id: str
    nome: str
    descricao: str
    padrao: EstadoLayout


LAYOUTS: dict[str, DefinicaoLayout] = {
    LAYOUT_CLASSICO: DefinicaoLayout(
        LAYOUT_CLASSICO,
        "Layout 1 — Clássico",
        "Cabeçalho, barra lateral, painel de ferramentas, player e timeline.",
        EstadoLayout(largura_painel=280, painel_aberto=True, altura_timeline=260),
    ),
    LAYOUT_FOCO_VIDEO: DefinicaoLayout(
        LAYOUT_FOCO_VIDEO,
        "Layout 2 — Foco no Vídeo",
        "Painéis recolhidos e timeline compacta para maximizar o player.",
        EstadoLayout(largura_painel=240, painel_aberto=False, altura_timeline=140),
    ),
    LAYOUT_EDICAO_AVANCADA: DefinicaoLayout(
        LAYOUT_EDICAO_AVANCADA,
        "Layout 3 — Edição Avançada",
        "Timeline ampliada, com painel lateral disponível.",
        EstadoLayout(largura_painel=320, painel_aberto=True, altura_timeline=420),
    ),
}


def _chave(layout_id: str, campo: str) -> str:
    return f"layout.{layout_id}.{campo}"


def carregar_estado(config: Configuracoes, layout_id: str) -> EstadoLayout:
    """Lê o estado salvo do layout, completando com os padrões do próprio layout."""
    if layout_id not in LAYOUTS:
        raise KeyError(f"Layout desconhecido: {layout_id}")
    base = LAYOUTS[layout_id].padrao
    valores = {}
    for campo in fields(EstadoLayout):
        padrao = getattr(base, campo.name)
        valor = config.obter(_chave(layout_id, campo.name))
        valores[campo.name] = padrao if valor is None else type(padrao)(valor)
    return EstadoLayout(**valores)


def salvar_estado(config: Configuracoes, layout_id: str, estado: EstadoLayout) -> None:
    for campo, valor in asdict(estado).items():
        config.definir(_chave(layout_id, campo), valor, salvar=False)
    config.salvar()
