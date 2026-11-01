"""«Vincular mi WhatsApp» y «Desconectar mi WhatsApp» de Fran desde la app (solo LOGIN_EMAILS). Solo biblioteca estándar.

Cómo está montado el WhatsApp de Fran (desde el recorte del 21-10):
  wacli-sync.service    `wacli sync --follow`: el dispositivo vinculado que lee su WhatsApp. Su almacén (sesión + mensajes) es
                        ~/.local/state/wacli (session.db = la sesión de WhatsApp, wacli.db = los mensajes, media/). Lo leen en solo
                        lectura el Hub (wa_fran, «agenda con mis chats»), el vigía y la habilidad buscar-en-whatsapp de Hermes.
  hermes-gateway        su WhatsApp está APAGADO a propósito (platforms.whatsapp.enabled: false en ~/.hermes/config.yaml); su sesión
                        vieja del puente (~/.hermes/whatsapp/session) no la usa nadie. Por eso aquí no se toca el gateway.

Vincular (código de 8 letras, «Vincular con el número de teléfono», como el de las invitadas):
  1. `wacli --store <almacén>.nuevo --events auth --phone N` empareja en una carpeta NUEVA. wacli-sync sigue funcionando con la vieja.
  2. Solo si conecta (y `auth status` de la carpeta nueva lo confirma): se para wacli-sync, la vieja se MUEVE a ~/Respaldos
     (whatsapp-fran-AAAAMMDD-HHMMSS), la nueva ocupa su sitio y wacli-sync vuelve a arrancar (unos segundos parado).
  3. Si falla, caduca o se cancela: se borra la carpeta nueva y no se toca nada más (wacli-sync ni se paró).
Desconectar: se para y se desactiva wacli-sync, `auth logout` (WhatsApp quita el dispositivo), el almacén se mueve a ~/Respaldos
y queda una carpeta vacía (la app lo ve «sin vincular»). Para volver, se vincula otra vez.

systemctl y wacli se inyectan (configurar): en las pruebas son falsos y nunca tocan los servicios de verdad.
"""
import json, os, re, shutil, subprocess, threading, time
from pathlib import Path

UNIDAD = "wacli-sync"
VALE = 150          # s que dura un código (WhatsApp cierra el emparejado a los ~160 s; wacli pide entonces otro)
ESPERA = 360        # el emparejado entero se corta a los 6 min
IDLE = "20s"        # tras conectar, wacli termina la primera carga cuando lleva 20 s sin recibir nada (wacli-sync sigue después)

_cfg = {}
_L = threading.Lock()
_V = {}             # el emparejado en curso (se SUSTITUYE, nunca se vacía: cada hilo sabe así si sigue siendo el suyo)
_CODIGO = re.compile(r"\b([A-Z0-9]{4})-?([A-Z0-9]{4})\b")


def configurar(store, respaldos, estado_json, wacli, systemctl, al_cambiar=lambda: None):
    """store: el almacén de wacli-sync; respaldos: ~/Respaldos; estado_json: dónde se apunta el número y la última copia;
    wacli: ruta del binario; systemctl: lista de la orden («["systemctl", "--user"]») o None (entonces no se toca nada);
    al_cambiar(): se llama tras cambiar el almacén (para borrar la caché de wa_fran)."""
    _cfg.update(store=Path(store), respaldos=Path(respaldos), estado_json=Path(estado_json), wacli=str(wacli), systemctl=systemctl,
                al_cambiar=al_cambiar)


def _nueva():
    return _cfg["store"].with_name(_cfg["store"].name + ".nuevo")


def _sc(*args):
    if not _cfg.get("systemctl"):
        raise RuntimeError("sin systemctl configurado")
    r = subprocess.run([*_cfg["systemctl"], *args, UNIDAD], capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    return r.returncode == 0


def _env():
    return {k: v for k, v in os.environ.items() if k != "WACLI_READONLY"}   # auth y logout escriben (en SU almacén, nunca en otro)


def _apuntes():
    try:
        return json.loads(_cfg["estado_json"].read_text())
    except (OSError, ValueError):
        return {}


def _apuntar(**kv):
    d = {**_apuntes(), **kv}
    _cfg["estado_json"].parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = _cfg["estado_json"].with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False))
    os.replace(tmp, _cfg["estado_json"])


