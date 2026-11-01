"""Pruebas de los arreglos en scripts sueltos de Zazu: noticias.py, movil-app.py y resumen-hoy.py. Sin red de verdad ni datos
reales: carpetas temporales, servidores locales y dobles. Uso: /usr/bin/python3 -m unittest discover -s zazu/scripts/tests -v"""
import http.server
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1]


def cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, SCRIPTS / archivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


noticias = cargar("noticias", "noticias.py")
resumen = cargar("resumen_hoy", "resumen-hoy.py")


class Lento:
    """Respuesta que gotea: 1 byte cada `pausa` segundos."""
    def __init__(self, pausa=0.1):
        self.pausa = pausa

    def read(self, n=-1):
        time.sleep(self.pausa)
        return b"x"


class TestNoticias(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [mock.patch.object(noticias, "DESTINO", d / "hoy.json"), mock.patch.object(noticias, "IMG_DIR", d / "img")]
        for p in self.p:
            p.start()
        noticias.IMG_DIR.mkdir()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_sin_titulares_no_machaca_hoy_json(self):
        noticias.DESTINO.write_text('{"bueno": 1}')
        vacio = {"fecha": "x", "generado": "x", "fuentes_caidas": ["Mundo/BBC: URLError"],
                 "apartados": [{"clave": "mundo", "titulo": "Mundo", "items": []}]}
        with mock.patch.object(noticias, "generar", return_value=vacio), mock.patch.object(sys, "argv", ["noticias.py"]), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(noticias.main(), 1)
        self.assertEqual(noticias.DESTINO.read_text(), '{"bueno": 1}')

    def test_descarga_con_tope_de_tiempo_total(self):
        t = time.monotonic()
        with self.assertRaises(ValueError):
            noticias._leer(Lento(0.05), 10_000, tope=0.3)
        self.assertLess(time.monotonic() - t, 2)
        self.assertEqual(noticias._leer(io.BytesIO(b"a" * 100), 10), b"a" * 10)
        self.assertEqual(noticias._leer(io.BytesIO(b"a" * 200_000)), b"a" * 200_000)

    def test_tope_de_tiempo_con_respuesta_http_de_verdad(self):
        # Con un doble que devuelve 1 byte por read() no se ve el fallo: read(65536) de http.client espera a juntar los
        # 65536 bytes. Aquí un servidor de verdad gotea 1 byte cada 0,2 s (con largo fijo y en trozos).
        for cabecera in (b"Content-Length: 100000", b"Transfer-Encoding: chunked"):
            srv = socket.socket()
            srv.bind(("127.0.0.1", 0))
            srv.listen()

            def gotear():
                c, _ = srv.accept()
                c.recv(4096)
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n" + cabecera + b"\r\n\r\n")
                try:
                    for _ in range(100):
                        c.sendall(b"1\r\nx\r\n" if b"chunked" in cabecera else b"x")
                        time.sleep(0.2)
                except OSError:
                    pass
                c.close()
            threading.Thread(target=gotear, daemon=True).start()
            t = time.monotonic()
            with self.assertRaises(ValueError, msg=cabecera):
                with noticias.urllib.request.urlopen(f"http://127.0.0.1:{srv.getsockname()[1]}/", timeout=3) as r:
                    noticias._leer(r, 768 * 1024, tope=1)
            self.assertLess(time.monotonic() - t, 5, cabecera)
            srv.close()

    def _png(self, tam, modo="RGB"):
        b = io.BytesIO()
        noticias.Image.new(modo, tam).save(b, "PNG")
        return b.getvalue()

    def test_imagen_enorme_en_pixeles_se_descarta_sin_decodificar(self):
        datos = self._png((6000, 5000), "1")              # 30 Mpx en pocos KB
        with mock.patch.object(noticias, "bajar_ajeno", return_value=(datos, "", "image/png")):
            self.assertIsNone(noticias.guardar_img("https://ejemplo.test/bomba.png"))

    def test_foto_jpeg_grande_no_se_descarta(self):
        # 35 Mpx en JPEG: el draft la decodifica a 1/8, así que no gasta memoria y no debe caer por el tope de píxeles
        b = io.BytesIO()
        noticias.Image.new("L", (7000, 5000)).save(b, "JPEG")
        with mock.patch.object(noticias, "bajar_ajeno", return_value=(b.getvalue(), "", "image/jpeg")):
            self.assertEqual(noticias.guardar_img("https://ejemplo.test/grande.jpg")[1], 7000)

    def test_misma_foto_en_varios_hilos_no_se_pisa(self):
        datos = self._png((800, 600))
        barrera = threading.Barrier(8)

        def bajar(*a, **k):
            barrera.wait(5)                               # los 8 hilos descargan a la vez
            return datos, "", "image/png"
        with mock.patch.object(noticias, "bajar_ajeno", side_effect=bajar):
            res = [None] * 8

            def uno(i):
                res[i] = noticias.guardar_img("https://ejemplo.test/logo.png")
            hilos = [threading.Thread(target=uno, args=(i,)) for i in range(8)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
        self.assertTrue(all(res), res)
        self.assertEqual([f.suffix for f in noticias.IMG_DIR.iterdir()], [".webp"])

    def test_rebinding_de_dns_no_llega_a_la_red_de_casa(self):
        class Secreto(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"DATO-INTERNO")

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), Secreto)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        puerto = srv.server_address[1]
        llamadas = []
        real = socket.getaddrinfo

        def dns(host, *a, **k):
            if host != "rebind.test":
                return real(host, *a, **k)
            llamadas.append(host)                         # 1.ª respuesta pública; luego, localhost
            ip = "93.184.216.34" if len(llamadas) == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, puerto))]
        try:
            with mock.patch("socket.getaddrinfo", side_effect=dns):
                with self.assertRaises(OSError):          # URLError es un OSError
                    noticias.bajar_ajeno(f"http://rebind.test:{puerto}/secreto", 1000)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertGreaterEqual(len(llamadas), 2)


