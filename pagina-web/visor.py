"""Visor de registros de HolaZazu: junta en un sitio lo que escriben la app (Hub), Zazu (Hermes) y los asistentes de los
invitados, para VISOR.md, el comando `visor` y la pestaña Administrador. Solo biblioteca estándar.

Cada entrada es una línea JSON en ~/.local/state/zazu-web/visor/AAAA-MM-DD.jsonl (se guardan 30 días):
  t  hora (epoch)                       o  origen: app · zazu · invitados · vigilante
  g  gravedad: info · aviso · error     p  perfil de Hermes (zazu, tecnico, zi…) o null
  x  el mensaje en una línea            d  el detalle de varias líneas (un Traceback), si lo hay
  f  firma: los errores iguales comparten firma (así se agrupan)
Todo pasa por privacidad.tachar() y se quitan correos, nombres y el texto de los mensajes de chat: se ve QUÉ falló, no lo
que dijo nadie. recoger() lee solo lo nuevo desde la última vez (cursor del journal y posición en cada archivo); se puede
llamar a la vez desde el vigilante, el Hub y la terminal (va con cerrojo).
"""
import fcntl, hashlib, importlib.util, json, os, re, subprocess, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

HOME = Path.home()
DIR = HOME / ".local/state/zazu-web/visor"
CURSOR = DIR / "cursor.json"
DIAS = 30
HERMES = HOME / ".hermes"
INVITADOS = HOME / ".local/state/zazu-web/errores-invitadas.jsonl"
NIVEL = {"info": 0, "aviso": 1, "error": 2}
ORIGENES = {"app": "La app (Hub)", "zazu": "Zazu", "invitados": "Invitados", "vigilante": "Vigilante"}



def _cargar_tachar():
    """privacidad.tachar() cargado por su ruta. NUNCA se añade ~/.hermes/scripts a sys.path: allí hay un movil.py (y más) que taparía
    los módulos del Hub con el mismo nombre (pasó el 2026-10-24: la app de Android dio AttributeError en /api/movil/…)."""
    try:
        spec = importlib.util.spec_from_file_location("privacidad_hermes", HERMES / "scripts/privacidad.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.tachar
    except Exception:   # sin privacidad.py se tacha lo básico: teléfonos (y los @lid/@s.whatsapp.net) y claves; correos y mensajes, en limpio()
        return lambda t: _CLAVE_BASICA.sub("[clave tachada]", _TELEFONO_BASICO.sub("[teléfono tachado]", str(t or "")))


_TELEFONO_BASICO = re.compile(r"\+?\d[\d ]{7,}\d(@[\w.]+)?")
_CLAVE_BASICA = re.compile(r"sk-[A-Za-z0-9_-]{8,}|\b[A-Za-z0-9_-]{40,}\b")
tachar = _cargar_tachar()


_CORREO = re.compile(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}")
_MENSAJE = re.compile(r"\b(msg|text|texto|message|prompt|reply_to_text|response_text|content)=(['\"]).*?(?:\2|$)")
_USUARIO = re.compile(r"\buser=.*?(?= chat=|$)")


def limpio(t, n=500):
    t = _USUARIO.sub("user=[persona]", _MENSAJE.sub(r"\1=[mensaje]", str(t or "")))
    return tachar(_CORREO.sub("<correo>", t))[:n]


def firma(o, x, d=""):
    """Los errores iguales (cambiando números, ids y valores entre comillas) tienen la misma firma."""
    lineas = [l.strip() for l in (d or "").splitlines() if l.strip()]
    base = lineas[-1] if lineas else x
    sitio = next((l for l in reversed(lineas) if l.startswith('File "')), "")
    m = re.match(r'File "([^"]+)", line \d+, in (\S+)', sitio)
    if m:   # el archivo y la función donde saltó, sin el número de línea
        base += f" @{Path(m[1]).name}:{m[2]}"
    base = re.sub(r"'[^']*'|\"[^\"]*\"", "'…'", base.lower())
    base = re.sub(r"0x[0-9a-f]+|[0-9a-f]{8,}|\d+", "#", base)
    return hashlib.sha1(f"{o}|{base[:200]}".encode()).hexdigest()[:10]


def entrada(t, o, g, x, p=None, d=""):
    x, d = limpio(x), (limpio(d, 6000) if d else "")
    e = {"t": int(t * 1000) / 1000, "o": o, "g": g, "p": p, "x": x, "f": firma(o, x, d)}
    if d:
        e["d"] = d
    return e


# ---------------------------------------------------------------- la app (journal de hermes-hub)
_PETICION = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD) (\S+) → (\d{3})")
_RUIDO_APP = re.compile(r"^(\[|Cannot determine format|-{10,}|Exception occurred during processing|Input #|Output #|Stream |"
                        r"frame=|size=|video:|Press \[q\]|\s*$)")   # sobre todo la salida de ffmpeg al hacer miniaturas
