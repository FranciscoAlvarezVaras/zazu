#!/usr/bin/env python3
"""Qué hay en el almacén de aprendizaje y qué se puede aprender con ello hoy. Solo lee. Uso: informe.py"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen

MINIMO_POR_CLASE = 40      # con menos ejemplos de cada clase, un modelo no merece confianza


def dia(ts):
    return datetime.fromtimestamp(ts).strftime("%d/%m") if ts else "-"


def main():
    c = almacen.conectar()
    print("== Qué hay guardado")
    for r in c.execute("SELECT fuente, tipo, COUNT(*) n, MIN(ts) a, MAX(ts) b FROM hecho GROUP BY 1,2 ORDER BY 1,2"):
        print(f"  {r['fuente']:8} {r['tipo']:14} {r['n']:6d}   {dia(r['a'])} → {dia(r['b'])}")
    print("\n== Tu opinión y lo aprendido")
    fb = {r["valor"]: r["n"] for r in c.execute("SELECT valor, COUNT(*) n FROM feedback GROUP BY 1")}
    le = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM leccion GROUP BY 1")}
    print(f"  feedback  sí {fb.get('si', 0)} · no {fb.get('no', 0)}")
    print(f"  lecciones propuestas {le.get('propuesta', 0)} · aprobadas {le.get('aprobada', 0)} · rechazadas {le.get('rechazada', 0)}")

    print("\n== Etiquetas que ya existen (lo que un modelo podría aprender)")
    est = {}
    for r in c.execute("SELECT json_extract(meta,'$.tipo') t, json_extract(meta,'$.estado') e, COUNT(*) n FROM hecho WHERE tipo='aviso' GROUP BY 1,2"):
        est.setdefault(r["t"], {})[r["e"]] = r["n"]
    for t in ("item_tarea", "item_evento"):
        print(f"  avisos {t:12}", est.get(t, {}))
    ofer = {r["e"]: r["n"] for r in c.execute("SELECT json_extract(meta,'$.estado') e, COUNT(*) n FROM hecho WHERE tipo='oferta' GROUP BY 1")}
    print(f"  ofertas de empleo     {ofer}")
    cor = c.execute("SELECT COUNT(*) FROM hecho WHERE tipo='correccion'").fetchone()[0]
    print(f"  correcciones tuyas a Zazu detectadas: {cor}")

    print("\n== ¿Hay datos para entrenar ya? (hacen falta ≥ %d de cada clase)" % MINIMO_POR_CLASE)
    guard, desc = ofer.get("guardada", 0) + ofer.get("candidatura", 0), ofer.get("descartada", 0)
    filas = [("D1 ¿esta tarea de WhatsApp sirve?", fb.get("si", 0), fb.get("no", 0), "botones ✓/✗ en la app (semana 1)"),
             ("D2 ¿te interesa esta oferta?", guard, desc, "guardar/descartar ofertas")]
    for nombre, si, no, como in filas:
        ok = si >= MINIMO_POR_CLASE and no >= MINIMO_POR_CLASE
        print(f"  {'LISTO ' if ok else 'faltan'} {nombre:36} sí {si:3d} · no {no:3d}   falta: {como if not ok else '-'}")


if __name__ == "__main__":
    main()
