"""Mapa de Mi nube: de dónde son las fotos y los vídeos de Compartido.

Saca el GPS de cada archivo (EXIF de JPEG/WebP/TIFF/PNG con Pillow; EXIF de HEIC/HEIF/AVIF con un lector propio de cajas ISOBMFF, porque Pillow
no los abre aquí; etiqueta de ubicación de MP4/MOV con ffprobe), lo apunta en un índice que se guarda en disco y lo agrupa en celdas según el zoom.
Solo lee: nunca modifica nada de Compartido. Las rutas son relativas a Compartido, como en nube.py.

El índice se hace en segundo plano (un solo hilo, de baja prioridad) y es incremental: lo que no ha cambiado (fecha y tamaño) no se vuelve a leer,
así que sobrevive a los reinicios y se puede reanudar a medias. Uso desde el hub (root = ROOTS["compartido"]):
    arrancar(root, ahora=False)         al arrancar o en la primera petición; se puede llamar siempre (no hace nada si ya corre);
                                        ahora=True pide recorrer ya (tras mover, tirar o subir algo)
    avisar(root)                        «algo cambió en Compartido»: recorre ya, pero solo si el mapa ya estaba en marcha
    puntos(root, zoom, s, w, n, e)      celdas para pintar en el mapa
    en_recuadro(root, s, w, n, e)       rutas dentro de un recuadro, para filtrar el listado
    recuadro("s,w,n,e")                 el ?bbox= de la URL → (s, w, n, e) o ValueError
    estado(root=None)                   {conGps, sinGps, indexando, progreso}
    gps_de(ruta_absoluta)               (lat, lon) o None, de un solo archivo
Los recuadros son (sur, oeste, norte, este) en grados; si oeste > este cruzan el antimeridiano. Los parámetros que no valen lanzan ValueError.
"""
import glob
import itertools
import json
import math
import os
import pwd
import re
import shutil
import stat
import struct
import subprocess
import sys
import threading
import time
import warnings
from datetime import datetime
from pathlib import Path

import archivos as A

# Pillow avisa por stderr de cada EXIF estropeado: aquí es lo normal en alguna foto rota y no hay nada que hacer
warnings.filterwarnings("ignore", message=r"Corrupt EXIF data|Truncated File Read", category=UserWarning)

HOME = Path(os.environ.get("HOME") or Path.home())
_ESTADOS = Path(os.environ["HUB_NUBE"]).parent if os.environ.get("HUB_NUBE") else HOME / ".local/state/zazu-nube"   # junto a nube.json: quien lo aparta para probar aparta también las coordenadas
ESTADO = Path(os.environ.get("HUB_NUBE_GEO") or _ESTADOS / "geo.json")
HEIF = ("heic", "heif", "avif")
VIDEO = ("mp4", "mov", "m4v", "3gp")
LEIBLES = frozenset(HEIF + VIDEO + ("jpg", "jpeg", "webp", "tif", "tiff", "png"))
MAX_META = 2 << 20        # caja «meta» de un HEIC: normalmente unos KB
MAX_EXIF = 1 << 20        # EXIF de un HEIC
MAX_WEBP = 64 << 20       # Pillow lee los WebP enteros; JPEG, TIFF y HEIC no (solo la cabecera) y de PNG se mira el tamaño en píxeles
TIMEOUT_FFPROBE = 15      # segundos por vídeo
MAX_PUNTOS = 600          # celdas que devuelve puntos() como máximo; si hay más, las más llenas
CELDA_PX = 64             # lado de una celda en pantalla (píxeles de un mapa de teselas de 256)
LAT_MAX = 85.0511287798   # límite del mapa Mercator de las teselas
TOPE = 1 - 1e-9
GUARDAR_CADA = 30         # segundos entre guardados mientras se indexa
REESCANEO = 60            # una petición despierta un nuevo recorrido si hace más de esto que acabó el último
INTERVALO = 300           # y, sin peticiones, se recorre de nuevo cada tanto
EPS = 1e-7                # holgura del recuadro: las coordenadas se guardan con 6 decimales, así que ningún vecino (a 1e-6) entra y un borde exacto nunca se pierde
_PIL = threading.Lock()   # una lectura de Pillow a la vez (ver _gps_pil)


