import unittest
from fractions import Fraction

from core import tempo


class TesteTempo(unittest.TestCase):
    def test_fps_fracionario_sem_erro_acumulado(self):
        fps = Fraction(30000, 1001)
        # 1001 segundos a 30000/1001 fps = exatamente 30000 frames
        self.assertEqual(tempo.segundos_para_frames(1001, fps), 30000)
        self.assertEqual(tempo.frames_para_segundos(30000, fps), Fraction(1001))

    def test_modos_de_arredondamento(self):
        fps = Fraction(30)
        self.assertEqual(tempo.segundos_para_frames(Fraction(1, 7), fps, "piso"), 4)
        self.assertEqual(tempo.segundos_para_frames(Fraction(1, 7), fps, "teto"), 5)
        self.assertEqual(tempo.segundos_para_frames(Fraction(1, 7), fps), 4)
        self.assertEqual(tempo.segundos_para_frames(0.5, fps), 15)

    def test_timecode_ida_e_volta(self):
        fps = Fraction(25)
        for frames in (0, 1, 24, 25, 3599 * 25 + 7, 90_000):
            tc = tempo.formatar_timecode(frames, fps)
            self.assertEqual(tempo.interpretar_timecode(tc, fps), frames)

    def test_formato_timecode(self):
        self.assertEqual(tempo.formatar_timecode(0, Fraction(30)), "00:00:00:00")
        self.assertEqual(tempo.formatar_timecode(30 * 3661 + 5, Fraction(30)), "01:01:01:05")

    def test_timecode_invalido(self):
        with self.assertRaises(ValueError):
            tempo.interpretar_timecode("abc", Fraction(30))
        with self.assertRaises(ValueError):
            tempo.interpretar_timecode("00:00:00:30", Fraction(30))
        with self.assertRaises(ValueError):
            tempo.criar_fps(0)


if __name__ == "__main__":
    unittest.main()