_FIN_TB = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt|Warning|Timeout\w*)(: |$)")   # «TypeError: …»


def _gravedad_app(msg, prioridad, ident):
    if prioridad <= 3 or msg.startswith("error "):
        return "error"
    m = _PETICION.match(msg)
    if m:
        return "error" if m[3] >= "500" else "aviso" if m[3] >= "400" else "info"
    if ident == "systemd" and re.search(r"[Ff]ailed|exited, code=|Killed", msg):
        return "error"
    return "aviso" if prioridad == 4 else "info"


def _app(cursor):
    cmd = ["journalctl", "--user", "-u", "hermes-hub", "-o", "json", "--no-pager"]
    cmd += ["--after-cursor", cursor] if cursor else ["--since", f"{DIAS} days ago"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return [], cursor
    out, tb = [], None
    for linea in r.stdout.splitlines():
        try:
            j = json.loads(linea)
        except ValueError:
            continue
        cursor = j.get("__CURSOR") or cursor
        msg = j.get("MESSAGE")
        if not isinstance(msg, str):   # journald guarda como lista de bytes lo que no es UTF-8
            continue
        t = int(j.get("__REALTIME_TIMESTAMP", 0)) / 1e6
        if tb is not None and (t - tb["t"] > 5 or len(tb["d"]) > 300):   # uno que nunca terminó (la app se paró a medias)
            out.append(entrada(tb["t"], "app", "error", tb["d"][-1], d="\n".join(tb["d"])))
            tb = None
        if tb is not None:   # dentro de un Traceback: se junta hasta la línea final («XxxError: …»)
            if msg[:1].isspace() or msg.startswith(("Traceback", "During handling", "The above exception")):
                tb["d"].append(msg)
                continue
            if _FIN_TB.match(msg):
                out.append(entrada(tb["t"], "app", "error", msg, d="\n".join(tb["d"] + [msg])))
                tb = None
                continue
            # otra línea metida en medio (otra petición a la vez): va aparte y el Traceback sigue abierto
        if msg.startswith("Traceback") and tb is None:
            tb = {"t": t, "d": [msg]}
            continue
        if _RUIDO_APP.match(msg) or msg[:1].isspace():
            continue
        out.append(entrada(t, "app", _gravedad_app(msg, int(j.get("PRIORITY", 6)), j.get("SYSLOG_IDENTIFIER", "")), msg))
    if tb:
        out.append(entrada(tb["t"], "app", "error", tb["d"][-1], d="\n".join(tb["d"])))
    return out, cursor


# ---------------------------------------------------------------- Zazu y los invitados (archivos de Hermes)
_LINEA_HERMES = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (DEBUG|INFO|WARNING|ERROR|CRITICAL) (\S+?):? (.*)$")
_RUIDO_HERMES = {"hermes_cli.plugins", "hermes_cli.mem_trim", "hermes_cli.plugin_capabilities", "hermes_plugins.dashboard_auth__basic",
                 "hermes_cli.dashboard_auth.registry", "agent.shell_hooks", "aiohttp.access"}   # miles de líneas al día sin nada que ver
_GRAV_HERMES = {"DEBUG": None, "INFO": "info", "WARNING": "aviso", "ERROR": "error", "CRITICAL": "error"}


def _hermes_lineas(texto, o, p):
    out, ultima = [], None
    for l in texto.splitlines():
        m = _LINEA_HERMES.match(l)
        if not m:   # continuación (un Traceback debajo de un ERROR)
            if ultima is not None and l.strip():
                ultima.setdefault("d", []).append(l)
            continue
        g = _GRAV_HERMES[m[2]]
        if g is None or (g == "info" and m[3] in _RUIDO_HERMES):
            ultima = None
            continue
        x = m[4] if m[3].startswith("[") else f"{m[3]}: {m[4]}"   # «[run_4202…]:» es solo el id de la conversación
        ultima = {"t": time.mktime(time.strptime(m[1], "%Y-%m-%d %H:%M:%S")), "g": g, "x": x}
        out.append(ultima)
    return [entrada(e["t"], o, e["g"], e["x"], p, "\n".join(e.get("d", []))) for e in out]


def _leer_nuevo(ruta, pos, rotados=()):
    """Lo nuevo de un archivo desde pos = [inodo, byte]. La primera vez (pos None) también lee sus copias viejas (.3 → .1);
    si rotó (otro inodo), primero lo que faltaba del viejo, que ahora es una de sus copias."""
    try:
        st = ruta.stat()
    except OSError:
        return "", pos
    texto = ""
    if pos is None:
        for r in reversed(rotados):
            try:
                texto += r.read_text("utf-8", "replace")
            except OSError:
                pass
        pos = [st.st_ino, 0]
    elif pos[0] != st.st_ino:
        for r in rotados:
            try:
                if r.stat().st_ino == pos[0]:
                    with open(r, "rb") as f:
                        f.seek(pos[1])
                        texto = f.read().decode("utf-8", "replace")
                    break
            except OSError:
                continue
        pos = [st.st_ino, 0]
    if st.st_size < pos[1]:   # lo vaciaron
        pos[1] = 0
    with open(ruta, "rb") as f:
        f.seek(pos[1])
        nuevo = f.read()
    corte = nuevo.rfind(b"\n") + 1   # una línea a medio escribir se lee la próxima vez
    return texto + nuevo[:corte].decode("utf-8", "replace"), [st.st_ino, pos[1] + corte]


def _archivos_hermes():
    """(ruta, origen, perfil) de cada agent.log: el de Zazu y el de cada perfil (zi… = invitados)."""
    yield HERMES / "logs/agent.log", "zazu", "zazu"
    for f in sorted((HERMES / "profiles").glob("*/logs/agent.log")):
        perfil = f.parent.parent.name
        yield f, "invitados" if perfil.startswith("zi") else "zazu", perfil


def _invitados(texto):
    out = []
    for l in texto.splitlines():
        try:
            d = json.loads(l)
            codigo = d.get("codigo")
            g = "aviso" if isinstance(codigo, int) and 400 <= codigo < 500 else "error"
            x = f"{d.get('origen')}{f' → {codigo}' if codigo else ''}: {d.get('detalle')}"
            out.append(entrada(float(d["t"]), "invitados", g, x, d.get("perfil")))
        except (ValueError, KeyError, TypeError):
            continue
    return out


# ---------------------------------------------------------------- guardar y recoger
def _dia(t):
    return DIR / f"{datetime.fromtimestamp(t):%Y-%m-%d}.jsonl"


def guardar(entradas):
    if not entradas:
        return
    DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    por_dia = {}
    for e in entradas:
        por_dia.setdefault(_dia(e["t"]), []).append(json.dumps(e, ensure_ascii=False))
    for f, lineas in por_dia.items():
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, ("\n".join(lineas) + "\n").encode())
        finally:
            os.close(fd)


