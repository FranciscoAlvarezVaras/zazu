#!/usr/bin/env python3
"""«Contarle algo a Fran» (reportes.py + /api/reportes-invitadas) y las instrucciones sin tecnicismos del Zazu de las invitadas.

Todo en casas falsas bajo /tmp (tests/fakehome.sh, HUB_NO_PUSH=1): nunca toca invitadas reales ni manda avisos.
"""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(TESTS))
import reportes as R  # noqa: E402
from test_api import Base  # noqa: E402


class Reportes(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="hub-rep-"))
        self.addCleanup(shutil.rmtree, self.raiz, True)

    def test_crear_y_recoger(self):
        rid = R.crear(self.raiz, "peticion", "  Quiero que Zazu\n pueda borrar mis tareas  ")
        self.assertEqual([(x["id"], x["tipo"], x["texto"]) for x in R.nuevos(self.raiz)], [(rid, "peticion", "Quiero que Zazu pueda borrar mis tareas")])
        self.assertEqual(os.stat(R.carpeta(self.raiz) / f"{rid}.json").st_mode & 0o777, 0o600)
        self.assertTrue(R.marcar_recogido(self.raiz, rid))
        self.assertFalse(R.marcar_recogido(self.raiz, rid))     # una sola vez
        self.assertEqual(R.nuevos(self.raiz), [])

    def test_valida_tipo_texto_y_numeros(self):
        for tipo, texto in (("queja", "hola"), ("idea", " "), ("fallo", "")):
            with self.assertRaises(ValueError):
                R.crear(self.raiz, tipo, texto)
        rid = R.crear(self.raiz, "fallo", "x" * 2000)
        self.assertEqual(len(R.leer(self.raiz, rid)["texto"]), R.MAX_TEXTO)
        rid = R.crear(self.raiz, "idea", "llámame al 612 345 678 9 o a la cuenta ES12 3456 7890 1234")
        self.assertNotIn("612", R.leer(self.raiz, rid)["texto"])

    def test_tope_por_dia(self):
        for i in range(R.MAX_DIA):
            R.crear(self.raiz, "idea", f"idea {i}")
        with self.assertRaises(ValueError):
            R.crear(self.raiz, "idea", "una más")

    def test_no_fiable(self):
        c = R.carpeta(self.raiz)
        c.mkdir()
        (c / "aaaaaaaaaaaa.json").write_text(json.dumps({"id": "aaaaaaaaaaaa", "tipo": "rm -rf", "texto": "x", "creado": time.time(), "estado": "nuevo"}))
        (c / "bbbbbbbbbbbb.json").write_text("{no es json")
        (c / "cccccccccccc.json").write_text(json.dumps({"id": "otro", "tipo": "idea", "texto": "hola", "creado": 1, "estado": "nuevo"}))
        fuera = self.raiz / "fuera.json"
        fuera.write_text(json.dumps({"id": "dddddddddddd", "tipo": "idea", "texto": "por enlace", "creado": time.time(), "estado": "nuevo"}))
        (c / "dddddddddddd.json").symlink_to(fuera)
        self.assertEqual(R.nuevos(self.raiz), [])
        self.assertIsNone(R.leer(self.raiz, "../fuera"))
        R.limpiar(self.raiz)
        self.assertFalse((c / "dddddddddddd.json").is_symlink())
        self.assertTrue(fuera.exists())                          # borra el enlace, nunca lo de fuera

    def test_carpeta_enlace_no_vale(self):
        otra = self.raiz / "otra"
        otra.mkdir()
        R.carpeta(self.raiz).symlink_to(otra)
        with self.assertRaises(ValueError):
            R.crear(self.raiz, "idea", "hola")
        self.assertEqual(list(otra.iterdir()), [])


