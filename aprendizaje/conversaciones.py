#!/usr/bin/env python3
"""Qué se puede aprender de tus conversaciones con Zazu, mirando solo el almacén (sin IA y sin red).

  1. Dónde hay roces: correcciones y repeticiones por asistente.
  2. Lo que pides una y otra vez: candidatos a rutina o a habilidad (que Zazu lo haga solo).
  3. Lo que Zazu dice que no puede o no ha podido: huecos de capacidad (candidatos a una herramienta nueva).
  4. De qué hablas con cada asistente.
Uso: conversaciones.py [--ver N]   (N = cuántos ejemplos enseñar en cada apartado, recortados)
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen
from modelo_texto import palabras

NO_PUEDO = re.compile(r"\b(no puedo|no he podido|no tengo (acceso|permiso|forma|manera|esa)|no me (deja|permite)|no est[aá] disponible|no consigo|no pude|fall[oó]|sin acceso)\b", re.I)


def _plano(t):
    return unicodedata.normalize("NFD", (t or "").lower()).encode("ascii", "ignore").decode()


def es_rutina(origen):
    """Rutinas y pruebas de medición: no son conversaciones tuyas."""
    o = origen or ""
    return o in ("cron", "oneshot", "tool") or o.startswith(("med-", "prueba", "medida"))


def cargar(c, con_clave=False):
    """Mensajes de conversaciones de verdad (no las rutinas automáticas): [(perfil, sesion, rol, texto, ts)] en orden.
    con_clave=True añade al final la clave del hecho (para usarla como evidencia de una lección)."""
    out = []
    for r in c.execute("SELECT clave, perfil, texto, ts, tipo, json_extract(meta,'$.sesion') s, json_extract(meta,'$.origen') o, json_extract(meta,'$.msg') m FROM hecho "
                       "WHERE fuente='hermes' AND tipo IN ('user','assistant') ORDER BY s, m"):
        if es_rutina(r["o"]):
            continue
        out.append((r["perfil"], r["s"], r["tipo"], r["texto"] or "", r["ts"]) + ((r["clave"],) if con_clave else ()))
    return out


def sin_botones(msgs, minimo=3):
    """Quita los mensajes de «usuario» que en realidad son botones de la app o pruebas: el mismo texto exacto en 3 o más conversaciones.
    → (mensajes limpios, cuántos se quitaron)."""
    sesiones = defaultdict(set)
    for m in msgs:
        if m[2] == "user":
            sesiones[_plano(m[3]).strip()].add(m[1])
    fuera = {t for t, ss in sesiones.items() if len(ss) >= minimo}
    limpios = [m for m in msgs if not (m[2] == "user" and _plano(m[3]).strip() in fuera)]
    return limpios, len(msgs) - len(limpios)


def roces(msgs, c):
    por = defaultdict(lambda: {"tuyos": 0, "correcciones": 0, "repites": 0})
    previo = {}
    for perfil, ses, rol, txt, ts in msgs:
        if rol != "user":
            continue
        por[perfil]["tuyos"] += 1
        anterior = previo.get(ses)
        if anterior and len(txt) > 15 and difflib.SequenceMatcher(None, _plano(anterior), _plano(txt)).ratio() >= 0.85:
            por[perfil]["repites"] += 1             # volviste a mandar casi lo mismo: algo no salió a la primera
        previo[ses] = txt
    for r in c.execute("SELECT perfil, COUNT(*) n FROM hecho WHERE tipo='correccion' GROUP BY 1"):
        por[r["perfil"]]["correcciones"] = r["n"]
    return por


def repetidas(msgs, minimo=3):
    """Peticiones tuyas parecidas que aparecen en varias sesiones distintas: lo que pides «cada vez»."""
    grupos = []                                     # [texto_modelo, set(sesiones), n, ejemplo, [claves si se cargaron con_clave]]
    for m in msgs:
        ses, rol, txt = m[1], m[2], m[3]
        if rol != "user" or not 20 <= len(txt) <= 300:
            continue
        t = _plano(txt)
        for g in grupos:
            if difflib.SequenceMatcher(None, g[0], t).ratio() >= 0.7:
                g[1].add(ses)
                g[2] += 1
                g[4].extend(m[5:6])
                break
        else:
            grupos.append([t, {ses}, 1, txt, list(m[5:6])])
    return sorted([g for g in grupos if len(g[1]) >= minimo], key=lambda g: -len(g[1]))


def huecos(msgs):
    """Frases de Zazu donde reconoce que no puede o no ha podido, agrupadas por las palabras que las acompañan."""
    cont, ejemplos = Counter(), {}
    for perfil, ses, rol, txt, ts in msgs:
        if rol != "assistant":
            continue
        for frase in re.split(r"(?<=[.!?\n])\s+", txt[:1500]):
            if NO_PUEDO.search(frase) and 20 <= len(frase) <= 200:
                clave = " ".join(sorted(set(palabras(frase)))[:4])
                cont[clave] += 1
                ejemplos.setdefault(clave, frase.strip())
    return [(n, ejemplos[k]) for k, n in cont.most_common()]


def temas(msgs, n=6):
    por = defaultdict(Counter)
    for perfil, ses, rol, txt, ts in msgs:
        if rol == "user":
            por[perfil].update(set(palabras(txt)))
    return {p: [w for w, _ in cnt.most_common(n)] for p, cnt in por.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", type=int, default=3)
    a = ap.parse_args(argv)
    c = almacen.conectar()
    msgs, quitados = sin_botones(cargar(c))
    print(f"(descartados {quitados} mensajes que son botones de la app o pruebas repetidas)")
    print(f"Conversaciones reales (sin rutinas): {len({m[1] for m in msgs})} sesiones · {sum(1 for m in msgs if m[2] == 'user')} mensajes tuyos · {sum(1 for m in msgs if m[2] == 'assistant')} de Zazu\n")
    print("== 1. Dónde hay roces (por cada 100 mensajes tuyos)")
    for p, d in sorted(roces(msgs, c).items(), key=lambda x: -x[1]["tuyos"]):
        if d["tuyos"] >= 5:
            print(f"  {p:12} tuyos {d['tuyos']:4d} · correcciones {100 * d['correcciones'] / d['tuyos']:4.1f} · repites lo mismo {100 * d['repites'] / d['tuyos']:4.1f}")
    print("\n== 2. Lo que pides una y otra vez (en 3 o más conversaciones distintas)")
    rep = repetidas(msgs)
    for g in rep[:a.ver]:
        print(f"  {len(g[1])} conversaciones · {g[3][:90]!r}")
    if not rep:
        print("  (nada se repite todavía lo bastante)")
    print("\n== 3. Lo que Zazu dice que no puede o no ha podido (huecos)")
    hu = huecos(msgs)
    for n, f in hu[:a.ver + 2]:
        print(f"  {n:3d} × {f[:110]!r}")
    print("\n== 4. De qué hablas con cada asistente")
    for p, ws in sorted(temas(msgs).items(), key=lambda x: -len(x[1])):
        print(f"  {p:12} {', '.join(ws)}")


if __name__ == "__main__":
    main()
