import json
import os
import unittest

from base import FIX, ZVTest, config
from zv import calma, entrega
from zv.db import DB


class TestDB(ZVTest):
    def test_dedupe_y_codigos(self):
        db = self.db()
        a, n1 = db.alta("k1", "correo", "correo", "Hola 612345678 mundo", prio=2)
        b, n2 = db.alta("k1", "correo", "correo", "otra", prio=2)
        c, n3 = db.alta("k2", "correo", "correo", "dos")
        self.assertTrue(n1); self.assertFalse(n2); self.assertTrue(n3)
        self.assertEqual(a, b)
        self.assertEqual(db.buscar("A1")["id"], a); self.assertEqual(db.buscar("a2")["id"], c)
        self.assertNotIn("612345678", db.buscar(a)["titulo"])   # tachado al guardar

    def test_fallos_umbral_y_resuelto(self):
        db = self.db()
        self.assertIsNone(db.latido("x", False, "e")); self.assertIsNone(db.latido("x", False, "e"))
        self.assertEqual(db.latido("x", False, "e"), "fallo_alerta")
        self.assertIsNone(db.latido("x", False, "e"))        # una sola vez
        self.assertEqual(db.latido("x", True), "resuelto")
        self.assertIsNone(db.latido("x", True))

    def test_purga_borradores(self):
        db = self.db()
        i, _ = db.alta("k", "wa", "wa_urgente", "t", borrador="borr")
        db.c.execute("UPDATE avisos SET creado=? WHERE id=?", (db.ts() - 50 * 3600, i)); db.c.commit()
        db.purgar(config.cargar())
        self.assertEqual(db.buscar(i)["borrador"], "")
        db.c.execute("UPDATE avisos SET creado=? WHERE id=?", (db.ts() - 20 * 86400, i)); db.c.commit()
        db.purgar(config.cargar())
        self.assertIsNone(db.buscar(i))


class TestCalma(ZVTest):
    def test_silencio(self):
        cfg = config.cargar()
        from datetime import datetime
        f = lambda h, m: datetime(2026, 10, 8, h, m, tzinfo=config.TZ)
        self.assertTrue(calma.en_silencio(f(23, 0), cfg)); self.assertTrue(calma.en_silencio(f(3, 0), cfg)); self.assertTrue(calma.en_silencio(f(7, 29), cfg))
        self.assertFalse(calma.en_silencio(f(7, 30), cfg)); self.assertFalse(calma.en_silencio(f(22, 59), cfg))
        self.assertEqual(calma.ventana_digest(f(13, 5), cfg), "2026-10-08T13:00"); self.assertIsNone(calma.ventana_digest(f(8, 0), cfg))


class TestEntrega(ZVTest):
    def alta(self, db, clave, prio=2, **k):
        return db.alta(clave, "correo", k.pop("tipo", "correo"), f"aviso {clave}", prio=prio, ref=k.pop("ref", clave), **k)[0]

    def test_sombra_por_defecto_no_envia(self):
        db = self.db(); self.alta(db, "a", 1)
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 1); self.assertEqual(self.log("sent.log"), "")
        self.assertIn("aviso a", (self.estado / "sombra.log").read_text())
        self.assertEqual(db.buscar("A1")["entrega"], "sombra")

    def test_modo_activo_sin_interruptor_sigue_en_sombra(self):
        self.cfg_set(**{"modo.correo": "activo"})
        db = self.db(); self.alta(db, "a", 1)
        entrega.procesar(db, config.cargar())
        self.assertEqual(self.log("sent.log"), "")

    def test_real_exige_interruptor_modo_y_sin_pausa(self):
        self.cfg_set(**{"modo.correo": "activo"})
        config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_entrega().touch()
        db = self.db(); self.alta(db, "a", 1)
        config.f_pausa().touch()
        entrega.procesar(db, config.cargar())     # con PAUSA no es real (lo normal es que ciclo() ni llegue aquí)
        self.assertEqual(self.log("sent.log"), "")
        config.f_pausa().unlink()
        self.alta(db, "b", 1)
        entrega.procesar(db, config.cargar())
        self.assertIn("aviso b", self.log("sent.log"))

    def test_silencio_retiene_y_libera(self):
        db = self.db()
        self.ahora("2026-10-08T23:30")
        self.alta(db, "p2", 2); self.alta(db, "p1", 1); self.alta(db, "seg", 1, noche_ok=True, tipo="seguridad")
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 1)                       # solo seguridad/cargo de noche
        self.assertEqual(db.buscar("A3")["entrega"], "sombra")
        self.assertEqual(db.buscar("A1")["entrega"], "retenido"); self.assertEqual(db.buscar("A2")["entrega"], "retenido")
        self.ahora("2026-10-09T07:00"); entrega.procesar(db, config.cargar())
        self.assertEqual(db.buscar("A1")["entrega"], "retenido")
        self.ahora("2026-10-09T07:31"); r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 2); self.assertIn("Mientras no te molestaba", (self.estado / "sombra.log").read_text())

    def test_limite_y_resumen(self):
        db = self.db()
        for i in range(6):
            self.alta(db, f"n{i}", 2)
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 4); self.assertEqual(r["diferidos"], 2)    # 4 por cada 3 h
        self.ahora("2026-10-08T18:10"); r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 0)                        # los diferidos esperan a una ventana posterior
        self.ahora("2026-10-08T21:05"); r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 0)                        # (la ventana de las 18:00 ya pasó: la siguiente es mañana a las 09:00)
        self.ahora("2026-10-09T09:05"); r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 2); self.assertEqual(r["resumenes"], 1)
        self.assertIn("Resumen de avisos pendientes", (self.estado / "sombra.log").read_text())

    def test_p1_ignora_limite_programado_exento(self):
        db = self.db()
        for i in range(6):
            self.alta(db, f"u{i}", 1)
        for i in range(6):
            self.alta(db, f"p{i}", 2, programado=True, tipo="evento")
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["sombra"], 12)

    def test_cooldown_por_chat(self):
        db = self.db()
        self.alta(db, "x1", 2, ref="chat1"); entrega.procesar(db, config.cargar())
        self.ahora("2026-10-08T18:20")
        self.alta(db, "x2", 2, ref="chat1")
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["diferidos"], 1)

    def test_caducado(self):
        db = self.db(); self.alta(db, "v", 2, vence=db.ts() - 5)
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["caducados"], 1)

    def test_fallo_de_envio_reintenta(self):
        self.cfg_set(**{"modo.correo": "activo"}); config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_entrega().touch()
        os.environ["ZV_HERMES"] = "/bin/false"
        try:
            db = self.db(); self.alta(db, "z", 1)
            entrega.procesar(db, config.cargar())
            self.assertEqual(db.buscar("A1")["entrega"], "pendiente"); self.assertEqual(db.buscar("A1")["intentos"], 1)
        finally:
            del os.environ["ZV_HERMES"]


