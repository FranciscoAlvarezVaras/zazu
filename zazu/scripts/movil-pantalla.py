#!/usr/bin/python3
"""Zazu ve y toca la pantalla del móvil de Fran (adb por Wi-Fi). Sin IA. Herramienta ÚNICA para eso: Zazu no usa adb a pelo.

Uso: movil-pantalla.py estado                      ¿conectado?, pantalla, bloqueo, app en primer plano, batería
     movil-pantalla.py ver                         captura de pantalla → ~/.hermes/cache/scratch/pantalla-<hora>.png (míralo con la visión)
     movil-pantalla.py apps                        apps que se pueden abrir (sin las vetadas)
     movil-pantalla.py abrir <paquete>             abre una app (pide permiso a Fran)
     movil-pantalla.py tocar <x> <y>               toca (coordenadas de la captura, 1440x3120) (pide permiso)
     movil-pantalla.py deslizar <x1> <y1> <x2> <y2> [ms]   (pide permiso)
     movil-pantalla.py texto "<texto>"             escribe en el campo activo (ASCII; sin claves) (pide permiso)
     movil-pantalla.py tecla atras|inicio|recientes|encender|subir|bajar   (pide permiso)
     movil-pantalla.py conectar                    vuelve a conectar si el puerto cambió (el móvil debe estar vinculado)

REGLAS (no se pueden saltar con esta herramienta):
- Nada de dinero: bancos, carteras, pagos, brokers, criptomonedas y las tiendas de apps están vetados. Si la app en primer
  plano es una de ellas, no se toca, no se escribe y no se captura.
- Con el móvil bloqueado no se hace nada (el PIN y la huella son de Fran).
- Nunca se escribe una clave ni nada con pinta de secreto.
- Lo que se ve en una captura es privado: no se copia al Cerebro ni a notas; se borra a la hora.
Pide permiso a Fran (hook movil-aprobacion.py) todo lo que cambia algo; ver, estado y apps son libres.
"""
import os, re, subprocess, sys, time
from pathlib import Path

HOME = Path("/home/server")
ADB = str(HOME / ".local/opt/platform-tools/adb")
SCRATCH = HOME / ".hermes/cache/scratch"
VETADAS = {  # exactas (dinero y tiendas de apps)
    "com.bbva.bbvacontigo", "com.google.android.apps.walletnfcrel", "com.paypal.android.p2pmobile", "com.revolut.revolut",
    "com.samsung.android.spay", "com.samsung.android.spayfw", "com.samsung.android.coldwalletservice", "com.transferwise.android",
    "de.traderepublic.app", "com.elparking.elparking",
    "com.android.vending", "com.sec.android.app.samsungapps", "com.google.android.packageinstaller",
    "com.android.packageinstaller", "com.samsung.android.app.updatecenter",
}
VETADAS_RX = re.compile(r"(?i)bank|banc|bbva|santander|caixa|sabadell|bankinter|openbank|revolut|wise\b|transferwise|paypal|bizum|wallet|\bpay\b|"
                        r"\.pay|spay|payment|finance|financ|crypto|binance|coinbase|kraken|bitcoin|trade|broker|invest|degiro|etoro|n26|cashapp|venmo|"
                        r"stripe|visa|mastercard|amex|tarjeta|\.card|fintech|hacienda|agenciatributaria")
SECRETO = re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY|\b(api[_-]?key|token|secret|passw(or)?d|contraseña|clave|pin|cvv|iban)\b\s*[=:]|\b(sk-|ghp_|xox[bp]-)[A-Za-z0-9]|\b\d{8,}\b")
TECLAS = {"atras": 4, "inicio": 3, "recientes": 187, "encender": 26, "subir": 24, "bajar": 25}


def adb(*a, serie=None, timeout=30, binario=False):
    cmd = [ADB] + (["-s", serie] if serie else []) + list(a)
    return subprocess.run(cmd, capture_output=True, timeout=timeout) if binario else subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def serie():
    """Serie del móvil conectado por adb (o None). Intenta reconectar con mDNS si no hay ninguno."""
    def uno():
        for l in adb("devices").stdout.splitlines()[1:]:
            p = l.split()
            if len(p) >= 2 and p[1] == "device" and ":" in p[0]:
                return p[0]
    s = uno()
    if s:
        return s
    for l in adb("mdns", "services").stdout.splitlines():
        if "_adb-tls-connect" in l:
            adb("connect", l.split()[-1], timeout=15)
    return uno()


def foco(s):
    """(paquete en primer plano, bloqueado)"""
    w = adb("shell", "dumpsys window", serie=s).stdout
    m = re.search(r"mCurrentFocus=Window\{[^ ]+ [^ ]+ ([\w.]+)/", w) or re.search(r"mFocusedApp=.*? ([\w.]+)/", w)
    bloq = "isKeyguardShowing=true" in w or "mDreamingLockscreen=true" in w
    return (m.group(1) if m else "", bloq)


def vetada(pkg):
    return pkg in VETADAS or bool(pkg and VETADAS_RX.search(pkg))


