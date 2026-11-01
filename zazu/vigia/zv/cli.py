"""CLI `zv`. Nada de aquí envía mensajes: `draft` solo IMPRIME el comando visible de wacli (para que el hook de aprobación
de Hermes se lo enseñe a Fran). `sombra off` y `modo` son los dos interruptores de la entrega real."""
import argparse
import json
import shlex
import sys
from datetime import datetime, timedelta

from . import config, ciclo as _ciclo, flujos, gastos, permisos, registro, wa
from .db import DB
from .priv import limpio


def _fila(a):
    return (f"{a['codigo']:<4} #{a['id']:<4} P{a['prio']} {a['fuente']:<6} {a['tipo']:<13} {a['entrega']:<10} {a['estado']:<9} "
            f"{a['titulo']}" + (f" · {a['detalle']}" if a["detalle"] else ""))


def cmd_list(a, db):
    filas = db.listar(estado=a.estado, fuente=a.fuente, dia=a.dia, limite=a.n, solo_items=a.items)
    for r in reversed(filas):
        print(_fila(r))
    print(f"({len(filas)} avisos)")


def cmd_show(a, db):
    r = db.buscar(a.codigo)
    if not r:
        print("No encuentro ese aviso.")
        return 1
    for k in r.keys():
        v = r[k]
        if v in (None, "") or k in ("destino",):
            continue
        if k in ("creado", "aviso_en", "vence", "entregado_en", "accion_en", "pospuesto_hasta"):
            v = datetime.fromtimestamp(v, config.TZ).strftime("%Y-%m-%d %H:%M")
        print(f"{k:>14}: {v}")
    ev = r["evidencia"] or ""
    if ev.startswith("chat="):
        d = dict(p.split("=", 1) for p in ev.split(";") if "=" in p)
        print("\nPara ver el mensaje de origen (solo lectura):")
        print(f"  wacli --read-only messages context --chat {shlex.quote(d.get('chat', ''))} --id {shlex.quote(d.get('id', ''))}")
    return 0


def cmd_draft(a, db):
    """Imprime el comando de envío; NO lo ejecuta. Lo corre Zazu como comando visible y el hook pide el OK a Fran."""
    r = db.buscar(a.codigo)
    if not r or not r["borrador"] or not r["destino"]:
        print(f"{a.codigo}: no hay borrador con destinatario. Nada que enviar.")
        return 1
    print("Comando (NO se ha ejecutado; ejecútalo tal cual para que Fran lo apruebe):")
    print(f"wacli send text --to {shlex.quote(r['destino'])} --message {shlex.quote(r['borrador'])}")
    return 0


def _estado(nuevo):
    def f(a, db):
        r = db.buscar(a.codigo)
        if not r:
            print("No encuentro ese aviso.")
            return 1
        hasta = None
        if nuevo == "luego":
            hasta = int((config.ahora() + timedelta(hours=a.horas)).timestamp())
        db.marcar(r["id"], nuevo, hasta)
        if nuevo == "descartado" and permisos.es_propuesta(r):      # «No» / «Descartar» a una propuesta: cuenta como un «no»
            db.set(r["id"], decision="no")
            permisos.anotar_respuesta(db, r["permiso"], False)
        print(f"{r['codigo']} → {nuevo}" + (f" (vuelve en {a.horas} h)" if hasta else ""))
        quien = {"hecho": "Marcado como hecho", "descartado": "Descartado", "luego": f"Pospuesto {a.horas:g} h" if nuevo == "luego" else ""}[nuevo]
        registro.anota(db, "descarto", r["fuente"] if r["fuente"] in registro.FUENTES else "sistema", f"{quien}: {r['titulo']}", None, actor="app",
                       ref=f"aviso:{r['id']}", modo="sombra" if r["entrega"] in ("sombra", "silencioso") else "vivo")
        return 0
    return f


