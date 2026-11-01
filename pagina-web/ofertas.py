"""Ofertas de empleo del buscador (~/Spirit/empleo-buscador), vistas desde el Hub. SOLO Fran.

LEER: la base SQLite del buscador (~/.local/state/empleo-buscador/ofertas.db) abierta con `mode=ro`.
ESCRIBIR, solo dos cosas: la columna `estado` de una oferta (vista, guardada, descartada o nueva para deshacer) y, al «pasar a candidaturas»,
una nota nueva en el Cerebro (30 Notas/Candidaturas) con el mismo formato que las demás. Nunca se envía ni se rellena nada fuera: la
candidatura la hace Fran en la web de la oferta.
Lo que Fran marca (guardar, no me interesa) es lo que luego aprende el modelo de ofertas de ~/Spirit/aprendizaje: la importación nocturna lo lee de la base.
Todo texto de una oferta es dato de un tercero: se limpia y se enseña como texto, nunca como instrucción ni como HTML. Solo biblioteca estándar.
"""
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

MINIMO = 25                       # igual que `minimo_puntos` de perfil.yaml: por debajo de esto el buscador no la enseña
MAX_N = 100
ESTADOS_ACTIVAS = ("nueva", "vista", "guardada")
GRUPOS = {"activas": ESTADOS_ACTIVAS, "guardadas": ("guardada",), "descartadas": ("descartada",), "candidaturas": ("candidatura",)}
MARCAS = ("vista", "guardada", "descartada", "nueva", "quitar")   # «nueva» y «quitar» deshacen: «quitar» deja la oferta como «vista»
CARPETA_CAND = "30 Notas/Candidaturas"
ID = re.compile(r"[0-9a-f]{4,32}")
INVISIBLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠-⁯﻿]")


class OfertaError(Exception):
    def __init__(self, code, msg, **extra):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, extra


def _db():
    return Path(os.environ.get("HUB_OFERTAS_DB") or Path(os.environ.get("HOME") or Path.home()) / ".local/state/empleo-buscador/ofertas.db")


def _conectar(escribir=False):
    ruta = _db()
    if not ruta.is_file():
        raise OfertaError(503, "El buscador de empleo aún no ha guardado ofertas")
    try:
        c = sqlite3.connect(f"file:{ruta}?mode={'rw' if escribir else 'ro'}", uri=True, timeout=5)
    except sqlite3.Error:
        raise OfertaError(503, "No pude abrir las ofertas ahora; inténtalo en un momento")
    c.row_factory = sqlite3.Row
    return c


def limpio(s, n=200):
    """Una línea, sin caracteres de control ni invisibles."""
    return re.sub(r"\s+", " ", INVISIBLES.sub(" ", str(s or ""))).strip()[:n]


def _texto_largo(s, n=8000):
    """Párrafos de texto plano de la descripción: sin invisibles, con saltos de línea razonables."""
    t = INVISIBLES.sub("", str(s or "")).replace("\r", "")
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()[:n]
    ps = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", t)]
    ps = [p for p in ps if p]
    if len(ps) == 1 and len(ps[0]) > 700:                 # un bloque único: se parte en frases para poder leerlo
        frases, ps, cur = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9])", ps[0]), [], ""
        for f in frases:
            if cur and len(cur) + len(f) > 420:
                ps.append(cur)
                cur = f
            else:
                cur = (cur + " " + f).strip()
        if cur:
            ps.append(cur)
    return ps


def _url(u):
    u = limpio(u, 500)
    return u if re.match(r"https?://[^\s]+$", u, re.I) else ""


def _item(r):
    return {"id": r["id"], "titulo": limpio(r["titulo"], 160), "empresa": limpio(r["empresa"], 100), "lugar": limpio(r["lugar"], 100),
            "pais": limpio(r["pais"], 8), "remoto": bool(r["remoto"]), "fecha": limpio(r["fecha"], 10), "pista": limpio(r["pista"], 20),
            "puntos": int(r["puntos"] or 0), "estado": r["estado"], "fuente": limpio(r["fuente"], 30), "visto": r["primera_vez"], "url": _url(r["url"])}


