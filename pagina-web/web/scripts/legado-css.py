#!/usr/bin/python3
"""Repinta con las fichas de Zazu (panel.css) las pantallas «de siempre» que Fran ve dentro del marco nuevo (Agenda, Tareas, Correo, WhatsApp, Carpetas,
Rutinas, Ajustes y el chat) SIN tocar su CSS (que es también el de las invitadas): lee ese CSS, cambia cada color suelto por la ficha que le toca (claro y oscuro
salen solos) y escribe web/src/panel/legado.css, con todas las reglas limitadas a `.pz .pz-legado`, que solo existe en la pantalla de Fran.

  /usr/bin/python3 web/scripts/legado-css.py          (reescribe web/src/panel/legado.css; se puede repetir)
  /usr/bin/python3 web/scripts/legado-css.py -v       (además, lista los colores que no sabe repintar)

Cada color se reparte por LUMINOSIDAD, MATIZ y USO (fondo, texto, borde) entre las fichas: superficies, tintes, texto, acento (turquesa), peligro, correcto…
Si cambias la paleta, solo hay que tocar panel.css; si cambia el CSS de siempre, se vuelve a ejecutar esto."""
import colorsys, re, sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
SRC = WEB / "src"
ARCHIVOS = ["theme.css", "design.css", "hermes.css", "conversacion.css", "shell.css", "carpetas/carpetas.css"]
SALIDA = SRC / "panel/legado.css"
SIN_PREFIJO = re.compile(r"^(html|body|:root|\*|\.page-shell|\.phone|\.desktop-|\.status-|\.boot|\.visually-hidden|\.toast)")
# Las hojas de Carpetas y de WhatsApp (y el aviso de Carpetas) se pintan en <body> (createPortal), fuera de `.pz .pz-legado`: en oscuro
# (que solo elige Fran) también se repintan ellas y lo que llevan dentro (botones, enlaces, notas). En claro se quedan con su paleta de siempre.
PORTALES = (".cp-velo", ".cp-aviso-live", ".wa-hoja-fondo")
EN_PORTAL = re.compile(r"^\.(cp-|wa-hoja|btn-|text-link$|md$|mini-)")
OSCURO = ':root[data-pz-tema="oscuro"] body>'

def prefijos(x):
    pc = primer_compuesto(x)
    out = [".pz .pz-legado " + x]
    if pc in PORTALES: out.append(OSCURO + x)
    elif EN_PORTAL.match(pc): out.append(f"{OSCURO}:is({','.join(PORTALES)}) {x}")
    return out

# ---------- lectura mínima de CSS (llaves, cadenas y paréntesis) ----------
def sin_comentarios(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)

def bloques(s):
    out, i, n = [], 0, len(s)
    while i < n:
        j = s.find("{", i)
        if j < 0:
            break
        pre, depth, k, par, q = s[i:j].strip(), 1, j + 1, 0, None
        while k < n and depth:
            c = s[k]
            if q:
                if c == q: q = None
            elif c in "\"'": q = c
            elif c == "(": par += 1
            elif c == ")": par -= 1
            elif c == "{" and par == 0: depth += 1
            elif c == "}" and par == 0: depth -= 1
            k += 1
        out.append((pre, s[j + 1:k - 1]))
        i = k
    return out

def declaraciones(cuerpo):
    out, cur, par, q = [], "", 0, None
    for c in cuerpo:
        if q:
            cur += c
            if c == q: q = None
            continue
        if c in "\"'": q = c; cur += c; continue
        if c == "(": par += 1
        elif c == ")": par -= 1
        if c == ";" and par == 0:
            out.append(cur); cur = ""
        else:
            cur += c
    out.append(cur)
    res = []
    for d in out:
        if ":" in d:
            p, v = d.split(":", 1)
            res.append((p.strip(), v.strip()))
    return res

def reglas(css, medio=""):
    for pre, cuerpo in bloques(sin_comentarios(css)):
        if pre.startswith(("@media", "@supports")):
            yield from reglas(cuerpo, pre)
        elif pre.startswith("@"):
            continue
        else:
            yield medio, pre, declaraciones(cuerpo)

# ---------- el reparto de colores ----------
RGBA_BLANCO = re.compile(r"rgba\(\s*(?:255\s*,\s*255\s*,\s*255|25[0-5]\s*,\s*25[0-5]\s*,\s*25[0-5])\s*,\s*([0-9.]+)\s*\)")
HEX = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])|#[0-9a-fA-F]{3}(?![0-9a-fA-F])|(?<![\w-])white(?![\w-])")

def hsl(h):
    h = "ffffff" if h.lower() == "white" else h.lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, l, s = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, s, l

