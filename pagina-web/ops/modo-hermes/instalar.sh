#!/usr/bin/env bash
# Modo Hermes de HolaZazu: prepara el lado de Hermes. Idempotente: se puede repetir; lo que ya está, no se toca.
#
#   1. copia de seguridad (.env, config.yaml, permisos de hooks, agent-hooks y los config/.env/permisos de cada perfil);
#   2. perfil «tecnico» (clon de default sin canales de mensajería) con su SOUL.md, memorias compartidas en solo
#      lectura (enlace a ../../memories y sin la herramienta memory) y herramientas fijas para api_server y cli;
#   3. SUDO_PASSWORD se queda en tecnico (Fran: «sudo con permiso»: funciona tras aprobarlo en la app);
#   4. API_SERVER_KEY en ~/.hermes/.env (abre 127.0.0.1:8642) y otra distinta en profiles/tecnico/.env (/p/tecnico/);
#   5. el hook de aprobaciones (hooks.pre_tool_call + su permiso en shell-hooks-allowlist.json) en CADA perfil que no
#      sea de invitada (tecnico, charla, escritor, investigador…). Los perfiles zi* (invitadas) solo se revisan: si
#      tienen desactivadas terminal/archivos/código/rutinas/habilidades/mensajería no necesitan hook;
#   6. parche del hook movil-aprobacion.py (hook.patch, con .bak-<fecha> antes) y su prueba de regresión (probar_hook.py);
#      hook-a.patch es solo la parte (a), la que deja deshacer.sh. Tras el parche, el permiso del hook se renueva con la
#      fecha del script nuevo (si no, «hermes hooks doctor» avisa de «script modified since approval»).
# No reinicia nada: los hooks de los perfiles y el puerto 8642 solo se activan al reiniciar hermes-gateway.
#
# Uso:   HERMES_HOME=<casa de pruebas> ops/modo-hermes/instalar.sh
#        ops/modo-hermes/instalar.sh --real          (tu ~/.hermes de verdad: solo con el OK de Fran)
#        ops/modo-hermes/instalar.sh --comprobar     (solo lee y cuenta qué haría; vale también sin --real)
# Nunca imprime claves ni valores del .env.
#
# Mantenimiento: el config.yaml de tecnico es una COPIA. Si cambias en la raíz «hooks:», «approvals» o
# «command_allowlist», cópialo a tecnico (hermes -p tecnico config set …) y vuelve a pasar este script: él ya
# re-copia el bloque hooks.pre_tool_call y el permiso del hook a todos los perfiles que no son de invitada.
set -euo pipefail
umask 077

AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PERFIL=tecnico
REAL=0
COMPROBAR=0
for a in "$@"; do
  case "$a" in
    --real) REAL=1 ;;
    --comprobar) COMPROBAR=1 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "opción desconocida: $a" >&2; exit 2 ;;
  esac
done

HH=$(realpath -m -- "${HERMES_HOME:-$HOME/.hermes}")
# La casa de Hermes de verdad, venga de $HOME o de /etc/passwd (por si alguien cambia HOME para probar)
CASA_PASSWD=$(getent passwd "$(id -un)" | cut -d: -f6)
es_real=0
for r in "$HOME/.hermes" "$CASA_PASSWD/.hermes"; do
  r=$(realpath -m -- "$r")
  if [ "$HH" = "$r" ]; then
    es_real=1
  else
    case "$HH/" in "$r/"*)
      echo "HERMES_HOME apunta DENTRO de tu Hermes de verdad ($HH): tiene que ser la raíz. No hago nada." >&2
      exit 3 ;;
    esac
  fi
done
if [ "$es_real" = 1 ] && [ "$REAL" = 0 ] && [ "$COMPROBAR" = 0 ]; then
  echo "Esto es tu Hermes de verdad ($HH). No toco nada sin --real (y sin el OK de Fran)." >&2
  echo "Para ver qué haría sin cambiar nada: $0 --comprobar" >&2
  exit 3
