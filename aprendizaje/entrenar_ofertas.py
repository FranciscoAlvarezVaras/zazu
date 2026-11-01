#!/usr/bin/env python3
"""Modelo D2: aprender qué ofertas de empleo te interesan, a partir de lo que guardas y descartas (tabla feedback del almacén).
Examen honesto con pocos datos (dejando uno fuera), comparado con DOS rivales: adivinar siempre lo más frecuente y la puntuación escrita a mano del buscador.
Uso: entrenar_ofertas.py [--minimo 6]"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen
from modelo_texto import NaiveBayes, validar_dejando_uno_fuera


def texto_de(r, m):
    extra = f"pais_{m.get('pais') or ''} remoto_{m.get('remoto') or 0} pista_{m.get('pista') or ''} fuente_{m.get('fuente') or ''}"
    return f"{r['texto']} {extra}"


def cargar(c):
    """→ (textos, etiquetas 1/0, puntos del buscador) de las ofertas con opinión tuya (la última opinión manda)."""
    ops = {}
    for r in c.execute("SELECT objeto, valor FROM feedback WHERE objeto LIKE 'oferta:%' ORDER BY id"):
        ops[r["objeto"].split(":")[1]] = 1 if r["valor"] == "si" else 0
    X, y, pts = [], [], []
    for oid, v in ops.items():
        r = c.execute("SELECT texto, meta FROM hecho WHERE clave=?", (f"empleo:oferta:{oid}",)).fetchone()
        if r:
            m = json.loads(r["meta"] or "{}")
            X.append(texto_de(r, m)); y.append(v); pts.append(m.get("puntos") or 0)
    return X, y, pts


def mejor_umbral(pts, y):
    """La mejor regla del tipo «me gusta si el buscador le da ≥ t»: se le da al rival ventaja (se elige t mirando estos mismos datos)."""
    mejor = (0, 0)
    for t in sorted(set(pts)):
        ac = sum((p >= t) == bool(v) for p, v in zip(pts, y))
        if ac > mejor[0]:
            mejor = (ac, t)
    return mejor


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--minimo", type=int, default=6, help="ejemplos mínimos de cada clase para atreverse a entrenar")
    a = ap.parse_args(argv)
    c = almacen.conectar()
    X, y, pts = cargar(c)
    si, no = sum(y), len(y) - sum(y)
    print(f"Opiniones tuyas sobre ofertas: {si} sí · {no} no")
    if si < a.minimo or no < a.minimo:
        print(f"Aún no se puede entrenar: hacen falta al menos {a.minimo} de cada clase (y para fiarse, 40). Faltan {max(0, a.minimo - si)} sí y {max(0, a.minimo - no)} no.")
        return 1
    ac, n, base = validar_dejando_uno_fuera(X, y)
    ac_regla, umbral = mejor_umbral(pts, y)
    print(f"\nExamen honesto (dejando uno fuera): el modelo acierta {ac}/{n} = {100 * ac / n:.0f} %")
    print(f"  rival 1, adivinar siempre lo más frecuente: {base}/{n} = {100 * base / n:.0f} %")
    print(f"  rival 2, la puntuación a mano del buscador (con su mejor umbral, {umbral}): {ac_regla}/{n} = {100 * ac_regla / n:.0f} %")
    veredicto = "SUPERA a los dos rivales" if ac > max(base, ac_regla) else ("supera a adivinar pero no a las reglas a mano" if ac > base else "NO supera a adivinar: faltan datos")
    print("  →", veredicto)
    m = NaiveBayes().entrenar(X, y)
    k = m.palabras_clave(6)
    print(f"\nLo que le empuja a «sí»: {', '.join(k['si'])}\nLo que le empuja a «no»: {', '.join(k['no'])}")
    ruta = almacen.RAIZ / "modelo-ofertas.json"
    m.guardar(ruta); os.chmod(ruta, 0o600)
    ya = {r["objeto"] for r in c.execute("SELECT objeto FROM feedback WHERE objeto LIKE 'oferta:%'")}
    pun = []
    for r in c.execute("SELECT clave, texto, meta FROM hecho WHERE tipo='oferta'"):
        mt = json.loads(r["meta"] or "{}")
        oid = r["clave"].split(":")[-1]
        if f"oferta:{oid}" not in ya and mt.get("estado") not in ("excluida", "descartada"):
            pun.append((m.probabilidad(texto_de(r, mt)), r["texto"][:80]))
    pun.sort(reverse=True)
    print("\nLas que el modelo cree que te gustarán más (sin opinión tuya aún):")
    for p, t in pun[:5]:
        print(f"  {100 * p:3.0f} %  {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
