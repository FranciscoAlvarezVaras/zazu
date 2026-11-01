"""Avisos del vigía de Zazu (zv) vistos desde el Hub.

LEER: directamente la base SQLite del vigía (~/.local/state/zazu-vigia/avisos.db) en modo solo lectura.
ESCRIBIR: únicamente llamando al CLI `zv` (hecho / descartar / luego / draft / responder / permisos quitar) con una lista de argumentos (nunca un shell)
y un id numérico validado. `draft` solo IMPRIME el comando de envío: nada de aquí manda mensajes.
Los textos de la base ya vienen tachados y recortados por el vigía; aun así van tal cual como cadenas JSON inertes
(el front debe pintarlos con textContent, nunca como HTML). Solo biblioteca estándar.
"""
import json, os, re, sqlite3, subprocess, time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
ID_OK = re.compile(r"[1-9][0-9]{0,8}")
ESTADOS = ("abierto", "nuevo", "visto", "luego", "hecho", "descartado")
# avisos que el vigía de agenda deriva de un evento o una tarea (los que el Panel ya enseña como evento/tarea)
DE_AGENDA = ("evento", "llevar", "despues", "tarea", "tarea_vence", "recordar")
URL_OK = re.compile(r"https?://[^\s<>\"']{1,290}", re.I)
FRESCO_MIN = 45          # un vigía sin latido en tantos minutos se da por parado (ciclo cada 30 min, de 08:00 a 20:00)
HORA_INI, HORA_FIN = 8, 20   # horas de la pasada primera y última del vigía; fuera de ahí descansa (+10 min de margen al abrir)
WACLI_FRESCO_MIN = 30      # el latido de wacli se renueva cada ~13 min en la práctica


class AvisoError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def _home():
    return Path(os.environ.get("HOME") or Path.home())


def estado_dir():
    return Path(os.environ.get("ZV_ESTADO") or _home() / ".local/state/zazu-vigia")


def conf_dir():
    return Path(os.environ.get("ZV_CONFIG") or _home() / ".config/zazu-vigia")


def zv_bin():
    return os.environ.get("HUB_ZV") or str(_home() / ".local/bin/zv")


def ahora():
    return datetime.now(TZ)


def iso(ts):
    return datetime.fromtimestamp(ts, TZ).isoformat(timespec="seconds") if ts else None


def limpio(s, n=300):
    s = re.sub(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e]+", " ", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def enlace_ok(u):
    """Solo http(s): un `javascript:` o `data:` en la base nunca llega a un href."""
    m = URL_OK.match(str(u or "").strip())
    return m.group(0) if m else ""


def _conectar():
    ruta = estado_dir() / "avisos.db"
    if not ruta.is_file():
        raise FileNotFoundError("el vigía aún no ha creado su bandeja de avisos")
    c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=2)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=1")
    return c


def _aviso(r):
    return {"id": r["id"], "codigo": r["codigo"], "fuente": r["fuente"], "tipo": r["tipo"], "prio": r["prio"],
            "titulo": limpio(r["titulo"], 160), "detalle": limpio(r["detalle"], 300),
            "borrador": limpio(r["borrador"], 200), "tiene_borrador": bool(r["borrador"] and r["destino"]),
            "enlace": enlace_ok(r["enlace"]), "cuenta": limpio(r["cuenta"], 40) or None, "chat": limpio(r["chat"], 40) or None,
            "due": r["due"] or None, "hora": r["hora"] or None, "creado": iso(r["creado"]), "vence": iso(r["vence"]),
            "estado": r["estado"], "pospuesto_hasta": iso(r["pospuesto_hasta"]), "entrega": r["entrega"]}


def listar(estado="abierto", n=50):
    """Avisos visibles (nunca los silenciosos ni los 'item_*' de WhatsApp). estado: abierto = nuevos, vistos y los
    pospuestos cuya hora ya llegó. Orden: prioridad y luego el más reciente."""
    if estado not in ESTADOS:
        raise AvisoError(400, "estado no válido")
    n = min(max(int(n), 1), 200)
    now = int(time.time())
    base = "silencioso=0 AND tipo NOT LIKE 'item\\_%' ESCAPE '\\'"
    if estado == "abierto":
        where = (f"{base} AND entrega NOT IN ('superado','caducado') AND (estado IN ('nuevo','visto') OR "
                 "(estado='luego' AND COALESCE(pospuesto_hasta,0)<=:now)) AND (vence IS NULL OR vence>:now) "
                 "AND (aviso_en IS NULL OR aviso_en<=:now)")
    else:
        where = f"{base} AND estado=:estado"
    with closing(_conectar()) as c:
        filas = c.execute(f"SELECT * FROM avisos WHERE {where} ORDER BY prio ASC, creado DESC, id DESC LIMIT :n",
                          {"now": now, "estado": estado, "n": n}).fetchall()
    return [_aviso(r) for r in filas]


