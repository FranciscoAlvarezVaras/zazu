#!/usr/bin/env python3
"""Ida y vuelta por /p/tecnico/v1/runs contra un gateway de Hermes de PRUEBAS (el de run.sh, con el LLM falso).

Uso: client.py <HERMES_HOME de pruebas> [escenario…]     (por defecto, todos)
Escenarios: ok, aprobar, denegar, parar, caduca, entorno, control, modelo, reanudar, sin_clave y perfil:<nombre>
(este último pide «USA_PERMISO» en /p/<nombre>/ y lo deniega: comprueba que el hook corre en ese perfil dentro del gateway;
necesita que ese perfil de PRUEBAS tenga su API_SERVER_KEY, que run.sh le pone).
Hace lo mismo que hará HolaZazu (§4.9 del plan): POST /v1/runs, SSE de /events, POST …/approval, POST …/stop.
Lee la clave de profiles/tecnico/.env y nunca la imprime. Sale con 1 si algo no cuadra.
"""
import json, os, sys, time, urllib.error, urllib.request

HOME = sys.argv[1]
GW = os.environ.get("GW", "http://127.0.0.1:18642")
FIN = ("run.completed", "run.failed", "run.cancelled")
PERFIL = "tecnico"            # perfil de las peticiones (perfil:<nombre> lo cambia)


def cab():
    clave = next(l.split("=", 1)[1].strip() for l in open(os.path.join(HOME, f"profiles/{PERFIL}/.env"))
                 if l.startswith("API_SERVER_KEY="))
    return {"Authorization": "Bearer " + clave, "Content-Type": "application/json"}


def base():
    return f"{GW}/p/{PERFIL}"


