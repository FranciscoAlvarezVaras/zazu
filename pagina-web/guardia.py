"""Guardia del puerto público de HolaZazu (lo que llega de internet por Cloudflare). Sin dependencias.

- Límite: 600 peticiones por minuto y por IP (3000 con una sesión válida) → 429.
- Bloqueo: 30 «rutas raras» en un minuto (rutas de escáner como .env, .git, wp-admin, .php… o respuestas 401/404)
  → esa IP queda bloqueada 1 hora (403). Con una sesión válida no cuenta ni se bloquea: Fran nunca se cierra la puerta
  a sí mismo, aunque comparta IP con otros (datos móviles).
- Registro: ~/.local/state/hermes-hub/seguridad.log, solo lo sospechoso (ruta sin parámetros, recortada); se rota a 5 MB.
- Resumen del día: ~/.local/state/hermes-hub/seguridad.json (lo lee estado-servidor.py; las IP no van al Cerebro).
- Los bloqueos viven en memoria: reiniciar hermes-hub los quita todos.
"""
import json, os, re, threading, time
from collections import deque
from pathlib import Path
from urllib.parse import unquote

DIR = Path.home() / ".local/state/hermes-hub"
LOG = DIR / "seguridad.log"
RESUMEN = DIR / "seguridad.json"
LIMITE, LIMITE_SESION, VENTANA = 600, 3000, 60
RARAS, BLOQUEO = 30, 3600
ESCANER = re.compile(
    r"(?i)(^|/)\.(env|git|svn|hg|aws|ssh|docker|htaccess|htpasswd|ds_store|vscode|idea)\b|wp-(admin|login|content|includes|json)"
    r"|xmlrpc|phpmyadmin|pma\b|adminer|\.(php\d?|asp|aspx|jsp|cgi|sql|bak|old|swp)(\?|$)|cgi-bin|/etc/passwd|/proc/self"
    r"|\.\./|\bunion\s+select\b|\bselect\s.+\bfrom\b|sleep\(|benchmark\(|<script|/actuator|/vendor/|/solr|/boaform"
    r"|/hnap1|/owa/|/autodiscover|/server-status|/telescope|/_profiler|/console\b|/manager/html|/shell|/cmd\b|/eval")

ENLACE = re.compile(r"/c/([A-Za-z0-9_-]{16,40})")   # enlace para compartir de Mi nube: el token son letras al azar, no una ruta de escáner

_lock = threading.Lock()
_peticiones = {}   # ip -> deque de instantes (último minuto)
_raras = {}        # ip -> deque de instantes de rutas raras (último minuto)
_bloqueadas = {}   # ip -> instante en que se desbloquea
_hoy = {"fecha": "", "sospechosas": 0, "bloqueadas": 0, "frenadas": 0, "ips": []}
_ultimo_guardado = [0.0]


def _limpio(path):
    p = re.sub(r"[\x00-\x1f\x7f]", "?", unquote(path.split("?", 1)[0]))
    return re.sub(r"^/c/[^/]*", "/c/…", p)[:120]   # el token de un enlace compartido nunca va al registro


def es_rara(path):
    try:
        if ENLACE.fullmatch(path.split("?", 1)[0]):
            return False   # (un token con «pma-» o «/eval…» al azar no es un escáner; si el enlace no existe, el 404 sí cuenta como respuesta rara)
        return bool(ESCANER.search(unquote(path)))
    except Exception:
        return False


def _log(texto):
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 5 * 1024 * 1024:
            os.replace(LOG, LOG.with_suffix(".log.1"))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} · {texto}\n")
    except OSError:
        pass


def _anotar(campo, ip=None, forzar=False):
    """Suma al resumen del día y lo guarda (como mucho cada 5 s, o ya si forzar). Se llama con _lock tomado."""
    hoy = time.strftime("%Y-%m-%d")
    if _hoy["fecha"] != hoy:
        _hoy.update(fecha=hoy, sospechosas=0, bloqueadas=0, frenadas=0, ips=[])
    _hoy[campo] += 1
    if ip and ip not in _hoy["ips"]:
        _hoy["ips"] = (_hoy["ips"] + [ip])[-20:]
    if forzar or time.time() - _ultimo_guardado[0] > 5:
        _ultimo_guardado[0] = time.time()
        try:
            DIR.mkdir(parents=True, exist_ok=True)
            tmp = RESUMEN.with_suffix(".tmp")
            tmp.write_text(json.dumps(dict(_hoy, actualizado=time.strftime("%Y-%m-%d %H:%M:%S")), ensure_ascii=False))
            os.replace(tmp, RESUMEN)
        except OSError:
            pass


def _podar(ahora):
    """Que la memoria no crezca: quita IPs sin actividad en el último minuto (se llama con _lock tomado)."""
    if len(_peticiones) > 5000:
        for d in (_peticiones, _raras):
            for ip in [ip for ip, dq in d.items() if not dq or ahora - dq[-1] > VENTANA]:
                del d[ip]
    for ip in [ip for ip, hasta in _bloqueadas.items() if hasta <= ahora]:
        del _bloqueadas[ip]


def _rara(ip, metodo, path, motivo):
    """Apunta una ruta rara; si ya van RARAS en un minuto, bloquea la IP. Devuelve True si queda bloqueada."""
    ahora = time.time()
    with _lock:
        dq = _raras.setdefault(ip, deque())
        while dq and ahora - dq[0] > VENTANA:
            dq.popleft()
        dq.append(ahora)
        _anotar("sospechosas", ip)
        n = len(dq)
        if n >= RARAS:
            _bloqueadas[ip] = ahora + BLOQUEO
            dq.clear()
            _anotar("bloqueadas", ip, forzar=True)
    _log(f"{ip} · sospechosa · {metodo} {_limpio(path)} · {motivo}")
    if n >= RARAS:
        _log(f"{ip} · BLOQUEADA 1 h · {RARAS} rutas raras en 1 minuto")
        return True
    return False


def entrada(ip, metodo, path, sesion):
    """Antes de atender una petición del puerto público. sesion() → True si trae una sesión válida (solo se mira si
    hace falta). Devuelve None si puede pasar, o (código, texto, segundos de espera) si hay que frenarla."""
    ahora = time.time()
    with _lock:
        hasta = _bloqueadas.get(ip, 0)
        dq = _peticiones.setdefault(ip, deque())
        while dq and ahora - dq[0] > VENTANA:
            dq.popleft()
        dq.append(ahora)
        n = len(dq)
        if len(_peticiones) > 5000 or _bloqueadas:
            _podar(ahora)
    if hasta > ahora and not sesion():
        with _lock:
            _anotar("frenadas")
        return 403, "Acceso bloqueado temporalmente.", int(hasta - ahora)
    if n > LIMITE and (n > LIMITE_SESION or not sesion()):
        with _lock:
            _anotar("frenadas", ip)
        if n == LIMITE + 1:
            _log(f"{ip} · frenada · más de {LIMITE} peticiones en 1 minuto")
        return 429, "Demasiadas peticiones. Espera un minuto.", VENTANA
    if es_rara(path) and not sesion():
        if _rara(ip, metodo, path, "ruta de escáner"):
            return 403, "Acceso bloqueado temporalmente.", BLOQUEO
    return None


def respuesta(ip, metodo, path, codigo, sesion):
    """Después de responder: un 401/404 cuenta como ruta rara (salvo con sesión válida o si ya contó como escáner)."""
    if codigo in (401, 404) and not es_rara(path) and not sesion():
        _rara(ip, metodo, path, f"respuesta {codigo}")


def login_fallido(ip):
    _log(f"{ip} · login fallido")
