"""Registro de actividad: «leyó» por fuente y ciclo, propuso/escribió/descartó/falló, contrato JSON, retención, migración,
bandeja en solo lectura y que nada sensible llegue al registro."""
import contextlib
import hashlib
import io
import json
import sqlite3
import unittest

from base import CANARIO, FH, FIX, YO, ZVTest, chat, config, msg
from test_wa import IBAN, NURIA, WABase, item
from zv import acciones, cli, flujos, registro
from zv.db import DB

BANDEJA_ESQUEMA = """
CREATE TABLE items(clave TEXT PRIMARY KEY, tipo TEXT, cuenta TEXT, huella TEXT, visto_ts REAL, ultima_ts REAL, estado TEXT, resultado TEXT);
CREATE TABLE acciones(clave TEXT, modo TEXT, tipo TEXT, prio INT, ts REAL, estado TEXT, intentos INT DEFAULT 0, proximo REAL, detalle TEXT, PRIMARY KEY(clave, modo));
CREATE TABLE inbox(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, modo TEXT, prio INT, tipo TEXT, texto TEXT, entregado INT DEFAULT 0, clave TEXT UNIQUE);
CREATE TABLE propuestas(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, clave TEXT UNIQUE, tipo TEXT, campos TEXT, estado TEXT);
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
"""


def cli_run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(list(argv))
    return rc, out.getvalue()


def reg_json(*argv):
    rc, out = cli_run("registro", "--json", *argv)
    return rc, json.loads(out)


