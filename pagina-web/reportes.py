"""«Contarle algo a Fran»: peticiones, fallos e ideas de las invitadas.

Su Zazu (avisar_a_fran en mcp_google.py, dentro de la jaula) o ella misma desde Tu espacio dejan el reporte en
invitadas/<perfil>/reportes/<id>.json. El Hub lo recoge en su hilo de avisos, lo pasa al registro de Fran y le manda un push.

Como en aprobaciones.py, esa carpeta la puede escribir la jaula: lo que hay dentro es NO fiable. Se valida el id, el tipo
y el texto (recortado), no se siguen enlaces simbólicos y se escribe en un temporal propio antes de reemplazar.
"""
import json, os, re, secrets, time
from pathlib import Path

import aprobaciones as A

TIPOS = ("peticion", "fallo", "idea")
MAX_TEXTO = 600
MAX_DIA = 20                 # reportes por persona en 24 h (que un Zazu despistado no llene el registro de Fran)
ID_OK = re.compile(r"[0-9a-f]{12}")
ESTADOS = ("nuevo", "recogido")
_NUMEROS = re.compile(r"(?:\d[ .-]?){9,}\d")   # teléfonos, cuentas, tarjetas: Fran no los necesita para entender la petición


def limpio(texto):
    return _NUMEROS.sub("[número]", " ".join(str(texto or "").split()))[:MAX_TEXTO]


def carpeta(raiz):
    return Path(raiz) / "reportes"


def leer(raiz, rid):
    """El reporte validado, o None."""
    c = carpeta(raiz)
    if not ID_OK.fullmatch(str(rid)) or not A._dir_ok(c):
        return None
    try:
        fd = os.open(c / f"{rid}.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as fh:
            d = json.loads(fh.read(8192))
        creado = float(d.get("creado"))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not isinstance(d, dict) or d.get("id") != rid or d.get("tipo") not in TIPOS or d.get("estado") not in ESTADOS:
        return None
    texto = limpio(d.get("texto"))
    if len(texto) < 2:
        return None
    return {"id": rid, "tipo": d["tipo"], "texto": texto, "creado": creado, "estado": d["estado"]}


def _todos(raiz):
    c = carpeta(raiz)
    if not A._dir_ok(c):
        return []
    return [e for e in (leer(raiz, f.stem) for f in sorted(c.glob("*.json"))[:200]) if e]


def crear(raiz, tipo, texto):
    """Nuevo reporte. Devuelve su id. ValueError si el tipo o el texto no valen o ya hay demasiados hoy."""
    if tipo not in TIPOS:
        raise ValueError("el tipo va como peticion, fallo o idea")
    texto = limpio(texto)
    if len(texto) < 2:
        raise ValueError("falta qué contarle a Fran")
    c = carpeta(raiz)
    c.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not A._dir_ok(c):
        raise ValueError("carpeta de reportes no válida")
    ahora = time.time()
    if sum(1 for e in _todos(raiz) if ahora - e["creado"] < 86400) >= MAX_DIA:
        raise ValueError("hoy ya le has contado muchas cosas a Fran; mañana puedes mandarle más")
    rid = secrets.token_hex(6)
    A._escribir(c, rid, {"id": rid, "tipo": tipo, "texto": texto, "creado": ahora, "estado": "nuevo"})
    return rid


def nuevos(raiz):
    """Los que el Hub aún no ha recogido, del más antiguo al más nuevo."""
    return sorted((e for e in _todos(raiz) if e["estado"] == "nuevo"), key=lambda e: e["creado"])


def marcar_recogido(raiz, rid):
    e = leer(raiz, rid)
    if not e or e["estado"] != "nuevo":
        return False
    e["estado"] = "recogido"
    A._escribir(carpeta(raiz), rid, e)
    return True


def limpiar(raiz, dias=7):
    """Fuera los viejos (y temporales a medias o enlaces). El Hub recoge los nuevos en segundos: a los 7 días ya no queda nada que recoger."""
    c = carpeta(raiz)
    if not A._dir_ok(c):
        return
    limite = time.time() - dias * 86400
    for f in c.iterdir():
        try:
            if f.is_symlink() or f.lstat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass
