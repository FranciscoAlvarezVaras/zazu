"""Rutas, reloj y configuración (~/.config/zazu-vigia/config.json). Todo se resuelve en cada llamada para que las
pruebas puedan cambiar HOME / ZV_* sin recargar módulos."""
import copy
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
VERSION_CONFIG = 1


def home():
    return Path(os.environ.get("HOME") or Path.home())


def estado_dir():
    return Path(os.environ.get("ZV_ESTADO") or home() / ".local/state/zazu-vigia")


def conf_dir():
    return Path(os.environ.get("ZV_CONFIG") or home() / ".config/zazu-vigia")


def scripts_dir():
    return Path(os.environ.get("ZV_SCRIPTS") or home() / ".hermes/scripts")


def bin_path(nombre):
    """Binario externo: ZV_<NOMBRE> si existe (pruebas), si no ~/.local/bin/<nombre>."""
    v = os.environ.get("ZV_" + nombre.upper())
    return v or str(home() / ".local/bin" / nombre)


def ahora():
    v = os.environ.get("ZV_AHORA")
    if v:
        d = datetime.fromisoformat(v)
        return d if d.tzinfo else d.replace(tzinfo=TZ)
    return datetime.now(TZ)


def f_pausa():
    return conf_dir() / "PAUSA"


def f_entrega():
    return conf_dir() / "ENTREGA_ACTIVA"


def pausado():
    return f_pausa().exists()


def entrega_global():
    """Interruptor global de entrega real. Sin el archivo (o ZV_ENTREGA=1) todo va a la sombra."""
    return f_entrega().exists() or os.environ.get("ZV_ENTREGA") == "1"


