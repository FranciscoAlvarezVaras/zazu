"""Recordatorios de las invitadas sin Google: su Zazu los apunta y, a la hora, le llega un aviso al móvil.

mcp_google.py (dentro de la jaula) escribe invitadas/<perfil>/recordatorios/<id>.json; el Hub manda el aviso cuando toca.
Como en aprobaciones.py, lo que hay en esa carpeta es NO fiable: se valida, se recorta y no se siguen enlaces.
"""
import json, os, re, secrets, time
from pathlib import Path

import aprobaciones as A

MAX = 50                    # pendientes a la vez por persona
TARDE = 6 * 3600            # si el Hub estuvo apagado más de esto, el aviso ya no se manda
ID_OK = re.compile(r"[0-9a-f]{12}")
ESTADOS = ("pendiente", "enviado", "perdido")


def carpeta(raiz):
    return Path(raiz) / "recordatorios"


def leer(raiz, rid):
    c = carpeta(raiz)
    if not ID_OK.fullmatch(str(rid)) or not A._dir_ok(c):
        return None
    try:
        fd = os.open(c / f"{rid}.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as fh:
            d = json.loads(fh.read(8192))
        cuando = float(d.get("cuando"))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not isinstance(d, dict) or d.get("id") != rid or d.get("estado") not in ESTADOS:
        return None
    return {"id": rid, "texto": " ".join(str(d.get("texto") or "").split())[:200], "cuando": cuando, "estado": d["estado"]}


def _todos(raiz):
    c = carpeta(raiz)
    if not A._dir_ok(c):
        return []
    return [e for e in (leer(raiz, f.stem) for f in sorted(c.glob("*.json"))[:200]) if e]


def pendientes(raiz):
    return sorted((e for e in _todos(raiz) if e["estado"] == "pendiente"), key=lambda e: e["cuando"])


def crear(raiz, texto, cuando):
    texto = " ".join(str(texto).split())[:200]
    if len(texto) < 2:
        raise ValueError("falta qué recordar")
    if cuando < time.time() - 60:
        raise ValueError("esa hora ya ha pasado")
    c = carpeta(raiz)
    c.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not A._dir_ok(c):
        raise ValueError("carpeta de recordatorios no válida")
    if len(pendientes(raiz)) >= MAX:
        raise ValueError(f"ya tienes {MAX} recordatorios pendientes")
    rid = secrets.token_hex(6)
    A._escribir(c, rid, {"id": rid, "texto": texto, "cuando": float(cuando), "estado": "pendiente"})
    return rid


def _poner(raiz, rid, estado):
    e = leer(raiz, rid)
    if not e or e["estado"] != "pendiente":
        return False
    e["estado"] = estado
    A._escribir(carpeta(raiz), rid, e)
    return True


def borrar(raiz, rid):
    if not leer(raiz, rid):
        return False
    try:
        (carpeta(raiz) / f"{rid}.json").unlink()
    except OSError:
        return False
    return True


def vencidos(raiz):
    """Los que toca avisar ya. Los muy atrasados se marcan como perdidos (no se manda un aviso de hace horas)."""
    ahora, out = time.time(), []
    for e in pendientes(raiz):
        if e["cuando"] > ahora:
            break
        if ahora - e["cuando"] > TARDE:
            _poner(raiz, e["id"], "perdido")
        else:
            out.append(e)
    return out


def marcar_enviado(raiz, rid):
    return _poner(raiz, rid, "enviado")
