import json
import tempfile
import time
import unittest
from pathlib import Path

from core.configuracoes import ArmazenamentoJson, Configuracoes
from core.constantes import MAX_VERSOES_HISTORICO, TIPO_VIDEO
from core.excecoes import ErroSalvamento, ProjetoIncompativelError, ProjetoInvalidoError
from editor.clipes import criar_clipe
from projetos import recuperacao
from projetos.gerenciamento import GerenciadorProjetos
from projetos.modelos import MidiaRef, Projeto
from projetos.salvamento import carregar_projeto, listar_versoes, salvar_projeto


def projeto_exemplo() -> Projeto:
    p = Projeto.novo("Exemplo")
    m = MidiaRef("m1", "C:/vídeos/ação 1.mp4", TIPO_VIDEO, "ação 1.mp4", 300, 1920, 1080, True, True)
    p.midias[m.id] = m
    c = criar_clipe(m, 10)
    c.cor = "#ff0000"
    p.faixas[0].clipes.append(c)
    p.faixas[0].bloqueada = True
    return p


class TesteSerializacao(unittest.TestCase):
    def test_ida_e_volta_preserva_tudo(self):
        p = projeto_exemplo()
        q = Projeto.de_dict(json.loads(json.dumps(p.para_dict())))
        self.assertEqual(p.para_dict(), q.para_dict())
        self.assertEqual(q.faixas[0].clipes[0].cor, "#ff0000")
        self.assertTrue(q.faixas[0].bloqueada)

    def test_versao_futura_e_incompativel(self):
        d = projeto_exemplo().para_dict()
        d["versao_formato"] = 999
        with self.assertRaises(ProjetoIncompativelError):
            Projeto.de_dict(d)

    def test_estrutura_invalida(self):
        with self.assertRaises(ProjetoInvalidoError):
            Projeto.de_dict([])
        with self.assertRaises(ProjetoInvalidoError):
            Projeto.de_dict({"versao_formato": 1})
        d = projeto_exemplo().para_dict()
        d["midias"][0]["tipo"] = "xyz"
        with self.assertRaises(ProjetoInvalidoError):
            Projeto.de_dict(d)

    def test_duracao_total(self):
        self.assertEqual(projeto_exemplo().duracao_frames, 310)


class TesteSalvamento(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_salvar_e_carregar_com_caminho_unicode_e_espaco(self):
        destino = self.dir / "meu projeto ação" / "p.mmproj"
        salvar_projeto(projeto_exemplo(), destino)
        self.assertEqual(carregar_projeto(destino).nome, "Exemplo")
        self.assertEqual([f.name for f in destino.parent.iterdir() if f.suffix == ".mmtmp"], [])

    def test_historico_de_versoes_e_limite(self):
        destino = self.dir / "p.mmproj"
        for i in range(MAX_VERSOES_HISTORICO + 5):
            p = projeto_exemplo()
            p.nome = f"v{i}"
            salvar_projeto(p, destino)
        versoes = listar_versoes(destino)
        self.assertEqual(len(versoes), MAX_VERSOES_HISTORICO)
        self.assertEqual(len({v.name for v in versoes}), MAX_VERSOES_HISTORICO)  # nomes únicos

    def test_arquivo_corrompido_nao_derruba(self):
        destino = self.dir / "ruim.mmproj"
        destino.write_text("{ não é json", encoding="utf-8")
        with self.assertRaises(ProjetoInvalidoError):
            carregar_projeto(destino)

    def test_falha_de_escrita_preserva_arquivo_anterior(self):
        destino = self.dir / "p.mmproj"
        salvar_projeto(projeto_exemplo(), destino)
        antes = destino.read_text(encoding="utf-8")
        # Um diretório no lugar do destino força falha em os.replace
        ruim = self.dir / "dir.mmproj"
        ruim.mkdir()
        with self.assertRaises(ErroSalvamento):
            salvar_projeto(projeto_exemplo(), ruim)
        self.assertEqual(destino.read_text(encoding="utf-8"), antes)
        self.assertEqual(list(self.dir.glob(".tmp_*")), [])

    def test_recuperacao_apos_falha(self):
        destino = self.dir / "p.mmproj"
        salvar_projeto(projeto_exemplo(), destino)
        self.assertFalse(recuperacao.existe_recuperacao(destino))
        time.sleep(0.05)
        novo = projeto_exemplo()
        novo.nome = "Não salvo"
        recuperacao.gravar_autossalvamento(novo, destino)
        self.assertTrue(recuperacao.existe_recuperacao(destino))
        self.assertEqual(recuperacao.recuperar(destino).nome, "Não salvo")
        recuperacao.descartar_autossalvamento(destino)
        self.assertFalse(recuperacao.existe_recuperacao(destino))


class TesteGerenciador(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.config = Configuracoes(ArmazenamentoJson(self.dir / "cfg.json"))
        self.g = GerenciadorProjetos(self.config)

    def tearDown(self):
        self._tmp.cleanup()

    def test_midia_ausente_e_religacao(self):
        self.g.projeto = projeto_exemplo()
        self.assertEqual(len(self.g.midias_ausentes()), 1)
        real = self.dir / "real.mp4"
        real.write_bytes(b"x")
        self.g.religar_midia("m1", real)
        self.assertEqual(self.g.midias_ausentes(), [])

    def test_caminho_relativo_resolve_apos_mover_pasta(self):
        pasta = self.dir / "a"
        pasta.mkdir()
        (pasta / "v.mp4").write_bytes(b"x")
        p = Projeto.novo()
        p.midias["m"] = MidiaRef("m", str(pasta / "v.mp4"), TIPO_VIDEO, "v.mp4", 30)
        self.g.projeto = p
        self.g.salvar(pasta / "p.mmproj")
        nova = self.dir / "b"
        pasta.rename(nova)                      # "projeto portátil" movido de lugar
        g2 = GerenciadorProjetos(self.config)
        g2.abrir(nova / "p.mmproj")
        self.assertEqual(g2.midias_ausentes(), [])

    def test_recentes_sem_duplicatas(self):
        self.g.projeto = projeto_exemplo()
        self.g.salvar(self.dir / "a.mmproj")
        self.g.salvar(self.dir / "b.mmproj")
        self.g.salvar(self.dir / "a.mmproj")
        rec = self.config.projetos_recentes()
        self.assertEqual(len(rec), 2)
        self.assertTrue(rec[0].endswith("a.mmproj"))


if __name__ == "__main__":
    unittest.main()
