#!/usr/bin/env python3
"""Etiquetar desde la conversación: te enseño una tanda numerada y tú contestas «me gustan 1, 4 y 7; no 2, 3 y 5».
Así se consigue lo único que de verdad hace aprender a un modelo: tu opinión sobre ejemplos reales. (Los botones ✓/✗ de la app harán lo mismo.)

  etiquetar.py preparar [-n 25]            elige ofertas de empleo sin opinión tuya (variadas) y las enseña numeradas
  etiquetar.py registrar --si 1,4 --no 2,3 guarda tus respuestas (y marca esas ofertas como guardadas / descartadas en el buscador de empleo)
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen

LOTE = lambda: almacen.RAIZ / "lote-ofertas.json"


def _ruta_empleo():
    return Path(os.environ.get("EMPLEO_DB") or Path(os.environ.get("HOME") or Path.home()) / ".local/state/empleo-buscador/ofertas.db")


def preparar(c, n=25):
    """Una tanda variada: de las que el buscador puntúa alto a las que puntúa bajo, para que haya de las dos clases."""
    ya = {r[0] for r in c.execute("SELECT objeto FROM feedback WHERE objeto LIKE 'oferta:%'")}
    filas = []
    for r in c.execute("SELECT clave, texto, meta FROM hecho WHERE tipo='oferta' ORDER BY ts"):
        m = json.loads(r["meta"] or "{}")
        oid = r["clave"].split(":")[-1]
        if m.get("estado") in ("excluida", "descartada", "guardada", "candidatura") or f"oferta:{oid}" in ya:
            continue
        filas.append((m.get("puntos") or 0, oid, r["texto"], m))
    filas.sort(key=lambda x: -x[0])
    if len(filas) > n:                       # reparto parejo a lo largo de toda la lista ordenada por puntos
        paso = len(filas) / n
        filas = [filas[int(i * paso)] for i in range(n)]
    lote = [{"n": i, "id": oid, "texto": t, "puntos": p} for i, (p, oid, t, m) in enumerate(filas, 1)]
    almacen.RAIZ.mkdir(parents=True, exist_ok=True)
    with open(LOTE(), "w", encoding="utf-8") as f:
        json.dump(lote, f, ensure_ascii=False, indent=1)
    os.chmod(LOTE(), 0o600)
    return lote


def _numeros(s):
    return [int(x) for x in (s or "").replace(" ", "").split(",") if x.isdigit()]


def registrar(c, si, no, marcar_en_empleo=True):
    lote = {x["n"]: x for x in json.load(open(LOTE(), encoding="utf-8"))}
    malos = [n for n in si + no if n not in lote]
    if malos:
        raise SystemExit(f"Números que no están en la tanda: {malos}")
    if set(si) & set(no):
        raise SystemExit("Un número no puede ser sí y no a la vez")
    for n in si:
        almacen.dar_feedback(c, f"oferta:{lote[n]['id']}", "si", origen="fran:conversacion")
    for n in no:
        almacen.dar_feedback(c, f"oferta:{lote[n]['id']}", "no", origen="fran:conversacion")
    if marcar_en_empleo and _ruta_empleo().exists():     # que el buscador también lo sepa: lo que descartas deja de salirte
        e = sqlite3.connect(_ruta_empleo(), timeout=20)
        for ns, estado in ((si, "guardada"), (no, "descartada")):
            for n in ns:
                e.execute("UPDATE ofertas SET estado=? WHERE id=?", (estado, lote[n]["id"]))
        e.commit()
        e.close()
    return len(si), len(no)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("preparar")
    p.add_argument("-n", type=int, default=25)
    r = sp.add_parser("registrar")
    r.add_argument("--si", default="")
    r.add_argument("--no", default="")
    a = ap.parse_args(argv)
    c = almacen.conectar()
    if a.cmd == "preparar":
        for x in preparar(c, a.n):
            print(f"{x['n']:2d}. {x['texto'][:95]}   (el buscador le da {x['puntos']})")
    else:
        s, n = registrar(c, _numeros(a.si), _numeros(a.no))
        print(f"guardado: {s} sí · {n} no")


if __name__ == "__main__":
    main()