class TestMovilApp(unittest.TestCase):
    def correr(self, *args):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "HUB_MOVIL_COLA": str(Path(d) / "peticiones.jsonl")}
            return subprocess.run([sys.executable, str(SCRIPTS / "movil-app.py"), *args], env=env, capture_output=True, text=True, timeout=30)

    def test_error_y_pendiente_tienen_codigos_distintos(self):
        r = self.correr("listar", "../etc", "--motivo", "prueba")
        self.assertEqual(r.returncode, 1, r.stderr)               # ruta no válida: error, no «pendiente»
        self.assertEqual(self.correr("listar", "--motivo", "x").returncode, 1)   # falta la ruta
        self.assertEqual(self.correr("listar", "/sdcard/Download").returncode, 1)  # falta el motivo
        self.assertEqual(self.correr("listar", "/sdcard/Download", "--motivo", "prueba").returncode, 0)
        r = self.correr("listar", "/sdcard/Download", "--motivo", "prueba", "--esperar", "1")
        self.assertEqual(r.returncode, 2)                         # sigue pendiente al acabar la espera
        self.assertEqual(json.loads(r.stdout)["estado"], "pendiente")


class TestResumenHoy(unittest.TestCase):
    ENVIADO = "<datos>\nHoy es miércoles 22 de octubre.\nTareas atrasadas (urgente):\n- Pagar IBI (era para el 20/10)\nAgenda de hoy:\n- 18:00: Último día para usar el reinicio de límites\n</datos>"

    def test_calificaciones_y_fechas_que_no_estaban(self):
        self.assertEqual(resumen.palabras_inventadas("A las 18:00 vence el reinicio, así que úsalo.", self.ENVIADO), ["vence", "así que"])
        self.assertEqual(resumen.palabras_inventadas("Tienes el IBI del 21/10 atrasado.", self.ENVIADO), ["21/10"])
        self.assertEqual(resumen.palabras_inventadas("Buenos días, Fran. Tienes una tarea atrasada y urgente: pagar el IBI, del 20/10. "
                                                     "A las 18:00, último día para usar el reinicio de límites.", self.ENVIADO), [])


if __name__ == "__main__":
    unittest.main()
