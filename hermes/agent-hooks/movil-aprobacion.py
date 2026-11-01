#!/usr/bin/env python3
"""Hook pre_tool_call de Hermes. Zazu puede usar todo Hermes; en lo delicado, Hermes le pide permiso a Fran enseñándole
el comando entero (Fran decidió el 2026-10-07 abrirlo todo con aprobación en vez de bloquear):
- enviar correos o WhatsApp en su nombre (zgog --enviar, gog … send/reply/forward, wacli send/forward/edit…, hermes send
  o send_message a otro chat que no sea el suyo, el puente local de WhatsApp en :3100); a su propio chat, sin preguntar;
- programar una tarea (cronjob_manage / hermes cron) que escriba a otra persona, a «all» o a un bot-chat;
- cambiar, pausar, reanudar o borrar una rutina que ya existe (cronjob_manage update/pause/resume/remove, «hermes cron
  edit/pause/resume/rm…»); crear un recordatorio para Fran sigue sin preguntar;
- en Google: invitar a otras personas o responder invitaciones (--attendees, --add-attendee, calendar respond/rsvp,
  propose-time, out-of-office) y borrar eventos, tareas o correos (calendar delete, tasks delete/clear, gmail
  trash/delete/batch delete…), también en bucles (for/xargs);
- cambiar una habilidad o sus scripts (skill_manage);
- sudo y demás permisos de administrador; leer o cambiar las claves (~/.hermes/.env);
- cambiar la configuración de Hermes (config.yaml, hermes config/setup/update…, skills, memorias, scripts, HolaZazu,
  unidades systemd) e instalar programas;
- en el móvil: SMS, mandarle algo, hacerlo sonar, y BORRAR o SOBRESCRIBIR archivos. Mover y ordenar no pregunta.
Bloquea (sin preguntar): dejar la terminal apuntando al móvil (cd/export/alias/ln: este hook no ve el estado de la
terminal entre llamadas) y tocar el propio hook, su permiso o los planes del ordenador del móvil (que nadie pueda
apagar este control convenciendo a Zazu; eso lo cambia Fran con Claude Code).
Intenta bloquear usar el control de HolaZazu o del gateway (curl/urllib… a :8642/:8790/:8792 locales, /v1/runs,
/api/hermes/, la cabecera Tailscale-User[-Login], ~/.config/hermes-hub o la cookie hub_s). ESTO ES BEST-EFFORT: una
lista de patrones no puede cubrir toda forma de escribir «localhost:8642» (puertos calculados, rutas o cabeceras
montadas por trozos, IPs en decimal/hex, variables entre llamadas). El control de verdad son la API_SERVER_KEY y los
toolsets del perfil (el perfil ROOT no da herramientas por api_server) y, en el hub, que la identidad de Fran solo
valga si llega por tailscaled; la regex solo sube el listón. Pide permiso (no bloquea) para leer las claves desde el
entorno de otro proceso (/proc/<pid>/environ, «ps e…»): el arreglo de fondo es que los hijos del gateway no las hereden.
Detecta movil.py y también las vías directas (kdeconnect-cli, D-Bus de KDE Connect, import movil, rutas del móvil).
Los perfiles (~/.hermes/profiles/<p>/config.yaml…, «hermes -p <p> config…», el alias «zazu») cuentan como la configuración.
Los avisos dicen «Zazu» en todos los perfiles (un solo agente desde 2026-10-10; del 10 al 11 de oct se llamó Zazu).
Configurado en ~/.hermes/config.yaml › hooks.pre_tool_call (y en cada perfil con herramientas), matcher
terminal|execute_code|write_file|patch|process_manage|cronjob_manage|skill_manage|send_message|browser_exec
(fail_closed: si este script fallara, se bloquearía; por eso cualquier error interno acaba en «pedir permiso»)."""
import hashlib, json, os, re, shlex, sys, time

ARRIESGADO = re.compile(
    r"movil\.py['\"]?\s+(sonar|enviar|texto|sms)\b"
    r"|\bmovil\.(sms|texto|enviar|sonar)\s*\("
    r"|kdeconnect-cli\b.*--(send-sms|ring|share|share-text)\b"
    r"|kdeconnect\.device\.(sms|share|findmyphone)|findmyphone|sendSms|shareText|shareUrl",
    re.S)
# Rutas del móvil: ~/Móvil (también con comodines: M?vil, M*vil), el montaje de KDE Connect y la memoria de Android.
# No cuenta «movil.py», «movil-orden.md» ni «Notas Móvil.md»: solo «Móvil» como carpeta.
EN_MOVIL = re.compile(r"(?:^|[/~'\"\s=:])M\S{0,3}vil(?=/|['\"\s;)|&]|$)|M\\u00f3vil|169f574a|/run/user/\d+/[0-9a-f]{16}"
                      r"|storage/emulated|readlink[^\n]*M\S{0,3}vil", re.M)
# Dejan la terminal «dentro» del móvil para los comandos siguientes
FIJA = re.compile(r"(?<![\w-])(cd|pushd|export|alias|ln|declare\s+-\w*x)\b|\bos\.(chdir|environ|putenv)\b|\bcwd\s*=")
# Cambian archivos: mover, borrar, sobrescribir, escribir, papelera… (para la configuración y lo protegido)
CAMBIA = re.compile(
    r"(?<![\w-])(mv|rm|rmdir|unlink|rename|shred|truncate|tee|dd|gio|kioclient5?|trash-put|trash|wipe|srm)\b"
    r"|-delete\b|-exec(dir)?\s+(rm|mv|shred)\b|--remove-source-files|\bsed\s+(-\S+\s+)*-[a-zA-Z]*i"
    r"|\bos\.(rename|replace|remove|unlink|rmdir|removedirs|truncate|makedirs|mkdir)\b|\bshutil\.(move|rmtree|copy\w*)\b"
    r"|\.(rename|unlink|rmdir|write_text|write_bytes|touch|mkdir)\s*\(|\bopen\([^)]*['\"][wax+]")
