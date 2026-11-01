#!/usr/bin/env bash
# Deshace el Modo Hermes en el lado de Hermes (marcha atrás del plan, §9):
#   - quita API_SERVER_KEY de ~/.hermes/.env y de profiles/tecnico/.env (escritura atómica, 600): al reiniciar
#     hermes-gateway se cierra 127.0.0.1:8642 y HolaZazu muestra «Modo Hermes no está activado»;
#   - devuelve el hook movil-aprobacion.py a como estaba antes de instalar.sh (lo mismo que su último .bak), pero
#     conservando la parte (a) del parche (la configuración de los perfiles cuenta como configuración: es un arreglo).
#     Se hace quitando hook.patch y poniendo hook-a.patch, así no se pierde ningún otro cambio que Fran hiciera después;
#     si no encaja, no toca nada y dice qué .bak copiar a mano.
# Deja el perfil tecnico (sin clave no sirve para nada; borrarlo lo decide Fran) y deja el hook en los demás perfiles
# (eso arregla un agujero que ya existía). No reinicia nada.
#
# Uso:   HERMES_HOME=<casa de pruebas> ops/modo-hermes/deshacer.sh
#        ops/modo-hermes/deshacer.sh --real       (tu ~/.hermes de verdad: solo con el OK de Fran)
set -euo pipefail
umask 077

AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PERFIL=tecnico
REAL=0
for a in "$@"; do
  case "$a" in
    --real) REAL=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "opción desconocida: $a" >&2; exit 2 ;;
  esac
done

HH=$(realpath -m -- "${HERMES_HOME:-$HOME/.hermes}")
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
if [ "$es_real" = 1 ] && [ "$REAL" = 0 ]; then
  echo "Esto es tu Hermes de verdad ($HH). No toco nada sin --real (y sin el OK de Fran)." >&2
  exit 3
fi
[ -f "$HH/config.yaml" ] || { echo "No hay config.yaml en $HH: no parece una casa de Hermes." >&2; exit 3; }
PY=/usr/bin/python3
P="$HH/profiles/$PERFIL"
HOOK="$HH/agent-hooks/movil-aprobacion.py"
FECHA=$(date +%Y%m%d-%H%M%S)

echo "Deshacer Modo Hermes · casa de Hermes: $HH$([ "$es_real" = 1 ] && echo ' (LA DE VERDAD)')"
mkdir -p "$HH/backups"
lista=()
for f in .env "profiles/$PERFIL/.env" agent-hooks; do [ -e "$HH/$f" ] && lista+=("$f"); done
tar czf "$HH/backups/modo-hermes-deshacer-$FECHA.tgz" -C "$HH" "${lista[@]}"
chmod 600 "$HH/backups/modo-hermes-deshacer-$FECHA.tgz"
echo "  ✓ copia: $HH/backups/modo-hermes-deshacer-$FECHA.tgz"