# ---------- GPS de un archivo ----------
def _valido(lat, lon):
    """(lat, lon) con 6 decimales (11 cm), o None si faltan, no son números, se salen de rango o son el (0, 0) de «sin fix»."""
    try:
        lat, lon = round(float(lat), 6), round(float(lon), 6)
    except (TypeError, ValueError, OverflowError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon) else None


def _grados(v, ref, neg):
    """Grados decimales de un valor EXIF (grados, minutos, segundos) con su letra de hemisferio (neg = la letra del negativo: S u W);
    None si no se entiende. Los números son magnitudes; si alguna cámara los escribe con signo, solo manda cuando falta la letra."""
    v = v if isinstance(v, (tuple, list)) else (v,)
    try:
        nums = [float(x) for x in v[:3]]
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if not nums:
        return None
    if isinstance(ref, bytes):
        ref = ref.decode("ascii", "ignore")
    ref = str(ref or "").strip("\x00 ").upper()
    d = sum(abs(x) / 60 ** i for i, x in enumerate(nums))
    return -d if ref.startswith(neg) or (not ref and nums[0] < 0) else d


def _coords(g):
    """(lat, lon) del IFD GPS de un EXIF (etiquetas 1 a 4), o None."""
    return _valido(_grados(g.get(2), g.get(1), "S"), _grados(g.get(4), g.get(3), "W")) if g else None


def _gps_exif(tiff):
    """GPS de un bloque TIFF/EXIF (cabecera «II*» o «MM*»); None si no es uno."""
    if not tiff or tiff[:4] not in (b"II*\x00", b"MM\x00*"):
        return None
    from PIL import Image
    ex = Image.Exif()
    ex.load(tiff)
    return _coords(ex.get_ifd(0x8825))


def _gps_pil(ruta):
    from PIL import Image   # perezoso: la primera vez tarda ~0,1 s
    with _PIL:   # solo se lee la cabecera: el tope contra «bombas» de descompresión es para quien descodifica, y un JPEG de 200 Mpíx daría error
        tope, Image.MAX_IMAGE_PIXELS = Image.MAX_IMAGE_PIXELS, None
        try:
            with Image.open(ruta) as im:
                if im.format == "PNG" and im.width * im.height > 25_000_000:
                    return None   # para llegar al EXIF Pillow descodificaría todo el PNG
                return _coords(im.getexif().get_ifd(0x8825))
        finally:
            Image.MAX_IMAGE_PIXELS = tope


def _cajas(leer, i, fin):
    """(tipo, inicio del contenido, fin) de cada caja ISOBMFF entre i y fin. leer(pos, n) devuelve bytes del archivo o de un búfer."""
    while i + 8 <= fin:
        h = leer(i, 16)
        n, t = struct.unpack_from(">I4s", h)
        cab = 8
        if n == 1:
            n, cab = struct.unpack_from(">Q", h, 8)[0], 16
        elif n == 0:
            n = fin - i
        if n < cab:
            return
        yield t, i + cab, min(i + n, fin)
        i += n