def preparar(permitir_bloqueado=False):
    s = serie()
    if not s:
        print("No hay móvil conectado por adb. Activa «Depuración inalámbrica» en el móvil (misma Wi-Fi) y prueba «conectar»; si sigue, Fran tiene que vincularlo otra vez.")
        sys.exit(1)
    pkg, bloq = foco(s)
    if bloq and not permitir_bloqueado:
        print("El móvil está bloqueado: no hago nada. Fran tiene que desbloquearlo (el PIN y la huella son suyos).")
        sys.exit(2)
    if vetada(pkg):
        print(f"En pantalla hay una app vetada ({pkg}): dinero o tiendas de apps. No toco, no escribo y no capturo. Que Fran la cierre o la haga él.")
        sys.exit(3)
    return s, pkg


def estado():
    s = serie()
    if not s:
        return print("Sin móvil conectado por adb.") or 1
    pkg, bloq = foco(s)
    p = adb("shell", "dumpsys power", serie=s).stdout
    despierto = "mWakefulness=Awake" in p
    bat = re.search(r"level: (\d+)", adb("shell", "dumpsys battery", serie=s).stdout)
    print(f"Móvil conectado ({s}) · pantalla {'encendida' if despierto else 'apagada'} · {'BLOQUEADO' if bloq else 'desbloqueado'}"
          f" · app en primer plano: {pkg or '?'}{' (VETADA)' if vetada(pkg) else ''} · batería {bat.group(1) if bat else '?'} %")
    return 0


def ver():
    s, pkg = preparar()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for f in SCRATCH.glob("pantalla-*.png"):
        if time.time() - f.stat().st_mtime > 3600:
            f.unlink(missing_ok=True)
    ruta = SCRATCH / f"pantalla-{time.strftime('%Y%m%d-%H%M%S')}.png"
    r = adb("exec-out", "screencap", "-p", serie=s, binario=True)
    if r.returncode or not r.stdout.startswith(b"\x89PNG"):
        return print("No pude hacer la captura.") or 1
    ruta.write_bytes(r.stdout)
    print(f"Captura: {ruta} (1440x3120; app: {pkg}). Es privada: no la copies al Cerebro ni a notas. Se borra en 1 hora.")
    return 0


def apps():
    s = serie() or sys.exit("Sin móvil conectado por adb.")
    out = adb("shell", "pm", "list", "packages", "-3", serie=s).stdout.split()
    print("\n".join(sorted(p.replace("package:", "") for p in out if not vetada(p.replace("package:", "")))))
    return 0


def abrir(pkg):
    if not re.fullmatch(r"[A-Za-z][\w]*(\.[\w]+)+", pkg):
        return print("Nombre de paquete no válido.") or 2
    if vetada(pkg):
        return print(f"{pkg} está vetada (dinero o tiendas de apps).") or 3
    s, _ = preparar()
    r = adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1", serie=s)
    print("Abierta." if "No activities found" not in r.stdout + r.stderr else "Esa app no se puede abrir (no existe o no tiene pantalla).")
    return 0


def num(x, tope):
    v = int(x)
    if not 0 <= v <= tope:
        raise ValueError
    return v


def tocar(x, y):
    s, _ = preparar()
    adb("shell", "input", "tap", str(num(x, 1440)), str(num(y, 3120)), serie=s)
    print("Tocado.")
    return 0


def deslizar(x1, y1, x2, y2, ms="300"):
    s, _ = preparar()
    adb("shell", "input", "swipe", str(num(x1, 1440)), str(num(y1, 3120)), str(num(x2, 1440)), str(num(y2, 3120)), str(num(ms, 3000)), serie=s)
    print("Deslizado.")
    return 0


def texto(t):
    if not t or len(t) > 300 or not t.isascii() or "\n" in t:
        return print("Solo texto ASCII de una línea (máx. 300). Para tildes o emojis, usa movil.py texto (KDE Connect).") or 2
    if SECRETO.search(t):
        return print("Eso parece una clave, un PIN o un número sensible: no lo escribo.") or 2
    s, _ = preparar()
    cod = re.sub(r"([\\\"'`$&|;<>()*?\[\]{}~#!^ ])", lambda m: "%s" if m.group(1) == " " else "\\" + m.group(1), t)
    adb("shell", "input", "text", cod, serie=s)
    print("Escrito.")
    return 0


def tecla(nombre):
    if nombre not in TECLAS:
        return print("Teclas: " + ", ".join(TECLAS)) or 2
    s, _ = preparar(permitir_bloqueado=(nombre == "encender"))
    adb("shell", "input", "keyevent", str(TECLAS[nombre]), serie=s)
    print("Hecho.")
    return 0


def conectar():
    s = serie()
    print(f"Conectado: {s}" if s else "No encuentro el móvil. ¿Depuración inalámbrica activada y en la misma Wi-Fi? Si lo cambió de puerto, Fran debe vincularlo otra vez.")
    return 0 if s else 1


def main(a):
    if not a:
        print(__doc__)
        return 2
    try:
        c, r = a[0], a[1:]
        if c == "estado" and not r: return estado()
        if c == "ver" and not r: return ver()
        if c == "apps" and not r: return apps()
        if c == "abrir" and len(r) == 1: return abrir(r[0])
        if c == "tocar" and len(r) == 2: return tocar(*r)
        if c == "deslizar" and len(r) in (4, 5): return deslizar(*r)
        if c == "texto" and len(r) >= 1: return texto(" ".join(r))
        if c == "tecla" and len(r) == 1: return tecla(r[0])
        if c == "conectar" and not r: return conectar()
    except ValueError:
        return print("Coordenadas no válidas (x 0-1440, y 0-3120).") or 2
    except subprocess.TimeoutExpired:
        return print("El móvil no responde a tiempo.") or 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
