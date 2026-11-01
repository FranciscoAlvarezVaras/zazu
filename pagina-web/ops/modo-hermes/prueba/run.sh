#!/usr/bin/env bash
# Prueba completa del lado Hermes del Modo Hermes (§8.2 del plan) sobre una casa de Hermes SINTÉTICA:
# el gateway de Hermes de verdad (su código) + un LLM falso, en 127.0.0.1:18642 / :18978. Nunca toca ~/.hermes
# (solo copia de él el script del hook, para parchear la copia) y nunca manda mensajes ni gasta en modelos.
#
#  1. casa sintética: raíz con hook espía + movil-aprobacion.py (copia), perfiles escritor/investigador/charla como los
#     de verdad (sin hook ni permiso) y una invitada zitest; SUDO_PASSWORD falso en la raíz (nunca se ejecuta sudo);
#  2. ANTES: escritor por la CLI ejecuta un comando «sudo…» sin preguntar (riesgo 13);
#  3. instalar.sh: se niega con la casa de verdad, --comprobar no escribe, dos pasadas = mismo resultado;
#  4. DESPUÉS: escritor e investigador por la CLI → BLOCKED (el hook corre en su perfil);
#  5. gateway SIN --accept-hooks (como el de verdad): los permisos copiados bastan; client.py hace ok, aprobar, denegar,
#     parar, caduca, entorno, control, modelo, reanudar y sin_clave por /p/tecnico/v1/runs;
#  6. lo que vio el LLM falso: SOUL de tecnico, memoria por el enlace, sin la herramienta memory;
#  7. deshacer.sh y vuelta a instalar; parche que no encaja → no toca el hook.
# Para el gateway y el LLM falso al final, comprobando en /proc/<pid>/environ que son los de esta casa.
#
# Uso: prueba/run.sh [carpeta de trabajo]       Sale con 1 si algo falla. Resumen en <carpeta>/resumen.txt
set -uo pipefail

AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MH=$(dirname "$AQUI")
RUN=$(realpath -m -- "${1:-$(mktemp -d "${TMPDIR:-/tmp}/modo-hermes-prueba.XXXXXX")}")
H="$RUN/home"
PGW=18642
PLLM=18978
CASA_REAL=$(realpath -m -- "$(getent passwd "$(id -un)" | cut -d: -f6)/.hermes")
HOOK_REAL="$CASA_REAL/agent-hooks/movil-aprobacion.py"
HERMES=${HERMES_BIN:-$(command -v hermes)}
MATCHER="terminal|execute_code|write_file|patch|process_manage|cronjob_manage|skill_manage|send_message"
export PATH

case "$RUN/" in "$CASA_REAL/"*) echo "La carpeta de trabajo no puede estar dentro de $CASA_REAL" >&2; exit 2 ;; esac
for p in $PGW $PLLM; do
  if ss -ltnH "sport = :$p" | grep -q .; then echo "El puerto $p está ocupado: no arranco nada." >&2; exit 2; fi
