#!/usr/bin/env python3
"""Gateway de Hermes FALSO para probar el Hub (plan §8.1). Solo biblioteca estándar; nunca llama a ningún modelo.

Imita el api_server real (gateway/platforms/api_server_runs.py) con las formas de evento vistas en la prueba real:
  GET  /health
  POST /p/<perfil>/v1/runs                    (Bearer = API_SERVER_KEY de <home>/profiles/<perfil>/.env; si no, 401)
  GET  /p/<perfil>/v1/runs/{id}
  GET  /p/<perfil>/v1/runs/{id}/events?last_seq=N   (SSE: «: open», «id: N» + «data: {…,"seq":N}», «: keepalive»)
  POST /p/<perfil>/v1/runs/{id}/approval      {choice, request_id?} → 200 resolved:1 / 409 approval_not_pending
  POST /p/<perfil>/v1/runs/{id}/stop          → {status:"stopping"}; una aprobación pendiente SIGUE pendiente (como el real)
Escenarios por palabra clave en «input»: PERMISO (aprobación del hook), PELIGRO (control propio, smart_denied;
con OCULTO el comando lleva 60 líneas en blanco antes del «rm», con ESPACIOS 4100 espacios y con ENORME pasa de 20000 caracteres),
LENTO (30 s de herramientas), FALLA (run.failed), CORTE (corta el SSE una vez tras el primer evento),
OLVIDA (el gateway «se reinicia» y olvida la ejecución) y, si no, una herramienta + texto + run.completed.
Escribe las filas en <home>/profiles/<perfil>/state.db y cada petición en <home>/../peticiones.jsonl (nunca la clave).
Uso: fake_gateway.py --port 18642 --home <fh>/.hermes [--timeout 20] [--keepalive 10]
"""
import argparse, json, sqlite3, threading, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

A = None
RUNS = {}
LOCK = threading.Lock()
LOG_LOCK = threading.Lock()


def clave(perfil):
    try:
        for l in (Path(A.home) / "profiles" / perfil / ".env").read_text().splitlines():
            if l.startswith("API_SERVER_KEY="):
                return l.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def anotar(**kv):
    with LOG_LOCK, open(Path(A.home).parent / "peticiones.jsonl", "a") as f:
        f.write(json.dumps({"t": time.time(), **kv}, ensure_ascii=False) + "\n")


# ---------- state.db del perfil (lo que luego lee el Hub) ----------
def con(perfil):
    c = sqlite3.connect(Path(A.home) / "profiles" / perfil / "state.db", timeout=10)
    c.row_factory = sqlite3.Row
    return c


def db_mensaje(run, role, content=None, tool_calls=None, tool_call_id=None, tool_name=None):
    c = con(run["perfil"])
    try:
        ahora = time.time()
        if not c.execute("select 1 from sessions where id=?", (run["session_id"],)).fetchone():
            c.execute("insert into sessions (id, source, started_at, model, title, message_count, last_activity_at) values (?,?,?,?,?,0,?)",
                      (run["session_id"], "api_server", ahora, run["model"] or "fake", (run["input"] or "")[:40], ahora))
        c.execute("insert into messages (session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp) values (?,?,?,?,?,?,?)",
                  (run["session_id"], role, content, tool_call_id, json.dumps(tool_calls) if tool_calls else None, tool_name, ahora))
        c.execute("update sessions set message_count=message_count+1, last_activity_at=? where id=?", (ahora, run["session_id"]))
        c.execute("""insert into session_model_usage (session_id, model, billing_provider, task, api_call_count, first_seen, last_seen)
                     values (?,?,?,'',1,?,?) on conflict(session_id, model, billing_provider, billing_base_url, billing_mode, task)
                     do update set api_call_count=api_call_count+1, last_seen=excluded.last_seen""",
                  (run["session_id"], run["model"] or "fake", run["provider"] or "", ahora, ahora))
        c.commit()
    finally:
        c.close()


