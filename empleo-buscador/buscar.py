#!/usr/bin/env python3
"""Buscador de ofertas de empleo de Fran, SIN IA: consulta las fuentes (fuentes/*.py), puntúa cada oferta contra perfil.yaml, quita duplicados,
guarda en SQLite y enseña las mejores. Zazu Empleo lo usa; también sirve a mano.
Uso: buscar.py [--pista dev|marketing] [--n 20] [--nuevas] [--fuentes arbeitnow,remotive] [--json] [--sin-red]
     buscar.py --guardar ID | --descartar ID | --vista ID   (ID = primeras letras del id)
"""
import argparse, concurrent.futures, importlib, json, sys, time, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
from puntuar import puntuar
from modelo import Oferta
from fuentes import FUENTES

PERFIL = Path(__file__).resolve().parent / "perfil.yaml"


def cargar_perfil():
    return yaml.safe_load(PERFIL.read_text(encoding="utf-8"))


def recoger(perfil, fuentes):
    """Lanza las fuentes en paralelo; una que falle no tumba al resto (se apunta el error)."""
    resultados, errores = [], {}
    def una(nombre):
        mod = importlib.import_module(f"fuentes.{nombre}")
        return nombre, mod.buscar(perfil)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(una, n) for n in fuentes]):
            try:
                nombre, lista = fut.result(); resultados += lista
            except Exception as e:
                errores[str(e)[:60]] = errores.get(str(e)[:60], 0) + 1
    return resultados, errores


def procesar(ofertas, perfil):
    """Puntúa, quita duplicados (misma oferta en dos fuentes: se queda la de más puntos) y descarta lo excluido."""
    mejores, motivos = {}, {}
    for o in ofertas:
        pista, puntos, m = puntuar(o, perfil)
        if not pista or puntos < perfil.get("minimo_puntos", 25):
            continue
        o.pista, o.puntos = pista, puntos
        if o.id not in mejores or puntos > mejores[o.id].puntos:
            mejores[o.id] = o; motivos[o.id] = m
    return list(mejores.values()), motivos


def tabla(filas, con_motivos=False):
    if not filas:
        print("(nada que enseñar)"); return
    for r in filas:
        print(f"{r['puntos']:3d} [{r['pista']:9s}] {r['titulo'][:60]:60s} · {r['empresa'][:28]:28s} · {r['lugar'][:24]:24s} · {r['fecha']} · {r['fuente']} · {r['id'][:6]}\n      {r['url']}")
        if con_motivos and r['motivos']:
            print(f"      {r['motivos'][:120]}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--pista", choices=["dev", "marketing"]); ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--nuevas", action="store_true", help="solo las que aparecen por primera vez hoy"); ap.add_argument("--fuentes", default=",".join(FUENTES))
    ap.add_argument("--json", action="store_true"); ap.add_argument("--sin-red", action="store_true", help="no consulta las fuentes: enseña lo guardado")
    ap.add_argument("--motivos", action="store_true"); ap.add_argument("--guardar"); ap.add_argument("--descartar"); ap.add_argument("--vista")
    a = ap.parse_args(); perfil = cargar_perfil(); c = db.conectar()
    for flag, estado in (("guardar", "guardada"), ("descartar", "descartada"), ("vista", "vista")):
        if getattr(a, flag):
            n = db.marcar(c, getattr(a, flag), estado)
            print(f"«{getattr(a, flag)}» coincide con varias ofertas: escribe más letras del id" if n < 0 else f"{n} oferta(s) → {estado}" if n else f"No encuentro ninguna oferta con el id «{getattr(a, flag)}» (usa al menos 4 letras del id)")
            return
    desde = None
    db.repuntuar(c, perfil, puntuar, Oferta)   # el perfil manda: lo guardado se reevalúa cada vez
    if not a.sin_red:
        t0 = time.time(); crudas, errores = recoger(perfil, [f for f in a.fuentes.split(",") if f])
        buenas, motivos = procesar(crudas, perfil); nuevas = db.guardar(c, buenas, motivos)
        if not a.json:
            print(f"Consultadas {len(crudas)} ofertas en {time.time()-t0:.0f} s · {len(buenas)} encajan · {nuevas} nuevas" + (f" · fallos: {errores}" if errores else ""))
        if a.nuevas: desde = time.time() - 60
    filas = [dict(r) for r in db.listar(c, pista=a.pista, minimo=perfil.get("minimo_puntos", 25), desde=desde, n=a.n, sin_estados=("descartada", "excluida"))]
    if a.json:
        print(json.dumps(filas, ensure_ascii=False, indent=1))
    else:
        tabla(filas, a.motivos)


if __name__ == "__main__":
    main()