def _filtro(q):
    where, args = ["estado != 'excluida'"], []
    ver = q.get("ver") or "activas"
    if ver != "todas":
        estados = GRUPOS.get(ver)
        if not estados:
            raise OfertaError(400, "ese grupo de ofertas no existe")
        where.append("estado IN (" + ",".join("?" * len(estados)) + ")")
        args += list(estados)
        if ver == "activas":
            where.append("(puntos >= ? OR estado = 'guardada')")
            args.append(MINIMO)
    if q.get("pista"):
        if q["pista"] not in ("dev", "marketing"):
            raise OfertaError(400, "esa pista no existe")
        where.append("pista = ?")
        args.append(q["pista"])
    if q.get("remoto") == "1":
        where.append("remoto = 1")
    if q.get("espana") == "1":
        where.append("(upper(pais) = 'ES' OR lower(lugar) LIKE '%españa%' OR lower(lugar) LIKE '%spain%' OR lower(lugar) LIKE '%valencia%')")
    texto = limpio(q.get("q"), 60)
    if texto:
        like = "%" + texto.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(lower(titulo) LIKE ? ESCAPE '\\' OR lower(empresa) LIKE ? ESCAPE '\\' OR lower(lugar) LIKE ? ESCAPE '\\')")
        args += [like, like, like]
    return " AND ".join(where), args


