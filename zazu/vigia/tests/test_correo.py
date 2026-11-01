import json
import unittest

from base import CANARIO, FIX, ZVTest, config


def hilo(i, de, asunto, n=1, labs=("INBOX", "UNREAD", "CATEGORY_UPDATES")):
    return {"id": i, "date": "2026-10-08", "internalDateIso": "2026-10-08T10:00:00Z", "from": de, "subject": asunto, "labels": list(labs), "messageCount": n}


class TestCorreo(ZVTest):
    def setUp(self):
        super().setUp()
        self.hilos = {"varas": [hilo("t0", "Amazon <no-reply@amazon.es>", "Tu pedido ha salido")], "alvarez": []}
        self.guardar()
        self.ciclo("correo")      # línea base

    def guardar(self):
        for acc, hs in self.hilos.items():
            d = {"threads": hs}
            p = FIX / f"gog_{acc}.json"
            if p.exists():
                d = {**json.loads(p.read_text()), "threads": hs}
            self.escribir(f"gog_{acc}.json", d)

    def cuerpos(self, acc, **b):
        d = json.loads((FIX / f"gog_{acc}.json").read_text()); d["thread_bodies"] = b; self.escribir(f"gog_{acc}.json", d)

    def avisos(self):
        return self.filas("SELECT * FROM avisos WHERE fuente='correo' ORDER BY id")

    def test_linea_base_no_avisa_y_repeticion_tampoco(self):
        self.assertEqual(self.avisos(), [])
        self.ciclo("correo"); self.assertEqual(self.avisos(), [])

    def test_clases_y_dedupe(self):
        self.hilos["varas"] += [hilo("s1", "Google <no-reply@accounts.google.com>", "Alerta de seguridad: nuevo inicio de sesión"),
                                hilo("c1", "Banco X <avisos@bancox.es>", "Cargo en tu cuenta de 49,99 €"),
                                hilo("o1", "DGT <noreply@dgt.es>", "Notificación de la DGT"),
                                hilo("e1", "Ana RRHH <ana@acme.com>", "Entrevista con ACME: elige horario"),
                                hilo("d1", "Telefonía <facturas@tel.es>", "Tu factura de octubre"),
                                hilo("r1", "News <news@x.com>", "Newsletter: descuento especial"),
                                hilo("a1", "ACME <jobs@acme.com>", "Gracias por aplicar a ACME"),
                                hilo("l1", "Ana <ana@acme.com>", "Factura leída", labs=("INBOX", "CATEGORY_UPDATES"))]
        self.hilos["alvarez"] += [hilo("x1", "Hacienda <aviso@agenciatributaria.gob.es>", "Aviso")]
        self.guardar()
        self.cuerpos("varas", e1=f"Hola, elige hora aquí https://acme.com/cita/123?x=1. Ref {CANARIO}")
        self.ciclo("correo")
        por = {a["clave"].split(":")[2]: a for a in self.avisos()}
        self.assertEqual(set(por), {"s1", "c1", "o1", "e1", "d1", "x1"})
        self.assertEqual((por["s1"]["tipo"], por["s1"]["prio"], por["s1"]["noche_ok"]), ("seguridad", 1, 1))
        self.assertEqual((por["c1"]["tipo"], por["c1"]["noche_ok"]), ("cobro", 1))
        self.assertEqual((por["e1"]["tipo"], por["e1"]["noche_ok"], por["e1"]["enlace"]), ("entrevista", 0, "https://acme.com/cita/123?x=1"))
        self.assertTrue(por["x1"]["titulo"].startswith("[alvarez]") and por["x1"]["tipo"] == "oficial")
        self.assertNotIn(CANARIO, self.todo_el_texto())                 # del cuerpo solo sale el enlace
        n = len(self.avisos()); self.ciclo("correo"); self.assertEqual(len(self.avisos()), n)

    def test_respuesta_nueva_en_hilo_viejo_avisa(self):
        self.hilos["varas"] = [hilo("t0", "Ana <ana@acme.com>", "Entrevista: confirmación", n=1, labs=("INBOX", "CATEGORY_UPDATES"))]; self.guardar(); self.ciclo("correo")
        self.hilos["varas"] = [hilo("t0", "Ana <ana@acme.com>", "Entrevista: confirmación", n=2)]; self.guardar(); self.ciclo("correo")
        self.assertEqual([a["clave"] for a in self.avisos()], ["correo:varas:t0:2"])

    def test_p2_con_modelo(self):
        self.hilos["varas"] += [hilo("h1", "Marta Gil <marta@gmail.com>", "¿Quedamos para lo del piso?", labs=("INBOX", "UNREAD", "IMPORTANT")),
                                hilo("h2", "Pepe <pepe@gmail.com>", "Foto del finde", labs=("INBOX", "UNREAD", "IMPORTANT"))]
        self.guardar()
        self.escribir("llm_resp.json", [json.dumps({"requiere_accion": True, "resumen": "Pide quedar para firmar el piso", "plazo": "viernes"}),
                                        json.dumps({"requiere_accion": False, "resumen": "", "plazo": None})])
        self.ciclo("correo")
        a = self.avisos()
        self.assertEqual(len(a), 1); self.assertEqual((a[0]["tipo"], a[0]["prio"]), ("correo", 2)); self.assertIn("firmar el piso", a[0]["detalle"]); self.assertIn("plazo: viernes", a[0]["detalle"])

    def test_p2_sin_presupuesto_avisa_sin_resumen(self):
        self.cfg_set(**{"llm.habilitado": False})
        self.hilos["varas"] += [hilo("h1", "Marta Gil <marta@gmail.com>", "¿Quedamos?", labs=("INBOX", "UNREAD", "IMPORTANT"))]; self.guardar(); self.ciclo("correo")
        self.assertIn("sin resumen", self.avisos()[0]["detalle"]); self.assertEqual(self.log("llm_prompts.log"), "")

    def test_automaticos_no_humanos_no_avisan(self):
        self.hilos["varas"] += [hilo("n1", "LinkedIn <jobs-noreply@linkedin.com>", "Nuevas ofertas para ti", labs=("INBOX", "UNREAD", "IMPORTANT")),
                                hilo("n2", "Tienda <info@tienda.com>", "Tu pedido", labs=("INBOX", "UNREAD", "IMPORTANT"))]
        self.guardar(); self.ciclo("correo"); self.assertEqual(self.avisos(), [])
        self.assertEqual(self.log("llm_prompts.log"), "")

    def test_error_de_autorizacion(self):
        (FIX / "gog_falla_alvarez").write_text("4")
        self.ciclo("correo")
        a = self.filas("SELECT * FROM avisos WHERE clave LIKE 'fallo:auth:alvarez%'")
        self.assertEqual(len(a), 1); self.assertEqual(a[0]["prio"], 1)

    def test_no_se_llama_a_escrituras(self):
        self.hilos["varas"] += [hilo("s1", "Google <no-reply@accounts.google.com>", "Alerta de seguridad")]; self.guardar(); self.ciclo("correo")
        c = self.log("calls.log")
        self.assertNotIn("PROHIBIDO", c); self.assertNotIn(" send", c); self.assertEqual(self.log("gog_writes.log"), "")
        self.assertIn("--readonly", c)


if __name__ == "__main__":
    unittest.main()
