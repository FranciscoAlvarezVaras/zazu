"""La app de Android de Zazu (v2): copia sola al PC los archivos de WhatsApp y las fotos del móvil, y se actualiza sola.

Autenticación: un TOKEN DE DISPOSITIVO. La app lo pide una vez a POST /api/movil/token usando la sesión de Fran del WebView
(cookie hub_s + X-Hub, solo admin) y lo guarda en su almacén privado. Desde entonces el trabajo en segundo plano manda
«Authorization: Bearer <token>»: no caduca a los 14 días como la sesión ni depende de que el WebView siga abierto, y solo vale
para las rutas /api/movil/*. Aquí solo se guarda su sha256 (~/.config/hermes-hub/movil.json, 0600). Quitar el móvil: borrar
su entrada de ese archivo (o el archivo entero; la app pedirá otro la próxima vez que Fran la abra con la sesión iniciada).

Carpetas: todo cae en ~/Documentos/Movil-S25 con la ruta que tiene en el móvil (relativa a /sdcard), salvo WhatsApp:
    Android/media/com.whatsapp/WhatsApp/Media/<X>  →  Movil-S25/WhatsApp/<X>     (lo mismo que dejó la copia por ADB)
    DCIM/Camera/<X>                                →  Movil-S25/DCIM/Camera/<X>
Si ya hay un archivo con ese nombre y el MISMO tamaño, se da por copiado (no se sube otra vez); si el tamaño es otro,
el nuevo entra como «nombre (2).ext» y nunca se pisa nada.

Subida por trozos (Cloudflare corta cada petición a 100 MB): POST /api/movil/subir?ruta=&tam=&desde=&mtime= con un trozo
(≤ TROZO_MAX) en el cuerpo. Lo recibido se guarda en un «.<nombre>.<tam>.parte» oculto junto al destino; si se corta,
la siguiente vez se sigue desde lo que ya hay (el servidor dice cuánto tiene). Cada trozo escribe con la .parte bajo flock, así
que dos subidas a la vez del mismo archivo no se mezclan; las .parte abandonadas (otro tamaño, o más de 7 días) se borran solas.
"""
import contextlib, fcntl, hashlib, json, os, re, secrets, threading, time
from pathlib import Path

HOME = Path.home()
TOKENS = HOME / ".config/hermes-hub/movil.json"
APK = Path(os.environ.get("HUB_APK") or HOME / ".local/share/zazu-android/zazu.apk")
APK_INFO = APK.with_suffix(".json")   # lo escribe build.sh leyendo el APK con aapt2
MAX_ARCHIVO = 4 * 1024**3       # 4 GB por archivo (un vídeo largo); más es un error
TROZO_MAX = 64 * 1024**2        # por petición; la app manda 16 MB (bajo el límite de 100 MB de Cloudflare y su espera de 100 s)
MAX_TOKENS = 5
PARTE_CADUCA = 7 * 86400        # una .parte sin tocar en una semana es de una subida abandonada
WHATSAPP = "Android/media/com.whatsapp/WhatsApp/Media/"
_LOCK = threading.Lock()


def destino_base():
    return Path(os.environ.get("HUB_MOVIL_DIR") or HOME / "Documentos/Movil-S25")


# ---------- tokens de dispositivo ----------
def _leer():
    try:
        d = json.loads(TOKENS.read_text())
        return d if isinstance(d, dict) and isinstance(d.get("tokens"), dict) else {"tokens": {}}
    except Exception:
        return {"tokens": {}}


