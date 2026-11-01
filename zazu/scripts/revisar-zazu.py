#!/usr/bin/python3
"""Revisión de Zazu («revisa lo que has hecho», «revisa el calendario», «¿está bien la agenda?»). SIN IA y SOLO LECTURA.

1. Lo que HIZO: lee las acciones de Zazu en state.db (la suya y la de cada perfil): eventos y tareas de Google (gog/zgog),
   borradores y envíos, notas y archivos del Cerebro, recordatorios (cronjob_manage / hermes cron), aprobaciones y errores.
   Las compara con lo que hay AHORA (Google Calendar y Tasks de las dos cuentas con gog --readonly, cron/jobs.json,
   cron/executions.db, los archivos del Cerebro y «00 Inicio/Informe del Cerebro.md») y aplica reglas fijas.
2. AGENDA: cómo está el calendario AHORA, lo haya puesto quien sea (Zazu, el asistente anterior o Fran), de hoy a +60 días,
   las dos cuentas, solo calendarios propios (accessRole owner: fuera festivos y cumpleaños). Duplicados, el mismo evento
   de todo el día y con hora, fin antes del inicio o más de 12 h, eventos sin su tarea gemela en Google Tasks (regla de
   Fran del 07/10) y tareas pendientes vencidas hace más de 3 días.
Imprime bloques DATOS en español para el prompt de la rutina «Revisión de Zazu» o de la skill «revisar-lo-hecho». Todo
pasa por privacidad.tachar(); de lo que pidió Fran solo salen horas y de lo que dijo Zazu una frase corta, nunca de una
conversación en la que leyó las notificaciones del móvil (privacidad.LEE_NOTIFICACIONES). No mira los perfiles de
invitados (zi*). Excepción: con --codigo salen también los IDs de Google del punto (para arreglarlo; no son datos
personales). Nunca cambia nada en Google, el Cerebro ni Hermes: solo escribe su propio estado en
~/.local/state/revisar-zazu/ (o REVISAR_ZAZU_ESTADO).

Uso:
  revisar-zazu.py                 últimas 26 h, todo lo encontrado
  revisar-zazu.py --dias 7        última semana
  revisar-zazu.py --rutina        desde la última pasada (mín. 26 h, 2 h de solape); solo lo NUEVO y como mucho 5 puntos
                                  (lo que no cabe sale la noche siguiente: solo se marca como avisado lo que se manda); si no
                                  hay nada nuevo ni AVISOS sin contar en el último día, la última línea es {"wakeAgent": false}
                                  y Hermes no despierta a la IA ni manda nada.
  revisar-zazu.py --codigo X      solo el punto X (10 caracteres hex), con sus IDs (para «arregla X»), mirando al menos 14 días
                                  atrás; si X junta varios, salen todos. Las órdenes propuestas llevan cada valor entre comillas
                                  simples de shell (shlex.quote): un título con $(…) no se ejecuta.
  revisar-zazu.py --ignorar X     Fran dijo «déjalo X»: no vuelve a salir (si X junta varios, ninguno de ellos)
  revisar-zazu.py --simular-hoy AAAA-MM-DD[THH:MM]   pruebas: hace como si fuera ese momento (sin estado real salvo
                                  con REVISAR_ZAZU_ESTADO)
Gravedad: ERROR = hay que arreglarlo · REVISAR = puede estar bien, que lo mire Fran · INFO = solo para saberlo.
"""
import argparse, difflib, os, hashlib, importlib.util, json, re, shlex, sqlite3, sys, unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path("/home/server/.hermes/scripts")
sys.path.insert(0, str(SCRIPTS))
import recoger                                   # noqa: E402  gog --readonly con credenciales, lista(), limpio()
from privacidad import DE_OTRA, LEE_NOTIFICACIONES, sin_datos_ajenos, tachar  # noqa: E402

TZ = ZoneInfo("Europe/Madrid")
CANAL = {"whatsapp": "WhatsApp", "hub": "HolaZazu", "cli": "terminal", "tui": "terminal", "oneshot": "terminal",
         "api_server": "Modo Hermes", "cron": "rutina"}
H = Path("/home/server/.hermes")
CEREBRO = Path("/home/server/Cerebro")
ESTADO = Path(os.environ.get("REVISAR_ZAZU_ESTADO") or Path.home() / ".local/state/revisar-zazu")
AHORA = datetime.now(TZ)
CUENTA_DE = {None: None, "varas": None, "alvarez": "cuenta.secundaria@example.com"}   # etiqueta → --account de recoger.gog
SIN_ESTADO = False   # --simular-hoy sin REVISAR_ZAZU_ESTADO: no se escribe nada


def flag(cuenta):
    """Lo que hay que poner tras «zgog» para esa cuenta (varas es la de por defecto; gog no tiene alias)."""
    return f" -a {q(CUENTA_DE[cuenta])}" if CUENTA_DE.get(cuenta) else ""


def q(v):
    """Todo valor que entra en una orden propuesta va entre comillas simples de shell: un título con $(…), `…` o $VAR
    se queda en texto y no se ejecuta cuando Zazu lanza el arreglo."""
    return shlex.quote(str(v))

# ───────────────────────── utilidades ─────────────────────────
def corto(s, n=70):
    return recoger.limpio(tachar(str(s or "")), n)


def norm(s):
    """Título comparable: sin emojis, tildes, signos ni «Mañana:»."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if c.isalnum() or c == " ")
    s = re.sub(r"^\s*manana\s+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parecidos(a, b):
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)


def local(ts):
    return datetime.fromtimestamp(ts, TZ)


DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def cuando(d):
    if isinstance(d, datetime):
        d = d.astimezone(TZ)
        return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]} {d.year if d.year != AHORA.year else ''} {d:%H:%M}".replace("  ", " ")
    if isinstance(d, date):
        return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}{' ' + str(d.year) if d.year != AHORA.year else ''} (todo el día)"
    return "?"


def dia_txt(d):
    """«vie 16 oct» (con el año si no es este)."""
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}{' ' + str(d.year) if d.year != AHORA.year else ''}"


def cuenta_de(valor):
    v = str(valor or "")
    return "alvarez" if "alvarez" in v else "varas"


# ───────────────────────── 1. acciones en state.db ─────────────────────────
def bases():
    yield "zazu", H / "state.db"
    for p in sorted((H / "profiles").glob("*/state.db")):
        yield p.parent.name, p


def filas(db, desde):
    """Mensajes de las sesiones con actividad desde `desde`, sin las copias que Hermes re-guarda al compactar o
    rebobinar (mismo message_uid): se queda la más antigua. Las ramas rebobinadas cuentan: lo que hicieron, se hizo."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = ("SELECT m.id, m.session_id, m.role, m.content, m.tool_call_id, m.tool_calls, m.tool_name, m.timestamp, "
         "m.message_uid, s.source, coalesce(s.title,''), coalesce(m.api_content,'') FROM messages m JOIN sessions s ON s.id = m.session_id "
         "WHERE m.session_id IN (SELECT DISTINCT session_id FROM messages WHERE timestamp >= ?) ORDER BY m.timestamp, m.id")
    vistos, out = set(), []
    for f in con.execute(q, (desde.timestamp(),)):
        clave = f[8] or ("id", f[0])
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(f)
    con.close()
    return out


def llamadas(tool_calls):
    """[(id, nombre, args)] desenvolviendo la meta-herramienta tool_call ({"calls":[…]} o {"name","arguments"})."""
    out = []
    for tc in json.loads(tool_calls or "[]"):
        f = tc.get("function") or {}
        try:
            a = json.loads(f.get("arguments") or "{}")
        except Exception:
            a = {}
        if f.get("name") == "tool_call":
            for c in (a.get("calls") or [a]):
                ca = c.get("arguments")
                if isinstance(ca, str):
                    try:
                        ca = json.loads(ca)
                    except Exception:
                        ca = {}
                out.append((tc.get("id"), c.get("name"), ca or {}))
        else:
            out.append((tc.get("id"), f.get("name"), a))
    return out


SEP = set(";&|()\n")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2[ \t]*(?=\n|$)", re.S)
SUBSHELL = re.compile(r"\$\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


def comandos(cmd):
    """Comandos simples de una orden de terminal (respeta comillas; entra en $( … ))."""
    cmd = HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0] + "\n", cmd)   # el cuerpo de un heredoc no son comandos
    extra = [m.group(1) for m in SUBSHELL.finditer(cmd)]
    try:
        lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
        lx.whitespace, lx.whitespace_split, lx.commenters = " \t\r", True, ""
        toks = list(lx)
    except ValueError:            # comillas sin cerrar: línea a línea, sin comillas
        toks = []
        for linea in cmd.splitlines():
            toks += linea.replace('"', " ").replace("'", " ").split() + ["\n"]
    cur = []
    for t in toks:
        if t and set(t) <= SEP and not set(t) & set("<>"):
            if cur:
                yield cur
            cur = []
        else:
            cur.append(t)
    if cur:
        yield cur
    for e in extra:
        yield from comandos(e)


VARIABLE = re.compile(r"(?m)^\s*(?:export\s+)?([A-Za-z_]\w*)=(\"[^\"\n]*\"|'[^'\n]*'|[^\s;&|]+)")
CON_VALOR = {"-a", "--account", "--summary", "--from", "--to", "--location", "--description", "--title", "--due",
             "--notes", "--reminder", "--rrule", "--start-timezone", "--end-timezone", "--max", "--query", "--subject",
             "--body", "--cc", "--bcc", "--days", "--attendees", "--parent", "--client", "--fields", "--select"}


PREFIJOS = {"do", "then", "else", "elif", "if", "while", "until", "!", "time", "exec", "nohup", "command", "builtin", "{", "env", "sudo"}   # «for …; do zgog …»


