#!/usr/bin/python3
"""Genera los iconos de la app a partir del logo de Zazu (web/public/icon.svg: el gato abisinio sobre la baldosa teja).

  /usr/bin/python3 web/scripts/generar-iconos.py [carpeta_de_salida]      (por defecto web/public)

Dibuja el SVG con Chrome sin ventana (fondo transparente) y recorta con Pillow. Escribe, con los nombres de siempre
(los de manifest.json, index.html y sw.js): icon-512.png, icon-192.png, icon-maskable-512.png (la baldosa a sangre y el gato
dentro de la zona segura), apple-touch-icon.png (180, sin transparencia), favicon-32.png, favicon.ico y badge-96.png
(silueta blanca sobre transparente: lo que Android enseña en la barra de notificaciones).
"""
import subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

AQUI = Path(__file__).resolve().parent
PUBLIC = AQUI.parent / "public"
SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else PUBLIC
TEJA = (0x0b, 0x4f, 0x6c, 255)
SILUETA = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><g fill="#fff">
<path d="M132,512 C128,430 170,364 256,364 C342,364 384,430 380,512 Z"/><path d="M214,250 C206,320 188,350 186,372 L326,372 C324,350 306,320 298,250 Z"/>
<g transform="translate(37,-10) scale(0.855)"><path d="M128,78 L158,228 C168,302 214,354 256,354 C298,354 344,302 354,228 L384,78 L300,172 C284,158 228,158 212,172 Z"/></g></g>
<g transform="translate(37,-10) scale(0.855)" fill="#000"><path d="M186,236 C198,218 230,218 242,236 C230,250 198,250 186,236 Z"/><path d="M270,236 C282,218 314,218 326,236 C314,250 282,250 270,236 Z"/><path d="M245,270 L267,270 L256,283 Z"/></g></svg>"""


def dibujar(svg: str, lado: int) -> Image.Image:
    """El SVG a un PNG de lado×lado con fondo transparente, usando Chrome sin ventana."""
    with tempfile.TemporaryDirectory(prefix="iconos-") as d:
        html = Path(d) / "i.html"
        html.write_text(f"<!doctype html><html><body style='margin:0;background:transparent'><div style='width:{lado}px;height:{lado}px'>{svg.replace('<svg ', f'<svg width=\"{lado}\" height=\"{lado}\" ', 1)}</div></body></html>")
        png = Path(d) / "i.png"
        subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={d}/perfil",
                        "--default-background-color=00000000", f"--window-size={lado},{lado}", f"--screenshot={png}", html.as_uri()],
                       check=True, capture_output=True, timeout=60)
        return Image.open(png).convert("RGBA").copy()


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    svg = (PUBLIC / "icon.svg").read_text()
    grande = dibujar(svg, 1024)
    def a(lado): return grande.resize((lado, lado), Image.LANCZOS)
    a(512).save(SALIDA / "icon-512.png"); a(192).save(SALIDA / "icon-192.png"); a(32).save(SALIDA / "favicon-32.png")
    # maskable: la baldosa a sangre (sin esquinas) y el gato dentro del 80 % central (zona segura de Android)
    m = Image.new("RGBA", (512, 512), TEJA); chico = a(410); m.alpha_composite(chico, (51, 51)); m.save(SALIDA / "icon-maskable-512.png")
    # Apple no quiere transparencia: las esquinas, del color de la baldosa
    ap = Image.new("RGBA", (180, 180), TEJA); ap.alpha_composite(a(180)); ap.convert("RGB").save(SALIDA / "apple-touch-icon.png")
    a(64).save(SALIDA / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    # insignia de notificación: solo la silueta (blanco y transparente; los ojos y la nariz, negros = agujeros)
    s = dibujar(SILUETA, 384)
    px = s.load()
    for y in range(s.height):
        for x in range(s.width):
            r, g, b, al = px[x, y]
            px[x, y] = (255, 255, 255, 0) if r < 128 and al > 0 else (255, 255, 255, al)
    s.resize((96, 96), Image.LANCZOS).save(SALIDA / "badge-96.png")
    print("iconos escritos en", SALIDA)


if __name__ == "__main__":
    main()