def _h(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def emitir_token(email, nombre="móvil"):
    tok = "zm_" + secrets.token_urlsafe(32)
    with _LOCK:
        d = _leer()
        d["tokens"][_h(tok)] = {"email": email, "nombre": str(nombre)[:60], "creado": int(time.time())}
        viejos = sorted(d["tokens"], key=lambda k: d["tokens"][k].get("creado", 0))
        for k in viejos[:-MAX_TOKENS]:
            del d["tokens"][k]
        TOKENS.parent.mkdir(parents=True, exist_ok=True)
        tmp = TOKENS.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(d, f, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, TOKENS)
    return tok


def email_del_token(tok):
    """El email de quien emitió el token, o None si no vale."""
    if not tok or not tok.startswith("zm_") or len(tok) > 200:
        return None
    rec = _leer()["tokens"].get(_h(tok))
    return rec.get("email") if isinstance(rec, dict) else None


# ---------- rutas ----------
def ruta_segura(rel):
    """Ruta relativa a /sdcard tal como la manda el móvil → ruta relativa dentro de Movil-S25 (str), o None si no es válida."""
    if not isinstance(rel, str) or not rel or len(rel.encode()) > 1024 or "\x00" in rel or "\\" in rel or rel.startswith("/"):
        return None
    partes = rel.split("/")
    if len(partes) > 24 or any(p in ("", ".", "..") or len(p.encode()) > 240 for p in partes):
        return None
    if partes[-1].startswith("."):
        return None   # los ocultos (.nomedia, .trashed-…, las .parte de aquí) no se copian
    if rel.startswith(WHATSAPP):
        rel = "WhatsApp/" + rel[len(WHATSAPP):]
    return rel


def destino(rel):
    """Path absoluto dentro de la base para una ruta ya validada, o None si escapa (enlaces simbólicos incluidos)."""
    base = destino_base().resolve()
    p = base / rel
    try:
        p.parent.resolve().relative_to(base)
    except ValueError:
        return None
    if p.is_symlink():
        return None
    return p


def parte_de(dest, tam):
    return dest.parent / f".{dest.name}.{tam}.parte"


def ya_esta(dest, tam):
    """¿Hay ya en el PC uno con ese nombre y ese tamaño? También cuenta un hermano «nombre (N).ext» (el que dejó colocar() cuando
    ya había otro distinto con ese nombre): si no, cada consulta diría «falta» y cada subida crearía otra copia más."""
    try:
        if dest.stat().st_size == tam and dest.is_file():
            return True
    except FileNotFoundError:
        return False   # sin el original no hay hermanos que mirar (colocar solo los crea cuando el nombre está ocupado)
    n = dest.name
    base, ext = (n[:n.rfind(".")], n[n.rfind("."):]) if "." in n.lstrip(".") else (n, "")   # como archivos.nombre_libre
    hermano = re.compile(re.escape(base) + r" \([0-9]+\)" + re.escape(ext))
    try:
        with os.scandir(dest.parent) as it:
            return any(hermano.fullmatch(e.name) and e.is_file(follow_symlinks=False) and e.stat().st_size == tam for e in it)
    except OSError:
        return False


def abrir_parte(parte, espera=60):
    """fd de la .parte con cerrojo exclusivo (flock), o None si otra subida la retiene más de «espera» s. Dos trozos a la vez
    del mismo archivo (la copia de fondo y una orden «subir») añadían los dos al final y lo corrompían. Al soltarse el cerrojo
    la .parte puede ya no ser la de esa ruta (la otra la colocó o la borró): entonces se abre la de ahora."""
    fin = time.monotonic() + espera
    while True:
        fd = os.open(parte, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > fin:
                        os.close(fd)
                        return None
                    time.sleep(0.1)
            try:
                if os.stat(parte, follow_symlinks=False).st_ino == os.fstat(fd).st_ino:
                    return fd
            except FileNotFoundError:
                pass
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)


def borrar_parte(p):
    """Borra una .parte salvo que una subida la tenga con el cerrojo puesto. True si la borró."""
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.stat(p, follow_symlinks=False).st_ino != os.fstat(fd).st_ino:
            return False   # ya es otra
        os.unlink(p)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def limpiar_partes(carpeta, nombre):
    """Tras completar «nombre»: borra sus .parte de otros tamaños (el archivo cambió a mitad de subida) y cualquier .parte
    de la carpeta sin tocar en PARTE_CADUCA. Si no, se quedaban ocultas para siempre."""
    pre, viejo = f".{nombre}.", time.time() - PARTE_CADUCA
    try:
        with os.scandir(carpeta) as it:
            for e in it:
                if not (e.name.startswith(".") and e.name.endswith(".parte")) or not e.is_file(follow_symlinks=False):
                    continue
                if (e.name.startswith(pre) and e.name[len(pre):-6].isdigit()) or e.stat(follow_symlinks=False).st_mtime < viejo:
                    borrar_parte(e.path)
    except OSError:
        pass


def estado(rel_movil, tam):
    """{"estado": "ya-estaba"} si ya hay uno igual (mismo tamaño), si no {"estado": "falta", "tengo": bytes ya recibidos}."""
    rel = ruta_segura(rel_movil)
    dest = rel and destino(rel)
    if not dest or not isinstance(tam, int) or tam < 0 or tam > MAX_ARCHIVO:
        return {"estado": "invalida"}
    if ya_esta(dest, tam):
        return {"estado": "ya-estaba"}
    parte = parte_de(dest, tam)
    tengo = parte.stat().st_size if parte.is_file() else 0
    if tengo > tam:   # sobra (de una carrera de antes): no vale; la app calcularía un trozo negativo y no avanzaría nunca
        borrar_parte(parte)
        tengo = 0
    return {"estado": "falta", "tengo": tengo}


# ---------- peticiones de Zazu (cada una la aprueba Fran en el móvil antes de que se haga) ----------
# Cola en disco. Zazu (zazu/scripts/movil-app.py) o Fran desde la web crean una petición «pendiente»; la app la recoge, enseña
# «Zazu quiere: … — motivo» con Permitir / Rechazar y SOLO si Fran pulsa Permitir avisa «aprobada», la hace y manda «hecha»/«error».
# Sin respuesta en 15 min, caduca; aprobada y sin final en 24 h, pasa a «error». Solo una lista fija de tipos (nada de comandos ni shell) y rutas bajo /storage/emulated/0.
COLA = Path(os.environ.get("HUB_MOVIL_COLA") or HOME / ".local/state/zazu-movil/peticiones.jsonl")
CADUCA = 15 * 60
CADUCA_APROBADA = 24 * 3600   # aprobada y sin «hecha»/«error» en un día: la app murió a mitad; pasa a error para que nadie espere más
RAIZ = "/storage/emulated/0"
# tipo → {argumento: clase}; hoy todos son rutas bajo /storage/emulated/0. Nunca se borra para siempre: «papelera» mueve a /sdcard/.ZazuPapelera/<fecha>/.
TIPOS = {"listar": {"ruta": "ruta"}, "tamanos": {"ruta": "ruta"}, "duplicados": {"ruta": "ruta"}, "mover": {"origen": "ruta", "destino": "ruta"},
         "crear_carpeta": {"ruta": "ruta"}, "papelera": {"ruta": "ruta"}, "subir": {"ruta": "ruta"}, "info": {"ruta": "ruta"}}


def _arg(clase, v):
    """El argumento limpio, o None si no vale."""
    return ruta_movil(v) if clase == "ruta" else None


PASOS = {"pendiente": ("aprobada", "rechazada"), "aprobada": ("hecha", "error")}   # lo demás es final


def ruta_movil(r):
    """«/sdcard/Download», «Download» o «/storage/emulated/0/Download» → «/storage/emulated/0/Download»; None si sale de ahí."""
    if not isinstance(r, str) or "\x00" in r or "\\" in r or len(r.encode()) > 1024:
        return None
    r = r.strip()
    for pre in (RAIZ, "/sdcard"):
        if r == pre or r.startswith(pre + "/"):
            r = r[len(pre):]
            break
    else:
        if r.startswith("/"):
            return None
    partes = [p for p in r.split("/") if p]
    if any(p in (".", "..") for p in partes) or len(partes) > 30:
        return None
    return RAIZ + "".join("/" + p for p in partes)


@contextlib.contextmanager
def _cola():
    """La cola entera, bloqueada (también entre procesos: el script de Zazu escribe aquí sin pasar por el servidor). Caduca lo viejo."""
    COLA.parent.mkdir(parents=True, exist_ok=True)
    with open(COLA.with_suffix(".lock"), "a") as cerrojo:
        fcntl.flock(cerrojo, fcntl.LOCK_EX)
        try:
            texto = COLA.read_text()
        except FileNotFoundError:
            texto = ""
        items = []
        for x in texto.splitlines():
            try:
                p = json.loads(x)
            except ValueError:
                continue   # una línea rota (editada a mano) se salta: antes tumbaba la cola entera
            if isinstance(p, dict) and isinstance(p.get("id"), str) and isinstance(p.get("estado"), str) and isinstance(p.get("creada"), (int, float)):
                items.append(p)
        ahora = time.time()
        for p in items:
            if p["estado"] == "pendiente" and ahora - p["creada"] > CADUCA:
                p["estado"] = "caducada"
            elif p["estado"] == "aprobada" and ahora - (p.get("cambiada") or p["creada"]) > CADUCA_APROBADA:
                p.update(estado="error", resultado={"error": "la app no respondió"}, cambiada=int(ahora))
        yield items
        nuevo = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in items[-300:])
        if nuevo == texto:
            return   # nada cambió (peticion() y peticiones() solo leen, y el script pregunta cada 3 s): no se reescribe
        tmp = COLA.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(nuevo)
        os.replace(tmp, COLA)


