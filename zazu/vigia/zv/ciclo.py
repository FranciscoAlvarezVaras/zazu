"""Un ciclo del vigía (lo lanza zazu-vigia.timer cada 30 min de 08:00 a 20:00): wa → correo → agenda → acciones → entrega → mantenimiento.
Cada vigía falla por separado. PAUSA lo detiene todo. Un bloqueo de archivo evita ciclos solapados."""
import fcntl
import json
import os
import sys
import time

from . import acciones, agenda, config, correo, entrega, gastos, llm, registro, wa
from .db import DB


DESCARTES_WA = {"acuse": "acuses", "bot": "de bots", "grupo_no_dirigido": "de grupos sin hablarte a ti", "sin_texto": "sin texto", "reaccion": "reacciones",
                "borrado": "borrados", "silenciado": "de chats silenciados", "propio_o_ignorado": "de tu propio chat o ignorados"}
DE_QUE = {"wa": "WhatsApp", "correo": "el correo", "agenda": "la agenda", "gastos": "los gastos", "entrega": "la entrega de avisos"}


def _leyo(db, cfg, nombre, r):
    """Un «leyó» por fuente y ciclo, solo con cifras (nunca contenido)."""
    try:
        _leyo_(db, cfg, nombre, r)
    except (KeyError, TypeError):
        pass


def _leyo_(db, cfg, nombre, r):
    if nombre == "wa":
        if r.get("linea_base"):
            registro.anota(db, "leyo", "wa", "Primera lectura de WhatsApp: solo marco el punto de partida", "No apunto nada de lo anterior", cfg=cfg)
            return
        top = sorted((r.get("descartes") or {}).items(), key=lambda kv: -kv[1])[:3]
        desc = ", ".join(f"{v} {DESCARTES_WA.get(k, k)}" for k, v in top)
        registro.anota(db, "leyo", "wa", f"Leí {r['mensajes']} mensajes de WhatsApp, {r['relevantes']} con posible interés",
                       f"{r['chats_con_marca']} conversaciones con algo que mirar, {r['juzgados']} revisadas, {r['items']} cosas apuntadas" + (f". Descartados: {desc}" if desc else ""), cfg=cfg)
    elif nombre == "correo":
        base = r.get("baseline") or []
        registro.anota(db, "leyo", "correo", f"Leí {r['hilos']} hilos de correo, {r['nuevos']} nuevos",
                       (f"Primera lectura de {', '.join(base)}: punto de partida. " if base else "") + f"{r['alertas']} avisos, {r['ruido']} sin interés, {r.get('flujos', 0)} con algún flujo", cfg=cfg)
    elif nombre == "agenda":
        registro.anota(db, "leyo", "agenda", f"Leí {r['eventos']} eventos de la agenda",
                       f"{r['avisos']} avisos nuevos, {r.get('vencidas_cerradas', 0)} vencidas cerradas", cfg=cfg)
        registro.anota(db, "leyo", "tareas", f"Leí {r['tareas']} tareas de Google Tasks, {r.get('vencidas', 0)} vencidas", None, cfg=cfg)
    elif nombre == "gastos":
        if r.get("apagado") or not (r["nuevos"] or r["sospechosos"]):
            return          # solo cuando hay novedades: un «Leí 0» cada media hora sería ruido (y el «leyó» de correo ya sale una vez por ciclo)
        base = r.get("baseline") or []
        registro.anota(db, "leyo", "correo", f"Revisé {r['cuerpos']} correos de pagos y apunté {r['nuevos']} gastos nuevos",
                       (f"Fin de la lectura inicial de {', '.join(base)}. " if base else "") + f"{r['publicidad']} eran publicidad, {r['dudosos']} dudosos, {r['pendientes']} por revisar en próximos ciclos"
                       + (f", {r['llm']} consulta(s) al modelo" if r["llm"] else ""), cfg=cfg)


def _fallos(db, cfg, fuente, ok, detalle):
    """Latido + aviso de fallo (a la tercera seguida) + aviso de «resuelto». Los avisos de fallo van por la misma entrega (sombra incluida)."""
    if not ok:
        registro.anota(db, "fallo", fuente if fuente in registro.FUENTES else "sistema", f"No pude {'enviar los avisos' if fuente == 'entrega' else 'leer ' + DE_QUE.get(fuente, fuente)}",
                       detalle or None, cfg=cfg)
    ev = db.latido(fuente, ok, detalle)
    if ev == "fallo_alerta":
        db.alta(f"fallo:{fuente}:{db.episodio(fuente)}", "sistema", "fallo", f"El vigía de {fuente} falla desde hace {cfg['fallos']['umbral']} ciclos", prio=2,
                detalle=detalle[:150], ref=f"fallo:{fuente}")
    elif ev == "resuelto":
        db.alta(f"resuelto:{fuente}:{db.episodio(fuente)}", "sistema", "resuelto", f"El vigía de {fuente} vuelve a funcionar", prio=3, ref=f"fallo:{fuente}")


