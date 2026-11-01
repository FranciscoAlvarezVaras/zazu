#!/usr/bin/env python3
"""Mini-pruebas de regresión (sin datos reales): casos «de oro» para los dos usos de IA barata de Zazu.
  correo  → el juicio del vigía (SISTEMA_P2 de zv/correo.py): ¿requiere acción? ¿hay plazo?
  orden   → el intérprete de «Mi día» (entender.py del hub): tipos, fechas, horas.
Uso: correr.py [--modelo claude-haiku-5-5] [--solo correo|orden]. Llama al modelo por llm_worker.py (sin herramientas).
Imprime aciertos y tokens; los precios son los oficiales (por millón) para estimar el coste."""
import argparse, datetime, json, subprocess, sys, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HOME = Path.home()
WORKER = HOME / ".hermes/scripts/zazu-vigia/llm_worker.py"
PRECIO = {"claude-haiku-4-5-20251001": (1.0, 5.0), "claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0)}
sys.path.insert(0, str(HOME / ".hermes/scripts/zazu-vigia")); sys.path.insert(0, str(HOME / "hermes-hub"))
from zv import correo as zc   # noqa: E402
import entender as ent        # noqa: E402


def py():
    return str(sorted((HOME / ".hermes/tools").glob("python-*/bin/python3"))[-1])


def llamar(modelo, system, user, max_tokens):
    req = json.dumps({"system": system, "user": user, "model": modelo, "provider": "anthropic", "max_tokens": max_tokens})
    r = subprocess.run([py(), "-I", str(WORKER)], input=req, capture_output=True, text=True, timeout=120,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(HOME), "HERMES_HOME": str(HOME / ".hermes")})
    d = json.loads(r.stdout or "{}")
    u = d.get("usage") or {}
    return d.get("text", ""), (u.get("prompt_tokens") or u.get("input_tokens") or 0), (u.get("completion_tokens") or u.get("output_tokens") or 0)


def prueba_correo(modelo):
    casos = json.loads((AQUI / "casos-correo.json").read_text())
    ok = 0; tin = tout = 0; fallos = []
    m = lambda t: t.replace("<", "‹").replace(">", "›")
    for c in casos:
        user = "<datos>\nAsunto: " + m(c["asunto"]) + "\nDe: " + m(c["de"]) + "\nTexto: " + m(c["texto"]) + "\n</datos>"
        txt, i, o = llamar(modelo, zc.SISTEMA_P2, user, 250); tin += i; tout += o
        obj = zc.llm.extraer_json(txt) if hasattr(zc, "llm") else None
        req = obj.get("requiere_accion") if isinstance(obj, dict) else None
        bien = (req == c["requiere"]) and (not c.get("plazo_tiene") or bool(obj.get("plazo")))
        ok += bien
        if not bien: fallos.append(f"{c['id']} esperado={c['requiere']} obtenido={req} plazo={obj.get('plazo') if isinstance(obj, dict) else '?'}")
    return ok, len(casos), tin, tout, fallos


def prueba_orden(modelo):
    casos = json.loads((AQUI / "casos-orden.json").read_text())
    hoy = datetime.date.today(); ahora = datetime.datetime.now()   # validar() espera date, no texto
    tareas = [{"title": "comprar pilas", "id": "t1"}]; eventos = []
    ok = 0; tin = tout = 0; fallos = []
    for c in casos:
        user = ent.construir_usuario(c["orden"], ahora, eventos, tareas if c.get("con_tareas") else [])
        txt, i, o = llamar(modelo, ent.SISTEMA, user, ent.MAX_TOKENS); tin += i; tout += o
        v = ent.validar(txt, hoy, len(eventos), len(tareas) if c.get("con_tareas") else 0)
        items = (v or {}).get("items") or []
        tipos = [x.get("tipo") for x in items]
        bien = tipos == c["tipos"]
        if bien and c.get("hora"): bien = items[0].get("hora") == c["hora"]
        if bien and c.get("fecha_null"): bien = items[0].get("fecha") in (None, "")
        if bien and c.get("fecha_dia"): bien = str(items[0].get("fecha") or "").endswith(f"-{c['fecha_dia']:02d}")
        if bien and c.get("accion"): bien = items[0].get("accion") == c["accion"]
        ok += bien
        if not bien: fallos.append(f"{c['id']} esperado={c['tipos']} obtenido={tipos} {[(x.get('fecha'), x.get('hora'), x.get('accion')) for x in items][:3]}")
    return ok, len(casos), tin, tout, fallos


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--modelo", default="claude-haiku-4-5-20251001"); ap.add_argument("--solo", choices=["correo", "orden"])
    a = ap.parse_args(); pin, pout = PRECIO.get(a.modelo, (0, 0))
    t0 = time.time(); total = (0, 0, 0, 0)
    for nombre, fn in (("correo", prueba_correo), ("orden", prueba_orden)):
        if a.solo and a.solo != nombre: continue
        ok, n, tin, tout, fallos = fn(a.modelo)
        coste = tin / 1e6 * pin + tout / 1e6 * pout
        print(f"[{a.modelo}] {nombre}: {ok}/{n} aciertos · {tin} tokens entrada, {tout} salida · ~{coste:.4f} $")
        for f in fallos: print("   ✗", f)
        total = tuple(x + y for x, y in zip(total, (ok, n, tin, tout)))
    coste = total[2] / 1e6 * pin + total[3] / 1e6 * pout
    print(f"[{a.modelo}] TOTAL {total[0]}/{total[1]} · ~{coste:.4f} $ · {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