def cmd_responder(a, db):
    """zv responder <id> si|no|siempre|nunca [--json]: respuesta de Fran a una propuesta (la app la manda). No escribe en Google.
    Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: tools/proactive_tools.py (parse_approval_response).
    Cambios: un subcomando con la respuesta ya elegida (sin leer texto libre) y reglas en permisos.responder."""
    r = db.buscar(a.codigo)
    if not r:
        return _salida_json({"ok": False, "error": "no encuentro ese aviso"}, 1) if a.json else (print("No encuentro ese aviso.") or 1)
    ok, msg = permisos.responder(db, r, a.que)
    if ok:
        txt = {"si": "Aceptada", "no": "Descartada", "siempre": "Aceptada (y «siempre» para las parecidas)", "nunca": "Descartada (y «nunca» para las parecidas)"}[a.que]
        registro.anota(db, "descarto", r["fuente"] if r["fuente"] in registro.FUENTES else "sistema", f"{txt}: {r['titulo']}", None, actor="app",
                       ref=f"aviso:{r['id']}", modo="sombra" if r["accion"] in (None, "sombra") else "vivo")
    if a.json:
        return _salida_json({"ok": ok, "mensaje" if ok else "error": msg}, 0 if ok else 1)
    print(f"{r['codigo']}: {msg}")
    return 0 if ok else 1


def cmd_permisos(a, db):
    """zv permisos [--json] · zv permisos quitar <clave>: las reglas «siempre / nunca» que Fran ha dado."""
    if a.accion == "quitar":
        if not a.clave or not permisos.CLAVE_OK.fullmatch(a.clave):
            return _salida_json({"ok": False, "error": "clave no válida"}, 2) if a.json else (print("clave no válida") or 2)
        ok = permisos.quitar(db, a.clave)
        return _salida_json({"ok": ok, **({"mensaje": "regla quitada"} if ok else {"error": "esa regla no existe"})}, 0 if ok else 1) if a.json \
            else (print("Regla quitada." if ok else "Esa regla no existe.") or (0 if ok else 1))
    reglas = permisos.listar(db)
    if a.json:
        return _salida_json({"ok": True, "permisos": reglas})
    if not reglas:
        print("No hay reglas «siempre / nunca».")
    for x in reglas:
        print(f"{x['decision']:<7} {x['clave']}  (sí {x['veces_si']} · no {x['veces_no']} · aplicada {x['aplicada']})" + (f" · p. ej. «{x['ejemplo']}»" if x["ejemplo"] else ""))
    return 0


def cmd_pausa(a, db):
    config.conf_dir().mkdir(parents=True, exist_ok=True)
    config.f_pausa().touch()
    print("PAUSA puesta: el vigía no hace nada desde el próximo ciclo. Quitarla: zv reanudar")


def cmd_reanudar(a, db):
    config.f_pausa().unlink(missing_ok=True)
    print("PAUSA quitada.")


def cmd_sombra(a, db):
    cfg = config.cargar()
    if a.valor == "off":
        if not a.si:
            print("Esto activa la entrega REAL (WhatsApp a tu chat y escritura en Google) para los vigías en modo 'activo'.\n"
                  "Hoy ninguno lo está (config.json › modo). Para confirmarlo: zv sombra off --si")
            return 1
        config.conf_dir().mkdir(parents=True, exist_ok=True)
        config.f_entrega().touch()
        print("ENTREGA_ACTIVA puesta. Entregan/escriben solo los vigías con modo 'activo':", {k: v for k, v in cfg["modo"].items()})
        print("Para activar uno: zv modo wa activo   (correo | agenda | wa)")
    elif a.valor == "on":
        config.f_entrega().unlink(missing_ok=True)
        print("Modo sombra: no se entrega ni se escribe nada (todo queda en la bandeja y en sombra.log).")
    else:
        print("sombra" if not config.entrega_global() else "ENTREGA_ACTIVA puesta (decide el modo de cada vigía)")
    return 0


def cmd_avisos(a, db):
    """Interruptor de los AVISOS (notificaciones), aparte del de escribir en Google (zv sombra off)."""
    cfg = config.cargar()
    if a.valor in ("on", "off"):
        config.actualizar("entrega.avisos", a.valor == "on")
        cfg = config.cargar()
        print("Avisos " + ("ACTIVADOS" if a.valor == "on" else "apagados (vuelven a la sombra)") + f" por el canal «{config.canal(cfg)}». Escribir en Google sigue igual: "
              + ("permitido" if config.entrega_global() else "NO (falta ENTREGA_ACTIVA)") + ".")
    else:
        print(f"avisos: {'ACTIVADOS' if (cfg.get('entrega') or {}).get('avisos') else 'apagados'} · canal: {config.canal(cfg)} · escribir en Google: "
              + ("permitido" if config.entrega_global() else "NO"))


