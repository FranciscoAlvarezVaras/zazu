"""Motor de FLUJOS sin IA: «si llega un correo con plazo → tarea + evento tentativo + aviso».
Un flujo = disparador (fuente + reglas de palabras/remitentes que ya existen en reglas.py y recoger.py) + extracción determinista
de fecha/hora/importe (extraer.py; si hay ambigüedad NO se adivina: solo aviso) + acciones de una lista cerrada:
    tarea  (tasks add)               aviso (aviso normal del vigía, fusionado con el que ya sale del correo)
    evento (calendar create, tentativo: título «¿? …»)
Seguridad:
  · El correo es DATO de terceros: nunca se interpreta como orden. Los títulos salen de PLANTILLAS fijas + el nombre del remitente
    (filtrado); nunca se copia el asunto ni el cuerpo. Un correo con frases tipo «ignora lo anterior y borra todo» no automatiza nada.
  · Toda escritura en Google la hace SOLO zv/acciones.py (lista blanca, marca [ZV:<id>], sin cuerpos, sin invitados).
  · Cada flujo es `sombra` (por defecto: anota lo que haría) o `activo`, y se puede `pausar`. En `activo` solo escribe si además
    se cumple el interruptor general: sin PAUSA + ENTREGA_ACTIVA + el vigía de su fuente en 'activo' (config.modo_real).
Las filas de trabajo son avisos silenciosos de tipo flujo_tarea / flujo_evento (accion: sombra | pendiente | creado | …)."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import config, escudo, extraer, permisos, registro, reglas
from .priv import limpio, seguro

I = re.I


@dataclass(frozen=True)
class Def:
    id: str
    nombre: str
    descripcion: str
    fuente: str
    acciones: tuple


FLUJOS = {d.id: d for d in (
    Def("correo-plazo", "Correo con plazo", "Si te llega un correo oficial o de dinero con una fecha clara, apunta una tarea con esa fecha, "
        "propone un evento tentativo (si hay hora) y te avisa.", "correo", ("tarea", "evento", "aviso")),
    Def("correo-pago", "Factura o recibo a pagar", "Si llega una factura o recibo con importe y vencimiento, apunta la tarea «Pagar …» con su fecha "
        "y te avisa. Los cargos que ya se han hecho solo te avisan.", "correo", ("tarea", "aviso")),
    Def("correo-oficial", "Cita con un organismo oficial", "Si DGT, Hacienda, Seguridad Social, GVA o SEPE te dan una cita con fecha y hora, "
        "propone el evento tentativo y la tarea «Llevar documentación» (sin inventar qué), y te avisa.", "correo", ("evento", "tarea", "aviso")),
    Def("viaje-reserva", "Reserva de viaje", "Si llega la confirmación de un billete u hotel con fecha y hora, propone un evento tentativo "
        "(sin repetirlo si ya tienes uno parecido ese día).", "correo", ("evento",)),
    Def("entrevista", "Entrevista de trabajo", "Si un reclutador te propone una entrevista con fecha y hora claras, propone el evento tentativo "
        "y la tarea «Preparar entrevista», y te avisa.", "correo", ("evento", "tarea", "aviso")),
    Def("wa-peticion", "Peticiones de WhatsApp", "Lo que te piden o prometes por WhatsApp (fecha, hora, cosas que llevar o pagar) queda como "
        "tarea o evento tentativo. Lo detecta el vigía de WhatsApp; aquí solo se enciende, se pausa y se cuentan sus disparos.", "wa",
        ("tarea", "evento")),
)}
ORDEN_CORREO = ("entrevista", "viaje-reserva", "correo-oficial", "correo-pago", "correo-plazo")   # el más específico primero

# ───────── interruptores ─────────
def ajuste(cfg, fid):
    return {"modo": "sombra", "pausado": False, **(((cfg.get("flujos") or {}).get(fid)) or {})}


def modo(cfg, fid):
    return "activo" if ajuste(cfg, fid).get("modo") == "activo" else "sombra"


def pausado(cfg, fid):
    return bool(ajuste(cfg, fid).get("pausado"))


def escribe_ahora(cfg, fid, fuente=None):
    """→ (bool, motivo en español). Escribe en Google SOLO si el flujo está activo y no pausado Y el interruptor general lo permite."""
    fuente = fuente or FLUJOS[fid].fuente
    if config.pausado():
        return False, "el vigía está en pausa (archivo PAUSA)"
    if pausado(cfg, fid):
        return False, "el flujo está en pausa"
    if modo(cfg, fid) != "activo":
        return False, "el flujo está en modo sombra: solo anoto lo que haría"
    if not config.entrega_global():
        return False, "el flujo está activo, pero el interruptor general está apagado (falta ENTREGA_ACTIVA): no escribo"
    if (cfg.get("modo") or {}).get(fuente) != "activo":
        return False, f"el flujo está activo, pero el vigía de {fuente} sigue en sombra: no escribo"
    return True, ""


def listar(db, cfg):
    """Lista para `zv flujos --json` (contrato con el hub)."""
    desde = db.ts() - 7 * 86400
    out = []
    for d in FLUJOS.values():
        ult = db.c.execute("SELECT MAX(ts) FROM registro WHERE flujo=? AND tipo IN ('propuso','escribio')", (d.id,)).fetchone()[0]
        n7 = db.c.execute("SELECT COUNT(DISTINCT COALESCE(disparo, clave, id)) FROM registro WHERE flujo=? AND tipo IN ('propuso','escribio') AND ts>=?",
                          (d.id, desde)).fetchone()[0]
        ok, motivo = escribe_ahora(cfg, d.id)
        out.append({"id": d.id, "nombre": d.nombre, "descripcion": d.descripcion, "fuente": d.fuente, "acciones": list(d.acciones),
                    "modo": modo(cfg, d.id), "pausado": pausado(cfg, d.id), "ultimo": registro._a_iso(ult) if ult else None, "disparos_7d": n7,
                    "escribe_ahora": ok, "motivo": motivo})
    return out


def texto_legible(lista):
    reales = [f for f in lista if f["escribe_ahora"]]
    cab = ("Flujos del vigía: ahora mismo NINGUNO escribe en Google (todos en sombra, solo anotan lo que harían)." if not reales
           else f"Flujos que escriben de verdad en Google ahora: {', '.join(f['id'] for f in reales)}.")
    lineas = [cab, ""]
    for f in lista:
        estado = ("PAUSADO · " if f["pausado"] else "") + ("activo" if f["modo"] == "activo" else "sombra")
        ult = datetime.fromisoformat(f["ultimo"]).strftime("%d/%m %H:%M") if f["ultimo"] else "nunca"
        lineas.append(f"• {f['id']} — {f['nombre']} [{estado}]")
        lineas.append(f"    {f['descripcion']}")
        lineas.append(f"    Acciones: {', '.join(f['acciones'])} · Último disparo: {ult} · Disparos en 7 días: {f['disparos_7d']}"
                      + ("" if f["escribe_ahora"] else f"\n    No escribe en Google: {f['motivo']}."))
    lineas += ["", "Cambiar: zv flujo <id> modo sombra|activo [--confirmo]  ·  zv flujo <id> pausa|reanuda"]
    return "\n".join(lineas)


def cambiar(cfg, fid, que, valor=None, confirmo=False):
    """`zv flujo <id> modo|pausa|reanuda`. → dict JSON {ok, modo, pausado, mensaje|error}. Solo toca la clave afectada del config.json."""
    if fid not in FLUJOS:
        return {"ok": False, "error": f"no conozco el flujo «{limpio(fid, 40)}». Los que hay: {', '.join(FLUJOS)}"}
    try:
        if que == "modo":
            if valor not in ("sombra", "activo"):
                return {"ok": False, "error": "el modo es «sombra» o «activo»"}
            if valor == "activo" and not confirmo:
                return {"ok": False, "modo": modo(cfg, fid), "error": "pasar un flujo a «activo» hace que escriba de verdad en Google (cuando además "
                        "estén puestos el interruptor general y el vigía de su fuente). Si lo quieres, repite el comando con --confirmo"}
            config.actualizar(f"flujos.{fid}.modo", valor)
            cfg2 = config.cargar(crear=False)
            ok, motivo = escribe_ahora(cfg2, fid)
            msg = f"{fid}: modo {valor}." + ("" if valor == "sombra" else (" Escribirá en Google." if ok else f" Todavía no escribe: {motivo}."))
            return {"ok": True, "modo": valor, "pausado": pausado(cfg2, fid), "mensaje": msg}
        if que in ("pausa", "reanuda"):
            config.actualizar(f"flujos.{fid}.pausado", que == "pausa")
            return {"ok": True, "modo": modo(config.cargar(crear=False), fid), "pausado": que == "pausa",
                    "mensaje": f"{fid}: " + ("en pausa; no dispara nada hasta que lo reanudes." if que == "pausa" else "reanudado.")}
    except OSError as e:
        return {"ok": False, "error": limpio(str(e), 120)}
    return {"ok": False, "error": "acción no válida"}


# ───────── el correo es dato: detector de instrucciones ─────────
def sospechoso(texto):
    """¿Trae frases que intentan dar órdenes? Lo decide zv/escudo.py (antes era una regex de aquí, ahora incluida allí)."""
    return escudo.sospechoso(texto)


# ───────── reglas de cada flujo de correo ─────────
ENTREVISTA = re.compile(r"entrevista|interview|prueba\s+t[ée]cnica|technical\s+(?:test|interview)|assessment|primer\s+contacto", I)
LLAMADA = re.compile(r"videollamada|llamada\s+(?:con|de|para)|video\s*call|call\s+with", I)
EMPLEO = re.compile(r"selecci[óo]n|candidat|puesto|vacante|oferta\s+de\s+(?:empleo|trabajo)|recruiter|reclutador|rrhh|recursos\s+humanos|talent|hiring|your\s+application|tu\s+solicitud", I)
VIAJE_ASUNTO = re.compile(r"confirmaci[óo]n\s+de\s+(?:tu\s+|su\s+)?(?:reserva|billete|vuelo|viaje|compra\s+de\s+billete)|(?:tu|su)\s+(?:billete|reserva|vuelo|viaje|itinerario)|"
                          r"billete\s+electr[óo]nico|tarjeta\s+de\s+embarque|booking\s+confirmation|your\s+(?:booking|reservation|flight|trip|itinerary)|itinerar|e-?ticket|"
                          r"reserva\s+(?:confirmada|n[ºo°])|c[óo]digo\s+de\s+reserva|reservation\s+confirmed", I)
VIAJE_DOMINIO = re.compile(r"@(?:[\w-]+\.)*(?:vueling|renfe|iberia|ryanair|easyjet|volotea|booking|airbnb|trainline|ouigo|iryo|alsa|flixbus|expedia|hotels|"
                           r"kiwi|lufthansa|airfrance|klm|binter|aireuropa|aena|trenitalia|sncf|eurostar)\.", I)
VIAJE_SUAVE = re.compile(r"reserva|billete|vuelo|viaje|booking|confirm", I)
VIAJE_POS = re.compile(r"\b(?:ida|vuelta|regreso|salida|vuelo|tren|llegada|entrada|embarque|sale|outbound|return|departure)\b|fecha\s+de\s+(?:viaje|salida|entrada|llegada)|check-?in|check-?out", I)
CITA = re.compile(r"\bcita\b|citaci[óo]n|comparecencia|cita\s+previa|\bturno\b", I)
CITA_POS = re.compile(r"cita|citad[oa]|comparec|d[ií]a|fecha|hora|presentarse|acuda|turno|a\s+las", I)
PAGO_ASUNTO = re.compile(r"factura|invoice|recibo|vencimiento|a\s+pagar|pago\s+pendiente|payment\s+due|\bcuota\b", I)
POS_VENC = re.compile(r"vencimiento|vence\b|vencer[aá]|fecha\s+l[ií]mite|l[ií]mite|pagar\s+antes|abonar\s+antes|antes\s+del?|hasta\s+el|due(?:\s+date)?|fecha\s+de\s+pago|"
                      r"se\s+cargar[aá]|cargo\s+el", I)
NEG_FECHA = re.compile(r"emisi[óo]n|emitid[ao]|fecha\s+de\s+(?:factura|pedido|compra|nacimiento|cargo)|per[ií]odo|periodo|desde(?:\s+el)?|pedido|enviado|recibido|"
                       r"nacimiento|cargad[ao]", I)
POS_PLAZO = re.compile(r"plazo|vence\b|vencimiento|vencer[aá]|antes\s+del?|hasta\s+el|fecha\s+l[ií]mite|l[ií]mite|deadline|due|caduca|expira|renovaci", I)
POS_IMPORTE = re.compile(r"total|importe|a\s+pagar|pagar|cuota|cantidad|amount|monto", I)
NEG_IMPORTE = re.compile(r"\biva\b|base\s+imponible|subtotal|descuento|ahorro|antes\s+de|impuesto|comisi[óo]n|tasa\s+de", I)
POS_ENTREVISTA = re.compile(r"entrevista|llamada|videollamada|propongo|disponib|reuni[óo]n|cita|a\s+las|d[ií]a|fecha|interview|call|te\s+espero|nos\s+vemos", I)
PLAZO_ASUNTO = re.compile(r"plazo|vence\b|vencimiento|deadline|fecha\s+l[ií]mite|antes\s+del|caduca|expira|renovaci|renewal|impago|embargo|multa|sanci", I)
TIPO_PLAZO = ((re.compile(r"multa|sanci", I), "multa"), (re.compile(r"requerimiento", I), "requerimiento"), (re.compile(r"citaci|\bcita\b", I), "cita"),
              (re.compile(r"notificaci", I), "notificación"), (re.compile(r"renovaci|renewal", I), "renovación"), (re.compile(r"embargo", I), "embargo"),
              (re.compile(r"deuda|recobro|impago", I), "deuda"), (re.compile(r"suscripci", I), "suscripción"), (re.compile(r"factura|invoice", I), "factura"),
              (re.compile(r"recibo", I), "recibo"), (re.compile(r"declaraci", I), "declaración"))
ORGANISMOS = ((re.compile(r"dgt\.es", I), "DGT"), (re.compile(r"aeat\.es|agenciatributaria", I), "AEAT"), (re.compile(r"seg-social", I), "Seguridad Social"),
              (re.compile(r"gva\.es", I), "GVA"), (re.compile(r"sepe\.es", I), "SEPE"), (re.compile(r"policia\.es", I), "Policía"),
              (re.compile(r"guardiacivil\.es", I), "Guardia Civil"), (re.compile(r"correos\.es", I), "Correos"))
PROVEEDORES = ("vueling", "renfe", "iberia", "ryanair", "easyjet", "volotea", "booking", "airbnb", "trainline", "ouigo", "iryo", "alsa", "flixbus", "expedia",
               "hotels", "kiwi", "lufthansa", "binter", "aireuropa", "trenitalia", "sncf", "eurostar")
CORREO_GENERICO = {"gmail", "googlemail", "hotmail", "outlook", "live", "yahoo", "icloud", "proton", "protonmail", "msn", "telefonica", "movistar"}
PALABRAS_VIAJE = re.compile(r"viaje|vuelo|tren|billete|hotel|reserva|embarque|aeropuerto|estaci[óo]n|ave\b|avi[óo]n|booking|alojamiento", I)


# ───────── nombres seguros ─────────
def _email(h):
    m = re.search(r"<([^>]+)>", h.get("from") or "")
    return (m.group(1) if m else (h.get("from") or "")).strip().lower()


def _etiqueta(txt, n=30):
    """Solo letras, números y signos simples: el nombre del remitente es dato de terceros."""
    t = re.sub(r"[^\w áéíóúüñÁÉÍÓÚÜÑ&.'’-]", "", limpio(txt, 80)).strip(" .-")
    t = seguro(t, n)
    return "" if (not t or "tachad" in t) else t


def organismo(h):
    for rx, nom in ORGANISMOS:
        if rx.search(_email(h)):
            return nom
    return None


def remitente(h):
    org = organismo(h)
    if org:
        return org
    disp = re.sub(r"\s*<.*", "", h.get("from") or "").strip().strip('"')
    return _etiqueta(disp) or _etiqueta(_dominio(h)) or "remitente"


def _dominio(h):
    d = _email(h).rpartition("@")[2]
    p = [x for x in d.split(".") if x]
    if len(p) >= 3 and p[-2] in ("co", "com", "org", "gob"):
        base = p[-3]
    else:
        base = p[-2] if len(p) >= 2 else (p[0] if p else "")
    return "" if base in CORREO_GENERICO else base.capitalize()


def empresa(h):
    return _etiqueta(_dominio(h)) or remitente(h)


def proveedor(h):
    d = (_email(h) + " " + (h.get("from") or "")).lower()
    for p in PROVEEDORES:
        if p in d:
            return p.capitalize() if p not in ("aireuropa", "flixbus") else {"aireuropa": "Air Europa", "flixbus": "FlixBus"}[p]
    return remitente(h)


def tipo_plazo(asunto):
    for rx, nom in TIPO_PLAZO:
        if rx.search(asunto or ""):
            return nom
    return "plazo"


def _corto(s, n=70):
    s = limpio(s, 200)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


# ───────── lecturas de Google (solo lectura) para no duplicar ─────────
class Contexto:
    """Lecturas perezosas de tareas y eventos de la cuenta destino (solo lectura, intentos=1) y el módulo revisar-zazu, durante un ciclo."""
    def __init__(self, cfg):
        self.cfg, self._rz, self._t, self._e = cfg, None, "sin leer", {}

    def cuenta(self):
        return self.cfg["flujos"]["cuenta_destino"]

    def _acc(self):
        return (self.cfg["correo"]["cuentas"] or {}).get(self.cuenta())

    def rz(self):
        if self._rz is None:
            from . import acciones
            self._rz = acciones._revisar_zazu()
        return self._rz

    def tareas(self):
        """Lista de tareas de la lista configurada, o None si no se pudo leer."""
        if self._t == "sin leer":
            try:
                r = reglas.recoger()
                d = r.gog(["tasks", "list", self.cfg["flujos"]["lista_tareas"], "--max=100", "--all", "--show-completed", "--show-hidden"], self._acc(), intentos=1)
                self._t = r.lista(d, "tasks", "items")
            except Exception:
                self._t = None
        return self._t

    def eventos(self, dia):
        """Eventos de ese día (lista) o None si no se pudo leer."""
        if dia not in self._e:
            try:
                r = reglas.recoger()
                d = r.gog(["calendar", "events", "--all", f"--from={dia}", "--days=1", "--max=100"], self._acc(), intentos=1)
                rz = self.rz()
                out = []
                for e in r.lista(d, "events", "items"):
                    if e.get("status") == "cancelled":
                        continue
                    ini, _ = rz.inicio_fin(e)
                    if ini is not None and (ini.astimezone(config.TZ).date() if isinstance(ini, datetime) else ini) == dia:
                        out.append(e)
                self._e[dia] = out
            except Exception:
                self._e[dia] = None
        return self._e[dia]

    def anota_tarea(self, titulo, dia, marca):
        if isinstance(self._t, list):
            self._t.append({"title": titulo, "due": f"{dia}T00:00:00Z", "notes": marca, "status": "needsAction"})

    def anota_evento(self, titulo, dia, marca):
        if isinstance(self._e.get(dia), list):
            self._e[dia].append({"summary": f"¿? {titulo}", "description": marca, "start": {"date": str(dia)}, "end": {"date": str(dia)}})


def tarea_duplicada(ctx, titulo, dia, claves=()):
    """True/False, o None si no se pudo comprobar. Más estricta que `tiene_tarea` (pensada para gemelas): dos títulos de plantilla
    («Revisar … de X») se parecen siempre, así que aquí hace falta un título casi igual (≥0,85) o que la tarea nombre al mismo
    remitente/organismo, y que su fecha esté a ±7 días (sin fecha: solo el título casi igual)."""
    ts = ctx.tareas()
    if ts is None:
        return None
    rz = ctx.rz()
    claves = [set(rz.norm(c).split()) for c in claves if c]
    for t in ts:
        nt = t.get("title") or ""
        if not nt:
            continue
        due = str(t.get("due") or "")[:10]
        try:
            fecha = date.fromisoformat(due) if due else None
        except ValueError:
            fecha = None
        if fecha is not None and abs((fecha - dia).days) > 7:
            continue
        if rz.parecidos(nt, titulo):
            return True
        if fecha is not None and any(k and k <= set(rz.norm(nt).split()) for k in claves):
            return True
    return False


def evento_duplicado(ctx, titulo, dia, claves=(), viaje=False):
    """Título del evento parecido que ya hay ese día, '' si no hay, None si no se pudo comprobar."""
    evs = ctx.eventos(dia)
    if evs is None:
        return None
    rz = ctx.rz()
    claves = [set(rz.norm(c).split()) for c in claves if c]       # «Seguridad Social» exige las dos palabras
    for e in evs:
        s = e.get("summary") or ""
        sn = re.sub(r"^\s*¿\?\s*", "", s)
        if rz.parecidos(sn, titulo):
            return s
        palabras = set(rz.norm(s).split())
        if any(k and k <= palabras for k in claves) or (viaje and PALABRAS_VIAJE.search(s)):
            return s
    return ""


# ───────── planes ─────────
@dataclass
class Plan:
    fid: str
    acciones: list = field(default_factory=list)     # {"tipo": tarea|evento, "titulo", "fecha": date, "hora": str|None, "dur": int, "claves": tuple, "viaje": bool}
    aviso: str = None                                 # texto para el detalle del aviso
    sin: str = None                                   # por qué no hay acciones de escritura (para el registro)


def _txt(msg):
    return f"{msg['asunto']} {msg['cuerpo']}"


def _plan_entrevista(m, cfg):
    es = ENTREVISTA.search(m["asunto"]) or (LLAMADA.search(m["asunto"]) and EMPLEO.search(m["asunto"] + " " + m["cuerpo"][:800]))
    if not (es and not reglas.recoger().PORTALES.search(m["de"]) and not reglas.AUTOMATICO.search(m["asunto"] + " " + m["cuerpo"][:300])):
        return None
    p, emp, txt = Plan("entrevista"), empresa(m["h"]), _txt(m)
    f, mot = extraer.elegir(extraer.candidatos_fecha(txt, m["hoy"], POS_ENTREVISTA, NEG_FECHA), txt)
    if not f:
        p.sin = {"sin_fecha": "no encuentro la fecha de la entrevista", "ambigua": "hay varias fechas posibles y no sé cuál es",
                 "formato_ambiguo": "el formato de la fecha es ambiguo"}[mot]
        return p
    quedada = f"{extraer.fecha_corta(f.fecha)}" + (f" {f.hora}" if f.hora else "")
    p.aviso = f"entrevista el {quedada}" if f.hora else f"entrevista (fecha {quedada}, sin hora clara)"
    if f.hora:
        p.acciones.append({"tipo": "evento", "titulo": _corto(f"Entrevista con {emp}"), "fecha": f.fecha, "hora": f.hora,
                           "dur": cfg["flujos"]["evento_duracion_min"], "claves": (emp,)})
    else:
        p.sin = "falta la hora: solo apunto la tarea"
    p.acciones.append({"tipo": "tarea", "titulo": _corto(f"Preparar entrevista con {emp}"), "fecha": f.fecha, "hora": None, "dur": 0, "claves": (emp,)})
    return p


def _plan_viaje(m, cfg):
    if not (VIAJE_ASUNTO.search(m["asunto"]) or (VIAJE_DOMINIO.search(m["de"]) and VIAJE_SUAVE.search(m["asunto"]))):
        return None
    p, prov, txt = Plan("viaje-reserva"), proveedor(m["h"]), _txt(m)
    fs, mot = extraer.elegir_varias(extraer.candidatos_fecha(txt, m["hoy"], VIAJE_POS, NEG_FECHA), txt, 2)
    if not fs:
        p.sin = {"sin_fecha": "no encuentro la fecha del viaje", "ambigua": "hay varias fechas y no sé cuáles son del viaje",
                 "formato_ambiguo": "el formato de la fecha es ambiguo"}[mot]
        return p
    for i, f in enumerate(fs):
        if not f.hora:
            p.sin = "no tengo una hora clara del viaje: no creo el evento"
            continue
        etiqueta = (" (ida)" if i == 0 else " (vuelta)") if len(fs) == 2 else ""
        p.acciones.append({"tipo": "evento", "titulo": _corto(f"Viaje {prov}{etiqueta}"), "fecha": f.fecha, "hora": f.hora, "dur": 120,
                           "claves": (prov,), "viaje": True})
    return p


def _plan_oficial(m, cfg):
    org = organismo(m["h"])
    if not (org and CITA.search(_txt(m)[:2500])):
        return None
    p, txt = Plan("correo-oficial"), _txt(m)
    f, mot = extraer.elegir(extraer.candidatos_fecha(txt, m["hoy"], CITA_POS, NEG_FECHA), txt)
    if not (f and f.hora):
        p.sin = "no encuentro una fecha y hora claras de la cita" if not f else "falta la hora de la cita"
        return p
    p.aviso = f"cita el {extraer.fecha_corta(f.fecha)} a las {f.hora}"
    p.acciones += [{"tipo": "evento", "titulo": _corto(f"Cita {org}"), "fecha": f.fecha, "hora": f.hora, "dur": cfg["flujos"]["evento_duracion_min"], "claves": (org,)},
                   {"tipo": "tarea", "titulo": _corto(f"Llevar documentación a la cita ({org})"), "fecha": f.fecha, "hora": None, "dur": 0, "claves": (org,)}]
    return p


def _plan_pago(m, cfg):
    if not PAGO_ASUNTO.search(m["asunto"]) or reglas.SEGURIDAD.search(m["asunto"]):
        return None
    p, quien = Plan("correo-pago"), remitente(m["h"])
    if reglas.CARGO.search(m["asunto"]):
        p.sin = "es un cargo o cobro ya hecho: solo aviso"
        p.aviso = "cargo ya hecho"
        return p
    txt = _txt(m)
    imp, _ = extraer.importe(txt, POS_IMPORTE, NEG_IMPORTE)
    f, mot = extraer.elegir(extraer.candidatos_fecha(txt, m["hoy"], POS_VENC, NEG_FECHA), txt)
    if f:
        p.aviso = f"vence el {extraer.fecha_corta(f.fecha)}" + (f" · {imp}" if imp else "")
    if not (f and imp):
        p.sin = ("no encuentro un vencimiento claro" if not f else "no encuentro un importe claro")
        return p
    p.acciones.append({"tipo": "tarea", "titulo": _corto(f"Pagar {quien} {imp}"), "fecha": f.fecha, "hora": None, "dur": 0, "claves": (quien,)})
    return p


def _plan_plazo(m, cfg):
    a, de = m["asunto"], m["de"]
    if reglas.SEGURIDAD.search(a) or reglas.CARGO.search(a):
        return None
    if not (reglas.OFICIAL.search(de) or reglas.DINERO.search(a) or PLAZO_ASUNTO.search(a)):
        return None
    p, quien, noun, txt = Plan("correo-plazo"), remitente(m["h"]), tipo_plazo(a), _txt(m)
    f, mot = extraer.elegir(extraer.candidatos_fecha(txt, m["hoy"], POS_PLAZO, NEG_FECHA), txt)
    if not f:
        p.sin = {"sin_fecha": "no encuentro una fecha clara", "ambigua": "hay varias fechas y no sé cuál es el plazo",
                 "formato_ambiguo": "el formato de la fecha es ambiguo"}[mot]
        return p
    p.aviso = f"plazo el {extraer.fecha_corta(f.fecha)}" + (f" a las {f.hora}" if f.hora else "")
    p.acciones.append({"tipo": "tarea", "titulo": _corto(f"Revisar {noun} de {quien}"), "fecha": f.fecha, "hora": None, "dur": 0, "claves": (quien,)})
    if f.hora:
        p.acciones.append({"tipo": "evento", "titulo": _corto(f"Plazo {noun} {quien}"), "fecha": f.fecha, "hora": f.hora, "dur": 30, "claves": (quien,)})
    return p


PLANES = {"entrevista": _plan_entrevista, "viaje-reserva": _plan_viaje, "correo-oficial": _plan_oficial, "correo-pago": _plan_pago, "correo-plazo": _plan_plazo}


def candidatos_correo(cfg, h):
    """Flujos de correo (no pausados) cuyo disparador casa con el asunto o el remitente. Barato: sin cuerpo ni red."""
    r = reglas.recoger()
    a, de = h.get("subject") or "", h.get("from") or ""
    if r.RUIDO.search(a + " " + de) or reglas.AUTOMATICO.search(a):
        return []
    port = bool(r.PORTALES.search(de))
    sec = bool(reglas.SEGURIDAD.search(a))
    c = []
    if (ENTREVISTA.search(a) or LLAMADA.search(a)) and not port:
        c.append("entrevista")
    if VIAJE_ASUNTO.search(a) or (VIAJE_DOMINIO.search(de) and VIAJE_SUAVE.search(a)):
        c.append("viaje-reserva")
    if reglas.OFICIAL.search(de):
        c.append("correo-oficial")
    if PAGO_ASUNTO.search(a) and not sec and not port:
        c.append("correo-pago")
    if (reglas.OFICIAL.search(de) or reglas.DINERO.search(a) or PLAZO_ASUNTO.search(a)) and not sec and not port and not reglas.CARGO.search(a):
        c.append("correo-plazo")
    return [x for x in ORDEN_CORREO if x in c and not pausado(cfg, x)]


# ───────── ejecución sobre un correo ─────────
RIESGO_FLUJO = {"correo-pago": "alto", "correo-oficial": "alto"}     # dinero y organismos: se pregunta siempre
def _crear_fila(db, cfg, p, a, idx, msg, quien, origen):
    """Fila silenciosa (flujo_tarea / flujo_evento) + «propuso» en el registro. → (id, nuevo, accion)."""
    fid, kind = p.fid, a["tipo"]
    disparo = f"{fid}:{origen}"
    escribe, motivo = escribe_ahora(cfg, fid, "correo")
    clave = f"flujo:{fid}:{kind}:{msg['et']}:{msg['hid']}:{a['fecha']}:{a['hora'] or '-'}:{idx}"   # sin el nº de mensajes: una respuesta del hilo no repite
    # permiso: clave estrecha por remitente, riesgo (dinero y organismos: alto) y regla «siempre / nunca» de Fran
    permiso = permisos.clave(permisos.accion_de(kind), "remitente", _email(msg["h"]) or quien)
    nivel = permisos.riesgo(kind, a["titulo"], minimo=RIESGO_FLUJO.get(fid))
    reparto = permisos.decidir(db, permiso, nivel)
    if escribe and not permisos.puede_sola(nivel, False):
        escribe, motivo = False, "es de riesgo alto: te lo pregunto antes"
    escribe = escribe and reparto != "ocultar"
    accion = "pendiente" if escribe else "sombra"
    if escribe:
        hoy_n = db.c.execute("SELECT COUNT(*) FROM avisos WHERE tipo IN ('flujo_tarea','flujo_evento') AND dia=? AND accion<>'tope'", (db.hoy(),)).fetchone()[0]
        if hoy_n >= cfg["flujos"]["max_escrituras_dia"]:
            accion = "tope"
    id_, nuevo = db.alta(clave, "correo", "flujo_tarea" if kind == "tarea" else "flujo_evento", a["titulo"], prio=3, silencioso=True,
                         detalle=f"De correo ({quien}, {msg['hoy']:%d/%m})", ref=f"correo:{msg['et']}:{msg['hid']}", chat=quien, cuenta=cfg["flujos"]["cuenta_destino"],
                         due=a["fecha"].isoformat(), hora=a["hora"], dur=a["dur"] or None, evidencia=f"flujo={fid};origen={origen}", accion=accion,
                         riesgo=nivel, permiso=permiso, decision=permisos.DECISION_REPARTO.get(reparto))
    if nuevo and permisos.tras_alta(db, cfg, id_, permiso, reparto, "correo", ("¿? " if kind == "evento" else "") + a["titulo"], fid):
        return id_, nuevo, "oculta"
    if nuevo:
        titulo = ("¿? " if kind == "evento" else "") + a["titulo"]
        if accion == "tope":
            registro.anota(db, "descarto", "correo", f"No creo {kind}: tope diario de flujos ({cfg['flujos']['max_escrituras_dia']})", titulo,
                           flujo=fid, ref=f"aviso:{id_}", modo="sombra", clave=f"tope:{clave}", disparo=disparo, cfg=cfg)
        else:
            registro.propuesta(db, cfg, "correo", kind, titulo, due=a["fecha"].isoformat(), hora=a["hora"], flujo=fid, ref=f"aviso:{id_}",
                               clave=f"propuso:{clave}", disparo=disparo, modo="vivo" if accion == "pendiente" else "sombra",
                               detalle=f"Origen: correo de {quien}" + ("" if accion == "pendiente" else f" · {motivo}"))
    return id_, nuevo, accion


def procesar_correo(db, cfg, ctx, et, h, cuerpo, candidatos, clasif=None):
    """Evalúa los flujos candidatos sobre UN correo nuevo. → dict {extra, flujo, disparo, estandar} o None.
    `extra`: texto para el detalle del aviso (fusionado con el aviso normal del correo). Si no hay aviso normal (`clasif` None) y el
    correo no está leído, el aviso lo crea aquí el propio flujo."""
    hoy = config.ahora().date()
    asunto, de = h.get("subject") or "", h.get("from") or ""
    msg = {"et": et, "hid": str(h.get("id")), "n": int(h.get("messageCount") or 1), "h": h, "asunto": limpio(asunto, 300), "de": de,
           "cuerpo": cuerpo or "", "hoy": hoy}
    disparo_base = f"correo:{et}:{msg['hid']}:{msg['n']}"
    quien = remitente(h)
    if sospechoso(f"{msg['asunto']} {msg['cuerpo']} {limpio(de, 120)}"):
        fid = candidatos[0]
        registro.anota(db, "descarto", "correo", f"No automatizo el correo de {quien}: trae instrucciones sospechosas", "Lo trato como dato; solo queda el aviso normal.",
                       flujo=fid, modo="sombra", clave=f"sospechoso:{disparo_base}", disparo=f"{fid}:{disparo_base}", cfg=cfg)
        return {"extra": "trae instrucciones sospechosas: no he automatizado nada", "flujo": fid, "disparo": f"{fid}:{disparo_base}", "estandar": True}
    primero_sin = None
    reclamado = None
    for fid in candidatos:
        p = PLANES[fid](msg, cfg)
        if p is None:
            continue
        if p.acciones:
            reclamado = p
            break
        if primero_sin is None:
            primero_sin = p
    if reclamado is None:
        if primero_sin is None:
            return None
        disp = f"{primero_sin.fid}:{disparo_base}"
        registro.anota(db, "descarto", "correo", f"Sin automatizar el correo de {quien}: {primero_sin.sin}", "Solo queda el aviso.", flujo=primero_sin.fid,
                       modo="sombra", clave=f"sin:{disp}", disparo=disp, cfg=cfg)
        return {"extra": primero_sin.aviso if "aviso" in FLUJOS[primero_sin.fid].acciones else None, "flujo": primero_sin.fid, "disparo": disp}
    p = reclamado
    disp = f"{p.fid}:{disparo_base}"
    n_ok = 0
    for i, a in enumerate(p.acciones):
        if a["tipo"] == "tarea":
            existe = bool(tarea_duplicada(ctx, a["titulo"], a["fecha"], a["claves"]))
        else:
            existe = bool(evento_duplicado(ctx, a["titulo"], a["fecha"], a["claves"], a.get("viaje")))
        if existe:
            registro.anota(db, "descarto", "correo", f"No creo {a['tipo']}: ya existe algo parecido el {a['fecha']:%d/%m}", ("¿? " if a["tipo"] == "evento" else "") + a["titulo"],
                           flujo=p.fid, modo="sombra", clave=f"dup:{p.fid}:{a['tipo']}:{et}:{msg['hid']}:{msg['n']}:{i}", disparo=disp, cfg=cfg)
            continue
        _, nuevo, _ac = _crear_fila(db, cfg, p, a, i, msg, quien, disparo_base)
        n_ok += nuevo
        if nuevo:
            marca = f"[ZV:pendiente-{i}]"
            (ctx.anota_tarea if a["tipo"] == "tarea" else ctx.anota_evento)(a["titulo"], a["fecha"], marca)
    if p.sin and n_ok:
        registro.anota(db, "descarto", "correo", f"Solo parte de lo posible con el correo de {quien}: {p.sin}", None, flujo=p.fid, modo="sombra",
                       clave=f"parcial:{disp}", disparo=disp, cfg=cfg)
    return {"extra": p.aviso if "aviso" in FLUJOS[p.fid].acciones else None, "flujo": p.fid, "disparo": disp}


TIPO_AVISO = {"entrevista": "entrevista", "correo-oficial": "oficial", "correo-pago": "dinero", "correo-plazo": "dinero"}


def aviso_propio(db, cfg, et, h, res):
    """Si el correo NO tiene aviso normal (ninguna regla de correo.clasificar lo recoge) pero un flujo con acción «aviso» sí lo ve,
    el aviso lo crea el flujo. Solo si el correo está sin leer (si ya lo leíste, lo sabes)."""
    if not res or not res.get("extra") or res["flujo"] not in TIPO_AVISO or "UNREAD" not in (h.get("labels") or []):
        return None
    n = int(h.get("messageCount") or 1)
    titulo = f"[{et}] {remitente(h)} · {seguro(h.get('subject'), 90)}"
    id_, nuevo = db.alta(f"flujo:{res['flujo']}:aviso:{et}:{h.get('id')}:{n}", "correo", TIPO_AVISO[res["flujo"]], titulo, prio=1, noche_ok=False,
                         detalle=res["extra"], ref=f"correo:{et}:{h.get('id')}", cuenta=et)
    if nuevo:
        registro.propuesta(db, cfg, "correo", "aviso", titulo, flujo=res["flujo"], ref=f"aviso:{id_}", clave=f"propuso:aviso:{id_}", disparo=res["disparo"],
                           detalle=res["extra"])
    return nuevo


# ───────── datos de una fila de trabajo ─────────
def id_de(fila):
    m = re.search(r"flujo=([\w-]+)", fila["evidencia"] or "")
    return m.group(1) if m and m.group(1) in FLUJOS else None


def disparo_de(fila):
    m = re.search(r"origen=(\S+)", fila["evidencia"] or "")
    fid = id_de(fila)
    return f"{fid}:{m.group(1)}" if m and fid else None
