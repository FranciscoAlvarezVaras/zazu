"""Barra de órdenes de Zazu: SIN charla libre.

interpretar(texto) es un analizador determinista (reglas en español, sin IA, sin red) que devuelve una PROPUESTA
(tipo, titulo, fecha, destino…) o «fuera_de_ambito» («Eso mejor lo hablamos en el chat»). No escribe nada. Las propuestas se guardan
en memoria 15 min; solo `confirmar(id)` ejecuta, y solo por una lista cerrada de acciones (las mismas formas que la bandeja
de Tareas/Calendar: `tasks add` con --title/--due y `calendar create` con --summary/--from/--to/--start-timezone/
--end-timezone/--all-day/--location; las notas, por nota_rapida en «10 Bandeja»). Nunca envía, borra ni invita.
Solo biblioteca estándar.
"""
import calendar as _cal
import re, secrets, threading, time, unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import entender
import privado

TZ = ZoneInfo("Europe/Madrid")
MAX_TEXTO = 500
CADUCA_S = 900
FUERA = {"ok": True, "tipo": "fuera_de_ambito", "mensaje": "Eso mejor lo hablamos en el chat", "abrir": "hermes"}   # `abrir`: campo del contrato (no se ve); la app abre el chat
DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
DIA_CORTO = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                                     "octubre", "noviembre", "diciembre"], 1)}
NUM = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
       "once": 11, "doce": 12}
# lista cerrada de escrituras (misma forma que zazu-bandeja/google.py: ESCRITURAS + FLAGS_OK; calendar create, la del vigía)
PERMITIDO = {("tasks", "add"): ("@default", ("--title", "--due")),
             ("calendar", "create"): ("primary", ("--summary", "--from", "--to", "--start-timezone", "--end-timezone", "--location"))}
SOLO_SIN_VALOR = ("--all-day",)
# Sobre una tarea que YA existe (id de Google sacado de NUESTRA lista, nunca del modelo): solo completarla o cambiarle el día. Nunca borrar.
ID_TAREA = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{5,63}")
SOBRE_TAREA = {("tasks", "done"): (), ("tasks", "update"): ("--due",)}


class OrdenError(Exception):
    def __init__(self, code, msg, **extra):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, extra


