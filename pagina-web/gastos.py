"""«Gastos y suscripciones» vistos desde el Hub: SOLO LECTURA.

TODO pasa por el CLI `zv` con una lista cerrada de subcomandos (`suscripciones --json`, `gastos --json [--mes AAAA-MM]`), con una lista de argumentos
(nunca un shell), entorno mínimo, tiempo máximo y tope de tamaño de la salida (la misma tubería segura de registro.py). El Hub no calcula ningún importe, ni
total, ni fecha de cobro: enseña lo que dice el vigía, validado campo a campo contra listas cerradas o limpiado y recortado (el front lo pinta como texto,
jamás como HTML). Un fallo se dice («no pude leer los gastos»), nunca se disfraza de «0 €». Contrato: docs/contrato-gastos.md. Solo biblioteca estándar.
"""
import json, math, os, re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import avisos, registro
from avisos import limpio
from registro import RegistroError

MONEDAS = ("EUR", "USD", "GBP")
PERIODOS = ("semanal", "mensual", "trimestral", "anual")
ESTADOS = ("activa", "nueva", "posible_cancelada", "solo_agenda")
BASES = ("correo", "agenda", "correo+agenda")
FUENTES_PROXIMO = ("estimado", "recibo", "agenda")
FASES = ("inicial", "al_dia")
MES_OK = re.compile(r"\d{4}-\d{2}")
CUENTA_OK = re.compile(r"[a-z0-9_-]{1,20}")
T_GASTOS = float(os.environ.get("HUB_GASTOS_T") or 6)          # segundos por llamada a zv (las pruebas lo acortan)
N_MAX = 200
SIN_SUSCRIPCIONES = "pendiente del vigilante de correo"
VIGIA_VIEJO = "el vigía todavía no sabe de gastos: falta actualizarlo"


# ───────── el CLI (lista cerrada) ─────────
def _args(que, mes=None):
    """Los únicos comandos que este módulo lanza. Cualquier otra cosa es un fallo del programa, no una opción."""
    if que == "suscripciones":
        return ["suscripciones", "--json"]
    if que == "gastos":
        if mes and not (isinstance(mes, str) and MES_OK.fullmatch(mes)):
            raise RegistroError(400, "mes no válido")
        return ["gastos", "--json"] + (["--mes", mes] if mes else [])
    raise RegistroError(400, "consulta no válida")


ACCIONES_SUB = ("cancelada", "quiero-cancelar", "sigue", "deshacer")
COMERCIO_OK = re.compile(r"[a-z0-9][a-z0-9 .&_+-]{0,59}")


def decidir(accion, comercio):
    """Decisión de Fran sobre una suscripción → `zv suscripcion <accion> <comercio> --json` (el vigía la anota en su config y recalcula)."""
    if accion not in ACCIONES_SUB or not isinstance(comercio, str) or not COMERCIO_OK.fullmatch(comercio.strip().lower()):
        raise RegistroError(400, "decisión no válida")
    rc, out = registro._correr(["suscripcion", accion, comercio.strip().lower(), "--json"], T_GASTOS * 3)
    try:
        d = json.loads(out)
    except (ValueError, RecursionError):
        d = None
    if not isinstance(d, dict) or rc or d.get("ok") is not True:
        raise RegistroError(502, "el vigía no pudo anotarlo")
    return {"ok": True, "mensaje": limpio(d.get("mensaje"), 80) or "Anotado"}


def _leer(que, mes=None):
    """Ejecuta una consulta y devuelve el dict del vigía. Lanza RegistroError con un motivo en español."""
    rc, out = registro._correr(_args(que, mes), T_GASTOS)
    try:
        d = json.loads(out)
    except (ValueError, RecursionError):
        d = None
    if not isinstance(d, dict):
        if rc == 2:
            raise RegistroError(503, VIGIA_VIEJO)         # argparse: «invalid choice» (un zv anterior a los gastos)
        raise RegistroError(502, "el vigía contestó algo que no entiendo")
    if rc or d.get("ok") is not True:
        raise RegistroError(502, "el vigía no pudo hacerlo")      # el motivo que dé el CLI no se repite: podría llevar rutas o datos
    return d


# ───────── validación de lo que sale del CLI ─────────
def _importe(v, tope=10 ** 7):
    """Número finito entre 0 y el tope, con 2 decimales; si no, None (no se inventa)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= tope:
        return None
    return round(float(v), 2)


def _neto(v, tope=10 ** 7):
    """Como _importe pero también negativo: un mes (o una categoría, o un comercio) con más reembolsos que cargos tiene neto < 0 y es un dato
    correcto. Antes se tiraba como «no entiendo lo que dice el vigía» y caía todo el bloque de gastos."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not -tope <= v <= tope:
        return None
    return round(float(v), 2)


