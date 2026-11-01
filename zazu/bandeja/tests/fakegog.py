#!/usr/bin/python3
"""gog FALSO para los tests: sirve datos de $FAKE_DIR/data.json, guarda los cambios y apunta cada llamada en calls.log.
Una escritura con --readonly es una VIOLACIÓN (se apunta y falla): los tests exigen que no haya ninguna."""
import json, os, sys, uuid
from pathlib import Path

D = Path(os.environ["FAKE_DIR"])
if os.environ.get("FAKE_GOG_FAIL"):
    sys.exit(int(os.environ["FAKE_GOG_FAIL"]))
data = json.loads((D / "data.json").read_text())
args = sys.argv[1:]
cuenta, readonly, pos, flags = "varas", False, [], {}
for a in args:
    if a.startswith("--account="):
        cuenta = "alvarez" if "alvarez" in a else "varas"
    elif a == "--readonly":
        readonly = True
    elif a in ("--gmail-no-send", "--no-input", "--json"):
        pass
    elif a.startswith("--"):
        k, _, v = a[2:].partition("=")
        flags[k] = v if _ else True
    else:
        pos.append(a)
acc = data["accounts"][cuenta]
ESCR = {("tasks", "add"), ("tasks", "update"), ("tasks", "done"), ("tasks", "delete"), ("calendar", "create"), ("calendar", "update"), ("calendar", "delete"), ("gmail", "send")}
verbo = tuple(pos[:2])


def log(extra=""):
    with open(D / "calls.log", "a") as f:
        f.write(json.dumps({"cuenta": cuenta, "args": [a for a in args if not a.startswith("--title") and not a.startswith("--notes")], "ro": readonly, "extra": extra}) + "\n")


def guardar():
    (D / "data.json").write_text(json.dumps(data))


def lista_id(x):
    return acc["lists"][0]["id"] if x == "@default" else x


if verbo in ESCR:
    if readonly:
        log("VIOLACION")
        print("read-only", file=sys.stderr)
        sys.exit(1)
    if verbo not in {("tasks", "add"), ("tasks", "update"), ("tasks", "done")}:
        log("PROHIBIDO")
        sys.exit(2)
    log("ESCRITURA")
    L = lista_id(pos[2])
    if verbo == ("tasks", "add"):
        t = {"id": "T" + uuid.uuid4().hex[:8], "title": flags.get("title", ""), "status": "needsAction", "updated": os.environ.get("ZB_AHORA", "2026-10-08T21:00:00") + "Z"}
        if flags.get("due"):
            t["due"] = flags["due"] + "T00:00:00.000Z"
        acc["tasks"].setdefault(L, []).append(t)
        guardar()
        print(json.dumps({"task": t}))
    else:
        t = next(x for x in acc["tasks"][L] if x["id"] == pos[3])
        if verbo == ("tasks", "done"):
            t["status"] = "completed"
        else:
            if "notes" in flags:
                t["notes"] = flags["notes"]
            if "due" in flags:
                t["due"] = flags["due"] + "T00:00:00.000Z"
        t["updated"] = os.environ.get("ZB_AHORA", "2026-10-08T21:00:00") + "Z"
        guardar()
        print(json.dumps({"task": t}))
    sys.exit(0)

log()
if verbo == ("tasks", "lists"):
    print(json.dumps({"tasklists": acc["lists"]}))
elif verbo == ("tasks", "list"):
    L = lista_id(pos[2])
    ts = acc["tasks"].get(L, [])
    if not flags.get("show-completed"):
        ts = [t for t in ts if t.get("status", "needsAction") == "needsAction"]
    print(json.dumps({"tasks": ts}))
elif verbo == ("calendar", "events"):
    print(json.dumps({"events": acc["events"]}))
elif verbo == ("calendar", "calendars"):
    print(json.dumps({"calendars": [{"id": "cal1", "accessRole": "owner", "primary": True}]}))
else:
    log("DESCONOCIDO")
    sys.exit(2)
