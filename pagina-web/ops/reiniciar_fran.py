#!/usr/bin/env python3
"""Reinicia el perfil de Fran para recorrer la app como un usuario nuevo, con COPIA COMPLETA y restaurable antes de tocar nada.

Uso (desde ~/Spirit/pagina-web):
  python3 ops/reiniciar_fran.py                 → solo dice lo que haría (no toca nada)
  python3 ops/reiniciar_fran.py --si            → copia en ~/Respaldos/fran-reinicio-<fecha>/ y reinicia
  python3 ops/reiniciar_fran.py --si --google   → además desconecta sus cuentas de Google (con copia de los tokens)
  python3 ops/reiniciar_fran.py --si --whatsapp → además desconecta su WhatsApp (wacli-sync; el almacén va a ~/Respaldos)
  python3 ops/reiniciar_fran.py --restaurar [carpeta] [--si]   → lo deja como estaba (por defecto, la copia más antigua sin restaurar)
  --email correo   solo esa cuenta de Fran (por defecto, las dos de LOGIN_EMAILS)
  --otra-vez       reiniciar aunque quede un reinicio sin restaurar (si no, se niega: la copia nueva guardaría a Fran ya vacío)

La copia: users.json, push.json, las memorias de sus perfiles (~/.hermes/memories y las de sus otros perfiles, p. ej. «tecnico»),
el state.db de cada uno de sus perfiles (con la API de copia de sqlite: vale aunque Hermes esté escribiendo) y ~/.config/hermes-hub/fran.
Si algo de la copia falla, no se toca nada.

El reinicio: en users.json, onboarded=False y sin prefs/ocultas/portada/noticias/dinero; USER.md y MEMORY.md vacíos;
sus conversaciones OCULTAS (hidden=1, nunca borradas: la lista queda en la copia para volver a enseñarlas) y sus avisos push quitados.
Las invitadas no se tocan. El servidor no hace falta reiniciarlo: lee users.json y push.json en cada petición.

Restaurar devuelve lo de Fran sin pisar lo que hayan cambiado las invitadas después: sus entradas de users.json, sus memorias,
vuelve a enseñar SOLO las conversaciones que se ocultaron, sus avisos push y, si se quitaron, sus tokens de Google.
El WhatsApp no se puede restaurar copiando (al desconectar, WhatsApp quita el dispositivo): se vuelve a vincular con el código.
"""
import argparse, json, os, pwd, shutil, sqlite3, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402  (con el HOME que toque: el de verdad o una casa falsa de pruebas)

HOME = server.HOME
RESPALDOS = HOME / "Respaldos"
QUITAR = ("prefs", "ocultas", "portada", "noticias", "dinero")


def copias_sin_restaurar():
    """Las copias de reinicios que aún no se han restaurado, de la más antigua a la más reciente."""
    out = []
    for f in RESPALDOS.glob("fran-reinicio-*/reinicio.json"):
        try:
            m = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not m.get("restaurado"):
            out.append((m.get("fecha") or "", f.stat().st_mtime, f.parent))
    return [d for _, _, d in sorted(out)]


def perfiles_fran():
    """{perfil: carpeta de Hermes} de Fran: default (~/.hermes) y los suyos de ~/.hermes/profiles (no los de las invitadas)."""
    invitadas = server.guest_profiles()
    out = {}
    for p, db in server.profiles().items():
        if p not in invitadas:
            out[p] = db.parent
    return out


def _gog(args):
    """gog de Fran (sin --home), con su entorno. → (código, salida)."""
    r = subprocess.run(["gog", "--no-input", *args], env=server._gog_env(), capture_output=True, text=True, timeout=60, cwd=str(HOME))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def cuentas_google():
    """[(email, cliente)] de Fran: cada token que tiene guardado gog (una cuenta puede tener dos, default y web)."""
    return [(a["email"], a.get("client") or "default") for a in server._list(server.gog(["auth", "list"]), "accounts") if a.get("email")]


def copia_sqlite(origen, destino):
    a = sqlite3.connect(f"file:{origen}?mode=ro", uri=True, timeout=30)
    b = sqlite3.connect(destino)
    try:
        a.backup(b)
        ok = b.execute("pragma integrity_check").fetchone()[0] == "ok"
    finally:
        b.close()
        a.close()
    if not ok:
        raise RuntimeError(f"la copia de {origen} no pasa integrity_check")


def escribir(p, texto, modo=0o600):
    tmp = p.with_name(p.name + ".tmp-reinicio")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modo)
    try:
        os.write(fd, texto.encode())
    finally:
        os.close(fd)
    os.replace(tmp, p)


def guardar_manifiesto(dest, m):
    escribir(dest / "reinicio.json", json.dumps(m, ensure_ascii=False, indent=1))


