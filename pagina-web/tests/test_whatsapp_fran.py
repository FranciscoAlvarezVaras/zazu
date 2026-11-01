#!/usr/bin/env python3
"""«Vincular / Desconectar mi WhatsApp» de Fran (whatsapp_fran.py y /api/whatsapp-fran), con wacli y systemctl FALSOS
(tests/fakewacli.py, tests/fakesystemctl.py): nunca habla con WhatsApp ni toca wacli-sync de verdad. Todo bajo /tmp.

    python3 -m unittest tests.test_whatsapp_fran -v"""
import base64, hashlib, hmac, json, os, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(TESTS))
import whatsapp_fran as WF  # noqa: E402
import test_api  # noqa: E402

FAKE_WACLI, FAKE_SC = str(TESTS / "fakewacli.py"), str(TESTS / "fakesystemctl.py")


def esperar(cond, segundos=20):
    fin = time.time() + segundos
    while time.time() < fin:
        r = cond()
        if r:
            return r
        time.sleep(0.2)
    raise AssertionError("no llegó a la condición")


class Unidad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.casa = Path(self.tmp.name)
        if not str(self.casa.resolve()).startswith("/tmp/"):
            self.skipTest("solo bajo /tmp")
        self.home0 = os.environ.get("HOME")
        os.environ["HOME"] = str(self.casa)   # el systemctl falso anota en $HOME/systemctl.log
        self.store = self.casa / ".local/state/wacli"
        self.store.mkdir(parents=True)
        (self.store / "sesion").write_text("34600111222")          # su WhatsApp de antes (falso)
        (self.store / "wacli.db").write_text("mensajes de antes")
        self.cambios = []
        WF.configurar(store=self.store, respaldos=self.casa / "Respaldos", estado_json=self.casa / "fran/whatsapp.json", wacli=FAKE_WACLI,
                      systemctl=[FAKE_SC, "--user"], al_cambiar=lambda: self.cambios.append(1))

    def tearDown(self):
        WF.cancelar()
        os.environ["HOME"] = self.home0
        self.tmp.cleanup()

    def sc(self):
        p = self.casa / "systemctl.log"
        return [json.loads(l)["args"] for l in p.read_text().splitlines()] if p.exists() else []

    def test_vincular_bien_mueve_la_vieja_a_respaldos(self):
        st = WF.vincular("34611222333")
        self.assertEqual((st["emparejando"], st["codigo"], st["telefono"]), ("esperando", "ABCD-EFGH", "34611222333"))
        self.assertTrue(0 < st["caduca_en"] <= WF.VALE)
        self.assertEqual(self.sc(), [])   # mientras empareja, wacli-sync sigue funcionando
        self.assertEqual((self.store / "sesion").read_text(), "34600111222")
        esperar(lambda: WF.estado()["emparejando"] == "conectado")
        self.assertEqual(self.sc(), [["--user", "stop", "wacli-sync"], ["--user", "enable", "wacli-sync"], ["--user", "restart", "wacli-sync"]])
        self.assertEqual((self.store / "sesion").read_text(), "34611222333")   # la nueva en su sitio
        self.assertFalse(WF._nueva().exists())
        copias = list((self.casa / "Respaldos").iterdir())
        self.assertEqual(len(copias), 1)
        self.assertTrue(copias[0].name.startswith("whatsapp-fran-antes-"))
        self.assertEqual((copias[0] / "wacli.db").read_text(), "mensajes de antes")
        e = WF.estado()
        self.assertEqual((e["numero"], e["respaldo"], e["codigo"]), ("2333", copias[0].name, None))
        self.assertEqual(self.cambios, [1])

    def test_falla_deja_todo_como_estaba(self):
        st = WF.vincular("34611222000")   # el falso «no lo completa»
        self.assertEqual(st["codigo"], "ABCD-EFGH")
        esperar(lambda: WF.estado()["emparejando"] == "error")
        self.assertIn("código nuevo", WF.estado()["error"])
        self.assertEqual(self.sc(), [])   # ni se paró
        self.assertEqual((self.store / "sesion").read_text(), "34600111222")
        self.assertFalse(WF._nueva().exists())
        self.assertFalse((self.casa / "Respaldos").exists())
        self.assertEqual(self.cambios, [])

    def test_cancelar_y_otro_numero(self):
        st = WF.vincular("34611222999")   # nadie escribe el código
        self.assertEqual(st["codigo"], "ABCD-EFGH")
        p1 = WF._V["proc"]
        self.assertEqual(WF.vincular("34611222999")["codigo"], "ABCD-EFGH")   # el mismo número: sigue el mismo
        self.assertIs(WF._V["proc"], p1)
        WF.vincular("34611222999", nuevo=True)                                   # «Pedir otro código»: empieza otra vez
        self.assertIsNot(WF._V["proc"], p1)
        self.assertIsNotNone(p1.poll())
        p2 = WF._V["proc"]
        self.assertTrue(WF.cancelar())
        self.assertIsNotNone(p2.poll())
        self.assertFalse(WF._nueva().exists())
        self.assertIsNone(WF.estado()["emparejando"])
        time.sleep(0.5)
        self.assertEqual(self.sc(), [])
        self.assertEqual((self.store / "sesion").read_text(), "34600111222")

    def test_desconectar_con_copia(self):
        b, ok = WF.desconectar()
        self.assertTrue(ok is False)   # el falso solo «cierra» si hay session.db; aquí no hay: no se intenta
        self.assertEqual(self.sc(), [["--user", "stop", "wacli-sync"], ["--user", "disable", "wacli-sync"]])
        self.assertTrue(b.name.startswith("whatsapp-fran-desconectado-"))
        self.assertEqual((b / "wacli.db").read_text(), "mensajes de antes")
        self.assertTrue(self.store.is_dir() and not any(self.store.iterdir()))   # vacía: «sin vincular»
        self.assertEqual(WF.estado()["desconectado"], time.strftime("%Y-%m-%d"))
        # y vincular otra vez lo vuelve a encender
        WF.vincular("34611222333")
        esperar(lambda: WF.estado()["emparejando"] == "conectado")
        self.assertEqual(self.sc()[-2:], [["--user", "enable", "wacli-sync"], ["--user", "restart", "wacli-sync"]])
        self.assertEqual(len(list((self.casa / "Respaldos").iterdir())), 1)   # la carpeta vacía no se copia
        self.assertIsNone(WF.estado()["desconectado"])

    def test_desconectar_cierra_sesion(self):
        (self.store / "session.db").write_text("x")
        b, ok = WF.desconectar()
        self.assertTrue(ok)
        self.assertFalse((b / "sesion").exists())   # logout antes de copiar

    def test_desconectar_sin_parar_no_toca_nada(self):
        os.environ["FAKE_SC_FALLA"] = "stop"
        try:
            with self.assertRaises(RuntimeError):
                WF.desconectar()
        finally:
            os.environ.pop("FAKE_SC_FALLA", None)
        self.assertEqual(self.sc(), [["--user", "stop", "wacli-sync"]])   # ni disable ni logout
        self.assertEqual((self.store / "wacli.db").read_text(), "mensajes de antes")
        self.assertFalse((self.casa / "Respaldos").exists())

    def test_vinculado_sin_arrancar_lo_dice_y_se_arranca(self):
        os.environ["FAKE_SC_FALLA"] = "enable,restart"
        try:
            WF.vincular("34611222333")
            esperar(lambda: WF.estado()["emparejando"] == "conectado")
        finally:
            os.environ.pop("FAKE_SC_FALLA", None)
        self.assertTrue(WF.estado()["parado"])   # no dice «¡Conectado!» a secas: falta ponerlo en marcha
        (self.store / "session.db").write_text("x")
        self.assertTrue(WF.arrancar())
        self.assertEqual(self.sc()[-2:], [["--user", "enable", "wacli-sync"], ["--user", "restart", "wacli-sync"]])
        self.assertFalse(WF.estado()["parado"])

    def test_arrancar_sin_vincular(self):
        with self.assertRaises(ValueError):
            WF.arrancar()
        self.assertEqual(self.sc(), [])

    def test_sin_systemctl_no_hace_nada(self):
        WF.configurar(store=self.store, respaldos=self.casa / "Respaldos", estado_json=self.casa / "w.json", wacli=FAKE_WACLI, systemctl=None)
        with self.assertRaises(RuntimeError):
            WF.vincular("34611222333")
        with self.assertRaises(RuntimeError):
            WF.desconectar()
        self.assertEqual(self.sc(), [])


