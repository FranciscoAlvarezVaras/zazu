#!/usr/bin/env python3
"""Permisos de nivel Familia (aprobaciones.py): pedir, responder, caducar y no dejarse engañar por lo que escriba la jaula."""
import json, os, sys, tempfile, threading, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aprobaciones as A  # noqa: E402


class Aprobaciones(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="hub-aprob-"))

    def test_pedir_y_responder(self):
        pid = A.pedir(self.raiz, "Apuntar la tarea «Pan»\n  ya")
        p = A.pendientes(self.raiz)
        self.assertEqual([(x["id"], x["que"]) for x in p], [(pid, "Apuntar la tarea «Pan» ya")])
        self.assertTrue(A.marcar_avisada(self.raiz, pid))
        self.assertFalse(A.marcar_avisada(self.raiz, pid))                 # el aviso sale una sola vez
        self.assertTrue(A.responder(self.raiz, pid, "aprobada"))
        self.assertFalse(A.responder(self.raiz, pid, "rechazada"))         # ya no está pendiente
        self.assertEqual(A.esperar(self.raiz, pid, espera=1, paso=0.1), "aprobada")
        self.assertEqual(A.pendientes(self.raiz), [])

    def test_respuesta_mientras_espera(self):
        pid = A.pedir(self.raiz, "Crear la cita")
        threading.Timer(0.3, lambda: A.responder(self.raiz, pid, "rechazada")).start()
        self.assertEqual(A.esperar(self.raiz, pid, espera=5, paso=0.1), "rechazada")

    def test_caduca_sin_respuesta(self):
        pid = A.pedir(self.raiz, "Crear la cita")
        self.assertEqual(A.esperar(self.raiz, pid, espera=0.3, paso=0.1), "caducada")
        self.assertFalse(A.responder(self.raiz, pid, "aprobada"))          # tarde: ya no vale

    def test_vieja_no_se_aprueba(self):
        pid = A.pedir(self.raiz, "x")
        f = A.carpeta(self.raiz) / f"{pid}.json"
        d = json.loads(f.read_text())
        d["creada"] = time.time() - A.ESPERA - 1
        f.write_text(json.dumps(d))
        self.assertEqual(A.pendientes(self.raiz), [])
        self.assertFalse(A.responder(self.raiz, pid, "aprobada"))

    def test_lo_que_escribe_la_jaula_no_es_fiable(self):
        c = A.carpeta(self.raiz)
        c.mkdir()
        (c / "zzz.json").write_text('{"id": "zzz", "estado": "pendiente"}')                       # id no válido
        (c / "aaaaaaaaaaaa.json").write_text('{"id": "bbbbbbbbbbbb", "estado": "pendiente", "creada": 9e99}')   # no coincide
        (c / "cccccccccccc.json").write_text("no es json")
        self.assertEqual(A.pendientes(self.raiz), [])
        # un enlace a un archivo de fuera: ni se lee ni se escribe a través de él
        fuera = self.raiz / "secreto.txt"
        fuera.write_text("NO TOCAR")
        pid = "dddddddddddd"
        os.symlink(fuera, c / f"{pid}.json")
        self.assertIsNone(A.leer(self.raiz, pid))
        self.assertFalse(A.responder(self.raiz, pid, "aprobada"))
        self.assertEqual(fuera.read_text(), "NO TOCAR")
        A.limpiar(self.raiz)
        self.assertFalse((c / f"{pid}.json").is_symlink())                 # los enlaces se borran
        self.assertEqual(fuera.read_text(), "NO TOCAR")

    def test_carpeta_enlazada_no_vale(self):
        otra = Path(tempfile.mkdtemp(prefix="hub-aprob-otra-"))
        os.symlink(otra, A.carpeta(self.raiz))
        self.assertEqual(A.pendientes(self.raiz), [])
        with self.assertRaises(ValueError):
            A.pedir(self.raiz, "x")
        self.assertEqual(list(otra.iterdir()), [])


class Recordatorios(unittest.TestCase):
    def setUp(self):
        import recordatorios
        self.R = recordatorios
        self.raiz = Path(tempfile.mkdtemp(prefix="hub-rec-"))

    def test_crear_vencer_enviar(self):
        rid = self.R.crear(self.raiz, "Ir a  misa", time.time() + 0.2)
        self.assertEqual([r["texto"] for r in self.R.pendientes(self.raiz)], ["Ir a misa"])
        self.assertEqual(self.R.vencidos(self.raiz), [])
        time.sleep(0.3)
        self.assertEqual([r["id"] for r in self.R.vencidos(self.raiz)], [rid])
        self.assertTrue(self.R.marcar_enviado(self.raiz, rid))
        self.assertEqual(self.R.vencidos(self.raiz), [])                   # una sola vez
        with self.assertRaises(ValueError):
            self.R.crear(self.raiz, "tarde", time.time() - 3600)          # ya pasó

    def test_muy_atrasado_no_se_manda(self):
        rid = self.R.crear(self.raiz, "Llamar", time.time() + 1)
        f = self.R.carpeta(self.raiz) / f"{rid}.json"
        d = json.loads(f.read_text())
        d["cuando"] = time.time() - self.R.TARDE - 10
        f.write_text(json.dumps(d))
        self.assertEqual(self.R.vencidos(self.raiz), [])
        self.assertEqual(self.R.leer(self.raiz, rid)["estado"], "perdido")


class RegistroErrores(unittest.TestCase):
    def test_anota_sin_datos_sensibles(self):
        import errores_invitadas as E
        E.F = Path(tempfile.mkdtemp(prefix="hub-err-")) / "errores.jsonl"
        E.anotar("zitest", "POST /api/send", "falló para ana@example.com con clave sk-ant-abcdefghijklmnopqrstuvwxyz", 500)
        E.anotar("ziotra", "chat", "otra cosa")
        d = E.leer(["zitest"], lambda p: Path("/nada"))
        self.assertEqual(len(d), 1)                                          # solo las invitadas pedidas
        self.assertNotIn("ana@example.com", d[0]["detalle"])
        self.assertNotIn("sk-ant-", d[0]["detalle"])
        self.assertEqual((d[0]["origen"], d[0]["codigo"]), ("POST /api/send", 500))


if __name__ == "__main__":
    unittest.main()
