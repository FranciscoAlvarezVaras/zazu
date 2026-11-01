"""Modelo común de oferta: todas las fuentes devuelven Oferta con los mismos campos. Así puntuar.py y db.py no saben de APIs."""
import hashlib, html, re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class Oferta:
    fuente: str          # arbeitnow, remotive, remoteok, jobicy, themuse, himalayas, adzuna, eures…
    titulo: str
    empresa: str
    url: str
    lugar: str = ""      # ciudad / país / «Remote»
    pais: str = ""       # código ISO si se sabe (ES, DE, …) o "EU"/"REMOTE"
    remoto: bool = False
    fecha: str = ""      # AAAA-MM-DD
    descripcion: str = ""  # texto plano, recortado
    etiquetas: list = field(default_factory=list)
    salario: str = ""
    pista: str = ""      # dev | marketing (lo pone puntuar.py)
    puntos: int = 0      # 0–100 (lo pone puntuar.py)

    @property
    def id(self):
        """Identidad estable: misma oferta en dos fuentes = mismo id (título+empresa normalizados)."""
        base = re.sub(r"[^a-z0-9]+", " ", f"{self.titulo} {self.empresa}".lower()).strip()
        return hashlib.sha1(base.encode()).hexdigest()[:16]

    def dict(self):
        d = asdict(self); d["id"] = self.id; return d


def limpiar_html(t):
    t = re.sub(r"<(script|style).*?</\1>", " ", str(t or ""), flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\xa0", " ")   # antes solo 5 entidades: «&aacute;», «&#225;», «&quot;» o «&eacute;» se quedaban escritas tal cual y no casaban con las palabras del perfil
    return re.sub(r"\s+", " ", t).strip()


def fecha_iso(valor):
    """Acepta ISO, epoch, 'YYYY-MM-DD…' → 'YYYY-MM-DD' (o '' si no se entiende)."""
    if valor in (None, ""):
        return ""
    if isinstance(valor, (int, float)):
        try: return datetime.fromtimestamp(float(valor), tz=timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, ValueError): return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(valor))
    return m.group(1) if m else ""
