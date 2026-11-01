"""ÚNICO sitio donde el vigía escribe en Google, y solo en modo activo (sin PAUSA + ENTREGA_ACTIVA + wa='activo').
Lista cerrada: crear tarea (tasks add + tasks update --notes), crear evento tentativo (calendar create) y su tarea gemela.
Nada de invitados, respuestas, borrados, correo ni WhatsApp. Nunca se escribe el texto del mensaje: solo el título corto ya
filtrado, el nombre del chat y la marca de idempotencia [ZV:<id>]."""
import json
import re
import subprocess
from datetime import datetime, timedelta

from . import config, flujos, reglas, registro
from .priv import seguro

PERMITIDOS = {("tasks", "add"), ("tasks", "update"), ("calendar", "create")}
FLAGS_OK = ("--title=", "--due=", "--notes=", "--summary=", "--from=", "--to=", "--start-timezone=", "--end-timezone=", "--description=")
DESTINOS_OK = {"@default", "primary"}
MARCA = re.compile(r"\[ZV:(\d+)\]")


class AccionError(Exception):
    pass


def _cuenta(cfg, etiqueta):
    return (cfg["correo"]["cuentas"] or {}).get(etiqueta)


def _escribir(cfg, etiqueta, partes):
    """Ejecuta UNA escritura permitida. `partes` = ['tasks','add','@default','--title=…',…]."""
    if tuple(partes[:2]) not in PERMITIDOS:
        raise AccionError("acción no permitida")
    if partes[2] not in DESTINOS_OK and not (partes[:2] == ["tasks", "update"] and partes[2] == "@default"):
        raise AccionError("destino no permitido")
    resto = partes[3:]
    if partes[:2] == ["tasks", "update"]:
        resto = resto[1:]   # el id de la tarea
    for p in resto:
        if not p.startswith(FLAGS_OK):
            raise AccionError("opción no permitida")
    cuenta = _cuenta(cfg, etiqueta)
    cmd = [config.bin_path("gog")] + ([f"--account={cuenta}"] if cuenta else []) + ["--no-input", "--gmail-no-send", "--json"] + partes
    env = reglas.recoger().ENV
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise AccionError(f"gog {partes[0]} {partes[1]} falló (código {r.returncode})")
    try:
        d = json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        d = {}
    for k in ("task", "event"):
        if isinstance(d.get(k), dict):
            d = d[k]
    return d


def _leer(cfg, etiqueta, args):
    return reglas.recoger().gog(args, _cuenta(cfg, etiqueta), intentos=1)


