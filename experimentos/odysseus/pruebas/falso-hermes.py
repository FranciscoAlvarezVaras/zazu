#!/usr/bin/env python3
"""Hermes FALSO para probar Odysseus sin tocar el Hermes real ni sus claves.
Imita lo que hace el api_server de Hermes en /v1/chat/completions (leído de gateway/platforms/api_server*.py):
 - exige 'Authorization: Bearer <clave de prueba>' (una clave inventada, NO la de Fran)
 - ignora 'tools'; los mensajes 'system' los usa como prompt efímero
 - en streaming manda trozos estándar y, además, eventos propios con nombre: hermes.tool.progress, hermes.status y
   approval.request (el permiso se contesta aparte, en POST /v1/runs/<id>/approval)
Guarda lo que recibe en falso-hermes.log para ver qué manda Odysseus.
Uso: venv/bin/python pruebas/falso-hermes.py 8655
"""
import asyncio, json, sys, time, uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

CLAVE = "clave-falsa-de-prueba-0123456789abcdef"
LOG = "/home/server/Odysseus/pruebas/falso-hermes.log"
app = FastAPI()

def log(obj):
    with open(LOG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def frame(data, event=None):
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.get("/v1/models")
async def models(request: Request):
    log({"GET": "/v1/models", "auth_ok": request.headers.get("authorization") == f"Bearer {CLAVE}"})
    if request.headers.get("authorization") != f"Bearer {CLAVE}":
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)
    return {"object": "list", "data": [{"id": "hermes-agent", "object": "model", "owned_by": "hermes"}]}

@app.post("/v1/chat/completions")
async def chat(request: Request):
    ok = request.headers.get("authorization") == f"Bearer {CLAVE}"
    body = await request.json()
    try:
        open(LOG.replace(".log", "-completo.log"), "a").write(json.dumps(body, ensure_ascii=False) + "\n")
    except Exception:
        pass
    msgs = body.get("messages", [])
    log({"POST": "/v1/chat/completions", "auth_ok": ok, "claves_del_cuerpo": sorted(body.keys()),
         "stream": body.get("stream"), "n_tools": len(body.get("tools") or []), "tool_choice": body.get("tool_choice"),
         "roles": [m.get("role") for m in msgs],
         "largo_system": sum(len(str(m.get("content"))) for m in msgs if m.get("role") == "system"),
         "ultimo_usuario": str(msgs[-1].get("content"))[:200] if msgs else None,
         "cabeceras": {k: v for k, v in request.headers.items() if k.lower().startswith(("x-", "user-agent", "content-type"))}})
    if not ok:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)
    ultimo = str(msgs[-1].get("content")) if msgs else ""
    cid = "chatcmpl-" + uuid.uuid4().hex[:24]
    def chunk(delta, fin=None):
        return {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": "hermes-agent",
                "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}
    if not body.get("stream"):
        return {"id": cid, "object": "chat.completion", "created": int(time.time()), "model": "hermes-agent",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hola, soy el Hermes falso (sin streaming)."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
    async def gen():
        yield frame(chunk({"role": "assistant"}))
        yield frame({"kind": "start", "text": "pensando"}, "hermes.status")
        yield frame(chunk({"content": "Hola, "}))
        if "[herramienta]" in ultimo:
            yield frame({"tool": "terminal", "label": "ls ~/Cerebro", "toolCallId": "t1", "status": "running"}, "hermes.tool.progress")
            await asyncio.sleep(0.5)
            yield frame({"tool": "terminal", "toolCallId": "t1", "status": "completed"}, "hermes.tool.progress")
        if "[aprobacion]" in ultimo:
            yield frame({"type": "approval.request", "run_id": cid, "command": "rm -rf /tmp/algo", "choices": ["once", "deny"]}, "approval.request")
            await asyncio.sleep(6)   # el Hermes real se queda esperando a que alguien conteste en /v1/runs/<id>/approval
            yield frame(chunk({"content": "(permiso no contestado: se acabó el tiempo) "}))
        yield frame(chunk({"content": "soy el Hermes falso. "}))
        yield frame(chunk({"content": "Todo bien."}))
        yield frame(chunk({}, "stop"))
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"X-Hermes-Session-Id": "sesion-falsa"})

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8655, log_level="warning")
