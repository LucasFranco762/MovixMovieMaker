import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from core.configuracoes import ArmazenamentoJson, Configuracoes
from core.constantes import TIPO_LEGENDA
from core.controlador import Controlador
from editor.legendas import gerar_srt, interpretar_srt


SRT = """1
00:00:01,000 --> 00:00:02,500
Primeira legenda

2
00:00:03,250 --> 00:00:05,000
Segunda
linha
"""


class TesteFormatoSrt(unittest.TestCase):
    def test_interpretar_blocos_e_multiplas_linhas(self):
        self.assertEqual(interpretar_srt(SRT), [
            (1000, 2500, "Primeira legenda"),
            (3250, 5000, "Segunda\nlinha"),
        ])

    def test_rejeitar_intervalo_invalido(self):
        with self.assertRaises(ValueError):
            interpretar_srt("1\n00:00:02,000 --> 00:00:01,000\nInválida")


class TesteFluxoLegendas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.c = Controlador(Configuracoes(ArmazenamentoJson(self.pasta / "cfg.json")))
        self.c.novo_projeto()

    def tearDown(self):
        self.tmp.cleanup()

    def test_importar_editar_exportar_e_remover(self):
        origem = self.pasta / "entrada.srt"
        origem.write_text(SRT, encoding="utf-8")
        self.assertEqual(self.c.importar_legendas_srt(origem), 2)
        legendas = [c for f in self.c.projeto.faixas for c in f.clipes
                    if c.tipo == TIPO_LEGENDA]
        self.assertEqual([(c.inicio, c.duracao) for c in legendas], [(30, 45), (98, 52)])
        self.assertEqual(legendas[1].conteudo, "Segunda\nlinha")

        destino = self.pasta / "saida.srt"
        self.assertEqual(self.c.exportar_legendas_srt(destino), 2)
        restauradas = interpretar_srt(destino.read_text(encoding="utf-8-sig"))
        self.assertEqual(restauradas[0], (1000, 2500, "Primeira legenda"))

        self.c.remover_elemento_texto(legendas[0].id)
        restantes = [c for f in self.c.projeto.faixas for c in f.clipes
                      if c.tipo == TIPO_LEGENDA]
        self.assertEqual(len(restantes), 1)

    def test_gerar_srt_vazio(self):
        self.assertEqual(gerar_srt([], Fraction(30, 1)), "")


if __name__ == "__main__":
    unittest.main()
