#!/usr/bin/env python3
"""Parches locales del núcleo de Hermes para el Modo Hermes (seguridad).

Problema (revisión adversaria, hallazgo ALTO): el gateway lanza procesos hijos de larga vida que heredan TODO su
entorno, con las claves dentro (API_SERVER_KEY, SUDO_PASSWORD, claves de proveedores…). Su /proc/<pid>/environ lo
puede leer cualquier proceso del mismo usuario (incluido el agente), así que las claves que Fran protege tras una
aprobación se pueden leer en una línea. Los hijos afectados:
  - scripts/whatsapp-bridge/bridge.js        (plugins/platforms/whatsapp/adapter.py :: _bridge_env)
  - tools/mcp_death_supervisor.py            (tools/mcp_tool.py :: _spawn_death_supervisor)
Los servidores MCP stdio (p.ej. mcp_google.py) ya salen con el entorno saneado; estos dos no.

Estos ficheros son del núcleo de Hermes: «hermes update» los sobreescribe. Por eso este parche:
  - es idempotente (si ya está aplicado, no hace nada);
  - va guardado por un CONTEXTO EXACTO: solo toca el código si coincide letra por letra con lo esperado; si el
    upstream ha cambiado, lo deja intacto, lo registra y sigue (nunca corrompe el fichero);
  - comprueba que el fichero sigue siendo Python válido (ast.parse) antes de reemplazar nada;
  - se re-aplica tras cada actualización nocturna (lo llama scripts/actualizar-hermes.sh).

Uso:
  aplicar.py [--arbol DIR] [--comprobar] [--sin-copia]
    --arbol DIR    raíz del árbol de hermes-agent (por defecto: el de ~/.hermes, autodetectado)
    --comprobar    solo dice qué haría; no escribe nada (sirve para el log y para probar)
    --sin-copia    no deja .bak-fix2 (para pruebas en una copia desechable)

Salida (última línea, estable para scripts): «RESULTADO aplicados=N ya=M saltados=K errores=E».
Sale 0 si no hay errores (aunque haya saltos), 1 si algún parche dejó el fichero en estado inesperado.
Nunca imprime valores de variables de entorno: solo nombres de ficheros y de parches.
"""
import argparse
import ast
import os
import sys


# --- Definición de los parches ---------------------------------------------------------------------------------
# Cada parche: nombre, ruta relativa, VIEJO (contexto exacto que debe aparecer una sola vez) y NUEVO (lo que lo
# sustituye). MARCA es un trozo del NUEVO que, si ya está en el fichero, significa «ya aplicado» (idempotencia).

_BRIDGE_VIEJO = (
    "        bridge_env = with_hermes_node_path()\n"
)
_BRIDGE_NUEVO = (
    "        # fix2 (Modo Hermes): el bridge.js NO hereda los secretos del gateway. Su /proc/<pid>/environ lo puede\n"
    "        # leer cualquier proceso del mismo usuario; dejar aquí API_SERVER_KEY/SUDO_PASSWORD/claves de proveedor\n"
    "        # permitía leerlas sin aprobación. Solo PATH/NODE/HOME/locale/HERMES_HOME y las WHATSAPP_*; el resto fuera.\n"
    "        _MH_CONSERVAR = (\"PATH\", \"HOME\", \"USER\", \"LOGNAME\", \"LANG\", \"LC_ALL\", \"LC_CTYPE\", \"TZ\",\n"
    "                         \"TMPDIR\", \"TMP\", \"TEMP\", \"XDG_RUNTIME_DIR\", \"HERMES_HOME\", \"HERMES_SCRATCH_DIR\",\n"
    "                         \"NODE_PATH\", \"NODE_OPTIONS\")\n"
    "        bridge_env = {_k: _v for _k, _v in with_hermes_node_path().items()\n"
    "                      if _k in _MH_CONSERVAR or _k.startswith(\"WHATSAPP_\")}\n"
)
_BRIDGE_MARCA = "_MH_CONSERVAR = ("

_SUPER_VIEJO = (
    "        return subprocess.Popen(\n"
    "            [sys.executable, supervisor, \"--parent-pgid\", str(os.getpgid(0))],\n"
    "            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=_get_mcp_stderr_log(),\n"
    "            start_new_session=True, close_fds=True, text=True)\n"
)
_SUPER_NUEVO = (
    "        return subprocess.Popen(\n"
    "            [sys.executable, supervisor, \"--parent-pgid\", str(os.getpgid(0))],\n"
    "            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=_get_mcp_stderr_log(),\n"
    "            start_new_session=True, close_fds=True, text=True,\n"
    "            # fix2 (Modo Hermes): el supervisor es solo-stdlib y no necesita secretos; no se los heredamos\n"
    "            # (su /proc/<pid>/environ es legible por el mismo usuario). Solo PATH y HOME.\n"
    "            env={\"PATH\": os.environ.get(\"PATH\", \"\"), \"HOME\": os.environ.get(\"HOME\", \"\")})\n"
)
_SUPER_MARCA = "env={\"PATH\": os.environ.get(\"PATH\", \"\"), \"HOME\": os.environ.get(\"HOME\", \"\")})"

