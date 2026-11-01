"""«Dinero» de una invitada (nivel Familia, con su Gmail conectado): sus gastos y suscripciones sacados de los recibos de SU Gmail.

· Lee con la carpeta de gog de ELLA (nunca la de Fran) y en solo lectura: busca hilos con pinta de recibo de los últimos 90 días (con tope de páginas,
  de cuerpos abiertos y de tiempo) en un hilo aparte, para no bloquear el servidor. Lo que falte se sigue leyendo en la siguiente pasada.
· El extractor es el de Fran, sin IA: zazu/vigia/zv/recibos.py (importe, comercio, fecha, categoría; recibo frente a publicidad). Las suscripciones
  salen de zv/gastos.detectar, el mismo detector de cobros repetidos. Un «dudoso» no se apunta (aquí no hay modelo que lo aclare).
· El correo es dato de terceros y NO fiable: nada de él se interpreta como orden; un hilo con frases que parecen órdenes (zv/escudo) no se apunta.
  Solo se guarda lo extraído —comercio ya limpio, importe, moneda, fecha, tipo y categoría— más el id del hilo (para no volver a abrirlo). Nunca
  el cuerpo, ni el asunto, ni HTML.
· Todo va a <su carpeta>/dinero.json (0600). Sus elecciones (qué ver, presupuesto y moneda) las guarda el servidor en users.json.
Solo biblioteca estándar."""
import json, os, re, sys, threading, time, uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
MONEDAS = ("EUR", "USD", "GBP")
VER = ("gastos", "suscripciones", "presupuesto")
VER_DEF = {"gastos": True, "suscripciones": True, "presupuesto": False}
DIAS = 90                     # ventana de correo
POR_PAGINA, PAGINAS = 25, 4   # hasta 100 hilos por cuenta en cada pasada
MAX_CUERPOS = 40              # hilos abiertos por pasada
T_MAX = 75                    # segundos por pasada
MAX_CUENTAS = 3
MAX_IMPORTE_CENT = 500000     # más de 5.000 € en un correo: no se apunta (como el «importe dudoso» de Fran)
REFRESCO = 6 * 3600           # al abrir Dinero se vuelve a mirar si lo último tiene más de 6 h
SEGUIR = 60                   # si la pasada anterior quedó a medias, la siguiente puede empezar al minuto
MANUAL = 300                  # «Actualizar» a mano: como mucho cada 5 minutos
ID_OK = re.compile(r"[A-Za-z0-9_-]{6,64}")
NOMBRE_OK = re.compile(r"[\w ÁÉÍÓÚÜÑáéíóúüñ&.'+-]{2,40}")
SIN_GMAIL = "Para ver tu dinero, conecta tu Gmail en Tu espacio. Solo leo los recibos; nunca escribo ni borro nada."
NO_PUDE = "No pude leer tu Gmail ahora mismo. Lo vuelvo a intentar más tarde."

_ZV = Path(__file__).resolve().parent.parent / "zazu/vigia"
_LOCK = threading.Lock()
_EN_CURSO = set()                   # carpetas con una lectura en marcha
_SEM = threading.BoundedSemaphore(2)   # como mucho dos invitadas leyendo a la vez


def _zv():
    """El extractor de Fran (recibos), el detector de suscripciones (gastos), el escudo y la búsqueda de recibos de la configuración por defecto."""
    if str(_ZV) not in sys.path:
        sys.path.append(str(_ZV))
    from zv import config, escudo, gastos, recibos
    return recibos, gastos, escudo, config.DEFECTO["gastos"]


def hoy():
    return datetime.now(TZ).date()


# ───────── elecciones ─────────
def eleccion(v):
    """Lo guardado en users.json, normalizado. Sin elegir todavía: elegido=False (la pantalla pregunta primero)."""
    v = v if isinstance(v, dict) else {}
    ver = v.get("ver") if isinstance(v.get("ver"), dict) else {}
    p = v.get("presupuesto")
    p = round(float(p), 2) if isinstance(p, (int, float)) and not isinstance(p, bool) and 0 < p <= 1_000_000 else None
    return {"elegido": v.get("elegido") is True, "ver": {k: ver[k] if isinstance(ver.get(k), bool) else VER_DEF[k] for k in VER},
            "presupuesto": p, "moneda": v.get("moneda") if v.get("moneda") in MONEDAS else "EUR"}