# En el móvil, mover y ordenar es libre; esto es lo que borra o machaca algo (sin papelera por esta vía)
BORRA = re.compile(
    r"(?<![\w-])(rm|rmdir|unlink|shred|truncate|tee|dd|trash-put|trash|wipe|srm)\b|\bgio\s+(trash|remove|rm|save|copy)\b"
    r"|-delete\b|-exec(dir)?\s+(rm|shred)\b|--remove-source-files|\bsed\s+(-\S+\s+)*-[a-zA-Z]*i"
    r"|\bos\.(remove|unlink|rmdir|removedirs|truncate)\b|\bshutil\.(rmtree|copy\w*)\b"
    r"|\.(unlink|rmdir|write_text|write_bytes)\s*\(|\bopen\([^)]*['\"][wax+]")
# Enviar en nombre de Fran por gog/zgog o wacli, en cualquier orden y mayúsculas, aunque intenten quitar el freno
# (--gmail-no-send=false, --no-gmail-no-send, --notify) o usen gog «a pelo». Las subórdenes de wacli que mandan o
# mutan (send, forward, edit, revoke, delete, create…) también piden permiso.
ENVIA = re.compile(
    r"\bz?gog\b.*?(--enviar|no-send\s*=|--no-gmail-no-send|--notify\b"
    r"|(?<![\w-])(send|reply|reply-?all|replyall|forward|fwd|autoreply|send-updates)(?![\w-]))"
    r"|\bwacli\b.*?(?<![\w-])(send|forward|edit|revoke|delete|create|participants|invite|join|leave|vote|presence)(?![\w-])"
    r"|WACLI_READONLY\s*=\s*0|--read-only=(?:false|0|no)\b",
    re.S | re.I)
# Mandar a otra persona por la vía de Hermes (hermes [-p x] send -t plataforma:chat, en cualquier orden y mayúsculas)
HERMES_SEND = re.compile(r"\b(?:hermes|zazu)\w*\b[^\n;&|]*?(?<![\w-])send\b[^\n;&|]*?(?:-t|--to|--target)(?:[=\s]+|(?=['\"\w]))"
                         r"['\"]?([a-z_]+)['\"]?:['\"]?([^\s'\"]+)", re.I)
# El puente local de WhatsApp (sin autenticación): el puerto 3100 con algo que no sea /health, o una ruta /send… local
PUENTE = re.compile(r"\b3100\b(?![^\n]*/health)|(localhost|127\.\d[\d.]*|::1|0\.0\.0\.0)[^\s'\"]*/(send|edit|react|messages)", re.I)
# Programar desde la terminal una tarea que entrega a alguien (hermes cron create|edit|update --deliver …)
CRON_CLI = re.compile(r"\b(?:hermes|zazu)\w*\b[^\n]*?\bcron\s+(?:create|add|edit|update)\b[^\n]*?--(?:failure-)?deliver[=\s]+['\"]?([^\s'\"]+)", re.I)
ROOT = re.compile(r"\bsudo\b|SUDO_PASSWORD|(?:^|[;&|\n(`]|\$\(|\bexec\s)\s*su\b|\b(pkexec|run0|doas)\b")
CONFIG_RUTA = re.compile(r"\.hermes/(profiles/[^/]+/)?(config\.yaml|skills/|memories/|cron/|scripts/|plugins/|state/vigilar-persistencia/|SOUL\.md)|/Hermes/(skills|memories|scripts)/|hermes-hub/"
                         r"|\.config/systemd/user/|\.local/bin/|/Spirit\b")
CONFIG_ORDEN = re.compile(r"\b(?:hermes|zazu)(?:\s+(?:-p|--profile)(?:\s+|=)\S+)?\s+(config\s+(set|edit|reset)|setup|update|hooks|approvals|plugins\s+(install|remove|enable|disable)"
                          r"|skills\s+(install|remove|uninstall)|model|profile\s+(create|delete|set))\b"
                          r"|\bsystemctl\s+--user\s+(enable|disable|mask|unmask|edit|daemon-reload)\b"
                          r"|\b(apt|apt-get|snap|flatpak)\s+(install|remove|purge|refresh)\b|\b(uv\s+)?pip3?\s+install\b|\bnpm\s+(i|install)\s+-g\b")
REDIRIGE = re.compile(r"(?<![<>&\d])>>?(?![&>])")      # «> archivo» en la terminal (no «2>/dev/null» ni «>&2»)
# Destino de cada «>»: si es una ruta fija fuera del móvil, no machaca nada del móvil
DESTINO = re.compile(r"(?<![<>])(?:&|\d)?>>?\|?\s*(\"[^\"]*\"|'[^']*'|[^\s;|&()<>]+)")
SCRIPT = re.compile(r"\.(sh|bash|zsh|py|js|mjs|cjs|pl|rb|service|timer|desktop)$|(^|/)[^./]+$")
COPIA = {"cp", "install", "rsync", "rclone", "scp"}
# El control de HolaZazu y del gateway (lo maneja Fran): pedir por HTTP a sus puertos o rutas, o hacerse pasar por él.
# Estrecho a propósito: «ss -ltnp | grep 8790» o «systemctl --user status hermes-hub» siguen libres.
CONTROL_HTTP = re.compile(r"\b(curl|wget|httpie|http|nc|ncat|socat|telnet|socket|urllib\d?|requests|fetch|aiohttp|httpx)\b|/dev/tcp/",
                          re.I)
