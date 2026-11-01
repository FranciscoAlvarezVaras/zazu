"""Base local de ofertas (SQLite en ~/.local/state/empleo-buscador/ofertas.db). Guarda lo visto, su estado y cuándo apareció."""
import os, re, sqlite3, time
from pathlib import Path

RUTA = Path(os.environ.get("EMPLEO_DB") or Path.home() / ".local/state/empleo-buscador/ofertas.db")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
  id TEXT PRIMARY KEY, fuente TEXT, titulo TEXT, empresa TEXT, url TEXT, lugar TEXT, pais TEXT, remoto INTEGER, fecha TEXT,
  descripcion TEXT, etiquetas TEXT, salario TEXT, pista TEXT, puntos INTEGER, motivos TEXT,
  estado TEXT DEFAULT 'nueva',   -- nueva · vista · guardada · descartada · candidatura
  primera_vez REAL, ultima_vez REAL);
CREATE INDEX IF NOT EXISTS ofertas_puntos ON ofertas(pista, puntos DESC);
"""


def conectar():
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(RUTA, timeout=30); c.row_factory = sqlite3.Row
    c.executescript(ESQUEMA); return c


def guardar(c, ofertas, motivos):
    """Inserta las nuevas y refresca las vistas antes. Devuelve cuántas son nuevas."""
    ahora = time.time(); nuevas = 0
    for o in ofertas:
        d = o.dict()
        fila = c.execute("SELECT id FROM ofertas WHERE id=?", (d["id"],)).fetchone()
        if fila:
            c.execute("UPDATE ofertas SET puntos=?, pista=?, ultima_vez=?, url=COALESCE(NULLIF(url,''),?), lugar=?, pais=?, remoto=?, fecha=MAX(COALESCE(fecha,''),?) WHERE id=?",
                      (d["puntos"], d["pista"], ahora, d["url"], d["lugar"], d["pais"], int(d["remoto"]), d["fecha"] or "", d["id"]))
        else:
            nuevas += 1
            c.execute("INSERT INTO ofertas(id,fuente,titulo,empresa,url,lugar,pais,remoto,fecha,descripcion,etiquetas,salario,pista,puntos,motivos,primera_vez,ultima_vez)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (d["id"], d["fuente"], d["titulo"], d["empresa"], d["url"], d["lugar"], d["pais"], int(d["remoto"]), d["fecha"], d["descripcion"][:1500],
                       ", ".join(d["etiquetas"])[:300], d["salario"], d["pista"], d["puntos"], " · ".join(motivos.get(d["id"], []))[:400], ahora, ahora))
    c.commit(); return nuevas


def listar(c, pista=None, estado=None, minimo=0, desde=None, n=30, sin_estados=()):
    """sin_estados: estados que no se quieren (se quitan en la consulta, ANTES del límite: filtrarlos después dejaba la lista vacía si lo mejor estaba descartado)."""
    q = "SELECT * FROM ofertas WHERE puntos>=?"; args = [minimo]
    if pista: q += " AND pista=?"; args.append(pista)
    if estado: q += " AND estado=?"; args.append(estado)
    if sin_estados: q += " AND estado NOT IN (" + ",".join("?" * len(sin_estados)) + ")"; args += list(sin_estados)
    if desde: q += " AND primera_vez>=?"; args.append(desde)
    q += " ORDER BY puntos DESC, fecha DESC LIMIT ?"; args.append(n)
    return c.execute(q, args).fetchall()


def marcar(c, id_, estado):
    """Cambia el estado de la oferta cuyo id empieza por `id_` (mínimo 4 letras/números). Devuelve cuántas cambió; -1 si empiezan así varias (no se toca ninguna).
    Antes cualquier texto valía: «_» o «%» marcaban TODAS, y «3» marcaba todas las que empezaran por 3."""
    id_ = str(id_ or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{4,16}", id_):
        return 0
    ids = [r["id"] for r in c.execute("SELECT id FROM ofertas WHERE id LIKE ?", (id_ + "%",)).fetchall()]
    if len(ids) > 1 and id_ not in ids:
        return -1
    n = c.execute("UPDATE ofertas SET estado=? WHERE id=?", (estado, id_ if id_ in ids else (ids[0] if ids else ""))).rowcount; c.commit()
    return n


def repuntuar(c, perfil, puntuar, Oferta):
    """Vuelve a puntuar TODO lo guardado con el perfil actual (así cambiar perfil.yaml se nota al momento). Lo excluido queda como 'excluida'."""
    n = 0
    for r in c.execute("SELECT * FROM ofertas").fetchall():
        o = Oferta(r["fuente"], r["titulo"], r["empresa"], r["url"], lugar=r["lugar"], pais=r["pais"], remoto=bool(r["remoto"]), fecha=r["fecha"], descripcion=r["descripcion"] or "")
        pista, puntos, m = puntuar(o, perfil)
        estado = r["estado"]
        if not pista and estado in ("guardada", "candidatura"):
            continue   # lo que guardaste o a lo que te presentaste no se borra por haberse hecho viejo: se queda con sus puntos
        if not pista and estado in ("nueva", "vista", "excluida"):
            estado = "excluida"
        elif pista and estado == "excluida":
            estado = "nueva"
        c.execute("UPDATE ofertas SET pista=?, puntos=?, motivos=?, estado=? WHERE id=?", (pista, puntos, " · ".join(m)[:400], estado, r["id"])); n += 1
    c.commit(); return n
