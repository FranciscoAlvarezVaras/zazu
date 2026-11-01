"""Privacidad: todo texto que se guarda o se manda pasa por privacidad.tachar() (el filtro del servidor)."""
import re
import sys

from . import config

_tachar = None


def _cargar():
    global _tachar
    if _tachar is None:
        s = str(config.scripts_dir())
        if s not in sys.path:
            sys.path.insert(0, s)
        try:
            from privacidad import tachar
            _tachar = tachar
        except Exception:   # sin el filtro: cierra por lo seguro (tacha toda cifra larga)
            _tachar = lambda t: re.sub(r"\d[\d .\-]{4,}\d", "[número tachado]", t or "")
    return _tachar


def limpio(s, n=140):
    """Una línea, sin caracteres de control, recortada."""
    s = re.sub(r"[\x00-\x1f\x7f​-‏‪-‮]+", " ", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def tachar(t):
    return _cargar()(str(t or "")[:4000])


def seguro(s, n=140):
    """Limpio + tachado + recorte (en ese orden: recortar al final no deja un trozo de número a medias)."""
    t = limpio(tachar(limpio(s, 4000)), 4000)
    return t[:n].rstrip()