def copiar(emails, google, whatsapp):
    """La copia completa. Devuelve (carpeta, manifiesto). Si algo falla, borra la copia a medias y sale sin tocar nada."""
    RESPALDOS.mkdir(mode=0o700, parents=True, exist_ok=True)
    dest = base = RESPALDOS / f"fran-reinicio-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while dest.exists():
        n += 1
        dest = base.with_name(f"{base.name}-{n}")
    dest.mkdir(mode=0o700)
    m = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "home": str(HOME), "emails": emails, "perfiles": {}, "sesiones_ocultadas": {},
         "push_quitadas": [], "google": [], "whatsapp": None, "creadas": [], "hecho": False}
    try:
        server.push_subs(estricto=True)   # si push.json no se lee, mejor saberlo antes de tocar nada
        cfg = HOME / ".config/hermes-hub"
        for f in ("users.json", "push.json"):
            if (cfg / f).exists():
                shutil.copy2(cfg / f, dest / f)
        if (cfg / "fran").is_dir():
            shutil.copytree(cfg / "fran", dest / "fran", symlinks=True)
        (dest / "bd").mkdir(mode=0o700)
        for p, d in perfiles_fran().items():
            info = {"carpeta": str(d), "memorias": None, "no_habia": [f for f in ("USER.md", "MEMORY.md") if not (d / "memories" / f).exists()]}
            if (d / "memories").is_dir():
                shutil.copytree(d / "memories", dest / "memorias" / p, symlinks=True)
                info["memorias"] = f"memorias/{p}"
            copia_sqlite(d / "state.db", dest / "bd" / f"{p}.state.db")
            info["bd"] = f"bd/{p}.state.db"
            m["perfiles"][p] = info
        if google:
            (dest / "google").mkdir(mode=0o700)
            for email, cliente in cuentas_google():
                f = dest / "google" / f"{email}.{cliente}.json"
                rc, _ = _gog([f"--client={cliente}", "auth", "tokens", "export", email, "--out", str(f)])
                if rc or not f.exists():
                    raise RuntimeError(f"no pude copiar el token de Google de {email} ({cliente})")
                os.chmod(f, 0o600)
                m["google"].append({"email": email, "client": cliente, "archivo": f"google/{f.name}", "quitado": False})
        guardar_manifiesto(dest, m)
        (dest / "LEEME.txt").write_text(
            "Copia de Fran antes de reiniciar su perfil (ops/reiniciar_fran.py).\n"
            f"Para dejarlo como estaba: cd ~/Spirit/pagina-web && python3 ops/reiniciar_fran.py --restaurar {dest} --si\n"
            "Dentro: users.json y push.json (enteros), memorias/<perfil>/, bd/<perfil>.state.db (copia entera de cada historial),\n"
            "fran/ (~/.config/hermes-hub/fran), google/ (tokens, si se desconectó Google: SECRETOS) y reinicio.json (qué se cambió).\n")
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest, m


