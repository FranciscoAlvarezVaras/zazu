#!/usr/bin/env python3
"""Regresión del hook movil-aprobacion.py: el mismo lote de llamadas al script viejo y al nuevo.

Solo pueden cambiar los casos marcados como «cambio» (parche del Modo Hermes):
  (a) configuración de los perfiles (~/.hermes/profiles/<p>/…, «hermes -p <p> config…», alias «zazu»);
  (b) bloqueo del control de HolaZazu y del gateway (HTTP a :8642/:8790/:8792, /v1/runs, /api/hermes/,
      Tailscale-User-Login, ~/.config/hermes-hub, hub_s=);
  (c) los avisos dicen «Hermes» en el perfil tecnico;
  (r) revisión 2 (2026-10-07): piden permiso cambiar/pausar/borrar una rutina que ya existe, invitar a otras personas
      o responder invitaciones, y borrar eventos, tareas o correos de Google (también en bucle).
Todo lo demás tiene que dar exactamente la misma salida (acción, mensaje y rule_key).

Uso: probar_hook.py [--viejo RUTA] [--nuevo RUTA] [--solo-a]
     por defecto, el último movil-aprobacion.py.bak-* y el movil-aprobacion.py de $HERMES_HOME/agent-hooks.
No toca nada: solo ejecuta los dos scripts con JSON por stdin. No imprime ningún dato de Fran (solo nombres de caso).
"""
import argparse, glob, json, os, subprocess, sys

H = os.path.expanduser(os.environ.get("HERMES_HOME") or "~/.hermes")
OTRO = "whatsapp:34600000000@s.whatsapp.net"          # un chat que no es de Fran


def chat_de_fran():
    """El chat principal de Fran según el config.yaml raíz (lo mismo que lee el hook). No se imprime nunca."""
    try:
        import yaml
        pl = (yaml.safe_load(open("/home/server/.hermes/config.yaml")) or {}).get("platforms") or {}
        hc = (pl.get("whatsapp") or {}).get("home_channel") or {}
        return "whatsapp:" + str(hc.get("chat_id")) if hc.get("chat_id") else None
    except Exception:
        return None


def T(cmd, perfil="default"):
    return {"tool_name": "terminal", "tool_input": {"command": cmd}, "profile": perfil}


def W(path, content="hola", perfil="default"):
    return {"tool_name": "write_file", "tool_input": {"path": path, "content": content}, "profile": perfil}


