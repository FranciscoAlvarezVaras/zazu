#!/usr/bin/env python3
"""Escribe el estado del servidor en el cerebro (Obsidian): ~/Cerebro/60 Servidor/estado.md.
Lo lanza zazu-estado.timer cada 15 min. Solo lee; no cambia nada. Sin IA.
Fran lo mira en Obsidian (PC o móvil); Hermes y Claude Code lo leen para saber qué pasa en el PC."""
import json, re, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path

import psutil

HOME = Path("/home/server")
VAULT = HOME / "Cerebro"
SALIDA = VAULT / "60 Servidor/estado.md"

# (unidad, nombre para Fran, --user o sistema)
SERVICIOS = [
    ("hermes-gateway", "Hermes: tu asistente (WhatsApp)", True),
    ("hermes-hub", "HolaZazu: tu app", True),
    ("cloudflared-zazu", "Túnel de holazazu.app a internet", True),
    ("hermes-dashboard", "Panel de configuración de Hermes", True),
    ("wacli-sync", "Lectura de WhatsApp para Hermes", True),
    ("syncthing", "Sincronización con el móvil", True),
    ("kdeconnectd", "KDE Connect: enlace con tu móvil", True),
    ("panel-servidor", "Panel del servidor", True),
    ("open-webui", "Open WebUI: chat con la IA local", True),
    ("zazu-exportar.timer", "Cerebro: copia de lo de Zazu cada 15 min", True),
    ("cerebro-ordenar.timer", "Cerebro: ordenador e informe de cada noche", True),
    ("recibidos-whatsapp.timer", "Carpetas: lo que mandas por WhatsApp, a Recibidos (tarda 10-15 min)", True),
    ("zazu-vigia.timer", "Vigía de Zazu: tareas de WhatsApp, correo y agenda (modo sombra)", True),
    ("zazu-bandeja.timer", "Bandeja de Google Tasks/Calendar de Fran (modo sombra)", True),
    ("apache2", "Apache: la web de Nextcloud", False),
    ("postgresql", "PostgreSQL: base de datos de Nextcloud", False),
    ("nextcloud-cron.timer", "Nextcloud: tareas de fondo", False),
    ("ollama", "Ollama: IA local", False),
    ("smbd", "Samba: carpetas de red", False),
    ("ssh", "SSH: terminal remota", False),
]
# (nombre, url local que debe responder, dónde lo abres)
WEBS = [
    ("HolaZazu (tu app)", "http://127.0.0.1:8792/login", "https://holazazu.app"),
    ("Panel de Hermes", "http://127.0.0.1:9119/", "solo en este PC: http://127.0.0.1:9119"),
    ("Panel del servidor", "http://127.0.0.1:8765/", "solo en este PC: http://127.0.0.1:8765"),
    ("Nextcloud (tu nube)", "http://127.0.0.1:8080/status.php", "https://nube.holazazu.app"),
    ("Open WebUI (chat con IA local)", "http://127.0.0.1:3000/health", "solo en este PC: http://localhost:3000"),
    ("Ollama (IA local)", "http://127.0.0.1:11434/", "solo para programas"),
]


def sh(*cmd, timeout=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def activo(unidad, user):
    return sh("systemctl", *(["--user"] if user else []), "is-active", unidad) == "active"


def responde(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "zazu-estado"}), timeout=5) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def dns_ok():
    t = time.time()
    try:
        socket.getaddrinfo("www.google.com", 443)
        return time.time() - t
    except Exception:
        return None


def hace(ts):
    if not ts:
        return "nunca"
    s = int(time.time() - ts)
    return "ahora" if s < 90 else f"hace {s // 60} min" if s < 3600 else f"hace {s // 3600} h" if s < 86400 else f"hace {s // 86400} d"


def gb(n):
    return f"{n / 2**30:.0f} GB"


def syncthing():
    """[(dispositivo, visto)] y [(carpeta, estado)] desde la API local de Syncthing."""
    try:
        cfg = (HOME / ".local/state/syncthing/config.xml").read_text()
        key = re.search(r"<apikey>([^<]+)</apikey>", cfg).group(1)
        def api(ruta):
            req = urllib.request.Request("http://127.0.0.1:8384" + ruta, headers={"X-API-Key": key})
            return json.load(urllib.request.urlopen(req, timeout=5))
        nombres = {d["deviceID"]: d["name"] for d in api("/rest/config/devices")}
        stats = api("/rest/stats/device")
        conex = api("/rest/system/connections").get("connections", {})
        mio = api("/rest/system/status").get("myID")
        disp = []
        for did, nombre in nombres.items():
            if did == mio:
                continue
            visto = stats.get(did, {}).get("lastSeen", "")
            ts = time.mktime(time.strptime(visto[:19], "%Y-%m-%dT%H:%M:%S")) if visto and not visto.startswith("1970") else 0
            disp.append((nombre, "conectado ahora" if conex.get(did, {}).get("connected") else f"visto {hace(ts)}"))
        carp = []
        for f in api("/rest/config/folders"):
            st = api(f"/rest/db/status?folder={f['id']}")
            carp.append((f.get("label") or f["id"], f["path"], st.get("state", "?"), st.get("needFiles", 0)))
        return disp, carp
    except Exception as e:
        return [("Syncthing", f"no responde ({type(e).__name__})")], []


