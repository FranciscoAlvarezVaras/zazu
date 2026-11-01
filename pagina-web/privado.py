"""Filtro de privacidad del Cerebro para lo que escribe el Hub (barra de órdenes y tableros).
Usa el mismo `privacidad.tachar()` que el resto del sistema (~/.hermes/scripts/privacidad.py). Si no está, cae a un filtro
conservador propio (cierra por lo seguro). Un texto es «privado» si el filtro lo cambiaría: el Cerebro nunca guarda claves,
PIN, cuentas bancarias, DNI ni números largos."""
import importlib.util, os, re, sys
from pathlib import Path

_tachar = None


def _cargar():
    global _tachar
    if _tachar is not None:
        return _tachar
    ruta = Path(os.environ.get("HOME") or Path.home()) / ".hermes/scripts/privacidad.py"
    try:
        spec = importlib.util.spec_from_file_location("privacidad_hub", ruta)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _tachar = m.tachar
    except Exception:
        _tachar = _propio
    return _tachar


def _propio(t):
    t = re.sub(r"(?i)\b(contraseña|contrasena|password|clave|pin|cvv|iban|swift|dni|nie|pasaporte|token|api[ _-]?key)\b\s*(es|:|=|-)?\s*\S+", "[tachado]", t or "")
    t = re.sub(r"\b[A-Z]{2}\d{2}[ ]?(?:\d{4}[ ]?){2,6}\d{1,4}\b", "[tachado]", t)      # IBAN
    t = re.sub(r"\b\d{8}[A-Za-z]\b|\b[XYZxyz]\d{7}[A-Za-z]\b", "[tachado]", t)           # DNI / NIE
    return re.sub(r"(?<![\d-])\d(?:[ .\-]?\d){8,}(?![\d-])", "[tachado]", t)                  # número de 9 cifras o más (una fecha ISO tiene 8)


def tachar(t):
    return _cargar()(str(t or "")[:4000])


def es_privado(t):
    t = str(t or "")
    return tachar(t) != t[:4000]