IGUAL = None   # marca: la salida tiene que ser idéntica
URL_RUNS = "http://127.0.0.1:8642/p/tecnico/v1/runs"
# (nombre, payload, esperado) — esperado = IGUAL, o (parte del parche, acción_vieja|None, acción_nueva|None, texto que debe
# salir en el nuevo). Con --solo-a (lo que deja deshacer.sh) los casos de las partes b y c tienen que salir iguales.
CASOS = [
    # --- sin cambios ---
    ("ls", T("ls -la ~"), IGUAL),
    ("git status", T("git -C ~/hermes-hub status"), IGUAL),
    ("sudo (default)", T("sudo apt update"), IGUAL),
    ("sudo (escritor)", T("sudo -n true", "escritor"), IGUAL),
    ("sudo (charla)", T("sudo systemctl restart foo", "charla"), IGUAL),
    ("leer .env raíz", T("cat ~/.hermes/.env"), IGUAL),
    ("leer .env de perfil", T("cat ~/.hermes/profiles/escritor/.env"), IGUAL),
    ("grep clave en .env de tecnico (default)", T("grep API_SERVER_KEY /home/server/.hermes/profiles/tecnico/.env"), IGUAL),
    ("ss | grep 8790 (diagnóstico)", T("ss -ltnp | grep 8790"), IGUAL),
    ("ss | grep 8642|8790 (tecnico)", T("ss -ltnp | grep -E '8642|8790'", "tecnico"), IGUAL),
    ("systemctl status hub", T("systemctl --user status hermes-hub"), IGUAL),
    ("journal | grep 8642", T("journalctl --user -u hermes-gateway -n 50 | grep 8642"), IGUAL),
    ("puente WhatsApp /health", T("curl -s http://127.0.0.1:3100/health"), IGUAL),
    ("curl a internet", T("curl -s https://api.github.com/zen"), IGUAL),
    ("python requests a internet", T("python3 -c \"import requests; print(requests.get('https://example.com').status_code)\""), IGUAL),
    ("wacli send", T("wacli send text --to 34600000000 --message hola"), IGUAL),
    ("hermes send a otro", T(f"hermes send -t {OTRO} 'hola'"), IGUAL),
    ("send_message a otro", {"tool_name": "send_message", "tool_input": {"action": "send", "target": OTRO, "message": "hola"}, "profile": "default"}, IGUAL),
    ("nota que menciona el hub (contenido no cuenta)", W("/home/server/Cerebro/60 Servidor/nota.md", "curl -s 127.0.0.1:8790/api/job y ~/.config/hermes-hub"), IGUAL),
    ("escribir config.yaml raíz", W("/home/server/.hermes/config.yaml", "x: 1"), IGUAL),
    ("sed -i config.yaml raíz", T("sed -i 's/a/b/' ~/.hermes/config.yaml"), IGUAL),
    ("leer config.yaml raíz", T("cat ~/.hermes/config.yaml"), IGUAL),
    ("leer config.yaml de perfil", T("cat ~/.hermes/profiles/escritor/config.yaml"), IGUAL),
    ("hermes config set raíz", T("hermes config set model.default x"), IGUAL),
    ("npm -g", T("npm install -g cowsay"), IGUAL),
    ("rm en el móvil", T("rm ~/Móvil/DCIM/foto.jpg"), IGUAL),
    ("cd al móvil", T("cd ~/Móvil && ls"), IGUAL),
    ("cd al móvil (tecnico, sin «Zazu»)", T("cd ~/Móvil && ls", "tecnico"), IGUAL),
    ("tocar el hook", T("echo x > ~/.hermes/agent-hooks/movil-aprobacion.py"), IGUAL),
    ("skill_manage", {"tool_name": "skill_manage", "tool_input": {"action": "create", "name": "x"}, "profile": "default"}, IGUAL),
    ("cron a otro", {"tool_name": "cronjob_manage", "tool_input": {"action": "create", "deliver": OTRO, "prompt": "hola"}, "profile": "default"}, IGUAL),
    ("process_manage write", {"tool_name": "process_manage", "tool_input": {"action": "write", "data": "y\n"}, "profile": "default"}, IGUAL),
    ("process_manage poll", {"tool_name": "process_manage", "tool_input": {"action": "poll", "session_id": "p1"}, "profile": "default"}, IGUAL),
    ("execute_code inocuo", {"tool_name": "execute_code", "tool_input": {"code": "print(1+1)"}, "profile": "default"}, IGUAL),
    ("ls (tecnico)", T("ls /tmp", "tecnico"), IGUAL),
    ("entrada rota (error interno)", {"tool_name": "terminal", "tool_input": "no-es-un-dict", "profile": "tecnico"}, IGUAL),
    # --- (a) configuración de los perfiles ---
    ("escribir config.yaml de perfil", W("/home/server/.hermes/profiles/escritor/config.yaml", "x: 1"), ("a", None, "approve", "cambiar su configuración")),
    ("patch SOUL.md de tecnico", {"tool_name": "patch", "tool_input": {"path": "/home/server/.hermes/profiles/tecnico/SOUL.md", "old_string": "a", "new_string": "b"}, "profile": "default"}, ("a", None, "approve", "cambiar su configuración")),
    ("sed -i config.yaml de perfil", T("sed -i 's/smart/off/' ~/.hermes/profiles/tecnico/config.yaml"), ("a", None, "approve", "cambiar su configuración")),
    ("cp a memorias de perfil", T("cp /tmp/m.md ~/.hermes/profiles/charla/memories/MEMORY.md"), ("a", None, "approve", "cambiar su configuración")),
    ("hermes -p X config set", T("hermes -p escritor config set approvals.mode off"), ("a", None, "approve", "cambiar su configuración")),
    ("hermes --profile=X config set", T("hermes --profile=charla config set hooks '{}'"), ("a", None, "approve", "cambiar su configuración")),
    ("hermes -p X hooks", T("hermes -p tecnico hooks revoke x"), ("a", None, "approve", "cambiar su configuración")),
    ("alias zazu config set", T("zazu config set approvals.mode off"), ("a", None, "approve", "cambiar su configuración")),
    ("alias zazu send a otro", T(f"zazu send -t {OTRO} hola"), ("a", None, "approve", "enviar un mensaje")),
    ("alias zazu cron a otro", T(f"zazu cron create '0 9 * * *' 'hola' --deliver {OTRO}"), ("a", None, "approve", "enviar un mensaje")),
    # --- (b) control de HolaZazu y del gateway ---
    ("curl con Tailscale-User-Login a :8790", T("curl -s -H 'Tailscale-User-Login: fran@x' http://127.0.0.1:8790/api/job?id=1"), ("b", None, "block", "control de HolaZazu")),
    ("urllib a :8642/v1/runs", T(f"python3 -c \"import urllib.request; urllib.request.urlopen('{URL_RUNS}')\""), ("b", None, "block", "control de HolaZazu")),
    ("curl aprobar run", T("curl -s -X POST http://127.0.0.1:8642/p/tecnico/v1/runs/run_x/approval -d '{\"choice\":\"once\"}'"), ("b", None, "block", "control de HolaZazu")),
    ("wget /api/hermes/", T("wget -qO- http://localhost:8792/api/hermes/aprobar"), ("b", None, "block", "control de HolaZazu")),
    ("nc al gateway", T("nc -z 127.0.0.1 8642"), ("b", None, "block", "control de HolaZazu")),
    ("/dev/tcp al hub", T("exec 3<>/dev/tcp/127.0.0.1/8790"), ("b", None, "block", "control de HolaZazu")),
    ("curl salud del hub", T("curl -s http://127.0.0.1:8792/login"), ("b", None, "block", "control de HolaZazu")),
    ("leer ~/.config/hermes-hub", T("cat ~/.config/hermes-hub/auth.json"), ("b", None, "block", "control de HolaZazu")),
    ("cookie hub_s=", T("curl -s -b 'hub_s=abc' https://holazazu.app/api/job"), ("b", None, "block", "control de HolaZazu")),
    ("execute_code requests al hub", {"tool_name": "execute_code", "tool_input": {"code": "import requests\nrequests.post('http://127.0.0.1:8790/api/hermes/aprobar')"}, "profile": "default"}, ("b", None, "block", "control de HolaZazu")),
    ("process_manage escribe curl al hub", {"tool_name": "process_manage", "tool_input": {"action": "write", "data": "curl 127.0.0.1:8790/api/send\n"}, "profile": "default"}, ("b", "approve", "block", "control de HolaZazu")),
    ("write_file en ~/.config/hermes-hub", W("/home/server/.config/hermes-hub/users.json", "{}"), ("b", "approve", "block", "control de HolaZazu")),
    ("script que llama al gateway", W("/tmp/x.sh", "#!/bin/sh\ncurl http://127.0.0.1:8642/v1/runs\n"), ("b", None, "block", "control de HolaZazu")),
    ("curl al hub (tecnico)", T("curl -s http://127.0.0.1:8790/api/job", "tecnico"), ("b", None, "block", "Zazu no puede usar el control de HolaZazu")),
    # --- (c) «Hermes» en el perfil tecnico ---
    ("sudo (tecnico)", T("sudo -n true", "tecnico"), ("c", "approve", "approve", "Zazu quiere usar permisos de administrador")),
    ("leer .env (tecnico)", T("cat ~/.hermes/.env", "tecnico"), ("c", "approve", "approve", "Zazu quiere leer o cambiar tus claves")),
    ("rm en el móvil (tecnico)", T("rm ~/Móvil/x.txt", "tecnico"), ("c", "approve", "approve", "Zazu quiere borrar o sobrescribir")),
    ("hermes config set (tecnico)", T("hermes config set model.default x", "tecnico"), ("c", "approve", "approve", "Zazu quiere cambiar su configuración")),
    ("tocar el hook (tecnico)", T("echo x > ~/.hermes/agent-hooks/movil-aprobacion.py", "tecnico"), ("c", "block", "block", "Zazu no puede tocar su propio control")),
    # --- (fix2) el puerto solo cuenta como puerto: descargas normales y comprobaciones de solo lectura NO se bloquean ---
    ("descarga open-meteo (lat 36.8642)", T("curl -s 'https://api.open-meteo.com/v1/forecast?latitude=36.8642&longitude=-2.46'"), IGUAL),
    ("issue 8642 de GitHub", T("curl -s https://api.github.com/repos/x/hermes-agent/issues/8642"), IGUAL),
    ("BOE-A-2026-8790", T("curl -sL 'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8790'"), IGUAL),
    ("factura-8792.pdf", T("wget -q https://example.com/factura-8792.pdf -O /tmp/f.pdf"), IGUAL),
    ("urllib ?page=8790 e id==8790", {"tool_name": "execute_code", "tool_input": {"code": "import urllib.request; d=urllib.request.urlopen('https://api.example.com/items?page=8790'); print(d.status==8790)"}, "profile": "default"}, IGUAL),
    ("ancla #8642", T("curl -s 'https://example.com/a#8642'"), IGUAL),
    # --- (fix2) el control sí se bloquea aunque el PUERTO se calcule, mientras quede algo reconocible (/v1/runs) ---
    ("puerto calculado 8000+642 con /v1/runs", T("P=$((8000+642)); curl -s \"http://127.0.0.1:$P/p/tecnico/v1/runs/x/approval\" -d '{}'", "tecnico"), ("b", None, "block", "control de HolaZazu")),
    ("socket a ('127.0.0.1', 8790)", {"tool_name": "execute_code", "tool_input": {"code": "import socket; socket.create_connection(('127.0.0.1', 8790))"}, "profile": "tecnico"}, ("b", None, "block", "control de HolaZazu")),
    ("HTTPConnection port=8790", {"tool_name": "execute_code", "tool_input": {"code": "import http.client; http.client.HTTPConnection('localhost', port=8790)"}, "profile": "tecnico"}, ("b", None, "block", "control de HolaZazu")),
    ("cabecera Tailscale-User-Login montada con printf", T("H=$(printf 'Tailscale-User-%s: fran@x' Login); curl -H \"$H\" http://127.0.0.1:$((8000+790))/api/nota", "tecnico"), ("b", None, "block", "control de HolaZazu")),
    # --- (fix2) leer las claves desde el entorno de otro proceso pide permiso (no se bloquea) ---
    ("cat /proc/<pid>/environ", T("b=$(pgrep -f bridge.js); cat /proc/$b/environ", "tecnico"), ("b", None, "approve", "leer o cambiar tus claves")),
    ("ps eww (entorno de un proceso)", T("ps eww -p 1", "tecnico"), ("b", None, "approve", "leer o cambiar tus claves")),
    ("execute_code open(/proc/.../environ)", {"tool_name": "execute_code", "tool_input": {"code": "print(open('/proc/999/environ').read())"}, "profile": "tecnico"}, ("b", None, "approve", "leer o cambiar tus claves")),
    ("ps -ef (no es entorno) sigue libre", T("ps -ef | grep hermes", "tecnico"), IGUAL),
    ("ps aux (no es entorno) sigue libre", T("ps aux | grep node", "tecnico"), IGUAL),
    ("cat /proc/meminfo sigue libre", T("cat /proc/meminfo", "tecnico"), IGUAL),
    # --- (fix2) el contenido largo de write_file/patch no se enseña a trozos: se bloquea ---
    ("write_file enorme a config → bloqueado (no a trozos)", W("/home/server/.hermes/config.yaml", "# config\n" + "model: sonnet\n" * 300 + "hooks: {}  # PELIGRO_OCULTO\n", "tecnico"), ("b", "approve", "block", "demasiado largo")),
    ("write_file corto a config sigue mostrándose entero", W("/home/server/.hermes/config.yaml", "model: sonnet\nhooks: {}  # corto\n"), IGUAL),
    # --- (r) cambiar, pausar o borrar una rutina que ya existe pide permiso; crear un recordatorio para Fran, no ---
    ("hermes cron rm", T("hermes cron rm a5a6b1f07404"), ("r", None, "approve", "cambiar o borrar una rutina")),
    ("hermes -p X cron pause", T("hermes -p charla cron pause 89ff805059f9"), ("r", None, "approve", "cambiar o borrar una rutina")),
    ("hermes cron edit (horario)", T("hermes cron edit a5a6b1f07404 --schedule '0 22 * * *'"), ("r", None, "approve", "cambiar o borrar una rutina")),
    ("hermes cron resume (tecnico)", T("hermes cron resume a5a6b1f07404", "tecnico"), ("r", None, "approve", "Zazu quiere cambiar o borrar una rutina")),
    ("cronjob_manage remove", {"tool_name": "cronjob_manage", "tool_input": {"action": "remove", "job_id": "a5a6b1f07404"}, "profile": "default"}, ("r", None, "approve", "job_id='a5a6b1f07404'")),
    ("cronjob_manage update sin destino", {"tool_name": "cronjob_manage", "tool_input": {"action": "update", "job_id": "a5a6b1f07404", "enabled_toolsets": ["web"]}, "profile": "default"}, ("r", None, "approve", "enabled_toolsets=['web']")),
    ("cronjob_manage pause", {"tool_name": "cronjob_manage", "tool_input": {"action": "pause", "job_id": "89ff805059f9"}, "profile": "default"}, ("r", None, "approve", "cambiar o borrar una rutina")),
    ("cronjob_manage Remove (mayúscula)", {"tool_name": "cronjob_manage", "tool_input": {"action": "Remove", "job_id": "x"}, "profile": "default"}, ("r", None, "approve", "cambiar o borrar una rutina")),
    ("recordatorio para Fran sigue libre", {"tool_name": "cronjob_manage", "tool_input": {"action": "create", "schedule": "30m", "prompt": "Recuérdale a Fran sacar la ropa", "deliver": "origin"}, "profile": "default"}, IGUAL),
    ("hermes cron list sigue libre", T("hermes cron list"), IGUAL),
    ("cronjob_manage list sigue libre", {"tool_name": "cronjob_manage", "tool_input": {"action": "list"}, "profile": "default"}, IGUAL),
    # --- (r) invitar a otras personas o responder invitaciones pide permiso ---
    ("calendar create --attendees", T("zgog calendar create primary --summary='Cena' --from 2026-10-10T21:00:00+02:00 --to 2026-10-10T23:00:00+02:00 --attendees ana@example.com"), ("r", None, "approve", "invitar a otras personas")),
    ("calendar update --add-attendee", T("zgog calendar update primary ev1 --add-attendee=ana@example.com"), ("r", None, "approve", "invitar a otras personas")),
    ("calendar respond", T("zgog calendar respond primary ev1 --status accepted"), ("r", None, "approve", "invitar a otras personas")),
    ("cal rsvp (alias)", T("zgog cal rsvp primary ev1 --status declined"), ("r", None, "approve", "invitar a otras personas")),
    ("evento sin invitados sigue libre", T("zgog calendar create primary --summary='Cita del médico' --from 2026-10-10T10:00:00+02:00 --to 2026-10-10T11:00:00+02:00"), IGUAL),
    # --- (r) borrar eventos, tareas o correos pide permiso (también en bucle) ---
    ("calendar delete", T("zgog calendar delete primary ev1 --force"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("cal rm (alias, opciones antes)", T("zgog -y cal rm primary ev1"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("tasks delete en bucle silenciado", T("for t in $ids; do zgog tasks delete @default $t --force >/dev/null && echo ok; done"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("tasks clear", T("zgog tasks clear @default"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("xargs calendar delete", T("echo \"$ids\" | xargs -n1 zgog calendar delete primary"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("gmail trash", T("zgog gmail trash 18c1 18c2"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("gmail batch delete", T("zgog gmail batch delete 18c1 18c2"), ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("execute_code tasks delete", {"tool_name": "execute_code", "tool_input": {"code": "import subprocess\nfor t in ids:\n    subprocess.run(['zgog', 'tasks', 'delete', '@default', t])"}, "profile": "default"}, ("r", None, "approve", "borrar eventos/tareas/correos")),
    ("tasks delete (tecnico)", T("zgog tasks delete @default t1", "tecnico"), ("r", None, "approve", "Zazu quiere borrar eventos/tareas/correos")),
    ("tarea con «del» en el título sigue libre", T("zgog tasks add @default --title='Cita del médico' --due 2026-10-08"), IGUAL),
    ("tasks done sigue libre", T("zgog tasks done @default t1"), IGUAL),
    ("buscar en la papelera sigue libre", T("zgog gmail search 'in:trash newer_than:2d' --max 5"), IGUAL),
    ("listar eventos y borrar un temporal sigue libre", T("zgog calendar events primary --json > /tmp/e.json; rm /tmp/e.json"), IGUAL),
]


def correr(script, payload):
    r = subprocess.run([sys.executable, script], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                       text=True, timeout=20)
    out = r.stdout.strip()
    if r.returncode != 0 and not out:
        return {"_error": f"rc={r.returncode}"}
    return json.loads(out) if out else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--viejo")
    ap.add_argument("--nuevo")
    ap.add_argument("--solo-a", action="store_true", help="el nuevo solo lleva la parte (a) del parche (tras deshacer.sh)")
    a = ap.parse_args()
    baks = sorted(glob.glob(os.path.join(H, "agent-hooks", "movil-aprobacion.py.bak-*")), key=os.path.getmtime)
    viejo = a.viejo or (baks[-1] if baks else None)
    nuevo = a.nuevo or os.path.join(H, "agent-hooks", "movil-aprobacion.py")
    if not viejo or not os.path.exists(viejo) or not os.path.exists(nuevo):
        sys.exit("falta el script viejo o el nuevo (--viejo/--nuevo)")
    casos = list(CASOS)
    propio = chat_de_fran()
    if propio:   # mandarle algo a Fran no pregunta, ni antes ni ahora
        casos.append(("send_message a Fran", {"tool_name": "send_message", "tool_input": {"action": "send", "target": propio, "message": "hola"}, "profile": "tecnico"}, IGUAL))
    fallos = cambios = 0
    for nombre, payload, esperado in casos:
        if esperado is not IGUAL and a.solo_a and esperado[0] != "a":
            esperado = IGUAL
        v, n = correr(viejo, payload), correr(nuevo, payload)
        acc = lambda x: x.get("action") if isinstance(x, dict) else None
        if esperado is IGUAL:
            ok, nota = v == n, ("igual" if v == n else f"CAMBIÓ {acc(v)} → {acc(n)}")
        else:
            _, av, an, texto = esperado
            msg = (n or {}).get("message", "") if isinstance(n, dict) else ""
            ok = acc(v) == av and acc(n) == an and texto in msg and (v != n or texto.startswith('Zazu'))   # los avisos de Zazu ya no cambian de texto entre perfiles
            if True:   # desde 2026-10-10 el aviso habla de «Zazu» en todos los perfiles, nunca de «Zazu quiere/no puede»
                ok = ok and "Zazu quiere" not in msg and "Zazu no puede" not in msg
            nota = f"{acc(v)} → {acc(n)}" + ("" if ok else f"  (esperado {av} → {an} con «{texto}»)")
            cambios += 1
        fallos += not ok
        print(f"{'OK   ' if ok else 'FALLA'} {nombre:52s} {nota}")
    print(f"\n{len(casos)} casos · {cambios} cambios buscados · {fallos} fallos")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
