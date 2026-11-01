#!/home/server/voz/venv/bin/python
"""Servicio de dictado de Zazu: Whisper (faster-whisper, CPU) ya cargado en memoria, para que dictar no espere a arrancar el modelo.

Solo escucha en 127.0.0.1:8794 (lo llama el Hub, nadie más). El audio no sale de casa y no se guarda: se descodifica desde memoria.
  POST /calentar        carga el modelo en segundo plano (el Hub lo pide en cuanto empiezas a grabar, así está listo al parar)
  POST /transcribir     cuerpo = el audio tal cual (webm, ogg, mp4, wav…) → {"texto", "audio_s", "proceso_s", "modelo"}
  GET  /salud           {"cargado", "modelo", "libre_en_s"}
El modelo se descarga de la memoria tras IDLE_S sin uso (el servidor va justo de RAM) y vuelve a cargarse en 1-2 s.
Variables: ZAZU_STT_MODELO (small), ZAZU_STT_PUERTO (8794), ZAZU_STT_FALSO=1 (pruebas: sin modelo, devuelve el tamaño del audio).
Por qué «small» y no «large-v3-turbo»: en esta CPU el grande tarda más que lo que dura el audio (6 s de voz = 8 s); el pequeño, con el vocabulario
de ayuda (`PISTA`), acierta nombres como «Zazu» y tarda unos 3 s. El texto va al cuadro para revisarlo antes de enviar."""
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = int(os.environ.get("ZAZU_STT_PUERTO", "8794"))
MODELO = os.environ.get("ZAZU_STT_MODELO", "small")
FALSO = os.environ.get("ZAZU_STT_FALSO") == "1"
IDLE_S = float(os.environ.get("ZAZU_STT_IDLE_S", "900"))
MAX_BYTES = 15 * 1024 ** 2
PISTA = "Conversación en español con Zazu, el asistente de Fran, en holazazu.app. Hermes, Claude, agenda, tareas, WhatsApp, Mi nube."

_modelo = None
_ultimo_uso = 0.0
_cerrojo_carga = threading.Lock()
_cerrojo_uso = threading.Lock()   # Whisper en CPU: de uno en uno


def cargar():
    """Devuelve el modelo, cargándolo si hace falta (a la vez solo una carga)."""
    global _modelo, _ultimo_uso
    with _cerrojo_carga:
        if _modelo is None:
            if FALSO:
                _modelo = "falso"
            else:
                from faster_whisper import WhisperModel
                _modelo = WhisperModel(MODELO, device="cpu", compute_type="int8", cpu_threads=8)
        _ultimo_uso = time.time()
        return _modelo


def transcribir(audio):
    t0 = time.time()
    m = cargar()
    if FALSO:
        return {"texto": f"[{len(audio)} bytes]", "audio_s": 0.0, "proceso_s": round(time.time() - t0, 2), "modelo": "falso"}
    with _cerrojo_uso:
        segs, info = m.transcribe(io.BytesIO(audio), language="es", vad_filter=True, beam_size=1, condition_on_previous_text=False, initial_prompt=PISTA)
        texto = " ".join(s.text.strip() for s in segs).strip()
    global _ultimo_uso
    _ultimo_uso = time.time()
    return {"texto": texto, "audio_s": round(info.duration, 1), "proceso_s": round(time.time() - t0, 2), "modelo": MODELO}


def vigilar_reposo():
    """Libera la memoria del modelo cuando nadie dicta."""
    global _modelo
    while True:
        time.sleep(30)
        with _cerrojo_carga:
            if _modelo is not None and time.time() - _ultimo_uso > IDLE_S and not _cerrojo_uso.locked():
                _modelo = None
                import gc
                gc.collect()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):   # sin registro de peticiones: nada de lo dictado queda en el diario
        pass

    def responder(self, datos, codigo=200):
        b = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/salud":
            return self.responder({"cargado": _modelo is not None, "modelo": "falso" if FALSO else MODELO,
                                   "libre_en_s": max(0, round(IDLE_S - (time.time() - _ultimo_uso))) if _modelo is not None else None})
        self.responder({"error": "no existe"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if self.path == "/calentar":
            if n:
                self.rfile.read(min(n, MAX_BYTES))
            threading.Thread(target=cargar, daemon=True).start()
            return self.responder({"ok": True})
        if self.path == "/transcribir":
            if n <= 0 or n > MAX_BYTES:
                return self.responder({"error": "tamaño de audio no válido"}, 413 if n > 0 else 400)
            audio = self.rfile.read(n)
            if len(audio) != n:
                return self.responder({"error": "audio incompleto"}, 400)
            try:
                return self.responder(transcribir(audio))
            except Exception as e:   # un audio roto no tumba el servicio
                return self.responder({"error": f"{type(e).__name__}"}, 422)
        self.responder({"error": "no existe"}, 404)


if __name__ == "__main__":
    threading.Thread(target=vigilar_reposo, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), H)
    srv.daemon_threads = True
    print(f"Dictado de Zazu en 127.0.0.1:{PUERTO} (modelo {'falso' if FALSO else MODELO}, se descarga tras {int(IDLE_S)} s sin uso)", flush=True)
    srv.serve_forever()
