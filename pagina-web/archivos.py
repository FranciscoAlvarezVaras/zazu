"""Carpetas de HolaZazu: raíces, listados, búsqueda, mover/renombrar y papelera. Solo biblioteca estándar.

Reglas: nunca se sigue un acceso directo (symlink), nunca se pisa un archivo (« (2)», « (3)»…)
y nada se borra de verdad desde la app: va a la papelera, que se vacía sola a los 30 días.
"""
import functools, heapq, json, math, mimetypes, os, re, secrets, shutil, threading, time, unicodedata
from pathlib import Path

HIDDEN = (".stfolder", ".stversions", ".stignore")
PAPELERA_DIAS = 30
ID_PAPELERA = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")
MALOS = re.compile(r'[\\:*?"<>|\x00-\x1f\x7f]')   # lo que el móvil (Android) y Windows no aceptan en un nombre
RESERVADO = "Ese nombre lo usa el móvil para sincronizar: elige otro."   # oculto(): Carpetas no lo enseñaría y Syncthing lo borra
# lo escribe recibidos-whatsapp.py: una ruta por línea, relativa a «40 Compartido», de lo que copió desde WhatsApp
ORIGEN_WHATSAPP = Path.home() / ".local/state/recibidos-whatsapp-origen.txt"
LOCK = threading.RLock()   # mover/renombrar/tirar de uno en uno: dos a la vez podrían elegir el mismo « (2)»
# lo que el navegador puede enseñar sin riesgo (nada que ejecute código)
SAFE_INLINE = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp", "application/pdf",
               "text/plain", "text/markdown", "audio/mpeg", "audio/ogg", "audio/wav", "audio/mp4", "audio/aac",
               "video/mp4", "video/webm", "video/quicktime")
