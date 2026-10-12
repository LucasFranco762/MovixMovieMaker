"""Constantes e valores padrão compartilhados por todo o Movix Movie Maker."""
from __future__ import annotations

NOME_APLICATIVO = "Movix Movie Maker"
ORGANIZACAO = "MovixMovieMaker"
VERSAO_APLICATIVO = "0.1.0"
ARQUIVO_LOGO = "Logo Movix Movie Maker em Neon.png"

# Versão do formato de arquivo de projeto. Incrementar ao alterar o esquema
# e implementar a migração correspondente em projetos/modelos.py.
VERSAO_FORMATO_PROJETO = 3
EXTENSAO_PROJETO = ".mmproj"
EXTENSAO_PROJETO_FILTRO = "Projeto do Movix Movie Maker (*.mmproj)"

# Formatos previstos (REQ-009). A compatibilidade real depende do FFmpeg
# instalado e deve ser validada (ver ferramentas/prova_conceito.py).
EXTENSOES_VIDEO = (".mp4", ".mov", ".mkv", ".avi", ".webm")
EXTENSOES_IMAGEM = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
EXTENSOES_AUDIO = (".mp3", ".wav", ".aac", ".flac", ".ogg")

# Tipos de mídia / categorias de clipe (REQ-017, 19.9)
TIPO_VIDEO = "video"
TIPO_AUDIO = "audio"
TIPO_IMAGEM = "imagem"
TIPO_TEXTO = "texto"
TIPO_LEGENDA = "legenda"
TIPOS_MIDIA = (TIPO_VIDEO, TIPO_AUDIO, TIPO_IMAGEM, TIPO_TEXTO, TIPO_LEGENDA)

# Tipos de faixa
FAIXA_VIDEO = "video"
FAIXA_AUDIO = "audio"

# Transições visuais disponíveis no catálogo.
TRANSICAO_DISSOLVER = "dissolver"
TIPOS_TRANSICAO = (TRANSICAO_DISSOLVER,)

# Tipos de clipe aceitos por tipo de faixa
CLIPES_POR_FAIXA = {
    FAIXA_VIDEO: (TIPO_VIDEO, TIPO_IMAGEM, TIPO_TEXTO, TIPO_LEGENDA),
    FAIXA_AUDIO: (TIPO_AUDIO,),
}

# Cores predefinidas por categoria (podem ser personalizadas no projeto)
CORES_CATEGORIA = {
    TIPO_VIDEO: "#3b82c4",
    TIPO_AUDIO: "#3aa17e",
    TIPO_IMAGEM: "#c48a3b",
    TIPO_TEXTO: "#a060c4",
    TIPO_LEGENDA: "#c4607a",
}
# Símbolos usados como ícone textual enquanto não há conjunto de ícones em
# recursos/icones. Identificam a categoria independentemente da cor.
ICONES_CATEGORIA = {
    TIPO_VIDEO: "▶",
    TIPO_AUDIO: "♪",
    TIPO_IMAGEM: "▣",
    TIPO_TEXTO: "T",
    TIPO_LEGENDA: "≡",
}

# Configurações audiovisuais padrão de um projeto novo
LARGURA_PADRAO = 1920
ALTURA_PADRAO = 1080
FPS_PADRAO = (30, 1)
TAXA_AMOSTRAGEM_PADRAO = 48000
CANAIS_PADRAO = 2

# Histórico de versões do projeto
MAX_VERSOES_HISTORICO = 20
INTERVALO_AUTOSSALVAMENTO_S = 120
MAX_PROJETOS_RECENTES = 10
LIMITE_HISTORICO_COMANDOS = 500

# Painel de propriedades (REQ-017, 19.4)
INATIVIDADE_PROPRIEDADES_PADRAO_S = 8

# Layouts (REQ-017, 19.10)
LAYOUT_CLASSICO = "classico"
LAYOUT_FOCO_VIDEO = "foco_video"
LAYOUT_EDICAO_AVANCADA = "edicao_avancada"
LAYOUT_PADRAO = LAYOUT_CLASSICO