def cmd_modo(a, db):
    cfg = config.cargar()
    if a.vigia not in cfg["modo"] or a.valor not in ("sombra", "activo"):
        print("uso: zv modo wa|correo|agenda sombra|activo")
        return 1
    cfg["modo"][a.vigia] = a.valor
    config.guardar_cfg(cfg)
    print(f"modo {a.vigia} = {a.valor}" + ("" if a.valor == "sombra" or config.entrega_global() else "  (sigue sin entregar: falta ENTREGA_ACTIVA, zv sombra off --si)"))


def cmd_status(a, db):
    cfg = config.cargar()
    ahora = db.ts()
    avisos_on = bool((cfg.get("entrega") or {}).get("avisos"))
    print(f"PAUSA: {'SÍ' if config.pausado() else 'no'} · escribir en Google: {'PUESTO' if config.entrega_global() else 'apagado (sombra)'} · avisos: {'ACTIVADOS (' + config.canal(cfg) + ')' if avisos_on or config.entrega_global() else 'apagados (sombra)'}")
    for k, v in cfg["modo"].items():
        real = config.aviso_real(cfg, k)
        print(f"  {k:<7} modo={v:<7} → avisos {'REALES' if real else 'sombra'} · Google {'sí' if config.modo_real(cfg, k) else 'no'}")
    print("Latidos:")
    for k, v in sorted(db.latidos().items()):
        print(f"  {k:<8} hace {(ahora - v['ts']) // 60:>4} min · {'ok' if v['ok'] else 'FALLA'} · fallos seguidos {v['fallos']}" + (f" · {v['detalle']}" if v['detalle'] else ""))
    c = db.c
    print("Bandeja:", dict(c.execute("SELECT entrega, COUNT(*) FROM avisos WHERE silencioso=0 GROUP BY entrega").fetchall()),
          "· items WhatsApp:", dict(c.execute("SELECT accion, COUNT(*) FROM avisos WHERE tipo LIKE 'item_%' GROUP BY accion").fetchall()))
    print(f"Modelo hoy: {db.uso_llm_hoy()}/{cfg['llm']['max_por_dia']} llamadas (máx. {cfg['llm']['max_por_ciclo']} por ciclo) · habilitado={cfg['llm']['habilitado']}")
    print("Contadores de hoy:", db.contadores())
    try:
        print("Vencidas (agenda):", db.kv_get("agenda_vencidas", "?"))
    except Exception:
        pass


def cmd_resumen_dia(a, db):
    dia = a.fecha or db.hoy()
    items = db.listar(dia=dia, solo_items=True, limite=100)
    if not items:
        print(f"Capturado de WhatsApp el {dia}: nada.")
        return 0
    print(f"Capturado de WhatsApp el {dia}: {len(items)} cosa(s).")
    for r in reversed(items):
        cuando = f" para el {r['due'][8:10]}/{r['due'][5:7]}" + (f" {r['hora']}" if r["hora"] else "") if r["due"] else ""
        est = {"sombra": "(sombra: no creada)", "creado": "(creada en Google)", "pendiente": "(por crear)", "tope": "(tope diario: no creada)",
               "duplicado": "(ya existía)", "fallido": "(falló)", "evento_creado": "(evento creado)"}.get(r["accion"], "")
        print(f"- {'Evento tentativo' if r['tipo'] == 'item_evento' else 'Tarea'}: {r['titulo']}{cuando} · {r['chat']} {est}")
    return 0


def cmd_ciclo(a, db):
    return _ciclo.ciclo(a.solo)