def _entero(v, tope=10 ** 6):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= tope else None


def _fecha(v):
    if not isinstance(v, str) or len(v) < 10:
        return None
    try:
        return date.fromisoformat(v[:10]).isoformat()
    except ValueError:
        return None


def _moneda(v):
    return v if v in MONEDAS else None


def _dias_hasta(f):
    """Días desde hoy (reloj del Hub) hasta la fecha ISO; None si no hay fecha."""
    return (date.fromisoformat(f) - avisos.ahora().date()).days if f else None


def _cat(v):
    t = limpio(v, 30)
    return t if re.fullmatch(r"[\wáéíóúüñÁÉÍÓÚÜÑ ]{1,30}", t) else None


def _sub(x):
    if not isinstance(x, dict):
        return None
    estado = x.get("estado")
    nombre = limpio(x.get("nombre"), 60)
    if estado not in ESTADOS or not nombre:
        return None
    prox, ult = _fecha(x.get("proximo_cobro")), _fecha(x.get("ultimo_cobro"))
    periodo = x.get("periodo") if x.get("periodo") in PERIODOS else None
    sp = _importe(x.get("subida_pct"), 1000)
    cuenta = x.get("cuenta")
    return {"nombre": nombre, "importe": _importe(x.get("importe")), "moneda": _moneda(x.get("moneda")), "periodo": periodo,
            "mensual": _importe(x.get("mensual")) if periodo else None, "anual": _importe(x.get("anual")) if periodo else None,
            "proxima_fecha": prox, "dias": _dias_hasta(prox), "ultimo_cobro": ult,
            "proximo_fuente": x.get("proximo_fuente") if x.get("proximo_fuente") in FUENTES_PROXIMO else None, "estado": estado,
            "cancelar": x.get("cancelar") is True, "cargos": _entero(x.get("cargos")) or 0, "base": x.get("base") if x.get("base") in BASES else "correo",
            "comercio": limpio(x.get("comercio"), 60) or nombre, "categoria": _cat(x.get("categoria")), "cuenta": cuenta if isinstance(cuenta, str) and CUENTA_OK.fullmatch(cuenta) else None,
            "subida_pct": sp if sp and sp > 0 else None}


def _totales(w):
    out = {}
    for mon, t in (w.items() if isinstance(w, dict) else ()):
        if mon in MONEDAS and isinstance(t, dict):
            m, a, n = _importe(t.get("mensual")), _importe(t.get("anual")), _entero(t.get("n"))
            if m is not None and a is not None and n is not None:
                out[mon] = {"mensual": m, "anual": a, "n": n}
    return out


def _estado(w):
    w = w if isinstance(w, dict) else {}
    ult = w.get("ultima_lectura")
    try:
        ult = datetime.fromisoformat(ult).isoformat(timespec="seconds") if isinstance(ult, str) and len(ult) <= 40 else None
    except ValueError:
        ult = None
    return {"fase": w.get("fase") if w.get("fase") in FASES else None, "pendientes": _entero(w.get("pendientes")), "ultima_lectura": ult, "desde": _fecha(w.get("desde")),
            "cuentas_leidas": _entero(w.get("cuentas_leidas"), 50), "cuentas": _entero(w.get("cuentas"), 50)}


def suscripciones():
    """`zv suscripciones --json` validado. → {ok, items, totales, estado, omitidos}. Lanza RegistroError."""
    d = _leer("suscripciones")
    crudos = d.get("items") if isinstance(d.get("items"), list) else None
    if crudos is None:
        raise RegistroError(502, "el vigía contestó algo que no entiendo")
    items, vistos = [], set()
    for x in crudos[:N_MAX]:
        s = _sub(x)
        k = (s["nombre"].lower(), s["moneda"]) if s else None
        if s and k not in vistos:
            vistos.add(k)
            items.append(s)
    canc = [{"comercio": limpio(c.get("comercio"), 60), "desde": _fecha(c.get("desde"))} for c in (d.get("canceladas") if isinstance(d.get("canceladas"), list) else [])[:50]
            if isinstance(c, dict) and limpio(c.get("comercio"), 60)]
    cons = [{"comercio": limpio(c.get("comercio"), 60), "texto": limpio(c.get("texto"), 200), "acciones": [a for a in (c.get("acciones") or []) if a in ACCIONES_SUB][:3],
             "ia": c.get("ia") is True} for c in (d.get("consejos") if isinstance(d.get("consejos"), list) else [])[:8]
            if isinstance(c, dict) and limpio(c.get("comercio"), 60) and limpio(c.get("texto"), 200)]
    return {"ok": True, "items": items, "totales": _totales(d.get("totales")), "estado": _estado(d.get("estado")), "omitidos": len(crudos[:N_MAX]) - len(items),
            "canceladas": canc, "ocultas": _entero(d.get("ocultas")) or 0, "consejos": cons}