fi
case "$(basename "$(dirname "$HH")")" in profiles)
  echo "HERMES_HOME es un perfil ($HH): tiene que ser la raíz de Hermes. No hago nada." >&2; exit 3 ;;
esac
[ -f "$HH/config.yaml" ] || { echo "No hay config.yaml en $HH: no parece una casa de Hermes." >&2; exit 3; }

PY=/usr/bin/python3
"$PY" -c 'import yaml' 2>/dev/null || { echo "Falta python3 con PyYAML ($PY)." >&2; exit 4; }
command -v patch >/dev/null || { echo "Falta el programa patch." >&2; exit 4; }
HERMES=${HERMES_BIN:-$(command -v hermes || true)}
[ "$COMPROBAR" = 1 ] || [ -x "$HERMES" ] || { echo "No encuentro el comando hermes." >&2; exit 4; }
export HERMES_HOME="$HH"
P="$HH/profiles/$PERFIL"
FECHA=$(date +%Y%m%d-%H%M%S)
HOOK="$HH/agent-hooks/movil-aprobacion.py"
CAMBIOS=0

paso() { printf '\n== %s\n' "$*"; }
ok() { printf '  ✓ %s\n' "$*"; }
aviso() { printf '  ! %s\n' "$*"; }
# hace "texto" orden…  → en --comprobar solo lo cuenta; si no, lo hace
hace() {
  local t=$1; shift
  CAMBIOS=$((CAMBIOS + 1))
  if [ "$COMPROBAR" = 1 ]; then printf '  · haría: %s\n' "$t"; else printf '  → %s\n' "$t"; "$@"; fi
}
hermes_p() { "$HERMES" -p "$1" "${@:2}" </dev/null; }
silencio() { "$@" >/dev/null; }

# Ayudante en Python (solo lee y escribe ficheros de $HH; nunca imprime valores de claves)
read -r -d '' AYUDA <<'PY' || true
import fcntl, json, os, secrets, sys, yaml
from contextlib import contextmanager

VIGILADAS = {"terminal", "file", "code_execution", "cronjob", "skills", "messaging"}   # toolsets de las herramientas del matcher

def cargar(p):
    try:
        return yaml.safe_load(open(p, encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}

def obtener(d, clave):
    for k in clave.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d

def canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)

