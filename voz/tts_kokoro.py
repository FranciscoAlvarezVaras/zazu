"""Texto a voz con Kokoro (voces en español). Uso: tts_kokoro.py TEXTO.txt SALIDA.wav

Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0:
la letra inicial de la voz es el idioma («e» = español, p. ej. ef_dora, em_alex).
El modelo (hexgrad/Kokoro-82M) lo baja el paquete `kokoro` de Hugging Face la primera vez.
"""
import os
import sys

import numpy as np
import soundfile as sf
from kokoro import KPipeline

VOZ = os.environ.get("KOKORO_VOZ", "ef_dora")  # ef_dora (mujer), em_alex / em_santa (hombre)

texto = open(sys.argv[1], encoding="utf-8").read().strip()
pipe = KPipeline(lang_code=VOZ[0], repo_id="hexgrad/Kokoro-82M")
trozos = [audio for _, _, audio in pipe(texto, voice=VOZ, speed=1.0)]
sf.write(sys.argv[2], np.concatenate(trozos) if trozos else np.zeros(2400), 24000)
