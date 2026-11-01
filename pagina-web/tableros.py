"""Tableros (estilo CRM) leídos de las notas del Cerebro: Proyectos, Candidaturas, Programación y Carnet.

LEER: el frontmatter de las notas de «30 Notas» (tipo, estado, siguiente, plazo, empresa, puesto, tags…). Las columnas y
los estados válidos salen de «90 Sistema/SCHEMA.md» (tabla «Propiedades»); si no se puede leer, caen a las constantes de
ESTADOS_BASE (que una prueba compara con SCHEMA y con las bases de Obsidian).
ESCRIBIR (solo dos operaciones, siempre bajo «30 Notas», sin seguir accesos directos):
  · mover(): cambia ÚNICAMENTE la línea `estado:` del frontmatter (+ una línea arriba de «## Historial» y una en log.md).
  · paso():  marca/desmarca UNA casilla `- [ ]` de «## Pasos».
  Ambas: lectura → comprobación de la versión (mtime en ms, 409 si cambió) → fichero temporal en la misma carpeta →
  segunda comprobación justo antes de `os.replace` → reemplazo atómico. Solo biblioteca estándar.
"""
import calendar as _cal
import os, re, tempfile, threading, time, unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import archivos as A
import privado

TZ = ZoneInfo("Europe/Madrid")
CARPETA = "30 Notas"
MAX_NOTA = 1024 * 1024          # una nota de más de 1 MB no se toca
MAX_LEER = 256 * 1024
MAX_NOTAS = 4000
ESTADOS_BASE = {"proyecto": ["activo", "esperando", "en pausa", "hecho"],
                "candidatura": ["por enviar", "enviada", "prueba", "entrevista", "oferta", "rechazada", "descartada"],
                "idea": ["nueva", "aparcada"]}
TERMINALES = {"hecho", "rechazada", "descartada", "aparcada"}
TAGS_PROG = {"programacion", "codigo", "dev"}
TABLEROS = (
    {"id": "proyectos", "titulo": "Proyectos", "carpeta": "30 Notas/Proyectos", "tipos": ("proyecto",)},
    {"id": "candidaturas", "titulo": "Candidaturas", "carpeta": "30 Notas/Candidaturas", "tipos": ("candidatura",)},
    {"id": "programacion", "titulo": "Programación", "carpeta": "30 Notas", "tipos": ("idea", "proyecto"), "tags": TAGS_PROG},
    {"id": "carnet", "titulo": "Carnet", "especial": "carnet"},
    {"id": "personas", "titulo": "Personas", "especial": "personas"},
    {"id": "viajes", "titulo": "Viajes", "especial": "viajes"},
    {"id": "fechas", "titulo": "Fechas clave", "especial": "fechas"},
    {"id": "suscripciones", "titulo": "Suscripciones", "especial": "suscripciones"},
)
CARPETA_PERSONAS = "30 Notas/Personas y empresas"
CARPETA_VIAJES = "40 Compartido/Importante/Viajes"
SIN_SUSCRIPCIONES = "pendiente del vigilante de correo"
NOTA_CARNET = "Carnet de conducir"
LOCK = threading.RLock()
_TTL = float(os.environ.get("HUB_TABLEROS_TTL", "15"))
_cache = {"t": 0.0, "v": None, "k": None}
_parse = {}                      # (ruta, mtime_ns, size) → ficha básica


class TableroError(Exception):
    def __init__(self, code, msg, **extra):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, extra


# ───────────────────────── utilidades ─────────────────────────
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).casefold()
    return "".join(c for c in s if not unicodedata.combining(c))


def raiz(vault):
    """Raíz de solo «30 Notas»: Raiz.ruta no sale de ella, no sigue accesos directos y esconde lo oculto."""
    return A.Raiz("tableros", Path(vault), solo=(CARPETA,))


def hoy():
    return datetime.now(TZ).date()


def _ms(st):
    return st.st_mtime_ns // 1_000_000


def frontmatter(texto):
    """→ (dict, ok). Admite BOM, CRLF, listas en línea `[a, b]` y listas en bloque (como las escribe Obsidian)."""
    t = str(texto or "").lstrip("\ufeff")
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", t, re.S)
    if not m:
        return {}, False
    fm, clave = {}, None
    for ln in m.group(1).splitlines():
        k = re.match(r"^([A-Za-z_][\w\-]*)[ \t]*:[ \t]*(.*?)[ \t]*$", ln)
        if k:
            clave, v = k.group(1), k.group(2)
            if v == "":
                fm[clave] = ""
            elif v.startswith("[") and v.endswith("]"):
                fm[clave] = [_escalar(x) for x in _trocear(v[1:-1]) if x.strip()]
            else:
                fm[clave] = _escalar(v)
            continue
        b = re.match(r"^[ \t]*-[ \t]+(.*?)[ \t]*$", ln)
        if b and clave is not None and (fm.get(clave) == "" or isinstance(fm.get(clave), list)):
            if not isinstance(fm[clave], list):
                fm[clave] = []
            fm[clave].append(_escalar(b.group(1)))
    return fm, True


def _trocear(s):
    out, cur, q = [], "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _escalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return v


# ───────────────────────── SCHEMA ─────────────────────────
_schema = {"k": None, "v": None}


def estados_schema(vault):
    """{tipo: [estados]} de la tabla «Propiedades» de SCHEMA.md. Cae a ESTADOS_BASE por tipo si falta o no se entiende."""
    ruta = Path(vault) / "90 Sistema/SCHEMA.md"
    try:
        st = ruta.stat()
        k = (str(ruta), st.st_mtime_ns)
        if _schema["k"] == k:
            return _schema["v"]
        t = ruta.read_text(encoding="utf-8")[:300_000]
    except (OSError, UnicodeDecodeError):
        return {k: list(v) for k, v in ESTADOS_BASE.items()}
    sec = re.search(r"^## Propiedades.*?(?=^## |\Z)", t, re.S | re.M)
    out = {}
    for ln in (sec.group(0).splitlines() if sec else []):
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 3 or "estado" not in [x.strip() for x in c[1].split(",")]:
            continue
        vals = [x.strip() for x in re.sub(r"\([^)]*\)", "", c[2]).split("·") if x.strip()]
        if vals and re.fullmatch(r"[a-z]+", c[0]):
            out[c[0]] = vals
    res = {k: list(v) for k, v in ESTADOS_BASE.items()}
    res.update(out)
    _schema["k"], _schema["v"] = k, res
    return res


# ───────────────────────── lectura de notas ─────────────────────────
def _leer_bytes(p, tope=MAX_LEER):
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        return os.read(fd, tope + 1)[:tope]
    finally:
        os.close(fd)


def pasos_de(texto):
    """[(linea 1-based, hecho, texto)] de las casillas bajo «## Pasos» (las vacías de la plantilla no cuentan)."""
    out, dentro = [], False
    for i, ln in enumerate(re.findall(r"[^\n]*\n|[^\n]+", texto), 1):
        s = ln.rstrip("\r\n")
        if re.match(r"^##[ \t]+", s):
            dentro = bool(re.match(r"^##[ \t]+Pasos[ \t]*$", s))
            continue
        if dentro:
            m = re.match(r"^[ \t]*[-*+][ \t]+\[([ xX])\][ \t]+(\S.*?)[ \t]*$", s)
            if m:
                out.append((i, m.group(1) != " ", m.group(2)))
    return out


def seccion(texto, patron, maximo=12, ancho=220):
    """Viñetas de la primera sección `## <patron…>` (texto sin el «- »)."""
    out, dentro = [], False
    for ln in texto.splitlines():
        if re.match(r"^##[ \t]+", ln):
            if dentro:
                break
            dentro = bool(re.match(rf"^##[ \t]+{patron}", ln, re.I))
            continue
        m = re.match(r"^[ \t]*[-*+][ \t]+(?:\[[ xX]\][ \t]+)?(\S.*?)[ \t]*$", ln) if dentro else None
        if m and len(out) < maximo:
            out.append(m.group(1)[:ancho])
    return out


def _fecha(v):
    try:
        return date.fromisoformat(str(v).strip()[:10]) if re.match(r"^\d{4}-\d{2}-\d{2}", str(v or "").strip()) else None
    except ValueError:
        return None


def _url(v):
    m = re.match(r"^https?://[^\s<>\"']{1,300}", str(v or "").strip(), re.I)
    return m.group(0) if m else None


def _ficha(rel, p, st, estados):
    """Ficha de una nota a partir de su frontmatter (con caché por mtime/tamaño). Nunca lanza: una nota rota = ficha con aviso."""
    k = (str(p), st.st_mtime_ns, st.st_size)
    base = _parse.get(k)
    if base is None:
        if len(_parse) > 3000:
            _parse.clear()
        aviso, fm, texto = None, {}, ""
        try:
            texto = _leer_bytes(p).decode("utf-8")
            fm, ok = frontmatter(texto)
            if not ok:
                aviso = "propiedades ilegibles"
        except UnicodeDecodeError:
            aviso = "la nota no es UTF-8"
        except OSError:
            aviso = "no se pudo leer"
        ps = pasos_de(texto)
        tags = fm.get("tags")
        tags = [t.strip().lstrip("#") for t in (tags if isinstance(tags, list) else [tags] if tags else []) if str(t).strip()][:12]
        plazo = _fecha(fm.get("plazo"))
        base = {"titulo": p.stem, "tipo": str(fm.get("tipo") or "").strip() or None, "estado": str(fm.get("estado") or "").strip(),
                "siguiente": str(fm.get("siguiente") or "")[:300] or None, "plazo": plazo.isoformat() if plazo else None,
                "empresa": str(fm.get("empresa") or "")[:120] or None, "puesto": str(fm.get("puesto") or "")[:160] or None,
                "ciudad": str(fm.get("ciudad") or "")[:80] or None, "enlace": _url(fm.get("enlace")), "tags": tags,
                "pasos": {"hechos": sum(1 for x in ps if x[1]), "total": len(ps)}, "aviso": aviso, "_texto": texto if p.stem == NOTA_CARNET else None,
                "_relacion": str(fm.get("relacion") or "")[:60], "_cumple": str(fm.get("cumple") or "").strip(),
                "_aliases": [str(a)[:80] for a in (fm.get("aliases") if isinstance(fm.get("aliases"), list) else [fm.get("aliases")] if fm.get("aliases") else [])][:8]}
        _parse[k] = base
    c = {kk: vv for kk, vv in base.items() if not kk.startswith("_")}
    c["ruta"] = rel
    c["mtime"] = _ms(st)
    ok_est = estados.get(c["tipo"] or "", [])
    c["mover_a"] = list(ok_est)
    if c["estado"] and ok_est and c["estado"] not in ok_est and not c["aviso"]:
        c["aviso"] = f"estado no válido: «{c['estado'][:30]}»"
    pl = _fecha(c["plazo"])
    c["dias"] = (pl - hoy()).days if pl else None
    c["vencido"] = bool(pl and pl < hoy() and c["estado"] not in TERMINALES)
    c["obsidian"] = "obsidian://open?vault=Cerebro&file=" + quote(rel[:-3] if rel.endswith(".md") else rel, safe="")
    return c, base


def _recorrer(vault, carpeta):
    """(ruta relativa, Path, stat) de las .md bajo `carpeta` (sin accesos directos, sin ocultos). Lanza FileNotFoundError si no existe."""
    r = raiz(vault)
    base = r.ruta(carpeta)
    if not base.is_dir():
        raise FileNotFoundError(f"No encuentro la carpeta «{carpeta}»")
    n = 0
    for e in A.recorrer(r, carpeta):
        if not e.name.lower().endswith(".md") or e.is_dir(follow_symlinks=False):
            continue
        n += 1
        if n > MAX_NOTAS:
            return
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        p = Path(e.path)
        yield r.rel(p), p, st


def _col_titulo(e):
    return e[:1].upper() + e[1:]


def _tablero_kanban(vault, t, estados):
    tipos = t["tipos"]
    tags = t.get("tags")
    cols_ids = []
    for tp in tipos:
        for e in estados.get(tp, []):
            if e not in cols_ids:
                cols_ids.append(e)
    cols = {e: [] for e in cols_ids}
    otros = []
    for rel, p, st in _recorrer(vault, t["carpeta"]):
        c, _ = _ficha(rel, p, st, estados)
        if tags is not None:
            if c["tipo"] not in tipos or not any(norm(x).split("/")[0] in tags for x in c["tags"]):
                continue
        elif c["tipo"] not in tipos:
            if c["aviso"] == "propiedades ilegibles":
                otros.append(c)       # nota rota dentro de la carpeta del tablero: se ve, con su aviso
            continue
        (cols[c["estado"]] if c["estado"] in cols and c["estado"] in estados.get(c["tipo"], []) else otros).append(c)
    clave = lambda c: (c["plazo"] or "9999-12-31", norm(c["titulo"]))
    columnas = [{"id": e, "titulo": _col_titulo(e), "tarjetas": sorted(cols[e], key=clave)} for e in cols_ids]
    if otros:
        columnas.append({"id": "_otros", "titulo": "Sin estado válido", "tarjetas": sorted(otros, key=clave)})
    return {"id": t["id"], "titulo": t["titulo"], "tipo": "kanban", "ok": True, "columnas": columnas,
            "total": sum(len(c["tarjetas"]) for c in columnas)}


def _tablero_carnet(vault, estados, ctx):
    sub = "30 Notas/Proyectos"
    for rel, p, st in _recorrer(vault, sub):
        if norm(p.stem) == norm(NOTA_CARNET):
            c, base = _ficha(rel, p, st, estados)
            texto = base.get("_texto") or _leer_bytes(p).decode("utf-8", "replace")
            ps = [{"linea": i, "texto": tx, "hecho": h} for i, h, tx in pasos_de(texto)]
            ev = _seguro_ctx(ctx, "carnet") or {"ok": True, "items": []}
            return {"id": "carnet", "titulo": "Carnet", "tipo": "lista", "ok": True, "nota": c, "pasos": ps,
                    "llevar": seccion(texto, r"Qué llevar"), "estudio": seccion(texto, r"Plan de estudio", 8), "eventos": ev,
                    "total": len(ps)}
    raise FileNotFoundError(f"No encuentro la nota «{NOTA_CARNET}» en Proyectos")


# ───────────────────────── tableros de solo lectura: Personas, Viajes, Fechas clave, Suscripciones ─────────────────────────
def _seguro_ctx(ctx, nombre):
    """Llama a una fuente lenta del servidor; un fallo no rompe el tablero (devuelve {ok:false,error})."""
    f = ctx.get(nombre)
    if not f:
        return None
    try:
        return f()
    except Exception as e:
        return {"ok": False, "error": f"No pude leer {nombre} ({type(e).__name__})"}


def _cumple(valor, hoy_):
    """('MM-DD', próximo cumple, edad|None) de «AAAA-MM-DD» (año 1900 = no se sabe)."""
    d = _fecha(valor)
    if not d:
        return None, None, None
    try:
        prox = d.replace(year=hoy_.year)
    except ValueError:                                  # 29 de febrero
        prox = date(hoy_.year, 3, 1)
    if prox < hoy_:
        try:
            prox = d.replace(year=hoy_.year + 1)
        except ValueError:
            prox = date(hoy_.year + 1, 3, 1)
    return f"{d.month:02d}-{d.day:02d}", prox, (prox.year - d.year if d.year > 1900 else None)


def _nombres_persona(titulo, aliases, relacion):
    n = {norm(re.sub(r"\([^)]*\)", "", titulo)).strip()}
    n |= {norm(a).strip() for a in aliases}
    primero = norm(re.sub(r"\([^)]*\)", "", titulo)).split()[:1]
    if primero and len(primero[0]) >= 4 and norm(relacion) != "mascota":
        n.add(primero[0])
    return {x for x in n if len(x) >= 3}


def _menciona(texto, nombres):
    t = norm(texto)
    return any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", t) for n in nombres)


def _vip_de(vip, nombres):
    """True/False/None (None = aún no se sabe quién es VIP). Solo compara NOMBRES de chat; nunca se guardan ni se enseñan JIDs."""
    if not vip or not vip.get("ok"):
        return None
    vs = [norm(x) for x in vip.get("nombres", [])]
    for v in vs:
        for n in nombres:
            if len(v) >= 3 and len(n) >= 3 and (v == n or (len(v) >= 4 and v in n) or (len(n) >= 4 and n in v)):
                return True
    return None if vip.get("sin_resolver") else False


def _tablero_personas(vault, estados, ctx):
    hoy_ = hoy()
    pend = _seguro_ctx(ctx, "pendientes")
    vip = _seguro_ctx(ctx, "vip")
    items = []
    for rel, p, st in _recorrer(vault, CARPETA_PERSONAS):
        c, base = _ficha(rel, p, st, estados)
        if c["tipo"] not in ("persona", "empresa"):
            continue
        nombres = _nombres_persona(c["titulo"], base["_aliases"], base["_relacion"])
        mm_dd, prox, edad = _cumple(base["_cumple"], hoy_)
        pt = pa = None
        if pend and pend.get("ok"):
            pt = [x["titulo"] for x in pend.get("tareas", []) if _menciona(x["titulo"], nombres)][:5]
            pa = [x["titulo"] for x in pend.get("avisos", []) if _menciona(x["titulo"], nombres)][:5]
        items.append({"ruta": rel, "titulo": c["titulo"], "tipo": c["tipo"], "relacion": base["_relacion"] or None, "cumple": mm_dd,
                      "proximo_cumple": prox.isoformat() if prox else None, "dias_cumple": (prox - hoy_).days if prox else None, "edad": edad,
                      "siguiente": c["siguiente"], "plazo": c["plazo"], "tags": c["tags"], "vip": _vip_de(vip, nombres),
                      "pendientes": None if pt is None else {"tareas": pt, "avisos": pa, "total": len(pt) + len(pa)},
                      "aviso": c["aviso"], "mtime": c["mtime"], "obsidian": c["obsidian"], "mover_a": []})
    items.sort(key=lambda x: (x["vip"] is not True, -(x["pendientes"] or {}).get("total", 0), norm(x["titulo"])))
    avisos_ = []
    if pend is None or not pend.get("ok"):
        avisos_.append("No pude mirar tareas y avisos: " + str((pend or {}).get("error", "sin datos")))
    if vip is None or not vip.get("ok"):
        avisos_.append("No sé quién es VIP: " + str((vip or {}).get("error", "sin datos")))
    elif vip.get("sin_resolver"):
        avisos_.append(f"{vip['sin_resolver']} VIP sin nombre de chat resuelto")
    return {"id": "personas", "titulo": "Personas", "tipo": "lista", "ok": True, "items": items, "total": len(items), "avisos": avisos_}


def _tablero_viajes(vault, estados, ctx):
    hoy_ = hoy()
    items, pasados = [], 0
    rv = A.Raiz("viajes", Path(vault), solo=("40 Compartido",))
    nota = None
    try:
        for it in A.listar(rv, CARPETA_VIAJES)["items"]:
            m = re.match(r"^(\d{4}-\d{2}-\d{2})[ _-]+(.+?)(?:\.[A-Za-z0-9]{1,5})?$", it["name"])
            f = _fecha(m.group(1)) if m else None
            if not f:
                continue
            if f < hoy_:
                pasados += 1
                continue
            sub = CARPETA_VIAJES[len("40 Compartido/"):]
            items.append({"tipo": "carpeta" if it["dir"] else "archivo", "fecha": f.isoformat(), "dias": (f - hoy_).days, "titulo": m.group(2)[:120],
                          "archivo": it["name"], "ruta": None, "checklist": [],
                          "enlace": "/?tab=carpetas&ruta=" + quote(sub, safe="/") + "&archivo=" + quote(it["name"], safe="")})
    except FileNotFoundError:
        nota = "No hay carpeta de viajes en Importante."
    except PermissionError:
        nota = "No pude leer la carpeta de viajes."
    for rel, p, st in _recorrer(vault, "30 Notas/Proyectos"):
        c, base = _ficha(rel, p, st, estados)
        if c["tipo"] != "proyecto" or c["estado"] in TERMINALES or not any(norm(t).split("/")[0] in ("viajes", "viaje") for t in c["tags"]):
            continue
        try:
            texto = _leer_bytes(p).decode("utf-8", "replace")
        except OSError:
            texto = ""
        f = _fecha(c["plazo"])
        items.append({"tipo": "proyecto", "fecha": f.isoformat() if f else None, "dias": (f - hoy_).days if f else None, "titulo": c["titulo"],
                      "archivo": None, "ruta": rel, "estado": c["estado"], "siguiente": c["siguiente"], "obsidian": c["obsidian"],
                      "checklist": seccion(texto, r"(?:Qué )?llevar|Equipaje|Maleta", 12), "enlace": None})
    items.sort(key=lambda x: (x["fecha"] is None, x["fecha"] or "", norm(x["titulo"])))
    return {"id": "viajes", "titulo": "Viajes", "tipo": "lista", "ok": True, "items": items, "total": len(items), "pasados": pasados, "nota": nota}


def _tablero_fechas(vault, estados, ctx):
    hoy_ = hoy()
    fin_mes = hoy_.replace(day=_cal.monthrange(hoy_.year, hoy_.month)[1])
    items, avisos_ = [], []

    def poner(fecha, tipo, titulo, **x):
        if fecha is None or fecha < hoy_ - timedelta(days=14) or fecha > hoy_ + timedelta(days=400):
            return
        items.append({"fecha": fecha.isoformat(), "dias": (fecha - hoy_).days, "tipo": tipo, "titulo": titulo[:160], "vencido": fecha < hoy_, **x})
    try:
        for rel, p, st in _recorrer(vault, CARPETA_PERSONAS):
            c, base = _ficha(rel, p, st, estados)
            if c["tipo"] in ("persona", "empresa"):
                _, prox, edad = _cumple(base["_cumple"], hoy_)
                if prox:
                    poner(prox, "cumple", "Cumple de " + re.sub(r"\([^)]*\)", "", c["titulo"]).strip() + (f" ({edad})" if edad else ""), ruta=rel, obsidian=c["obsidian"])
    except FileNotFoundError:
        pass
    for carpeta in ("30 Notas/Proyectos", "30 Notas/Candidaturas"):
        try:
            for rel, p, st in _recorrer(vault, carpeta):
                c, _ = _ficha(rel, p, st, estados)
                if c["tipo"] in ("proyecto", "candidatura") and c["estado"] not in TERMINALES:
                    poner(_fecha(c["plazo"]), "plazo", c["titulo"], ruta=rel, obsidian=c["obsidian"], estado=c["estado"])
        except FileNotFoundError:
            pass
    ev = _seguro_ctx(ctx, "fechas")
    if ev is not None:
        if ev.get("ok"):
            for e in ev.get("items", []):
                d = _fecha(str(e.get("inicio", ""))[:10])
                poner(d, "evento", e.get("titulo", ""), cuenta=e.get("cuenta"))
        else:
            avisos_.append("No pude mirar el calendario: " + str(ev.get("error")))
    items.sort(key=lambda x: (x["fecha"], x["tipo"], norm(x["titulo"])))
    g = {"vencidas": [], "esta_semana": [], "este_mes": [], "despues": []}
    for it in items:
        d = it["dias"]
        g["vencidas" if d < 0 else "esta_semana" if d <= 6 else "este_mes" if date.fromisoformat(it["fecha"]) <= fin_mes else "despues"].append(it)
    titulos = {"vencidas": "Vencidas", "esta_semana": "Esta semana", "este_mes": "Este mes", "despues": "Después"}
    return {"id": "fechas", "titulo": "Fechas clave", "tipo": "lista", "ok": True, "total": len(items),
            "grupos": [{"id": k, "titulo": titulos[k], "items": v} for k, v in g.items()], "avisos": avisos_}


def _tablero_suscripciones(vault, estados, ctx):
    """Suscripciones y gastos del mes que detecta el vigía (gastos.tablero, que lee `zv suscripciones|gastos --json`). Si falla la lectura de las suscripciones,
    el tablero dice que falló; si solo fallan los gastos del mes, el tablero sigue y la sección de gastos lleva su propio error. Nunca «0 €» inventados."""
    r = _seguro_ctx(ctx, "suscripciones") or {"items": [], "nota": SIN_SUSCRIPCIONES}
    if r.get("ok") is False:
        return {"id": "suscripciones", "titulo": "Suscripciones", "tipo": "lista", "ok": False, "error": r.get("error"), "items": [], "total": 0}
    items = r.get("items", [])
    out = {"id": "suscripciones", "titulo": "Suscripciones", "tipo": "lista", "ok": True, "items": items, "total": len(items),
           "nota": None if items else (r.get("nota") or SIN_SUSCRIPCIONES)}
    out.update({k: r[k] for k in ("totales", "estado", "gastos", "canceladas", "ocultas", "consejos") if k in r})
    return out


ESPECIALES = {"carnet": _tablero_carnet, "personas": _tablero_personas, "viajes": _tablero_viajes, "fechas": _tablero_fechas, "suscripciones": _tablero_suscripciones}


def todos(vault, ctx=None, fresco=False):
    """Todos los tableros. Un tablero que falla sale como {ok:false, error} sin tumbar a los demás. Caché corta.
    `ctx`: fuentes lentas opcionales (callables) que pone el servidor: carnet, fechas, pendientes, vip, suscripciones."""
    ctx = ctx or {}
    clave = str(vault)
    with LOCK:
        if not fresco and _cache["k"] == clave and time.time() - _cache["t"] < _TTL and _cache["v"] is not None:
            return _cache["v"]
        estados = estados_schema(vault)
        out = []
        for t in TABLEROS:
            try:
                esp = t.get("especial")
                if esp:
                    out.append(ESPECIALES[esp](vault, estados, ctx))
                else:
                    out.append(_tablero_kanban(vault, t, estados))
            except (OSError, PermissionError) as e:
                out.append({"id": t["id"], "titulo": t["titulo"], "ok": False, "error": str(e) if isinstance(e, FileNotFoundError) and not e.errno else "No pude leer las notas"})
            except Exception as e:                                         # nunca tumbar los otros tableros
                out.append({"id": t["id"], "titulo": t["titulo"], "ok": False, "error": f"Error leyendo el tablero ({type(e).__name__})"})
        res = {"ok": True, "leido": datetime.now(TZ).isoformat(timespec="seconds"), "tableros": out}
        _cache.update(t=time.time(), v=res, k=clave)
        return res


def invalidar():
    with LOCK:
        _cache["v"] = None


# ───────────────────────── escritura segura ─────────────────────────
def _resolver(vault, ruta):
    """Ruta relativa «30 Notas/…/X.md» → Path del archivo regular. Cualquier cosa rara = 400/403/404."""
    if not isinstance(ruta, str) or not ruta or len(ruta) > 300 or "\\" in ruta:
        raise TableroError(400, "ruta no válida")
    if not ruta.startswith(CARPETA + "/") or not ruta.lower().endswith(".md"):
        raise TableroError(400, "solo se pueden tocar notas de 30 Notas")
    try:
        p = raiz(vault).ruta(ruta)
    except PermissionError:
        raise TableroError(403, "ruta no permitida")
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        raise TableroError(404, "esa nota ya no existe")
    import stat as _st
    if not _st.S_ISREG(st.st_mode):
        raise TableroError(400, "eso no es una nota")
    if st.st_size > MAX_NOTA:
        raise TableroError(400, "la nota es demasiado grande")
    return p, st