def gog(toks, vars_):
    i = 0
    while i < len(toks) and (re.match(r"^[A-Za-z_]\w*=", toks[i]) or toks[i] in PREFIJOS or toks[i] == "timeout"):
        if toks[i] == "timeout":   # «timeout [-s X] 30 zgog …»: se salta también sus opciones y la duración
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or re.fullmatch(r"\d+(\.\d+)?[smhd]?", toks[i])):
                i += 1
            continue
        i += 1
    if i < len(toks) and toks[i].split("/")[-1] in ("xargs", "parallel"):   # «… | xargs -I{} zgog tasks delete …»
        i += 1
        while i < len(toks) and toks[i].startswith("-"):
            i += 2 if toks[i] in ("-I", "-n", "-P", "-L", "-d", "-a", "-E", "-s") else 1
    if i >= len(toks) or not re.search(r"(^|/)z?gog$", toks[i]):
        return None
    sub = lambda t: re.sub(r"\$\{?(\w+)\}?", lambda m: vars_.get(m.group(1), m.group(0)), t)
    g = {"acc": None, "f": {}, "pos": [], "enviar": False}
    j = i + 1
    while j < len(toks):
        t = sub(toks[j])
        if re.match(r"^\d?>|^>|^<", t):          # redirecciones: lo que sigue no es del comando
            break
        if t.startswith("-"):
            if t.startswith("--") and "=" in t:
                k, v = t.split("=", 1)
            elif t in CON_VALOR and j + 1 < len(toks):
                k, v, j = t, sub(toks[j + 1]), j + 1
            else:
                k, v = t, True
            if k in ("-a", "--account"):
                g["acc"] = v
            elif k == "--enviar":
                g["enviar"] = True
            else:
                g["f"].setdefault(k, v)
        else:
            g["pos"].append(t)
        j += 1
    return g


VERBOS = {("calendar", v): "CAL_CREAR" for v in ("create", "add", "new")}
VERBOS.update({("calendar", v): "CAL_CAMBIAR" for v in ("update", "edit", "set", "move", "transfer")})
VERBOS.update({("calendar", v): "CAL_BORRAR" for v in ("delete", "rm", "del", "remove")})
VERBOS.update({("tasks", v): "TAREA_CREAR" for v in ("add", "create", "new")})
VERBOS.update({("tasks", v): "TAREA_CAMBIAR" for v in ("update", "edit", "set", "done", "complete", "undo", "move")})
VERBOS.update({("tasks", v): "TAREA_BORRAR" for v in ("delete", "rm", "del", "remove", "clear")})
VERBOS.update({("contacts", v): "CONTACTO" for v in ("create", "add", "update", "delete", "rm")})


def accion_gog(g):
    p = g["pos"] + ["", "", "", ""]
    svc = {"cal": "calendar", "mail": "gmail", "email": "gmail"}.get(p[0], p[0])
    if svc == "gmail":
        if p[1] in ("drafts", "draft"):
            tipo = "ENVIO" if p[2] in ("send", "post") else "BORRADOR" if p[2] in (
                "create", "add", "new", "update", "edit", "set", "reply", "reply-all", "replyall", "forward", "fwd") else None
        else:
            tipo = "ENVIO" if p[1] in ("send", "reply", "forward") else "CORREO_CAMBIO" if p[1] in (
                "trash", "delete", "archive", "modify", "batch") else None
    else:
        tipo = VERBOS.get((svc, p[1]))
        if svc == "tasks" and p[1] == "lists":
            tipo = None
    if not tipo or any(k in g["f"] for k in ("--help", "-h", "--dry-run", "-n")):
        return None
    a = {"tipo": tipo, "cuenta": cuenta_de(g["acc"]), "f": g["f"]}
    if tipo.startswith("CAL"):
        a["cal"], a["id"] = (p[2] or "primary"), (p[3] if tipo != "CAL_CREAR" else None)
    elif tipo.startswith("TAREA"):
        a["lista"], a["id"] = (p[2] or "@default"), (p[3] if tipo != "TAREA_CREAR" else None)
        a["verbo"] = p[1]
    if a.get("id") and a["id"].startswith("$"):
        a["id"] = None                          # bucle: el id va en una variable
    return a


PY_GOG = re.compile(r"['\"](calendar|tasks|gmail)['\"]\s*,\s*['\"](create|add|update|delete|done|send|drafts)['\"](?:\s*,\s*['\"](\w+)['\"])?")
PY_ENVIO = re.compile(r"(localhost|127\.0\.0\.1):3100/send|['\"]wacli['\"]\s*,\s*['\"](send|forward)")
ERROR_TXT = re.compile(r"Google API error|\b(error|failed|falló|invalid|unknown flag|not found|no such file|"
                       r"command not found|traceback|permission denied)\b|^BLOCKED", re.I | re.M)
ID_LINEA = re.compile(r'(?m)^(?:id\t|\s*"id":\s*")([A-Za-z0-9_\-]{10,})')


def resultado(contenido):
    """(texto, ok_general, tipo_bloqueo) de la salida de una herramienta."""
    txt = contenido or ""
    try:
        j = json.loads(txt)
    except Exception:
        j = None
    bloqueo = None
    if isinstance(j, dict):
        err = str(j.get("error") or "")
        txt = f"{j.get('output') or ''}\n{err}\n{j.get('approval') or ''}"
        if j.get("status") == "blocked" or err.startswith(("BLOCKED", "Zazu no puede", "Hermes no puede")):
            bloqueo = clase_bloqueo(err)
        ec = j.get("exit_code")
        ok = not bloqueo and not err and ec in (0, None)
        if "approved by the user" in str(j.get("approval") or ""):
            bloqueo = bloqueo or "aprobada"
    else:
        if txt.startswith("BLOCKED") or txt.startswith("Zazu no puede"):
            bloqueo = clase_bloqueo(txt)
        ok = not bloqueo
    return txt, ok, bloqueo


def clase_bloqueo(t):
    t = t or ""
    if "User denied" in t or "denied by the user" in t or "denied by user" in t:
        return "denegada"
    if "timed out without user response" in t:
        return "sin respuesta"
    if "requires approval" in t:
        return "sin canal para aprobar"
    if "deny rule" in t:
        return "regla"
    if "Security scan" in t or "flagged as dangerous" in t or "threat pattern" in t:
        return "seguridad"
    if t.startswith("Zazu no puede") or "Hermes no puede" in t:
        return "control"
    return "otro"


def ruta(t, cwd=""):
    """Ruta absoluta normalizada (~, /home/servidor, ~/Compartido = Cerebro/40 Compartido, relativa a un cd previo)."""
    t = re.sub(r"^~(?=/|$)|^\$HOME(?=/|$)", "/home/server", str(t)).replace("/home/servidor/", "/home/server/")
    if not t.startswith("/") and cwd:
        t = cwd.rstrip("/") + "/" + t
    return re.sub(r"^/home/server/Compartido(?=/|$)", "/home/server/Cerebro/40 Compartido", t)


def destinos(toks, cwd=""):
    """Rutas que escribe un comando de terminal (cp/mv/rsync/install destino, tee, > y >>, mkdir, touch)."""
    out = []
    cmd = toks[0].split("/")[-1]
    for k, t in enumerate(toks):
        if t in (">", ">>") and k + 1 < len(toks):
            out.append(ruta(toks[k + 1], cwd))
    args = [ruta(t, cwd) for t in toks[1:] if not t.startswith("-")]
    if cmd in ("cp", "mv", "rsync", "install") and args:
        out.append(args[-1])
    if cmd in ("tee", "mkdir", "touch"):
        out += args
    return [r for r in out if r.startswith("/") and not r.startswith(("/dev/", "/proc/"))]


BUCLE = re.compile(r"\bfor\s+\w+(?:\s*,\s*\w+)*\s+in\b|\bwhile\s|\buntil\s|\bxargs\b|\bparallel\b|\.forEach\(")