def _exif_heif(ruta):
    """Bloque TIFF del EXIF de un HEIC/HEIF/AVIF: el ítem «Exif» que dicen las cajas iinf e iloc de «meta» (en los del móvil va detrás de «mdat»).
    Lee unos KB, no la imagen. Con cualquier cosa rara (cajas cortadas, tamaños absurdos) lanza o devuelve None."""
    with open(ruta, "rb") as f:
        leer = lambda p, n: (f.seek(p), f.read(n))[1]
        tam = os.fstat(f.fileno()).st_size
        for t, a, b in itertools.islice(_cajas(leer, 0, tam), 64):
            if t == b"meta":
                break
        else:
            return None
        if not 12 <= b - a <= MAX_META:
            return None
        meta = leer(a, b - a)   # versión y banderas (4 bytes) y luego las cajas hijas
        hijas = {t: (x, y) for t, x, y in _cajas(lambda p, n: meta[p:p + n], 4, len(meta))}
        if b"iinf" not in hijas or b"iloc" not in hijas:
            return None
        pos = [0]

        def num(k):
            if pos[0] + k > len(meta):
                raise ValueError("caja cortada")
            v = int.from_bytes(meta[pos[0]:pos[0] + k], "big")
            pos[0] += k
            return v

        x, y = hijas[b"iinf"]   # qué ítem es el «Exif»
        pos[0] = x
        v = num(1)
        num(3 + (2 if v == 0 else 4))
        exif = None
        for t, a2, b2 in _cajas(lambda p, n: meta[p:p + n], pos[0], y):
            pos[0] = a2
            v = num(1)   # infe: versión 2 (ids de 16 bits) o 3 (de 32); antes no había tipo de ítem
            if t == b"infe" and v >= 2:
                num(3)
                i = num(2 if v == 2 else 4)
                num(2)
                if meta[pos[0]:pos[0] + 4] == b"Exif":
                    exif = i
                    break
        if exif is None:
            return None
        x, y = hijas[b"iloc"]   # dónde está
        pos[0] = x
        v = num(1)
        num(3)
        t_off, t_len = divmod(num(1), 16)
        t_base, t_idx = divmod(num(1), 16)
        for _ in range(num(2 if v < 2 else 4)):
            i, metodo = num(2 if v < 2 else 4), (num(2) & 15 if v else 0)
            num(2)
            base = num(t_base)
            trozos = []
            for _ in range(min(num(2), 64)):
                if v and t_idx:
                    num(t_idx)
                trozos.append((base + num(t_off), num(t_len)))
            if i == exif:
                break
        else:
            return None
        if sum(ln for _, ln in trozos) > MAX_EXIF:
            return None
        if metodo == 0:   # desplazamiento en el archivo
            datos = b"".join(leer(o, ln) for o, ln in trozos)
        elif metodo == 1 and b"idat" in hijas:   # dentro de la caja idat
            o = hijas[b"idat"][0]
            datos = b"".join(meta[o + d:o + d + ln] for d, ln in trozos)
        else:
            return None
    return datos[4 + struct.unpack_from(">I", datos)[0]:]   # 4 bytes con la distancia hasta la cabecera TIFF


_ISO6709 = re.compile(r"\s*([+-]\d{1,2}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)(?:[+-]\d+(?:\.\d+)?)?(?:CRS\w*)?/?\s*")
_FFP, _FFP_T = None, 0.0


def _iso6709(txt):
    """«+40.4168-003.7038+000.000/» → (lat, lon). Solo el formato en grados decimales (el que escriben Android e iPhone)."""
    m = _ISO6709.fullmatch(txt) if isinstance(txt, str) else None
    return _valido(m[1], m[2]) if m else None


def _ffprobe():
    """ffprobe: HUB_FFPROBE, el del sistema o el de ~/.hermes/tools (también en la casa de verdad si HOME es una falsa de pruebas).
    Si el que se encontró ya no está (se actualizó ffmpeg) o no había ninguno, busca de nuevo, como mucho una vez por minuto. "" si no hay."""
    global _FFP, _FFP_T
    if _FFP and os.access(_FFP, os.X_OK):
        return _FFP
    if _FFP is None or time.time() - _FFP_T > 60:
        casas = {HOME, Path(pwd.getpwuid(os.getuid()).pw_dir)}
        cand = [os.environ.get("HUB_FFPROBE"), shutil.which("ffprobe"), *(p for c in casas for p in sorted(glob.glob(str(c / ".hermes/tools/ffmpeg-*/bin/ffprobe"))))]
        _FFP, _FFP_T = next((c for c in cand if c and os.access(c, os.X_OK)), ""), time.time()
    return _FFP if _FFP and os.access(_FFP, os.X_OK) else ""


