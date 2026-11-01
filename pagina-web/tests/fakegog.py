#!/usr/bin/env python3
"""gog FALSO del banco de pruebas del Hub (Panel de tu día). Nunca toca Google.
Datos: $HOME/gogdata/<varas|alvarez>.tasks.json y .events.json (listas, las cambia la prueba en caliente).
Fallos y retrasos a pedido: $HOME/gogdata/fail  (una línea por orden: «tasks list», «tasks list:alvarez», «all»)
                            $HOME/gogdata/sleep (una línea «calendar events=5»)
                            $HOME/gogdata/basura (una línea por orden: sale 0 pero imprime algo que no es JSON)
Cada llamada se anota en $HOME/gog.log (JSON por línea). Una escritura con --readonly sale con error, como el gog real.
Con --home=<carpeta> (la de una invitada): sus cuentas salen de <carpeta>/accounts.json (sin él, ninguna) y sus datos de <carpeta>/gogdata/invitada.*.json.
Tareas en varias listas: <tag>.tasklists.json ([{id, title}]; sin él, una sola «principal»); la primera lista (y @default) usa <tag>.tasks.json,
las demás <tag>.tasks.<id>.json. Borrar (tareas o eventos) sin --force falla, como el gog real sin terminal.
Cada línea de gog.log lleva «llave»: los 8 primeros de sha256(GOG_KEYRING_PASSWORD) o "" (para ver con qué clave se abrió el llavero)."""
import hashlib, json, os, sys, time
from pathlib import Path

home = Path(os.environ.get("HOME", "."))
args = sys.argv[1:]
# la orden empieza en el primer argumento que no es una opción global (--account=, --client=, --home=, --readonly, …)
i = 0
while i < len(args) and args[i].startswith("--"):
    i += 1
orden = args[i:]
cuenta = next((a.split("=", 1)[1] for a in args[:i] if a.startswith("--account=")), "")
tag = "alvarez" if "alvarez" in cuenta else "varas"
readonly = "--readonly" in args[:i]
casa = next((a.split("=", 1)[1] for a in args[:i] if a.startswith("--home=")), "")
if casa:
    tag = "invitada"
llave = hashlib.sha256(os.environ["GOG_KEYRING_PASSWORD"].encode()).hexdigest()[:8] if os.environ.get("GOG_KEYRING_PASSWORD") else ""
with open(home / "gog.log", "a") as f:
    f.write(json.dumps({"orden": orden, "tag": tag, "readonly": readonly, "home": casa, "llave": llave}, ensure_ascii=False) + "\n")
verbo = " ".join(orden[:2])
datos = Path(casa) / "gogdata" if casa else home / "gogdata"
try:
    for ln in (datos / "fail").read_text().splitlines():
        ln = ln.strip()
        if ln == "all" or ln == verbo or ln == f"{verbo}:{tag}":
            sys.stderr.write("fallo pedido por la prueba\n")
            sys.exit(1)
except FileNotFoundError:
    pass
try:
    if verbo in (datos / "basura").read_text().split("\n"):
        print("esto no es JSON")
        sys.exit(0)
except FileNotFoundError:
    pass
try:
    for ln in (datos / "sleep").read_text().splitlines():
        if "=" in ln and ln.split("=")[0].strip() == verbo:
            time.sleep(float(ln.split("=")[1]))
except FileNotFoundError:
    pass


def leer(nombre):
    try:
        return json.loads((datos / f"{tag}.{nombre}.json").read_text())
    except FileNotFoundError:
        return []


def guardar(nombre, lista):
    (datos / f"{tag}.{nombre}.json").write_text(json.dumps(lista, ensure_ascii=False))


CON_VALOR = ("--max", "--out", "--page")                                  # opciones que llevan el valor en el argumento siguiente
pos = [a for j, a in enumerate(orden) if not a.startswith("--") and (j == 0 or orden[j - 1] not in CON_VALOR)]   # argumentos sueltos
opt = dict(a[2:].split("=", 1) for a in orden if a.startswith("--") and "=" in a)
banderas = {a[2:] for a in orden if a.startswith("--") and "=" not in a}


