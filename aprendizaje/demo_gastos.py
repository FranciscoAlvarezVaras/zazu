#!/usr/bin/env python3
"""Lección práctica 1: aprender la categoría de un gasto a partir del texto del cargo. Solo lee la base del vigía.
Sirve para ver el ciclo completo de un modelo: datos con respuesta -> examen honesto -> aciertos frente a adivinar -> fallos -> qué palabras pesan."""
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo_texto import Clasificador, validar_por_grupos

RUTA = Path(os.environ.get("HOME", "~")) / ".local/state/zazu-vigia/avisos.db"


def main():
    c = sqlite3.connect(f"file:{RUTA}?mode=ro", uri=True)
    filas = c.execute("SELECT comercio, nombre, categoria FROM gasto WHERE estado='ok' AND dup_de IS NULL AND COALESCE(categoria,'') NOT IN ('', 'sin_clasificar')").fetchall()
    textos = [f"{r[0]} {r[1] or ''}" for r in filas]
    etiquetas = [r[2] for r in filas]
    grupos = [(r[0] or "").lower() for r in filas]
    print(f"Ejemplos con categoría: {len(filas)} · comercios distintos: {len(set(grupos))} · categorías: {dict(Counter(etiquetas))}")
    ac, n, base, fallos = validar_por_grupos(textos, etiquetas, grupos)
    print(f"\nExamen honesto (se aparta un comercio entero cada vez): acierta {ac}/{n} = {100 * ac / n:.0f} %")
    print(f"Adivinar siempre la categoría más frecuente: {base}/{n} = {100 * base / n:.0f} %")
    print("→ " + ("aprende algo" if ac > base else "NO supera a adivinar: aún no ha aprendido nada útil"))
    # el mismo modelo con un examen TRAMPOSO: se aparta una fila suelta, y su «gemela» (el mismo comercio) sigue en el entrenamiento
    ac2, _, _, _ = validar_por_grupos(textos, etiquetas, list(range(len(textos))))
    print(f"Con el examen tramposo (se aparta una fila suelta): {ac2}/{n} = {100 * ac2 / n:.0f} %   ← parece que sabe, pero solo recuerda comercios ya vistos")
    print("\nEjemplos donde falla (texto · real · predicho):")
    for t, real, pred in fallos[:6]:
        print(f"  {t[:40]:40} {real:14} {pred}")
    m = Clasificador().entrenar(textos, etiquetas)
    print("\nPalabras que más distinguen cada categoría (entrenado con todo):")
    for cat in sorted(set(etiquetas)):
        print(f"  {cat:14} {', '.join(m.palabras_de(cat)) or '(pocas pistas)'}")


if __name__ == "__main__":
    main()