def _respaldo(motivo):
    _cfg["respaldos"].mkdir(mode=0o700, parents=True, exist_ok=True)
    b = base = _cfg["respaldos"] / f"whatsapp-fran-{motivo}-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while b.exists():
        n += 1
        b = base.with_name(f"{base.name}-{n}")
    return b


def _estado_auth(store):
    """`wacli auth status` en solo lectura (lee session.db sin el candado): {"authenticated": bool, "phone": "34…"} o {}."""
    try:
        r = subprocess.run([_cfg["wacli"], "--store", str(store), "--read-only", "--json", "auth", "status"], capture_output=True, text=True,
                           timeout=30, stdin=subprocess.DEVNULL, env={**_env(), "WACLI_READONLY": "1"})
        d = json.loads(r.stdout)
        d = d.get("data") if isinstance(d, dict) and "data" in d else d
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def _leer(linea, v):
    """Una línea de `wacli --events auth --phone` (NDJSON en stderr, o el texto de stdout)."""
    try:
        ev = json.loads(linea)
    except ValueError:
        ev = None
    if isinstance(ev, dict):
        nombre = str(ev.get("event") or "")
        datos = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if nombre == "pair_code":
            m = _CODIGO.fullmatch(str(datos.get("code") or ""))
            if m and f"{m.group(1)}-{m.group(2)}" != v["codigo"]:
                v["codigo"], v["codigo_t"] = f"{m.group(1)}-{m.group(2)}", time.time()
        elif nombre in ("connected", "authenticated") or datos.get("authenticated") is True:
            v["autenticado"] = True
        elif nombre in ("error", "fatal") or nombre.endswith(".fatal"):
            v["fallo"] = str(datos.get("error") or datos.get("message") or nombre)
        return
    if linea.startswith(("Authenticated", "Connected")):
        v["autenticado"] = True
    elif "error" in linea.lower():
        v["fallo"] = linea


def _motivo(fallo):
    f = (fallo or "").lower()
    if "rate" in f or "429" in f:
        return "WhatsApp pide esperar un rato antes de dar otro código. Prueba dentro de unos minutos."
    if "passkey" in f:
        return "WhatsApp pide una llave de acceso que este sistema aún no sabe usar. Tu WhatsApp de antes sigue igual."
    if "pair phone" in f or "invalid --phone" in f:
        return "WhatsApp no quiso dar el código. Revisa que el número es el de tu WhatsApp y prueba en un par de minutos."
    return None


def _matar(v):
    p = v.get("proc")
    if p and p.poll() is None:
        p.kill()
        try:
            p.wait(timeout=5)   # que no escriba en la carpeta nueva mientras se borra
        except subprocess.TimeoutExpired:
            pass


def _limpiar_nueva(logout=False):
    n = _nueva()
    if logout and n.exists() and _estado_auth(n).get("authenticated"):
        try:   # vinculó pero no se usa: que no quede un dispositivo fantasma en su WhatsApp
            subprocess.run([_cfg["wacli"], "--store", str(n), "auth", "logout"], capture_output=True, timeout=60, stdin=subprocess.DEVNULL, env=_env())
        except (OSError, subprocess.TimeoutExpired):
            pass
    shutil.rmtree(n, ignore_errors=True)


def estado():
    v = _V or {}
    a = _apuntes()
    codigo = v.get("codigo") if v.get("estado") == "esperando" and not v.get("autenticado") else None
    return {"emparejando": v.get("estado"), "codigo": codigo, "telefono": v.get("telefono"),
            "caduca_en": max(0, round(v["codigo_t"] + VALE - time.time())) if codigo else None,
            "guardando": bool(v.get("estado") == "esperando" and v.get("autenticado")),   # ya conectó: terminando de poner la sesión en su sitio
            "error": v.get("error") if v.get("estado") == "error" else None,
            "parado": bool(v.get("estado") == "conectado" and v.get("parado")),
            "numero": a.get("numero"), "desde": a.get("desde"), "respaldo": a.get("respaldo"), "desconectado": a.get("desconectado")}


