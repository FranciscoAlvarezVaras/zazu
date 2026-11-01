#!/usr/bin/env python3
"""Mapa de Mi nube (nube_geo.py): GPS de JPEG/WebP/PNG/TIFF (Pillow), de HEIC (cajas ISOBMFF a mano) y de vídeos (ffprobe); índice incremental
en segundo plano y celdas por zoom. Todo con archivos sintéticos bajo /tmp (o /dev/shm si /tmp no deja escribir): no toca Compartido ni el estado de verdad.

    python3 -m unittest tests.test_nube_geo -v
"""
import glob
import http.server
import json
import os
import pwd
import random
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
import warnings
from datetime import datetime
from pathlib import Path
from unittest import mock

try:
    import PIL  # noqa: F401
except ImportError:   # el hub corre con el python3 del sistema, que sí lo trae; el .venv no
    raise unittest.SkipTest("hacen falta Pillow y el python3 del sistema (no el .venv)")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["HUB_NUBE_GEO"] = "/proc/nube-geo-pruebas/geo.json"   # antes de importar: si algo usara el estado por defecto, ni lo lee ni puede escribirlo
import archivos as A  # noqa: E402
import nube_geo as G  # noqa: E402

CASA = Path(pwd.getpwuid(os.getuid()).pw_dir)   # la de verdad, por si HOME fuese una falsa
FFMPEG = next((p for p in [shutil.which("ffmpeg"), str(CASA / ".local/bin/ffmpeg"), *sorted(glob.glob(str(CASA / ".hermes/tools/ffmpeg-*/bin/ffmpeg")))]
               if p and os.access(p, os.X_OK)), None)


def _base_tmp():
    """/tmp si deja escribir unos MB; en este equipo es un tmpfs con cuota por usuario que a veces está lleno (entonces, /dev/shm)."""
    for d in (tempfile.gettempdir(), "/dev/shm"):
        try:
            with tempfile.TemporaryFile(dir=d) as f:
                f.write(bytes(8 << 20))
                f.flush()
            return d
        except OSError:
            continue
    return tempfile.gettempdir()


BASE_TMP = _base_tmp()
MADRID, BARNA, SYDNEY, NYC, LONDRES = (40.4168, -3.7038), (41.3874, 2.1686), (-33.8688, 151.2093), (40.7128, -74.0060), (51.5074, -0.1278)
MAX_EXIF_PRUEBA = G.MAX_EXIF + 1


# ---------- constructores de archivos de prueba ----------
def exif_pil(lat, lon):
    """EXIF de Pillow con un GPS (grados, minutos y segundos como floats; Pillow los guarda como racionales)."""
    from PIL import Image

    def dms(x):
        x = abs(x)
        return (float(int(x)), float(int(x % 1 * 60)), x % 1 * 60 % 1 * 60)
    ex = Image.Exif()
    ex[0x8825] = {1: "N" if lat >= 0 else "S", 2: dms(lat), 3: "E" if lon >= 0 else "W", 4: dms(lon)}
    return ex


def imagen(ruta, gps=None, exif=None):
    """Imagen de 8x8 (formato según la extensión) con GPS opcional."""
    from PIL import Image
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    formato = {".png": "PNG", ".webp": "WEBP"}.get(ruta.suffix.lower(), "JPEG")   # (los temporales .tmp de Syncthing llevan un JPEG dentro)
    Image.new("RGB", (8, 8), "navy").save(ruta, format=formato, exif=exif_pil(*gps) if gps else (exif or Image.Exif()))
    return ruta


def _rac(x, e):
    x = abs(x)
    g, m = int(x), int((x - int(x)) * 60)
    return struct.pack(e + "6I", g, 1, m, 1, round(((x - g) * 60 - m) * 60 * 10000), 10000)


def tiff(lat=None, lon=None, be=False, imagen=False, ifd_gps=True, ref=True):
    """Bloque TIFF/EXIF a mano. Sin lat/lon, sin GPS. imagen=True lo completa para que sea un TIFF que Pillow abre (1x1 gris);
    ifd_gps=False deja IFD0 sin el puntero GPSInfo; ref=False omite las letras N/S/E/W."""
    e = ">" if be else "<"
    corto, largo = (lambda v: struct.pack(e + "Hxx", v)), (lambda v: struct.pack(e + "I", v))
    gps = lat is not None and ifd_gps
    n0 = (9 if imagen else 0) + (1 if gps else 0)
    pix = 8 + 2 + 12 * n0 + 4
    goff = pix + (2 if imagen else 0)
    ent = []
    if imagen:
        ent += [(256, 3, 1, corto(1)), (257, 3, 1, corto(1)), (258, 3, 1, corto(8)), (259, 3, 1, corto(1)), (262, 3, 1, corto(1)),
                (273, 4, 1, largo(pix)), (277, 3, 1, corto(1)), (278, 3, 1, corto(1)), (279, 4, 1, largo(1))]
    if gps:
        ent.append((0x8825, 4, 1, largo(goff)))
    sal = (b"MM\x00*" if be else b"II*\x00") + struct.pack(e + "IH", 8, n0)
    sal += b"".join(struct.pack(e + "HHI", t, ty, c) + v for t, ty, c, v in ent) + struct.pack(e + "I", 0)
    if imagen:
        sal += b"\x80\x00"
    if gps:
        datos = goff + 2 + 12 * (4 if ref else 2) + 4
        g = [(2, 5, 3, largo(datos)), (4, 5, 3, largo(datos + 24))]
        if ref:
            g = [(1, 2, 2, (b"S" if lat < 0 else b"N") + bytes(3)), g[0], (3, 2, 2, (b"W" if lon < 0 else b"E") + bytes(3)), g[1]]
        sal += struct.pack(e + "H", len(g)) + b"".join(struct.pack(e + "HHI", t, ty, c) + v for t, ty, c, v in g) + struct.pack(e + "I", 0)
        sal += _rac(lat, e) + _rac(lon, e)
    return sal


def caja(tipo, *partes):
    cuerpo = b"".join(partes)
    return struct.pack(">I4s", 8 + len(cuerpo), tipo) + cuerpo


def completa(tipo, version, *partes):
    return caja(tipo, bytes([version, 0, 0, 0]), *partes)


def _iloc(v, items, t_off, t_len, t_base):
    """items: (id, método, base, [(desplazamiento, longitud)])."""
    cuerpo = bytes([(t_off << 4) | t_len, t_base << 4]) + struct.pack(">H" if v < 2 else ">I", len(items))
    for i, metodo, base, ext in items:
        cuerpo += struct.pack(">H" if v < 2 else ">I", i) + (struct.pack(">H", metodo) if v else b"") + struct.pack(">H", 0)
        cuerpo += base.to_bytes(t_base, "big") + struct.pack(">H", len(ext))
        cuerpo += b"".join(o.to_bytes(t_off, "big") + ln.to_bytes(t_len, "big") for o, ln in ext)
    return completa(b"iloc", v, cuerpo)


def heic(bloque, orden="mdat-meta", iloc_v=1, infe_v=2, t_off=4, t_len=4, t_base=0, metodo=0, prefijo=True, trozos=1, sin_exif=False,
         mdat_grande=False, mdat_tam0=False):
    """HEIC mínimo con el EXIF `bloque` (TIFF) como ítem «Exif». orden: «mdat-meta» (como los del móvil) o «meta-mdat» (como los del iPhone)."""
    item = struct.pack(">I", 6 if prefijo else 0) + (b"Exif\0\0" if prefijo else b"") + bloque
    ftyp = caja(b"ftyp", b"heic", bytes(4), b"mif1heic")
    foto = bytes(range(256)) + bytes(44)   # el «hvc1» falso
    partes = [item[i * len(item) // trozos:(i + 1) * len(item) // trozos] for i in range(trozos)]
    ident = lambda i: struct.pack(">H" if infe_v == 2 else ">I", i)

    def meta(off):   # off = dónde empieza el contenido de mdat en el archivo
        base = off if t_base else 0
        rel = (lambda x: x) if t_base else (lambda x: off + x)
        if metodo == 0:
            pos, ext = len(foto), []
            for p in partes:
                ext.append((rel(pos), len(p)))
                pos += len(p)
        else:
            pos, ext = 0, []
            for p in partes:
                ext.append((pos, len(p)))
                pos += len(p)
        items = [(1, 0, base, [(rel(0), len(foto))])] + ([] if sin_exif else [(2, metodo, base if metodo == 0 else 0, ext)])
        infes = completa(b"infe", infe_v, ident(1), struct.pack(">H", 0), b"hvc1", b"imagen\0")
        if not sin_exif:
            infes += completa(b"infe", infe_v, ident(2), struct.pack(">H", 0), b"Exif", b"Exif\0")
        hijas = [completa(b"hdlr", 0, bytes(4), b"pict", bytes(12), b"\0"), completa(b"pitm", 0, struct.pack(">H", 1)),
                 completa(b"iinf", 0, struct.pack(">H", 1 if sin_exif else 2), infes),
                 _iloc(iloc_v, items, t_off, t_len, t_base), caja(b"iprp", caja(b"ipco", caja(b"free", bytes(10))))]
        if metodo == 1:
            hijas.append(caja(b"idat", b"".join(partes)))
        return completa(b"meta", 0, *hijas)

    carga = foto + (b"".join(partes) if metodo == 0 and not sin_exif else b"")
    cab = 16 if mdat_grande else 8
    cab_mdat = (struct.pack(">I4sQ", 1, b"mdat", cab + len(carga)) if mdat_grande else
                struct.pack(">I4s", 0 if mdat_tam0 else 8 + len(carga), b"mdat"))
    if orden == "mdat-meta":
        return ftyp + cab_mdat + carga + meta(len(ftyp) + cab)
    m = meta(0)
    return ftyp + meta(len(ftyp) + len(m) + cab) + cab_mdat + carga


def escribir(ruta, datos):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_bytes(datos)
    return ruta


def hacer_video(ruta, *extra):
    r = subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=0.2:r=5", "-c:v", "mpeg4", *extra, str(ruta)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
    return ruta


def setUpModule():
    # el ejecutor de unittest pone todos los avisos a «default» y tapa el filtro del módulo: se vuelve a poner para que no ensucie la salida
    warnings.filterwarnings("ignore", message=r"Corrupt EXIF data|Truncated File Read", category=UserWarning)


class ConTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="geo-test-", dir=BASE_TMP))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.hijos = []
        self.addCleanup(lambda: [ix.detener() for ix in self.hijos])

    def cerca(self, g, esperado, lugares=4):
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g[0], esperado[0], places=lugares)
        self.assertAlmostEqual(g[1], esperado[1], places=lugares)