# El puerto solo cuenta cuando se escribe COMO puerto (:8790, «('127.0.0.1', 8790)», port=8790, {8790}, /dev/tcp/h/8790),
# no cuando es parte de otra URL o de un id ajeno (latitude=36.8642, issues/8642, BOE-A-2026-8790, factura-8792.pdf,
# ?page=8790, x["id"]==8790, …#8642). Así una descarga normal o una comprobación de solo lectura no se bloquea.
CONTROL_DESTINO = re.compile(r"(?<![\w./=#-])(8642|8790|8792)(?![\w.-])|\bport\s*=\s*['\"]?(8642|8790|8792)\b"
                             r"|/dev/tcp/[^\s/]+/(8642|8790|8792)\b|/v1/runs\b|/api/hermes/", re.I)
# Hacerse pasar por Fran ante el hub: la cabecera Tailscale-User[-Login] (aunque monten «-Login» con printf),
# ~/.config/hermes-hub o la cookie de sesión del hub. Es best-effort: el control de verdad es la clave + los toolsets.
CONTROL_ID = re.compile(r"tailscale-user|\.config/hermes-hub|hub_s=", re.I)
# Lo que protege a este hook: el propio hook, su permiso, la configuración y los planes del ordenador del móvil
PROTEGIDO = re.compile(r"agent-hooks|shell-hooks-allowlist|\.local/state/movil-ordenar")
# Las claves de Hermes (~/.hermes/.env): la ruta directa, o abrir un .env con Python
_CLAVE_DIRECTA = re.compile(r"(?:\.hermes|(?:^|[/~\s'\"=:$({])Hermes)/\.env\b|(?:open|read_text|load_dotenv|dotenv_values)\s*\([^)]*\.env", re.I)
# …o mencionar a la vez la casa de Hermes y un fichero .env/.en?/*env* (p.ej. «cd ~/.hermes && cat .env»)
_CLAVE_HOGAR = re.compile(r"\.hermes\b|(?:^|[/~\s'\"=:$({])Hermes/", re.I)
_CLAVE_ENV = re.compile(r"\.env\b|\.en[v?*]|[*?]env[*?]?|\benv[*?]", re.I)
# …o leerlas del entorno de OTRO proceso: los hijos del gateway (puente de WhatsApp, supervisor de MCP) heredan
# todas las claves, y su /proc/<pid>/environ lo puede leer cualquier proceso del mismo usuario. Pedir permiso
# (no bloquear) para /proc/.../environ, «ps e…» (la «e» de BSD enseña el entorno, no «ps -e» ni «ps -eo»),
# y abrir environ desde Python. Es un seguro best-effort: el agujero de verdad se tapa arriba (que esos hijos
# no hereden las claves). Un agente decidido puede montar la ruta de otra forma; por eso además se corrige el core.
_CLAVE_PROC = re.compile(r"/proc\b[^\n;&|]*\benviron\b|\benviron\b[^\n;&|]*/proc\b"
                         r"|(?<![\w-])ps\s+[A-Za-z]*e[A-Za-z]*(?![\w-])", re.I)


# Otros sitios con credenciales de Fran (tokens de Google, GitHub, 1Password, cookies del navegador, cuentas del escritorio)
_CLAVE_SITIOS = re.compile(r"\.config/(gogcli|gh|op|google-chrome[\w-]*|chromium|BraveSoftware|evolution|goa-1\.0)\b|\.mozilla/firefox|\.ssh/id_|\.gnupg/(private|secring)", re.I)


def lee_claves(texto):
    """True si el comando lee o cambia las claves de Hermes (~/.hermes/.env o el entorno de otro proceso),
    aun con cd, comodines o rutas sueltas."""
    if _CLAVE_DIRECTA.search(texto) or _CLAVE_PROC.search(texto) or _CLAVE_SITIOS.search(texto):
        return True
    return bool(_CLAVE_HOGAR.search(texto) and _CLAVE_ENV.search(texto))


