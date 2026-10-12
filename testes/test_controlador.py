import tempfile
import unittest
from pathlib import Path

from core.configuracoes import ArmazenamentoJson, Configuracoes
from core.constantes import FAIXA_AUDIO, TIPO_AUDIO, TIPO_VIDEO, TRANSICAO_DISSOLVER
from core.controlador import Controlador
from core.eventos import PROJETO_ALTERADO, PROJETO_CARREGADO, SELECAO_ALTERADA
from core.excecoes import ErroEdicao
from projetos.modelos import MidiaRef


class TesteControlador(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.c = Controlador(Configuracoes(ArmazenamentoJson(self.dir / "c.json")))
        self.c.novo_projeto()
        self.c.projeto.midias["mv"] = MidiaRef("mv", "v.mp4", TIPO_VIDEO, "v.mp4", 90, tem_video=True)
        self.c.projeto.midias["ma"] = MidiaRef("ma", "a.mp3", TIPO_AUDIO, "a.mp3", 120, tem_audio=True)
        self.eventos: list[str] = []
        for e in (PROJETO_ALTERADO, PROJETO_CARREGADO, SELECAO_ALTERADA):
            self.c.eventos.assinar(e, lambda e=e: self.eventos.append(e))

    def tearDown(self):
        self._tmp.cleanup()

    def test_fluxo_adicionar_dividir_mover_desfazer(self):
        self.c.adicionar_midia_na_timeline("mv")
        self.c.adicionar_midia_na_timeline("ma", 10)
        v, a = self.c.projeto.faixas
        self.assertEqual((len(v.clipes), len(a.clipes)), (1, 1))
        clip = v.clipes[0]
        self.c.selecionar([clip.id])
        self.c.ir_para(30)
        self.assertEqual(self.c.dividir_selecionados_na_posicao(), 1)
        self.assertEqual(len(v.clipes), 2)
        self.c.mover_clipe(v.clipes[1].id, 200)
        self.assertEqual(v.clipes[1].inicio, 200)
        self.c.desfazer(); self.c.desfazer()
        self.assertEqual((len(v.clipes), v.clipes[0].duracao), (1, 90))
        self.assertIn(PROJETO_ALTERADO, self.eventos)
        self.assertTrue(self.c.gerenciador.modificado)

    def test_excluir_poda_selecao(self):
        self.c.adicionar_midia_na_timeline("mv")
        cid = self.c.projeto.faixas[0].clipes[0].id
        self.c.selecionar([cid])
        self.c.excluir_selecionados()
        self.assertEqual(len(self.c.selecao), 0)

    def test_dividir_sem_selecao_ou_fora_do_clipe(self):
        with self.assertRaises(ErroEdicao):
            self.c.dividir_selecionados_na_posicao()
        self.c.adicionar_midia_na_timeline("mv")
        self.c.selecionar([self.c.projeto.faixas[0].clipes[0].id])
        self.c.ir_para(0)
        with self.assertRaises(ErroEdicao):
            self.c.dividir_selecionados_na_posicao()

    def test_sem_faixa_compativel_livre(self):
        self.c.adicionar_midia_na_timeline("mv", 0)
        with self.assertRaises(ErroEdicao):
            self.c.adicionar_midia_na_timeline("mv", 10)
        self.c.adicionar_faixa("video")
        self.c.adicionar_midia_na_timeline("mv", 10)
        self.assertEqual(len(self.c.projeto.faixas[2].clipes), 1)

    def test_salvar_abrir_recupera_timeline(self):
        self.c.adicionar_midia_na_timeline("mv", 5)
        self.c.adicionar_midia_na_timeline("ma", 0)
        self.c.alterar_faixa(self.c.projeto.faixas[0].id, nome="Principal", cor="#123456")
        destino = self.c.salvar_projeto(self.dir / "p.mmproj")
        antes = self.c.projeto.para_dict()
        outro = Controlador(Configuracoes(ArmazenamentoJson(self.dir / "c2.json")))
        outro.abrir_projeto(destino)
        depois = outro.projeto.para_dict()
        for m in antes["midias"] + depois["midias"]:
            m.pop("caminho_relativo", None)            # só difere por ser preenchido ao salvar
        self.assertEqual(antes["faixas"], depois["faixas"])
        self.assertFalse(outro.gerenciador.modificado)
        self.assertFalse(outro.historico.pode_desfazer())

    def test_ir_para_limita_ao_intervalo(self):
        self.c.adicionar_midia_na_timeline("mv")
        self.c.ir_para(-10)
        self.assertEqual(self.c.posicao, 0)
        self.c.ir_para(10_000)
        self.assertEqual(self.c.posicao, 90)

    def test_importar_sem_ffmpeg_informa_erro(self):
        self.assertEqual(len(self.c.importar_midias(["x.mp4"])), 1)

    def test_audio_sobreposto_cria_nova_faixa_e_mixagem_e_desfeita(self):
        self.c.adicionar_midia_na_timeline("ma", 0)
        self.c.adicionar_midia_na_timeline("ma", 10, criar_faixa_se_necessario=True)
        faixas_audio = [f for f in self.c.projeto.faixas if f.tipo == FAIXA_AUDIO]
        self.assertEqual(len(faixas_audio), 2)
        self.c.configurar_mixagem_audio(0, 1)
        self.assertEqual((self.c.projeto.mixagem_audio.volume_original,
                          self.c.projeto.mixagem_audio.volume_adicionado), (0.0, 1.0))
        self.c.desfazer()
        self.assertEqual(self.c.projeto.mixagem_audio.volume_original, 1.0)

    def test_aplicar_transicao_pela_selecao_e_remover(self):
        self.c.adicionar_midia_na_timeline("mv", 0)
        self.c.adicionar_midia_na_timeline("mv", 90)
        clipes = self.c.projeto.faixas[0].clipes
        self.c.selecionar([clipes[0].id, clipes[1].id])
        transicao = self.c.aplicar_transicao(TRANSICAO_DISSOLVER, 1.0)
        self.assertEqual(transicao.duracao, 30)
        self.assertEqual(clipes[1].inicio, 60)
        self.c.remover_transicao(transicao.id)
        self.assertEqual(clipes[1].inicio, 90)

    def test_aplicar_transicao_no_corte_sob_o_cursor(self):
        self.c.adicionar_midia_na_timeline("mv", 0)
        self.c.adicionar_midia_na_timeline("mv", 90)
        self.c.ir_para(90)
        self.c.aplicar_transicao(TRANSICAO_DISSOLVER, 0.5)
        self.assertEqual(self.c.projeto.faixas[0].clipes[1].inicio, 75)


if __name__ == "__main__":
    unittest.main()
