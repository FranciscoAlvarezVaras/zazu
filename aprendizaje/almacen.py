"""Almacén de aprendizaje de Spirit: una base SQLite LOCAL donde se queda todo lo que Zazu y Fran van generando.

Dónde: ~/Spirit/aprendizaje/datos/almacen.db (carpeta 0700, fichero 0600, fuera de git). No sale del servidor: ni red, ni Syncthing, ni copias de seguridad
(no está en la lista de respaldo-pc). Si algún día eso cambia, que sea una decisión expresa de Fran.

Tablas:
  hecho     lo que ocurrió: mensajes de Hermes, avisos del vigía, ofertas de empleo, correcciones detectadas… (clave única: se puede reimportar sin duplicar)
  feedback  tu opinión (si / no) sobre un objeto: «hecho:123», «oferta:ab12cd»…
  leccion   lo que se ha aprendido, en lenguaje normal, con su evidencia; solo vale cuando Fran la aprueba
  marca     hasta dónde se ha leído cada fuente (para importar solo lo nuevo)
  reflexion qué correcciones ya se han mirado para sacar lecciones (por clave, que no cambia)
"""
import json
import os
import sqlite3
import time
from pathlib import Path

RAIZ = Path(os.environ.get("APRENDIZAJE_DATOS") or Path(__file__).resolve().parent / "datos")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS hecho (
  id INTEGER PRIMARY KEY, clave TEXT UNIQUE NOT NULL, fuente TEXT NOT NULL, tipo TEXT NOT NULL, ts REAL, perfil TEXT, texto TEXT, meta TEXT, ingerido REAL);
CREATE INDEX IF NOT EXISTS hecho_fuente ON hecho(fuente, tipo, ts);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, objeto TEXT NOT NULL, valor TEXT NOT NULL CHECK (valor IN ('si', 'no')), nota TEXT, origen TEXT);
CREATE INDEX IF NOT EXISTS feedback_objeto ON feedback(objeto);
CREATE TABLE IF NOT EXISTS leccion (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, texto TEXT NOT NULL, evidencia TEXT,
  estado TEXT NOT NULL DEFAULT 'propuesta' CHECK (estado IN ('propuesta', 'aprobada', 'rechazada')), origen TEXT, decidida REAL);
CREATE TABLE IF NOT EXISTS marca (fuente TEXT PRIMARY KEY, valor TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS reflexion (clave TEXT PRIMARY KEY, ts REAL NOT NULL, resultado TEXT);
"""


def conectar(ruta=None):
    ruta = Path(ruta) if ruta else RAIZ / "almacen.db"
    ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ruta.parent, 0o700)
    c = sqlite3.connect(ruta, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(ESQUEMA)
    for sufijo in ("", "-wal", "-shm"):
        try:
            os.chmod(f"{ruta}{sufijo}", 0o600)
        except OSError:
            pass
    return c


def anotar(c, clave, fuente, tipo, ts, perfil, texto, meta=None, actualizar=False):
    """Guarda un hecho. Devuelve True si es nuevo. actualizar=True: si ya estaba, refresca su texto y meta (para cosas que cambian de estado)."""
    m = json.dumps(meta, ensure_ascii=False) if meta is not None else None
    cur = c.execute("INSERT OR IGNORE INTO hecho(clave,fuente,tipo,ts,perfil,texto,meta,ingerido) VALUES(?,?,?,?,?,?,?,?)",
                    (clave, fuente, tipo, ts, perfil, texto, m, time.time()))
    if cur.rowcount:
        return True
    if actualizar:
        c.execute("UPDATE hecho SET texto=?, meta=?, ts=COALESCE(?, ts) WHERE clave=? AND (COALESCE(texto,'')<>COALESCE(?,'') OR COALESCE(meta,'')<>COALESCE(?,''))",
                  (texto, m, ts, clave, texto, m))
    return False


def marca(c, fuente, valor=None):
    """Sin valor: lee la marca. Con valor: la guarda."""
    if valor is None:
        r = c.execute("SELECT valor FROM marca WHERE fuente=?", (fuente,)).fetchone()
        return r["valor"] if r else None
    c.execute("INSERT INTO marca(fuente,valor,ts) VALUES(?,?,?) ON CONFLICT(fuente) DO UPDATE SET valor=excluded.valor, ts=excluded.ts", (fuente, str(valor), time.time()))
    return valor


def dar_feedback(c, objeto, valor, nota=None, origen="fran"):
    """valor: 'si' (útil, bien) o 'no' (no era eso)."""
    c.execute("INSERT INTO feedback(ts,objeto,valor,nota,origen) VALUES(?,?,?,?,?)", (time.time(), objeto, valor, nota, origen))
    c.commit()
