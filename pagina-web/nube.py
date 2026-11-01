"""Mi nube: lo que hace un NAS además de guardar archivos. Favoritos, álbumes y enlaces para compartir (un JSON propio) y duplicados (hash, en segundo plano).

Las rutas son relativas a Compartido, como en el resto de Carpetas. Si un archivo se mueve o se borra, su favorito/álbum deja de contar
(se filtra contra el índice al leer) en vez de dar error; al mover o renombrar, mover_rutas() las reescribe para no perderlas.
El estado vive en memoria y se guarda entero (atómico, 0600) en cada cambio: solo lo escribe el hub. Los fallos de validación son A.Fallo
(código + frase en español), que server.py ya sabe contestar."""
import contextlib, hashlib, hmac, json, os, re, secrets, threading, time, unicodedata
from pathlib import Path

import archivos as A

HOME = Path(os.environ.get("HOME") or Path.home())
ESTADO = Path(os.environ.get("HUB_NUBE") or HOME / ".local/state/zazu-nube/nube.json")
MAX_FAV, MAX_ALBUM, MAX_ALBUMES, MAX_ENLACES = 100000, 20000, 200, 500
_LOCK = threading.RLock()
_E = None   # {"fav": set, "albumes": {id: {nombre, items, creado}}, "enlaces": {token: {path, creado, caduca, visitas, clave?}}}


def _vacio():
    return {"fav": set(), "albumes": {}, "enlaces": {}}


def _estado():
    """El estado en memoria; la primera vez se lee del disco. Uno estropeado se aparta (.estropeado) en vez de pisarlo."""
    global _E
    if _E is not None:
        return _E
    with _LOCK:
        if _E is None:
            try:
                d = json.loads(ESTADO.read_text(encoding="utf-8"))
                _E = {"fav": {x for x in d.get("fav", []) if isinstance(x, str)}, "albumes": dict(d.get("albumes", {})), "enlaces": dict(d.get("enlaces", {}))}
            except FileNotFoundError:
                _E = _vacio()
            except (OSError, ValueError, TypeError, AttributeError):
                with contextlib.suppress(OSError):
                    os.replace(ESTADO, ESTADO.with_name(ESTADO.name + ".estropeado"))
                _E = _vacio()
        return _E


def _guardar():
    ESTADO.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = ESTADO.with_name(ESTADO.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)   # el archivo lleva los enlaces secretos: nunca legible por otros
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(_E, f, ensure_ascii=False, default=sorted)   # los conjuntos salen como listas ordenadas
        f.flush()
        os.fsync(f.fileno())   # a disco antes del cambio de nombre: tras un corte de luz no puede quedar un nube.json vacío
    os.replace(tmp, ESTADO)


def _cambiar(f):
    """f(estado) cambia el estado en memoria (las validaciones van antes de tocar nada) y se guarda. Si no se pudo guardar, se vuelve a lo que hay en disco."""
    global _E
    with _LOCK:
        try:
            r = f(_estado())
            _guardar()
        except A.Fallo:
            raise
        except BaseException:
            _E = None
            raise
        return r


# ---------- favoritos ----------
def favoritos():
    """El conjunto de rutas favoritas. Solo para leer: cada cambio crea uno nuevo."""
    return _estado()["fav"]


def poner_fav(paths, on):
    def f(d):
        s = set(d["fav"])
        if on:
            s.update(paths)
            if len(s) > MAX_FAV:
                raise A.Fallo(400, "Hay demasiados favoritos.")
        else:
            s.difference_update(paths)
        d["fav"] = s
    _cambiar(f)


# ---------- álbumes ----------
def _nombre(n, d, excepto=None):
    if not isinstance(n, str):
        raise A.Fallo(400, "Ponle un nombre al álbum.")
    n = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", n).split())
    if not n:
        raise A.Fallo(400, "Ponle un nombre al álbum.")
    if len(n) > 60:
        raise A.Fallo(400, "El nombre es demasiado largo: 60 letras como mucho.")
    if any(i != excepto and A.clave(a["nombre"]) == A.clave(n) for i, a in d["albumes"].items()):
        raise A.Fallo(409, "Ya hay un álbum con ese nombre.")
    return n


def albumes():
    """{id: {nombre, items, creado}}. Solo para leer."""
    return dict(_estado()["albumes"])


def album(i):
    a = _estado()["albumes"].get(i)
    if not a:
        raise A.Fallo(404, "Ese álbum ya no existe.")
    return a


def album_nuevo(nombre, paths=()):
    def f(d):
        if len(d["albumes"]) >= MAX_ALBUMES:
            raise A.Fallo(400, "Ya hay demasiados álbumes.")
        nom = _nombre(nombre, d)
        i = secrets.token_hex(4)
        while i in d["albumes"]:
            i = secrets.token_hex(4)
        d["albumes"][i] = {"nombre": nom, "items": list(dict.fromkeys(paths)), "creado": int(time.time())}
        return i
    return _cambiar(f)