def _filas(w, campo, n):
    out = []
    for x in (w if isinstance(w, list) else ())[:n]:
        if not isinstance(x, dict):
            continue
        nom = limpio(x.get(campo), 60) if campo == "comercio" else _cat(x.get(campo))
        imp, mon = _neto(x.get("importe")), _moneda(x.get("moneda"))
        if nom and imp is not None and mon:
            out.append({campo: nom, "importe": imp, "moneda": mon, "importe_eur": _neto(x.get("importe_eur")), "n": _entero(x.get("n")) or 0})
    return out


def gastos_mes(mes=None):
    """`zv gastos --json` validado. → {ok, mes, total_eur, sin_convertir, por_categoria, por_comercio, anterior, …}. Lanza RegistroError."""
    d = _leer("gastos", mes)
    m = d.get("mes") if isinstance(d.get("mes"), str) and MES_OK.fullmatch(d.get("mes")) else None
    total = _neto(d.get("total_eur"))
    if m is None or total is None:
        raise RegistroError(502, "el vigía contestó algo que no entiendo")
    ant = d.get("mes_anterior") if isinstance(d.get("mes_anterior"), dict) else {}
    pres = d.get("presupuesto") if isinstance(d.get("presupuesto"), dict) else {}
    sin = {k: v for k, v in ((k, _neto(v)) for k, v in (d.get("sin_convertir") or {}).items() if k in MONEDAS) if v is not None} if isinstance(d.get("sin_convertir"), dict) else {}
    return {"ok": True, "mes": m, "total_eur": total, "sin_convertir": sin, "por_categoria": _filas(d.get("por_categoria"), "categoria", 12),
            "por_comercio": _filas(d.get("por_comercio"), "comercio", 5),
            "anterior": {"mes": ant.get("mes") if isinstance(ant.get("mes"), str) and MES_OK.fullmatch(ant.get("mes")) else None, "total_eur": _neto(ant.get("total_eur")),
                         "total_eur_a_esta_altura": _neto(ant.get("total_eur_a_esta_altura"))},
            "sin_clasificar": _entero(d.get("sin_clasificar")), "dudosos": _entero(d.get("dudosos")),
            "presupuesto": {"tope_activo": pres.get("tope_activo") is True, "tope": _importe(pres.get("tope")) if pres.get("tope_activo") is True else None, "usado": _importe(pres.get("usado"))},
            "estado": _estado(d.get("estado"))}


# ───────── el tablero «Suscripciones» ─────────
def tablero():
    """Lo que necesita tableros._tablero_suscripciones: las suscripciones y el resumen de gastos del mes, leídos a la vez. Si fallan las suscripciones, falla el
    tablero (ok:false con el motivo); si solo fallan los gastos, el tablero sigue y la parte de gastos dice por qué no hay cifras."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        fs, fg = ex.submit(suscripciones), ex.submit(gastos_mes)
        try:
            s = fs.result()
        except RegistroError as e:
            return {"ok": False, "error": e.msg}
        except Exception as e:                                         # nunca tumbar el servidor por un fallo raro
            return {"ok": False, "error": f"No pude leer las suscripciones ({type(e).__name__})"}
        try:
            g = fg.result()
        except RegistroError as e:
            g = {"ok": False, "error": e.msg}
        except Exception as e:
            g = {"ok": False, "error": f"No pude leer los gastos ({type(e).__name__})"}
    nota = None
    if not s["items"]:
        nota = ("todavía estoy leyendo tu correo de los últimos meses" if s["estado"]["fase"] == "inicial" else "no he detectado suscripciones en tu correo")
    return {"ok": True, "items": s["items"], "totales": s["totales"], "estado": s["estado"], "gastos": g, "nota": nota, "omitidos": s["omitidos"],
            "canceladas": s["canceladas"], "ocultas": s["ocultas"], "consejos": s["consejos"]}
