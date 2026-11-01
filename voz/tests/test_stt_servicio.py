"""Servicio de dictado con el modelo FALSO (sin Whisper): límites, rutas, errores y descarga por reposo.  python3 -m unittest tests.test_stt_servicio"""
import importlib
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["ZAZU_STT_FALSO"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stt_servicio as S


class Servicio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        cls.srv.daemon_threads = True
        cls.puerto = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        S._modelo = None

    def pedir(self, ruta, cuerpo=None, metodo="POST"):
        r = urllib.request.Request(f"http://127.0.0.1:{self.puerto}{ruta}", data=cuerpo, method=metodo)
        try:
            with urllib.request.urlopen(r, timeout=10) as f:
                return f.status, json.loads(f.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_transcribe_y_carga_el_modelo_una_vez(self):
        self.assertEqual(self.pedir("/salud", metodo="GET")[1]["cargado"], False)
        c, d = self.pedir("/transcribir", b"x" * 100)
        self.assertEqual((c, d["texto"]), (200, "[100 bytes]"))
        self.assertEqual(self.pedir("/salud", metodo="GET")[1]["cargado"], True)

    def test_calentar_carga_en_segundo_plano(self):
        self.assertEqual(self.pedir("/calentar", b"")[0], 200)
        for _ in range(50):
            if S._modelo is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(S._modelo)

    def test_limites_y_rutas(self):
        self.assertEqual(self.pedir("/transcribir", b"")[0], 400)
        self.assertEqual(self.pedir("/otra", b"x")[0], 404)
        self.assertEqual(self.pedir("/otra", metodo="GET")[0], 404)
        S.MAX_BYTES, viejo = 10, S.MAX_BYTES
        try:
            self.assertEqual(self.pedir("/transcribir", b"x" * 11)[0], 413)
        finally:
            S.MAX_BYTES = viejo

    def test_un_audio_roto_no_tumba_el_servicio(self):
        antes = S.transcribir
        S.transcribir = lambda a: (_ for _ in ()).throw(ValueError("roto"))
        try:
            c, d = self.pedir("/transcribir", b"x")
            self.assertEqual((c, d["error"]), (422, "ValueError"))
        finally:
            S.transcribir = antes
        self.assertEqual(self.pedir("/transcribir", b"x")[0], 200)

    def test_el_reposo_libera_el_modelo(self):
        S.cargar()
        S._ultimo_uso = time.time() - S.IDLE_S - 1
        with S._cerrojo_carga:      # una pasada del vigilante, sin esperar 30 s
            if S._modelo is not None and time.time() - S._ultimo_uso > S.IDLE_S and not S._cerrojo_uso.locked():
                S._modelo = None
        self.assertIsNone(S._modelo)


if __name__ == "__main__":
    unittest.main()
