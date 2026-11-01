#!/usr/bin/env python3
"""«hermes chat … --format stream-json» FALSO (lo usa el guardia de tests/fakehome.sh). Sin IA ni red.

Lee la consulta de stdin y emite el protocolo de hermes_cli/stream_json.py: system/init → text / tool_use / tool_result → result.
Si la consulta lleva LENTO, hace herramientas durante 30 s; un SIGINT (botón Parar) se apunta en <casa>/sigint.log y sale con 130.
"""
import json, os, signal, sys, time
from pathlib import Path

CASA = Path(__file__).resolve().parents[2]
args = sys.argv[1:]
sid = args[args.index("--resume") + 1] if "--resume" in args else "zazu_" + time.strftime("%Y%m%d_%H%M%S")


def emitir(**ev):
    sys.stdout.write(json.dumps({**ev, "timestamp": int(time.time() * 1000)}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def parar(*_):
    with open(CASA / "sigint.log", "a") as f:
        f.write(f"SIGINT {os.getpid()} {time.time()}\n")
    emitir(type="result", session_id=sid, exit_code=130, text="", error="interrumpido")
    sys.exit(130)


signal.signal(signal.SIGINT, parar)
consulta = sys.stdin.read()
emitir(type="system", subtype="init", model="falso", session_id=sid)
for trozo in ("Hola, ", "Fran. "):
    emitir(type="text", text=trozo)
    time.sleep(0.1)
vueltas = 15 if "LENTO" in consulta else 1
for i in range(vueltas):
    cid = f"call_z{i}"
    emitir(type="tool_use", name="terminal", tool_call_id=cid, input={"command": f"ls -la  # {i + 1}", "timeout": 30})
    time.sleep(2 if vueltas > 1 else 0.2)
    emitir(type="tool_result", name="terminal", tool_call_id=cid, output="total 0", duration_ms=200, is_error=False)
emitir(type="text", text="Ya está.")
if "RAPIDAS" in consulta:
    emitir(type="text", text="\n¿Lo apunto?\n[[Sí | No | Luego]]")


def guardar(respuesta):
    """Como el Hermes real: la conversación queda en la base del perfil (sessions + messages), para que el hub la encuentre."""
    import sqlite3
    prof = args[args.index("-p") + 1] if "-p" in args else None
    db = Path(os.environ.get("HOME", "")) / ".hermes" / (f"profiles/{prof}/state.db" if prof else "state.db")
    if not db.exists():
        return
    c, t = sqlite3.connect(db), time.time()
    if "--resume" not in args:
        c.execute("insert or ignore into sessions (id, source, started_at, title, message_count, last_activity_at) values (?,?,?,?,0,?)",
                  (sid, "hub", t, consulta.strip().split("\n")[0][:80], t))
    for role, content in (("user", consulta), ("assistant", respuesta)):
        c.execute("insert into messages (session_id, role, content, timestamp) values (?,?,?,?)", (sid, role, content, t))
    c.execute("update sessions set message_count=message_count+2, last_activity_at=? where id=?", (t, sid))
    c.commit()
    c.close()


guardar("Hola, Fran. Ya está." + ("\n¿Lo apunto?\n[[Sí | No | Luego]]" if "RAPIDAS" in consulta else ""))
emitir(type="result", session_id=sid, exit_code=0, text="Hola, Fran. Ya está.")
