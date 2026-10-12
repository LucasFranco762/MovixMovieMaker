from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from core.configuracoes import criar_configuracoes_padrao, diretorio_dados_usuario
from core.constantes import ARQUIVO_LOGO, NOME_APLICATIVO, ORGANIZACAO, VERSAO_APLICATIVO
from core.controlador import Controlador
from core.excecoes import DependenciaAusenteError
from core.logging_config import configurar_logging
from multimidia.motor_ffmpeg import MotorFFmpeg
from multimidia.motor_mlt import MotorMLT

_log = logging.getLogger(NOME_APLICATIVO)


def _preparar_servicos() -> tuple[MotorFFmpeg | None, MotorMLT, list[str]]:
    avisos: list[str] = []
    try:
        ffmpeg: MotorFFmpeg | None = MotorFFmpeg()
        _log.info("FFmpeg: %s", ffmpeg.versao())
    except DependenciaAusenteError as exc:
        ffmpeg = None
        avisos.append(str(exc))
        _log.error("FFmpeg indisponível: %s", exc)
    motor = MotorMLT()
    if not motor.disponivel():
        avisos.append(motor.descricao())
    return ffmpeg, motor, avisos


def main() -> int:
    configurar_logging(diretorio_dados_usuario() / "logs")
    _log.info("Iniciando %s %s", NOME_APLICATIVO, VERSAO_APLICATIVO)

    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMessageBox   # import tardio: falha clara se ausente
    app = QApplication(sys.argv)
    app.setApplicationName(NOME_APLICATIVO)
    app.setOrganizationName(ORGANIZACAO)
    caminho_logo = Path(__file__).resolve().parent / ARQUIVO_LOGO
    if caminho_logo.is_file():
        app.setWindowIcon(QIcon(str(caminho_logo)))

    from interface.splash import ATRASO_APOS_CARREGAMENTO_MS, criar_splash
    splash = criar_splash(app, caminho_logo)

    def ao_excecao_nao_tratada(tipo, valor, tb) -> None:
        """Erros inesperados são registrados e mostrados sem encerrar o aplicativo."""
        _log.critical("Exceção não tratada", exc_info=(tipo, valor, tb))
        QMessageBox.critical(None, "Erro inesperado",
                             f"Ocorreu um erro inesperado:\n{valor}\n\nDetalhes foram gravados no log.")
        traceback.print_exception(tipo, valor, tb)

    sys.excepthook = ao_excecao_nao_tratada

    from interface.estilos import QSS, instalar_cursor_botoes
    from interface.janela_principal import JanelaPrincipal

    app.setStyleSheet(QSS)
    filtro_cursor_botoes = instalar_cursor_botoes(app)
    config = criar_configuracoes_padrao()
    ffmpeg, motor, avisos = _preparar_servicos()
    controlador = Controlador(config, motor=motor, ffmpeg=ffmpeg)
    controlador.novo_projeto()

    janela = JanelaPrincipal(controlador, aviso_inicial=" | ".join(avisos))

    def revelar_janela() -> None:
        janela.mostrar()
        if splash is not None:
            splash.finish(janela)

    # A janela e todos os seus componentes já estão construídos. A margem de
    # segurança solicitada mantém a splash por mais dois segundos.
    QTimer.singleShot(ATRASO_APOS_CARREGAMENTO_MS, revelar_janela)
    codigo = app.exec()
    del filtro_cursor_botoes
    controlador.encerrar()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
