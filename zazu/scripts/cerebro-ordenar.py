#!/usr/bin/env python3
"""Ordenador del Cerebro: pone en su sitio lo que se ha desordenado en el vault de Obsidian de Fran y escribe
cada día «00 Inicio/Informe del Cerebro.md», siempre con la misma estructura. Sin IA.

Qué ordena (solo lo seguro). NUNCA borra nada y nunca sobrescribe: si el destino existe, añade « (2)».
  a) Archivos sueltos en la raíz: las notas (.md, .canvas, .base) a 10 Bandeja; el resto a 40 Compartido/Guardado.
  b) Carpetas que no son del plan en la raíz: las de la skill llm-wiki (entities, concepts, comparisons, queries, raw,
     _archive; también dentro de 90 Sistema) reparten su contenido según 90 Sistema/SCHEMA.md; las demás van enteras
     a 10 Bandeja/<nombre>; las vacías (p. ej. Compartido, Diario, Servidor o Inbox que reaparecen) se quitan (rmdir).
  c) Notas de 00 Inicio, 10 Bandeja, 20 Diario o 30 Notas cuyo «tipo» es de otra carpeta: a la de su tipo (TABLA, que es
     la «Tabla tipo → carpeta» de 90 Sistema/SCHEMA.md). Las de tipo nota o sin tipo de 00 Inicio y de 20 Diario (sin
     nombre de fecha) van a la Bandeja; en la Bandeja se quedan (las ordena Zazu con Fran el domingo); en 30 Notas no se
     mueven (tipo nota: aviso; sin tipo: «Notas sin tipo» del Informe). Los tipos de páginas fijas (FIJOS: guia,
     informe, indice, sistema, zazu, conversacion, informe-zazu) son válidos pero no se mueven: si están fuera de su
     carpeta, solo se avisa. Una nota «AAAA-MM-DD.md» de 20 Diario con otro tipo tampoco se mueve: se avisa.
     En 00 Inicio no toca Inicio.md, Cómo usar el Cerebro.md, el Informe ni Bases de datos/.
  d) Notas de 30 Notas sin «tipo»: se les pone el de su carpeta y «creado»; días «AAAA-MM-DD.md» de 20 Diario sin tipo
     o sin fecha: «tipo: diario» y «fecha» (sin tocar el texto).
  e) Notas vacías y lienzos vacíos: a 90 Sistema/Archivo/<ruta original>. Una «Sin título» que solo tiene propiedades
     cuenta como vacía si todas, salvo tipo y creado, están en blanco; si tiene alguna rellena, se queda y el Informe
     pide renombrarla.
  f) Imágenes y PDF sueltos en 10 Bandeja, 20 Diario o 30 Notas: a 40 Compartido/Adjuntos, solo si su nombre es único.
Los accesos directos (symlinks) nunca se mueven, ni se leen, ni se reescriben, ni se siguen: salen en el Informe.
Un nombre está ocupado si en la carpeta de destino hay otro igual sin contar mayúsculas ni NFC/NFD (el móvil Android y
Windows no los distinguen): entonces « (2)». Las notas se leen y se reescriben como Obsidian: respeta \\r\\n y el BOM.
Si mueve algo, arregla los enlaces con ruta (completa [[30 Notas/Ideas/X]], parcial [[Ideas/X]] o relativa [[../X]]) de la
raíz, 00 Inicio, 10 Bandeja, 20 Diario y 30 Notas que ya no llevan adonde llevaban; si la nota se cambió hace menos de
10 min, no la reescribe y el Informe dice qué cambiar. No toca 40 Compartido (solo recibe), 50 Zazu, 60 Servidor,
90 Sistema (Archivo y Fuentes solo reciben), .obsidian ni Syncthing. Lo de 00 Inicio que no se mueve y no es una página
fija (archivos que no son notas, notas dentro de Bases de datos) sale en el Informe.
El Informe nunca copia tal cual texto sacado de las notas: limpio() lo deja en una línea, sin [[ ]] ni marcas, máx. 60.
Si movió o cambió algo, añade una línea a 90 Sistema/log.md.
Lo lanza cerebro-ordenar.timer a las 05:15.
Uso: cerebro-ordenar.py [--simular] [--vault RUTA]
  --simular  no cambia nada: dice lo que haría y saca el informe por pantalla. No encadena pasos: lo que movería
             un paso no lo vuelven a mirar los siguientes."""
import argparse, contextlib, fcntl, json, os, posixpath, re, stat, sys, tempfile, time, unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:          # sin PyYAML: lector mínimo de «clave: valor»
    yaml = None

VAULT = Path("/home/server/Cerebro")
ESTADO = Path.home() / ".local/state/cerebro-ordenar.json"
INFORME, LOG = "00 Inicio/Informe del Cerebro.md", "90 Sistema/log.md"
INICIO, BANDEJA, DIARIO, NOTAS, COMPARTIDO = "00 Inicio", "10 Bandeja", "20 Diario", "30 Notas", "40 Compartido"
ADJUNTOS, GUARDADO = "40 Compartido/Adjuntos", "40 Compartido/Guardado"
SISTEMA, ARCHIVO, FUENTES, ZAZU, SERVIDOR = "90 Sistema", "90 Sistema/Archivo", "90 Sistema/Fuentes", "50 Zazu", "60 Servidor"
FIJAS = {"00 Inicio/Inicio.md", "00 Inicio/Cómo usar el Cerebro.md", INFORME}   # páginas de 00 Inicio que nunca se tocan
BASES = "00 Inicio/Bases de datos"
RAIZ_OK = {INICIO, BANDEJA, DIARIO, NOTAS, COMPARTIDO, ZAZU, SERVIDOR, SISTEMA,
           ".obsidian", ".stfolder", ".stversions", ".trash"}
SUBCARPETAS = {"Ideas": "idea", "Proyectos": "proyecto", "Candidaturas": "candidatura",
               "Personas y empresas": None, "Temas": "tema", "Lecturas": "lectura"}   # None: persona o empresa, no se adivina
# La «Tabla tipo → carpeta» de 90 Sistema/SCHEMA.md, igual. Si cambia una, cambia la otra.
TABLA = {"nota": BANDEJA, "idea": "30 Notas/Ideas", "proyecto": "30 Notas/Proyectos", "candidatura": "30 Notas/Candidaturas",
         "persona": "30 Notas/Personas y empresas", "empresa": "30 Notas/Personas y empresas",
         "tema": "30 Notas/Temas", "respuesta": "30 Notas/Temas", "lectura": "30 Notas/Lecturas", "diario": DIARIO,
         "guia": INICIO, "informe": INICIO, "indice": SISTEMA, "sistema": SISTEMA,
         "zazu": ZAZU, "conversacion": "50 Zazu/Conversaciones", "informe-zazu": "50 Zazu/Informes"}
FIJOS = {"guia", "informe", "indice", "sistema", "zazu", "conversacion", "informe-zazu"}   # válidos, pero no se mueven
CARPETA_DE = {t: c for t, c in TABLA.items() if t not in FIJOS and t != "nota"}
LLM_TIPO = {"concept": "tema", "comparison": "respuesta", "query": "respuesta", "summary": "lectura", "entity": None}
LLM_CARPETA = {"concept": "30 Notas/Temas", "comparison": "30 Notas/Temas", "query": "30 Notas/Temas",
               "summary": "30 Notas/Lecturas", "entity": "30 Notas/Personas y empresas"}
LLM_DIRS = {"entities": "30 Notas/Personas y empresas", "concepts": "30 Notas/Temas", "comparisons": "30 Notas/Temas",
            "queries": "30 Notas/Temas", "raw": FUENTES, "_archive": ARCHIVO}
ADJ_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".heic", ".heif", ".avif", ".tif", ".tiff", ".pdf"}
DOCS = {".md", ".canvas", ".base"}                          # documentos de Obsidian
FINAL_CANDIDATURA = {"oferta", "rechazada", "descartada"}
CLAVE = ["00 Inicio/Inicio.md", "00 Inicio/Cómo usar el Cerebro.md", "90 Sistema/AGENTS.md",
         "90 Sistema/SCHEMA.md", "90 Sistema/index.md", LOG]
RECIENTE = 600               # lo cambiado hace menos de 10 min no se toca (alguien lo está escribiendo)
TOPE = 40                    # máximo de líneas por lista en el informe
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
CONSEJOS = [   # uno por día de la semana (lunes = 0)
    "Empieza la semana en [[Inicio]]: «Lo que tienes entre manos» te dice qué proyectos siguen abiertos y cuál es su siguiente paso.",
    "Si no sabes dónde va algo, apúntalo en la Bandeja (Ctrl+N en Obsidian, o «apunta en mis notas…» a Zazu). Ordenar es cosa del domingo, no de ahora.",
    "Una cosa, una nota. Si una nota habla de dos asuntos, pártela en dos y únelas con un enlace `[[ ]]`.",
    "Para cambiar una nota de carpeta, cambia su «tipo» en las propiedades (por ejemplo, de idea a proyecto): esa noche la pongo en su sitio.",
    "Los archivos (PDF, fotos, documentos) van a 40 Compartido, que es lo mismo que HolaZazu › Carpetas. Desde una nota se enseñan con `![[nombre del archivo]]`.",
    "No apuntes contraseñas, PIN ni números de tarjeta o de cuenta: el Cerebro se copia al móvil y a las copias de seguridad.",
    "Hoy toca ordenar: en la revisión de las 20:00 Zazu te propone adónde va cada nota de la Bandeja. Contesta «sí» y las mueve.",
]

