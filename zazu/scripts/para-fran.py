#!/usr/bin/env python3
"""«Déjale un mensaje a Fran»: lo que un asistente no puede o no debe hacer solo, lo deja en la bandeja de avisos de la app
(pestaña Zazu › Avisos, con botones Hecho / Luego / Descartar) y manda una notificación push. SIN IA.
Uso: para-fran.py "Título corto" ["Detalle, qué hace falta de Fran"] [--de viajes] [--enlace URL] [--urgente]
Idempotente por título+día (el mismo aviso no se repite). Nunca incluyas claves ni números de cuenta en el texto."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path

H = Path.home()
sys.path.insert(0, str(H / ".hermes/scripts/zazu-vigia"))
sys.path.insert(0, str(H / ".hermes/scripts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("titulo"); ap.add_argument("detalle", nargs="?", default="")
    _hh = Path(os.environ.get("HERMES_HOME", "")).name
    ap.add_argument("--de", default=os.environ.get("ZAZU_ASISTENTE") or ("zazu" if not _hh or _hh.startswith(".") else _hh))
    ap.add_argument("--enlace", default=""); ap.add_argument("--urgente", action="store_true")
    a = ap.parse_args()
    try:
        from privacidad import tachar
    except Exception:
        tachar = lambda t: t
    titulo = tachar(a.titulo.strip())[:120]
    detalle = tachar(a.detalle.strip())[:900]
    from zv import db as zdb
    d = zdb.DB()
    clave = "para_fran:" + hashlib.sha1(f"{a.de}|{titulo}|{d.hoy()}".encode()).hexdigest()[:16]
    id_, nuevo = d.alta(clave, "agente", "para_fran", f"{a.de.capitalize()}: {titulo}", prio=1 if a.urgente else 2,
                        detalle=detalle, enlace=a.enlace, chat=a.de)
    d.close()
    if not nuevo:
        print(f"ya estaba en la bandeja (aviso {id_})"); return
    print(f"aviso {id_} en la bandeja de Fran (app › Zazu › Avisos)")
    vig = H / "hermes-hub/vigilante.py"; py = H / "hermes-hub/.venv/bin/python"
    if vig.exists():
        cuerpo = json.dumps({"titulo": f"{a.de.capitalize()} necesita de ti", "cuerpo": titulo, "url": "/?tab=zazu", "tag": f"para-fran-{id_}", "urgente": a.urgente})
        try:
            subprocess.run([str(py if py.exists() else "python3"), str(vig), "--push-json"], input=cuerpo, text=True, timeout=60, capture_output=True)
        except Exception as e:
            print(f"(sin push: {type(e).__name__})")


if __name__ == "__main__":
    main()
