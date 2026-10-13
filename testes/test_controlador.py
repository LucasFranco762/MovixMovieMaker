import tempfile
import unittest
from pathlib import Path

from core.configuracoes import ArmazenamentoJson, Configuracoes
from core.constantes import (
    EFEITO_DESFOQUE, EFEITO_SEPIA, FAIXA_AUDIO, TIPO_AUDIO, TIPO_VIDEO,
    TIPO_TEXTO, TRANSICAO_DISSOLVER,
)
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

    def test_alterar_volume_e_remover_clipe_de_audio(self):
        self.c.adicionar_midia_na_timeline("ma")
        clipe = self.c.projeto.faixas[1].clipes[0]
        self.c.alterar_clipe(clipe.id, volume=0.35)
        self.assertEqual(clipe.volume, 0.35)
        self.c.remover_clipe(clipe.id)
        with self.assertRaises(KeyError):
            self.c.projeto.localizar_clipe(clipe.id)
        self.c.desfazer()
        self.assertEqual(self.c.projeto.localizar_clipe(clipe.id)[1].volume, 0.35)

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

    def test_aplicar_remover_e_desfazer_efeitos_no_clipe_selecionado(self):
        self.c.adicionar_midia_na_timeline("mv")
        clipe = self.c.projeto.faixas[0].clipes[0]
        self.c.selecionar([clipe.id])
        self.c.aplicar_efeito(EFEITO_SEPIA, 65)
        self.c.aplicar_efeito(EFEITO_DESFOQUE, 80)
        self.assertEqual(clipe.efeitos, {EFEITO_SEPIA: 65, EFEITO_DESFOQUE: 80})
        with self.assertRaises(ErroEdicao):
            self.c.aplicar_efeito(EFEITO_SEPIA, 65)
        self.c.aplicar_efeito(EFEITO_SEPIA, 40)
        self.assertEqual(clipe.efeitos[EFEITO_SEPIA], 40)
        self.c.remover_efeito(EFEITO_SEPIA)
        self.assertEqual(clipe.efeitos, {EFEITO_DESFOQUE: 80})
        self.c.desfazer()
        self.assertEqual(clipe.efeitos, {EFEITO_SEPIA: 40, EFEITO_DESFOQUE: 80})

    def test_efeito_exige_um_clipe_visual(self):
        with self.assertRaises(ErroEdicao):
            self.c.aplicar_efeito(EFEITO_SEPIA)

    def test_criar_editar_remover_e_desfazer_texto(self):
        texto = self.c.salvar_elemento_texto(
            tipo=TIPO_TEXTO, conteudo="Meu título", duracao_segundos=2,
            familia_fonte="Segoe UI", tamanho_fonte=64, cor_texto="#ffffff",
            cor_fundo_texto="#00000000", alinhamento_h="center", alinhamento_v="middle")
        self.assertEqual((texto.tipo, texto.duracao, texto.conteudo),
                         (TIPO_TEXTO, 60, "Meu título"))
        self.assertEqual(self.c.selecao.ids, (texto.id,))
        faixa_texto, _ = self.c.projeto.localizar_clipe(texto.id)
        self.assertNotEqual(faixa_texto.id, self.c.projeto.faixas[0].id)
        self.c.salvar_elemento_texto(
            tipo=TIPO_TEXTO, conteudo="Título alterado", duracao_segundos=3,
            familia_fonte="Arial", tamanho_fonte=80, cor_texto="#ff0000",
            cor_fundo_texto="#00000000", alinhamento_h="left", alinhamento_v="top",
            clipe_id=texto.id)
        self.assertEqual((texto.conteudo, texto.duracao, texto.alinhamento_v),
                         ("Título alterado", 90, "top"))
        self.c.remover_elemento_texto(texto.id)
        with self.assertRaises(KeyError):
            self.c.projeto.localizar_clipe(texto.id)
        self.c.desfazer()
        self.assertEqual(self.c.projeto.localizar_clipe(texto.id)[1].conteudo, "Título alterado")

    def test_texto_vazio_e_rejeitado(self):
        with self.assertRaises(ErroEdicao):
            self.c.salvar_elemento_texto(
                tipo=TIPO_TEXTO, conteudo="  ", duracao_segundos=2,
                familia_fonte="Arial", tamanho_fonte=48, cor_texto="#ffffff",
                cor_fundo_texto="#00000000", alinhamento_h="center",
                alinhamento_v="middle")
        self.c.adicionar_midia_na_timeline("ma")
        clipe_audio = self.c.projeto.faixas[1].clipes[0]
        self.c.selecionar([clipe_audio.id])
        with self.assertRaises(ErroEdicao):
            self.c.aplicar_efeito(EFEITO_SEPIA)


if __name__ == "__main__":
    unittest.main()