def no_si_solo_lectura():
    if readonly:
        sys.stderr.write("escritura con --readonly\n")
        sys.exit(1)


def listas():
    return leer("tasklists") or [{"id": "principal", "title": "Mis tareas"}]


def de_lista(lid):
    """Nombre del archivo de tareas de una lista (la primera y @default: «tasks»)."""
    ids = [l["id"] for l in listas()]
    if lid == "@default" or lid == ids[0]:
        return "tasks"
    if lid not in ids:
        sys.stderr.write("lista inexistente\n")
        sys.exit(1)
    return f"tasks.{lid}"


def cuenta_casa():
    try:
        return next(iter(json.loads((Path(casa) / "accounts.json").read_text())), {})
    except (OSError, ValueError):
        return {}


if orden[:2] == ["auth", "credentials"]:
    print("{}")
elif orden[:3] == ["auth", "tokens", "import"]:   # lo que llega por stdin (o en el archivo) queda en gog-import.log (los tokens son de mentira)
    origen = sys.stdin.read() if pos[3:4] in ([], ["-"]) else Path(pos[3]).read_text()
    with open(home / "gog-import.log", "a") as f:
        f.write(json.dumps({**json.loads(origen), "home": casa, "llave": llave}, ensure_ascii=False) + "\n")
    print("{}")
elif orden[:3] == ["auth", "tokens", "export"] and casa:
    a = next((a for a in json.loads((Path(casa) / "accounts.json").read_text()) if a.get("email") == pos[3]), None)
    if not a or not opt.get("out"):
        sys.stderr.write("token inexistente\n")
        sys.exit(1)
    Path(opt["out"]).write_text(json.dumps({**{k: v for k, v in a.items() if k != "error"}, "refresh_token": "rt-falso"}))
    print(json.dumps({"exported": True}))
elif orden[:2] == ["auth", "list"] and casa:
    try:
        print(json.dumps({"accounts": json.loads((Path(casa) / "accounts.json").read_text())}))
    except FileNotFoundError:
        print(json.dumps({"accounts": []}))
elif orden[:2] == ["auth", "list"]:
    print(json.dumps({"accounts": [{"email": "cuenta.principal@example.com", "client": "default", "services": ["calendar", "gmail", "tasks"], "error": False},
                                   {"email": "cuenta.secundaria@example.com", "client": "default", "services": ["calendar", "gmail", "tasks"], "error": False}]}))
elif orden[:3] == ["tasks", "lists", "list"]:
    print(json.dumps({"tasklists": listas()}))
elif orden[:2] == ["tasks", "list"]:
    print(json.dumps({"tasks": leer(de_lista(pos[2] if len(pos) > 2 else "@default"))}))
elif orden[:2] in (["tasks", "done"], ["tasks", "undo"], ["tasks", "update"], ["tasks", "delete"]) and len(pos) >= 4:
    no_si_solo_lectura()
    if orden[1] == "delete" and "force" not in banderas:
        sys.stderr.write("refusing to delete without --force (non-interactive)\n")
        sys.exit(1)
    nombre = de_lista(pos[2])
    lista = leer(nombre)
    tarea = next((t for t in lista if t.get("id") == pos[3]), None)
    if tarea is None:
        sys.stderr.write("tarea inexistente\n")
        sys.exit(1)
    if orden[1] == "done":
        tarea["status"] = "completed"
    elif orden[1] == "undo":
        tarea["status"] = "needsAction"
    elif orden[1] == "delete":
        lista.remove(tarea)
    else:
        if "due" in opt:
            tarea["due"] = opt["due"] + "T00:00:00.000Z" if opt["due"] else ""
        if "title" in opt:
            tarea["title"] = opt["title"]
        if "notes" in opt:
            tarea["notes"] = opt["notes"]
    guardar(nombre, lista)
    print(json.dumps({"task": {"id": tarea["id"], "title": tarea.get("title", "")}}))