def copia_al_movil(cmd):
    """True si un cp/rsync/install deja algo DENTRO del móvil (destino = último argumento o -t/--target-directory)."""
    for seg in re.split(r"&&|\|\||[;\n|]", cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        while toks and re.fullmatch(r"\w+=.*|env|nice|command|builtin|timeout|\d+[smh]?", toks[0]):
            toks = toks[1:]
        if not toks or toks[0].rsplit("/", 1)[-1] not in COPIA:
            continue
        args = [t for t in toks[1:] if not t.startswith("-")]
        destinos = [t.split("=", 1)[1] for t in toks if t.startswith("--target-directory=")]
        destinos += [toks[i + 1] for i, t in enumerate(toks[:-1]) if t == "-t"]
        if any(EN_MOVIL.search(d) for d in destinos + args[-1:]):
            return True
    return False


# Sacar datos del ordenador hacia fuera sin pasar por un mensaje normal: subir ficheros con curl/wget, scp, sftp, rsync a otro equipo,
# nc/socat con redirección, smtplib. Zazu casi no lo usa; preguntar siempre es barato.
SUBE = re.compile(r"\b(curl|wget)\b[^\n]*?(?:\s-(?:d|F|T)\s*['\"]?[^\s'\"]*@|\s--(?:data(?:-binary|-raw|-urlencode)?|form|upload-file)(?:=|\s+)['\"]?[^\s'\"]*@|\s--upload-file\b|\s-T\s)"
                  r"|\b(?:scp|sftp)\b|\brsync\b[^\n]*\s[\w.-]+(?:@[\w.-]+)?:\S|\b(?:nc|ncat|socat)\b[^\n]*(?:<|\|)|\bsmtplib\b", re.I)


# Dar por bueno el estado de Zazu (la «foto» del vigilante de cambios) solo lo hace Fran
# Navegador del servidor (browser_exec, Browser Use): mirar y navegar es libre; escribir en formularios, iniciar sesión, enviar,
# comprar, subir o bajar archivos y usar el almacén de contraseñas piden permiso.
NAVEGA_ACTUA = re.compile(r"\b(fill|type|press|keyboard|select_option|set_input_files|upload|download|login|log_?in|sign_?in|password|passw|contrase[ñn]|credential|vault"
                          r"|checkout|payment|pay|pagar|pago|buy|comprar|purchase|cart|carrito|submit|enviar|send|post|delete|borrar|unsubscribe|dar_de_baja)\b"
                          r"|\.click\([^)]*(?:pagar|comprar|enviar|submit|buy|pay|send|checkout|confirm)", re.I)
FOTO_ACEPTAR = re.compile(r"vigilar[_-]persistencia[^\n]*--aceptar|--aceptar[^\n]*vigilar[_-]persistencia", re.I)
# Un recordatorio normal es corto y sin enlaces ni órdenes; lo que lleva eso se mira antes de programarlo
RUTINA_RARA = re.compile(r"https?://|\bcurl\b|\bwget\b|\bzgog\b|\bwacli\b|\bsudo\b|cada vez que|ignora (lo|las|tus)|\bsend\b|[\s\S]{401,}", re.I)


def toca_control(texto):
    """True si el texto pide algo al control de HolaZazu/gateway o usa la identidad de Fran ante HolaZazu."""
    return bool(CONTROL_ID.search(texto) or (CONTROL_HTTP.search(texto) and CONTROL_DESTINO.search(texto)))


def chats_de_fran():
    """Los chats de Fran (canal principal de cada plataforma en config.yaml): mandarle algo a él no pregunta.
    Incluye chat_id y user_id: sus tareas cron entregan a su JID de teléfono (user_id), no al chat_id @lid."""
    try:
        import yaml
        plataformas = (yaml.safe_load(open("/home/server/.hermes/config.yaml")) or {}).get("platforms") or {}
        return {str((v.get("home_channel") or {}).get(k)) for v in plataformas.values() if isinstance(v, dict)
                for k in ("chat_id", "user_id")} - {"None"}
    except Exception:
        return set()


def destino_ajeno(valor):
    """Primer destino de una tarea cron que NO es Fran, o None. local/origin/plataforma a secas/su propio chat = él;
    «all», «bot-chat…» o un platform:chat de otra persona = ajeno (pide permiso)."""
    for t in (x.strip() for x in str(valor or "").split(",")):
        if not t or t in ("local", "origin"):
            continue
        if t == "all" or t.startswith("bot-chat"):
            return t
        if ":" in t and t.split(":", 2)[1] not in chats_de_fran():
            return t
    return None


def redirige_al_movil(cmd):
    """True si algún «>» escribe en el móvil o en una ruta que no se ve (variable, $(…), comodín, \\)."""
    for m in DESTINO.finditer(cmd):
        d = m.group(1).strip("'\"")
        if d in ("/dev/null", "/dev/stdout", "/dev/stderr") or not d:
            continue
        if EN_MOVIL.search(m.group(1)) or re.search(r"[$`*?\[\\]", d):
            return True
    return False


# Palabras de una orden: espacios, comillas, comas o corchetes (también la lista de Python «["zgog", "tasks", "delete"]»)
# y la línea partida con «\». _OPC: opciones sueltas antes de la subórden (--force, -a cuenta, --json…).
_SEP = r"(?:[\s'\",\[\]]|\\\n)+"
_VAL = r"(?:[^\s'\",\[\]\\]|\\(?!\n))"      # un carácter de un valor («\» solo si no parte la línea: sin ambigüedad)
_OPC = rf"(?:-[\w-]+(?:={_VAL}*)?{_SEP}(?:(?!-){_VAL}+{_SEP})??)*"
# gog/zgog, google_api.py (skill google-workspace) o una variable que los guarde («$G tasks delete»), y su grupo de
# órdenes, mirando solo la PRIMERA palabra tras las opciones: así «--title='Cita del médico'» o
# «--summary='Revisar calendar…'» no cuentan como subórdenes.
_GOG = rf"(?:\bz?gog\b|google_api\.py|\$\{{?\w+\}}?){_SEP}{_OPC}"
# Cambiar, pausar, reanudar o borrar una rutina que ya existe desde la terminal (crear sigue libre si es para Fran)
RUTINA_CLI = re.compile(rf"(?:\b(?:hermes|zazu)\w*\b[^\n;&|]*?|\$\{{?\w+\}}?{_SEP})\bcron{_SEP}{_OPC}"
                        r"(?:edit|update|pause|resume|remove|rm|delete|del)(?![\w-])", re.I)
RUTINA_ACCIONES = ("update", "pause", "resume", "remove", "delete", "rm")    # las de cronjob_manage sobre una que ya existe
# Invitar a otras personas o responder invitaciones en nombre de Fran (gog no manda correo por defecto, pero el evento
# aparece en el calendario de los invitados; respond/propose-time/out-of-office avisan al organizador)
INVITA = re.compile(rf"{_GOG}(?:calendar|cal){_SEP}{_OPC}(?:respond|rsvp|reply|propose-time|out-of-office|ooo)(?![\w-])"
                    rf"|{_GOG}api{_SEP}{_OPC}call{_SEP}[^\n;&|]*?\battendees\b")
ASISTENTES = re.compile(r"(?<![\w-])--(?:attendees|add-attendee|send-updates)\b")     # con gog, google_api.py o lo que sea;
# --send-updates manda correo a los invitados en nombre de Fran
# Ajustes de Gmail que actúan hacia fuera o cambian la cuenta (respuesta automática, reenvío, filtros, delegados, alias),
# solo cuando cambian algo (leerlos sigue libre), y borrar contactos o archivos de Drive
# adb (Android Debug Bridge) controla el móvil entero: ver la pantalla, tocar, instalar apps, leer datos. Siempre con permiso.
# movil-pantalla.py (ver la pantalla del móvil): estado, ver y apps son libres; lo que toca, escribe o abre pide permiso
PANTALLA = re.compile(r"movil-pantalla(?:\.py)?['\"]?\s+(?:tocar|deslizar|texto|tecla|abrir|conectar)\b")
ADB = re.compile(r"(?<![\w.-])adb(?![\w-])|platform-tools/|\.android/adbkey|\bscrcpy\b")
AJUSTES_GOOGLE = re.compile(
    rf"{_GOG}(?:gmail|mail|email){_SEP}{_OPC}(?:settings{_SEP}{_OPC})?(?:vacation|autoreply|autoforward|forwarding|forward-address|filters?|delegates?|sendas|send-as|imap|pop)(?![\w-])"
    r"[^\n;&|]*?(?<![\w-])(?:update|create|set|enable|disable|add|delete|rm|remove|--enable|--disable)(?![\w-])"
    rf"|{_GOG}(?:contacts?|people){_SEP}{_OPC}(?:delete|rm|del|remove)(?![\w-])"
    rf"|{_GOG}drive{_SEP}{_OPC}(?:delete|rm|del|remove|trash|empty-trash)(?![\w-])", re.I)
# Borrar eventos, tareas o correos de Google (una vez o en bucle: for/while/xargs repiten la misma orden)
BORRA_GOOGLE = re.compile(
    rf"{_GOG}(?:calendar|cal){_SEP}{_OPC}(?:delete|rm|del|remove|delete-calendar)(?![\w-])"
    rf"|{_GOG}tasks?{_SEP}{_OPC}(?:delete|rm|del|remove|clear)(?![\w-])"
    rf"|{_GOG}(?:gmail|mail|email){_SEP}{_OPC}(?:(?:batch|messages?|msgs?|threads?|drafts?|labels?){_SEP}{_OPC})?"
    r"(?:trash|delete|rm|del|remove)(?![\w-])"
    rf"|{_GOG}(?:gmail|mail|email){_SEP}[^\n;&|]*?--add(?:-labels?)?[=\s]+['\"]?[\w,]*(?i:trash)\b"
    rf"|{_GOG}api{_SEP}{_OPC}call{_SEP}[^\n;&|]*?\.(?:delete|trash|batchDelete|clear)\b")



# ─────────────────────────────────────────────────────────────────────────────
# Candado de claves (hallazgo 3 de la auditoría 2026-10-21): Zazu puede explorar ~/Spirit con read_file/search_files y,
# siguiendo el enlace hermes/ajustes/profiles -> ~/.hermes/profiles, llegar a .env de invitadas, auth.json, memorias…
# Se bloquea (deny) toda lectura/escritura/listado cuya ruta REAL (os.path.realpath, para seguir symlinks) caiga en:
#   - SECRETO (bloquea leer, buscar Y escribir): cualquier .env, auth.json, *.key/*.pem/keystore, ~/.cloudflared,
#     ~/.config/hermes-hub, ~/.local/share/gog (llavero). Son puras claves: Zazu no tiene por qué tocarlas.
#   - PERFILES (bloquea solo leer/buscar/listar): todo ~/.hermes/profiles (tiene .env y conversaciones de invitadas).
#     Escribir en un config.yaml de perfil sigue por la puerta normal (pide permiso), para no romper el trabajo legítimo.
# NO entra aquí el trabajo normal: ~/Spirit, ~/.hermes/skills, ~/.hermes/memories, el config.yaml raíz ni el Cerebro.
CANDADO_MSG = "Candado: esto contiene claves o datos privados; no lo abro"
_SECRETO_NOMBRE = re.compile(r"(?:^\.env|\.env)(?:$|\.)|^auth\.json$|\.(?:key|pem|keystore|jks|p12|pfx)$|^\.?keystore$", re.I)
_SECRETO_DIRS = ("~/.cloudflared", "~/.config/hermes-hub", "~/.local/share/gog")
_PERFILES_DIR = "~/.hermes/profiles"
# Candado best-effort para texto de terminal/execute_code (no se puede resolver realpath de una orden libre): nombra una
# carpeta de claves o un fichero de clave/credencial. El .env de ~/.hermes ya lo detecta lee_claves (abajo se enruta a bloqueo).
_CANDADO_TEXTO = re.compile(r"\.cloudflared\b|\.config/hermes-hub\b|\.local/share/gog\b"
                            r"|(?<![\w.])[\w./~-]*\.(?:key|pem|keystore|jks|p12|pfx)\b|(?<![\w./-])auth\.json\b", re.I)


def _real(path):
    try:
        return os.path.realpath(os.path.expanduser(str(path).strip().strip("'\"")))
    except Exception:
        return ""


def _bajo(real, base):
    b = _real(base)
    return bool(real) and bool(b) and (real == b or real.startswith(b + os.sep))


def ruta_sensible(path, incluir_perfiles=True):
    """True si la ruta REAL (resolviendo symlinks) es una clave/credencial, o (si incluir_perfiles) está en ~/.hermes/profiles.
    incluir_perfiles=False para escrituras: editar un config.yaml de perfil sigue pidiendo permiso, no se bloquea."""
    if not path or not str(path).strip():
        return False
    real = _real(path)
    if not real:
        return False
    if _SECRETO_NOMBRE.search(os.path.basename(real)):
        return True
    if any(_bajo(real, d) for d in _SECRETO_DIRS):
        return True
    return bool(incluir_perfiles) and _bajo(real, _PERFILES_DIR)


def _rutas_de(entrada):
    """Las rutas que toca una herramienta de archivos: 'path' y, en parches V4A, las cabeceras *** Update/Add/Delete/Move File:."""
    rutas = [str(entrada.get("path") or "")]
    rutas += re.findall(r"^\*\*\*\s*(?:Update|Add|Delete|Move)\s+File:\s*(.+)",
                        str(entrada.get("patch") or ""), re.M)
    return [r for r in rutas if r.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Freno de bucles (A). Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0
# (agents/loop_guard.py: huella sha256(tool_name+argumentos) y tope max_identical_calls). Aquí: cuenta por SESIÓN la
# huella de cada acción exacta (herramienta + argumentos); si la MISMA se repite FRENO_MAX veces, se para. La huella
# incluye los argumentos, así que acciones distintas (p.ej. leer archivos distintos) no se frenan. El estado va en un
# fichero pequeño por sesión en ~/.local/state, con límite de tamaño y limpieza. Best-effort: si algo falla, no frena.
FRENO_MAX = 3
FRENO_MSG = "Freno: esta acción se repitió 3 veces, la paro para no entrar en bucle"


def _estado_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "zazu-aprobacion", "freno-bucles")


def _limpiar(dirp, max_edad=86400, max_fich=200):
    """Borra sesiones viejas (>1 día) y limita cuántos ficheros se guardan."""
    try:
        ahora, ents = time.time(), []
        for n in os.listdir(dirp):
            p = os.path.join(dirp, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if ahora - st.st_mtime > max_edad:
                try:
                    os.remove(p)
                except OSError:
                    pass
            else:
                ents.append((st.st_mtime, p))
        for _, p in sorted(ents)[:-max_fich] if len(ents) > max_fich else []:
            try:
                os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def freno_de_bucles(session_id, herramienta, clave):
    """True si la MISMA acción (herramienta+argumentos) llega a FRENO_MAX veces en esta sesión. Sin sesión no cuenta
    (no frena ni ensucia el estado: así las pruebas de regresión, que no mandan session_id, no se ven afectadas)."""
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id or ""))[:120]
    if not sid:
        return False
    try:
        dirp = _estado_dir()
        os.makedirs(dirp, exist_ok=True)
        _limpiar(dirp)
        fich = os.path.join(dirp, sid + ".json")
        try:
            with open(fich, encoding="utf-8") as f:
                datos = json.load(f)
        except Exception:
            datos = {}
        cuentas = datos.get("c") if isinstance(datos, dict) and isinstance(datos.get("c"), dict) else {}
        if len(cuentas) > 2000:   # cota de tamaño por sesión: un reinicio del contador es inocuo (como mucho, frena algo más tarde)
            cuentas = {}
        h = hashlib.sha256((str(herramienta) + "\0" + str(clave)).encode("utf-8", "replace")).hexdigest()[:16]
        cuentas[h] = int(cuentas.get(h, 0) or 0) + 1
        n = cuentas[h]
        tmp = fich + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"c": cuentas, "t": time.time()}, f)
        os.replace(tmp, fich)
        return n >= FRENO_MAX
    except Exception:
        return False


