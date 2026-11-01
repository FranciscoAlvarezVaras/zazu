"""Permisos de las personas de nivel Familia: su Zazu pide hacer algo en su Google y ella lo aprueba en su móvil.

mcp_google.py (dentro de la jaula de la invitada) deja la petición en invitadas/<perfil>/aprobaciones/<id>.json y espera.
El Hub le manda un aviso al móvil (Permitir / Rechazar) y apunta la respuesta en el mismo archivo. Si no responde a tiempo,
no se hace nada.

Esa carpeta la puede escribir la jaula, así que el Hub trata lo que hay dentro como NO fiable: el id y el texto se validan
y se recortan, no se siguen enlaces simbólicos, y se escribe en un temporal propio antes de reemplazar. Solo biblioteca estándar.
"""
import json, os, re, secrets, time
from pathlib import Path

ESPERA = 120                       # segundos que Zazu espera la respuesta (el MCP de la invitada tiene 180 de margen)
ID_OK = re.compile(r"[0-9a-f]{12}")
ESTADOS = ("pendiente", "aprobada", "rechazada", "caducada")
MAX_TEXTO = 500                    # cabe la lista de un lote («Borrar 5 tareas: «A», «B»…»)


def carpeta(raiz):
    return Path(raiz) / "aprobaciones"


def _dir_ok(c):
    return c.is_dir() and not c.is_symlink()


def _escribir(c, pid, d):
    tmp = c / f".{pid}.{secrets.token_hex(4)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, json.dumps(d, ensure_ascii=False).encode())
    finally:
        os.close(fd)
    os.replace(tmp, c / f"{pid}.json")   # reemplaza el nombre (aunque fuera un enlace), nunca escribe a través de él


def leer(raiz, pid):
    """La petición validada, o None."""
    c = carpeta(raiz)
    if not ID_OK.fullmatch(str(pid)) or not _dir_ok(c):
        return None
    try:
        fd = os.open(c / f"{pid}.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as fh:
            d = json.loads(fh.read(8192))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("id") != pid or d.get("estado") not in ESTADOS:
        return None
    try:
        creada = float(d.get("creada") or 0)
    except (TypeError, ValueError):
        return None
    return {"id": pid, "que": " ".join(str(d.get("que") or "").split())[:MAX_TEXTO], "creada": creada,
            "estado": d["estado"], "avisada": bool(d.get("avisada"))}


def pedir(raiz, que):
    """Nueva petición pendiente. Devuelve su id."""
    c = carpeta(raiz)
    c.mkdir(mode=0o700, exist_ok=True)
    if not _dir_ok(c):
        raise ValueError("carpeta de permisos no válida")
    pid = secrets.token_hex(6)
    _escribir(c, pid, {"id": pid, "que": " ".join(str(que).split())[:MAX_TEXTO], "creada": time.time(), "estado": "pendiente"})
    return pid


def responder(raiz, pid, estado):
    """Apunta la respuesta si la petición sigue pendiente y a tiempo. True si se apuntó."""
    if estado not in ESTADOS[1:]:
        return False
    e = leer(raiz, pid)
    if not e or e["estado"] != "pendiente" or (estado != "caducada" and time.time() - e["creada"] >= ESPERA):
        return False
    e["estado"] = estado
    _escribir(carpeta(raiz), pid, e)
    return True


def marcar_avisada(raiz, pid):
    e = leer(raiz, pid)
    if e and not e["avisada"]:
        e["avisada"] = True
        _escribir(carpeta(raiz), pid, e)
        return True
    return False


def esperar(raiz, pid, espera=ESPERA, paso=1.5):
    """Espera la respuesta: 'aprobada', 'rechazada' o 'caducada'."""
    fin = time.time() + espera
    while True:
        e = leer(raiz, pid)
        if not e:
            return "caducada"
        if e["estado"] != "pendiente":
            return e["estado"]
        if time.time() >= fin:
            responder(raiz, pid, "caducada")
            e = leer(raiz, pid)
            return e["estado"] if e and e["estado"] != "pendiente" else "caducada"
        time.sleep(paso)


def pendientes(raiz):
    """Las que esperan respuesta, de la más antigua a la más nueva (como mucho 20)."""
    c = carpeta(raiz)
    if not _dir_ok(c):
        return []
    ahora, out = time.time(), []
    for f in sorted(c.glob("*.json"))[:100]:
        e = leer(raiz, f.stem)
        if e and e["estado"] == "pendiente" and ahora - e["creada"] < ESPERA:
            out.append(e)
    return sorted(out, key=lambda x: x["creada"])[:20]


def limpiar(raiz, horas=48):
    """Borra las viejas (y los temporales que se quedaran a medias)."""
    c = carpeta(raiz)
    if not _dir_ok(c):
        return
    limite = time.time() - horas * 3600
    for f in c.iterdir():
        try:
            if f.is_symlink() or f.lstat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass
