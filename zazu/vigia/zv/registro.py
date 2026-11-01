"""Registro de actividad del vigía: «qué leyó, qué propuso, qué escribió». Una fila por hecho, con texto corto YA filtrado
(priv.seguro): nunca cuerpos de mensajes, claves, cuentas, teléfonos ni DNI. Retención de 30 días (db.purgar).

Tipos:  leyo (uno por fuente y ciclo, con cifras) · propuso (lo que habría creado/avisado; en sombra «Habría …») ·
        escribio (solo si de verdad se escribió en Google: modo vivo) · descarto (se descarta o no se automatiza algo) ·
        fallo (error de una fuente) · aviso (aviso entregado de verdad por WhatsApp).
Actores: vigia (este paquete) · bandeja (paquete hermano zazu-bandeja, leído en SOLO LECTURA) · app (Fran desde la app).

Es una ayuda: si falla escribir el registro (disco, base bloqueada) NUNCA tumba un ciclo."""
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .priv import limpio, seguro

TIPOS = ("leyo", "propuso", "escribio", "descarto", "fallo", "aviso")
FUENTES = ("wa", "correo", "agenda", "tareas", "sistema")
ACTORES = ("vigia", "bandeja", "app")
MODO_DE = {"wa": "wa", "correo": "correo", "agenda": "agenda", "tareas": "agenda"}   # qué interruptor manda en cada fuente
OFFSET_BANDEJA_ACCION, OFFSET_BANDEJA_INBOX = 1_000_000_000, 2_000_000_000


def modo_de(fuente, cfg=None):
    """«vivo» solo si de verdad se entregaría/escribiría ahora (sin PAUSA + ENTREGA_ACTIVA + vigía en activo); si no, «sombra»."""
    try:
        cfg = cfg or config.cargar(crear=False)
        k = MODO_DE.get(fuente)
        if k:
            return "vivo" if config.modo_real(cfg, k) else "sombra"
        return "vivo" if (config.entrega_global() and not config.pausado()) else "sombra"
    except Exception:
        return "sombra"


def anota(db, tipo, fuente, titulo, detalle=None, *, flujo=None, ref=None, modo=None, actor="vigia", clave=None, disparo=None,
          ts=None, cfg=None):
    """Añade una fila. Devuelve su id, o None si `clave` ya existía (idempotente) o si no se pudo escribir."""
    try:
        if tipo not in TIPOS or fuente not in FUENTES or actor not in ACTORES:
            raise ValueError(f"registro: valor no válido ({tipo}/{fuente}/{actor})")
        modo = modo if modo in ("sombra", "vivo") else modo_de(fuente, cfg)
        if tipo == "escribio":
            modo = "vivo"          # «escribió» solo existe de verdad
        cur = db.c.execute(
            "INSERT OR IGNORE INTO registro(ts,actor,fuente,tipo,modo,titulo,detalle,flujo,ref,clave,disparo) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (ts or db.ts(), actor, fuente, tipo, modo, seguro(titulo, 120) or "(sin título)", seguro(detalle, 200) if detalle else None,
             limpio(flujo, 40) or None, limpio(ref, 60) or None, limpio(clave, 160) or None, limpio(disparo, 160) or None))
        db.c.commit()
        return cur.lastrowid if cur.rowcount else None
    except (sqlite3.Error, ValueError, OSError) as e:
        sys.stderr.write(f"zv: no pude anotar en el registro ({type(e).__name__})\n")
        return None


def _fmt_fecha(due, hora=None):
    if not due:
        return ""
    return f"{due[8:10]}/{due[5:7]}" + (f" {hora}" if hora else "")


def propuesta(db, cfg, fuente, que, titulo, *, due=None, hora=None, flujo=None, ref=None, clave=None, disparo=None, detalle=None, modo=None):
    """Propuesta del vigía. `que`: aviso | tarea | evento | tarea_gemela. En sombra «Habría …»; en vivo «Voy a …»."""
    modo = modo or modo_de(fuente, cfg)
    sombra = modo != "vivo"
    cuando = _fmt_fecha(due, hora)
    pref = {"aviso": ("Habría avisado", "Voy a avisar"), "tarea": ("Habría creado tarea", "Voy a crear tarea"),
            "evento": ("Habría creado evento tentativo", "Voy a crear evento tentativo"),
            "tarea_gemela": ("Habría creado tarea gemela", "Voy a crear tarea gemela")}[que][0 if sombra else 1]
    return anota(db, "propuso", fuente, f"{pref}: {titulo}" + (f" (para el {cuando})" if cuando and que != "aviso" else ""), detalle,
                 flujo=flujo, ref=ref, modo=modo, clave=clave, disparo=disparo, cfg=cfg)


# ───────── lectura ─────────
def _a_iso(ts):
    return datetime.fromtimestamp(ts, config.TZ).isoformat(timespec="seconds")


def limites_dia(dia):
    d0 = datetime.strptime(dia, "%Y-%m-%d").replace(tzinfo=config.TZ)
    return int(d0.timestamp()), int((d0 + timedelta(days=1)).timestamp())


def parsea_instante(s):
    d = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=config.TZ)


def _fila(r):
    return {"id": r["id"], "ts": _a_iso(r["ts"]), "actor": r["actor"], "fuente": r["fuente"], "tipo": r["tipo"], "modo": r["modo"],
            "titulo": r["titulo"], "detalle": r["detalle"], "flujo": r["flujo"], "ref": r["ref"]}


# ───────── la bandeja (paquete hermano): SOLO LECTURA ─────────
def _ruta_bandeja():
    """Misma carpeta que usa la bandeja (ZB_ESTADO si existe, si no ~/.local/state/zazu-bandeja)."""
    return Path(os.environ.get("ZB_ESTADO") or config.home() / ".local/state/zazu-bandeja")


def _titulo_entre_comillas(texto):
    m = re.search(r"«([^»]{2,120})»", texto or "")
    return m.group(1) if m else None


def de_bandeja(desde_ts, hasta_ts):
    """Lo que la bandeja (zazu-bandeja) tiene anotado, traducido a filas del registro con actor «bandeja». Abre su base con
    mode=ro y NO escribe nada. Si no existe o está ocupada, devuelve []. Qué se puede y qué no (su modelo de datos):
      · sí: acciones en sombra (gemelas, aplicar…) → «propuso»; acciones en vivo hechas → «escribio»; fallidas → «fallo»;
        omitidas → «descarto»; avisos de su inbox → «propuso» (sombra) o «aviso» (entregado); errores → «fallo»; último ciclo → «leyo».
      · no: no guarda el título de lo que procesa (solo el plan), ni lecturas por ciclo (solo la hora del último), ni descartes de Fran."""
    ruta = _ruta_bandeja() / "estado.db"
    if not ruta.exists():
        return []
    out = []
    try:
        c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=2)
        c.row_factory = sqlite3.Row
        try:
            for r in c.execute("SELECT rowid AS rid, * FROM acciones WHERE ts>=? AND ts<? ORDER BY ts", (desde_ts, hasta_ts)):
                if r["tipo"] == "aviso":
                    continue      # los avisos se leen de su inbox (el mismo aviso está en las dos tablas)
                out.append(_de_accion(r))
            for r in c.execute("SELECT * FROM inbox WHERE ts>=? AND ts<? ORDER BY ts", (desde_ts, hasta_ts)):
                out.append(_de_inbox(r))
            m = {k: v for k, v in c.execute("SELECT k, v FROM meta WHERE k='ultimo_ciclo'")}
            u = m.get("ultimo_ciclo")
            if u:
                t = parsea_instante(u.split(" ")[0]).timestamp()
                if desde_ts <= t < hasta_ts:
                    pausado = u.endswith("pausado")
                    n_t = c.execute("SELECT COUNT(*) FROM items WHERE tipo='tarea' AND ultima_ts>=?", (t - 120,)).fetchone()[0]
                    n_e = c.execute("SELECT COUNT(*) FROM items WHERE tipo='evento' AND ultima_ts>=?", (t - 120,)).fetchone()[0]
                    out.append({"id": OFFSET_BANDEJA_INBOX - 1, "ts": int(t), "actor": "bandeja", "fuente": "sistema" if pausado else "tareas",
                                "tipo": "leyo", "modo": "sombra",
                                "titulo": "La bandeja estaba en pausa" if pausado else f"La bandeja revisó {n_t} tareas y {n_e} eventos",
                                "detalle": None, "flujo": None, "ref": None})
        finally:
            c.close()
    except (sqlite3.Error, OSError, ValueError):
        return out
    return [dict(f, titulo=seguro(f["titulo"], 120), detalle=seguro(f["detalle"], 200) if f.get("detalle") else None) for f in out]


def _de_accion(r):
    sombra, modo = r["modo"] == "sombra", "sombra" if r["modo"] == "sombra" else "vivo"
    tit = _titulo_entre_comillas(r["detalle"])
    base = {"id": OFFSET_BANDEJA_ACCION + r["rid"], "ts": int(r["ts"]), "actor": "bandeja", "modo": modo, "flujo": None, "ref": f"bandeja:{r['rid']}"}
    nombre = {"gemela": "tarea gemela", "aplicar": "candidatura", "investigar": "investigación"}.get(r["tipo"], r["tipo"])
    fuente = "agenda" if r["tipo"] == "gemela" else "tareas"
    if r["estado"] == "sombra":
        return {**base, "fuente": fuente, "tipo": "propuso", "titulo": f"Habría creado {nombre}" + (f": {tit}" if tit else ""), "detalle": None if tit else r["detalle"]}
    if r["estado"] == "hecho":
        return {**base, "fuente": fuente, "tipo": "escribio", "titulo": f"Creó {nombre}" + (f": {tit}" if tit else ""), "detalle": None if tit else r["detalle"]}
    if r["estado"] == "omitido":
        return {**base, "fuente": fuente, "tipo": "descarto", "titulo": f"No toca {nombre} (ya existía antes de activar)", "detalle": r["detalle"]}
    return {**base, "fuente": fuente, "tipo": "fallo", "titulo": f"No pudo crear {nombre}" if r["estado"] == "fallido" else f"Reintenta {nombre}",
            "detalle": r["detalle"]}