# ───────────────────────── texto ─────────────────────────
def limpiar(s):
    s = re.sub(r"[\x00-\x1f\x7f​-‏‪-‮  ]+", " ", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def fold(s):
    """Minúsculas y sin tildes, MISMA longitud (para recortar el original con las posiciones de la versión plegada)."""
    return "".join((unicodedata.normalize("NFD", c)[:1] or c).lower()[:1] for c in s)


def cap(s):
    return s[:1].upper() + s[1:] if s else s


def _libre(spans, a, b):
    return all(b <= x or a >= y for x, y in spans)


def _buscar(rx, f, spans, flags=0):
    for m in re.finditer(rx, f, flags):
        if _libre(spans, m.start(), m.end()):
            return m
    return None


# ───────────────────────── fecha y hora ─────────────────────────
def _hora(h, m, q):
    """Hora de 24 h con el calificador «de la tarde/noche/mañana» o, sin él, la costumbre (1–7 = tarde)."""
    h, m = int(h), int(m or 0)
    if h > 23 or m > 59:
        return None
    if q == "noche" and h == 12:
        h = 0                                  # «las 12 de la noche» es medianoche
    elif q in ("tarde", "noche") and h < 12:
        h += 12
    elif q == "madrugada" and h == 12:
        h = 0
    elif q is None and 1 <= h <= 7:
        h += 12
    return h, m


def _sumar_meses(d, n):
    mes = d.month - 1 + n
    anio, mes = d.year + mes // 12, mes % 12 + 1
    return date(anio, mes, min(d.day, _cal.monthrange(anio, mes)[1]))


def extraer_cuando(f, ahora):
    """→ {fecha, hora, fin, dur, supuesta, spans}. `f` es el texto plegado. Solo lo que se reconoce con seguridad."""
    spans, out = [], {"fecha": None, "hora": None, "fin": None, "dur": None, "supuesta": None}
    hoy = ahora.date()
    num = r"(\d{1,2}|" + "|".join(sorted(NUM, key=len, reverse=True)) + r")\b"

    def n(v):
        return NUM.get(v) or int(v)

    # rango «de 10 a 11» / «de las 10:30 a las 12»
    m = _buscar(r"\bde (?:las? )?(\d{1,2})(?:[:h](\d{2}))? a (?:las? )?(\d{1,2})(?:[:h](\d{2}))?(?:\s+(?:de la |por la )?(manana|tarde|noche))?\b(?!\s*(?:euros?|eur|%|personas|dias?|km|kg|min))", f, spans)
    if m:
        q = m.group(5)
        a, b = _hora(m.group(1), m.group(2), q), _hora(m.group(3), m.group(4), q)
        if a and b and (b > a or q is None):
            out["hora"], out["fin"] = a, b if b > a else None
            spans.append(m.span())
    if out["hora"] is None:
        m = _buscar(r"\b(?:a|sobre|hacia) las? " + num + r"(?:(?::|\.|h)\s?(\d{2}))?(?:\s*h(?:oras?)?\b)?(?:\s+(y media|y cuarto|menos cuarto)\b)?(?:\s+(?:de la |del |por la |en la )?(manana|tarde|noche|madrugada))?", f, spans)
        if m:
            hh, mm, extra = n(m.group(1)), m.group(2), m.group(3)
            if extra == "y media":
                mm = 30
            elif extra == "y cuarto":
                mm = 15
            elif extra == "menos cuarto":
                hh, mm = (hh - 1 if hh > 0 else 23), 45
            h = _hora(hh, mm, m.group(4))
            if h:
                out["hora"] = h
                spans.append(m.span())
    if out["hora"] is None:
        m = _buscar(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", f, spans)
        if m:
            out["hora"] = _hora(m.group(1), m.group(2), "tal_cual")  # con «:» se toma tal cual
            spans.append(m.span())
    if out["hora"] is None:
        m = _buscar(r"\ba mediodia\b", f, spans)
        if m:
            out["hora"] = (12, 0)
            spans.append(m.span())
    m = _buscar(r"\bhasta las? (\d{1,2})(?::(\d{2}))?\b", f, spans)
    if m and out["fin"] is None:
        out["fin"] = _hora(m.group(1), m.group(2), "tarde" if out["hora"] and out["hora"][0] >= 12 and int(m.group(1)) < 12 else None)
        spans.append(m.span())
    m = _buscar(r"\bdurante (\d+|una|dos|media)\s*(horas?|h|minutos?|min)\b", f, spans)
    if m:
        v = 0.5 if m.group(1) == "media" else n(m.group(1))
        out["dur"] = int(v * 60) if m.group(2).startswith(("h", "hora")) else int(v)
        spans.append(m.span())
    # «por la mañana/tarde/noche» sueltos: se quitan del título
    for m in re.finditer(r"\b(?:por|de|en) la (?:manana|tarde|noche|madrugada)\b", f):
        if _libre(spans, *m.span()):
            spans.append(m.span())

    # ── fecha ──
    def poner(d, span):
        out["fecha"] = d
        spans.append(span)

    m = _buscar(r"\bpasado manana\b", f, spans)
    if m:
        poner(hoy + timedelta(days=2), m.span())
    if out["fecha"] is None:
        m = _buscar(r"(?<!la )(?<!esta )\bmanana\b", f, spans)
        if m:
            poner(hoy + timedelta(days=1), m.span())
    if out["fecha"] is None:
        m = _buscar(r"\bhoy\b|\besta (?:tarde|noche|manana)\b", f, spans)
        if m:
            poner(hoy, m.span())
    if out["fecha"] is None:
        m = _buscar(r"\b(?:este |el )?(?:fin de semana|finde)(?: (que viene|proximo|siguiente))?\b", f, spans)
        if m:
            dias = 0 if hoy.weekday() >= 5 and not m.group(1) else (5 - hoy.weekday()) % 7 or 7   # sáb/dom y «este finde»: ya es hoy
            poner(hoy + timedelta(days=dias), m.span())
    if out["fecha"] is None:
        m = _buscar(r"\b(?:el )?(?:proximo )?(" + "|".join(DIAS) + r")(?: (?:que viene|proximo))?\b", f, spans)
        if m:
            dif = (DIAS[m.group(1)] - hoy.weekday()) % 7 or 7
            poner(hoy + timedelta(days=dif), m.span())
    if out["fecha"] is None:
        m = _buscar(r"\b(?:el )?(\d{1,2})([/\-])(\d{1,2})(?:\2(\d{2,4}))?\b(?!\s*(?:kilos?|kg|gramos?|litros?|euros?|eur|%|personas|dias?|km|min|minutos|horas?|uds?|unidades|g\b|l\b))", f, spans)
        if m and (m.group(2) == "/" or m.group(4) or m.group(0).startswith("el ")):
            d_, mes_ = int(m.group(1)), int(m.group(3))
            anio = int(m.group(4)) + (2000 if len(m.group(4)) == 2 else 0) if m.group(4) else None
            try:
                d = date(anio or hoy.year, mes_, d_)
                if anio is None and d < hoy:
                    d = date(hoy.year + 1, mes_, d_)
                poner(d, m.span())
            except ValueError:
                pass
    if out["fecha"] is None:
        m = _buscar(r"\b(?:el (?:dia )?)?(\d{1,2}) de (" + "|".join(MESES) + r")(?: de (\d{4}))?\b", f, spans)
        if m:
            try:
                anio = int(m.group(3)) if m.group(3) else hoy.year
                d = date(anio, MESES[m.group(2)], int(m.group(1)))
                if not m.group(3) and d < hoy:
                    d = date(hoy.year + 1, d.month, d.day)
                poner(d, m.span())
            except ValueError:
                pass
    if out["fecha"] is None:
        m = _buscar(r"\bel (?:dia )?(\d{1,2})\b(?!\s*(?:euros?|eur|€|%|min|minutos|horas?|dias?|kg|km|personas|veces|de\b|/))", f, spans)
        if m and 1 <= int(m.group(1)) <= 31:
            dia_ = int(m.group(1))
            d = None
            for k in range(0, 14):                      # este mes o el primero que tenga ese día
                base = _sumar_meses(hoy.replace(day=1), k)
                if dia_ <= _cal.monthrange(base.year, base.month)[1]:
                    c = base.replace(day=dia_)
                    if c >= hoy:
                        d = c
                        break
            if d:
                poner(d, m.span())
    if out["fecha"] is None:
        m = _buscar(r"\ben " + num + r" (dias?|semanas?|meses?)\b", f, spans)
        if m:
            v = n(m.group(1))
            u = m.group(2)
            poner(hoy + timedelta(days=v) if u.startswith("dia") else hoy + timedelta(weeks=v) if u.startswith("sem") else _sumar_meses(hoy, v), m.span())
    if out["fecha"] is None and out["hora"] is None:
        m = _buscar(r"\ben " + num + r" (horas?|minutos?)\b", f, spans)
        if m:
            v = n(m.group(1))
            t = ahora + (timedelta(hours=v) if m.group(2).startswith("hora") else timedelta(minutes=v))
            out["fecha"], out["hora"] = t.date(), (t.hour, t.minute)
            spans.append(m.span())
    # hora sin día: la próxima vez que ocurra
    if out["fecha"] is None and out["hora"] is not None:
        h, mi = out["hora"]
        ya = (h, mi) <= (ahora.hour, ahora.minute)
        out["fecha"] = hoy + timedelta(days=1 if ya else 0)
        out["supuesta"] = "mañana (la hora de hoy ya pasó)" if ya else "hoy"
    out["spans"] = sorted(spans)
    return out


def _titulo(original, spans, quitar_inicio=0):
    """El texto sin las partes de fecha/hora y sin preposiciones colgando."""
    partes, i = [], quitar_inicio
    for a, b in spans:
        if a >= i:
            partes.append(original[i:a])
            i = b
    partes.append(original[i:])
    t = re.sub(r"\s+", " ", " ".join(partes)).strip()
    t = re.sub(r"\s+([,;:.])", r"\1", t)
    for _ in range(4):
        t2 = re.sub(r"(?i)(?:^|\s)(?:el|la|a|para|de|del|en|y|que|por|este|esta|al|sobre|hacia|con)$", "", t).strip(" ,;:.-–—")
        t2 = re.sub(r"(?i)^(?:que|de|a|para|y)\s+", "", t2)
        if t2 == t:
            break
        t = t2
    return t.strip(" ,;:.-–—")


# ───────────────────────── intenciones ─────────────────────────
def _fecha_txt(d, hora=None):
    s = f"{DIA_CORTO[d.weekday()]} {d.day}/{d.month}"
    return s + (f" {hora}" if hora else "")


def _hhmm(h):
    return f"{h[0]:02d}:{h[1]:02d}" if h else None


# Frases libres: «Hacer la maleta para el sábado y además ponlo en tareas». Sin IA: un verbo en infinitivo (o «hay que…») al principio
# es una tarea; «ponlo en el calendario» con día claro es un evento. Lo que sigue sin entenderse se manda al chat.
INFINITIVOS = ("hacer comprar llamar pagar enviar mandar reservar pedir recoger llevar traer preparar revisar escribir renovar sacar ir visitar "
               "devolver cancelar contratar buscar arreglar limpiar ordenar terminar empezar estudiar cambiar firmar imprimir solicitar confirmar "
               "alquilar probar organizar lavar planchar tramitar actualizar subir vender cobrar transferir ingresar rellenar mirar coger cortar "
               "montar instalar avisar acordarme quedar entregar presentar apuntarme inscribirme pasar hablar decir felicitar").split()
LIBRE_INI = re.compile(r"^(?:(?:hay que|necesito|no olvidar|no olvides|debo|toca|pendiente|me falta|falta)\s*[:,]?\s+)?((?:" + "|".join(INFINITIVOS) + r")\b.*)$")
DESTINO_FIN = re.compile(r"[,.;]?\s*(?:y\s+)?(?:ademas\s+)?(?:y\s+)?(?:ponl[oa]s?|pon(?:me)?lo|ponmelo|anadel[oa]s?|anademe(?:lo|la)|apuntal[oa]s?|guardal[oa]s?|metel[oa]s?)\s+"
                         r"(?:en|a)\s+(?:mis\s+|mi\s+|las\s+|la\s+|el\s+|los\s+)?(?P<d>google tareas|tareas de google|tareas?|tasks?|calendario|agenda)\b")


def interpretar(texto, ahora=None, cuenta="varas"):
    """→ dict con 'tipo'. Tipos: nota, idea, tarea, evento, aplicar, investigar, proyecto (propuestas),
    'fuera_de_ambito' y 'privado'. Lanza ValueError si el texto está vacío o es enorme."""
    if not isinstance(texto, str):
        raise ValueError("texto no válido")
    t = limpiar(texto)
    if not t:
        raise ValueError("texto vacío")
    if len(t) > MAX_TEXTO:
        raise ValueError("texto demasiado largo")
    ahora = (ahora or datetime.now(TZ))
    f = fold(t)
    t0 = re.match(r"^(?:oye |hey )?(?:(?:byte|zazu)[ ,]+)?(?:por favor[ ,]+)?", f).end()
    g = f[t0:]
    o = t[t0:]

    def prop(tipo, titulo, destino, resumen, fecha=None, hora=None, **campos):
        d = {"ok": True, "tipo": tipo, "titulo": titulo, "fecha": fecha.isoformat() if fecha else None, "hora": hora,
             "destino": destino, "resumen": resumen, "confirmable": True, "falta": [], "aviso": None}
        d.update(campos)
        return d

    # 1) prefijos de la bandeja de Tareas: «Aplicar: …», «Investigar: …», «Proyecto: …»
    m = re.match(r"^(aplicar|investigar|proyecto)\s*[:\-–—]\s*(.+)$", g)
    if m:
        verbo, arg = m.group(1), o[m.start(2):].strip()
        if privado.es_privado(arg):
            return _privado()
        if re.search(r"(?i)\b(?!https?://)[a-z][a-z0-9+.\-]*://", arg):
            raise ValueError("enlace no válido")
        url = re.search(r"https?://\S+", arg)
        if url and not re.fullmatch(r"https?://[^\s<>\"']{4,450}", url.group(0)):
            raise ValueError("enlace no válido")
        titulo = f"{cap(verbo)}: {arg}"[:300]
        return prop(verbo, titulo, f"Google Tareas [{cuenta}] · Zazu la procesa", f"{cap(verbo)}: {arg[:100]} → tarea en Google Tareas; el vigía de la bandeja se encarga",
                    campos={"titulo": titulo, "due": None, "cuenta": cuenta}, cuenta=cuenta)
    # 2) idea:
    m = re.match(r"^idea\s*[:\-–—]\s*(.+)$", g)
    if m:
        cuerpo = o[m.start(1):].strip()
        if privado.es_privado(cuerpo):
            return _privado()
        return prop("idea", cap(cuerpo[:60]), "Cerebro › 10 Bandeja (Zazu la pasa a Ideas)", f"Idea: {cuerpo[:100]}", texto=cuerpo)
    # 3) apunta… / anota… / nota:
    m = re.match(r"^(?:(?:apunta|anota)(?:me)?(?:\s+en\s+(?:mis\s+)?notas?)?\s*[:,\-–—]?\s*(?:que\s+)?|nota\s*[:\-–—]\s*)(.+)$", g)
    if m:
        cuerpo = o[m.start(1):].strip()
        if privado.es_privado(cuerpo):
            return _privado()
        return prop("nota", cap(re.split(r"[.\n]", cuerpo)[0][:60]), "Cerebro › 10 Bandeja", f"Nota: {cuerpo[:100]}", texto=cuerpo)
    # 4) recuérdame… → tarea con fecha
    m = re.match(r"^(?:recuerdame|acuerdame|recordarme|tengo que|tarea\s*[:\-–—])\s*[:,]?\s*(?:que\s+)?(.+)$", g)
    if m:
        a = m.start(1)
        cu = extraer_cuando(g[a:], ahora)
        desp = [(x + t0 + a, y + t0 + a) for x, y in cu["spans"]]
        titulo = cap(_titulo(t, desp, t0 + a))
        if not titulo:
            return dict(FUERA, texto=t)
        hora = _hhmm(cu["hora"])
        if hora:
            titulo = f"{titulo} ({hora})"
        if privado.es_privado(titulo):
            return _privado()
        titulo = titulo[:200]
        d = cu["fecha"]
        res = f"Tarea: {titulo}" + (f" · {_fecha_txt(d)}" if d else " · sin fecha")
        p = prop("tarea", titulo, f"Google Tareas [{cuenta}]", res, fecha=d, hora=hora, cuenta=cuenta,
                 campos={"titulo": titulo, "due": d.isoformat() if d else None, "cuenta": cuenta})
        if cu["supuesta"]:
            p["aviso"] = f"No dijiste el día: lo he puesto para {cu['supuesta']}."
        elif not d:
            p["aviso"] = "Sin fecha: quedará en Tareas sin día."
        return p
    # 5) cita / evento … a las …
    m = re.match(r"^(?:(?:crea|crear|anade|anademe|agenda|agendame|pon|ponme|programa)\s+(?:una?\s+)?)?(cita|evento|reunion|quedada)\b\s*[:\-–—]?\s*(.*)$", g)
    if m and m.group(2).strip():
        a = m.start(2)
        cu = extraer_cuando(g[a:], ahora)
        desp = [(x + t0 + a, y + t0 + a) for x, y in cu["spans"]]
        cuerpo = _titulo(t, desp, t0 + a)
        nombre = m.group(1)
        titulo = cap(cuerpo) if nombre == "evento" else cap(f"{o[m.start(1):m.end(1)].lower()} {cuerpo}".strip())
        titulo = titulo[:200]
        if not cuerpo:
            return dict(FUERA, texto=t)
        if privado.es_privado(titulo):
            return _privado()
        d = cu["fecha"]
        h, fin = cu["hora"], cu["fin"]
        todo_dia = d is not None and h is None
        dur = cu["dur"] or 60
        if h and not fin:
            ini = datetime.combine(d, datetime.min.time()).replace(hour=h[0], minute=h[1])
            e = min(ini + timedelta(minutes=dur), ini.replace(hour=23, minute=59))
            fin = (e.hour, e.minute) if e > ini else None
        if h and fin and fin <= h:
            fin = None
        falta = [] if d else ["fecha"]
        res = f"Evento: {titulo}" + (f" · {_fecha_txt(d, _hhmm(h))}" + (f"–{_hhmm(fin)}" if fin else "") if d else " · ¿qué día?")
        p = prop("evento", titulo, f"Google Calendar [{cuenta}]", res, fecha=d, hora=_hhmm(h), fin=_hhmm(fin), todo_dia=todo_dia,
                 cuenta=cuenta, campos={"titulo": titulo, "fecha": d.isoformat() if d else None, "hora": _hhmm(h), "fin": _hhmm(fin), "todo_dia": todo_dia, "cuenta": cuenta})
        p["falta"], p["confirmable"] = falta, not falta
        if falta:
            p["aviso"] = "¿Para qué día? Escríbelo con la fecha («el viernes a las 10»)."
        elif todo_dia:
            p["aviso"] = "Sin hora: lo apunto de todo el día."
        elif cu["supuesta"]:
            p["aviso"] = f"No dijiste el día: lo he puesto para {cu['supuesta']}."
        return p
    # 6) frase libre: «hacer X…», «hay que X…», con o sin «y ponlo en tareas / el calendario»
    ms = DESTINO_FIN.search(g)
    if ms:   # «…, ponlo en el calendario»: se tapa esa parte (con espacios, para no mover las posiciones) y se sigue con el resto
        a0, a1 = t0 + ms.start(), t0 + ms.end()
        tt, ff = t[:a0] + " " * (a1 - a0) + t[a1:], f[:a0] + " " * (a1 - a0) + f[a1:]
    else:
        tt, ff = t, f
    resto = ff[t0:]
    ml = LIBRE_INI.match(resto.strip())
    if ml:
        lead = len(resto) - len(resto.lstrip())
        cuerpo = re.sub(r"\s+", " ", tt[t0:]).strip(" ,.;")
        cu = extraer_cuando(resto, ahora)
        if ms and ms.group("d") in ("calendario", "agenda") and cu["fecha"]:
            return interpretar("evento " + cuerpo, ahora, cuenta)
        a = lead + ml.start(1)
        desp = [(x + t0, y + t0) for x, y in cu["spans"]]
        titulo = cap(_titulo(tt, desp, t0 + a))
        if not titulo:
            return dict(FUERA, texto=t)
        hora = _hhmm(cu["hora"])
        if hora:
            titulo = f"{titulo} ({hora})"
        if privado.es_privado(titulo):
            return _privado()
        titulo = titulo[:200]
        d = cu["fecha"]
        res = f"Tarea: {titulo}" + (f" · {_fecha_txt(d)}" if d else " · sin fecha")
        p = prop("tarea", titulo, f"Google Tareas [{cuenta}]", res, fecha=d, hora=hora, cuenta=cuenta,
                 campos={"titulo": titulo, "due": d.isoformat() if d else None, "cuenta": cuenta})
        if cu["supuesta"]:
            p["aviso"] = f"No dijiste el día: lo he puesto para {cu['supuesta']}."
        elif ms and ms.group("d") in ("calendario", "agenda"):
            p["aviso"] = "Quieres verlo en el calendario, pero no dijiste el día: queda como tarea. Si es una cita, escribe «cita … el viernes a las 10»."
        elif not d:
            p["aviso"] = "Sin fecha: quedará en Tareas sin día. Puedes editarlo y poner «el sábado»."
        return p
    return dict(FUERA, texto=t)


def _privado():
    return {"ok": True, "tipo": "privado", "mensaje": "Eso lleva datos que no guardo (claves, cuentas, DNI…). No he apuntado nada."}


# ───────────────────────── entender con IA (Haiku) ─────────────────────────
# interpretar() de arriba son las REGLAS (sin IA, sin red). entender_orden() las envuelve: prefijos explícitos → reglas; texto privado →
# «privado» sin llamar al modelo; el resto → Claude Haiku (entender.py) con la lista de eventos y tareas próximos para enlazar sin
# duplicar. Lo que devuelve el modelo es DATO ya validado por entender.validar(); aquí se convierte en propuestas del mismo tipo que las
# de las reglas, que solo ejecuta `ejecutar` por la lista cerrada y tras «Confirmar». Si el modelo falla, tarda, no está o devuelve algo
# raro, se usan las reglas.
MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
PREFIJO_FIJO = re.compile(r"^(?:(?:oye|hey) )?(?:(?:byte|zazu)[ ,]+)?(?:por favor[ ,]+)?(?:aplicar|investigar|proyecto|idea|nota)\s*[:\-–—]\s*\S")
URL_RX = re.compile(r"https?://[^\s<>\"']{4,450}")
VERBO_DE = {"aplicar": "Aplicar", "investigar": "Investigar", "proyecto": "Proyecto"}


def _fecha_corta(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{DIA_CORTO[d.weekday()]} {d.day} {MES_CORTO[d.month - 1]}"


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", fold(re.sub(r"\s*\(\d{2}:\d{2}\)\s*$", "", str(s or ""))))).strip()


def _etiqueta_rel(tipo, o):
    cuando = _fecha_corta(o["fecha"]) if o.get("fecha") else "sin fecha"
    if tipo == "evento" and o.get("hora"):
        cuando += f" {o['hora']}"
    return f"«{o['titulo']}» · {cuando}"


def destino_txt(it):
    """El destino en lenguaje llano («Irá a: tus tareas de Google, para el 17 oct»)."""
    t, f = it.get("tipo"), it.get("fecha")
    fc = None
    try:
        fc = f"{DIA_CORTO[date.fromisoformat(f).weekday()]} {date.fromisoformat(f).day} {MES_CORTO[date.fromisoformat(f).month - 1]}" if f else None
    except (ValueError, TypeError):
        pass
    if t == "tarea":
        return "Irá a: tus tareas de Google, " + (f"para el {fc}" if fc else "sin fecha")
    if t == "evento":
        if not fc:
            return "Irá a: tu calendario de Google (falta el día)"
        return f"Irá a: tu calendario de Google, el {fc}" + (f" a las {it['hora']}" if it.get("hora") else ", todo el día")
    if t == "nota":
        return "Irá a: tus notas (Cerebro › Bandeja)"
    if t == "idea":
        return "Irá a: tus ideas (Cerebro › Bandeja; Zazu la clasifica)"
    if t == "proyecto":
        return "Irá a: tus tareas de Google, como proyecto (Zazu lo prepara)"
    if t == "aplicar":
        return "Irá a: tus tareas de Google, como candidatura (Zazu la prepara)"
    if t == "investigar":
        return "Irá a: tus tareas de Google, como tema por investigar (Zazu lo investiga)"
    if t == "completar":
        return f"Se marcará como hecha tu tarea de Google «{it.get('titulo', '')}»"
    if t == "reprogramar":
        return f"Cambiará la fecha de tu tarea de Google «{it.get('titulo', '')}»" + (f" al {fc}" if fc else "")
    return it.get("destino") or ""


def _item_reglas(p):
    """Propuesta de las reglas → elemento de la lista (mismos campos + destino llano)."""
    it = dict(p)
    it.pop("items", None)
    it.setdefault("relacionado", None)
    it.setdefault("duplicado", False)
    it["destino_txt"] = destino_txt(it)
    return it


def _con_reglas(p, como, motivo=None):
    if p["tipo"] in ("fuera_de_ambito", "privado"):
        p["entendido_con"] = como
        return p
    it = _item_reglas(p)
    p.update(relacionado=None, duplicado=False, destino_txt=it["destino_txt"], items=[it], entendido_con=como, motivo_reglas=motivo)
    return p


def _item_modelo(it, ctx, cuenta, ahora, url):
    """Un elemento validado del modelo → propuesta (dict). ctx = {"eventos":[…]|None,"tareas":[…]|None}."""
    tipo, hoy = it["tipo"], ahora.date()
    evs, tas = ctx.get("eventos"), ctx.get("tareas")
    rel_obj = None
    if it["relacionado"]:
        lista = evs if it["relacionado"]["tipo"] == "evento" else tas
        rel_obj = lista[it["relacionado"]["indice"] - 1]
    avisos = []
    if (tipo in ("tarea", "evento")) and (evs is None or tas is None):
        avisos.append("No pude comprobar si ya existe en tu agenda o tus tareas.")
    base = {"ok": True, "tipo": tipo, "fecha": None, "hora": None, "confirmable": True, "falta": [], "aviso": None, "cuenta": cuenta,
            "relacionado": None, "duplicado": False}
    if rel_obj:
        base["relacionado"] = {"tipo": it["relacionado"]["tipo"], "titulo": rel_obj["titulo"], "fecha": rel_obj.get("fecha"), "hora": rel_obj.get("hora"),
                               "etiqueta": _etiqueta_rel(it["relacionado"]["tipo"], rel_obj)}

    def cerrar(p, resumen):
        p["resumen"] = resumen
        p["aviso"] = " ".join(avisos) or None
        p["destino_txt"] = destino_txt(p)
        return p

    if tipo == "tarea":
        titulo = cap(it["titulo"].strip(" ,;:.-–—"))
        hora = it["hora"]
        if hora:
            titulo = f"{titulo} ({hora})"
        titulo = titulo[:200]
        fecha, de_evento = it["fecha"], False
        if not fecha and rel_obj and it["relacionado"]["tipo"] == "evento" and rel_obj.get("fecha"):
            fecha, de_evento = rel_obj["fecha"], True
        dup = next((t for t in (tas or []) if _norm(t["titulo"]) == _norm(titulo)), None)
        if not dup and it["duplicado"] and rel_obj and it["relacionado"]["tipo"] == "tarea":
            dup = rel_obj
        if dup:
            base["duplicado"] = True
            avisos.insert(0, f"Ya tienes esta tarea: {_etiqueta_rel('tarea', dup)}. Si la confirmas, quedará repetida.")
        elif it["duplicado"]:
            base["duplicado"] = True
            avisos.insert(0, "Parece que ya lo tienes apuntado. Si lo confirmas, quedará repetido.")
        if de_evento:
            avisos.append(f"He puesto el día de «{rel_obj['titulo']}» ({_fecha_corta(fecha)}).")
        elif not fecha:
            avisos.append("Sin fecha: quedará en Tareas sin día.")
        p = dict(base, titulo=titulo, fecha=fecha, hora=hora, destino=f"Google Tareas [{cuenta}]",
                 campos={"titulo": titulo, "due": fecha, "cuenta": cuenta})
        return cerrar(p, f"Tarea: {titulo}" + (f" · {_fecha_txt(date.fromisoformat(fecha))}" if fecha else " · sin fecha"))

    if tipo == "evento":
        titulo = cap(it["titulo"].strip(" ,;:.-–—"))[:200]
        fecha, hora, fin = it["fecha"], (None if it["todo_dia"] else it["hora"]), (None if it["todo_dia"] else it["fin"])
        if not fecha and rel_obj and it["relacionado"]["tipo"] == "evento" and rel_obj.get("fecha"):
            fecha = rel_obj["fecha"]
        todo_dia = fecha is not None and hora is None
        if hora and not fin:
            ini = datetime.combine(date.fromisoformat(fecha), datetime.min.time()).replace(hour=int(hora[:2]), minute=int(hora[3:])) if fecha else None
            if ini:
                e = min(ini + timedelta(hours=1), ini.replace(hour=23, minute=59))
                fin = f"{e:%H:%M}" if e > ini else None
        if hora and fin and fin <= hora:
            fin = None
        dup = next((e for e in (evs or []) if e["fecha"] == fecha and _norm(e["titulo"]) == _norm(titulo)), None)
        if not dup and rel_obj and it["relacionado"]["tipo"] == "evento" and (it["duplicado"] or rel_obj.get("fecha") == fecha):
            dup = rel_obj
        if dup:
            base["duplicado"] = True
            avisos.insert(0, f"Ya tienes este evento: {_etiqueta_rel('evento', dup)}. Si lo confirmas, quedará repetido.")
        elif rel_obj and it["relacionado"]["tipo"] == "evento":
            avisos.insert(0, f"Ya hay {_etiqueta_rel('evento', rel_obj)}. Si es una cita distinta, confírmala; si no, cancela.")
        falta = [] if fecha else ["fecha"]
        p = dict(base, titulo=titulo, fecha=fecha, hora=hora, fin=fin, todo_dia=todo_dia, destino=f"Google Calendar [{cuenta}]",
                 campos={"titulo": titulo, "fecha": fecha, "hora": hora, "fin": fin, "todo_dia": todo_dia, "cuenta": cuenta})
        p["falta"], p["confirmable"] = falta, not falta
        if falta:
            avisos.insert(0, it["pregunta"] or "¿Para qué día? Escríbelo con la fecha («el viernes a las 10»).")
        elif todo_dia:
            avisos.append("Sin hora: lo apunto de todo el día.")
        return cerrar(p, f"Evento: {titulo}" + (f" · {_fecha_txt(date.fromisoformat(fecha), hora)}" + (f"–{fin}" if fin else "") if fecha else " · ¿qué día?"))

    if tipo in ("nota", "idea"):
        texto = it["texto"] or it["titulo"]
        titulo = cap(re.split(r"[.\n]", it["titulo"])[0][:60])
        p = dict(base, titulo=titulo, texto=texto, destino="Cerebro › 10 Bandeja" + (" (Zazu la pasa a Ideas)" if tipo == "idea" else ""))
        return cerrar(p, f"{'Idea' if tipo == 'idea' else 'Nota'}: {texto[:100]}")

    if tipo in ("proyecto", "aplicar", "investigar"):
        titulo = f"{VERBO_DE[tipo]}: {it['titulo'].strip(' ,;:.-–—')}"
        if url and tipo in ("aplicar", "investigar"):
            titulo += f" {url}"
        titulo = titulo[:300]
        p = dict(base, titulo=titulo, destino=f"Google Tareas [{cuenta}] · Zazu la procesa", campos={"titulo": titulo, "due": None, "cuenta": cuenta})
        return cerrar(p, f"{titulo[:100]} → tarea en Google Tareas; el vigía de la bandeja se encarga")

    # modificar: solo completar o cambiar el día de una tarea que ya existe (la elige el índice, el id sale de nuestra lista)
    o = rel_obj
    etq = o.get("cuenta") or cuenta
    campos = {"id": o["id"], "email": o["email"], "cuenta": etq, "titulo": o["titulo"]}
    if it["accion"] == "completar":
        p = dict(base, tipo="completar", titulo=o["titulo"], fecha=o.get("fecha"), destino=f"Google Tareas [{etq}]", campos=dict(campos, accion="completar"))
        return cerrar(p, f"Marcar como hecha: {o['titulo']}")
    p = dict(base, tipo="reprogramar", titulo=o["titulo"], fecha=it["fecha"], destino=f"Google Tareas [{etq}]", campos=dict(campos, accion="fecha", due=it["fecha"]))
    if o.get("fecha") == it["fecha"]:
        p["confirmable"] = False
        avisos.insert(0, "Esa tarea ya está para ese día.")
    elif o.get("fecha"):
        avisos.insert(0, f"Ahora está para el {_fecha_corta(o['fecha'])}.")
    return cerrar(p, f"Cambiar la fecha de «{o['titulo']}» a {_fecha_txt(date.fromisoformat(it['fecha']))}")


CUE_HECHO = re.compile(r"\b(?:hech[oa]s?|complet\w+|terminad[oa]s?|acabad[oa]s?|tacha\w*|quita\w*|cierra\w*|resuelt[oa]s?|listo|lista|ya (?:he|ha|esta|estan|lo|la|esta)\b)")


def _sin_confundir(i, texto, ctx):
    """Red de seguridad: «completar» una tarea solo si Fran habló de hecho/terminado. Si no («comprar pilas» y ya hay una tarea igual) es una
    tarea NUEVA repetida, no un «marcar como hecha»."""
    if i["tipo"] == "modificar" and i["accion"] == "completar" and not CUE_HECHO.search(fold(texto)):
        o = ctx["tareas"][i["relacionado"]["indice"] - 1]
        return dict(i, tipo="tarea", accion=None, titulo=o["titulo"], fecha=None, duplicado=True)
    return i


def entender_orden(texto, ahora=None, cuenta="varas", contexto=None):
    """Misma salida que interpretar() más: `items` (lista de propuestas; una por cosa, hasta 5), `entendido_con` ("haiku"|"reglas"),
    `relacionado` y `duplicado`. `contexto()` → {"eventos":[…]|None,"tareas":[…]|None}. Lanza ValueError con texto vacío o enorme."""
    if not isinstance(texto, str):
        raise ValueError("texto no válido")
    t = limpiar(texto)
    if not t:
        raise ValueError("texto vacío")
    if len(t) > MAX_TEXTO:
        raise ValueError("texto demasiado largo")
    ahora = ahora or datetime.now(TZ)
    if PREFIJO_FIJO.match(fold(t)):                       # «Aplicar: …», «Idea: …»: deterministas, sin modelo
        return _con_reglas(interpretar(t, ahora, cuenta), "reglas")
    if privado.es_privado(t):
        return dict(_privado(), entendido_con="reglas")
    if not entender.puede():
        return _con_reglas(interpretar(t, ahora, cuenta), "reglas", "sin_ia")
    ctx = {"eventos": None, "tareas": None}
    if contexto:
        try:
            c = contexto() or {}
            ctx = {"eventos": c.get("eventos"), "tareas": c.get("tareas")}
        except Exception:                                  # sin lista de lo que ya existe se sigue igual
            pass
    ctx = {k: ([x for x in v[:entender.MAX_EVENTOS if k == "eventos" else entender.MAX_TAREAS]] if isinstance(v, list) else None) for k, v in ctx.items()}
    urls = URL_RX.findall(t)
    res, estado = entender.consultar(URL_RX.sub("[enlace]", t), ahora, ctx["eventos"], ctx["tareas"])
    if not res:
        return _con_reglas(interpretar(t, ahora, cuenta), "reglas", estado)
    utiles = [i for i in res["items"] if i["tipo"] != "hermes"]
    if not utiles:
        return dict(FUERA, texto=t, entendido_con="haiku")
    utiles = [_sin_confundir(i, t, ctx) for i in utiles]
    url = urls[0] if len(urls) == 1 and sum(i["tipo"] in ("aplicar", "investigar") for i in utiles) == 1 else None
    try:
        items = [_item_modelo(i, ctx, cuenta, ahora, url) for i in utiles]
    except (KeyError, TypeError, ValueError, IndexError):  # no cuadra con lo que tenemos: mejor las reglas
        return _con_reglas(interpretar(t, ahora, cuenta), "reglas", "invalido")
    generales = []
    if len(utiles) < len(res["items"]):
        generales.append("Una parte de la frase mejor la hablamos en el chat: no la he apuntado.")
    if res["recortado"]:
        generales.append(f"Solo he cogido las {entender.MAX_ITEMS} primeras cosas.")
    if len(items) == 1:
        p = dict(items[0])
    else:
        p = {"ok": True, "tipo": "varios", "titulo": f"{len(items)} cosas", "fecha": None, "hora": None, "destino": "Varios destinos",
             "destino_txt": "Cada cosa irá a su sitio", "resumen": " · ".join(i["titulo"] for i in items)[:200], "confirmable": any(i["confirmable"] for i in items),
             "falta": [], "aviso": None, "cuenta": cuenta, "relacionado": None, "duplicado": any(i["duplicado"] for i in items)}
    p["items"] = items
    p["entendido_con"] = "haiku"
    if generales:
        p["aviso_general"] = " ".join(generales)
    return p


def publica(p):
    """Lo que se manda al navegador: igual que la propuesta, sin el correo de la cuenta de las tareas que se van a tocar."""
    def limpia(x):
        x = dict(x)
        if isinstance(x.get("campos"), dict):
            x["campos"] = {k: v for k, v in x["campos"].items() if k != "email"}
        return x
    out = limpia(p)
    if "items" in p:
        out["items"] = [limpia(i) for i in p["items"]]
    return out


# ───────────────────────── propuestas y ejecución ─────────────────────────
class Propuestas:
    """Propuestas pendientes en memoria (15 min, máx. 50). Una propuesta se ejecuta UNA vez: el segundo «confirmar»
    devuelve lo que ya se hizo."""
    def __init__(self):
        self.lock = threading.Lock()
        self.d = {}

    def _purgar(self):
        ahora = time.time()
        for k in [k for k, v in self.d.items() if ahora - v["t"] > CADUCA_S]:
            del self.d[k]
        while len(self.d) > 50:
            del self.d[min(self.d, key=lambda k: self.d[k]["t"])]

    def guardar(self, owner, p):
        with self.lock:
            self._purgar()
            pid = "p_" + secrets.token_urlsafe(9)
            self.d[pid] = {"t": time.time(), "owner": owner, "p": p, "estado": "pendiente", "res": None, "hechos": {}, "sel": None}
            return pid

    def tomar(self, owner, pid, marcados=None):
        """Reserva la propuesta para ejecutarla. `marcados` = posiciones (0…) de las cosas marcadas en la hoja; None = todas las que se pueden
        apuntar. Deja la selección en r["sel"]."""
        with self.lock:
            self._purgar()
            r = self.d.get(str(pid))
            if not r or r["owner"] != owner:
                raise OrdenError(410, "Esa propuesta caducó. Escríbela otra vez.")
            if r["estado"] == "hecha":
                raise OrdenError(409, "Ya lo hice.", creado=r["res"])
            if r["estado"] == "ejecutando":
                raise OrdenError(409, "Ya lo estoy haciendo.")
            items = r["p"].get("items") or [r["p"]]
            if marcados is None:
                sel = [i for i, it in enumerate(items) if it.get("confirmable")]
            else:
                if (not isinstance(marcados, list) or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(items) for i in marcados)
                        or len(set(marcados)) != len(marcados)):
                    raise OrdenError(400, "Lo marcado no es válido.")
                sel = sorted(marcados)
                if not sel:
                    raise OrdenError(400, "No has marcado nada.")
                if not all(items[i].get("confirmable") for i in sel):
                    raise OrdenError(400, "Hay algo marcado que todavía no se puede apuntar.")
            if not sel:
                raise OrdenError(400, r["p"].get("aviso") or "Falta algún dato para poder apuntarlo.")
            r["estado"], r["sel"] = "ejecutando", sel
            return r

    def terminar(self, r, res):
        with self.lock:
            r["estado"], r["res"] = "hecha", res

    def liberar(self, r):
        with self.lock:
            r["estado"] = "pendiente"


PROPUESTAS = Propuestas()


def comprobar(args):
    """Solo estas formas exactas: `tasks add @default --title=… [--due=AAAA-MM-DD]`, `tasks done @default <id>`, `tasks update @default <id> --due=AAAA-MM-DD` y
    `calendar create primary --summary=… --from=… --to=… [--start-timezone --end-timezone --all-day --location]`."""
    if len(args) >= 2 and tuple(args[:2]) in SOBRE_TAREA:      # `tasks done @default <id>` · `tasks update @default <id> --due=AAAA-MM-DD`
        if len(args) < 4 or args[2] != "@default" or not ID_TAREA.fullmatch(str(args[3])):
            raise PermissionError("tarea no válida")
        resto = args[4:]
        if tuple(args[:2]) == ("tasks", "done") and resto:
            raise PermissionError("opción no permitida")
        if tuple(args[:2]) == ("tasks", "update") and not (len(resto) == 1 and re.fullmatch(r"--due=\d{4}-\d{2}-\d{2}", resto[0])):
            raise PermissionError("opción no permitida")
        return args
    if len(args) < 3 or tuple(args[:2]) not in PERMITIDO:
        raise PermissionError("acción fuera de la lista cerrada")
    destino, flags = PERMITIDO[tuple(args[:2])]
    if args[2] != destino:
        raise PermissionError("destino no permitido")
    vistos = set()
    for a in args[3:]:
        k = a.split("=", 1)[0]
        if a in SOLO_SIN_VALOR and tuple(args[:2]) == ("calendar", "create"):
            continue
        if "=" not in a or k not in flags or k in vistos:
            raise PermissionError(f"opción no permitida: {k[:20]}")
        vistos.add(k)
    if tuple(args[:2]) == ("tasks", "add") and "--title" not in vistos:
        raise PermissionError("falta el título")
    return args


def _cuenta(env, servicio, tag):
    cs = env.cuentas_con(servicio)
    if not cs:
        raise OrdenError(503, f"Ninguna cuenta de Google tiene permiso de {'Tareas' if servicio == 'tasks' else 'Calendario'}.")
    return next((c for c in cs if env.etiqueta(c) == tag), cs[0])


def _id_corto(d):
    try:
        x = d.get("task", d) if isinstance(d, dict) else {}
        x = x.get("event", x)
        return str(x.get("id") or "")[-4:] or None
    except AttributeError:
        return None


def ejecutar(p, env, ahora=None):
    """Hace lo que la propuesta enseñó, por la lista cerrada. `env` aporta gog, cuentas_con, etiqueta, nota_rapida, invalidar."""
    tipo, c = p["tipo"], p.get("campos") or {}
    if tipo == "nota":
        env.nota_rapida(p["texto"])
        return {"tipo": "nota", "donde": "Cerebro › 10 Bandeja", "titulo": p["titulo"], "id": None}
    if tipo == "idea":
        env.nota_rapida(p["texto"], tipo="idea")
        return {"tipo": "idea", "donde": "Cerebro › 10 Bandeja (Zazu la pasa a Ideas)", "titulo": p["titulo"], "id": None}
    if tipo in ("tarea", "aplicar", "investigar", "proyecto"):
        email = _cuenta(env, "tasks", c.get("cuenta"))
        due = c.get("due")
        args = comprobar(["tasks", "add", "@default", f"--title={limpiar(c['titulo'])[:300]}"] + ([f"--due={due}"] if due and re.fullmatch(r"\d{4}-\d{2}-\d{2}", due) else []))
        d = env.gog(args, email, write=True)
        env.invalidar()
        return {"tipo": tipo, "donde": f"Google Tareas [{env.etiqueta(email)}]", "titulo": c["titulo"], "id": _id_corto(d)}
    if tipo in ("completar", "reprogramar"):
        email = c.get("email")
        if email not in env.cuentas_con("tasks"):
            raise OrdenError(503, "Esa cuenta de Google ya no tiene permiso de Tareas.")
        if tipo == "completar":
            args = comprobar(["tasks", "done", "@default", str(c["id"])])
        else:
            args = comprobar(["tasks", "update", "@default", str(c["id"]), f"--due={c['due']}"])
        env.gog(args, email, write=True)
        env.invalidar()
        return {"tipo": tipo, "donde": f"Google Tareas [{env.etiqueta(email)}]", "titulo": c["titulo"], "id": str(c["id"])[-4:]}
    if tipo == "evento":
        email = _cuenta(env, "calendar", c.get("cuenta"))
        f = date.fromisoformat(c["fecha"])
        if c.get("todo_dia"):
            args = ["calendar", "create", "primary", f"--summary={c['titulo']}", f"--from={f.isoformat()}", f"--to={(f + timedelta(days=1)).isoformat()}", "--all-day"]
        else:
            hi, hf = c["hora"], c.get("fin") or None
            ini = datetime.combine(f, datetime.strptime(hi, "%H:%M").time(), TZ)
            fin = datetime.combine(f, datetime.strptime(hf, "%H:%M").time(), TZ) if hf else ini + timedelta(hours=1)
            if fin <= ini:
                fin = ini + timedelta(hours=1)
            args = ["calendar", "create", "primary", f"--summary={c['titulo']}", f"--from={ini.isoformat(timespec='seconds')}",
                    f"--to={fin.isoformat(timespec='seconds')}", "--start-timezone=Europe/Madrid", "--end-timezone=Europe/Madrid"]
        d = env.gog(comprobar(args), email, write=True)
        env.invalidar()
        return {"tipo": "evento", "donde": f"Google Calendar [{env.etiqueta(email)}]", "titulo": c["titulo"], "id": _id_corto(d)}
    raise OrdenError(400, "Esa propuesta no se puede ejecutar.")


def confirmar(owner, pid, env, marcados=None):
    """Apunta lo marcado (por defecto, todo lo que se pueda). → {"creado": el primero, "creados": [...], "fallos": [...]}.
    Cada cosa se ejecuta sola por `ejecutar` (lista cerrada); si una falla las demás siguen y la propuesta queda viva para reintentar
    SOLO lo que falló. Si no se pudo apuntar nada, el error es el de siempre (502/503/400)."""
    r = PROPUESTAS.tomar(owner, pid, marcados)
    items = r["p"].get("items") or [r["p"]]
    creados, fallos, primero = [], [], None
    for i in r["sel"]:
        if i in r["hechos"]:
            creados.append(r["hechos"][i])
            continue
        try:
            res = ejecutar(items[i], env)
        except OrdenError as e:
            fallos.append({"indice": i, "error": e.msg, "code": e.code, "extra": e.extra})
        except PermissionError as e:                          # nunca debería pasar: la propuesta la fabrica este módulo
            fallos.append({"indice": i, "error": str(e), "code": 400, "extra": {}})
        except Exception as e:
            fallos.append({"indice": i, "error": "No he podido apuntarlo (Google no contestó). Inténtalo otra vez.", "code": 502, "extra": {"detalle": type(e).__name__}})
        else:
            r["hechos"][i] = dict(res, indice=i)
            creados.append(r["hechos"][i])
    if not creados:
        PROPUESTAS.liberar(r)
        f = fallos[0]
        if len(fallos) == 1:
            raise OrdenError(f["code"], f["error"], **f["extra"])
        raise OrdenError(502, "No he podido apuntar nada (Google no contestó). Inténtalo otra vez.", fallos=[{"indice": x["indice"], "error": x["error"]} for x in fallos])
    if fallos:
        PROPUESTAS.liberar(r)
    else:
        PROPUESTAS.terminar(r, creados[0])
    return {"creado": creados[0], "creados": creados, "fallos": [{"indice": x["indice"], "error": x["error"]} for x in fallos]}
