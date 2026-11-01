#!/usr/bin/env python3
"""Mete en el almacén lo nuevo de cada fuente. Solo LEE las fuentes (SQLite en modo solo lectura) y no usa red ni IA.
Se puede lanzar las veces que haga falta: cada hecho tiene una clave única y lo ya guardado no se duplica.

Fuentes:
  hermes   las conversaciones de Zazu y de cada asistente (lo que dices tú y lo que contesta; no el contenido bruto de las herramientas)
  vigia    avisos y registro del vigía (qué propuso, qué hiciste con ello)
  empleo   ofertas de empleo y su estado
  claude   cuántas observaciones de Claude Code hay por día y proyecto (el detalle se queda donde ECC lo guarda)
Uso: ingerir.py [--solo hermes,vigia,empleo,claude]
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen

HOME = Path(os.environ.get("HOME") or Path.home())


def _ro(ruta):
    return sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=20)


def _bases_hermes():
    out = []
    if (HOME / ".hermes/state.db").exists():
        out.append(("default", HOME / ".hermes/state.db"))
    for p in sorted(glob.glob(str(HOME / ".hermes/profiles/*/state.db"))):
        out.append((Path(p).parent.name, Path(p)))
    return out


def hermes(c):
    nuevos = total = 0
    for perfil, ruta in _bases_hermes():
        try:
            s = _ro(ruta)
            s.row_factory = sqlite3.Row
            for r in s.execute("SELECT id, source, title, model, started_at, ended_at, message_count, tool_call_count, estimated_cost_usd FROM sessions"):
                almacen.anotar(c, f"hermes:{perfil}:sesion:{r['id']}", "hermes", "sesion", r["started_at"], perfil, r["title"],
                               {"sesion": r["id"], "origen": r["source"], "modelo": r["model"], "mensajes": r["message_count"], "herramientas": r["tool_call_count"],
                                "coste_usd": r["estimated_cost_usd"], "fin": r["ended_at"]}, actualizar=True)
            ultimo = int(almacen.marca(c, f"hermes:{perfil}") or 0)
            maximo = ultimo
            for r in s.execute("SELECT m.id, m.session_id, m.role, m.content, m.tool_calls, m.timestamp, x.source FROM messages m JOIN sessions x ON x.id = m.session_id "
                               "WHERE m.id > ? AND m.role IN ('user','assistant') AND COALESCE(m.content,'') <> '' ORDER BY m.id", (ultimo,)):
                herr = []
                if r["tool_calls"]:
                    try:
                        herr = [((x.get("function") or {}).get("name") or x.get("name")) for x in json.loads(r["tool_calls"])]
                    except (ValueError, AttributeError, TypeError):
                        pass
                total += 1
                nuevos += almacen.anotar(c, f"hermes:{perfil}:{r['session_id']}:{r['id']}", "hermes", r["role"], r["timestamp"], perfil, r["content"],
                                         {"sesion": r["session_id"], "origen": r["source"], "msg": r["id"], **({"herramientas": herr} if herr else {})})
                maximo = max(maximo, r["id"])
            almacen.marca(c, f"hermes:{perfil}", maximo)
            s.close()
        except sqlite3.Error as e:
            print(f"  hermes/{perfil}: no pude leer ({type(e).__name__})")
    c.commit()
    return nuevos, total


def vigia(c):
    ruta = HOME / ".local/state/zazu-vigia/avisos.db"
    if not ruta.exists():
        return 0, 0
    nuevos = total = 0
    s = _ro(ruta)
    s.row_factory = sqlite3.Row
    for r in s.execute("SELECT id, codigo, dia, fuente, tipo, prio, titulo, estado, due, accion, creado FROM avisos"):
        total += 1
        nuevos += almacen.anotar(c, f"vigia:aviso:{r['id']}", "vigia", "aviso", r["creado"], None, r["titulo"],
                                 {"fuente": r["fuente"], "tipo": r["tipo"], "estado": r["estado"], "accion": r["accion"], "due": r["due"], "prio": r["prio"]}, actualizar=True)
    ultimo = int(almacen.marca(c, "vigia:registro") or 0)
    maximo = ultimo
    for r in s.execute("SELECT id, ts, actor, fuente, tipo, modo, titulo FROM registro WHERE id > ? ORDER BY id", (ultimo,)):
        total += 1
        nuevos += almacen.anotar(c, f"vigia:registro:{r['id']}", "vigia", "registro", r["ts"], None, r["titulo"], {"fuente": r["fuente"], "tipo": r["tipo"], "modo": r["modo"], "actor": r["actor"]})
        maximo = max(maximo, r["id"])
    almacen.marca(c, "vigia:registro", maximo)
    s.close()
    c.commit()
    return nuevos, total


def empleo(c):
    ruta = HOME / ".local/state/empleo-buscador/ofertas.db"
    if not ruta.exists():
        return 0, 0
    nuevos = total = 0
    s = _ro(ruta)
    s.row_factory = sqlite3.Row
    for r in s.execute("SELECT id, fuente, titulo, empresa, lugar, pais, remoto, fecha, pista, puntos, estado, primera_vez FROM ofertas"):
        total += 1
        nuevos += almacen.anotar(c, f"empleo:oferta:{r['id']}", "empleo", "oferta", r["primera_vez"], None, f"{r['titulo']} · {r['empresa']} · {r['lugar']}",
                                 {"fuente": r["fuente"], "pais": r["pais"], "remoto": r["remoto"], "fecha": r["fecha"], "pista": r["pista"], "puntos": r["puntos"], "estado": r["estado"]},
                                 actualizar=True)
        # lo que Fran decide en Empleo es un ejemplo para entrenar (entrenar_ofertas.py, afinar_ofertas.py); solo si cambió de opinión
        valor = {"guardada": "si", "candidatura": "si", "descartada": "no"}.get(r["estado"])
        if valor:
            antes = c.execute("SELECT valor FROM feedback WHERE objeto = ? ORDER BY id DESC LIMIT 1", (f"oferta:{r['id']}",)).fetchone()
            if not antes or antes[0] != valor:
                almacen.dar_feedback(c, f"oferta:{r['id']}", valor, origen="empleo")
    s.close()
    c.commit()
    return nuevos, total


def claude(c):
    """Solo cuenta (por proyecto y día): el detalle de cada observación se queda en ~/.local/share/ecc-homunculus."""
    base = Path(os.environ.get("CLV2_HOMUNCULUS_DIR") or HOME / ".local/share/ecc-homunculus")
    nuevos = total = 0
    for f in glob.glob(str(base / "projects/*/observations.jsonl")):
        proyecto = Path(f).parent.name
        dias = {}
        with open(f, encoding="utf-8", errors="replace") as fh:
            for linea in fh:
                m = re.search(r'"timestamp":\s*"(\d{4}-\d\d-\d\d)', linea)
                if m:
                    dias[m.group(1)] = dias.get(m.group(1), 0) + 1
        for dia, n in dias.items():
            total += 1
            ts = datetime.strptime(dia, "%Y-%m-%d").timestamp()
            nuevos += almacen.anotar(c, f"claude:obs:{proyecto}:{dia}", "claude", "observaciones", ts, None, None, {"proyecto": proyecto, "n": n}, actualizar=True)
    c.commit()
    return nuevos, total


FUENTES = {"hermes": hermes, "vigia": vigia, "empleo": empleo, "claude": claude}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--solo", default=",".join(FUENTES))
    a = ap.parse_args(argv)
    c = almacen.conectar()
    for nombre in [x for x in a.solo.split(",") if x in FUENTES]:
        try:
            nuevos, total = FUENTES[nombre](c)
            print(f"{nombre:8} leídos {total:6d} · nuevos {nuevos:6d}")
        except Exception as e:      # una fuente caída no tumba a las demás
            print(f"{nombre:8} FALLÓ: {type(e).__name__}: {str(e)[:80]}")
    n = c.execute("SELECT COUNT(*) FROM hecho").fetchone()[0]
    print(f"almacén: {n} hechos en {almacen.RAIZ / 'almacen.db'}")


if __name__ == "__main__":
    main()
