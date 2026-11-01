#!/usr/bin/env python3
"""systemctl FALSO para «Vincular mi WhatsApp» de Fran (whatsapp_fran.py): nunca toca un servicio de verdad.
Anota cada llamada en $HOME/systemctl.log (HOME es la casa falsa bajo /tmp) y sale 0
(o 1 si la orden está en FAKE_SC_FALLA, p. ej. «stop» o «enable,restart»)."""
import json, os, sys, time
from pathlib import Path

home = Path(os.environ.get("HOME", ""))
if not str(home.resolve()).startswith("/tmp/"):
    sys.exit("systemctl falso: solo en una casa falsa bajo /tmp")
with open(home / "systemctl.log", "a") as f:
    f.write(json.dumps({"t": time.time(), "args": sys.argv[1:]}) + "\n")
if sys.argv[1:] and set(sys.argv[1:]) & set(filter(None, os.environ.get("FAKE_SC_FALLA", "").split(","))):
    sys.exit(1)
