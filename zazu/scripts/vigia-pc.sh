#!/usr/bin/env bash
# vigia-pc — vigila el PC-servidor y SOLO imprime algo si hay un problema (o si se resolvió).
# Lo lanza aviso-pc.timer (cada 15 min, sin IA) a través de aviso-pc.sh: lo que imprime llega como aviso a la app y al PC.
# Si no imprime nada, no se avisa de nada. Uso manual: vigia-pc [--prueba]
set -uo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

ESTADO_DIR="${VIGIA_ESTADO_DIR:-$HOME/.local/state/vigia-pc}"
ESTADO="$ESTADO_DIR/estado.json"
mkdir -p "$ESTADO_DIR"
problemas=()
ahora=$(date +%s)

# 1) Copia diaria: última ejecución correcta hace menos de 30 h, y sin fallos en la última.
LOGR="$HOME/Respaldos/respaldo.log"
ult_ok=$(grep -a "fin · fallos=0" "$LOGR" 2>/dev/null | tail -1 | sed -E 's/^=== ([^ ]+) .*/\1/')
ult_fin=$(grep -a "fin · fallos=" "$LOGR" 2>/dev/null | tail -1)
if [ -z "$ult_ok" ]; then
  problemas+=("copia|No hay ninguna copia de seguridad correcta registrada.")
else
  edad=$(( (ahora - $(date -d "$ult_ok" +%s)) / 3600 ))
  [ "$edad" -ge 30 ] && problemas+=("copia|La última copia correcta fue hace ${edad} h.")
fi
case "$ult_fin" in *"fallos=0"*|"") ;; *) problemas+=("copia-fallos|La última copia terminó con fallos (ver ~/Respaldos/respaldo.log).") ;; esac

# 2) Disco.
uso=$(df --output=pcent / | tail -1 | tr -dc '0-9')
[ "${uso:-0}" -ge 90 ] && problemas+=("disco|El disco está al ${uso} %.")

# 3) Servicios (solo los que estén habilitados). hermes-gateway no se mira a propósito:
#    esta rutina corre dentro del gateway, así que si está caído este aviso no llegaría.
for s in hermes-hub hermes-dashboard cloudflared-zazu wacli-sync kdeconnectd; do
  if systemctl --user is-enabled --quiet "$s" 2>/dev/null && ! systemctl --user is-active --quiet "$s"; then
    problemas+=("servicio-$s|El servicio $s está caído.")
  fi
done
systemctl is-enabled --quiet ollama 2>/dev/null && ! systemctl is-active --quiet ollama && problemas+=("servicio-ollama|El servicio ollama está caído.")


# 5) Copia externa (solo si su temporizador está activado): correcta en los últimos 8 días.
if systemctl --user is-enabled --quiet respaldo-externo.timer 2>/dev/null; then
  LOGE="$HOME/Respaldos/respaldo-externo.log"
  ult_ext=$(grep -a -E "^=== .* fin$" "$LOGE" 2>/dev/null | tail -1 | sed -E 's/^=== ([^ ]+) .*/\1/')
  if [ -z "$ult_ext" ] || [ $(( (ahora - $(date -d "$ult_ext" +%s)) / 86400 )) -ge 8 ]; then
    problemas+=("externa|La copia externa en Drive no se completa desde hace más de 8 días.")
  fi
fi

[ "${1:-}" = "--prueba" ] && problemas+=("prueba|Esto es una prueba de la alerta (ignórala).")

# Comparar con el estado anterior y decidir qué decir.
VIGIA_PROBLEMAS="$(printf '%s\n' "${problemas[@]:-}")" python3 - "$ESTADO" "$ahora" "${1:-}" <<'PY'
import json, os, sys
path, ahora, modo = sys.argv[1], int(sys.argv[2]), sys.argv[3]
actual = {}
for line in os.environ.get("VIGIA_PROBLEMAS", "").splitlines():
    if "|" in line:
        k, msg = line.split("|", 1)
        actual[k] = msg
try:
    prev = json.load(open(path))
except Exception:
    prev = {"problemas": {}, "avisado": 0}
antes = prev.get("problemas", {})
nuevos = [k for k in actual if k not in antes]
resueltos = [k for k in antes if k not in actual]
salida = []
if actual and (nuevos or ahora - prev.get("avisado", 0) >= 6 * 3600):
    cab = "⚠️ *Problemas en tu PC*" if nuevos else "⚠️ *Siguen los problemas en tu PC*"
    salida.append(cab)
    salida += [f"- {m}" for m in actual.values()]
    prev["avisado"] = ahora
if resueltos:
    salida.append("✅ *Resuelto:* " + "; ".join(antes[k] for k in resueltos))
if modo != "--prueba":
    prev["problemas"] = actual
    json.dump(prev, open(path, "w"))
if salida:
    print("\n".join(salida))
PY
exit 0
