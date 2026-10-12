"""Modelo de dados do projeto (REQ-014, 16.1).

O modelo é independente de interface e de motor multimídia. Posições e durações
são sempre frames inteiros. Os arquivos originais são apenas referenciados.

Efeitos, keyframes, textos e legendas ainda serão ampliados. O formato é
versionado para permitir essa evolução sem perder projetos anteriores.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from core.constantes import (
    ALTURA_PADRAO,
    CANAIS_PADRAO,
    CLIPES_POR_FAIXA,
    CORES_CATEGORIA,
    FAIXA_AUDIO,
    FAIXA_VIDEO,
    FPS_PADRAO,
    LARGURA_PADRAO,
    TAXA_AMOSTRAGEM_PADRAO,
    TIPOS_MIDIA,
    TIPOS_TRANSICAO,
    VERSAO_FORMATO_PROJETO,
)
from core.excecoes import ProjetoIncompativelError, ProjetoInvalidoError


def novo_id() -> str:
    return uuid.uuid4().hex


@dataclass
class ConfiguracaoAV:
    largura: int = LARGURA_PADRAO
    altura: int = ALTURA_PADRAO
    fps_num: int = FPS_PADRAO[0]
    fps_den: int = FPS_PADRAO[1]
    taxa_amostragem: int = TAXA_AMOSTRAGEM_PADRAO
    canais: int = CANAIS_PADRAO

    @property
    def fps(self) -> Fraction:
        return Fraction(self.fps_num, self.fps_den)


@dataclass
class MidiaRef:
    id: str
    caminho: str                      # caminho absoluto atual
    tipo: str                         # um de TIPOS_MIDIA
    nome: str = ""
    duracao_frames: int = 0           # nos FPS do projeto; 0 para imagens (duração livre)
    largura: int = 0
    altura: int = 0
    tem_audio: bool = False
    tem_video: bool = False
    pasta_virtual: str = ""
    caminho_relativo: str | None = None   # relativo ao arquivo do projeto, p/ portabilidade


@dataclass
class Clipe:
    id: str
    midia_id: str
    tipo: str
    inicio: int                       # frame na timeline
    duracao: int                      # frames na timeline
    entrada: int = 0                  # frame de entrada (in) na mídia original
    nome: str = ""
    cor: str | None = None            # None = cor padrão da categoria
    grupo_id: str | None = None
    volume: float = 1.0

    def __post_init__(self) -> None:
        self.volume = max(0.0, min(2.0, float(self.volume)))

    @property
    def fim(self) -> int:
        """Frame final exclusivo."""
        return self.inicio + self.duracao

    def cor_efetiva(self) -> str:
        return self.cor or CORES_CATEGORIA.get(self.tipo, "#777777")


@dataclass
class Faixa:
    id: str
    nome: str
    tipo: str                         # FAIXA_VIDEO | FAIXA_AUDIO
    clipes: list[Clipe] = field(default_factory=list)
    bloqueada: bool = False
    visivel: bool = True              # relevante para faixas de vídeo
    silenciada: bool = False          # relevante para faixas de áudio
    cor: str | None = None
    volume: float = 1.0

    def __post_init__(self) -> None:
        self.volume = max(0.0, min(2.0, float(self.volume)))

    def aceita(self, tipo_clipe: str) -> bool:
        return tipo_clipe in CLIPES_POR_FAIXA.get(self.tipo, ())


@dataclass
class MixagemAudio:
    """Balanço entre o áudio embutido nos vídeos e as faixas de áudio."""

    volume_original: float = 1.0
    volume_adicionado: float = 1.0

    def __post_init__(self) -> None:
        self.volume_original = max(0.0, min(2.0, float(self.volume_original)))
        self.volume_adicionado = max(0.0, min(2.0, float(self.volume_adicionado)))


@dataclass
class Transicao:
    """Transição visual entre dois clipes consecutivos da mesma faixa."""

    id: str
    faixa_id: str
    clipe_origem_id: str
    clipe_destino_id: str
    tipo: str
    duracao: int

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_TRANSICAO:
            raise ValueError(f"Tipo de transição desconhecido: {self.tipo!r}")
        self.duracao = int(self.duracao)
        if self.duracao < 1:
            raise ValueError("A duração da transição deve ser positiva.")


@dataclass
class Projeto:
    id: str = field(default_factory=novo_id)
    versao_formato: int = VERSAO_FORMATO_PROJETO
    nome: str = "Projeto sem título"
    config: ConfiguracaoAV = field(default_factory=ConfiguracaoAV)
    midias: dict[str, MidiaRef] = field(default_factory=dict)
    faixas: list[Faixa] = field(default_factory=list)
    mixagem_audio: MixagemAudio = field(default_factory=MixagemAudio)
    transicoes: list[Transicao] = field(default_factory=list)

    # ---- consultas ---------------------------------------------------------
    @property
    def duracao_frames(self) -> int:
        return max((c.fim for f in self.faixas for c in f.clipes), default=0)

    def faixa_por_id(self, faixa_id: str) -> Faixa:
        for f in self.faixas:
            if f.id == faixa_id:
                return f
        raise KeyError(faixa_id)

    def localizar_clipe(self, clipe_id: str) -> tuple[Faixa, Clipe]:
        for f in self.faixas:
            for c in f.clipes:
                if c.id == clipe_id:
                    return f, c
        raise KeyError(clipe_id)

    def transicao_por_id(self, transicao_id: str) -> Transicao:
        for transicao in self.transicoes:
            if transicao.id == transicao_id:
                return transicao
        raise KeyError(transicao_id)

    def transicoes_do_clipe(self, clipe_id: str) -> list[Transicao]:
        return [t for t in self.transicoes
                if clipe_id in (t.clipe_origem_id, t.clipe_destino_id)]

    # ---- fábrica -------------------------------------------------------------
    @classmethod
    def novo(cls, nome: str = "Projeto sem título") -> "Projeto":
        p = cls(nome=nome)
        p.faixas = [
            Faixa(novo_id(), "Vídeo 1", FAIXA_VIDEO),
            Faixa(novo_id(), "Áudio 1", FAIXA_AUDIO),
        ]
        return p

    # ---- serialização --------------------------------------------------------
    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "versao_formato": self.versao_formato,
            "nome": self.nome,
            "config": vars(self.config).copy(),
            "mixagem_audio": vars(self.mixagem_audio).copy(),
            "transicoes": [vars(t).copy() for t in self.transicoes],
            "midias": [vars(m).copy() for m in self.midias.values()],
            "faixas": [
                {
                    "id": f.id, "nome": f.nome, "tipo": f.tipo,
                    "bloqueada": f.bloqueada, "visivel": f.visivel,
                    "silenciada": f.silenciada, "cor": f.cor, "volume": f.volume,
                    "clipes": [vars(c).copy() for c in f.clipes],
                }
                for f in self.faixas
            ],
        }

    @classmethod
    def de_dict(cls, dados: Any) -> "Projeto":
        if not isinstance(dados, dict):
            raise ProjetoInvalidoError("O arquivo de projeto não contém um objeto válido.")
        versao = dados.get("versao_formato")
        if not isinstance(versao, int):
            raise ProjetoInvalidoError("O projeto não informa a versão do formato.")
        if versao > VERSAO_FORMATO_PROJETO:
            raise ProjetoIncompativelError(
                f"Este projeto usa o formato versão {versao}, mais novo que o suportado "
                f"({VERSAO_FORMATO_PROJETO}). Atualize o Movix Movie Maker para abri-lo."
            )
        dados = _migrar(dados, versao)
        try:
            config = ConfiguracaoAV(**dados["config"])
            mixagem = MixagemAudio(**dados.get("mixagem_audio", {}))
            transicoes = [Transicao(**t) for t in dados.get("transicoes", [])]
            midias = {}
            for m in dados["midias"]:
                ref = MidiaRef(**m)
                if ref.tipo not in TIPOS_MIDIA:
                    raise ProjetoInvalidoError(f"Tipo de mídia desconhecido: {ref.tipo!r}.")
                midias[ref.id] = ref
            faixas = []
            for fd in dados["faixas"]:
                if fd["tipo"] not in (FAIXA_VIDEO, FAIXA_AUDIO):
                    raise ProjetoInvalidoError(f"Tipo de faixa desconhecido: {fd['tipo']!r}.")
                clipes = [Clipe(**c) for c in fd["clipes"]]
                faixas.append(Faixa(
                    id=fd["id"], nome=fd["nome"], tipo=fd["tipo"], clipes=clipes,
                    bloqueada=fd.get("bloqueada", False), visivel=fd.get("visivel", True),
                    silenciada=fd.get("silenciada", False), cor=fd.get("cor"),
                    volume=float(fd.get("volume", 1.0)),
                ))
            projeto = cls(id=dados["id"], versao_formato=VERSAO_FORMATO_PROJETO,
                          nome=dados["nome"], config=config, midias=midias, faixas=faixas,
                          mixagem_audio=mixagem, transicoes=transicoes)
            for transicao in projeto.transicoes:
                faixa_a, _ = projeto.localizar_clipe(transicao.clipe_origem_id)
                faixa_b, _ = projeto.localizar_clipe(transicao.clipe_destino_id)
                if faixa_a.id != transicao.faixa_id or faixa_b.id != transicao.faixa_id:
                    raise ProjetoInvalidoError("Uma transição referencia clipes de outra faixa.")
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjetoInvalidoError(f"Estrutura do projeto inválida: {exc}") from exc
        return projeto


def _migrar(dados: dict[str, Any], versao: int) -> dict[str, Any]:
    """Completa campos novos sem invalidar projetos de versões anteriores."""
    if versao < 2:
        dados.setdefault("mixagem_audio", {"volume_original": 1.0, "volume_adicionado": 1.0})
        for faixa in dados.get("faixas", []):
            faixa.setdefault("volume", 1.0)
            for clipe in faixa.get("clipes", []):
                clipe.setdefault("volume", 1.0)
    if versao < 3:
        dados.setdefault("transicoes", [])
    return dados
