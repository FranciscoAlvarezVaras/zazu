"""Panel de tu día: UNA llamada (GET /api/panel) que compone lo urgente de hoy a partir de varias fuentes.

Reglas: (1) cada fuente se pide en paralelo, con caché propia, un único refresco en vuelo y un tope de espera de 3 s en
total; (2) un fallo o un retraso de una fuente solo estropea SU sección ({ok:false, error}); el resto sale entero;
(3) nunca se enseña «nada» cuando en realidad falló: el error se dice; (4) nada de contenido de mensajes: los avisos del
vigía ya vienen con etiquetas cortas y tachadas. Solo biblioteca estándar.
"""
import os, re, threading, time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import avisos, gastos

TZ = ZoneInfo("Europe/Madrid")
ESPERA_S = float(os.environ.get("HUB_PANEL_ESPERA", "3"))        # tope total de espera por las fuentes
CACHE_S = float(os.environ.get("HUB_PANEL_CACHE", "5"))          # caché de la respuesta entera
REBOTE_S = float(os.environ.get("HUB_PANEL_REBOTE", "2"))        # ?fresco=1 no repite fuentes más de una vez cada tanto
OBSOLETO_S = 600                                                 # un dato más viejo que esto no se enseña si la fuente se atasca
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="panel")
INNER = ThreadPoolExecutor(max_workers=8, thread_name_prefix="panel-cuenta")
E = None


def configurar(gog, cuentas_con, etiqueta, lista, wa=None):
    """El servidor inyecta sus ayudantes de Google (gog, cuentas_con, etiqueta, _list)."""
    global E
    E = SimpleNamespace(gog=gog, cuentas_con=cuentas_con, etiqueta=etiqueta, lista=lista, wa=wa)


