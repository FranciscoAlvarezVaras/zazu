"""Pasarela del Modo Hermes: el Hub habla con el api_server del gateway de Hermes (perfil «tecnico»).

Solo biblioteca estándar. La clave del perfil se lee en cada llamada de su .env y nunca se escribe en ningún log.
Contrato (plan §4.9): POST /p/<perfil>/v1/runs, GET …/runs/{id}, GET …/runs/{id}/events (SSE), POST …/approval y …/stop.
"""
import json, os, time, urllib.error, urllib.request
from pathlib import Path

GW = os.environ.get("HUB_GATEWAY_URL", "http://127.0.0.1:8642").rstrip("/")
PERFIL = os.environ.get("HUB_HERMES_PERFIL", "tecnico")
HOME = Path.home()

# Lista blanca: el cliente solo manda el id; proveedor y modelo salen siempre de aquí (plan §3).
MODELOS = {
    "sonnet": {"nombre": "Claude Sonnet 5.5", "proveedor": "anthropic", "modelo": "claude-sonnet-5-5", "pago": "suscripcion", "nota": "Equilibrado · incluido en tu plan"},
    "opus": {"nombre": "Claude Opus 5.5", "proveedor": "anthropic", "modelo": "claude-opus-5-5", "pago": "suscripcion", "nota": "El más listo · gasta ~1,7× cupo"},
    "haiku": {"nombre": "Claude Haiku 4.5", "proveedor": "anthropic", "modelo": "claude-haiku-4-5-20251001", "pago": "suscripcion", "nota": "Rápido"},
    "chatgpt": {"nombre": "GPT-5.6 Terra", "proveedor": "openai-codex", "modelo": "gpt-5.6-terra", "pago": "suscripcion", "nota": "Tu ChatGPT"},
    "gpt": {"nombre": "GPT-6.1 Sol", "proveedor": "openai-api", "modelo": "gpt-6.1-sol", "pago": "uso", "nota": "Pago por uso"},
    "gemini-flash": {"nombre": "Gemini 3.8 Flash", "proveedor": "gemini", "modelo": "gemini-3.8-flash", "pago": "uso", "nota": "Barato · pago por uso"},
    "gemini-pro": {"nombre": "Gemini 3.1 Pro", "proveedor": "gemini", "modelo": "gemini-3.1-pro-preview", "pago": "uso", "nota": "Pago por uso"},
}
DEFECTO = "sonnet"
PROVEEDORES = {"anthropic": "Claude · tu plan", "openai-codex": "ChatGPT · tu plan", "openai-api": "OpenAI · pago por uso", "gemini": "Google Gemini · pago por uso"}
TERMINALES = ("completed", "failed", "cancelled", "interrupted")


class Caido(Exception):
    """El gateway no contesta (apagado, puerto cerrado o tiempo agotado)."""


class SinClave(Exception):
    """No hay clave del perfil, o el gateway no la acepta (401/403)."""


class NoEncontrado(Exception):
    """El gateway no conoce esa ejecución (404): se reinició o ya la olvidó."""


class Respuesta(Exception):
    """Cualquier otra respuesta HTTP inesperada."""

    def __init__(self, code, cuerpo=None):
        super().__init__(f"HTTP {code}")
        self.code, self.cuerpo = code, cuerpo or {}


def perfil_dir(perfil=PERFIL):
    return HOME / ".hermes/profiles" / perfil


