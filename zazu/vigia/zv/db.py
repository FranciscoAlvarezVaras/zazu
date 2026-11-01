"""Bandeja de avisos (SQLite, 0600, WAL) con dedupe por `clave`, códigos cortos por día (A1, A2…), latidos de los
vigías, contadores, uso del modelo y registro de entregas. Los textos se guardan YA tachados y recortados."""
import sqlite3
import time
from . import config
from .priv import seguro, limpio

ESQUEMA = """
CREATE TABLE IF NOT EXISTS avisos(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 codigo TEXT, dia TEXT,
 clave TEXT UNIQUE NOT NULL,
 fuente TEXT NOT NULL, tipo TEXT NOT NULL,
 prio INTEGER NOT NULL DEFAULT 2,
 noche_ok INTEGER NOT NULL DEFAULT 0,
 programado INTEGER NOT NULL DEFAULT 0,
 silencioso INTEGER NOT NULL DEFAULT 0,
 titulo TEXT, detalle TEXT, borrador TEXT, enlace TEXT, destino TEXT, ref TEXT,
 cuenta TEXT, due TEXT, hora TEXT, dur INTEGER, evidencia TEXT, chat TEXT,
 creado INTEGER NOT NULL, aviso_en INTEGER, vence INTEGER,
 estado TEXT NOT NULL DEFAULT 'nuevo',
 pospuesto_hasta INTEGER,
 entrega TEXT NOT NULL DEFAULT 'pendiente',
 entregado_en INTEGER,
 accion TEXT, accion_ref TEXT, accion_en INTEGER,
 intentos INTEGER NOT NULL DEFAULT 0, error TEXT, diferido_en INTEGER
);
CREATE INDEX IF NOT EXISTS ix_avisos_estado ON avisos(estado, entrega);
CREATE INDEX IF NOT EXISTS ix_avisos_ref ON avisos(ref);
CREATE TABLE IF NOT EXISTS entregas(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, aviso_id INTEGER, modo TEXT, canal TEXT, ok INTEGER, nota TEXT);
CREATE TABLE IF NOT EXISTS latidos(
 fuente TEXT PRIMARY KEY, ts INTEGER, ok INTEGER, detalle TEXT,
 fallos INTEGER NOT NULL DEFAULT 0, alertado INTEGER NOT NULL DEFAULT 0, episodio INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS uso_llm(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, dia TEXT, fuente TEXT, ok INTEGER, in_tok INTEGER, out_tok INTEGER, ms INTEGER, nota TEXT);
CREATE TABLE IF NOT EXISTS contadores(dia TEXT, clave TEXT, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(dia, clave));
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS registro(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL,
 actor TEXT NOT NULL DEFAULT 'vigia', fuente TEXT NOT NULL, tipo TEXT NOT NULL, modo TEXT NOT NULL DEFAULT 'sombra',
 titulo TEXT NOT NULL, detalle TEXT, flujo TEXT, ref TEXT, clave TEXT UNIQUE, disparo TEXT);
CREATE INDEX IF NOT EXISTS ix_registro_ts ON registro(ts);
CREATE INDEX IF NOT EXISTS ix_registro_flujo ON registro(flujo, ts);
CREATE TABLE IF NOT EXISTS gasto(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 comercio TEXT NOT NULL, nombre TEXT NOT NULL,
 importe_cent INTEGER NOT NULL, moneda TEXT NOT NULL DEFAULT 'EUR',
 fecha TEXT NOT NULL,
 tipo TEXT NOT NULL DEFAULT 'cargo',
 categoria TEXT NOT NULL DEFAULT 'sin_clasificar',
 cuenta TEXT NOT NULL, hilo TEXT NOT NULL,
 origen TEXT NOT NULL DEFAULT 'reglas',
 estado TEXT NOT NULL DEFAULT 'ok',
 dup_de INTEGER, proximo TEXT,
 creado INTEGER NOT NULL,
 UNIQUE(comercio, importe_cent, moneda, fecha, hilo));
CREATE INDEX IF NOT EXISTS ix_gasto_fecha ON gasto(fecha);
CREATE INDEX IF NOT EXISTS ix_gasto_comercio ON gasto(comercio, moneda, fecha);
CREATE TABLE IF NOT EXISTS suscripcion(
 comercio TEXT NOT NULL, moneda TEXT NOT NULL,
 nombre TEXT NOT NULL, categoria TEXT, cuenta TEXT,
 periodo TEXT, importe_cent INTEGER, ultimo_importe_cent INTEGER, anterior_importe_cent INTEGER,
 n_cargos INTEGER NOT NULL DEFAULT 0,
 primer_cobro TEXT, ultimo_cobro TEXT, proximo_cobro TEXT, proximo_fuente TEXT,
 estado TEXT NOT NULL, base TEXT NOT NULL DEFAULT 'correo',
 cancelar INTEGER NOT NULL DEFAULT 0, cancelar_desde TEXT,
 subida_pct REAL, actualizado INTEGER NOT NULL,
 importe REAL, proxima_fecha TEXT,          -- copia legible (euros y fecha) para el lector antiguo del Hub: nombre, importe, moneda, proxima_fecha, cuenta
 PRIMARY KEY(comercio, moneda));
-- reglas «siempre / nunca» que Fran da en la app sobre una clave estrecha (permisos.py; idea de OpenJarvis permission_memory)
CREATE TABLE IF NOT EXISTS permisos(
 clave TEXT PRIMARY KEY,
 decision TEXT NOT NULL CHECK(decision IN ('siempre','nunca')),
 veces_si INTEGER NOT NULL DEFAULT 0, veces_no INTEGER NOT NULL DEFAULT 0, aplicada INTEGER NOT NULL DEFAULT 0,
 creado INTEGER NOT NULL, actualizado INTEGER NOT NULL, usado INTEGER, ejemplo TEXT);
"""
# Columnas añadidas después: se suman con ALTER TABLE (nunca se borra nada). riesgo bajo|medio|alto · permiso = clave estrecha ·
# sospechoso = el escudo saltó con el texto de origen · decision: si | no | auto (aceptada por una regla «siempre») | nunca (oculta por regla)
MIGRACIONES = (("avisos", "riesgo", "TEXT"), ("avisos", "permiso", "TEXT"), ("avisos", "sospechoso", "INTEGER NOT NULL DEFAULT 0"),
               ("avisos", "decision", "TEXT"))