def album_cambiar(i, accion, nombre=None, paths=()):
    """accion: renombrar | borrar | añadir | quitar."""
    def f(d):
        a = d["albumes"].get(i)
        if not a:
            raise A.Fallo(404, "Ese álbum ya no existe.")
        if accion == "borrar":
            del d["albumes"][i]
        elif accion == "renombrar":
            a["nombre"] = _nombre(nombre, d, excepto=i)
        elif accion == "añadir":
            items = list(dict.fromkeys([*a["items"], *paths]))
            if len(items) > MAX_ALBUM:
                raise A.Fallo(400, f"Un álbum admite {MAX_ALBUM} archivos como mucho.")
            a["items"] = items
        elif accion == "quitar":
            q = set(paths)
            a["items"] = [p for p in a["items"] if p not in q]
        else:
            raise A.Fallo(400, "Acción no válida.")
    _cambiar(f)


# ---------- enlaces para compartir: UN archivo, caducan, se pueden revocar ----------
MAX_HORAS = 720   # 30 días
VENTANA, POR_IP, POR_ENLACE = 600, 5, 30   # intentos de clave: 5 por IP y 30 en total cada 10 minutos
_FALLOS, _FALLOS_LOCK = {}, threading.Lock()   # (token, ip) y (token, None) -> instantes de los intentos de clave
_SECRETO = secrets.token_bytes(32)   # firma los pases; solo en memoria: al reiniciar el hub se vuelve a escribir la clave
_KDF_SEM = threading.BoundedSemaphore(4)   # scrypt reserva 16 MB cada vez: con peticiones a la vez, como mucho 4 (64 MB)


def _kdf(clave, sal):
    clave = unicodedata.normalize("NFC", clave)   # «contraseña» es la misma venga el teclado como venga
    return hashlib.scrypt(clave.encode(), salt=sal.encode(), n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024).hex()


def crear_enlace(path, horas=24, clave=None, copia=None):
    """Enlace secreto (128 bits al azar) a un archivo. Caduca (1 h – 30 días); la clave, si hay, se guarda con scrypt.
    copia: nombre de la copia sin ubicación que se sirve en vez del original (la guarda server.py). -> (token, caduca)."""
    ahora = int(time.time())
    horas = min(max(int(horas or 24), 1), MAX_HORAS)
    tok = secrets.token_urlsafe(16)
    reg = {"path": path, "creado": ahora, "caduca": ahora + horas * 3600, "visitas": 0}
    if copia:
        reg["copia"] = copia
    if clave:
        sal = secrets.token_hex(16)
        reg["clave"] = sal + ":" + _kdf(clave, sal)

    def f(d):
        if sum(1 for v in d["enlaces"].values() if v["caduca"] > ahora) >= MAX_ENLACES:
            raise A.Fallo(400, "Ya hay demasiados enlaces activos: quita alguno.")
        d["enlaces"] = {k: v for k, v in d["enlaces"].items() if v["caduca"] > ahora - 86400}   # fuera los caducados hace más de un día
        d["enlaces"][tok] = reg
    _cambiar(f)
    return tok, reg["caduca"]


def enlace(tok):
    """El enlace vivo ({path, caduca, protegido, copia}) o None: desconocido, caducado y revocado son lo mismo."""
    e = _estado()["enlaces"].get(tok)
    if not e or e["caduca"] <= time.time():
        return None
    return {"path": e["path"], "caduca": e["caduca"], "protegido": bool(e.get("clave")), "copia": e.get("copia")}


def clave_vale(tok, clave):
    e = _estado()["enlaces"].get(tok)
    if not e or not e.get("clave") or not isinstance(clave, str):
        return False
    sal, h = e["clave"].split(":", 1)
    with _KDF_SEM:
        return hmac.compare_digest(_kdf(clave, sal), h)   # tiempo constante


def clave_intento(tok, ip):
    """Apunta un intento de clave ANTES de mirarla: con peticiones a la vez, apuntar solo los fallos (después de gastar scrypt) dejaba pasar todas.
    -> 0 si puede probar, o los segundos que faltan. Si la clave era buena, clave_acierto() devuelve el intento."""
    ahora = time.time()
    claves = ((tok, ip), (tok, None))
    with _FALLOS_LOCK:
        if len(_FALLOS) > 5000:   # que la memoria no crezca: fuera lo que ya no cuenta
            for k in [k for k, v in _FALLOS.items() if not v or ahora - v[-1] >= VENTANA]:
                del _FALLOS[k]
        vs = [[t for t in _FALLOS.get(k, ()) if ahora - t < VENTANA] for k in claves]
        for v, tope in zip(vs, (POR_IP, POR_ENLACE)):
            if len(v) >= tope:
                return int(VENTANA - (ahora - v[0])) + 1
        for k, v in zip(claves, vs):
            _FALLOS[k] = v + [ahora]
    return 0


