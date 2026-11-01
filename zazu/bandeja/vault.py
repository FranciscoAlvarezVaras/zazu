"""Escritura SEGURA en el Cerebro (/home/server/Cerebro) siguiendo 90 Sistema/SCHEMA.md.
Reglas en código: solo notas NUEVAS (O_EXCL, nunca sobrescribe), a partir de la plantilla del tipo, en la carpeta del tipo
(las carpetas deben existir: no se crean), nombre único en todo el vault y no reservado, sin símbolos prohibidos, ≤80
caracteres, sin acceso directos (symlinks), y NADA que privacidad.tachar() cambiaría (claves, teléfonos, DNI, cuentas…).
Las únicas ediciones de notas existentes son líneas añadidas: «## Historial» de Buscar trabajo, index.md y log.md.
Con escribir=False (modo sombra) cualquier escritura lanza PermissionError."""
import difflib, os, re, sys, tempfile
from pathlib import Path

import config
sys.path.insert(0, str(config.SCRIPTS))

CARPETA = {"nota": "10 Bandeja", "idea": "30 Notas/Ideas", "proyecto": "30 Notas/Proyectos", "candidatura": "30 Notas/Candidaturas"}
PLANTILLA = {"nota": "Nota", "idea": "Idea", "proyecto": "Proyecto", "candidatura": "Candidatura"}
SECCION_INDEX = {"idea": "Ideas", "proyecto": "Proyectos", "candidatura": "Candidaturas"}
RESERVADOS = {"diario", "nota", "idea", "proyecto", "candidatura", "persona", "empresa", "tema", "lectura", "proyectos", "candidaturas",
              "ideas", "personas y empresas", "temas y lecturas", "bandeja", "archivos", "relacionado", "zazu", "inicio",
              "como usar el cerebro", "informe del cerebro", "agents", "schema", "index", "log", "rutinas", "memoria", "estado", "mapa"}
PROHIBIDOS = re.compile(r'[/\\:*?"<>|#^\[\]]')


class Privado(ValueError):
    """El texto contiene algo que el Cerebro nunca guarda."""


class Existe(FileExistsError):
    pass


def tachar(t):
    from privacidad import tachar as _t
    return _t(t)


