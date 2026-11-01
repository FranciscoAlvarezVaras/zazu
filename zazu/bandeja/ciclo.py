"""Un ciclo de la bandeja: lee Google Tasks y Calendar (las dos cuentas), planifica qué haría según las convenciones de
Fran y, SOLO en modo vivo, lo ejecuta con una lista cerrada de acciones. En modo sombra (por defecto) lo escribe en el
registro de sombra y no toca Google, el Cerebro ni WhatsApp. Idempotente: cada acción tiene una clave en estado.db."""
import fcntl, hashlib, http.client, json, os, re, subprocess, sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import config, convenciones as cv, entrega, llm, web
from estado import Estado
from google import Google, GogError
from vault import Vault, Privado, Existe, tachar, limpiar_nombre

ESCRIBEN = {"aplicar", "investigar", "nota", "idea", "proyecto", "zazu"}
REINTENTOS = [timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2)]
CV_RUTA = "40 Compartido/Adjuntos/CV - Francisco Alvarez Varas.pdf"


class Retry(Exception):
    """Fallo pasajero (red, IA, Google): se reintenta a los 5 min, 30 min y 2 h."""


class Fallo(Exception):
    """Fallo que no se arregla reintentando: se avisa una vez."""


@dataclass
class Accion:
    clave: str
    tipo: str                       # aplicar|investigar|nota|idea|proyecto|zazu|gemela|aviso
    prio: int
    titulo: str                     # etiqueta corta, ya tachada
    plan: list
    inmediata: bool = True
    fire: datetime = None
    fin: datetime = None
    gracia: timedelta = timedelta(minutes=90)
    texto: str = ""                 # aviso a mandar (tipo aviso)
    ctx: dict = field(default_factory=dict)
    antiguo: bool = False           # existía antes de activar: en vivo no se toca (línea base)


def corto(s, n=60):
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", tachar(str(s or "")))
    return re.sub(r"\s+", " ", s).strip()[:n]


