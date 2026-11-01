#!/home/server/voz/venv/bin/python
"""stt.py ENTRADA SALIDA.txt [idioma] -> transcribe con faster-whisper (CPU, int8)."""
import sys
from faster_whisper import WhisperModel
src, dst = sys.argv[1], sys.argv[2]
lang = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "es"
# ponytail: modelo se recarga en cada audio (~2 s); si molesta, dejarlo residente en un servicio
m = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
segs, _ = m.transcribe(src, language=lang, vad_filter=True)
open(dst, "w").write(" ".join(s.text.strip() for s in segs))