DEFECTO = {
    "_ayuda": "Config del vigía de Zazu. 'modo' de cada vigía: sombra (por defecto) o activo. Aunque un vigía esté en "
              "'activo', NADA se entrega ni se escribe en Google mientras no exista el archivo ENTREGA_ACTIVA en esta "
              "carpeta (zv sombra off --si). El archivo PAUSA para todo el vigía en el siguiente ciclo.",
    "version": VERSION_CONFIG,
    "modo": {"wa": "sombra", "correo": "sombra", "agenda": "sombra"},
    "silencio": {"inicio": "23:00", "fin": "07:30", "liberar_al_acabar": True},
    "limites": {"no_p1_por_3h": 4, "no_p1_por_dia": 10, "cooldown_chat_min": 60,
                "digest_horas": ["09:00", "13:00", "18:00"]},
    "wa": {
        "mis_ids": ["10000000000099@lid", "34600000099@s.whatsapp.net"],
        "mis_numeros": ["10000000000099", "34600000099"],
        "mis_nombres": ["fran", "francisco"],
        "vip": [], "ignorar_chats": [], "silenciados": [], "grupos_ok": [],
        "asentar_min": 10, "caducidad_h": 24, "ventana_mensajes": 12, "max_chars_contexto": 1500,
        "max_msgs_por_ciclo": 500, "lookback_inicial_h": 0,
        "max_items_por_dia": 3, "cuenta_destino": "varas", "lista_tareas": "@default",   # poco y bueno (antes 8): mejor perder una que molestar con cinco
        "confianza_min": 0.8,        # el modelo debe estar MUY seguro (antes 0.5→0.7): solo peticiones claras y dirigidas a Fran, no charla
        "gemela_evento": False,      # un evento apuntado desde WhatsApp NO crea además una tarea con el mismo título (duplicaba la agenda)
        "alerta_vip": {"habilitado": False,
                       "palabras": "urgente|llámame|llamame|ayuda|dónde estás|donde estas|accidente|hospital"},
    },
    "correo": {"cuentas": {"varas": None, "alvarez": "cuenta.secundaria@example.com"},
               "query": "in:inbox newer_than:2d -category:promotions -category:social", "max": 50,
               "max_cuerpos_ciclo": 5},
    "agenda": {"ventana_dias": 62, "aviso_con_lugar_min": 45, "aviso_sin_lugar_min": 10,
               "listas_excluidas": ["Notas del asistente"], "conflicto_margen_min": 30,
               "auditoria_hora": "09:00",
               # Las tareas gemelas de eventos se quitaron (Fran ya no las quiere, 2026-10-21): el vigía NUNCA las propone.
               "auditoria_activa": False,        # auditar lo que YA existe en Google inundaba la bandeja (52 avisos): apagada por defecto
               "auditoria_gravedad": "ERROR"},   # si se activa, solo salen los hallazgos accionables (ERROR; admite «ERROR,REVISAR»)
    "llm": {"habilitado": True, "modelo": "claude-haiku-4-5-20251001", "proveedor": "anthropic",
            "max_por_ciclo": 3, "max_por_dia": 30, "timeout_s": 90,
            "python": "~/.hermes/tools/python-3.14.7+20260901-linux-x64/bin/python3"},
    "entrega": {"_ayuda": "Cómo y si salen los avisos. canal: 'app' (notificación en la app del móvil y en la web instalada; es lo que hay desde que WhatsApp "
                "está apagado, 2026-10-21) o 'whatsapp' (`hermes send`, ya no disponible mientras WhatsApp siga apagado). avisos: true = los avisos de los vigías en "
                "'activo' salen de verdad AUNQUE no exista ENTREGA_ACTIVA; ese archivo sigue siendo lo único que deja escribir en Google. Se cambia con: zv avisos on|off.",
                "canal": "app", "avisos": False},
    "retencion": {"avisos_dias": 14, "borradores_h": 48, "registro_dias": 30,
                  "cerrar_informativos_dias": 3},   # avisos solo informativos (auditoría, gemelas, items creados…) que nadie atendió en 3 días se cierran solos; 0 = nunca
    "flujos": {
        "_ayuda": "Flujos sin IA («si llega un correo con plazo → tarea + evento tentativo + aviso»). Cada flujo: 'modo' sombra "
                  "(por defecto: solo anota lo que haría) o activo, y 'pausado'. Aunque un flujo esté 'activo', NADA se escribe en "
                  "Google mientras no se cumpla además el interruptor general: sin PAUSA, con ENTREGA_ACTIVA y el vigía de su fuente "
                  "en 'activo'. Se cambian con: zv flujo <id> modo sombra|activo [--confirmo] · zv flujo <id> pausa|reanuda.",
        "cuenta_destino": "varas", "lista_tareas": "@default", "evento_duracion_min": 60,
        "max_escrituras_dia": 8, "max_cuerpos_ciclo": 6,
        "correo-plazo": {"modo": "sombra", "pausado": False},
        "correo-pago": {"modo": "sombra", "pausado": False},
        "correo-oficial": {"modo": "sombra", "pausado": False},
        "viaje-reserva": {"modo": "sombra", "pausado": False},
        "entrevista": {"modo": "sombra", "pausado": False},
        "wa-peticion": {"modo": "sombra", "pausado": False},
    },
    "gastos": {
        "_ayuda": "Gastos y suscripciones (se leen SOLO del correo; la agenda sirve de pista de renovaciones). 'categorias': lista cerrada. 'tope_mensual': "
                  "{activo, importe en euros} apagado por defecto; 'topes_categoria': {categoria: euros}. 'cambio': {USD: 0.92} para sumar otras monedas al total en euros "
                  "(si no, se enseñan aparte, sin convertir). 'comercios': {clave: {nombre, categoria, alias}} para tus propios comercios. Se cambia a mano en este archivo.",
        "habilitado": True,
        "categorias": ["suscripciones", "vivienda", "coche", "comida", "salud", "ocio", "trámites", "otros"],
        "tope_mensual": {"activo": False, "importe": 0},
        "topes_categoria": {},
        "cambio": {},
        "comercios": {},
        "ventana_inicial_dias": 90,
        "query": "(subject:(recibo OR factura OR receipt OR invoice OR cargo OR cobro OR renovación OR renovacion OR renewal OR suscripción OR suscripcion OR subscription OR "
                 "cuota OR pago OR payment OR pedido OR order OR compra OR comprar OR purchase OR billing OR statement OR reembolso OR refund OR charged OR reserva OR booking OR "
                 "devolución OR devolucion OR confirmación OR confirmation) OR from:(billing OR invoice OR invoices OR receipt OR receipts OR facturacion OR payments OR stripe OR paddle))",
        "excluir": "-category:promotions -category:social",
        "max_por_pagina": 20, "max_paginas": 8, "max_segundos_busqueda": 60, "pausa_s": 2, "pausa_limite_s": 10,
        "max_cuerpos_ciclo": 12, "max_cuerpos_inicial": 20, "max_segundos_ciclo": 70,
        "max_llm_ciclo": 1,
        "aviso_subida_pct": 10,
        "importe_dudoso": 5000,
        "agenda": {"leer": True, "cada_h": 6, "dias": 45},
        "retencion_dias": 800,
    },
    "suscripciones": {
        "_ayuda": "'cancelar': suscripciones que Fran quiere cancelar (nombre del comercio, o {comercio, desde: AAAA-MM-DD}). Si siguen cobrando después de esa fecha "
                  "(sin 'desde': desde el día en que el vigía las vio en esta lista) avisa.",
        "cancelar": ["genspark", "twitch", "kick"],
        "siguen": [],            # confirmadas por Fran como activas (no se ocultan aunque solo salgan en la agenda)
        "canceladas": [],        # ya canceladas por Fran: {comercio, desde}. No salen en la lista de suscripciones; un cobro posterior a «desde» sigue avisando
    },
    "fallos": {"umbral": 3},
}


