"""Estado de la bandeja (SQLite, 0600) y registro de sombra (JSONL). Vive en ~/.local/state/zazu-bandeja/, fuera del Cerebro
y de la copia de seguridad (restic nombra rutas concretas)."""
import json, os, sqlite3
from datetime import datetime, timedelta

import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS items(clave TEXT PRIMARY KEY, tipo TEXT, cuenta TEXT, huella TEXT, visto_ts REAL, ultima_ts REAL,
  estado TEXT, resultado TEXT);
CREATE TABLE IF NOT EXISTS acciones(clave TEXT, modo TEXT, tipo TEXT, prio INT, ts REAL, estado TEXT, intentos INT DEFAULT 0,
  proximo REAL, detalle TEXT, PRIMARY KEY(clave, modo));
CREATE TABLE IF NOT EXISTS inbox(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, modo TEXT, prio INT, tipo TEXT, texto TEXT, entregado INT DEFAULT 0, clave TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS propuestas(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, clave TEXT UNIQUE, tipo TEXT, campos TEXT, estado TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


class Estado:
    def __init__(self, memoria=False):
        """memoria=True: base en RAM y sin registro (simulacros de solo lectura: no escribe nada en disco)."""
        self.memoria = memoria
        if memoria:
            self.dir, self.sombra_log = None, None
            self.db = sqlite3.connect(":memory:")
            self.db.executescript(ESQUEMA)
            return
        self.dir = config.asegurar_dir(config.estado_dir())
        nuevo = not (self.dir / "estado.db").exists()
        self.db = sqlite3.connect(self.dir / "estado.db", timeout=30)
        self.db.executescript(ESQUEMA)
        if nuevo:
            os.chmod(self.dir / "estado.db", 0o600)
        self.sombra_log = self.dir / "sombra.log"

    def cerrar(self):
        self.db.commit()
        self.db.close()

    # meta
    def meta(self, k, defecto=None):
        r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else defecto

    def poner_meta(self, k, v):
        self.db.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))

    # items (tareas/eventos vistos)
    def item(self, clave):
        r = self.db.execute("SELECT huella, estado, resultado FROM items WHERE clave=?", (clave,)).fetchone()
        return {"huella": r[0], "estado": r[1], "resultado": r[2]} if r else None

    def ver_item(self, clave, tipo, cuenta, huella, estado=None, resultado=None):
        t = config.ahora().timestamp()
        self.db.execute("INSERT INTO items(clave,tipo,cuenta,huella,visto_ts,ultima_ts,estado,resultado) VALUES(?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(clave) DO UPDATE SET huella=excluded.huella, ultima_ts=excluded.ultima_ts, "
                        "estado=coalesce(?,estado), resultado=coalesce(?,resultado)",
                        (clave, tipo, cuenta, huella, t, t, estado, resultado, estado, resultado))

    def items_abiertos(self, tipo):
        return [r[0] for r in self.db.execute("SELECT clave FROM items WHERE tipo=? AND coalesce(estado,'') != 'cerrado'", (tipo,))]

    # acciones (idempotencia: una fila por clave y modo; la de sombra no impide la de vivo)
    def accion(self, clave, modo):
        r = self.db.execute("SELECT estado, intentos, proximo, detalle FROM acciones WHERE clave=? AND modo=?", (clave, modo)).fetchone()
        return {"estado": r[0], "intentos": r[1], "proximo": r[2], "detalle": r[3]} if r else None

    def anotar(self, clave, modo, tipo, prio, estado, detalle="", intentos=0, proximo=None):
        self.db.execute("INSERT INTO acciones(clave,modo,tipo,prio,ts,estado,intentos,proximo,detalle) VALUES(?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(clave,modo) DO UPDATE SET ts=excluded.ts, estado=excluded.estado, intentos=excluded.intentos, "
                        "proximo=excluded.proximo, detalle=excluded.detalle",
                        (clave, modo, tipo, prio, config.ahora().timestamp(), estado, intentos, proximo, detalle[:500]))

    def contar_hoy(self, tipo, modo, estado="hecho"):
        d0 = config.ahora().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return self.db.execute("SELECT count(*) FROM acciones WHERE tipo=? AND modo=? AND estado=? AND ts>=?", (tipo, modo, estado, d0)).fetchone()[0]

    # sombra
    def registrar_sombra(self, **campos):
        if self.memoria:
            return
        campos = {"ts": config.ahora().isoformat(timespec="seconds"), **campos}
        fd = os.open(self.sombra_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(campos, ensure_ascii=False) + "\n")

    # inbox (bandeja de avisos propia; dedupe por clave)
    def inbox(self, clave, modo, prio, tipo, texto, entregado=0):
        cur = self.db.execute("INSERT OR IGNORE INTO inbox(ts,modo,prio,tipo,texto,entregado,clave) VALUES(?,?,?,?,?,?,?)",
                              (config.ahora().timestamp(), modo, prio, tipo, texto[:400], entregado, clave))
        return cur.rowcount == 1

    def purgar(self):
        corte = (config.ahora() - timedelta(days=30)).timestamp()
        self.db.execute("DELETE FROM inbox WHERE ts<?", (corte,))
        self.db.execute("DELETE FROM acciones WHERE ts<? AND modo='sombra'", (corte,))
