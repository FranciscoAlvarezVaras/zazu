"""Horas de silencio, ventanas de resumen y límites. Funciones puras sobre (ahora, config, db)."""
from datetime import datetime, timedelta
from . import config


def _hm(txt):
    h, m = txt.split(":")
    return int(h) * 60 + int(m)


def en_silencio(dt, cfg):
    """23:00–07:30 (cruza medianoche)."""
    ini, fin = _hm(cfg["silencio"]["inicio"]), _hm(cfg["silencio"]["fin"])
    m = dt.hour * 60 + dt.minute
    return (m >= ini or m < fin) if ini > fin else (ini <= m < fin)


def fin_silencio(dt, cfg):
    """Cuándo termina el silencio que está en curso (o el más próximo)."""
    fin = _hm(cfg["silencio"]["fin"])
    cand = dt.replace(hour=fin // 60, minute=fin % 60, second=0, microsecond=0)
    return cand if cand > dt else cand + timedelta(days=1)


def ventana_digest(dt, cfg):
    """Clave de la última ventana de resumen ya abierta hoy ('2026-10-08T13:00'), o None si aún no ha empezado ninguna."""
    m = dt.hour * 60 + dt.minute
    pasadas = [h for h in cfg["limites"]["digest_horas"] if _hm(h) <= m]
    return f"{dt:%Y-%m-%d}T{max(pasadas, key=_hm)}" if pasadas else None


def ultima_ventana(dt, cfg):
    """Inicio (datetime) de la última ventana de resumen ya abierta (hoy o ayer)."""
    for dia in (0, 1):
        d = dt - timedelta(days=dia)
        pasadas = [h for h in cfg["limites"]["digest_horas"] if dia == 1 or _hm(h) <= dt.hour * 60 + dt.minute]
        if pasadas:
            h = max(pasadas, key=_hm)
            return d.replace(hour=_hm(h) // 60, minute=_hm(h) % 60, second=0, microsecond=0)
    return None


def cupo(db, cfg, ahora_ts):
    """(libres_3h, libres_dia) para avisos que no son P1 ni programados."""
    lim = cfg["limites"]
    dia0 = int(config.ahora().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    return (lim["no_p1_por_3h"] - db.entregas_desde(ahora_ts - 3 * 3600), lim["no_p1_por_dia"] - db.entregas_desde(dia0))


def en_cooldown(db, cfg, ref, ahora_ts):
    if not ref:
        return False
    return ahora_ts - db.ultima_entrega_ref(ref) < cfg["limites"]["cooldown_chat_min"] * 60
