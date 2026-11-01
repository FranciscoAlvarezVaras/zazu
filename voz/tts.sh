#!/bin/bash
# tts.sh TEXTO.txt SALIDA.wav -> Piper, voz es_MX claude (alta calidad)
exec /home/server/voz/venv/bin/python -m piper -m /home/server/voz/voces/es_MX-claude-high.onnx -f "$2" < "$1"
