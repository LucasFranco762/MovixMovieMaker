import unittest

from core.constantes import (
    FAIXA_AUDIO, FAIXA_VIDEO, TIPO_AUDIO, TIPO_VIDEO, TRANSICAO_DISSOLVER,
)
from core.excecoes import ErroEdicao
from editor.clipes import criar_clipe
from editor.comandos import (
    AdicionarClipe, AdicionarFaixa, AdicionarTransicao, AlterarClipe, AlterarFaixa,
    AlterarMixagemAudio, DividirClipe, HistoricoComandos, MoverClipe, RemoverClipe,
    RemoverTransicao,
)
from editor.faixas import criar_faixa
from editor.selecao import Selecao
from projetos.modelos import MidiaRef, Projeto, Transicao


class BaseEdicao(unittest.TestCase):
    def setUp(self):
        self.p = Projeto.novo()
        self.v1, self.a1 = self.p.faixas
        self.mv = MidiaRef("mv", "v.mp4", TIPO_VIDEO, "v.mp4", 100, tem_video=True, tem_audio=True)
        self.ma = MidiaRef("ma", "a.mp3", TIPO_AUDIO, "a.mp3", 200, tem_audio=True)
        self.p.midias.update({"mv": self.mv, "ma": self.ma})
        self.h = HistoricoComandos()

    def add_video(self, inicio=0):
        c = criar_clipe(self.mv, inicio)
        self.h.executar(self.p, AdicionarClipe(self.v1.id, c))
        return c


class TesteAdicionarEMover(BaseEdicao):
    def test_adicionar_e_desfazer_refazer(self):
        c = self.add_video(5)
        self.assertEqual(self.v1.clipes, [c])
        self.h.desfazer(self.p)
        self.assertEqual(self.v1.clipes, [])
        self.h.refazer(self.p)
        self.assertEqual(self.v1.clipes, [c])

    def test_sobreposicao_na_mesma_faixa_e_rejeitada(self):
        self.add_video(0)
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, AdicionarClipe(self.v1.id, criar_clipe(self.mv, 50)))
        self.assertEqual(len(self.v1.clipes), 1)
        self.assertFalse(self.h.pode_refazer())

    def test_sobrepor_em_outra_faixa_de_video(self):
        self.add_video(0)
        v2 = criar_faixa(self.p, FAIXA_VIDEO)
        self.h.executar(self.p, AdicionarFaixa(v2))
        self.h.executar(self.p, AdicionarClipe(v2.id, criar_clipe(self.mv, 50)))
        self.assertEqual(len(v2.clipes), 1)

    def test_tipo_incompativel_com_faixa(self):
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, AdicionarClipe(self.a1.id, criar_clipe(self.mv, 0)))
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, AdicionarClipe(self.v1.id, criar_clipe(self.ma, 0)))

    def test_faixa_bloqueada_impede_edicao(self):
        c = self.add_video(0)
        self.h.executar(self.p, AlterarFaixa(self.v1.id, bloqueada=True))
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, MoverClipe(c.id, 10))
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, RemoverClipe(c.id))
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, DividirClipe(c.id, 10))
        self.assertEqual((c.inicio, c.duracao), (0, 100))

    def test_mover_na_mesma_faixa_e_entre_faixas(self):
        c = self.add_video(0)
        self.h.executar(self.p, MoverClipe(c.id, 30))
        self.assertEqual(c.inicio, 30)
        v2 = criar_faixa(self.p, FAIXA_VIDEO)
        self.h.executar(self.p, AdicionarFaixa(v2))
        self.h.executar(self.p, MoverClipe(c.id, 5, v2.id))
        self.assertEqual((self.v1.clipes, v2.clipes), ([], [c]))
        self.h.desfazer(self.p)
        self.assertEqual((self.v1.clipes, v2.clipes), ([c], []))
        self.assertEqual(c.inicio, 30)
        self.h.desfazer(self.p)          # desfaz a criação da faixa v2
        self.assertEqual(self.p.faixas, [self.v1, self.a1])
        self.h.desfazer(self.p)          # desfaz o primeiro movimento
        self.assertEqual(c.inicio, 0)

    def test_mover_para_frame_negativo_ou_sobre_outro(self):
        a = self.add_video(0)
        b = self.add_video(100)
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, MoverClipe(a.id, -1))
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, MoverClipe(b.id, 50))
        self.assertEqual((a.inicio, b.inicio), (0, 100))

    def test_mover_dentro_de_si_mesmo_e_permitido(self):
        c = self.add_video(0)
        self.h.executar(self.p, MoverClipe(c.id, 10))   # sobrepõe a própria posição antiga
        self.assertEqual(c.inicio, 10)


