"""Entrega de avisos al WhatsApp PROPIO de Fran (hermes send, sin IA). Solo en modo vivo. Nunca a otras personas:
el destino es fijo («whatsapp» = su chat contigo mismo)."""
import subprocess

import config


def enviar(texto):
    r = subprocess.run([config.hermes_bin(), "send", "-t", "whatsapp", "-q", texto[:1500]],
                       capture_output=True, text=True, timeout=90)
    if r.returncode:
        raise RuntimeError(f"hermes send falló ({r.returncode})")
    return True
