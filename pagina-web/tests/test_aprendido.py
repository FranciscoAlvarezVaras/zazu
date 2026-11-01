"""«Qué ha aprendido Zazu» (aprendido.py): mapa de lecciones y decisiones. Sobre una base temporal, nunca el almacén de verdad.

    python3 -m unittest tests.test_aprendido
"""
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ESQUEMA = """CREATE TABLE hecho (id INTEGER PRIMARY KEY, clave TEXT UNIQUE, fuente TEXT, tipo TEXT, ts REAL, perfil TEXT, texto TEXT, meta TEXT, ingerido REAL);
CREATE TABLE leccion (id INTEGER PRIMARY KEY, ts REAL NOT NULL, texto TEXT NOT NULL, evidencia TEXT,
  estado TEXT NOT NULL DEFAULT 'propuesta' CHECK (estado IN ('propuesta','aprobada','rechazada')), origen TEXT, decidida REAL);"""


class Aprendido(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = Path(self.tmp.name) / "almacen.db"
        os.environ["HUB_APRENDIZAJE_DB"] = str(ruta)
        c = sqlite3.connect(ruta)
        c.executescript(ESQUEMA)
        t = 1793000000.0
        c.execute("INSERT INTO hecho VALUES (1,'correccion:a','hermes','correccion',?,'tecnico','no lo hagas así, llama al 612 345 678 o escribe a x@y.com',NULL,0)", (t,))
        c.execute("INSERT INTO hecho VALUES (2,'correccion:b','hermes','correccion',?,'default','mira https://ejemplo.com/cuenta antes de seguir',NULL,0)", (t + 5,))
        L = [("Cuando Fran pida los pasos, explícalos y no cambies nada hasta que lo pida.", ["correccion:a", "correccion:b"], "propuesta", "claude", None),
             ("Recuerda: Fran vive en Valencia.", ["correccion:a"], "aprobada", "hechos-conversacion", t + 9),
             ("Podría crear una habilidad que haga terminal → web de una vez.", [], "rechazada", "habilidades", t + 9)]
        for tx, ev, es, og, de in L:
            c.execute("INSERT INTO leccion(ts,texto,evidencia,estado,origen,decidida) VALUES (?,?,?,?,?,?)", (t, tx, json.dumps(ev), es, og, de))
        c.commit(); c.close()
        import aprendido
        self.a = importlib.reload(aprendido)

    def tearDown(self):
        os.environ.pop("HUB_APRENDIZAJE_DB", None)
        self.tmp.cleanup()

    def estado(self, i):
        c = sqlite3.connect(os.environ["HUB_APRENDIZAJE_DB"])
        try:
            return c.execute("SELECT estado, decidida FROM leccion WHERE id=?", (i,)).fetchone()
        finally:
            c.close()

    def test_mapa_clasifica_cuenta_y_limpia(self):
        m = self.a.mapa()
        self.assertEqual(m["resumen"]["total"], 3)
        self.assertEqual(m["resumen"]["estado"], {"aprobada": 1, "propuesta": 1, "rechazada": 1})
        self.assertEqual(m["resumen"]["tipo"], {"dato": 1, "habilidad": 1, "regla": 1})
        l1 = next(x for x in m["lecciones"] if x["id"] == 1)
        self.assertEqual((l1["pruebas"], l1["asistentes"]), (2, ["default", "tecnico"]))
        textos = " ".join(e["texto"] for e in l1["evidencia"])
        for privado in ("612", "x@y.com", "ejemplo.com"):
            self.assertNotIn(privado, textos)                 # ni teléfonos, ni correos, ni enlaces
        self.assertLessEqual(len(l1["corto"]), 71)

    def test_aprobar_rechazar_y_reabrir(self):
        self.assertEqual(self.a.decidir(1, "aprobar")["estado"], "aprobada")
        self.assertIsNotNone(self.estado(1)[1])
        with self.assertRaises(self.a.AprendidoError) as cm:
            self.a.decidir(1, "aprobar")                       # ya aprobada
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.a.decidir(1, "rechazar")["estado"], "rechazada")       # «ya no vale»
        self.assertEqual(self.a.decidir(1, "reabrir")["estado"], "propuesta")
        self.assertEqual(self.estado(1), ("propuesta", None))
        with self.assertRaises(self.a.AprendidoError):
            self.a.decidir(1, "reabrir")                       # una propuesta no se «reabre»

    def test_entradas_malas(self):
        for i, a in ((99, "aprobar"), ("x", "aprobar"), (None, "aprobar"), (1, "borrar"), (1, "")):
            with self.assertRaises(self.a.AprendidoError, msg=(i, a)):
                self.a.decidir(i, a)
        self.assertEqual(self.estado(1)[0], "propuesta")

    def test_sin_base(self):
        os.environ["HUB_APRENDIZAJE_DB"] = str(Path(self.tmp.name) / "no-existe.db")
        with self.assertRaises(self.a.AprendidoError) as cm:
            self.a.mapa()
        self.assertEqual(cm.exception.code, 503)


if __name__ == "__main__":
    unittest.main()