def anotar(o, g, x, p=None, d=""):
    """Una entrada suelta (la usa el vigilante para sus avisos)."""
    guardar([entrada(time.time(), o, g, x, p, d)])


def recoger():
    """Lee lo nuevo de todas las fuentes y lo guarda. Devuelve cuántas entradas nuevas hubo."""
    DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(DIR / ".cerrojo", "w") as cerrojo:
        fcntl.flock(cerrojo, fcntl.LOCK_EX)
        try:
            cur = json.loads(CURSOR.read_text())
        except (OSError, ValueError):
            cur = {}
        archivos = cur.setdefault("archivos", {})
        nuevas, cur["app"] = _app(cur.get("app"))
        fuentes = [(r, o, p, [r.with_name(f"agent.log.{i}") for i in (1, 2, 3)]) for r, o, p in _archivos_hermes()]
        fuentes.append((INVITADOS, "invitados", None, [INVITADOS.with_name(INVITADOS.name + ".1")]))
        for ruta, o, p, rotados in fuentes:
            texto, archivos[str(ruta)] = _leer_nuevo(ruta, archivos.get(str(ruta)), rotados)
            nuevas += _invitados(texto) if ruta == INVITADOS else _hermes_lineas(texto, o, p)
        limite = time.time() - DIAS * 86400
        nuevas = [e for e in nuevas if e["t"] >= limite]
        guardar(nuevas)
        tmp = CURSOR.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur))
        os.chmod(tmp, 0o600)
        os.replace(tmp, CURSOR)
        for f in DIR.glob("*.jsonl"):   # lo de hace más de 30 días se borra
            if f < _dia(limite):
                f.unlink(missing_ok=True)
    return len(nuevas)