# 1. Claves del api_server (nunca se imprimen)
"$PY" - "$HH/.env" "$P/.env" <<'PY'
import fcntl, os, sys
for p in sys.argv[1:]:
    if not os.path.exists(p):
        continue
    with open(p + ".lock", "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        L = open(p, encoding="utf-8").read().splitlines()
        M = [l for l in L if not l.startswith("API_SERVER_KEY=")]
        if M != L:
            t = p + ".modo-hermes.tmp"
            fd = os.open(t, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(M) + "\n"); f.flush(); os.fsync(f.fileno())
            os.replace(t, p)
            print(f"  → API_SERVER_KEY quitada de {p}")
        else:
            print(f"  ✓ sin API_SERVER_KEY en {p}")
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
PY

# 2. Hook: quitar (b) y (c), dejar (a)
if [ ! -f "$HOOK" ]; then
  echo "  ! no hay $HOOK"
elif patch -s -f -F0 -R --dry-run "$HOOK" < "$AQUI/hook.patch" >/dev/null 2>&1; then
  t=$(mktemp "$HH/agent-hooks/.movil-aprobacion.XXXXXX")
  viejo=$(mktemp "$HH/agent-hooks/.viejo.XXXXXX")
  cp -p "$HOOK" "$t"
  patch -s -f -F0 -R --no-backup-if-mismatch "$t" < "$AQUI/hook.patch" >/dev/null
  cp -p "$t" "$viejo"                                   # el hook de antes del Modo Hermes
  patch -s -f -F0 --no-backup-if-mismatch "$t" < "$AQUI/hook-a.patch" >/dev/null
  "$PY" -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$t"
  if ! "$PY" "$AQUI/probar_hook.py" --viejo "$viejo" --nuevo "$t" --solo-a > "$HH/backups/modo-hermes-deshacer-$FECHA-probar_hook.txt" 2>&1; then
    rm -f "$t" "$viejo"
    echo "La prueba del hook deshecho falló (ver $HH/backups/modo-hermes-deshacer-$FECHA-probar_hook.txt). No lo toco." >&2
    exit 6
  fi
  chmod --reference="$HOOK" "$t"
  cp -p "$HOOK" "$HOOK.deshecho-$FECHA"
  mv -f "$t" "$HOOK"
  rm -f "$viejo"
  "$PY" - "$HH" "$HOOK" <<'PY'
import datetime, fcntl, json, os, sys, time
hh, script = sys.argv[1:]   # el permiso del hook apunta a la fecha del script nuevo (si no, «hooks doctor» avisa)
iso = lambda t: datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
mtime, ahora = iso(os.path.getmtime(script)), iso(time.time())
pr = os.path.join(hh, "profiles")
for c in [hh] + ([os.path.join(pr, n) for n in sorted(os.listdir(pr)) if not n.startswith(("zi", "."))] if os.path.isdir(pr) else []):
    f = os.path.join(c, "shell-hooks-allowlist.json")
    if not os.path.isfile(f):
        continue
    with open(f + ".lock", "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        d = json.load(open(f, encoding="utf-8-sig"))
        es = [e for e in d.get("approvals", []) if isinstance(e, dict) and e.get("event") == "pre_tool_call"
              and script in str(e.get("command", "")).split() and e.get("script_mtime_at_approval") != mtime]
        for e in es:
            e["script_mtime_at_approval"], e["approved_at"] = mtime, ahora
        if es:
            t = f + ".modo-hermes.tmp"
            fd = os.open(t, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as o:
                o.write(json.dumps(d, indent=2, sort_keys=True) + "\n")
            os.replace(t, f)
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
PY
  echo "  → hook sin el bloqueo del control de HolaZazu ni los avisos «Hermes»; se queda el arreglo de los perfiles"
  echo "    (antes: movil-aprobacion.py.deshecho-$FECHA · prueba: $(tail -1 "$HH/backups/modo-hermes-deshacer-$FECHA-probar_hook.txt"))"
elif patch -s -f -F0 -R --dry-run "$HOOK" < "$AQUI/hook-a.patch" >/dev/null 2>&1; then
  echo "  ✓ el hook ya estaba deshecho (solo con el arreglo de los perfiles)"
elif patch -s -f -F0 --dry-run "$HOOK" < "$AQUI/hook.patch" >/dev/null 2>&1; then
  echo "  ✓ el hook no tiene el parche del Modo Hermes: no lo toco"
else
  echo "  ! el hook ha cambiado y el parche no encaja: no lo toco. Para volver a una copia anterior:" >&2
  ls -1t "$HOOK".bak-* 2>/dev/null | head -3 | sed 's/^/      cp -p /; s/$/ movil-aprobacion.py/' >&2
  exit 6
fi

echo
echo "Falta (con el OK de Fran): systemctl --user restart hermes-gateway"
echo "El perfil $PERFIL se queda (sin clave no se puede usar). Para borrarlo: hermes profile delete $PERFIL"
