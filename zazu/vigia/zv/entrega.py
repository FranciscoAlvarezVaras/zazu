"""Entrega de avisos: reglas de calma → notificación en la app (canal «app», por defecto) o WhatsApp propio (`hermes send -t whatsapp`) o, en modo sombra, solo al registro.
La entrega real exige: sin PAUSA + el vigía en 'activo' + (cfg entrega.avisos o el archivo ENTREGA_ACTIVA). Nunca responde a nadie."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

from . import calma, config, registro
from .priv import limpio

EMOJI = {"seguridad": "🔐", "cobro": "💶", "dinero": "💶", "oficial": "🏛️", "entrevista": "🎯", "correo": "✉️", "evento": "⏰",
         "llevar": "🎒", "despues": "↩️", "tarea": "📌", "tarea_vence": "📌", "conflicto": "⚠️", "cumple": "🎂", "fallo": "⚠️",
         "resuelto": "✅", "wa_urgente": "💬", "recordar": "🔔"}


def formato(a):
    em = EMOJI.get(a["tipo"], "🔔")
    partes = [f"{em} {a['titulo']}"]
    if a["detalle"]:
        partes.append(a["detalle"])
    if a["enlace"]:
        partes.append(a["enlace"])
    txt = " · ".join(partes) + f" ({a['codigo']})"
    if a["borrador"]:
        txt += f"\nBorrador {a['codigo']}: «{a['borrador']}» · di «manda {a['codigo']}», «cambia {a['codigo']}: …» o «déjalo {a['codigo']}»."
    return txt


def _enviar_whatsapp(texto):
    r = subprocess.run([config.bin_path("hermes"), "send", "-t", "whatsapp", "-q", texto], capture_output=True, text=True, timeout=90,
                       env=dict(os.environ, PATH=f"{config.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin"))
    return r.returncode == 0, (r.stderr or "")[:120]


_BORRADOR = re.compile(r"\nBorrador [A-Z]*\d+:.*$", re.S)   # «di manda A3…» es para contestar por WhatsApp: en la app no sirve


def _comando_push():
    ext = os.environ.get("ZV_VIGILANTE")                       # gancho para pruebas: un ejecutable que lee el JSON por stdin
    if ext:
        return [ext]
    hub = config.home() / "hermes-hub"
    py = hub / ".venv/bin/python"
    return [str(py if py.exists() else sys.executable), str(hub / "vigilante.py"), "--push-json"]


def _enviar_app(textos):
    """Una notificación por aviso (misma `tag` = sustituye a la anterior); si son más de 4, una sola de resumen. Usa el push del Hub
    (`vigilante.py --push-json`): web push a la web instalada y la cola de la app de Android. Falla si no llegó a ningún aparato."""
    items = [_BORRADOR.sub("", t).strip() for t in textos if not t.endswith(":")]
    items = [t for t in items if t]
    if not items:
        return True, "nada que avisar"
    if len(items) > 4:
        envios = [(f"Zazu · {len(items)} avisos", "\n".join(items), "vigia-resumen")]
    else:
        envios = [("Zazu", t, "vigia-" + hashlib.sha1(t.encode()).hexdigest()[:10]) for t in items]
    total = 0
    for titulo, cuerpo, tag in envios:
        entrada = json.dumps({"titulo": titulo, "cuerpo": cuerpo, "tag": tag, "url": "/?tab=inicio", "urgente": False}, ensure_ascii=False)
        try:
            r = subprocess.run(_comando_push(), input=entrada, capture_output=True, text=True, timeout=90,
                               env=dict(os.environ, PATH=f"{config.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin"))
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, type(e).__name__
        m = re.match(r"\s*(\d+)", r.stdout or "")
        n = int(m.group(1)) if m else 0
        if r.returncode != 0 or n < 1:
            return False, ((r.stderr or "").strip() or f"no llegó a ningún aparato ({n})")[:120]
        total += n
    return True, f"app: {total} notificaciones"


def _enviar_real(textos, cfg):
    """`textos`: lista de avisos ya formateados (puede llevar un encabezado que acaba en «:»)."""
    if config.canal(cfg) == "whatsapp":
        return _enviar_whatsapp("\n".join(textos))
    return _enviar_app(textos)


def _log_sombra(modo, lineas):
    ruta = config.estado_dir() / "sombra.log"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not ruta.exists()
    with open(ruta, "a") as f:
        for l in lineas:
            f.write(f"{config.ahora():%Y-%m-%dT%H:%M} [{modo}] " + limpio(l, 600) + "\n")
    if nuevo:
        os.chmod(ruta, 0o600)


def purgar_log(dias=14):
    ruta = config.estado_dir() / "sombra.log"
    if not ruta.exists():
        return
    corte = (config.ahora() - __import__("datetime").timedelta(days=dias)).strftime("%Y-%m-%d")
    lineas = [l for l in ruta.read_text().splitlines() if l[:10] >= corte]
    config.escribir_atomico(ruta, "\n".join(lineas) + ("\n" if lineas else ""))


def _fuente_reg(a):
    return a["fuente"] if a["fuente"] in registro.FUENTES else "sistema"


def _decidir(a, db, cfg, ahora, ahora_ts, cupo, usados, liberar=False):
    """→ 'enviar' | 'retener' | 'diferir' | 'caducar'. `liberar`: sale en un resumen (no se vuelve a mirar el cupo)."""
    if a["vence"] and a["vence"] < ahora_ts:
        return "caducar"
    if calma.en_silencio(ahora, cfg) and not a["noche_ok"]:
        return "retener"
    if a["prio"] <= 1 or a["programado"] or liberar:
        return "enviar"
    if calma.en_cooldown(db, cfg, a["ref"], ahora_ts):
        return "diferir"
    if cupo[0] - usados <= 0 or cupo[1] - usados <= 0:
        return "diferir"
    return "enviar"


def procesar(db, cfg):
    """Un ciclo de entrega. Devuelve contadores (solo cifras)."""
    ahora = config.ahora()
    ahora_ts = int(ahora.timestamp())
    res = {"enviados": 0, "sombra": 0, "retenidos": 0, "diferidos": 0, "caducados": 0, "resumenes": 0}
    filas = db.c.execute(
        "SELECT * FROM avisos WHERE silencioso=0 AND estado IN ('nuevo','visto') AND entrega IN ('pendiente','retenido','diferido') "
        "AND (aviso_en IS NULL OR aviso_en<=?) AND (pospuesto_hasta IS NULL OR pospuesto_hasta<=?) ORDER BY prio, id", (ahora_ts, ahora_ts)).fetchall()
    cupo = calma.cupo(db, cfg, ahora_ts)
    usados = 0
    lote = {"real": [], "sombra": []}    # filas a entregar ahora
    en_silencio = calma.en_silencio(ahora, cfg)
    ventana = calma.ultima_ventana(ahora, cfg)
    ventana_ts = int(ventana.timestamp()) if ventana else 0
    liberar_noche = cfg["silencio"]["liberar_al_acabar"] and not en_silencio
    for a in filas:
        # lo retenido por silencio sale al acabar; lo diferido por cupo, en la primera ventana de resumen posterior
        liberar = False
        if a["entrega"] == "retenido":
            if not liberar_noche:
                res["retenidos"] += 1
                continue
            liberar = True
        elif a["entrega"] == "diferido":
            if not (a["diferido_en"] and a["diferido_en"] < ventana_ts):
                res["diferidos"] += 1
                continue
            liberar = True
        d = _decidir(a, db, cfg, ahora, ahora_ts, cupo, usados, liberar)
        if d == "caducar":
            db.set(a["id"], entrega="caducado")
            res["caducados"] += 1
            registro.anota(db, "descarto", _fuente_reg(a), f"Caducó sin avisar: {a['titulo']}", "Ya no tenía sentido cuando le tocaba salir", ref=f"aviso:{a['id']}",
                           modo="sombra", clave=f"caduco:{a['id']}", cfg=cfg)
        elif d == "retener":
            db.set(a["id"], entrega="retenido")
            res["retenidos"] += 1
        elif d == "diferir":
            db.set(a["id"], entrega="diferido", diferido_en=ahora_ts)
            res["diferidos"] += 1
        else:
            (lote["real"] if config.aviso_real(cfg, a["fuente"]) else lote["sombra"]).append(a)
            if a["prio"] > 1 and not a["programado"] and not liberar:
                usados += 1
    for modo, avisos in lote.items():
        if not avisos:
            continue
        previos = [a for a in avisos if a["entrega"] in ("retenido", "diferido")]
        textos = []
        if previos:
            textos.append("Mientras no te molestaba:" if any(a["entrega"] == "retenido" for a in previos) else "Resumen de avisos pendientes:")
        textos += [formato(a) for a in avisos]
        canal = config.canal(cfg)
        etiqueta = "WhatsApp" if canal == "whatsapp" else "la app"
        if modo == "real":
            ok, nota = _enviar_real(textos, cfg)
        else:
            _log_sombra("sombra", textos)
            ok, nota = True, "sombra"
        for a in avisos:
            if ok:
                db.set(a["id"], entrega="enviado" if modo == "real" else "sombra", entregado_en=ahora_ts)
                db.registrar_entrega(a["id"], modo, "wa" if canal == "whatsapp" else "app", True, nota)
                if modo == "real":     # en sombra no se registra: el «Habría avisado» ya salió al crear el aviso
                    registro.anota(db, "aviso", _fuente_reg(a), f"Avisé por {etiqueta}: {a['titulo']}", a["detalle"] or None, ref=f"aviso:{a['id']}", modo="vivo",
                                   clave=f"avise:{a['id']}", cfg=cfg)
            else:
                n = a["intentos"] + 1
                db.set(a["id"], intentos=n, error=nota, entrega="pendiente" if n < 3 else "fallido")
                db.registrar_entrega(a["id"], modo, "wa" if canal == "whatsapp" else "app", False, nota)
                if n >= 3:
                    registro.anota(db, "fallo", _fuente_reg(a), f"No pude enviar el aviso por {etiqueta}: {a['titulo']}", nota, ref=f"aviso:{a['id']}", modo="vivo",
                                   clave=f"fallo-envio:{a['id']}", cfg=cfg)
        if ok:
            res["enviados" if modo == "real" else "sombra"] += len(avisos)
            if previos:
                res["resumenes"] += 1
    return res
