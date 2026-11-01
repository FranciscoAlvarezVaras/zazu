#!/usr/bin/env python3
"""`visor`: el visor de registros a pantalla completa en la terminal, como el Explorador de registros de Google.

Lee lo que junta visor.py (la app, Zazu, los invitados y el vigilante) y lo enseña EN VIVO: cada 2 segundos recoge lo nuevo
y lo añade abajo, salvo en pausa (p). Solo biblioteca estándar (curses).

Teclas: ↑ ↓ RePág AvPág Inicio Fin moverse · Enter detalle · e gravedad · o origen · t tiempo · / buscar · g agrupar
        p pausa · x explícamelo (s solución · m mini examen · r arreglado) · Esc quitar filtros · ? ayuda · q salir
Sin terminal (o con --md) imprime el resumen de VISOR.md.
"""
import curses, locale, os, sys, textwrap, time, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import visor as V  # noqa: E402
import explicar as X  # noqa: E402

RANGOS = [("1 hora", 3600), ("6 horas", 6 * 3600), ("24 horas", 86400), ("7 días", 7 * 86400), ("30 días", 30 * 86400)]
GRAVEDADES = [(None, "Todo"), ("aviso", "Avisos y errores"), ("error", "Solo errores")]
ORIGENES = [(None, "Todos")] + list(V.ORIGENES.items())
MAXIMO = 20000   # entradas cargadas a la vez (30 días caben de sobra)
CADA = 2.0       # segundos entre recogidas en vivo
_BARRAS = " ▁▂▃▄▅▆▇█"
AYUDA = """VISOR DE REGISTROS · AYUDA

Un registro (log) es una línea que un programa escribe para contar lo que hace.
Aquí ves los de la app (holazazu.app), Zazu, los asistentes de los invitados y los avisos del vigilante.

  ●  gris      Info: algo normal. No hay que hacer nada.
  ●  amarillo  Aviso: algo raro o un fallo pequeño (una página que no existe, un dato mal escrito).
  ●  rojo      Error: algo ha fallado de verdad. Si se repite mucho, hay que mirarlo.

Teclas
  ↑ ↓  RePág AvPág  Inicio Fin    moverse por la lista
  Enter    abrir el detalle de la línea (el error entero y lo que pasó justo antes y después)
  e        gravedad: todo → avisos y errores → solo errores
  o        origen: todos → la app → Zazu → invitados → vigilante
  t        tiempo: 1 hora → 6 horas → 24 horas → 7 días → 30 días
  /        buscar un texto (Enter vacío para quitarlo)
  g        errores agrupados: los iguales juntos, el que más se repite arriba; Enter para ver solo ese
  p        pausa: deja de añadir líneas para leer tranquilo (vuelve a pulsar para seguir en vivo)
  x        explícamelo: Claude te explica la línea elegida (en el detalle: s solución, m mini examen, r lo he arreglado)
           «Entendido» solo se gana aprobando el mini examen; «arreglado», después de aprobarlo.
  Esc      quitar la búsqueda y el «solo este error»
  q        salir (o volver atrás)

Truco: un Traceback es el rastro que deja Python al fallar. Lee la ÚLTIMA línea (qué falló)
y la de encima que empieza por «File» (dónde). Lo demás es el camino hasta allí.

Pulsa cualquier tecla para volver."""


def plano(t):
    """Una línea sin emojis ni caracteres anchos (descuadran la terminal)."""
    t = str(t).replace("\t", " ").replace("\n", " ⏎ ")
    return "".join(c for c in t if unicodedata.east_asian_width(c) not in "WF" and c not in "️‍")


