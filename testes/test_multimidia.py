"""Testes de metadados. Os que usam FFmpeg real são pulados se ele não existir."""
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from core.constantes import TIPO_AUDIO, TIPO_IMAGEM, TIPO_VIDEO
from core.excecoes import DependenciaAusenteError, MidiaInvalidaError
from multimidia.metadados import analisar_midia, interpretar_taxa, montar_midia
from multimidia.motor_ffmpeg import MotorFFmpeg

FPS = Fraction(30)


class TesteMontarMidia(unittest.TestCase):
    def test_video_com_audio(self):
        info = {"format": {"duration": "10.0"},
                "streams": [{"codec_type": "video", "width": 1280, "height": 720},
                            {"codec_type": "audio"}]}
        m = montar_midia(info, Path("x.mp4"), FPS)
        self.assertEqual((m.tipo, m.duracao_frames, m.largura, m.tem_audio), (TIPO_VIDEO, 300, 1280, True))

    def test_audio_com_capa_e_audio(self):
        info = {"format": {"duration": "2.0"},
                "streams": [{"codec_type": "audio"},
                            {"codec_type": "video", "disposition": {"attached_pic": 1}}]}
        m = montar_midia(info, Path("m.mp3"), FPS)
        self.assertEqual((m.tipo, m.duracao_frames, m.tem_video), (TIPO_AUDIO, 60, False))

    def test_imagem_nao_tem_duracao(self):
        info = {"format": {}, "streams": [{"codec_type": "video", "width": 10, "height": 20}]}
        m = montar_midia(info, Path("f.png"), FPS)
        self.assertEqual((m.tipo, m.duracao_frames, m.altura), (TIPO_IMAGEM, 0, 20))

    def test_sem_streams_utilizaveis(self):
        with self.assertRaises(MidiaInvalidaError):
            montar_midia({"format": {}, "streams": [{"codec_type": "data"}]}, Path("x.mp4"), FPS)

    def test_video_sem_duracao(self):
        with self.assertRaises(MidiaInvalidaError):
            montar_midia({"format": {}, "streams": [{"codec_type": "video"}]}, Path("x.mp4"), FPS)

    def test_interpretar_taxa(self):
        self.assertEqual(interpretar_taxa("30000/1001"), Fraction(30000, 1001))
        self.assertIsNone(interpretar_taxa("0/0"))
        self.assertIsNone(interpretar_taxa(None))
        self.assertIsNone(interpretar_taxa("abc"))


try:
    _MOTOR = MotorFFmpeg()
except DependenciaAusenteError:
    _MOTOR = None


@unittest.skipIf(_MOTOR is None, "FFmpeg não disponível neste ambiente")
class TesteFFmpegReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        d = Path(cls._tmp.name)
        cls.video = d / "teste áudio e vídeo.mp4"        # espaço e Unicode no caminho
        cls.audio = d / "tom.wav"
        base = [_MOTOR.ffmpeg, "-y", "-v", "error"]
        subprocess.run(base + ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=2",
                               "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                               "-shortest", "-pix_fmt", "yuv420p", str(cls.video)], check=True)
        subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(cls.audio)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_analisa_video(self):
        m = analisar_midia(_MOTOR, self.video, FPS)
        self.assertEqual(m.tipo, TIPO_VIDEO)
        self.assertEqual((m.largura, m.altura), (320, 240))
        self.assertTrue(m.tem_audio)
        self.assertIn(m.duracao_frames, range(58, 63))

    def test_analisa_audio(self):
        m = analisar_midia(_MOTOR, self.audio, FPS)
        self.assertEqual(m.tipo, TIPO_AUDIO)
        self.assertIn(m.duracao_frames, range(29, 32))

    def test_arquivo_inexistente_e_corrompido(self):
        with self.assertRaises(MidiaInvalidaError):
            analisar_midia(_MOTOR, self.video.with_name("nao_existe.mp4"), FPS)
        ruim = self.video.with_name("lixo.mp4")
        ruim.write_bytes(b"isso nao e um video")
        with self.assertRaises(MidiaInvalidaError):
            analisar_midia(_MOTOR, ruim, FPS)

    def test_formato_nao_previsto(self):
        with self.assertRaises(MidiaInvalidaError):
            analisar_midia(_MOTOR, self.video.with_suffix(".xyz"), FPS)

    def test_miniatura_e_encoders(self):
        mini = _MOTOR.gerar_miniatura(self.video, self.video.parent / "mini.jpg", 0.5, 160)
        self.assertGreater(mini.stat().st_size, 0)
        self.assertIsInstance(_MOTOR.listar_encoders(), set)
        self.assertTrue(_MOTOR.versao())


if __name__ == "__main__":
    unittest.main()
