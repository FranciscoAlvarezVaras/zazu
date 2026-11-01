#!/usr/bin/env python3
"""Vigilante de HolaZazu: cada 5 min recoge los registros para el visor, comprueba que todo funcione y avisa a Fran si algo falla.

Lo lanza un temporizador de systemd (zazu-vigilante.timer), aparte del Hub: así avisa aunque el Hub se caiga.
1. Recoge lo nuevo de los registros de la app, Zazu y los invitados (visor.py) y reescribe VISOR.md en la raíz de Spirit.
2. Solo avisa cuando algo EMPIEZA a fallar y cuando se ARREGLA (y recuerda cada 12 h si sigue mal); cada aviso queda también
   en el visor (origen «vigilante»).
Avisos: push a la app del móvil, notificación en el PC y tarjeta en la app (alertas.json); sin WhatsApp desde 2026-10-21.
Uso: vigilante.py            → una pasada
     vigilante.py --prueba   → manda un aviso de prueba
     vigilante.py --push-json → una notificación push con {titulo, cuerpo, url, tag} leído de stdin (lo usa el Hub
                                para «Zazu necesita tu permiso»; por stdin porque argv se ve en /proc)
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

HOME = Path.home()
sys.path.insert(0, str(Path(__file__).parent))
import server  # noqa: E402  (solo funciones de lectura)
import visor  # noqa: E402

ESTADO = HOME / ".config/hermes-hub/alertas.json"
VISOR_MD = Path(__file__).resolve().parent.parent / "VISOR.md"   # junto a README.md y APRENDIZAJE.md
SERVICIOS = {"hermes-hub": "la app (Hub)", "hermes-gateway": "el servicio de Zazu (tu WhatsApp)", "cloudflared-zazu": "el túnel de holazazu.app",
             "hermes-dashboard": "el panel interno de Zazu", "syncthing": "Syncthing (carpeta compartida)", "wacli-sync": "la lectura de WhatsApp"}
RECORDAR = 12 * 3600


def sh(*cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def activo(unit):
    return sh("systemctl", "--user", "is-active", unit).stdout.strip() == "active"


def comprobar():
    """{clave: (gravedad, texto)} de lo que está mal AHORA. gravedad: 'error' o 'aviso'."""
    mal, info = {}, []

    # 1. servicios (si uno está caído, se intenta reiniciar una vez)
    guests = [l.split()[0].removesuffix(".service") for l in sh("systemctl", "--user", "list-unit-files", "hermes-gateway-zi*", "--state=enabled", "--no-legend").stdout.splitlines() if l.strip()]
    for unit in list(SERVICIOS) + guests:
        if activo(unit):
            continue
        sh("systemctl", "--user", "restart", unit, timeout=120)
        time.sleep(8)
        nombre = SERVICIOS.get(unit, f"el WhatsApp/Telegram del invitado ({unit.removeprefix('hermes-gateway-zi')})")
        if activo(unit):
            info.append(f"🔁 {nombre[0].upper() + nombre[1:]} se había parado y lo he reiniciado.")
        else:
            mal[f"servicio:{unit}"] = ("error", f"{nombre[0].upper() + nombre[1:]} está caído y no arranca.")

    # 2. la web desde internet (Cloudflare) y en local
    for clave, url, texto in (("web", "https://holazazu.app/", "holazazu.app no responde desde internet."),
                              ("hub", "http://127.0.0.1:8792/login", "La app no responde en este PC.")):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "zazu-vigilante"}), timeout=20) as r:
                if r.status != 200:
                    raise ValueError(r.status)
        except Exception as e:
            mal[clave] = ("error", f"{texto} ({e})"[:200])


    # 4. tus cuentas de Google
    try:
        server._CACHE.clear()
        for c in server.cuentas():
            if c.get("error"):
                mal[f"google:{c['email']}"] = ("error", f"La cuenta de Google {c['email']} ha perdido el permiso: reconéctala en Cuentas.")
    except Exception as e:
        mal["google"] = ("aviso", f"No he podido comprobar tus cuentas de Google ({type(e).__name__}).")

    # 5. tus rutinas de Hermes
    try:
        for j in json.loads((HOME / ".hermes/cron/jobs.json").read_text()).get("jobs", []):
            if j.get("enabled") and (j.get("last_status") == "error" or j.get("last_delivery_error")):
                err = (j.get("last_error") or j.get("last_delivery_error") or "")[:120]
                mal[f"rutina:{j.get('id')}"] = ("aviso", f"La rutina «{j.get('name')}» falló la última vez{': ' + err if err else ''}.")
    except Exception:
        pass

    # 6. errores de la app en los últimos 6 minutos (ya recogidos por el visor; un Traceback cuenta como uno)
    errores = visor.leer(time.time() - 360, origen="app", gravedad="error")
    if len(errores) >= 3:
        mal["errores"] = ("aviso", f"La app ha tenido {len(errores)} errores en 5 minutos. El último: {errores[0]['x'][:140]} "
                                   "(míralo en el visor: `visor` o VISOR.md)")

    # 7. disco
    du = shutil.disk_usage("/")
    if du.free / du.total < 0.08:
        mal["disco"] = ("error", f"Queda poco disco: {du.free // 2**30} GB libres.")

    # 8. la lista de personas (users.json) legible y coherente
    try:
        us = json.loads(server.USERS_FILE.read_text())
        for e, v in us.items():
            if v.get("role") == "guest" and not (server.prof_dir(v.get("profile") or "x")).exists():
                mal[f"perfil:{e}"] = ("error", f"El asistente de {v.get('name')} no existe en el disco.")
    except Exception as e:
        mal["usuarios"] = ("error", f"La lista de personas (users.json) no se puede leer: {type(e).__name__}. Hay copia en users.bak.")

    # 9b. ninguna invitada usando una credencial de Fran (Hermes deja que los perfiles las tomen prestadas)
    try:
        for e, v in server.users().items():
            if v.get("role") == "guest" and server.vigilar_prestamo(e):
                info.append(f"🛡️ El asistente de {v.get('name')} iba a usar tu cuenta de IA. Lo he cortado: tendrá que conectar su propia IA.")
    except Exception:
        pass

    # 9. invitadas cerca del tope (aviso, no error)
    try:
        for e, v in server.users().items():
            if v.get("role") == "guest" and not v.get("ai") and v.get("profile"):
                gasto = server.coste_mes_eur(v["profile"])
                if gasto >= 0.8 * server.GUEST_MONTH_CAP_EUR:
                    mal[f"tope:{e}:{time.strftime('%Y-%m')}"] = ("aviso", f"{v.get('name')} lleva {gasto:.2f} € de {server.GUEST_MONTH_CAP_EUR:.0f} € este mes.")
    except Exception:
        pass
    return mal, info


def push(texto, urgente=False, titulo="Zazu", url="/?tab=inicio", tag="zazu-alerta", para=None, aprob=None):
    """Notificación push a los aparatos suscritos en la app (icono de Zazu). `para`: correo de una invitada; sin él, solo los de
    Fran (las alertas del servidor y los permisos nunca le llegan a una invitada). Devuelve cuántas salieron.
    La app de Android no admite web push: el mismo aviso queda en la cola de sus móviles (movil.encolar_aviso) y la app lo recoge."""
    lineas = [l for l in texto.splitlines() if l.strip() and l.strip() not in ("Zazu", "HolaZazu")]
    aviso = {"title": titulo, "body": "\n".join(lineas)[:520], "url": url, "tag": tag, **({"aprob": aprob} if aprob else {})}   # aprob: el aviso lleva Permitir / Rechazar
    try:
        en_app = server.movil.encolar_aviso(aviso, para, {e for e, v in server.users().items() if v.get("role") == "guest"})
    except Exception as e:
        print(f"avisos de la app: {type(e).__name__}", file=sys.stderr)
        en_app = 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return en_app
    todas, muertas, n = server.push_subs(), set(), en_app
    subs = [x for x in todas if server.push_de(x) == (para or None)]
    datos = json.dumps(aviso, ensure_ascii=False)
    for sub in subs:
        try:
            webpush(sub, datos, vapid_private_key=str(HOME / ".config/hermes-hub/vapid.pem"),
                    vapid_claims={"sub": "mailto:cuenta.principal@example.com"}, ttl=86400, headers={"Urgency": "high" if urgente else "normal"}, timeout=15)
            n += 1
        except WebPushException as e:
            if getattr(e.response, "status_code", 0) in (404, 410):   # 404/410: el móvil ya no existe → se borra
                muertas.add(sub["endpoint"])
        except Exception:
            pass
    if muertas:   # se reescribe con TODAS las demás (también las de otras personas)
        server.PUSH_FILE.write_text(json.dumps([x for x in server.push_subs() if x["endpoint"] not in muertas], indent=1))
        os.chmod(server.PUSH_FILE, 0o600)
    return n


def avisar(texto):
    """Push a la app del móvil + notificación en el PC (sin WhatsApp desde 2026-10-21). Devuelve True si llegó al móvil."""
    n = push(texto, urgente="🔴" in texto)
    sh("notify-send", "-a", "HolaZazu", "-i", str(Path(__file__).parent / "brand/zazu-64.png"), "HolaZazu", texto, timeout=10)
    return bool(n)


def guardar(estado):
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    os.chmod(tmp, 0o600)
    os.replace(tmp, ESTADO)


def main():
    try:
        estado = json.loads(ESTADO.read_text())
    except Exception:
        estado = {"activas": {}, "historial": []}
    if "--push-json" in sys.argv:
        d = json.loads(sys.stdin.read() or "{}")
        url = str(d.get("url") or "/?tab=inicio")
        if not url.startswith("/") or url.startswith("//"):
            url = "/?tab=inicio"   # solo enlaces de la propia app
        print(f"{push(str(d.get('cuerpo') or ''), urgente=bool(d.get('urgente', True)), titulo=str(d.get('titulo') or 'Zazu')[:80], url=url, tag=str(d.get('tag') or 'zazu-alerta')[:64], para=d.get('para') or None, aprob=d.get('aprob') if re.fullmatch(r"[0-9a-f]{12}", str(d.get('aprob') or '')) else None)} notificaciones enviadas")
        return
    if "--push-prueba" in sys.argv:   # stdin opcional: {"para": correo de una invitada}
        d = json.loads((sys.stdin.read() if not sys.stdin.isatty() else "") or "{}")
        print(f"{push('🐾 Prueba: las notificaciones de Zazu llegarán aquí.', para=d.get('para') or None)} notificaciones enviadas")
        return
    if "--prueba" in sys.argv:
        ok = avisar("🐾 Prueba de alertas de Zazu: si lees esto, los avisos te llegan bien.")
        print("enviado por WhatsApp" if ok else "WhatsApp falló (se mostró en el PC y en la app)")
        return
    ahora = time.time()
    try:
        visor.recoger()
    except Exception as e:   # el visor nunca para los avisos
        print(f"visor: {type(e).__name__}: {e}", file=sys.stderr)
    mal, info = comprobar()
    activas = estado.get("activas", {})
    mensajes = list(info)
    for k, (grav, texto) in mal.items():
        a = activas.get(k)
        if not a:
            activas[k] = {"gravedad": grav, "texto": texto, "desde": ahora, "avisado": ahora}
            mensajes.append(("🔴 " if grav == "error" else "🟡 ") + texto)
        else:
            a["texto"] = texto
            if ahora - a["avisado"] > RECORDAR and grav == "error":
                a["avisado"] = ahora
                mensajes.append(f"🔴 Sigue fallando desde las {time.strftime('%H:%M', time.localtime(a['desde']))}: {texto}")
    for k in [k for k in activas if k not in mal]:
        a = activas.pop(k)
        if not k.startswith("tope:"):
            mensajes.append(f"✅ Resuelto: {a['texto']}")
    if mensajes:
        texto = "Zazu\n" + "\n".join(mensajes)
        ok = avisar(texto)
        estado.setdefault("historial", []).insert(0, {"t": ahora, "texto": texto, "whatsapp": ok})
        estado["historial"] = estado["historial"][:50]
    estado["activas"], estado["ultima"] = activas, ahora
    guardar(estado)
    try:
        for m in mensajes:
            visor.anotar("vigilante", "error" if m.startswith("🔴") else "aviso" if m.startswith("🟡") else "info", m)
        tmp = VISOR_MD.with_suffix(".tmp")
        tmp.write_text(visor.resumen_md(activas))
        os.replace(tmp, VISOR_MD)
    except Exception as e:
        print(f"VISOR.md: {type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