def _mezcla(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mezcla(base[k], v)
        else:
            base[k] = v
    return base


def _sanear(valor, defecto):
    """Un valor de la config con el tipo que toca; si Fran escribió otra cosa (un texto donde va un número, un número donde va una lista…), se usa el valor por defecto.
    Recorre los diccionarios por dentro. Un `gastos` roto no debe tumbar el ciclo."""
    if isinstance(defecto, dict):
        if not isinstance(valor, dict):
            return copy.deepcopy(defecto)
        return {**valor, **{k: _sanear(valor.get(k), v) for k, v in defecto.items() if not k.startswith("_") and k in valor}}
    if isinstance(defecto, bool):
        ok = isinstance(valor, bool)
    elif isinstance(defecto, (int, float)):
        ok = isinstance(valor, (int, float)) and not isinstance(valor, bool)
    else:
        ok = isinstance(valor, type(defecto))
    return valor if ok else copy.deepcopy(defecto)


def _sanear_gastos(cfg):
    g = cfg.get("gastos")
    if isinstance(g, dict) and isinstance(g.get("tope_mensual"), (int, float)) and not isinstance(g.get("tope_mensual"), bool):
        g["tope_mensual"] = {"activo": g["tope_mensual"] > 0, "importe": g["tope_mensual"]}      # «tope_mensual: 300» = un tope de 300 € activo
    cfg["gastos"] = _sanear(g, DEFECTO["gastos"])
    s = cfg.get("suscripciones")
    cfg["suscripciones"] = _sanear(s if isinstance(s, dict) else None, DEFECTO["suscripciones"])
    if not isinstance(cfg["suscripciones"].get("cancelar"), list):
        cfg["suscripciones"]["cancelar"] = list(DEFECTO["suscripciones"]["cancelar"])
    if not isinstance(cfg["suscripciones"].get("canceladas"), list):
        cfg["suscripciones"]["canceladas"] = []


def escribir_atomico(ruta, texto, modo=0o600):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name + ".")
    with os.fdopen(fd, "w") as f:
        f.write(texto)
    os.chmod(tmp, modo)
    os.replace(tmp, ruta)


def cargar(crear=True):
    """Config con valores por defecto para lo que falte. Si el archivo no existe, lo crea con los valores seguros.
    Un JSON roto no tumba el vigía: se usan los valores por defecto y se avisa por stderr."""
    ruta = conf_dir() / "config.json"
    cfg = copy.deepcopy(DEFECTO)
    if ruta.exists():
        try:
            _mezcla(cfg, json.loads(ruta.read_text()))
        except (OSError, ValueError) as e:
            sys.stderr.write(f"zv: config.json ilegible ({type(e).__name__}); uso los valores por defecto\n")
    elif crear:
        try:
            conf_dir().mkdir(parents=True, exist_ok=True)
            os.chmod(conf_dir(), 0o700)
            escribir_atomico(ruta, json.dumps(DEFECTO, ensure_ascii=False, indent=2) + "\n")
        except OSError:
            pass
    _sanear_gastos(cfg)
    return cfg


def actualizar(clave, valor):
    """Cambia SOLO una clave (ruta con puntos: 'flujos.correo-plazo.modo') en el config.json de Fran, sin tocar el resto
    ni añadir los valores por defecto. Si el archivo no existe, lo crea con esa única clave."""
    ruta = conf_dir() / "config.json"
    try:
        datos = json.loads(ruta.read_text()) if ruta.exists() else {}
    except (OSError, ValueError):
        raise OSError("config.json ilegible: no lo toco")
    d = datos
    *ks, ult = clave.split(".")
    for k in ks:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    d[ult] = valor
    escribir_atomico(ruta, json.dumps(datos, ensure_ascii=False, indent=2) + "\n")


def guardar_cfg(cfg):
    escribir_atomico(conf_dir() / "config.json", json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")


def aviso_real(cfg, fuente):
    """¿Sale de verdad el AVISO de esta fuente? Sin PAUSA, con el vigía en 'activo' y con el interruptor de avisos (cfg entrega.avisos) o el global.
    Escribir en Google sigue dependiendo SOLO de modo_real (ENTREGA_ACTIVA): activar los avisos no deja al vigía tocar tus tareas ni tu calendario."""
    return (not pausado()) and (entrega_global() or bool((cfg.get("entrega") or {}).get("avisos"))) and (cfg.get("modo") or {}).get(fuente) == "activo"


def canal(cfg):
    c = str((cfg.get("entrega") or {}).get("canal") or "app")
    return c if c in ("app", "whatsapp") else "app"


def modo_real(cfg, fuente):
    """True solo si: sin PAUSA, interruptor global puesto y el vigía en 'activo'."""
    return (not pausado()) and entrega_global() and (cfg.get("modo") or {}).get(fuente) == "activo"