def ficha(uso, color):
    """uso: 'fondo' | 'texto' | 'borde' | 'otro'. → expresión CSS o None (se deja como está)."""
    h, s, l = hsl(color)
    rojo = (h < 28 or h > 340) and s > .3
    calido = 20 <= h < 65 and s > .15
    verde = 70 <= h < 170
    if uso == "fondo":
        if l >= .975: return "var(--pz-surface)"
        if l >= .955 and s < .5 and not calido: return "var(--pz-background)"
        if rojo and l >= .88: return "var(--pz-secondary-soft)"
        if rojo: return "var(--pz-secondary)"
        if l >= .88: return "var(--pz-primary-soft)" if (verde and s >= .38) else "var(--pz-surface-subtle)"
        if l >= .78: return "var(--pz-primary-contrast)" if (verde and s >= .5) else "var(--pz-surface-hover)"
        if l >= .5: return "var(--pz-success)" if verde else "var(--pz-secondary)" if calido and h < 45 else "var(--pz-border-strong)"
        if verde and l < .5 and s >= .2 and l >= .36: return "var(--pz-success)"
        return "var(--pz-primary)"                      # los fondos verde oscuro (botones, pestañas elegidas, tarjetas) pasan al turquesa
    if uso == "texto":
        if l >= .78: return "var(--pz-primary-contrast)"
        if rojo: return "var(--pz-danger)"
        if calido: return "var(--pz-text-muted)"
        if verde and s >= .26 and l < .36: return "var(--pz-primary)"
        if verde and s >= .17 and .36 <= l < .5: return "var(--pz-primary)"
        if l < .27: return "var(--pz-text)"
        if l < .40: return "var(--pz-text-muted)"
        return "var(--pz-text-soft)"
    if uso == "borde":
        if rojo or calido and l > .8: return "var(--pz-rojo-borde)"
        if l >= .9: return "var(--pz-separador)"
        if l >= .8: return "var(--pz-border)"
        if l >= .5: return "var(--pz-border-strong)"
        return "var(--pz-primary)"
    return None

def uso_de(prop):
    if prop.startswith("background"): return "fondo"
    if prop == "color": return "texto"
    if prop.startswith(("border", "outline")): return "borde"
    return "otro"

NO_TOCAR = ("box-shadow", "text-shadow", "filter", "-webkit-mask", "mask", "--")

def primer_compuesto(sel):
    """El primer trozo de un selector: «.day-hero .eyebrow» → «.day-hero»."""
    return re.split(r"[\s>+~]", sel.strip(), maxsplit=1)[0].split(":")[0]

def repintar(prop, valor, faltan, sobre_relleno=False):
    if prop.startswith(NO_TOCAR) or "url(" in valor and "gradient" not in valor:
        return None
    uso = uso_de(prop)
    if uso == "otro" and prop in ("fill", "stroke", "caret-color", "accent-color", "text-decoration-color"):
        uso = "texto"
    if uso == "otro":
        return None
    cambiado = [False]
    if uso in ("texto", "fondo", "borde"):
        def blanco(m):
            cambiado[0] = True
            return f"color-mix(in srgb, var(--pz-primary-contrast) {round(float(m.group(1)) * 100)}%, transparent)"
        valor = RGBA_BLANCO.sub(blanco, valor)
        def blanco8(m):
            cambiado[0] = True
            return f"color-mix(in srgb, var(--pz-primary-contrast) {round(int(m.group(1), 16) / 255 * 100)}%, transparent)"
        valor = re.sub(r"#[fF]{6}([0-9a-fA-F]{2})(?![0-9a-fA-F])", blanco8, valor)
    def sub(m):
        if uso == "texto" and sobre_relleno and hsl(m.group(0))[2] >= .45:
            cambiado[0] = True
            return "var(--pz-primary-contrast)"      # texto claro sobre una tarjeta de relleno oscuro: pasa al color de contraste (claro u oscuro según el tema)
        t = ficha(uso, m.group(0))
        if t is None:
            faltan.add((uso, m.group(0).lower())); return m.group(0)
        cambiado[0] = True
        return t
    nuevo = HEX.sub(sub, valor)
    # un fondo que pasa a ficha de relleno (turquesa, peligro…) necesita su texto de contraste: lo pone la regla del texto claro
    return nuevo if cambiado[0] else None

def es_relleno(ds):
    """¿Esta regla pinta un fondo verde oscuro (una tarjeta o botón de relleno)?"""
    for p, v in ds:
        if p.startswith("background"):
            for m in HEX.findall(v):
                if ficha("fondo", m) == "var(--pz-primary)":
                    return True
    return False

def main():
    faltan, salida, n = set(), [], 0
    rellenos = set()
    for a in ARCHIVOS:
        for _, sel, ds in reglas((SRC / a).read_text()):
            if es_relleno(ds):
                for x in re.split(r",(?![^()]*\))", sel):
                    if len(x.split()) == 1:
                        rellenos.add(primer_compuesto(x))
    for a in ARCHIVOS:
        salida.append(f"/* ---- {a} ---- */")
        for medio, sel, ds in reglas((SRC / a).read_text()):
            sels = [x.strip() for x in re.split(r",(?![^()]*\))", sel) if x.strip()]
            sels = [x for x in sels if not SIN_PREFIJO.match(x) and not x.startswith(".pz")]
            if not sels:
                continue
            sobre = any(primer_compuesto(x) in rellenos for x in sels)
            cambios = [(p, v) for p, v in ((p, repintar(p, v, faltan, sobre)) for p, v in ds) if v]
            if not cambios:
                continue
            regla = f"{','.join(y for x in sels for y in prefijos(x))}{{{';'.join(f'{p}:{v}' for p, v in cambios)}}}"
            n += 1
            salida.append(f"{medio}{{{regla}}}" if medio else regla)
    cab = ("/* GENERADO por web/scripts/legado-css.py: NO se edita a mano. Repinta con las fichas de Zazu (panel.css) las pantallas de siempre\n"
           "   (Agenda, Tareas, Correo, WhatsApp, Carpetas, Rutinas, Ajustes y el chat) dentro del marco de Fran. Solo vale dentro de `.pz .pz-legado`:\n"
           "   la pantalla de las invitadas no lo carga ni lo ve. */\n")
    SALIDA.write_text(cab + "\n".join(salida) + "\n")
    print(f"{n} reglas en {SALIDA.relative_to(WEB)} ({SALIDA.stat().st_size // 1024} KB)")
    if "-v" in sys.argv:
        for uso, c in sorted(faltan):
            print("sin ficha:", uso, c)

if __name__ == "__main__":
    main()