def limpiar_nombre(s, maximo=77):
    s = PROHIBIDOS.sub(" ", str(s or ""))
    s = re.sub(r"[\x00-\x1f]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:maximo].strip(" .")


def yaml_val(v):
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(x if str(x).startswith('"') else (f'"{x}"' if "[[" in str(x) else str(x)) for x in v) + "]"
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    if v and re.search(r"(^[\s'\"\[\]{}&*!|>%@`#-])|: | #|\s$", v):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


def norm(s):
    from convenciones import norm as n
    return n(s)


def url_clave(u):
    u = str(u or "").strip()
    m = re.search(r"linkedin\.com(?:/[^?]*?)?/jobs/view/(?:[^/?]*-)?(\d{6,})", u) or re.search(r"[?&]currentJobId=(\d{6,})", u)
    if m:
        return "li:" + m.group(1)
    return re.sub(r"[?#].*$", "", u).rstrip("/").lower()


class Vault:
    def __init__(self, raiz=None, escribir=False):
        self.raiz = Path(raiz or config.vault())
        self.escribir = escribir
        self.tocadas = []

    # ── seguridad ──
    def _exige(self):
        if not self.escribir:
            raise PermissionError("modo sombra: no se escribe en el Cerebro")

    def _dentro(self, ruta):
        ruta = Path(ruta)
        r = Path(os.path.abspath(ruta))
        if self.raiz not in r.parents:
            raise PermissionError("fuera del Cerebro")
        p = r
        while p != self.raiz:
            if p.is_symlink():
                raise PermissionError("acceso directo (symlink) en la ruta")
            p = p.parent
        return r

    def _revisar(self, texto):
        if tachar(texto) != texto:
            raise Privado("el texto lleva algo que el Cerebro no guarda (clave, teléfono, DNI, cuenta…)")

    def _atomico(self, ruta, texto):
        fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".zb-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, ruta)

    # ── búsqueda ──
    def notas(self):
        for p in self.raiz.rglob("*.md"):
            if not any(x.startswith(".") for x in p.relative_to(self.raiz).parts):
                yield p

    def existe_nombre(self, nombre):
        n = norm(nombre)
        return any(norm(p.stem) == n for p in self.notas())

    def frontmatter(self, ruta):
        try:
            t = Path(ruta).read_text(encoding="utf-8")
        except OSError:
            return {}
        m = re.match(r"﻿?---\r?\n(.*?)\r?\n---", t, re.S)
        fm = {}
        for ln in (m.group(1).splitlines() if m else []):
            k, _, v = ln.partition(":")
            fm[k.strip()] = v.strip().strip('"')
        return fm

    def buscar_candidatura(self, url=None, empresa=None, puesto=None):
        d = self.raiz / CARPETA["candidatura"]
        for p in sorted(d.glob("*.md")) if d.is_dir() else []:
            fm = self.frontmatter(p)
            if url and fm.get("enlace") and url_clave(fm["enlace"]) == url_clave(url):
                return p
            if empresa and puesto and fm.get("empresa") and fm.get("puesto"):
                if norm(fm["empresa"]) == norm(empresa) and difflib.SequenceMatcher(None, norm(fm["puesto"]), norm(puesto)).ratio() >= 0.85:
                    return p
        return None

    def buscar_proyecto(self, nombre):
        d = self.raiz / CARPETA["proyecto"]
        return next((p for p in d.glob("*.md") if norm(p.stem) == norm(nombre)), None) if d.is_dir() else None

    def buscar_nota_exacta(self, carpeta_clave, nombre):
        d = self.raiz / CARPETA[carpeta_clave]
        return next((p for p in d.glob("*.md") if norm(p.stem) == norm(nombre)), None) if d.is_dir() else None

    # ── crear ──
    def render(self, tipo, campos, reemplazos=None, extra=""):
        hoy = config.ahora().strftime("%Y-%m-%d")
        t = (self.raiz / "90 Sistema/Plantillas" / f"{PLANTILLA[tipo]}.md").read_text(encoding="utf-8").replace("{{date}}", hoy)
        m = re.match(r"---\n(.*?)\n---\n?(.*)", t, re.S)
        fm, cuerpo = m.group(1).split("\n"), m.group(2)
        vistas, out = set(), []
        for ln in fm:
            k = ln.split(":", 1)[0].strip()
            vistas.add(k)
            out.append(f"{k}: {yaml_val(campos[k])}".rstrip() if k in campos else ln)
        out += [f"{k}: {yaml_val(v)}".rstrip() for k, v in campos.items() if k not in vistas]
        for a, b in (reemplazos or {}).items():
            cuerpo = cuerpo.replace(a, b)
        return "---\n" + "\n".join(out) + "\n---\n" + cuerpo.rstrip("\n") + ("\n" + extra.rstrip("\n") if extra else "") + "\n"

    def crear_nota(self, tipo, nombre, campos, reemplazos=None, extra=""):
        """→ ruta nueva. Existe si ya hay una nota con ese nombre en el vault (no se crea otra)."""
        self._exige()
        nombre = limpiar_nombre(nombre)
        if not nombre:
            raise ValueError("nombre vacío")
        if norm(nombre) in RESERVADOS:
            nombre = f"{nombre} ({tipo})"
        if self.existe_nombre(nombre):
            raise Existe(nombre)
        d = self.raiz / CARPETA[tipo]
        if not d.is_dir():
            raise PermissionError("la carpeta no existe (no se crean carpetas)")
        ruta = self._dentro(d / f"{nombre}.md")
        texto = self.render(tipo, campos, reemplazos, extra)
        self._revisar(texto)
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        self.tocadas.append(str(ruta.relative_to(self.raiz)))
        return ruta

    def anadir_seccion(self, ruta, texto):
        """Añade al final de una nota NUEVA nuestra (la carta) una sección; solo notas que creamos en esta pasada."""
        self._exige()
        ruta = self._dentro(ruta)
        self._revisar(texto)
        t = ruta.read_text(encoding="utf-8")
        self._atomico(ruta, t.rstrip("\n") + "\n\n" + texto.strip("\n") + "\n")

    # ── líneas en notas compartidas ──
    def historial(self, ruta, linea):
        """Línea nueva arriba del todo en «## Historial» (SCHEMA)."""
        self._exige()
        ruta = self._dentro(ruta)
        self._revisar(linea)
        t = ruta.read_text(encoding="utf-8")
        m = re.search(r"(?m)^## Historial[ \t]*\r?\n", t)
        t = (t[:m.end()] + linea.rstrip("\n") + "\n" + t[m.end():]) if m else t.rstrip("\n") + "\n\n## Historial\n" + linea.rstrip("\n") + "\n"
        self._atomico(ruta, t)

    def indice(self, tipo, nombre, descripcion):
        """Línea en 90 Sistema/index.md, sección del tipo, por orden alfabético; sube «Total»."""
        sec = SECCION_INDEX.get(tipo)
        if not sec:
            return
        self._exige()
        ruta = self._dentro(self.raiz / "90 Sistema/index.md")
        t = ruta.read_text(encoding="utf-8")
        if f"[[{nombre}]]" in t:
            return
        nueva = f"- [[{nombre}]] — {re.sub(chr(10), ' ', descripcion)[:120]}"
        self._revisar(nueva)
        lineas = t.split("\n")
        try:
            i = lineas.index(f"## {sec}")
        except ValueError:
            return
        j = i + 1
        while j < len(lineas) and not lineas[j].startswith("## "):
            j += 1
        fin = j
        while fin > i + 1 and not lineas[fin - 1].strip():
            fin -= 1
        pos = fin
        for k in range(i + 1, fin):
            if lineas[k].startswith("- [[") and norm(lineas[k][4:]) > norm(nombre):
                pos = k
                break
        lineas.insert(pos, nueva)
        t = "\n".join(lineas)
        hoy = config.ahora().strftime("%Y-%m-%d")
        t = re.sub(r"Total: (\d+) notas · Última actualización: \S+", lambda m: f"Total: {int(m.group(1)) + 1} notas · Última actualización: {hoy}", t, count=1)
        t = re.sub(r"(?m)^actualizado: .*$", f"actualizado: {hoy}", t, count=1)
        self._atomico(ruta, t)

    def log(self, texto, tocadas=""):
        self._exige()
        ruta = self._dentro(self.raiz / "90 Sistema/log.md")
        hoy = config.ahora().strftime("%Y-%m-%d")
        linea = f"- {hoy} · Zazu (bandeja de tareas) · {texto}" + (f" · notas tocadas: {tocadas}" if tocadas else "")
        self._revisar(linea)
        t = ruta.read_text(encoding="utf-8")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(("" if t.endswith("\n") else "\n") + linea + "\n")
