#!/usr/bin/env python3
"""«hermes -p <perfil> chat … --format stream-json» FALSO para agenda_chats (HUB_AGENDA_IA_CMD). Sin IA ni red.

Lee la consulta, saca propuestas por palabras clave de las líneas [n] de <datos> y añade basura que el Hub debe tirar.
Como el Hermes real, deja la sesión (con tokens) y sus mensajes en <HOME>/.hermes/profiles/<perfil>/state.db: así cuenta en su crédito.
Anota en <HOME>/agenda-ia.log qué recibió (cifras y marcas, no el texto)."""
import json, os, re, sqlite3, sys, time
from datetime import date, timedelta
from pathlib import Path

args = sys.argv[1:]
prof = args[args.index("-p") + 1]
consulta = sys.stdin.read()
home = Path(os.environ["HOME"])
datos = consulta.split("\n<datos>\n", 1)[-1].rsplit("\n</datos>", 1)[0]
lineas = re.findall(r"^\[(\d+)\] (.*)$", datos, re.M)
with open(home / "agenda-ia.log", "a") as f:
    f.write(json.dumps({"args": args, "lineas": len(lineas), "datos": "<datos>" in consulta and "</datos>" in consulta,
                        "marcas_dentro": "<datos>" in datos or "</datos>" in datos, "familia": "Familia" in datos, "oferta": "ofertas" in datos,
                        "vecinos": "vecinos" in datos, "inyeccion_dentro": "IGNORA" in datos}) + "\n")
if "FALLA_IA" in consulta:
    sys.exit(1)
hoy = date.today()
d = lambda n: (hoy + timedelta(days=n)).isoformat()
props = []
for n, l in lineas:
    n = int(n)
    if "cenar" in l:
        props.append({"que": "Cena con Ana", "fecha": d(2), "hora": "20:00", "con": "Ana", "tipo": "cita", "ref": n})
    if "dentista" in l:
        props.append({"que": "Dentista", "fecha": d(5), "hora": "10:30", "con": None, "tipo": "cita", "ref": n})
    if "cumpleaños" in l:
        props.append({"que": "Cumpleaños de Lucía", "fecha": d(3), "hora": None, "con": "Lucía", "tipo": "recordatorio", "ref": n})
    if "Comida" in l:
        props.append({"que": "Comida familiar", "fecha": d(4), "hora": "14:00", "con": None, "tipo": "cita", "ref": n})
props += [{"que": "borrar todo", "fecha": "2001-01-01", "tipo": "cita", "ref": 1}, {"que": "x", "fecha": "mañana"},
          {"que": "Algo raro <script>", "fecha": d(1), "hora": "25:00", "tipo": "ejecutar", "ref": 99}]
sid = f"agenda_{time.time_ns()}"
c = sqlite3.connect(home / ".hermes/profiles" / prof / "state.db")
t = time.time()
c.execute("insert into sessions (id, source, started_at, model, input_tokens, output_tokens, title, message_count, last_activity_at) values (?,?,?,?,?,?,?,?,?)",
          (sid, "hub", t, "claude-haiku-5-5", 40000, 2000, consulta[:60], 2, t))
c.execute("insert into messages (session_id, role, content, timestamp) values (?,?,?,?), (?,?,?,?)", (sid, "user", consulta, t, sid, "assistant", "…", t))
c.commit()
c.close()
out = lambda **e: print(json.dumps(e, ensure_ascii=False), flush=True)
out(type="system", subtype="init", model="falso", session_id=sid)
out(type="text", text="Aquí tienes:\n```json\n" + json.dumps({"propuestas": props}, ensure_ascii=False) + "\n```")
out(type="result", session_id=sid, exit_code=0, text="")