def _gps_video(ruta):
    prog = _ffprobe()
    if not prog:
        return None
    # -f mov: solo el desmontador de MP4/MOV; -protocol_whitelist file: un «vídeo» que en realidad es una lista con URLs no sale a internet
    r = subprocess.run([prog, "-v", "quiet", "-f", "mov", "-protocol_whitelist", "file", "-show_entries", "format_tags:stream_tags", "-of", "json", "-i", ruta],
                       capture_output=True, text=True, errors="replace", timeout=TIMEOUT_FFPROBE, stdin=subprocess.DEVNULL)
    d = json.loads(r.stdout)
    for tags in [(d.get("format") or {}).get("tags") or {}] + [s.get("tags") or {} for s in d.get("streams") or []]:
        for k, v in tags.items():
            if (k.lower().startswith("location") or k.lower() == "com.apple.quicktime.location.iso6709") and (g := _iso6709(v)):
                return g
    return None


def _hay_lector(ext):
    """¿Hay con qué leer este tipo? Si no (sin ffprobe o sin Pillow) no se apunta «sin GPS» para siempre: se reintenta cuando lo haya."""
    if ext in VIDEO:
        return bool(_ffprobe())
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        return False


def gps_de(ruta):
    """(lat, lon) en grados decimales de una foto o un vídeo, o None si no tiene GPS, el archivo está estropeado o no es de un tipo que se lea. Nunca lanza."""
    try:
        ruta = os.fspath(ruta)
        st = os.stat(ruta)
        ext = os.path.splitext(ruta)[1][1:].lower()
        if not stat.S_ISREG(st.st_mode) or ext not in LEIBLES:   # ni tuberías ni carpetas: abrirlas podría bloquear
            return None
        if ext in VIDEO:
            return _gps_video(ruta)
        if ext == "webp" and st.st_size > MAX_WEBP:
            return None
        return _gps_exif(_exif_heif(ruta)) if ext in HEIF else _gps_pil(ruta)
    except Exception:
        return None


# ---------- el mapa: posición, recuadros y celdas ----------
def _xy(lat, lon):
    """Posición 0..1 en el mapa Mercator de teselas: x de oeste a este, y de norte a sur."""
    la = math.radians(max(-LAT_MAX, min(LAT_MAX, lat)))
    y = 0.5 - math.log(math.tan(math.pi / 4 + la / 2)) / (2 * math.pi)
    return min(max((lon + 180) / 360, 0.0), TOPE), min(max(y, 0.0), TOPE)


def _num(*xs):
    """Los números finitos de xs como floats; ValueError si alguno falta (None), no es un número o es NaN o infinito."""
    try:
        r = [float(x) for x in xs]
    except TypeError:
        raise ValueError("falta un número") from None
    if not all(map(math.isfinite, r)):
        raise ValueError("número no válido")
    return r


def _norm(s, w, n, e):
    """Recuadro normalizado (s, w, n, e): latitudes en -90..90 y de menor a mayor; longitudes en -180..180. Si w > e cruza el antimeridiano (±180)."""
    s, w, n, e = _num(s, w, n, e)
    s, n = sorted((max(-90.0, min(90.0, s)), max(-90.0, min(90.0, n))))
    ancho = e - w if e >= w else e - w + 360   # (w > e: da la vuelta por los 180°)
    if ancho >= 360:
        return s, -180.0, n, 180.0
    if -180 <= w <= 180 and -180 <= e <= 180:   # ya está bien; un este de justo 180° no cruza nada
        return s, w, n, e
    w = (w + 180) % 360 - 180
    return s, w, n, w + ancho if w + ancho <= 180 else w + ancho - 360


def recuadro(texto):
    """«s,w,n,e» (como llega en ?bbox=) → (s, w, n, e) normalizado. ValueError si no son cuatro números."""
    partes = str(texto).split(",")
    if len(partes) != 4:
        raise ValueError("recuadro no válido")
    return _norm(*partes)


def _dentro(lat, lon, s, w, n, e):
    return s - EPS <= lat <= n + EPS and ((w - EPS <= lon <= e + EPS) if w <= e else (lon >= w - EPS or lon <= e + EPS))


# ---------- el índice ----------
_FECHA_NOMBRE = re.compile(r"(?<!\d)(20\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")