def _de_inbox(r):
    base = {"id": OFFSET_BANDEJA_INBOX + r["id"], "ts": int(r["ts"]), "actor": "bandeja", "flujo": None, "ref": f"bandeja:i{r['id']}"}
    texto = limpio(r["texto"], 160)
    if r["tipo"] == "error":
        return {**base, "fuente": "sistema", "tipo": "fallo", "modo": "vivo" if r["modo"] == "vivo" else "sombra", "titulo": texto, "detalle": None}
    if r["modo"] == "vivo" and r["entregado"] == 1:
        return {**base, "fuente": "tareas", "tipo": "aviso", "modo": "vivo", "titulo": f"Avisó: {texto}", "detalle": None}
    return {**base, "fuente": "tareas", "tipo": "propuso", "modo": "sombra" if r["modo"] != "vivo" else "vivo",
            "titulo": ("Habría avisado: " if r["modo"] != "vivo" else "Va a avisar: ") + texto, "detalle": None}


def _del_vigia(db, desde_ts, hasta_ts, fuente=None, tipo=None):
    q, a = "SELECT * FROM registro WHERE ts>=? AND ts<?", [desde_ts, hasta_ts]
    for col, v in (("fuente", fuente), ("tipo", tipo)):
        if v:
            q += f" AND {col}=?"; a.append(v)
    return [dict(_fila(r), ts=r["ts"]) for r in db.c.execute(q + " ORDER BY ts DESC, id DESC", a)]


def consultar(db, *, desde=None, dia=None, fuente=None, tipo=None, n=100):
    """→ dict del contrato: {ok, items (más reciente primero), resumen del día, n}. Mezcla vigía + bandeja (solo lectura)."""
    hoy = db.hoy()
    ahora_ts = db.ts()
    if desde:
        d0, d1 = int(parsea_instante(desde).timestamp()), ahora_ts + 86400
    elif dia:
        d0, d1 = limites_dia(dia)
    else:
        d0, d1 = 0, ahora_ts + 86400
    def todo(a, b, f=None, t=None):
        filas = _del_vigia(db, a, b, f, t) + [x for x in de_bandeja(a, b) if (not f or x["fuente"] == f) and (not t or x["tipo"] == t)]
        return sorted(filas, key=lambda x: (x["ts"], x["id"]), reverse=True)
    filas = todo(d0, d1, fuente, tipo)[:max(1, min(int(n), 1000))]
    items = [dict(x, ts=_a_iso(x["ts"])) for x in filas]
    dia_res = dia or hoy
    r0, r1 = limites_dia(dia_res)
    por = {f: {t: 0 for t in TIPOS} for f in FUENTES}
    tot = {t: 0 for t in TIPOS}
    for x in todo(r0, r1):
        por[x["fuente"]][x["tipo"]] += 1
        tot[x["tipo"]] += 1
    return {"ok": True, "items": items, "resumen": {"dia": dia_res, **tot, "por_fuente": por}, "n": len(items)}


ROTULO_TIPO = {"leyo": "Leyó", "propuso": "Propuso", "escribio": "Escribió", "descarto": "Descartó", "fallo": "Falló", "aviso": "Avisó"}
ROTULO_ACTOR = {"vigia": "Vigía", "bandeja": "Bandeja", "app": "Fran"}
ROTULO_FUENTE = {"wa": "WhatsApp", "correo": "Correo", "agenda": "Agenda", "tareas": "Tareas", "sistema": "Sistema"}


def texto_legible(res):
    """Salida para personas (sin --json)."""
    r = res["resumen"]
    cab = (f"Actividad del {r['dia'][8:10]}/{r['dia'][5:7]}: {r['leyo']} lecturas, {r['propuso']} propuestas, {r['escribio']} cosas escritas en Google, "
           f"{r['descarto']} descartes, {r['fallo']} fallos y {r['aviso']} avisos enviados.")
    if not res["items"]:
        return cab + "\nNo hay actividad que enseñar con ese filtro."
    lineas = [cab, ""]
    for x in res["items"]:
        d = datetime.fromisoformat(x["ts"])
        marca = " (sombra)" if x["modo"] == "sombra" and x["tipo"] in ("propuso", "aviso", "escribio") else ""
        flujo = f" [flujo {x['flujo']}]" if x["flujo"] else ""
        lineas.append(f"{d:%d/%m %H:%M} · {ROTULO_ACTOR[x['actor']]} · {ROTULO_FUENTE[x['fuente']]} · {ROTULO_TIPO[x['tipo']]}: {x['titulo']}{flujo}{marca}"
                      + (f"\n      {x['detalle']}" if x["detalle"] else ""))
    return "\n".join(lineas)