def crear_peticion(tipo, args, motivo):
    """Nueva petición pendiente; ValueError si el tipo o las rutas no valen."""
    if tipo == "tamaños":
        tipo = "tamanos"
    if tipo not in TIPOS:
        raise ValueError(f"tipo desconocido; vale: {', '.join(TIPOS)}")
    if not isinstance(args, dict):
        raise ValueError("args debe ser un objeto")
    if set(args) - set(TIPOS[tipo]):
        raise ValueError(f"argumentos de más para {tipo}: {', '.join(sorted(set(args) - set(TIPOS[tipo])))}")
    limpios = {}
    for k, clase in TIPOS[tipo].items():
        v = _arg(clase, args.get(k))
        if v is None:
            raise ValueError(f"«{k}» debe ser una ruta del móvil (bajo {RAIZ}, sin ..)")
        limpios[k] = v
    motivo = str(motivo or "").strip()[:300]
    if not motivo:
        raise ValueError("falta el motivo")
    p = {"id": secrets.token_hex(6), "tipo": tipo, "args": limpios, "motivo": motivo,
         "estado": "pendiente", "resultado": None, "creada": int(time.time())}
    with _cola() as items:
        items.append(p)
    return p


def peticiones(todas=False):
    with _cola() as items:
        return [dict(p, caduca=p["creada"] + CADUCA) for p in items if todas or p["estado"] == "pendiente"]