def reiniciar(dest, m, emails, google, whatsapp):
    # 1. users.json: Fran como nuevo (la guía de bienvenida y la pregunta de sus datos vuelven a salir)
    # server.users() siempre añade las cuentas de LOGIN_EMAILS: lo que había de verdad en users.json es la copia
    copia = json.loads((dest / "users.json").read_text()) if (dest / "users.json").exists() else {}
    with server.USERS_LOCK:
        us = server.users()
        for e in emails:
            if e not in copia:
                m["creadas"].append(e)   # al restaurar se quita: antes no estaba
            v = us.setdefault(e, {"name": "Fran", "role": "admin"})
            v["onboarded"] = False
            for k in QUITAR:
                v.pop(k, None)
        server.save_users(us)
    guardar_manifiesto(dest, m)
    print("  users.json: onboarded=False, sin prefs/ocultas/portada/noticias/dinero")
    # 2. memorias vacías (las copias .bak y los .lock de Hermes se quedan)
    for p, info in m["perfiles"].items():
        md = Path(info["carpeta"]) / "memories"
        md.mkdir(mode=0o700, parents=True, exist_ok=True)
        for f in ("USER.md", "MEMORY.md"):
            escribir(md / f, "")
        print(f"  memorias de «{p}»: USER.md y MEMORY.md vacíos")
    # 3. conversaciones ocultas (no borradas). La lista se apunta ANTES de ocultarlas.
    for p, info in m["perfiles"].items():
        c = sqlite3.connect(Path(info["carpeta"]) / "state.db", timeout=30)
        try:
            ids = [r[0] for r in c.execute("select id from sessions where hidden=0")]
            m["sesiones_ocultadas"][p] = ids
            guardar_manifiesto(dest, m)
            c.executemany("update sessions set hidden=1 where id=?", [(i,) for i in ids])
            c.commit()
        finally:
            c.close()
        print(f"  conversaciones de «{p}»: {len(ids)} ocultas")
    # 4. avisos push de Fran (los que no llevan correo de invitada)
    subs = server.push_subs(estricto=True)
    suyas = [x for x in subs if server.push_de(x) is None]
    m["push_quitadas"] = suyas
    guardar_manifiesto(dest, m)
    if suyas:
        escribir(server.PUSH_FILE, json.dumps([x for x in subs if server.push_de(x) is not None], indent=1))
    print(f"  avisos push: {len(suyas)} dispositivo(s) de Fran quitados")
    # 5. Google (opcional): el token ya está copiado; se quita uno a uno
    for g in m["google"]:
        rc, _ = _gog([f"--client={g['client']}", "auth", "remove", g["email"], "--force"])
        g["quitado"] = rc == 0
        guardar_manifiesto(dest, m)
        print(f"  Google {g['email']} ({g['client']}): {'desconectado' if rc == 0 else 'NO se pudo quitar'}")
    # 6. WhatsApp (opcional): la función de la app (para wacli-sync, cierra la sesión y mueve el almacén a ~/Respaldos)
    if whatsapp:
        try:
            habia = (server.WF._cfg["store"] / "session.db").exists()
            b, ok = server.WF.desconectar()
            m["whatsapp"] = {"respaldo": str(b) if b else None, "logout": ok}
            if not habia and not b:
                print("  WhatsApp: ya estaba desconectado (no había nada que hacer)")
            else:
                print(f"  WhatsApp: desconectado (almacén en {b or '—'}; cierre de sesión {'hecho' if ok else 'no confirmado'})")
        except Exception as e:
            m["whatsapp"] = {"error": str(e)}
            print(f"  WhatsApp: NO se pudo desconectar ({e})")
    m["hecho"] = True
    guardar_manifiesto(dest, m)


def restaurar(dest, si):
    m = json.loads((dest / "reinicio.json").read_text())
    if Path(m["home"]) != HOME:
        raise SystemExit(f"Esa copia es de otra casa ({m['home']}), no de {HOME}.")
    print(f"Restaurar desde {dest} (copia del {m['fecha']}):")
    viejos = json.loads((dest / "users.json").read_text()) if (dest / "users.json").exists() else {}
    print(f"  users.json: las entradas de {', '.join(m['emails'])} como estaban (las invitadas no se tocan)")
    for p, info in m["perfiles"].items():
        print(f"  «{p}»: memorias {'de la copia' if info.get('memorias') else '(no había)'}; {len(m['sesiones_ocultadas'].get(p, []))} conversaciones se vuelven a ver")
    print(f"  avisos push: {len(m['push_quitadas'])} dispositivo(s) de Fran")
    for g in m["google"]:
        if g.get("quitado"):
            print(f"  Google {g['email']} ({g['client']}): se vuelve a importar el token")
    if m.get("whatsapp"):
        print("  WhatsApp: no se restaura copiando. Vuélvelo a vincular en la app (Tus cuentas) con el código de 8 letras."
              + (f" Los mensajes viejos están en {m['whatsapp'].get('respaldo')}." if m["whatsapp"].get("respaldo") else ""))
    if not si:
        print("\n(Simulacro: no he tocado nada. Repite con --si para hacerlo.)")
        return
    with server.USERS_LOCK:
        us = server.users()
        for e in m["emails"]:
            if e in viejos:
                us[e] = viejos[e]
            elif e in m.get("creadas", []):
                us.pop(e, None)   # la creó el reinicio
            else:
                us.get(e, {}).pop("onboarded", None)
        server.save_users(us)
    for p, info in m["perfiles"].items():
        d = Path(info["carpeta"])
        if info.get("memorias"):
            for f in ("USER.md", "MEMORY.md"):
                src = dest / info["memorias"] / f
                if src.exists():
                    (d / "memories").mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copy2(src, d / "memories" / f)
        for f in info.get("no_habia", []):   # no existían antes del reinicio: si siguen vacías, fuera
            x = d / "memories" / f
            if x.is_file() and not x.stat().st_size:
                x.unlink()
        ids = m["sesiones_ocultadas"].get(p, [])
        if ids:
            c = sqlite3.connect(d / "state.db", timeout=30)
            try:
                c.executemany("update sessions set hidden=0 where id=?", [(i,) for i in ids])
                c.commit()
            finally:
                c.close()
    if m["push_quitadas"]:
        subs = server.push_subs(estricto=True)
        ya = {x["endpoint"] for x in subs}
        escribir(server.PUSH_FILE, json.dumps(subs + [x for x in m["push_quitadas"] if x["endpoint"] not in ya], indent=1))
    for g in m["google"]:
        if g.get("quitado"):
            rc, _ = _gog(["auth", "tokens", "import", str(dest / g["archivo"])])
            print(f"  Google {g['email']}: {'restaurado' if rc == 0 else 'NO se pudo importar (el archivo sigue en la copia)'}")
    server._CACHE.clear()
    m["restaurado"] = time.strftime("%Y-%m-%d %H:%M:%S")
    guardar_manifiesto(dest, m)
    print("Hecho: Fran está como antes del reinicio.")
    for d in copias_sin_restaurar():   # las de reinicios posteriores guardan a Fran ya reiniciado: quedan superadas
        f = d / "reinicio.json"
        m2 = json.loads(f.read_text())
        if d != dest and m2.get("fecha", "") >= m["fecha"]:
            m2["restaurado"] = f"superada al restaurar {dest.name}"
            guardar_manifiesto(d, m2)
    otras = copias_sin_restaurar()
    if otras:
        print("Ojo: quedan copias más antiguas sin restaurar: " + ", ".join(str(d) for d in otras))


