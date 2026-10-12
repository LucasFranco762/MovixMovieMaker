"""Prova de conceito MLT + FFmpeg + PyQt6 (REQ-004, 6.1) — rodar NO WINDOWS.

Uso (PowerShell, na pasta MovixMovieMaker, com o ambiente virtual ativo):

    python ferramentas\\prova_conceito.py
    python ferramentas\\prova_conceito.py --saida C:\\temp\\poc --reproduzir-audio

Gera mídias sintéticas com o FFmpeg, executa os 10 passos do REQ-004 6.1 e grava
``relatorio_poc.json`` e ``relatorio_poc.txt``. Cada passo termina como:

    APROVADO   - verificado automaticamente por este script
    MANUAL     - executado, mas exige conferência humana (som/imagem)
    FALHOU     - erro (com diagnóstico)
    NAO_EXECUTADO - dependência anterior ausente

Nada aqui é considerado validado até você enviar o relatório de volta.
Este script NÃO troca de motor silenciosamente: se o MLT falhar, os passos que
dependem dele falham com o diagnóstico.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.excecoes import ErroMovieMaker  # noqa: E402
from multimidia.motor_ffmpeg import MotorFFmpeg  # noqa: E402
from multimidia.motor_mlt import formato_imagem_rgba, importar_mlt, inicializar_mlt  # noqa: E402

APROVADO, MANUAL, FALHOU, NAO_EXEC = "APROVADO", "MANUAL", "FALHOU", "NAO_EXECUTADO"


@dataclass
class Resultado:
    passo: int
    nome: str
    status: str = NAO_EXEC
    detalhe: str = ""


class Poc:
    def __init__(self, saida: Path, reproduzir_audio: bool) -> None:
        self.saida = saida
        self.saida.mkdir(parents=True, exist_ok=True)
        self.reproduzir_audio = reproduzir_audio
        self.resultados = [Resultado(i, n) for i, n in enumerate([
            "", "Importação das bibliotecas (PyQt6, mlt, FFmpeg)", "Instanciação do MLT",
            "Abertura de um arquivo de vídeo", "Reprodução com áudio", "Navegação temporal",
            "Integração do vídeo ao PyQt6", "Dois clipes em sequência",
            "Transição simples (luma/mix)", "Composição com áudio", "Exportação funcional",
        ])][1:]
        self.ff: MotorFFmpeg | None = None
        self.mlt = None
        self.perfil = None
        self.clipe_a = self.clipe_b = None

    def r(self, n: int) -> Resultado:
        return self.resultados[n - 1]

    def passo(self, n: int, funcao) -> None:
        res = self.r(n)
        try:
            status, detalhe = funcao()
            res.status, res.detalhe = status, detalhe
        except Exception as exc:  # noqa: BLE001 - o objetivo é diagnosticar
            res.status = FALHOU
            res.detalhe = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"
        print(f"[{res.passo:>2}] {res.status:<14} {res.nome}")
        if res.status == FALHOU:
            print("     " + res.detalhe.splitlines()[0])

    # ---- geração de mídias ---------------------------------------------------------
    def gerar_midias(self) -> None:
        ff = self.ff.ffmpeg
        base = [ff, "-y", "-v", "error"]
        for nome, src, freq in (("a.mp4", "testsrc", 440), ("b.mp4", "smptebars", 660)):
            subprocess.run(base + [
                "-f", "lavfi", "-i", f"{src}=size=640x360:rate=30:duration=4",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=4",
                "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
                str(self.saida / nome)], check=True)

    # ---- passos ----------------------------------------------------------------------
    def p1(self):
        partes, falhas = [], []
        try:
            import PyQt6.QtCore as qc
            partes.append(f"PyQt6 {qc.PYQT_VERSION_STR}")
        except ImportError as exc:
            falhas.append(f"PyQt6 ausente: {exc}")
        try:
            self.ff = MotorFFmpeg()
            partes.append(self.ff.versao())
        except ErroMovieMaker as exc:
            falhas.append(str(exc))
        try:
            self.mlt = importar_mlt()
            partes.append(f"módulo MLT: {self.mlt.__name__}")
        except ErroMovieMaker as exc:
            falhas.append(str(exc))
        if self.ff is not None:
            self.gerar_midias()
        if falhas:
            raise RuntimeError(" | ".join(falhas) + (f" (OK: {'; '.join(partes)})" if partes else ""))
        return APROVADO, "; ".join(partes)

    def p2(self):
        inicializar_mlt(self.mlt)
        self.perfil = self.mlt.Profile("atsc_720p_30")
        return APROVADO, f"Factory.init OK; perfil {self.perfil.width()}x{self.perfil.height()}"

    def p3(self):
        mlt = self.mlt
        self.clipe_a = mlt.Producer(self.perfil, str(self.saida / "a.mp4"))
        self.clipe_b = mlt.Producer(self.perfil, str(self.saida / "b.mp4"))
        if not (self.clipe_a.is_valid() and self.clipe_b.is_valid()):
            raise RuntimeError("Producer inválido (módulo avformat ausente?)")
        return APROVADO, f"a.mp4 com {self.clipe_a.get_length()} frames; b.mp4 com {self.clipe_b.get_length()}"

    def p4(self):
        mlt = self.mlt
        if not self.reproduzir_audio:
            return NAO_EXEC, "Use --reproduzir-audio para tocar 2 s de áudio e conferir o som."
        consumidor = mlt.Consumer(self.perfil, "sdl2_audio")
        if not consumidor.is_valid():
            raise RuntimeError("Consumidor 'sdl2_audio' indisponível neste MLT (necessário para tocar áudio).")
        consumidor.set("video_off", "1")
        consumidor.connect(self.clipe_a)
        self.clipe_a.seek(0)
        consumidor.start()
        time.sleep(2)
        consumidor.stop()
        return MANUAL, "Tocaram 2 s de áudio (tom de 440 Hz)? Confirme manualmente."

    def p5(self):
        p = self.clipe_a
        posicoes = []
        for alvo in (0, 60, 119, 30):
            p.seek(alvo)
            posicoes.append(p.position())
        if posicoes != [0, 60, 119, 30]:
            raise RuntimeError(f"seek inconsistente: {posicoes}")
        return APROVADO, "seek para 0, 60, 119 e 30 retornou as posições corretas"

    def p6(self):
        from PyQt6.QtGui import QGuiApplication, QImage
        mlt = self.mlt
        app = QGuiApplication.instance() or QGuiApplication([])
        self.clipe_a.seek(45)
        quadro = self.clipe_a.get_frame()
        largura, altura = 640, 360
        dados = quadro.get_image(formato_imagem_rgba(mlt), largura, altura)
        imagem = QImage(bytes(dados), largura, altura, largura * 4, QImage.Format.Format_RGBA8888).copy()
        destino = self.saida / "quadro_qimage.png"
        if imagem.isNull() or not imagem.save(str(destino)):
            raise RuntimeError("QImage nula ou não foi possível salvar.")
        soma = sum(imagem.pixelColor(x, y).red() for x in range(0, largura, 40) for y in range(0, altura, 40))
        if soma == 0:
            raise RuntimeError("Quadro totalmente preto: get_image provavelmente retornou dados inválidos.")
        del app
        return MANUAL, f"Quadro 45 convertido em QImage e salvo em {destino}. Abra e confira a imagem."

    def _sequencia(self):
        mlt = self.mlt
        a = mlt.Producer(self.perfil, str(self.saida / "a.mp4"))
        b = mlt.Producer(self.perfil, str(self.saida / "b.mp4"))
        playlist = mlt.Playlist(self.perfil)
        playlist.append(a, 0, 119)
        playlist.append(b, 0, 119)
        return playlist

    def p7(self):
        pl = self._sequencia()
        total = pl.get_playtime()
        if total != 240:
            raise RuntimeError(f"duração esperada 240 frames, obtida {total}")
        pl.seek(119); f1 = pl.get_frame()
        pl.seek(120); f2 = pl.get_frame()
        return APROVADO, f"playlist de 240 frames; frame 119 e 120 lidos (fronteira entre clipes) sem erro"

    def _com_transicao(self, frames_transicao: int = 30):
        mlt = self.mlt
        pl = mlt.Playlist(self.perfil)
        a = mlt.Producer(self.perfil, str(self.saida / "a.mp4"))
        b = mlt.Producer(self.perfil, str(self.saida / "b.mp4"))
        pl.append(a, 0, 119)
        pl.append(b, 0, 119)
        # mix(clip_index, length) cria a dissolução com sobreposição entre clipes consecutivos
        resultado = pl.mix(0, frames_transicao, mlt.Transition(self.perfil, "luma"))
        if resultado != 0:
            raise RuntimeError(f"Playlist.mix retornou {resultado}")
        return pl

    def p8(self):
        pl = self._com_transicao(30)
        total = pl.get_playtime()
        if total != 240 - 30:
            raise RuntimeError(f"com 30 frames de transição esperava 210, obteve {total}")
        return APROVADO, "Playlist.mix com 'luma' reduziu a duração de 240 para 210 frames (sobreposição correta)"

    def p9(self):
        mlt = self.mlt
        pl = self._com_transicao(30)
        tractor = mlt.Tractor(self.perfil)
        tractor.multitrack().connect(pl, 0)
        # Trilha de áudio extra (a.mp4 em outra faixa) misturada com mix
        extra = mlt.Producer(self.perfil, str(self.saida / "a.mp4"))
        tractor.multitrack().connect(extra, 1)
        mix = mlt.Transition(self.perfil, "mix")
        mix.set("always_active", 1)
        tractor.plant_transition(mix, 0, 1)
        if tractor.get_playtime() <= 0:
            raise RuntimeError("tractor sem duração")
        self.tractor = tractor
        return APROVADO, f"tractor com 2 faixas e transição 'mix' ({tractor.get_playtime()} frames)"

    def p10(self):
        mlt = self.mlt
        destino = self.saida / "exportado.mp4"
        destino.unlink(missing_ok=True)
        consumidor = mlt.Consumer(self.perfil, "avformat", str(destino))
        if not consumidor.is_valid():
            raise RuntimeError("Consumidor 'avformat' indisponível.")
        consumidor.set("vcodec", "libx264")
        consumidor.set("acodec", "aac")
        consumidor.connect(self.tractor)
        consumidor.run()
        consumidor.stop()
        info = self.ff.sondar(destino)
        tipos = {s["codec_type"] for s in info["streams"]}
        duracao = float(info["format"]["duration"])
        if not {"video", "audio"} <= tipos:
            raise RuntimeError(f"arquivo exportado sem vídeo+áudio: {tipos}")
        if abs(duracao - 7.0) > 0.25:
            raise RuntimeError(f"duração exportada {duracao:.2f}s; esperado ~7,0 s")
        return MANUAL, (f"{destino.name}: {duracao:.2f}s com vídeo e áudio (verificado via ffprobe). "
                        "Reproduza e confira a transição e a sincronia.")

    def executar(self) -> None:
        self.passo(1, self.p1)
        for n, f in ((2, self.p2), (3, self.p3), (4, self.p4), (5, self.p5), (6, self.p6),
                     (7, self.p7), (8, self.p8), (9, self.p9), (10, self.p10)):
            if self.mlt is None or self.perfil is None and n > 2:
                self.r(n).detalhe = "Depende dos passos 1-2."
                print(f"[{n:>2}] {NAO_EXEC:<14} {self.r(n).nome}")
                continue
            self.passo(n, f)

    def relatorio(self) -> None:
        (self.saida / "relatorio_poc.json").write_text(
            json.dumps([asdict(r) for r in self.resultados], ensure_ascii=False, indent=2), encoding="utf-8")
        linhas = [f"[{r.passo:>2}] {r.status:<14} {r.nome}\n     {r.detalhe}" for r in self.resultados]
        (self.saida / "relatorio_poc.txt").write_text("\n".join(linhas), encoding="utf-8")
        print(f"\nRelatório gravado em {self.saida}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Prova de conceito MLT + FFmpeg (Windows).")
    ap.add_argument("--saida", type=Path, default=Path(tempfile.gettempdir()) / "moviemaker_poc")
    ap.add_argument("--reproduzir-audio", action="store_true", help="toca 2 s de áudio (passo 4)")
    args = ap.parse_args()
    try:
        poc = Poc(args.saida, args.reproduzir_audio)
        poc.executar()
        poc.relatorio()
    except (ErroMovieMaker, subprocess.CalledProcessError) as exc:
        print(f"Erro: {exc}")
        return 2
    return 0 if all(r.status in (APROVADO, MANUAL) for r in poc.resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