class TesteDividir(BaseEdicao):
    def test_divisao_preserva_continuidade_na_midia(self):
        c = self.add_video(10)
        c.entrada = 20; c.duracao = 60                    # trecho 20..80 da mídia
        self.h.executar(self.p, DividirClipe(c.id, 40))
        esq, dir_ = self.v1.clipes
        self.assertEqual((esq.inicio, esq.duracao, esq.entrada), (10, 30, 20))
        self.assertEqual((dir_.inicio, dir_.duracao, dir_.entrada), (40, 30, 50))
        self.assertEqual(esq.entrada + esq.duracao, dir_.entrada)    # sem perda nem repetição
        self.assertEqual(esq.fim, dir_.inicio)

    def test_desfazer_refazer_divisao_mantem_ids(self):
        c = self.add_video(0)
        cmd = DividirClipe(c.id, 40)
        self.h.executar(self.p, cmd)
        self.h.desfazer(self.p)
        self.assertEqual(len(self.v1.clipes), 1)
        self.assertEqual(self.v1.clipes[0].duracao, 100)
        self.h.refazer(self.p)
        self.assertEqual([x.id for x in self.v1.clipes], [c.id, cmd.novo_clipe_id])

    def test_divisao_nas_extremidades_e_rejeitada(self):
        c = self.add_video(0)
        for frame in (0, 100, -5, 200):
            with self.assertRaises(ErroEdicao):
                self.h.executar(self.p, DividirClipe(c.id, frame))
        self.assertEqual(len(self.v1.clipes), 1)

    def test_original_da_midia_nunca_e_alterado(self):
        c = self.add_video(0)
        self.h.executar(self.p, DividirClipe(c.id, 40))
        self.assertEqual(self.mv.duracao_frames, 100)
        self.assertEqual(self.mv.caminho, "v.mp4")


