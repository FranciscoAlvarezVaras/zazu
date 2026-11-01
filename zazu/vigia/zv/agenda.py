"""Vigía de agenda y plazos. NO es un segundo auditor: reutiliza revisar-zazu.py como biblioteca (inicio_fin, TIPOS_FUERA
y, si se activa, una vez al día revisar_agenda()) y añade la parte que depende de la hora: avisos de citas, «llevar:», «después:»,
tareas que vencen según el verbo, choques y cumpleaños. Solo lectura de Google. Las citas de terceros solo tienen avisos
genéricos y choques: su título y descripción nunca se interpretan como órdenes (ni llegan a ningún modelo).
Lo que YA NO hace (para no inundar a Fran): tareas gemelas de eventos (se quitó de las skills el 2026-10-21) y la auditoría
diaria de lo que ya existe en Google (apagada por defecto: agenda.auditoria_activa). Eventos iguales que llegan dos veces con
distintas mayúsculas/tildes se deduplican. Un aviso de tarea vencida sale UNA sola vez y se cierra solo cuando la tarea se
completa o cambia de fecha."""
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from . import config, registro, reglas
from .priv import limpio, seguro

TZ = config.TZ

REGLAS_TAREAS_DEFECTO = {
    "_ayuda": "Avisos por tipo de tarea con fecha. 'patron' (regex sobre el título), 'dias_antes' (0 = el mismo día), 'hora' HH:MM, "
              "'prio' 1 = importante. Se puede editar; si el archivo tiene un error se usan estos valores.",
    "reglas": [
        {"patron": r"^\W*(pagar|renovar)\b", "avisos": [{"dias_antes": 2, "hora": "09:00", "prio": 1, "pide_enlace": True}]},
        {"patron": r"^\W*llamar\b", "avisos": [{"dias_antes": 0, "hora": "10:00", "prio": 2}]},
        {"patron": r"^\W*comprar\b", "avisos": [{"dias_antes": 0, "hora": "17:30", "prio": 2}]},
        {"patron": r"^\W*(pedir cita|reservar)\b", "avisos": [{"dias_antes": 7, "hora": "09:00", "prio": 2}, {"dias_antes": 1, "hora": "09:00", "prio": 2}]},
    ]}
LLEVAR = re.compile(r"(?im)^\s*(?:llevar|preparar)\s*[:\-]\s*(.+)$")
DESPUES = re.compile(r"(?im)^\s*(?:despu[ée]s)\s*[:\-]\s*(.+)$")
RECORDAR = re.compile(r"(?im)^\s*recordar\s*[:\-]\s*(\d+)\s*([dh])\b")
VIDEO = re.compile(r"meet\.google|zoom\.us|teams\.microsoft|webex|whereby|jitsi", re.I)
CUMPLE = re.compile(r"🎂|cumple|birthday|aniversario", re.I)


def cargar_reglas_tareas():
    f = config.conf_dir() / "reglas-tareas.json"
    if not f.exists():
        try:
            config.escribir_atomico(f, json.dumps(REGLAS_TAREAS_DEFECTO, ensure_ascii=False, indent=2) + "\n")
        except OSError:
            pass
        return REGLAS_TAREAS_DEFECTO["reglas"]
    try:
        r = json.loads(f.read_text())["reglas"]
        [re.compile(x["patron"]) for x in r]
        return r
    except Exception:
        return REGLAS_TAREAS_DEFECTO["reglas"]