def leer_acciones(desde):
    """Turnos (petición de Fran → lo que hizo Zazu → lo que contestó) con sus acciones. Sin los perfiles de invitados
    (zi*): no tienen terminal ni escriben archivos, y su uso no es trabajo de Zazu para Fran."""
    turnos = []
    for perfil, db in bases():
        if perfil.startswith("zi"):
            continue
        try:
            fs = filas(db, desde)
        except Exception as e:
            AVISOS.append(f"no se pudo leer {db.name} de {perfil}: {e}")
            continue
        res = {f[4]: f[3] for f in fs if f[2] == "tool" and f[4]}
        # conversaciones en las que Zazu leyó las notificaciones del móvil (en una llamada, en la salida de una herramienta
        # o en datos que mete el sistema): de ellas nunca se cita lo que dijo Zazu (privacidad.LEE_NOTIFICACIONES)
        movil = {f[1] for f in fs if (f[5] and LEE_NOTIFICACIONES.search(f[5]))
                 or (f[2] in ("tool", "user") and f[3] and LEE_NOTIFICACIONES.search(f[3]))
                 or (len(f) > 11 and f[11] and (LEE_NOTIFICACIONES.search(f[11]) or DE_OTRA.search(f[11])))}
        turno, scripts = None, {}
        for (mid, sid, rol, cont, tcid, tcs, tname, ts, uid, fuente, titulo, _api) in fs:
            if rol == "user" or turno is None or turno["sid"] != sid:
                turno = {"perfil": perfil, "invitado": False, "sid": sid, "fuente": fuente, "titulo": titulo,
                         "movil": sid in movil, "ts": ts, "peticion": "", "acciones": [], "respuesta": "",
                         "bloqueos": [], "errores": []}
                turnos.append(turno)
                if rol == "user":
                    turno["peticion"] = sin_datos_ajenos(cont or "") if fuente != "cron" else ""
                    continue
            if rol != "assistant":
                continue
            if cont and not tcs:
                turno["respuesta"] = cont
            for (cid, nombre, a) in llamadas(tcs):
                txt, ok, bloqueo = resultado(res.get(cid))
                base = {"ts": ts, "herr": nombre, "ok": ok, "salida": txt, "cid": cid, "sid": sid}
                if bloqueo:
                    turno["bloqueos"].append((bloqueo, nombre, ts))
                if not ok and bloqueo not in ("aprobada",):
                    turno["errores"].append((nombre, txt, bloqueo))
                if nombre == "terminal":
                    cmd = str(a.get("command") or "")
                    vars_ = {m.group(1): m.group(2).strip("\"'") for m in VARIABLE.finditer(cmd)}
                    nuevos = [m.group(1) for m in ID_LINEA.finditer(txt)]
                    cwd = ""
                    # Python o scripts que llaman a gog/WhatsApp por dentro (subprocess.run([... "tasks", "add" ...]), :3100)
                    codigo = cmd + "".join(scripts.get(ruta(m.group(1)), "") for m in re.finditer(r"(?:python3?|bash|sh)\s+(\S+\.(?:py|sh))\b", cmd))
                    base["bucle"] = bool(BUCLE.search(codigo))   # for/while/xargs: un solo comando puede borrar muchas
                    if re.search(r"\bpython3?\b|<<", cmd):
                        for m in PY_GOG.finditer(codigo):
                            ac = accion_gog({"acc": "alvarez" if "alvarez" in codigo else None, "f": {}, "pos": [m.group(1), m.group(2), m.group(3) or ""], "enviar": False})
                            if ac:
                                if ac["tipo"] in ("CAL_CREAR", "TAREA_CREAR"):
                                    ac["id_salida"] = nuevos.pop(0) if nuevos else None
                                ac["ok"] = ok and (bool(ac.get("id_salida")) or not ERROR_TXT.search(txt))
                                turno["acciones"].append({**base, **ac, "script": True})
                    if PY_ENVIO.search(codigo):
                        turno["acciones"].append({**base, "tipo": "ENVIO", "ok": ok and bool(re.search(r'"success":\s*true|messageId', txt))})
                    for toks in comandos(cmd):
                        g = gog(toks, vars_)
                        if g:
                            ac = accion_gog(g)
                            if ac:
                                if ac["tipo"] in ("CAL_CREAR", "TAREA_CREAR"):
                                    ac["id_salida"] = nuevos.pop(0) if nuevos else None
                                ac["ok"] = ok and (not ERROR_TXT.search(txt) or bool(ac.get("id_salida"))
                                                   or (ac.get("id") and ac["id"] in txt))
                                turno["acciones"].append({**base, **ac, "ok": ac["ok"]})
                            elif g["enviar"]:
                                turno["acciones"].append({**base, "tipo": "ENVIO", "cuenta": cuenta_de(g["acc"])})
                            continue
                        prog = toks[0].split("/")[-1] if toks else ""
                        if prog == "hermes" and len(toks) > 2 and toks[1] == "cron" and toks[2] in ("create", "add", "edit", "rm", "remove", "delete"):
                            turno["acciones"].append({**base, "tipo": "REC_" + toks[2].upper()})
                        elif prog == "hermes" and len(toks) > 1 and toks[1] == "send" or prog == "wacli" and "send" in toks[1:3]:
                            turno["acciones"].append({**base, "tipo": "ENVIO"})
                        if toks and toks[0] == "cd" and len(toks) > 1:
                            cwd = ruta(toks[1], cwd)
                        for r in destinos(toks, cwd):
                            turno["acciones"].append({**base, "tipo": "NOTA" if "/Cerebro/" in r else "ESCRITO", "ruta": r,
                                                      "ok": ok and not ERROR_TXT.search(txt)})
                elif nombre in ("write_file", "patch"):
                    r = ruta(a.get("path") or a.get("file_path") or "")
                    if a.get("content") and r.endswith((".py", ".sh")):
                        scripts[r] = str(a.get("content"))
                    turno["acciones"].append({**base, "tipo": "NOTA" if "/Cerebro/" in r else "ESCRITO", "ruta": r})
                elif nombre == "cronjob_manage":
                    acc = str(a.get("action") or "")
                    if acc in ("create", "add", "update", "edit", "remove", "delete", "pause"):
                        jid = None
                        try:
                            jid = json.loads(res.get(cid) or "{}").get("job_id")
                        except Exception:
                            pass
                        turno["acciones"].append({**base, "tipo": "REC_" + acc.upper(), "job": jid,
                                                  "deliver": a.get("deliver"), "schedule": a.get("schedule")})
                elif nombre == "send_message":
                    turno["acciones"].append({**base, "tipo": "ENVIO"})
                elif nombre == "memory" and ({a.get("action")} | {o.get("action") for o in a.get("operations") or [] if isinstance(o, dict)}) & {"add", "replace", "remove"}:
                    turno["acciones"].append({**base, "tipo": "MEMORIA"})
    return [t for t in turnos if t["ts"] >= desde.timestamp() or any(a["ts"] >= desde.timestamp() for a in t["acciones"])]


# ───────────────────────── 2. estado actual (Google) ─────────────────────────
CACHE = {}


def g_json(args, cuenta):
    k = (tuple(args), cuenta)
    if k not in CACHE:
        try:
            CACHE[k] = recoger.gog(args, CUENTA_DE[cuenta], intentos=2)
        except Exception as e:
            AVISOS.append(f"no se pudo consultar Google ({cuenta}: {' '.join(args[:2])}): {e}")
            CACHE[k] = None
    return CACHE[k]


def evento(cuenta, cal, eid):
    d = g_json(["calendar", "event", cal or "primary", eid], cuenta)
    return d.get("event", d) if isinstance(d, dict) else None


def eventos_dia(cuenta, dia):
    """Eventos de todos los calendarios de dia-1 a dia+1 (sin festivos ni cumpleaños de contactos)."""
    d = g_json(["calendar", "events", "--all", f"--from={dia - timedelta(days=1)}", f"--to={dia + timedelta(days=2)}",
                "--max=250", "--all-pages"], cuenta)
    evs = recoger.lista(d, "events", "items") if d else []
    return [e for e in evs if e.get("status") != "cancelled"
            and not re.search(r"#(holiday|contacts)@", str((e.get("organizer") or {}).get("email")))]


def tareas(cuenta, lista):
    d = g_json(["tasks", "list", lista, "--max=100", "--all", "--show-completed", "--show-hidden", "--show-deleted",
                f"--updated-min={(AHORA - timedelta(days=45)).date()}T00:00:00Z"], cuenta)
    return recoger.lista(d, "tasks", "items") if d else []


def inicio_fin(e):
    def uno(k):
        x = e.get(k) or {}
        if x.get("dateTime"):
            return datetime.fromisoformat(x["dateTime"].replace("Z", "+00:00"))
        if x.get("date"):
            return date.fromisoformat(x["date"])
        return None
    return uno("start"), uno("end")


def dia_de(v):
    return v.astimezone(TZ).date() if isinstance(v, datetime) else v


# ───────────────────────── 3. reglas ─────────────────────────
HALLAZGOS, AVISOS = [], []


def hallazgo(grav, area, clave, texto, arreglo="", ids=(), grupo=None, etiqueta="", area_huella=None):
    """`ids`: IDs de Google («cuenta calendario/lista id»), solo salen con --codigo. `grupo`: los del mismo grupo salen
    juntos en una línea con un código común (GRUPOS). `area_huella`: para que dos reglas que ven lo mismo den el mismo código."""
    huella = hashlib.sha1(f"{area_huella or area}|{clave}".encode()).hexdigest()[:10]
    HALLAZGOS.append({"grav": grav, "area": area, "huella": huella, "texto": tachar(texto), "arreglo": arreglo,   # los valores ya van tachados (corto) y entrecomillados (shlex)
                      "ids": [i for i in ids if ID_GOOGLE.match(i)], "grupo": grupo, "etiqueta": tachar(etiqueta)})


ID_GOOGLE = re.compile(r"^(varas|alvarez) [\w@.\-]+ [A-Za-z0-9_\-]{5,200}$")


HORA_PEDIDA = re.compile(r"\b([01]?\d|2[0-3])(?:[:.h]([0-5]\d)|\s*(?:h\b|horas\b))|\ba las (\d{1,2})(?!\d|[:.h]\d)(?:\s*y\s*(media|cuarto))?", re.I)
DIRECCION = re.compile(r"\b(c/|calle|avda\.?|avenida|plaza|pza\.?|paseo|carrer|camino|ctra\.?|carretera)\s+\w", re.I)
FECHA_PEDIDA = re.compile(r"\b(hoy|mañana|pasado mañana|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|"
                          r"\d{1,2}[/-]\d{1,2}|\d{1,2} de [a-z]+|semana que viene|próxima semana|el día \d)", re.I)


def horas_pedidas(txt, solo_dichas=False):
    """Horas que aparecen en lo que pidió Fran; para comparar, también la misma hora +12 h («a las 5» = 17:00)."""
    out = set()
    for m in HORA_PEDIDA.finditer(txt or ""):
        if m.group(3):
            h, mi = int(m.group(3)), {"media": 30, "cuarto": 15}.get((m.group(4) or "").lower(), 0)
        else:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
        out |= {(h % 24, mi)} if solo_dichas else {(h % 24, mi), ((h + 12) % 24, mi)}
    return out


