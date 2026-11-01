#!/usr/bin/env bash
# Actualiza Hermes cada noche si hay versión nueva y lo apunta en el cerebro (Obsidian).
# Lo lanza hermes-actualizar.timer. Antes de actualizar, Hermes hace su copia rápida de estado.
# Si el gateway no vuelve a arrancar, el vigilante de HolaZazu avisa a Fran.
set -u
H=/home/server/.hermes/hermes-agent/.hermes/bin/hermes
REPO=/home/server/.hermes/hermes-agent
NOTA="/home/server/Cerebro/60 Servidor/hermes-actualizaciones.md"
cuando=$(date '+%Y-%m-%d %H:%M')

if [ ! -f "$NOTA" ]; then
  printf -- '---\ntitle: Actualizaciones de Hermes\ntags: [servidor]\n---\nVolver al [[Inicio]]\n\nCada noche a las 04:30 se comprueba si hay versión nueva de Hermes y se instala sola.\nLo más nuevo, arriba.\n\n' > "$NOTA"
fi
apuntar() {   # inserta la línea debajo de la cabecera (lo más nuevo arriba)
  python3 - "$NOTA" "$1" <<'EOF'
import sys
p, linea = sys.argv[1], sys.argv[2]
t = open(p).read()
marca = "Lo más nuevo, arriba.\n\n"
open(p, "w").write(t.replace(marca, marca + linea + "\n", 1) if marca in t else t + linea + "\n")
EOF
}

antes=$(git -C "$REPO" rev-parse --short HEAD)
comprobar=$("$H" update --check 2>&1)
if ! grep -q "Update available" <<<"$comprobar"; then
  echo "Hermes al día ($antes)"
  exit 0
fi
pendientes=$(grep -o '[0-9]* commits behind' <<<"$comprobar" | cut -d' ' -f1)

# ── Red de seguridad (2026-10-11): copia de lo que una actualización puede romper, antes de tocar nada ──
COPIA="/home/server/Respaldos/hermes-antes-update-$(date +%Y%m%d-%H%M)"
mkdir -p "$COPIA/profiles"
for f in state.db config.yaml shell-hooks-allowlist.json cron/jobs.json; do cp -a "/home/server/.hermes/$f" "$COPIA/" 2>/dev/null || true; done
for d in /home/server/.hermes/profiles/*/; do n=$(basename "$d"); mkdir -p "$COPIA/profiles/$n"; cp -a "$d/state.db" "$d/config.yaml" "$d/shell-hooks-allowlist.json" "$COPIA/profiles/$n/" 2>/dev/null || true; done
echo "$antes" > "$COPIA/VERSION-ANTES"
ls -dt /home/server/Respaldos/hermes-antes-update-* 2>/dev/null | tail -n +6 | xargs -r rm -rf   # se guardan las 5 últimas

avisar() {   # tarjeta y push en la app (sin IA), por si el gateway no vuelve
  printf '{"titulo":"Hermes: actualización con problemas","cuerpo":%s,"url":"/?tab=inicio","tag":"hermes-update"}' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")" \
    | /home/server/hermes-hub/.venv/bin/python /home/server/hermes-hub/vigilante.py --push-json >/dev/null 2>&1 || true
}
prueba_rapida() {   # 0 si todo responde: gateway (90 s), hooks sanos, rutinas legibles
  for i in $(seq 1 45); do curl -s -m 2 -o /dev/null http://127.0.0.1:8642/health && break; sleep 2; done
  curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8642/health | grep -q 200 || return 1
  "$H" hooks doctor 2>&1 | grep -q "look healthy" || return 2
  "$H" cron list >/dev/null 2>&1 || return 3
  return 0
}

if "$H" update --yes >/tmp/hermes-update-$$.log 2>&1; then
  despues=$(git -C "$REPO" rev-parse --short HEAD)
  # Re-aplicar los parches de seguridad del núcleo: «hermes update» sobreescribe los ficheros parcheados (bridge.js
  # y el supervisor de MCP dejarían de nuevo las claves en su entorno). El parcheador es idempotente y, si el
  # upstream cambió, se salta el parche sin corromper nada. Si aplica algo, hace falta reiniciar para recogerlo.
  PARCHE=/home/server/hermes-hub/ops/parches-hermes/aplicar.py
  if [ -f "$PARCHE" ]; then
    parches=$(/usr/bin/python3 "$PARCHE" --silencioso 2>&1 | tail -1)
    if echo "$parches" | grep -qE 'aplicados=[1-9]'; then
      systemctl --user restart hermes-gateway   # recoger los parches recién re-aplicados
    fi
    parches=" · ${parches#RESULTADO }"
  else
    parches=" · parches núcleo: falta $PARCHE (sin aplicar)"
  fi
  sleep 20
  if prueba_rapida; then
    apuntar "- $cuando · ✅ Actualizado $antes → $despues (${pendientes:-?} cambios). Gateway, hooks y rutinas responden. Copia previa: $COPIA.${parches}"
  else
    fallo=$?
    apuntar "- $cuando · 🔴 Actualizado $antes → $despues, pero la prueba rápida falla (código $fallo: 1 gateway, 2 hooks, 3 rutinas). Copia previa en $COPIA. Pídele a Claude volver a $antes.${parches}"
    avisar "Tras actualizar Hermes ($antes → $despues) falla la prueba rápida (código $fallo). Copia previa en $COPIA. Pídele a Claude que lo revise."
  fi
else
  apuntar "- $cuando · 🔴 Falló la actualización (sigue en $antes). Últimas líneas: $(tail -n 2 /tmp/hermes-update-$$.log | tr '\n' ' ' | cut -c1-200)"
  avisar "La actualización de Hermes de esta noche falló; sigue en la versión $antes y todo funciona como antes."
  rm -f /tmp/hermes-update-$$.log
  exit 1
fi
rm -f /tmp/hermes-update-$$.log