def decidir(herramienta, entrada):
    """(acción, aviso) o None si no hace falta preguntar."""
    texto = "\n".join(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for v in entrada.values())   # texto real, sin escapar
    if herramienta in ("read_file", "search_files"):
        # Candado de claves (B): leer o buscar dentro de una ruta sensible se bloquea (incluye ~/.hermes/profiles).
        if any(ruta_sensible(r, incluir_perfiles=True) for r in _rutas_de(entrada)):
            return "block", CANDADO_MSG
        return None
    if herramienta in ("write_file", "patch"):
        # Solo cuenta DÓNDE escribe (path y, en parches V4A, las cabeceras «*** Update/Add/Delete/Move File:»),
        # no lo que dice la nota: «Móvil nuevo», «~/hermes-hub/» o «agent-hooks» dentro de una nota no tocan nada.
        rutas = [str(entrada.get("path") or "")] + re.findall(
            r"^\*\*\*\s*(?:Update|Add|Delete|Move)\s+File:\s*(.+)", str(entrada.get("patch") or ""), re.M)
        contenido = "\n".join(str(entrada.get(k) or "") for k in ("content", "new_string", "patch"))
        if any(SCRIPT.search(r.strip()) for r in rutas) or contenido.lstrip().startswith("#!"):
            r = decidir("terminal", {"command": contenido})   # un script se mira como si se ejecutara
            if r:
                return r
        texto = "\n".join(rutas)
        if CONTROL_ID.search(texto):
            return "block", "Zazu no puede usar el control de HolaZazu ni del gateway (lo maneja Fran)"
        if PROTEGIDO.search(texto):
            return "block", "Zazu no puede editar su propio control de permisos ni los planes del ordenador del móvil (eso con Claude Code)"
        if any(ruta_sensible(r, incluir_perfiles=False) for r in rutas):
            return "block", CANDADO_MSG   # candado: escribir sobre un .env/auth.json/clave es siempre no
        if EN_MOVIL.search(texto):
            return "approve", "Zazu quiere escribir un archivo dentro de tu móvil. Revisa cuál"
        if lee_claves(texto):
            return "approve", "Zazu quiere cambiar tus claves (.env). Revisa qué"
        if CONFIG_RUTA.search(texto):
            return "approve", "Zazu quiere cambiar su configuración (Hermes, habilidades, scripts o HolaZazu). Revisa qué"
        return None
    if herramienta == "send_message":
        destino = str(entrada.get("target") or "")
        _, _, chat = destino.partition(":")
        if str(entrada.get("action") or "send") in ("send", "react", "unreact") and chat.strip() and chat.strip() not in chats_de_fran():
            return "approve", f"Zazu quiere escribir a otra persona o grupo ({destino}). Revisa destinatario y texto"
        return None
    if herramienta == "cronjob_manage":
        accion = str(entrada.get("action") or "").strip().lower()     # Hermes normaliza igual («Remove» = remove)
        if accion in ("create", "update", "run", "run_now", "trigger"):
            ajeno = destino_ajeno(entrada.get("deliver")) or destino_ajeno(entrada.get("failure_deliver"))
            if ajeno:
                return "approve", f"Zazu quiere programar una tarea que escribirá a otra persona o grupo ({ajeno}). Revisa destinatario y texto"
        if accion in ("create", "update") and RUTINA_RARA.search(str(entrada.get("prompt") or "")):
            return "approve", "Zazu quiere programar una rutina con texto inusual (enlaces, comandos o muy larga). Revisa qué hará"
        if accion in RUTINA_ACCIONES:
            return "approve", "Zazu quiere cambiar o borrar una rutina (o pausarla o reanudarla). Revisa cuál y qué cambia"
        return None
    if herramienta == "skill_manage":
        # Cualquier escritura en una habilidad o sus scripts pide permiso (skill_manage no tiene acciones de solo lectura).
        return "approve", "Zazu quiere crear o cambiar una habilidad (o sus scripts). Revisa qué"
    if herramienta == "process_manage":
        if toca_control(texto):
            return "block", "Zazu no puede usar el control de HolaZazu ni del gateway (lo maneja Fran)"
        if str(entrada.get("action")) in ("write", "submit"):
            return "approve", "Zazu quiere escribir en un proceso que tiene abierto en segundo plano. Revisa qué"
        return None
    if herramienta == "browser_exec":
        if lee_claves(texto) or NAVEGA_ACTUA.search(texto):
            return "approve", "Zazu quiere actuar en una web con el navegador (escribir en un formulario, iniciar sesión, enviar, comprar, subir o bajar algo). Revisa el código"
        return None
    escribe = CAMBIA.search(texto) or (herramienta == "terminal" and REDIRIGE.search(texto))
    if PROTEGIDO.search(texto) and (escribe or copia_al_movil(texto) or re.search(r"(?<![\w-])cp\b", texto)):
        return "block", "Zazu no puede tocar su propio control de permisos ni los planes del ordenador del móvil (eso con Claude Code)"
    if EN_MOVIL.search(texto) and FIJA.search(texto):
        return "block", ("No dejes la terminal apuntando al móvil (cd, export, alias o ln hacia ~/Móvil): la carpeta y las "
                         "variables se quedan para los comandos siguientes y así nadie ve qué tocan. Usa rutas absolutas")
    if toca_control(texto):
        return "block", "Zazu no puede usar el control de HolaZazu ni del gateway (lo maneja Fran)"
    if ROOT.search(texto):
        return "approve", "Zazu quiere usar permisos de administrador (sudo). Revisa el comando entero"
    m = HERMES_SEND.search(texto)
    c = CRON_CLI.search(texto)
    if (ENVIA.search(texto) or PUENTE.search(texto) or (m and m.group(2) not in chats_de_fran())
            or (c and destino_ajeno(c.group(1)))):
        return "approve", "Zazu quiere enviar un mensaje en tu nombre. Revisa destinatario y texto"
    # Candado de claves (B) en terminal/execute_code (best-effort: no hay realpath de una orden libre). El .env se bloquea
    # (antes solo pedía permiso); leer el entorno de otro proceso (ps e / /proc) sigue pidiendo permiso vía lee_claves.
    if _CANDADO_TEXTO.search(texto) or _CLAVE_DIRECTA.search(texto) or (_CLAVE_HOGAR.search(texto) and _CLAVE_ENV.search(texto)):
        return "block", CANDADO_MSG
    if lee_claves(texto):
        return "approve", "Zazu quiere leer o cambiar tus claves (.env). Revisa qué"
    if FOTO_ACEPTAR.search(texto):
        return "approve", "Zazu quiere dar por bueno el estado actual de su configuración (la foto del vigilante de cambios). Solo si tú has revisado los cambios"
    if SUBE.search(texto):
        return "approve", "Zazu quiere enviar un archivo o datos a otro equipo (curl, scp, rsync…). Revisa destino y contenido"
    if CONFIG_ORDEN.search(texto) or (CONFIG_RUTA.search(texto) and (escribe or re.search(r"(?<![\w-])cp\b", texto))):
        return "approve", "Zazu quiere cambiar su configuración o instalar algo. Revisa qué"
    borra = BORRA.search(texto) or (herramienta == "terminal" and redirige_al_movil(texto))
    if EN_MOVIL.search(texto) and (borra or copia_al_movil(texto)):
        return "approve", "Zazu quiere borrar o sobrescribir archivos de tu móvil. Revisa el comando"
    if ARRIESGADO.search(texto):
        return "approve", "Zazu quiere usar tu móvil. Revisa número, texto o archivo antes de aprobar"
    if AJUSTES_GOOGLE.search(texto):
        return "approve", "Zazu quiere cambiar ajustes de tu Gmail (respuesta automática, reenvío, filtros, delegados) o borrar contactos o archivos de Drive. Revisa el comando entero"
    if PANTALLA.search(texto):
        return "approve", "Zazu quiere tocar o escribir en la pantalla de tu móvil o abrir una app (nunca dinero ni tiendas de apps). Revisa lo que hace"
    if ADB.search(texto):
        return "approve", "Zazu quiere controlar tu móvil por adb (ver la pantalla, tocar, instalar o leer datos). Revisa el comando entero"
    if BORRA_GOOGLE.search(texto):
        return "approve", "Zazu quiere borrar eventos/tareas/correos de tu cuenta de Google. Revisa cuáles (y si es en bucle, cuántos)"
    if INVITA.search(texto) or ASISTENTES.search(texto):
        return "approve", "Zazu quiere invitar a otras personas a un evento o responder a una invitación en tu nombre. Revisa quién y qué"
    if RUTINA_CLI.search(texto):
        return "approve", "Zazu quiere cambiar o borrar una rutina (o pausarla o reanudarla). Revisa cuál y qué cambia"
    return None