def rz_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("revisar_zazu", config.scripts_dir() / "revisar-zazu.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ───────── lectura (solo lectura de Google) ─────────
def _leer_cuenta(cfg, et, acc, st, ahora, rz):
    r = reglas.recoger()
    hoy = ahora.date()
    cache = st.setdefault("cache", {}).setdefault(et, {})
    ts = ahora.timestamp()
    if ts - cache.get("cals_ts", 0) > 3600 or "cals" not in cache:
        cals = r.lista(r.gog(["calendar", "calendars"], acc, intentos=1), "calendars", "items")
        cache["cals"] = [c.get("id") for c in cals if c.get("accessRole") == "owner"]
        cache["primary"] = next((c.get("id") for c in cals if c.get("primary")), None)
        cache["cals_ts"] = ts
    if ts - cache.get("listas_ts", 0) > 3600 or "listas" not in cache:
        ls = r.lista(r.gog(["tasks", "lists", "list"], acc, intentos=1), "tasklists", "items", "lists")
        cache["listas"] = [l["id"] for l in ls if l.get("title") not in cfg["agenda"]["listas_excluidas"]]
        cache["listas_ts"] = ts
    d = r.gog(["calendar", "events", "--all", f"--from={hoy - timedelta(days=1)}", f"--days={cfg['agenda']['ventana_dias']}", "--max=250", "--all-pages"], acc, intentos=1)
    eventos = []
    for e in r.lista(d, "events", "items"):
        cid = e.get("CalendarID")
        if e.get("status") == "cancelled" or (cid is not None and cid not in cache["cals"]):
            continue
        if e.get("eventType") in rz.TIPOS_FUERA and not CUMPLE.search(e.get("summary") or ""):
            continue
        ini, fin = rz.inicio_fin(e)
        if ini is None:
            continue
        if isinstance(ini, datetime):
            ini = ini.astimezone(TZ)
            fin = fin.astimezone(TZ) if isinstance(fin, datetime) else fin
        eventos.append({"c": et, "e": e, "ini": ini, "fin": fin, "todo": not isinstance(ini, datetime)})
    tareas = []
    for lid in cache["listas"]:
        for t in r.lista(r.gog(["tasks", "list", lid, "--all", "--max=100"], acc, intentos=1), "tasks", "items"):
            if t.get("status") == "needsAction" and not t.get("deleted"):
                tareas.append({**t, "_c": et})
    return eventos, tareas


# ───────── lógica pura ─────────
def _norm_titulo(t):
    """Título normalizado para deduplicar: minúsculas, sin tildes, espacios colapsados."""
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()



def es_de_fran(e):
    return bool((e.get("creator") or {}).get("self") or (e.get("organizer") or {}).get("self"))


def hay_video(e):
    return bool(e.get("hangoutLink") or e.get("conferenceData") or VIDEO.search(f"{e.get('location') or ''} {e.get('description') or ''}"))


def lugar_fisico(e):
    l = (e.get("location") or "").strip()
    return l if l and not VIDEO.search(l) and not l.lower().startswith("http") else ""


def _a(dt):
    return int(dt.timestamp())


def _dt(dia, hhmm):
    h, m = hhmm.split(":")
    return datetime(dia.year, dia.month, dia.day, int(h), int(m), tzinfo=TZ)


def _avisos_escalonados(add, ahora, dia, pasos, datos):
    """Avisos 'D-n' de un evento de día entero: cada uno vale hasta que toca el siguiente (y el último, hasta el día)."""
    pasos = sorted(pasos, key=lambda p: -p[0])
    for i, (n, hora) in enumerate(pasos):
        fin = _dt(dia - timedelta(days=pasos[i + 1][0]), pasos[i + 1][1]) if i + 1 < len(pasos) else _dt(dia, "00:00")
        if _dt(dia - timedelta(days=n), hora) <= ahora < fin:
            clave, titulo, cuando, fecha, ref, et = datos(n)
            add(clave=clave, tipo="cumple", titulo=titulo, detalle=f"{cuando} {fecha}", prio=3, ref=ref, cuenta=et, vence=_a(_dt(dia, "00:00")))


def deduplicar_eventos(eventos):
    """El mismo evento llega a veces dos veces (p. ej. importado con distintas mayúsculas/tildes: «Train to València…» y
    «Train to VALÈNCIA…»). Se colapsan por (título normalizado, inicio), que es lo que ve Fran, para no avisar dos veces."""
    vistos, unicos = set(), []
    for x in eventos:
        ini = x["ini"]
        k = (_norm_titulo(x["e"].get("summary")), ini.isoformat() if hasattr(ini, "isoformat") else str(ini))
        if k in vistos:
            continue
        vistos.add(k)
        unicos.append(x)
    return unicos


def calcular(eventos, tareas, ahora, cfg, reglas_t, rz=None):
    """→ lista de dicts de avisos (clave, tipo, titulo, …). Pura: solo depende de los datos y de `ahora`."""
    out = []
    hoy = ahora.date()
    ag = cfg["agenda"]
    eventos = deduplicar_eventos(eventos)

    def add(**k):
        k.setdefault("prio", 2); k.setdefault("programado", True); k.setdefault("noche_ok", False)
        out.append(k)

    for x in eventos:
        e, ini, fin, et = x["e"], x["ini"], x["fin"], x["c"]
        eid, titulo = e.get("id"), limpio(e.get("summary") or "(sin título)", 80)
        propio = es_de_fran(e)
        dia = ini if x["todo"] else ini.date()
        base = f"ev:{et}:{eid}:{ini.isoformat()}"
        ref = f"ev:{et}:{eid}"
        if not x["todo"]:
            fis = lugar_fisico(e)
            lead = None if (hay_video(e) and not fis) else (ag["aviso_con_lugar_min"] if fis else ag["aviso_sin_lugar_min"])
            if lead and ini - timedelta(minutes=lead) <= ahora < ini:
                mins = max(1, int((ini - ahora).total_seconds() // 60))
                add(clave=f"{base}:aviso", tipo="evento", titulo=f"{ini:%H:%M} {titulo}", detalle=f"en {mins} min" + (f" · {limpio(fis, 70)}" if fis else ""),
                    ref=ref, cuenta=et, vence=_a(ini))
        if propio:
            desc = e.get("description") or ""
            ll = LLEVAR.search(desc)
            if ll:
                lista = limpio(ll.group(1), 200)
                t1 = _dt(dia - timedelta(days=1), "20:00")
                limite1 = (ini - timedelta(hours=2)) if not x["todo"] else _dt(dia, "00:00")
                if t1 <= ahora < limite1:
                    add(clave=f"{base}:llevar1", tipo="llevar", titulo=f"Mañana{'' if x['todo'] else f' {ini:%H:%M}'}: {titulo}", detalle=f"llevar: {lista}", ref=ref, cuenta=et, vence=_a(limite1))
                if not x["todo"] and ini - timedelta(minutes=60) <= ahora < ini:
                    add(clave=f"{base}:llevar2", tipo="llevar", titulo=f"En 1 h: {titulo}", detalle=f"llevar: {lista}", ref=ref, cuenta=et, vence=_a(ini))
            dp = DESPUES.search(desc)
            if dp and not x["todo"] and isinstance(fin, datetime) and fin + timedelta(minutes=60) <= ahora < fin + timedelta(hours=3):
                add(clave=f"{base}:despues", tipo="despues", titulo=f"Después de «{titulo}»", detalle=limpio(dp.group(1), 200), ref=ref, cuenta=et, vence=_a(fin + timedelta(hours=3)))
            rc = RECORDAR.search(desc)
            if rc and not x["todo"]:
                delta = timedelta(days=int(rc.group(1))) if rc.group(2).lower() == "d" else timedelta(hours=int(rc.group(1)))
                if ini - delta <= ahora < ini:
                    add(clave=f"{base}:recordar{rc.group(1)}{rc.group(2)}", tipo="recordar", titulo=f"{ini:%d/%m %H:%M} {titulo}", detalle="recordatorio pedido", ref=ref, cuenta=et, vence=_a(ini))
        if x["todo"] and CUMPLE.search(e.get("summary") or ""):
            _avisos_escalonados(add, ahora, dia, [(7, "09:00"), (1, "09:00")], lambda n: (f"cumple:{et}:{eid}:{dia}:{n}", titulo,
                                "dentro de una semana" if n == 7 else "mañana", f"({dia:%d/%m})", ref, et))

    # tareas con fecha
    for t in tareas:
        due_s = str(t.get("due") or "")[:10]
        if not due_s:
            continue
        try:
            due = date.fromisoformat(due_s)
        except ValueError:
            continue
        titulo, et, tid = limpio(t.get("title"), 80), t["_c"], t.get("id")
        for rg in reglas_t:
            if re.search(rg["patron"], t.get("title") or "", re.I):
                for av in sorted(rg["avisos"], key=lambda v: -v["dias_antes"]):
                    n = av["dias_antes"]
                    sig = max((v for v in rg["avisos"] if v["dias_antes"] < n), key=lambda v: v["dias_antes"], default=None)   # el siguiente aviso en el tiempo
                    fin = _dt(due - timedelta(days=sig["dias_antes"]), sig["hora"]) if sig else _dt(due + timedelta(days=1), "00:00")
                    if _dt(due - timedelta(days=n), av["hora"]) <= ahora < fin:
                        tiene_url = bool(reglas.URL.search(t.get("notes") or ""))
                        falta = av.get("pide_enlace") and not tiene_url
                        add(clave=f"tarea:{et}:{tid}:{due_s}:{n}", tipo="tarea_vence", titulo=f"{titulo} ({due:%d/%m})",
                            detalle="falta el enlace de pago en la tarea" if falta else ("enlace en las notas de la tarea" if av.get("pide_enlace") else ""),
                            prio=av.get("prio", 2), ref=f"tarea:{et}:{tid}", cuenta=et, vence=_a(_dt(due + timedelta(days=1), "00:00")))
                break
        if due < hoy and reglas.recoger().P1.search(t.get("title") or "") and ahora >= _dt(hoy, "09:00"):
            # clave SIN la fecha de hoy: sale una sola vez por tarea vencida (antes una nueva cada día, que se repetía y nunca se cerraba);
            # el aviso se cierra solo en ejecutar() cuando la tarea deja de estar vencida (hecha o reprogramada).
            add(clave=f"tarea:{et}:{tid}:venc", tipo="tarea_vence", titulo=f"Vencida: {titulo} ({due:%d/%m})", detalle="sigue pendiente", prio=1,
                ref=f"tarea:{et}:{tid}", cuenta=et, vence=_a(_dt(hoy + timedelta(days=1), "00:00")))

    # choques entre citas con hora (las dos cuentas)
    margen = timedelta(minutes=ag["conflicto_margen_min"])
    # fuera los recordatorios de 15 min o menos y los «Mañana: …» (avisos del día anterior): no son citas que se pisen
    cand = sorted([x for x in eventos if not x["todo"] and isinstance(x["fin"], datetime) and x["e"].get("transparency") != "transparent"
                   and x["fin"] - x["ini"] > timedelta(minutes=20) and not re.match(r"^\W*ma[ñn]ana\b", x["e"].get("summary") or "", re.I)
                   and ahora <= x["ini"] <= ahora + timedelta(days=14)], key=lambda x: x["ini"])
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if b["ini"] >= a["fin"] + margen:
                break
            ea, eb = a["e"], b["e"]
            if ea.get("id") == eb.get("id") or (ea.get("iCalUID") and ea.get("iCalUID") == eb.get("iCalUID")) \
                    or (rz and rz.parecidos(ea.get("summary"), eb.get("summary"))):   # el mismo evento repetido es cosa de la auditoría, no un choque
                continue
            solapa = b["ini"] < a["fin"]
            la, lb = lugar_fisico(ea), lugar_fisico(eb)
            if not solapa and not (la and lb and la.lower() != lb.lower()):
                continue
            ids = "|".join(sorted([f"{a['c']}:{ea.get('id')}", f"{b['c']}:{eb.get('id')}"]))
            add(clave=f"conf:{ids}:{a['ini'].isoformat()}", tipo="conflicto", programado=False,
                titulo=f"Se pisan: {limpio(ea.get('summary'), 35)} y {limpio(eb.get('summary'), 35)}",
                detalle=f"{a['ini']:%d/%m %H:%M}–{a['fin']:%H:%M} y {b['ini']:%H:%M}–{b['fin']:%H:%M}" + ("" if solapa else " (poco margen para ir de un sitio a otro)"),
                ref=f"conf:{ids}", cuenta=a["c"], vence=_a(b["ini"]))
    return out


def ejecutar(db, cfg):
    cuentas = cfg["correo"]["cuentas"]
    ahora = config.ahora()
    rz = rz_mod()
    rz.AHORA = ahora
    st = leer_estado()
    stats = {"eventos": 0, "tareas": 0, "avisos": 0, "errores": {}, "auditoria": None}
    with ThreadPoolExecutor(max_workers=len(cuentas) or 1) as ex:
        fut = {et: ex.submit(_leer_cuenta, cfg, et, acc, st, ahora, rz) for et, acc in cuentas.items()}
    eventos, tareas = [], []
    for et in cuentas:
        try:
            ev, ta = fut[et].result()
            eventos += ev; tareas += ta
        except Exception as e:
            stats["errores"][et] = limpio(str(e), 100)
            if re.search(r"código 4\b", str(e)):
                db.alta(f"fallo:auth:{et}:{db.hoy()}", "sistema", "fallo", f"Hay que volver a autorizar Google [{et}]", prio=1,
                        detalle="La agenda de esa cuenta no se puede leer hasta que se renueve el permiso", cuenta=et)
    stats["eventos"], stats["tareas"] = len(eventos), len(tareas)
    if stats["errores"] and len(stats["errores"]) == len(cuentas):
        guardar_estado(st)
        raise RuntimeError("ninguna cuenta se pudo leer: " + "; ".join(stats["errores"].values()))
    for a in calcular(eventos, tareas, ahora, cfg, cargar_reglas_tareas(), rz):
        clave = a.pop("clave"); tipo = a.pop("tipo"); titulo = a.pop("titulo")
        id_, nuevo = db.alta(clave, "agenda", tipo, titulo, **a)
        if nuevo:
            stats["avisos"] += 1
            registro.propuesta(db, cfg, "agenda", "aviso", titulo, ref=f"aviso:{id_}", clave=f"propuso:aviso:{id_}", detalle=a.get("detalle") or None)
    vencidas = [t for t in tareas if str(t.get("due") or "")[:10] and str(t.get("due"))[:10] < str(ahora.date())]
    db.kv_set("agenda_vencidas", len(vencidas))
    stats["vencidas"] = len(vencidas)
    # cerrar los avisos de vencidas que ya no lo están: la tarea se completó (no vuelve en needsAction) o cambió de fecha
    # (ya no < hoy). Así no quedan colgados ni se repiten. Solo las cuentas que se pudieron leer, para no cerrar por un error de lectura.
    ok_ets = {et for et in cuentas if et not in stats["errores"]}
    vivas = {f"tarea:{t['_c']}:{t.get('id')}" for t in vencidas}
    cerradas = 0
    for r in db.c.execute("SELECT id, ref FROM avisos WHERE tipo='tarea_vence' AND clave LIKE '%:venc' AND estado IN ('nuevo','visto')").fetchall():
        ref = r["ref"] or ""
        et = ref.split(":")[1] if ref.count(":") >= 2 else None
        if et in ok_ets and ref not in vivas:
            db.set(r["id"], estado="hecho")
            cerradas += 1
    stats["vencidas_cerradas"] = cerradas
    # auditoría diaria (revisar-zazu como biblioteca): APAGADA por defecto (agenda.auditoria_activa). Audita lo que YA existe en Google
    # y generaba mucho ruido (52 avisos). Si Fran la activa, solo salen los hallazgos accionables (agenda.auditoria_gravedad, por defecto ERROR).
    h, m = cfg["agenda"]["auditoria_hora"].split(":")
    if cfg["agenda"].get("auditoria_activa") and (ahora.hour, ahora.minute) >= (int(h), int(m)) and db.kv_get("agenda_auditoria") != str(ahora.date()):
        db.kv_set("agenda_auditoria", ahora.date())
        graves = {g.strip().upper() for g in str(cfg["agenda"].get("auditoria_gravedad", "ERROR")).split(",") if g.strip()}
        try:
            rz.HALLAZGOS.clear(); rz.AVISOS.clear(); rz.CACHE.clear()
            rz.revisar_agenda()
            n = 0
            for hz in rz.HALLAZGOS:
                if (hz.get("grav") or "").upper() not in graves:
                    continue   # solo lo accionable y de valor claro; el resto no inunda la bandeja
                _, nuevo = db.alta(f"aud:{hz['huella']}:{ahora.isocalendar().week}", "agenda", "auditoria", hz["texto"], prio=3, silencioso=True,
                                   detalle=f"{hz['grav']} · {hz['area']}", cuenta=None)
                n += nuevo
            stats["auditoria"] = {"hallazgos": len(rz.HALLAZGOS), "nuevos": n}
        except Exception as e:
            stats["auditoria"] = {"error": type(e).__name__}
    guardar_estado(st)
    return stats


def leer_estado():
    try:
        return json.loads((config.estado_dir() / "agenda.json").read_text())
    except (OSError, ValueError):
        return {}


def guardar_estado(st):
    config.escribir_atomico(config.estado_dir() / "agenda.json", json.dumps(st))
