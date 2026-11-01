#!/usr/bin/env python3
"""Regenera ~/.hermes/shared/ficha-de-fran.md a partir del USER.md de Zazu, SIN datos sensibles (correos, teléfonos, cuentas,
líneas con claves). Todos los asistentes de un solo oficio leen esa ficha como su USER.md (enlace simbólico). Sin IA."""
import re, datetime
from pathlib import Path
H = Path.home(); SRC = H / ".hermes/memories/USER.md"; DST = H / ".hermes/shared/ficha-de-fran.md"


def limpiar(t):
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[correo]", t)
    t = re.sub(r"(?<!\d)(?:\+?\d[\d .\-]{7,}\d)(?!\d)", lambda m: "[número]" if sum(c.isdigit() for c in m.group(0)) >= 9 else m.group(0), t)   # teléfonos/cuentas, no fechas
    t = re.sub(r"\b[A-Z]{2}\d{2}[ ]?(?:\d{4}[ ]?){4,}\d*\b", "[número]", t)
    t = re.sub(r"(?im)^.*\b(pin|contraseñ|password|clave|token|iban|tarjeta|cuenta bancaria)\b.*$\n?", "", t)
    return re.sub(r"^# USER\.md[^\n]*\n", "", t, count=1).strip()


def main():
    cab = (f"# Ficha de Fran (compartida por todos los asistentes)\n\n"
           "Lo que cualquier asistente de un solo oficio (Viajes, Empleo, Comidas, Dinero, Papeles, Compras, Profe, Analista…) debe saber de Fran\n"
           "para tratarle bien. Es el USER.md de Zazu sin datos sensibles: sin correos, teléfonos, cuentas ni claves (se tachan al generarla).\n"
           f"Fuente: ~/.hermes/memories/USER.md (la que mantiene Zazu). Regenerar: python3 ~/Spirit/zazu/scripts/ficha-de-fran.py. Generada el {datetime.date.today().isoformat()}.\n"
           "Si un asistente aprende algo nuevo de Fran, lo anota en su propia MEMORY.md; esta ficha solo la cambia Fran (o Zazu, en el USER.md original).\n\n")
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(cab + limpiar(SRC.read_text(encoding="utf-8")) + "\n", encoding="utf-8")
    print(f"ficha regenerada: {DST} ({DST.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
