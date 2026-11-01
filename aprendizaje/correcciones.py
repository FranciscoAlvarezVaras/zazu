#!/usr/bin/env python3
"""Busca en el almacén las veces que Fran CORRIGIÓ a Zazu en una conversación («eso no», «te dije…», «otra vez…», «mejor así»).
Cada corrección es el ejemplo más valioso que hay: dice exactamente qué hizo mal el asistente y qué quería Fran.
Guarda cada una como hecho tipo «correccion» con la respuesta anterior de Zazu (recortada). No usa IA: solo reglas.
Uso: correcciones.py [--ver N]   (enseña N ejemplos recortados)
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen

# (nombre, patrón sobre el texto sin tildes y en minúsculas)
CLAVES = [
    ("te_dije", r"\b(te (lo )?(dije|he dicho|habia dicho)|ya te (lo )?(dije|he dicho))\b"),
    ("otra_vez", r"\b(otra vez|de nuevo|sigue (sin|igual|mal)|todavia (no|sigue))\b"),
    ("eso_no", r"^(no\b[ ,.!]|nop\b|que no\b)|\b(eso no|no es eso|no era eso|no es lo que|no quiero (eso|que)|no vuelvas|deja de|para ya)\b"),
    ("error", r"\b(esta mal|mal hecho|incorrecto|te equivocas|equivocad[oa]|error|no funciona|no sirve)\b"),
    ("prefiero", r"\b(prefiero|mejor (asi|que|hazlo|dime|pon)|en vez de|en lugar de)\b"),   # «cambia el modelo», «corrígelo»… son órdenes, no quejas
]
CLAVES = [(n, re.compile(p)) for n, p in CLAVES]


def plano(t):
    return unicodedata.normalize("NFD", (t or "").lower()).encode("ascii", "ignore").decode()


def tipo_de_correccion(texto):
    """Nombre de la pista que dice que es una corrección, o None. Se ignoran los mensajes larguísimos (suelen ser texto pegado) o diminutos."""
    if not texto or not 8 <= len(texto) <= 500 or "http" in texto:      # con un enlace suele ser una orden o una prueba, no una queja
        return None
    t = plano(texto).strip()
    for nombre, rx in CLAVES:
        if rx.search(t):
            return nombre
    return None


def detectar(c):
    """Rehace todas las correcciones desde cero (son un derivado: si cambian las pistas, cambian ellas). → (nuevas respecto a antes, total)."""
    antes = {r[0] for r in c.execute("SELECT clave FROM hecho WHERE tipo='correccion'")}
    c.execute("DELETE FROM hecho WHERE tipo='correccion'")
    filas = c.execute("SELECT clave, tipo, ts, perfil, texto, meta FROM hecho WHERE fuente='hermes' AND tipo IN ('user','assistant') ORDER BY json_extract(meta,'$.sesion'), json_extract(meta,'$.msg')").fetchall()
    nuevas = total = 0
    previa = {}
    for r in filas:
        meta = json.loads(r["meta"] or "{}")
        if r["tipo"] == "assistant":
            previa[meta.get("sesion")] = r["texto"]
            continue
        if meta.get("origen") in ("cron",):                 # los avisos de las rutinas los escribe una máquina, no Fran
            continue
        cue = tipo_de_correccion(r["texto"])
        if not cue:
            continue
        total += 1
        nuevas += almacen.anotar(c, "correccion:" + r["clave"], "hermes", "correccion", r["ts"], r["perfil"], r["texto"],
                                 {"pista": cue, "sesion": meta.get("sesion"), "origen": meta.get("origen"), "respuesta_previa": (previa.get(meta.get("sesion")) or "")[:400]})
    c.commit()
    ahora = {r[0] for r in c.execute("SELECT clave FROM hecho WHERE tipo='correccion'")}
    return len(ahora - antes), total


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", type=int, default=0)
    a = ap.parse_args(argv)
    c = almacen.conectar()
    nuevas, total = detectar(c)
    print(f"correcciones encontradas: {total} (nuevas {nuevas})")
    for r in c.execute("SELECT json_extract(meta,'$.pista') p, perfil, COUNT(*) n FROM hecho WHERE tipo='correccion' GROUP BY 1,2 ORDER BY n DESC LIMIT 12"):
        print(f"  {r['p']:10} {str(r['perfil']):10} {r['n']}")
    if a.ver:
        for r in c.execute("SELECT texto, json_extract(meta,'$.pista') p FROM hecho WHERE tipo='correccion' ORDER BY ts DESC LIMIT ?", (a.ver,)):
            print(f"  · [{r['p']}] {r['texto'][:150]!r}")


if __name__ == "__main__":
    main()
