#!/usr/bin/env python3
"""Copia la sección «## Propuestas pendientes» de cada salida nueva del «Repaso de la noche» a ~/.hermes/notas/AAAA-MM-DD.md (= ~/Cerebro/20 Diario).
Lo hace el PC, no la IA (la IA solo redacta). Idempotente: recuerda la última salida procesada. Lo lanza zazu-propuestas.timer cada 10 min."""
import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from privacidad import tachar  # noqa: E402  (mismos filtros que el volcado de Zazu: nada de claves, PIN, cuentas ni teléfonos en el Diario)

HOME = Path.home()
SALIDAS = HOME / ".hermes/cron/output/89ff805059f9"     # Repaso de la noche
NOTAS = HOME / ".hermes/notas"
ESTADO = HOME / ".local/state/zazu-propuestas.ultimo"
CABECERA = re.compile(r"^## Propuestas pendientes\s*$", re.M)


def seccion(texto):
    """Desde el ÚLTIMO «## Propuestas pendientes» a inicio de línea (el del prompt va a mitad de línea) hasta el siguiente '## ' o '---'."""
    ms = list(CABECERA.finditer(texto))
    if not ms:
        return None
    resto = texto[ms[-1].end():]
    corte = re.search(r"^(## |---\s*$)", resto, re.M)
    cuerpo = (resto[:corte.start()] if corte else resto).strip()
    cuerpo = "\n".join(l for l in cuerpo.splitlines()
                       if not re.match(r"^\s*Guardad[ao]s? en ", l) and l.strip() != "[SILENT]").strip()   # fuera «Guardado en…» (la IA no guarda) y [SILENT]
    return cuerpo or None


def main():
    ultimo = ESTADO.read_text().strip() if ESTADO.exists() else ""
    nuevos = sorted(p for p in SALIDAS.glob("*.md") if p.name > ultimo) if SALIDAS.exists() else []
    hechos = 0
    for p in nuevos:
        cuerpo = seccion(p.read_text(errors="replace"))
        cuerpo = tachar(cuerpo) if cuerpo else cuerpo
        fecha, hora = p.stem[:10], p.stem[11:16].replace("-", ":")
        if cuerpo:
            NOTAS.mkdir(exist_ok=True)
            nota = NOTAS / f"{fecha}.md"
            previo = nota.read_text() if nota.exists() else ""
            marca = f"<!-- origen: {p.name} -->"
            if marca not in previo:
                if not previo.strip():   # nota nueva: frontmatter de la plantilla Diario (la lista de días la da Diario.base)
                    previo = f"---\ntipo: diario\nfecha: {fecha}\ntags: [diario]\n---\nVolver al [[Inicio]]\n\n## Mis notas\n"
                nota.write_text(previo.rstrip() + "\n\n" + f"## Propuestas pendientes\n{marca}\n_Repaso de las {hora}_\n{cuerpo}\n")
                hechos += 1
                print(f"guardadas en {nota} (de {p.name})")
        else:
            print(f"{p.name}: sin sección de propuestas", file=sys.stderr)
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(p.name)
    if not nuevos:
        print("nada nuevo")


if __name__ == "__main__":
    main()
