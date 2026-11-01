import contextlib
import io
import json
import os
import unittest

from base import CANARIO, FH, FIX, YO, ZVTest, chat, config, msg
from zv import acciones, cli
from test_wa import GRP, NURIA, item


def cli_run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(list(argv))
    return rc, out.getvalue()


class TestListaCerrada(ZVTest):
    def test_rechaza_todo_lo_que_no_es_crear_tarea_o_evento(self):
        cfg = config.cargar()
        malos = [["gmail", "send", "primary"], ["calendar", "delete", "primary", "x"], ["tasks", "delete", "@default", "x"], ["tasks", "done", "@default", "x"],
                 ["calendar", "create", "otro", "--summary=a"], ["calendar", "create", "primary", "--summary=a", "--attendees=a@b.c"], ["calendar", "update", "primary", "x"],
                 ["tasks", "add", "@default", "--title=a", "--send-updates=all"], ["tasks", "add", "OtraLista", "--title=a"]]
        for m in malos:
            with self.assertRaises(acciones.AccionError, msg=str(m)):
                acciones._escribir(cfg, "varas", m)
        self.assertEqual(self.log("gog_writes.log"), "")


class TestLive(ZVTest):
    def activar(self):
        self.cfg_set(**{"modo.wa": "activo", "modo.agenda": "activo", "flujos.wa-peticion.modo": "activo"})   # el flujo wa-peticion también debe estar activo
        config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_entrega().touch()

    def alta_item(self, db, titulo="Mandar el presupuesto", tipo="item_tarea", due="2026-10-09", hora=None, accion="pendiente", clave="k1"):
        return db.alta(clave, "wa", tipo, titulo, prio=3, silencioso=True, detalle="De WhatsApp (Nuria, 08/10)", chat="Nuria", cuenta="varas", due=due, hora=hora, dur=60,
                       evidencia="chat=x;id=y;ts=z", accion=accion, ref="wa:1")[0]

    def escrituras(self):
        return [json.loads(l) for l in self.log("gog_writes.log").splitlines()]

    def test_sin_modo_activo_no_escribe_nada(self):
        db = self.db(); self.alta_item(db)
        self.assertEqual(acciones.aplicar_pendientes(db, config.cargar()), {"creados": 0, "duplicados": 0, "fallidos": 0})
        self.cfg_set(**{"modo.wa": "activo"})        # falta el interruptor global
        acciones.aplicar_pendientes(db, config.cargar()); self.assertEqual(self.escrituras(), [])

    def test_crea_tarea_con_marca_y_sin_texto(self):
        self.activar(); db = self.db(); i = self.alta_item(db)
        r = acciones.aplicar_pendientes(db, config.cargar())
        self.assertEqual(r["creados"], 1)
        w = self.escrituras()
        self.assertEqual(w[0]["args"], ["tasks", "add", "@default", "--title=Mandar el presupuesto", "--due=2026-10-09"])
        self.assertEqual(w[1]["args"][:4], ["tasks", "update", "@default", "id1"]); self.assertEqual(w[1]["args"][4], f"--notes=De WhatsApp (Nuria, 08/10) · [ZV:{i}]")
        self.assertEqual(db.buscar(i)["accion"], "creado")
        acciones.aplicar_pendientes(db, config.cargar()); self.assertEqual(len(self.escrituras()), 2)      # idempotente
        c = self.log("calls.log"); self.assertNotIn("PROHIBIDO", c)

    def test_marca_en_google_evita_duplicar_tras_perder_el_estado(self):
        self.activar(); db = self.db(); i = self.alta_item(db)
        self.escribir("gog_varas.json", {"tasks": {"@default": [{"id": "T1", "title": "Mandar el presupuesto", "notes": f"De WhatsApp (Nuria, 08/10) · [ZV:{i}]", "status": "needsAction"}]}})
        r = acciones.aplicar_pendientes(db, config.cargar())
        self.assertEqual((r["duplicados"], self.escrituras()), (1, []))

    def test_no_duplica_con_tarea_parecida_existente(self):
        self.activar(); db = self.db(); i = self.alta_item(db)
        self.escribir("gog_varas.json", {"tasks": {"@default": [{"id": "T1", "title": "Mandar el presupuesto a Nuria", "due": "2026-10-09T00:00:00Z", "status": "needsAction"}]}})
        acciones.aplicar_pendientes(db, config.cargar())
        self.assertEqual((db.buscar(i)["accion"], self.escrituras()), ("duplicado", []))

    def test_evento_tentativo_sin_gemela_por_defecto(self):
        """Un evento apuntado desde WhatsApp es solo el evento: antes siempre creaba además una tarea con el mismo título y la agenda salía duplicada."""
        self.activar(); db = self.db(); i = self.alta_item(db, "Cenar con Nuria", "item_evento", "2026-10-10", "21:00")
        r = acciones.aplicar_pendientes(db, config.cargar())
        w = self.escrituras()
        self.assertEqual([x["args"][:2] for x in w], [["calendar", "create"]])
        self.assertEqual((r["creados"], db.buscar(i)["accion"], db.buscar(i)["accion_ref"]), (1, "creado", "ev:id1"))
        self.assertEqual(acciones.aplicar_pendientes(db, config.cargar())["creados"], 0)      # y no se repite en el ciclo siguiente
        self.assertEqual(len(self.escrituras()), 1)

    def test_evento_tentativo_con_gemela(self):
        """Con wa.gemela_evento = true vuelve el comportamiento de antes: evento y, además, su tarea."""
        self.activar(); self.cfg_set(**{"wa.gemela_evento": True}); db = self.db(); i = self.alta_item(db, "Cenar con Nuria", "item_evento", "2026-10-10", "21:00")
        acciones.aplicar_pendientes(db, config.cargar())
        w = self.escrituras()
        self.assertEqual(w[0]["args"][:3], ["calendar", "create", "primary"])
        self.assertIn("--summary=¿? Cenar con Nuria", w[0]["args"]); self.assertIn("--from=2026-10-10T21:00:00", w[0]["args"]); self.assertIn("--to=2026-10-10T22:00:00", w[0]["args"])
        self.assertIn("--start-timezone=Europe/Madrid", w[0]["args"]); self.assertTrue(all(not a.startswith("--attendees") for a in w[0]["args"]))
        self.assertEqual(w[1]["args"][:2], ["tasks", "add"]); self.assertEqual(db.buscar(i)["accion"], "creado")
        self.assertIn("ev:id1", db.buscar(i)["accion_ref"])

    def test_cierra_solos_los_avisos_informativos_viejos(self):
        """Auditoría, tarea gemela e items ya creados que nadie atendió en 3 días se cierran; lo que pide algo, no."""
        db = self.db(); cfg = config.cargar(); hace = lambda d: db.ts() - d * 86400
        def alta(clave, fuente, tipo, dias, accion=None):
            i = db.alta(clave, fuente, tipo, f"aviso {clave}", prio=3, accion=accion, ref=f"r:{clave}")[0]
            db.c.execute("UPDATE avisos SET creado=? WHERE id=?", (hace(dias), i)); db.c.commit(); return i
        viejos = [alta("a1", "agenda", "auditoria", 5), alta("a2", "agenda", "accion_gemela", 4, "sombra"), alta("a3", "wa", "item_tarea", 6, "creado"),
                  alta("a4", "correo", "flujo_evento", 4, "sombra")]
        quedan = [alta("b1", "agenda", "auditoria", 1), alta("b2", "wa", "item_tarea", 6, "pendiente"), alta("b3", "wa", "item_evento", 6, "evento_creado"),
                  alta("b4", "agenda", "tarea_vence", 9), alta("b5", "correo", "dinero", 9), alta("b6", "sistema", "fallo", 9)]
        self.assertEqual(db.cerrar_informativos(cfg), 4)
        self.assertEqual([db.buscar(i)["estado"] for i in viejos], ["descartado"] * 4)
        self.assertEqual([db.buscar(i)["estado"] for i in quedan], ["nuevo"] * 6)
        self.assertEqual(db.cerrar_informativos(cfg), 0)                                  # idempotente
        self.cfg_set(**{"retencion.cerrar_informativos_dias": 0})
        self.assertEqual(db.cerrar_informativos(config.cargar()), 0)                       # 0 = nunca

    def test_fallo_reintenta_y_acaba_fallido(self):
        self.activar(); db = self.db(); i = self.alta_item(db)
        (FIX / "gog_falla_varas").write_text("9")
        for _ in range(3):
            acciones.aplicar_pendientes(db, config.cargar())
        self.assertEqual(db.buscar(i)["accion"], "fallido")

    def test_flujo_completo_wa_en_modo_activo(self):
        self.activar()
        self.escribir("wa_chats.json", [chat(NURIA, "Nuria")]); self.escribir("wa_msgs.json", [])
        self.ciclo("wa")
        self.escribir("wa_msgs.json", [msg(NURIA, f"Me mandas el presupuesto mañana? {CANARIO}", "2026-10-08T18:03")])
        self.escribir("llm_resp.json", [json.dumps({"items": [item("Mandar el presupuesto", "m1")]})])
        self.ahora("2026-10-08T18:20"); self.ciclo("wa")
        w = self.escrituras()
        self.assertEqual(len(w), 2); self.assertNotIn(CANARIO, json.dumps(w))
        self.assertEqual(self.log("sent.log"), "")                      # nunca responde a nadie

    def test_agenda_activa_no_crea_gemelas(self):
        """Fran ya no quiere tareas gemelas de eventos: ni siquiera en modo activo el vigía crea la tarea que las acompañaba."""
        self.activar()
        self.escribir("gog_varas.json", {"events": [{"id": "x", "summary": "Revisión coche", "start": {"dateTime": "2026-10-12T17:00:00+02:00"}, "end": {"dateTime": "2026-10-12T18:00:00+02:00"},
                                                    "status": "confirmed", "creator": {"self": True}, "organizer": {"self": True}, "CalendarID": "primary"}]})
        self.escribir("gog_alvarez.json", {})
        self.ahora("2026-10-08T09:30"); self.ciclo("agenda")
        self.assertEqual(self.escrituras(), [])                                        # nada escrito en Google
        self.assertEqual(self.filas("SELECT * FROM avisos WHERE tipo='accion_gemela'"), [])   # ni se propone