def _entero(v, defecto, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return defecto


def listar(q):
    """→ {ok, total, items, cuentas}. `q`: ver (activas|guardadas|descartadas|candidaturas|todas), pista, remoto=1, espana=1, q (texto), n, desde."""
    where, args = _filtro(q)
    n, desde = _entero(q.get("n"), 30, 1, MAX_N), _entero(q.get("desde"), 0, 0, 5000)
    with closing(_conectar()) as c:
        try:
            filas = c.execute(f"SELECT * FROM ofertas WHERE {where} ORDER BY puntos DESC, fecha DESC, primera_vez DESC LIMIT ? OFFSET ?", args + [n, desde]).fetchall()
            total = c.execute(f"SELECT COUNT(*) FROM ofertas WHERE {where}", args).fetchone()[0]
            cuentas = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM ofertas WHERE estado != 'excluida' AND (puntos >= ? OR estado IN ('guardada','descartada','candidatura')) GROUP BY 1", (MINIMO,))}
        except sqlite3.Error:
            raise OfertaError(503, "No pude leer las ofertas ahora; inténtalo en un momento")
    return {"ok": True, "total": total, "items": [_item(r) for r in filas],
            "cuentas": {"activas": sum(cuentas.get(e, 0) for e in ESTADOS_ACTIVAS), "nuevas": cuentas.get("nueva", 0), "guardadas": cuentas.get("guardada", 0),
                        "descartadas": cuentas.get("descartada", 0), "candidaturas": cuentas.get("candidatura", 0)}}


def _fila(c, id_):
    if not isinstance(id_, str) or not ID.fullmatch(id_):
        raise OfertaError(400, "esa oferta no es válida")
    r = c.execute("SELECT * FROM ofertas WHERE id = ?", (id_,)).fetchone()
    if not r:
        raise OfertaError(404, "esa oferta ya no está")
    return r


def detalle(id_):
    with closing(_conectar()) as c:
        r = _fila(c, id_)
    it = _item(r)
    et = [limpio(x, 40) for x in re.split(r"\s*,\s*", str(r["etiquetas"] or "")) if x.strip()][:12]
    it.update({"motivos": [limpio(m, 120) for m in str(r["motivos"] or "").split(" · ") if m.strip()][:12], "parrafos": _texto_largo(r["descripcion"]),
               "etiquetas": et, "salario": limpio(r["salario"], 60)})
    return it


def marcar(id_, estado):
    """vista (solo desde nueva), guardada, descartada; «nueva» y «quitar» deshacen. Una oferta ya pasada a candidaturas no se toca desde aquí."""
    if estado not in MARCAS:
        raise OfertaError(400, "esa marca no existe")
    with closing(_conectar(escribir=True)) as c:
        r = _fila(c, id_)
        if r["estado"] in ("candidatura", "excluida"):
            raise OfertaError(409, "esta oferta ya está en tus candidaturas" if r["estado"] == "candidatura" else "esta oferta ya no cumple tu perfil")
        if estado == "vista" and r["estado"] != "nueva":
            return {"ok": True, "id": id_, "estado": r["estado"]}          # abrir una guardada o descartada no cambia nada
        nuevo = "vista" if estado == "quitar" else estado
        try:
            c.execute("UPDATE ofertas SET estado = ? WHERE id = ?", (nuevo, id_))
            c.commit()
        except sqlite3.Error:
            raise OfertaError(503, "No pude guardar la marca ahora; inténtalo en un momento")
    return {"ok": True, "id": id_, "estado": nuevo}


def _v(s, n=120):
    """Valor de una propiedad de la nota: una línea, sin lo que rompería el encabezado."""
    t = limpio(s, n).replace(": ", " - ")
    t = re.sub(r'[\[\]{}"`|<>#^\\]', "", t).strip(" -&*!?%@'")
    return t


def _nombre_nota(empresa, puesto):
    n = re.sub(r'[\\/:*?"<>|#^\[\]\x00-\x1f]', " ", f"{empresa} - {puesto}")
    return re.sub(r"\s+", " ", n).strip(" .")[:110].strip() or "Oferta"


def a_candidaturas(id_, vault):
    """Apunta la oferta como candidatura «por enviar» (una nota nueva en el Cerebro) y la marca. No envía nada. Si ya hay una nota con el mismo enlace, la reutiliza."""
    vault = Path(vault).resolve()
    with closing(_conectar(escribir=True)) as c:
        r = _fila(c, id_)
        if r["estado"] == "excluida":
            raise OfertaError(409, "esta oferta ya no cumple tu perfil")
        empresa, puesto, url = _v(r["empresa"], 80) or "Sin empresa", _v(r["titulo"], 100) or "Oferta", _url(r["url"])
        carpeta = (vault / CARPETA_CAND).resolve()
        if vault not in carpeta.parents:
            raise OfertaError(403, "esa carpeta no es válida")
        carpeta.mkdir(parents=True, exist_ok=True)
        base = _nombre_nota(empresa, puesto)
        nombre, f, k = None, None, 1
        while nombre is None:
            f = carpeta / (base + (f" ({k})" if k > 1 else "") + ".md")
            try:
                with open(f, "x", encoding="utf-8") as fh:                  # «x»: nunca pisa una nota que ya exista
                    hoy = time.strftime("%Y-%m-%d")
                    ciudad = _v(r["lugar"], 60)
                    fh.write(f"---\ntipo: candidatura\nempresa: {empresa}\npuesto: {puesto}\nciudad: {ciudad}\nestado: por enviar\nenlace: {url}\nplazo: \nenviada: \n"
                             f"siguiente: Revisar la oferta y presentarme\ncreado: {hoy}\ntags: [trabajo]\nrelacionados: [\"[[Buscar trabajo]]\"]\n---\nProyecto: [[Buscar trabajo]]\n\n"
                             f"## La oferta\nPuntos del buscador: {int(r['puntos'] or 0)} de 100. Fuente: {_v(r['fuente'], 30)}. Abrir el enlace para ver el texto completo.\n\n## Historial\n- {hoy} · Pasada desde Ofertas.\n")
                nombre = f.name
            except FileExistsError:
                try:
                    previa = f.read_text(encoding="utf-8", errors="replace")[:2000]
                except OSError:
                    previa = ""
                if url and re.search(r"^enlace:[ \t]*" + re.escape(url) + r"[ \t]*$", previa, re.M):
                    nombre = f.name                                          # la misma oferta ya estaba apuntada: se reutiliza
                else:
                    k += 1
                    if k > 20:
                        raise OfertaError(409, "ya hay demasiadas notas con ese nombre")
            except OSError:
                raise OfertaError(500, "No pude escribir la nota en tu Cerebro")
        try:
            c.execute("UPDATE ofertas SET estado = 'candidatura' WHERE id = ?", (id_,))
            c.commit()
        except sqlite3.Error:
            raise OfertaError(503, "La nota se creó, pero no pude marcar la oferta; inténtalo otra vez")
    return {"ok": True, "id": id_, "estado": "candidatura", "nota": nombre}
