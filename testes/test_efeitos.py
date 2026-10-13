import unittest

from core.constantes import (
    EFEITO_BRILHO,
    EFEITO_DESFOQUE,
    EFEITO_ESCALA_CINZA,
    EFEITO_INVERTER,
    EFEITO_SEPIA,
)
from multimidia.motor_mlt import _filtro_efeito


class TesteIntensidadeEfeitos(unittest.TestCase):
    def test_zero_e_estado_neutro_e_cem_e_intensidade_total(self):
        self.assertEqual(_filtro_efeito(EFEITO_ESCALA_CINZA, 0)[1]["av.s"], "1.0000")
        self.assertEqual(_filtro_efeito(EFEITO_ESCALA_CINZA, 100)[1]["av.s"], "0.0000")
        self.assertEqual(_filtro_efeito(EFEITO_BRILHO, 0)[1]["level"], "1.0000")
        self.assertEqual(_filtro_efeito(EFEITO_BRILHO, 100)[1]["level"], "1.3500")
        self.assertEqual(_filtro_efeito(EFEITO_DESFOQUE, 50)[1]["hradius"], "4.00")

    def test_todos_os_efeitos_produzem_configuracao_em_qualquer_intensidade(self):
        for tipo in (
            EFEITO_ESCALA_CINZA, EFEITO_SEPIA, EFEITO_INVERTER,
            EFEITO_DESFOQUE, EFEITO_BRILHO,
        ):
            for intensidade in (0, 35, 100):
                servico, propriedades = _filtro_efeito(tipo, intensidade)
                self.assertTrue(servico)
                self.assertTrue(propriedades)


if __name__ == "__main__":
    unittest.main()