def pedir(metodo, ruta, cuerpo=None, extra=None, clave=True):
    h = {**(cab() if clave else {"Content-Type": "application/json"}), **(extra or {})}
    r = urllib.request.Request(base() + ruta, method=metodo, headers=h,
                               data=json.dumps(cuerpo).encode() if cuerpo is not None else None)
    try:
        with urllib.request.urlopen(r, timeout=30) as f:
            return f.status, json.loads(f.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def correr(texto, al_pedir=None, extra=None, limite=180):
    """Lanza un run y sigue sus eventos hasta el final. al_pedir(run_id, ev, notas) responde a approval.request."""
    cuerpo = {"input": texto, **(extra or {})}
    st, r = pedir("POST", "/v1/runs", cuerpo, {"Idempotency-Key": "prueba-" + str(time.time())})
    assert st == 202, (st, r)
    run = r["run_id"]
    st, estado = pedir("GET", f"/v1/runs/{run}")
    notas = {"run_id": run, "session_id": estado.get("session_id"), "eventos": [], "tiempos": []}
    t0 = time.time()
    req = urllib.request.Request(base() + f"/v1/runs/{run}/events", headers=cab())
    with urllib.request.urlopen(req, timeout=limite) as f:
        for crudo in f:
            linea = crudo.decode().rstrip("\n")
            if not linea.startswith("data: "):
                continue
            ev = json.loads(linea[6:])
            tipo = ev.get("event")
            notas["eventos"].append(tipo)
            notas["tiempos"].append(round(time.time() - t0, 1))
            if tipo == "approval.request":
                notas["peticion"] = {k: ev.get(k) for k in ("command", "description", "choices", "request_id", "timestamp",
                                                            "smart_denied", "pattern_key", "allow_session", "allow_permanent")}
                notas["campos_peticion"] = sorted(ev)
                if al_pedir:
                    al_pedir(run, ev, notas)
            if tipo in ("message.delta",):
                notas["texto"] = notas.get("texto", "") + (ev.get("delta") or "")
            if tipo in FIN:
                notas["salida"] = ev.get("output") or ev.get("error") or ""
                break
    st, fin = pedir("GET", f"/v1/runs/{run}")
    notas["estado_final"] = fin.get("status")
    return notas


def responder(eleccion):
    def f(run, ev, notas):
        notas["respuesta"] = pedir("POST", f"/v1/runs/{run}/approval", {"choice": eleccion, "request_id": ev["request_id"]})
        notas["respuesta_otra_vez"] = pedir("POST", f"/v1/runs/{run}/approval", {"choice": eleccion, "request_id": ev["request_id"]})
    return f


def parar(run, ev, notas):   # lo que hará HolaZazu en /api/parar: primero deny (el stop solo no la cancela), luego stop
    notas["deny"] = pedir("POST", f"/v1/runs/{run}/approval", {"choice": "deny", "request_id": ev["request_id"]})
    notas["stop"] = pedir("POST", f"/v1/runs/{run}/stop", {})


RESULTADOS = {}
SESION = {}


def comprobar(nombre, condiciones, notas):
    fallos = [k for k, v in condiciones.items() if not v]
    RESULTADOS[nombre] = {"ok": not fallos, "fallos": fallos,
                          "eventos": " ".join(e for e in notas.get("eventos", []) if e != "reasoning.available"),
                          **{k: notas[k] for k in ("respuesta", "respuesta_otra_vez", "deny", "stop", "estado_final",
                                                   "peticion", "campos_peticion", "espera_s") if k in notas},
                          "salida": str(notas.get("salida", ""))[:240]}
    print(("OK    " if not fallos else "FALLA ") + nombre + ("" if not fallos else "  ← " + ", ".join(fallos)), flush=True)


def e_ok():
    n = correr("di ok")
    SESION["id"] = n["session_id"]
    comprobar("ok", {"completado": n["eventos"][-1] == "run.completed", "texto": str(n.get("salida", "")).startswith("OK modelo=")}, n)


def e_aprobar():
    n = correr("USA_PERMISO", responder("once"))
    p = n.get("peticion") or {}
    ev = n["eventos"]
    i = ev.index("approval.request") if "approval.request" in ev else 99
    comprobar("aprobar", {
        "pide permiso": "approval.request" in ev,
        "es del hook": p.get("command") == "<terminal> (plugin approval rule)",
        "dice Hermes": str(p.get("description", "")).startswith("Hermes quiere usar permisos de administrador (sudo)"),
        "sin Zazu": "Zazu" not in str(p.get("description", "")),
        "trae el comando": "echo prueba-permiso sudo-falso" in str(p.get("description", "")),
        "opciones": {"once", "deny"} <= set(p.get("choices") or []),
        "200 resolved": n.get("respuesta", (0,))[0] == 200,
        "409 la segunda": n.get("respuesta_otra_vez", (0, {}))[0] == 409,
        "herramienta tras aprobar": "tool.started" in ev[i:] and "tool.completed" in ev[i:],
        "salida del comando": "prueba-permiso" in str(n.get("salida", "")) and "BLOCKED" not in str(n.get("salida", "")),
        "completado": ev[-1] == "run.completed",
    }, n)


def e_denegar():
    n = correr("USA_PERMISO", responder("deny"))
    ev = n["eventos"]
    comprobar("denegar", {
        "pide permiso": "approval.request" in ev, "200": n.get("respuesta", (0,))[0] == 200,
        "sin tool.started": "tool.started" not in ev, "BLOCKED": "BLOCKED" in str(n.get("salida", "")),
        "completado": ev[-1] == "run.completed",
    }, n)


def e_parar():
    n = correr("USA_PERMISO", parar)
    ev = n["eventos"]
    comprobar("parar", {
        "pide permiso": "approval.request" in ev, "deny 200": n.get("deny", (0,))[0] == 200,
        "stop 200": n.get("stop", (0,))[0] in (200, 202), "sin tool.started": "tool.started" not in ev,
        "termina": ev[-1] in FIN, "no sigue corriendo": n.get("estado_final") not in ("running", "waiting_for_approval"),
    }, n)


def e_caduca():
    n = correr("USA_PERMISO")
    ev, ts = n["eventos"], n["tiempos"]
    i = ev.index("approval.request") if "approval.request" in ev else None
    n["espera_s"] = round(ts[i + 1] - ts[i], 1) if i is not None and i + 1 < len(ts) else None
    comprobar("caduca", {
        "pide permiso": i is not None, "sin evento de caducidad": not any("expir" in e or "timeout" in e for e in ev),
        "sin tool.started": "tool.started" not in ev,
        "BLOCKED por tiempo": "timed out" in str(n.get("salida", "")) or "timed out" in n.get("texto", ""),
        "espera ≈ approvals.timeout": (n["espera_s"] or 0) >= 10,
        "completado": ev[-1] == "run.completed",
    }, n)


def e_entorno():
    n = correr("USA_ENV")
    s = str(n.get("salida", ""))
    comprobar("entorno", {"sin aprobación": "approval.request" not in ev_(n), "KEYS=0": "KEYS=0" in s}, n)


def ev_(n):
    return n["eventos"]


def e_control():
    n = correr("USA_CONTROL")
    comprobar("control", {
        "sin aprobación": "approval.request" not in ev_(n),
        "bloqueado por el hook": "Hermes no puede usar el control de HolaZazu" in str(n.get("salida", "")),
        "completado": ev_(n)[-1] == "run.completed",
    }, n)


def e_modelo():
    n = correr("di ok", extra={"model": "fake-barato", "provider": "custom:fakeb"})
    comprobar("modelo", {"usa el modelo pedido": "OK modelo=fake-barato" in str(n.get("salida", ""))}, n)


def e_reanudar():
    sid = SESION.get("id")
    n = correr("di ok otra vez", extra={"session_id": sid} if sid else None)
    comprobar("reanudar", {"hay sesión previa": bool(sid), "misma sesión": n.get("session_id") == sid,
                           "completado": ev_(n)[-1] == "run.completed"}, n)


def e_perfil(nombre):
    global PERFIL
    PERFIL = nombre
    try:
        n = correr("USA_PERMISO", responder("deny"))
    finally:
        PERFIL = "tecnico"
    p = n.get("peticion") or {}
    comprobar("perfil:" + nombre, {
        "el hook pide permiso en este perfil": "approval.request" in n["eventos"] and p.get("command") == "<terminal> (plugin approval rule)",
        "dice Zazu (no es tecnico)": str(p.get("description", "")).startswith("Zazu quiere usar permisos de administrador"),
        "sin tool.started": "tool.started" not in n["eventos"], "BLOCKED": "BLOCKED" in str(n.get("salida", "")),
    }, n)


def e_sin_clave():
    st, _ = pedir("POST", "/v1/runs", {"input": "di ok"}, clave=False)
    RESULTADOS["sin_clave"] = {"ok": st == 401, "status": st}
    print(("OK    " if st == 401 else "FALLA ") + f"sin_clave (HTTP {st})", flush=True)


ESCENARIOS = {"ok": e_ok, "aprobar": e_aprobar, "denegar": e_denegar, "parar": e_parar, "caduca": e_caduca,
              "entorno": e_entorno, "control": e_control, "modelo": e_modelo, "reanudar": e_reanudar, "sin_clave": e_sin_clave}

if __name__ == "__main__":
    for nombre in sys.argv[2:] or list(ESCENARIOS):
        try:
            if nombre.startswith("perfil:"):
                e_perfil(nombre.split(":", 1)[1])
                continue
            ESCENARIOS[nombre]()
        except Exception as e:   # un escenario roto no tapa los demás
            RESULTADOS[nombre] = {"ok": False, "fallos": [f"{type(e).__name__}: {e}"[:300]]}
            print(f"FALLA {nombre}  ← {type(e).__name__}: {str(e)[:200]}", flush=True)
    print(json.dumps(RESULTADOS, ensure_ascii=False, indent=1))
    sys.exit(0 if all(r["ok"] for r in RESULTADOS.values()) else 1)