def ts_de(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def dt_de(x):
    """start/end de Google → (datetime con zona, es_todo_el_dia)."""
    if not x:
        return None, False
    if x.get("dateTime"):
        return datetime.fromisoformat(x["dateTime"].replace("Z", "+00:00")).astimezone(config.TZ), False
    if x.get("date"):
        return datetime.fromisoformat(x["date"]).replace(tzinfo=config.TZ), True
    return None, False


def hhmm(d):
    return d.astimezone(config.TZ).strftime("%H:%M")


def ddmm(d):
    return d.strftime("%d/%m")


def hace_texto(delta):
    if delta >= timedelta(days=1):
        n = round(delta / timedelta(days=1))
        return f"{n} día{'s' if n != 1 else ''}"
    if delta >= timedelta(hours=1):
        n = round(delta / timedelta(hours=1))
        return f"{n} h"
    return f"{round(delta / timedelta(minutes=1))} min"


class Ciclo:
    def __init__(self, vivo=None, simular=False, forzar=None, google=None):
        v = (config.modo() == "vivo") if vivo is None else vivo
        self.simular = simular
        self.vivo = bool(v) and not simular                    # un simulacro nunca es vivo
        self.modo = "vivo" if self.vivo else "sombra"
        self.forzar = forzar                                    # subcadena de clave que se reprocesa (zb replay)
        self.g = google or Google(vivo=self.vivo)
        self.vault = Vault(escribir=self.vivo)
        self.est = Estado(memoria=simular)
        self.web, self.llm = web, llm                           # sustituibles en tests
        self.reglas = config.reglas()
        self.ahora = config.ahora()
        self.cede = self._cede()
        self.errores = {}
        self.inertes = []                                       # (clave, motivo)
        self.acciones = []
        self.resumen = Counter()

    def _cede(self):
        """Partes que se apagan para no duplicar al vigía de agenda (zv.agenda) cuando ESE está en modo activo
        (solo se lee su config), más lo que pida reglas.json › desactivar. Valores: gemela llevar despues recordar salida cumple verbos."""
        cede = set(self.reglas.get("desactivar") or [])
        try:
            cfg = json.loads((config.home() / ".config/zazu-vigia/config.json").read_text())
            if (cfg.get("modo") or {}).get("agenda") == "activo":
                cede |= {"gemela", "llevar", "despues", "salida", "cumple", "verbos"}
        except (OSError, ValueError):
            pass
        return cede

    # ───────────────────────── lectura ─────────────────────────
    def leer(self):
        hoy = self.ahora.date()
        self.datos = {}
        for cuenta in self.g.cuentas:
            d = {"listas": [], "eventos": [], "gemelas": None, "ok": False}
            try:
                clave = ((self.reglas.get("alcance") or {}).get("contiene") or "").lower()
                en_alcance = (lambda x: clave in str(x or "").lower()) if clave else (lambda x: True)
                for l in self.g.listas(cuenta):
                    d["listas"].append((l, [t for t in self.g.tareas(cuenta, l["id"]) if en_alcance(t.get("title"))]))
                d["eventos"] = [e for e in self.g.eventos(cuenta, hoy - timedelta(days=1), self.reglas["ventana_dias"]) if en_alcance(e.get("summary"))]
                try:
                    d["gemelas"] = self.g.tareas_todas(cuenta)
                except GogError:
                    d["gemelas"] = None
                d["ok"] = True
            except GogError as e:
                self.errores[cuenta] = e
            self.datos[cuenta] = d
            self.resumen[f"leidas_{cuenta}"] = len(d["eventos"]) + sum(len(x[1]) for x in d["listas"])

    # ───────────────────────── planificación ─────────────────────────
    def _silencio(self, dt):
        a, b = (tuple(int(x) for x in h.split(":")) for h in self.reglas["silencio"])
        m = dt.hour * 60 + dt.minute
        return m >= a[0] * 60 + a[1] or m < b[0] * 60 + b[1]

    def _apertura(self, dt):
        b = tuple(int(x) for x in self.reglas["silencio"][1].split(":"))
        d = dt.replace(hour=b[0], minute=b[1], second=0, microsecond=0)
        return d if d >= dt else d + timedelta(days=1)

    def _efectivo(self, fire, prio):
        return fire if prio <= 1 or not self._silencio(fire) else self._apertura(fire)

    def _vencida(self, a):
        """¿toca ya? Un aviso programado vale desde su hora (o desde las 07:30 si cae en silencio) un rato y nunca tras `fin`."""
        ef = self._efectivo(a.fire, a.prio)
        tope = ef + a.gracia
        if a.fin:
            tope = min(tope, a.fin)
        return ef <= self.ahora <= tope

    def _aviso(self, clave, prio, fire, fin, texto, gracia=None, etiqueta="aviso"):
        a = Accion(clave, "aviso", prio, etiqueta, [f"avisaría por WhatsApp ({etiqueta})"], inmediata=False, fire=fire, fin=fin, texto=tachar(texto)[:300])
        if gracia:
            a.gracia = gracia
        self.acciones.append(a)

    def planificar_tareas(self):
        vivo_desde = ts_de(self.est.meta("vivo_desde")) if self.vivo else None
        sin_fecha = Counter()
        for cuenta, d in self.datos.items():
            for lista, tareas in d["listas"]:
                for t in tareas:
                    ck = f"t:{cuenta}:{lista['id']}:{t.get('id')}"
                    h = cv.huella(t)
                    ajena = cv.tarea_ajena(t)
                    verbo, arg = cv.clasificar_tarea(t)
                    self.est.ver_item(ck, "tarea", cuenta, h)
                    self.resumen["tareas"] += 1
                    if ajena in ("zv", "asignada", "de_correo"):
                        self.inertes.append((ck, ajena))
                        continue
                    if not verbo:
                        continue
                    titulo = corto(t.get("title"), 60)
                    upd = ts_de(t.get("updated"))
                    base = ts_de(self.est.meta("vivo_desde" if self.vivo else "primer_ciclo"))
                    antiguo = bool(upd and base and upd < base)
                    if verbo in ESCRIBEN:
                        if ajena == "origen_agente":
                            self.inertes.append((ck, ajena))
                            continue
                        marcada = bool(cv.MARCA_ZAZU.search(str(t.get("notes") or "")))
                        if marcada and verbo not in ("nota", "idea"):
                            continue
                        ctx = {"cuenta": cuenta, "lista": lista["id"], "t": t, "arg": arg, "notas": t.get("notes") or "",
                               "solo_cerrar": marcada, "titulo": titulo, "item": ck}
                        a = Accion(f"{ck}:{h}:{verbo}", verbo, 2, titulo, self._plan_tarea(verbo, arg, t, marcada), ctx=ctx, antiguo=antiguo)
                        self.acciones.append(a)
                    elif "verbos" not in self.cede:
                        self._avisos_tarea(ck, verbo, arg, t, cuenta, sin_fecha)
        if sin_fecha and self.ahora.weekday() == 0:
            sem = self.ahora.strftime("%G-W%V")
            ini = self.ahora.replace(hour=9, minute=0, second=0, microsecond=0)
            self._aviso(f"sinfecha:{sem}", 3, ini, ini.replace(hour=23, minute=59),
                        f"📋 Tienes {sum(sin_fecha.values())} tarea(s) de pagar/llamar/comprar/pedir cita sin fecha. Ponles día y te aviso a tiempo.",
                        etiqueta="tareas sin fecha")

    def _plan_tarea(self, verbo, arg, t, marcada):
        if marcada:
            return ["cerraría la tarea (ya estaba capturada)"]
        if verbo == "aplicar":
            p = cv.parsear_aplicar(arg, t.get("notes"))
            lineas = ["buscaría en Cerebro/Candidaturas si ya existe (mismo enlace o empresa+puesto)"]
            if p["url"]:
                lineas += ["descargaría la oferta (solo web pública, 1 MB) y pasaría el texto recortado por la IA sin herramientas para sacar empresa/puesto/plazo"]
            lineas += ["crearía la nota de candidatura desde la plantilla (estado: por enviar)",
                       "añadiría línea en Buscar trabajo › Historial, en index.md y en log.md"]
            if p["url"]:
                lineas += ["pediría la carta (IA sin herramientas, solo con el CV) y la guardaría como «## Carta»"]
            lineas += ["pondría el plazo como fecha de la tarea", "añadiría «✓ Zazu …» a las notas de la tarea", "te avisaría por WhatsApp: Apuntada"]
            return lineas
        return {
            "investigar": ["una IA solo con búsqueda web redactaría una nota breve con fuentes (máx. 3 al día)",
                           "la guardaría en 10 Bandeja (tipo nota, origen zazu)", "añadiría «✓ Zazu …» y te avisaría: Investigación lista"],
            "nota": ["crearía la nota en 10 Bandeja (tipo nota, origen zazu)", "añadiría «✓ Zazu …» a las notas y marcaría la tarea como hecha"],
            "idea": ["crearía la nota en 30 Notas/Ideas (tipo idea) y su línea en index.md y log.md", "añadiría «✓ Zazu …» y marcaría la tarea como hecha"],
            "proyecto": ["crearía la nota en 30 Notas/Proyectos desde la plantilla (estado: activo) y su línea en index.md y log.md",
                         "añadiría «✓ Zazu …» a las notas de la tarea"],
            "zazu": ["clasificaría el texto (tarea/nota/evento/Hermes) y dejaría una PROPUESTA en la bandeja; no ejecutaría nada sin tu confirmación"],
        }[verbo]

    def _avisos_tarea(self, ck, verbo, arg, t, cuenta, sin_fecha):
        due = str(t.get("due") or "")[:10]
        titulo = corto(arg or t.get("title"), 50)
        if not due:
            sin_fecha[cuenta] += 1
            return
        try:
            dia = date.fromisoformat(due)
        except ValueError:
            return
        base = datetime(dia.year, dia.month, dia.day, tzinfo=config.TZ)
        fin_dia = base + timedelta(hours=23, minutes=59)
        m = cv.URL.search(str(t.get("notes") or ""))
        url = m.group(0) if m else None
        k = f"{ck}:{due}:{verbo}"
        if verbo == "pagar":
            extra = url if url else "Falta el enlace de pago."
            self._aviso(k + ":d2", 1, base - timedelta(days=2) + timedelta(hours=9), fin_dia,
                        f"💶 Pagar «{titulo}» vence el {ddmm(dia)}. {extra}", gracia=fin_dia - (base - timedelta(days=2)), etiqueta="pagar")
        elif verbo == "llamar":
            self._aviso(k, 2, base + timedelta(hours=10), fin_dia, f"📞 Hoy toca llamar: «{titulo}».", gracia=timedelta(hours=13), etiqueta="llamar")
        elif verbo == "comprar":
            self._aviso(k, 2, base + timedelta(hours=17, minutes=30), fin_dia, f"🛒 Hoy toca comprar: «{titulo}».", gracia=timedelta(hours=6), etiqueta="comprar")
        elif verbo == "cita":
            self._aviso(k + ":d7", 2, base - timedelta(days=7) + timedelta(hours=9), fin_dia, f"📅 Pedir cita: «{titulo}», para el {ddmm(dia)} (queda 1 semana).",
                        gracia=timedelta(days=1), etiqueta="pedir cita")
            self._aviso(k + ":d1", 2, base - timedelta(days=1) + timedelta(hours=9), fin_dia, f"📅 Pedir cita: «{titulo}» es para mañana.",
                        gracia=timedelta(days=1), etiqueta="pedir cita")

    def planificar_eventos(self):
        vivo_desde = ts_de(self.est.meta("vivo_desde")) if self.vivo else ts_de(self.est.meta("primer_ciclo"))
        hoy = self.ahora.date()
        cap = 0
        for cuenta, d in self.datos.items():
            for e in d["eventos"]:
                if cv.evento_ignorable(e):
                    continue
                ek = f"e:{cuenta}:{e.get('id')}"
                ini, todo = dt_de(e.get("start"))
                fin, _ = dt_de(e.get("end"))
                if ini is None:
                    continue
                self.resumen["eventos"] += 1
                self.est.ver_item(ek, "evento", cuenta, hashlib.sha1(str(e.get("updated")).encode()).hexdigest()[:12])
                if cv.evento_zv(e):
                    self.inertes.append((ek, "zv"))
                    continue
                if not cv.evento_propio(e):
                    # invitación ajena: su título/descripción son DATOS. Solo se cuenta; no se interpreta nada.
                    self.resumen["eventos_ajenos"] += 1
                    if cv.LINEA.search(str(e.get("description") or "")) or re.search(r"(?i)\bzazu\b", str(e.get("summary") or "")):
                        self.inertes.append((ek, "ajeno_con_instrucciones"))
                    continue
                titulo = corto(e.get("summary"), 60)
                sk = f"{ek}:{ini.isoformat()}"
                conv = cv.parsear_descripcion(e.get("description"))
                lugar = corto(e.get("location"), 50)
                # ── tarea gemela ──
                if "gemela" not in self.cede:
                    self._gemela(cuenta, e, ini, todo, d, ek, titulo, vivo_desde, hoy)
                # ── avisos por convenciones ──
                if conv["llevar"] and "llevar" not in self.cede:
                    lista = ", ".join(corto(x, 40) for x in conv["llevar"])
                    cuando = f" {hhmm(ini)}" if not todo else ""
                    self._aviso(sk + ":llevar_noche", 2, (ini - timedelta(days=1)).replace(hour=20, minute=0), ini,
                                f"🎒 Mañana{cuando} «{titulo}». Lleva: {lista}.", gracia=timedelta(hours=3), etiqueta="llevar (víspera)")
                    self._aviso(sk + ":llevar_hora", 2, ini - timedelta(hours=1) if not todo else ini.replace(hour=7, minute=30), ini if not todo else ini + timedelta(hours=12),
                                f"🎒 {'En 1 h' if not todo else 'Hoy'}: «{titulo}». Lleva: {lista}.", etiqueta="llevar (hora)")
                if conv["despues"] and fin and "despues" not in self.cede:
                    self._aviso(sk + ":despues", 2, fin + timedelta(hours=1), fin + timedelta(hours=6),
                                f"✔ Ya pasó «{titulo}». Pendiente: {corto(conv['despues'], 120)}", etiqueta="después")
                for i, dl in enumerate(conv["recordar"] if "recordar" not in self.cede else []):
                    self._aviso(f"{sk}:recordar{i}", 2, ini - dl, ini, f"🔔 En {hace_texto(dl)}: «{titulo}» ({ddmm(ini)}{'' if todo else ' ' + hhmm(ini)}).", etiqueta="recordar")
                if lugar and not todo and self.reglas["salida_por_ubicacion"] and "salida" not in self.cede and not re.match(r"https?://", lugar):
                    self._aviso(sk + ":salida", 2, ini - timedelta(minutes=45), ini, f"🚗 «{titulo}» a las {hhmm(ini)} en {lugar}. Sal ya (quedan 45 min).",
                                etiqueta="salida")
                if cv.es_cumple(e) and "cumple" not in self.cede:
                    dia0 = ini.replace(hour=9, minute=0)
                    self._aviso(sk + ":cumple7", 3, dia0 - timedelta(days=7), ini, f"🎂 En 7 días: {titulo.replace('🎂', '').strip()} ({ddmm(ini)}).", gracia=timedelta(days=1), etiqueta="cumpleaños")
                    self._aviso(sk + ":cumple1", 3, dia0 - timedelta(days=1), ini, f"🎂 Mañana: {titulo.replace('🎂', '').strip()}.", gracia=timedelta(days=1), etiqueta="cumpleaños")

    def _gemela(self, cuenta, e, ini, todo, d, ek, titulo, vivo_desde, hoy):
        if e.get("eventType", "default") != "default" or e.get("recurringEventId") or e.get("recurrence"):
            return
        if cv.evento_tentativo(e) or re.search(r"(?m)^\s*Origen:", str(e.get("description") or "")) or re.match(r"^\W*mañana\b", str(e.get("summary") or ""), re.I):
            return
        dia = ini.date()
        if dia < hoy or dia > hoy + timedelta(days=30) or (not todo and ini < self.ahora):
            return
        if d["gemelas"] is None:
            return                                           # no se pudo leer las tareas: ni se comprueba ni se crea
        if cv.tiene_tarea(e.get("summary"), dia, d["gemelas"]):
            return
        creado = ts_de(e.get("created"))
        antiguo = bool(creado and vivo_desde and creado < vivo_desde and not self.reglas["gemela_retro"])
        ctx = {"cuenta": cuenta, "evento": e, "dia": dia, "titulo": titulo, "item": ek}
        self.acciones.append(Accion(f"g:{cuenta}:{e.get('id')}:{dia}", "gemela", 3, titulo,
                                    [f"crearía la tarea «{titulo}» para el {ddmm(dia)} en Mis tareas ({cuenta}) con la nota «gemela de evento»"], ctx=ctx, antiguo=antiguo))

    # ───────────────────────── ejecución ─────────────────────────
    def ejecutar(self):
        for a in self.acciones:
            try:
                if a.inmediata or self._vencida(a) or (self.forzar and self.forzar in a.clave):
                    self.procesar(a)
            except Exception as e:                           # un fallo no tumba el ciclo
                self.resumen["errores_internos"] += 1
                sys.stderr.write(f"zb: error procesando {a.tipo}: {type(e).__name__}\n")
        self.cierre()

    def procesar(self, a):
        forzada = bool(self.forzar and self.forzar in a.clave)
        prev = None if (self.simular or forzada) else self.est.accion(a.clave, self.modo)
        if prev and prev["estado"] in ("hecho", "sombra", "fallido", "omitido"):
            return
        if prev and prev["estado"] == "reintento" and prev["proximo"] and self.ahora.timestamp() < prev["proximo"]:
            return
        if a.tipo == "aviso":
            self.resumen[f"aviso_{a.titulo}"] += 1
            if not self.simular:
                self.est.inbox(a.clave, self.modo, a.prio, "aviso", a.texto)
                self.est.anotar(a.clave, self.modo, "aviso", a.prio, "sombra" if not self.vivo else "hecho", a.texto)
                if not self.vivo:
                    self.est.registrar_sombra(item=a.clave[:80], tipo="aviso", prio=a.prio, titulo=a.titulo,
                                              plan=[f"te mandaría por WhatsApp: {a.texto}"], retro=False)
            return
        self.resumen[f"accion_{a.tipo}"] += 1
        if self.simular:
            return
        if not self.vivo:
            self.est.anotar(a.clave, "sombra", a.tipo, a.prio, "sombra", " | ".join(a.plan))
            self.est.registrar_sombra(item=a.ctx.get("item"), tipo=a.tipo, prio=a.prio, titulo=a.titulo, plan=a.plan, retro=a.antiguo)
            return
        # ── vivo ──
        if a.antiguo and not forzada:
            self.est.anotar(a.clave, "vivo", a.tipo, a.prio, "omitido", "existía antes de activar (línea base)")
            return
        for tope, tipo_t in (("tope_gemelas_dia", "gemela"), ("tope_aplicar_dia", "aplicar"), ("tope_investigar_dia", "investigar")):
            if a.tipo == tipo_t and self.est.contar_hoy(tipo_t, "vivo") >= self.reglas[tope]:
                return
        if a.tipo == "gemela" and self.resumen["_gemelas_ciclo"] >= self.reglas["tope_gemelas_ciclo"]:
            return
        intentos = prev["intentos"] if prev else 0
        try:
            texto, detalle = getattr(self, "ej_" + a.tipo)(a)
            self.est.anotar(a.clave, "vivo", a.tipo, a.prio, "hecho", detalle)
            self.est.ver_item(a.ctx["item"], "tarea" if a.tipo != "gemela" else "evento", a.ctx["cuenta"],
                              cv.huella(a.ctx["t"]) if "t" in a.ctx else "", estado="procesado", resultado=detalle[:200])
            if texto:
                self.est.inbox(a.clave, "vivo", a.prio, a.tipo, texto)
        except Retry as e:
            intentos += 1
            if intentos >= len(REINTENTOS) + 1:
                self._fallido(a, str(e), intentos)
            else:
                self.est.anotar(a.clave, "vivo", a.tipo, a.prio, "reintento", str(e), intentos, (self.ahora + REINTENTOS[intentos - 1]).timestamp())
        except GogError as e:
            if e.codigo == 4:
                self.est.inbox(f"auth:{a.ctx.get('cuenta')}:{self.ahora:%Y-%m-%d}", "vivo", 1, "error",
                               f"🔑 Hay que volver a autorizar Google ({a.ctx.get('cuenta')}).")
                return
            intentos += 1
            if intentos >= len(REINTENTOS) + 1:
                self._fallido(a, "Google no responde", intentos)
            else:
                self.est.anotar(a.clave, "vivo", a.tipo, a.prio, "reintento", "gog", intentos, (self.ahora + REINTENTOS[intentos - 1]).timestamp())
        except Privado:
            self._fallido(a, "lleva algo que el Cerebro no guarda (clave, teléfono, DNI, cuenta…); no lo apunto", intentos)
        except (Fallo, PermissionError, ValueError, FileNotFoundError) as e:
            self._fallido(a, str(e) or type(e).__name__, intentos)
        if a.tipo == "gemela":
            self.resumen["_gemelas_ciclo"] += 1

    def _fallido(self, a, causa, intentos):
        causa = corto(causa, 120)
        self.est.anotar(a.clave, "vivo", a.tipo, a.prio, "fallido", causa, intentos)
        self.est.inbox("fallo:" + a.clave, "vivo", 1, "error", f"⚠ No pude procesar «{a.titulo}»: {causa}. Se queda como estaba.")

    def cierre(self):
        """Tareas que ya no están pendientes (hechas o borradas): se marcan cerradas."""
        if self.simular:
            return
        vistas = {f"t:{c}:{l['id']}:{t.get('id')}" for c, d in self.datos.items() for l, ts in d["listas"] for t in ts}
        buenas = {c for c, d in self.datos.items() if d["ok"]}
        for ck in self.est.items_abiertos("tarea"):
            if ck.split(":")[1] in buenas and ck not in vistas:
                self.est.db.execute("UPDATE items SET estado='cerrado' WHERE clave=?", (ck,))

    # ───────────────────────── acciones (lista cerrada) ─────────────────────────
    def _marcar(self, a, texto):
        """Añade «✓ Zazu dd/mm hh:mm · …» a las notas de la tarea (conservando las de Fran). Idempotente."""
        c = a.ctx
        notas = str(c["t"].get("notes") or "")
        if cv.MARCA_ZAZU.search(notas):
            return
        linea = f"✓ Zazu {self.ahora:%d/%m %H:%M} · {texto}"
        self.g.tarea_notas(c["cuenta"], c["lista"], c["t"]["id"], (notas.rstrip() + "\n" if notas.strip() else "") + linea)

    def _rel(self):
        """SCHEMA: toda nota nueva de 30 Notas enlaza a algo. Aquí, al Diario del día si existe."""
        d = f"{self.ahora:%Y-%m-%d}"
        return [f"[[{d}]]"] if (self.vault.raiz / f"20 Diario/{d}.md").exists() else []

    def _nombre_unico(self, tipo, base):
        for i in range(1, 6):
            n = base if i == 1 else f"{base} ({i})"
            if not self.vault.existe_nombre(n):
                return n
        raise Fallo("demasiadas notas con ese nombre")

    def _reutilizar(self, tipo, base, texto):
        """Si una pasada anterior ya creó esa nota (se cayó antes de anotarlo), se reutiliza en vez de duplicarla."""
        for i in range(1, 6):
            n = base if i == 1 else f"{base} ({i})"
            p = self.vault.buscar_nota_exacta(tipo, n)
            if p and texto in p.read_text(encoding="utf-8"):
                return p
        return None

    def ej_nota(self, a):
        c = a.ctx
        if not c["solo_cerrar"]:
            texto = c["arg"]
            self.vault._revisar(texto)                       # Privado → no se apunta (SCHEMA: «Eso no lo apunto»)
            base = limpiar_nombre(f"{self.ahora:%Y-%m-%d} " + (re.sub(r"https?://\S+", "", texto).strip() or texto)[:50])
            m = cv.URL.search(texto)
            ruta = self._reutilizar("nota", base, texto)
            if not ruta:
                ruta = self.vault.crear_nota("nota", self._nombre_unico("nota", base), {"origen": "zazu", "enlace": m.group(0) if m else ""}, extra=texto)
                self.vault.log("nota capturada desde una tarea de Google Tasks (Nota:)", f"10 Bandeja/{ruta.stem}")
            self._marcar(a, "nota guardada en Cerebro › Bandeja")
            lugar = f"Cerebro › Bandeja › {ruta.stem}"
        else:
            lugar = "ya capturada"
        self.g.tarea_hecha(c["cuenta"], c["lista"], c["t"]["id"])
        return None, lugar

    def ej_idea(self, a):
        c = a.ctx
        if not c["solo_cerrar"]:
            texto = c["arg"]
            self.vault._revisar(texto)
            base = texto[:60].strip()
            base = base[:1].upper() + base[1:]
            ruta = self._reutilizar("idea", limpiar_nombre(base), texto)
            if not ruta:
                ruta = self.vault.crear_nota("idea", self._nombre_unico("idea", limpiar_nombre(base)), {"estado": "nueva", "relacionados": self._rel()},
                                             reemplazos={"**Qué es:** ": f"**Qué es:** {texto}"})
                self.vault.indice("idea", ruta.stem, texto[:100])
                self.vault.log("idea capturada desde una tarea de Google Tasks (Idea:)", f"30 Notas/Ideas/{ruta.stem}, 90 Sistema/index")
            self._marcar(a, "idea guardada en Cerebro › Ideas")
            lugar = f"Cerebro › Ideas › {ruta.stem}"
        else:
            lugar = "ya capturada"
        self.g.tarea_hecha(c["cuenta"], c["lista"], c["t"]["id"])
        return None, lugar

    def ej_proyecto(self, a):
        c = a.ctx
        nombre = re.sub(r"\s+", " ", c["arg"]).strip()[:77]
        self.vault._revisar(nombre)
        ya = self.vault.buscar_proyecto(nombre)
        if ya:
            self._marcar(a, f"ya existe el proyecto en Cerebro › Proyectos › {ya.stem}")
            return None, f"ya existía: {ya.stem}"
        ruta = self.vault.crear_nota("proyecto", nombre, {"siguiente": "Decidir los primeros pasos", "relacionados": self._rel()},
                                     reemplazos={"(Qué quieres conseguir y cuándo está terminado.)": f"Creado desde una tarea de Google Tasks («Proyecto: {nombre}»). Falta decir para qué es y cuándo está terminado."})
        self.vault.indice("proyecto", ruta.stem, "creado desde Google Tasks; falta definirlo")
        self.vault.log("proyecto creado desde una tarea de Google Tasks (Proyecto:)", f"30 Notas/Proyectos/{ruta.stem}, 90 Sistema/index")
        self._marcar(a, "proyecto creado en Cerebro › Proyectos")
        return f"📁 Proyecto «{ruta.stem}» creado en tu Cerebro.", f"Proyectos/{ruta.stem}"

    def ej_aplicar(self, a):
        c = a.ctx
        p = cv.parsear_aplicar(c["arg"], c["notas"])
        v = self.vault
        ya = v.buscar_candidatura(p["url"], p["empresa"], p["puesto"])
        if ya:
            self._marcar(a, f"ya estaba en Cerebro › Candidaturas › {ya.stem}")
            return None, f"ya estaba: {ya.stem}"
        datos = {"empresa": p["empresa"], "puesto": p["puesto"], "ciudad": None, "plazo": None, "resumen": None, "idioma": "es"}
        oferta = None
        if p["url"]:
            try:
                _, oferta = self.web.leer(p["url"])
            except web.Bloqueada as e:
                raise Fallo(f"enlace no permitido ({e})")
            except (OSError, http.client.HTTPException):
                raise Retry("no pude abrir el enlace")
            if len(oferta) < 120:
                raise Fallo("la página no da texto (¿LinkedIn?): pégame el texto de la oferta")
            try:
                ext, _ = self.llm.extraer_oferta(oferta)
            except llm.LlmError as e:
                raise Retry(f"IA: {e}")
            datos.update({k: ext[k] for k in ext if ext.get(k)})
            ya = v.buscar_candidatura(p["url"], datos["empresa"], datos["puesto"])
            if ya:
                self._marcar(a, f"ya estaba en Cerebro › Candidaturas › {ya.stem}")
                return None, f"ya estaba: {ya.stem}"
        if not datos["empresa"] or not datos["puesto"]:
            raise Fallo("no sé la empresa o el puesto: escribe «Aplicar: puesto – empresa»")
        emp, pue = tachar(datos["empresa"]), tachar(datos["puesto"])
        plazo = datos["plazo"] or (self.ahora.date() + timedelta(days=2)).isoformat()
        sin_plazo = not datos["plazo"]
        nombre = f"{emp} - {pue}"
        campos = {"empresa": emp, "puesto": pue, "ciudad": tachar(datos["ciudad"] or ""), "enlace": p["url"] or "", "plazo": plazo,
                  "siguiente": "Revisar la oferta y enviar la candidatura"}
        resumen = tachar(datos["resumen"] or "Sin enlace: falta leer la oferta y completar los datos.")
        ruta = v.crear_nota("candidatura", nombre, campos,
                            reemplazos={"(Dos líneas: qué piden y de dónde salió.)": f"{resumen} Salió de Google Tasks (Aplicar:).",
                                        "Apuntada.": "Apuntada desde Google Tasks."})
        carta_ok = None
        if oferta:
            carta_ok = self._carta(ruta, oferta, datos["idioma"])
        v.historial(v.raiz / "30 Notas/Proyectos/Buscar trabajo.md", f"- {self.ahora:%Y-%m-%d} · Apuntada la candidatura de {emp} ([[{ruta.stem}]]).")
        v.indice("candidatura", ruta.stem, f"{(datos['ciudad'] or 'sin ciudad')}; plazo {plazo[8:10]}-{plazo[5:7]}")
        v.log("candidatura apuntada desde una tarea de Google Tasks (Aplicar:)", f"30 Notas/Candidaturas/{ruta.stem}, Buscar trabajo, 90 Sistema/index")
        due_actual = str(c["t"].get("due") or "")[:10]
        if due_actual != plazo:
            self.g.tarea_due(c["cuenta"], c["lista"], c["t"]["id"], plazo)
        self._marcar(a, f"candidatura creada en Cerebro › Candidaturas › {ruta.stem}" + ("" if carta_ok is None else (" · carta lista" if carta_ok else " · sin carta")))
        txt = f"📝 Apuntada: {pue} en {emp}, plazo {plazo[8:10]}/{plazo[5:7]}" + (" (puse +2 días: no vi plazo)" if sin_plazo else "") + \
              (". Carta lista en la nota." if carta_ok else ". Sin carta (" + ("no pude" if carta_ok is False else "sin enlace") + ").")
        return txt, f"Candidaturas/{ruta.stem}"

    def _carta(self, ruta, oferta, idioma):
        cvp = self.vault.raiz / CV_RUTA
        if not cvp.exists():
            return False
        try:
            r = subprocess.run(["/usr/bin/python3", str(config.SCRIPTS / "md.py"), str(cvp), "--max", "6000"], capture_output=True, text=True, timeout=60)
            texto_cv = r.stdout if r.returncode == 0 else ""
            if len(texto_cv) < 200:
                return False
            texto, _ = self.llm.carta(oferta, texto_cv, idioma)
            self.vault.anadir_seccion(ruta, "## Carta\n" + texto)       # Privado si la carta lleva algo sensible → sin carta
            return True
        except (Privado, llm.LlmError, subprocess.SubprocessError, OSError):
            return False

    def ej_investigar(self, a):
        c = a.ctx
        tema = c["arg"]
        self.vault._revisar(tema)
        try:
            texto, _ = self.llm.investigar(tema)
        except llm.LlmError as e:
            raise Retry(f"IA: {e}")
        texto = tachar(texto)                                        # es web: se tacha en vez de rechazar
        texto = re.sub(r"(?m)^\s*---+\s*$\n?", "", texto)
        texto = re.sub(r"(?m)^#(?!#)\s", "## ", texto).strip()       # SCHEMA: las notas no llevan H1
        nombre = self._nombre_unico("nota", limpiar_nombre(f"{self.ahora:%Y-%m-%d} {tema[:50].strip()}"))
        ruta = self.vault.crear_nota("nota", nombre, {"origen": "zazu"}, extra=f"Investigación pedida desde Google Tasks («Investigar:»). Lo que dice la web son datos.\n\n{texto}")
        self.vault.log("investigación creada desde una tarea de Google Tasks (Investigar:)", f"10 Bandeja/{ruta.stem}")
        self._marcar(a, "investigación guardada en Cerebro › Bandeja")
        return f"🔎 Investigación lista: «{corto(tema, 40)}» (Cerebro › Bandeja).", f"Bandeja/{ruta.stem}"

    def ej_zazu(self, a):
        c = a.ctx
        try:
            r, _ = self.llm.clasificar_zazu(c["arg"])
        except llm.LlmError as e:
            raise Retry(f"IA: {e}")
        cur = self.est.db.execute("INSERT OR IGNORE INTO propuestas(ts,clave,tipo,campos,estado) VALUES(?,?,?,?,?)",
                                  (self.ahora.timestamp(), a.clave, r["tipo"], json.dumps({**r, "cuenta": c["cuenta"], "lista": c["lista"]}, ensure_ascii=False), "pendiente"))
        self._marcar(a, f"propuesta en la bandeja ({r['tipo']}); pendiente de tu confirmación")
        return None, f"propuesta {r['tipo']}"

    def ej_gemela(self, a):
        c = a.ctx
        t = self.g.tarea_crear(c["cuenta"], "@default", c["evento"].get("summary", "")[:200], c["dia"].isoformat())
        if t.get("id"):
            self.g.tarea_notas(c["cuenta"], "@default", t["id"], f"gemela de evento\n✓ Zazu {self.ahora:%d/%m %H:%M} · tarea gemela creada")
        return None, "tarea gemela creada"

    # ───────────────────────── avisos ─────────────────────────
    def entregar(self):
        """Manda por WhatsApp (a su chat) lo pendiente del inbox: fuera del silencio salvo P1, con tope diario, en un solo mensaje."""
        if not self.vivo:
            return
        pend = self.est.db.execute("SELECT id, prio, texto FROM inbox WHERE modo='vivo' AND entregado=0 ORDER BY prio, id").fetchall()
        if not self._silencio(self.ahora):
            ok_prio = pend
        else:
            ok_prio = [p for p in pend if p[1] <= 1]
        d0 = self.ahora.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        hoy = self.est.db.execute("SELECT count(*) FROM inbox WHERE modo='vivo' AND entregado=1 AND prio>1 AND ts>=?", (d0,)).fetchone()[0]
        lote = []
        for id_, prio, texto in ok_prio:
            if prio > 1 and hoy + len([x for x in lote if x[1] > 1]) >= self.reglas["tope_avisos_dia"]:
                self.est.db.execute("UPDATE inbox SET entregado=2 WHERE id=?", (id_,))     # tope: solo queda en la bandeja
                continue
            lote.append((id_, prio, texto))
        for i in range(0, len(lote), 4):
            grupo = lote[i:i + 4]
            try:
                entrega.enviar("\n".join(x[2] for x in grupo))
            except Exception:
                n = int(self.est.meta("fallos_entrega", 0)) + 1
                self.est.poner_meta("fallos_entrega", n)
                return
            self.est.poner_meta("fallos_entrega", 0)
            self.est.db.executemany("UPDATE inbox SET entregado=1 WHERE id=?", [(x[0],) for x in grupo])
            self.resumen["enviados"] += len(grupo)

    # ───────────────────────── ciclo ─────────────────────────
    def avisos_de_lectura(self):
        """3 fallos seguidos leyendo una cuenta → un aviso; al recuperarse, «resuelto»."""
        for cuenta, d in self.datos.items():
            k = f"fallos_{cuenta}"
            if d["ok"]:
                if int(self.est.meta(k, 0)) >= 3:
                    self.est.inbox(f"lectura-ok:{cuenta}:{self.ahora:%Y%m%d%H}", self.modo, 2, "error", f"✅ Vuelvo a leer Google ({cuenta}).")
                self.est.poner_meta(k, 0)
                continue
            n = int(self.est.meta(k, 0)) + 1
            self.est.poner_meta(k, n)
            e = self.errores.get(cuenta)
            if e is not None and e.codigo == 4:
                self.est.inbox(f"auth:{cuenta}:{self.ahora:%Y-%m-%d}", self.modo, 1, "error", f"🔑 Hay que volver a autorizar Google ({cuenta}).")
            elif n == 3:
                self.est.inbox(f"lectura:{cuenta}:{self.ahora:%Y%m%d}", self.modo, 2, "error", f"⚠ No consigo leer Google Tasks/Calendar ({cuenta}) desde hace 15 min.")

    def run(self):
        if not self.simular:
            if config.pausado():
                self.est.poner_meta("ultimo_ciclo", f"{self.ahora.isoformat(timespec='seconds')} pausado")
                self.est.cerrar()
                return {"pausado": True}
            self._lock = open(config.asegurar_dir(config.estado_dir()) / "lock", "w")
            try:
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return {"ocupado": True}
            if self.vivo and not self.est.meta("vivo_desde"):
                self.est.poner_meta("vivo_desde", self.ahora.isoformat(timespec="seconds"))
            if not self.est.meta("primer_ciclo"):
                self.est.poner_meta("primer_ciclo", self.ahora.isoformat(timespec="seconds"))
        self.leer()
        if not self.simular:
            self.avisos_de_lectura()
        self.planificar_tareas()
        self.planificar_eventos()
        self.ejecutar()
        if not self.simular:
            self.entregar()
            self.est.purgar()
            self.est.poner_meta("ultimo_ciclo", f"{self.ahora.isoformat(timespec='seconds')} {self.modo}")
            self.est.poner_meta("ultimo_resumen", json.dumps({k: v for k, v in self.resumen.items() if not k.startswith("_")}))
            self.est.cerrar()
            self._lock.close()
        return dict(self.resumen)

    def informe_simulacro(self):
        """Solo conteos y tipos (sin títulos): qué haría AHORA y qué tiene programado."""
        ahora, futuros, inm = Counter(), Counter(), Counter()
        for a in self.acciones:
            if a.inmediata:
                inm[a.tipo + (" (anterior a hoy)" if False else "")] += 1
            elif self._vencida(a):
                ahora[a.titulo] += 1
            elif a.fire and a.fire > self.ahora:
                futuros[a.titulo] += 1
        return {"lecturas": {k: v for k, v in self.resumen.items() if k.startswith("leidas_") or k in ("tareas", "eventos", "eventos_ajenos")},
                "acciones_inmediatas": dict(inm), "avisos_ahora": dict(ahora), "avisos_programados": dict(futuros),
                "inertes": dict(Counter(m for _, m in self.inertes)), "errores_lectura": {k: f"código {e.codigo}" for k, e in self.errores.items()},
                "llamadas_google": len(self.g.llamadas), "escrituras_google": sum(1 for _, w in self.g.llamadas if w)}
