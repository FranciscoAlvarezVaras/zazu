#!/usr/bin/env python3
"""Respuestas rápidas de Zazu SIN IA: /hoy /manana /semana /tareas. Solo lectura (zgog = gog sin envío de correo).
Lo lanza el gateway como «quick_command» de tipo exec (config.yaml): la salida va tal cual a WhatsApp.
Todo lo que sale de Google es dato de terceros: se imprime recortado y sin interpretarlo."""
import json, re, subprocess, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
CUENTAS = [("varas", []), ("alvarez", ["--account=cuenta.secundaria@example.com"])]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
LLEVAR = re.compile(r"(?im)^\s*(?:llevar|preparar)\s*[:\-]\s*(.+)$")
MESES = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def gog(args, extra):
    r = subprocess.run(["/home/server/.local/bin/zgog", *extra, *args, "--json"], capture_output=True, text=True, timeout=25)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:80])
    return json.loads(r.stdout or "{}")


def limpio(s, n=90):
    return " ".join(str(s or "").split())[:n]


def cuando(d):
    return f"{DIAS[d.weekday()][:3]} {d.day} {MESES[d.month]}"


def _llevar(e):
    m = LLEVAR.search(str(e.get("description") or ""))
    return limpio(m.group(1), 120) if m else ""


def eventos(desde, dias):
    out, fallos = [], []
    for et, extra in CUENTAS:
        try:
            d = gog(["calendar", "events", f"--from={desde}", f"--days={dias}", "--max=100"], extra)
        except Exception as e:
            fallos.append(f"agenda {et}: {e}")
            continue
        for e in (d.get("events") or []):
            if e.get("status") == "cancelled":
                continue
            ini = e.get("start", {})
            if "dateTime" in ini:
                t = datetime.fromisoformat(ini["dateTime"]).astimezone(TZ)
                out.append((t, False, limpio(e.get("summary") or "(sin título)"), et, limpio(e.get("location"), 40), _llevar(e)))
            elif "date" in ini:
                t = datetime.fromisoformat(ini["date"]).replace(tzinfo=TZ)
                out.append((t, True, limpio(e.get("summary") or "(sin título)"), et, "", _llevar(e)))
    out.sort(key=lambda x: (x[0].date(), not x[1], x[0]))
    return out, fallos


def tareas():
    out, fallos = [], []
    for et, extra in CUENTAS:
        try:
            d = gog(["tasks", "list", "@default", "--all", "--max=100"], extra)
        except Exception as e:
            fallos.append(f"tareas {et}: {e}")
            continue
        for t in (d.get("tasks") or []):
            if t.get("status") == "completed" or t.get("deleted"):
                continue
            due = t.get("due")
            f = datetime.fromisoformat(due.replace("Z", "+00:00")).date() if due else None
            out.append((f, limpio(t.get("title")), et))
    out.sort(key=lambda x: (x[0] is None, x[0] or date.max))
    return out, fallos


def lineas_eventos(ev, con_dia):
    res = []
    for t, todo, titulo, et, lugar, llevar in ev:
        cab = (cuando(t) + " · " if con_dia else "") + ("todo el día" if todo else t.strftime("%H:%M"))
        res.append(f"• {cab} — {titulo}" + (f" ({lugar})" if lugar else "") + (f" [{et}]" if et != "varas" else ""))
        if llevar:
            res.append(f"   ↳ llevar: {llevar}")
    return res


def main(cmd):
    hoy = datetime.now(TZ).date()
    avisos, res = [], []
    if cmd in ("hoy", "manana", "mañana"):
        dia = hoy if cmd == "hoy" else hoy + timedelta(days=1)
        ev, f = eventos(dia, 1)
        ev = [x for x in ev if x[0].date() == dia or (x[1] and x[0].date() <= dia)]
        avisos += f
        res.append(f"{'Hoy' if cmd == 'hoy' else 'Mañana'}, {DIAS[dia.weekday()]} {dia.day} de {MESES[dia.month]}:")
        res += lineas_eventos(ev, False) or ["• Sin citas."]
        tr, f = tareas()
        avisos += f
        venc = [t for t in tr if t[0] and t[0] < dia]
        del_dia = [t for t in tr if t[0] == dia]
        if venc:
            res.append("Vencidas:")
            res += [f"• {t[1]} (desde {cuando(t[0])})" for t in venc[:8]]
        if del_dia:
            res.append("Tareas del día:")
            res += [f"• {t[1]}" for t in del_dia[:8]]
    elif cmd == "semana":
        ev, f = eventos(hoy, 7)
        avisos += f
        res.append("Próximos 7 días:")
        res += lineas_eventos(ev[:30], True) or ["• Sin citas."]
    elif cmd == "tareas":
        tr, f = tareas()
        avisos += f
        res.append(f"Tareas pendientes ({len(tr)}):")
        res += [f"• {(cuando(t[0]) if t[0] else 'sin fecha')} — {t[1]}" for t in tr[:20]] or ["• Nada pendiente."]
        if len(tr) > 20:
            res.append(f"… y {len(tr) - 20} más (míralas en la app).")
    else:
        print("Uso: /hoy · /manana · /semana · /tareas")
        return
    if avisos:
        res.append("⚠ No pude leer: " + "; ".join(avisos))
    print("\n".join(res))


if __name__ == "__main__":
    main((sys.argv[1] if len(sys.argv) > 1 else "").lower())