def clave_acierto(tok, ip):
    """La clave era buena: ese intento no cuenta."""
    with _FALLOS_LOCK:
        for k in ((tok, ip), (tok, None)):
            if _FALLOS.get(k):
                _FALLOS[k].pop()


def _firma(tok, hasta):
    return hmac.new(_SECRETO, f"{tok}.{hasta}".encode(), "sha256").hexdigest()[:32]


def pase(tok, hasta):
    """Valor de la galleta que deja ver un enlace con clave ya abierta (hasta = segundos Unix)."""
    return f"{hasta}.{_firma(tok, hasta)}"


def pase_vale(tok, valor):
    hasta, _, mac = str(valor or "").partition(".")
    return hasta.isascii() and hasta.isdigit() and len(hasta) <= 12 and int(hasta) > time.time() and hmac.compare_digest(mac.encode(), _firma(tok, hasta).encode())


_ULT = [0.0]


def visita(tok):
    """Cuenta una visita. Se guarda en disco como mucho cada 30 s (o con el siguiente cambio): perder unas pocas visitas no importa."""
    with _LOCK:
        e = _estado()["enlaces"].get(tok)
        if e:
            e["visitas"] += 1
            if time.time() - _ULT[0] > 30:
                _ULT[0] = time.time()
                with contextlib.suppress(OSError):
                    _guardar()


def enlaces_de(path=None):
    ahora = time.time()
    out = [{"id": hashlib.sha256(k.encode()).hexdigest()[:8], "token": k, "path": v["path"], "creado": v["creado"], "caduca": v["caduca"],
            "visitas": v["visitas"], "clave": bool(v.get("clave"))}
           for k, v in list(_estado()["enlaces"].items()) if v["caduca"] > ahora and (path is None or v["path"] == path)]
    return sorted(out, key=lambda x: -x["creado"])


def revocar_enlace(tok):
    """Quita el enlace y devuelve su registro (o None), por si hay una copia suya que borrar."""
    return _cambiar(lambda d: d["enlaces"].pop(tok, None))


# ---------- al mover, renombrar o tirar ----------
def mover_rutas(viejo, nuevo):
    """Un archivo o carpeta cambió de sitio: sus favoritos, álbumes y enlaces lo siguen (por prefijo: lo de dentro de una carpeta también).
    nuevo=None: se tiró a la papelera; solo se quitan sus enlaces (favoritos y álbumes vuelven con él si se restaura, un enlace no resucita)."""
    pre = viejo + "/"
    afecta = lambda p: p == viejo or p.startswith(pre)

    def f(d):
        if nuevo is None:
            d["enlaces"] = {k: v for k, v in d["enlaces"].items() if not afecta(v["path"])}
            return
        sigue = lambda p: nuevo + p[len(viejo):] if afecta(p) else p
        d["fav"] = {sigue(p) for p in d["fav"]}
        for a in d["albumes"].values():
            a["items"] = list(dict.fromkeys(sigue(p) for p in a["items"]))
        for e in d["enlaces"].values():
            e["path"] = sigue(e["path"])
    _cambiar(f)


# ---------- duplicados: mismo tamaño → mismo principio y final → mismo hash entero ----------
MIN_DUP, TTL = 10240, 3600   # las miniaturas y notas de unos pocos KB no cuentan
_DUP = {"estado": "nuevo", "t": 0.0, "gen": 0, "grupos": [], "ahorro": 0, "vistos": 0, "error": ""}
_DUP_LOCK = threading.Lock()
_HASHES = {}   # (ruta, tamaño, mtime_ns, parcial) -> hash: lo que ya se leyó no se vuelve a leer en el siguiente escaneo
_COPIA = re.compile(r" \(\d+\)(\.[^./ ]*)?$")   # «foto (2).jpg»: lo que pone Carpetas cuando ya había una igual


def _sha(fp, size, parcial):
    h = hashlib.blake2b(digest_size=16)
    fd = os.open(fp, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
        if parcial:   # principio y final
            h.update(os.pread(fd, 65536, 0))
            h.update(os.pread(fd, 65536, max(size - 65536, 0)))
        else:
            leido = 0
            while b := os.read(fd, 1 << 20):
                h.update(b)
                leido += len(b)
                if leido >= 64 << 20:   # una pausa cada 64 MB: el disco y el procesador tienen más cosas que hacer
                    leido = 0
                    time.sleep(0.02)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)   # lo que se lee una sola vez no debe llenar la caché del disco
    finally:
        os.close(fd)
    return h.hexdigest()