COLS_TEXTO = {"titulo": 120, "detalle": 300, "borrador": 200}


class DB:
    def __init__(self, ruta=None):
        d = config.estado_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            d.chmod(0o700)
        except OSError:
            pass
        self.ruta = ruta or d / "avisos.db"
        nuevo = not self.ruta.exists()
        self.c = sqlite3.connect(self.ruta, timeout=30)
        self.c.row_factory = sqlite3.Row
        if nuevo:
            self.ruta.touch(mode=0o600)
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript(ESQUEMA)
        self._migrar()
        self.c.commit()
        try:
            self.ruta.chmod(0o600)
        except OSError:
            pass

    def _migrar(self):
        for tabla, col, tipo in MIGRACIONES:
            if col not in {r[1] for r in self.c.execute(f"PRAGMA table_info({tabla})")}:
                self.c.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")

    def close(self):
        try:
            self.c.close()
        except Exception:
            pass

    # ───── tiempo ─────
    @staticmethod
    def ts():
        return int(config.ahora().timestamp())

    @staticmethod
    def hoy():
        return config.ahora().strftime("%Y-%m-%d")

    # ───── contadores ─────
    def contar(self, clave, n=1, dia=None):
        dia = dia or self.hoy()
        self.c.execute("INSERT INTO contadores(dia,clave,n) VALUES(?,?,?) ON CONFLICT(dia,clave) DO UPDATE SET n=n+?", (dia, clave, n, n))
        self.c.commit()

    def contadores(self, dia=None):
        return {r["clave"]: r["n"] for r in self.c.execute("SELECT clave,n FROM contadores WHERE dia=?", (dia or self.hoy(),))}

    # ───── avisos ─────
    def alta(self, clave, fuente, tipo, titulo, *, prio=2, detalle="", borrador="", enlace="", destino="", ref="",
             noche_ok=False, programado=False, silencioso=False, cuenta=None, due=None, hora=None, dur=None,
             evidencia="", chat="", aviso_en=None, vence=None, accion=None, riesgo=None, permiso=None, sospechoso=False, decision=None):
        """Crea el aviso si su `clave` no existe. Devuelve (id, nuevo)."""
        fila = self.c.execute("SELECT id FROM avisos WHERE clave=?", (clave,)).fetchone()
        if fila:
            return fila["id"], False
        dia = self.hoy()
        n = self.c.execute("SELECT COALESCE(MAX(n),0)+1 FROM contadores WHERE dia=? AND clave=?", (dia, "cod_A")).fetchone()[0]
        self.c.execute("INSERT INTO contadores(dia,clave,n) VALUES(?,?,?) ON CONFLICT(dia,clave) DO UPDATE SET n=?", (dia, "cod_A", n, n))
        cur = self.c.execute(
            "INSERT INTO avisos(codigo,dia,clave,fuente,tipo,prio,noche_ok,programado,silencioso,titulo,detalle,borrador,enlace,destino,ref,"
            "cuenta,due,hora,dur,evidencia,chat,creado,aviso_en,vence,accion,entrega,riesgo,permiso,sospechoso,decision) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"A{n}", dia, clave, fuente, tipo, prio, int(noche_ok), int(programado), int(silencioso),
             seguro(titulo, COLS_TEXTO["titulo"]), seguro(detalle, COLS_TEXTO["detalle"]), seguro(borrador, COLS_TEXTO["borrador"]),
             limpio(enlace, 300), destino or "", ref or "", cuenta, due, hora, dur, limpio(evidencia, 300), seguro(chat, 40),
             self.ts(), aviso_en, vence, accion, "silencioso" if silencioso else "pendiente", riesgo, permiso, int(bool(sospechoso)), decision))
        self.c.commit()
        return cur.lastrowid, True

    def buscar(self, ident):
        """Por id numérico o por código del día (A3: el más reciente que no esté cerrado)."""
        ident = str(ident).strip()
        if ident.isdigit():
            return self.c.execute("SELECT * FROM avisos WHERE id=?", (int(ident),)).fetchone()
        return self.c.execute("SELECT * FROM avisos WHERE codigo=? ORDER BY (estado IN ('nuevo','visto','luego')) DESC, id DESC LIMIT 1",
                              (ident.upper(),)).fetchone()

    def listar(self, estado=None, fuente=None, dia=None, limite=50, solo_items=False):
        q, a = "SELECT * FROM avisos WHERE 1=1", []
        if estado:
            q += " AND estado=?"; a.append(estado)
        if fuente:
            q += " AND fuente=?"; a.append(fuente)
        if dia:
            q += " AND dia=?"; a.append(dia)
        if solo_items:
            q += " AND tipo LIKE 'item_%'"
        q += " ORDER BY id DESC LIMIT ?"
        a.append(limite)
        return self.c.execute(q, a).fetchall()

    def set(self, id_, **campos):
        if not campos:
            return
        self.c.execute(f"UPDATE avisos SET {','.join(k + '=?' for k in campos)} WHERE id=?", (*campos.values(), id_))
        self.c.commit()

    def marcar(self, id_, estado, hasta=None):
        self.set(id_, estado=estado, pospuesto_hasta=hasta)

    def superar_antiguos(self, ref, id_nuevo):
        """Un aviso nuevo del mismo chat/hilo deja obsoletos los anteriores que aún no se entregaron."""
        if ref:
            self.c.execute("UPDATE avisos SET entrega='superado' WHERE ref=? AND id<>? AND entrega IN ('pendiente','retenido','diferido') AND silencioso=0",
                           (ref, id_nuevo))
            self.c.commit()

    # ───── entregas ─────
    def registrar_entrega(self, aviso_id, modo, canal, ok, nota=""):
        self.c.execute("INSERT INTO entregas(ts,aviso_id,modo,canal,ok,nota) VALUES(?,?,?,?,?,?)", (self.ts(), aviso_id, modo, canal, int(ok), nota[:200]))
        self.c.commit()

    def entregas_desde(self, desde_ts, no_p1=True):
        q = ("SELECT COUNT(*) FROM entregas e JOIN avisos a ON a.id=e.aviso_id WHERE e.ts>=? AND e.canal='wa' AND e.ok=1 "
             "AND a.tipo NOT LIKE 'resumen%'")
        if no_p1:
            q += " AND a.prio>1 AND a.programado=0"
        return self.c.execute(q, (desde_ts,)).fetchone()[0]

    def ultima_entrega_ref(self, ref):
        r = self.c.execute("SELECT MAX(e.ts) FROM entregas e JOIN avisos a ON a.id=e.aviso_id WHERE a.ref=? AND e.ok=1 AND e.canal='wa'", (ref,)).fetchone()
        return r[0] or 0

    # ───── kv ─────
    def kv_get(self, k, defecto=None):
        r = self.c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r["v"] if r else defecto

    def kv_set(self, k, v):
        self.c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
        self.c.commit()

    # ───── latidos y fallos ─────
    def latido(self, fuente, ok=True, detalle=""):
        """Registra el resultado de un ciclo. Devuelve 'fallo_alerta' (llega al umbral), 'resuelto' (se recupera tras avisar) o None."""
        umbral = config.cargar(crear=False)["fallos"]["umbral"]
        r = self.c.execute("SELECT * FROM latidos WHERE fuente=?", (fuente,)).fetchone()
        fallos, alertado, episodio = (r["fallos"], r["alertado"], r["episodio"]) if r else (0, 0, 0)
        evento = None
        if ok:
            if alertado:
                evento = "resuelto"
            fallos, alertado = 0, 0
        else:
            fallos += 1
            if fallos >= umbral and not alertado:
                alertado, episodio, evento = 1, episodio + 1, "fallo_alerta"
        self.c.execute("INSERT INTO latidos(fuente,ts,ok,detalle,fallos,alertado,episodio) VALUES(?,?,?,?,?,?,?) "
                       "ON CONFLICT(fuente) DO UPDATE SET ts=excluded.ts, ok=excluded.ok, detalle=excluded.detalle, fallos=excluded.fallos, alertado=excluded.alertado, episodio=excluded.episodio",
                       (fuente, self.ts(), int(ok), limpio(detalle, 200), fallos, alertado, episodio))
        self.c.commit()
        return evento

    def latidos(self):
        return {r["fuente"]: dict(r) for r in self.c.execute("SELECT * FROM latidos")}

    def episodio(self, fuente):
        r = self.c.execute("SELECT episodio FROM latidos WHERE fuente=?", (fuente,)).fetchone()
        return r["episodio"] if r else 0

    # ───── modelo ─────
    def uso_llm_hoy(self):
        return self.c.execute("SELECT COUNT(*) FROM uso_llm WHERE dia=?", (self.hoy(),)).fetchone()[0]

    def uso_llm(self, fuente, ok, in_tok=None, out_tok=None, ms=0, nota=""):
        self.c.execute("INSERT INTO uso_llm(ts,dia,fuente,ok,in_tok,out_tok,ms,nota) VALUES(?,?,?,?,?,?,?,?)",
                       (self.ts(), self.hoy(), fuente, int(ok), in_tok, out_tok, ms, nota[:120]))
        self.c.commit()

    # ───── retención ─────
    TIPOS_INFORMATIVOS = ("auditoria", "accion_gemela", "item_tarea", "item_evento", "flujo_tarea", "flujo_evento")

    def cerrar_informativos(self, cfg, dias=None):
        """Cierra (estado «descartado») los avisos solo informativos que llevan `dias` días sin atender (por defecto retencion.cerrar_informativos_dias, 3).
        Antes se acumulaban (35 de auditoría de la agenda y 13 de «tarea gemela» desde el 8 de octubre). Solo los que ya no esperan una acción del
        vigía (accion pendiente / evento_creado se respetan) y solo estos tipos: los avisos que piden algo (vencimientos, dinero, fallos…) no se tocan.
        Devuelve cuántos cerró."""
        dias = (cfg.get("retencion") or {}).get("cerrar_informativos_dias", 3) if dias is None else dias
        if not dias or dias < 0:
            return 0
        marcas = ",".join("?" * len(self.TIPOS_INFORMATIVOS))
        cur = self.c.execute(f"UPDATE avisos SET estado='descartado' WHERE estado='nuevo' AND tipo IN ({marcas}) "
                             "AND COALESCE(accion,'') NOT IN ('pendiente','evento_creado') AND creado<?",
                             (*self.TIPOS_INFORMATIVOS, self.ts() - dias * 86400))
        self.c.commit()
        return cur.rowcount

    def purgar(self, cfg):
        ahora = self.ts()
        dias = cfg["retencion"]["avisos_dias"]
        self.c.execute("DELETE FROM avisos WHERE creado<?", (ahora - dias * 86400,))
        self.c.execute("UPDATE avisos SET borrador='' WHERE creado<? AND borrador<>''", (ahora - cfg["retencion"]["borradores_h"] * 3600,))
        self.c.execute("DELETE FROM entregas WHERE ts<?", (ahora - dias * 86400,))
        self.c.execute("DELETE FROM uso_llm WHERE ts<?", (ahora - 30 * 86400,))
        self.c.execute("DELETE FROM registro WHERE ts<?", (ahora - cfg.get("retencion", {}).get("registro_dias", 30) * 86400,))
        self.c.execute("DELETE FROM gasto WHERE fecha<?", (time.strftime("%Y-%m-%d", time.localtime(ahora - (cfg.get("gastos") or {}).get("retencion_dias", 800) * 86400)),))
        self.c.execute("DELETE FROM contadores WHERE dia<?", (time.strftime("%Y-%m-%d", time.localtime(ahora - 30 * 86400)),))
        self.c.commit()
