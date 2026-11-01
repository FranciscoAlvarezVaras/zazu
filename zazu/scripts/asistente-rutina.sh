#!/bin/bash
# Rutina de un asistente de un solo oficio: corre su Hermes (perfil $1) con la petición que sigue y escribe lo que diga.
# Lo que imprime lo guarda la rutina en ~/.hermes/cron/output y el hub lo enseña en el chat de ese asistente (pestaña Chats);
# además avisa al móvil con una notificación corta que abre ese chat. Sin WhatsApp: esto vive en la app.
# Uso: asistente-rutina.sh <perfil> "<petición>"       (NOMBRE="Comidas y compra" para el título del aviso)
# Si Hermes falla o tarda más de 15 minutos, la rutina termina con error (no se da por buena en silencio).
set -u -o pipefail
perfil="${1:?perfil}"; shift; peticion="$*"
errlog=$(mktemp); trap 'rm -f "$errlog"' EXIT
salida=$(printf '%s' "$peticion" | timeout 900 hermes -p "$perfil" chat --query-file - -Q --format text --source cron 2>"$errlog" | sed '/^\[SILENT\]$/d')
rc=$?
if [ "$rc" -ne 0 ]; then
  [ "$rc" -eq 124 ] && motivo="pasó de los 15 minutos" || motivo="código $rc"
  echo "La rutina de «$perfil» falló ($motivo). Última línea de Hermes: $(tail -n 1 "$errlog" | cut -c1-160)" >&2
  exit 1
fi
[ -z "${salida// }" ] && exit 0        # nada que decir (p. ej. [SILENT]): no es un fallo
printf '%s\n' "$salida"
vig="$HOME/hermes-hub/vigilante.py"; py="$HOME/hermes-hub/.venv/bin/python"; [ -x "$py" ] || py=python3
# El texto va por el entorno: con «python - <<heredoc» el heredoc ocupa la entrada estándar y no quedaría nada que leer (la notificación salía vacía).
[ -f "$vig" ] && RUTINA_TEXTO="$salida" "$py" - "$vig" "${NOMBRE:-$perfil}" "$perfil" <<'PY' >/dev/null 2>&1 || true
import json, os, subprocess, sys
vig, nombre, perfil = sys.argv[1:4]
texto = " ".join(os.environ.get("RUTINA_TEXTO", "").split())[:140]
cuerpo = json.dumps({"titulo": f"{nombre} te ha escrito", "cuerpo": texto, "url": f"/?tab=chat&contacto={perfil}", "tag": f"rutina-{perfil}"})
subprocess.run([sys.executable, vig, "--push-json"], input=cuerpo, text=True, timeout=60, capture_output=True)
PY
exit 0
