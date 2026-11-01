#!/usr/bin/env python3
"""LLM falso compatible con OpenAI (chat/completions, con y sin stream) para probar el Modo Hermes sin gastar nada.

Uso: fake_llm.py <puerto> <registro.jsonl>
Responde según una palabra clave del último mensaje del usuario:
  USA_TERMINAL → terminal «echo hola-prueba»                       (el hook no pregunta)
  USA_PERMISO  → terminal «echo prueba-permiso sudo-falso»         (el hook pide permiso: «sudo»; no ejecuta sudo de verdad)
  USA_CONTROL  → terminal «curl … 127.0.0.1:18642/p/tecnico/v1/runs» (el hook lo bloquea: control del gateway)
  USA_ENV      → terminal que cuenta API_SERVER_KEY/SUDO_PASS* en su entorno e imprime solo NOMBRES de variables
  otra cosa    → texto «OK modelo=<modelo>»
Tras un resultado de herramienta responde «RESULTADO_TOOL: <resultado>».
Cada petición se apunta en el registro (sin el system prompt entero: solo marcas y sus primeros 300 caracteres).
"""
import json, os, sys, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[2]
COMANDOS = {
    "USA_TERMINAL": "echo hola-prueba",
    "USA_PERMISO": "echo prueba-permiso sudo-falso",
    "USA_CONTROL": "curl -s -m 2 http://127.0.0.1:18642/p/tecnico/v1/runs",
    "USA_ENV": "echo KEYS=$(env | grep -c API_SERVER_KEY) SUDOPW=$(env | grep -c '^SUDO_PASS'); "
               "env | grep -E '^(HERMES|API_)' | cut -d= -f1 | sort | tr '\\n' ' '",
}


def texto(c):
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)


def respuesta(body):
    msgs = body.get("messages") or []
    last = msgs[-1] if msgs else {}
    tools = [t.get("function", {}).get("name") for t in body.get("tools") or []]
    if last.get("role") == "tool":
        return {"text": "RESULTADO_TOOL: " + texto(last.get("content"))[:600]}
    contenido = texto(last.get("content"))
    for clave, cmd in COMANDOS.items():
        if clave in contenido and "terminal" in tools:
            return {"tool": ("terminal", {"command": cmd})}
    return {"text": f"OK modelo={body.get('model')}"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._json({"object": "list", "data": [
                {"id": m, "object": "model", "owned_by": "fake", "context_length": 200000}
                for m in ("fake-grande", "fake-barato")]})
        self._json({"error": "nf"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages") or []
        sysmsg = texto(next((m.get("content") for m in msgs if m.get("role") == "system"), ""))
        ultimo_user = next((texto(m.get("content")) for m in reversed(msgs) if m.get("role") == "user"), "")
        ultimo_tool = next((texto(m.get("content")) for m in reversed(msgs) if m.get("role") == "tool"), None)
        r = respuesta(body)
        with open(LOG, "a") as f:
            f.write(json.dumps({
                "t": time.time(), "path": self.path, "model": body.get("model"), "stream": bool(body.get("stream")),
                "roles": [m.get("role") for m in msgs],
                "tools": sorted(t.get("function", {}).get("name") for t in body.get("tools") or []),
                "system_head": sysmsg[:300], "system_len": len(sysmsg),
                "soul_tecnico": "No eres Zazu" in sysmsg, "soul_zazu": "ZAZU-SOUL-MARCADOR" in sysmsg,
                "memoria": "VERDE-MARCADOR" in sysmsg,
                "user": ultimo_user[:200], "tool_result": None if ultimo_tool is None else ultimo_tool[:600],
                "respuesta": r.get("text") or ("tool:" + r["tool"][1]["command"]),
            }, ensure_ascii=False) + "\n")
        cid = "chatcmpl-" + uuid.uuid4().hex[:8]
        usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
        if r.get("tool"):
            name, args = r["tool"]
            tc = {"index": 0, "id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                  "function": {"name": name, "arguments": json.dumps(args)}}
            msg = {"role": "assistant", "content": None, "tool_calls": [{k: v for k, v in tc.items() if k != "index"}]}
            fin = "tool_calls"
        else:
            msg = {"role": "assistant", "content": r["text"]}
            fin = "stop"
        if not body.get("stream"):
            return self._json({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": body.get("model"),
                               "choices": [{"index": 0, "message": msg, "finish_reason": fin}], "usage": usage})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def send(d):
            self.wfile.write(("data: " + json.dumps(d) + "\n\n").encode())
            self.wfile.flush()
        base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model")}
        delta = {"role": "assistant", "tool_calls": [tc]} if r.get("tool") else {"role": "assistant", "content": r["text"]}
        send({**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
        send({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": fin}]})
        send({**base, "choices": [], "usage": usage})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