def cmd_wa(a, db):
    cfg = config.cargar()
    if a.sub == "simular":
        from .llm import Presupuesto
        r = wa.ejecutar(db, cfg, Presupuesto(db, {**cfg, "llm": {**cfg["llm"], "habilitado": False}}), simular=True, desde_h=a.horas)
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        st = wa.leer_estado()
        print(json.dumps({"hwm": st.get("hwm"), "pendientes": len(st.get("pend", {})), "juzgados": len(st.get("juzgado", {}))}))
    return 0


def _salida_json(obj, rc=0):
    print(json.dumps(obj, ensure_ascii=False))
    return rc


def cmd_registro(a, db):
    """Lo que han leído, propuesto y escrito el vigía y la bandeja. --json para el hub (contrato en el informe de la sesión)."""
    try:
        if a.dia:
            datetime.strptime(a.dia, "%Y-%m-%d")
        if a.desde:
            registro.parsea_instante(a.desde)
    except ValueError:
        msg = "fecha no válida: usa AAAA-MM-DD para --dia y AAAA-MM-DDTHH:MM:SS para --desde"
        return _salida_json({"ok": False, "error": msg}, 2) if a.json else (print(msg) or 2)
    res = registro.consultar(db, desde=a.desde, dia=a.dia, fuente=a.fuente, tipo=a.tipo, n=a.n)
    if a.json:
        return _salida_json(res)
    print(registro.texto_legible(res))
    return 0


def cmd_flujos(a, db):
    lista = flujos.listar(db, config.cargar(crear=False))
    if a.json:
        return _salida_json({"ok": True, "flujos": lista})
    print(flujos.texto_legible(lista))
    return 0


def cmd_flujo(a, db):
    """zv flujo <id> modo sombra|activo [--confirmo] · zv flujo <id> pausa|reanuda. Siempre imprime JSON ({ok, modo, pausado, mensaje|error})."""
    if a.accion == "modo" and a.valor is None:
        return _salida_json({"ok": False, "error": "falta el modo: sombra o activo"}, 2)
    r = flujos.cambiar(config.cargar(crear=False), a.id, a.accion, a.valor, a.confirmo)
    return _salida_json(r, 0 if r["ok"] else 1)


def cmd_gastos(a, db):
    """zv gastos [--mes AAAA-MM] [--json] · zv gastos resumen · zv gastos recalcular [--releer]. Solo `recalcular` escribe (su propia tabla, nada en Google)."""
    cfg = config.cargar(crear=False)
    try:
        if a.accion == "recalcular":
            r = gastos.recalcular(db, cfg, releer=a.releer)
            return _salida_json(r) if a.json else (print(r["mensaje"]) or 0)
        if a.accion == "resumen":
            print(gastos.resumen_texto(db, cfg))
            return 0
        d = gastos.consulta_mes(db, cfg, a.mes)
    except ValueError as e:
        return _salida_json({"ok": False, "error": str(e)}, 2) if a.json else (print(f"zv: {e}") or 2)
    if a.json:
        return _salida_json(d)
    print(gastos.texto_gastos(d))
    return 0


def cmd_suscripciones(a, db):
    d = gastos.lista_suscripciones(db, config.cargar(crear=False))
    if a.json:
        return _salida_json(d)
    print(gastos.texto_suscripciones(d))
    return 0


def cmd_suscripcion(a, db):
    """zv suscripcion cancelada|quiero-cancelar|sigue|deshacer <comercio> --json. Solo escribe config.json (decisión de Fran) y la tabla propia."""
    try:
        r = gastos.decidir(db, config.cargar(crear=False), a.accion, a.comercio)
    except ValueError as e:
        return _salida_json({"ok": False, "error": str(e)}, 2)
    return _salida_json(r)