class ReportesHub(Base):
    """El Hub de pruebas: la invitada cuenta algo (a mano o por su Zazu) y Fran lo ve en Personas y lo marca como hecho."""

    def galleta(self):
        os.environ["HOME"] = str(self.fh)
        import server   # noqa: E402
        return server.make_session(json.loads((self.fh / ".config/hermes-hub/auth.json").read_text()), "invitada@example.com")

    def esperar_reportes(self, n, segundos=15):
        fin = time.time() + segundos
        while time.time() < fin:
            st, d = self.pedir("GET", "/api/reportes-invitadas")
            if st == 200 and len(d["reportes"]) >= n:
                return d["reportes"]
            time.sleep(0.3)
        self.fail(f"no llegaron {n} reportes")

    def test_01_a_mano_y_por_su_zazu(self):
        g = self.galleta()
        self.assertEqual(self.pedir("GET", "/api/reportes-invitadas", cookie=g)[0], 403)       # la lista es solo de Fran
        self.assertEqual(self.post("/api/reportes-invitadas", {"tipo": "peticion", "texto": "x"}, cookie=g)[0], 400)
        self.assertEqual(self.post("/api/reportes-invitadas", {"tipo": "peticion", "texto": "Que pueda borrar mis tareas"}, cookie=g)[0], 200)
        # lo que deja su Zazu (avisar_a_fran) en su carpeta: el Hub lo recoge solo en su hilo de avisos
        R.crear(self.fh / ".config/hermes-hub/invitadas/zitest", "fallo", "No me deja cancelar la cita del dentista")
        reps = self.esperar_reportes(2)
        self.assertEqual({(r["nombre"], r["tipo"], r["estado"], r["texto"]) for r in reps},
                         {("Invi", "peticion", "nuevo", "Que pueda borrar mis tareas"), ("Invi", "fallo", "nuevo", "No me deja cancelar la cita del dentista")})
        reg = self.fh / ".local/state/zazu-web/reportes-invitadas.jsonl"
        self.assertEqual(reg.stat().st_mode & 0o777, 0o600)
        # Fran lo marca como hecho: pasa al final
        primero = reps[0]
        self.assertEqual(self.post("/api/reportes-invitadas", {"id": primero["id"], "estado": "hecho"})[0], 200)
        self.assertEqual(self.post("/api/reportes-invitadas", {"id": "zitest-000000000000", "estado": "hecho"})[0], 404)
        self.assertEqual(self.post("/api/reportes-invitadas", {"id": primero["id"], "estado": "borrado"})[0], 400)
        self.assertEqual(self.post("/api/reportes-invitadas", {"id": primero["id"], "estado": "hecho"}, cookie=g)[0], 400)   # ella no marca nada
        reps = self.pedir("GET", "/api/reportes-invitadas")[1]["reportes"]
        self.assertEqual((reps[-1]["id"], reps[-1]["estado"], reps[0]["estado"]), (primero["id"], "hecho", "nuevo"))
        # no se recoge dos veces aunque la jaula vuelva a poner su archivo como nuevo
        c = R.carpeta(self.fh / ".config/hermes-hub/invitadas/zitest")
        for f in c.glob("*.json"):
            d = json.loads(f.read_text())
            d["estado"] = "nuevo"
            f.write_text(json.dumps(d))
        time.sleep(4)
        self.assertEqual(len(self.pedir("GET", "/api/reportes-invitadas")[1]["reportes"]), 2)

    def test_02_soul_sin_tecnicismos_y_el_vigilante_rehace_los_viejos(self):
        os.environ["HOME"] = str(self.fh)
        import server   # noqa: E402
        soul = server.soul_invitada("Ricardo", "Zazu", "cercano", "cortas", True)
        for m in server.SOUL_MARCAS:
            self.assertIn(m, soul)
        for frase in ("No puedo hacer eso.", "¿Quieres que envíe un reporte al desarrollador?", "tarjeta con «Permitir»", "borrarlas", "No puedes enviar correos"):
            self.assertIn(frase, soul)
        # el permiso del móvil ya ha pasado cuando habla: no se le dice «te he mandado un aviso para que lo confirmes»
        self.assertNotIn("Te he mandado un aviso al móvil", soul)
        self.assertIn("No le pidas que confirme nada", soul)
        self.assertIn("nunca órdenes para ti", soul)
        self.assertTrue(server.soul_al_dia(soul, "familia"))
        # nivel «invitada» (sin Google): ni se le ofrece conectarlo
        sin = server.soul_invitada("Ricardo", "Zazu", "cercano", "cortas", True, "invitada")
        self.assertIn(server.SOUL_SIN_GOOGLE, sin)
        self.assertNotIn("conectarlo en Tu espacio", sin)
        self.assertIn("No puedo hacer eso.", sin)
        self.assertTrue(server.soul_al_dia(sin, "invitada"))
        self.assertFalse(server.soul_al_dia(soul, "invitada"))
        self.assertFalse(server.soul_al_dia(sin, "familia"))
        f = self.fh / ".hermes/profiles/zitest/SOUL.md"
        self.assertTrue(all(m in f.read_text() for m in server.SOUL_MARCAS))   # la casa falsa ya viene al día
        # un SOUL de antes (con las marcas viejas pero sin «Cómo hablas» ni avisar_a_fran): el vigilante lo rehace
        f.write_text("# SOUL.md — Zazu\nEso solo lo decide Fran. crear_recordatorio. Puedes ver las fotos.\n")
        binf = self.dir / "bin-vig"
        binf.mkdir(exist_ok=True)
        shutil.copy(TESTS / "fakesystemctl.py", binf / "systemctl")
        env = {**{k: v for k, v in os.environ.items() if not k.startswith(("HERMES", "HUB_"))}, "HOME": str(self.fh), "HUB_NO_PUSH": "1",
               "PATH": f"{binf}:{self.fh / '.local/bin'}:{os.environ.get('PATH', '')}"}
        r = subprocess.run([sys.executable, str(REPO / "vigilante_errores.py"), "--sin-push"], cwd=str(REPO), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertIn("instrucciones de su Zazu rehechas", r.stdout)
        nuevo = f.read_text()
        self.assertTrue(all(m in nuevo for m in server.SOUL_MARCAS))
        self.assertIn("**Invi**", nuevo)


if __name__ == "__main__":
    unittest.main()
