#!/usr/bin/env python3
"""«Ofertas del día» SIN IA: consulta las fuentes y escribe un resumen corto para WhatsApp con las mejores ofertas que aún no has visto,
por pista (dev / marketing). Lo lanza la rutina de Hermes a las 08:15.
Lo que enseña queda como «vista»: no se repite al día siguiente (antes, una ventana de 26 h contra una rutina de 24 h repetía cada oferta dos días).
Si las fuentes no se pudieron consultar, lo dice."""
import subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

AQUI = Path(__file__).resolve().parent
aviso = ""
try:   # refresca la base; antes se tiraba su salida y un fallo se veía como «0 nuevas»
    r = subprocess.run([sys.executable, str(AQUI / "buscar.py"), "--n", "1"], capture_output=True, text=True, timeout=600)
    if r.returncode:
        aviso = f"⚠️ No pude consultar las fuentes hoy (código {r.returncode}): lo de abajo es lo que ya tenía."
    elif "fallos:" in r.stdout:
        aviso = "⚠️ Alguna fuente no respondió hoy: puede que falten ofertas."
except subprocess.TimeoutExpired:
    aviso = "⚠️ La consulta de las fuentes tardó demasiado: lo de abajo es lo que ya tenía."
c = db.conectar(); desde = time.time() - 72 * 3600   # tres días: si un día no corrió, no se pierde nada (lo ya enseñado no se repite)
lineas = ["💼 Ofertas del día (las que aún no habías visto, mejores primero)"] + ([aviso] if aviso else [])
enseñadas = []
for pista, nombre in (("dev", "Datos / desarrollo"), ("marketing", "Marketing digital")):
    todas = db.listar(c, pista=pista, estado="nueva", desde=desde, minimo=25, n=500)
    filas = todas[:6]
    lineas.append(f"\n{nombre}: {len(todas)} nuevas" + (f" (te enseño las {len(filas)} mejores)" if len(todas) > len(filas) else ""))
    for r in filas:
        lineas.append(f"• {r['titulo'][:55]} · {r['empresa'][:24]} · {r['lugar'][:22] or 'remoto'} ({r['puntos']}) [{r['id'][:6]}]\n  {r['url']}")
    enseñadas += [r["id"] for r in filas]
for i in enseñadas:
    c.execute("UPDATE ofertas SET estado='vista' WHERE id=? AND estado='nueva'", (i,))
c.commit()
total = c.execute("SELECT COUNT(*) FROM ofertas WHERE estado='nueva' AND puntos>=25 AND pista!=''").fetchone()[0]
lineas.append(f"\n{total} sin mirar en total. Di «Empleo, enséñame las ofertas» en la app, o «guarda <código entre corchetes>».")
print("\n".join(lineas))