def clave(perfil=PERFIL):
    """API_SERVER_KEY del perfil, leída en cada llamada ('' si no hay). Nunca se imprime."""
    try:
        for l in (perfil_dir(perfil) / ".env").read_text().splitlines():
            if l.startswith("API_SERVER_KEY="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        pass
    return ""


def _peticion(metodo, ruta, cuerpo=None, timeout=10, cabeceras=None):
    """(status, json) de /p/<perfil><ruta>. Lanza Caido, SinClave, NoEncontrado o Respuesta."""
    k = clave()
    if not k:
        raise SinClave()
    h = {"Authorization": "Bearer " + k, "Accept": "application/json"}
    if cuerpo is not None:
        h["Content-Type"] = "application/json"
    h.update(cabeceras or {})
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{GW}/p/{PERFIL}{ruta}", data=data, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            det = json.loads(e.read() or b"{}")
        except Exception:
            det = {}
        if e.code in (401, 403):
            raise SinClave() from None
        if e.code == 404:
            raise NoEncontrado() from None
        raise Respuesta(e.code, det) from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise Caido(type(e).__name__) from None


_SALUD = [0.0, False]


def activo():
    """True si hay clave del perfil y el gateway responde a /health en 2 s (la salud se recuerda 30 s)."""
    if not clave():
        return False
    if time.time() - _SALUD[0] > 30:
        try:
            with urllib.request.urlopen(f"{GW}/health", timeout=2) as r:
                ok = r.status == 200
        except Exception:
            ok = False
        _SALUD[:] = [time.time(), ok]
    return _SALUD[1]


def proveedores_con_credencial():
    """Proveedores con alguna credencial en auth.json (raíz o del perfil). Solo se leen las claves, nunca los valores."""
    out = set()
    for p in (HOME / ".hermes/auth.json", perfil_dir() / "auth.json"):
        try:
            out |= set((json.loads(p.read_text()).get("credential_pool") or {}).keys())
        except Exception:
            pass
    return out


def lista_modelos():
    disp = proveedores_con_credencial()
    return [{"id": k, "nombre": m["nombre"], "detalle": m["modelo"], "proveedor": m["proveedor"],
             "proveedor_nombre": PROVEEDORES.get(m["proveedor"], m["proveedor"]), "pago": m["pago"], "nota": m["nota"],
             "disponible": m["proveedor"] in disp} for k, m in MODELOS.items()]


def id_de_modelo(modelo):
    """El id de MODELOS de un nombre de modelo del proveedor (None si no es de la lista)."""
    return next((k for k, m in MODELOS.items() if m["modelo"] == modelo), None)


def iniciar(job_id, texto, session=None, modelo=None):
    """Lanza una ejecución. Devuelve run_id. Idempotency-Key = id del trabajo (un reintento no duplica)."""
    cuerpo = {"input": texto}
    if session:
        cuerpo["session_id"] = session
    if modelo:
        m = MODELOS[modelo]
        cuerpo["model"], cuerpo["provider"] = m["modelo"], m["proveedor"]
    st, r = _peticion("POST", "/v1/runs", cuerpo, timeout=10, cabeceras={"Idempotency-Key": job_id})
    if not r.get("run_id"):
        raise Respuesta(st, r)
    return r["run_id"]


def estado(run_id, timeout=10):
    """Estado de la ejecución ({status, session_id, …}) o None si el gateway ya no la conoce."""
    try:
        return _peticion("GET", f"/v1/runs/{run_id}", timeout=timeout)[1]
    except NoEncontrado:
        return None


def eventos(run_id, last_seq=-1):
    """Generador de eventos SSE (dicts con «seq») desde last_seq. Socket con 30 s de espera (el gateway manda
    un keepalive cada 10 s). Termina cuando el gateway cierra el flujo. Lanza NoEncontrado si no conoce la ejecución."""
    k = clave()
    if not k:
        raise SinClave()
    req = urllib.request.Request(f"{GW}/p/{PERFIL}/v1/runs/{run_id}/events?last_seq={int(last_seq)}",
                                 headers={"Authorization": "Bearer " + k, "Accept": "text/event-stream"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NoEncontrado() from None
        if e.code in (401, 403):
            raise SinClave() from None
        raise Respuesta(e.code) from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise Caido(type(e).__name__) from None
    with r:
        datos = []
        for raw in r:
            linea = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not linea:
                if datos:
                    try:
                        ev = json.loads("\n".join(datos))
                    except ValueError:
                        ev = None
                    datos = []
                    if isinstance(ev, dict):
                        yield ev
                continue
            if linea.startswith("data:"):
                datos.append(linea[5:].lstrip(" "))


def aprobar(run_id, request_id, decision):
    """Responde a la aprobación pendiente. 200 → True; 409 (ya no está pendiente) → False."""
    cuerpo = {"choice": decision}
    if request_id:
        cuerpo["request_id"] = request_id
    try:
        _peticion("POST", f"/v1/runs/{run_id}/approval", cuerpo, timeout=10)
        return True
    except Respuesta as e:
        if e.code == 409:
            return False
        raise


def parar(run_id):
    """Pide parar la ejecución (el gateway contesta «stopping» y luego emite run.cancelled)."""
    try:
        return _peticion("POST", f"/v1/runs/{run_id}/stop", {}, timeout=10)[1]
    except Respuesta as e:
        if e.code == 409:   # ya no está activa en este gateway
            return {"status": "not_active"}
        raise
