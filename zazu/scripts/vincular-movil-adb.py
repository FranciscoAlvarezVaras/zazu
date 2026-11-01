#!/home/server/.hermes/tools/pyenv/bin/python
"""Vincula el móvil de Fran con el servidor por adb (depuración inalámbrica) usando un código QR. Sin IA.

Uso: vincular-movil-adb.py qr          → genera el QR (nombre y clave de un solo uso inventados aquí) y lo guarda en
                                          ~/.local/state/movil-adb/qr.png; después espera hasta 3 min a que Fran lo escanee
                                          (Opciones de desarrollador › Depuración inalámbrica › Vincular con código QR)
     vincular-movil-adb.py conectar    → conecta con el móvil ya vinculado (lo busca por mDNS en la red de casa)
     vincular-movil-adb.py estado      → dice si hay un móvil conectado por adb

La clave del QR la inventa este script y solo sirve para esta vinculación: Fran no tiene que dictar ningún código.
Requisito: el móvil en la misma Wi-Fi que el servidor. Zazu solo puede usar adb con el permiso de Fran (hook).
"""
import re, secrets, string, subprocess, sys, time
from pathlib import Path

ADB = str(Path.home() / ".local/opt/platform-tools/adb")
ESTADO = Path.home() / ".local/state/movil-adb"


def adb(*args, timeout=30):
    return subprocess.run([ADB, *args], capture_output=True, text=True, timeout=timeout)


def servicios():
    """[(nombre, tipo, ip:puerto)] que anuncian los móviles por mDNS."""
    out = adb("mdns", "services").stdout
    return [tuple(l.split()[:3]) for l in out.splitlines() if "_adb-tls-" in l and len(l.split()) >= 3]


def qr():
    import qrcode
    ESTADO.mkdir(parents=True, exist_ok=True)
    nombre = "zazu-" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    clave = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    qrcode.make(f"WIFI:T:ADB;S:{nombre};P:{clave};;").save(ESTADO / "qr.png")
    print(f"QR listo: {ESTADO / 'qr.png'}. Escanéalo en el móvil: Opciones de desarrollador › Depuración inalámbrica › "
          "Vincular dispositivo con código QR. Espero hasta 3 minutos…", flush=True)
    fin = time.time() + 180
    while time.time() < fin:
        for n, tipo, dir_ in servicios():
            if n == nombre and "pairing" in tipo:
                r = adb("pair", dir_, clave, timeout=60)
                ok = "Successfully paired" in r.stdout
                print("✅ Móvil vinculado." if ok else f"🔴 No se pudo vincular: {(r.stdout + r.stderr).strip()[:200]}")
                (ESTADO / "qr.png").unlink(missing_ok=True)
                if ok:
                    time.sleep(3)
                    conectar()
                return 0 if ok else 1
        time.sleep(2)
    (ESTADO / "qr.png").unlink(missing_ok=True)
    print("🔴 No vi el QR escaneado en 3 minutos. ¿El móvil está en la misma Wi-Fi que el servidor? Pídelo otra vez.")
    return 1


def conectar():
    for _, tipo, dir_ in servicios():
        if "connect" in tipo:
            r = adb("connect", dir_)
            print(r.stdout.strip() or r.stderr.strip())
    return estado()


def estado():
    lineas = [l for l in adb("devices", "-l").stdout.splitlines()[1:] if l.strip()]
    if not lineas:
        print("No hay ningún móvil conectado por adb. Activa «Depuración inalámbrica» en el móvil y pide «conectar».")
        return 1
    for l in lineas:
        m = re.search(r"model:(\S+)", l)
        print(f"Conectado: {m.group(1) if m else l.split()[0]} ({'listo' if ' device ' in l + ' ' else l.split()[1]})")
    return 0


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "estado"
    sys.exit({"qr": qr, "conectar": conectar, "estado": estado}.get(accion, estado)())