# ---------- GPS de un archivo ----------
class Iso6709(unittest.TestCase):
    def test_formas_validas(self):
        for txt, esp in (("+40.4168-003.7038/", (40.4168, -3.7038)), ("+40.4168-003.7038+000.000/", (40.4168, -3.7038)), ("-33.8688+151.2093/", (-33.8688, 151.2093)),
                         ("+40.4168-003.7038+000.000CRSWGS_84/", (40.4168, -3.7038)), (" +51.5-0.1 ", (51.5, -0.1)), ("+40-003/", (40.0, -3.0)),
                         ("+0.5+0.5/", (0.5, 0.5)), ("+90.0+180.0/", (90.0, 180.0))):
            self.assertEqual(G._iso6709(txt), esp, txt)

    def test_formas_no_validas(self):
        for txt in ("", "basura", "+91.0+000.0/", "+40.0+181.0/", "+00.0000+000.0000/", "+4025.0-00342.0/", "40.4168,-3.7038", "+40.4168", "++40.4-3.7/", None, 7):
            self.assertIsNone(G._iso6709(txt), txt)


class FechaReal(unittest.TestCase):
    def test_del_nombre_o_del_archivo(self):
        medio = lambda y, m, d: int(datetime(y, m, d, 12).timestamp())
        self.assertEqual(G.fecha_medio("IMG_20240117_212002.jpg", 5), medio(2024, 1, 17))
        self.assertEqual(G.fecha_medio("IMG-20261023-WA0001.jpg", 5), medio(2026, 10, 23))
        self.assertEqual(G.fecha_medio("20240117_212002.mp4", 5), medio(2024, 1, 17))
        for nombre in ("foto.jpg", "IMG_20230231_x.jpg", "IMG_20241301_x.jpg", "IMG_1999_0101.jpg", "12345" "20240117.jpg", "IMG_202401171.jpg", ""):
            self.assertEqual(G.fecha_medio(nombre, 777), 777, nombre)   # sin fecha en el nombre, o imposible: la del archivo

    def test_fecha_de_archivo_absurda(self):
        """Un archivo con la fecha en el año 14000 (o antes de 1970) tumbaba el listado y «un día como hoy» con un 400: se queda en 0."""
        for absurda in (4e11, 4102444800, -5, -4e11):
            self.assertEqual(G.fecha_medio("foto.jpg", int(absurda)), 0, absurda)
        self.assertEqual(G.fecha_medio("foto.jpg", 4102444799), 4102444799)   # (hasta el 1 de enero de 2100)
        self.assertEqual(G.fecha_medio("foto.jpg", 0), 0)
        medio = int(datetime(2024, 1, 17, 12).timestamp())
        self.assertEqual(G.fecha_medio("IMG_20240117_x.jpg", 4e11), medio)   # con fecha en el nombre, la del archivo ni se mira

    def test_misma_regla_que_el_hub(self):
        """El listado de la web (server.py) y la portada de una zona del mapa tienen que ordenar por la misma fecha: server.py usa esta función, no una copia."""
        fuente = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^_FECHA_NOMBRE = ", fuente, re.M), "server.py vuelve a tener su propia copia de la regla de la fecha")
        self.assertIn("NG.fecha_medio(e.name, int(st.st_mtime))", fuente)


class CoordenadasExif(unittest.TestCase):
    def test_hemisferios_y_formas(self):
        from PIL.TiffImagePlugin import IFDRational as R
        self.assertEqual(G._coords({1: "N", 2: (40, 25, 0), 3: "W", 4: (3, 42, 0)}), (40.416667, -3.7))
        self.assertEqual(G._coords({1: "S", 2: (R(33, 1), R(52, 1), R(1, 2)), 3: b"W\x00", 4: (70.0, 0, 0)}), (-33.866806, -70.0))
        self.assertEqual(G._coords({1: "s", 2: (10, 30, 0), 3: "e", 4: (20, 0, 0)}), (-10.5, 20.0))
        self.assertEqual(G._coords({2: (10, 30, 0), 4: (20, 0, 0)}), (10.5, 20.0))      # sin letras: norte y este
        self.assertEqual(G._coords({1: "N", 2: 10.5, 3: "E", 4: 20.25}), (10.5, 20.25))   # un solo número = grados decimales
        self.assertEqual(G._coords({1: "N", 2: (10, 30), 3: "E", 4: (20, 15)}), (10.5, 20.25))   # sin segundos
        # números con signo (mal escritos): con letra manda la letra; sin ella, el signo
        self.assertEqual(G._coords({1: "S", 2: (-33, 51, 0), 3: "W", 4: (-70, 30, 0)}), (-33.85, -70.5))
        self.assertEqual(G._coords({1: "N", 2: (-10, 30, 0), 3: "E", 4: (-20, 0, 0)}), (10.5, 20.0))
        self.assertEqual(G._coords({2: -10.5, 4: -20.25}), (-10.5, -20.25))

    def test_descartes(self):
        from PIL.TiffImagePlugin import IFDRational as R
        for g in ({}, None, {1: "N", 2: (0, 0, 0), 3: "E", 4: (0, 0, 0)},                 # el (0, 0) de «sin fix»
                  {1: "N", 2: (91, 0, 0), 3: "E", 4: (3, 0, 0)}, {1: "N", 2: (40, 0, 0), 3: "E", 4: (181, 0, 0)},   # fuera de rango
                  {1: "N", 2: (R(1, 0), 0, 0), 3: "E", 4: (3, 0, 0)},                      # denominador 0
                  {1: "N", 2: "abc", 3: "E", 4: (3, 0, 0)}, {1: "N", 2: (float("nan"), 0, 0), 3: "E", 4: (3, 0, 0)},
                  {1: "N", 2: (float("inf"), 0, 0), 3: "E", 4: (3, 0, 0)}, {1: "N", 2: (40, 0, 0)}, {3: "E", 4: (3, 0, 0)},
                  {1: "N", 2: (), 3: "E", 4: (3, 0, 0)}):
            self.assertIsNone(G._coords(g), g)
        self.assertEqual(G._coords({1: "N", 2: (0, 0, 0), 3: "E", 4: (3, 0, 0)}), (0.0, 3.0))   # el ecuador no se descarta