class TesteTransicoes(BaseEdicao):
    def setUp(self):
        super().setUp()
        self.a = self.add_video(0)
        self.b = self.add_video(100)
        self.c = self.add_video(200)

    def transicao(self, origem=None, destino=None, duracao=20):
        return Transicao(
            "t1", self.v1.id, (origem or self.a).id, (destino or self.b).id,
            TRANSICAO_DISSOLVER, duracao,
        )

    def test_aplicar_encurta_timeline_e_desfazer_refazer(self):
        transicao = self.transicao()
        self.h.executar(self.p, AdicionarTransicao(transicao))
        self.assertEqual((self.b.inicio, self.c.inicio, self.p.duracao_frames), (80, 180, 280))
        self.assertEqual(self.p.transicoes, [transicao])

        self.h.desfazer(self.p)
        self.assertEqual((self.b.inicio, self.c.inicio, self.p.duracao_frames), (100, 200, 300))
        self.assertEqual(self.p.transicoes, [])
        self.h.refazer(self.p)
        self.assertEqual((self.b.inicio, self.c.inicio), (80, 180))

    def test_remover_e_desfazer_remocao(self):
        transicao = self.transicao()
        self.h.executar(self.p, AdicionarTransicao(transicao))
        self.h.executar(self.p, RemoverTransicao(transicao.id))
        self.assertEqual((self.b.inicio, self.c.inicio), (100, 200))
        self.assertEqual(self.p.transicoes, [])
        self.h.desfazer(self.p)
        self.assertEqual((self.b.inicio, self.c.inicio), (80, 180))
        self.assertEqual(self.p.transicoes, [transicao])

    def test_multiplas_transicoes_preservam_sobreposicoes(self):
        self.h.executar(self.p, AdicionarTransicao(self.transicao()))
        segunda = Transicao(
            "t2", self.v1.id, self.b.id, self.c.id, TRANSICAO_DISSOLVER, 10)
        self.h.executar(self.p, AdicionarTransicao(segunda))
        self.assertEqual((self.a.inicio, self.b.inicio, self.c.inicio), (0, 80, 170))
        self.assertEqual(self.p.duracao_frames, 270)

    def test_rejeita_duracao_excessiva_e_clipes_nao_consecutivos(self):
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, AdicionarTransicao(self.transicao(duracao=51)))
        with self.assertRaises(ErroEdicao):
            self.h.executar(self.p, AdicionarTransicao(self.transicao(self.a, self.c)))

    def test_clipe_com_transicao_nao_pode_ser_movido_dividido_ou_excluido(self):
        self.h.executar(self.p, AdicionarTransicao(self.transicao()))
        for comando in (MoverClipe(self.a.id, 10), DividirClipe(self.a.id, 30),
                        RemoverClipe(self.a.id)):
            with self.assertRaises(ErroEdicao):
                self.h.executar(self.p, comando)


class TesteHistoricoEPropriedades(BaseEdicao):
    def test_alterar_clipe_e_desfazer(self):
        c = self.add_video(0)
        self.h.executar(self.p, AlterarClipe(c.id, nome="Novo", cor="#00ff00"))
        self.assertEqual((c.nome, c.cor), ("Novo", "#00ff00"))
        self.h.desfazer(self.p)
        self.assertEqual((c.nome, c.cor), ("v.mp4", None))

    def test_volume_e_mixagem_tem_limites_e_desfazer(self):
        c = self.add_video(0)
        self.h.executar(self.p, AlterarClipe(c.id, volume=3))
        self.assertEqual(c.volume, 2.0)
        self.h.executar(self.p, AlterarMixagemAudio(
            volume_original=0, volume_adicionado=0.75))
        self.assertEqual((self.p.mixagem_audio.volume_original,
                          self.p.mixagem_audio.volume_adicionado), (0.0, 0.75))
        self.h.desfazer(self.p)
        self.assertEqual((self.p.mixagem_audio.volume_original,
                          self.p.mixagem_audio.volume_adicionado), (1.0, 1.0))

    def test_propriedade_invalida(self):
        c = self.add_video(0)
        with self.assertRaises(ErroEdicao):
            AlterarClipe(c.id, inicio=3)
        with self.assertRaises(ErroEdicao):
            AlterarFaixa(self.v1.id, tipo="audio")

    def test_nova_acao_limpa_refazer(self):
        self.add_video(0)
        self.h.desfazer(self.p)
        self.assertTrue(self.h.pode_refazer())
        self.add_video(0)
        self.assertFalse(self.h.pode_refazer())

    def test_remover_e_restaurar(self):
        c = self.add_video(0)
        self.h.executar(self.p, RemoverClipe(c.id))
        self.assertEqual(self.v1.clipes, [])
        self.h.desfazer(self.p)
        self.assertEqual(self.v1.clipes, [c])

    def test_selecao_poda_clipes_removidos(self):
        c = self.add_video(0)
        s = Selecao()
        s.definir([c.id, c.id, "fantasma"])
        self.assertEqual(len(s), 2)
        s.podar(self.p)
        self.assertEqual(s.ids, (c.id,))
        s.alternar(c.id)
        self.assertEqual(len(s), 0)


if __name__ == "__main__":
    unittest.main()