def peticion(pid):
    with _cola() as items:
        return next((p for p in items if p["id"] == pid), None)


def poner_resultado(pid, estado, resultado=None):
    """Avanza una petición (pendiente → aprobada/rechazada → hecha/error). (petición, None) o (None|petición, motivo del fallo)."""
    with _cola() as items:
        p = next((x for x in items if x["id"] == pid), None)
        if not p:
            return None, "no existe"
        if estado not in PASOS.get(p["estado"], ()):
            return p, f"ya está {p['estado']}"
        p["estado"] = estado
        if resultado is not None:
            p["resultado"] = resultado
        p["cambiada"] = int(time.time())
        return p, None


def apk_info():
    """{versionCode, versionName, sha256, tam, url} del APK publicado (build.sh deja zazu.json al lado), o None."""
    try:
        d = json.loads(APK_INFO.read_text())
        if not APK.is_file() or APK.stat().st_size != d.get("tam"):
            return None   # el json no es de este APK
        return {"versionCode": int(d["versionCode"]), "versionName": str(d["versionName"]), "sha256": d["sha256"], "tam": d["tam"], "url": "/api/movil/apk"}
    except Exception:
        return None


# ---------- avisos para la app (el WebView no admite Web Push) ----------
# Cada push que sale (vigilante.push: recordatorios, rutinas, permisos de Zazu, alertas del vigía) se deja también aquí para cada
# móvil con la app de quien lo recibe (para=None: Fran, o sea los tokens que no son de una invitada). La app los recoge con su token
# (GET /api/movil/avisos, al abrirse y cada 15 min), los enseña como notificación y los confirma (POST /api/movil/avisos/confirmar).
# Mismo tag = sustituye al anterior aún sin recoger (como el web push); como mucho MAX_AVISOS por móvil y caducan en un día.
AVISOS = Path(os.environ.get("HUB_MOVIL_AVISOS") or HOME / ".local/state/zazu-movil/avisos.json")
AVISO_CADUCA = 24 * 3600   # el mismo ttl que el web push
MAX_AVISOS = 30