TIPOS = {"pdf": "pdf",
         **dict.fromkeys(("jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "bmp", "avif", "svg", "tif", "tiff"), "image"),
         **dict.fromkeys(("mp4", "webm", "mov", "mkv", "avi", "3gp", "m4v"), "video"),
         **dict.fromkeys(("mp3", "ogg", "opus", "m4a", "wav", "aac", "flac", "amr", "oga"), "audio"),
         **dict.fromkeys(("doc", "docx", "odt", "rtf", "pages", "ppt", "pptx", "odp", "key", "epub"), "doc"),
         **dict.fromkeys(("xls", "xlsx", "ods", "csv", "numbers", "tsv"), "sheet"),
         **dict.fromkeys(("txt", "log", "json", "xml", "yaml", "yml", "ini", "html", "htm"), "text"),
         "md": "note"}


class Fallo(Exception):
    """Error que se le enseña a Fran tal cual (código HTTP + frase corta en español)."""
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def oculto(nombre):
    return (nombre.startswith(".") or nombre in HIDDEN or nombre.startswith("~syncthing~")
            or nombre.endswith(".subiendo") or nombre.endswith(".syncthing.tmp"))


def tipo(nombre, es_dir=False):
    if es_dir:
        return "folder"
    return TIPOS.get(nombre.rsplit(".", 1)[-1].lower() if "." in nombre else "", "other")


def mime(nombre):
    return mimetypes.guess_type(nombre)[0] or "application/octet-stream"


def clave(s):
    """Como compara el móvil: sin distinguir mayúsculas ni cómo se guardó la tilde."""
    return unicodedata.normalize("NFC", s).casefold()


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


class Raiz:
    """Una raíz de Carpetas. solo = únicas carpetas visibles arriba; sin = carpetas de arriba que no se ven."""
    def __init__(self, nombre, base, rw=False, solo=None, sin=(), protegidas=()):
        self.nombre, self.base, self.rw = nombre, Path(base), rw
        self.solo = set(solo) if solo else None
        self.sin, self.protegidas = set(sin), set(protegidas)

    @functools.cached_property
    def real(self):
        return self.base.resolve()

    def visible(self, nombre, arriba=False):
        if oculto(nombre):
            return False
        return not arriba or ((self.solo is None or nombre in self.solo) and nombre not in self.sin)

    def ruta(self, rel):
        """Ruta absoluta y comprobada de rel. Nunca sale de la raíz ni pasa por un acceso directo."""
        rel = str(rel or "")
        if "\x00" in rel:
            raise PermissionError("ruta no válida")
        partes = [x for x in rel.split("/") if x not in ("", ".")]
        if ".." in partes:
            raise PermissionError("ruta fuera de tus carpetas")
        for i, x in enumerate(partes):
            if not self.visible(x, i == 0):
                raise PermissionError("ruta reservada")
        p = self.real.joinpath(*partes)
        if p.resolve() != p:
            raise PermissionError("ruta no permitida")   # hay un acceso directo por medio: no se sigue
        return p

    def rel(self, p):
        r = Path(p).relative_to(self.real).as_posix()
        return "" if r == "." else r

    def escribible(self):
        if not self.rw:
            raise Fallo(403, "Esta carpeta es solo para ver.")


def _ficha(raiz, e, contar=False):
    es_dir = e.is_dir(follow_symlinks=False)
    st = e.stat(follow_symlinks=False)
    it = {"name": e.name, "path": raiz.rel(e.path), "dir": es_dir, "size": 0 if es_dir else st.st_size,
          "mtime": int(st.st_mtime), "kind": tipo(e.name, es_dir), "inline": not es_dir and mime(e.name) in SAFE_INLINE}
    if es_dir and contar:
        try:
            with os.scandir(e.path) as dentro:
                it["n"] = sum(1 for x in dentro if not oculto(x.name) and not x.is_symlink())
        except OSError:
            it["n"] = 0
    return it


def listar(raiz, rel=""):
    p = raiz.ruta(rel)
    if not p.is_dir():
        if not p.exists():
            raise FileNotFoundError(p)
        raise Fallo(400, "Eso no es una carpeta.")
    arriba = p == raiz.real
    with os.scandir(p) as it:
        out = [_ficha(raiz, e, contar=True) for e in it if raiz.visible(e.name, arriba) and not e.is_symlink()]
    out.sort(key=lambda x: (not x["dir"], clave(x["name"])))
    return {"root": raiz.nombre, "path": raiz.rel(p), "readonly": not raiz.rw, "items": out}


def recorrer(raiz, rel="", limite=30000):
    """DirEntry de todo lo visible bajo rel, sin seguir accesos directos (con tope, por si acaso)."""
    pila, n = [raiz.ruta(rel)], 0
    while pila:
        d = pila.pop()
        arriba = d == raiz.real
        try:
            with os.scandir(d) as it:
                ents = list(it)
        except OSError:
            continue
        for e in ents:
            if not raiz.visible(e.name, arriba) or e.is_symlink():
                continue
            n += 1
            if n > limite:
                return
            yield e
            if e.is_dir(follow_symlinks=False):
                pila.append(Path(e.path))


_wa = (None, frozenset())   # (firma del archivo, rutas): se relee solo si cambia


def de_whatsapp():
    """Rutas (relativas a 40 Compartido) que llegaron por WhatsApp, según recibidos-whatsapp.py. Si se mueve, pierde la marca."""
    global _wa
    try:
        st = ORIGEN_WHATSAPP.stat()
        firma = (st.st_mtime_ns, st.st_size, st.st_ino)
        if firma != _wa[0]:
            txt = ORIGEN_WHATSAPP.read_text(encoding="utf-8", errors="replace")
            rutas = (unicodedata.normalize("NFC", x.strip("\r").removeprefix("./")) for x in txt.split("\n"))
            _wa = (firma, frozenset(x for x in rutas if x.strip()))
    except OSError:
        return frozenset()
    return _wa[1]


def origen(rel):
    if rel.startswith("Adjuntos/"):
        return "app"
    return "whatsapp" if unicodedata.normalize("NFC", rel) in de_whatsapp() else ""


def recientes(raiz, n=20):
    fs = (e for e in recorrer(raiz) if e.is_file(follow_symlinks=False))
    top = heapq.nlargest(n, ((e.stat(follow_symlinks=False).st_mtime, e.path, e) for e in fs), key=lambda t: t[0])
    out = []
    for _, _, e in top:
        it = _ficha(raiz, e)
        out.append({"path": it["path"], "name": it["name"], "folder": it["path"].rpartition("/")[0], "size": it["size"],
                    "mtime": it["mtime"], "kind": it["kind"], "inline": it["inline"], "origen": origen(it["path"])})
    return out


def buscar(raiz, q, maximo=50):
    palabras = sin_tildes(q).split()
    if not palabras:
        return []
    hits = []
    for e in recorrer(raiz):
        nom = sin_tildes(e.name)
        if all(w in nom for w in palabras):
            it = _ficha(raiz, e)
            it["folder"] = it["path"].rpartition("/")[0]
            hits.append(it)
            if len(hits) >= 1000:
                break
    hits.sort(key=lambda x: x["mtime"], reverse=True)
    return hits[:maximo]


# ---------- mover, renombrar y papelera ----------
def nombre_valido(nombre):
    nombre = unicodedata.normalize("NFC", str(nombre or "")).strip()
    if not nombre:
        raise Fallo(400, "Escribe un nombre.")
    if "/" in nombre:
        raise Fallo(400, "El nombre no puede llevar /")
    if nombre.startswith("."):
        raise Fallo(400, "El nombre no puede empezar por un punto.")
    if oculto(nombre):
        raise Fallo(400, RESERVADO)
    if MALOS.search(nombre):
        raise Fallo(400, 'El nombre no puede llevar estos signos: \\ : * ? " < > |')
    if len(nombre.encode()) > 200:
        raise Fallo(400, "Ese nombre es demasiado largo.")
    return nombre


def nombre_libre(carpeta, nombre, es_dir=False, ignorar=None):
    """nombre, o «nombre (2).ext», «nombre (3).ext»… si ya hay uno igual (sin mirar mayúsculas ni tildes)."""
    try:
        usados = {clave(x) for x in os.listdir(carpeta) if x != ignorar}
    except FileNotFoundError:
        usados = set()
    base, ext = (nombre, "") if es_dir or "." not in nombre.lstrip(".") else (nombre[:nombre.rfind(".")], nombre[nombre.rfind("."):])
    cand, i = nombre, 2
    while clave(cand) in usados:
        cand, i = f"{base} ({i}){ext}", i + 1
    return cand


def colocar(src, carpeta, nombre):
    """Mueve src a carpeta/nombre sin pisar nunca nada; devuelve la ruta final."""
    src, carpeta = Path(src), Path(carpeta)
    with LOCK:
        for _ in range(500):
            es_dir = src.is_dir() and not src.is_symlink()
            dest = carpeta / nombre_libre(carpeta, nombre, es_dir, src.name if src.parent == carpeta else None)
            if dest == src:
                return src
            if es_dir:
                if os.path.lexists(dest):
                    continue
                os.rename(src, dest)
                return dest
            try:
                os.link(src, dest, follow_symlinks=False)   # falla si ya existe: así nunca se pisa
            except FileExistsError:
                continue
            except OSError:   # otro disco o sin enlaces duros
                if os.path.lexists(dest):
                    continue
                shutil.move(str(src), str(dest))
                return dest
            os.unlink(src)
            return dest
    raise Fallo(409, "No encuentro un nombre libre.")


def _tocable(raiz, p, papelera=False):
    raiz.escribible()
    partes = p.relative_to(raiz.real).parts
    if not partes:
        raise Fallo(400, "La carpeta principal no se puede tocar.")
    if not os.path.lexists(p):
        raise FileNotFoundError(p)
    if len(partes) == 1 and partes[0] in raiz.protegidas:
        raise Fallo(403, "Esta carpeta la usa Zazu: no se puede mover, renombrar ni tirar.")
    if partes[0] == "Adjuntos" and "Adjuntos" in raiz.protegidas:
        # lo recién adjuntado en el chat sí se puede tirar (al quitarlo del mensaje); lo demás lo usan tus notas
        if not (papelera and p.is_file() and time.time() - p.stat().st_mtime < 86400):
            raise Fallo(403, "Lo de Adjuntos no se mueve: lo usan el chat y tus notas.")


def mover(raiz, rel, destino):
    p = raiz.ruta(rel)
    _tocable(raiz, p)
    d = raiz.ruta(destino)
    if not d.is_dir():
        raise Fallo(400, "Esa carpeta de destino no existe.")
    dp = d.relative_to(raiz.real).parts
    if dp and dp[0] == "Adjuntos" and "Adjuntos" in raiz.protegidas:
        raise Fallo(403, "Adjuntos es solo para lo que adjuntas en el chat.")
    if p.is_dir() and (d == p or p in d.parents):
        raise Fallo(400, "No puedes meter una carpeta dentro de sí misma.")
    if d == p.parent:
        return raiz.rel(p)
    return raiz.rel(colocar(p, d, p.name))


def renombrar(raiz, rel, nombre):
    p = raiz.ruta(rel)
    _tocable(raiz, p)
    nombre = nombre_valido(nombre)
    ext = p.suffix if p.is_file() else ""
    nueva = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    # «Billete» → «Billete.pdf»: si no escribe una extensión conocida, se queda la de antes
    if ext and not nombre.lower().endswith(ext.lower()) and not (nueva and mimetypes.guess_type("x." + nueva)[0] or nueva in TIPOS):
        nombre = nombre_valido(nombre + ext)   # «x.syncthing» + «.tmp» también quedaría oculto
    if nombre == p.name:
        return raiz.rel(p)
    return raiz.rel(colocar(p, p.parent, nombre))


def _peso(p):
    if not p.is_dir():
        return p.stat().st_size
    total = 0
    for d, _, fs in os.walk(p):
        for f in fs:
            try:
                total += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
    return total


def _papelera_dir(papelera):
    papelera.mkdir(parents=True, exist_ok=True)
    os.chmod(papelera, 0o700)
    return papelera


def tirar(raiz, rel, papelera):
    p = raiz.ruta(rel)
    _tocable(raiz, p, papelera=True)
    with LOCK:
        pid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
        d = _papelera_dir(papelera) / pid
        (d / "f").mkdir(parents=True)
        meta = {"id": pid, "nombre": p.name, "origen": raiz.rel(p), "fecha": int(time.time()), "size": _peso(p), "dir": p.is_dir()}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        try:
            shutil.move(str(p), str(d / "f" / p.name))   # mismo disco: es un rename instantáneo
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise
    return pid


def _meta(d):
    """meta.json de una entrada de la papelera como dict, o {} si no se puede leer (lo escribe la app, pero se puede estropear)."""
    try:
        m = json.loads((d / "meta.json").read_text())
    except Exception:
        return {}
    return m if isinstance(m, dict) else {}


def _numero(x):
    try:
        x = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _fecha(d, m):
    """Cuándo se tiró (segundos): la del meta.json si es un número de verdad; si no, la de la carpeta."""
    f = _numero(m.get("fecha"))
    return int(f) if f is not None and 0 < f < time.time() + 86400 else int(d.stat().st_mtime)   # una del futuro no la libraría nunca


def papelera_items(papelera):
    out = []
    if not papelera.is_dir():
        return out
    for d in papelera.iterdir():
        if not ID_PAPELERA.fullmatch(d.name) or d.is_symlink():
            continue
        m = _meta(d)
        nombre = m.get("nombre")
        if not nombre or not isinstance(nombre, str) or nombre != Path(nombre).name:
            continue   # meta.json raro: no se enseña (y tampoco se puede restaurar)
        try:
            fecha = _fecha(d, m)
        except OSError:
            continue   # se acaba de vaciar o restaurar
        out.append({"id": d.name, "nombre": nombre, "origen": str(m.get("origen") or ""), "fecha": fecha,
                    "size": int(_numero(m.get("size")) or 0), "dir": bool(m.get("dir")), "kind": tipo(nombre, bool(m.get("dir"))),
                    "caduca": fecha + PAPELERA_DIAS * 86400})
    out.sort(key=lambda x: x["fecha"], reverse=True)
    return out


def restaurar(raiz, pid, papelera):
    raiz.escribible()
    pid = str(pid or "")
    if not ID_PAPELERA.fullmatch(pid) or not (papelera / pid / "meta.json").is_file():
        raise Fallo(404, "Eso ya no está en la papelera.")
    d = papelera / pid
    m = _meta(d)
    nombre, orig = str(m.get("nombre") or ""), str(m.get("origen") or "")
    src = d / "f" / nombre
    if not nombre or nombre != Path(nombre).name or oculto(nombre) or not os.path.lexists(src):
        raise Fallo(404, "Eso ya no está en la papelera.")
    carpeta = raiz.ruta(orig.rpartition("/")[0])   # se comprueba otra vez: el meta.json no es de fiar
    with LOCK:
        carpeta.mkdir(parents=True, exist_ok=True)   # si su carpeta ya no existe, se vuelve a crear
        dest = colocar(src, carpeta, nombre)
        shutil.rmtree(d, ignore_errors=True)
    return raiz.rel(dest)


def purgar(papelera, dias=PAPELERA_DIAS):
    """Vacía lo que lleva más de `dias` en la papelera. Devuelve cuántos quitó."""
    if not papelera.is_dir():
        return 0
    limite, n = time.time() - dias * 86400, 0
    for d in papelera.iterdir():
        if not ID_PAPELERA.fullmatch(d.name) or d.is_symlink():
            continue
        try:   # una entrada estropeada nunca para el vaciado de las demás
            if _fecha(d, _meta(d)) < limite:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        except OSError:
            continue
    return n
