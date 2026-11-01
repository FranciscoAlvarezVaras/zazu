#!/usr/bin/env python3
"""El Google de las invitadas desde su Zazu (mcp_google.py): tareas por listas, agenda, correo, borradores y «contárselo a Fran».

Se lanza el MCP de verdad (un proceso, por stdio, como lo lanza Hermes) con una casa falsa bajo /tmp y el gog FALSO (tests/fakegog.py).
La casa NO tiene ~/.hermes/.env, igual que la jaula de la invitada (antes eso tumbaba todas sus herramientas de Google).
Los permisos del móvil los contesta la prueba (aprobaciones.py), como haría ella con «Permitir» / «Rechazar».

    python3 -m unittest tests.test_google_invitadas -v      (TMPDIR bajo /tmp)"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import aprobaciones  # noqa: E402
import reportes  # noqa: E402
# Textos de mcp_google (los rellena setUpClass). NUNCA «import mcp_google» aquí: importaría server con la casa DE VERDAD
# antes que las demás pruebas (unittest discover carga todos los módulos primero) y esas escribirían en el ~ real.
P, HERRAMIENTAS = "", ()

TAREAS = [{"id": "tpan0001", "title": "Comprar pan", "status": "needsAction", "due": "2026-11-05T00:00:00.000Z"},
          {"id": "tluz0001", "title": "Pagar la luz", "status": "needsAction"},
          {"id": "thecha01", "title": "Llamar al médico", "status": "completed"}]
TAREAS_RICARDO = [{"id": "tric0001", "title": "Recoger a Ricardo", "status": "needsAction"},
                  {"id": "tric0002", "title": "Cumple de Ricardo", "status": "needsAction", "notes": "comprar regalo"}]
LISTAS = [{"id": "principal", "title": "Mis tareas"}, {"id": "listaricardo", "title": "Ricardo"}]
EVENTOS = [{"id": "evdent001", "summary": "Dentista", "location": "Calle Mayor 3", "status": "confirmed",
            "start": {"dateTime": "2026-11-03T10:00:00+01:00"}, "end": {"dateTime": "2026-11-03T10:45:00+01:00"}},
           {"id": "evyoga01_20261104T170000Z", "recurringEventId": "evyoga01", "summary": "Yoga", "status": "confirmed",
            "start": {"dateTime": "2026-11-04T18:00:00+01:00"}, "end": {"dateTime": "2026-11-04T19:00:00+01:00"},
            "originalStartTime": {"dateTime": "2026-11-04T18:00:00+01:00"}},
           {"id": "evyoga01_20261111T170000Z", "recurringEventId": "evyoga01", "summary": "Yoga", "status": "confirmed",
            "start": {"dateTime": "2026-11-11T18:00:00+01:00"}, "end": {"dateTime": "2026-11-11T19:00:00+01:00"},
            "originalStartTime": {"dateTime": "2026-11-11T18:00:00+01:00"}},
           {"id": "evcumple1", "summary": "Cumple de Ana", "status": "confirmed", "start": {"date": "2026-11-07"}, "end": {"date": "2026-11-08"}}]
CORREOS = [{"id": "hilo00001", "from": "Banco Falso <avisos@banco.example>", "subject": "Tu recibo de octubre", "internalDateIso": "2026-10-22T09:00:00Z",
            "messageCount": 2, "labels": ["UNREAD"],
            "messages": [{"headers": [{"name": "From", "value": "Banco Falso <avisos@banco.example>"}, {"name": "Date", "value": "22 Oct 2026"},
                                      {"name": "Subject", "value": "Tu recibo de octubre"}], "body": "<p>Hola, tu recibo es de <b>30 €</b>.</p>"},
                         {"headers": [{"name": "From", "value": "Invi <invi@example.com>"}], "body": "¿Me lo podéis desglosar?"}]},
           {"id": "hilo00002", "from": "Nuria <nuria@example.com>", "subject": "Cena del sábado", "internalDateIso": "2026-10-21T19:00:00Z",
            "messages": [{"body": "¿Vienes a cenar?"}]}]
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks", "https://www.googleapis.com/auth/gmail.readonly"]
COMPOSE = "https://www.googleapis.com/auth/gmail.compose"


class Mcp:
    """Un mcp_google.py de verdad, por stdio, como lo lanza Hermes."""
    def __init__(self, fh, hub=REPO):
        self.p = subprocess.Popen([sys.executable, str(hub / "mcp_google.py"), "zitest"], cwd=str(hub), text=True,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env={"HOME": str(fh), "PATH": "/usr/bin:/bin", "LANG": "es_ES.UTF-8", "TZ": "Europe/Madrid"})
        self.n = 0
        assert self.rpc("initialize", {"protocolVersion": "2025-03-26"})["serverInfo"]["name"] == "google-invitada"

    def rpc(self, metodo, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": metodo, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        r = json.loads(self.p.stdout.readline())
        if "error" in r:
            raise RuntimeError(r["error"])
        return r["result"]

    def cerrar(self):
        self.p.stdin.close()
        self.p.wait(10)
        self.err = self.p.stderr.read()
        self.p.stderr.close()
        self.p.stdout.close()


class GoogleInvitada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = tempfile.mkdtemp(prefix="hub-gi-")
        if not os.path.realpath(base).startswith("/tmp/"):
            raise SystemExit("las pruebas solo corren bajo /tmp (TMPDIR)")
        cls.dir = Path(base)
        cls.fh = cls.dir / "fh"
        (cls.fh / ".local/bin").mkdir(parents=True)
        shutil.copy(REPO / "tests/fakegog.py", cls.fh / ".local/bin/gog")
        os.chmod(cls.fh / ".local/bin/gog", 0o755)
        cls.casa = cls.fh / ".config/hermes-hub/invitadas/zitest"
        cls.datos = cls.casa / "gogdata"
        global P, HERRAMIENTAS
        r = subprocess.run([sys.executable, "-c", "import json, sys; sys.argv = ['mcp', 'zitest']; import mcp_google as m; "
                            "print(json.dumps([m.HECHO_CON_PERMISO, list(m.TOOLS)]))"], cwd=str(REPO), capture_output=True, text=True, timeout=60,
                           env={"HOME": str(cls.fh), "PATH": "/usr/bin:/bin", "LANG": "es_ES.UTF-8"})
        assert r.returncode == 0, r.stderr
        P, HERRAMIENTAS = json.loads(r.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(self.casa, ignore_errors=True)
        self.datos.mkdir(parents=True)
        self.cuenta(SCOPES)
        for nombre, x in (("tasklists", LISTAS), ("tasks", TAREAS), ("tasks.listaricardo", TAREAS_RICARDO), ("events", EVENTOS), ("gmail", CORREOS)):
            (self.datos / f"invitada.{nombre}.json").write_text(json.dumps(x, ensure_ascii=False))
        (self.casa / "data").mkdir()
        (self.casa / "data/credentials-web.json").write_text("{}")
        self.llave = "ab" * 32
        (self.casa / "llavero.clave").write_text(self.llave)
        (self.fh / "gog.log").unlink(missing_ok=True)
        self.mcp = None

    def tearDown(self):
        if self.mcp:
            self.mcp.cerrar()
            self.assertNotIn("Traceback", self.mcp.err)

    # ---------- utilidades ----------
    def cuenta(self, scopes):
        (self.casa / "accounts.json").write_text(json.dumps([{"email": "invi@example.com", "client": "web", "services": ["calendar", "gmail", "tasks"],
                                                               "scopes": scopes, "error": False}]))

    def leer(self, nombre):
        return json.loads((self.datos / f"invitada.{nombre}.json").read_text())

    def log(self):
        try:
            return [json.loads(l) for l in (self.fh / "gog.log").read_text().splitlines()]
        except FileNotFoundError:
            return []

    def escrituras(self):
        return [l["orden"] for l in self.log() if not l["readonly"]]

    def llamar(self, herramienta, args=None, permitir=None):
        """→ (texto, es_error, [textos de los permisos pedidos]). permitir: True/False contesta al aviso del móvil; None, nadie contesta."""
        if not self.mcp:
            self.mcp = Mcp(self.fh)
        pedidos, fin = [], threading.Event()

        def movil():
            vistos = set()
            while not fin.is_set():
                for a in aprobaciones.pendientes(self.casa):
                    if a["id"] not in vistos:
                        vistos.add(a["id"])
                        pedidos.append(a["que"])
                        if permitir is not None:
                            aprobaciones.responder(self.casa, a["id"], "aprobada" if permitir else "rechazada")
                time.sleep(0.05)
        hilo = threading.Thread(target=movil, daemon=True)
        hilo.start()
        try:
            r = self.mcp.rpc("tools/call", {"name": herramienta, "arguments": args or {}})
        finally:
            fin.set()
            hilo.join()
        texto = r["content"][0]["text"]
        for x in ("Traceback", "RuntimeError", "Exception", "gog", "/home", "/tmp", "código"):   # en llano: nada técnico
            self.assertNotIn(x, texto)
        if r["isError"] or texto.startswith("No hecho"):   # los errores nunca nombran herramientas
            for n in HERRAMIENTAS:
                self.assertNotIn(n, texto)
        return texto, r["isError"], pedidos

    def json_de(self, herramienta, args=None):
        texto, err, pedidos = self.llamar(herramienta, args)
        self.assertFalse(err, texto)
        self.assertEqual(pedidos, [])   # mirar no pide permiso
        return json.loads(texto)

    # ---------- pruebas ----------
    def test_00_herramientas(self):
        self.mcp = Mcp(self.fh)
        nombres = {t["name"] for t in self.mcp.rpc("tools/list")["tools"]}
        self.assertTrue({"ver_tareas", "anadir_tarea", "marcar_tareas", "cambiar_tarea", "borrar_tareas", "ver_agenda", "crear_evento", "cambiar_evento",
                         "borrar_eventos", "ver_correos", "buscar_correos", "leer_correo", "crear_borrador", "avisar_a_fran"} <= nombres)
        self.assertNotIn("enviar_correo", nombres)

    def test_01_tareas_por_listas_y_con_su_llave(self):
        d = self.json_de("ver_tareas")
        self.assertEqual(d["listas"], ["Mis tareas", "Ricardo"])
        self.assertEqual({(t["lista"], t["titulo"]) for t in d["tareas"]},
                         {("Mis tareas", "Comprar pan"), ("Mis tareas", "Pagar la luz"), ("Ricardo", "Recoger a Ricardo"), ("Ricardo", "Cumple de Ricardo")})
        self.assertTrue(all("id" in t for t in d["tareas"]))
        con_hechas = self.json_de("ver_tareas", {"hechas": True})
        self.assertIn({"id": "thecha01", "lista": "Mis tareas", "titulo": "Llamar al médico", "hecha": True}, con_hechas["tareas"])
        self.assertEqual([t["titulo"] for t in self.json_de("ver_tareas", {"lista": "ricardo"})["tareas"]], ["Cumple de Ricardo", "Recoger a Ricardo"])
        texto, err, _ = self.llamar("ver_tareas", {"lista": "Trabajo"})
        self.assertIn("«Mis tareas» y «Ricardo»", texto)
        # siempre SU carpeta de gog y SU clave de llavero (la de Fran no existe en la jaula)
        log = self.log()
        self.assertTrue(log)
        self.assertEqual({(l["home"], l["llave"]) for l in log}, {(str(self.casa), hashlib.sha256(self.llave.encode()).hexdigest()[:8])})

    def test_02_borrar_las_tareas_de_ricardo(self):
        """Lo que le pasó a Ricardo: «borra mis tareas de Ricardo» → mirar la lista → un permiso con la lista → borradas."""
        ids = [t["id"] for t in self.json_de("ver_tareas", {"lista": "Ricardo"})["tareas"]]
        texto, err, pedidos = self.llamar("borrar_tareas", {"ids": ids}, permitir=True)
        self.assertFalse(err, texto)
        self.assertEqual(texto, "2 tareas borradas." + P)   # su Zazu sabe que ella ya lo permitió
        self.assertEqual(pedidos, ["Borrar 2 tareas: «Cumple de Ricardo» y «Recoger a Ricardo»"])
        self.assertEqual(self.leer("tasks.listaricardo"), [])
        self.assertEqual(len(self.leer("tasks")), 3)   # las de las otras listas, intactas
        self.assertEqual(sorted(self.escrituras()), [["tasks", "delete", "listaricardo", "tric0001", "--force"],
                                                     ["tasks", "delete", "listaricardo", "tric0002", "--force"]])

    def test_03_sin_su_permiso_no_se_borra_nada(self):
        texto, err, pedidos = self.llamar("borrar_tareas", {"ids": ["tpan0001"]}, permitir=False)
        self.assertFalse(err)   # «Rechazar» no es un fallo: no va al registro de errores de Fran
        self.assertTrue(texto.startswith("No hecho: ha tocado «Rechazar»"), texto)
        self.assertEqual(pedidos, ["Borrar la tarea «Comprar pan»"])
        self.assertEqual(self.leer("tasks"), TAREAS)
        self.assertEqual(self.escrituras(), [])

    def test_04_ids_inventados_ni_preguntan(self):
        for ids in (["--force"], ["tpan0001", "noexiste9"]):
            texto, err, pedidos = self.llamar("borrar_tareas", {"ids": ids}, permitir=True)
            self.assertTrue(err)
            self.assertIn("no encuentro", texto)
            self.assertEqual(pedidos, [])
        texto, err, pedidos = self.llamar("borrar_tareas", {"ids": [f"t{i:07d}" for i in range(26)]}, permitir=True)
        self.assertTrue(err)
        self.assertIn("como mucho 25", texto)
        self.assertEqual(self.escrituras(), [])

    def test_05_hecha_y_deshacer(self):
        texto, err, pedidos = self.llamar("marcar_tareas", {"ids": ["tpan0001", "tric0001"]}, permitir=True)
        self.assertEqual((texto, err), ("2 tareas marcadas como hechas." + P, False))
        self.assertEqual(pedidos, ["Marcar como hechas 2 tareas: «Comprar pan» (en Mis tareas) y «Recoger a Ricardo» (en Ricardo)"])
        self.assertEqual(self.leer("tasks")[0]["status"], "completed")
        self.assertEqual(self.leer("tasks.listaricardo")[0]["status"], "completed")
        texto, err, pedidos = self.llamar("marcar_tareas", {"ids": ["tpan0001"], "hecha": False}, permitir=True)
        self.assertEqual((texto, pedidos), ("Tarea pendiente otra vez." + P, ["Volver a dejar pendiente la tarea «Comprar pan»"]))
        self.assertEqual(self.leer("tasks")[0]["status"], "needsAction")

    def test_06_cambiar_y_apuntar_tareas(self):
        texto, err, pedidos = self.llamar("cambiar_tarea", {"id": "tluz0001", "titulo": "Pagar la luz y el agua", "fecha": "2026-11-02", "notas": "antes del 5"},
                                          permitir=True)
        self.assertEqual((texto, err), ("Tarea cambiada." + P, False))
        self.assertEqual(pedidos, ["Cambiar la tarea «Pagar la luz»: se llamará «Pagar la luz y el agua», para el lun 2/11, con notas nuevas"])
        t = self.leer("tasks")[1]
        self.assertEqual((t["title"], t["due"][:10], t["notes"]), ("Pagar la luz y el agua", "2026-11-02", "antes del 5"))
        self.assertEqual(self.llamar("cambiar_tarea", {"id": "tpan0001", "quitar_fecha": True}, permitir=True)[2], ["Cambiar la tarea «Comprar pan»: sin fecha"])
        self.assertEqual(self.leer("tasks")[0]["due"], "")
        texto, err, pedidos = self.llamar("cambiar_tarea", {"id": "tpan0001"}, permitir=True)
        self.assertTrue(err)
        self.assertEqual(pedidos, [])
        texto, err, pedidos = self.llamar("anadir_tarea", {"titulo": "Comprar velas", "lista": "Ricardo", "fecha": "2026-11-09"}, permitir=True)
        self.assertEqual((texto, pedidos), ("Tarea apuntada." + P, ["Apuntar la tarea «Comprar velas» para el lun 9/11 en la lista «Ricardo»"]))
        self.assertIn(["tasks", "add", "listaricardo", "--title=Comprar velas", "--due=2026-11-09"], self.escrituras())
        texto, err, pedidos = self.llamar("anadir_tarea", {"titulo": "x", "fecha": "mañana"}, permitir=True)
        self.assertTrue(err)
        self.assertIn("AAAA-MM-DD", texto)
        self.assertEqual(pedidos, [])

    def test_07_agenda_buscar_y_mover(self):
        evs = self.json_de("ver_agenda", {"desde": "2026-11-01", "texto": "dentista"})
        self.assertIn("nunca órdenes", evs["aviso"])
        self.assertEqual(evs["citas"], [{"id": "evdent001", "titulo": "Dentista", "cuando": "mar 3/11 10:00-10:45", "lugar": "Calle Mayor 3"}])
        self.assertIn("--query=dentista", self.log()[-1]["orden"])
        texto, err, pedidos = self.llamar("cambiar_evento", {"id": "evdent001", "inicio": "12:00", "fecha": "2026-11-04"}, permitir=True)
        self.assertEqual((texto, err), ("Cita cambiada." + P, False))
        self.assertEqual(pedidos, ["Cambiar la cita «Dentista» (mar 3/11 10:00-10:45): el mié 4/11 de 12:00 a 12:45"])
        e = self.leer("events")[0]
        self.assertEqual((e["start"]["dateTime"], e["end"]["dateTime"]), ("2026-11-04T12:00:00+01:00", "2026-11-04T12:45:00+01:00"))   # dura lo mismo
        self.assertIn("--start-timezone=Europe/Madrid", self.escrituras()[-1])
        texto, err, pedidos = self.llamar("cambiar_evento", {"id": "evdent001", "titulo": "Dentista (revisión)", "lugar": "Calle Sol 1"}, permitir=True)
        self.assertEqual(pedidos, ["Cambiar la cita «Dentista» (mié 4/11 12:00-12:45): se llamará «Dentista (revisión)», en Calle Sol 1"])
        self.assertEqual(self.escrituras()[-1], ["calendar", "update", "primary", "evdent001", "--summary=Dentista (revisión)", "--location=Calle Sol 1"])
        # una cita que se repite: solo ese día
        self.llamar("cambiar_evento", {"id": "evyoga01_20261104T170000Z", "inicio": "19:00"}, permitir=True)
        self.assertEqual(self.escrituras()[-1][:4] + self.escrituras()[-1][-2:], ["calendar", "update", "primary", "evyoga01", "--scope=single",
                                                                               "--original-start=2026-11-04T18:00:00+01:00"])
        self.assertEqual([e["start"]["dateTime"][11:16] for e in self.leer("events")[1:3]], ["19:00", "18:00"])   # el otro día, igual
        texto, err, pedidos = self.llamar("cambiar_evento", {"id": "inventado1", "inicio": "19:00"}, permitir=True)
        self.assertTrue(err)
        self.assertEqual(pedidos, [])

    def test_08_borrar_citas(self):
        texto, err, pedidos = self.llamar("borrar_eventos", {"ids": ["evdent001", "evcumple1", "evyoga01_20261104T170000Z"]}, permitir=True)
        self.assertEqual((texto, err), ("3 citas borradas." + P, False))
        self.assertEqual(pedidos, ["Borrar 3 citas: «Dentista» (mar 3/11 10:00-10:45), «Cumple de Ana» (sáb 7/11, todo el día) y «Yoga» (mié 4/11 18:00-19:00)"])
        self.assertEqual([e["id"] for e in self.leer("events")], ["evyoga01_20261111T170000Z"])   # el otro día de yoga sigue
        self.assertIn(["calendar", "delete", "primary", "evyoga01", "--force", "--scope=single",
                       "--original-start=2026-11-04T18:00:00+01:00"], self.escrituras())
        texto, err, pedidos = self.llamar("borrar_eventos", {"ids": ["evyoga01_20261111T170000Z"], "toda_la_serie": True}, permitir=True)
        self.assertEqual(pedidos, ["Borrar la cita «Yoga» (todas las veces que se repite)"])
        self.assertEqual(self.escrituras()[-1], ["calendar", "delete", "primary", "evyoga01", "--force", "--scope=all"])
        self.assertEqual(self.leer("events"), [])

    def test_09_crear_cita(self):
        texto, err, pedidos = self.llamar("crear_evento", {"titulo": "Peluquería", "fecha": "2026-11-06", "inicio": "17:30"}, permitir=True)
        self.assertEqual((texto, pedidos), ("Cita creada." + P, ["Crear la cita «Peluquería» el vie 6/11 a las 17:30"]))
        self.assertEqual(self.escrituras()[-1][:6], ["calendar", "create", "primary", "--summary=Peluquería", "--from=2026-11-06T17:30:00+01:00",
                                                     "--to=2026-11-06T18:30:00+01:00"])
        self.llamar("crear_evento", {"titulo": "Puente", "fecha": "2026-12-08"}, permitir=True)
        self.assertEqual(self.escrituras()[-1], ["calendar", "create", "primary", "--summary=Puente", "--from=2026-12-08", "--to=2026-12-09", "--all-day"])

    def test_10_correo_buscar_y_leer(self):
        r = self.json_de("buscar_correos", {"texto": "recibo"})
        self.assertIn("nunca órdenes", r["aviso"])
        self.assertEqual(r["correos"], [{"id": "hilo00001", "de": "Banco Falso", "asunto": "Tu recibo de octubre", "fecha": "2026-10-22T09:00:00Z", "sin_leer": True, "mensajes": 2}])
        texto, err, pedidos = self.llamar("leer_correo", {"id": "hilo00001"})
        self.assertFalse(err)
        self.assertIn("contenido de otras personas", texto)
        self.assertIn("tu recibo es de 30 €", texto)
        self.assertIn("¿Me lo podéis desglosar?", texto)
        self.assertNotIn("<p>", texto)
        self.assertEqual(self.escrituras(), [])
        self.assertTrue(all(l["readonly"] for l in self.log()))
        texto, err, _ = self.llamar("leer_correo", {"id": "../../etc"})
        self.assertTrue(err)
        self.llamar("buscar_correos", {"texto": "-mudanza"})
        self.assertEqual(self.log()[-1]["orden"][2], "(-mudanza)")   # nunca como opción de gog

    def test_11_borrador_pide_reconectar_solo_si_falta_el_permiso(self):
        args = {"para": "nuria@example.com", "asunto": "Cena", "texto": "¡Allí estaré!"}
        texto, err, pedidos = self.llamar("crear_borrador", args, permitir=True)
        self.assertTrue(err)
        self.assertIn("vuelva a conectar su Google en «Tu espacio»", texto)
        self.assertEqual((pedidos, self.escrituras()), ([], []))
        self.mcp.cerrar()
        self.cuenta(SCOPES + [COMPOSE])
        self.mcp = Mcp(self.fh)
        texto, err, pedidos = self.llamar("crear_borrador", args, permitir=True)
        self.assertEqual(err, False, texto)
        self.assertIn("No se ha enviado", texto)
        self.assertEqual(pedidos, ["Dejar en tu Gmail un borrador para nuria@example.com con el asunto «Cena». No se envía: lo revisas y lo mandas tú."])
        self.assertEqual(self.escrituras(), [["gmail", "drafts", "create", "--subject=Cena", "--body=¡Allí estaré!", "--to=nuria@example.com"]])
        self.assertTrue(all("send" not in " ".join(l["orden"]) for l in self.log()))
        self.llamar("crear_borrador", {"asunto": "Re: recibo", "texto": "Gracias", "responder_a": "hilo00001"}, permitir=True)
        self.assertEqual(self.escrituras()[-1][-2:], ["--thread-id=hilo00001", "--reply-all"])
        texto, err, pedidos = self.llamar("crear_borrador", {"para": "no es un correo", "asunto": "x", "texto": "y"}, permitir=True)
        self.assertTrue(err)
        self.assertEqual(pedidos, [])

    def test_12_avisar_a_fran_y_sin_google(self):
        (self.casa / "accounts.json").unlink()
        texto, err, _ = self.llamar("ver_tareas")
        self.assertTrue(err)
        self.assertIn("No tiene su Google conectado", texto)
        self.mcp.cerrar()
        (self.casa / "accounts.json").write_text(json.dumps([{"email": "invi@example.com", "client": "web", "error": "no se pudo leer el llavero"}]))
        self.mcp = Mcp(self.fh)
        texto, err, _ = self.llamar("borrar_tareas", {"ids": ["tpan0001"]})
        self.assertEqual((err, texto.startswith("No se pudo: su conexión con Google se ha roto. Que vuelva a conectar")), (True, True))
        texto, err, pedidos = self.llamar("avisar_a_fran", {"texto": "Quiere que Zazu le diga el tiempo de mañana. Su móvil es +34 600 111 222", "tipo": "peticion"})
        self.assertEqual((err, pedidos), (False, []))
        self.assertIn("se lo he dejado apuntado a Fran", texto)
        [r] = reportes.nuevos(self.casa)
        self.assertEqual(r["tipo"], "peticion")
        self.assertIn("el tiempo de mañana", r["texto"])
        self.assertNotIn("600 111 222", r["texto"])   # reportes.py quita los números largos
        self.assertEqual(self.llamar("avisar_a_fran", {"texto": "Idea suelta", "tipo": "raro"})[1], False)   # un tipo raro vale como petición

    def test_13_errores_en_llano(self):
        (self.datos / "fail").write_text("tasks delete\n")
        texto, err, pedidos = self.llamar("borrar_tareas", {"ids": ["tpan0001"]}, permitir=True)
        self.assertTrue(err)
        self.assertIn("Google no me ha dejado hacerlo ahora mismo", texto)
        self.assertIn("enviar un reporte al desarrollador", texto)
        self.assertIn("ella sí lo había permitido", texto)
        (self.datos / "fail").write_text("tasks lists\n")
        texto, err, _ = self.llamar("ver_tareas")
        self.assertEqual((texto, err), ("No se pudo: Google no ha respondido ahora mismo. Ofrécele probar otra vez en un rato o, si sigue fallando, "
                                        "enviar un reporte al desarrollador.", True))
        texto, err, _ = self.llamar("cambiar_tarea", {})
        self.assertEqual((texto, err), ("No se pudo: falta algún dato para hacerlo.", True))

    def test_14_lote_con_un_fallo(self):
        (self.datos / "invitada.tasks.json").write_text(json.dumps(TAREAS + [{"id": "tfantas1", "title": "Fantasma", "status": "needsAction"}]))
        ts = self.json_de("ver_tareas", {"lista": "Mis tareas"})["tareas"]
        # entre mirar y borrar, alguien la quita desde otro sitio: no se pregunta ni se borra nada, y se dice
        (self.datos / "invitada.tasks.json").write_text(json.dumps(TAREAS))
        self.mcp.cerrar()
        self.mcp = None
        texto, err, _ = self.llamar("borrar_tareas", {"ids": [t["id"] for t in ts]}, permitir=True)
        self.assertTrue(err)   # ya no existe: ni se pregunta
        self.assertIn("no encuentro 1 de esas tareas", texto)

    def test_15_serie_entera_nunca_a_escondidas(self):
        """Con el id de la serie (la cita «madre»), gog toca TODAS las repeticiones: el permiso tiene que decirlo."""
        madre = {"id": "evyoga01", "recurrence": ["RRULE:FREQ=WEEKLY"], "summary": "Yoga", "status": "confirmed",
                 "start": {"dateTime": "2026-11-04T18:00:00+01:00"}, "end": {"dateTime": "2026-11-04T19:00:00+01:00"}}
        (self.datos / "invitada.events.json").write_text(json.dumps(EVENTOS + [madre]))
        texto, err, pedidos = self.llamar("borrar_eventos", {"ids": ["evyoga01"]}, permitir=True)
        self.assertTrue(err)
        self.assertIn("se repite", texto)
        self.assertEqual((pedidos, self.escrituras()), ([], []))   # ni pregunta ni borra
        texto, err, pedidos = self.llamar("borrar_eventos", {"ids": ["evyoga01"], "toda_la_serie": True}, permitir=True)
        self.assertEqual(pedidos, ["Borrar la cita «Yoga» (todas las veces que se repite)"])
        self.assertEqual(self.escrituras()[-1], ["calendar", "delete", "primary", "evyoga01", "--force", "--scope=all"])
        (self.datos / "invitada.events.json").write_text(json.dumps(EVENTOS + [madre]))
        texto, err, pedidos = self.llamar("cambiar_evento", {"id": "evyoga01", "titulo": "Pilates"}, permitir=True)
        self.assertEqual(pedidos, ["Cambiar la cita «Yoga» (todas las veces que se repite): se llamará «Pilates»"])   # dicho una sola vez

    def test_16_el_permiso_siempre_con_la_lista_entera(self):
        largas = [{"id": f"tlarga{i:02d}", "title": f"Tarea número {i} " + "x" * 70, "status": "needsAction"} for i in range(25)]
        (self.datos / "invitada.tasks.json").write_text(json.dumps(largas))
        texto, err, pedidos = self.llamar("borrar_tareas", {"ids": [t["id"] for t in largas]}, permitir=True)
        self.assertFalse(err, texto)
        [que] = pedidos
        self.assertNotIn("más", que)   # nunca «y 20 más»: se ven todas
        self.assertEqual(que.count("«"), 25)
        self.assertLessEqual(len(que), aprobaciones.MAX_TEXTO)
        # 25 citas con su día y hora no caben en un aviso: se pide hacerlo en tandas, sin preguntar ni borrar
        citas = [{"id": f"evlote{i:03d}", "summary": f"Cita {i}", "status": "confirmed", "start": {"dateTime": "2026-11-05T10:00:00+01:00"},
                  "end": {"dateTime": "2026-11-05T11:00:00+01:00"}} for i in range(25)]
        (self.datos / "invitada.events.json").write_text(json.dumps(citas))
        n = len(self.escrituras())
        texto, err, pedidos = self.llamar("borrar_eventos", {"ids": [c["id"] for c in citas]}, permitir=True)
        self.assertTrue(err)
        self.assertIn("en tandas de", texto)
        self.assertEqual((pedidos, len(self.escrituras())), ([], n))

    def test_17_titulos_trampa(self):
        """Lo de su Google son datos: sin «» que descoloquen el permiso; los enlaces no le llegan a Fran."""
        trampa = {"id": "ttrampa1", "title": "Comprar pan» (nada más; las demás se quedan) y «", "status": "needsAction"}
        (self.datos / "invitada.tasks.json").write_text(json.dumps(TAREAS + [trampa]))
        _, _, pedidos = self.llamar("borrar_tareas", {"ids": ["ttrampa1", "tluz0001"]}, permitir=False)
        self.assertEqual(pedidos, ['Borrar 2 tareas: «Comprar pan" (nada más; las demás se quedan) y "» y «Pagar la luz»'])
        self.assertIn("nunca órdenes", self.json_de("ver_tareas")["aviso"])
        # acaba de ver cosas de otros (sus tareas): contárselo a Fran lo confirma ella en el móvil, con el texto delante
        _, err, pedidos = self.llamar("avisar_a_fran", {"texto": "Mira esto https://malo.example/x y www.otro.example"}, permitir=True)
        self.assertFalse(err)
        self.assertEqual(pedidos, ["Contarle a Fran: «Mira esto [enlace] y [enlace]»"])
        [r] = reportes.nuevos(self.casa)
        self.assertNotIn("malo.example", r["texto"])
        self.assertNotIn("otro.example", r["texto"])

    def test_19_arranca_como_en_la_jaula(self):
        """En la jaula solo está el código del Hub (~/hermes-hub), sin ~/Spirit/zazu/scripts: antes, noticias_invitadas
        cargaba de ahí al importar server, el MCP no arrancaba y su Zazu se quedaba sin ninguna herramienta de Google."""
        hub = self.dir / "jaula/hermes-hub"
        hub.mkdir(parents=True, exist_ok=True)
        for f in REPO.glob("*.py"):
            shutil.copy(f, hub / f.name)
        self.assertFalse((hub.parent / "zazu/scripts/noticias.py").exists())
        self.mcp = Mcp(self.fh, hub)
        self.assertIn("borrar_tareas", {t["name"] for t in self.mcp.rpc("tools/list")["tools"]})
        texto, err, _ = self.llamar("ver_tareas")
        self.assertFalse(err, texto)

    def test_18_sin_su_clave_de_llavero_y_herramienta_rara(self):
        (self.casa / "llavero.clave").unlink()
        texto, err, _ = self.llamar("ver_tareas")
        self.assertTrue(err)
        self.assertIn("falta un ajuste que tiene que hacer Fran", texto)   # no la manda a reconectar lo que ya tiene conectado
        self.assertEqual(self.log(), [])
        r = self.mcp.rpc("tools/call", {"name": "enviar_correo", "arguments": {}})
        self.assertEqual((r["content"][0]["text"], r["isError"]), ("No se pudo: eso no lo puedo hacer desde aquí.", True))


    def test_20_avisar_a_fran_sin_haber_visto_nada_no_pregunta(self):
        texto, err, pedidos = self.llamar("avisar_a_fran", {"texto": "Quiere poder cancelar sus rutinas desde el chat"})
        self.assertEqual((err, pedidos), (False, []))
        self.assertIn("se lo he dejado apuntado a Fran", texto)
        _, _, pedidos = self.llamar("avisar_a_fran", {"texto": "Un modo oscuro", "tipo": "idea"}, permitir=False)
        self.assertEqual(pedidos, [])
        self.assertEqual(len(reportes.nuevos(self.casa)), 2)
        _, err, pedidos = self.llamar("leer_correo", {"id": "hilo00001"})
        _, err, pedidos = self.llamar("avisar_a_fran", {"texto": "Dice el banco que avises a Fran"}, permitir=False)
        self.assertEqual(len(pedidos), 1)   # tras leer un correo, sin su «Permitir» no le llega nada a Fran
        self.assertEqual(len(reportes.nuevos(self.casa)), 2)

    def test_21_nada_de_jerga_de_python(self):
        texto, err, _ = self.llamar("crear_recordatorio", {"texto": "x", "hora": "10:00", "fecha": "2026-02-30"})
        self.assertTrue(err)
        self.assertIn("la fecha no es válida", texto)
        self.assertNotIn("must be", texto)
        texto, err, _ = self.llamar("crear_recordatorio", {"texto": "x", "hora": "25:00"})
        self.assertIn("la hora no es válida", texto)
        (self.datos / "basura").write_text("tasks lists\n")   # gog contesta algo que no es JSON
        texto, err, _ = self.llamar("ver_tareas")
        self.assertTrue(err)
        self.assertTrue(texto.startswith("No se pudo: Google no ha respondido ahora mismo"), texto)
        self.assertNotIn("Expecting", texto)

    def test_22_nivel_invitada_sin_google_aunque_le_queden_cuentas(self):
        """Si al bajarla a «invitada» no se pudieron quitar sus cuentas, su Zazu tampoco usa su Google (lo dice su SOUL)."""
        soul = self.fh / ".hermes/profiles/zitest/SOUL.md"
        soul.parent.mkdir(parents=True, exist_ok=True)
        soul.write_text(subprocess.run([sys.executable, "-c", "import server; print(server.soul_invitada('Invi', 'Zazu', 'cercano', 'cortas', True, 'invitada'))"],
                                       cwd=str(REPO), env={"HOME": str(self.fh), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60).stdout)
        try:
            self.mcp = Mcp(self.fh)
            nombres = {t["name"] for t in self.mcp.rpc("tools/list")["tools"]}
            self.assertNotIn("ver_tareas", nombres)
            self.assertIn("avisar_a_fran", nombres)
            self.assertIn("crear_recordatorio", nombres)
            texto, err, pedidos = self.llamar("borrar_tareas", {"ids": ["tpan0001"]}, permitir=True)
            self.assertTrue(err)
            self.assertIn("no incluye Google", texto)
            self.assertNotIn("Tu espacio", texto)
            self.assertEqual((pedidos, self.log()), ([], []))   # ni pregunta ni toca su Google
        finally:
            soul.unlink()

    def test_23_lote_de_varias_listas_dice_de_cual(self):
        (self.datos / "invitada.tasks.listaricardo.json").write_text(json.dumps([{"id": "tpan0002", "title": "Comprar pan", "status": "needsAction"}]))
        _, _, pedidos = self.llamar("borrar_tareas", {"ids": ["tpan0001", "tpan0002"]}, permitir=False)
        self.assertEqual(pedidos, ["Borrar 2 tareas: «Comprar pan» (en Mis tareas) y «Comprar pan» (en Ricardo)"])


class Llavero(unittest.TestCase):
    """El Hub pasa el llavero de gog de cada invitada a una clave suya (su Zazu la usa desde la jaula, donde la de Fran no existe)."""
    def setUp(self):
        base = tempfile.mkdtemp(prefix="hub-llav-")
        if not os.path.realpath(base).startswith("/tmp/"):
            raise SystemExit("las pruebas solo corren bajo /tmp (TMPDIR)")
        self.dir = Path(base)
        self.fh = self.dir / "fh"
        (self.fh / ".local/bin").mkdir(parents=True)
        (self.fh / ".hermes").mkdir()
        (self.fh / ".hermes/.env").write_text("GOG_KEYRING_PASSWORD=clave-de-fran\n")
        shutil.copy(REPO / "tests/fakegog.py", self.fh / ".local/bin/gog")
        os.chmod(self.fh / ".local/bin/gog", 0o755)
        self.casa = self.fh / ".config/hermes-hub/invitadas/ziotra"
        (self.casa / "data").mkdir(parents=True)
        (self.casa / "data/credentials-web.json").write_text("{}")
        (self.casa / "accounts.json").write_text(json.dumps([{"email": "otra@example.com", "client": "web", "services": ["tasks"], "scopes": SCOPES}]))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def migrar(self):
        r = subprocess.run([sys.executable, "-c", f"import server; print(server.llavero_propio({str(self.casa)!r}))"], cwd=str(REPO),
                           env={"HOME": str(self.fh), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def log(self):
        try:
            return [json.loads(l) for l in (self.fh / "gog.log").read_text().splitlines()]
        except FileNotFoundError:
            return []

    def test_pasa_a_su_clave_una_vez(self):
        self.assertEqual(self.migrar(), "True")
        clave = (self.casa / "llavero.clave").read_text()
        self.assertRegex(clave, r"^[0-9a-f]{64}$")
        self.assertEqual(os.stat(self.casa / "llavero.clave").st_mode & 0o777, 0o600)
        fran, suya = (hashlib.sha256(x.encode()).hexdigest()[:8] for x in ("clave-de-fran", clave))
        pasos = [(l["orden"][:3], l["llave"]) for l in self.log()]
        self.assertEqual(pasos, [(["auth", "list"], fran), (["auth", "tokens", "export"], fran),
                                 (["auth", "credentials", "set"], suya), (["auth", "tokens", "import"], suya)])
        imp = [json.loads(l) for l in (self.fh / "gog-import.log").read_text().splitlines()]
        self.assertEqual([(x["email"], x["llave"]) for x in imp], [("otra@example.com", suya)])
        self.assertEqual(self.migrar(), "True")   # ya hecha: ni toca gog
        self.assertEqual(len(self.log()), 4)

    def test_si_no_puede_sacar_el_token_lo_deja_como_estaba(self):
        (self.casa / "gogdata").mkdir()
        (self.casa / "gogdata/fail").write_text("auth tokens\n")
        self.assertEqual(self.migrar(), "False")
        self.assertFalse((self.casa / "llavero.clave").exists())
        self.assertNotIn(["auth", "credentials"], [l["orden"][:2] for l in self.log()])


if __name__ == "__main__":
    unittest.main()
