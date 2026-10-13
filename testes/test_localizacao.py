import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from interface.estilos import COR_PAINEL, COR_TEXTO, QSS
from interface.localizacao import instalar_portugues_brasileiro, traduzir_botoes


class TesteLocalizacaoQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tradutor = instalar_portugues_brasileiro(cls.app)

    def test_botoes_do_modal_de_alteracoes_estao_em_portugues(self):
        caixa = QMessageBox()
        caixa.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        traduzir_botoes(caixa)
        self.assertEqual(caixa.button(QMessageBox.StandardButton.Save).text(), "Salvar")
        self.assertEqual(caixa.button(QMessageBox.StandardButton.Discard).text(), "Descartar")
        self.assertEqual(caixa.button(QMessageBox.StandardButton.Cancel).text(), "Cancelar")

    def test_traducao_global_cobre_sim_e_nao(self):
        self.assertIsNotNone(self.tradutor)
        caixa = QMessageBox()
        caixa.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self.assertIn(caixa.button(QMessageBox.StandardButton.Yes).text().replace("&", ""), ("Sim",))
        self.assertIn(caixa.button(QMessageBox.StandardButton.No).text().replace("&", ""), ("Não",))

    def test_modal_tem_fundo_escuro_e_texto_claro(self):
        self.app.setStyleSheet(QSS)
        caixa = QMessageBox(
            QMessageBox.Icon.Question, "Alterações não salvas",
            "O projeto tem alterações não salvas. Deseja salvá-las?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        caixa.show()
        self.app.processEvents()
        rotulo = next(item for item in caixa.findChildren(QLabel) if item.text())
        self.assertEqual(
            caixa.palette().color(QPalette.ColorRole.Window).name(), COR_PAINEL)
        self.assertEqual(
            rotulo.palette().color(QPalette.ColorRole.WindowText).name(), COR_TEXTO)


if __name__ == "__main__":
    unittest.main()