def _cols(c, tabla="avisos"):
    return {r[1] for r in c.execute(f"PRAGMA table_info({tabla})")}


PROPUESTA = "(tipo LIKE 'item\\_%' ESCAPE '\\' OR tipo LIKE 'flujo\\_%' ESCAPE '\\')"
ETIQUETA_ACCION = {"sombra": "sombra: no creada", "creado": "creada en Google", "pendiente": "por crear", "tope": "tope diario: no creada",
                   "duplicado": "ya existía", "fallido": "falló", "evento_creado": "evento creado"}


def recientes_hoy(n=30):
    """Las PROPUESTAS abiertas del vigía (tareas y eventos tentativos de WhatsApp y de los flujos de correo) de los últimos 7 días:
    las que Fran aún no ha contestado. Lo contestado (Sí / No) y lo oculto por una regla «nunca» ya no sale: la lista se ordena sola.
    Si la base del vigía es anterior a los permisos (sin columnas riesgo/permiso/…), salen igual con valores por defecto."""
    desde = int(time.time()) - 7 * 86400
    with closing(_conectar()) as c:
        cols = _cols(c)
        nunca = " AND COALESCE(decision,'')<>'nunca'" if "decision" in cols else ""
        filas = c.execute(f"SELECT * FROM avisos WHERE {PROPUESTA} AND estado IN ('nuevo','visto') AND creado>=?{nunca} ORDER BY id DESC LIMIT ?",
                          (desde, n)).fetchall()
        reglas = {}
        if "permisos" in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            reglas = {r["clave"]: r["decision"] for r in c.execute("SELECT clave, decision FROM permisos")}
    out = []
    for r in filas:
        g = (lambda k, d=None: r[k] if k in cols else d)
        riesgo = g("riesgo") if g("riesgo") in ("bajo", "medio", "alto") else ("medio" if r["tipo"].endswith("evento") else "bajo")
        sosp = bool(g("sospechoso", 0))
        out.append({"id": r["id"], "codigo": r["codigo"], "fuente": "wa" if r["fuente"] == "wa" else "correo",
                    "tipo": "evento" if r["tipo"].endswith("evento") else "tarea",
                    "titulo": limpio(r["titulo"], 160), "detalle": limpio(r["detalle"], 160), "due": r["due"] or None, "hora": r["hora"] or None,
                    "chat": limpio(r["chat"], 40) or None, "accion": r["accion"], "accion_txt": ETIQUETA_ACCION.get(r["accion"] or "", ""),
                    "creado": iso(r["creado"]), "riesgo": riesgo, "sospechoso": sosp,
                    "preparada": g("decision") == "auto" and not sosp and riesgo == "bajo",
                    "regla": reglas.get(g("permiso")), "recordable": riesgo != "alto"})
    return out


def permisos():
    """Reglas «siempre / nunca» del vigía (solo lectura). Vacío si la base aún no tiene la tabla."""
    with closing(_conectar()) as c:
        if "permisos" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            return []
        filas = c.execute("SELECT * FROM permisos ORDER BY actualizado DESC LIMIT 200").fetchall()
    out = []
    for r in filas:
        accion, _, quien = r["clave"].partition(":remitente:")
        que = {"apuntar_tarea": "Tareas", "apuntar_cita": "Citas"}.get(accion, limpio(accion, 30))
        quien = "un chat de WhatsApp" if quien.startswith("wa-") else limpio(quien, 80)
        out.append({"clave": limpio(r["clave"], 160), "decision": r["decision"], "texto": f"{que} de {quien}", "ejemplo": limpio(r["ejemplo"], 90),
                    "veces_si": r["veces_si"], "veces_no": r["veces_no"], "aplicada": r["aplicada"], "actualizado": iso(r["actualizado"])})
    return out


def _json(ruta):
    try:
        return json.loads(Path(ruta).read_text())
    except (OSError, ValueError):
        return {}


def _al_dia(ts, ahora=None):
    """¿Está al día el último latido? Dentro del horario, con FRESCO_MIN; de noche vale haber hecho la última pasada (20:00)."""
    ahora = ahora or datetime.now().astimezone()
    t = datetime.fromtimestamp(int(ts or 0)).astimezone()
    if (ahora - t).total_seconds() / 60 <= FRESCO_MIN:
        return True
    de_dia = ahora.replace(hour=HORA_INI, minute=10, second=0, microsecond=0) <= ahora <= ahora.replace(hour=HORA_FIN, minute=FRESCO_MIN, second=0, microsecond=0)
    if de_dia:
        return False
    cierre = ahora.replace(hour=HORA_FIN, minute=0, second=0, microsecond=0)
    if ahora < cierre:
        cierre -= timedelta(days=1)
    return t >= cierre - timedelta(minutes=10)