def _revisar_zazu():
    import importlib.util
    ruta = config.scripts_dir() / "revisar-zazu.py"
    spec = importlib.util.spec_from_file_location("revisar_zazu", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _notas(a):
    return f"De WhatsApp ({a['chat']}, {a['detalle'].rsplit(', ', 1)[-1].rstrip(')')}) · [ZV:{a['id']}]"


def _cuando(due, hora=None):
    return (f" (para el {due[8:10]}/{due[5:7]}" + (f" {hora}" if hora else "") + ")") if due else ""


def _reg(db, cfg, tipo, fuente, titulo, detalle=None, a=None, flujo=None, **k):
    """Atajo para anotar en el registro lo que hace este módulo (nunca rompe una escritura)."""
    registro.anota(db, tipo, fuente, titulo, detalle, flujo=flujo, ref=f"aviso:{a['id']}" if a is not None else None, cfg=cfg, **k)


def aplicar_pendientes(db, cfg, max_por_ciclo=5):
    """Crea en Google los items pendientes de WhatsApp. Devuelve contadores. Exige el flujo «wa-peticion» activo y sin pausa,
    además del interruptor general (PAUSA ausente + ENTREGA_ACTIVA + vigía de WhatsApp en activo)."""
    res = {"creados": 0, "duplicados": 0, "fallidos": 0}
    if not (config.modo_real(cfg, "wa") and flujos.escribe_ahora(cfg, "wa-peticion", "wa")[0]):
        return res
    filas = db.c.execute("SELECT * FROM avisos WHERE tipo LIKE 'item_%' AND accion IN ('pendiente','evento_creado') ORDER BY id LIMIT ?", (max_por_ciclo,)).fetchall()
    if not filas:
        return res
    rz = None
    lista_t = cfg["wa"]["lista_tareas"]
    cache_tareas = {}
    for a in filas:
        et = a["cuenta"] or cfg["wa"]["cuenta_destino"]
        try:
            if et not in cache_tareas:
                d = _leer(cfg, et, ["tasks", "list", lista_t, "--max=100", "--all", "--show-completed", "--show-hidden"])
                cache_tareas[et] = reglas.recoger().lista(d, "tasks", "items")
            tareas = cache_tareas[et]
            # idempotencia: ¿ya existe una con nuestra marca? (el estado local pudo perderse)
            ya = next((t for t in tareas if f"[ZV:{a['id']}]" in (t.get("notes") or "")), None)
            if ya and a["accion"] == "pendiente":
                db.set(a["id"], accion="creado", accion_ref=ya.get("id"), accion_en=db.ts())
                res["duplicados"] += 1
                _reg(db, cfg, "descarto", "wa", f"Ya estaba creada en Google: {a['titulo']}", "Encontré su marca [ZV]", a, "wa-peticion")
                continue
            if a["accion"] == "pendiente":
                rz = rz or _revisar_zazu()
                dia = datetime.strptime(a["due"], "%Y-%m-%d").date() if a["due"] else None
                if rz.tiene_tarea(a["titulo"], dia or config.ahora().date(), tareas) and dia:
                    db.set(a["id"], accion="duplicado", accion_en=db.ts())
                    res["duplicados"] += 1
                    _reg(db, cfg, "descarto", "wa", f"No creo la tarea: ya hay una parecida: {a['titulo']}", None, a, "wa-peticion")
                    continue
            if a["tipo"] == "item_evento" and a["accion"] == "pendiente":
                ini = datetime.fromisoformat(f"{a['due']}T{a['hora']}:00")
                fin = ini + timedelta(minutes=a["dur"] or 60)
                ev = _escribir(cfg, et, ["calendar", "create", "primary", f"--summary=¿? {a['titulo']}",
                                         f"--from={ini:%Y-%m-%dT%H:%M:%S}", f"--to={fin:%Y-%m-%dT%H:%M:%S}",
                                         "--start-timezone=Europe/Madrid", "--end-timezone=Europe/Madrid",
                                         f"--description=Origen: WhatsApp de {a['chat']} · [ZV:{a['id']}]"])
                db.set(a["id"], accion="evento_creado", accion_ref=f"ev:{ev.get('id')}", accion_en=db.ts())
                _reg(db, cfg, "escribio", "wa", f"Creé evento tentativo: ¿? {a['titulo']}{_cuando(a['due'], a['hora'])}", f"Origen: WhatsApp de {a['chat']}", a, "wa-peticion",
                     clave=f"escribio:ev:{a['id']}")
                if not cfg["wa"].get("gemela_evento", False):
                    # sin tarea gemela (antes siempre se creaba una con el mismo título y la agenda salía duplicada): el evento basta
                    db.set(a["id"], accion="creado", accion_en=db.ts(), error=None)
                    res["creados"] += 1
                    continue
                a = db.c.execute("SELECT * FROM avisos WHERE id=?", (a["id"],)).fetchone()
            # tarea (o tarea gemela del evento)
            partes = ["tasks", "add", lista_t, f"--title={a['titulo']}"] + ([f"--due={a['due']}"] if a["due"] else [])
            t = _escribir(cfg, et, partes)
            if t.get("id"):
                _escribir(cfg, et, ["tasks", "update", lista_t, t["id"], f"--notes={_notas(a)}"])
            ref = (a["accion_ref"] + "|" if a["accion_ref"] else "") + f"task:{t.get('id')}"
            db.set(a["id"], accion="creado", accion_ref=ref, accion_en=db.ts(), error=None)
            res["creados"] += 1
            _reg(db, cfg, "escribio", "wa", f"Creé tarea: {a['titulo']}{_cuando(a['due'])}", f"Origen: WhatsApp de {a['chat']}", a, "wa-peticion",
                 clave=f"escribio:t:{a['id']}")
        except Exception as e:   # un fallo no se traga: reintentos y luego 'fallido'
            n = a["intentos"] + 1
            db.set(a["id"], intentos=n, error=seguro(f"{type(e).__name__}: {e}", 120), accion="fallido" if n >= 3 else a["accion"])
            res["fallidos"] += 1
            _reg(db, cfg, "fallo", "wa", f"No pude crear en Google: {a['titulo']}", f"{type(e).__name__} (intento {n})", a, "wa-peticion")
    return res


def aplicar_gemelas(db, cfg, max_por_ciclo=5):
    """Tarea gemela de los eventos de Fran (regla del 07/10). Solo modo activo del vigía de agenda."""
    res = {"creadas": 0, "ya_existian": 0, "fallidas": 0}
    if not config.modo_real(cfg, "agenda"):
        return res
    filas = db.c.execute("SELECT * FROM avisos WHERE tipo='accion_gemela' AND accion='pendiente' ORDER BY id LIMIT ?", (max_por_ciclo,)).fetchall()
    rz = _revisar_zazu() if filas else None
    for a in filas:
        try:
            lista_t = cfg["wa"]["lista_tareas"]
            d = _leer(cfg, a["cuenta"], ["tasks", "list", lista_t, "--max=100", "--all", "--show-completed", "--show-hidden"])
            tareas = reglas.recoger().lista(d, "tasks", "items")
            dia = datetime.strptime(a["due"], "%Y-%m-%d").date()
            if any(f"[ZV:{a['id']}]" in (t.get("notes") or "") for t in tareas) or rz.tiene_tarea(a["titulo"], dia, tareas):
                db.set(a["id"], accion="ya_existia", accion_en=db.ts())
                res["ya_existian"] += 1
                _reg(db, cfg, "descarto", "agenda", f"No creo la tarea gemela: ya existe: {a['titulo']}", None, a)
                continue
            t = _escribir(cfg, a["cuenta"], ["tasks", "add", lista_t, f"--title={a['titulo']}", f"--due={a['due']}"])
            if t.get("id"):
                _escribir(cfg, a["cuenta"], ["tasks", "update", lista_t, t["id"], f"--notes=gemela de evento · [ZV:{a['id']}]"])
            db.set(a["id"], accion="creado", accion_ref=f"task:{t.get('id')}", accion_en=db.ts())
            res["creadas"] += 1
            _reg(db, cfg, "escribio", "agenda", f"Creé tarea gemela: {a['titulo']}{_cuando(a['due'])}", "gemela de un evento", a, clave=f"escribio:g:{a['id']}")
        except Exception as e:
            n = a["intentos"] + 1
            db.set(a["id"], intentos=n, error=seguro(f"{type(e).__name__}: {e}", 120), accion="fallido" if n >= 3 else "pendiente")
            res["fallidas"] += 1
            _reg(db, cfg, "fallo", "agenda", f"No pude crear la tarea gemela: {a['titulo']}", f"{type(e).__name__} (intento {n})", a)
    return res


def aplicar_flujos(db, cfg, max_por_ciclo=5):
    """Escribe en Google lo que dejaron pendiente los flujos (filas flujo_tarea / flujo_evento con accion='pendiente').
    Vuelve a comprobar los interruptores (flujo activo y sin pausa + interruptor general): si ya no se cumplen, la fila pasa a
    sombra y NO se escribe. Idempotente: marca [ZV:<id>] en las notas / la descripción y comprobación de duplicados (revisar-zazu)."""
    res = {"creados": 0, "duplicados": 0, "fallidos": 0, "en_sombra": 0}
    filas = db.c.execute("SELECT * FROM avisos WHERE tipo IN ('flujo_tarea','flujo_evento') AND accion='pendiente' ORDER BY id LIMIT ?", (max_por_ciclo,)).fetchall()
    if not filas:
        return res
    ctx = flujos.Contexto(cfg)
    for a in filas:
        fid = flujos.id_de(a)
        disp = flujos.disparo_de(a)
        ok, motivo = flujos.escribe_ahora(cfg, fid, a["fuente"]) if fid else (False, "flujo desconocido")
        if not ok:
            db.set(a["id"], accion="sombra")
            res["en_sombra"] += 1
            _reg(db, cfg, "descarto", a["fuente"], f"No escribo ahora: {a['titulo']}", motivo, a, fid, modo="sombra", disparo=disp)
            continue
        et, marca, lista_t = a["cuenta"] or cfg["flujos"]["cuenta_destino"], f"[ZV:{a['id']}]", cfg["flujos"]["lista_tareas"]
        origen = f"Origen: correo ({a['chat']}) · flujo {fid} · {marca}"
        dia = datetime.strptime(a["due"], "%Y-%m-%d").date()
        try:
            if a["tipo"] == "flujo_tarea":
                tareas = ctx.tareas()
                if tareas is None:
                    raise AccionError("no pude leer las tareas para comprobar duplicados")
                ya = next((t for t in tareas if marca in (t.get("notes") or "")), None)
                if ya or flujos.tarea_duplicada(ctx, a["titulo"], dia, (a["chat"],)):
                    db.set(a["id"], accion="creado" if ya else "duplicado", accion_ref=f"task:{ya.get('id')}" if ya else None, accion_en=db.ts())
                    res["duplicados"] += 1
                    _reg(db, cfg, "descarto", a["fuente"], f"No creo la tarea: ya existe: {a['titulo']}", "Encontré su marca [ZV]" if ya else None, a, fid, disparo=disp)
                    continue
                t = _escribir(cfg, et, ["tasks", "add", lista_t, f"--title={a['titulo']}", f"--due={a['due']}"])
                if t.get("id"):
                    _escribir(cfg, et, ["tasks", "update", lista_t, t["id"], f"--notes={origen}"])
                ctx.anota_tarea(a["titulo"], dia, marca)
                db.set(a["id"], accion="creado", accion_ref=f"task:{t.get('id')}", accion_en=db.ts(), error=None)
                _reg(db, cfg, "escribio", a["fuente"], f"Creé tarea: {a['titulo']}{_cuando(a['due'])}", f"Origen: correo de {a['chat']}", a, fid, disparo=disp, clave=f"escribio:{a['id']}")
            else:
                eventos = ctx.eventos(dia)
                if eventos is None:
                    raise AccionError("no pude leer el calendario para comprobar duplicados")
                ya = next((e for e in eventos if marca in (e.get("description") or "")), None)
                if ya or flujos.evento_duplicado(ctx, a["titulo"], dia, (a["chat"],), a["titulo"].startswith("Viaje")):
                    db.set(a["id"], accion="creado" if ya else "duplicado", accion_ref=f"ev:{ya.get('id')}" if ya else None, accion_en=db.ts())
                    res["duplicados"] += 1
                    _reg(db, cfg, "descarto", a["fuente"], f"No creo el evento: ya hay uno parecido: {a['titulo']}", "Encontré su marca [ZV]" if ya else None, a, fid, disparo=disp)
                    continue
                ini = datetime.fromisoformat(f"{a['due']}T{a['hora']}:00")
                fin = ini + timedelta(minutes=a["dur"] or 60)
                ev = _escribir(cfg, et, ["calendar", "create", "primary", f"--summary=¿? {a['titulo']}", f"--from={ini:%Y-%m-%dT%H:%M:%S}", f"--to={fin:%Y-%m-%dT%H:%M:%S}",
                                         "--start-timezone=Europe/Madrid", "--end-timezone=Europe/Madrid", f"--description={origen}"])
                ctx.anota_evento(a["titulo"], dia, marca)
                db.set(a["id"], accion="creado", accion_ref=f"ev:{ev.get('id')}", accion_en=db.ts(), error=None)
                _reg(db, cfg, "escribio", a["fuente"], f"Creé evento tentativo: ¿? {a['titulo']}{_cuando(a['due'], a['hora'])}", f"Origen: correo de {a['chat']}", a, fid,
                     disparo=disp, clave=f"escribio:{a['id']}")
            res["creados"] += 1
        except Exception as e:
            n = a["intentos"] + 1
            db.set(a["id"], intentos=n, error=seguro(f"{type(e).__name__}: {e}", 120), accion="fallido" if n >= 3 else "pendiente")
            res["fallidos"] += 1
            _reg(db, cfg, "fallo", a["fuente"], f"No pude crear en Google: {a['titulo']}", f"{type(e).__name__} (intento {n})", a, fid, disparo=disp)
    return res