if __name__ == "__main__":
    unittest.main()


class TestEntregaApp(ZVTest):
    """Avisos por la app: salen con su propio interruptor y NUNCA abren la escritura en Google."""
    def setUp(self):
        super().setUp()
        self.cfg_set(**{"modo.correo": "activo", "entrega.canal": "app"})

    def alta(self, db, clave, prio=2, **k):
        return db.alta(clave, "correo", k.pop("tipo", "correo"), f"aviso {clave}", prio=prio, ref=k.pop("ref", clave), **k)[0]

    def push(self):
        return [json.loads(l) for l in self.log("push.log").splitlines() if l.strip()]

    def test_sin_interruptor_de_avisos_todo_sigue_en_sombra(self):
        db = self.db(); self.alta(db, "a", 1)
        r = entrega.procesar(db, config.cargar())
        self.assertEqual((r["sombra"], r["enviados"]), (1, 0)); self.assertEqual(self.push(), [])

    def test_con_interruptor_sale_por_la_app_sin_abrir_google(self):
        config.actualizar("entrega.avisos", True)
        db = self.db(); self.alta(db, "a", 1, borrador="ok, gracias")
        r = entrega.procesar(db, config.cargar())
        self.assertEqual(r["enviados"], 1); self.assertEqual(self.log("sent.log"), "")            # nada por WhatsApp
        p = self.push()
        self.assertEqual(len(p), 1); self.assertIn("aviso a", p[0]["cuerpo"]); self.assertNotIn("Borrador", p[0]["cuerpo"])   # el «di manda A1» no va a la app
        self.assertEqual(db.buscar("A1")["entrega"], "enviado")
        self.assertFalse(config.entrega_global()); self.assertFalse(config.modo_real(config.cargar(), "correo"))   # Google sigue sin escribirse

    def test_pausa_y_modo_sombra_siguen_mandando_mas_que_el_interruptor(self):
        config.actualizar("entrega.avisos", True)
        db = self.db(); self.alta(db, "a", 1)
        config.conf_dir().mkdir(parents=True, exist_ok=True); config.f_pausa().touch()
        entrega.procesar(db, config.cargar()); self.assertEqual(self.push(), [])
        config.f_pausa().unlink(); self.cfg_set(**{"modo.correo": "sombra"})
        self.alta(db, "b", 1); entrega.procesar(db, config.cargar()); self.assertEqual(self.push(), [])

    def test_si_no_llega_a_ningun_aparato_se_reintenta_y_no_se_da_por_enviado(self):
        config.actualizar("entrega.avisos", True)
        (FIX / "push-falla").write_text("")
        db = self.db(); self.alta(db, "a", 1)
        entrega.procesar(db, config.cargar())
        a = db.buscar("A1"); self.assertEqual((a["entrega"], a["intentos"]), ("pendiente", 1))
        (FIX / "push-falla").unlink()
        entrega.procesar(db, config.cargar()); self.assertEqual(db.buscar("A1")["entrega"], "enviado")

    def test_muchos_avisos_salen_en_un_solo_resumen(self):
        config.actualizar("entrega.avisos", True)
        db = self.db()
        for i in range(6): self.alta(db, f"x{i}", 1)
        entrega.procesar(db, config.cargar())
        p = self.push(); self.assertEqual(len(p), 1); self.assertIn("6 avisos", p[0]["titulo"])