class Pantalla:
    def __init__(self, scr):
        self.scr = scr
        self.rango, self.grav, self.orig = 2, 0, 0
        self.q, self.firma, self.pausa = "", None, False
        self.vista, self.sel, self.top, self.scroll = "lista", 0, 0, 0
        self.entradas, self.grupos, self.detalle = [], [], []
        self.estado, self.ultima = "", 0.0
        curses.curs_set(0)
        curses.use_default_colors()
        for i, c in enumerate((curses.COLOR_RED, curses.COLOR_YELLOW, 8 if curses.COLORS > 8 else curses.COLOR_WHITE,
                               curses.COLOR_CYAN, curses.COLOR_GREEN), 1):
            curses.init_pair(i, c, -1)
        self.color = {"error": curses.color_pair(1) | curses.A_BOLD, "aviso": curses.color_pair(2), "info": curses.color_pair(3)}
        scr.timeout(500)
        scr.keypad(True)

    # ------------------------------------------------------------ datos
    def cargar(self, mantener=True):
        al_final = not self.entradas or self.sel >= len(self.entradas) - 1
        elegida = self.entradas[self.sel] if self.entradas and mantener and not al_final else None
        desde = time.time() - RANGOS[self.rango][1]
        filtros = dict(origen=ORIGENES[self.orig][0], q=self.q)
        self.entradas = list(reversed(V.leer(desde, gravedad=GRAVEDADES[self.grav][0], firma_=self.firma, n=MAXIMO, **filtros)))
        self.grupos = V.grupos(desde, gravedad=GRAVEDADES[self.grav][0] or "aviso", **filtros)
        if elegida in self.entradas:
            self.sel = self.entradas.index(elegida)
        elif self.vista == "lista":   # en vivo: siempre en la última, como `tail -f`
            self.sel = max(0, len(self.entradas) - 1)

    def recoger(self):
        if self.pausa or self.vista != "lista" or time.time() - self.ultima < CADA:
            return
        self.ultima = time.time()
        try:
            if V.recoger():
                self.cargar()
        except Exception as e:   # un registro raro no tumba el visor
            self.estado = f"No he podido leer lo nuevo: {type(e).__name__}"

    # ------------------------------------------------------------ dibujo
    def poner(self, y, x, texto, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and 0 <= x < w - 1:
            try:
                self.scr.addnstr(y, x, plano(texto), w - 1 - x, attr)
            except curses.error:
                pass

    def cabecera(self):
        h, w = self.scr.getmaxyx()
        partes = [RANGOS[self.rango][0], GRAVEDADES[self.grav][1], ORIGENES[self.orig][1]]
        if self.q:
            partes.append(f"buscar «{self.q}»")
        if self.firma:
            partes.append("solo este error (Esc para quitar)")
        vivo = "‖ PAUSA" if self.pausa else "● EN VIVO"
        self.poner(0, 0, f" Visor de registros · {' · '.join(partes)}".ljust(w), curses.A_REVERSE)
        self.poner(0, max(0, w - len(vivo) - 2), vivo, curses.A_REVERSE | curses.color_pair(2 if self.pausa else 5))
        # el gráfico: una columna por trozo de tiempo; alto = cuántas hubo, color = lo peor que hubo
        ancho = max(10, w - 2)
        desde = time.time() - RANGOS[self.rango][1]
        cubo = RANGOS[self.rango][1] / ancho
        cuentas = [[0, 0] for _ in range(ancho)]   # [total, peor nivel]
        for e in self.entradas:
            i = min(ancho - 1, max(0, int((e["t"] - desde) / cubo)))
            cuentas[i][0] += 1
            cuentas[i][1] = max(cuentas[i][1], V.NIVEL[e["g"]])
        tope = max(c[0] for c in cuentas) or 1
        for i, (n, peor) in enumerate(cuentas):
            if n:
                self.poner(1, 1 + i, _BARRAS[max(1, round(n / tope * 8))], self.color[("info", "aviso", "error")[peor]])
        izq = time.strftime("%H:%M" if RANGOS[self.rango][1] <= 86400 else "%d/%m", time.localtime(desde))
        cuenta = {g: sum(1 for e in self.entradas if e["g"] == g) for g in V.NIVEL}
        resumen = f"{len(self.entradas)} registros · {cuenta['aviso']} avisos · {cuenta['error']} errores"
        self.poner(2, 1, izq, curses.A_DIM)
        self.poner(2, max(len(izq) + 2, (w - len(resumen)) // 2), resumen)
        self.poner(2, w - 7, "ahora", curses.A_DIM)

    def pie(self):
        h, w = self.scr.getmaxyx()
        teclas = {"lista": "Enter detalle  e gravedad  o origen  t tiempo  / buscar  g agrupar  p pausa  x explícamelo  ? ayuda  q salir",
                  "grupos": "Enter ver solo ese error  e gravedad  o origen  t tiempo  g volver a la lista  ? ayuda  q volver",
                  "detalle": "↑ ↓ moverse  x explícamelo  s solución  m mini examen  r lo he arreglado  q volver"}[self.vista]
        self.poner(h - 1, 0, ((f" {self.estado}  ·  " if self.estado else " ") + teclas).ljust(w), curses.A_REVERSE)

    def _hora(self, t):
        return time.strftime("%H:%M:%S" if RANGOS[self.rango][1] <= 86400 else "%d/%m %H:%M", time.localtime(t))

    def _origen(self, e):
        quien = "App" if e["o"] == "app" else V.ORIGENES.get(e["o"], e["o"])
        return (f"{quien}·{e['p']}" if e.get("p") and e["p"] != "zazu" else quien)[:16]

    def _ventana(self, total, alto):
        self.sel = max(0, min(self.sel, total - 1))
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + alto:
            self.top = self.sel - alto + 1

    def lista(self):
        h, w = self.scr.getmaxyx()
        alto = h - 5
        if not self.entradas:
            self.poner(5, 2, "No hay nada con estos filtros. Prueba con más tiempo (t), todas las gravedades (e) o Esc.", curses.A_DIM)
            return
        self._ventana(len(self.entradas), alto)
        for fila, e in enumerate(self.entradas[self.top:self.top + alto]):
            y, attr = 4 + fila, curses.A_REVERSE if self.top + fila == self.sel else 0
            hora = self._hora(e["t"])
            x = len(hora) + 2
            self.poner(y, 0, " " * w, attr)
            self.poner(y, 1, hora, attr | curses.A_DIM)
            self.poner(y, x, "●", attr | self.color[e["g"]])
            self.poner(y, x + 2, self._origen(e).ljust(17), attr | curses.color_pair(4))
            self.poner(y, x + 19, e["x"] + ("  [+detalle]" if e.get("d") else ""), attr | (self.color[e["g"]] if e["g"] != "info" else 0))

    def lista_grupos(self):
        h, w = self.scr.getmaxyx()
        alto = h - 6
        if not self.grupos:
            self.poner(5, 2, "Ningún aviso ni error con estos filtros.", curses.A_DIM)
            return
        self.poner(4, 1, "Veces  ●  Dónde              Qué pasó", curses.A_BOLD)
        self.poner(4, w - 22, "Primera → Última", curses.A_BOLD)
        self._ventana(len(self.grupos), alto)
        for fila, g in enumerate(self.grupos[self.top:self.top + alto]):
            y, attr = 5 + fila, curses.A_REVERSE if self.top + fila == self.sel else 0
            fechas = f"{self._hora(g['primera'])} → {self._hora(g['ultima'])}"
            donde = (V.ORIGENES[g["o"]] + (f" ({', '.join(g['perfiles'])})" if g["perfiles"] else ""))[:18]
            self.poner(y, 0, " " * w, attr)
            self.poner(y, 1, f"{g['n']:>5}", attr | curses.A_BOLD)
            self.poner(y, 8, "●", attr | self.color[g["g"]])
            self.poner(y, 11, donde.ljust(19), attr | curses.color_pair(4))
            self.poner(y, 30, g["x"][: max(10, w - 34 - len(fechas))], attr)
            self.poner(y, w - len(fechas) - 2, fechas, attr | curses.A_DIM)

    def abrir_detalle(self):
        e = self.entradas[self.sel]
        _, w = self.scr.getmaxyx()
        ancho = max(30, w - 6)
        veces = sum(1 for x in self.entradas if x["f"] == e["f"])
        lineas = [("titulo", f"{e['g'].upper()} · {V.ORIGENES[e['o']]}" + (f" · perfil {e['p']}" if e.get("p") else "")),
                  ("dim", time.strftime("%A %d/%m/%Y a las %H:%M:%S", time.localtime(e["t"]))),
                  ("dim", f"Sale {veces} {'vez' if veces == 1 else 'veces'} en la lista ({RANGOS[self.rango][0]}) · firma {e['f']}"), ("", ""),
                  ("seccion", "Qué dice")]
        lineas += [("", l) for l in textwrap.wrap(e["x"], ancho)]
        if e.get("d"):
            lineas += [("", ""), ("seccion", "Detalle completo")]
            partes = e["d"].splitlines()
            for i, l in enumerate(partes):
                importante = l.strip().startswith('File "') or i == len(partes) - 1
                lineas += [("marca" if importante else "", c) for c in (textwrap.wrap(l, ancho, drop_whitespace=False) or [""])]
            lineas.append(("dim", "Lo que va en negrita es lo que importa: «File …» dice dónde y la última línea dice qué falló."))
        # lo que pasó justo antes y después en el mismo sitio (como «entradas cercanas» de Google)
        cerca = sorted((x for x in V.leer(e["t"] - 120, e["t"] + 120, origen=e["o"], n=400) if x != e), key=lambda x: x["t"])
        antes, despues = [x for x in cerca if x["t"] <= e["t"]][-6:], [x for x in cerca if x["t"] > e["t"]][:6]
        if antes or despues:
            lineas += [("", ""), ("seccion", "Justo antes y después (2 minutos, mismo origen)")]
            lineas += [(x["g"], f"  {time.strftime('%H:%M:%S', time.localtime(x['t']))}  {x['x']}") for x in antes]
            lineas.append(("marca", f"→ {time.strftime('%H:%M:%S', time.localtime(e['t']))}  {e['x']}"))
            lineas += [(x["g"], f"  {time.strftime('%H:%M:%S', time.localtime(x['t']))}  {x['x']}") for x in despues]
        self.detalle, self.scroll, self.vista, self.elegida = lineas, 0, "detalle", e

    def profesor(self, modo):
        """Claude explica (o da la solución de) el registro del detalle y se añade debajo. Espera ~20-30 s la primera vez; luego, guardada."""
        self.estado = "Claude está leyendo el error y el código… (unos 20-30 segundos)" if modo == "explicar" else "Claude prepara la solución paso a paso…"
        self.pintar()
        r = X.explicar(self.elegida, modo)
        if not r["ok"]:
            self.estado = {"tope": "Este mes ya se gastó el tope de 15 $ en explicaciones.", "sin_ia": "No hay forma de llamar a Claude desde aquí.",
                           "ocupado": "Claude está con otra explicación; prueba en unos segundos."}.get(r["motivo"], "Claude no ha contestado. Prueba otra vez.")
            return
        _, w = self.scr.getmaxyx()
        ancho, empieza, codigo = max(30, w - 8), len(self.detalle) + 1, False
        self.detalle += [("", ""), ("seccion", "Claude te lo explica" if modo == "explicar" else "La solución (la aplicas tú)")]
        for l in r["texto"].splitlines():
            if l.startswith("```"):
                codigo = not codigo
                continue
            if codigo:
                self.detalle.append(("marca", "    " + l))
            elif l.startswith("#"):
                self.detalle += [("", ""), ("titulo", l.lstrip("# ").upper())]
            else:
                limpio = l.replace("**", "").replace("`", "")
                sangria = "  " if l.lstrip().startswith(("-", "*")) or l.lstrip()[:2].rstrip(".").isdigit() else ""
                self.detalle += [("", c) for c in (textwrap.wrap(limpio, ancho, subsequent_indent=sangria + "  ") or [""])]
        self.scroll = empieza
        coste = "guardada: gratis" if r["guardada"] else f"ha costado {r['coste']:.2f} $"
        self.estado = f"{coste} · nivel {r['nivel']} ({r['nombre']}) · s solución · m mini examen · r arreglado"

    def mini_examen(self):
        """Dos preguntas de Claude; contestas abajo. Con las dos bien: entendido (+1 punto, APRENDIZAJE.md). Nada se apunta sin aprobar."""
        e = self.elegida
        if X.de_firma(e["f"])["entendido"]:
            self.estado = "Este ya lo tienes entendido (examen aprobado)."
            return
        self.estado = "Claude está preparando 2 preguntas…"
        self.pintar()
        ex = X.examen(e)
        if not ex["ok"]:
            self.estado = {"sin_explicacion": "Primero pulsa x para la explicación.", "tope": "Este mes ya se gastó el tope de 15 $."}.get(
                ex["motivo"], "Claude no ha contestado. Prueba otra vez.")
            return
        _, w = self.scr.getmaxyx()
        empieza = len(self.detalle) + 1
        self.detalle += [("", ""), ("seccion", "Mini examen (contesta abajo con tus palabras)")]
        for i, p in enumerate(ex["preguntas"], 1):
            self.detalle += [("titulo", c) for c in textwrap.wrap(f"{i}. {p}", max(30, w - 8))]
        self.scroll = empieza
        resp = []
        for i in range(len(ex["preguntas"])):
            self.pintar()
            r = self.preguntar(f"Respuesta {i + 1}: ", "")
            if r is None:
                self.estado = "Examen cancelado. Pulsa m para volver a intentarlo."
                return
            resp.append(r)
        self.estado = "Claude está corrigiendo…"
        self.pintar()
        n = X.corregir(e, resp)
        if not n["ok"]:
            self.estado = "Escribe al menos una respuesta." if n["motivo"] == "vacio" else "Claude no ha podido corregir. Prueba otra vez."
            return
        for i, nota in enumerate(n["notas"], 1):
            self.detalle += [("info" if nota["bien"] else "error", c) for c in textwrap.wrap(f"{'✓' if nota['bien'] else '✗'} {i}. {nota['comentario']}", max(30, w - 8))]
        self.detalle.append(("marca", n.get("frase") or ""))
        self.estado = (f"¡Aprobado! +1 punto · nivel {n['nivel']}: {n['nombre']} · ya puedes marcar r si lo arreglas" if n["aprobado"]
                       else "Casi: repasa la explicación y pulsa m para intentarlo otra vez.")

    def pintar_detalle(self):
        h, _ = self.scr.getmaxyx()
        alto = h - 5
        self.scroll = max(0, min(self.scroll, len(self.detalle) - alto))
        estilo = {"titulo": curses.A_BOLD, "seccion": curses.A_BOLD | curses.A_UNDERLINE | curses.color_pair(4), "dim": curses.A_DIM,
                  "marca": curses.A_BOLD, "error": self.color["error"], "aviso": self.color["aviso"], "info": curses.A_DIM}
        for fila, (tipo, texto) in enumerate(self.detalle[self.scroll:self.scroll + alto]):
            self.poner(4 + fila, 2, texto, estilo.get(tipo, 0))

    def pintar(self):
        self.scr.erase()
        if self.vista == "ayuda":
            for i, l in enumerate(AYUDA.splitlines()):
                self.poner(1 + i, 2, l, curses.A_BOLD if l in ("VISOR DE REGISTROS · AYUDA", "Teclas") else 0)
        else:
            self.cabecera()
            {"lista": self.lista, "grupos": self.lista_grupos, "detalle": self.pintar_detalle}[self.vista]()
            self.pie()
        self.scr.refresh()

    # ------------------------------------------------------------ teclas
    def preguntar(self, texto, inicial=None):
        """Una línea de texto abajo (acepta acentos). Esc cancela → None."""
        h, w = self.scr.getmaxyx()
        valor = self.q if inicial is None else inicial
        curses.curs_set(1)
        self.scr.timeout(-1)
        try:
            while True:
                self.poner(h - 1, 0, f" {texto}{valor}".ljust(w), curses.A_REVERSE)
                self.scr.move(h - 1, min(w - 2, len(texto) + len(valor) + 1))
                c = self.scr.get_wch()
                if c in ("\n", "\r", curses.KEY_ENTER):
                    return valor.strip()
                if c == "\x1b":
                    return None
                if c in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    valor = valor[:-1]
                elif isinstance(c, str) and c.isprintable():
                    valor += c
        finally:
            curses.curs_set(0)
            self.scr.timeout(500)

    def tecla(self, c):
        h, _ = self.scr.getmaxyx()
        self.estado = ""
        if self.vista == "ayuda":
            self.vista = "lista"
            return True
        if self.vista == "detalle":
            pasos = {curses.KEY_UP: -1, "k": -1, curses.KEY_DOWN: 1, "j": 1, curses.KEY_PPAGE: 6 - h, curses.KEY_NPAGE: h - 6}
            if c in ("q", "\x1b", "\n", "\r", curses.KEY_ENTER, curses.KEY_LEFT):
                self.vista = "lista"
            elif c in pasos:
                self.scroll += pasos[c]
            elif c in ("x", "s"):
                self.profesor("explicar" if c == "x" else "solucion")
            elif c == "m":
                self.mini_examen()
            elif c == "r":
                r = X.aprender(self.elegida, "arreglado")
                self.estado = ("Primero aprueba el mini examen (m): no se arregla lo que no se entiende." if r.get("falta_examen")
                               else f"Apuntado en APRENDIZAJE.md · +2 puntos · nivel {r['nivel']}: {r['nombre']}" if r["nuevo"] else "Ya lo tenías apuntado.")
            return True
        total = len(self.entradas if self.vista == "lista" else self.grupos)
        pasos = {curses.KEY_UP: -1, "k": -1, curses.KEY_DOWN: 1, "j": 1, curses.KEY_PPAGE: 6 - h, curses.KEY_NPAGE: h - 6,
                 curses.KEY_HOME: -10**9, curses.KEY_END: 10**9}
        if c in pasos:
            self.sel = max(0, min(total - 1, self.sel + pasos[c]))
        elif c == "q":
            if self.vista != "grupos":
                return False
            self.vista, self.sel = "lista", len(self.entradas) - 1
        elif c == "?":
            self.vista = "ayuda"
        elif c == "p":
            self.pausa = not self.pausa
            self.estado = "En pausa: no entran líneas nuevas. Pulsa p para seguir en vivo." if self.pausa else "En vivo otra vez."
            self.ultima = 0
        elif c in ("e", "o", "t"):
            if c == "e":
                self.grav = (self.grav + 1) % len(GRAVEDADES)
            elif c == "o":
                self.orig = (self.orig + 1) % len(ORIGENES)
            else:
                self.rango = (self.rango + 1) % len(RANGOS)
            self.cargar(mantener=False)
            if self.vista == "grupos":
                self.sel = 0
        elif c == "/":
            q = self.preguntar("Buscar: ")
            if q is not None:
                self.q = q
                self.cargar(mantener=False)
        elif c == "\x1b":
            self.q, self.firma = "", None
            self.cargar(mantener=False)
        elif c == "g":
            self.vista = "lista" if self.vista == "grupos" else "grupos"
            self.sel, self.top = (len(self.entradas) - 1, 0) if self.vista == "lista" else (0, 0)
        elif c in ("\n", "\r", curses.KEY_ENTER, curses.KEY_RIGHT) and total:
            if self.vista == "grupos":
                self.firma, self.vista = self.grupos[self.sel]["f"], "lista"
                self.cargar(mantener=False)
            else:
                self.abrir_detalle()
        elif c == "x" and total and self.vista == "lista":
            self.abrir_detalle()
            self.profesor("explicar")
        return True

    def bucle(self):
        self.estado = "Recogiendo lo nuevo…"
        self.pintar()
        V.recoger()
        self.ultima = time.time()
        self.cargar()
        self.estado = "Pulsa ? para ver la ayuda."
        while True:
            self.pintar()
            try:
                c = self.scr.get_wch()
            except curses.error:   # medio segundo sin teclas: toca mirar si hay algo nuevo
                self.recoger()
                continue
            if c != curses.KEY_RESIZE and not self.tecla(c):
                return


def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return
    if "--md" in sys.argv or not sys.stdout.isatty():
        V.recoger()
        print(V.resumen_md())
        return
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")   # sin esto, Esc tarda un segundo en responder
    try:
        curses.wrapper(lambda scr: Pantalla(scr).bucle())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