_OAUTH_LOOP_VIEJO = (
    "    native_host = not text or (urlparse(text).hostname or \"\").lower().rstrip(\".\") == \"api.anthropic.com\"\n"
)
_OAUTH_LOOP_NUEVO = (
    "    # fix3 (experimento Headroom): un proxy LOCAL (127.0.0.1/localhost) que reenvía a api.anthropic.com conserva la\n"
    "    # identidad OAuth de la suscripción (Bearer + cabeceras de Claude Code); sin esto Hermes mandaba el token como\n"
    "    # x-api-key y Anthropic contestaba 401. Solo bucle local: ningún host remoto cambia de trato.\n"
    "    _mh_host = (urlparse(text).hostname or \"\").lower().rstrip(\".\") if text else \"\"\n"
    "    native_host = not text or _mh_host == \"api.anthropic.com\" or _mh_host in (\"127.0.0.1\", \"localhost\", \"::1\")\n"
)
_OAUTH_LOOP_MARCA = "fix3 (experimento Headroom)"

_TERCERO_VIEJO = (
    "    normalized = _normalized_lower(base_url)\n"
    "    return bool(normalized) and \"anthropic.com\" not in normalized\n"
)
_TERCERO_NUEVO = (
    "    normalized = _normalized_lower(base_url)\n"
    "    # fix3 (experimento Headroom): un proxy LOCAL (127.0.0.1/localhost/::1) que reenvía a api.anthropic.com no es un\n"
    "    # tercero: conserva la identidad OAuth de la suscripción (Bearer + cabeceras de Claude Code). Solo bucle local.\n"
    "    if normalized.startswith((\"http://127.0.0.1\", \"http://localhost\", \"http://[::1]\")):\n"
    "        return False\n"
    "    return bool(normalized) and \"anthropic.com\" not in normalized\n"
)
_TERCERO_MARCA = "fix3 (experimento Headroom): un proxy LOCAL (127.0.0.1/localhost/::1)"

PARCHES = [
    {"nombre": "bridge.js sin secretos", "ruta": "plugins/platforms/whatsapp/adapter.py",
     "viejo": _BRIDGE_VIEJO, "nuevo": _BRIDGE_NUEVO, "marca": _BRIDGE_MARCA},
    {"nombre": "mcp_death_supervisor sin secretos", "ruta": "tools/mcp_tool.py",
     "viejo": _SUPER_VIEJO, "nuevo": _SUPER_NUEVO, "marca": _SUPER_MARCA},
    {"nombre": "OAuth de Anthropic a través de un proxy local (Headroom)", "ruta": "agent/anthropic_credentials.py",
     "viejo": _OAUTH_LOOP_VIEJO, "nuevo": _OAUTH_LOOP_NUEVO, "marca": _OAUTH_LOOP_MARCA},
    {"nombre": "proxy local no es un tercero (Headroom)", "ruta": "agent/anthropic_endpoints.py",
     "viejo": _TERCERO_VIEJO, "nuevo": _TERCERO_NUEVO, "marca": _TERCERO_MARCA},
]


def detectar_arbol():
    """Raíz de hermes-agent por defecto: la de ~/.hermes, o la que diga HERMES_HOME."""
    hh = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    cand = os.path.join(hh, "hermes-agent")
    return cand if os.path.isdir(cand) else hh


def aplicar_uno(arbol, p, comprobar, sin_copia, log):
    """Devuelve 'aplicado' | 'ya' | 'saltado' | 'error'. Nunca deja el fichero a medias."""
    ruta = os.path.join(arbol, p["ruta"])
    if not os.path.isfile(ruta):
        log(f"  · {p['nombre']}: no existe {p['ruta']} → lo salto")
        return "saltado"
    texto = open(ruta, encoding="utf-8").read()
    if p["marca"] in texto:
        log(f"  ✓ {p['nombre']}: ya aplicado")
        return "ya"
    n = texto.count(p["viejo"])
    if n == 0:
        log(f"  ! {p['nombre']}: el código de {p['ruta']} no coincide con lo esperado (¿cambió el upstream?) → lo salto SIN tocar")
        return "saltado"
    if n > 1:
        log(f"  ! {p['nombre']}: el contexto aparece {n} veces en {p['ruta']} (ambiguo) → lo salto SIN tocar")
        return "saltado"
    nuevo_texto = texto.replace(p["viejo"], p["nuevo"], 1)
    try:
        ast.parse(nuevo_texto)
    except SyntaxError as e:
        log(f"  ✗ {p['nombre']}: tras el parche {p['ruta']} no sería Python válido ({e.__class__.__name__}) → NO lo toco")
        return "error"
    if comprobar:
        log(f"  · {p['nombre']}: se aplicaría a {p['ruta']}")
        return "aplicado"
    if not sin_copia:
        bak = ruta + ".bak-fix2"
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                f.write(texto)
    tmp = ruta + ".fix2.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(nuevo_texto)
    os.replace(tmp, ruta)
    log(f"  → {p['nombre']}: aplicado a {p['ruta']}")
    return "aplicado"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arbol")
    ap.add_argument("--comprobar", action="store_true")
    ap.add_argument("--sin-copia", action="store_true")
    ap.add_argument("--silencioso", action="store_true", help="solo la línea RESULTADO (para el log nocturno)")
    a = ap.parse_args()
    arbol = a.arbol or detectar_arbol()
    buffer = []
    def log(s):
        if not a.silencioso:
            print(s)
        buffer.append(s)
    log(f"Parches de seguridad del núcleo de Hermes · árbol: {arbol}{' · solo comprobar' if a.comprobar else ''}")
    cuenta = {"aplicado": 0, "ya": 0, "saltado": 0, "error": 0}
    for p in PARCHES:
        cuenta[aplicar_uno(arbol, p, a.comprobar, a.sin_copia, log)] += 1
    linea = (f"RESULTADO aplicados={cuenta['aplicado']} ya={cuenta['ya']} "
             f"saltados={cuenta['saltado']} errores={cuenta['error']}")
    print(linea)
    sys.exit(1 if cuenta["error"] else 0)


if __name__ == "__main__":
    main()
