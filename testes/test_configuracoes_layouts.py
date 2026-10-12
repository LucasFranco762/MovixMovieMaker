import tempfile
import unittest
from pathlib import Path

from core import layouts
from core.configuracoes import ArmazenamentoJson, Configuracoes
from core.constantes import LAYOUT_CLASSICO, LAYOUT_EDICAO_AVANCADA, LAYOUT_FOCO_VIDEO


class TesteConfiguracoes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self._tmp.name) / "sub" / "cfg.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_persistencia_entre_instancias(self):
        c = Configuracoes(ArmazenamentoJson(self.arq))
        c.definir("layout.atual", LAYOUT_FOCO_VIDEO)
        c2 = Configuracoes(ArmazenamentoJson(self.arq))
        self.assertEqual(c2.obter("layout.atual"), LAYOUT_FOCO_VIDEO)

    def test_padroes(self):
        c = Configuracoes(ArmazenamentoJson(self.arq))
        self.assertEqual(c.obter("layout.atual"), LAYOUT_CLASSICO)
        self.assertEqual(c.obter("inexistente", 7), 7)

    def test_arquivo_corrompido_usa_padroes(self):
        self.arq.parent.mkdir(parents=True)
        self.arq.write_text("{{{", encoding="utf-8")
        c = Configuracoes(ArmazenamentoJson(self.arq))
        self.assertEqual(c.obter("layout.atual"), LAYOUT_CLASSICO)
        self.assertTrue(self.arq.with_suffix(".corrompido").exists())


class TesteLayouts(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Configuracoes(ArmazenamentoJson(Path(self._tmp.name) / "c.json"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_padroes_diferem_por_layout(self):
        foco = layouts.carregar_estado(self.config, LAYOUT_FOCO_VIDEO)
        avanc = layouts.carregar_estado(self.config, LAYOUT_EDICAO_AVANCADA)
        classico = layouts.carregar_estado(self.config, LAYOUT_CLASSICO)
        self.assertFalse(foco.painel_aberto)
        self.assertTrue(classico.painel_aberto)
        self.assertGreater(avanc.altura_timeline, classico.altura_timeline)
        self.assertLess(foco.altura_timeline, classico.altura_timeline)

    def test_estado_e_independente_por_layout(self):
        est = layouts.carregar_estado(self.config, LAYOUT_CLASSICO)
        est.largura_painel = 333
        est.timeline_recolhida = True
        layouts.salvar_estado(self.config, LAYOUT_CLASSICO, est)
        outro = layouts.carregar_estado(self.config, LAYOUT_EDICAO_AVANCADA)
        self.assertNotEqual(outro.largura_painel, 333)
        self.assertFalse(outro.timeline_recolhida)
        # e sobrevive a reabrir o programa
        nova = Configuracoes(ArmazenamentoJson(Path(self._tmp.name) / "c.json"))
        de_novo = layouts.carregar_estado(nova, LAYOUT_CLASSICO)
        self.assertEqual((de_novo.largura_painel, de_novo.timeline_recolhida), (333, True))

    def test_layout_desconhecido(self):
        with self.assertRaises(KeyError):
            layouts.carregar_estado(self.config, "nao_existe")


if __name__ == "__main__":
    unittest.main()