def ciclo(solo=None):
    cfg = config.cargar()
    db = DB()
    if config.pausado():
        db.latido("ciclo", True, "PAUSA activa: no se hace nada")
        db.close()
        print("zv: PAUSA activa; no se hace nada")
        return 0
    lock = open(config.estado_dir() / "ciclo.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("zv: otro ciclo está en marcha")
        return 0
    t0 = time.time()
    pres = llm.Presupuesto(db, cfg)
    resumen = {}
    for nombre, fn in (("wa", lambda: wa.ejecutar(db, cfg, pres)), ("correo", lambda: correo.ejecutar(db, cfg, pres)),
                       ("agenda", lambda: agenda.ejecutar(db, cfg)), ("gastos", lambda: gastos.ejecutar(db, cfg, pres))):
        if solo and nombre != solo:
            continue
        try:
            r = fn()
            ok, det = True, ""
            if nombre == "wa":
                if r.get("salud"):   # wacli sin latido o sesión revocada: un aviso cada 12 h
                    db.alta(f"fallo:wacli:{int(time.time() // (12 * 3600))}", "sistema", "fallo", "WhatsApp no se está sincronizando", prio=2, detalle=r["salud"][:150], ref="fallo:wacli")
                resumen["wa"] = acciones.aplicar_pendientes(db, cfg) | {k: v for k, v in r.items() if k not in ("descartes", "salud")}
                for k, v in (r.get("descartes") or {}).items():
                    db.contar(f"wa_descarte_{k}", v)
            elif nombre == "correo":
                if r["errores"]:
                    ok, det = False, "; ".join(f"{k}: {v}" for k, v in r["errores"].items())
                resumen["correo"] = {k: v for k, v in r.items() if k != "errores"} | {f"flujos_{k}": v for k, v in acciones.aplicar_flujos(db, cfg).items()}
            elif nombre == "gastos":
                if r["errores"]:
                    ok, det = False, "; ".join(f"{k}: {v}" for k, v in r["errores"].items())
                resumen["gastos"] = {k: v for k, v in r.items() if k not in ("errores", "baseline")} | {"baseline": len(r["baseline"])}
            else:
                if r["errores"]:
                    ok, det = False, "; ".join(f"{k}: {v}" for k, v in r["errores"].items())
                resumen["agenda"] = {k: v for k, v in r.items() if k != "errores"} | acciones.aplicar_gemelas(db, cfg)
            _leyo(db, cfg, nombre, r)
            _fallos(db, cfg, nombre, ok, det)
        except Exception as e:
            _fallos(db, cfg, nombre, False, f"{type(e).__name__}: {e}")
            resumen[nombre] = {"error": type(e).__name__}
    try:
        resumen["entrega"] = entrega.procesar(db, cfg)
    except Exception as e:
        _fallos(db, cfg, "entrega", False, f"{type(e).__name__}: {e}")
        resumen["entrega"] = {"error": type(e).__name__}
    else:
        _fallos(db, cfg, "entrega", True, "")
    db.purgar(cfg)
    db.cerrar_informativos(cfg)
    entrega.purgar_log()
    db.latido("ciclo", True, f"{int((time.time() - t0) * 1000)} ms")
    config.escribir_atomico(config.estado_dir() / "latido.json", json.dumps({"ts": int(time.time()), "latidos": {k: {"ts": v["ts"], "ok": v["ok"]} for k, v in db.latidos().items()},
                                                                              "entrega_real": config.entrega_global(), "modo": cfg["modo"]}))
    log = config.estado_dir() / "ciclos.log"
    try:
        if log.exists() and log.stat().st_size > 1_000_000:   # rotación simple: se queda con la mitad más reciente
            lineas = log.read_text().splitlines()
            config.escribir_atomico(log, "\n".join(lineas[len(lineas) // 2:]) + "\n")
    except OSError:
        pass
    with open(os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a") as f:   # solo cifras, nunca contenido
        f.write(json.dumps({"t": config.ahora().isoformat(timespec="seconds"), **resumen}, ensure_ascii=False) + "\n")
    print(json.dumps(resumen, ensure_ascii=False))
    db.close()
    lock.close()      # suelta el bloqueo ya (si no, una excepción capturada arriba lo retiene hasta que el recolector pase)
    return 0


if __name__ == "__main__":
    sys.exit(ciclo())