# ---------------------------------------------------------------- consultas (VISOR.md, terminal y la app)
def _dias(desde, hasta):
    d, fin = date.fromtimestamp(hasta), date.fromtimestamp(max(desde, 0))
    while d >= fin:
        yield DIR / f"{d:%Y-%m-%d}.jsonl"
        d -= timedelta(days=1)


def leer(desde=None, hasta=None, origen=None, gravedad=None, perfil=None, q=None, firma_=None, n=500):
    """Entradas que cumplen los filtros, la más nueva primero. gravedad = la mínima (aviso → avisos y errores)."""
    hasta = hasta or time.time()
    desde = desde if desde is not None else hasta - 86400
    minimo, q = NIVEL.get(gravedad or "info", 0), (q or "").lower().strip()
    out = []
    for f in _dias(desde, hasta):
        try:
            lineas = f.read_text("utf-8").splitlines()
        except OSError:
            continue
        dia = []
        for l in lineas:
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if (desde <= e["t"] <= hasta and NIVEL.get(e["g"], 0) >= minimo and (not origen or e["o"] == origen)
                    and (not perfil or e.get("p") == perfil) and (not firma_ or e["f"] == firma_)
                    and (not q or q in e["x"].lower() or q in e.get("d", "").lower())):
                dia.append(e)
        out += sorted(dia, key=lambda e: e["t"], reverse=True)
        if len(out) >= n:
            break
    return out[:n]