class PorLaApp(test_api.Base):
    """/api/whatsapp-fran en el Hub de pruebas (casa falsa), como lo usaría Fran desde la APK."""
    @classmethod
    def entorno(cls, puerto, gw):
        e = super().entorno(puerto, gw)
        e.update(HUB_WACLI=FAKE_WACLI, HUB_SYSTEMCTL=FAKE_SC)
        return e

    def galleta(self, email):
        cfg = json.loads((self.fh / ".config/hermes-hub/auth.json").read_text())
        body = f"{int(time.time()) + 3600}.{base64.urlsafe_b64encode(email.encode()).decode().rstrip('=')}.abcdef"
        return f"{body}.{hmac.new(bytes.fromhex(cfg['session_key']), body.encode(), hashlib.sha256).hexdigest()}"

    def test_flujo(self):
        yo, ella = self.galleta("cuenta.principal@example.com"), self.galleta("invitada@example.com")
        store = self.fh / ".local/state/wacli"
        store.mkdir(parents=True, exist_ok=True)
        (store / "sesion").write_text("34600111222")
        # solo Fran (LOGIN_EMAILS): ni una invitada ni «dev»
        self.assertEqual(self.pedir("GET", "/api/whatsapp-fran", cookie=ella)[0], 403)
        self.assertEqual(self.post("/api/whatsapp-fran", {"accion": "desconectar"}, cookie=ella)[0], 403)
        self.assertEqual(self.pedir("GET", "/api/whatsapp-fran")[0], 403)
        st, d = self.pedir("GET", "/api/whatsapp-fran", cookie=yo)
        self.assertEqual((st, d["emparejando"]), (200, None), d)
        self.assertEqual(self.post("/api/whatsapp-fran", {"accion": "vincular", "telefono": "+34 600"}, cookie=yo)[0], 400)
        self.assertEqual(self.post("/api/whatsapp-fran", {"accion": "otra"}, cookie=yo)[0], 400)
        st, d = self.post("/api/whatsapp-fran", {"accion": "vincular", "telefono": "+34 611 222 333"}, cookie=yo)
        self.assertEqual((st, d["codigo"], d["telefono"]), (200, "ABCD-EFGH", "34611222333"), d)
        d = esperar(lambda: (x := self.pedir("GET", "/api/whatsapp-fran", cookie=yo)[1])["emparejando"] == "conectado" and x)
        self.assertEqual(d["numero"], "2333")
        self.assertEqual((store / "sesion").read_text(), "34611222333")
        self.assertEqual(len(list((self.fh / "Respaldos").iterdir())), 1)
        log = [json.loads(l)["args"] for l in (self.fh / "systemctl.log").read_text().splitlines()]
        self.assertEqual(log, [["--user", "stop", "wacli-sync"], ["--user", "enable", "wacli-sync"], ["--user", "restart", "wacli-sync"]])
        st, d = self.post("/api/whatsapp-fran", {"accion": "desconectar"}, cookie=yo)
        self.assertEqual(st, 200, d)
        self.assertTrue(d["copia"].startswith("whatsapp-fran-desconectado-"))
        self.assertFalse(any(store.iterdir()))


if __name__ == "__main__":
    unittest.main()
