"""Registro de errores de las invitadas, para que Fran los revise en Personas: qué falló, dónde y a quién.

Nunca guarda lo que escribieron: solo el sitio (ruta, herramienta, «chat»…), el código y el texto del error.
Un archivo JSONL (0600) que rota a los 2 MB. Se suman los errores del gateway de cada una (rutinas, WhatsApp, Telegram)
y las líneas ERROR de los registros de su Hermes. Solo biblioteca estándar.
"""
import json, os, re, subprocess, threading, time
from pathlib import Path

F = Path.home() / ".local/state/zazu-web/errores-invitadas.jsonl"
MAX_BYTES = 2_000_000
DIAS = 7
_L = threading.Lock()
_CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CLAVE = re.compile(r"sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,}")


def _limpio(x, n=300):
    """Una línea, corta, sin correos ni nada que parezca una clave."""
    return _CLAVE.sub("…", _CORREO.sub("<correo>", " ".join(str(x or "").split())))[:n]


def anotar(perfil, origen, detalle, codigo=None):
    linea = json.dumps({"t": round(time.time(), 1), "perfil": str(perfil or "?")[:40], "origen": _limpio(origen, 60),
                        "codigo": codigo, "detalle": _limpio(detalle)}, ensure_ascii=False)
    try:
        with _L:
            F.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if F.exists() and F.stat().st_size > MAX_BYTES:
                os.replace(F, F.with_name(F.name + ".1"))
            fd = os.open(F, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (linea + "\n").encode())
            finally:
                os.close(fd)
    except OSError:
        pass   # el registro nunca tumba una petición


def _propios(desde):
    out = []
    for f in (F.with_name(F.name + ".1"), F):
        try:
            lineas = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for l in lineas:
            try:
                d = json.loads(l)
            except ValueError:
                continue
            if isinstance(d, dict) and float(d.get("t") or 0) >= desde:
                out.append(d)
    return out


def _gateway(perfil, desde):
    """Errores del gateway de la invitada (systemd: hermes-gateway-<perfil>), prioridad warning o peor."""
    try:
        r = subprocess.run(["journalctl", "--user", "-u", f"hermes-gateway-{perfil}", "-p", "warning", "--since", f"@{int(desde)}",
                            "-o", "json", "--no-pager", "-n", "100"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for l in r.stdout.splitlines():
        try:
            d = json.loads(l)
            out.append({"t": int(d.get("__REALTIME_TIMESTAMP", 0)) / 1e6, "perfil": perfil, "origen": "gateway (rutinas y canales)",
                        "codigo": None, "detalle": _limpio(d.get("MESSAGE"))})
        except (ValueError, TypeError):
            continue
    return out


def _hermes(perfil, prof_dir, desde):
    """Líneas ERROR de los registros de su Hermes (~/.hermes/profiles/<perfil>/logs), recortadas."""
    out = []
    logs = Path(prof_dir) / "logs"
    if not logs.is_dir():
        return out
    for f in sorted(logs.glob("*.log"))[-5:]:
        try:
            if f.stat().st_mtime < desde:
                continue
            with open(f, "rb") as fh:
                fh.seek(max(0, f.stat().st_size - 200_000))
                lineas = fh.read().decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for i, l in enumerate(lineas):
            if " ERROR " in l or l.startswith("ERROR") or "Traceback" in l:
                m = re.match(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", l)
                if "Traceback" in l:   # «Traceback…» no dice nada: lo útil es su última línea (FileNotFoundError: …)
                    l = _final_traceback(lineas, i)
                try:
                    t = time.mktime(time.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")) if m else f.stat().st_mtime
                except ValueError:
                    t = f.stat().st_mtime
                if t >= desde:
                    out.append({"t": t, "perfil": perfil, "origen": f"hermes · {f.name}", "codigo": None, "detalle": _limpio(l)})
    return out[-30:]


def _final_traceback(lineas, i):
    """La línea «Tipo: mensaje» que cierra el Traceback que empieza en lineas[i] (sin la fecha del registro)."""
    for l in lineas[i + 1:i + 80]:
        x = re.sub(r"^\d{4}-\d{2}-\d{2}[ T][\d:,.]+\s*", "", l)
        if not x.strip() or "Traceback" in x:
            break
        if re.match(r"[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt)\b", x):
            return x
    return lineas[i]


# errores ya explicados o arreglados: (patrón, explicación). En Personas no cuentan como pendientes y el vigilante no los avisa.
CONOCIDOS = [
    (r"conecta tu ChatGPT o tu Claude", "error antiguo de la IA propia (arreglado el 22/10)"),
    (r"rango inválido", "la agenda se pidió sin fechas (no lo hace la app)"),
    (r"ha gastado el crédito", "se le acabó el crédito del mes"),
    (r"todavía no está activo", "su Zazu no tenía crédito activo"),
    (r"Ya hay una carpeta con ese nombre", "carpeta repetida (normal)"),
    (r"no ha conectado su Google", "intentó usar Google sin tenerlo conectado"),
    (r"esa hora ya ha pasado", "recordatorio a una hora pasada (desde el 22/10 se pasa a mañana)"),
    (r"zazu/scripts/noticias\.py", "sus herramientas de Google no arrancaban (arreglado el 22/10)"),
    (r"el nombre solo puede llevar letras", "no aceptaba paréntesis en el nombre (arreglado el 23/10)"),
    (r"UNIQUE constraint failed: sessions\.title", "choque de títulos al limpiar la agenda (arreglado el 23/10)"),
    (r"no se completó la vinculación", "el código de WhatsApp caducó sin escribirse (no es un fallo de la app)"),
]


def conocido(detalle):
    """La explicación si es un error conocido; si no, None."""
    return next((e for p, e in CONOCIDOS if re.search(p, str(detalle or ""))), None)


def leer(perfiles, prof_dir, perfil=None, dias=DIAS, n=300):
    """Los errores de los últimos `dias`, lo más nuevo primero. `perfiles`: los de las invitadas (otros no se miran)."""
    desde = time.time() - dias * 86400
    mios = [p for p in perfiles if not perfil or p == perfil]
    out = [d for d in _propios(desde) if d.get("perfil") in mios]
    for p in mios:
        out += _gateway(p, desde) + _hermes(p, prof_dir(p), desde)
    for d in out:
        d["conocido"] = conocido(d.get("detalle"))
    return sorted(out, key=lambda d: -float(d.get("t") or 0))[:n]