class TestCLI(ZVTest):
    def test_draft_solo_imprime(self):
        db = self.db(); db.alta("d", "wa", "wa_urgente", "Nuria", destino=NURIA, borrador="Llego a las 8, ¿cenamos? 'ok'")
        rc, out = cli_run("draft", "A1")
        self.assertEqual(rc, 0); self.assertIn(f"wacli send text --to {NURIA} --message", out); self.assertIn("NO se ha ejecutado", out)
        self.assertEqual(self.log("calls.log"), ""); self.assertEqual(self.log("sent.log"), "")
        db.alta("e", "correo", "correo", "sin borrador")
        self.assertEqual(cli_run("draft", "A2")[0], 1)

    def test_sombra_y_modo(self):
        self.assertFalse(config.entrega_global())
        rc, out = cli_run("sombra", "off"); self.assertEqual(rc, 1); self.assertFalse(config.entrega_global())
        rc, out = cli_run("sombra", "off", "--si"); self.assertTrue(config.entrega_global())
        cli_run("sombra", "on"); self.assertFalse(config.entrega_global())
        cli_run("modo", "wa", "activo"); self.assertEqual(config.cargar()["modo"]["wa"], "activo"); self.assertFalse(config.modo_real(config.cargar(), "wa"))
        self.assertEqual(cli_run("modo", "wa", "loquesea")[0], 1)

    def test_pausa_detiene_el_ciclo(self):
        cli_run("pausa"); self.escribir("wa_chats.json", [])
        self.ciclo(); self.assertEqual(self.log("calls.log"), "")
        cli_run("reanudar"); self.ciclo(); self.assertIn("wacli", self.log("calls.log"))

    def test_list_show_estados_resumen(self):
        db = self.db(); i = db.alta("k", "wa", "item_tarea", "Llamar al fontanero", prio=3, silencioso=True, chat="Nuria", due="2026-10-09", evidencia=f"chat={NURIA};id=M1;ts=2026-10-08T18:03", accion="sombra", detalle="De WhatsApp (Nuria, 08/10)")[0]
        db.alta("k2", "correo", "seguridad", "[varas] Google · Alerta", prio=1)
        rc, out = cli_run("list"); self.assertIn("Llamar al fontanero", out); self.assertIn("Alerta", out)
        rc, out = cli_run("list", "--items"); self.assertNotIn("Alerta", out)
        rc, out = cli_run("show", f"#{i}".lstrip("#")); self.assertIn("wacli --read-only messages context", out); self.assertNotIn(YO, out)
        rc, out = cli_run("resumen-dia"); self.assertIn("Tarea: Llamar al fontanero para el 09/10 · Nuria (sombra: no creada)", out)
        cli_run("hecho", "A2"); self.assertEqual(db.buscar("A2")["estado"], "hecho")
        cli_run("luego", "A2", "2"); self.assertEqual(db.buscar("A2")["estado"], "luego"); self.assertIsNotNone(db.buscar("A2")["pospuesto_hasta"])
        rc, out = cli_run("status"); self.assertEqual(rc, 0); self.assertIn("sombra", out)

    def test_wa_simular_por_cli(self):
        self.escribir("wa_chats.json", [chat(NURIA, "Nuria")]); self.escribir("wa_msgs.json", [msg(NURIA, "Me dices la hora mañana?", "2026-10-08T17:30")])
        self.ahora("2026-10-08T18:00")
        rc, out = cli_run("wa", "simular", "--horas", "3"); d = json.loads(out)
        self.assertEqual((d["mensajes"], d["chats_con_marca"]), (1, 1)); self.assertNotIn("hora mañana", out)
        self.assertFalse((self.estado / "wa.json").exists())