def _version(mtime):
    if isinstance(mtime, bool) or not isinstance(mtime, int):
        raise TableroError(400, "falta la versión (mtime) de la tarjeta")
    return mtime


def _escribir(p, st0, texto, rel, vault):
    """Fichero temporal junto a la nota; justo antes de reemplazar se vuelve a comprobar que nadie la tocó (409)."""
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".hub-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(texto.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, st0.st_mode & 0o777)
        st1 = os.lstat(p)
        if (st1.st_mtime_ns, st1.st_size, st1.st_ino) != (st0.st_mtime_ns, st0.st_size, st0.st_ino):
            raise TableroError(409, "La nota cambió mientras tanto. He recargado el tablero.", tarjeta=_tarjeta_de(vault, rel))
        os.replace(tmp, p)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _tarjeta_de(vault, rel):
    try:
        p = raiz(vault).ruta(rel)
        st = os.lstat(p)
        return _ficha(rel, p, st, estados_schema(vault))[0]
    except Exception:
        return None


def _leer_nota(vault, ruta, mtime):
    """Lee la nota para tocarla: ruta segura → es de un tablero → la versión (mtime) es la que vio quien pide (409 si no)."""
    p, st = _resolver(vault, ruta)
    v = _version(mtime)
    try:
        texto = _leer_bytes(p, MAX_NOTA).decode("utf-8")
    except UnicodeDecodeError:
        raise TableroError(400, "la nota no es UTF-8")
    except OSError:
        raise TableroError(404, "no se pudo leer la nota")
    fm, ok = frontmatter(texto)
    if not ok or str(fm.get("tipo") or "").strip() not in ("proyecto", "candidatura", "idea"):
        raise TableroError(400, "esta nota no está en ningún tablero")
    if _ms(st) != v:
        raise TableroError(409, "La nota cambió mientras tanto. He recargado el tablero.", tarjeta=_tarjeta_de(vault, ruta))
    return p, st, texto


def mover(vault, ruta, estado, mtime, ahora=None):
    """Cambia SOLO la línea `estado:` de la nota (y añade su línea de Historial y una de log.md)."""
    ahora = ahora or datetime.now(TZ)
    if not isinstance(estado, str) or not 1 <= len(estado) <= 40:
        raise TableroError(400, "estado no válido")
    if estado == "aplicada":                                  # «aplicada» es el nombre coloquial de «enviada» (SCHEMA)
        estado = "enviada"
    with LOCK:
        p, st, texto = _leer_nota(vault, ruta, mtime)
        fm, ok = frontmatter(texto)
        tipo = str(fm.get("tipo") or "").strip()
        estados = estados_schema(vault)
        if not ok or tipo not in ("proyecto", "candidatura", "idea"):
            raise TableroError(400, "esta nota no está en ningún tablero")
        validos = estados.get(tipo, [])
        if estado not in validos:
            extra = " Para ponerla en marcha, conviértela en proyecto desde Obsidian." if tipo == "idea" and estado in estados.get("proyecto", []) else ""
            raise TableroError(400, f"«{estado}» no es un estado de {tipo}. Valen: {', '.join(validos)}.{extra}")
        antes = str(fm.get("estado") or "").strip()
        if antes == estado:
            return {"ok": True, "sin_cambios": True, "tarjeta": _tarjeta_de(vault, ruta), "historial": False, "registro": False, "enviada_puesta": False}
        lineas = re.findall(r"[^\n]*\n|[^\n]+", texto)
        bom = 1 if lineas and lineas[0].startswith("\ufeff") else 0
        if not re.match(r"^---[ \t]*\r?\n?$", lineas[0][bom:]):
            raise TableroError(400, "la nota no tiene propiedades")
        fin = next((i for i in range(1, len(lineas)) if re.match(r"^---[ \t]*\r?\n?$", lineas[i])), None)
        if fin is None:
            raise TableroError(400, "la nota no tiene propiedades")
        eol = "\r\n" if lineas[0].endswith("\r\n") else "\n"
        i_est = next((i for i in range(1, fin) if re.match(r"^estado[ \t]*:", lineas[i])), None)
        nueva = f"estado: {estado}"
        i_t = next((i for i in range(1, fin) if re.match(r"^tipo[ \t]*:", lineas[i])), 0)
        if i_est is not None:
            fin_l = "\r\n" if lineas[i_est].endswith("\r\n") else "\n" if lineas[i_est].endswith("\n") else ""
            lineas[i_est] = nueva + fin_l
        else:                                           # sin línea `estado:` → una línea nueva detrás de `tipo:`
            lineas.insert(i_t + 1, nueva + eol)
            fin += 1
            i_est = i_t + 1
        enviada = False
        if tipo == "candidatura" and estado == "enviada":      # primera vez que se envía: fecha de hoy, sin pisar una existente
            fin_l = lambda i: "\r\n" if lineas[i].endswith("\r\n") else "\n" if lineas[i].endswith("\n") else ""
            i_env = next((i for i in range(1, fin) if re.match(r"^enviada[ \t]*:", lineas[i])), None)
            hoy_txt = f"{ahora:%Y-%m-%d}"
            if i_env is None:
                lineas.insert((i_est if i_est is not None else i_t) + 1, f"enviada: {hoy_txt}{eol}")
                fin += 1
                enviada = True
            elif not _escalar(lineas[i_env].split(":", 1)[1].strip()):
                lineas[i_env] = f"enviada: {hoy_txt}{fin_l(i_env) or eol}"
                enviada = True
        historial = False
        linea_h = f"- {ahora:%Y-%m-%d} · Estado: {antes or 'sin estado'} → {estado} (desde HolaZazu)."
        for i in range(fin + 1, len(lineas)):
            if re.match(r"^##[ \t]+Historial[ \t]*\r?\n?$", lineas[i]):
                if not lineas[i].endswith("\n"):
                    lineas[i] += eol
                lineas.insert(i + 1, linea_h + eol)
                historial = True
                break
        nuevo = "".join(lineas)
        if privado.es_privado(linea_h):
            raise TableroError(400, "ese estado lleva algo que el Cerebro no guarda")
        _escribir(p, st, nuevo, ruta, vault)
        invalidar()
        registro = _log(vault, ahora, p.stem, antes, estado)
        return {"ok": True, "sin_cambios": False, "antes": antes, "despues": estado, "tarjeta": _tarjeta_de(vault, ruta),
                "historial": historial, "registro": registro, "enviada_puesta": enviada}