class Imagenes(ConTmp):
    def test_formatos_de_pillow(self):
        for ext in ("jpg", "jpeg", "webp", "png"):
            for lugar in (MADRID, SYDNEY, NYC, LONDRES, (-0.5, 0.5)):
                p = imagen(self.tmp / f"a.{ext}", lugar)
                self.cerca(G.gps_de(p), lugar)
                self.cerca(G.gps_de(str(p)), lugar)
        self.cerca(G.gps_de(imagen(self.tmp / "b.JPG", MADRID)), MADRID)   # mayúsculas en la extensión

    def test_tiff_little_y_big_endian(self):
        for be in (False, True):
            self.cerca(G.gps_de(escribir(self.tmp / f"a{be}.tif", tiff(*SYDNEY, be=be, imagen=True))), SYDNEY)
        self.cerca(G.gps_de(escribir(self.tmp / "b.tiff", tiff(*NYC, imagen=True, ref=False))), (NYC[0], abs(NYC[1])))   # sin letras: este
        self.assertIsNone(G.gps_de(escribir(self.tmp / "c.tif", tiff(imagen=True))))

    def test_sin_gps(self):
        from PIL import Image
        ex = Image.Exif()
        ex[0x010F] = "Marca"   # EXIF sin GPS
        self.assertIsNone(G.gps_de(imagen(self.tmp / "a.jpg", exif=ex)))
        self.assertIsNone(G.gps_de(imagen(self.tmp / "b.jpg")))   # sin EXIF
        self.assertIsNone(G.gps_de(imagen(self.tmp / "c.jpg", (0.0, 0.0))))   # (0, 0)
        ex = Image.Exif()
        ex[0x8825] = {1: "N", 2: (95.0, 0.0, 0.0), 3: "E", 4: (3.0, 0.0, 0.0)}
        self.assertIsNone(G.gps_de(imagen(self.tmp / "d.jpg", exif=ex)))   # latitud fuera de rango

    def test_estropeados_y_vacios(self):
        buena = imagen(self.tmp / "buena.jpg", MADRID).read_bytes()
        casos = {"vacio.jpg": b"", "texto.jpg": b"esto no es una imagen\n", "basura.webp": os.urandom(500), "corto.png": b"\x89PNG\r\n\x1a\n",
                 "cortado.jpg": buena[:len(buena) // 2], "cabecera.jpg": buena[:3], "otro.tif": b"II*\x00" + os.urandom(40), "enorme.jpg": b"\xff\xd8" + b"\xff\xe1\xff\xff" * 200}
        for nombre, datos in casos.items():
            self.assertIsNone(G.gps_de(escribir(self.tmp / nombre, datos)), nombre)

    def test_que_no_es_un_archivo(self):
        (self.tmp / "carpeta.jpg").mkdir()
        os.mkfifo(self.tmp / "tuberia.jpg")   # abrirla bloquearía para siempre
        t = time.time()
        for r in ("carpeta.jpg", "tuberia.jpg", "no-existe.jpg", "x.txt", "sin-extension"):
            self.assertIsNone(G.gps_de(self.tmp / r))
        escribir(self.tmp / "x.txt", b"hola")
        self.assertIsNone(G.gps_de(self.tmp / "x.txt"))
        self.assertIsNone(G.gps_de(None))
        self.assertLess(time.time() - t, 2)

    @unittest.skipIf(os.geteuid() == 0, "root lee todo")
    def test_sin_permiso(self):
        p = imagen(self.tmp / "a.jpg", MADRID)
        p.chmod(0)
        self.addCleanup(p.chmod, 0o600)
        self.assertIsNone(G.gps_de(p))

    def test_png_enorme_no_se_descodifica(self):
        from PIL import Image
        p = self.tmp / "grande.png"
        Image.new("L", (5100, 5100)).save(p, exif=exif_pil(*MADRID))   # 26 Mpíxeles: Pillow lo descodificaría entero para llegar al EXIF
        t = time.time()
        self.assertIsNone(G.gps_de(p))
        self.assertLess(time.time() - t, 1)

    def test_nombre_raro(self):
        for nombre in ("-print_format.jpg", "foto con espacios y ñ.jpg", "a'b\"c;$(x).jpg", "—.jpg"):
            self.cerca(G.gps_de(imagen(self.tmp / nombre, MADRID)), MADRID)

    def test_imagen_enorme_no_da_error_de_pillow(self):
        from PIL import Image
        p = imagen(self.tmp / "a.jpg", MADRID)
        with self.assertRaises(Image.DecompressionBombError), mock.patch.object(Image, "MAX_IMAGE_PIXELS", 10):
            Image.open(p)   # (con un tope así de bajo, Pillow se negaría a abrirla…)
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 10):
            self.cerca(G.gps_de(p), MADRID)   # …pero para el GPS solo se lee la cabecera
            self.assertEqual(Image.MAX_IMAGE_PIXELS, 10)   # y el tope de los demás queda como estaba
        self.assertIsNotNone(Image.MAX_IMAGE_PIXELS)


# ---------- HEIC ----------
class Heic(ConTmp):
    def prueba(self, datos, ext="heic", esperado=MADRID):
        r = G.gps_de(escribir(self.tmp / f"x.{ext}", datos))
        if esperado is None:
            self.assertIsNone(r)
        else:
            self.cerca(r, esperado)

    def test_como_los_del_movil_y_los_del_iphone(self):
        for orden in ("mdat-meta", "meta-mdat"):
            for lugar in (MADRID, SYDNEY, NYC):
                self.prueba(heic(tiff(*lugar), orden=orden), esperado=lugar)

    def test_variantes_de_iloc_e_infe(self):
        base = tiff(*SYDNEY)
        for kw in (dict(iloc_v=0), dict(iloc_v=1), dict(iloc_v=2, infe_v=3), dict(iloc_v=2, infe_v=3, t_off=8, t_len=8, t_base=4),
                   dict(iloc_v=1, t_off=8, t_len=4, t_base=8), dict(t_base=4), dict(iloc_v=2, infe_v=3, t_base=8, orden="meta-mdat"),
                   dict(trozos=3), dict(trozos=5, orden="meta-mdat"), dict(prefijo=False), dict(metodo=1), dict(metodo=1, trozos=2, iloc_v=2, infe_v=3),
                   dict(mdat_grande=True), dict(mdat_grande=True, orden="meta-mdat"), dict(mdat_tam0=True, orden="meta-mdat")):
            with self.subTest(**kw):
                self.prueba(heic(base, **kw), esperado=SYDNEY)

    def test_big_endian_y_extensiones(self):
        self.prueba(heic(tiff(*NYC, be=True)), esperado=NYC)
        for ext in ("heif", "avif", "HEIC"):
            self.prueba(heic(tiff(*NYC)), ext=ext, esperado=NYC)

    def test_sin_gps(self):
        self.prueba(heic(tiff()), esperado=None)                          # EXIF sin nada
        self.prueba(heic(tiff(*MADRID, ifd_gps=False)), esperado=None)   # sin puntero GPS
        self.prueba(heic(tiff(0.0, 0.0)), esperado=None)                  # (0, 0)
        self.prueba(heic(tiff(*MADRID), sin_exif=True), esperado=None)    # no hay ítem Exif
        self.prueba(heic(b"esto no es un TIFF"), esperado=None)

    def test_estropeados(self):
        for orden in ("mdat-meta", "meta-mdat"):
            buena = heic(tiff(*MADRID), orden=orden)
            for corte in list(range(0, len(buena), max(1, len(buena) // 60))) + [len(buena) - 1, len(buena)]:
                r = G.gps_de(escribir(self.tmp / "cortado.heic", buena[:corte]))
                # cortado por una caja que no hace falta (iprp...) aún sale; en cualquier otro sitio, nada; nunca unas coordenadas distintas
                self.assertTrue(r is None or r == MADRID, (orden, corte, r))
            self.assertIsNone(G.gps_de(escribir(self.tmp / "cortado.heic", buena[:len(buena) // 2])))
        for datos in (b"", b"\0" * 8, b"\0\0\0\x08ftyp", os.urandom(2000), b"\xff" * 64, struct.pack(">I4s", 0xFFFFFFF0, b"meta") + bytes(100),
                      caja(b"ftyp", b"heic") + struct.pack(">I4sQ", 1, b"meta", 1 << 62) + bytes(100), caja(b"ftyp", b"heic") + struct.pack(">I4s", 4, b"meta"),
                      caja(b"ftyp", b"heic") + completa(b"meta", 0), caja(b"ftyp", b"heic") + completa(b"meta", 0, completa(b"iinf", 0, b"\xff\xff"), completa(b"iloc", 0))):
            self.prueba(datos, esperado=None)

    def test_tamanos_absurdos(self):
        buena = heic(tiff(*MADRID), orden="meta-mdat")
        # la longitud del ítem Exif en iloc dice 1 GB: no se intenta leer
        largo = struct.pack(">I", 4 + 6 + len(tiff(*MADRID)))
        i = buena.index(largo, buena.index(b"iloc"))
        self.prueba(buena[:i] + struct.pack(">I", 1 << 30) + buena[i + 4:], esperado=None)
        self.prueba(buena[:i] + struct.pack(">I", MAX_EXIF_PRUEBA) + buena[i + 4:], esperado=None)   # justo por encima del tope
        self.assertEqual(len(G._exif_heif(escribir(self.tmp / "ok.heic", buena)) or b""), len(tiff(*MADRID)))

    def test_no_lee_la_imagen(self):
        # como los del móvil: mdat (con la imagen) delante de meta. Aquí mdat lleva 200 MB más al final (un hueco: no ocupa disco)
        buena = heic(tiff(*MADRID))
        i = buena.index(b"mdat") - 4
        tam = struct.unpack(">I", buena[i:i + 4])[0]
        hueco = 200 << 20
        p = self.tmp / "gigante.heic"
        with open(p, "wb") as f:
            f.write(buena[:i] + struct.pack(">I", tam + hueco) + buena[i + 4:i + tam])
            f.seek(hueco, 1)
            f.write(buena[i + tam:])   # el meta, detrás del hueco (sus desplazamientos apuntan a antes)
        self.cerca(G.gps_de(p), MADRID)   # (esta vez calienta Pillow)
        tracemalloc.start()
        try:
            t = time.time()
            self.cerca(G.gps_de(p), MADRID)
            self.assertLess(time.time() - t, 1)
            self.assertLess(tracemalloc.get_traced_memory()[1], 4 << 20)   # nada de cargar 200 MB
        finally:
            tracemalloc.stop()

    def test_fuzz(self):
        rnd = random.Random(7)
        for orden in ("mdat-meta", "meta-mdat"):
            buena = heic(tiff(*MADRID), orden=orden, iloc_v=1)
            for i in range(250):
                b = bytearray(buena)
                for _ in range(rnd.randint(1, 4)):
                    b[rnd.randrange(len(b))] = rnd.randrange(256)
                p = escribir(self.tmp / "fuzz.heic", bytes(b))
                t = time.time()
                r = G.gps_de(p)
                self.assertLess(time.time() - t, 1, (orden, i))
                self.assertTrue(r is None or (len(r) == 2 and -90 <= r[0] <= 90 and -180 <= r[1] <= 180), r)


# ---------- vídeos ----------
@unittest.skipUnless(FFMPEG, "hace falta ffmpeg para crear los vídeos de prueba")
class Videos(ConTmp):
    def test_android_y_apple(self):
        self.cerca(G.gps_de(hacer_video(self.tmp / "a.mp4", "-metadata", "location=+40.4168-003.7038/")), MADRID)
        self.cerca(G.gps_de(hacer_video(self.tmp / "b.mov", "-movflags", "use_metadata_tags", "-metadata", "com.apple.quicktime.location.ISO6709=-33.8688+151.2093+000.000/")), SYDNEY)
        self.cerca(G.gps_de(hacer_video(self.tmp / "c.m4v", "-metadata", "location=+51.5074-000.1278/")), LONDRES)
        self.cerca(G.gps_de(hacer_video(self.tmp / "d.3gp", "-f", "3gp", "-metadata", "location=+40.7128-074.0060/")), NYC)
        self.cerca(G.gps_de(hacer_video(self.tmp / "e.MOV", "-metadata", "location=+40.4168-003.7038/", "-metadata", "location-eng=+40.4168-003.7038/")), MADRID)

    def test_sin_ubicacion_o_no_valida(self):
        self.assertIsNone(G.gps_de(hacer_video(self.tmp / "a.mp4")))
        self.assertIsNone(G.gps_de(hacer_video(self.tmp / "b.mp4", "-metadata", "location=+00.0000+000.0000/")))
        self.assertIsNone(G.gps_de(hacer_video(self.tmp / "c.mp4", "-metadata", "location=basura")))
        self.assertIsNone(G.gps_de(hacer_video(self.tmp / "d.mp4", "-metadata", "location=+95.0+010.0/")))

    def test_estropeados(self):
        buena = hacer_video(self.tmp / "buena.mp4", "-metadata", "location=+40.4168-003.7038/").read_bytes()
        for nombre, datos in {"vacio.mp4": b"", "texto.mp4": b"hola\n", "basura.mov": os.urandom(3000), "cortado.mp4": buena[:len(buena) // 3], "cabecera.mp4": buena[:20]}.items():
            self.assertIsNone(G.gps_de(escribir(self.tmp / nombre, datos)), nombre)
        # con el moov cortado a la mitad puede o no salir: lo que no puede es lanzar ni tardar
        t = time.time()
        for corte in range(0, len(buena), 97):
            r = G.gps_de(escribir(self.tmp / "c.mp4", buena[:corte]))
            self.assertTrue(r is None or r == (40.4168, -3.7038), (corte, r))
        self.assertLess(time.time() - t, 60)

    def test_una_lista_hls_no_sale_a_internet(self):
        visitas = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                visitas.append(self.path)
                self.send_response(404)
                self.end_headers()
            do_HEAD = do_GET

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_port}/seg.ts"
        for nombre in ("lista.mp4", "lista.mov"):
            escribir(self.tmp / nombre, f"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:1,\n{url}\n#EXT-X-ENDLIST\n".encode())
            self.assertIsNone(G.gps_de(self.tmp / nombre))
        escribir(self.tmp / "concat.mp4", f"ffconcat version 1.0\nfile '{url}'\n".encode())
        self.assertIsNone(G.gps_de(self.tmp / "concat.mp4"))
        self.assertEqual(visitas, [])

    def test_ffprobe_colgado_se_corta(self):
        falso = self.tmp / "ffprobe-falso"
        falso.write_text("#!/bin/sh\nexec sleep 30\n")
        falso.chmod(0o755)
        v = hacer_video(self.tmp / "a.mp4", "-metadata", "location=+40.4168-003.7038/")
        with mock.patch.object(G, "_FFP", str(falso)), mock.patch.object(G, "TIMEOUT_FFPROBE", 0.4):
            t = time.time()
            self.assertIsNone(G.gps_de(v))
            self.assertLess(time.time() - t, 5)

    def test_sin_ffprobe(self):
        v = hacer_video(self.tmp / "a.mp4", "-metadata", "location=+40.4168-003.7038/")
        with mock.patch.object(G, "_FFP", ""), mock.patch.object(G, "_FFP_T", time.time()):   # «ya busqué y no hay»
            self.assertIsNone(G.gps_de(v))
        with mock.patch.object(G, "_FFP", str(self.tmp / "no-existe")), mock.patch.object(G, "_FFP_T", time.time()):
            self.assertIsNone(G.gps_de(v))

    def test_si_el_ffprobe_desaparece_busca_otro(self):
        v = hacer_video(self.tmp / "a.mp4", "-metadata", "location=+40.4168-003.7038/")
        with mock.patch.object(G, "_FFP", str(self.tmp / "ffmpeg-viejo/bin/ffprobe")), mock.patch.object(G, "_FFP_T", 0.0):   # lo que había ya no existe
            self.cerca(G.gps_de(v), MADRID)
            self.assertTrue(os.access(G._FFP, os.X_OK) and "viejo" not in G._FFP)

    def test_encuentra_ffprobe_aunque_home_sea_falso(self):
        with mock.patch.object(G, "_FFP", None), mock.patch.object(G, "HOME", self.tmp), mock.patch.dict(os.environ, {"HUB_FFPROBE": ""}):
            self.assertTrue(G._ffprobe())


# ---------- recuadros ----------
class Recuadros(unittest.TestCase):
    def test_normalizacion(self):
        self.assertEqual(G._norm(10, 20, 30, 40), (10, 20, 30, 40))
        self.assertEqual(G._norm(30, 20, 10, 40), (10, 20, 30, 40))                    # sur y norte al revés
        self.assertEqual(G._norm(-100, -20, 100, 20), (-90, -20, 90, 20))              # latitudes fuera de rango
        self.assertEqual(G._norm(-10, 170, 10, 190), (-10, 170, 10, -170))             # cruza el antimeridiano
        self.assertEqual(G._norm(-10, 170, 10, -170), (-10, 170, 10, -170))
        self.assertEqual(G._norm(-10, -190, 10, -170), (-10, 170, 10, -170))
        self.assertEqual(G._norm(-10, -400, 10, 400), (-10, -180, 10, 180))            # el mundo repetido
        self.assertEqual(G._norm(-10, -180, 10, 180), (-10, -180, 10, 180))
        self.assertEqual(G._norm(-10, 100, 10, 180), (-10, 100, 10, 180))              # un este de justo 180° no cruza nada
        self.assertEqual(G._norm(-10, -180, 10, -170), (-10, -180, 10, -170))
        self.assertEqual(G._norm(-10, 180, 10, -170), (-10, 180, 10, -170))            # esto sí: de 180° hacia el oeste de la fecha
        self.assertEqual(G._norm(-10, 100, 10, 190), (-10, 100, 10, -170))
        self.assertEqual(G._norm(-10, 175, 10, 185), (-10, 175, 10, -175))
        self.assertEqual(G._norm(-10, -185, 10, -175), (-10, 175, 10, -175))
        self.assertEqual(G._norm(-10, 20, 10, 20), (-10, 20, 10, 20))                  # un meridiano
        self.assertEqual(G._norm("1", "2", "3", "4"), (1, 2, 3, 4))
        for malo in ((float("nan"), 0, 1, 1), (0, float("inf"), 1, 1), ("a", 0, 1, 1), (None, 0, 1, 1), ([], 0, 1, 1)):
            with self.assertRaises(ValueError):
                G._norm(*malo)

    def test_texto(self):
        self.assertEqual(G.recuadro("40,-4,41,-3"), (40, -4, 41, -3))
        self.assertEqual(G.recuadro("-10.5, 170 ,10.5,-170"), (-10.5, 170, 10.5, -170))
        for malo in ("", "1,2,3", "1,2,3,4,5", "a,b,c,d", "1,2,3,nan", "1,2,3,", None):
            with self.assertRaises(ValueError):
                G.recuadro(malo)

    def test_dentro(self):
        self.assertTrue(G._dentro(40.5, -3.5, 40, -4, 41, -3))
        self.assertTrue(G._dentro(40, -4, 40, -4, 41, -3))      # bordes incluidos
        self.assertTrue(G._dentro(41, -3, 40, -4, 41, -3))
        self.assertFalse(G._dentro(41.1, -3.5, 40, -4, 41, -3))
        self.assertFalse(G._dentro(40.5, -2.9, 40, -4, 41, -3))
        self.assertTrue(G._dentro(0, 179.9, -10, 170, 10, -170) and G._dentro(0, -179.9, -10, 170, 10, -170) and G._dentro(0, 180, -10, 170, 10, -170))
        self.assertFalse(G._dentro(0, 0, -10, 170, 10, -170))
        self.assertFalse(G._dentro(0, 169.9, -10, 170, 10, -170))


# ---------- consultas: celdas y recuadros ----------
class Consultas(ConTmp):
    def setUp(self):
        super().setUp()
        self.ix = G.Indice(A.Raiz("compartido", self.tmp), ruta=self.tmp / "estado" / "geo.json", pausa=0)
        self.hijos.append(self.ix)

    def punto(self, rel, lugar, mt=1000):
        escribir(self.tmp / rel, b"x")
        self.ix._poner(rel, mt, 1, lugar)

    def mundo(self):
        """Tres fotos pegadas en Madrid (la más nueva es b), otra a 2 km, y Barcelona, Sydney y Nueva York."""
        self.punto("a.jpg", (40.4168, -3.7038), 10)
        self.punto("b.heic", (40.416801, -3.703799), 30)
        self.punto("c.mp4", (40.416799, -3.703801), 20)
        self.punto("lejos.jpg", (40.4348, -3.7038), 5)
        self.punto("barna.jpg", BARNA, 7)
        self.punto("sydney.jpg", SYDNEY, 8)
        self.punto("nyc.jpg", NYC, 9)

    def p(self, z, s=-90, w=-180, n=90, e=180, **kw):
        return self.ix.puntos(z, s, w, n, e, **kw)

    def test_zoom_maximo_agrupa_lo_pegado(self):
        self.mundo()
        r = self.p(18)
        self.assertEqual(sorted(c["n"] for c in r), [1, 1, 1, 1, 3])
        c = r[0]   # la más llena primero
        self.assertEqual((c["n"], c["path"], c["kind"]), (3, "b.heic", "image"))   # la portada es la más nueva
        self.assertAlmostEqual(c["lat"], 40.4168, places=5)
        self.assertAlmostEqual(c["lon"], -3.7038, places=5)
        self.assertEqual(c["caja"], [40.416799, -3.703801, 40.416801, -3.703799])
        self.assertEqual(set(c), {"lat", "lon", "n", "path", "kind", "caja"})
        self.assertEqual({x["path"]: x["kind"] for x in r}, {"b.heic": "image", "lejos.jpg": "image", "barna.jpg": "image", "sydney.jpg": "image", "nyc.jpg": "image"})

    def test_el_tipo_es_el_de_la_portada(self):
        self.punto("v.mov", (10.0, 10.0), 99)
        self.punto("f.jpg", (10.0, 10.0), 50)
        r = self.p(10)
        self.assertEqual((r[0]["n"], r[0]["path"], r[0]["kind"]), (2, "v.mov", "video"))

    def test_la_portada_es_la_mas_nueva_por_su_fecha_real(self):
        # la fecha del archivo dice lo contrario de la del nombre: manda el nombre, como en la web
        self.punto("IMG_20200101_100000.jpg", (10.0, 10.0), 9_000_000_000)   # archivo «nuevo» (copiado ahora), foto vieja
        self.punto("IMG_20240101_080000.jpg", (10.0, 10.0), 1_000)           # archivo viejo, foto nueva
        self.punto("sin-fecha.jpg", (10.0, 10.0), 1_700_000_000)             # sin fecha en el nombre: la del archivo (nov. de 2023)
        self.assertEqual(self.p(10)[0]["path"], "IMG_20240101_080000.jpg")
        self.punto("IMG_20240101_210000.jpg", (10.0, 10.0), 2_000)           # el mismo día: la hora va en el nombre
        self.assertEqual(self.p(10)[0]["path"], "IMG_20240101_210000.jpg")
        self.assertEqual(self.p(10)[0]["n"], 4)

    def test_con_menos_zoom_hay_menos_celdas_y_nada_se_pierde(self):
        self.mundo()
        rnd = random.Random(4)
        for i in range(300):
            self.punto(f"r/{i}.jpg", (rnd.uniform(-60, 70), rnd.uniform(-179, 179)), i)
        total = 307
        antes = None
        for z in range(18, -1, -1):
            r = self.p(z, maximo=10_000)
            self.assertEqual(sum(c["n"] for c in r), total, z)
            if antes is not None:
                self.assertLessEqual(len(r), antes, z)
            antes = len(r)
        self.assertLessEqual(len(self.p(0)), 16)
        self.assertGreater(len(self.p(14, maximo=10_000)), 100)

    def test_recuadro_y_celdas_enteras(self):
        self.mundo()
        r = self.p(12, 40, -4, 41, -3)
        self.assertEqual(sum(c["n"] for c in r), 4)   # solo Madrid
        self.assertEqual({c["path"] for c in r if c["n"] == 3}, {"b.heic"})
        # un recuadro que corta la celda por la mitad la devuelve entera: los números no bailan al mover el mapa
        a = self.p(18, 40.4168, -3.70381, 40.4169, -3.70379)
        b = self.p(18, 40.41679, -3.703795, 40.4169, -3.7037)
        self.assertEqual([(c["n"], c["lat"], c["lon"]) for c in a], [(c["n"], c["lat"], c["lon"]) for c in b])
        self.assertEqual(a[0]["n"], 3)
        self.assertEqual(self.p(12, 0, 0, 1, 1), [])
        self.assertEqual(self.p(12, 50, -4, 51, -3), [])

    def test_tocar_un_grupo_da_justo_sus_fotos(self):
        self.mundo()
        c = self.p(18)[0]
        self.assertEqual(self.ix.en_recuadro(*c["caja"]), {"a.jpg", "b.heic", "c.mp4"})
        for z in (3, 9, 15):
            for c in self.p(z):
                dentro = self.ix.en_recuadro(*c["caja"])
                self.assertEqual(len(dentro), c["n"], (z, c))
                self.assertIn(c["path"], dentro)

    def test_antimeridiano(self):
        self.punto("este.jpg", (-17.7134, 179.9), 1)
        self.punto("oeste.jpg", (-17.5, -179.95), 2)
        self.punto("medio.jpg", (-17.6, 0.0), 3)
        for bbox in ((-20, 170, -10, -170), (-20, 170, -10, 190), (-20, -190, -10, -170)):
            self.assertEqual({c["path"] for c in self.p(3, *bbox)}, {"este.jpg", "oeste.jpg"}, bbox)
            self.assertEqual(self.ix.en_recuadro(*bbox), {"este.jpg", "oeste.jpg"}, bbox)
        for bbox in ((-20, -100, -10, 100), (-20, -10, -10, 10)):
            self.assertNotIn("este.jpg", {c["path"] for c in self.p(3, *bbox)})
            self.assertNotIn("oeste.jpg", {c["path"] for c in self.p(3, *bbox)})
        self.assertEqual(self.ix.en_recuadro(-20, -10, -10, 10), {"medio.jpg"})
        self.assertEqual(len(self.p(3, -20, 170, -10, -170)), 2)   # nunca se juntan de un lado al otro de los 180°
        self.assertEqual(self.ix.en_recuadro(-20, -180, -10, 180), {"este.jpg", "oeste.jpg", "medio.jpg"})
        self.assertEqual(self.ix.en_recuadro(-20, -400, -10, 400), {"este.jpg", "oeste.jpg", "medio.jpg"})
        # un mapa que llega justo hasta los 180° por el este no enseña lo del otro lado (la primera columna de celdas, ni a zoom bajo)
        for z in (0, 3, 10):
            self.assertEqual({c["path"] for c in self.p(z, -20, 100, -10, 180)}, {"este.jpg"}, z)
        self.assertEqual(self.ix.en_recuadro(-20, 100, -10, 180), {"este.jpg"})
        self.assertEqual({c["path"] for c in self.p(3, -20, -180, -10, -100)}, {"oeste.jpg"})

    def test_polos(self):
        self.punto("norte.jpg", (89.99, 10.0), 1)
        self.punto("sur.jpg", (-89.99, -10.0), 2)
        r = {c["path"]: c for c in self.p(5)}
        self.assertEqual(set(r), {"norte.jpg", "sur.jpg"})
        self.assertAlmostEqual(r["norte.jpg"]["lat"], 89.99)
        self.assertEqual(self.ix.en_recuadro(80, -180, 90, 180), {"norte.jpg"})
        self.assertEqual(self.ix.en_recuadro(-90, -180, -80, 180), {"sur.jpg"})
        self.assertEqual({c["path"] for c in self.p(18, 85.06, -180, 90, 180)}, {"norte.jpg"})

    def test_zoom_fuera_de_rango_o_con_decimales(self):
        self.mundo()
        igual = lambda a, b: self.assertEqual(a, b)
        igual(self.p(-5), self.p(0))
        igual(self.p(99), self.p(18))
        igual(self.p(7.4), self.p(7))
        igual(self.p("7"), self.p(7))
        for malo in (float("nan"), float("inf"), "alto", None, ""):
            with self.assertRaises(ValueError, msg=malo):
                self.p(malo)

    def test_recuadro_malo(self):
        self.mundo()
        for mal in ((float("nan"), 0, 1, 1), ("a", 0, 1, 1), (0, 0, 1, float("inf")), (None, 0, 1, 1), (0, 0, 1, None), ("", "", "", "")):
            with self.assertRaises(ValueError):
                self.p(5, *mal)
            with self.assertRaises(ValueError):
                self.ix.en_recuadro(*mal)
        self.assertEqual(self.p(5, 90, -180, -90, 180), self.p(5, -90, -180, 90, 180))   # sur y norte al revés: se da la vuelta, no falla

    def test_tope_de_celdas(self):
        for i in range(60):
            for k in range(i % 5 + 1):   # celdas con 1 a 5 fotos, en sitios sueltos
                self.punto(f"g/{i}_{k}.jpg", (-60 + i, -170 + 5 * i), i * 10 + k)
        todo = self.p(18, maximo=1000)
        self.assertEqual(len(todo), 60)
        pocos = self.p(18, maximo=7)
        self.assertEqual(len(pocos), 7)
        self.assertEqual([c["n"] for c in pocos], sorted((c["n"] for c in todo), reverse=True)[:7])
        self.assertEqual([c["n"] for c in todo], sorted((c["n"] for c in todo), reverse=True))   # de más a menos llena
        self.assertLessEqual(len(self.ix.puntos(18, -90, -180, 90, 180)), G.MAX_PUNTOS)

    def test_portada_borrada_se_sustituye(self):
        self.mundo()
        (self.tmp / "b.heic").unlink()   # la portada del grupo de Madrid desaparece sin que el índice se entere
        c = self.p(18)[0]
        self.assertEqual((c["n"], c["path"]), (2, "c.mp4"))   # la siguiente más nueva y sin contar la borrada
        self.assertNotIn("b.heic", self.ix.f)
        self.assertNotIn("b.heic", self.ix.p)

    def test_en_recuadro(self):
        self.mundo()
        r = self.ix.en_recuadro(40, -4, 41, -3)
        self.assertIsInstance(r, set)
        self.assertEqual(r, {"a.jpg", "b.heic", "c.mp4", "lejos.jpg"})
        self.assertEqual(self.ix.en_recuadro(40.4168, -3.7038, 40.4168, -3.7038), {"a.jpg"})   # un punto: bordes incluidos
        self.assertEqual(self.ix.en_recuadro(60, 0, 61, 1), set())
        self.assertEqual(len(self.ix.en_recuadro(-90, -180, 90, 180)), 7)


# ---------- el índice en segundo plano ----------
class ConArbol(ConTmp):
    """Un «Compartido» de pruebas en self.base y su índice en self.estado."""

    def setUp(self):
        super().setUp()
        self.base = self.tmp / "Compartido"
        self.base.mkdir()
        self.estado = self.tmp / "estado" / "geo.json"
        self.root = A.Raiz("compartido", self.base, rw=True, protegidas=("Adjuntos",))

    def indice(self, **kw):
        ix = G.Indice(self.root, ruta=self.estado, **{"pausa": 0, "intervalo": 60, **kw})
        self.hijos.append(ix)
        return ix

    def esperar(self, ix, pasadas=1, t=30):
        fin = time.time() + t
        while ix.pasadas < pasadas and time.time() < fin:
            time.sleep(0.01)
        self.assertGreaterEqual(ix.pasadas, pasadas, "el índice no terminó a tiempo")

    def arbol(self):
        b = self.base
        imagen(b / "DCIM/Camera/IMG_1.jpg", MADRID)
        imagen(b / "DCIM/Camera/IMG_2.jpg", (MADRID[0] + 1e-4, MADRID[1]))
        imagen(b / "DCIM/Camera/IMG_3.png", SYDNEY)
        imagen(b / "DCIM/Camera/IMG_4.jpg")                                   # sin GPS
        escribir(b / "DCIM/Camera/IMG_5.heic", heic(tiff(*NYC)))
        escribir(b / "DCIM/Camera/IMG_6.heic", heic(tiff()))                  # HEIC sin GPS
        escribir(b / "Docs/notas.txt", b"no es un medio")
        escribir(b / "Docs/roto.jpg", b"estropeado")                          # cuenta como «sin GPS»
        # lo que NO se indexa: ocultos, reservados y accesos directos
        imagen(b / ".oculta/x.jpg", MADRID)
        imagen(b / ".stfolder/y.jpg", MADRID)
        imagen(b / "Docs/.z.jpg", MADRID)
        imagen(b / "Docs/w.jpg.syncthing.tmp", MADRID)
        imagen(b / "Docs/~syncthing~v.jpg.tmp", MADRID)
        fuera = self.tmp / "fuera"
        imagen(fuera / "f.jpg", MADRID)
        os.symlink(fuera, b / "enlace-a-carpeta")
        os.symlink(fuera / "f.jpg", b / "enlace-a-foto.jpg")
        return {"DCIM/Camera/IMG_1.jpg", "DCIM/Camera/IMG_2.jpg", "DCIM/Camera/IMG_3.png", "DCIM/Camera/IMG_5.heic"}, \
               {"DCIM/Camera/IMG_4.jpg", "DCIM/Camera/IMG_6.heic", "Docs/roto.jpg"}



class IndiceEnSegundoPlano(ConArbol):
    def test_indexa_lo_visible(self):
        con, sin = self.arbol()
        ix = self.indice()
        self.assertEqual(ix.estado(), {"conGps": 0, "sinGps": 0, "indexando": False, "progreso": 0.0})
        ix.arrancar()
        self.esperar(ix)
        self.assertEqual(ix.estado(), {"conGps": 4, "sinGps": 3, "indexando": False, "progreso": 1.0})
        self.assertEqual(set(ix.f), con | sin)
        self.assertEqual(set(ix.p), con)
        self.cerca(ix.f["DCIM/Camera/IMG_5.heic"][2:], NYC)

    def test_guarda_en_disco_de_forma_privada(self):
        self.arbol()
        ix = self.indice()
        ix.arrancar()
        self.esperar(ix)
        self.assertEqual(stat.S_IMODE(self.estado.stat().st_mode), 0o600)
        self.assertEqual(sorted(os.listdir(self.estado.parent)), ["geo.json"])   # ni rastro del temporal
        d = json.loads(self.estado.read_text())
        self.assertEqual(d["v"], 1)
        self.assertEqual(set(d["f"]), set(ix.f))
        self.assertEqual(len(d["f"]["DCIM/Camera/IMG_4.jpg"]), 2)
        self.assertEqual(len(d["f"]["DCIM/Camera/IMG_1.jpg"]), 4)

    def test_otro_arranque_no_vuelve_a_leer(self):
        self.arbol()
        a = self.indice()
        a.arrancar()
        self.esperar(a)
        a.detener()
        b = self.indice()
        self.assertEqual(b.estado()["conGps"], 4)   # ya está cargado antes de arrancar
        with mock.patch.object(G, "gps_de", wraps=G.gps_de) as leer:
            b.arrancar()
            self.esperar(b)
        self.assertEqual(leer.call_count, 0)
        self.assertEqual(b.estado(), {"conGps": 4, "sinGps": 3, "indexando": False, "progreso": 1.0})

    def test_incremental(self):
        self.arbol()
        ix = self.indice()
        ix.arrancar()
        self.esperar(ix)
        # una foto cambia de sitio, otra se borra, otra llega
        imagen(self.base / "DCIM/Camera/IMG_1.jpg", SYDNEY)
        os.utime(self.base / "DCIM/Camera/IMG_1.jpg", (time.time() + 50, time.time() + 50))
        (self.base / "DCIM/Camera/IMG_2.jpg").unlink()
        imagen(self.base / "DCIM/Camera/IMG_7.jpg", LONDRES)
        with mock.patch.object(G, "gps_de", wraps=G.gps_de) as leer:
            ix.despierta.set()
            self.esperar(ix, 2)
        self.assertEqual(sorted(Path(c.args[0]).name for c in leer.call_args_list), ["IMG_1.jpg", "IMG_7.jpg"])   # solo lo nuevo o cambiado
        self.cerca(ix.f["DCIM/Camera/IMG_1.jpg"][2:], SYDNEY)
        self.cerca(ix.f["DCIM/Camera/IMG_7.jpg"][2:], LONDRES)
        self.assertNotIn("DCIM/Camera/IMG_2.jpg", ix.f)
        self.assertNotIn("DCIM/Camera/IMG_2.jpg", ix.p)
        self.assertEqual(ix.estado()["conGps"], 4)
        self.assertNotIn("DCIM/Camera/IMG_2.jpg", json.loads(self.estado.read_text())["f"])

    def test_un_medio_que_pasa_a_ser_oculto_se_quita(self):
        self.arbol()
        ix = self.indice()
        ix.arrancar()
        self.esperar(ix)
        os.rename(self.base / "DCIM/Camera/IMG_1.jpg", self.base / "DCIM/Camera/.IMG_1.jpg")
        ix.despierta.set()
        self.esperar(ix, 2)
        self.assertNotIn("DCIM/Camera/IMG_1.jpg", ix.f)
        self.assertEqual(ix.estado()["conGps"], 3)

    def test_reanuda_tras_una_interrupcion(self):
        for i in range(30):
            imagen(self.base / f"f/IMG_{i:02d}.jpg", (10.0 + i, 20.0))
            os.utime(self.base / f"f/IMG_{i:02d}.jpg", (1_700_000_000 + i, 1_700_000_000 + i))
        a = self.indice()
        real = G.gps_de
        n = []

        def corta(ruta):
            n.append(ruta)
            if len(n) == 12:
                a.parar = True   # «se apaga el hub» a medio camino
            return real(ruta)
        with mock.patch.object(G, "gps_de", corta):
            a.arrancar()
            a.hilo.join(30)
        self.assertFalse(a.hilo.is_alive())
        self.assertFalse(a.indexando)
        guardado = json.loads(self.estado.read_text())["f"]
        self.assertEqual(len(guardado), 12)   # lo hecho hasta ahí quedó en disco
        self.assertEqual(sorted(guardado)[0], "f/IMG_18.jpg")   # y se empieza por lo más reciente
        b = self.indice()
        self.assertEqual(b.estado()["conGps"], 12)
        with mock.patch.object(G, "gps_de", wraps=real) as leer:
            b.arrancar()
            self.esperar(b)
        self.assertEqual(leer.call_count, 18)   # solo lo que faltaba
        self.assertEqual(b.estado(), {"conGps": 30, "sinGps": 0, "indexando": False, "progreso": 1.0})

    def test_archivo_que_desaparece_o_cambia_mientras_se_lee(self):
        for i in range(3):
            imagen(self.base / f"IMG_{i}.jpg", (10.0 + i, 20.0))
        real = G.gps_de

        def tramposo(ruta):
            r = real(ruta)
            if ruta.endswith("IMG_0.jpg"):
                os.unlink(ruta)                                   # desaparece
            elif ruta.endswith("IMG_1.jpg"):
                os.utime(ruta, (time.time() + 99, time.time() + 99))   # lo tocan mientras se lee
            return r
        ix = self.indice()
        with mock.patch.object(G, "gps_de", tramposo):
            ix.arrancar()
            self.esperar(ix)
        self.assertEqual(set(ix.f), {"IMG_2.jpg"})   # ni el que se fue ni el que cambió se apuntan a medias
        ix.despierta.set()
        self.esperar(ix, 2)
        self.assertEqual(set(ix.f), {"IMG_1.jpg", "IMG_2.jpg"})   # y a la siguiente, el que cambió ya está estable

    def test_json_estropeado(self):
        self.estado.parent.mkdir(parents=True)
        buenas = {"a.jpg": [1, 2, 10.5, 20.5], "b.jpg": [1, 2]}
        raiz = str(self.root.real)
        for contenido in ("", "no es json", "[]", "null", '"x"', "{}", json.dumps({"v": 2, "raiz": raiz, "f": {"a.jpg": [1, 2]}}), json.dumps({"v": 1, "raiz": raiz}),
                          json.dumps({"v": 1, "raiz": raiz, "f": []}), json.dumps({"v": 1, "raiz": raiz, "f": "x"}),
                          json.dumps({"v": 1, "raiz": "/otra/carpeta", "f": buenas}), json.dumps({"v": 1, "f": buenas}),   # de otra carpeta, o sin decir de cuál
                          json.dumps({"v": 1, "raiz": raiz, "f": {"a": 5, "b": [1], "c": [1, 2, 3], "d": ["x", 2], "e": [1, 2, 99, 20], "f": [1, 2, 0, 0], "g": None,
                                                                  "h": [1, 2, "a", "b"], "i": [1, 2, float("nan"), 1]}})):
            self.estado.write_text(contenido)
            ix = self.indice()
            self.assertEqual((ix.f, ix.p), ({}, {}), contenido)
        self.estado.write_bytes(b"\xff\xfe\x00\x01")
        self.assertEqual(self.indice().f, {})
        self.estado.write_text(json.dumps({"v": 1, "raiz": raiz, "f": {**buenas, "mala": [1, 2, 99, 20], "otra": 5}}))
        ix = self.indice()   # una entrada mala no tira las demás
        self.assertEqual(set(ix.f), {"a.jpg", "b.jpg"})
        self.assertEqual(ix.estado()["conGps"], 1)

    def test_carpeta_ausente_o_vacia(self):
        sin = A.Raiz("compartido", self.tmp / "no-existe")
        ix = G.Indice(sin, ruta=self.estado, pausa=0)
        self.hijos.append(ix)
        ix.arrancar()
        self.esperar(ix)
        self.assertEqual(ix.estado(), {"conGps": 0, "sinGps": 0, "indexando": False, "progreso": 1.0})

    def test_si_la_carpeta_desaparece_no_se_borra_el_indice(self):
        self.arbol()
        ix = self.indice()
        ix.arrancar()
        self.esperar(ix)
        for hijo in self.base.iterdir():   # p. ej. el disco sin montar: queda una carpeta vacía
            shutil.rmtree(hijo) if hijo.is_dir() and not hijo.is_symlink() else hijo.unlink()
        ix.despierta.set()
        self.esperar(ix, 2)
        self.assertEqual(ix.estado()["conGps"], 4)

    def test_arrancar_es_idempotente(self):
        self.arbol()
        ix = self.indice()
        for _ in range(5):
            ix.arrancar()
        h = ix.hilo
        self.esperar(ix)
        for _ in range(5):
            ix.arrancar()
        self.assertIs(ix.hilo, h)
        self.assertEqual(sum(t.name == "nube-geo" and t.is_alive() for t in threading.enumerate()), 1)
        self.assertTrue(h.daemon)
        time.sleep(0.5)
        self.assertEqual(ix.pasadas, 1)   # y llamar otra vez nada más empezar no provoca un segundo recorrido entero

    def test_llamar_otra_vez_nada_mas_empezar_no_repite_el_recorrido(self):
        self.arbol()
        ix = self.indice()
        with mock.patch.object(G.os, "setpriority", lambda *a: time.sleep(0.3)):   # el hilo tarda en ponerse en marcha (CPU saturada)
            ix.arrancar()
            ix.arrancar()   # (todavía no ha puesto «activo»; con fin = 0 parecería que toca recorrer otra vez)
            self.esperar(ix)
        time.sleep(0.4)
        self.assertEqual(ix.pasadas, 1)

    def test_arrancar_despierta_solo_si_toca(self):
        self.arbol()
        ix = self.indice()
        ix.arrancar()
        self.esperar(ix)
        ix.arrancar()
        time.sleep(0.2)
        self.assertEqual(ix.pasadas, 1)   # hace menos de REESCANEO s del último recorrido: no se repite
        imagen(self.base / "nueva.jpg", LONDRES)
        with mock.patch.object(G, "REESCANEO", 0):
            ix.arrancar()
            self.esperar(ix, 2)
        self.assertIn("nueva.jpg", ix.p)

    def test_arrancar_ahora_recorre_sin_esperar(self):
        self.arbol()
        ix = self.indice(intervalo=3600)
        ix.arrancar()
        self.esperar(ix)
        imagen(self.base / "nueva.jpg", LONDRES)
        ix.arrancar()
        time.sleep(0.2)
        self.assertNotIn("nueva.jpg", ix.p)   # sin ahora, hace menos de REESCANEO s: no se repite
        ix.arrancar(ahora=True)
        self.esperar(ix, 2)
        self.assertIn("nueva.jpg", ix.p)

    def test_arrancar_ahora_con_un_recorrido_en_marcha_repite_al_acabar(self):
        imagen(self.base / "a.jpg", SYDNEY)
        real = G.gps_de
        dentro, sigue = threading.Event(), threading.Event()

        def espera(ruta):
            dentro.set()
            sigue.wait(10)
            return real(ruta)
        ix = self.indice(intervalo=3600)
        with mock.patch.object(G, "gps_de", espera):
            ix.arrancar()
            self.assertTrue(dentro.wait(10))                # a medio recorrido
            imagen(self.base / "nueva.jpg", LONDRES)        # llega algo que este recorrido ya no verá
            ix.arrancar(ahora=True)
            sigue.set()
            self.esperar(ix, 2)
        self.assertEqual(set(ix.p), {"a.jpg", "nueva.jpg"})

    def test_con_el_indice_en_disco_solo_dice_indexando_si_hay_algo_nuevo(self):
        self.arbol()
        a = self.indice()
        a.arrancar()
        self.esperar(a)
        a.detener()
        os.unlink(self.base / "DCIM/Camera/IMG_4.jpg")   # algo que ya no está: el recorrido lo quita del índice

        def parada(f, dentro, sigue):   # f, pero esperando a que la dejen seguir
            def g(*args):
                dentro.set()
                sigue.wait(10)
                return f(*args)
            return g
        b = self.indice()
        e1, e2, s1, s2 = (threading.Event() for _ in range(4))
        with mock.patch.object(b, "_listar", parada(b._listar, e1, s1)), mock.patch.object(b, "_quitar", parada(b._quitar, e2, s2)):
            b.arrancar()
            self.assertTrue(e1.wait(10))
            leyendo = b.estado()     # recorriendo la carpeta, con el índice de antes
            s1.set()
            self.assertTrue(e2.wait(10))
            quitando = b.estado()    # ya sabe que no hay nada nuevo que leer
            s2.set()
            self.esperar(b)
        ya = {"conGps": 4, "sinGps": 3, "indexando": False, "progreso": 1.0}
        self.assertEqual((leyendo, quitando), (ya, ya))
        self.assertEqual(b.estado(), {**ya, "sinGps": 2})
        imagen(self.base / "nueva.jpg", LONDRES)
        c = self.indice()
        dentro, sigue = threading.Event(), threading.Event()
        with mock.patch.object(G, "gps_de", parada(G.gps_de, dentro, sigue)):
            c.arrancar()
            self.assertTrue(dentro.wait(10))
            durante = c.estado()
            sigue.set()
            self.esperar(c)
        self.assertEqual(durante, {"conGps": 4, "sinGps": 2, "indexando": True, "progreso": 0.857})   # 6 de 7 ya sabidos
        self.assertEqual(c.estado(), {"conGps": 5, "sinGps": 2, "indexando": False, "progreso": 1.0})

    def test_empieza_por_lo_mas_reciente_segun_su_fecha_real(self):
        for m in range(1, 11):   # cuanto más nueva la foto (por su nombre), más vieja la fecha del archivo
            p = imagen(self.base / f"IMG_2024{m:02d}15_000000.jpg", (10.0 + m, 20.0))
            os.utime(p, (1_700_000_000 - m * 86400, 1_700_000_000 - m * 86400))
        a = self.indice()
        real, n = G.gps_de, []

        def corta(ruta):
            n.append(ruta)
            if len(n) == 4:
                a.parar = True
            return real(ruta)
        with mock.patch.object(G, "gps_de", corta):
            a.arrancar()
            a.hilo.join(30)
        self.assertEqual(sorted(json.loads(self.estado.read_text())["f"]), [f"IMG_2024{m:02d}15_000000.jpg" for m in (7, 8, 9, 10)])

    def test_recorre_solo_cada_intervalo(self):
        self.arbol()
        ix = self.indice(intervalo=0.2)
        ix.arrancar()
        self.esperar(ix, 3)   # sin que nadie lo despierte
        imagen(self.base / "nueva.jpg", LONDRES)
        self.esperar(ix, ix.pasadas + 2)
        self.assertIn("nueva.jpg", ix.p)

    def test_progreso_mientras_indexa(self):
        for i in range(20):
            imagen(self.base / f"IMG_{i:02d}.jpg", (10.0 + i, 20.0))
        real = G.gps_de

        def lenta(ruta):
            time.sleep(0.04)
            return real(ruta)
        ix = self.indice()
        vistos = []
        with mock.patch.object(G, "gps_de", lenta):
            ix.arrancar()
            while ix.pasadas < 1:
                vistos.append(ix.estado())
                time.sleep(0.02)
        self.assertTrue(any(e["indexando"] and 0 < e["progreso"] < 1 for e in vistos), vistos[-5:])
        self.assertTrue(all(0 <= e["progreso"] <= 1 for e in vistos))
        self.assertEqual([e["progreso"] for e in vistos], sorted(e["progreso"] for e in vistos))   # solo crece
        self.assertEqual(vistos[0]["indexando"], True)
        self.assertEqual(ix.estado(), {"conGps": 20, "sinGps": 0, "indexando": False, "progreso": 1.0})

    def test_guarda_cada_poco_mientras_indexa(self):
        for i in range(20):
            imagen(self.base / f"IMG_{i:02d}.jpg", (10.0 + i, 20.0))
        real = G.gps_de
        ix = self.indice()
        visto = []

        def lenta(ruta):
            time.sleep(0.03)
            if self.estado.exists():
                visto.append(len(json.loads(self.estado.read_text())["f"]))
            return real(ruta)
        with mock.patch.object(G, "gps_de", lenta), mock.patch.object(G, "GUARDAR_CADA", 0.1):
            ix.arrancar()
            self.esperar(ix)
        self.assertTrue(visto and 0 < max(visto) < 20, visto)   # el disco iba por delante del final

    def test_no_se_cae_si_no_puede_guardar(self):
        self.arbol()
        ix = G.Indice(self.root, ruta="/proc/nube-geo-pruebas/geo.json", pausa=0)
        self.hijos.append(ix)
        ix.arrancar()
        self.esperar(ix)
        self.assertEqual(ix.estado()["conGps"], 4)
        self.assertTrue(ix.sucio)   # sigue pendiente de guardar

    def test_excepcion_en_una_pasada_no_mata_el_hilo(self):
        self.arbol()
        ix = self.indice(intervalo=0.1)
        malas = iter([RuntimeError("fallo de prueba")])

        def listar(self_=ix, orig=ix._listar):
            e = next(malas, None)
            if e:
                raise e
            return orig()
        with mock.patch.object(ix, "_listar", listar):
            ix.arrancar()
            fin = time.time() + 20
            while ix.pasadas < 1 and time.time() < fin:
                time.sleep(0.01)
        self.assertGreaterEqual(ix.pasadas, 1)
        self.assertEqual(ix.estado()["conGps"], 4)
        self.assertFalse(ix.indexando)

    def test_detener(self):
        self.arbol()
        ix = self.indice(intervalo=3600)
        ix.arrancar()
        self.esperar(ix)
        t = time.time()
        ix.detener()
        self.assertLess(time.time() - t, 2)
        self.assertFalse(ix.hilo.is_alive())

    def test_nombre_que_no_es_utf8(self):
        buena = imagen(self.tmp / "modelo.jpg", MADRID).read_bytes()
        raro = os.fsencode(self.base) + b"/caf\xe9 \xff.jpg"
        with open(raro, "wb") as f:
            f.write(buena)
        ix = self.indice()
        ix.arrancar()
        self.esperar(ix)
        rel = os.fsdecode(b"caf\xe9 \xff.jpg")
        self.assertIn(rel, ix.p)
        self.assertEqual(ix.puntos(10, -90, -180, 90, 180)[0]["path"], rel)
        self.assertEqual(ix.en_recuadro(40, -4, 41, -3), {rel})
        otro = self.indice()   # el JSON se escribe y se lee bien con ese nombre
        self.assertEqual(set(otro.p), {rel})

    @unittest.skipUnless(FFMPEG, "hace falta ffmpeg")
    def test_sin_ffprobe_no_se_apunta_como_sin_gps(self):
        hacer_video(self.base / "v.mp4", "-metadata", "location=+40.4168-003.7038/")
        imagen(self.base / "a.jpg", SYDNEY)
        ix = self.indice()
        with mock.patch.object(G, "_FFP", ""), mock.patch.object(G, "_FFP_T", time.time()):
            ix.arrancar()
            self.esperar(ix)
        self.assertEqual(set(ix.f), {"a.jpg"})   # la foto sí; el vídeo no se pudo mirar y no se da por «sin GPS»
        self.assertEqual(ix.estado()["progreso"], 1.0)
        ix.despierta.set()   # con ffprobe otra vez
        self.esperar(ix, 2)
        self.cerca(ix.f["v.mp4"][2:], MADRID)

    def test_sin_pillow_no_se_apunta_como_sin_gps(self):
        imagen(self.base / "a.jpg", SYDNEY)
        ix = self.indice()
        with mock.patch.object(G, "gps_de", return_value=None), mock.patch.dict(sys.modules, {"PIL.Image": None}):   # no se pudo leer y no hay Pillow
            ix.arrancar()
            self.esperar(ix)
        self.assertEqual(ix.f, {})
        ix.despierta.set()   # con Pillow otra vez
        self.esperar(ix, 2)
        self.cerca(ix.f["a.jpg"][2:], SYDNEY)

    def test_consultas_mientras_indexa_y_se_borra(self):
        for i in range(150):
            imagen(self.base / f"d{i % 5}/IMG_{i:03d}.jpg", (10.0 + (i % 7) * .01, 20.0 + (i % 11) * .01))
            os.utime(self.base / f"d{i % 5}/IMG_{i:03d}.jpg", (1_700_000_000 + i, 1_700_000_000 + i))
        ix = self.indice(intervalo=0.05)
        fallos, seguir = [], [True]

        def consulta():
            while seguir[0]:
                try:
                    ix.puntos(14, 0, 0, 20, 30)
                    ix.en_recuadro(0, 0, 20, 30)
                    ix.estado()
                except Exception as e:   # noqa: BLE001
                    fallos.append(repr(e))
        hilos = [threading.Thread(target=consulta) for _ in range(3)]
        for h in hilos:
            h.start()
        ix.arrancar()
        for i in range(0, 150, 3):   # mientras tanto desaparecen fotos (las portadas más nuevas entre ellas)
            try:
                (self.base / f"d{i % 5}/IMG_{149 - i:03d}.jpg").unlink()
            except FileNotFoundError:
                pass
            time.sleep(0.002)
        self.esperar(ix, 4)
        seguir[0] = False
        for h in hilos:
            h.join(10)
        self.assertEqual(fallos, [])
        ix.despierta.set()
        self.esperar(ix, ix.pasadas + 1)
        en_disco = {os.path.relpath(p, self.base) for p in glob.glob(str(self.base / "d*/*.jpg"))}
        self.assertEqual(set(ix.f), en_disco)

    def test_prioridad_baja_solo_en_su_hilo(self):
        if not hasattr(os, "setpriority"):
            self.skipTest("sin setpriority")
        self.arbol()
        visto = []
        real = G.gps_de

        def mira(ruta):
            visto.append(os.getpriority(os.PRIO_PROCESS, threading.get_native_id()))
            return real(ruta)
        antes = os.getpriority(os.PRIO_PROCESS, threading.get_native_id())
        ix = self.indice()
        with mock.patch.object(G, "gps_de", mira):
            ix.arrancar()
            self.esperar(ix)
        self.assertTrue(visto and all(v >= 10 for v in visto), visto)
        self.assertEqual(os.getpriority(os.PRIO_PROCESS, threading.get_native_id()), antes)   # el hilo que llama no se toca


class ApiDelModulo(ConArbol):
    """Las funciones sueltas que usará el hub: un índice por raíz."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(G, "ESTADO", self.estado)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.limpiar)
        self.limpiar()

    def limpiar(self):
        for ix in list(G._INDICES.values()):
            ix.detener()
        G._INDICES.clear()
        G._ULTIMO = None

    def test_sin_arrancar(self):
        self.assertEqual(G.estado(), {"conGps": 0, "sinGps": 0, "indexando": False, "progreso": 0.0})

    def test_de_punta_a_punta(self):
        self.arbol()
        G.arrancar(self.root)
        G.arrancar(self.root)
        ix = G._indice(self.root)
        self.assertIs(G._indice(A.Raiz("compartido", self.base)), ix)   # misma carpeta = mismo índice
        self.esperar(ix)
        self.assertEqual(G.estado(), {"conGps": 4, "sinGps": 3, "indexando": False, "progreso": 1.0})
        self.assertEqual(G.estado(self.root), G.estado())
        pts = G.puntos(self.root, 18, -90, -180, 90, 180)
        self.assertEqual(sum(c["n"] for c in pts), 4)
        self.assertEqual(G.en_recuadro(self.root, 40, -4, 41, -3), {"DCIM/Camera/IMG_1.jpg", "DCIM/Camera/IMG_2.jpg"})
        self.assertEqual(G.en_recuadro(self.root, *G.recuadro("-90,-180,90,180")), {"DCIM/Camera/IMG_1.jpg", "DCIM/Camera/IMG_2.jpg", "DCIM/Camera/IMG_3.png", "DCIM/Camera/IMG_5.heic"})
        self.assertTrue(self.estado.exists())

    def test_arrancar_ahora(self):
        self.arbol()
        G.arrancar(self.root)
        ix = G._indice(self.root)
        self.esperar(ix)
        imagen(self.base / "nueva.jpg", LONDRES)
        G.arrancar(self.root)   # hace menos de un minuto del último recorrido: espera
        time.sleep(0.2)
        self.assertEqual(G.en_recuadro(self.root, 51, -1, 52, 1), set())
        G.arrancar(self.root, ahora=True)
        self.esperar(ix, 2)
        self.assertEqual(G.en_recuadro(self.root, 51, -1, 52, 1), {"nueva.jpg"})

    def test_arrancar_desde_muchos_hilos_a_la_vez(self):
        self.arbol()
        fuera = threading.Barrier(16)
        hilos = [threading.Thread(target=lambda: (fuera.wait(), G.arrancar(self.root))) for _ in range(16)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(10)
        self.esperar(G._indice(self.root))
        self.assertEqual(sum(t.name == "nube-geo" and t.is_alive() for t in threading.enumerate()), 1)
        self.assertEqual(len(G._INDICES), 1)

    def test_puntos_arranca_solo(self):
        self.arbol()
        G.puntos(self.root, 5, -90, -180, 90, 180)   # sin arrancar antes
        ix = G._indice(self.root)
        self.assertTrue(ix.hilo and ix.hilo.is_alive())
        self.esperar(ix)

    def test_estado_sin_raiz_es_el_ultimo_usado(self):
        self.arbol()
        G.arrancar(self.root)
        self.esperar(G._indice(self.root))
        otra = A.Raiz("compartido", self.tmp / "otra")
        (self.tmp / "otra").mkdir()
        G.estado(otra)
        self.assertEqual(G.estado()["conGps"], 0)   # ahora el último es el de «otra»
        self.assertEqual(G.estado(self.root)["conGps"], 4)

    def test_errores_de_parametros(self):
        self.arbol()
        with self.assertRaises(ValueError):
            G.puntos(self.root, 5, "x", 0, 1, 1)
        with self.assertRaises(ValueError):
            G.en_recuadro(self.root, 0, 0, float("nan"), 1)


# ---------- rendimiento y memoria con una nube de verdad ----------
class Rendimiento(ConTmp):
    def test_35000_archivos(self):
        rnd = random.Random(2)
        ciudades = [(rnd.uniform(-55, 65), rnd.uniform(-170, 170)) for _ in range(40)]
        ix = G.Indice(A.Raiz("compartido", self.tmp), ruta=self.tmp / "geo.json", pausa=0)
        tracemalloc.start()
        antes = tracemalloc.get_traced_memory()[0]
        for i in range(35000):
            rel = f"Movil-S25/DCIM/Camera/IMG_2024{i % 12 + 1:02d}{i % 28 + 1:02d}_{i:06d}.jpg"
            gps = None
            if i % 5 < 2:   # 40 % con GPS, repartidos en 40 ciudades
                c = rnd.choice(ciudades)
                gps = (round(min(max(c[0] + rnd.gauss(0, .05), -89), 89), 6), round(min(max(c[1] + rnd.gauss(0, .05), -179), 179), 6))
            ix._poner(rel, 1_700_000_000 + i * 60, 200_000 + i, gps)
        mem = (tracemalloc.get_traced_memory()[0] - antes) / 1e6
        tracemalloc.stop()
        self.assertEqual(ix.estado()["conGps"], 14000)
        t = {}

        def mide(nombre, f):
            t0 = time.perf_counter()
            r = f()
            t[nombre] = (time.perf_counter() - t0) * 1000
            return r
        with mock.patch.object(G.os.path, "lexists", return_value=True):
            mundo = mide("puntos z=2 mundo", lambda: ix.puntos(2, -90, -180, 90, 180))
            mide("puntos z=8 mundo", lambda: ix.puntos(8, -90, -180, 90, 180))
            mide("puntos z=14 barrio", lambda: ix.puntos(14, ciudades[0][0] - .02, ciudades[0][1] - .02, ciudades[0][0] + .02, ciudades[0][1] + .02))
            mide("puntos z=18 mundo", lambda: ix.puntos(18, -90, -180, 90, 180))
        enr = mide("en_recuadro ciudad", lambda: ix.en_recuadro(ciudades[1][0] - .3, ciudades[1][1] - .3, ciudades[1][0] + .3, ciudades[1][1] + .3))
        mide("guardar", ix._guardar)
        tam = (self.tmp / "geo.json").stat().st_size / 1e6
        t0 = time.perf_counter()
        ix2 = G.Indice(A.Raiz("compartido", self.tmp), ruta=self.tmp / "geo.json", pausa=0)
        t["cargar"] = (time.perf_counter() - t0) * 1000
        self.assertEqual(ix2.estado(), ix.estado())
        print(f"\n  35.000 archivos (14.000 con GPS): memoria {mem:.1f} MB, JSON {tam:.1f} MB, " + ", ".join(f"{k} {v:.0f} ms" for k, v in t.items()))
        self.assertEqual(sum(c["n"] for c in mundo), 14000)
        self.assertGreater(len(enr), 10)
        self.assertLess(mem, 60)
        self.assertLess(tam, 8)
        for k, v in t.items():
            self.assertLess(v, 1500, k)


if __name__ == "__main__":
    unittest.main()