def kdeconnect():
    """Línea del móvil por KDE Connect. Nunca incluye notificaciones (datos privados de terceros)."""
    # Con el servicio parado no se llama a D-Bus: lo arrancaría por su cuenta, fuera de systemd.
    if not activo("kdeconnectd", True):
        return "KDE Connect no responde (servicio `kdeconnectd` parado)"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import movil
        d = movil.datos()
    except Exception:
        return "KDE Connect no responde"
    if not d.get("vinculado"):
        return "sin vincular"
    if not d.get("conectado"):
        return "vinculado pero no accesible ahora"
    bat = d.get("bateria")
    bat = f"{bat} %" if isinstance(bat, int) and bat >= 0 else "?"   # -1 = desconocido
    return (f"conectado · batería {bat}{' (cargando)' if d.get('cargando') else ''} · red {d.get('red') or '?'} · "
            + ("archivos montados en ~/Móvil" if d.get("archivos") else "archivos no montados"))


def guardia_hoy():
    """Resumen del día de la guardia del puerto público (hermes-hub/guardia.py). Solo cuentas: las IP no van al Cerebro."""
    try:
        r = json.loads((HOME / ".local/state/hermes-hub/seguridad.json").read_text())
    except (OSError, ValueError):
        r = {}
    if r.get("fecha") != time.strftime("%Y-%m-%d"):
        return "- Hoy: nada sospechoso. Límite de 600 peticiones por minuto y bloqueo de 1 h a quien busque rutas raras (.env, .git, wp-admin…)."
    return (f"- Hoy: **{r.get('sospechosas', 0)}** peticiones sospechosas, **{r.get('bloqueadas', 0)}** IP bloqueadas 1 h, "
            f"**{r.get('frenadas', 0)}** peticiones frenadas. Detalle con IP: `~/.local/state/hermes-hub/seguridad.log`. "
            "Si alguna vez te bloquea a ti: `systemctl --user restart hermes-hub`.")