def limpio(s, n=160):
    s = re.sub(r"[\x00-\x1f\x7f​-‏‪-‮]+", " ", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def _msg(e):
    """Mensaje para Fran: nunca la salida de gog ni rutas del disco."""
    if isinstance(e, avisos.AvisoError):
        return e.msg
    if isinstance(e, OSError) and getattr(e, "errno", None):
        return "No pude leer el archivo"
    if isinstance(e, (RuntimeError, FileNotFoundError, PermissionError)):
        return limpio(e, 120)
    if isinstance(e, TimeoutError) or type(e).__name__ == "TimeoutExpired":
        return "Tardó demasiado en contestar"
    return f"Error inesperado ({type(e).__name__})"


class Fuente:
    """Una fuente con caché (ttl), un único refresco en vuelo y espera limitada. Los datos viejos solo se enseñan, marcados
    como `obsoleto`, si la fuente se atasca; un error real se dice como error."""
    def __init__(self, nombre, ttl, fn, ttl_error=15):
        self.nombre, self.ttl, self.fn, self.ttl_error = nombre, ttl, fn, ttl_error
        self.lock = threading.Lock()
        self.rec = None          # último resultado (ok o error)
        self.bueno = None        # último resultado correcto
        self.fut = None

    def iniciar(self, fresco=False):
        with self.lock:
            r = self.rec
            if r:
                edad = time.time() - r["t"]
                if (not fresco and edad < (self.ttl if r["ok"] else self.ttl_error)) or (fresco and edad < REBOTE_S):
                    return None
            if self.fut is None or self.fut.done():
                self.fut = POOL.submit(self._cargar)
            return self.fut

    def _cargar(self):
        try:
            rec = {"ok": True, "v": self.fn(), "t": time.time()}
        except Exception as e:                                   # una fuente que falla no tumba a las demás
            rec = {"ok": False, "error": _msg(e), "t": time.time()}
        with self.lock:
            self.rec = rec
            if rec["ok"]:
                self.bueno = rec

    def leer(self, fut, espera):
        atascada = False
        if fut is not None:
            try:
                fut.result(timeout=max(espera, 0.0))
            except FutTimeout:
                atascada = True
            except Exception:
                pass
        with self.lock:
            r, bueno = self.rec, self.bueno
        if atascada:
            if bueno and time.time() - bueno["t"] < OBSOLETO_S:
                return {"ok": True, **bueno["v"], "obsoleto": True, "actualizado": _iso(bueno["t"])}
            return {"ok": False, "error": f"{self.nombre} tardó más de {ESPERA_S:g} s"}
        if r is None:
            return {"ok": False, "error": f"{self.nombre} aún no ha contestado"}
        if not r["ok"]:
            return {"ok": False, "error": r["error"]}
        return {"ok": True, **r["v"], "actualizado": _iso(r["t"])}


def _iso(t):
    return datetime.fromtimestamp(t, TZ).isoformat(timespec="seconds")


def _por_cuenta(cuentas, fn, que):
    """fn(email) → lista. Si fallan TODAS las cuentas, falla la fuente; si falla alguna, sale `parcial` con su etiqueta."""
    futs = [(c, INNER.submit(fn, c)) for c in cuentas]
    items, fallos = [], []
    for c, f in futs:
        try:
            items += f.result()
        except Exception:
            fallos.append(E.etiqueta(c))
    if cuentas and len(fallos) == len(cuentas):
        raise RuntimeError(f"No pude leer {que} de ninguna cuenta de Google")
    return {"items": items, "parcial": fallos}


# ───────────────────────── fuentes ─────────────────────────
def _g(home):
    """Argumentos para los ayudantes de Google: la carpeta de gog de una invitada, o nada (las cuentas de Fran)."""
    return {"home": home} if home else {}


def _tareas(home=None):
    cs = E.cuentas_con("tasks", **_g(home))
    if not cs:
        raise RuntimeError("Ninguna cuenta de Google tiene permiso de Tareas")

    def una(email):
        d = E.gog(["tasks", "list", "@default", "--all", "--max=100"], email, **_g(home))
        return [{"id": x["id"], "cuenta": E.etiqueta(email), "email": email, "titulo": limpio(x.get("title")),
                 "due": (x.get("due") or "")[:10], "hecha": x.get("status") == "completed"}
                for x in E.lista(d, "tasks", "items") if x.get("id")]
    return _por_cuenta(cs, una, "las tareas")


LLEVAR = re.compile(r"^[ \t]*(?:llevar|preparar)[ \t]*[:\-–][ \t]*(.+?)[ \t]*$", re.I | re.M)


def llevar_de(descripcion):
    """Líneas `llevar:` / `preparar:` de la descripción de un evento DE FRAN (nunca de una invitación ajena)."""
    out = []
    for v in LLEVAR.findall(str(descripcion or "")):
        out += [limpio(x, 80) for x in re.split(r"[;,]", v) if x.strip()]
    return out[:12]


def _evento(e, email):
    if e.get("status") == "cancelled":
        return None
    st, en = e.get("start") or {}, e.get("end") or {}
    ini = st.get("dateTime") or st.get("date")
    if not ini:
        return None
    propio = (e.get("organizer") or {}).get("self") is True and e.get("eventType", "default") in ("default", "birthday")
    titulo = limpio(e.get("summary") or "(sin título)")
    return {"id": e.get("id"), "cuenta": E.etiqueta(email), "titulo": titulo, "inicio": ini, "fin": en.get("dateTime") or en.get("date"),
            "todo_dia": "date" in st and "dateTime" not in st, "lugar": limpio(e.get("location"), 120), "propio": propio,
            "tentativo": titulo.startswith("¿?"), "llevar": llevar_de(e.get("description")) if propio else []}


def _eventos_rango(desde, dias, home=None):
    cs = E.cuentas_con("calendar", **_g(home))
    if not cs:
        raise RuntimeError("Ninguna cuenta de Google tiene permiso de Calendario")

    def una(email):
        d = E.gog(["calendar", "events", f"--from={desde}", f"--days={dias}", "--max=250", "--all-pages"], email, **_g(home))
        return [x for x in (_evento(e, email) for e in E.lista(d, "events", "items")) if x]
    r = _por_cuenta(cs, una, "la agenda")
    vistos, items = set(), []
    for ev in sorted(r["items"], key=lambda e: (not e["propio"], -len(e["llevar"]))):   # el de Fran (con su «llevar») gana al de la invitación                              # el mismo evento en las dos cuentas (invitaciones) sale una vez
        k = (ev["titulo"], ev["inicio"])
        if k not in vistos:
            vistos.add(k)
            items.append(ev)
    return {"items": items, "parcial": r["parcial"]}


def _eventos(home=None):
    return _eventos_rango(datetime.now(TZ).date().isoformat(), 2, home)


CARNET = re.compile(r"tr[aá]fico|dgt|ex[aá]men|te[oó]rico|carnet|autoescuela|trafik", re.I)


def _eventos_carnet():
    r = _eventos_rango(datetime.now(TZ).date().isoformat(), 43)
    items = [e for e in r["items"] if CARNET.search(e["titulo"])]
    items.sort(key=lambda e: e["inicio"])
    return {"items": [{k: e[k] for k in ("id", "cuenta", "titulo", "inicio", "fin", "todo_dia", "lugar")} for e in items[:10]], "parcial": r["parcial"]}


FECHAS = re.compile(r"plazo|entrega|vence|vencimiento|caduca|deadline", re.I)


def _eventos_fechas():
    r = _eventos_rango(datetime.now(TZ).date().isoformat(), 43)
    return {"items": [{k: e[k] for k in ("id", "cuenta", "titulo", "inicio", "fin", "todo_dia")} for e in r["items"] if FECHAS.search(e["titulo"])], "parcial": r["parcial"]}


def _vip():
    """Nombres de los chats VIP. La config guarda JIDs (teléfonos); solo se conserva el NOMBRE del chat que wacli les pone,
    en memoria. Los JIDs ni se devuelven ni se guardan en ningún sitio."""
    cfg = avisos._json(avisos.conf_dir() / "config.json")
    wa_ = (cfg.get("wa") or {}) if isinstance(cfg, dict) else {}
    entradas = [str(x).strip() for x in (wa_.get("vip") or []) + (wa_.get("vip_nombres") or []) if str(x).strip()]
    nombres = [x for x in entradas if "@" not in x and not x.isdigit()]
    jids = [x for x in entradas if x not in nombres]
    sin_resolver = 0
    if jids:
        try:
            chats = {c.get("jid"): c.get("name") for c in E.lista(E.wa(["chats", "list", "--limit", "800"]), "chats")}
        except Exception:
            chats = None
        for j in jids:
            n = (chats or {}).get(j)
            if n:
                nombres.append(limpio(n, 60))
            else:
                sin_resolver += 1
    return {"nombres": nombres, "sin_resolver": sin_resolver}


def _eventos_orden():
    """Eventos de hoy a +120 días para la barra de órdenes (solo título, día y hora: el intérprete busca relacionados/duplicados)."""
    hoy = datetime.now(TZ).date()
    r = _eventos_rango(hoy.isoformat(), 120)
    out = []
    for e in r["items"]:
        try:
            if e["todo_dia"]:
                fecha, hora = e["inicio"][:10], None
            else:
                i = datetime.fromisoformat(e["inicio"]).astimezone(TZ)
                fecha, hora = i.date().isoformat(), f"{i:%H:%M}"
        except (ValueError, TypeError):
            continue
        if fecha >= hoy.isoformat():
            out.append({"titulo": e["titulo"], "fecha": fecha, "hora": hora, "todo_dia": e["todo_dia"]})
    out.sort(key=lambda x: (x["fecha"], x["hora"] or ""))
    return {"items": out, "parcial": r["parcial"]}


FUENTES = {}


def _crear():
    FUENTES.update({
        "tareas": Fuente("Las tareas", 60, _tareas),
        "eventos": Fuente("La agenda", 120, _eventos),
        "avisos": Fuente("Los avisos", 1, lambda: {"items": avisos.listar("abierto", 100)}),
        "recientes": Fuente("Lo capturado hoy", 10, lambda: {"items": avisos.recientes_hoy()}),
        "vigias": Fuente("Los vigías", 5, avisos.vigias),
        "carnet": Fuente("Los eventos del carnet", 300, _eventos_carnet),
        "fechas": Fuente("Las fechas del calendario", 300, _eventos_fechas),
        "vip": Fuente("Los VIP", 600, _vip),
        "orden_eventos": Fuente("Los eventos próximos", 300, _eventos_orden),
    })


_crear()


ORDEN_ESPERA_S = float(os.environ.get("HUB_ORDEN_ESPERA", "5"))


def contexto_orden():
    """Lo que el intérprete de la barra de órdenes necesita para enlazar sin duplicar: eventos próximos (≤80: título, día, hora) y
    tareas abiertas (≤60). Cada lista es None si no se pudo leer a tiempo (la orden sigue sin ella). Las tareas llevan `id` y
    `email` SOLO para ejecutar un «completar/cambiar fecha» ya confirmado: el modelo nunca los ve."""
    t_fin = time.time() + ORDEN_ESPERA_S
    fe, ft = FUENTES["orden_eventos"], FUENTES["tareas"]
    fresco = os.environ.get("HUB_ORDEN_FRESCO") == "1"      # solo para las pruebas: sin esperar a que caduque la caché
    futs = (fe.iniciar(fresco), ft.iniciar(fresco))
    ev = fe.leer(futs[0], t_fin - time.time())
    ta = ft.leer(futs[1], t_fin - time.time())
    eventos = ev["items"][:80] if ev["ok"] else None
    tareas = None
    if ta["ok"]:
        abiertas = [t for t in ta["items"] if not t["hecha"] and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{5,63}", str(t["id"]))]
        abiertas.sort(key=lambda t: (t["due"] or "9999", t["titulo"]))
        tareas = [{"id": t["id"], "email": t["email"], "cuenta": t["cuenta"], "titulo": t["titulo"], "fecha": t["due"] or None} for t in abiertas[:60]]
    return {"eventos": eventos, "tareas": tareas}


def carnet_eventos():
    """Próximos eventos del carnet para el tablero Carnet (misma regla: tope de espera y error dicho)."""
    f = FUENTES["carnet"]
    return f.leer(f.iniciar(), ESPERA_S)


def ctx_tableros(eventos=True, fresco=False):
    """Lo que necesitan los tableros de las fuentes lentas del Panel. Todas se lanzan a la vez y comparten UN tope de espera
    (3 s); cada una falla por separado con su error."""
    t_fin = time.time() + ESPERA_S
    nombres = ["tareas", "avisos", "vip"] + (["carnet", "fechas"] if eventos else [])
    futs = {n: FUENTES[n].iniciar(fresco) for n in nombres}

    def sec(n):
        return FUENTES[n].leer(futs[n], t_fin - time.time())

    def pendientes():
        """Tareas y avisos abiertos (SOLO títulos) para saber qué está «pendiente con» cada persona."""
        ta, av = sec("tareas"), sec("avisos")
        if not ta["ok"] and not av["ok"]:
            return {"ok": False, "error": f"{ta['error']} · {av['error']}"}
        return {"ok": True, "tareas": [{"titulo": t["titulo"]} for t in ta.get("items", []) if not t["hecha"]] if ta["ok"] else [],
                "avisos": [{"titulo": a["titulo"]} for a in av.get("items", [])] if av["ok"] else [],
                "parcial": [n for n, s in (("tareas", ta), ("avisos", av)) if not s["ok"]]}
    return {"carnet": (lambda: sec("carnet")) if eventos else None, "fechas": (lambda: sec("fechas")) if eventos else None,
            "pendientes": pendientes, "vip": lambda: sec("vip"), "suscripciones": gastos.tablero}


# ───────────────────────── composición ─────────────────────────
_LOCK = threading.Lock()
_RESP = {"t": 0.0, "v": None}


def invalidar():
    """Tras cambiar un aviso: la siguiente lectura va a la base."""
    with _LOCK:
        _RESP["v"] = None
    for n in ("avisos", "recientes"):
        FUENTES[n].rec = None


def invalidar_google():
    """Tras crear una tarea o un evento: la siguiente lectura vuelve a preguntar a Google."""
    with _LOCK:
        _RESP["v"] = None
    for n in ("tareas", "eventos", "carnet", "orden_eventos"):
        FUENTES[n].rec = None
    with _LOCK_DE:
        for fs in _DE.values():
            for f in fs.values():
                f.rec = None


def componer(fresco=False):
    with _LOCK:
        if _RESP["v"] is not None and time.time() - _RESP["t"] < (REBOTE_S if fresco else CACHE_S):
            return _RESP["v"]
        v = _componer(fresco)
        _RESP.update(t=time.time(), v=v)
        return v


def _dia_evento(ev, hoy, ahora):
    """'hoy' | 'mañana' | None (ya terminó o no toca)."""
    try:
        if ev["todo_dia"]:
            a = date.fromisoformat(ev["inicio"][:10])
            b = date.fromisoformat(ev["fin"][:10]) if ev.get("fin") else a + timedelta(days=1)
            for d, etq in ((hoy, "hoy"), (hoy + timedelta(days=1), "mañana")):
                if a <= d < b:
                    return etq
            return None
        i = datetime.fromisoformat(ev["inicio"]).astimezone(TZ)
        f = datetime.fromisoformat(ev["fin"]).astimezone(TZ) if ev.get("fin") else i + timedelta(hours=1)
        if f < ahora:
            return None
        d = i.date()
        return "hoy" if d <= hoy else "mañana" if d == hoy + timedelta(days=1) else None
    except (ValueError, TypeError, KeyError):
        return None


# Panel de una invitada: SOLO sus fuentes (su agenda y sus tareas, con su carpeta de gog). Nada del vigía, de WhatsApp ni del Cerebro de Fran.
_DE = {}   # carpeta de gog → {nombre: Fuente}
_LOCK_DE = threading.Lock()   # aparte de _LOCK: el panel de una invitada no espera a que se componga el de Fran


def componer_de(home, nombre, fresco=False):
    """El mismo JSON que componer(), con las secciones que la invitada tiene (agenda y tareas, si su Google les dio permiso).
    Lo que solo existe para Fran (avisos, capturas, vigías) no sale: el front lo esconde."""
    if not home:
        raise ValueError("falta la carpeta de gog del invitado")
    with _LOCK_DE:
        fs = _DE.get(home)
        if fs is None:
            fs = _DE[home] = {"tareas": Fuente("Las tareas", 60, lambda: _tareas(home)), "eventos": Fuente("La agenda", 120, lambda: _eventos(home))}

    def tiene(servicio):
        try:
            return bool(E.cuentas_con(servicio, home=home))
        except Exception:   # sin poder leer sus cuentas: la sección sale con su error, no desaparece
            return True
    return _componer(fresco, {n: f for n, f in fs.items() if tiene({"tareas": "tasks", "eventos": "calendar"}[n])}, nombre)


def _componer(fresco, fs=None, nombre="Fran"):
    t0 = time.time()
    ahora = datetime.now(TZ)
    hoy = ahora.date()
    fs = FUENTES if fs is None else fs
    nombres = [n for n in ("tareas", "eventos", "avisos", "recientes", "vigias") if n in fs]
    futs = {n: fs[n].iniciar(fresco) for n in nombres}
    sec = {n: fs[n].leer(futs[n], ESPERA_S - (time.time() - t0)) for n in nombres}
    NO = {"ok": False, "error": "no disponible", "items": []}   # sección que esta persona no tiene: no se devuelve
    for n in ("tareas", "eventos", "avisos", "recientes"):
        sec.setdefault(n, NO)

    # ── eventos de hoy y mañana ──
    ev = sec["eventos"]
    if ev["ok"]:
        lista = []
        for e in ev["items"]:
            d = _dia_evento(e, hoy, ahora)
            if d:
                lista.append({**e, "dia": d})
        lista.sort(key=lambda e: (e["dia"] != "hoy", not e["todo_dia"], e["inicio"]))
        ev = {**ev, "items": lista}
    # ── tareas vencidas y de hoy ──
    ta = sec["tareas"]
    sin_fecha = 0
    if ta["ok"]:
        lista = []
        for t in ta["items"]:
            if t["hecha"]:
                continue
            if not t["due"]:
                sin_fecha += 1
            elif t["due"] <= hoy.isoformat():
                atraso = (hoy - date.fromisoformat(t["due"])).days if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["due"]) else 0
                lista.append({"id": t["id"], "cuenta": t["cuenta"], "email": t["email"], "titulo": t["titulo"], "due": t["due"],
                              "estado": "vencida" if atraso > 0 else "hoy", "dias_retraso": max(atraso, 0)})
        lista.sort(key=lambda t: (t["due"], t["titulo"]))
        ta = {**ta, "items": lista, "sin_fecha": sin_fecha}
    # ── avisos ──
    av = sec["avisos"]
    por_fuente, p1 = {}, 0
    if av["ok"]:
        for a in av["items"]:
            por_fuente[a["fuente"]] = por_fuente.get(a["fuente"], 0) + 1
            p1 += a["prio"] == 1
        av = {**av, "total": len(av["items"])}

    # ── la lista «Para ti ahora» ──
    ahora_l = []
    solape = ev["ok"] and ta["ok"]
    if av["ok"]:
        for a in av["items"]:
            if solape and a["tipo"] in avisos.DE_AGENDA:       # ya sale como evento o como tarea
                continue
            ahora_l.append({"clave": f"aviso:{a['id']}", "tipo": {"correo": "correo", "wa": "whatsapp"}.get(a["fuente"], "aviso"),
                            "prio": min(max(a["prio"], 1), 3), "titulo": a["titulo"], "detalle": a["detalle"] or None, "cuando": a["creado"],
                            "cuenta": a["cuenta"], "codigo": a["codigo"], "aviso_id": a["id"], "fuente": a["fuente"], "subtipo": a["tipo"],
                            "enlace": a["enlace"] or None, "borrador": a["borrador"] or None, "tiene_borrador": a["tiene_borrador"],
                            "acciones": ["hecho", "luego", "descartar"] + (["borrador"] if a["tiene_borrador"] else [])})
    if ev["ok"]:
        for e in ev["items"]:
            try:
                ini = datetime.fromisoformat(e["inicio"]).astimezone(TZ) if not e["todo_dia"] else None
            except ValueError:
                ini = None
            prio = 3
            if e["dia"] == "hoy":
                prio = 1 if ini and ini - ahora <= timedelta(minutes=90) else 2
            elif e["llevar"]:
                prio = 2
            if e["dia"] == "mañana" and not e["llevar"]:
                continue
            ahora_l.append({"clave": f"evento:{e['id']}", "tipo": "evento", "prio": prio, "titulo": e["titulo"], "cuando": e["inicio"], "fin": e["fin"],
                            "todo_dia": e["todo_dia"], "lugar": e["lugar"] or None, "cuenta": e["cuenta"], "dia": e["dia"],
                            "checklist": e["llevar"] or None, "tentativo": e["tentativo"], "acciones": []})
    if ta["ok"]:
        for t in ta["items"]:
            ahora_l.append({"clave": f"tarea:{t['id']}", "tipo": "tarea", "prio": 2, "titulo": t["titulo"], "cuando": t["due"], "cuenta": t["cuenta"],
                            "detalle": (f"vencida hace {t['dias_retraso']} d" if t["dias_retraso"] else "para hoy"),
                            "ref": {"account": t["email"], "id": t["id"]}, "acciones": ["hecho"]})
    ahora_l.sort(key=lambda x: (x["prio"], str(x.get("cuando") or "9999")))

    rc = sec["recientes"]
    resumen = {
        "eventos_hoy": sum(1 for e in ev["items"] if e["dia"] == "hoy") if ev["ok"] else None,
        "eventos_manana": sum(1 for e in ev["items"] if e["dia"] == "mañana") if ev["ok"] else None,
        "llevar": sum(1 for e in ev["items"] if e["llevar"]) if ev["ok"] else None,
        "tareas_vencidas": sum(1 for t in ta["items"] if t["estado"] == "vencida") if ta["ok"] else None,
        "tareas_hoy": sum(1 for t in ta["items"] if t["estado"] == "hoy") if ta["ok"] else None,
        "tareas_sin_fecha": sin_fecha if ta["ok"] else None,
        "avisos": len(av["items"]) if av["ok"] else None,
        "avisos_p1": p1 if av["ok"] else None,
        "avisos_por_fuente": por_fuente if av["ok"] else None,
        "capturado_hoy": len(rc["items"]) if rc["ok"] else None,
    }
    fuentes = {}
    final = {"tareas": ta, "eventos": ev, "avisos": av, "recientes": rc, "vigias": sec.get("vigias")}
    for n in nombres:
        s = final[n]
        act = s.get("actualizado")
        edad = int(time.time() - datetime.fromisoformat(act).timestamp()) if act else None
        fuentes[n] = {"ok": s["ok"], "actualizado": act, "edad_s": edad, "obsoleto": bool(s.get("obsoleto")), "error": s.get("error"), "parcial": s.get("parcial") or None}
    out = {
        "ok": True, "generado": ahora.isoformat(timespec="seconds"), "ms": int((time.time() - t0) * 1000),
        "fecha": hoy.isoformat(), "hora": f"{ahora:%H:%M}", "dia_semana": DIAS[hoy.weekday()],
        "saludo": {"nombre": nombre, "fecha": hoy.isoformat(), "hora": f"{ahora:%H:%M}", "dia_semana": DIAS[hoy.weekday()]},
        "resumen": resumen,
        "ahora": ahora_l[:20], "ahora_total": len(ahora_l),
        "urgentes": {n: final[n] for n in ("eventos", "tareas", "avisos") if n in nombres},
        "recientes": rc, "vigias": sec.get("vigias"), "fuentes": fuentes,
        "errores": [{"fuente": n, "error": f["error"]} for n, f in fuentes.items() if not f["ok"]],
    }
    if fs is not FUENTES:   # una invitada: fuera las secciones que no tiene (nunca un «0» ni un error inventado)
        for n in ("recientes", "vigias"):
            if n not in nombres:
                out.pop(n)
        de = {"eventos_hoy": "eventos", "eventos_manana": "eventos", "llevar": "eventos", "avisos": "avisos", "avisos_p1": "avisos",
              "avisos_por_fuente": "avisos", "capturado_hoy": "recientes"}
        out["resumen"] = {k: v for k, v in resumen.items() if de.get(k, "tareas") in nombres}
    return out