def validar(d):
    """Lo que manda la pantalla «¿Qué quieres ver?». → elección limpia. Lanza ValueError con el motivo en español."""
    if not isinstance(d, dict) or not isinstance(d.get("ver"), dict):
        raise ValueError("Dime qué quieres ver")
    ver = {k: d["ver"].get(k) is True for k in VER}
    if not any(ver.values()):
        raise ValueError("Elige al menos una cosa para ver")
    mon = d.get("moneda") or "EUR"
    if mon not in MONEDAS:
        raise ValueError("Esa moneda no la conozco: elige euros, dólares o libras")
    p = d.get("presupuesto")
    if isinstance(p, str):
        p = p.strip().replace("€", "").replace(" ", "")
        p = p.replace(".", "").replace(",", ".") if "," in p else p
        try:
            p = float(p) if p else None
        except ValueError:
            raise ValueError("El presupuesto tiene que ser una cifra, por ejemplo 400") from None
    if ver["presupuesto"]:
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 < p <= 1_000_000:
            raise ValueError("Pon la cifra de tu presupuesto al mes, por ejemplo 400")
        p = round(float(p), 2)
    else:
        p = None
    return {"elegido": True, "ver": ver, "presupuesto": p, "moneda": mon}


# ───────── el archivo de cada invitada ─────────
def ruta(casa):
    return Path(casa) / "dinero.json"


def cargar(casa):
    try:
        d = json.loads(ruta(casa).read_text())
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    return {"gastos": [g for g in d.get("gastos") or [] if isinstance(g, dict)], "hilos": d.get("hilos") if isinstance(d.get("hilos"), dict) else {},
            "leido": d.get("leido") if isinstance(d.get("leido"), str) else None, "inicio": float(d.get("inicio") or 0), "fin": float(d.get("fin") or 0),
            "parcial": d.get("parcial") is True, "error": d.get("error") if isinstance(d.get("error"), str) else None}