def vigias():
    """Frescura de cada vigía (latidos) + interruptores. Sin contenidos. Cada pieza falla por separado."""
    ahora_ts = int(time.time())
    cfg = _json(conf_dir() / "config.json")
    modo = (cfg.get("modo") or {}) if isinstance(cfg, dict) else {}
    out = {"fuentes": {}, "pausa": (conf_dir() / "PAUSA").exists(), "entrega_real": (conf_dir() / "ENTREGA_ACTIVA").exists(), "modo": modo}
    try:
        with closing(_conectar()) as c:
            for r in c.execute("SELECT fuente, ts, ok, detalle, fallos FROM latidos"):
                hace = max(0, (ahora_ts - int(r["ts"] or 0)) // 60)
                out["fuentes"][r["fuente"]] = {"ultimo": iso(r["ts"]), "hace_min": hace, "ok": bool(r["ok"]) and _al_dia(r["ts"]),
                                               "fallos": r["fallos"], "detalle": limpio(r["detalle"], 80), "modo": modo.get(r["fuente"])}
    except (OSError, sqlite3.Error) as e:
        out["error"] = f"no pude leer los latidos ({type(e).__name__})"
    try:
        m = (_home() / ".local/state/wacli/HEARTBEAT").stat().st_mtime
        hace = max(0, int((time.time() - m) // 60))
        out["wacli"] = {"ultimo": iso(m), "hace_min": hace, "ok": hace <= WACLI_FRESCO_MIN}
    except OSError:
        out["wacli"] = {"ultimo": None, "hace_min": None, "ok": False}
    out["bandeja"] = _bandeja()
    return out


def _bandeja():
    """Estado de la bandeja de Tareas/Calendar (zb): solo lectura, sin contenidos."""
    d = Path(os.environ.get("ZB_ESTADO") or _home() / ".local/state/zazu-bandeja")
    cd = Path(os.environ.get("ZB_CONFIG") or _home() / ".config/zazu-bandeja")
    try:
        modo = "vivo" if (cd / "MODO").read_text().strip() == "vivo" else "sombra"
    except OSError:
        modo = "sombra"
    ruta = d / "estado.db"
    if not ruta.is_file():
        return {"ok": False, "modo": modo, "ultimo": None, "hace_min": None, "propuestas": 0}
    try:
        with closing(sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=2)) as c:
            u = c.execute("SELECT v FROM meta WHERE k='ultimo_ciclo'").fetchone()
            p = c.execute("SELECT count(*) FROM propuestas WHERE estado='pendiente'").fetchone()[0]
        ts = datetime.fromisoformat(u[0].split()[0]) if u else None
        hace = max(0, int((time.time() - ts.timestamp()) // 60)) if ts else None
        return {"ok": ts is not None and _al_dia(ts.timestamp()), "modo": modo, "ultimo": ts.isoformat(timespec="seconds") if ts else None,
                "hace_min": hace, "propuestas": p}
    except (OSError, ValueError, sqlite3.Error):
        return {"ok": False, "modo": modo, "ultimo": None, "hace_min": None, "propuestas": 0}


# ───────── escritura: solo por el CLI zv ─────────
def _id(valor):
    s = str(valor).strip()
    if not ID_OK.fullmatch(s):
        raise AvisoError(400, "id de aviso no válido")
    return s


def _zv(args, timeout=15):
    home = _home()
    env = {"PATH": f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8"}
    env.update({k: v for k, v in os.environ.items() if k.startswith("ZV_") or k == "PYTHONPATH"})
    try:
        r = subprocess.run([zv_bin()] + args, env=env, capture_output=True, text=True, timeout=timeout, cwd=str(home), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise AvisoError(504, "el vigía tardó demasiado en contestar")
    except OSError:
        raise AvisoError(503, "no encuentro el comando del vigía (zv)")
    return r.returncode, r.stdout


def _existe(i):
    with closing(_conectar()) as c:
        r = c.execute("SELECT * FROM avisos WHERE id=? AND silencioso=0", (int(i),)).fetchone()
    if not r:
        raise AvisoError(404, "ese aviso no existe")
    return r


def horas_hasta(cuando=None, horas=None):
    """`horas` (0,1–168) o `cuando`: 'manana' (08:00 del día siguiente) / 'tarde' (17:00 de hoy, o mañana si ya pasó)."""
    if cuando in ("manana", "mañana"):
        d = ahora()
        fin = (d + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        return round(max((fin.timestamp() - d.timestamp()) / 3600, 0.1), 2)   # timestamps: con la misma zona, «fin - d» ignora el cambio de hora
    if cuando == "tarde":
        d = ahora()
        fin = d.replace(hour=17, minute=0, second=0, microsecond=0)
        if fin <= d:
            fin += timedelta(days=1)
        return round((fin.timestamp() - d.timestamp()) / 3600, 2)
    if horas is None:
        return 3.0
    try:
        h = float(horas)
    except (TypeError, ValueError):
        raise AvisoError(400, "horas no válidas")
    if not 0.1 <= h <= 168 or h != h:
        raise AvisoError(400, "horas no válidas")
    return round(h, 2)


def accion(id_, que, cuando=None, horas=None):
    """hecho | descartar | luego → llama a `zv <que> <id> [horas]`. Devuelve el aviso ya actualizado."""
    i = _id(id_)
    if que not in ("hecho", "descartar", "luego"):
        raise AvisoError(400, "acción no válida")
    _existe(i)
    args = [que, i] + ([f"{horas_hasta(cuando, horas):g}"] if que == "luego" else [])
    rc, _ = _zv(args)
    if rc:
        raise AvisoError(502, "el vigía no pudo cambiar el aviso")
    return _aviso(_existe(i))


RESPUESTAS = ("si", "no", "siempre", "nunca")
CLAVE_OK = re.compile(r"[a-z_]{3,30}:[a-z]{3,20}:[\w@.+-]{1,120}")


def _propuesta(i):
    with closing(_conectar()) as c:
        r = c.execute(f"SELECT * FROM avisos WHERE id=? AND {PROPUESTA}", (int(i),)).fetchone()
    if not r:
        raise AvisoError(404, "esa propuesta no existe")
    return r


def responder(id_, que):
    """Sí / No / Sí, siempre / No, nunca a una propuesta del vigía. «No» va por `zv descartar <id>`; lo demás por `zv responder <id> <que>`.
    Nada de esto escribe en Google: en modo sombra el vigía solo anota la decisión (y la regla, si la hay).
    Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: tools/proactive_tools.py (parse_approval_response).
    Cambios: una ruta por botón en vez de leer «yes/no/always» de un mensaje; la decisión la guarda el CLI zv, no este proceso."""
    i = _id(id_)
    if que not in RESPUESTAS:
        raise AvisoError(400, "respuesta no válida")
    _propuesta(i)
    if que == "no":
        rc, _ = _zv(["descartar", i])
        if rc:
            raise AvisoError(502, "el vigía no pudo descartarla")
        return {"id": int(i), "mensaje": "Descartada"}
    rc, out = _zv(["responder", i, que, "--json"])
    try:
        d = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except ValueError:
        d = {}
    if not isinstance(d, dict) or not d.get("ok"):
        raise AvisoError(409 if rc == 1 and isinstance(d, dict) and d.get("error") else 502,
                         limpio(d.get("error"), 160) if isinstance(d, dict) and d.get("error") else "el vigía no pudo guardar la respuesta")
    return {"id": int(i), "mensaje": limpio(d.get("mensaje"), 120)}


def quitar_permiso(clave):
    """Quita una regla «siempre / nunca» (`zv permisos quitar <clave>`)."""
    k = str(clave or "").strip()
    if not CLAVE_OK.fullmatch(k):
        raise AvisoError(400, "regla no válida")
    rc, _ = _zv(["permisos", "quitar", k, "--json"])
    if rc == 1:
        raise AvisoError(404, "esa regla no existe")
    if rc:
        raise AvisoError(502, "el vigía no pudo quitar la regla")
    return {"clave": k}


def borrador(id_):
    """Texto del comando de envío que el vigía propone (`zv draft`). NO se ejecuta: Zazu lo corre como comando visible y el
    hook de aprobación le enseña a Fran destinatario y texto completos."""
    i = _id(id_)
    r = _existe(i)
    if not (r["borrador"] and r["destino"]):
        raise AvisoError(404, "ese aviso no tiene borrador con destinatario")
    rc, out = _zv(["draft", i])
    cmd = next((l.strip() for l in out.splitlines() if l.startswith("wacli send text --to ")), None)
    if rc or not cmd:
        raise AvisoError(502, "el vigía no pudo preparar el borrador")
    return {"id": r["id"], "codigo": r["codigo"], "comando": cmd, "ejecutado": False,
            "aviso": "No se ha enviado nada. Pídele a Zazu «manda %s»: te enseñará el comando completo y esperará tu OK." % r["codigo"]}