def main():
    ahora = time.strftime("%Y-%m-%d %H:%M")
    malos, L = [], []

    # servicios
    filas = []
    for unidad, nombre, user in SERVICIOS:
        ok = activo(unidad, user)
        filas.append(f"| {'✅' if ok else '🔴'} | {nombre} | `{unidad}` |")
        if not ok:
            malos.append(f"{nombre} está parado")
    webs = []
    for nombre, url, donde in WEBS:
        ok = responde(url)
        webs.append(f"| {'✅' if ok else '🔴'} | {nombre} | {donde} |")
        if not ok:
            malos.append(f"{nombre} no responde")
    t = dns_ok()
    if t is None or t > 2:
        malos.append("el DNS va lento o no resuelve" + (f" ({t:.1f} s por consulta)" if t else ""))

    # WhatsApp y rutinas de Hermes
    try:
        wa = (json.loads((HOME / ".hermes/gateway_state.json").read_text()).get("platforms") or {}).get("whatsapp") or {}
        wa_estado = wa.get("state") or "desconocido"
    except Exception:
        wa_estado = "desconocido"
    if wa_estado != "connected":
        malos.append(f"WhatsApp de Hermes: {wa_estado}")
    rutinas = []
    try:
        for j in json.loads((HOME / ".hermes/cron/jobs.json").read_text()).get("jobs", []):
            if not j.get("enabled"):
                continue
            ok = j.get("last_status") != "error"
            rutinas.append(f"| {'✅' if ok else '🟡'} | {j.get('name')} | `{j.get('schedule_display') or j.get('schedule')}` |")
    except Exception:
        pass
    try:
        alertas = json.loads((HOME / ".config/hermes-hub/alertas.json").read_text())
        activas = [a["texto"] for a in alertas.get("activas", {}).values()]
    except Exception:
        activas = []

    # recursos
    du = shutil.disk_usage("/")
    mem = psutil.virtual_memory()
    temps = psutil.sensors_temperatures()
    cpu_t = next((round(x.current) for x in temps.get("k10temp", [])), None)
    if du.free / du.total < 0.1:
        malos.append(f"queda poco disco ({gb(du.free)} libres)")
    if mem.available / mem.total < 0.1:
        malos.append("la RAM está casi llena")

    # Hermes: versión y actualizaciones (sin red: compara con el último fetch)
    repo = HOME / ".hermes/hermes-agent"
    commit = sh("git", "-C", str(repo), "log", "-1", "--format=%h del %cs")
    pendientes = sh("git", "-C", str(repo), "rev-list", "--count", "HEAD..origin/main")
    auto = sh("systemctl", "--user", "is-enabled", "hermes-actualizar.timer") == "enabled"

    # copias de seguridad
    copias = []
    for unidad, nombre in (("respaldo-pc", "Copia diaria (restic)"), ("respaldo-externo", "Copia semanal a Google Drive")):
        p = dict(l.split("=", 1) for l in sh("systemctl", "--user", "show", unidad, "-p", "Result", "-p", "ExecMainExitTimestamp").splitlines() if "=" in l)
        ok = p.get("Result") == "success"
        copias.append(f"| {'✅' if ok else '🔴'} | {nombre} | {p.get('ExecMainExitTimestamp') or 'sin ejecutar desde el arranque'} |")
        if not ok:
            malos.append(f"{nombre}: {p.get('Result')}")
    try:   # respaldo de documentos de WhatsApp (respaldo-whatsapp.py): avisa si lleva más de 3 días sin completarse
        rw = json.loads((HOME / ".local/state/respaldo-whatsapp.json").read_text())
        ok = time.time() - (rw.get("ultimo_ok") or 0) < 3 * 86400
        copias.append(f"| {'✅' if ok else '🟡'} | Documentos de WhatsApp → `~/Documentos/WhatsApp` ({rw.get('total', '?')} archivos) | "
                      f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(rw['ultimo_ok'])) if rw.get('ultimo_ok') else 'nunca'} · último intento: {rw.get('resultado', '?')} |")
    except Exception:
        copias.append("| 🟡 | Documentos de WhatsApp | sin datos todavía |")

    disp, carp = syncthing()
    kde = kdeconnect()
    recientes = sorted((f for f in (HOME / "Cerebro/40 Compartido").rglob("*") if f.is_file() and ".stfolder" not in f.parts and ".stversions" not in f.parts),
                       key=lambda f: f.stat().st_mtime, reverse=True)[:8]

    # ---------- nota ----------
    L += ["---", "title: Estado del servidor", f"updated: {ahora}", "tags: [servidor]", "---",
          "Volver al [[Inicio]] · [[60 Servidor/mapa|Mapa del servidor]]", "",
          f"# Estado del servidor · {ahora}", "_Se reescribe sola cada 15 minutos (`zazu-estado.timer`). No la edites a mano._", ""]
    if malos:
        L += ["> [!danger] Ahora mismo falla", *[f"> - {m}" for m in malos], ""]
    else:
        L += ["> [!success] Todo funciona", f"> Encendido desde hace {int((time.time() - psutil.boot_time()) // 3600)} h.", ""]
    if activas:
        L += ["> [!warning] Avisos del vigilante de HolaZazu", *[f"> - {a.splitlines()[0][:200]}" for a in activas], ""]
    L += ["## Servicios", "| | Qué | Servicio |", "|---|---|---|", *filas, "",
          "## Webs y paneles", "| | Qué | Dónde lo abres |", "|---|---|---|", *webs, "",
          "## Hermes", f"- WhatsApp: **{'conectado' if wa_estado == 'connected' else wa_estado}**",
          f"- Versión instalada: `{commit}` · cambios nuevos publicados: **{pendientes or '?'}**",
          f"- Actualización automática: **{'activada (04:30)' if auto else 'desactivada'}** · historial en [[60 Servidor/hermes-actualizaciones]]",
          "- Configurar: [[60 Servidor/hermes|cómo configurar Hermes]]", "",
          "### Rutinas", "| | Rutina | Cuándo |", "|---|---|---|", *rutinas, "",
          "## Móvil y sincronización", f"- **Enlace KDE Connect**: {kde}", *[f"- **{n}**: {e}" for n, e in disp],
          *[f"- Carpeta «{n}» (`{p}`): {s}{f', faltan {nf} archivos' if nf else ''}" for n, p, s, nf in carp], "",
          "### Últimos archivos en Compartido", *[f"- {time.strftime('%Y-%m-%d %H:%M', time.localtime(f.stat().st_mtime))} · `{f.relative_to(HOME / 'Cerebro/40 Compartido')}`" for f in recientes], "",
          "## Recursos",
          f"- Disco: {gb(du.used)} usados de {gb(du.total)} ({gb(du.free)} libres)",
          f"- RAM: {mem.percent:.0f} % usada ({gb(mem.available)} libres)",
          f"- CPU: {psutil.cpu_percent(interval=1):.0f} %" + (f" · {cpu_t} °C" if cpu_t else "") + f" · carga {psutil.getloadavg()[0]:.1f}",
          f"- DNS: {'OK' if t is not None and t < 2 else 'LENTO' if t else 'SIN RESPUESTA'}" + (f" ({t:.2f} s)" if t else ""), "",
          "## Copias de seguridad", "| | Copia | Última vez |", "|---|---|---|", *copias, "",
          "## Seguridad de HolaZazu (lo que llega de internet)", guardia_hoy(), ""]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    tmp = SALIDA.with_suffix(".tmp")
    tmp.write_text("\n".join(L) + "\n")
    tmp.replace(SALIDA)
    print(f"estado escrito: {len(malos)} problemas")


if __name__ == "__main__":
    main()