def fecha_medio(nombre, mtime):
    """La fecha real de una foto: la de su nombre (IMG_20240117_…, IMG-20261023-WA…) y, si no la tiene, la del archivo (la del archivo casi nunca vale: se copió
    después). Es la que usa también el listado de server.py, para que «la más nueva» de una celda sea la que la web ordena como más nueva.
    Una fecha de archivo absurda (antes de 1970 o después de 2100) se queda en 0: no tumba el listado ni «un día como hoy»."""
    m = _FECHA_NOMBRE.search(nombre)
    if m:
        try:
            return int(datetime(int(m[1]), int(m[2]), int(m[3]), 12).timestamp())
        except ValueError:
            pass
    return mtime if 0 <= mtime < 4102444800 else 0


class Indice:
    """Las coordenadas de todos los medios de una raíz. f: ruta → (mtime, tamaño) o (mtime, tamaño, lat, lon); p: lo mismo solo de los que tienen GPS,
    ya con su posición en el mapa: (x, y, lat, lon, fecha real, ruta)."""

    def __init__(self, root, ruta=None, pausa=1.0, intervalo=INTERVALO):
        self.root, self.ruta, self.pausa, self.intervalo = root, Path(ruta or ESTADO), pausa, intervalo
        self.base = str(root.real)
        self.f, self.p = {}, {}
        self.lock, self.despierta = threading.Lock(), threading.Event()
        self.hilo, self.parar, self.sucio, self.activo = None, False, False, False
        self.total = self.hechos = self.pasadas = 0
        self.indexando, self.fin = False, 0.0
        self._cargar()

    # -- disco --
    def _cargar(self):
        try:
            d = json.loads(self.ruta.read_text(encoding="utf-8"))
            datos = d["f"] if d["v"] == 1 and d["raiz"] == self.base else None   # el de otra carpeta no sirve
        except (OSError, ValueError, KeyError, TypeError):
            return
        if not isinstance(datos, dict):
            return
        for rel, v in datos.items():
            try:   # una entrada estropeada se salta sin más: se vuelve a leer en la próxima pasada
                mt, sz = int(v[0]), int(v[1])
                gps = _valido(v[2], v[3]) if len(v) == 4 else None
                if isinstance(rel, str) and (len(v) == 2 or gps):
                    self._poner(rel, mt, sz, gps)
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
        self.sucio = False

    def _guardar(self):
        with self.lock:
            copia, self.sucio = dict(self.f), False
        try:
            self.ruta.parent.mkdir(mode=0o700, parents=True, exist_ok=True)   # (la carpeta es la de nube.json: privada también si la crea el mapa primero)
            tmp = self.ruta.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # las coordenadas son privadas
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"v": 1, "raiz": self.base, "f": copia}, separators=(",", ":")))
            os.replace(tmp, self.ruta)
        except OSError as e:
            self.sucio = True
            print(f"nube_geo: no pude guardar el índice: {e}", file=sys.stderr)

    # -- memoria --
    def _poner(self, rel, mt, sz, gps):
        with self.lock:
            self.sucio = True
            if gps:
                self.f[rel] = (mt, sz, *gps)
                self.p[rel] = (*_xy(*gps), *gps, fecha_medio(rel.rpartition("/")[2], mt), rel)
            else:
                self.f[rel] = (mt, sz)
                self.p.pop(rel, None)

    def _quitar(self, rel):
        with self.lock:
            self.sucio = True
            self.f.pop(rel, None)
            self.p.pop(rel, None)

    def _puntos(self):
        with self.lock:
            return list(self.p.values())

    # -- hilo --
    def arrancar(self, ahora=False):
        with self.lock:
            if self.hilo and self.hilo.is_alive():
                if ahora or (not self.activo and time.time() - self.fin > REESCANEO):   # (si ahora está recorriendo, repite al acabar)
                    self.despierta.set()
                return
            # activo ya (no cuando el hilo llegue a ponerlo): otra llamada justo después no debe creer que está parado y pedir un segundo recorrido
            self.parar, self.activo, self.indexando = False, True, not (self.pasadas or self.f)   # con el índice ya en disco no hay «indexando» hasta que haya algo nuevo
            self.hilo = threading.Thread(target=self._bucle, name="nube-geo", daemon=True)
            self.hilo.start()

    def detener(self):
        self.parar = True
        self.despierta.set()
        if self.hilo:
            self.hilo.join(30)

    def _bucle(self):
        try:   # en Linux la prioridad es por hilo: solo baja la de este (y la de los ffprobe que lance), no la del hub
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 15)
        except (AttributeError, OSError):
            pass
        while not self.parar:
            self.activo = True
            try:
                self._pasada()
            except Exception as e:
                print(f"nube_geo: {e}", file=sys.stderr)
            self.fin, self.indexando, self.activo = time.time(), False, False   # (activo el último: quien lo vea parado ya ve el fin de ahora)
            if not self.parar:
                self.despierta.wait(self.intervalo)
                self.despierta.clear()

    def _listar(self):
        out = []
        for e in A.recorrer(self.root, limite=5_000_000):
            if self.parar:
                break
            if os.path.splitext(e.name)[1][1:].lower() in LEIBLES and e.is_file(follow_symlinks=False):
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                out.append((self.root.rel(e.path), e.path, int(st.st_mtime), st.st_size))
        return out

    def _pasada(self):
        """Recorre Compartido, lee el GPS de lo nuevo o cambiado (lo más reciente primero) y quita lo que ya no está."""
        inicio, cand = time.time(), self._listar()
        if self.parar:
            return
        pend = [c for c in cand if self.f.get(c[0], ())[:2] != (c[2], c[3])]
        pend.sort(key=lambda c: -fecha_medio(c[0].rpartition("/")[2], c[2]))   # lo más reciente (por su fecha real) sale antes en el mapa
        self.total, self.hechos = len(cand), len(cand) - len(pend)
        self.indexando = bool(pend) or not (self.pasadas or self.f)
        ult = time.time()
        for rel, ruta, mt, sz in pend:
            if self.parar:
                break
            t = time.perf_counter()
            gps = gps_de(ruta)
            try:   # si cambió o desapareció mientras se leía, no se apunta: se verá en la próxima pasada
                st = os.stat(ruta)
                if (int(st.st_mtime), st.st_size) == (mt, sz) and (gps or _hay_lector(os.path.splitext(ruta)[1][1:].lower())):
                    self._poner(rel, mt, sz, gps)
            except OSError:
                pass
            self.hechos += 1
            if time.time() - ult > GUARDAR_CADA and self.sucio:
                self._guardar()
                ult = time.time()
            if self.pausa:
                time.sleep(min(0.05, (time.perf_counter() - t) * self.pausa))
        if not self.parar and cand:   # sin ningún medio visible no se quita nada: puede ser que la carpeta no esté montada
            vistos = {c[0] for c in cand}
            with self.lock:   # (puntos() también quita cosas desde otros hilos)
                muertos = [k for k in self.f if k not in vistos]
            for rel in muertos:
                self._quitar(rel)
        if self.sucio:
            self._guardar()
        if not self.parar:
            self.hechos, self.indexando = self.total, False
            self.pasadas += 1
            if len(pend) >= 100:
                print(f"nube_geo: leídos {len(pend)} archivos en {time.time() - inicio:.0f} s; {len(self.p)} con GPS de {len(self.f)}", file=sys.stderr)

    # -- consultas --
    def estado(self):
        con = len(self.p)
        prog = self.hechos / self.total if self.total else float(bool(self.pasadas or self.f))
        return {"conGps": con, "sinGps": len(self.f) - con, "indexando": self.indexando, "progreso": round(prog, 3)}

    def en_recuadro(self, s, w, n, e):
        s, w, n, e = _norm(s, w, n, e)
        return {rel for _, _, lat, lon, _, rel in self._puntos() if _dentro(lat, lon, s, w, n, e)}

    def _celdas(self, zoom, s, w, n, e):
        z = int(round(min(max(_num(zoom)[0], 0.0), 18.0)))
        s, w, n, e = _norm(s, w, n, e)
        N = (256 << z) // CELDA_PX   # celdas por lado de todo el mapa
        col = lambda lon: min(int((lon + 180) / 360 * N), N - 1)
        a, b, cruza = col(w), col(e), w > e
        y0, y1 = int(_xy(n, 0)[1] * N), int(_xy(s, 0)[1] * N)   # las celdas que toca el recuadro, enteras: así no cambian al mover el mapa
        celdas = {}
        for x, y, lat, lon, fe, rel in self._puntos():
            cx, cy = int(x * N), int(y * N)
            if not (y0 <= cy <= y1 and ((cx >= a or cx <= b) if cruza else a <= cx <= b)):
                continue
            c = celdas.get(cy * N + cx)
            if c is None:
                celdas[cy * N + cx] = [1, lat, lon, fe, rel, lat, lon, lat, lon]
                continue
            c[0] += 1
            c[1] += lat
            c[2] += lon
            if (fe, rel) > (c[3], c[4]):   # la portada es la más nueva por su fecha real (y, el mismo día, la de nombre mayor: la hora va en el nombre)
                c[3], c[4] = fe, rel
            c[5], c[6], c[7], c[8] = min(c[5], lat), min(c[6], lon), max(c[7], lat), max(c[8], lon)
        return celdas.values()

    def puntos(self, zoom, s, w, n, e, maximo=MAX_PUNTOS):
        for _ in range(3):   # si la portada de una celda ya no existe se quita del índice y se repite (como mucho tres veces)
            cs = sorted(self._celdas(zoom, s, w, n, e), key=lambda c: (-c[0], -c[3], c[4]))[:max(0, int(maximo))]
            muertos = [c[4] for c in cs if not os.path.lexists(os.path.join(self.base, c[4]))]
            if not muertos:
                break
            for rel in muertos:
                self._quitar(rel)
        return [{"lat": round(c[1] / c[0], 6), "lon": round(c[2] / c[0], 6), "n": c[0], "path": c[4],
                 "kind": "video" if os.path.splitext(c[4])[1][1:].lower() in VIDEO else "image", "caja": [c[5], c[6], c[7], c[8]]} for c in cs]