def _log(vault, ahora, nombre, antes, despues):
    """Una línea en 90 Sistema/log.md (solo añadir, O_APPEND). Si algo falla no deshace el movimiento: devuelve False."""
    try:
        ruta = Path(vault) / "90 Sistema/log.md"
        if not ruta.is_file() or any(q.is_symlink() for q in (ruta, ruta.parent)):
            return False
        nom = re.sub(r"[\x00-\x1f]+", " ", nombre)[:80]
        linea = f"- {ahora:%Y-%m-%d} · Fran (app) · «{nom}» pasa de «{antes or 'sin estado'}» a «{despues}» desde el tablero · notas tocadas: {nom}"
        if privado.es_privado(linea):
            return False
        fd = os.open(ruta, os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
        try:
            fin = os.pread(fd, 1, max(os.fstat(fd).st_size - 1, 0))
            os.write(fd, (b"" if fin in (b"\n", b"") else b"\n") + linea.encode("utf-8") + b"\n")
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def paso(vault, ruta, linea, texto_paso, hecho, mtime):
    """Marca/desmarca UNA casilla de «## Pasos». La línea y su texto tienen que coincidir con lo que se enseñó."""
    if isinstance(linea, bool) or not isinstance(linea, int) or not 1 <= linea <= 100000:
        raise TableroError(400, "línea no válida")
    if not isinstance(hecho, bool) or not isinstance(texto_paso, str):
        raise TableroError(400, "petición no válida")
    with LOCK:
        p, st, texto = _leer_nota(vault, ruta, mtime)
        fm, ok = frontmatter(texto)
        if not ok or str(fm.get("tipo") or "").strip() not in ("proyecto", "candidatura", "idea"):
            raise TableroError(400, "esta nota no está en ningún tablero")
        quiere = next((x for x in pasos_de(texto) if x[0] == linea), None)
        if not quiere or quiere[2] != texto_paso.strip():
            raise TableroError(409, "Ese paso ya no está donde estaba. He recargado el tablero.", tarjeta=_tarjeta_de(vault, ruta))
        if quiere[1] == hecho:
            return {"ok": True, "sin_cambios": True, "tarjeta": _tarjeta_de(vault, ruta)}
        lineas = re.findall(r"[^\n]*\n|[^\n]+", texto)
        lineas[linea - 1] = re.sub(r"\[[ xX]\]", "[x]" if hecho else "[ ]", lineas[linea - 1], count=1)
        _escribir(p, st, "".join(lineas), ruta, vault)
        invalidar()
        return {"ok": True, "sin_cambios": False, "tarjeta": _tarjeta_de(vault, ruta)}