FM = re.compile(r"\A---[ \t]*\r?\n(.*?\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.S)
ENLACE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
MD_ENLACE = re.compile(r"\]\(<?([^)<>\n]+?)>?\)")
CODIGO = re.compile(r"(```.*?```|~~~.*?~~~|`[^`\n]*`|<!--.*?-->|%%.*?%%)", re.S)
FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
MARCAS = re.compile(r"[\[\]|`<>%$\\{}#^]")                  # lo que abre enlaces, código, comentarios, etiquetas o fórmulas


# ---------- utilidades ----------
def leer(p, limite=None):
    """Texto de un archivo tal cual (con sus saltos \\r\\n y su BOM, si los tiene). None si no se puede leer o si es un
    acceso directo (los symlinks no se siguen)."""
    try:
        if Path(p).is_symlink():
            return None
        with open(p, encoding="utf-8", newline="") as f:
            return f.read(limite) if limite else f.read()
    except (OSError, UnicodeDecodeError):
        return None


def escribir(p, texto, modo):
    """Escribe p entero de una vez (archivo temporal nuevo + replace): nunca escribe a través de un symlink."""
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".ordenar.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        os.chmod(tmp, modo)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def bom(texto):
    """El BOM (U+FEFF) del principio de la nota, o "". Obsidian lo salta al leer las propiedades; el script también."""
    return "\ufeff" if (texto or "").startswith("\ufeff") else ""


def frontmatter(texto):
    """(propiedades, fin del bloque). ({}, 0) si no tiene; (None, fin) si el YAML está roto."""
    b = len(bom(texto))
    m = FM.match((texto or "")[b:])
    if not m:
        return {}, 0
    bloque = m.group(1) or ""
    try:
        d = yaml.safe_load(bloque) if yaml else dict(re.findall(r"(?m)^([^\s:#][^:]*):[ \t]*(.*?)\s*$", bloque))
    except Exception:
        return None, b + m.end()
    d = {} if d is None else d
    return (d if isinstance(d, dict) else None), b + m.end()


def vacio(v):
    return v is None or v == [] or v == {} or (isinstance(v, str) and not v.strip())


def valor(d, k):
    v = (d or {}).get(k)
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v if not vacio(x)) or None
    return "" if vacio(v) else str(v).strip().lower()