# ---------- eventos ----------
def evento(run, nombre, **campos):
    ev = {"event": nombre, "run_id": run["run_id"], "timestamp": time.time(), **campos}
    with run["cond"]:
        run["eventos"].append(ev)
        run["status"] = {"run.completed": "completed", "run.failed": "failed", "run.cancelled": "cancelled",
                         "approval.request": "waiting_for_approval", "approval.responded": "running"}.get(nombre, run["status"])
        run["last_event"], run["updated_at"] = nombre, time.time()
        if nombre in ("run.completed", "run.failed", "run.cancelled"):
            run["cerrado"] = True
        run["cond"].notify_all()


def fin(run, salida):
    if run["stop"]:
        return evento(run, "run.cancelled", completed=False, partial=False, interrupted=True)
    db_mensaje(run, "assistant", salida)
    evento(run, "run.completed", completed=True, partial=False, interrupted=False, output=salida,
           usage={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220})


def llamada(run, cmd, extra=None):
    """Fila del asistente con la llamada a la herramienta (como la guarda Hermes). Devuelve su id."""
    cid = "call_" + uuid.uuid4().hex[:12]
    args = {"command": cmd, **(extra or {})}
    db_mensaje(run, "assistant", "", tool_calls=[{"id": cid, "type": "function", "function": {"name": "terminal", "arguments": json.dumps(args, ensure_ascii=False)}}])
    return cid


def herramienta(run, cmd, salida="ok", error=False, extra=None, cid=None):
    cid = cid or llamada(run, cmd, extra)
    evento(run, "tool.started", tool="terminal", preview=cmd)
    time.sleep(0.3)
    db_mensaje(run, "tool", json.dumps({"output": salida, "exit_code": 1 if error else 0}), tool_call_id=cid, tool_name="terminal")
    evento(run, "tool.completed", tool="terminal", duration=0.3, error=error, preview=json.dumps({"output": salida})[:500])


def comando_peligro(texto):
    """Comandos que intentan esconder la parte peligrosa en la tarjeta de permiso (el Hub debe enseñarla entera)."""
    if "OCULTO" in texto:
        return "ls /tmp/prueba-hub" + "\n" * 60 + "rm -rf /tmp/prueba-hub/oculto"
    if "ESPACIOS" in texto:
        return "ls /tmp/prueba-hub" + " " * 4100 + "&& rm -rf /tmp/prueba-hub/oculto"
    if "ENORME" in texto:
        return "echo " + "x" * 25000 + " && rm -rf /tmp/prueba-hub/oculto"
    return "rm -rf /tmp/prueba-hub"


