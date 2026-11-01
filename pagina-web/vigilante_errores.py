#!/usr/bin/env python3
"""Vigilante de errores de las invitadas: lo lanza un temporizador cada 10 minutos (zazu-vigilante-errores.timer).

1. Lee los errores nuevos del registro (errores_invitadas.py).
2. Revisa a cada invitada y ARREGLA lo que es seguro arreglar solo:
   - su Zazu sin el modelo incluido (Claude Haiku) cuando no tiene IA propia → se vuelve a poner;
   - el crédito sin aplicar (tiene crédito y no tiene la clave, o al revés) → se aplica;
   - le faltan reglas en sus instrucciones (server.SOUL_MARCAS: solo Fran cambia la app, recordatorios, hablar sin
     tecnicismos y contárselo a Fran…) → se rehacen con su nombre y su tono;
   - el tiempo de espera de sus herramientas de Google por debajo de 180 s → se sube;
   - tiene rutinas y su gateway (el que las ejecuta) está parado → se arranca, dentro de su jaula.
3. Lo que no sabe arreglar (errores nuevos sin causa conocida, falta la clave de la API, nadie tiene avisos…) lo deja
   en el informe y se lo manda a Fran por push. Nunca cambia el código: eso lo decide Fran.

Informe: ~/.local/state/zazu-web/vigilante-errores.json (lo enseña la pantalla Personas).
Uso a mano: python3 vigilante_errores.py   (--sin-push para no avisar)
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import errores_invitadas  # noqa: E402
import server  # noqa: E402

INFORME = Path.home() / ".local/state/zazu-web/vigilante-errores.json"
MAX_ARREGLOS = 100



def _cargar():
    try:
        return json.loads(INFORME.read_text())
    except (OSError, ValueError):
        return {"visto_hasta": time.time() - 3600, "arreglos": []}


def _guardar(d):
    INFORME.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = INFORME.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, json.dumps(d, ensure_ascii=False, indent=1).encode())
    os.close(fd)
    os.replace(tmp, INFORME)


def _cfg(prof, clave):
    try:
        m = re.search(rf"^\s*{re.escape(clave)}:\s*['\"]?([^'\"\n]+)", (server.prof_dir(prof) / "config.yaml").read_text(), re.M)
        return m.group(1).strip() if m else ""
    except OSError:
        return ""


def revisar(email, v, arreglos, pendientes):
    prof, nombre = v["profile"], v.get("name") or email
    def arreglado(que):
        arreglos.append({"t": round(time.time()), "perfil": prof, "nombre": nombre, "que": que})
    if prof not in server.profiles():
        pendientes.append({"perfil": prof, "nombre": nombre, "problema": "su perfil de Zazu no existe en el PC"})
        return
    pd = server.prof_dir(prof)
    # 1. modelo incluido
    if not v.get("ai") and (_cfg(prof, "provider") != server.SHARED["provider"] or _cfg(prof, "default") != server.SHARED["model"]):
        server.set_shared(prof)
        arreglado(f"modelo vuelto a {server.SHARED['model']}")
    # 2. crédito
    if not v.get("ai") and not v.get("demo"):
        antes = bool(server.env_get(prof, server.SHARED["var"]))
        ahora = server.aplicar_credito(email)
        if antes != ahora:
            arreglado("crédito aplicado" if ahora else "crédito retirado (tope del mes o sin clave)")
    # 3. instrucciones (SOUL)
    try:
        soul = (pd / "SOUL.md").read_text()
    except OSError:
        soul = ""
    if not server.soul_al_dia(soul, v.get("nivel")):   # p. ej. los de antes del 23/10 no tienen «## Cómo hablas»; o su Google no es el de su nivel
        z = server.mi_zazu(email)
        (pd / "SOUL.md").write_text(server.soul_invitada(nombre, z["asistente"], z["tono"], z["largo"], z["web"], v.get("nivel")))
        arreglado("instrucciones de su Zazu rehechas (faltaban reglas)")
    # 4. espera de las herramientas de Google
    cfg = (pd / "config.yaml").read_text() if (pd / "config.yaml").exists() else ""
    m = re.search(r"google:[\s\S]{0,400}?timeout:\s*['\"]?(\d+)", cfg)
    if m and int(m.group(1)) < 180:
        server.hermes_set(prof, [("mcp_servers.google.timeout", "180")])
        arreglado("espera de sus herramientas subida a 180 s")
    # 5. rutinas sin gateway
    if server.rutinas_de(prof):
        unit = f"hermes-gateway-{prof}"
        activo = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True).stdout.strip()
        if activo != "active":
            enjaulado = "jaula.py" in subprocess.run(["systemctl", "--user", "cat", unit], capture_output=True, text=True).stdout
            if enjaulado:
                subprocess.run(["systemctl", "--user", "restart", unit], capture_output=True, timeout=120)
                arreglado("arrancado el servicio que ejecuta sus rutinas")
            else:
                pendientes.append({"perfil": prof, "nombre": nombre, "problema": "tiene rutinas pero su servicio no está instalado en la jaula: "
                                   "que borre y vuelva a crear una rutina desde la app"})


def main():
    push = "--sin-push" not in sys.argv
    inf = _cargar()
    desde = float(inf.get("visto_hasta") or 0)
    arreglos, pendientes = [], []
    if not server.clave_credito():
        pendientes.append({"perfil": "", "nombre": "todas", "problema": "falta la clave de la API de Claude: nadie puede chatear con tu crédito"})
    invitadas = {e: v for e, v in server.users().items() if v.get("role") == "guest" and v.get("profile")}
    for email, v in invitadas.items():
        try:
            revisar(email, v, arreglos, pendientes)
        except Exception as e:
            pendientes.append({"perfil": v["profile"], "nombre": v.get("name", ""), "problema": f"el vigilante falló al revisarla: {type(e).__name__}"})
    subs = server.push_subs()
    sin_avisos = [v.get("name") for e, v in invitadas.items() if not v.get("demo") and not any(server.push_de(s) == e for s in subs)]
    if sin_avisos:
        pendientes.append({"perfil": "", "nombre": ", ".join(sin_avisos), "problema": "no tienen activados los avisos en el móvil: no les llegan recordatorios ni permisos"})
    # errores nuevos del registro
    perfiles = [v["profile"] for v in invitadas.values() if not v.get("demo")]
    nuevos = [x for x in errores_invitadas.leer(perfiles, server.prof_dir, dias=2) if float(x.get("t") or 0) > desde]
    sin_causa = [x for x in nuevos if not errores_invitadas.conocido(x.get("detalle"))]
    nombres = {v["profile"]: v.get("name", "") for v in invitadas.values()}
    for x in sin_causa[:20]:
        pendientes.append({"perfil": x["perfil"], "nombre": nombres.get(x["perfil"], ""), "problema": f"error nuevo en {x['origen']}: {x['detalle'][:160]}"})
    inf.update(ultima=round(time.time()), visto_hasta=max([desde] + [float(x["t"]) for x in nuevos]), errores_nuevos=len(nuevos),
               arreglos=(arreglos + inf.get("arreglos", []))[:MAX_ARREGLOS], pendientes=pendientes)
    _guardar(inf)
    avisar = arreglos or sin_causa
    if push and avisar:
        partes = ([f"Arreglé {len(arreglos)}: " + "; ".join(f"{a['nombre']}: {a['que']}" for a in arreglos[:3])] if arreglos else []) + \
                 ([f"{len(sin_causa)} error(es) nuevo(s) sin causa conocida: " + "; ".join(f"{nombres.get(x['perfil'], '')}: {x['detalle'][:60]}" for x in sin_causa[:2])]
                  if sin_causa else [])
        server._push_hub({"titulo": "Vigilante de invitados", "cuerpo": " · ".join(partes)[:400], "tag": "vigilante-invitadas", "url": "/?tab=cuentas"})
    print(f"revisadas {len(invitadas)}, errores nuevos {len(nuevos)} ({len(sin_causa)} sin causa), arreglos {len(arreglos)}, pendientes {len(pendientes)}")
    for a in arreglos:
        print(f"  arreglado · {a['nombre']}: {a['que']}")
    for p in pendientes:
        print(f"  pendiente · {p['nombre']}: {p['problema']}")


if __name__ == "__main__":
    main()
