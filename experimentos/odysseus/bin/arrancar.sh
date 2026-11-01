#!/bin/bash
# Arranca Odysseus DENTRO de una jaula (bubblewrap): solo ve /usr (lectura), un HOME vacío y la carpeta
# ~/Odysseus. No ve ~/.hermes, ~/Cerebro, ~/.config, ~/.ssh ni nada del resto de la casa.
# ODYSSEUS_RED (en odysseus.env):
#   cerrada (por defecto)  la jaula NO tiene red; solo salen los puertos de ODYSSEUS_PUENTES (p. ej. Ollama 11434)
#   abierta                comparte la red del PC (internet y todos los servicios locales). Solo para pruebas.
set -euo pipefail
RAIZ=/home/server/Odysseus
args=(); RED=cerrada; PUENTES=""
while IFS= read -r l; do
  case "$l" in ''|'#'*) continue;; esac
  k="${l%%=*}"; v="${l#*=}"
  [ "$k" = ODYSSEUS_RED ] && RED="$v"
  [ "$k" = ODYSSEUS_PUENTES ] && PUENTES="$v"
  args+=(--setenv "$k" "$v")
done < "$RAIZ/odysseus.env"
red=()
if [ "$RED" = "cerrada" ]; then
  red=(--unshare-net)
  # Puentes del lado del PC: tu navegador (127.0.0.1:7011) -> jaula, y cada puerto permitido -> su servicio
  pares=("tcp:7011>unix:$RAIZ/run/in7011.sock")
  for p in ${PUENTES//,/ }; do pares+=("unix:$RAIZ/run/p$p.sock>tcp:$p"); done
  /usr/bin/python3 "$RAIZ/bin/puente.py" "${pares[@]}" &
  sleep 0.5
fi
exec /usr/bin/bwrap \
  --die-with-parent --new-session --cap-drop ALL \
  --unshare-pid --unshare-ipc --unshare-uts "${red[@]}" \
  --clearenv --setenv PATH /usr/bin:/bin --setenv LANG C.UTF-8 --setenv TZ Europe/Madrid \
  --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/sbin /sbin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --ro-bind /etc/ssl /etc/ssl --ro-bind /etc/ca-certificates /etc/ca-certificates \
  --ro-bind /etc/resolv.conf /etc/resolv.conf --ro-bind /etc/hosts /etc/hosts \
  --ro-bind /etc/nsswitch.conf /etc/nsswitch.conf --ro-bind /etc/localtime /etc/localtime \
  --ro-bind /etc/passwd /etc/passwd --ro-bind /etc/group /etc/group \
  --proc /proc --dev /dev --tmpfs /tmp \
  --tmpfs /home/server \
  --bind "$RAIZ" "$RAIZ" \
  --ro-bind "$RAIZ/venv" "$RAIZ/venv" \
  --ro-bind "$RAIZ/bin" "$RAIZ/bin" \
  --ro-bind /dev/null "$RAIZ/.admin" \
  --chdir "$RAIZ/src" \
  "${args[@]}" \
  "$RAIZ/bin/dentro.sh"
