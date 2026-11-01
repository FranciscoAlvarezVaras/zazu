#!/usr/bin/env python3
"""Informe semanal de gasto en IA, SIN IA: suma lo que Hermes apunta en sus bases de datos (sessions.estimated_cost_usd)
de todos los perfiles y lo compara con la semana anterior. Solo cifras: ningún texto de conversaciones.
Lo lanza la rutina «Gasto de la semana» (lunes 09:00, no-agent) y se puede ejecutar a mano."""
import glob, sqlite3, time
from collections import defaultdict
from pathlib import Path

HOME = Path.home()
FUENTE = {"api_server": "app", "hub": "app", "whatsapp": "WhatsApp", "cron": "rutinas", "oneshot": "terminal", "cli": "terminal", "tui": "terminal", "tool": "herramientas"}
NOMBRE = {"claude-haiku-4-5-20251001": "Haiku 4.5", "claude-haiku-5-5": "Haiku 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5"}


def sumar(desde, hasta):
    por_modelo, por_fuente, total, n = defaultdict(float), defaultdict(float), 0.0, 0
    for db in [HOME / ".hermes/state.db"] + [Path(p) for p in sorted(glob.glob(str(HOME / ".hermes/profiles/*/state.db")))]:
        try:
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            filas = c.execute("select source, model, estimated_cost_usd from sessions where started_at>=? and started_at<?", (desde, hasta)).fetchall()
            c.close()
        except sqlite3.Error:
            continue
        for fuente, modelo, coste in filas:
            coste = float(coste or 0)
            if coste <= 0:
                continue
            n += 1; total += coste
            por_modelo[NOMBRE.get(modelo, str(modelo)[:24])] += coste
            f = str(fuente or "")
            por_fuente["pruebas" if f.startswith(("prueba", "med")) else FUENTE.get(f, f or "otros")] += coste
    return total, n, por_modelo, por_fuente


def eur(d):   # dólares → euros, aproximado; la factura real llega en dólares
    return f"{d:.2f} $"


def main():
    ahora = time.time()
    semana = 7 * 86400
    tot, n, modelos, fuentes = sumar(ahora - semana, ahora)
    ant, _, _, _ = sumar(ahora - 2 * semana, ahora - semana)
    dif = tot - ant
    flecha = "↑" if dif > 0.05 else ("↓" if dif < -0.05 else "=")
    lineas = [f"💶 Gasto en IA, últimos 7 días: {eur(tot)} ({n} conversaciones) · semana anterior {eur(ant)} {flecha}"]
    if modelos:
        lineas.append("Por modelo: " + " · ".join(f"{k} {eur(v)}" for k, v in sorted(modelos.items(), key=lambda x: -x[1])))
    if fuentes:
        lineas.append("Por uso: " + " · ".join(f"{k} {eur(v)}" for k, v in sorted(fuentes.items(), key=lambda x: -x[1])))
    lineas.append(f"Al mes, a este ritmo: ~{eur(tot * 30 / 7)}. Son estimaciones de Hermes; la factura exacta está en console.anthropic.com.")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
