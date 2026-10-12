"""Hierarquia de exceções do Movie Maker.

Todas as mensagens destinadas ao usuário ficam em português brasileiro.
"""
from __future__ import annotations


class ErroMovieMaker(Exception):
    """Base de todos os erros previstos pelo aplicativo."""


class ErroConfiguracao(ErroMovieMaker):
    """Falha ao ler ou gravar configurações locais."""


class ErroProjeto(ErroMovieMaker):
    """Falha genérica relacionada a projetos."""


class ProjetoInvalidoError(ErroProjeto):
    """Arquivo de projeto corrompido ou com estrutura inesperada."""


class ProjetoIncompativelError(ErroProjeto):
    """Projeto criado por uma versão de formato mais nova que a suportada."""


class ErroSalvamento(ErroProjeto):
    """Falha ao gravar o projeto em disco."""


class ErroEdicao(ErroMovieMaker):
    """Operação de edição inválida (ex.: faixa bloqueada, sobreposição)."""


class ErroMultimidia(ErroMovieMaker):
    """Falha em operações do motor multimídia."""


class DependenciaAusenteError(ErroMultimidia):
    """Biblioteca ou executável necessário não foi encontrado."""


class MidiaInvalidaError(ErroMultimidia):
    """Arquivo de mídia ausente, corrompido ou não suportado."""


class ErroExportacao(ErroMultimidia):
    """Falha durante a exportação/renderização."""