@contextlib.contextmanager
def _avisos():
    """{sha256 del token: [aviso, …]} bloqueado también entre procesos (vigilante.py escribe sin pasar por el servidor).
    Fuera lo caducado y lo de móviles que ya no existen."""
    AVISOS.parent.mkdir(parents=True, exist_ok=True)
    with open(AVISOS.with_suffix(".lock"), "a") as cerrojo:
        fcntl.flock(cerrojo, fcntl.LOCK_EX)
        try:
            texto = AVISOS.read_text()
            d = json.loads(texto)
        except (OSError, ValueError):
            texto, d = "", {}
        ahora, vivos = time.time(), set(_leer()["tokens"])
        d = {k: [a for a in v if isinstance(a, dict) and a.get("x", 0) > ahora] for k, v in (d if isinstance(d, dict) else {}).items()
             if k in vivos and isinstance(v, list)}
        yield d
        nuevo = json.dumps({k: v[-MAX_AVISOS:] for k, v in d.items() if v}, ensure_ascii=False)
        if nuevo == texto:
            return
        tmp = AVISOS.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(nuevo)
        os.replace(tmp, AVISOS)


def encolar_aviso(datos, para=None, invitadas=()):
    """datos: {title, body, url, tag, aprob?} (lo mismo que va al web push). Devuelve a cuántos móviles con la app va."""
    para = (para or "").lower() or None
    invitadas = {e.lower() for e in invitadas}
    destinos = [h for h, r in _leer()["tokens"].items() if isinstance(r, dict)
                and (str(r.get("email") or "").lower() == para if para else str(r.get("email") or "").lower() not in invitadas)]
    url = str(datos.get("url") or "/?tab=inicio")
    ahora = int(time.time())
    a = {"id": secrets.token_hex(6), "t": ahora, "x": ahora + AVISO_CADUCA, "title": str(datos.get("title") or "Zazu")[:80],
         "body": str(datos.get("body") or "")[:520], "url": url if url.startswith("/") and not url.startswith("//") and len(url) <= 600 else "/?tab=inicio",
         "tag": str(datos.get("tag") or "zazu")[:64]}
    if re.fullmatch(r"[0-9a-f]{12}", str(datos.get("aprob") or "")):
        a["aprob"] = datos["aprob"]
    with _avisos() as d:
        for h in destinos:
            d[h] = [x for x in d.get(h, []) if x.get("tag") != a["tag"]] + [a]
    return len(destinos)


def avisos_de(tok):
    """Los avisos sin confirmar de ESE móvil, del más viejo al más nuevo."""
    with _avisos() as d:
        return list(d.get(_h(tok), []))


def confirmar_avisos(tok, ids):
    """Quita los avisos que la app ya enseñó. Devuelve cuántos quitó."""
    ids = {i for i in ids if isinstance(i, str)}
    with _avisos() as d:
        antes = d.get(_h(tok), [])
        d[_h(tok)] = [a for a in antes if a.get("id") not in ids]
        return len(antes) - len(d[_h(tok)])