def guardar(casa, st):
    p = ruta(casa)
    tmp = p.with_name(f".dinero.{uuid.uuid4().hex[:8]}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, p)


# ───────── leer el correo (en un hilo aparte) ─────────
def _lista(d):
    if isinstance(d, list):
        return d
    for k in ("threads", "messages", "items"):
        if isinstance(d, dict) and isinstance(d.get(k), list):
            return d[k]
    return []


def _textos(gog, acc, hid, sin_html):
    """Texto plano de cada mensaje del hilo (hasta 6). Solo se analiza aquí: nada de esto se guarda."""
    d = gog(["gmail", "thread", "get", hid, "--full", "--sanitize-content"], acc)
    t = d.get("thread", d) if isinstance(d, dict) else {}
    out = []
    for m in (t.get("messages") or [])[:6]:
        if isinstance(m, dict):
            txt = re.sub(r"\s+", " ", sin_html(str(m.get("body") or m.get("snippet") or "")[:80000]))[:14000].strip()
            if txt:
                out.append(txt)
    return out


def _nombre(R, com):
    n = re.sub(r"[\x00-\x1f\x7f]+", " ", str(com.nombre or "")).strip()
    return n if NOMBRE_OK.fullmatch(n) else (R.titulo(com.clave) or "Comercio")[:40]


def _apuntar(st, h, textos, dia):
    """Analiza los mensajes de un hilo con el extractor de Fran y apunta los recibos claros. → gastos nuevos."""
    R, _G, esc, _cfg = _zv()
    asunto = re.sub(r"\s+", " ", str(h.get("subject") or ""))[:300]
    if esc.sospechoso(f"{asunto} {' '.join(textos)} {str(h.get('from') or '')[:120]}"):
        return 0                          # trae frases que parecen órdenes: es dato, no se apunta
    vistos = {(g["comercio"], g["moneda"], g["importe_cent"], g["fecha"]) for g in st["gastos"]}
    nuevos = 0
    for texto in textos:
        r = R.analizar(h, texto, dia)
        if r.veredicto != "recibo" or not r.comercio or r.comercio.clave == "desconocido" or not 0 < r.importe_cent <= MAX_IMPORTE_CENT or r.moneda not in MONEDAS:
            continue                      # publicidad, dudoso (sin modelo que lo aclare), sin importe o de quién no se sabe: no se apunta
        com = r.comercio
        cat = com.categoria or R.categoria_por_palabras(f"{asunto} {com.nombre}") or ("suscripciones" if r.tipo == "renovacion" else "otros")
        g = {"hilo": str(h.get("id")), "comercio": R.clave_de(com.clave) or com.clave[:40], "nombre": _nombre(R, com), "importe_cent": int(r.importe_cent),
             "moneda": r.moneda, "fecha": r.fecha.isoformat(), "tipo": r.tipo if r.tipo in R.TIPOS else "cargo",
             "categoria": cat if cat in R.CATEGORIAS else "otros", "proximo": r.proximo.isoformat() if r.proximo else None}
        k = (g["comercio"], g["moneda"], g["importe_cent"], g["fecha"])
        if k in vistos:
            continue                      # el mismo cobro por dos correos cuenta una vez
        vistos.add(k)
        st["gastos"].append(g)
        nuevos += 1
    return nuevos


def leer_correo(casa, cuentas, gog, sin_html):
    """Una pasada por el Gmail de la invitada. `gog(args, cuenta)` ya va con SU carpeta y en solo lectura. Escribe dinero.json."""
    R, _G, _esc, cfg = _zv()
    st = cargar(casa)
    dia = hoy()
    t_fin = time.time() + T_MAX
    q = re.sub(r"\s+", " ", f"{cfg['query']} {cfg.get('excluir', '')} after:{dia - timedelta(days=DIAS):%Y/%m/%d}").strip()
    abiertos, parcial, fallos, cuentas = 0, False, 0, list(cuentas)[:MAX_CUENTAS]
    for acc in cuentas:
        hilos, token = [], None
        try:
            for _ in range(PAGINAS):
                d = gog(["gmail", "search", q, "--max", str(POR_PAGINA)] + (["--page", token] if token else []), acc)
                hilos += _lista(d)
                token = d.get("nextPageToken") if isinstance(d, dict) else None
                if not token:
                    break
        except Exception:
            if not hilos:
                fallos += 1
                continue
            parcial = True
        for h in hilos:
            if not isinstance(h, dict) or not ID_OK.fullmatch(str(h.get("id") or "")):
                continue
            hid, n = str(h["id"]), h.get("messageCount") if isinstance(h.get("messageCount"), int) else 1
            if st["hilos"].get(hid) == n:
                continue                  # ya mirado y sin mensajes nuevos
            if not R.candidato(str(h.get("subject") or ""), str(h.get("from") or ""))[0]:
                st["hilos"][hid] = n      # ni se abre: por el asunto no es un cobro
                continue
            if abiertos >= MAX_CUERPOS or time.time() > t_fin:
                parcial = True
                break
            abiertos += 1
            try:
                textos = _textos(gog, acc, hid, sin_html)
            except Exception:
                parcial = True
                continue
            st["hilos"][hid] = n
            _apuntar(st, h, textos, dia)
    limite = (dia - timedelta(days=400)).isoformat()
    st["gastos"] = sorted((g for g in st["gastos"] if g.get("fecha", "") >= limite), key=lambda g: g["fecha"])[-600:]
    if len(st["hilos"]) > 3000:
        st["hilos"] = dict(list(st["hilos"].items())[-3000:])
    todas_fallan = bool(cuentas) and fallos == len(cuentas)
    st.update(fin=time.time(), parcial=parcial or todas_fallan, error=NO_PUDE if todas_fallan else None)
    if not todas_fallan:
        st["leido"] = datetime.now(TZ).isoformat(timespec="seconds")
    guardar(casa, st)
    return st


def lanzar(casa, cuentas, gog, sin_html, manual=False):
    """Empieza una lectura en segundo plano si toca. → (True, '') si está leyendo (ya o ahora), (False, motivo) si no toca."""
    if not cuentas:
        return False, SIN_GMAIL
    st = cargar(casa)
    ahora = time.time()
    with _LOCK:
        if casa in _EN_CURSO:
            return True, ""
        if manual:
            if ahora - st["inicio"] < MANUAL and not st["parcial"]:
                return False, f"Lo acabo de mirar. Vuelve a probar en {max(1, round((MANUAL - (ahora - st['inicio'])) / 60))} min."
        elif st["leido"] and not (st["parcial"] and ahora - st["fin"] > SEGUIR) and ahora - st["fin"] < REFRESCO:
            return False, ""
        elif not st["leido"] and st["fin"] and ahora - st["fin"] < SEGUIR:
            return False, ""          # la anterior falló hace nada: no insistir en bucle
        _EN_CURSO.add(casa)
    st["inicio"] = ahora
    guardar(casa, st)

    def trabajo():
        try:
            with _SEM:
                leer_correo(casa, cuentas, gog, sin_html)
        except Exception as e:
            print(f"dinero de invitado: la lectura falló ({type(e).__name__})", file=sys.stderr)   # sin detalles: podrían traer datos
            try:
                s = cargar(casa)
                s.update(fin=time.time(), error=NO_PUDE)
                guardar(casa, s)
            except OSError:
                pass
        finally:
            with _LOCK:
                _EN_CURSO.discard(casa)
    threading.Thread(target=trabajo, name="dinero-invitada", daemon=True).start()
    return True, ""


def leyendo(casa):
    with _LOCK:
        return casa in _EN_CURSO


# ───────── lo que ve la pantalla ─────────
def _e(cent):
    return round(cent / 100, 2)


def _neto(fs):
    return sum(-g["importe_cent"] if g["tipo"] == "reembolso" else g["importe_cent"] for g in fs)


def resumen(st, el, dia=None):
    """Total del mes, categorías, últimos gastos, suscripciones y presupuesto, solo lo que ella eligió. Importes en su moneda; lo de otras
    monedas se dice aparte (sin convertir: no se inventa un cambio)."""
    _R, G, _esc, _cfg = _zv()
    dia = dia or hoy()
    mon, mes = el["moneda"], dia.strftime("%Y-%m")
    fs = st["gastos"]
    del_mes = [g for g in fs if g["fecha"].startswith(mes) and g["fecha"] <= dia.isoformat()]
    total = _neto([g for g in del_mes if g["moneda"] == mon])
    out = {"mes": mes, "moneda": mon}
    if el["ver"]["gastos"]:
        cats = {}
        for g in del_mes:
            if g["moneda"] == mon:
                c = cats.setdefault(g["categoria"], [0, 0])
                c[0] += -g["importe_cent"] if g["tipo"] == "reembolso" else g["importe_cent"]
                c[1] += 1
        otras = {}
        for g in del_mes:
            if g["moneda"] != mon:
                otras[g["moneda"]] = otras.get(g["moneda"], 0) + (-g["importe_cent"] if g["tipo"] == "reembolso" else g["importe_cent"])
        ult = sorted(fs, key=lambda g: g["fecha"], reverse=True)[:8]
        out["gastos"] = {"total": _e(total), "n": sum(1 for g in del_mes if g["moneda"] == mon and g["tipo"] != "reembolso"),
                         "categorias": [{"categoria": k, "importe": _e(v[0]), "n": v[1]} for k, v in sorted(cats.items(), key=lambda x: -x[1][0])],
                         "otras_monedas": [{"moneda": k, "importe": _e(v)} for k, v in sorted(otras.items())],
                         "ultimos": [{"nombre": g["nombre"], "importe": _e(g["importe_cent"]), "moneda": g["moneda"], "fecha": g["fecha"], "categoria": g["categoria"],
                                      "reembolso": g["tipo"] == "reembolso"} for g in ult]}
    if el["ver"]["suscripciones"]:
        filas = [dict(g, id=i, estado="ok", dup_de=None, cuenta="") for i, g in enumerate(fs)]
        subs = G.detectar(filas, dia, None)
        items = [{"nombre": s.nombre, "importe": _e(s.importe) if s.importe else None, "moneda": s.moneda, "periodo": s.periodo,
                  "mensual": _e(G.eq_mensual(s.importe, s.periodo)) if s.importe and s.periodo else None,
                  "proximo": s.proximo.isoformat() if s.proximo else None, "dias": (s.proximo - dia).days if s.proximo else None, "estado": s.estado,
                  "categoria": s.categoria} for s in subs if s.estado != "solo_agenda"][:30]
        vivas = [x for x in items if x["estado"] in ("activa", "nueva")]
        out["suscripciones"] = {"items": items, "activas": len(vivas),
                                "al_mes": round(sum(x["mensual"] or 0 for x in vivas if x["moneda"] == mon), 2)}
    if el["ver"]["presupuesto"] and el["presupuesto"]:
        out["presupuesto"] = {"tope": el["presupuesto"], "usado": _e(total), "pasado": total > el["presupuesto"] * 100}
    return out


def vista(casa, el, cuentas):
    """Respuesta de GET /api/inv/dinero (y de elegir/actualizar)."""
    if not cuentas:
        return {"ok": True, "gmail": False, "mensaje": SIN_GMAIL, "eleccion": el}
    st = cargar(casa)
    lee = leyendo(casa)
    return {"ok": True, "gmail": True, "eleccion": el, "leyendo": lee, "leido": st["leido"], "parcial": st["parcial"],
            "error": None if lee else st["error"], "resumen": resumen(st, el) if el["elegido"] and st["leido"] else None}