def main():
    ap = argparse.ArgumentParser(description="Reinicia el perfil de Fran (con copia) o lo restaura.")
    ap.add_argument("--si", action="store_true", help="hacerlo de verdad (sin esto, solo dice lo que haría)")
    ap.add_argument("--google", action="store_true", help="desconectar también sus cuentas de Google (con copia de los tokens)")
    ap.add_argument("--whatsapp", action="store_true", help="desconectar también su WhatsApp")
    ap.add_argument("--otra-vez", action="store_true", help="reiniciar aunque haya un reinicio anterior sin restaurar")
    ap.add_argument("--email", action="append", help="solo esta cuenta de Fran (se puede repetir)")
    ap.add_argument("--restaurar", nargs="?", const="", metavar="CARPETA", help="dejarlo como estaba (por defecto, la copia más antigua sin restaurar)")
    a = ap.parse_args()
    if a.restaurar is not None:
        if a.restaurar:
            dest = Path(a.restaurar).expanduser()
        else:   # la más antigua sin restaurar: es la de antes del primer reinicio (las siguientes ya guardan a Fran reiniciado)
            copias = copias_sin_restaurar()
            if not copias:
                raise SystemExit(f"No hay copias sin restaurar en {RESPALDOS}.")
            dest = copias[0]
            if len(copias) > 1:
                print(f"Hay {len(copias)} copias sin restaurar; uso la más antigua ({dest.name}), la de antes del primer reinicio.")
        return restaurar(dest, a.si)
    emails = sorted(set(a.email or server.LOGIN_EMAILS))
    malos = [e for e in emails if e not in server.LOGIN_EMAILS]
    if malos:
        raise SystemExit(f"Eso no es una cuenta de Fran: {', '.join(malos)}")
    real = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if a.whatsapp and HOME.resolve() != real and server.WF._cfg.get("systemctl") == ["systemctl", "--user"]:
        raise SystemExit(f"Casa de pruebas ({HOME}) con el systemctl de verdad: --whatsapp pararía el wacli-sync REAL. "
                         "Usa HUB_DEV=1 y HUB_SYSTEMCTL=tests/fakesystemctl.py.")
    pend = copias_sin_restaurar()
    if a.si and pend and not a.otra_vez:
        raise SystemExit(f"Ya hay un reinicio sin restaurar ({pend[0]}): otra copia guardaría a Fran ya reiniciado.\n"
                         f"Restaura antes (python3 ops/reiniciar_fran.py --restaurar {pend[0]} --si) o repite con --otra-vez.")
    print(f"Casa: {HOME}\nCuentas: {', '.join(emails)}\nPerfiles de Fran: {', '.join(perfiles_fran())}")
    print("Hará: copia completa en ~/Respaldos/fran-reinicio-<fecha>/; onboarded=False y sin prefs/ocultas/portada/noticias/dinero;"
          " USER.md y MEMORY.md vacíos; conversaciones ocultas (no borradas); sus avisos push quitados"
          + ("; Google desconectado" if a.google else "") + ("; WhatsApp desconectado" if a.whatsapp else "") + ".")
    if not a.si:
        print("\n(Simulacro: no he tocado nada. Repite con --si para hacerlo.)")
        return
    dest, m = copiar(emails, a.google, a.whatsapp)
    print(f"Copia hecha en {dest}")
    reiniciar(dest, m, emails, a.google, a.whatsapp)
    server._CACHE.clear()
    print(f"\nListo. Para volver atrás: python3 ops/reiniciar_fran.py --restaurar {dest} --si")


if __name__ == "__main__":
    main()
