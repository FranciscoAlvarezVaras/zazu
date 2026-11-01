#!/bin/sh
# Guarda la llave (token) de Odysseus para Hermes en ~/Odysseus/.token-hermes (permisos 600), sin mostrarla en pantalla.
set -eu
F="$HOME/Odysseus/.token-hermes"
printf 'Pega aquí la llave que has copiado de Odysseus y pulsa Enter (no se verá): '
stty -echo 2>/dev/null || true
IFS= read -r T
stty echo 2>/dev/null || true
printf '\n'
[ -n "$T" ] || { echo "No has pegado nada. No se ha guardado."; exit 1; }
umask 077
printf '%s' "$T" > "$F"
chmod 600 "$F"
echo "Guardada en $F. Ya puedes decirle a Hermes que use Odysseus."
