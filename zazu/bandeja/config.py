"""Rutas, interruptores y reglas de la bandeja de Tareas/Calendar. Todo se lee en el momento (los tests cambian el entorno).

Interruptores (ficheros en ~/.config/zazu-bandeja/):
  PAUSA  si existe, el ciclo no hace nada (también vale ~/.config/zazu-vigia/PAUSA, el de los vigías)
  MODO   solo si contiene exactamente «vivo» se escribe de verdad. Si falta o dice otra cosa: SOMBRA (no escribe nada).
"""
import json, os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
AQUI = Path(__file__).resolve().parent
SCRIPTS = Path.home() / ".hermes/scripts"    # privacidad.py, md.py (ruta fija: esta carpeta ya no cuelga de scripts/)

REGLAS_BASE = {
    "listas_excluidas": ["Notas del asistente"],          # inventario de deudas: no se toca
    "cuentas": {"varas": None, "alvarez": "cuenta.secundaria@example.com"},
    "silencio": ["23:00", "07:30"],                       # solo avisos P1 dentro
    "ventana_dias": 62,
    "tope_gemelas_ciclo": 5, "tope_gemelas_dia": 20,
    "tope_investigar_dia": 3, "tope_aplicar_dia": 6, "tope_avisos_dia": 12,
    "gemela_retro": False,                                # False: sin gemela solo a los eventos creados desde que se activó
    "salida_por_ubicacion": True,                         # aviso de salida si el evento tiene lugar (ver docs: puede solaparse con el vigía de agenda)
    "modelo": "claude-haiku-4-5-20251001",
    "alcance": None,                                      # {"contiene": "TEXTO"}: solo tareas/eventos cuyo título lo contenga (pruebas y despliegue prudente)
}


def home():
    return Path(os.environ.get("ZB_HOME") or Path.home())


def estado_dir():
    return Path(os.environ.get("ZB_ESTADO") or home() / ".local/state/zazu-bandeja")


def config_dir():
    return Path(os.environ.get("ZB_CONFIG") or home() / ".config/zazu-bandeja")


def vault():
    return Path(os.environ.get("ZB_VAULT") or "/home/server/Cerebro")


def _bin(nombre):
    p = home() / ".local/bin" / nombre
    return str(p) if p.exists() else nombre


def gog_bin():
    return os.environ.get("ZB_GOG") or _bin("gog")


def hermes_bin():
    return os.environ.get("ZB_HERMES") or _bin("hermes")


def ahora():
    v = os.environ.get("ZB_AHORA")
    if not v:
        return datetime.now(TZ)
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=TZ)


def modo():
    f = config_dir() / "MODO"
    try:
        return "vivo" if f.read_text().strip() == "vivo" else "sombra"
    except OSError:
        return "sombra"


def pausado():
    return (config_dir() / "PAUSA").exists() or (home() / ".config/zazu-vigia/PAUSA").exists()


def reglas():
    r = json.loads(json.dumps(REGLAS_BASE))
    try:
        r.update(json.loads((config_dir() / "reglas.json").read_text()))
    except (OSError, ValueError):
        pass
    return r


def asegurar_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p