class TestExtremoAExtremo(ZVTest):
    def test_ciclo_completo_en_sombra_con_canario(self):
        """Todos los vigías a la vez con datos falsos: nada se envía, nada se escribe en Google ni en el Cerebro, el canario no queda en disco."""
        self.escribir("wa_chats.json", [chat(NURIA, "Nuria")]); self.escribir("wa_msgs.json", [])
        self.escribir("gog_varas.json", {"threads": [], "events": [], "thread_bodies": {}}); self.escribir("gog_alvarez.json", {})
        self.ciclo()
        self.escribir("wa_msgs.json", [msg(NURIA, f"Me pagas la cena el viernes? {CANARIO}", "2026-10-08T18:03")])
        d = json.loads((FIX / "gog_varas.json").read_text())
        d["threads"] = [{"id": "s1", "from": "Google <no-reply@accounts.google.com>", "subject": "Alerta de seguridad", "labels": ["INBOX", "UNREAD"], "messageCount": 1}]
        d["thread_bodies"] = {"s1": f"Alguien entró. {CANARIO}"}
        self.escribir("gog_varas.json", d)
        self.escribir("llm_resp.json", [json.dumps({"items": [item("Pagar la cena a Nuria", "m1", fecha="2026-10-09")]})])
        self.ahora("2026-10-08T18:20"); self.ciclo()
        filas = self.filas()
        self.assertGreaterEqual(len(filas), 2)
        self.assertEqual(self.log("sent.log"), ""); self.assertEqual(self.log("gog_writes.log"), "")
        calls = self.log("calls.log")
        self.assertNotIn("VIOLACION", calls); self.assertNotIn("PROHIBIDO", calls)
        self.assertFalse([l for l in calls.splitlines() if l.startswith("wacli") and " send" in l])
        self.assertNotIn(CANARIO, self.todo_el_texto())
        self.assertIn("sombra", (self.estado / "sombra.log").read_text())
        for f in [self.estado / "avisos.db", self.estado / "wa.json", self.estado / "sombra.log"]:
            self.assertEqual(oct(f.stat().st_mode & 0o777), "0o600", f.name)
        self.assertEqual(oct(self.estado.stat().st_mode & 0o777), "0o700")


if __name__ == "__main__":
    unittest.main()