def ejecutar(run):
    texto = run["input"] or ""
    db_mensaje(run, "user", texto)
    time.sleep(0.2)
    if "FALLA" in texto:
        return evento(run, "run.failed", completed=False, partial=False, interrupted=False, error="Fallo simulado del proveedor")
    if "OLVIDA" in texto:
        evento(run, "message.delta", delta="Empiezo… ")
        time.sleep(1.5)
        with LOCK:
            RUNS.pop(run["run_id"], None)   # el gateway «se reinicia»: ya no conoce la ejecución
        with run["cond"]:
            run["olvidado"] = True
            run["cond"].notify_all()
        return
    if "PERMISO" in texto or "PELIGRO" in texto:
        rid = uuid.uuid4().hex
        if "PERMISO" in texto:   # aviso del hook movil-aprobacion (plugin approval rule)
            cmd = "sudo -n true"
            datos = {"command": "<terminal> (plugin approval rule)", "pattern_key": "plugin_rule:movil:sudo",
                     "pattern_keys": ["plugin_rule:movil:sudo"],
                     "description": "Zazu quiere usar permisos de administrador (sudo). Revisa el comando entero:\n" + cmd,
                     "allow_permanent": True, "allow_session": True, "request_id": rid, "choices": ["once", "session", "always", "deny"]}
        else:   # control propio de Hermes, ya pasado por el revisor automático
            cmd = comando_peligro(texto)
            datos = {"command": cmd, "pattern_key": "recursive delete", "pattern_keys": ["recursive delete"], "description": "recursive delete",
                     "allow_permanent": False, "allow_session": False, "smart_denied": True, "request_id": rid, "choices": ["once", "deny"]}
        choices = datos.pop("choices")
        cid = llamada(run, cmd)
        with run["cond"]:
            run["pendiente"] = {"request_id": rid, "choice": None}
        evento(run, "approval.request", **datos, choices=choices)
        limite = time.time() + A.timeout
        with run["cond"]:
            while run["pendiente"]["choice"] is None and time.time() < limite:
                run["cond"].wait(0.2)
            eleccion = run["pendiente"]["choice"]
            run["pendiente"] = None
        time.sleep(0.6)   # el modelo vuelve a pensar con la respuesta (en el real son segundos)
        if eleccion in ("once", "session", "always"):
            herramienta(run, cmd, "sudo: se necesita una contraseña", error=True, cid=cid)
            if run["stop"]:
                return fin(run, "")
            evento(run, "message.delta", delta="Hecho: lo he intentado.")
            return fin(run, "Hecho: lo he intentado.")
        motivo = "User denied" if eleccion == "deny" else "Action timed out without user response"
        aviso = f'\n\nRESULTADO_TOOL: {{"error": "BLOCKED: {motivo}. The user has NOT consented to this action."}}'
        db_mensaje(run, "tool", json.dumps({"error": "BLOCKED: " + motivo}), tool_call_id=cid, tool_name="terminal")
        evento(run, "message.delta", delta=aviso)
        evento(run, "reasoning.available", text=aviso.strip())
        return fin(run, aviso.strip())
    if "LENTO" in texto:
        for i in range(15):
            if run["stop"]:
                break
            herramienta(run, f"sleep 1  # vuelta {i + 1}")
            time.sleep(1.7)
        return fin(run, "Terminé la tarea larga.")
    evento(run, "message.delta", delta="Voy a mirarlo. ")
    herramienta(run, "ls -la", "total 0", extra={"nota": "x" * 1500})   # argumentos largos: el Hub ya no corta a 600
    evento(run, "message.delta", delta="Listo: todo en orden.")
    fin(run, "Voy a mirarlo. Listo: todo en orden.")


# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def error(self, code, msg, tipo="invalid_request_error"):
        self.json({"error": {"message": msg, "type": tipo, "code": tipo}}, code)

    def ruta(self):
        u = urlparse(self.path)
        partes = u.path.strip("/").split("/")
        return u, partes, {k: v[0] for k, v in parse_qs(u.query).items()}

    def autorizado(self, perfil):
        k = clave(perfil)
        return bool(k) and self.headers.get("Authorization", "") == "Bearer " + k

    def cuerpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u, partes, q = self.ruta()
        if u.path == "/health":
            return self.json({"status": "ok", "platform": "hermes-agent"})
        if len(partes) < 5 or partes[0] != "p" or partes[2:4] != ["v1", "runs"]:
            return self.error(404, "not found", "not_found")
        perfil, run_id = partes[1], partes[4]
        ok = self.autorizado(perfil)
        anotar(metodo="GET", ruta=u.path, consulta=q, auth=ok)
        if not ok:
            return self.error(401, "Invalid API key", "invalid_api_key")
        run = RUNS.get(run_id)
        if not run:
            return self.error(404, f"Run not found: {run_id}", "run_not_found")
        if len(partes) == 5:
            return self.json({"object": "hermes.run", "run_id": run_id, "status": run["status"], "updated_at": run["updated_at"],
                              "created_at": run["created_at"], "session_id": run["session_id"], "model": "hermes-agent", "last_event": run["last_event"]})
        if partes[5:] == ["events"]:
            return self.sse(run, int(q.get("last_seq", "-1")))
        return self.error(404, "not found", "not_found")

    def sse(self, run, last_seq):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(b": open\n\n")
        self.wfile.flush()
        cursor, ultimo_ka = last_seq, time.time()
        try:
            while True:
                with run["cond"]:
                    if len(run["eventos"]) <= cursor + 1 and not run["cerrado"] and not run.get("olvidado"):
                        run["cond"].wait(0.25)
                    nuevos = [(i, e) for i, e in enumerate(run["eventos"]) if i > cursor]
                    cerrado, olvidado = run["cerrado"], run.get("olvidado")
                for seq, ev in nuevos:
                    self.wfile.write(f"id: {seq}\ndata: {json.dumps({**ev, 'seq': seq})}\n\n".encode())
                    cursor = seq
                    if "CORTE" in (run["input"] or "") and not run.get("cortado"):
                        run["cortado"] = True
                        self.wfile.flush()
                        return   # corta la conexión a mitad: el Hub debe reconectar con last_seq
                if nuevos:
                    self.wfile.flush()
                if olvidado:
                    return
                if cerrado and len(run["eventos"]) <= cursor + 1:
                    self.wfile.write(b": stream closed\n\n")
                    self.wfile.flush()
                    return
                if time.time() - ultimo_ka > A.keepalive:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    ultimo_ka = time.time()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        u, partes, q = self.ruta()
        if len(partes) < 4 or partes[0] != "p" or partes[2:4] != ["v1", "runs"]:
            return self.error(404, "not found", "not_found")
        perfil = partes[1]
        try:
            body = self.cuerpo()
        except ValueError:
            return self.error(400, "Invalid JSON")
        ok = self.autorizado(perfil)
        anotar(metodo="POST", ruta=u.path, cuerpo=body, auth=ok, idem=self.headers.get("Idempotency-Key"))
        if not ok:
            return self.error(401, "Invalid API key", "invalid_api_key")
        if len(partes) == 4:   # nueva ejecución
            idem = self.headers.get("Idempotency-Key")
            with LOCK:
                previo = next((r for r in RUNS.values() if idem and r["idem"] == idem), None)
                if previo:
                    return self.json({"run_id": previo["run_id"], "status": "started", "replayed": True}, 202)
                rid = "run_" + uuid.uuid4().hex
                run = {"run_id": rid, "perfil": perfil, "idem": idem, "input": body.get("input"), "model": body.get("model"),
                       "provider": body.get("provider"), "session_id": body.get("session_id") or rid, "status": "running",
                       "created_at": time.time(), "updated_at": time.time(), "last_event": None, "eventos": [], "cerrado": False,
                       "stop": False, "pendiente": None, "cond": threading.Condition()}
                RUNS[rid] = run
            threading.Thread(target=ejecutar, args=(run,), daemon=True).start()
            return self.json({"run_id": rid, "status": "started", "replayed": False}, 202)
        run = RUNS.get(partes[4])
        if not run:
            return self.error(404, f"Run not found: {partes[4]}", "run_not_found")
        accion = partes[5] if len(partes) > 5 else ""
        if accion == "approval":
            choice = str(body.get("choice", "")).strip().lower()
            if choice not in ("once", "session", "always", "deny"):
                return self.error(400, "Invalid approval choice", "invalid_approval_choice")
            req_id = body.get("request_id")
            with run["cond"]:
                p = run["pendiente"]
                if not p or p["choice"] is not None or (req_id and req_id != p["request_id"]):
                    return self.error(409, f"Run has no pending approval: {run['run_id']}", "approval_not_pending")
                p["choice"] = choice
                run["cond"].notify_all()
            evento(run, "approval.responded", choice=choice, **({"request_id": req_id} if req_id else {}), resolved=1)
            return self.json({"object": "hermes.run.approval_response", "run_id": run["run_id"], "choice": choice,
                              **({"request_id": req_id} if req_id else {}), "resolved": 1})
        if accion == "stop":
            if run["status"] in ("completed", "failed", "cancelled"):
                return self.json({"run_id": run["run_id"], "status": run["status"]})
            run["stop"] = True
            run["status"] = "stopping"
            return self.json({"run_id": run["run_id"], "status": "stopping"})
        return self.error(404, "not found", "not_found")


def main():
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18642)
    ap.add_argument("--home", required=True)
    ap.add_argument("--timeout", type=float, default=20, help="segundos que espera una aprobación")
    ap.add_argument("--keepalive", type=float, default=10)
    A = ap.parse_args()
    if not str(Path(A.home).resolve()).startswith("/tmp/"):
        raise SystemExit("--home debe estar bajo /tmp (nunca el ~/.hermes de verdad)")
    srv = ThreadingHTTPServer(("127.0.0.1", A.port), H)
    srv.daemon_threads = True
    print(f"gateway falso en 127.0.0.1:{A.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