@contextmanager
def candado(ruta, de_verdad=True):
    if not de_verdad:          # solo mirar: ni siquiera crear el .lock
        yield
        return
    with open(ruta + ".lock", "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

def escribir(ruta, texto):
    t = ruta + ".modo-hermes.tmp"
    fd = os.open(t, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto); f.flush(); os.fsync(f.fileno())
    os.replace(t, ruta)

def lineas_env(p):
    return open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []

def valor_env(L, k):
    for l in L:
        if l.startswith(k + "="):
            return l.split("=", 1)[1].strip().strip("'\"")
    return None

cmd, *a = sys.argv[1:]
if cmd == "get":                      # get <yaml> <clave.punteada> -> JSON canónico
    print(canon(obtener(cargar(a[0]), a[1])))
elif cmd == "hooks-raiz":             # el bloque hooks.pre_tool_call de la raíz, en JSON
    v = obtener(cargar(os.path.join(a[0], "config.yaml")), "hooks.pre_tool_call")
    if not isinstance(v, list) or not v:
        sys.exit(1)
    print(json.dumps(v, ensure_ascii=False))
elif cmd == "perfiles":               # nombre y tipo de cada perfil
    raiz = os.path.join(a[0], "profiles")
    for n in sorted(os.listdir(raiz)) if os.path.isdir(raiz) else []:
        if n.startswith(".") or not os.path.isfile(os.path.join(raiz, n, "config.yaml")):
            continue
        print(n, "invitado" if n.startswith("zi") else "normal")
elif cmd == "invitado":               # ¿la invitada puede llegar a alguna herramienta vigilada?
    c = cargar(a[0])
    off = set(obtener(c, "agent.disabled_toolsets") or [])
    falta = sorted(VIGILADAS - off)
    pt = obtener(c, "platform_toolsets") or {}
    en_listas = sorted({t for v in pt.values() if isinstance(v, list) for t in v if t in VIGILADAS or t.startswith("hermes-")} - off)
    print("ok" if not falta else "desactivadas: " + ",".join(sorted(off & VIGILADAS)) + " · NO desactivadas: " + ",".join(falta)
          + (" · en sus listas: " + ",".join(en_listas) if en_listas else ""))
elif cmd == "allowlist":              # allowlist <HH> <perfil_dir> <ver|poner>: copia el permiso de los hooks de la raíz
    hh, pd, modo = a
    hooks = obtener(cargar(os.path.join(hh, "config.yaml")), "hooks.pre_tool_call") or []
    raiz = json.load(open(os.path.join(hh, "shell-hooks-allowlist.json"))) if os.path.exists(os.path.join(hh, "shell-hooks-allowlist.json")) else {}
    ent_raiz = [e for e in raiz.get("approvals", []) if isinstance(e, dict)]
    destino = os.path.join(pd, "shell-hooks-allowlist.json")
    with candado(destino, modo == "poner"):
        try:
            d = json.load(open(destino, encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            d = {}
        if not isinstance(d, dict) or not isinstance(d.get("approvals"), list):
            d = {"approvals": []}
        nuevas, sin_permiso = [], []
        for h in hooks:
            c = (h or {}).get("command")
            if not c:
                continue
            if any(e.get("event") == "pre_tool_call" and e.get("command") == c for e in d["approvals"] if isinstance(e, dict)):
                continue
            e = next((e for e in ent_raiz if e.get("event") == "pre_tool_call" and e.get("command") == c), None)
            (nuevas if e else sin_permiso).append(e or c)
        if sin_permiso:
            print("SIN-PERMISO-EN-RAIZ"); sys.exit(5)
        if nuevas and modo == "poner":
            d["approvals"] += nuevas
            escribir(destino, json.dumps(d, indent=2, sort_keys=True) + "\n")
        print(len(nuevas))
elif cmd == "sudo":                   # sudo <HH> <P> <ver|poner>: SUDO_PASSWORD de la raíz en tecnico si le falta
    hh, pd, modo = a
    r, p = os.path.join(hh, ".env"), os.path.join(pd, ".env")
    if valor_env(lineas_env(p), "SUDO_PASSWORD") is not None:
        print("esta"); sys.exit(0)
    linea = next((l for l in lineas_env(r) if l.startswith("SUDO_PASSWORD=")), None)
    if linea is None:
        print("no-en-raiz"); sys.exit(0)
    if modo == "poner":
        with candado(p):
            L = lineas_env(p)
            if valor_env(L, "SUDO_PASSWORD") is None:
                escribir(p, "\n".join(L + [linea]) + "\n")
    print("copiar")
elif cmd == "claves":                 # claves <HH> <P> <ver|poner>: API_SERVER_KEY en raíz y tecnico (distintas)
    hh, pd, modo = a
    r, p = os.path.join(hh, ".env"), os.path.join(pd, ".env")
    hechos = []
    for ruta, nombre in ((r, "raiz"), (p, "tecnico")):
        with candado(ruta, modo == "poner"):
            L = lineas_env(ruta)
            v = valor_env(L, "API_SERVER_KEY")
            otra = valor_env(lineas_env(r), "API_SERVER_KEY") if nombre == "tecnico" else None
            if v and len(v) >= 16 and v != otra:
                continue
            hechos.append(nombre if not v else nombre + "(" + ("igual-que-raiz" if v == otra else "corta") + ")")
            if modo == "poner":
                L = [l for l in L if not l.startswith("API_SERVER_KEY=")] + ["API_SERVER_KEY=" + secrets.token_urlsafe(32)]
                escribir(ruta, "\n".join(L) + "\n")
    print(" ".join(hechos) or "-")
elif cmd == "renovar":               # renovar <HH> <script>: tras cambiar el hook, su permiso apunta a la fecha nueva
    import datetime                   # (si no, «hermes hooks doctor» avisa de «script modified since approval»)
    hh, script = a
    iso = lambda t: datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    mtime, ahora = iso(os.path.getmtime(script)), iso(__import__("time").time())
    casas = [hh] + [os.path.join(hh, "profiles", n) for n in sorted(os.listdir(os.path.join(hh, "profiles")))
                    if not n.startswith(("zi", ".")) and os.path.isdir(os.path.join(hh, "profiles", n))] if os.path.isdir(os.path.join(hh, "profiles")) else [hh]
    n = 0
    for c in casas:
        f = os.path.join(c, "shell-hooks-allowlist.json")
        if not os.path.exists(f):
            continue
        with candado(f):
            d = json.load(open(f, encoding="utf-8-sig"))
            cambia = False
            for e in d.get("approvals", []):
                if isinstance(e, dict) and e.get("event") == "pre_tool_call" and script in str(e.get("command", "")).split() \
                        and e.get("script_mtime_at_approval") != mtime:
                    e["script_mtime_at_approval"], e["approved_at"] = mtime, ahora
                    cambia = True
            if cambia:
                escribir(f, json.dumps(d, indent=2, sort_keys=True) + "\n"); n += 1
    print(n)
elif cmd == "comprobar-hooks":        # comprobar-hooks <HH> <perfil_dir>: hooks iguales a la raíz y con permiso
    hh, pd = a
    raiz = obtener(cargar(os.path.join(hh, "config.yaml")), "hooks.pre_tool_call")
    suyo = obtener(cargar(os.path.join(pd, "config.yaml")), "hooks.pre_tool_call")
    try:
        al = json.load(open(os.path.join(pd, "shell-hooks-allowlist.json"))).get("approvals", [])
    except Exception:
        al = []
    cmds = [h.get("command") for h in (suyo or []) if isinstance(h, dict)]
    falta = [c for c in cmds if not any(isinstance(e, dict) and e.get("event") == "pre_tool_call" and e.get("command") == c for e in al)]
    print("ok" if canon(raiz) == canon(suyo) and cmds and not falta else
          ("hooks distintos de la raíz" if canon(raiz) != canon(suyo) else "sin permiso: " + ", ".join(falta)))
elif cmd == "deny-difiere":           # deny-difiere <HH> <perfil_dir>: avisa si approvals.deny o command_allowlist != raíz
    hh, pd = a                        # (los perfiles deben negar lo mismo que root; enviar a otro se aprueba, no se bloquea)
    r, p = cargar(os.path.join(hh, "config.yaml")), cargar(os.path.join(pd, "config.yaml"))
    difs = [clave for clave in ("approvals.deny", "command_allowlist")
            if canon(obtener(r, clave) or []) != canon(obtener(p, clave) or [])]
    print("ok" if not difs else "difiere de root en: " + ", ".join(difs))
PY
ayuda() { "$PY" -c "$AYUDA" "$@"; }

echo "Modo Hermes · casa de Hermes: $HH$([ "$es_real" = 1 ] && echo ' (LA DE VERDAD)')$([ "$COMPROBAR" = 1 ] && echo ' · solo comprobar')"

# --- 0. Lo que necesita la raíz
paso "Comprobaciones"
HOOKS_RAIZ=$(ayuda hooks-raiz "$HH") || { echo "La raíz no tiene hooks.pre_tool_call: no hay hook que copiar a los perfiles." >&2; exit 5; }
ok "hook de la raíz: $(printf '%s' "$HOOKS_RAIZ" | "$PY" -c 'import json,sys; print("; ".join(h.get("matcher","*")+" → "+h.get("command","") for h in json.load(sys.stdin)))')"
[ -d "$HH/memories" ] || { echo "Falta $HH/memories." >&2; exit 5; }

# --- 1. Copia de seguridad
paso "Copia de seguridad"
if [ "$COMPROBAR" = 1 ]; then
  printf '  · haría: %s\n' "$HH/backups/modo-hermes-<fecha>.tgz (raíz + perfiles)"
else
  mkdir -p "$HH/backups"
  lista=()
  for f in .env config.yaml shell-hooks-allowlist.json SOUL.md agent-hooks; do [ -e "$HH/$f" ] && lista+=("$f"); done
  for d in "$HH"/profiles/*/; do
    [ -d "$d" ] || continue
    n=$(basename "$d")
    for f in config.yaml .env shell-hooks-allowlist.json SOUL.md; do [ -e "$d$f" ] && lista+=("profiles/$n/$f"); done
  done
  tar czf "$HH/backups/modo-hermes-$FECHA.tgz" -C "$HH" "${lista[@]}"
  chmod 600 "$HH/backups/modo-hermes-$FECHA.tgz"
  ok "$HH/backups/modo-hermes-$FECHA.tgz (${#lista[@]} ficheros/carpetas)"
fi

# --- 2. Perfil tecnico
paso "Perfil $PERFIL"
NUEVO=0
if [ -f "$P/config.yaml" ]; then
  ok "ya existe"
else
  NUEVO=1
  hace "crear el perfil $PERFIL (clon de default, sin canales de mensajería)" \
    "$HERMES" profile create "$PERFIL" --clone-from default --no-alias \
      --description "Hermes sin la persona de Zazu: técnico y directo (Modo Hermes de HolaZazu)" </dev/null
fi
EXISTE=1; [ -f "$P/config.yaml" ] || EXISTE=0

if [ "$EXISTE" = 1 ]; then
  # SOUL.md
  if cmp -s "$AQUI/SOUL.md" "$P/SOUL.md"; then ok "SOUL.md al día"; else hace "SOUL.md de Modo Hermes" install -m 644 "$AQUI/SOUL.md" "$P/SOUL.md"; fi
  # Memorias compartidas (solo lectura: tecnico no tiene la herramienta memory)
  if [ -L "$P/memories" ] && [ "$(readlink "$P/memories")" = "../../memories" ]; then
    ok "memorias: enlace a ../../memories"
  else
    if [ -e "$P/memories" ] || [ -L "$P/memories" ]; then
      hace "apartar sus memorias propias a backups/" mv "$P/memories" "$HH/backups/modo-hermes-$FECHA-$PERFIL-memories"
    fi
    hace "memorias: enlace a ../../memories" ln -s ../../memories "$P/memories"
  fi
  # Herramientas (sin clarify, memory ni code_execution)
  HERR='["connections","cronjob","file","session_search","skills","terminal","todo","vision","web"]'
  HERR_C=$(printf '%s' "$HERR" | "$PY" -c 'import json,sys; print(json.dumps(json.load(sys.stdin), sort_keys=True, ensure_ascii=False))')
  for plat in api_server cli; do
    if [ "$(ayuda get "$P/config.yaml" "platform_toolsets.$plat")" = "$HERR_C" ]; then
      ok "herramientas de $plat al día"
    else
      hace "herramientas de $plat" hermes_p "$PERFIL" config set "platform_toolsets.$plat" "$HERR" --force
    fi
  done
  # SUDO_PASSWORD: se queda (decisión de Fran). Si el clon no lo trajo, se copia de la raíz.
  s=$(ayuda sudo "$HH" "$P" ver)
  case "$s" in
    esta) ok "SUDO_PASSWORD presente en $PERFIL (sudo funciona tras aprobarlo en la app)" ;;
    no-en-raiz) aviso "no hay SUDO_PASSWORD ni en la raíz ni en $PERFIL: sudo fallará aunque lo apruebes" ;;
    copiar) hace "copiar SUDO_PASSWORD de la raíz a $PERFIL (sin enseñarlo)" silencio ayuda sudo "$HH" "$P" poner ;;
  esac
  # La API_SERVER_KEY de tecnico se escribe DESPUÉS del hook (paso 3): si se pusiera aquí, un gateway ya en marcha
  # serviría /p/tecnico/ con la clave nueva durante unos segundos ANTES de que el hook esté registrado en el perfil
  # (riesgo 5 de la revisión). Ver el bloque «Claves del api_server» tras el paso 3.
else
  printf '  · haría también: SOUL.md, enlace de memorias, herramientas, SUDO_PASSWORD y API_SERVER_KEY (esta última tras el hook)\n'
fi

# --- 3. Hook en todos los perfiles que no son de invitada (riesgo 13 del plan)
paso "Hook de aprobaciones en los perfiles"
while read -r n tipo <&3; do
  [ -n "${n:-}" ] || continue
  d="$HH/profiles/$n"
  if [ "$tipo" = invitado ]; then
    r=$(ayuda invitado "$d/config.yaml")
    if [ "$r" = ok ]; then ok "$n: invitada sin terminal/archivos/código/rutinas/habilidades/mensajería → no necesita hook"
    else aviso "$n: invitada con herramientas vigiladas ($r). NO le pongo el hook (pediría permiso en SU chat): revísalo con Fran"; fi
    continue
  fi
  if [ "$(ayuda get "$d/config.yaml" hooks.pre_tool_call)" = "$(ayuda get "$HH/config.yaml" hooks.pre_tool_call)" ]; then
    ok "$n: hooks.pre_tool_call igual que la raíz"
  else
    hace "$n: copiar hooks.pre_tool_call de la raíz" silencio hermes_p "$n" config set hooks.pre_tool_call "$HOOKS_RAIZ" --force
  fi
  falta=$(ayuda allowlist "$HH" "$d" ver) || { echo "El hook de la raíz no está aprobado en $HH/shell-hooks-allowlist.json: apruébalo antes (hermes hooks list)." >&2; exit 5; }
  if [ "$falta" = 0 ]; then ok "$n: permiso del hook en su shell-hooks-allowlist.json"
  else hace "$n: copiar el permiso del hook ($falta) a su shell-hooks-allowlist.json" silencio ayuda allowlist "$HH" "$d" poner; fi
done 3< <(ayuda perfiles "$HH")
[ -f "$P/config.yaml" ] || printf '  · haría también: hook y permiso en %s al crearlo\n' "$PERFIL"

# --- 3b. Claves del api_server (DESPUÉS del hook: riesgo 5). Solo ahora, con el hook ya registrado en tecnico,
#         se le da la clave que abre /p/tecnico/ en el gateway.
paso "Claves del api_server (tras el hook)"
if [ -f "$P/config.yaml" ]; then
  s=$(ayuda claves "$HH" "$P" ver)
  if [ "$s" = "-" ]; then ok "API_SERVER_KEY en la raíz y en $PERFIL (distintas)"; else hace "API_SERVER_KEY nueva en: $s" silencio ayuda claves "$HH" "$P" poner; fi
else
  printf '  · haría también: API_SERVER_KEY de la raíz y de %s (tras el hook)\n' "$PERFIL"
fi

# --- 4. Parche del hook
paso "Parche de movil-aprobacion.py"
estado_hook() {   # completo | original | solo-a | distinto
  if patch -s -f -F0 -R --dry-run "$1" < "$AQUI/hook.patch" >/dev/null 2>&1; then echo completo
  elif patch -s -f -F0 --dry-run "$1" < "$AQUI/hook.patch" >/dev/null 2>&1; then echo original
  elif patch -s -f -F0 -R --dry-run "$1" < "$AQUI/hook-a.patch" >/dev/null 2>&1; then echo solo-a
  else echo distinto; fi
}
parchear() {      # sobre una copia: (quitar la parte a si hace falta) + hook.patch; comprueba y reemplaza
  local t
  t=$(mktemp "$HH/agent-hooks/.movil-aprobacion.XXXXXX")
  cp -p "$HOOK" "$t"
  [ "$1" = solo-a ] && patch -s -f -F0 -R --no-backup-if-mismatch "$t" < "$AQUI/hook-a.patch" >/dev/null
  patch -s -f -F0 --no-backup-if-mismatch "$t" < "$AQUI/hook.patch" >/dev/null
  "$PY" -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$t"
  chmod --reference="$HOOK" "$t"
  cp -p "$HOOK" "$HOOK.bak-$FECHA"
  mv -f "$t" "$HOOK"
}
if [ ! -f "$HOOK" ]; then
  aviso "no hay $HOOK: sin parche (el hook de los perfiles apuntará a lo que diga la raíz)"
else
  e=$(estado_hook "$HOOK")
  case "$e" in
    completo) ok "ya parcheado" ;;
    original|solo-a) hace "parchear (copia en movil-aprobacion.py.bak-$FECHA)" parchear "$e" ;;
    distinto) echo "El hook ha cambiado desde que se preparó hook.patch: revísalo con Claude Code. No lo toco." >&2; exit 6 ;;
  esac
  if [ "$COMPROBAR" = 0 ] && [ "$e" != completo ]; then
    viejo=$(mktemp "$HH/agent-hooks/.viejo.XXXXXX")
    cp -p "$HOOK.bak-$FECHA" "$viejo"      # el hook sin el parche (si venía de deshacer.sh, también sin la parte a)
    [ "$e" = solo-a ] && patch -s -f -F0 -R --no-backup-if-mismatch "$viejo" < "$AQUI/hook-a.patch" >/dev/null
    if ! "$PY" "$AQUI/probar_hook.py" --viejo "$viejo" --nuevo "$HOOK" > "$HH/backups/modo-hermes-$FECHA-probar_hook.txt" 2>&1; then
      rm -f "$viejo"; cp -p "$HOOK.bak-$FECHA" "$HOOK"
      echo "La prueba de regresión del hook falló: lo he dejado como estaba (ver $HH/backups/modo-hermes-$FECHA-probar_hook.txt)." >&2
      exit 6
    fi
    rm -f "$viejo"
    ok "prueba de regresión: $(tail -1 "$HH/backups/modo-hermes-$FECHA-probar_hook.txt")"
    ok "permiso del hook renovado con la fecha del script nuevo en $(ayuda renovar "$HH" "$HOOK") shell-hooks-allowlist.json"
  fi
fi

# --- 5. Verificación
paso "Verificación"
mal=0
while read -r n tipo <&3; do
  [ -n "${n:-}" ] && [ "$tipo" = normal ] || continue
  r=$(ayuda comprobar-hooks "$HH" "$HH/profiles/$n")
  if [ "$r" = ok ]; then ok "$n: hook y permiso"; else aviso "$n: $r"; mal=1; fi
  # Aviso (no error) si el perfil niega cosas distintas a root: enviar a otra persona debe pedir aprobación, no
  # bloquearse en seco (política de Fran). No lo cambia solo; se arregla con «hermes -p <p> config set approvals.deny …».
  d=$(ayuda deny-difiere "$HH" "$HH/profiles/$n")
  [ "$d" = ok ] || aviso "$n: $d — alinéalo con root (hermes -p $n config set approvals.deny …)"
done 3< <(ayuda perfiles "$HH")
if [ "$COMPROBAR" = 0 ] && [ -f "$P/config.yaml" ]; then
  echo "  hermes -p $PERFIL hooks list:"
  hermes_p "$PERFIL" hooks list 2>&1 | sed 's/^/    /'
  echo "  hermes -p $PERFIL hooks doctor:"
  hermes_p "$PERFIL" hooks doctor 2>&1 | sed 's/^/    /' || true
fi

paso "Resumen"
if [ "$COMPROBAR" = 1 ]; then
  echo "  $CAMBIOS cambio(s) pendiente(s). No he tocado nada."
  [ "$mal" = 0 ] || echo "  (los avisos de la verificación son lo que falta por hacer)"
else
  echo "  $CAMBIOS cambio(s) hechos."
  [ "$mal" = 0 ] || { echo "  Hay perfiles sin hook: revisa los avisos." >&2; exit 7; }
  if [ "$CAMBIOS" -gt 0 ]; then
    echo "  Falta (con el OK de Fran, en un rato tranquilo): systemctl --user restart hermes-gateway"
    echo "  Después: ss -ltn | grep 127.0.0.1:8642 ; curl -s 127.0.0.1:8642/health"
  fi
fi