def vincular(telefono, nuevo=False):
    """Empieza el emparejado en una carpeta nueva y espera (hasta 30 s) el código. Devuelve estado()."""
    global _V
    if not _cfg.get("systemctl"):
        raise RuntimeError("Aquí no se puede vincular WhatsApp (falta configurar el servicio).")
    with _L:
        v = _V
        if v.get("estado") == "esperando" and v.get("autenticado"):   # aunque wacli ya haya salido: su hilo está poniendo la sesión en su sitio
            raise ValueError("Ya está conectado: espera unos segundos a que termine de guardarse.")
        if v.get("estado") == "esperando" and v.get("proc") and v["proc"].poll() is None:
            if v.get("telefono") == telefono and not nuevo:
                return estado()   # el mismo número: se sigue con el código que ya hay
        v["cancelado"] = True   # su hilo ya no es el bueno: no pone nada en su sitio
        _matar(v)
        _limpiar_nueva()
        n = _nueva()
        n.mkdir(mode=0o700, parents=True)
        nv = {"proc": None, "estado": "esperando", "codigo": None, "codigo_t": 0, "telefono": telefono, "error": None, "autenticado": False,
              "cancelado": False, "fallo": None}
        try:
            nv["proc"] = subprocess.Popen([_cfg["wacli"], "--store", str(n), "--events", "auth", "--phone", telefono, "--idle-exit", IDLE],
                                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env())
        except OSError:
            shutil.rmtree(n, ignore_errors=True)
            raise RuntimeError("No pude preparar WhatsApp ahora. Tu WhatsApp de antes sigue igual.") from None
        _V = nv
        hilo = threading.Thread(target=_seguir, args=(nv,), daemon=True)
        hilo.start()
    for _ in range(120):
        if nv["codigo"] or nv["estado"] != "esperando":
            break
        time.sleep(0.25)
    return estado()


def _seguir(v):
    proc = v["proc"]
    t = threading.Timer(ESPERA, lambda: (v.update(caducado=True), proc.kill()))
    t.daemon = True
    t.start()
    for linea in proc.stdout:
        _leer(linea.strip(), v)
    rc = proc.wait()
    proc.stdout.close()
    t.cancel()
    with _L:
        if v.get("cancelado") or _V is not v:
            return
        n = _nueva()
        st = _estado_auth(n) if (rc == 0 or v["autenticado"]) else {}
        if not st.get("authenticated"):
            _limpiar_nueva(logout=True)
            v["error"] = _motivo(v.get("fallo")) or ("Se acabó el tiempo para vincular. Pide un código nuevo." if v.get("caducado")
                                                    else "No se completó la vinculación. Pide un código nuevo y escríbelo enseguida.")
            v["estado"] = "error"
            return
        try:
            b, arrancado = _poner_en_su_sitio(n)
        except Exception as e:   # todo vuelve a como estaba (y wacli-sync arrancado)
            print(f"whatsapp de Fran: vinculado pero sin poner en su sitio: {type(e).__name__}: {e}", flush=True)
            _limpiar_nueva(logout=True)
            v["error"], v["estado"] = "WhatsApp se vinculó, pero no pude ponerlo en su sitio. Tu WhatsApp de antes sigue igual.", "error"
            return
        tel = re.sub(r"\D", "", str(st.get("phone") or v["telefono"] or ""))
        _apuntar(numero=tel[-4:] or None, desde=time.strftime("%Y-%m-%d"), respaldo=b.name if b else None, desconectado=None)
        v["estado"] = "conectado"
        v["parado"] = not arrancado   # vinculado, pero wacli-sync no arrancó: la app lo dice y ofrece «Ponerlo en marcha»
    _cfg["al_cambiar"]()


