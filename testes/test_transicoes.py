import unittest

from core.constantes import (
    TRANSICAO_IRIS_CIRCULAR,
    TRANSICAO_VARREDURA_DIAGONAL,
    TRANSICAO_VARREDURA_HORIZONTAL,
    TRANSICAO_VARREDURA_VERTICAL,
)
from multimidia.motor_mlt import _criar_mapa_luma


class TesteMapasLuma(unittest.TestCase):
    def test_mapas_sao_pgm_validos_com_a_dimensao_pedida(self):
        tipos = (
            TRANSICAO_VARREDURA_HORIZONTAL,
            TRANSICAO_VARREDURA_VERTICAL,
            TRANSICAO_VARREDURA_DIAGONAL,
            TRANSICAO_IRIS_CIRCULAR,
        )
        for tipo in tipos:
            dados = _criar_mapa_luma(tipo, 8)
            cabecalho, pixels = dados.split(b"255\n", 1)
            self.assertEqual(cabecalho, b"P5\n8 8\n")
            self.assertEqual(len(pixels), 64)
            self.assertEqual((min(pixels), max(pixels)), (0, 255))

    def test_varreduras_crescem_na_direcao_correta(self):
        horizontal = _criar_mapa_luma(TRANSICAO_VARREDURA_HORIZONTAL, 4).split(b"255\n", 1)[1]
        vertical = _criar_mapa_luma(TRANSICAO_VARREDURA_VERTICAL, 4).split(b"255\n", 1)[1]
        self.assertEqual(list(horizontal[:4]), [0, 85, 170, 255])
        self.assertEqual(list(vertical[::4]), [0, 85, 170, 255])


if __name__ == "__main__":
    unittest.main()