def _para_ensenar(tool, entrada):
    """Lo que ve Fran en WhatsApp: corto y legible. NUNCA se recorta el contenido que Fran aprueba: si es demasiado
    largo para leerlo entero, quien decide lo bloquea (abajo, len(orden) > 3500 → «divídelo en pasos»). Enseñar un
    trozo como si fuera todo dejaría aprobar a ciegas la parte oculta (p.ej. una línea «sudo…» al final)."""
    orden = entrada.get("command") or entrada.get("code")
    if orden:
        return str(orden)
    if tool in ("write_file", "patch"):
        rutas = [str(entrada.get("path") or "")] + re.findall(
            r"^\*\*\*\s*(?:Update|Add|Delete|Move)\s+File:\s*(.+)", str(entrada.get("patch") or ""), re.M)
        rutas = [r for r in rutas if r]
        cab = (tool + ": " + ", ".join(rutas)) if rutas else tool
        cuerpo = "\n".join(str(entrada.get(k) or "") for k in ("content", "new_string", "patch"))
        return (cab + ("\n" + cuerpo if cuerpo.strip() else "")).strip() or json.dumps(entrada, ensure_ascii=False)
    if tool == "skill_manage":
        ops = entrada.get("operations")
        ops = ops if isinstance(ops, list) else [entrada]
        return "skill_manage: " + "; ".join(
            (f"{o.get('action', '?')} {o.get('name') or ''}".strip()
             + (f" ({o.get('file_path')})" if o.get("file_path") else "")) for o in ops if isinstance(o, dict))
    if tool == "cronjob_manage":
        # Todo lo que cambia, sin recortar (el prompt entero: si no cabe, se bloquea por largo). En una rutina que ya
        # existe va primero cuál es (job_id); «deliver» solo si se toca o si se crea/lanza.
        accion = str(entrada.get("action") or "?")
        trozos = [f"cronjob_manage {entrada.get('action', '?')}"]
        if entrada.get("job_id") is not None:
            trozos.append(f"job_id={entrada.get('job_id')!r}")
        if entrada.get("deliver") is not None or accion.strip().lower() not in RUTINA_ACCIONES:
            trozos.append(f"deliver={entrada.get('deliver')!r}")
        if entrada.get("failure_deliver"):
            trozos.append(f"failure_deliver={entrada.get('failure_deliver')!r}")
        trozos += [f"{k}={v!r}" for k, v in entrada.items()
                   if k not in ("action", "job_id", "deliver", "failure_deliver", "prompt") and v is not None]   # [] o "" también cambian
        return (" · ".join(trozos) + f"\n{str(entrada.get('prompt') or '')}").strip()
    return json.dumps(entrada, ensure_ascii=False)


