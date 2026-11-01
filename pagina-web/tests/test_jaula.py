"""La jaula del Hermes de una invitada (jaula.py): qué ve y qué no. Sin ejecutar nada: solo mira la orden de bubblewrap.

    python3 -m unittest tests.test_jaula
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jaula  # noqa: E402

H = str(Path.home())


def montajes(a):
    """[(tipo, origen, destino)] de los --bind/--ro-bind de la orden."""
    out, i = [], 0
    while i < len(a):
        if a[i] in ("--bind", "--ro-bind", "--ro-bind-try"):
            out.append((a[i], a[i + 1], a[i + 2]))
            i += 3
        else:
            i += 1
    return out


class Jaula(unittest.TestCase):
    def tearDown(self):   # argv() crea las carpetas propias del perfil: las de la prueba no se quedan
        import shutil
        for d in (".config/hermes-hub/invitadas", ".local/share/holazazu", ".local/share/holazazu-jaula"):
            shutil.rmtree(Path(H) / d / "zijaulatest", ignore_errors=True)

    def test_solo_perfiles_de_invitada(self):
        for malo in ("default", "tecnico", "zi", "zi/../tecnico", "ziNURIA", "", None):
            with self.assertRaises(ValueError):
                jaula.argv(malo)

    def test_la_casa_de_fran_esta_vacia_y_solo_se_monta_lo_suyo(self):
        a = jaula.argv("zijaulatest")
        self.assertEqual(a[:5], ["/usr/bin/bwrap", "--ro-bind", "/", "/", "--tmpfs"])
        self.assertEqual(a[5], H)
        for d in ("/run/user", "/srv", "/var/www", "/tmp"):
            self.assertIn(d, a[a.index("--tmpfs"):])
        escritura = {o for t, o, _ in montajes(a) if t == "--bind"}
        for o in escritura:
            self.assertTrue(o.startswith((f"{H}/.hermes/profiles/zijaulatest", f"{H}/.config/hermes-hub/invitadas/zijaulatest",
                                          f"{H}/.local/share/holazazu/zijaulatest", f"{H}/.local/share/holazazu-jaula/zijaulatest"))
                            or o.endswith("/.leases"), o)
        todo = " ".join(o for _, o, _ in montajes(a))
        for prohibido in ("Cerebro", "auth.json", "users.json", ".hermes/.env", "profiles/tecnico", "profiles/zinuria", ".ssh", "Documentos"):
            self.assertNotIn(prohibido, todo)
        self.assertIn("--clearenv", a)
        self.assertIn("--unshare-pid", a)

    def test_unidad_envuelve_el_execstart(self):
        u = jaula.unidad("zijaulatest", '"/x/hermes" "--profile" "zijaulatest" "gateway" "run"')
        self.assertIn("ExecStart=\n", u)
        self.assertIn("jaula.py zijaulatest \"/x/hermes\"", u)
        self.assertIn("KillMode=control-group", u)


if __name__ == "__main__":
    unittest.main()
