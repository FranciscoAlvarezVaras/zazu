"""«Qué ha hecho Zazu»: registro de actividad del vigía y sus flujos, vistos desde el Hub.

TODO pasa por el CLI `zv` con una lista cerrada de subcomandos (`registro --json`, `flujos --json`, `flujo <id> modo|pausa|reanuda`),
con una lista de argumentos (nunca un shell), entorno mínimo, tiempo máximo y tope de tamaño de la salida.
Lo que sale del CLI se trata como NO fiable: cada campo se valida contra listas cerradas o se limpia y se recorta
(el front además lo pinta como texto, jamás como HTML). Contrato: docs/contrato-registro.md. Solo biblioteca estándar.
"""
import json, os, re, subprocess, threading
from datetime import date, datetime, timedelta

import avisos
from avisos import AvisoError, limpio, enlace_ok

FUENTES = ("wa", "correo", "agenda", "tareas", "sistema")
TIPOS = ("leyo", "propuso", "escribio", "descarto", "fallo", "aviso")
MODOS_ITEM = ("sombra", "vivo")
ACTORES = ("vigia", "bandeja", "app")
MODOS_FLUJO = ("sombra", "activo")
ACCIONES_FLUJO = ("pausa", "reanuda", "modo")
FLUJO_OK = re.compile(r"[a-z0-9-]{1,40}")
ACCION_OK = re.compile(r"[a-z_-]{1,20}")
DIA_OK = re.compile(r"\d{4}-\d{2}-\d{2}")
N_MAX, N_DEF = 200, 100
MAX_SALIDA = 1_500_000          # bytes que se aceptan del CLI: más es un fallo, no un registro
T_LEER = float(os.environ.get("HUB_ZV_T_LEER") or 10)         # segundos (las pruebas los acortan)
T_ESCRIBIR = float(os.environ.get("HUB_ZV_T_ESCRIBIR") or 15)
_OCUPADO = threading.BoundedSemaphore(4)   # como mucho 4 `zv` a la vez: una pestaña desbocada no llena el servidor de procesos
_ESCRITURA = threading.Lock()              # los cambios de flujo van de uno en uno


class RegistroError(AvisoError):
    """Mismo molde que AvisoError: el servidor ya sabe convertirlo en {"error": …} con su código."""