elif orden[:2] in (["tasks", "add"], ["calendar", "create"]):
    no_si_solo_lectura()
    print(json.dumps({"task" if orden[0] == "tasks" else "event": {"id": "nuevo" + str(int(time.time() * 1000))[-8:], "title": "x"}}))
elif orden[:2] == ["calendar", "events"]:
    evs = leer("events")
    q = opt.get("query", "").casefold()
    if q:
        evs = [e for e in evs if q in " ".join(str(e.get(k) or "") for k in ("summary", "location", "description")).casefold()]
    print(json.dumps({"events": evs}))
elif orden[:2] == ["calendar", "event"] and len(pos) >= 4:
    e = next((e for e in leer("events") if e.get("id") == pos[3]), None)
    if e is None:
        sys.stderr.write("evento inexistente\n")
        sys.exit(1)
    print(json.dumps({"event": e}))
elif orden[:2] in (["calendar", "update"], ["calendar", "delete"]) and len(pos) >= 4:
    no_si_solo_lectura()
    if orden[1] == "delete" and "force" not in banderas:
        sys.stderr.write("refusing to delete without --force (non-interactive)\n")
        sys.exit(1)
    evs = leer("events")
    if opt.get("scope") in ("single", "future"):   # como el gog real: el id de la serie y el comienzo original de ese día
        o = opt.get("original-start", "")
        tocan = [e for e in evs if e.get("recurringEventId") == pos[3] and o in ((e.get("originalStartTime") or {}).get("dateTime"), (e.get("originalStartTime") or {}).get("date"))]
    else:
        tocan = [e for e in evs if e.get("id") == pos[3] or e.get("recurringEventId") == pos[3]]
    if not tocan:
        sys.stderr.write("evento inexistente\n")
        sys.exit(1)
    for e in tocan:
        if orden[1] == "delete":
            evs.remove(e)
            continue
        if "summary" in opt:
            e["summary"] = opt["summary"]
        if "location" in opt:
            e["location"] = opt["location"]
        clave = "date" if "all-day" in banderas else "dateTime"
        if "from" in opt:
            e["start"] = {clave: opt["from"]}
        if "to" in opt:
            e["end"] = {clave: opt["to"]}
    guardar("events", evs)
    print(json.dumps({"event": {"id": pos[3]}}))
elif orden[:2] == ["gmail", "search"]:
    # correos inventados de <tag>.gmail.json: [{id, from, subject, internalDateIso, messageCount, messages: [{body}]}]; la búsqueda no trae cuerpos
    # una búsqueda de solo palabras sueltas («recibo banco») filtra por remitente y asunto; con operadores (newer_than:3d, OR, paréntesis…), todo
    palabras = [w.casefold() for w in " ".join(pos[2:]).split()]
    if any(":" in w or w in ("or", "and") or w[:1] in "-({" for w in palabras):
        palabras = []
    hilos = [t for t in leer("gmail") if all(w in (str(t.get("from")) + " " + str(t.get("subject"))).casefold() for w in palabras)]
    print(json.dumps({"threads": [{k: v for k, v in t.items() if k != "messages"} for t in hilos]}))
elif orden[:3] == ["gmail", "thread", "get"] and len(orden) >= 4:
    t = next((t for t in leer("gmail") if t.get("id") == orden[3]), None)
    if t is None:
        sys.stderr.write("hilo inexistente\n")
        sys.exit(1)
    print(json.dumps({"thread": {"id": t["id"], "messages": t.get("messages") or []}}))
elif orden[:3] == ["gmail", "drafts", "create"]:
    no_si_solo_lectura()
    if casa and "https://www.googleapis.com/auth/gmail.compose" not in (cuenta_casa().get("scopes") or []):
        sys.stderr.write("Request had insufficient authentication scopes.\n")
        sys.exit(1)
    print(json.dumps({"draftId": "borrador1", "threadId": opt.get("thread-id", "hilonuevo")}))
else:
    sys.stderr.write(f"gog falso: orden no soportada {orden}\n")
    sys.exit(2)
