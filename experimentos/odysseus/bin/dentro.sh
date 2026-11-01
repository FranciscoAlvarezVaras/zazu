#!/bin/bash
# Se ejecuta DENTRO de la jaula: levanta los puentes (entrada de tu navegador y salida a Ollama/Hermes) y luego Odysseus.
RAIZ=/home/server/Odysseus
if [ "${ODYSSEUS_RED:-cerrada}" = "cerrada" ]; then
  pares=("unix:$RAIZ/run/in7011.sock>tcp:7011")
  for p in ${ODYSSEUS_PUENTES//,/ }; do pares+=("tcp:$p>unix:$RAIZ/run/p$p.sock"); done
  /usr/bin/python3 "$RAIZ/bin/puente.py" "${pares[@]}" &
  sleep 0.5
fi
exec "$RAIZ/venv/bin/python" -m uvicorn app:app --host 127.0.0.1 --port 7011 --log-level info
