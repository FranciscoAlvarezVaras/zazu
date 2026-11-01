#!/bin/bash
# tts-kokoro.sh TEXTO.txt SALIDA.wav -> Kokoro, voz española ef_dora (cámbiala con KOKORO_VOZ=em_alex)
# Misma interfaz que tts.sh (Piper). Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0
D=/home/server/Escritorio/Spirit/voz
exec "$D/kokoro-venv/bin/python" "$D/tts_kokoro.py" "$1" "$2"
