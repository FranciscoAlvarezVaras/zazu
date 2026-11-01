"""«Qué ha aprendido Zazu»: las lecciones del almacén de aprendizaje (~/Spirit/aprendizaje) vistas desde el Hub. SOLO Fran.

LEER: la base `datos/almacen.db` con `mode=ro`. ESCRIBIR, solo una cosa: el estado de una lección (aprobar, rechazar o volver a pensarla).
Aprobar una lección NO cambia lo que hace Zazu: la deja guardada como válida. Aplicarla (a su memoria, a una habilidad) es un paso aparte
que decide Fran. La pantalla lo dice tal cual.
El texto de las lecciones y de su evidencia sale de lo que Fran escribió; se enseña recortado y sin teléfonos, correos ni enlaces. Solo biblioteca estándar."""
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

ESTADOS = ("propuesta", "aprobada", "rechazada")
ACCIONES = {"aprobar": ("aprobada", ("propuesta",)), "rechazar": ("rechazada", ("propuesta", "aprobada")), "reabrir": ("propuesta", ("aprobada", "rechazada"))}
INVISIBLES = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠-⁯﻿]")
PRIVADO = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+|\d[\d .\-]{6,}\d")
MAX_EVIDENCIAS = 5


class AprendidoError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, {}


def _db():
    return Path(os.environ.get("HUB_APRENDIZAJE_DB") or Path(os.environ.get("HOME") or Path.home()) / "Spirit/aprendizaje/datos/almacen.db")


def _conectar(escribir=False):
    ruta = _db()
    if not ruta.is_file():
        raise AprendidoError(503, "Zazu todavía no ha guardado lecciones")
    try:
        c = sqlite3.connect(f"file:{ruta}?mode={'rw' if escribir else 'ro'}", uri=True, timeout=5)
    except sqlite3.Error:
        raise AprendidoError(503, "No pude abrir las lecciones ahora; inténtalo en un momento")
    c.row_factory = sqlite3.Row
    return c


def limpio(s, n=200):
    """Una línea, sin invisibles ni teléfonos, correos o enlaces, recortada en una palabra entera."""
    t = re.sub(r"\s+", " ", PRIVADO.sub("[…]", INVISIBLES.sub(" ", str(s or "")))).strip()
    if len(t) <= n:
        return t
    corte = t[:n].rsplit(" ", 1)[0] or t[:n]
    return corte.rstrip(" ,.;:") + "…"


def tipo_de(texto):
    """dato: algo que Zazu sabe de Fran · habilidad: algo que podría saber hacer · regla: cómo actuar."""
    t = str(texto or "").lstrip()
    if t.startswith("Recuerda"):
        return "dato"
    if t.startswith("Podría crear una habilidad"):
        return "habilidad"
    return "regla"


def _evidencias(c, claves):
    if not claves:
        return [], []
    claves = list(claves)[:40]
    q = ",".join("?" * len(claves))
    filas = c.execute(f"SELECT tipo, perfil, ts, texto FROM hecho WHERE clave IN ({q}) ORDER BY ts DESC", claves).fetchall()
    perfiles = sorted({f["perfil"] for f in filas if f["perfil"]})
    ev = [{"fecha": time.strftime("%Y-%m-%d", time.localtime(f["ts"])) if f["ts"] else "", "perfil": f["perfil"] or "", "tipo": f["tipo"],
           "texto": limpio(f["texto"], 170)} for f in filas[:MAX_EVIDENCIAS]]
    return ev, perfiles


def mapa():
    """→ {ok, resumen, lecciones}. Cada lección: id, texto, corto, tipo, estado, origen, fecha, decidida, pruebas, asistentes, evidencia."""
    with closing(_conectar()) as c:
        try:
            filas = c.execute("SELECT * FROM leccion ORDER BY id DESC").fetchall()
            out = []
            for r in filas:
                try:
                    claves = json.loads(r["evidencia"] or "[]")
                except ValueError:
                    claves = []
                ev, perfiles = _evidencias(c, claves)
                out.append({"id": r["id"], "texto": limpio(r["texto"], 600), "corto": limpio(r["texto"], 70), "tipo": tipo_de(r["texto"]), "estado": r["estado"],
                            "origen": limpio(r["origen"], 30), "fecha": time.strftime("%Y-%m-%d", time.localtime(r["ts"])) if r["ts"] else "",
                            "decidida": time.strftime("%Y-%m-%d", time.localtime(r["decidida"])) if r["decidida"] else "",
                            "pruebas": len(claves), "asistentes": perfiles, "evidencia": ev})
        except sqlite3.Error:
            raise AprendidoError(503, "No pude leer las lecciones ahora; inténtalo en un momento")
    por = lambda k: {v: sum(1 for x in out if x[k] == v) for v in sorted({x[k] for x in out})}
    return {"ok": True, "resumen": {"total": len(out), "estado": por("estado"), "tipo": por("tipo"), "origen": por("origen")}, "lecciones": out}


def decidir(id_, accion):
    """aprobar (desde propuesta), rechazar (desde propuesta o aprobada), reabrir (desde aprobada o rechazada: vuelve a «propuesta»)."""
    if accion not in ACCIONES:
        raise AprendidoError(400, "esa acción no existe")
    try:
        id_ = int(id_)
    except (TypeError, ValueError):
        raise AprendidoError(400, "esa lección no es válida")
    nuevo, desde = ACCIONES[accion]
    with closing(_conectar(escribir=True)) as c:
        r = c.execute("SELECT estado FROM leccion WHERE id = ?", (id_,)).fetchone()
        if not r:
            raise AprendidoError(404, "esa lección ya no está")
        if r["estado"] not in desde:
            raise AprendidoError(409, f"esa lección está «{r['estado']}»: no se puede {accion}")
        try:
            c.execute("UPDATE leccion SET estado = ?, decidida = ? WHERE id = ?", (nuevo, None if nuevo == "propuesta" else time.time(), id_))
            c.commit()
        except sqlite3.Error:
            raise AprendidoError(503, "No pude guardar la decisión ahora; inténtalo en un momento")
    return {"ok": True, "id": id_, "estado": nuevo}
