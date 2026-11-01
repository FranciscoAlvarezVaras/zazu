#!/usr/bin/python3
"""La jaula del Hermes de una invitada (bubblewrap, sin sudo): ve el sistema en SOLO LECTURA y, de /home/server, únicamente lo suyo.

  jaula.py [--casa] <perfil> <orden…>        p. ej.  jaula.py zinuria /home/server/.local/bin/hermes -p zinuria chat -Q …

Por qué: el Hermes de una invitada corre con el usuario Unix de Fran. Sin jaula, «@file:», una ruta al principio del mensaje o un
gateway propio le dejaban leer auth.json (y entrar como Fran), users.json, el Cerebro o las memorias de otras invitadas.

Dentro ve:
  · todo «/» en solo lectura, salvo /home/server, /run/user, /srv, /var/www, /media, /mnt y /tmp, que son carpetas vacías;
  · el código y el Python de Hermes, el lanzador `hermes`, `gog` y el código del Hub (para mcp_google.py), en solo lectura;
  · con escritura: su perfil de Hermes, sus credenciales de Google (invitadas/<perfil>), sus carpetas (holazazu/<perfil>),
    sus cerrojos de la instalación y las carpetas `.leases` de los entornos (Hermes apunta ahí qué proceso usa cada entorno).
/proc es propio (no ve otros procesos ni su entorno) y el entorno de variables empieza vacío. La red sí: su IA está en internet.
Lo usan run_job (el chat de la app) y la unidad hermes-gateway-<perfil> (su WhatsApp/Telegram y sus rutinas).
"""
import os
import re
import sys
from pathlib import Path

HOME = Path.home()   # en las pruebas, la casa falsa: nunca se toca la de verdad
HUB = Path(__file__).resolve().parent
JAULAS = HOME / ".local/share/holazazu-jaula"
SOLO_LECTURA = [HOME / ".hermes/hermes-agent", HOME / ".hermes/tools", HOME / ".hermes/installs", HOME / ".local/bin/hermes", HOME / ".local/bin/gog"]
VACIAS = ["/run/user", "/srv", "/var/www", "/media", "/mnt", "/tmp"]


def argv(perfil, casa=False):
    """Prefijo bwrap para ejecutar algo como el Hermes de `perfil` (ziXXX). `casa`: además la Casa (lista, tareas) y la carpeta Familia."""
    if not re.fullmatch(r"zi[a-z0-9]{1,30}", perfil or ""):
        raise ValueError("perfil de invitado no válido")
    H, propio = str(HOME), JAULAS / perfil
    rw = [HOME / ".hermes/profiles" / perfil, HOME / ".config/hermes-hub/invitadas" / perfil, HOME / ".local/share/holazazu" / perfil]
    if casa:
        rw += [HOME / ".local/share/holazazu-casa", HOME / "Servicios/compartido/Familia"]
    for d in rw[1:] + [propio]:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
    a = ["/usr/bin/bwrap", "--ro-bind", "/", "/", "--tmpfs", H]
    for d in VACIAS:
        a += ["--tmpfs", d]
    a += ["--proc", "/proc", "--dev", "/dev", "--unshare-pid", "--unshare-ipc", "--die-with-parent", "--new-session"]
    for p in SOLO_LECTURA:
        if p.exists():
            a += ["--ro-bind", str(p), str(p)]
    a += ["--ro-bind", str(HUB), f"{H}/hermes-hub"]
    for inst in (HOME / ".hermes/installs").glob("*/"):
        for cerrojo in (".install.lock", ".recovery.lock", "pm-runtime/.prepare.lock"):
            if (inst / cerrojo).exists():
                mio = propio / f"{inst.name}-{cerrojo.replace('/', '-')}"
                mio.touch(mode=0o600, exist_ok=True)
                a += ["--bind", str(mio), str(inst / cerrojo)]
        for env in inst.glob("environments/*/"):
            (env / ".leases").mkdir(exist_ok=True)
            a += ["--bind", str(env / ".leases"), str(env / ".leases")]
    for p in rw:
        a += ["--bind", str(p), str(p)]
    a += ["--symlink", H, "/home/servidor", "--clearenv",
          "--setenv", "HOME", H, "--setenv", "USER", "server", "--setenv", "LANG", os.environ.get("LANG", "es_ES.UTF-8"),
          "--setenv", "PATH", f"{H}/.hermes/hermes-agent/node_modules/.bin:{H}/.local/bin:/usr/local/bin:/usr/bin:/bin",
          "--setenv", "TZ", "Europe/Madrid", "--chdir", str(rw[2])]
    # lo que pone la unidad de systemd del gateway (y nada más): su HERMES_HOME y la marca de proceso supervisado
    if os.environ.get("HERMES_HOME") == str(rw[0]):
        a += ["--setenv", "HERMES_HOME", str(rw[0])]
    if os.environ.get("HERMES_SUPERVISED_CHILD"):
        a += ["--setenv", "HERMES_SUPERVISED_CHILD", os.environ["HERMES_SUPERVISED_CHILD"]]
    return a


def unidad(perfil, exec_start, casa=False):
    """Ajuste (drop-in) de systemd que mete el gateway de la invitada en la jaula. `exec_start`: el ExecStart= que generó Hermes."""
    return ("# Lo escribe el Hub (jaula.py): el gateway de la invitada corre dentro de su jaula. No editar a mano.\n[Service]\n"
            f"ExecStart=\nExecStart=/usr/bin/python3 {HUB / 'jaula.py'} {'--casa ' if casa else ''}{perfil} {exec_start}\n"
            "ExecReload=\n"            # USR1 iría a bwrap, no a Hermes
            "KillMode=control-group\n")   # SIGTERM a todo lo de dentro (bwrap no reenvía señales): Hermes se apaga con calma


if __name__ == "__main__":
    con_casa = sys.argv[1:2] == ["--casa"]
    args = sys.argv[2:] if con_casa else sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    a = argv(args[0], casa=con_casa) + args[1:]
    os.execv(a[0], a)