def _escanear(root, previo):
    """-> (grupos, archivos vistos, hashes usados). Un grupo son archivos idénticos byte a byte; el primero es el que se conserva."""
    por_tam, vistos, inodos, usados = {}, 0, set(), {}
    for e in A.recorrer(root, limite=1 << 40):
        if not e.is_file(follow_symlinks=False):
            continue
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        vistos += 1
        if vistos % 500 == 0:
            _DUP["vistos"] = vistos   # para que la pantalla pueda enseñar cuánto lleva
        if st.st_size < MIN_DUP:
            continue
        if st.st_nlink > 1:   # un enlace duro (mismo archivo con dos nombres) no ahorra nada al borrarlo
            if (st.st_dev, st.st_ino) in inodos:
                continue
            inodos.add((st.st_dev, st.st_ino))
        por_tam.setdefault(st.st_size, []).append((e.path, st.st_mtime_ns))

    def hash_de(fp, tam, mt, parcial):
        k = (fp, tam, mt, parcial)
        h = usados[k] = previo.get(k) or _sha(fp, tam, parcial)
        return h

    def por_hash(lista, tam, parcial):
        out = {}
        for fp, mt in lista:
            with contextlib.suppress(OSError):   # se borró mientras tanto
                out.setdefault(hash_de(fp, tam, mt, parcial), []).append((fp, mt))
        return out

    grupos = []
    for tam, lista in por_tam.items():
        if len(lista) < 2:
            continue
        for cand in por_hash(lista, tam, True).values():
            if len(cand) < 2:
                continue
            for iguales in por_hash(cand, tam, False).values():
                if len(iguales) > 1:
                    # se conserva la que no parece una copia («… (2).jpg»), luego la más antigua, luego la de ruta más corta
                    iguales.sort(key=lambda x: (bool(_COPIA.search(os.path.basename(x[0]))), x[1], len(x[0]), x[0]))
                    grupos.append({"size": tam, "items": [{"path": root.rel(fp), "name": os.path.basename(fp), "mtime": mt // 10 ** 9, "kind": A.tipo(os.path.basename(fp))} for fp, mt in iguales]})
    grupos.sort(key=lambda g: g["size"] * (len(g["items"]) - 1), reverse=True)
    return grupos, vistos, usados


def _ahorro(grupos):
    return sum(g["size"] * (len(g["items"]) - 1) for g in grupos)


def _trabajo(root):
    global _HASHES
    with contextlib.suppress(OSError, AttributeError):
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 19)   # en Linux la prioridad es de este hilo, no del hub entero
    with _DUP_LOCK:
        gen = _DUP["gen"]
    try:
        grupos, vistos, _HASHES = _escanear(root, _HASHES)
        r = {"estado": "listo", "grupos": grupos, "vistos": vistos, "ahorro": _ahorro(grupos), "error": ""}
    except Exception as e:
        r = {"estado": "error", "grupos": [], "vistos": 0, "ahorro": 0, "error": f"{type(e).__name__}: {e}"[:200]}
    with _DUP_LOCK:
        _DUP.update(r, t=time.time() if gen == _DUP["gen"] else 0.0)   # si algo cambió mientras corría, el siguiente aviso lo rehace


def _vivos(root, g):
    items = [i for i in g["items"] if os.path.isfile(os.path.join(root.real, i["path"]))]
    return {**g, "items": items} if len(items) > 1 else None


def duplicados(root, rehacer=False):
    """El último resultado (o «calculando»). El escaneo corre en segundo plano y se rehace pasada una hora, si algo cambió o con rehacer.
    Mientras rehace, se enseña lo anterior pero solo lo que sigue existiendo."""
    with _DUP_LOCK:
        if _DUP["estado"] != "calculando" and (rehacer or _DUP["estado"] == "nuevo" or time.time() - _DUP["t"] > (60 if _DUP["estado"] == "error" else TTL)):
            _DUP.update(estado="calculando", vistos=0)
            threading.Thread(target=_trabajo, args=(root,), daemon=True).start()
        r = dict(_DUP)
    grupos, ahorro = r["grupos"], r["ahorro"]
    if r["estado"] == "calculando":
        grupos = [g for g in (_vivos(root, g) for g in grupos) if g]
        ahorro = _ahorro(grupos)
    out = {"estado": r["estado"], "grupos": grupos[:200], "total": len(grupos), "ahorro": ahorro, "vistos": r["vistos"]}
    if r["error"]:
        out["error"] = r["error"]
    return out


def olvidar_duplicados():
    """Algo cambió en Compartido: lo calculado ya no vale (la próxima consulta lo rehace; lo ya leído no se vuelve a leer)."""
    with _DUP_LOCK:
        _DUP.update(t=0.0, gen=_DUP["gen"] + 1)