def offset_madrid(texto_fecha):
    """Si la hora del comando lleva un desfase (+02:00) que no es el de España ese día, devuelve (usado, correcto)."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?)([+-]\d\d:\d\d|Z)$", str(texto_fecha or ""))
    if not m:
        return None
    naive = datetime.fromisoformat(m.group(1))
    usado = m.group(2)
    bueno = naive.replace(tzinfo=TZ).strftime("%z")
    bueno = bueno[:3] + ":" + bueno[3:]
    return None if usado in (bueno, "Z") else (usado, bueno)


def de_asistente(e):
    """Evento puesto por el asistente (OpenClaw/Zazu): marca en la descripción o propiedad privada clawbot."""
    return "Añadido por tu asistente" in str(e.get("description") or "") or "clawbot" in json.dumps(e.get("extendedProperties") or {})


def corregido_luego(a, turnos):
    """¿Un fallo se arregló después (misma sesión, 2 h): misma familia con el mismo id o un título parecido?"""
    fam = a["tipo"].split("_")[0]
    titulo = a["f"].get("--summary") or a["f"].get("--title") or ""
    for t in turnos:
        for b in t["acciones"]:
            if b is a or not b.get("ok") or b["tipo"].split("_")[0] != fam or not (0 <= b["ts"] - a["ts"] <= 7200):
                continue
            if t["sid"] != a.get("sid"):
                continue
            if b.get("script") or not titulo or "$" in titulo or (a.get("id") and a.get("id") == b.get("id")) \
                    or parecidos(titulo, b["f"].get("--summary") or b["f"].get("--title")):
                return True
    return False


def revisar_calendario(turnos):
    tocados = {}   # (cuenta, cal, id) → (acción, turno)
    for t in turnos:
        for a in t["acciones"]:
            if not a["tipo"].startswith("CAL"):
                continue
            eid = a.get("id") or a.get("id_salida")
            titulo = corto(a["f"].get("--summary") or "", 50)
            if not a["ok"] and not corregido_luego(a, turnos):
                hallazgo("REVISAR", "Calendario", f"fallo|{a['cid']}|{eid}",
                         f"{local(a['ts']):%d/%m %H:%M} · {a['tipo'].replace('CAL_', '').lower()} «{titulo or eid or '?'}» dio error: "
                         f"{corto(ERROR_TXT.search(a['salida']).group(0) if ERROR_TXT.search(a['salida']) else 'sin prueba', 60)}. "
                         "Mira si se repitió bien después.")
            for k in ("--from", "--to"):
                d = offset_madrid(a["f"].get(k))
                if d and a["ok"]:
                    hallazgo("ERROR", "Calendario", f"offset|{eid or titulo}",
                             f"«{titulo}»: se creó con {d[0]} pero ese día en España es {d[1]} → sale 1 h desplazado.",
                             f"zgog{flag(a['cuenta'])} calendar update {q(a.get('cal') or 'primary')} <id> "
                             f"--from=<AAAA-MM-DDTHH:MM:00> --to=<…> --start-timezone=Europe/Madrid --end-timezone=Europe/Madrid "
                             "(hora local SIN +01:00/+02:00: Google aplica el horario de verano solo)",
                             ids=[f"{a['cuenta']} {a.get('cal') or 'primary'} {eid}"] if eid else ())
                    break
            if a["tipo"] == "CAL_BORRAR" and eid:
                creado_por_zazu = any(b.get("id_salida") == eid for tt in turnos for b in tt["acciones"])
                e = evento(a["cuenta"], a.get("cal"), eid) or {} if not creado_por_zazu else {}
                if not creado_por_zazu and not de_asistente(e):
                    hallazgo("REVISAR", "Calendario", f"borrado|{eid}",
                             f"{local(a['ts']):%d/%m %H:%M} · borró «{corto(e.get('summary'), 50) or eid}», un evento que no había creado él. Confirma que querías quitarlo.")
            if eid and a["tipo"] != "CAL_BORRAR" and a["ok"]:
                tocados[(a["cuenta"], a.get("cal") or "primary", eid)] = (a, t)
            elif a["ok"] and a["tipo"] == "CAL_CREAR" and titulo:
                tocados[(a["cuenta"], a.get("cal") or "primary", "busca:" + titulo)] = (a, t)
    for (cuenta, cal, eid), (a, t) in tocados.items():
        titulo = a["f"].get("--summary") or ""
        if eid.startswith("busca:"):
            ini = str(a["f"].get("--from") or "")[:10]
            try:
                dia = date.fromisoformat(ini)
            except ValueError:
                continue
            cand = [e for e in eventos_dia(cuenta, dia) if parecidos(e.get("summary"), titulo)]
            if not cand:
                hallazgo("ERROR", "Calendario", f"falta|{norm(titulo)}|{ini}",
                         f"Dijo crear «{corto(titulo, 50)}» el {ini} y no está en el calendario ({cuenta}).",
                         "Volver a crearlo (con el OK de Fran).")
                continue
            e = cand[0]
        else:
            e = evento(cuenta, cal, eid)
            if e is None:
                continue
            if e.get("status") == "cancelled":
                borrado_por_zazu = any(b["tipo"] == "CAL_BORRAR" and b.get("id") == eid for tt in turnos for b in tt["acciones"])
                if not borrado_por_zazu:
                    hallazgo("ERROR", "Calendario", f"desaparecido|{eid}",
                             f"«{corto(e.get('summary') or titulo, 50)}» lo creó/cambió Zazu y ya no está (borrado fuera de Zazu o por error).")
                continue
            if titulo and a["tipo"] == "CAL_CREAR" and not parecidos(e.get("summary"), titulo):
                continue   # el id de la salida no era de este comando (orden con varios comandos): no se puede afirmar nada
        etiqueta = f"«{corto(e.get('summary'), 50)}» ({cuenta})"
        ini, fin = inicio_fin(e)
        if ini is None:
            continue
        creado = local(a["ts"])
        if a["tipo"] == "CAL_CREAR" or "--from" in a["f"]:
            if (isinstance(ini, datetime) and ini < creado - timedelta(hours=1)) or (not isinstance(ini, datetime) and ini < creado.date()):
                if not (e.get("recurrence") or e.get("recurringEventId")):
                    hallazgo("ERROR", "Calendario", f"pasado|{e.get('id')}",
                             f"{etiqueta}: se puso el {cuando(ini)}, que ya había pasado cuando se creó ({creado:%d/%m %H:%M}). ¿Año o mes equivocado?")
        if isinstance(ini, datetime):
            li = ini.astimezone(TZ)
            pedidas = horas_pedidas(t["peticion"])
            if li.hour < 7 and (li.hour, li.minute) not in pedidas:
                hallazgo("REVISAR", "Calendario", f"madrugada|{e.get('id')}", f"{etiqueta}: está a las {li:%H:%M} de la madrugada ({cuando(ini)}). ¿Hora o zona horaria mal?")
            if pedidas and (li.hour, li.minute) not in pedidas and a["tipo"] == "CAL_CREAR":
                hp = sorted({f"{h:02d}:{m:02d}" for h, m in horas_pedidas(t["peticion"], solo_dichas=True)})[:3]
                hallazgo("REVISAR", "Calendario", f"hora|{e.get('id')}",
                         f"{etiqueta}: en la petición salen las {', '.join(hp)} y el evento está a las {li:%H:%M}.")
            if isinstance(fin, datetime) and (fin <= ini or fin - ini > timedelta(hours=12)):
                hallazgo("REVISAR", "Calendario", f"duracion|{e.get('id')}",
                         f"{etiqueta}: dura {str(fin - ini)[:-3]} ({cuando(ini)} → {cuando(fin)}). ¿Fin equivocado?")
            tz = str((e.get("start") or {}).get("timeZone") or "")
            if tz.startswith("Etc/") and (e.get("recurrence") or e.get("recurringEventId")):
                hallazgo("REVISAR", "Calendario", f"zona|{e.get('recurringEventId') or e.get('id')}",
                         f"{etiqueta}: se repite con zona fija {tz}; tras el cambio de hora (25 oct) saldrá 1 h desplazado.",
                         f"zgog{flag(cuenta)} calendar update {q(cal)} <id> --start-timezone=Europe/Madrid --end-timezone=Europe/Madrid",
                         ids=[f"{cuenta} {cal} {e.get('recurringEventId') or e.get('id')}"])
        elif isinstance(fin, date) and fin <= ini:
            hallazgo("ERROR", "Calendario", f"fin|{e.get('id')}", f"{etiqueta}: el día de fin es anterior o igual al de inicio.")
        if DIRECCION.search(t["peticion"] or "") and not e.get("location") and a["tipo"] == "CAL_CREAR":
            hallazgo("REVISAR", "Calendario", f"lugar|{e.get('id')}", f"{etiqueta}: la petición traía una dirección y el evento no tiene lugar.")
        # duplicados y solapes (mismo día ±1, misma cuenta)
        for o in eventos_dia(cuenta, dia_de(ini)):
            if str(o.get("id")).split("_")[0] == str(e.get("id")).split("_")[0]:
                continue   # el mismo evento o una repetición suya
            oi, of = inicio_fin(o)
            if oi is None:
                continue
            if parecidos(o.get("summary"), e.get("summary")) and abs((dia_de(oi) - dia_de(ini)).days) <= 1:
                par = "|".join(sorted([e.get("id"), o.get("id")]))
                # el más nuevo primero (por «created»), igual que en la AGENDA: «borrar el primer ID» borra el repetido
                ocal = o.get("CalendarID") if o.get("CalendarID") and o.get("CalendarID") != e.get("CalendarID") else cal
                dos = sorted([(e, cal), (o, ocal)], key=lambda x: str(x[0].get("created") or ""), reverse=True)
                hallazgo("ERROR", "Calendario", f"duplicado|{par}",
                         f"{etiqueta} está repetido: hay otro igual el {cuando(oi)}. Propongo borrar el que se creó después (el primer ID).",
                         f"zgog{flag(cuenta)} calendar delete {q(dos[0][1])} <id> --force (con el OK de Fran)",
                         ids=[f"{cuenta} {c} {x.get('id')}" for x, c in dos])
            elif isinstance(ini, datetime) and isinstance(oi, datetime) and isinstance(fin, datetime) and isinstance(of, datetime) \
                    and oi < fin and ini < of and o.get("transparency") != "transparent" and of - oi > timedelta(minutes=15):
                par = "|".join(sorted([e.get("id"), o.get("id")]))
                hallazgo("REVISAR", "Calendario", f"solape|{par}",
                         f"{etiqueta} ({cuando(ini)}) se solapa con «{corto(o.get('summary'), 40)}» ({cuando(oi)}).")


# ───────────────────────── 3b. AGENDA: cómo está ahora, la haya hecho quien sea ─────────────────────────
TIPOS_FUERA = {"birthday", "workingLocation", "outOfOffice", "focusTime"}   # cumpleaños de contactos y similares
VACIAS = set("para como este esta esto estos estas desde hasta sobre entre cita citas plazo tarde noche todo toda "
             "dias semana antes despues hora horas manana pasado tras ante cual donde cuando".split())
AGENDA = {}   # resumen para la salida
GRUPOS = {"sintarea": ("{n} eventos de los próximos 30 días no tienen su tarea gemela en Google Tasks (regla de Fran del 07/10)",
                       "Crear cada tarea con su fecha (con el OK de Fran): --codigo <código> da la orden exacta de cada una, "
                       "con el título ya entre comillas simples; úsala tal cual."),
          "vencida3": ("{n} tareas pendientes llevan más de 3 días vencidas",
                       "Preguntar a Fran si ya están hechas (zgog tasks done @default <id>) o qué fecha nueva ponerles "
                       "(zgog tasks update @default <id> --due=AAAA-MM-DD); --codigo <código> da la lista.")}


def palabras(s):
    return {w for w in norm(s).split() if len(w) >= 4 and w not in VACIAS}


def tiene_tarea(titulo, dia, tareas_):
    """¿Hay una tarea gemela? Con fecha a ±7 días: título parecido (≥0,6) o 2+ palabras significativas en común (4+ letras,
    sin las vacías). Sin fecha: solo por parecido (≥0,6); si no, «Cancelar amazon aws» taparía cualquier evento con «Amazon»."""
    n, pal = norm(titulo), palabras(titulo)
    for t in tareas_:
        nt = norm(t.get("title"))
        if not nt:
            continue
        due = str(t.get("due") or "")[:10]
        try:
            fecha = date.fromisoformat(due) if due else None
        except ValueError:
            fecha = None
        if fecha and abs((fecha - dia).days) > 7:
            continue
        if difflib.SequenceMatcher(None, n, nt).ratio() >= 0.6 or (fecha and len(pal & palabras(t.get("title"))) >= 2):
            return True
    return False


def revisar_agenda(_turnos=None):
    hoy = AHORA.date()
    hasta = hoy + timedelta(days=60)
    evs, tareas_, tareas_ok = [], [], True
    for cuenta in ("varas", "alvarez"):
        cals = g_json(["calendar", "calendars"], cuenta)
        d = g_json(["calendar", "events", "--all", f"--from={hoy}", f"--to={hasta + timedelta(days=1)}", "--max=250",
                    "--all-pages"], cuenta) if cals is not None else None
        n = 0
        if d is not None:
            propios = {c.get("id"): ("primary" if c.get("primary") else c.get("id"))
                       for c in recoger.lista(cals, "calendars", "items") if c.get("accessRole") == "owner"}
            for e in recoger.lista(d, "events", "items"):
                cid = e.get("CalendarID")
                if e.get("status") == "cancelled" or e.get("eventType") in TIPOS_FUERA or (cid is not None and cid not in propios):
                    continue
                ini, fin = inicio_fin(e)
                if ini is None:
                    continue
                evs.append({"c": cuenta, "cal": propios.get(cid, "primary"), "e": e, "ini": ini, "fin": fin,
                            "dia": dia_de(ini), "todo": not isinstance(ini, datetime)})
                n += 1
        AGENDA[cuenta] = n if d is not None else None
        # tareas de «Mis tareas» (@default), también las hechas (cuentan como gemela). La lista «Notas del asistente»
        # guarda notas con fecha, no tareas: no cuenta.
        dt = g_json(["tasks", "list", "@default", "--max=100", "--all", "--show-completed", "--show-hidden"], cuenta)
        if dt is None:
            tareas_ok = False
        for t in recoger.lista(dt, "tasks", "items") if dt else []:
            if not t.get("deleted"):
                tareas_.append({**t, "_c": cuenta, "_l": "@default"})
    AGENDA["tareas"] = len(tareas_)
    AGENDA["pendientes"] = sum(1 for t in tareas_ if t.get("status") == "needsAction")
    AGENDA["hasta"] = hasta
    ident = lambda x: f"{x['c']} {x['cal']} {x['e'].get('id')}"
    hora = lambda x: "todo el día" if x["todo"] else f"a las {x['ini'].astimezone(TZ):%H:%M}"
    evs.sort(key=lambda x: (x["dia"], str(x["ini"])))
    # duplicados: mismo día y título parecido (≥85 %), que no sean el mismo evento ni la misma serie
    for i, a in enumerate(evs):
        for b in evs[i + 1:]:
            if b["dia"] != a["dia"]:
                break
            ea, eb = a["e"], b["e"]
            if ea.get("id") == eb.get("id") or (ea.get("iCalUID") and ea.get("iCalUID") == eb.get("iCalUID")) \
                    or (ea.get("recurringEventId") and ea.get("recurringEventId") == eb.get("recurringEventId")) \
                    or not parecidos(ea.get("summary"), eb.get("summary")):
                continue
            par = "|".join(sorted([ea["id"], eb["id"]]))
            titulo = corto(ea.get("summary"), 50)
            ultimo = max((a, b), key=lambda x: str(x["e"].get("created") or ""))
            donde = f" (cuentas {a['c']} y {b['c']})" if a["c"] != b["c"] else ""
            if a["todo"] != b["todo"]:
                hallazgo("REVISAR", "Agenda", f"diayhora|{par}",
                         f"«{titulo}» está dos veces el {dia_txt(a['dia'])}: una de todo el día y otra {hora(b if a['todo'] else a)}{donde}. ¿Sobra una?",
                         f"Si sobra una, la que se creó después es la {'de todo el día' if ultimo['todo'] else 'de ' + hora(ultimo)[2:]}: "
                         f"zgog{flag(ultimo['c'])} calendar delete {q(ultimo['cal'])} <id> --force (con el OK de Fran).",
                         ids=[ident(a), ident(b)])
            elif a["todo"] or a["ini"] == b["ini"]:
                hallazgo("ERROR", "Agenda", f"duplicado|{par}",
                         f"«{titulo}» está repetido el {cuando(a['ini'])}{donde}. Propongo borrar el que se creó después (el primer ID).",
                         f"zgog{flag(ultimo['c'])} calendar delete {q(ultimo['cal'])} <id> --force (con el OK de Fran).",
                         ids=[ident(ultimo), ident(a if ultimo is b else b)], area_huella="Calendario")
            else:
                hallazgo("REVISAR", "Agenda", f"dosveces|{par}",
                         f"«{titulo}» sale dos veces el mismo día: {cuando(a['ini'])} y {hora(b)}{donde}. ¿Es repetido?",
                         f"Si sobra uno, el que se creó después es el de {hora(ultimo)[2:]}: "
                         f"zgog{flag(ultimo['c'])} calendar delete {q(ultimo['cal'])} <id> --force (con el OK de Fran).",
                         ids=[ident(a), ident(b)])
    vistos = set()
    for x in evs:
        e = x["e"]
        serie = e.get("recurringEventId") or e.get("id")
        titulo = corto(e.get("summary"), 50)
        ini, fin = x["ini"], x["fin"]
        # fin antes del inicio o más de 12 h (una vez por serie)
        if serie not in vistos and fin is not None and type(ini) is type(fin):
            vistos.add(serie)
            if fin <= ini:
                hallazgo("REVISAR", "Agenda", f"fin|{serie}", f"«{titulo}» ({cuando(ini)}) termina antes de empezar.",
                         f"zgog{flag(x['c'])} calendar update {q(x['cal'])} <id> --to=… (con la hora buena)", ids=[ident(x)])
            elif not x["todo"] and fin - ini > timedelta(hours=12):
                hallazgo("REVISAR", "Agenda", f"duracion|{serie}",
                         f"«{titulo}» dura {int((fin - ini).total_seconds() // 3600)} h ({cuando(ini)} → {cuando(fin)}). ¿Fin equivocado?",
                         f"zgog{flag(x['c'])} calendar update {q(x['cal'])} <id> --to=… (con la hora buena)", ids=[ident(x)],
                         area_huella="Calendario" if not e.get("recurringEventId") else None)
        # evento suelto de los próximos 30 días sin tarea gemela (los «Mañana: …» son el aviso del día antes de otro)
        if not tareas_ok or e.get("recurringEventId") or e.get("recurrence") or x["dia"] > hoy + timedelta(days=30) \
                or (ini < AHORA if not x["todo"] else x["dia"] < hoy) or re.match(r"^\W*mañana\b", e.get("summary") or "", re.I):
            continue
        if not tiene_tarea(e.get("summary"), x["dia"], tareas_):
            entero = corto(e.get("summary"), 150)
            hallazgo("REVISAR", "Agenda", f"sintarea|{e.get('id')}",
                     f"«{titulo}» ({dia_txt(x['dia'])}{'' if x['todo'] else ini.astimezone(TZ).strftime(' %H:%M')}, cuenta {x['c']}) "
                     "no tiene tarea en Google Tasks.",
                     f"zgog{flag(x['c'])} tasks add @default --title={q(entero)} --due={q(x['dia'])} (con el OK de Fran)",
                     ids=[ident(x)], grupo="sintarea", etiqueta=f"«{corto(e.get('summary'), 40)}» ({dia_txt(x['dia'])})")
    # tareas pendientes vencidas hace más de 3 días
    for t in tareas_:
        due = str(t.get("due") or "")[:10]
        if t.get("status") == "needsAction" and due and due < str(hoy - timedelta(days=3)):
            hallazgo("REVISAR", "Agenda", f"vencida3|{t.get('id')}",
                     f"Tarea «{corto(t.get('title'), 50)}» ({t['_c']}) vencida desde el {due[8:10]}/{due[5:7]} "
                     f"({(hoy - date.fromisoformat(due)).days} días).",
                     f"¿Hecha? zgog{flag(t['_c'])} tasks done {q(t['_l'])} {q(t.get('id'))} · ¿Otra fecha? "
                     f"zgog{flag(t['_c'])} tasks update {q(t['_l'])} {q(t.get('id'))} --due=AAAA-MM-DD (con el OK de Fran)",
                     ids=[f"{t['_c']} {t['_l']} {t.get('id')}"], grupo="vencida3",
                     etiqueta=f"«{corto(t.get('title'), 40)}» ({due[8:10]}/{due[5:7]})")


def lista_de(a):
    """La lista de Google Tasks de la acción; si era una variable sin resolver ($V), la de por defecto."""
    lista = str(a.get("lista") or "@default")
    return "@default" if "$" in lista else lista


def revisar_tareas(turnos):
    for t in turnos:
        borrados = [a for a in t["acciones"] if a["tipo"] in ("TAREA_BORRAR", "CAL_BORRAR")]
        por_llamada = {}
        for a in borrados:
            por_llamada.setdefault(a["cid"], []).append(a)
        for cid, bs in por_llamada.items():
            sal = bs[0]["salida"]
            # cuántos: comandos analizados, líneas «id\t…» de gog, líneas «ok …» o «14 ok» (un bucle con >/dev/null && echo ok)
            n = max([len(bs), len(re.findall(r"(?m)^(?:\w+ \S+: )?id\t", sal)), len(re.findall(r"(?m)^\s*ok\b", sal))]
                    + [int(m) for m in re.findall(r"(?m)^\s*(\d+)\s+ok\s*$", sal)])
            bucle = any(b.get("bucle") for b in bs)
            if n >= 3 or (bucle and n < 2 and bs[0].get("ok")):
                cuantas = f"{n}" if n >= 3 else "varias"
                hallazgo("REVISAR", "Tareas", f"masivo|{cid}",
                         f"{local(bs[0]['ts']):%d/%m %H:%M} · borró {cuantas} {'tareas' if bs[0]['tipo'] == 'TAREA_BORRAR' else 'eventos'} "
                         f"de una vez{' (en bucle)' if bucle else ''}. Confirma que no se llevó nada que querías conservar.")
        for a in t["acciones"]:
            if not a["tipo"].startswith("TAREA"):
                continue
            titulo = a["f"].get("--title") or ""
            if not a["ok"]:
                if corregido_luego(a, turnos):
                    continue
                hallazgo("REVISAR", "Tareas", f"fallo|{a['cid']}|{a.get('id')}",
                         f"{local(a['ts']):%d/%m %H:%M} · tarea «{corto(titulo or a.get('id'), 50)}» ({a.get('verbo')}) dio error o no devolvió prueba.")
                continue
            if a["tipo"] != "TAREA_CREAR":
                continue
            if "$" in str(a.get("lista") or ""):
                continue   # lista en una variable sin resolver: no se sabe dónde mirar (y gog daría un falso AVISO)
            ts = tareas(a["cuenta"], a.get("lista") or "@default")
            if not ts and AVISOS:
                continue
            tid = a.get("id_salida")
            mia = next((x for x in ts if x.get("id") == tid), None) or next(
                (x for x in ts if parecidos(x.get("title"), titulo) and not x.get("deleted")), None)
            etiqueta = f"«{corto(titulo, 50)}» ({a['cuenta']})"
            if mia is None or mia.get("deleted"):
                borrada_por_zazu = any(b["tipo"] == "TAREA_BORRAR" and (b.get("id") in (tid, None)) for tt in turnos for b in tt["acciones"])
                if not borrada_por_zazu:
                    hallazgo("ERROR", "Tareas", f"falta|{tid or norm(titulo)}", f"Tarea {etiqueta}: la creó y ya no está.",
                             f"zgog{flag(a['cuenta'])} tasks add {q(lista_de(a))} --title={q(corto(titulo, 150) or '…')} "
                             "--due=AAAA-MM-DD (con el OK de Fran)")
                continue
            if mia.get("status") == "needsAction":
                otras = [x for x in ts if x is not mia and x.get("status") == "needsAction" and not x.get("deleted")
                         and parecidos(x.get("title"), mia.get("title"))]
                if otras:
                    par = "|".join(sorted([mia.get("id"), otras[0].get("id")]))
                    hallazgo("ERROR", "Tareas", f"duplicada|{par}", f"Tarea {etiqueta} está repetida ({len(otras) + 1} iguales pendientes).",
                             f"zgog{flag(a['cuenta'])} tasks delete {q(lista_de(a))} {q(otras[0].get('id'))} --force (con el OK de Fran)")
            if not mia.get("due") and FECHA_PEDIDA.search(t["peticion"] or ""):
                hallazgo("REVISAR", "Tareas", f"sinfecha|{mia.get('id')}", f"Tarea {etiqueta}: la petición tenía fecha y la tarea no tiene.",
                         f"zgog{flag(a['cuenta'])} tasks update {q(lista_de(a))} {q(mia.get('id'))} --due=AAAA-MM-DD")
            due = str(mia.get("due") or "")[:10]
            if due and due < str(local(a["ts"]).date()) and mia.get("status") == "needsAction":
                hallazgo("REVISAR", "Tareas", f"vencida|{mia.get('id')}", f"Tarea {etiqueta}: se creó ya vencida (fecha {due}).")


def revisar_recordatorios(turnos, desde):
    pedidos = {}
    for t in turnos:
        for a in t["acciones"]:
            if a["tipo"] in ("REC_CREATE", "REC_ADD") and a.get("job"):
                pedidos[a["job"]] = a
    for home in [H] + sorted(p for p in (H / "profiles").glob("*") if (p / "cron/jobs.json").exists()):
        try:
            jobs = json.loads((home / "cron/jobs.json").read_text()).get("jobs", [])
        except Exception:
            continue
        ejec = {}
        try:
            con = sqlite3.connect(f"file:{home / 'cron/executions.db'}?mode=ro", uri=True)
            for jid, out, fin in con.execute("SELECT job_id, delivery_outcome, finished_at FROM executions WHERE claimed_at >= ?",
                                             ((desde - timedelta(days=1)).isoformat(),)):
                ejec.setdefault(jid, []).append((out, fin))
            abiertas = con.execute("SELECT job_id, error, last_seen_at FROM cron_incidents WHERE state NOT IN ('resolved','closed','acked')").fetchall()
            con.close()
        except Exception:
            abiertas = []
        perfil = "" if home == H else f" [{home.name}]"
        con_fallo = set()   # rutinas que ya salen como «falló en su última pasada»: su incidente abierto sería la misma línea
        for j in jobs:
            nombre = corto(j.get("name"), 50) + perfil
            sch = j.get("schedule") or {}
            if sch.get("kind") == "once":
                try:
                    run = datetime.fromisoformat(sch.get("run_at")).astimezone(TZ)
                except Exception:
                    continue
                if run < desde - timedelta(days=1) or run > AHORA + timedelta(days=60):
                    continue
                if run.hour < 7:
                    hallazgo("REVISAR", "Recordatorios", f"madrugada|{j['id']}", f"Recordatorio «{nombre}» programado a las {run:%H:%M} del {run:%d/%m}. ¿Hora bien?")
                if run < AHORA - timedelta(minutes=15):
                    if not j.get("last_run_at"):
                        hallazgo("ERROR", "Recordatorios", f"nosalto|{j['id']}", f"Recordatorio «{nombre}» ({run:%d/%m %H:%M}) no saltó.",
                                 f"hermes cron run {q(j['id'])} (lo lanza en el siguiente tic; con el OK de Fran)")
                    else:
                        tarde = (j.get("last_dispatch") or {}).get("lateness_seconds") or 0
                        if tarde > 600:
                            hallazgo("REVISAR", "Recordatorios", f"tarde|{j['id']}", f"Recordatorio «{nombre}» saltó {int(tarde // 60)} min tarde.")
                        if j.get("last_delivery_error") or any(o == "failed" for o, _ in ejec.get(j["id"], [])):
                            hallazgo("ERROR", "Recordatorios", f"noentregado|{j['id']}",
                                     f"Recordatorio «{nombre}» saltó pero no llegó: {corto(j.get('last_delivery_error') or 'entrega fallida', 80)}.")
            elif j.get("enabled") and (j.get("last_status") not in (None, "ok") or (j.get("failure_streak") or 0) > 0 or j.get("last_delivery_error")):
                last = str(j.get("last_run_at") or "")[:16]
                if last and datetime.fromisoformat(j["last_run_at"]) >= desde:
                    con_fallo.add(j["id"])
                    hallazgo("REVISAR", "Rutinas", f"rutina|{j['id']}|{last}",
                             f"La rutina «{nombre}» falló en su última pasada ({last.replace('T', ' ')}): "
                             f"{corto(j.get('last_error') or j.get('last_delivery_error') or j.get('last_status'), 90)}.")
        ids = {j["id"] for j in jobs}
        for jid, a in pedidos.items():
            if jid not in ids and home == H and not ejec.get(jid):
                hallazgo("ERROR", "Recordatorios", f"nojob|{jid}", f"Dijo programar un recordatorio ({local(a['ts']):%d/%m %H:%M}) y no existe ni ha saltado.")
        nombres = {j["id"]: corto(j.get("name"), 50) for j in jobs}
        for jid, err, visto in abiertas:
            if jid in con_fallo:
                continue
            # una sola vez por incidente abierto (antes la huella llevaba la hora de la última vez que se vio: salía cada día)
            hallazgo("REVISAR", "Rutinas", f"incidente|{jid}",
                     f"Fallo abierto en la rutina «{nombres.get(jid, jid)}»{perfil}: {corto(err, 90)}")


def ordenar_mod():
    spec = importlib.util.spec_from_file_location("cerebro_ordenar", SCRIPTS / "cerebro-ordenar.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def revisar_cerebro(turnos):
    try:
        TABLA = ordenar_mod().TABLA
    except Exception as e:
        TABLA = {}
        AVISOS.append(f"no se pudo leer la tabla de carpetas de cerebro-ordenar.py: {e}")
    informe = CEREBRO / "00 Inicio/Informe del Cerebro.md"
    hora_informe = datetime.fromtimestamp(informe.stat().st_mtime, TZ) if informe.exists() else AHORA
    vistas = set()
    for t in turnos:
        for a in t["acciones"]:
            if a["tipo"] != "NOTA":
                continue
            p = Path(a["ruta"])
            if p in vistas or "$" in str(p) or "*" in str(p) or (a["herr"] == "terminal" and not p.suffix and not p.exists()
                                                                  and not re.search(r"\bmkdir\b", a["salida"] + str(p))):
                continue   # variables sin resolver o un trozo de texto que no es una ruta
            vistas.add(p)
            rel = str(p.relative_to(CEREBRO)) if str(p).startswith(str(CEREBRO)) else str(p)
            if not a["ok"]:
                hallazgo("REVISAR", "Cerebro", f"fallo|{rel}", f"Escribir «{corto(rel, 70)}» dio error. ¿Se guardó en otro intento?")
                continue
            if not p.exists():
                otra = next((q for q in CEREBRO.rglob(p.name) if ".trash" not in q.parts), None) if p.name else None
                if otra is None:
                    viejo = AHORA.timestamp() - a["ts"] > 86400
                    hallazgo("REVISAR" if viejo else "ERROR", "Cerebro", f"falta|{rel}",
                             f"Guardó «{corto(rel, 70)}» el {local(a['ts']):%d/%m} y ya no está en el Cerebro"
                             + (" (puede que se moviera o borrara después)." if viejo else "."))
                continue
            if rel.startswith(("50 Zazu/", "00 Inicio/")):
                hallazgo("REVISAR", "Cerebro", f"zona|{rel}", f"Escribió a mano en «{corto(rel, 70)}», que lo escriben los scripts. Se perderá en la próxima pasada.")
            if p.suffix != ".md" or not p.is_file():
                continue
            texto = p.read_text(errors="replace")
            marcas = sorted(set(re.findall(r"\[([^\[\]]{1,30} tachad[oa]s?)\]", tachar(texto))) - set(re.findall(r"\[([^\[\]]{1,30} tachad[oa]s?)\]", texto)))
            if marcas:
                hallazgo("ERROR", "Cerebro", f"secreto|{rel}",
                         f"«{corto(rel, 70)}» guarda datos que no pueden ir en el Cerebro ({', '.join(m.replace(' tachada', '').replace(' tachado', '') for m in marcas)}).",
                         "Decide Fran: quitar ese dato de la nota (y, si hace falta, guardarlo en el gestor de contraseñas, no en "
                         "Obsidian) o dejarlo como está («déjalo <código>»). No lo des por falso aviso sin mirarlo.")
            m = re.match(r"\A---\n(.*?)\n---", texto, re.S)
            tipo = (re.search(r"(?m)^tipo:\s*\"?([\w-]+)", m.group(1)).group(1) if m and re.search(r"(?m)^tipo:", m.group(1)) else None)
            carpeta = TABLA.get(tipo)
            if rel.startswith("30 Notas/") and tipo is None:
                hallazgo("REVISAR", "Cerebro", f"sintipo|{rel}", f"«{corto(rel, 70)}» no tiene tipo: el ordenador no sabrá dónde ponerla.")
            elif carpeta and not rel.startswith(("40 Compartido/", "90 Sistema/", "20 Diario/")) and not rel.startswith(carpeta + "/") \
                    and datetime.fromtimestamp(p.stat().st_mtime, TZ) < hora_informe:
                hallazgo("REVISAR", "Cerebro", f"carpeta|{rel}", f"«{corto(rel, 70)}» (tipo {tipo}) debería estar en «{carpeta}».")
    if informe.exists():
        txt = informe.read_text(errors="replace")
        fecha = re.search(r"(?m)^fecha:\s*(\S+)", txt)
        if fecha and fecha.group(1) < str(AHORA.date()) and AHORA.hour >= 7:
            # huella con la fecha del último informe (no la de hoy): si se queda parado, se avisa una vez, no cada noche
            hallazgo("REVISAR", "Cerebro", f"informe|{fecha.group(1)}", f"El ordenador del Cerebro no ha pasado hoy (último informe: {fecha.group(1)}).")
        m = re.search(r"\*\*Pendiente:\*\*([^\n]*)", txt)
        if m:
            cuenta = {k: int(n) for n, k in re.findall(r"(\d+) (sin tipo|enlaces rotos|sin mover|avisos)", m.group(1))}
            malos = {k: n for k, n in cuenta.items() if n}
            if malos:
                hallazgo("REVISAR", "Cerebro", f"pendiente|{sorted(malos.items())}",   # sin la fecha del Informe: cambia cada día
                         "Informe del Cerebro: " + ", ".join(f"{n} {k}" for k, n in malos.items()) + " (detalle en «00 Inicio/Informe del Cerebro»).")


RAIZ = r"(?:cread|guardad|apuntad|añadid|agendad|programad|enviad|mandad|borrad|eliminad|actualizad|cambiad|movid|marcad|puest|dejad|subid|copiad)"
PART = RAIZ + r"[oa]s?"
AFIRMA = re.compile(
    rf"\b(?:he|hemos|ya he|te he|lo he|la he|los he|las he|le he|te lo he|te la he)\s+{RAIZ}o\b"          # «he creado», «te lo he apuntado»
    r"|\b(?:creé|guardé|apunté|añadí|agendé|programé|envié|mandé|borré|eliminé|actualicé|cambié|moví|marqué|subí|copié)\b"
    rf"|^\W*(?:hecho|listo|lista|{PART})\b"                                                                     # «Hecho:», «Enviado a Nuria»
    rf"|\b(?:evento|cita|tarea|recordatorio|nota|borrador|mensaje|correo|carpeta|archivo)s?\s+{PART}\b", re.I)  # «tarea creada»
NIEGA = re.compile(r"\bno\s+(?:\w+\s+){0,2}(?:he|hemos|pude|puedo|está|consigo|se ha)\b|\bsin (?:permiso|prueba)\b|"
                   r"todavía no|aún no|cuando me digas|si quieres|\?|¿|\b(?:que|como|lo que) ya\b|\b(?:tienes|tenías|hay|había)\b|"
                   r"^\W*(?:está|están|sigue|siguen)\b", re.I)
OBJETO = {"Calendario": (re.compile(r"calendario|evento|agenda|\bcita\b", re.I), ("CAL_",)),
          "Tareas": (re.compile(r"\btareas?\b", re.I), ("TAREA_",)),
          "Recordatorios": (re.compile(r"recordatorio|alarma|\baviso\b", re.I), ("REC_", "TAREA_CREAR", "CAL_CREAR")),
          "Cerebro": (re.compile(r"\bnotas?\b|cerebro|obsidian|holazazu|carpeta|archivo", re.I), ("NOTA", "ESCRITO", "MEMORIA")),
          "Borradores": (re.compile(r"borrador", re.I), ("BORRADOR",)),
          "Envíos": (re.compile(r"\b(?:enviad[oa]|envié|mandad[oa]|mandé)\b", re.I), ("ENVIO",)),
          "Memoria": (re.compile(r"\bmemoria\b", re.I), ("MEMORIA",))}
RECONOCE = re.compile(r"no (he podido|pude|me has dado|se ha (hecho|podido))|deneg|sin (tu )?permiso|bloque|no lo has aprobado|no hubo respuesta|"
                      r"necesito (tu|que) (ok|apruebes|permiso)|pendiente de tu", re.I)


def revisar_afirmaciones(turnos):
    previo = {}
    for t in turnos:
        if t["fuente"] == "cron" or t["invitado"]:
            continue
        hechas = {a["tipo"] for a in t["acciones"] if a.get("ok")} | previo.get(t["sid"], set())
        previo[t["sid"]] = {a["tipo"] for a in t["acciones"] if a.get("ok")}
        for frase in re.split(r"(?<=[.!?\n])\s+", t["respuesta"] or ""):
            if not AFIRMA.search(frase) or NIEGA.search(frase):
                continue
            areas = [(area, pr) for area, (rx, pr) in OBJETO.items() if rx.search(frase)]
            if areas and not any(h.startswith(pr) for _, pr in areas for h in hechas):
                for area, _ in areas[:1]:
                    # si en esa conversación leyó las notificaciones del móvil, sin cita: no sale nada de lo que dijo
                    dijo = "dijo que lo había hecho" if t.get("movil") else f"dijo «{corto(frase, 90)}»"
                    hallazgo("ERROR", "Sin prueba (L1)", f"l1|{t['sid']}|{int(t['ts'])}|{area}",
                             f"{local(t['ts']):%d/%m %H:%M} ({CANAL.get(t['fuente'], t['fuente'])}) · {dijo} y en esa conversación no hay "
                             f"ninguna acción de {area.lower()} que saliera bien.",
                             "Comprobar si existe; si no, hacerlo o decírselo a Fran.")
                    break
        for clase, herr, ts in t["bloqueos"]:
            if clase in ("denegada", "sin respuesta") and not RECONOCE.search(t["respuesta"] or ""):
                hallazgo("REVISAR", "Aprobaciones", f"medias|{t['sid']}|{int(ts)}",
                         f"{local(ts):%d/%m %H:%M} ({CANAL.get(t['fuente'], t['fuente'])}) · aprobación {clase} ({herr}) y la respuesta "
                         "final no dice que quedó a medias: puede que Fran crea que está hecho.")


def revisar_errores(turnos):
    firmas = {}
    for t in turnos:
        for herr, txt, clase in t["errores"]:
            # bloqueos del escáner de seguridad o de una regla: no son fallos de Zazu (la lección L3 ya los cubre)
            if clase in ("seguridad", "regla") or LEE_NOTIFICACIONES.search(str(txt)):
                continue   # (y nunca se cita una salida con notificaciones del móvil)
            linea = next((l for l in str(txt).splitlines() if ERROR_TXT.search(l)), "")
            if not linea:
                continue
            firma = re.sub(r"[0-9a-f]{8,}|\d+|/[^\s:]+", "#", linea)[:70]
            firmas.setdefault((herr, firma), []).append(t["ts"])
    for (herr, firma), veces in firmas.items():
        if len(veces) >= 3:
            hallazgo("REVISAR", "Errores repetidos", f"err|{herr}|{firma}",
                     f"{herr}: el mismo error {len(veces)} veces («{corto(firma, 70)}»). Merece una lección en MEMORY.md o un cambio en la skill.")


# ───────────────────────── 4. salida ─────────────────────────
def resumen(turnos):
    n = {}
    for t in turnos:
        for a in t["acciones"]:
            if a["ts"] >= DESDE.timestamp():
                k = a["tipo"].split("_")[0]
                n[k] = n.get(k, 0) + 1
    b = {}
    for t in turnos:
        for clase, _, ts in t["bloqueos"]:
            if ts >= DESDE.timestamp():
                b[clase] = b.get(clase, 0) + 1
    nombres = {"ESCRITO": "archivos fuera del Cerebro", "CAL": "calendario", "TAREA": "tareas", "NOTA": "Cerebro", "REC": "recordatorios", "ENVIO": "envíos",
               "BORRADOR": "borradores", "MEMORIA": "memoria", "CORREO": "correo", "CONTACTO": "contactos"}
    acc = ", ".join(f"{nombres.get(k, k)} {v}" for k, v in sorted(n.items())) or "ninguna"
    apr = ", ".join(f"{v} {k}" for k, v in sorted(b.items())) or "ninguna"
    return acc, apr


def juntar(hs, grupos):
    """Los del mismo grupo (2 o más) salen en una sola línea con un código común; `grupos` guarda qué códigos lleva dentro."""
    out, por = [], {}
    for h in hs:
        (por.setdefault(h["grupo"], []) if h["grupo"] else out).append(h)
    for g, ms in por.items():
        if len(ms) == 1:
            out.append(ms[0])
            continue
        dentro = sorted(m["huella"] for m in ms)
        codigo = hashlib.sha1(("grupo|" + "|".join(dentro)).encode()).hexdigest()[:10]
        grupos[codigo] = dentro
        titulo, arreglo = GRUPOS[g]
        etiquetas = [m["etiqueta"] for m in ms]
        texto = f"{titulo.format(n=len(ms))}: {', '.join(etiquetas[:8])}" + (f" y {len(ms) - 8} más" if len(ms) > 8 else "") + "."
        out.append({**ms[0], "huella": codigo, "texto": texto, "arreglo": arreglo, "ids": [], "grupo": None})
    return out


ORDEN_AREAS = ["Calendario", "Recordatorios", "Sin prueba (L1)", "Aprobaciones", "Tareas", "Agenda", "Rutinas", "Cerebro",
               "Errores repetidos"]   # qué entra primero en los 5 de la rutina (dentro de cada gravedad)
TOPE_RUTINA = 5   # lo que cabe en el WhatsApp de la rutina; el resto sale la noche siguiente (no se marca como avisado)


def prioridad(h):
    return (0 if h["grav"] == "ERROR" else 1, ORDEN_AREAS.index(h["area"]) if h["area"] in ORDEN_AREAS else 99)


def codigo_valido(texto):
    """Un código son exactamente 10 caracteres hexadecimales (se aceptan corchetes y espacios alrededor)."""
    c = str(texto or "").strip().strip("[]").strip().lower()
    return c if re.fullmatch(r"[0-9a-f]{10}", c) else None


def clave_aviso(a):
    return hashlib.sha1(re.sub(r"\d+", "#", a).encode()).hexdigest()[:10]


def main():
    global DESDE, AHORA, SIN_ESTADO
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=float, default=26 / 24)
    ap.add_argument("--rutina", action="store_true")
    ap.add_argument("--codigo", help="solo el punto con este código (10 caracteres), con sus IDs (para «arregla <código>»); "
                                     "mira al menos 14 días atrás")
    ap.add_argument("--ignorar", metavar="CODIGO", help="Fran dijo «déjalo»: no vuelve a salir nunca")
    ap.add_argument("--simular-hoy", metavar="AAAA-MM-DD[THH:MM]", help="pruebas: hace como si fuera ese momento")
    args = ap.parse_args()
    if args.simular_hoy:
        v = args.simular_hoy
        AHORA = (datetime.fromisoformat(v).replace(tzinfo=TZ) if "T" in v
                 else datetime.combine(date.fromisoformat(v), AHORA.timetz()))
        SIN_ESTADO = not os.environ.get("REVISAR_ZAZU_ESTADO")
    leer = lambda n: set((ESTADO / n).read_text().split()) if (ESTADO / n).exists() else set()

    def leer_json(n):
        try:
            return json.loads((ESTADO / n).read_text()) if (ESTADO / n).exists() else {}
        except Exception:
            return {}
    grupos = leer_json("grupos.json")
    for opcion, valor in (("--ignorar", args.ignorar), ("--codigo", args.codigo)):
        if valor is not None and not codigo_valido(valor):
            print(f"Código no válido para {opcion}: «{corto(valor, 20)}». Son exactamente 10 caracteres del 0 al 9 y de la a a la f, "
                  "como 77ed067dc9 (cópialo tal cual del informe).")
            return 1
    if args.ignorar:
        c = codigo_valido(args.ignorar)
        dentro = grupos.get(c, [])
        if not SIN_ESTADO:
            ESTADO.mkdir(parents=True, exist_ok=True)
            with (ESTADO / "ignorados.txt").open("a") as f:
                f.write("\n".join([c] + dentro) + "\n")
        print(f"Hecho: [{c}]" + (f" ({len(dentro)} puntos)" if dentro else "") + " no volverá a salir en la revisión.")
        return 0
    if args.codigo:
        # Fran puede contestar días después, y lo que sale de state.db depende de la ventana: con la de 26 h, un punto
        # sacado con --dias 7 (o de la rutina de hace dos días) parecería «arreglado» sin estarlo
        args.dias = max(args.dias, 14)
    DESDE = AHORA - timedelta(days=args.dias)
    marca = ESTADO / "ultima.txt"
    if args.rutina and marca.exists():
        try:
            DESDE = min(DESDE, datetime.fromisoformat(marca.read_text().strip()) - timedelta(hours=2))
        except ValueError:
            pass
    turnos = leer_acciones(DESDE)
    for f in (revisar_calendario, revisar_tareas, revisar_afirmaciones, revisar_errores, revisar_cerebro, revisar_agenda):
        try:
            f(turnos)
        except Exception as e:
            AVISOS.append(f"la revisión «{f.__name__}» falló: {type(e).__name__}: {e}")
    try:
        revisar_recordatorios(turnos, DESDE)
    except Exception as e:
        AVISOS.append(f"la revisión de recordatorios falló: {type(e).__name__}: {e}")

    ignor = leer("ignorados.txt")
    avisados = leer("avisados.txt") if args.rutina else set()
    unicos, vistos = [], set()
    for h in HALLAZGOS:
        if h["huella"] not in vistos and h["grav"] != "INFO":
            vistos.add(h["huella"])
            unicos.append(h)
    nuevos = [h for h in unicos if h["huella"] not in avisados | ignor]
    grupos_hoy, sobran = {}, 0
    if args.codigo:
        c = codigo_valido(args.codigo)
        if c not in grupos:   # sin grupos.json (otro estado): los grupos que salen ahora
            for base in (unicos, [h for h in unicos if h["huella"] not in ignor]):
                juntar(base, grupos)
        dentro = set(grupos.get(c, [])) or {c}
        lista = [h for h in unicos if h["huella"] in dentro]
    else:
        lista = sorted(juntar(nuevos, grupos_hoy), key=prioridad)
        if args.rutina and len(lista) > TOPE_RUTINA:
            lista, sobran = lista[:TOPE_RUTINA], len(lista) - TOPE_RUTINA

    acc, apr = resumen(turnos)
    print(f"# DATOS · Revisión de Zazu ({DESDE:%d/%m %H:%M} → {AHORA:%d/%m %H:%M})")
    print(f"Lo que hizo Zazu: {acc} · Aprobaciones: {apr}")
    print(f"\n## AGENDA (cómo está ahora, la haya puesto quien sea)")
    if AGENDA.get("hasta"):
        cuentas = ", ".join(f"{k} {AGENDA[k] if AGENDA.get(k) is not None else 'sin leer'}" for k in ("varas", "alvarez"))
        print(f"- De hoy al {AGENDA['hasta']:%d/%m}: {sum(v for k in ('varas', 'alvarez') if (v := AGENDA.get(k)))} eventos de tus "
              f"calendarios ({cuentas}) y {AGENDA['tareas']} tareas ({AGENDA['pendientes']} pendientes). Lo que falla sale abajo como «Agenda ·».")
    else:
        print("- No se pudo revisar (mira AVISOS).")
    for grav, titulo in (("ERROR", "HAY QUE ARREGLARLO"), ("REVISAR", "PUEDE ESTAR BIEN: QUE LO MIRE FRAN")):
        hs = [h for h in lista if h["grav"] == grav]
        print(f"\n## {titulo}")
        if not hs:
            print("- (nada)")
        for h in sorted(hs, key=prioridad):
            print(f"- [{h['huella']}] {h['area']} · {h['texto']}" + (f"\n  Arreglo propuesto: {h['arreglo']}" if h["arreglo"] else "")
                  + (f"\n  IDs (cuenta, calendario o lista, id; en el orden del texto): {' · '.join(h['ids'])}" if args.codigo and h["ids"] else ""))
    if sobran:
        print(f"\n## NO CABEN HOY\n- Hay {sobran} más (salen en la próxima revisión o con «revisa lo que has hecho»).")
    if args.codigo and not lista:
        print(f"\n(El punto [{codigo_valido(args.codigo)}] no sale en los últimos {args.dias:g} días: puede que esté arreglado. "
              "Compruébalo en solo lectura antes de decírselo a Fran.)")
    avisos = list(dict.fromkeys(AVISOS))
    if avisos:
        print("\n## AVISOS DE LA REVISIÓN (no son errores de Zazu)")
        for a in avisos:
            print(f"- {corto(a, 160)}")
    # AVISOS que no se han contado en el último día (23 h: la rutina no sale cada día a la misma hora exacta)
    avisos_previos = leer_json("avisos.json") if args.rutina else {}

    def contado_hace_poco(a):
        try:
            return AHORA - datetime.fromisoformat(avisos_previos[clave_aviso(a)]) < timedelta(hours=23)
        except (KeyError, ValueError, TypeError):
            return False
    despertar = bool(lista) or any(not contado_hace_poco(a) for a in avisos)
    if not SIN_ESTADO and not args.codigo:
        if grupos_hoy or args.rutina:
            ESTADO.mkdir(parents=True, exist_ok=True)
        if grupos_hoy:
            todos = {**grupos, **grupos_hoy}
            (ESTADO / "grupos.json").write_text(json.dumps(dict(list(todos.items())[-300:])))
        if args.rutina:
            # solo lo que de verdad va en el WhatsApp de hoy (los de un grupo, todos sus puntos); lo que no cupo sale mañana
            contados = [h["huella"] for h in lista] + [m for h in lista for m in grupos_hoy.get(h["huella"], [])]
            todos = list(dict.fromkeys(((ESTADO / "avisados.txt").read_text().split() if (ESTADO / "avisados.txt").exists() else [])
                                       + contados))[-2000:]
            (ESTADO / "avisados.txt").write_text("\n".join(todos) + "\n")
            if despertar and avisos:
                hoy = {clave_aviso(a): AHORA.isoformat() for a in avisos}
                (ESTADO / "avisos.json").write_text(json.dumps(dict(list({**avisos_previos, **hoy}.items())[-200:])))
            marca.write_text(AHORA.isoformat())
    if args.rutina and not despertar:
        print('{"wakeAgent": false}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
