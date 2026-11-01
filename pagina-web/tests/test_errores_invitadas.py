"""Registro de errores de las invitadas: el Traceback se resume en su última línea y los errores conocidos se marcan."""
import sqlite3, sys, tempfile, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import errores_invitadas as E  # noqa: E402


class Errores(unittest.TestCase):
    def test_traceback_da_su_ultima_linea_y_se_reconoce(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "logs").mkdir()
            ahora = time.strftime("%Y-%m-%d %H:%M:%S")
            (Path(d) / "logs/mcp-stderr.log").write_text(
                f"{ahora},1 Traceback (most recent call last):\n"
                f"{ahora},1   File \"x.py\", line 1, in <module>\n"
                f"{ahora},1 FileNotFoundError: [Errno 2] No such file: '/home/x/zazu/scripts/noticias.py'\n")
            r = E._hermes("p", d, time.time() - 60)
            self.assertEqual(len(r), 1)
            self.assertTrue(r[0]["detalle"].startswith("FileNotFoundError"))
            self.assertIn("arreglado", E.conocido(r[0]["detalle"]))
        self.assertIsNone(E.conocido("algo nuevo que nadie conoce"))


class LimpiarAgenda(unittest.TestCase):
    def test_dos_consultas_no_chocan_por_el_titulo(self):
        """Hermes exige títulos únicos: limpiar dos consultas de la agenda no puede fallar ni dejar sus mensajes."""
        import server
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "state.db"
            c = sqlite3.connect(db)
            c.executescript("create table sessions(id text primary key, title text, hidden int, message_count int);"
                            "create unique index t on sessions(title) where title is not null;"
                            "create table messages(id integer primary key, session_id text, content text);"
                            "insert into sessions values('a',null,0,1),('b',null,0,1);"
                            "insert into messages(session_id,content) values('a','x'),('b','y');")
            c.commit(); c.close()
            fallos = []
            antes = server.prof_dir, server._ac_anotar
            server.prof_dir, server._ac_anotar = (lambda p: Path(d)), (lambda *a: fallos.append(a))
            try:
                server.agenda_limpiar_sesion("zi", "a")
                server.agenda_limpiar_sesion("zi", "b")
            finally:
                server.prof_dir, server._ac_anotar = antes
            c = sqlite3.connect(db)
            self.assertEqual(fallos, [])
            self.assertEqual(c.execute("select count(*) from messages").fetchone()[0], 0)
            self.assertEqual(c.execute("select count(*) from sessions where hidden=1").fetchone()[0], 2)
            c.close()


if __name__ == "__main__":
    unittest.main()