class TestContrato(ZVTest):
    def setUp(self):
        super().setUp()
        self.db_ = self.db()
        db = self.db_
        self.ids = [registro.anota(db, "leyo", "correo", "Leí 69 hilos de correo, 0 nuevos", "0 avisos", ts=db.ts() - 300),
                    registro.anota(db, "propuso", "wa", "Habría creado tarea: Llamar al fontanero (para el 09/10)", None, flujo="wa-peticion", ref="aviso:7", ts=db.ts() - 200),
                    registro.anota(db, "fallo", "agenda", "No pude leer la agenda", "ninguna cuenta", ts=db.ts() - 100),
                    registro.anota(db, "escribio", "correo", "Creé tarea: Pagar Orange (para el 20/10)", flujo="correo-pago", modo="vivo", ts=db.ts() - 50)]

    def test_forma_exacta_del_contrato(self):
        rc, d = reg_json()
        self.assertEqual((rc, d["ok"], d["n"]), (0, True, 4))
        for it in d["items"]:
            self.assertEqual(set(it), {"id", "ts", "actor", "fuente", "tipo", "modo", "titulo", "detalle", "flujo", "ref"})
            self.assertRegex(it["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+0[12]:00$")
            self.assertIn(it["actor"], ("vigia", "bandeja", "app")); self.assertIn(it["modo"], ("sombra", "vivo"))
        self.assertEqual([i["tipo"] for i in d["items"]], ["escribio", "fallo", "propuso", "leyo"])         # más reciente primero
        r = d["resumen"]
        self.assertEqual((r["dia"], r["leyo"], r["propuso"], r["escribio"], r["descarto"], r["fallo"], r["aviso"]), ("2026-10-08", 1, 1, 1, 0, 1, 0))
        self.assertEqual(set(r["por_fuente"]), {"wa", "correo", "agenda", "tareas", "sistema"})
        self.assertEqual(r["por_fuente"]["correo"], {"leyo": 1, "propuso": 0, "escribio": 1, "descarto": 0, "fallo": 0, "aviso": 0})
        self.assertEqual(r["por_fuente"]["wa"]["propuso"], 1)
        p = [i for i in d["items"] if i["tipo"] == "propuso"][0]
        self.assertEqual((p["actor"], p["fuente"], p["modo"], p["flujo"], p["ref"]), ("vigia", "wa", "sombra", "wa-peticion", "aviso:7"))
        e = [i for i in d["items"] if i["tipo"] == "escribio"][0]
        self.assertEqual(e["modo"], "vivo")

    def test_filtros(self):
        self.assertEqual([i["tipo"] for i in reg_json("--tipo", "fallo")[1]["items"]], ["fallo"])
        self.assertEqual([i["fuente"] for i in reg_json("--fuente", "correo")[1]["items"]], ["correo", "correo"])
        self.assertEqual(reg_json("-n", "2")[1]["n"], 2)
        self.assertEqual(reg_json("--dia", "2026-10-07")[1]["n"], 0)
        self.assertEqual(reg_json("--dia", "2026-10-08")[1]["n"], 4)
        self.assertEqual(reg_json("--dia", "2026-10-07")[1]["resumen"]["dia"], "2026-10-07")
        desde = "2026-10-08T17:56:00+02:00"                     # ahora = 18:00:00
        self.assertEqual([i["tipo"] for i in reg_json("--desde", desde)[1]["items"]], ["escribio", "fallo", "propuso"])
        self.assertEqual(reg_json("--desde", "2026-10-08T15:56:00Z")[1]["n"], 3)        # mismo instante en UTC

    def test_argumentos_malos_dan_error_json_sin_trazas(self):
        rc, d = reg_json("--dia", "ayer")
        self.assertEqual((rc, d["ok"]), (2, False)); self.assertIn("AAAA-MM-DD", d["error"])
        self.assertEqual(reg_json("--desde", "nunca")[0], 2)

    def test_salida_legible_en_castellano(self):
        rc, out = cli_run("registro")
        self.assertEqual(rc, 0)
        self.assertIn("Actividad del 08/10: 1 lecturas, 1 propuestas", out); self.assertIn("Vigía · Correo · Leyó: Leí 69 hilos de correo, 0 nuevos", out)
        self.assertIn("Propuso: Habría creado tarea: Llamar al fontanero (para el 09/10) [flujo wa-peticion] (sombra)", out)
        self.assertIn("Escribió: Creé tarea: Pagar Orange", out)
        rc, out = cli_run("registro", "--dia", "2026-01-01"); self.assertIn("No hay actividad", out)

    def test_escribio_siempre_es_vivo_y_valores_raros_no_revientan(self):
        db = self.db_
        i = registro.anota(db, "escribio", "wa", "x", modo="sombra")
        self.assertEqual(db.c.execute("SELECT modo FROM registro WHERE id=?", (i,)).fetchone()[0], "vivo")
        self.assertIsNone(registro.anota(db, "inventado", "wa", "x"))
        self.assertIsNone(registro.anota(db, "leyo", "marte", "x"))
        a = registro.anota(db, "leyo", "wa", "dup", clave="k1"); b = registro.anota(db, "leyo", "wa", "dup", clave="k1")
        self.assertEqual((a is not None, b), (True, None))

    def test_nada_sensible_llega_al_registro(self):
        db = self.db_
        registro.anota(db, "propuso", "correo", f"Habría avisado: pagar a {IBAN}", f"DNI 12345678Z teléfono 612345678 {CANARIO}"[:120])
        t = json.dumps(reg_json()[1], ensure_ascii=False)
        for dato in (IBAN, "12345678Z", "612345678"):
            self.assertNotIn(dato, t)
        long = registro.anota(db, "leyo", "wa", "L" * 500, "D" * 900)
        r = db.c.execute("SELECT titulo, detalle FROM registro WHERE id=?", (long,)).fetchone()
        self.assertLessEqual((len(r[0]), len(r[1])), (120, 200))


class TestCiclos(ZVTest):
    def setUp(self):
        super().setUp()
        self.escribir("wa_chats.json", [chat(NURIA, "Nuria")]); self.escribir("wa_msgs.json", [])
        self.escribir("gog_varas.json", {"threads": [{"id": "t0", "from": "Amazon <no-reply@amazon.es>", "subject": "Tu pedido", "labels": ["INBOX"], "messageCount": 1}],
                                         "tasks": {"@default": [{"id": "T1", "title": "Llamar al médico", "status": "needsAction", "due": "2026-10-07T00:00:00Z"}]}})
        self.escribir("gog_alvarez.json", {})

    def reg(self, tipo=None, fuente=None):
        q, a = "SELECT * FROM registro WHERE actor='vigia'", []
        for col, v in (("tipo", tipo), ("fuente", fuente)):
            if v:
                q += f" AND {col}=?"; a.append(v)
        return self.filas(q + " ORDER BY id", a)

    def test_un_leyo_por_fuente_y_ciclo(self):
        self.ciclo()
        ley = {r["fuente"]: r for r in self.reg("leyo")}
        self.assertEqual(set(ley), {"wa", "correo", "agenda", "tareas"})
        self.assertIn("Primera lectura de WhatsApp", ley["wa"]["titulo"])
        self.assertEqual(ley["correo"]["titulo"], "Leí 1 hilos de correo, 0 nuevos")
        self.assertRegex(ley["agenda"]["titulo"], r"^Leí \d+ eventos de la agenda$")
        self.assertEqual(ley["tareas"]["titulo"], "Leí 1 tareas de Google Tasks, 1 vencidas")
        self.ahora("2026-10-08T18:30"); self.ciclo()
        self.assertEqual(len(self.reg("leyo")), 8)                       # otro por fuente y ciclo
        wa = [r for r in self.reg("leyo", "wa")][-1]
        self.assertEqual(wa["titulo"], "Leí 0 mensajes de WhatsApp, 0 con posible interés")

    def test_leyo_dice_cifras_y_motivos_de_descarte_sin_texto(self):
        self.ciclo()
        self.escribir("wa_msgs.json", [msg(NURIA, "ok", "2026-10-08T18:03"), msg(NURIA, "vale", "2026-10-08T18:04")])
        self.ahora("2026-10-08T18:10"); self.ciclo("wa")
        r = self.reg("leyo", "wa")[-1]
        self.assertEqual(r["titulo"], "Leí 2 mensajes de WhatsApp, 0 con posible interés"); self.assertIn("2 acuses", r["detalle"])
        self.assertNotIn(CANARIO, self.todo_el_texto())

    def test_fallo_de_una_fuente(self):
        self.ciclo()
        (FIX / "wa_falla").write_text("1")
        self.ahora("2026-10-08T18:30"); self.ciclo("wa")
        f = self.reg("fallo", "wa")
        self.assertEqual(len(f), 1); self.assertEqual(f[0]["titulo"], "No pude leer WhatsApp"); self.assertIn("WaError", f[0]["detalle"])
        (FIX / "gog_falla_varas").write_text("9"); (FIX / "gog_falla_alvarez").write_text("9")
        self.ahora("2026-10-08T19:00"); self.ciclo("agenda")
        self.assertEqual([r["titulo"] for r in self.reg("fallo", "agenda")], ["No pude leer la agenda"])
        self.ciclo("correo")
        self.assertEqual([r["titulo"] for r in self.reg("fallo", "correo")], ["No pude leer el correo"])

    def test_sombra_nunca_deja_escribio_y_propuso_lo_que_haria(self):
        self.escribir("gog_varas.json", {"events": [{"id": "x", "summary": "Revisión coche", "start": {"dateTime": "2026-10-12T17:00:00+02:00"}, "end": {"dateTime": "2026-10-12T18:00:00+02:00"},
                                                    "status": "confirmed", "creator": {"self": True}, "organizer": {"self": True}, "CalendarID": "primary"}]})
        self.ahora("2026-10-12T16:50"); self.ciclo("agenda")                            # a punto de empezar: sale el aviso del evento
        self.assertEqual(self.reg("escribio"), [])
        p = [r["titulo"] for r in self.reg("propuso", "agenda")]
        self.assertIn("Habría avisado: 17:00 Revisión coche", p)
        self.assertTrue(all(r["modo"] == "sombra" for r in self.reg("propuso")))
        self.assertEqual(self.log("gog_writes.log"), "")

    def test_aviso_solo_cuando_se_entrega_de_verdad(self):
        d = json.loads((FIX / "gog_varas.json").read_text())
        self.ciclo()
        d["threads"] = [{"id": "s1", "from": "Google <no-reply@accounts.google.com>", "subject": "Alerta de seguridad", "labels": ["INBOX", "UNREAD"], "messageCount": 1}] + d["threads"]
        self.escribir("gog_varas.json", d)
        self.ahora("2026-10-08T18:30"); self.ciclo("correo")
        self.assertEqual(self.reg("aviso"), [])                                    # sombra: solo «Habría avisado»
        self.assertTrue(any(r["titulo"].startswith("Habría avisado: [varas] Google") for r in self.reg("propuso", "correo")))
        self.cfg_set(**{"modo.correo": "activo"}); config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_entrega().touch()
        d["threads"][0]["id"] = "s2"; self.escribir("gog_varas.json", d)
        self.ahora("2026-10-08T19:00"); self.ciclo("correo")
        a = self.reg("aviso")
        self.assertEqual(len(a), 1); self.assertTrue(a[0]["titulo"].startswith("Avisé por WhatsApp: [varas] Google")); self.assertEqual(a[0]["modo"], "vivo")
        self.assertIn("Voy a avisar", [r["titulo"] for r in self.reg("propuso", "correo")][-1])

    def test_caduca_sin_avisar(self):
        db = self.db()
        db.alta("v", "agenda", "evento", "Cita", prio=2, vence=db.ts() - 5)
        self.ciclo("agenda")
        self.assertTrue(any(r["titulo"] == "Caducó sin avisar: Cita" for r in self.reg("descarto")))

    def test_descartar_hecho_y_luego_desde_la_app(self):
        db = self.db()
        for k, f in (("a", "correo"), ("b", "wa"), ("c", "agenda")):
            db.alta(k, f, "correo", f"Aviso {k}", prio=2)
        cli_run("descartar", "A1"); cli_run("hecho", "A2"); cli_run("luego", "A3", "2")
        d = reg_json("--tipo", "descarto")[1]
        t = {i["titulo"]: i for i in d["items"]}
        self.assertEqual(set(t), {"Descartado: Aviso a", "Marcado como hecho: Aviso b", "Pospuesto 2 h: Aviso c"})
        self.assertTrue(all(i["actor"] == "app" and i["ref"].startswith("aviso:") for i in d["items"]))
        self.assertEqual({i["fuente"] for i in d["items"]}, {"correo", "wa", "agenda"})


class TestWaYFlujo(WABase):
    def llega(self):
        self.msgs += [msg(NURIA, f"Me mandas el presupuesto mañana? {CANARIO} mi cuenta {IBAN}", "2026-10-08T18:03")]; self.guardar()
        self.llm_resp(json.dumps({"items": [item("Mandar el presupuesto a Nuria", "m2")]}))
        self.ahora("2026-10-08T18:20"); self.ciclo("wa")

    def reg(self, tipo):
        return self.filas("SELECT * FROM registro WHERE tipo=? ORDER BY id", (tipo,))

    def test_sombra_registra_la_propuesta_con_su_flujo_y_cuenta_el_disparo(self):
        self.llega()
        p = self.reg("propuso")
        self.assertEqual([(r["titulo"], r["flujo"], r["fuente"], r["modo"]) for r in p], [("Habría creado tarea: Mandar el presupuesto a Nuria (para el 09/10)", "wa-peticion", "wa", "sombra")])
        self.assertEqual(self.reg("escribio"), [])
        w = {f["id"]: f for f in json.loads(cli_run("flujos", "--json")[1])["flujos"]}["wa-peticion"]
        self.assertEqual((w["disparos_7d"], w["modo"], w["escribe_ahora"]), (1, "sombra", False)); self.assertIsNotNone(w["ultimo"])
        disco = self.todo_el_texto()
        self.assertNotIn(CANARIO, disco); self.assertNotIn(IBAN, disco)

    def test_vigia_wa_activo_pero_flujo_en_sombra_no_escribe(self):
        self.cfg_set(**{"modo.wa": "activo"}); config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_entrega().touch()
        self.llega()
        self.assertEqual([r["accion"] for r in self.items()], ["sombra"])
        self.assertEqual(self.log("gog_writes.log"), ""); self.assertEqual(self.reg("escribio"), [])

    def test_con_el_flujo_activo_escribe_y_lo_registra(self):
        self.cfg_set(**{"modo.wa": "activo", "flujos.wa-peticion.modo": "activo"}); config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_entrega().touch()
        self.llega()
        e = self.reg("escribio")
        self.assertEqual([(r["titulo"], r["flujo"], r["modo"]) for r in e], [("Creé tarea: Mandar el presupuesto a Nuria (para el 09/10)", "wa-peticion", "vivo")])
        self.assertEqual(len(self.log("gog_writes.log").splitlines()), 2)
        self.ciclo("wa"); self.assertEqual(len(self.log("gog_writes.log").splitlines()), 2)

    def test_flujo_pausado_no_consulta_el_modelo_ni_apunta(self):
        cli_run("flujo", "wa-peticion", "pausa")
        self.llega()
        self.assertEqual(self.items(), []); self.assertEqual(self.llamadas_llm(), []); self.assertEqual(self.reg("propuso"), [])
        cli_run("flujo", "wa-peticion", "reanuda")


class TestRetencionYMigracion(ZVTest):
    def test_purga_a_los_30_dias(self):
        db = self.db()
        registro.anota(db, "leyo", "wa", "viejo", ts=db.ts() - 31 * 86400); registro.anota(db, "leyo", "wa", "reciente", ts=db.ts() - 29 * 86400)
        db.purgar(config.cargar())
        self.assertEqual([r["titulo"] for r in self.filas("SELECT titulo FROM registro")], ["reciente"])
        self.assertEqual(config.cargar()["retencion"]["registro_dias"], 30)

    def test_el_ciclo_purga(self):
        db = self.db(); registro.anota(db, "leyo", "wa", "viejo", ts=db.ts() - 40 * 86400); db.close()
        self.escribir("wa_chats.json", []); self.ciclo("wa")
        self.assertNotIn("viejo", [r["titulo"] for r in self.filas("SELECT titulo FROM registro")])

    def test_migracion_idempotente_no_pierde_avisos(self):
        db = self.db()
        db.alta("k1", "correo", "dinero", "Aviso viejo", prio=1); db.alta("k2", "wa", "item_tarea", "Item viejo", silencioso=True, due="2026-10-09", accion="sombra")
        db.c.executescript("DROP TABLE registro; DROP INDEX IF EXISTS ix_registro_ts; DROP INDEX IF EXISTS ix_registro_flujo;")    # BD de antes del cambio
        db.close()
        c = sqlite3.connect(self.estado / "avisos.db")
        self.assertEqual(c.execute("SELECT name FROM sqlite_master WHERE name='registro'").fetchall(), []); c.close()
        for _ in range(3):                                                  # abrir varias veces: idempotente
            d = DB(); d.close()
        self.assertEqual([r["titulo"] for r in self.filas("SELECT titulo FROM avisos ORDER BY id")], ["Aviso viejo", "Item viejo"])
        cols = [r[1] for r in self.db().c.execute("PRAGMA table_info(registro)")]
        self.assertEqual(cols, ["id", "ts", "actor", "fuente", "tipo", "modo", "titulo", "detalle", "flujo", "ref", "clave", "disparo"])
        self.assertEqual(oct((self.estado / "avisos.db").stat().st_mode & 0o777), "0o600")


class TestBandejaSoloLectura(ZVTest):
    def crear_bandeja(self):
        d = FH / ".local/state/zazu-bandeja"
        d.mkdir(parents=True, exist_ok=True)
        ruta = d / "estado.db"
        c = sqlite3.connect(ruta)
        c.executescript(BANDEJA_ESQUEMA)
        t = config.ahora().timestamp()
        filas = [("g:varas:ev1:2026-11-05", "sombra", "gemela", 3, t - 600, "sombra", "crearía la tarea «Viaje Valencia–París (Vueling)» para el 05/11 en Mis tareas (varas) con la nota «gemela de evento»"),
                 ("a:t1", "sombra", "aplicar", 2, t - 500, "sombra", "buscaría en Cerebro/Candidaturas | pondría el plazo como fecha de la tarea"),
                 ("g:varas:ev2:2026-11-06", "vivo", "gemela", 3, t - 400, "hecho", "tarea gemela creada"),
                 ("g:varas:ev3:2026-11-07", "vivo", "gemela", 3, t - 300, "fallido", f"Google no responde {IBAN}"),
                 ("g:varas:ev4:2026-11-08", "vivo", "gemela", 3, t - 250, "omitido", "existía antes de activar (línea base)"),
                 ("av:1", "sombra", "aviso", 2, t - 200, "sombra", "duplicada con el inbox")]
        c.executemany("INSERT INTO acciones(clave,modo,tipo,prio,ts,estado,detalle) VALUES(?,?,?,?,?,?,?)", filas)
        c.executemany("INSERT INTO inbox(ts,modo,prio,tipo,texto,entregado,clave) VALUES(?,?,?,?,?,?,?)",
                      [(t - 200, "sombra", 2, "aviso", "📌 Pagar la luz mañana", 0, "av:1"), (t - 150, "vivo", 1, "aviso", "📌 Cita dentista a las 10", 1, "av:2"),
                       (t - 120, "vivo", 1, "error", "🔑 Hay que volver a autorizar Google (varas).", 0, "auth:varas")])
        c.execute("INSERT INTO meta VALUES('ultimo_ciclo', ?)", (config.ahora().replace(second=0).isoformat(timespec="seconds") + " ok",))
        c.executemany("INSERT INTO items(clave,tipo,cuenta,huella,visto_ts,ultima_ts) VALUES(?,?,?,?,?,?)", [("t:a", "tarea", "varas", "h", t, t), ("t:b", "tarea", "varas", "h", t, t), ("e:a", "evento", "varas", "h", t, t)])
        c.commit(); c.close()
        return ruta

    def test_se_mezcla_con_actor_bandeja_sin_tocar_su_base(self):
        ruta = self.crear_bandeja()
        antes = (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns, sorted(p.name for p in ruta.parent.iterdir()))
        db = self.db(); registro.anota(db, "leyo", "correo", "Leí 3 hilos de correo, 0 nuevos")
        rc, d = reg_json()
        b = [i for i in d["items"] if i["actor"] == "bandeja"]
        t = {(i["tipo"], i["titulo"]) for i in b}
        self.assertIn(("propuso", "Habría creado tarea gemela: Viaje Valencia–París (Vueling)"), t)
        self.assertIn(("propuso", "Habría creado candidatura"), t)
        self.assertIn(("escribio", "Creó tarea gemela"), t)
        self.assertIn(("fallo", "No pudo crear tarea gemela"), t)
        self.assertIn(("descarto", "No toca tarea gemela (ya existía antes de activar)"), t)
        self.assertIn(("propuso", "Habría avisado: 📌 Pagar la luz mañana"), t)
        self.assertIn(("aviso", "Avisó: 📌 Cita dentista a las 10"), t)
        self.assertIn(("fallo", "🔑 Hay que volver a autorizar Google (varas)."), t)
        self.assertIn(("leyo", "La bandeja revisó 2 tareas y 1 eventos"), t)
        self.assertEqual(len([x for x in b if "duplicada" in (x["detalle"] or "")]), 0)       # el aviso no sale dos veces (acciones + inbox)
        self.assertTrue(all(i["modo"] in ("sombra", "vivo") for i in b))
        self.assertEqual([i for i in d["items"] if i["tipo"] == "escribio" and i["actor"] == "vigia"], [])
        self.assertNotIn(IBAN, json.dumps(d, ensure_ascii=False))                              # lo del detalle pasa por el filtro
        self.assertEqual(len({i["id"] for i in d["items"]}), len(d["items"]))
        self.assertGreater(d["resumen"]["propuso"], 0); self.assertEqual(d["resumen"]["por_fuente"]["agenda"]["propuso"], 1)
        despues = (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns, sorted(p.name for p in ruta.parent.iterdir()))
        self.assertEqual(antes, despues)                                                         # ni un byte, ni -wal, ni -journal

    def test_filtros_aplican_tambien_a_la_bandeja(self):
        self.crear_bandeja()
        self.assertTrue(all(i["tipo"] == "aviso" for i in reg_json("--tipo", "aviso")[1]["items"]))
        self.assertTrue(all(i["fuente"] == "agenda" for i in reg_json("--fuente", "agenda")[1]["items"]))
        self.assertEqual(reg_json("--dia", "2026-10-07")[1]["n"], 0)

    def test_si_no_hay_bandeja_o_esta_rota_no_pasa_nada(self):
        self.assertEqual(reg_json()[1]["n"], 0)
        d = FH / ".local/state/zazu-bandeja"; d.mkdir(parents=True, exist_ok=True)
        (d / "estado.db").write_bytes(b"esto no es sqlite")
        self.assertEqual(reg_json()[0], 0)
        (d / "estado.db").unlink()


if __name__ == "__main__":
    unittest.main()