done
mkdir -p "$RUN"
: > "$RUN/resumen.txt"
FALLOS=0
bien() { echo "OK    $*" | tee -a "$RUN/resumen.txt"; }
mal() { echo "FALLA $*" | tee -a "$RUN/resumen.txt"; FALLOS=$((FALLOS + 1)); }
cuenta() { if eval "$2"; then bien "$1"; else mal "$1"; fi; }
titulo() { printf '\n### %s\n' "$*" | tee -a "$RUN/resumen.txt"; }
# hermes en la casa de pruebas, sin variables de este entorno que puedan llevarlo a un proveedor de verdad
hp() { env -u HERMES_SINGLE_QUERY_SESSION -u ANTHROPIC_BASE_URL -u API_TIMEOUT_MS HERMES_HOME="$H" "$HERMES" "$@" </dev/null; }
huella_real() {   # sha256 de los ficheros de configuración de la casa de verdad (nunca su contenido)
  ( cd "$CASA_REAL" && for f in .env config.yaml shell-hooks-allowlist.json SOUL.md agent-hooks/movil-aprobacion.py \
      profiles/*/config.yaml profiles/*/.env profiles/*/SOUL.md profiles/*/shell-hooks-allowlist.json \
      profiles/*/shell-hooks-allowlist.json.lock; do [ -e "$f" ] && echo "$(sha256sum < "$f" | cut -c1-16) $(stat -c %a "$f") $f"; done
    ls -1 profiles agent-hooks backups ) 2>/dev/null
}
huella_todo() {   # TODO fichero de la casa de pruebas: ruta, tamaño, fecha y permisos (para ver que nada se escribe)
  ( cd "$H" && find . -printf '%p %s %T@ %m %l\n' | sort )
}
huella_config() { # los ficheros de los que se encarga instalar.sh (para ver que la 2.ª pasada no cambia ninguno)
  ( cd "$H" && for f in .env config.yaml shell-hooks-allowlist.json SOUL.md agent-hooks/* profiles/*/config.yaml profiles/*/.env \
      profiles/*/SOUL.md profiles/*/shell-hooks-allowlist.json; do [ -f "$f" ] && echo "$(sha256sum < "$f" | cut -c1-16) $(stat -c %a "$f") $f"; done
    find . -maxdepth 3 -type l -printf '%p -> %l\n' | sort )
}
mata_casa() {     # para todo proceso cuyo entorno diga HERMES_HOME=<esta casa> (y solo esos)
  local sig=$1 pid
  for e in /proc/[0-9]*/environ; do
    pid=${e#/proc/}; pid=${pid%/environ}
    [ "$pid" = "$$" ] && continue
    if { tr '\0' '\n' < "$e"; } 2>/dev/null | grep -qxF "HERMES_HOME=$H"; then kill "-$sig" "$pid" 2>/dev/null && echo "  $sig → $pid ($(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-80))"; fi
  done
}
LLMPID=""
limpiar() {
  titulo "Limpieza"
  local pid
  pid=$(ss -ltnpH "sport = :$PGW" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  if [ -n "$pid" ]; then
    if tr '\0' '\n' < "/proc/$pid/environ" | grep -qxF "HERMES_HOME=$H"; then echo "  gateway de pruebas en :$PGW = pid $pid (HERMES_HOME de esta casa)";
    else echo "  ¡:$PGW es de OTRA casa! No lo toco."; fi
  fi
  mata_casa TERM
  for _ in $(seq 1 30); do ss -ltnH "sport = :$PGW" | grep -q . || break; sleep 1; done
  mata_casa KILL
  if [ -n "$LLMPID" ] && tr '\0' ' ' < "/proc/$LLMPID/cmdline" 2>/dev/null | grep -q fake_llm.py; then kill "$LLMPID"; echo "  LLM falso parado ($LLMPID)"; fi
  sleep 1
  ss -ltnH "sport = :$PGW" | grep -q . && mal ":$PGW sigue abierto" || echo "  :$PGW cerrado"
  ss -ltnH "sport = :$PLLM" | grep -q . && mal ":$PLLM sigue abierto" || echo "  :$PLLM cerrado"
}
trap limpiar EXIT

huella_real > "$RUN/real-antes.txt"
echo "Carpeta de trabajo: $RUN"

# ---------------------------------------------------------------- 1. Casa sintética
titulo "1. Casa sintética"
mkdir -p "$H/memories" "$H/agent-hooks" "$H/backups"
cp -p "$HOOK_REAL" "$H/agent-hooks/movil-aprobacion.py"
cp -p "$HOOK_REAL" "$RUN/movil-aprobacion.original.py"
chmod 700 "$H/agent-hooks/movil-aprobacion.py"
PROVEEDORES='custom_providers:
  - name: fakea
    base_url: http://127.0.0.1:'"$PLLM"'/v1
    api_key: dummy
    api_mode: chat_completions
    models:
      fake-grande: {}
  - name: fakeb
    base_url: http://127.0.0.1:'"$PLLM"'/v1
    api_key: dummy
    api_mode: chat_completions
    models:
      fake-barato: {}'
COMUN='model:
  default: fake-grande
  provider: custom:fakea
  context_length: 200000
'"$PROVEEDORES"'
updates:
  check: false
telemetry:
  shared_metrics:
    enabled: false
    send: false
auth:
  adopt_external_logins: false
auxiliary:
  title_generation: {provider: custom:fakea, model: fake-grande}
  compression: {provider: custom:fakea, model: fake-grande}
  approval: {provider: custom:fakea, model: fake-grande}
  memory_query_rewrite: {provider: custom:fakea, model: fake-grande}
  vision: {provider: custom:fakea, model: fake-grande}'
cat > "$H/config.yaml" <<EOF
$COMUN
approvals:
  mode: manual
  timeout: 15
memory:
  memory_enabled: true
  user_profile_enabled: true
gateway:
  multiplex_profiles: true
platform_toolsets:
  api_server: [terminal]
  cli: [terminal, file, memory, session_search, skills, todo]
hooks:
  pre_tool_call:
    - command: "/usr/bin/python3 $AQUI/espia.py $RUN/espia.jsonl"
      timeout: 5
    - matcher: "$MATCHER"
      command: "/usr/bin/python3 $H/agent-hooks/movil-aprobacion.py"
      timeout: 5
      fail_closed: true
EOF
# .env raíz: puerto de PRUEBAS (nunca 8642) y un SUDO_PASSWORD falso (la prueba nunca ejecuta sudo de verdad)
printf 'API_SERVER_PORT=%s\nAPI_SERVER_HOST=127.0.0.1\nSUDO_PASSWORD=no-es-una-clave-de-verdad\n' "$PGW" > "$H/.env"
chmod 600 "$H/.env"
echo "ZAZU-SOUL-MARCADOR. Eres Zazu, el gato asistente de Fran." > "$H/SOUL.md"
echo "VERDE-MARCADOR: Fran tiene un servidor Geekom." > "$H/memories/MEMORY.md"
echo "Fran: habla de tú." > "$H/memories/USER.md"
/usr/bin/python3 - "$H" "$AQUI/espia.py" "$RUN/espia.jsonl" <<'PY'
import json, os, sys, datetime
h = sys.argv[1]
ahora = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
cmds = [f"/usr/bin/python3 {sys.argv[2]} {sys.argv[3]}", f"/usr/bin/python3 {h}/agent-hooks/movil-aprobacion.py"]
d = {"approvals": [{"approved_at": ahora, "command": c, "event": "pre_tool_call", "script_mtime_at_approval": ahora} for c in cmds]}
fd = os.open(os.path.join(h, "shell-hooks-allowlist.json"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, (json.dumps(d, indent=2) + "\n").encode()); os.close(fd)
PY
for n in escritor investigador charla zitest; do
  hp profile create "$n" --no-alias --no-skills > "$RUN/crear-$n.log" 2>&1 || mal "crear perfil $n (ver crear-$n.log)"
done
cat > "$H/profiles/escritor/config.yaml" <<EOF
$COMUN
approvals: {mode: manual, timeout: 15}
platform_toolsets:
  cli: [file, terminal, memory, session_search, skills]
  whatsapp: [hermes-whatsapp]
EOF
cat > "$H/profiles/investigador/config.yaml" <<EOF
$COMUN
approvals: {mode: manual, timeout: 15}
platform_toolsets:
  cli: [web, file, terminal, memory, session_search, skills]
  whatsapp: [hermes-whatsapp]
EOF
cat > "$H/profiles/charla/config.yaml" <<EOF
$COMUN
approvals: {mode: manual, timeout: 15}
platform_toolsets:
  cli: [memory, session_search]
  whatsapp: [hermes-whatsapp]
EOF
cat > "$H/profiles/zitest/config.yaml" <<EOF
$COMUN
platform_toolsets:
  cli: [clarify, web, memory, session_search, todo]
  whatsapp: [clarify, web, memory, session_search, todo]
agent:
  disabled_toolsets: [terminal, file, code_execution, browser, cronjob, delegation, skills, computer_use, homeassistant, kanban,
    image_gen, video_gen, tts, vision, connections, project, desktop_ui, setup, spotify, discord, discord_admin, x_search,
    video, moa, rl, messaging]
EOF
cuenta "casa sintética con 4 perfiles" '[ -d "$H/profiles/escritor" ] && [ -d "$H/profiles/zitest" ]'

python3 "$AQUI/fake_llm.py" $PLLM "$RUN/llm.jsonl" > "$RUN/llm.log" 2>&1 &
LLMPID=$!
for _ in $(seq 1 50); do curl -s -m 1 "http://127.0.0.1:$PLLM/v1/models" >/dev/null && break; sleep 0.2; done

ultimo_resultado() {   # resultado de herramienta que vio el LLM falso tras la petición cuyo usuario es $1
  python3 - "$RUN/llm.jsonl" "$1" <<'PY'
import json, sys
r = [json.loads(l) for l in open(sys.argv[1])]
v = [x["tool_result"] for x in r if x["user"] == sys.argv[2] and x["tool_result"]]
print(v[-1] if v else "SIN-RESULTADO")
PY
}
cli_permiso() {        # $1 perfil, $2 texto → resultado de la herramienta
  hp -p "$1" chat -q "$2" -Q --source hub > "$RUN/cli-$1-$(echo "$2" | tr ' ' _).log" 2>&1
  ultimo_resultado "$2"
}

# ---------------------------------------------------------------- 2. Antes: riesgo 13
titulo "2. Antes de instalar: escritor por la CLI"
r=$(cli_permiso escritor "USA_PERMISO antes")
cuenta "escritor ejecuta «echo prueba-permiso sudo-falso» SIN preguntar (riesgo 13 reproducido)" '[[ "$r" == *prueba-permiso* && "$r" != *BLOCKED* ]]'
cuenta "el hook no corrió en escritor" '! grep -q "\"profile\": \"escritor\"" "$RUN/espia.jsonl" 2>/dev/null'

# ---------------------------------------------------------------- 3. instalar.sh
titulo "3. instalar.sh"
for caso in "sin HERMES_HOME" "$CASA_REAL" "/home/servidor/.hermes" "$CASA_REAL/profiles/escritor" "$HOME/.hermes/"; do
  if [ "$caso" = "sin HERMES_HOME" ]; then env -u HERMES_HOME bash "$MH/instalar.sh" > "$RUN/rechazo.log" 2>&1; rc=$?
  else HERMES_HOME="$caso" bash "$MH/instalar.sh" > "$RUN/rechazo.log" 2>&1; rc=$?; fi
  cuenta "instalar.sh se niega ($caso) → rc=$rc" '[ $rc = 3 ]'
  if [ "$caso" = "sin HERMES_HOME" ]; then env -u HERMES_HOME bash "$MH/deshacer.sh" > "$RUN/rechazo.log" 2>&1; rc=$?
  else HERMES_HOME="$caso" bash "$MH/deshacer.sh" > "$RUN/rechazo.log" 2>&1; rc=$?; fi
  cuenta "deshacer.sh se niega ($caso) → rc=$rc" '[ $rc = 3 ]'
done
huella_todo > "$RUN/casa-0.txt"
HERMES_HOME="$H" bash "$MH/instalar.sh" --comprobar > "$RUN/instalar-comprobar.log" 2>&1; rc=$?
huella_todo > "$RUN/casa-0b.txt"
cuenta "--comprobar no escribe nada en la casa (rc=$rc)" '[ $rc = 0 ] && cmp -s "$RUN/casa-0.txt" "$RUN/casa-0b.txt" && ! ls "$H"/backups/modo-hermes-* >/dev/null 2>&1'
HERMES_HOME="$H" bash "$MH/instalar.sh" > "$RUN/instalar-1.log" 2>&1; rc=$?
cuenta "instalar.sh (1.ª pasada) rc=$rc" '[ $rc = 0 ]'
huella_config > "$RUN/casa-1.txt"
sleep 1
HERMES_HOME="$H" bash "$MH/instalar.sh" > "$RUN/instalar-2.log" 2>&1; rc=$?
huella_config > "$RUN/casa-2.txt"
cuenta "instalar.sh (2.ª pasada) rc=$rc y 0 cambios" '[ $rc = 0 ] && grep -q "0 cambio(s) hechos" "$RUN/instalar-2.log"'
cuenta "idempotente: la 2.ª pasada no cambia ni un fichero" 'cmp -s "$RUN/casa-1.txt" "$RUN/casa-2.txt"'
cuenta "copias de seguridad .tgz (600)" '[ "$(stat -c %a "$H"/backups/modo-hermes-*.tgz | sort -u)" = 600 ]'
P="$H/profiles/tecnico"
cuenta "perfil tecnico creado" '[ -f "$P/config.yaml" ]'
cuenta "SOUL.md de tecnico = ops/modo-hermes/SOUL.md" 'cmp -s "$MH/SOUL.md" "$P/SOUL.md"'
cuenta "memorias: enlace ../../memories" '[ "$(readlink "$P/memories")" = ../../memories ]'
cuenta "SUDO_PASSWORD se queda en tecnico (override 1)" 'grep -q "^SUDO_PASSWORD=" "$P/.env"'
cuenta "API_SERVER_KEY en raíz y tecnico, distintas, .env en 600" 'python3 - "$H/.env" "$P/.env" <<PY
import sys, os
v = [next((l.split("=",1)[1] for l in open(p) if l.startswith("API_SERVER_KEY=")), None) for p in sys.argv[1:]]
assert all(x and len(x) >= 32 for x in v) and v[0] != v[1]
assert all(oct(os.stat(p).st_mode)[-3:] == "600" for p in sys.argv[1:])
PY'
cuenta "herramientas api_server/cli de tecnico (sin memory/clarify/code_execution)" 'python3 - "$P/config.yaml" <<PY
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
q = ["connections","cronjob","file","session_search","skills","terminal","todo","vision","web"]
assert c["platform_toolsets"]["api_server"] == q and c["platform_toolsets"]["cli"] == q
PY'
for n in tecnico escritor investigador charla; do
  cuenta "$n: hooks.pre_tool_call = raíz y permiso copiado (override 2)" 'python3 - "$H" "$n" <<PY
import sys, yaml, json
h, n = sys.argv[1:]
r = yaml.safe_load(open(f"{h}/config.yaml"))["hooks"]["pre_tool_call"]
p = yaml.safe_load(open(f"{h}/profiles/{n}/config.yaml"))["hooks"]["pre_tool_call"]
a = json.load(open(f"{h}/profiles/{n}/shell-hooks-allowlist.json"))["approvals"]
assert r == p and all(any(e["command"] == x["command"] for e in a) for x in p)
PY'
done
cuenta "zitest (invitada): sin hook ni permiso, y avisado" '! grep -q "^hooks:" "$H/profiles/zitest/config.yaml" && [ ! -e "$H/profiles/zitest/shell-hooks-allowlist.json" ] && grep -q "zitest: invitada sin terminal" "$RUN/instalar-1.log"'
cp "$RUN/movil-aprobacion.original.py" "$RUN/esperado.py"; patch -s "$RUN/esperado.py" < "$MH/hook.patch"
cuenta "hook parcheado = original + hook.patch, con .bak y modo 700" 'cmp -s "$RUN/esperado.py" "$H/agent-hooks/movil-aprobacion.py" && ls "$H"/agent-hooks/movil-aprobacion.py.bak-* >/dev/null && [ "$(stat -c %a "$H/agent-hooks/movil-aprobacion.py")" = 700 ]'
cuenta "probar_hook.py (dentro de instalar): 0 fallos" 'grep -q " 0 fallos" "$H"/backups/modo-hermes-*-probar_hook.txt'
cuenta "hooks doctor de tecnico sin avisos (permiso renovado tras el parche)" 'grep -q "hooks doctor" "$RUN/instalar-1.log" && ! grep -q "modified since approval\|issue(s) found" "$RUN/instalar-1.log"'
for n in tecnico escritor investigador charla zitest; do
  hp -p "$n" hooks list > "$RUN/hooks-list-$n.txt" 2>&1
done
cuenta "hermes hooks list: tecnico/escritor/investigador/charla con el hook aprobado" 'for n in tecnico escritor investigador charla; do grep -q "movil-aprobacion.py" "$RUN/hooks-list-$n.txt" || exit 1; ! grep -qi "not allowlisted\|✗" "$RUN/hooks-list-$n.txt" || exit 1; done'
grep -i -A3 "movil-aprobacion" "$RUN/hooks-list-tecnico.txt" | head -8 | sed 's/^/    /'

# ---------------------------------------------------------------- 4. Después: CLI de los perfiles
titulo "4. Después de instalar: CLI de los perfiles"
r=$(cli_permiso escritor "USA_PERMISO despues")
cuenta "escritor: el mismo comando queda BLOCKED (el hook pide permiso; en -Q nadie puede darlo)" '[[ "$r" == *BLOCKED* ]]'
r=$(cli_permiso investigador "USA_PERMISO investigador")
cuenta "investigador: BLOCKED" '[[ "$r" == *BLOCKED* ]]'
cuenta "el hook espía vio escritor e investigador" 'grep -q "\"profile\": \"escritor\"" "$RUN/espia.jsonl" && grep -q "\"profile\": \"investigador\"" "$RUN/espia.jsonl"'

# ---------------------------------------------------------------- 5. Gateway de pruebas + client.py
titulo "5. Gateway de pruebas (sin --accept-hooks) y /p/tecnico/v1/runs"
if ! grep -qx "API_SERVER_PORT=$PGW" "$H/.env"; then mal "la casa de pruebas no fija API_SERVER_PORT=$PGW: no arranco el gateway"; exit 1; fi
# Solo en PRUEBAS: clave del api_server también en escritor/investigador/charla, para llamar a /p/<perfil>/ y ver que
# el hook corre en cada perfil dentro del gateway (en la casa de verdad no se les pone: HolaZazu solo usa tecnico).
for n in escritor investigador charla; do
  python3 - "$H/profiles/$n/.env" <<'PY'
import os, secrets, sys
p = sys.argv[1]; L = open(p).read().splitlines() if os.path.exists(p) else []
if not any(l.startswith("API_SERVER_KEY=") for l in L):
    L.append("API_SERVER_KEY=" + secrets.token_urlsafe(32))
fd = os.open(p + ".t", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.write(fd, ("\n".join(L) + "\n").encode()); os.close(fd)
os.replace(p + ".t", p)
PY
done
( cd "$RUN" && env -u HERMES_SINGLE_QUERY_SESSION -u ANTHROPIC_BASE_URL -u API_TIMEOUT_MS HERMES_HOME="$H" \
    timeout 1500 "$HERMES" gateway run -v > "$RUN/gw.log" 2>&1 < /dev/null ) &
arriba=0
for _ in $(seq 1 240); do curl -s -m 1 "http://127.0.0.1:$PGW/health" >/dev/null 2>&1 && { arriba=1; break; }; sleep 1; done
cuenta "gateway de pruebas responde en 127.0.0.1:$PGW/health" '[ $arriba = 1 ]'
sleep 3
cuenta "gateway: el hook de verdad se registra en los perfiles y ninguno queda «not allowlisted»" \
  '[ "$(grep -c "shell hook registered: pre_tool_call -> /usr/bin/python3 $H/agent-hooks/movil-aprobacion.py" "$RUN/gw.log")" -ge 4 ] && ! grep -q "not allowlisted" "$RUN/gw.log"'
grep -o "Another Hermes home's gateway owns this host[^(]*" "$RUN/gw.log" | head -1 | sed 's/^/    /'
python3 "$AQUI/client.py" "$H" ok aprobar denegar parar caduca entorno control modelo reanudar sin_clave \
  perfil:escritor perfil:investigador perfil:charla > "$RUN/client.out" 2>&1; rc=$?
grep -E "^(OK|FALLA) " "$RUN/client.out" | sed 's/^/    /'
cuenta "client.py: todos los escenarios (tecnico + el hook en escritor/investigador/charla dentro del gateway)" '[ $rc = 0 ]'

# ---------------------------------------------------------------- 6. Lo que vio el LLM falso, el espía y state.db
titulo "6. Prompt, herramientas, hook y state.db de tecnico"
python3 - "$RUN/llm.jsonl" "$RUN/espia.jsonl" "$P/state.db" > "$RUN/analisis.txt" 2>&1 <<'PY'
import json, sqlite3, sys
r = [json.loads(l) for l in open(sys.argv[1])]
t = [x for x in r if x["soul_tecnico"]]
herr = sorted({h for x in t for h in x["tools"]})
print("peticiones_tecnico", len(t))
print("soul_tecnico_sin_zazu", all(not x["soul_zazu"] for x in t))
print("memoria_por_enlace", all(x["memoria"] for x in t))
print("herramientas", " ".join(herr))
print("sin_memory_clarify_code", not ({"memory", "clarify", "execute_code"} & set(herr)) and "terminal" in herr)
print("system_head", json.dumps(t[0]["system_head"][:160] if t else "", ensure_ascii=False))
e = [json.loads(l) for l in open(sys.argv[2])]
print("espia_perfiles", " ".join(sorted({x["profile"] or "?" for x in e})))
db = sqlite3.connect(sys.argv[3])
print("sesiones_api_server", db.execute("select count(*) from sessions where source='api_server'").fetchone()[0])
try:
    print("modelos_usados", " ".join(sorted({m for (m,) in db.execute("select model from session_model_usage")})))
except Exception as ex:
    print("modelos_usados ?", type(ex).__name__)
PY
sed 's/^/    /' "$RUN/analisis.txt"
cuenta "el prompt de tecnico empieza por su SOUL y no lleva el de Zazu" 'grep -qx "soul_tecnico_sin_zazu True" "$RUN/analisis.txt" && ! grep -qx "peticiones_tecnico 0" "$RUN/analisis.txt"'
cuenta "la memoria compartida (MEMORY.md) llega al prompt por el enlace" 'grep -qx "memoria_por_enlace True" "$RUN/analisis.txt"'
cuenta "sin herramienta memory (ni clarify ni execute_code)" 'grep -qx "sin_memory_clarify_code True" "$RUN/analisis.txt"'
cuenta "el hook corrió en tecnico desde el gateway" 'grep -q "^espia_perfiles.*tecnico" "$RUN/analisis.txt"'
cuenta "las sesiones quedan en profiles/tecnico/state.db con source api_server" '! grep -qx "sesiones_api_server 0" "$RUN/analisis.txt"'
limpiar; trap - EXIT

# ---------------------------------------------------------------- 7. deshacer.sh y vuelta
titulo "7. deshacer.sh, reinstalar y parche que no encaja"
cp "$RUN/movil-aprobacion.original.py" "$RUN/esperado-a.py"; patch -s "$RUN/esperado-a.py" < "$MH/hook-a.patch"
HERMES_HOME="$H" bash "$MH/deshacer.sh" > "$RUN/deshacer-1.log" 2>&1; rc=$?
cuenta "deshacer.sh rc=$rc" '[ $rc = 0 ]'
cuenta "sin API_SERVER_KEY en raíz ni tecnico" '! grep -q "^API_SERVER_KEY=" "$H/.env" "$P/.env"'
cuenta "hook = original + parte (a), y los .env siguen en 600" 'cmp -s "$RUN/esperado-a.py" "$H/agent-hooks/movil-aprobacion.py" && [ "$(stat -c %a "$H/.env" "$P/.env" | sort -u)" = 600 ]'
cuenta "el perfil tecnico y el hook de los demás perfiles se quedan" '[ -f "$P/config.yaml" ] && grep -q movil-aprobacion "$H/profiles/escritor/config.yaml"'
HERMES_HOME="$H" bash "$MH/deshacer.sh" > "$RUN/deshacer-2.log" 2>&1; rc=$?
cuenta "deshacer.sh otra vez: no cambia nada (rc=$rc)" '[ $rc = 0 ] && grep -q "ya estaba deshecho" "$RUN/deshacer-2.log"'
HERMES_HOME="$H" bash "$MH/instalar.sh" > "$RUN/instalar-3.log" 2>&1; rc=$?
cuenta "reinstalar tras deshacer: hook completo y claves nuevas (rc=$rc)" '[ $rc = 0 ] && cmp -s "$RUN/esperado.py" "$H/agent-hooks/movil-aprobacion.py" && grep -q "^API_SERVER_KEY=" "$P/.env"'
cp -a "$H" "$RUN/home-distinto"
python3 - "$RUN/home-distinto/agent-hooks/movil-aprobacion.py" <<'PY'
import sys   # alguien cambió a mano justo una línea que toca el parche
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
assert "(profiles/[^/]+/)?" in s
open(p, "w", encoding="utf-8").write(s.replace("(profiles/[^/]+/)?", "(profiles/[^/]+/|perfiles/[^/]+/)?", 1))
PY
cp -p "$RUN/home-distinto/agent-hooks/movil-aprobacion.py" "$RUN/distinto-antes.py"
HERMES_HOME="$RUN/home-distinto" bash "$MH/deshacer.sh" > "$RUN/deshacer-distinto.log" 2>&1; rc=$?
cuenta "deshacer con un hook que ya no encaja: no lo toca (rc=$rc)" '[ $rc = 6 ] && cmp -s "$RUN/distinto-antes.py" "$RUN/home-distinto/agent-hooks/movil-aprobacion.py"'
HERMES_HOME="$RUN/home-distinto" bash "$MH/instalar.sh" > "$RUN/instalar-distinto.log" 2>&1; rc=$?
cuenta "instalar con un hook que ya no encaja: no lo toca (rc=$rc)" '[ $rc = 6 ] && cmp -s "$RUN/distinto-antes.py" "$RUN/home-distinto/agent-hooks/movil-aprobacion.py"'

# ---------------------------------------------------------------- 8. La casa de verdad
titulo "8. ~/.hermes de verdad"
huella_real > "$RUN/real-despues.txt"
cuenta "~/.hermes sin cambios (sha256 de .env, config.yaml, permisos, hook y perfiles; listados de perfiles y backups)" 'cmp -s "$RUN/real-antes.txt" "$RUN/real-despues.txt"'

printf '\n%s fallo(s). Detalle en %s\n' "$FALLOS" "$RUN" | tee -a "$RUN/resumen.txt"
[ "$FALLOS" = 0 ]
