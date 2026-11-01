#!/usr/bin/env bash
# Comprueba (sin escribir nada) si los parches de seguridad del núcleo de Hermes están aplicados.
# Es el modo solo-lectura de aplicar.py. Sale 0 si no hay errores.
exec /usr/bin/python3 "$(dirname "$0")/aplicar.py" --comprobar "$@"