def _poner_en_su_sitio(nueva):
    """wacli-sync parado solo mientras se cambian las carpetas: la vieja a ~/Respaldos, la nueva a su sitio. Si algo falla, la vieja
    vuelve. Pase lo que pase, wacli-sync se vuelve a encender. → (carpeta de la copia o None si no había almacén, si arrancó bien)."""
    store, b = _cfg["store"], None
    if not _sc("stop"):   # sin parar no se mueve nada: wacli-sync seguiría escribiendo en la carpeta vieja
        raise RuntimeError("no pude parar wacli-sync")
    try:
        if store.exists() and any(store.iterdir()):
            b = _respaldo("antes")
            shutil.move(str(store), str(b))
            os.chmod(b, 0o700)   # lleva la sesión y los mensajes: solo para Fran
        elif store.exists():
            store.rmdir()
        try:
            os.rename(nueva, store)
        except OSError:
            if b and not store.exists():
                shutil.move(str(b), str(store))
            raise
    finally:
        en = _sc("enable")
        arrancado = _sc("restart") and en
    return b, arrancado


def arrancar():
    """«Ponerlo en marcha»: vuelve a activar y arrancar wacli-sync (si se paró o no arrancó tras vincular). → True si arrancó."""
    if not _cfg.get("systemctl"):
        raise RuntimeError("Aquí no se puede arrancar WhatsApp (falta configurar el servicio).")
    with _L:
        if _V.get("estado") == "esperando":
            raise ValueError("Se está vinculando: espera a que termine.")
        if not (_cfg["store"] / "session.db").exists():
            raise ValueError("No hay ningún WhatsApp vinculado: vincúlalo con un código.")
        en = _sc("enable")
        ok = _sc("restart") and en
        if ok and _V.get("parado"):
            _V["parado"] = False
    _cfg["al_cambiar"]()
    return ok


def cancelar():
    global _V
    with _L:
        v = _V
        if v.get("estado") == "esperando" and v.get("autenticado"):
            return False   # ya vinculó: se deja terminar (si no, quedaría un dispositivo vinculado sin usar)
        if v.get("estado") == "esperando":
            v["cancelado"] = True
            _matar(v)
            _limpiar_nueva(logout=True)
        _V = {}
    return True


def desconectar():
    """Para y desactiva wacli-sync, cierra la sesión en WhatsApp y guarda el almacén en ~/Respaldos. → (copia, logout_ok)."""
    global _V
    if not _cfg.get("systemctl"):
        raise RuntimeError("Aquí no se puede desconectar WhatsApp (falta configurar el servicio).")
    if not cancelar():   # justo terminando de vincular: si se desconecta ahora, la sesión nueva se quedaría huérfana en .nuevo
        raise ValueError("Está terminando de guardar la vinculación: espera unos segundos y vuelve a probar.")
    with _L:
        store = _cfg["store"]
        if not _sc("stop"):   # con wacli-sync vivo, el logout falla por el candado y moveríamos sus archivos abiertos: no se toca nada
            raise RuntimeError("No pude parar el repaso de WhatsApp en el PC, así que no he tocado nada. Prueba otra vez en un momento.")
        _sc("disable")   # que no arranque solo al encender el PC y falle sin sesión
        ok = False
        if (store / "session.db").exists():
            try:
                ok = subprocess.run([_cfg["wacli"], "--store", str(store), "auth", "logout"], capture_output=True, timeout=60,
                                    stdin=subprocess.DEVNULL, env=_env()).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
        b = None
        if store.exists() and any(store.iterdir()):
            b = _respaldo("desconectado")
            shutil.move(str(store), str(b))
            os.chmod(b, 0o700)   # lleva la sesión y los mensajes: solo para Fran
        store.mkdir(mode=0o700, parents=True, exist_ok=True)   # vacía: la app lo ve «sin vincular»
        _apuntar(numero=None, desde=None, respaldo=b.name if b else None, desconectado=time.strftime("%Y-%m-%d"))
        _V = {}
    _cfg["al_cambiar"]()
    return b, ok
