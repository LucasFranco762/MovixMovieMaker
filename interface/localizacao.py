"""Configuração central de idioma da interface Qt."""
from __future__ import annotations

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication, QMessageBox


TEXTOS_BOTOES = {
    QMessageBox.StandardButton.Ok: "OK",
    QMessageBox.StandardButton.Save: "Salvar",
    QMessageBox.StandardButton.Discard: "Descartar",
    QMessageBox.StandardButton.Cancel: "Cancelar",
    QMessageBox.StandardButton.Yes: "Sim",
    QMessageBox.StandardButton.No: "Não",
    QMessageBox.StandardButton.Close: "Fechar",
    QMessageBox.StandardButton.Open: "Abrir",
    QMessageBox.StandardButton.Retry: "Tentar novamente",
}


def instalar_portugues_brasileiro(app: QApplication) -> QTranslator | None:
    """Define pt-BR e instala as traduções dos componentes nativos do Qt."""
    QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
    tradutor = QTranslator(app)
    pasta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not tradutor.load("qtbase_pt_BR", pasta):
        return None
    app.installTranslator(tradutor)
    return tradutor


def traduzir_botoes(caixa: QMessageBox) -> None:
    """Garante textos em pt-BR mesmo se a tradução externa do Qt não for encontrada."""
    for botao_padrao, texto in TEXTOS_BOTOES.items():
        botao = caixa.button(botao_padrao)
        if botao is not None:
            botao.setText(texto)