def main(argv=None):
    p = argparse.ArgumentParser(prog="zv", description="Vigía de Zazu (sombra por defecto)")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("list", help="lista avisos"); s.add_argument("--estado"); s.add_argument("--fuente"); s.add_argument("--dia"); s.add_argument("-n", type=int, default=40); s.add_argument("--items", action="store_true"); s.set_defaults(f=cmd_list)
    s = sp.add_parser("show", help="detalle de un aviso (A3 o #id)"); s.add_argument("codigo"); s.set_defaults(f=cmd_show)
    s = sp.add_parser("draft", help="IMPRIME el comando wacli para enviar el borrador (no lo ejecuta)"); s.add_argument("codigo"); s.set_defaults(f=cmd_draft)
    for n in ("hecho", "descartar"):
        s = sp.add_parser(n); s.add_argument("codigo"); s.set_defaults(f=_estado("hecho" if n == "hecho" else "descartado"))
    s = sp.add_parser("luego"); s.add_argument("codigo"); s.add_argument("horas", type=float, nargs="?", default=3); s.set_defaults(f=_estado("luego"))
    s = sp.add_parser("responder", help="responde a una propuesta: si | no | siempre | nunca"); s.add_argument("codigo"); s.add_argument("que", choices=permisos.RESPUESTAS)
    s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_responder)
    s = sp.add_parser("permisos", help="reglas «siempre / nunca»: lista o `quitar <clave>`"); s.add_argument("accion", nargs="?", choices=["quitar"]); s.add_argument("clave", nargs="?")
    s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_permisos)
    sp.add_parser("pausa").set_defaults(f=cmd_pausa)
    sp.add_parser("reanudar").set_defaults(f=cmd_reanudar)
    s = sp.add_parser("sombra"); s.add_argument("valor", choices=["on", "off", "estado"], nargs="?", default="estado"); s.add_argument("--si", action="store_true"); s.set_defaults(f=cmd_sombra)
    s = sp.add_parser("avisos", help="avisos por la app: on | off | estado (no toca lo que se escribe en Google)"); s.add_argument("valor", choices=["on", "off", "estado"], nargs="?", default="estado"); s.set_defaults(f=cmd_avisos)
    s = sp.add_parser("modo"); s.add_argument("vigia"); s.add_argument("valor"); s.set_defaults(f=cmd_modo)
    sp.add_parser("status").set_defaults(f=cmd_status)
    s = sp.add_parser("resumen-dia", help="lo capturado de WhatsApp hoy (para el cierre del día)"); s.add_argument("--fecha"); s.set_defaults(f=cmd_resumen_dia)
    s = sp.add_parser("ciclo"); s.add_argument("--solo", choices=["wa", "correo", "agenda", "gastos"]); s.set_defaults(f=cmd_ciclo)
    s = sp.add_parser("wa"); s.add_argument("sub", choices=["simular", "estado"]); s.add_argument("--horas", type=float, default=24); s.set_defaults(f=cmd_wa)
    s = sp.add_parser("registro", help="qué han leído, propuesto y escrito el vigía y la bandeja")
    s.add_argument("--json", action="store_true"); s.add_argument("--desde"); s.add_argument("--dia")
    s.add_argument("--fuente", choices=registro.FUENTES); s.add_argument("--tipo", choices=registro.TIPOS); s.add_argument("-n", type=int, default=100); s.set_defaults(f=cmd_registro)
    s = sp.add_parser("flujos", help="los flujos automáticos: estado, modo y disparos"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_flujos)
    s = sp.add_parser("gastos", help="lo que pagas, leído de tu correo: lista del mes, `resumen` para WhatsApp o `recalcular`")
    s.add_argument("accion", nargs="?", choices=["resumen", "recalcular"]); s.add_argument("--mes"); s.add_argument("--json", action="store_true")
    s.add_argument("--releer", action="store_true", help="con recalcular: borra lo apuntado y vuelve a leer el correo"); s.set_defaults(f=cmd_gastos)
    s = sp.add_parser("suscripciones", help="suscripciones detectadas: importe, próximo cobro y total"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_suscripciones)
    s = sp.add_parser("suscripcion", help="decide sobre una suscripción"); s.add_argument("accion", choices=gastos.ACCIONES_SUB); s.add_argument("comercio"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_suscripcion)
    s = sp.add_parser("flujo", help="cambia un flujo: modo sombra|activo [--confirmo] · pausa · reanuda")
    s.add_argument("id"); s.add_argument("accion", choices=["modo", "pausa", "reanuda"]); s.add_argument("valor", nargs="?"); s.add_argument("--confirmo", action="store_true"); s.set_defaults(f=cmd_flujo)
    a = p.parse_args(argv)
    return a.f(a, DB()) or 0