tool = ""
quien = "Zazu"
try:
    datos = json.load(sys.stdin)
    quien = "Zazu"   # un solo agente: los avisos hablan de Zazu en todos los perfiles (antes «Hermes» en el perfil tecnico y, un día, «Zazu»)
    tool = str(datos.get("tool_name") or "")
    entrada = datos.get("tool_input") or {}
    r = decidir(tool, entrada)
    # Freno de bucles (A): la MISMA acción repetida FRENO_MAX veces en la sesión se para. Un bloqueo de seguridad ya
    # corta; si no, y hay bucle, se bloquea. Best-effort: si el estado falla, no frena (nunca rompe el flujo de permisos).
    clave_freno = ((entrada.get("command") or entrada.get("code")
                    or json.dumps(entrada, ensure_ascii=False, sort_keys=True))
                   if isinstance(entrada, dict) else str(entrada))
    if not (r and r[0] == "block") and freno_de_bucles(str(datos.get("session_id") or ""), tool, clave_freno):
        r = ("block", FRENO_MSG)
except Exception as e:      # nunca bloquear todas las herramientas por un fallo de este script: que decida Fran
    entrada, r = {}, ("approve", f"El control del móvil no pudo revisar este comando ({type(e).__name__}). Revísalo tú")
if r:
    accion, aviso = r
    aviso = aviso.replace("Zazu", quien, 1)
    orden = _para_ensenar(tool, entrada)
    clave = (entrada.get("command") or entrada.get("code")
             or json.dumps(entrada, ensure_ascii=False, sort_keys=True))   # para el hash: entero y estable
    if accion == "approve" and len(orden) > 3500:   # Fran tiene que poder leerlo ENTERO en WhatsApp (máx. 4096); nunca un trozo
        accion, aviso = "block", "Es demasiado largo para revisarlo en una aprobación: divídelo en partes"
    salida = {"action": accion, "message": f"{aviso}:\n{orden}" if accion == "approve" else aviso + "."}
    if accion == "approve":
        salida["rule_key"] = "movil:" + hashlib.sha256(clave.encode()).hexdigest()[:12]   # «siempre» solo vale para este comando exacto
    print(json.dumps(salida, ensure_ascii=False))
