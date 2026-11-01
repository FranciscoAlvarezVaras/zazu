#!/usr/bin/env python3
"""«Tu día» (07:30) y «Semana» (domingo) de Zazu SIN IA: lo escribe este script con reglas fijas.
Solo lectura (Google vía zgog, vigía vía `zv`). Todo lo que viene de fuera son DATOS: se recorta y se imprime, nunca se interpreta.
Uso: zazu-dia.py tu-dia | semana"""
import importlib.util, json, re, subprocess, sys
from datetime import date, datetime, timedelta
from pathlib import Path

HOME = Path.home()
spec = importlib.util.spec_from_file_location("rapido", HOME / ".hermes/scripts/zazu-rapido.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

PRIO = re.compile(r"pag(?:ar|o)|cuota|transferi|factura|impuesto|multa|seguro|vence|plazo|renov|urgente|dgt|devoluci|reinvert|banco|hacienda|aplicar", re.I)
ZV = re.compile(r"^(\S+)\s+#\d+\s+(P[12])\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$")


def zv(*args, t=20):
    try:
        r = subprocess.run([str(HOME / ".local/bin/zv"), *args], capture_output=True, text=True, timeout=t)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def dinero():
    """Sección «Dinero» de la semana: `zv gastos resumen` (total del mes, mayores partidas, comparación con el mes anterior, renovaciones en 7 días).
    → (líneas, fallo|None). Un `zv` sin gastos (versión antigua) no da sección ni aviso; si existe y falla, se avisa con ⚠. Es texto del vigía: se recorta y se imprime."""
    try:
        r = subprocess.run([str(HOME / ".local/bin/zv"), "gastos", "resumen"], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return [], "no respondió a tiempo"
    except OSError:
        return [], "no encuentro zv"
    if r.returncode == 2 and "invalid choice" in r.stderr:
        return [], None
    if r.returncode:
        return [], f"falló (código {r.returncode})"
    return [R.limpio(l, 240) for l in r.stdout.splitlines() if l.strip()][:8], None


def renovaciones_cerca(titulos, dias=3):
    """Una sola línea si alguna suscripción renueva en `dias` días o menos (`zv suscripciones --json`). Si ya sale en la agenda de hoy o mañana
    (el evento «💳 Mañana: …»), no se repite. Cualquier fallo: sin línea (en «Tu día» no merece un aviso)."""
    try:
        d = json.loads(zv("suscripciones", "--json") or "{}")
        items = d.get("items") if isinstance(d, dict) and d.get("ok") is True and isinstance(d.get("items"), list) else []
    except ValueError:
        return ""
    texto = " ".join(t.lower() for t in titulos)
    prox = []
    for i in items:
        if not isinstance(i, dict) or i.get("estado") not in ("activa", "nueva", "solo_agenda"):
            continue
        n, nombre = i.get("dias_para_cobro"), R.limpio(i.get("nombre"), 30)
        if not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= dias or not nombre or nombre.lower() in texto:
            continue
        imp, mon = i.get("importe"), i.get("moneda")
        cuanto = f" {imp:.2f}".replace(".", ",") + (" €" if mon == "EUR" else f" {mon}" if isinstance(mon, str) and re.fullmatch(r"[A-Z]{3}", mon) else "") if isinstance(imp, (int, float)) and not isinstance(imp, bool) else ""
        prox.append((n, f"{nombre}{cuanto} ({'hoy' if n == 0 else 'mañana' if n == 1 else f'en {n} días'})"))
    return ("💳 Renueva: " + " · ".join(t for _n, t in sorted(prox)[:3])) if prox else ""


def wacli_al_dia():
    try:
        return (datetime.now().timestamp() - (HOME / ".local/state/wacli/HEARTBEAT").stat().st_mtime) < 30 * 60
    except OSError:
        return False


def avisos_vigia():
    out = []
    ok_wa = wacli_al_dia()
    for linea in zv("list", "--estado", "nuevo", "-n", "40").splitlines():
        m = ZV.match(linea)
        if m:
            if m.group(3) == "sistema" and "sincroniz" in m.group(7) and ok_wa:
                continue   # aviso viejo: wacli ya sincroniza
            out.append(f"{m.group(3)}: {R.limpio(m.group(7).split(' · ')[0], 100)}")
    return list(dict.fromkeys(out))[:5]


def capturado():
    return [l[2:].strip() for l in zv("resumen-dia").splitlines() if l.startswith("- ")][:6]


def papeles():
    """«Papeles: N por revisar» (archivador de papeles). None si no hay nada o si aún no está instalado; con ⚠ si falla."""
    script = HOME / ".hermes/scripts/archivador.py"
    if not script.exists():
        return None
    try:
        r = subprocess.run(["/usr/bin/python3", str(script), "estado", "--linea"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return "⚠ Papeles: no pude consultarlo."
    if r.returncode != 0:
        return "⚠ Papeles: no pude consultarlo."
    return " ".join(r.stdout.split())[:120] or None


def tareas_con_hechas():
    out, fallos = [], []
    for et, extra in R.CUENTAS:
        try:
            d = R.gog(["tasks", "list", "@default", "--all", "--max=100", "--show-completed", "--show-hidden"], extra)
        except Exception as e:
            fallos.append(f"tareas {et}: {e}")
            continue
        for t in (d.get("tasks") or []):
            if t.get("deleted"):
                continue
            due = t.get("due")
            f = datetime.fromisoformat(due.replace("Z", "+00:00")).date() if due else None
            hecha = datetime.fromisoformat(t["completed"].replace("Z", "+00:00")).astimezone(R.TZ).date() if t.get("completed") else None
            out.append({"fecha": f, "titulo": R.limpio(t.get("title")), "hecha": hecha, "cuenta": et})
    return out, fallos


def tu_dia():
    ahora = datetime.now(R.TZ); hoy = ahora.date(); man = hoy + timedelta(days=1)
    res = [f"Buenos días, Fran. {R.DIAS[hoy.weekday()].capitalize()} {hoy.day} de {R.MESES[hoy.month]}."]
    fallos = []
    ev, f = R.eventos(hoy, 2); fallos += f
    tr, f = tareas_con_hechas(); fallos += f
    pend = [t for t in tr if not t["hecha"]]
    pend.sort(key=lambda t: (t["fecha"] is None, t["fecha"] or date.max))
    venc = [t for t in pend if t["fecha"] and t["fecha"] < hoy]
    hoy_t = [t for t in pend if t["fecha"] == hoy]
    urg = [t for t in venc + hoy_t if PRIO.search(t["titulo"])]
    urg_ids = {id(t) for t in urg}
    if urg:
        res += ["", "Urgente (dinero y plazos):"] + [f"• {t['titulo']}" + (f" (desde {R.cuando(t['fecha'])})" if t['fecha'] < hoy else "") for t in urg[:5] if t['fecha']]
    ev_hoy = [x for x in ev if x[0].date() == hoy or (x[1] and x[0].date() <= hoy)]
    res += ["", "Hoy:"] + (R.lineas_eventos(ev_hoy, False) or ["• Sin citas."])
    res += [f"• {t['titulo']}" for t in hoy_t if id(t) not in urg_ids][:6]
    resto = [t for t in venc if id(t) not in urg_ids]
    if resto:
        res += ["", f"Vencidas ({len(resto)}):"] + [f"• {t['titulo']} (desde {R.cuando(t['fecha'])})" for t in resto[:4]]
        if len(resto) > 4:
            res.append(f"  … y {len(resto) - 4} más: /tareas")
    ev_man = [x for x in ev if x[0].date() == man]
    if ev_man:
        res += ["", "Mañana:"] + R.lineas_eventos(ev_man[:4], False)
    ren = renovaciones_cerca([x[2] for x in ev if x[0].date() in (hoy, man)])
    if ren:
        res += ["", ren]
    av = avisos_vigia()
    if av:
        res += ["", "Avisos del vigía:"] + [f"• {a}" for a in av]
    cap = capturado()
    if cap:
        res += ["", "Zazu ha visto en tus chats (nada se ha apuntado aún; mira la app):"] + [f"• {c}" for c in cap]
    pa = papeles()
    if pa:
        res += ["", pa]
    if fallos:
        res += ["", "⚠ No pude leer: " + "; ".join(fallos)]
    return res


def semana():
    hoy = datetime.now(R.TZ).date(); hace7 = hoy - timedelta(days=7)
    fallos = []
    tr, f = tareas_con_hechas(); fallos += f
    hechas = sorted([t for t in tr if t["hecha"] and t["hecha"] >= hace7], key=lambda t: t["hecha"])
    pend = sorted([t for t in tr if not t["hecha"]], key=lambda t: (t["fecha"] is None, t["fecha"] or date.max))
    venc = [t for t in pend if t["fecha"] and t["fecha"] < hoy]
    ev, f = R.eventos(hoy + timedelta(days=1), 7); fallos += f
    res = ["Tu semana, Fran.", "", f"Hechas ({len(hechas)}):"] + ([f"• {t['titulo']}" for t in hechas[:10]] or ["• Ninguna registrada."])
    res += ["", f"Pendiente ({len(pend)}; vencidas {len(venc)}):"]
    res += [f"• {t['titulo']}" + (f" (desde {R.cuando(t['fecha'])})" if t['fecha'] and t['fecha'] < hoy else "") for t in (venc + [t for t in pend if t not in venc])[:10]]
    res += ["", "La semana que viene:"] + (R.lineas_eventos(ev[:20], True) or ["• Sin citas."])
    prios = ([t for t in venc if PRIO.search(t["titulo"])] + [t for t in pend if t["fecha"] and PRIO.search(t["titulo"]) and t not in venc] + venc)
    vistos, tres = set(), []
    for t in prios:
        if t["titulo"] not in vistos:
            vistos.add(t["titulo"]); tres.append(t)
    if tres:
        res += ["", "Para empezar:"] + [f"{i}. {t['titulo']}" for i, t in enumerate(tres[:3], 1)]
    din, fallo_din = dinero()
    if din:
        res += ["", "Dinero:"] + din
    elif fallo_din:
        fallos.append("dinero: " + fallo_din)
    bandeja = list((HOME / "Cerebro/10 Bandeja").glob("*.md"))
    res += ["", f"Bandeja del Cerebro: {len(bandeja)} nota(s) sin ordenar." if bandeja else "Bandeja del Cerebro: vacía."]
    try:
        r = subprocess.run(["/usr/bin/python3", str(HOME / ".hermes/scripts/movil-ordenar.py"), "resumen"], capture_output=True, text=True, timeout=90)
        linea = (r.stdout.strip().splitlines() or [""])[-1]
        if linea:
            res.append("Móvil: " + R.limpio(linea, 160))
    except (OSError, subprocess.TimeoutExpired):
        res.append("Móvil: no respondió a tiempo.")
    if fallos:
        res += ["", "⚠ No pude leer: " + "; ".join(fallos)]
    return res


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo not in ("tu-dia", "semana"):
        sys.exit("uso: zazu-dia.py tu-dia | semana")
    print("\n".join(tu_dia() if modo == "tu-dia" else semana()))