# ---------- API para el hub: un índice por raíz ----------
_INDICES, _ULTIMO, _CERROJO = {}, None, threading.Lock()


def _indice(root):
    global _ULTIMO
    with _CERROJO:
        ix = _INDICES.get(str(root.real))
        if ix is None:
            ix = _INDICES[str(root.real)] = Indice(root)
        _ULTIMO = ix
    return ix


def arrancar(root, ahora=False):
    """Pone en marcha (una sola vez) el hilo que indexa el GPS de root. Se puede llamar en cada petición: si ya corre, solo lo despierta si toca recorrer otra vez
    (hace más de un minuto del último recorrido). ahora=True lo despierta ya, para cuando el hub sabe que algo cambió en Compartido (mover, tirar, subir)."""
    _indice(root).arrancar(ahora)


def avisar(root):
    """Algo cambió en root (mover, renombrar, tirar, subir): si el mapa ya está en marcha, recorre ya (solo lo nuevo o cambiado); si nadie lo ha pedido
    todavía no hace nada, porque el primer recorrido lo verá todo. Barata: la llama el hub en cada cambio."""
    with _CERROJO:
        ix = _INDICES.get(str(root.real))
    if ix and ix.hilo and ix.hilo.is_alive():
        ix.arrancar(ahora=True)


def estado(root=None):
    """{conGps, sinGps, indexando, progreso (0..1)}. Sin root, el de la última raíz que se usó."""
    ix = _indice(root) if root is not None else _ULTIMO
    return ix.estado() if ix else {"conGps": 0, "sinGps": 0, "indexando": False, "progreso": 0.0}


def puntos(root, zoom, s, w, n, e, maximo=MAX_PUNTOS):
    """Celdas del mapa dentro del recuadro (s, w, n, e) para ese zoom (0 a 18), de la más llena a la menos:
    [{lat, lon (medios), n (cuántos), path (el más nuevo, de portada), kind, caja [s, w, n, e] (recuadro justo de lo que agrupa)}].
    ValueError si el recuadro no son números."""
    ix = _indice(root)
    ix.arrancar()
    return ix.puntos(zoom, s, w, n, e, maximo)


def en_recuadro(root, s, w, n, e):
    """Set con las rutas (relativas a root) de los medios con GPS dentro del recuadro, bordes incluidos. ValueError si no son números."""
    ix = _indice(root)
    ix.arrancar()
    return ix.en_recuadro(s, w, n, e)