# ───────── el CLI ─────────
def _correr(args, timeout):
    """Ejecuta `zv <args>` y devuelve (código, stdout). Sin shell, sin entorno heredado, stdin cerrado, stderr descartado."""
    if not _OCUPADO.acquire(timeout=3):
        raise RegistroError(503, "el vigía está ocupado; prueba dentro de un momento")
    try:
        home = avisos._home()
        env = {"PATH": f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8"}
        env.update({k: v for k, v in os.environ.items() if k.startswith("ZV_") or k == "PYTHONPATH"})
        try:
            p = subprocess.Popen([avisos.zv_bin()] + args, env=env, cwd=str(home), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
        except OSError:
            raise RegistroError(503, "no encuentro el comando del vigía (zv)")
        buf, estado = bytearray(), {"exceso": False}

        def leer():
            while True:
                try:
                    trozo = p.stdout.read(65536)
                except (OSError, ValueError):
                    return
                if not trozo:
                    return
                if len(buf) + len(trozo) > MAX_SALIDA:
                    estado["exceso"] = True
                    p.kill()
                    return
                buf.extend(trozo)

        t = threading.Thread(target=leer, daemon=True)
        t.start()
        try:
            p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            t.join(2)
            raise RegistroError(504, "el vigía tardó demasiado en contestar")
        t.join(3)
        p.stdout.close()
        if estado["exceso"]:
            raise RegistroError(502, "el vigía contestó con demasiados datos")
        return p.returncode, bytes(buf).decode("utf-8", "replace")
    finally:
        _OCUPADO.release()


def _json(texto):
    try:
        d = json.loads(texto)
    except (ValueError, RecursionError):
        raise RegistroError(502, "el vigía contestó algo que no entiendo")
    if not isinstance(d, dict):
        raise RegistroError(502, "el vigía contestó algo que no entiendo")
    return d


def _llamar(args, timeout=T_LEER):
    rc, out = _correr(args, timeout)
    d = _json(out)
    if rc or d.get("ok") is not True:
        raise RegistroError(502, "el vigía no pudo hacerlo")      # el motivo que dé el CLI no se repite: puede llevar rutas o datos
    return d


# ───────── validación de lo que sale del CLI ─────────
def _entero(v, tope=10 ** 7):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= tope else None


def _iso(v):
    """ISO 8601 válido (con o sin zona) → texto normalizado; si no, None."""
    if not isinstance(v, str) or len(v) > 40:
        return None
    try:
        d = datetime.fromisoformat(v.strip())
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=avisos.TZ)
    return d.isoformat(timespec="seconds")


def _texto(v, n):
    return limpio(v, n) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _item(x):
    if not isinstance(x, dict):
        return None
    i, ts = _entero(x.get("id"), 10 ** 12), _iso(x.get("ts"))
    fuente, tipo, modo = x.get("fuente"), x.get("tipo"), x.get("modo")
    titulo = _texto(x.get("titulo"), 160)
    if i is None or ts is None or fuente not in FUENTES or tipo not in TIPOS or modo not in MODOS_ITEM or not titulo:
        return None
    flujo = x.get("flujo")
    ref = _texto(x.get("ref"), 200)
    return {"id": i, "ts": ts, "actor": x.get("actor") if x.get("actor") in ACTORES else None, "fuente": fuente, "tipo": tipo, "modo": modo,
            "titulo": titulo, "detalle": _texto(x.get("detalle"), 240) or None,
            "flujo": flujo if isinstance(flujo, str) and FLUJO_OK.fullmatch(flujo) else None,
            "ref": ref or None, "enlace": enlace_ok(x.get("ref")) or None}     # solo http(s) llega a ser un enlace


def _resumen(w, dia):
    if not isinstance(w, dict):
        return None
    out = {"dia": dia}
    for t in TIPOS:
        n = _entero(w.get(t))
        if n is None:
            return None            # un número que falta o es raro: no se inventa ninguno
        out[t] = n
    pf = w.get("por_fuente")
    out["por_fuente"] = {}
    for f, d in (pf.items() if isinstance(pf, dict) else ()):
        if f in FUENTES and isinstance(d, dict):
            out["por_fuente"][f] = {t: n for t in TIPOS if (n := _entero(d.get(t))) is not None}
    return out


def hoy():
    return avisos.ahora().date()


def _parametros(dia, fuente, tipo, n):
    if dia in (None, ""):
        dia = hoy().isoformat()
    ok = isinstance(dia, str) and DIA_OK.fullmatch(dia)
    try:
        d = date.fromisoformat(dia) if ok else None
    except ValueError:
        d = None
    if d is None or d > hoy() + timedelta(days=1) or d < date(2020, 1, 1):
        raise RegistroError(400, "día no válido")
    if fuente not in (None, "") and fuente not in FUENTES:
        raise RegistroError(400, "fuente no válida")
    if tipo not in (None, "") and tipo not in TIPOS:
        raise RegistroError(400, "tipo no válido")
    if n in (None, ""):
        n = N_DEF
    else:
        try:
            n = int(str(n))
        except ValueError:
            raise RegistroError(400, "n no válido")
        if not 1 <= n <= N_MAX:
            raise RegistroError(400, "n no válido (de 1 a %d)" % N_MAX)
    return dia, fuente or None, tipo or None, n


def listar(dia=None, fuente=None, tipo=None, n=None):
    """GET /api/registro. Un fallo del CLI no es un «no hay nada»: devuelve ok:false con el motivo y sin items."""
    dia, fuente, tipo, n = _parametros(dia, fuente, tipo, n)
    base = {"dia": dia, "filtros": {"fuente": fuente, "tipo": tipo}, "n_pedido": n}
    args = ["registro", "--json", "--dia", dia, "-n", str(n)] + (["--fuente", fuente] if fuente else []) + (["--tipo", tipo] if tipo else [])
    try:
        d = _llamar(args)
    except RegistroError as e:
        return {"ok": False, "error": e.msg, "items": [], "resumen": None, **base}
    crudos = d.get("items") if isinstance(d.get("items"), list) else None
    if crudos is None:
        return {"ok": False, "error": "el vigía contestó algo que no entiendo", "items": [], "resumen": None, **base}
    items, omitidos = [], 0
    for x in crudos[:N_MAX * 2]:
        it = _item(x)
        if it is None or (fuente and it["fuente"] != fuente) or (tipo and it["tipo"] != tipo):
            omitidos += 1 if it is None else 0
            continue
        items.append(it)
    items.sort(key=lambda it: it["ts"], reverse=True)    # el contrato dice «más reciente primero»; no nos fiamos
    return {"ok": True, "items": items[:n], "resumen": _resumen(d.get("resumen"), dia), "total": len(items[:n]), "omitidos": omitidos,
            "hay_mas": len(crudos) >= n, **base}      # «puede haber más»: si llegaron tantas como se pidieron, quizá se cortó


# ───────── flujos ─────────
def _flujo(x):
    if not isinstance(x, dict):
        return None
    i = x.get("id")
    if not isinstance(i, str) or not FLUJO_OK.fullmatch(i) or x.get("modo") not in MODOS_FLUJO:
        return None
    acciones = [a for a in (x.get("acciones") if isinstance(x.get("acciones"), list) else []) if isinstance(a, str) and ACCION_OK.fullmatch(a)][:8]
    return {"id": i, "nombre": _texto(x.get("nombre"), 80) or i, "descripcion": _texto(x.get("descripcion"), 240),
            "fuente": x.get("fuente") if x.get("fuente") in FUENTES else None, "acciones": acciones, "modo": x["modo"],
            "pausado": x.get("pausado") is True, "ultimo": _iso(x.get("ultimo")), "disparos_7d": _entero(x.get("disparos_7d"))}


def _global():
    """Interruptor general del vigía (PAUSA / ENTREGA_ACTIVA / modo de cada fuente), de solo lectura. None si no se puede leer."""
    try:
        v = avisos.vigias()
    except Exception:
        return None
    modo = v.get("modo") if isinstance(v.get("modo"), dict) else {}
    return {"pausa": bool(v.get("pausa")), "entrega_real": bool(v.get("entrega_real")),
            "modo": {k: m for k, m in modo.items() if k in FUENTES and m in MODOS_FLUJO}}


def efectivo(f, g):
    """Lo que de verdad pasa con un flujo: pausado · prueba · vivo · desconocido (no se puede saber). `motivo` explica por qué una
    activación no escribe. Regla del vigía: PAUSA ausente + ENTREGA_ACTIVA + modo de la fuente activo."""
    if f["pausado"]:
        return "pausado", None
    if f["modo"] == "sombra":
        return "prueba", None
    if g is None:
        return "desconocido", "no he podido leer el interruptor general del vigía"
    if g["pausa"]:
        return "prueba", "el vigía entero está en pausa"
    if not g["entrega_real"]:
        return "prueba", "el interruptor general del vigía está apagado"
    m = g["modo"].get(f["fuente"] or "")
    if m is None:
        return "desconocido", "no sé si la fuente de este flujo está activa"
    if m != "activo":
        return "prueba", "la fuente de este flujo sigue en modo prueba"
    return "vivo", None


def _con_efectivo(lista, g):
    for f in lista:
        f["efectivo"], f["motivo"] = efectivo(f, g)
    return lista


def _leer_flujos():
    """Flujos validados + interruptor general. Lanza RegistroError con el código que toque (503/504/502)."""
    d = _llamar(["flujos", "--json"])
    crudos = d.get("flujos") if isinstance(d.get("flujos"), list) else None
    if crudos is None:
        raise RegistroError(502, "el vigía contestó algo que no entiendo")
    vistos, unicos = set(), []
    for f in (_flujo(x) for x in crudos[:60]):
        if f and f["id"] not in vistos:
            vistos.add(f["id"])
            unicos.append(f)
    g = _global()
    return {"ok": True, "flujos": _con_efectivo(unicos, g), "general": g, "omitidos": len(crudos[:60]) - len(unicos)}


def flujos():
    """GET /api/flujos. Un fallo no es «0 flujos»: devuelve ok:false con el motivo."""
    try:
        return _leer_flujos()
    except RegistroError as e:
        return {"ok": False, "error": e.msg, "flujos": [], "general": None}


def flujo_id(valor):
    s = valor if isinstance(valor, str) else ""
    if not FLUJO_OK.fullmatch(s):
        raise RegistroError(400, "id de flujo no válido")
    return s


def cambiar(id_, d, rol):
    """POST /api/flujos/<id>. Cuerpo: {accion:"pausa"|"reanuda"|"modo", modo?:"sombra"|"activo", confirmo?:true}.
    Pasar a «activo» exige confirmo:true y que lo haga el dueño. Devuelve el flujo ya cambiado, leído otra vez del vigía."""
    i = flujo_id(id_)
    if not isinstance(d, dict):
        raise RegistroError(400, "petición no válida")
    accion = d.get("accion")
    if accion not in ACCIONES_FLUJO:
        raise RegistroError(400, "acción no válida")
    args = ["flujo", i]
    if accion == "modo":
        modo = d.get("modo")
        if modo not in MODOS_FLUJO:
            raise RegistroError(400, "modo no válido")
        args += ["modo", modo]
        if modo == "activo":
            if rol != "admin":
                raise RegistroError(403, "no disponible")
            if d.get("confirmo") is not True:
                raise RegistroError(400, "Para pasar un flujo a Activo hay que confirmarlo")
            args.append("--confirmo")
    else:
        args.append(accion)
    with _ESCRITURA:
        antes = _leer_flujos()                     # el flujo tiene que existir: a `zv` solo llegan ids conocidos
        if not any(f["id"] == i for f in antes["flujos"]):
            raise RegistroError(404, "ese flujo no existe")
        _llamar(args, T_ESCRIBIR)
        try:
            despues = _leer_flujos()
        except RegistroError:
            # el cambio se hizo pero no puedo confirmarlo: se dice, no se inventa el estado
            raise RegistroError(502, "el cambio se envió al vigía pero no he podido comprobarlo; recarga la lista")
    f = next((x for x in despues["flujos"] if x["id"] == i), None)
    if f is None:
        raise RegistroError(502, "el vigía ya no lista ese flujo; recarga la lista")
    return {"ok": True, "flujo": f, "general": despues["general"]}