def a_fecha(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", str(v or ""))
    try:
        return date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def es_dia(p):
    """¿Se llama como una nota del Diario, «AAAA-MM-DD.md», con una fecha que existe?"""
    return bool(FECHA.fullmatch(p.stem)) and a_fecha(p.stem) is not None


def mtime(p):
    try:
        return p.stat().st_mtime
    except OSError:
        return 0


def conflicto(p):
    return ".sync-conflict-" in p.name


def nfc(s):
    return unicodedata.normalize("NFC", s)


def igual(nombre):
    """Clave para comparar nombres como el móvil Android y Windows (con Syncthing): sin distinguir mayúsculas ni NFC/NFD."""
    return nfc(nombre).casefold()


def por_nombre(rutas):
    """{nombre del archivo en minúsculas: [rutas]}, como el índice de Obsidian."""
    d = {}
    for r in rutas:
        d.setdefault(nfc(r.rsplit("/", 1)[-1]).lower(), []).append(r)
    return d


def obsidian(ruta, origen, nombres):
    """El archivo al que lleva [[ruta]] escrito en la nota «origen», como lo resuelve Obsidian (getLinkpathDest): ruta
    relativa (./ ../) exacta, ruta completa exacta y, si no, la más corta que termina en la ruta, primero las de la carpeta
    de la nota. nombres: por_nombre() de los archivos del vault. None si no lleva a ninguno o si hay empate (no se sabe)."""
    o = nfc(ruta).lower()
    s = nombres.get(o.rsplit("/", 1)[-1]) if "." in o.rsplit("/", 1)[-1] else None
    if not s:
        o += ".md"
        s = nombres.get(o.rsplit("/", 1)[-1])
    if not s:
        return None
    if "/" not in o and len(s) == 1:
        return s[0]
    bajo = {r: nfc(r).lower() for r in s}
    carpeta = posixpath.dirname(nfc(origen).lower())
    if o.startswith(("./", "../")):
        if o.startswith("./../"):
            o = o[2:]
        if o.startswith("./"):
            o = o[2:]
        while o.startswith("../"):
            o, carpeta = o[3:], posixpath.dirname(carpeta)
        carpeta += "/" if carpeta else ""
        o = carpeta + o
        if o in bajo.values():
            return next(r for r in s if bajo[r] == o)
    o = o[1:] if o.startswith("/") else o
    if o in bajo.values():
        return next(r for r in s if bajo[r] == o)
    if ruta.lstrip().startswith("/"):
        return None
    orden = sorted(((not bajo[r].startswith(carpeta), len(r)), r) for r in s if bajo[r].endswith(o))
    if not orden or (len(orden) > 1 and orden[0][0] == orden[1][0]):
        return None
    return orden[0][1]


def desenlazar(lineas, ruta):
    """Las líneas ya escritas del Informe que enlazan a «ruta» (que se ha vuelto a mover) la enseñan como código: un
    enlace a donde ya no está crearía una nota vacía al pulsarlo."""
    sin_md = ruta[:-3] if ruta.endswith(".md") else ruta
    patron = re.compile(r"\[\[" + re.escape(sin_md) + r"(?:\\?\|[^\]\n]*)?\]\]|\[[^\]\n]*\]\(<" + re.escape(ruta) + r">\)")
    return [patron.sub(lambda m: cod(ruta), l) for l in lineas]


def sin_titulo(p):
    return nfc(p.stem).lower().startswith(("sin título", "untitled"))


def unir(carpeta, sub):
    return carpeta if sub in ("", ".") else f"{carpeta}/{sub}"


def sin_codigo(texto):
    return CODIGO.sub(" ", texto)


def control(c):
    return unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp")    # saltos, tabuladores, invisibles, cambios de dirección


def limpio(v, tope=60):
    """Texto sacado de una nota (propiedades, títulos, nombres) listo para el Informe: una sola línea, sin caracteres
    de control ni marcas que abran enlaces [[ ]], código, comentarios, etiquetas o fórmulas, y como mucho «tope» letras."""
    s = " ".join(MARCAS.sub("", "".join(" " if control(c) else c for c in str(v))).split())
    return s if len(s) <= tope else s[:tope - 1].rstrip() + "…"


def cod(rel):
    """Una ruta entre `comillas de código` (sin saltos ni acentos graves que la rompan)."""
    return "`" + "".join("?" if control(c) else c for c in str(rel)).replace("`", "'") + "`"


def cuantos(n, uno, varios):
    return f"{n} {uno if n == 1 else varios}"


def fecha_larga(d):
    return f"{DIAS[d.weekday()].capitalize()}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def fecha_corta(d):
    return f"{d.day} {MESES[d.month - 1][:3]}"


def enlace(rel, texto=None, tabla=False):
    """Enlace wiki con ruta relativa al vault y sin .md (o enlace markdown si el nombre lleva # ^ |; o la ruta como
    código si lleva algo que rompería cualquier enlace o metería otro, como [ ])."""
    destino = rel[:-3] if rel.endswith(".md") else rel
    texto = limpio(texto or Path(destino).name, 200) or "nota"
    if any(c in destino for c in "[]<>`") or "%%" in destino or any(control(c) for c in destino):
        return cod(rel).replace("|", chr(92) + "|") if tabla else cod(rel)
    if any(c in destino for c in "#^|"):
        return f"[{texto}](<{rel.replace('|', chr(92) + '|') if tabla else rel}>)"
    return f"[[{destino}{chr(92) if tabla else ''}|{texto}]]" if texto != destino else f"[[{destino}]]"


# ---------- el ordenador ----------
class Ordenador:
    def __init__(self, vault, simular):
        self.v, self.simular = vault, simular
        self.ahora = datetime.now()
        self.hoy = self.ahora.date()
        self.hecho, self.no_movidos, self.avisos = [], [], []
        self.movs = self.fichas = self.quitadas = self.enlaces = self.notas_enlace = 0
        self.origen = {}          # ruta actual -> ruta original (para arreglar enlaces)
        self.reservados = set()   # destinos ya usados en la simulación
        self.vaciables = set()    # carpetas que pueden haberse quedado vacías
        self.tocados = set()      # archivos que han dado aviso (no repetir)
        self.ya = set()           # en la simulación: lo que ya se habría movido (los pasos siguientes no lo ven)
        self.simbolicos = set()   # accesos directos (symlinks) encontrados: no se tocan, salen en el informe
        self.salidas = []         # rutas de las que ha salido algo (los enlaces del Informe a ellas ya no valen)
        self.pendientes = {}      # nota que estaban escribiendo → {enlace: archivo nuevo}: se arreglan la próxima vez
        self.pendientes_antes = {}  # los pendientes de la vez anterior (los pone main() desde ESTADO)
        todos = self.archivos("")
        self.antes = [self.rel(p) for p in todos]   # el vault antes de ordenar (para saber adónde llevaba cada enlace)
        self.nombres = Counter(igual(p.name) for p in todos)
        self.rutas_md = set()     # nombres de archivo enlazados como [texto](carpeta/archivo): moverlos rompería el enlace
        for p in [p for z in (INICIO, BANDEJA, DIARIO, NOTAS, SERVIDOR) for p in self.archivos(z)] + self.sueltos():
            if p.suffix.lower() == ".md":
                for t in MD_ENLACE.findall(sin_codigo(leer(p) or "")):
                    t = t.split("#")[0].strip().replace("%20", " ")
                    if "/" in t and not re.match(r"[a-z][a-z0-9+.-]*:", t, re.I):
                        self.rutas_md.add(t.rsplit("/", 1)[1].lower())

    # --- rutas ---
    def rel(self, p):
        return Path(p).relative_to(self.v).as_posix()

    def por_enlace(self, p):
        """¿p, o alguna carpeta entre el vault y p, es un acceso directo (symlink)?"""
        p = Path(p)
        while p != self.v and self.v in p.parents:
            if p.is_symlink():
                return True
            p = p.parent
        return False

    def archivos(self, carpeta, ocultos=False, recursivo=True):
        """Archivos de una carpeta del vault. Nunca entra en un symlink ni lo devuelve: lo apunta en self.simbolicos."""
        base = self.v / carpeta if carpeta else self.v
        if self.por_enlace(base):
            if base.is_symlink():
                self.simbolicos.add(base)
            return []
        if not base.is_dir():
            return []
        out = []
        for raiz, dirs, files in os.walk(base):
            r = Path(raiz)
            visibles = [d for d in dirs if ocultos or not d.startswith(".")]
            self.simbolicos.update(r / d for d in visibles if (r / d).is_symlink())
            dirs[:] = sorted(d for d in visibles if not (r / d).is_symlink())
            for f in sorted(files):
                p = r / f
                if not ocultos and f.startswith("."):
                    continue
                if p.is_symlink():
                    self.simbolicos.add(p)
                elif p not in self.ya:
                    out.append(p)
            if not recursivo:
                break
        return out

    def sueltos(self):
        """Archivos sueltos en la raíz del vault (sin los ocultos, como .stignore)."""
        return [p for p in sorted(self.v.iterdir())
                if p.is_file() and not p.is_symlink() and not p.name.startswith((".", "~")) and p not in self.ya]

    def inicio_notas(self):
        """Notas de 00 Inicio que sí se revisan: todas menos las páginas fijas y Bases de datos/."""
        return [p for p in self.archivos(INICIO) if p.suffix == ".md" and nfc(self.rel(p)) not in FIJAS
                and not nfc(self.rel(p)).startswith(BASES + "/")]

    def zona(self, rel):
        """Dónde está una nota: «suelta», «plan» u «otra» dentro de 30 Notas; si no, su carpeta de primer nivel."""
        partes = rel.split("/")
        if partes[0] != NOTAS:
            return partes[0]
        if len(partes) == 2:
            return "suelta"
        return "plan" if partes[1] in SUBCARPETAS else "otra"

    def con_enlaces(self, carpeta):
        return any(Path(r, n).is_symlink() for r, ds, fs in os.walk(carpeta) for n in ds + fs)

    def reciente(self, p):
        lista = self.archivos(self.rel(p), ocultos=True) if p.is_dir() else [p]
        return any(time.time() - mtime(f) < RECIENTE for f in lista)

    def libre(self, destino):
        """destino, o «nombre (2)», «(3)»… si en su carpeta ya hay uno que se llama igual sin contar mayúsculas ni NFC/NFD
        (en el móvil Android y en Windows serían el mismo archivo y Syncthing no podría copiar uno de los dos)."""
        carpeta = destino.parent
        try:
            ocupados = {igual(x.name) for x in carpeta.iterdir()} if carpeta.is_dir() else set()
        except OSError:
            ocupados = set()
        ocupados |= {igual(r.name) for r in self.reservados if r.parent == carpeta}
        n, base = 2, destino
        while os.path.lexists(destino) or igual(destino.name) in ocupados:
            nombre = f"{base.name} ({n})" if base.is_dir() or not base.suffix else f"{base.stem} ({n}){base.suffix}"
            destino, n = base.with_name(nombre), n + 1
        return destino

    # --- acciones ---
    def no_movido(self, p, motivo):
        if p not in self.tocados:
            self.tocados.add(p)
            self.no_movidos.append(f"{cod(self.rel(p))}: {motivo}")

    def aviso(self, p, texto):
        if p not in self.tocados:
            self.tocados.add(p)
            self.avisos.append(texto)

    def registrar(self, de, a):
        self.origen[a] = self.origen.pop(de, de)

    def mover(self, src, carpeta, motivo):
        """Mueve src (archivo o carpeta) dentro de «carpeta» (ruta relativa) sin sobrescribir. Devuelve el destino."""
        if self.por_enlace(src) or (src.is_dir() and self.con_enlaces(src)):
            self.no_movido(src, "es o lleva dentro un acceso directo (symlink) a otro sitio: no lo muevo")
            return None
        if self.por_enlace(self.v / carpeta):
            self.no_movido(src, f"la carpeta de destino {cod(carpeta)} es un acceso directo (symlink): no muevo nada ahí")
            return None
        dentro = [src] if src.is_file() else self.archivos(self.rel(src))
        enlazado = [f for f in dentro if f.name.lower() in self.rutas_md]
        if enlazado:
            nombre = enlazado[0].stem if enlazado[0].suffix == ".md" else enlazado[0].name
            self.no_movido(src, f"hay un enlace con ruta, tipo {cod(f'[texto](carpeta/{enlazado[0].name})')}, que se rompería; "
                                f"cámbialo por {cod(f'[[{nombre}]]')}")
            return None
        if self.reciente(src):
            self.no_movido(src, "se acababa de cambiar; lo intento la próxima vez")
            return None
        de = self.rel(src)
        pares = [(self.rel(f), f.relative_to(src).as_posix()) for f in dentro] if src.is_dir() else []
        destino = self.libre(self.v / carpeta / src.name)
        if not self.simular:
            try:
                destino = self.mover_sin_pisar(src, destino)
            except OSError as e:
                self.no_movido(src, f"no he podido moverlo ({e.strerror or e})")
                return None
        self.reservados.add(destino)
        if self.simular:
            self.ya.update([src] + dentro)
        a = self.rel(destino)
        for viejo, resto in pares:
            self.registrar(viejo, f"{a}/{resto}")
        if not pares:
            self.registrar(de, a)
        self.vaciables.add(src.parent)
        self.movs += 1
        cambio = ""
        if destino.name != src.name:
            vecinos = {nfc(r.name) for r in self.reservados if r.parent == destino.parent}
            vecinos |= {nfc(x.name) for x in destino.parent.iterdir()} if destino.parent.is_dir() else set()
            por = ("ya había uno con ese nombre" if nfc(src.name) in vecinos else
                   "ya había uno que solo cambia en mayúsculas (en el móvil serían el mismo archivo)")
            cambio = f" (renombrado a «{limpio(destino.name, 200)}» porque {por})"
        hacia = cod(a) if destino.is_dir() or src.is_dir() or carpeta.startswith(SISTEMA) else enlace(a, a.replace("/", " › ").removesuffix(".md"))
        for r in [viejo for viejo, _ in pares] or [de]:   # si ya se había movido antes, su línea anterior deja de enlazar
            self.salidas.append(r)
            self.hecho = desenlazar(self.hecho, r)
        self.hecho.append(f"{cod(de)} → {hacia}{cambio}. {motivo}")
        print(f"{'(simulación) movería' if self.simular else 'movido'}: {de} → {a}  [{motivo}]")
        return destino

    def mover_sin_pisar(self, src, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(20):
            try:
                if src.is_dir():
                    if os.path.lexists(destino):
                        raise FileExistsError
                    os.rename(src, destino)
                    return destino
                try:
                    os.link(src, destino, follow_symlinks=False)   # falla si el destino ya existe: nunca pisa nada
                except FileExistsError:
                    raise
                except OSError:                     # sistema de archivos sin enlaces duros
                    if os.path.lexists(destino):
                        raise FileExistsError
                    os.rename(src, destino)
                else:
                    os.unlink(src)
                return destino
            except FileExistsError:
                destino = self.libre(destino)
        raise OSError("no encuentro un nombre libre")

    def quitar_vacias(self, carpeta):
        """rmdir de abajo arriba de las subcarpetas vacías (nunca borra archivos)."""
        if not carpeta.is_dir() or self.por_enlace(carpeta):
            return
        for raiz, dirs, files in os.walk(carpeta, topdown=False):
            r = Path(raiz)
            if any(r.iterdir()):
                continue
            print(f"{'(simulación) quitaría' if self.simular else 'quitada'} la carpeta vacía: {self.rel(r)}")
            if not self.simular:
                try:
                    r.rmdir()
                except OSError:
                    continue
            self.quitadas += 1
            self.hecho.append(f"Quitada la carpeta vacía {cod(self.rel(r))}.")

    def guardar(self, p, texto):
        """Reescribe una nota sin cambiar su fecha (+1 s para que Syncthing note el cambio). Nunca a través de un symlink."""
        if self.por_enlace(p):
            raise OSError("es un acceso directo (symlink): no lo toco")
        st = p.lstat()
        escribir(p, texto, stat.S_IMODE(st.st_mode))
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000), follow_symlinks=False)

    def rellenar(self, p, texto, fm, fin, props, que):
        """Añade a una nota las propiedades que le faltan y lo cuenta. que: cómo se dice en el informe."""
        nuevo = self.poner(texto, fm, fin, props)
        if nuevo is None:
            self.aviso(p, f"{enlace(self.rel(p))} no tiene {que} y no he sabido ponérselo: ponlo a mano.")
            return
        if not self.simular:
            try:
                self.guardar(p, nuevo)
            except OSError as e:
                self.aviso(p, f"{enlace(self.rel(p))} no tiene {que} y no he podido escribir en ella ({e.strerror or e}).")
                return
        self.fichas += 1
        puesto = " y ".join(f"{k} «{v}»" for k, v in props.items())
        self.hecho.append(f"{enlace(self.rel(p))}: le he puesto {puesto} (no tenía).")
        print(f"{'(simulación) completaría' if self.simular else 'completada'}: {self.rel(p)} → {puesto}")

    # --- a) archivos sueltos en la raíz ---
    def raiz_archivos(self):
        for p in self.sueltos():
            if conflicto(p):
                continue
            if p.suffix.lower() in DOCS:
                self.mover(p, BANDEJA, "Estaba suelta en la raíz: queda en la Bandeja para ordenarla.")
            else:
                self.mover(p, GUARDADO, "Archivo suelto en la raíz: queda en 40 Compartido › Guardado.")

    # --- b) carpetas que no son del plan ---
    def raiz_carpetas(self):
        for p in sorted(self.v.iterdir()):
            if p.name in RAIZ_OK or p.name.startswith(".") or not p.is_dir():
                continue
            if p.is_symlink():
                self.simbolicos.add(p)                  # sale en el informe
            elif not self.archivos(self.rel(p), ocultos=True):
                self.quitar_vacias(p)
            elif p.name in LLM_DIRS:
                self.llm_wiki(p)
            else:
                self.mover(p, BANDEJA, "Carpeta que no es del Cerebro: la dejo entera en la Bandeja para que decidas.")
        for nombre in LLM_DIRS:                       # la skill llm-wiki escribe en WIKI_PATH = 90 Sistema
            p = self.v / SISTEMA / nombre
            if p.is_dir() and not self.por_enlace(p):
                self.llm_wiki(p)

    def llm_wiki(self, carpeta):
        """Reparte una carpeta en inglés de la skill llm-wiki según la traducción de 90 Sistema/SCHEMA.md."""
        nombre = carpeta.name
        for f in self.archivos(self.rel(carpeta)):
            dentro = f.relative_to(carpeta)
            if nombre == "_archive":
                destino = unir(ARCHIVO, dentro.parent.as_posix())
            elif nombre == "raw" and dentro.parts[0] != "assets" and f.suffix.lower() not in ADJ_EXT - {".pdf"}:
                destino = FUENTES
            elif f.suffix.lower() in ADJ_EXT:
                self.adjunto(f, f"Venía de {cod(nombre + '/')} (skill llm-wiki): los archivos van a 40 Compartido › Adjuntos.")
                continue
            elif f.suffix.lower() in DOCS:
                destino = LLM_DIRS[nombre]
            else:
                destino = GUARDADO
            self.mover(f, destino, f"Venía de {cod(self.rel(carpeta) + '/')} (skill llm-wiki, en inglés): va a {destino.replace('/', ' › ')}.")
        if self.simular:
            print(f"(simulación) quitaría la carpeta {self.rel(carpeta)} si se queda vacía")
        else:
            self.quitar_vacias(carpeta)

    # --- e) notas y lienzos vacíos ---
    def solo_propiedades(self, texto):
        """Las propiedades de una nota que no tiene nada más que propiedades; None si tiene texto o no tiene propiedades."""
        fm, fin = frontmatter(texto)
        return fm if fm is not None and fin > 0 and not texto[fin:].strip() else None

    @staticmethod
    def rellenas(fm):
        """Propiedades con algo escrito, sin contar tipo y creado (las pone Obsidian al crear la nota)."""
        return [k for k, v in fm.items() if str(k).lower() not in ("tipo", "creado")
                and not vacio(v) and not (isinstance(v, list) and all(vacio(x) for x in v))]

    def vacia(self, p):
        t = leer(p)
        if t is None:
            return False
        t = t[len(bom(t)):]
        if p.suffix.lower() == ".canvas":
            if not t.strip():
                return True
            try:
                d = json.loads(t)
            except ValueError:
                return False
            return isinstance(d, dict) and not d.get("nodes")
        if not t.strip():
            return True
        if sin_titulo(p):
            fm = self.solo_propiedades(t)
            return fm is not None and not self.rellenas(fm)       # con alguna propiedad rellena no está vacía
        return False

    def vacias(self):
        for p in self.sueltos() + self.inicio_notas() + self.archivos(BANDEJA) + self.archivos(DIARIO) + self.archivos(NOTAS):
            if p.suffix.lower() in (".md", ".canvas") and p.exists() and not conflicto(p) and not self.reciente(p) and self.vacia(p):
                self.mover(p, unir(ARCHIVO, Path(self.rel(p)).parent.as_posix()), "Estaba vacía: archivada (no borrada).")

    # --- c) cada nota a la carpeta de su tipo ---
    def notas_ordenables(self):
        out = self.inicio_notas() + self.archivos(BANDEJA) + self.archivos(DIARIO) + self.archivos(NOTAS)
        return [p for p in out if p.suffix == ".md" and not conflicto(p)]

    def por_tipo(self):
        for p in self.notas_ordenables():
            if not p.exists():
                continue
            rel = self.rel(p)
            zona = self.zona(rel)
            fm, _ = frontmatter(leer(p))
            if fm is None:
                if zona not in ("suelta", "plan", "otra"):   # las de 30 Notas salen en «Notas sin tipo»
                    self.aviso(p, f"{enlace(rel)}: sus propiedades (el bloque de arriba entre `---`) están mal escritas; "
                                  "Obsidian no las lee y no sé de qué tipo es.")
                continue
            tipo, llm = valor(fm, "tipo"), valor(fm, "type")
            if tipo and tipo not in TABLA:
                self.aviso(p, f"{enlace(rel)} tiene un tipo que no conozco: «{limpio(tipo)}». Ponle uno de la tabla de "
                              "90 Sistema/SCHEMA.md (idea, proyecto, tema…).")
                continue
            if zona == DIARIO and es_dia(p):
                if tipo not in ("", "diario"):
                    self.aviso(p, f"{enlace(rel)} se llama como un día del Diario pero su tipo es «{tipo}»: no la muevo. "
                                  "Si es la nota del día, ponle tipo «diario»; si no, cámbiale el nombre y esa noche la pongo en su sitio.")
                continue                                  # sin tipo o sin fecha: lo completa completar_diario()
            if tipo in FIJOS:
                casa = TABLA[tipo]
                if not rel.startswith(casa + "/"):
                    que = ("parece una copia automática de Zazu (esas viven en 50 Zazu y se crean solas)" if casa.startswith(ZAZU)
                           else f"ese tipo es de las páginas fijas de {casa}")
                    self.aviso(p, f"{enlace(rel)} tiene tipo «{tipo}» y {que}: no la muevo. Si es una nota tuya, cámbiale "
                                  "el tipo (idea, proyecto, tema…); si sobra, archívala.")
                continue
            if tipo == "diario" and zona == DIARIO:
                self.aviso(p, f"{enlace(rel)} es del Diario pero su nombre no es una fecha «AAAA-MM-DD»: si es un día, "
                              "júntala con la nota de ese día; si no, cámbiale el tipo.")
                continue
            if tipo == "nota" or (not tipo and llm not in LLM_CARPETA):
                if zona in (INICIO, DIARIO):
                    self.mover(p, BANDEJA, "Su tipo es «nota»: va a la Bandeja." if tipo else
                               "No tenía tipo: la dejo en la Bandeja para ordenarla.")
                elif tipo == "nota" and zona != BANDEJA:  # dentro de 30 Notas
                    self.aviso(p, f"{enlace(rel)} está en {cod(rel.rsplit('/', 1)[0])} pero su tipo es «nota»: ponle su tipo de verdad (idea, proyecto, tema…).")
                continue                                  # en la Bandeja se queda; sin tipo en 30 Notas: completar() o «Notas sin tipo»
            destino = CARPETA_DE.get(tipo) or LLM_CARPETA[llm]
            if rel.startswith(destino + "/"):
                continue
            if destino == DIARIO and (not es_dia(p) or os.path.lexists(self.v / DIARIO / p.name)):
                self.no_movido(p, "es de tipo «diario», pero su nombre no es una fecha AAAA-MM-DD o ese día ya tiene nota en 20 Diario: júntalas a mano")
                continue
            self.mover(p, destino, f"Su tipo es «{limpio(tipo or llm)}».")

    # --- d) completar las fichas sin tipo y los días del Diario ---
    def poner(self, texto, fm, fin, props):
        """Añade propiedades que faltan al frontmatter sin tocar el resto de la nota. None si no es seguro."""
        nl = "\r\n" if "\r\n" in texto[:300] else "\n"
        if fin == 0:                                  # el bloque va después del BOM, como lo lee Obsidian
            b = bom(texto)
            return b + "---" + nl + "".join(f"{k}: {v}{nl}" for k, v in props.items()) + "---" + nl + texto[len(b):]
        cab, cuerpo, nuevas = texto[:fin], texto[fin:], []
        for k, v in props.items():
            if k not in fm:
                nuevas.append(f"{k}: {v}{nl}")
            elif vacio(fm[k]):
                cab, n = re.subn(rf"(?m)^{k}:[ \t]*(?:\"\"|''|null|~|\[\])?[ \t]*(?=\r?$)", f"{k}: {v}", cab, count=1)
                if not n:
                    return None
        primera = cab.index("\n") + 1
        return cab[:primera] + "".join(nuevas) + cab[primera:] + cuerpo

    def completar(self):
        for sub, por_defecto in SUBCARPETAS.items():
            for p in self.archivos(f"{NOTAS}/{sub}"):
                if p.suffix != ".md" or conflicto(p) or self.reciente(p):
                    continue
                texto = leer(p)
                fm, fin = frontmatter(texto)
                if texto is None or fm is None or valor(fm, "tipo"):
                    continue
                llm = valor(fm, "type")
                tipo = LLM_TIPO[llm] if llm in LLM_TIPO else por_defecto
                if not tipo:
                    continue                          # persona o empresa: lo decide Fran (sale en el informe)
                creado = (a_fecha(fm.get("creado")) or a_fecha(fm.get("created")) or a_fecha(fm.get("fecha"))
                          or date.fromtimestamp(mtime(p)))
                props = {"tipo": tipo}
                if vacio(fm.get("creado")):
                    props["creado"] = creado.isoformat()
                self.rellenar(p, texto, fm, fin, props, "tipo")

    def completar_diario(self):
        for p in self.archivos(DIARIO):
            if p.suffix != ".md" or not es_dia(p) or conflicto(p) or self.reciente(p):
                continue
            texto = leer(p)
            fm, fin = frontmatter(texto)
            if texto is None or fm is None or valor(fm, "tipo") not in ("", "diario"):
                continue                              # propiedades rotas u otro tipo: avisa por_tipo()
            props = {}
            if not valor(fm, "tipo"):
                props["tipo"] = "diario"
            if vacio(fm.get("fecha")):
                props["fecha"] = p.stem
            if props:
                self.rellenar(p, texto, fm, fin, props, "tipo de día del Diario")

    # --- f) imágenes y PDF sueltos entre las notas ---
    def adjunto(self, p, motivo):
        if self.nombres[igual(p.name)] > 1:
            self.no_movido(p, "hay otro archivo con el mismo nombre en el Cerebro; si lo muevo, un `![[...]]` podría enseñar el otro. Renombra uno de los dos")
            return
        self.mover(p, ADJUNTOS, motivo)

    def adjuntos_sueltos(self):
        for p in self.archivos(BANDEJA, recursivo=False) + self.archivos(DIARIO) + self.archivos(NOTAS):
            ext = p.suffix.lower()
            if not p.exists() or ext in DOCS or conflicto(p):
                continue
            if ext in ADJ_EXT:
                self.adjunto(p, "Imagen o PDF suelto entre las notas: los archivos viven en 40 Compartido › Adjuntos.")
            else:
                self.no_movido(p, "no es una nota ni una imagen o PDF: dile a Zazu a qué carpeta de 40 Compartido va")

    # --- enlaces [[ruta/antigua]] ---
    def arreglar_enlaces(self):
        """Los [[enlaces con ruta]] (completa, parcial como [[Ideas/X]] o relativa como [[../X]]) que, tras mover, ya no
        llevan al mismo archivo que antes pasan a llevar su ruta nueva completa. Los [[enlaces por nombre]] no se tocan
        (no se rompen al mover). Una nota cambiada hace menos de 10 min no se reescribe: el Informe dice qué cambiar y el
        cambio queda pendiente (en ESTADO) para la próxima vez, si el enlace sigue roto y su destino sigue existiendo."""
        nuevo_de = {orig: actual for actual, orig in self.origen.items() if actual != orig}
        if not nuevo_de and not self.pendientes_antes:
            return
        antes, despues = por_nombre(self.antes), por_nombre(nuevo_de.get(r, r) for r in self.antes)
        existen = {nuevo_de.get(r, r) for r in self.antes}
        editables = [p for p in self.sueltos() + self.inicio_notas() if p.suffix == ".md"]
        editables += [p for c in (BANDEJA, DIARIO, NOTAS) for p in self.archivos(c) if p.suffix == ".md"]
        escrito = lambda d, ruta: d[:-3] if d.endswith(".md") and not ruta.lower().endswith(".md") else d
        for p in editables:
            texto = leer(p)
            if texto is None or "[[" not in texto:
                continue
            rel = self.rel(p)
            era, cambios = self.origen.get(rel, rel), {}
            previos = self.pendientes_antes.get(era) if isinstance(self.pendientes_antes.get(era), dict) else {}

            def cambiar(m):
                dentro = m.group(2).replace("\\|", "\0")
                corte = min([i for i in (dentro.find("#"), dentro.find("|"), dentro.find("\0")) if i >= 0] or [len(dentro)])
                ruta = dentro[:corte].strip()
                if "/" not in ruta:
                    return m.group(0)
                destino = obsidian(ruta, era, antes)  # adónde llevaba antes de ordenar
                if destino is None:                   # o adónde tenía que llevar (pendiente de una vez anterior)
                    destino = previos.get(ruta)
                    if not isinstance(destino, str) or obsidian(ruta, rel, despues) is not None:
                        return m.group(0)
                destino = nuevo_de.get(destino, destino)
                if destino not in existen or obsidian(ruta, rel, despues) == destino:   # no existe o sigue llevando ahí
                    return m.group(0)
                cambios[ruta] = destino
                return f"{m.group(1)}[[{escrito(destino, ruta)}{dentro[corte:].replace(chr(0), chr(92) + '|')}]]"

            trozos = CODIGO.split(texto)              # los trozos impares son código: no se tocan
            nuevo = "".join(t if i % 2 else ENLACE.sub(cambiar, t) for i, t in enumerate(trozos))
            if not cambios:
                continue
            if self.reciente(p):                      # alguien la está escribiendo: no se pisa
                self.pendientes[rel] = cambios
                pares = [(f"[[{a}]]", f"[[{escrito(b, a)}]]") for a, b in cambios.items()]
                self.avisos.append(f"{enlace(rel)} se acababa de cambiar y no he arreglado sus enlaces a lo que he movido: "
                                   f"cambia {', '.join(f'{cod(a)} por {cod(b)}' for a, b in pares[:5])}"
                                   f"{'…' if len(pares) > 5 else ''}. Si no, lo hago yo la próxima vez.")
                print(f"sin arreglar (se acababa de cambiar): {len(pares)} enlaces en {rel}: "
                      + ", ".join(f"{a} → {b}" for a, b in pares))
                continue
            if not self.simular:
                try:
                    self.guardar(p, nuevo)
                except OSError as e:
                    self.avisos.append(f"No he podido arreglar los enlaces de {enlace(rel)} ({e.strerror or e}).")
                    continue
            self.enlaces += len(cambios)
            self.notas_enlace += 1
            print(f"{'(simulación) arreglaría' if self.simular else 'arreglados'} {len(cambios)} enlaces en {rel}")
        if self.enlaces:
            self.hecho.append(f"He arreglado {self.enlaces} enlaces con ruta en {self.notas_enlace} notas para que sigan llevando a su sitio.")

    def ordenar(self):
        self.raiz_carpetas()      # b
        self.vacias()             # e (antes de c y d: una nota vacía no se mueve ni se rellena)
        self.raiz_archivos()      # a
        self.por_tipo()           # c
        self.completar()          # d
        self.completar_diario()   # d
        self.adjuntos_sueltos()   # f
        bandeja = self.v / BANDEJA
        for c in sorted(self.vaciables, key=lambda c: -len(c.parts)):   # subcarpetas de la Bandeja que se han quedado vacías
            while bandeja in c.parents and c.is_dir() and not any(c.iterdir()):
                self.quitar_vacias(c)
                c = c.parent
        self.arreglar_enlaces()

    # ---------- el informe ----------
    def indice(self):
        self.todos = self.archivos("")
        self.rutas = {self.rel(p).lower() for p in self.todos} | {INFORME.lower()}   # el informe existe tras esta ejecución
        self.por_nombre = {}
        for r in self.rutas:
            self.por_nombre.setdefault(r.rsplit("/", 1)[-1], []).append(r)

    def resuelve(self, destino, origen):
        t = destino.strip().replace("\\", "/").lstrip("/")
        for c in (t + ".md", t):
            c = c.lower()
            if c.startswith(("./", "../")):
                c = posixpath.normpath(posixpath.join(posixpath.dirname(origen.lower()), c))
            if "/" in c:
                if c in self.rutas or any(r.endswith("/" + c) for r in self.por_nombre.get(c.rsplit("/", 1)[1], [])):
                    return True
            elif c in self.por_nombre:
                return True
        return False

    def enlaces_rotos(self):
        zonas = [INICIO, BANDEJA, DIARIO, NOTAS, SERVIDOR]
        notas = [p for z in zonas for p in self.archivos(z) if p.suffix == ".md" and self.rel(p) != INFORME]
        notas += [self.v / SISTEMA / "index.md"]
        rotos = []
        for p in notas:
            rel = self.rel(p) if p.exists() and not self.por_enlace(p) else None
            texto = leer(p) if rel else None
            if not texto:
                continue
            vistos = set()
            for _, dentro in ENLACE.findall(sin_codigo(texto)):
                destino = re.split(r"[#|]|\\\|", dentro, maxsplit=1)[0].strip()
                if destino and destino not in vistos and not self.resuelve(destino, rel):
                    vistos.add(destino)
                    rotos.append((rel, destino))
        return rotos

    def info_notas(self, carpeta):
        """[(ruta, propiedades)] de las notas de una carpeta."""
        out = []
        for p in self.archivos(carpeta):
            if p.suffix == ".md":
                fm, _ = frontmatter(leer(p, 8000))
                out.append((p, fm))
        return out

    def antiguedad(self, p, fm):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
        d = a_fecha((fm or {}).get("creado")) or (a_fecha(m.group(1)) if m else None) or date.fromtimestamp(mtime(p))
        return max((self.hoy - d).days, 0)

    def zazu(self):
        z = self.v / ZAZU
        if not z.is_dir() or self.por_enlace(z):
            return ["Todavía no hay nada de Zazu en el Cerebro: la copia automática aún no ha escrito en 50 Zazu."], 0
        meses = {(self.hoy - timedelta(days=d)).strftime("%Y-%m") for d in range(8)}
        items = []
        for clase in ("Conversaciones", "Informes"):
            for mes in meses:
                for p in self.archivos(f"{ZAZU}/{clase}/{mes}", recursivo=False):
                    if p.suffix != ".md":
                        continue
                    fm, _ = frontmatter(leer(p, 4000))
                    fm = fm or {}
                    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2})[.:](\d{2})", p.name)
                    f = a_fecha(fm.get("fecha")) or (a_fecha(m.group(1)) if m else None)
                    if not f:
                        continue
                    hora = fm.get("hora")
                    h = re.match(r"(\d{1,2}):(\d{2})", str(hora or ""))
                    if isinstance(hora, int):              # YAML lee 10:15 sin comillas como minutos
                        hh, mm = divmod(hora, 60)
                    elif h or m:
                        hh, mm = (int(h.group(1)), int(h.group(2))) if h else (int(m.group(2)), int(m.group(3)))
                    else:
                        hh = mm = 0
                    try:
                        cuando = datetime(f.year, f.month, f.day, hh, mm)
                    except ValueError:
                        cuando = datetime(f.year, f.month, f.day)
                    titulo = limpio(fm.get("title") or p.stem.split(" · ", 1)[-1])
                    items.append((cuando, clase, p, limpio(fm.get("canal") or "", 30), titulo))
        items.sort(reverse=True)
        dia = [i for i in items if i[0] >= self.ahora - timedelta(hours=24)]
        semana = [i for i in items if i[0].date() > self.hoy - timedelta(days=7)]
        cuenta = lambda lista, c: sum(1 for i in lista if i[1] == c)
        out = [f"**Últimas 24 horas:** {cuantos(cuenta(dia, 'Conversaciones'), 'conversación', 'conversaciones')} y "
               f"{cuantos(cuenta(dia, 'Informes'), 'informe', 'informes')} de rutinas."]
        for clase, nombre in (("Conversaciones", "Conversaciones"), ("Informes", "Informes de rutinas")):
            lista = [i for i in dia if i[1] == clase]
            if lista:
                out.append(f"\n{nombre}:")
                out += [f"- {fecha_corta(c.date())} {c:%H:%M} · {enlace(self.rel(p), t)}" + (f" · {canal}" if canal else "")
                        for c, _, p, canal, t in lista[:TOPE]]
                if len(lista) > TOPE:
                    out.append(f"- …y {len(lista) - TOPE} más.")
        out += ["", f"**Últimos 7 días:** {cuantos(cuenta(semana, 'Conversaciones'), 'conversación', 'conversaciones')} y "
                f"{cuantos(cuenta(semana, 'Informes'), 'informe', 'informes')}. "
                "Cada día del Diario tiene su sección «Zazu hoy» con los enlaces.", "",
                "| Día | Conversaciones | Informes |", "|---|--:|--:|"]
        for d in range(7):
            f = self.hoy - timedelta(days=d)
            texto = f"{DIAS[f.weekday()]} {fecha_corta(f)}"
            nota = f"{DIARIO}/{f.isoformat()}.md"
            celda = enlace(nota, texto, tabla=True) if (self.v / nota).exists() else texto
            del_dia = [i for i in semana if i[0].date() == f]
            out.append(f"| {celda} | {cuenta(del_dia, 'Conversaciones')} | {cuenta(del_dia, 'Informes')} |")
        out += ["", self.rutinas()]
        if (z / "Zazu.md").exists():
            out.append(f"Todo lo de Zazu: {enlace(ZAZU + '/Zazu.md', 'Zazu')}.")
        return out, len(items)

    def rutinas(self):
        ruta = self.v / ZAZU / "rutinas.md"
        texto = None if self.por_enlace(ruta) else leer(ruta)
        if not texto:
            return "**Rutinas:** todavía no hay copia de las rutinas (50 Zazu/rutinas.md)."
        filas = [[c.strip() for c in l.strip().strip("|").split("|")] for l in texto.splitlines() if l.lstrip().startswith("|")]
        filas = [f for f in filas if not all(re.fullmatch(r":?-*:?", c) for c in f)]
        if len(filas) < 2:
            return f"**Rutinas:** no he encontrado la tabla en {enlace(ZAZU + '/rutinas.md', 'Rutinas de Zazu')}."
        cab = [c.lower() for c in filas[0]]
        i_nombre = next((i for i, c in enumerate(cab) if "rutina" in c or "nombre" in c), 1)
        i_activa = next((i for i, c in enumerate(cab) if "activ" in c), None)
        i_estado = next((i for i, c in enumerate(cab) if c in ("", "estado", "resultado")), 0)
        activas = errores = 0
        nombres_error = []
        for f in filas[1:]:
            estado_fila = f[i_estado].lower() if len(f) > i_estado else ""
            activa = i_activa is None or (len(f) > i_activa and f[i_activa].lower().startswith(("s", "✅", "true")))
            activas += activa
            if "🔴" in estado_fila or "error" in estado_fila or "❌" in estado_fila:
                errores += 1
                nombres_error.append(f"«{limpio(f[i_nombre]) if len(f) > i_nombre else '?'}»")
        estado = (f"con error en su última ejecución: {', '.join(nombres_error)}. Si se repite, díselo a Zazu o a Claude Code."
                  if errores else "todas terminaron bien la última vez.")
        return (f"**Rutinas:** {cuantos(activas, 'activa', 'activas')} de {len(filas) - 1}; {estado} "
                f"Detalle: {enlace(ZAZU + '/rutinas.md', 'Rutinas de Zazu')}.")

    def novedades(self):
        grupos = [(INICIO, INICIO, {".md"}), (BANDEJA, BANDEJA, DOCS), (DIARIO, DIARIO, DOCS)]
        grupos += [(f"30 Notas › {s}", f"{NOTAS}/{s}", DOCS) for s in SUBCARPETAS]
        grupos += [("40 Compartido (archivos)", COMPARTIDO, None), (SERVIDOR, SERVIDOR, DOCS)]
        limite = time.time() - 7 * 86400
        out = []
        for titulo, carpeta, extensiones in grupos:
            lista = []
            for p in self.archivos(carpeta):
                rel = self.rel(p)
                if (extensiones and p.suffix not in extensiones) or rel in (INFORME, f"{SERVIDOR}/estado.md") or mtime(p) < limite:
                    continue
                cuando = date.fromtimestamp(mtime(p))
                if p.suffix == ".md":
                    fm, _ = frontmatter(leer(p, 8000))
                    m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
                    nacio = a_fecha((fm or {}).get("creado")) or a_fecha((fm or {}).get("fecha")) or (a_fecha(m.group(1)) if m else None)
                    que = "nueva" if nacio and (self.hoy - nacio).days < 7 else "cambiada"
                else:
                    que = "guardado"
                lista.append((mtime(p), f"- {enlace(rel)} · {que} el {fecha_corta(cuando)}"))
            if lista:
                lista.sort(reverse=True)
                out.append(f"**{titulo}** ({len(lista)})")
                out += [l for _, l in lista[:TOPE]] + ([f"- …y {len(lista) - TOPE} más."] if len(lista) > TOPE else []) + [""]
        return out or ["Nada nuevo esta semana."]

    def informe(self, acciones):
        self.indice()
        siete = time.time() - 7 * 86400
        # 1. Resumen
        filas = [(BANDEJA, BANDEJA, ".md"), (DIARIO, DIARIO, ".md")]
        filas += [(f"30 Notas › {s}", f"{NOTAS}/{s}", ".md") for s in SUBCARPETAS]
        filas += [("40 Compartido (archivos)", COMPARTIDO, None), ("50 Zazu › Conversaciones", f"{ZAZU}/Conversaciones", ".md"),
                  ("50 Zazu › Informes", f"{ZAZU}/Informes", ".md"), (SERVIDOR, SERVIDOR, ".md")]
        tabla = ["| Carpeta | Total | Nuevas o cambiadas (7 días) |", "|---|--:|--:|"]
        for titulo, carpeta, ext in filas:
            lista = [p for p in self.archivos(carpeta) if ext is None or p.suffix == ext]
            tabla.append(f"| {titulo} | {len(lista)} | {sum(1 for p in lista if mtime(p) >= siete)} |")
        # 3. Lo que necesita tu decisión
        bandeja = sorted(((self.antiguedad(p, fm), p) for p, fm in self.info_notas(BANDEJA)), key=lambda x: (-x[0], x[1].name))
        sin_tipo = []
        for p, fm in self.info_notas(NOTAS):
            if conflicto(p):
                continue                              # sale en «Otros avisos»
            rel = self.rel(p)
            sub = rel.split("/")[1] if rel.count("/") >= 2 else None
            if fm is None:
                sin_tipo.append(f"- {enlace(rel)}: sus propiedades (el bloque de arriba entre `---`) están mal escritas; Obsidian no las lee.")
            elif not valor(fm, "tipo"):
                pista = "ponle tipo «persona» o «empresa»" if sub == "Personas y empresas" else (
                    "esta carpeta no es del plan: muévela a una de las seis de 30 Notas" if sub and sub not in SUBCARPETAS else "ponle su tipo")
                sin_tipo.append(f"- {enlace(rel)}: {pista}.")
        rotos = self.enlaces_rotos()
        avisos = list(self.avisos)
        otras = ([d.name for d in (self.v / NOTAS).iterdir() if d.is_dir() and not d.is_symlink() and not d.name.startswith(".")
                  and d.name not in SUBCARPETAS] if (self.v / NOTAS).is_dir() and not self.por_enlace(self.v / NOTAS) else [])
        avisos += [f"La carpeta {cod('30 Notas/' + n)} no es del plan: sus notas no salen en tus tablas. Dile a Zazu adónde van." for n in otras]
        if (self.v / BANDEJA).is_dir() and not self.por_enlace(self.v / BANDEJA):
            avisos += [f"La carpeta {cod(BANDEJA + '/' + d.name)} espera que decidas qué hacer con ella (llegó suelta o en una carpeta que no es del plan)."
                       for d in sorted((self.v / BANDEJA).iterdir()) if d.is_dir() and not d.is_symlink() and not d.name.startswith(".")]
        for r in CLAVE:
            if not self.por_enlace(self.v / r) and not (leer(self.v / r) or "").strip():
                avisos.append(f"Falta o está vacío {cod(r)}. Avisa a Claude Code para que lo recupere de la copia de seguridad.")
        for p in self.archivos(INICIO):               # lo que no se mueve de 00 Inicio y no sale en ninguna tabla
            rel = nfc(self.rel(p))
            en_bases = rel.startswith(BASES + "/")
            if conflicto(p) or rel in FIJAS or p.suffix.lower() == (".base" if en_bases else ".md"):
                continue
            avisos.append(f"{cod(self.rel(p))} " + (
                "está en Bases de datos, donde solo van las bases (.base): no sale en ninguna tabla y no lo muevo." if en_bases
                else "no es una nota y 00 Inicio solo guarda las páginas de inicio: no lo muevo.")
                + " Dile a Zazu adónde va (las notas, a su carpeta; los archivos, a 40 Compartido).")
        repes = Counter(igual(p.name) for p in self.todos if p.suffix in DOCS and not self.rel(p).startswith((COMPARTIDO, ZAZU, ARCHIVO, FUENTES)))
        for nombre, n in sorted(repes.items()):
            if n > 1:
                donde = [self.rel(p) for p in self.todos if igual(p.name) == nombre and not self.rel(p).startswith((COMPARTIDO, ZAZU, ARCHIVO, FUENTES))]
                avisos.append(f"Hay {n} notas que se llaman «{limpio(Path(donde[0]).stem, 200)}» ({', '.join(cod(d) for d in donde)}): "
                              "un `[[enlace]]` no sabe a cuál ir. Fusiónalas o renombra una.")
        avisos += [f"Conflicto de sincronización: {cod(self.rel(p))}. Compáralo con el original, junta lo que falte y archívalo."
                   for p in self.todos if ".sync-conflict-" in p.name]
        for raiz, dirs, _ in os.walk(self.v):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not (Path(raiz) / d).is_symlink()]
            avisos += [f"Carpeta en inglés de la skill llm-wiki que no debería existir: {cod(self.rel(Path(raiz) / d))}." for d in dirs
                       if d in LLM_DIRS and not (Path(raiz) / d).relative_to(self.v).as_posix().startswith(ARCHIVO)]
        for p in self.sueltos() + self.inicio_notas() + self.archivos(BANDEJA) + self.archivos(DIARIO) + self.archivos(NOTAS):
            if p.suffix == ".md" and sin_titulo(p):
                fm = self.solo_propiedades(leer(p) or "")
                if fm and self.rellenas(fm):
                    avisos.append(f"{enlace(self.rel(p))} se llama «Sin título» y solo tiene propiedades, pero alguna está rellena: "
                                  "no la archivo. Renómbrala con un nombre que diga de qué va.")
        avisos += [f"{cod(self.rel(p))} es un acceso directo (symlink) a otro sitio: no lo muevo, ni lo leo, ni lo sigo. "
                   "Si sobra, dile a Claude Code que lo quite." for p in sorted(self.simbolicos)]
        # 4. Zazu
        zazu, _ = self.zazu()
        # 6. Consejos
        consejos = []
        viejas = [b for b in bandeja if b[0] > 7]
        if len(bandeja) > 5 or viejas:
            dias = cuantos(bandeja[0][0], "día", "días") if bandeja else ""
            mas = "" if not bandeja or not bandeja[0][0] else (f" desde hace {dias}" if len(bandeja) == 1 else f", la más antigua de hace {dias}")
            consejos.append(f"Tienes {cuantos(len(bandeja), 'nota', 'notas')} en la Bandeja{mas}. Dile a Zazu «ordena la bandeja» y te propone adónde va cada una.")
        proyectos = [(p, fm) for p, fm in self.info_notas(f"{NOTAS}/Proyectos") if fm and valor(fm, "tipo") == "proyecto"]
        sin_siguiente = [enlace(self.rel(p)) for p, fm in proyectos if valor(fm, "estado") == "activo" and not valor(fm, "siguiente")]
        if sin_siguiente:
            consejos.append(f"Estos proyectos activos no tienen «siguiente»: {', '.join(sin_siguiente)}. Escribe en una frase cuál es el próximo paso.")
        vencidos = [f"{enlace(self.rel(p))} ({fecha_corta(a_fecha(fm.get('plazo')))})" for p, fm in proyectos
                    if valor(fm, "estado") in ("activo", "esperando") and a_fecha(fm.get("plazo")) and a_fecha(fm.get("plazo")) < self.hoy]
        if vencidos:
            consejos.append(f"Estos proyectos tienen el plazo pasado: {', '.join(vencidos)}. Pon un plazo nuevo o cambia su estado.")
        cand = [(p, fm) for p, fm in self.info_notas(f"{NOTAS}/Candidaturas") if fm and valor(fm, "tipo") == "candidatura"]
        vencidas = [f"{enlace(self.rel(p))} ({fecha_corta(a_fecha(fm.get('plazo')))})" for p, fm in cand
                    if valor(fm, "estado") not in FINAL_CANDIDATURA and a_fecha(fm.get("plazo")) and a_fecha(fm.get("plazo")) < self.hoy]
        if vencidas:
            consejos.append(f"Estas candidaturas tienen el plazo vencido: {', '.join(vencidas)}. Si ya no siguen, ponlas en «descartada»; si siguen, pon un plazo nuevo.")
        if sin_tipo:
            consejos.append(f"Hay {cuantos(len(sin_tipo), 'nota', 'notas')} sin tipo en 30 Notas: {'no sale' if len(sin_tipo) == 1 else 'no salen'} en tus tablas. Mira el punto 3.")
        if rotos:
            consejos.append(f"Hay {cuantos(len(rotos), 'enlace', 'enlaces')} {'que no lleva' if len(rotos) == 1 else 'que no llevan'} a ninguna nota (punto 3): {'corrígelo' if len(rotos) == 1 else 'corrígelos'} o crea la nota que falta.")
        if not consejos:
            consejos.append("Todo en orden. Sigue así: si dudas dónde va algo, a la Bandeja.")

        def seccion(lineas, nada):
            if not lineas:
                return [nada]
            return lineas[:TOPE] + ([f"- …y {len(lineas) - TOPE} más."] if len(lineas) > TOPE else [])

        pendientes = (f"**Pendiente:** {len(bandeja)} en la Bandeja · {len(sin_tipo)} sin tipo · "
                      f"{cuantos(len(rotos), 'enlace roto', 'enlaces rotos')} · {len(self.no_movidos)} sin mover · "
                      f"{cuantos(len(avisos), 'aviso', 'avisos')}.")
        decidir = len(viejas) + len(sin_tipo) + len(rotos) + len(self.no_movidos) + len(avisos)
        aviso = ("> [!success] Todo en orden: no hay nada que necesite tu decisión." if not decidir else
                 f"> [!warning] {'Hay 1 cosa que necesita' if decidir == 1 else f'Hay {decidir} cosas que necesitan'} tu decisión: mira el punto 3.")
        rotos_txt = [f"- `[[{limpio(d, 100)}]]` en {enlace(r)}" for r, d in rotos]
        bandeja_txt = ["| Nota | Días en la Bandeja |", "|---|--:|"] + [f"| {enlace(self.rel(p), tabla=True)} | {d} |" for d, p in bandeja[:TOPE]]
        if len(bandeja) > TOPE:
            bandeja_txt.append(f"| …y {len(bandeja) - TOPE} más | |")
        sim = "> [!note] SIMULACIÓN: no se ha cambiado nada.\n\n" if self.simular else ""
        partes = [
            f"---\ntipo: informe\nfecha: {self.hoy.isoformat()}\nhora: \"{self.ahora:%H:%M}\"\n---",
            f"{sim}Volver a [[Inicio]] · Lo escribe solo el Ordenador del Cerebro cada mañana a las 05:15: no lo edites, se reescribe entero. "
            f"Cómo funciona todo: [[Cómo usar el Cerebro]].",
            "", "## 1. Resumen de hoy",
            f"**{fecha_larga(self.hoy)}** · revisado a las {self.ahora:%H:%M}.", "", aviso, "", pendientes, "", *tabla,
            "", "## 2. Lo que he ordenado esta noche",
            *(["Lo he puesto en su sitio sin borrar nada:", ""] + seccion([f"- {a}" for a in acciones], "") if acciones else ["Nada: todo estaba en su sitio."]),
            "", "## 3. Lo que necesita tu decisión",
            "### Notas en la Bandeja",
            *(bandeja_txt if bandeja else ["La Bandeja está vacía."]),
            "", "### Notas sin tipo", *seccion(sin_tipo, "Nada: todas las notas de 30 Notas tienen tipo."),
            "", "### Enlaces rotos", *seccion(rotos_txt, "Nada: todos los enlaces llevan a algún sitio."),
            "", "### Lo que no he podido mover", *seccion([f"- {x}" for x in self.no_movidos], "Nada."),
            "", "### Otros avisos", *seccion([f"- {x}" for x in avisos], "Nada."),
            "", "## 4. Lo que ha hecho Zazu", *zazu,
            "", "## 5. Novedades de la semana", *self.novedades(),
            "", "## 6. Consejos para usar bien el Cerebro", *[f"- {c}" for c in consejos], "",
            f"**Consejo del {DIAS[self.hoy.weekday()]}:** {CONSEJOS[self.hoy.weekday()]}", "",
        ]
        return "\n".join(partes).replace("\n\n\n", "\n\n")


