#!/bin/sh
# aviso-pc — corre vigia-pc.sh y, si dice algo (copia que falla, disco lleno, servicio caído o «resuelto»),
# lo manda como notificación a la app de Fran (push) y al escritorio. Sin IA y sin WhatsApp. Lo lanza aviso-pc.timer.
texto=$("$HOME/Spirit/zazu/scripts/vigia-pc.sh" "$@")
[ -z "$texto" ] && exit 0
printf '%s' "$texto" | python3 -c 'import json,sys; t=sys.stdin.read().replace("*",""); print(json.dumps({"titulo":"Tu PC","cuerpo":t,"tag":"zazu-pc","urgente":"⚠️" in t}))' \
  | "$HOME/hermes-hub/.venv/bin/python" "$HOME/hermes-hub/vigilante.py" --push-json
notify-send -a HolaZazu "Tu PC" "$texto" 2>/dev/null || true
