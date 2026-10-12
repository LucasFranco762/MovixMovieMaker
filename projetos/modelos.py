"""Modelo de dados do projeto (REQ-014, 16.1).

O modelo é independente de interface e de motor multimídia. Posições e durações
são sempre frames inteiros. Os arquivos originais são apenas referenciados.

Ainda não modelados (previstos para a Etapa 5): transições, efeitos, keyframes,
textos e legendas. O formato é versionado para permitir essa evolução.
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

    def aceita(self, tipo_clipe: str) -> bool:
        return tipo_clipe in CLIPES_POR_FAIXA.get(self.tipo, ())


@dataclass
class Projeto:
    id: str = field(default_factory=novo_id)
    versao_formato: int = VERSAO_FORMATO_PROJETO
    nome: str = "Projeto sem título"
    config: ConfiguracaoAV = field(default_factory=ConfiguracaoAV)
    midias: dict[str, MidiaRef] = field(default_factory=dict)
    faixas: list[Faixa] = field(default_factory=list)

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
            "midias": [vars(m).copy() for m in self.midias.values()],
            "faixas": [
                {
                    "id": f.id, "nome": f.nome, "tipo": f.tipo,
                    "bloqueada": f.bloqueada, "visivel": f.visivel,
                    "silenciada": f.silenciada, "cor": f.cor,
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
                f"({VERSAO_FORMATO_PROJETO}). Atualize o Movie Maker para abri-lo."
            )
        dados = _migrar(dados, versao)
        try:
            config = ConfiguracaoAV(**dados["config"])
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
                ))
            projeto = cls(id=dados["id"], versao_formato=VERSAO_FORMATO_PROJETO,
                          nome=dados["nome"], config=config, midias=midias, faixas=faixas)
        except (KeyError, TypeError) as exc:
            raise ProjetoInvalidoError(f"Estrutura do projeto inválida: {exc}") from exc
        return projeto


def _migrar(dados: dict[str, Any], versao: int) -> dict[str, Any]:
    """Ponto de extensão para migrações de formato. Hoje só existe a versão 1."""
    return dados