def main():
    ap = argparse.ArgumentParser(description="Ordena el Cerebro (vault de Obsidian) y escribe el Informe del Cerebro.")
    ap.add_argument("--simular", action="store_true", help="no cambia nada: dice lo que haría y saca el informe por pantalla")
    ap.add_argument("--vault", type=Path, default=VAULT, help=f"carpeta del vault (por defecto {VAULT})")
    args = ap.parse_args()
    vault = args.vault.expanduser().resolve()
    if not (vault / ".obsidian").is_dir():
        print(f"{vault} no parece un vault de Obsidian (no tiene .obsidian/)", file=sys.stderr)
        return 2
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    cerrojo = open(ESTADO.with_suffix(".lock"), "w")
    try:
        fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Ya hay otro Ordenador del Cerebro en marcha.")
        return 0

    o = Ordenador(vault, args.simular)
    destino, log = vault / INFORME, vault / LOG
    for p in (destino, log):
        if o.por_enlace(p):                           # escribir ahí sería escribir fuera del vault
            print(f"{p} es (o está dentro de) un acceso directo (symlink): no ordeno nada. Quítalo y vuelve a lanzarme.", file=sys.stderr)
            return 1
    try:
        estado = json.loads(ESTADO.read_text())
    except (OSError, ValueError):
        estado = {}
    estado = estado if isinstance(estado, dict) else {}
    previo = estado.get(str(vault)) if isinstance(estado.get(str(vault)), dict) else {}
    pendientes = previo.get("pendientes")
    o.pendientes_antes = pendientes if isinstance(pendientes, dict) else {}
    o.ordenar()
    # lo ordenado hoy se acumula (si se lanza dos veces el mismo día, el informe no pierde lo de la noche)
    antes = previo.get("acciones", []) if previo.get("fecha") == o.hoy.isoformat() and not args.simular else []
    for r in o.salidas:                               # lo que se movió en una pasada anterior de hoy y ahora otra vez
        antes = desenlazar(antes, r)
    acciones = list(dict.fromkeys(antes + o.hecho))
    texto = o.informe(acciones)
    if args.simular:
        for x in o.no_movidos:
            print(f"(simulación) sin mover: {x}")
        print("\n========== INFORME (simulación, no se guarda) ==========\n")
        print(texto)
        return 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    if leer(destino) != texto:
        escribir(destino, texto, stat.S_IMODE(destino.lstat().st_mode) if destino.exists() else 0o664)
    estado[str(vault)] = {"fecha": o.hoy.isoformat(), "acciones": acciones, "pendientes": o.pendientes}
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False))
    if o.movs or o.fichas or o.enlaces or o.quitadas:
        extra = ((f", {cuantos(o.enlaces, 'enlace arreglado', 'enlaces arreglados')}" if o.enlaces else "")
                 + (f", {cuantos(o.quitadas, 'carpeta vacía quitada', 'carpetas vacías quitadas')}" if o.quitadas else ""))
        linea = (f"- {o.hoy.isoformat()} · Ordenador del Cerebro: {cuantos(o.movs, 'movimiento', 'movimientos')}, "
                 f"{cuantos(o.fichas, 'ficha completada', 'fichas completadas')}{extra}. Páginas: Informe del Cerebro.\n")
        previo_log = leer(log) or ""
        nl = "\r\n" if "\r\n" in previo_log else "\n"             # con los saltos de línea que ya tenga
        with open(log, "a", encoding="utf-8", newline="") as f:
            f.write((nl if previo_log and not previo_log.endswith("\n") else "") + linea.replace("\n", nl))
    for x in o.no_movidos:
        print(f"sin mover: {x}")
    print(f"Ordenador del Cerebro: {o.movs} movimientos, {o.fichas} fichas completadas, {o.enlaces} enlaces arreglados, "
          f"{o.quitadas} carpetas vacías quitadas, {len(o.no_movidos)} sin mover. Informe: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