def histograma(desde, hasta=None, cubo=3600, **filtros):
    """[{t: inicio del cubo, info, aviso, error}] de desde a hasta."""
    hasta = hasta or time.time()
    inicio = desde - desde % cubo
    cubos = [{"t": inicio + i * cubo, "info": 0, "aviso": 0, "error": 0} for i in range(int((hasta - inicio) // cubo) + 1)]
    for e in leer(desde, hasta, n=10**7, **filtros):
        cubos[int((e["t"] - inicio) // cubo)][e["g"]] += 1
    return cubos


def grupos(desde, hasta=None, gravedad="aviso", **filtros):
    """Los avisos y errores iguales juntos (como Error Reporting): primero los errores, y dentro el que más se repite."""
    return agrupar(leer(desde, hasta, gravedad=gravedad, n=10**7, **filtros))


def agrupar(entradas):
    """Junta por firma unas entradas ordenadas de la más nueva a la más vieja."""
    gs = {}
    for e in entradas:
        g = gs.get(e["f"])
        if not g:
            g = gs[e["f"]] = {"f": e["f"], "n": 0, "primera": e["t"], "ultima": e["t"], "o": e["o"], "g": e["g"], "x": e["x"], "perfiles": set()}
        g["n"] += 1
        g["primera"] = e["t"]
        if e.get("p"):
            g["perfiles"].add(e["p"])
    out = sorted(gs.values(), key=lambda g: (NIVEL[g["g"]], g["n"]), reverse=True)
    for g in out:
        g["perfiles"] = sorted(g["perfiles"])
    return out


def vista(desde, hasta=None, cubos=60, n=500, **filtros):
    """Lo que pinta la pestaña Administrador, de una sola lectura: las n más nuevas, el total, el gráfico (cubos barras) y los agrupados."""
    hasta = hasta or time.time()
    todas = leer(desde, hasta, n=10**7, **filtros)
    cubo = max(60.0, (hasta - desde) / cubos)
    hist = [{"t": desde + i * cubo, "info": 0, "aviso": 0, "error": 0} for i in range(max(1, -int(-(hasta - desde) // cubo)))]
    for e in todas:
        hist[min(len(hist) - 1, int((e["t"] - desde) // cubo))][e["g"]] += 1
    return {"entradas": todas[:n], "total": len(todas), "histograma": hist, "cubo": cubo,
            "cuentas": {g: sum(1 for e in todas if e["g"] == g) for g in NIVEL},
            "grupos": agrupar([e for e in todas if e["g"] != "info"])[:100]}


# ---------------------------------------------------------------- VISOR.md
_BARRAS = "·▁▂▃▄▅▆▇█"
ICONO = {"info": "⚪", "aviso": "🟡", "error": "🔴"}


def _celda(t, n=140):
    return str(t).replace("|", "\\|").replace("\n", " ")[:n]


def hora(t, con_dia=False):
    return time.strftime("%d/%m %H:%M" if con_dia else "%H:%M", time.localtime(t))


def resumen_md(activas=None):
    """El texto de VISOR.md: estado, cuentas de 24 h, gráfico por horas, errores agrupados y los últimos avisos."""
    ahora = time.time()
    desde = ahora - 86400
    todas = leer(desde, ahora, n=10**7)
    md = ["# Visor de registros", "",
          f"> Se reescribe solo cada 5 minutos (lo hace el vigilante). Última vez: **{hora(ahora, True)}**.  ",
          "> En vivo: escribe `visor` en la terminal. Aquí salen las **últimas 24 horas**; el visor guarda 30 días.", "",
          "## Ahora mismo", ""]
    if activas:
        md += [f"- {ICONO.get(a.get('gravedad'), '🟡')} {a.get('texto')} _(desde las {hora(a.get('desde', ahora))})_" for a in activas.values()]
    else:
        md.append("✅ Todo funciona: la web, Zazu, el túnel y los servicios responden.")

    md += ["", "## Últimas 24 horas", "", "| | Info | Avisos | Errores |", "|---|---:|---:|---:|"]
    for o, nombre in ORIGENES.items():
        c = {g: sum(1 for e in todas if e["o"] == o and e["g"] == g) for g in NIVEL}
        md.append(f"| {nombre} | {c['info']} | {c['aviso']} | {c['error']} |")

    cubos = histograma(ahora - 23 * 3600, ahora)
    for g, titulo in (("error", "Errores"), ("aviso", "Avisos")):
        tope = max(c[g] for c in cubos)
        barras = "".join(_BARRAS[0 if not c[g] else max(1, round(c[g] / tope * 8))] for c in cubos)
        md += ["", f"{titulo} por hora (cada carácter es una hora; la más alta tuvo {tope}):", "", "```", barras,
               f"{hora(cubos[0]['t'])[:2]}h{' ' * (len(cubos) - 6)}{hora(cubos[-1]['t'])[:2]}h", "```"]

    gs = grupos(desde, ahora)[:10]
    md += ["", "## Errores agrupados", ""]
    if gs:
        md += ["Los avisos y errores iguales salen juntos, como en el Error Reporting de Google.", "",
               "| Veces | | Dónde | Qué pasó | Primera | Última |", "|---:|---|---|---|---|---|"]
        for g in gs:
            donde = ORIGENES[g["o"]] + (f" ({', '.join(g['perfiles'])})" if g["perfiles"] else "")
            md.append(f"| {g['n']} | {ICONO[g['g']]} | {_celda(donde, 60)} | {_celda(g['x'])} | {hora(g['primera'])} | {hora(g['ultima'])} |")
    else:
        md.append("Ningún aviso ni error en las últimas 24 horas. 🎉")

    ultimos = []   # los seguidos iguales van en una línea («×13»)
    for e in (e for e in todas if e["g"] != "info"):
        if ultimos and ultimos[-1][0]["f"] == e["f"]:
            ultimos[-1][1] += 1
        elif len(ultimos) < 15:
            ultimos.append([e, 1])
        else:
            break
    if ultimos:
        md += ["", "## Últimos avisos y errores", ""]
        for e, veces in ultimos:
            quien = f" · {e['p']}" if e.get("p") and e["p"] != "zazu" else ""
            md.append(f"- `{hora(e['t'])}` {ICONO[e['g']]} **{ORIGENES[e['o']]}{quien}** · {_celda(e['x'], 200)}{f' **×{veces}**' if veces > 1 else ''}")

    md += ["", "## Cómo leer esto", "",
           "- **Info** ⚪: algo normal que ha pasado (alguien abrió la web, Zazu respondió un mensaje). No hay que hacer nada.",
           "- **Aviso** 🟡: algo raro que no rompe nada, o un fallo pequeño (una página que no existe, un dato mal escrito).",
           "- **Error** 🔴: algo que ha fallado de verdad. Si se repite mucho, hay que mirarlo.",
           "- **Traceback**: el «rastro» que deja Python cuando algo falla, con las funciones por las que pasó. "
           "La línea que importa es la **última** (qué falló); la de justo encima dice **dónde**.",
           "- **La app (Hub)** es holazazu.app · **Zazu** es tu asistente (Hermes) · **Invitados** son los asistentes de las personas "
           "invitadas · **Vigilante** son los avisos que te llegan al móvil.", ""]
    return "\n".join(md)


if __name__ == "__main__":   # a mano: recoge y enseña el resumen
    print(f"{recoger()} entradas nuevas", file=sys.stderr)
    print(resumen_md())
