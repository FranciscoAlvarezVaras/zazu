#!/usr/bin/env bash
# Rutina «Revisión de Zazu» (21:45, sin herramientas: enabled_toolsets []): solo lo nuevo desde la última pasada y como mucho
# 5 puntos (lo que no cabe sale al día siguiente). Sin novedades ni AVISOS sin contar en el último día → {"wakeAgent": false}
# (no despierta a la IA ni manda nada).
exec /usr/bin/python3 "$(dirname "$0")/revisar-zazu.py" --rutina
