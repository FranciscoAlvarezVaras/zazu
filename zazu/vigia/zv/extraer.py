"""Extracción DETERMINISTA (sin IA) de fecha, hora e importe en textos en español de España (zona Europe/Madrid).
Regla de oro: si hay ambigüedad NO se adivina; se devuelve None y el motivo, y quien llama se limita a avisar.
  · Fechas: 15/10/2026, 15-10-26, 15/10, 15.10.2026, 2026-10-15, «15 de octubre (de 2026)», «15 oct», «October 15, 2026».
    Sin año: la próxima vez que ocurra (una fecha pasada hace poco se descarta; una pasada hace más de 60 días es del año que viene).
    Las pasadas y las que están a más de 400 días se descartan. dd/mm/aaaa es el orden español; si ambos números son ≤12 y el texto
    parece inglés, la fecha es ambigua y no se usa.
  · Horas: 10:30, 10h30, 10 h, «a las 10.30», «a las 5 de la tarde», 5 pm. Se asignan a la fecha más cercana; con varias horas
    distintas para la misma fecha → sin hora (ambigua). 00:00 no cuenta (suele ser un marcador vacío).
  · Importes: 49,99 €, 1.234,56 euros, 49.99 EUR, € 12. Entre varios se elige el marcado como total / a pagar; si no, ambiguo.
El texto es dato de terceros: aquí solo se leen números; nada se interpreta como orden y no se devuelve ningún trozo del texto."""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

I = re.I
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
         "octubre": 10, "noviembre": 11, "diciembre": 12, "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8,
         "sep": 9, "sept": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
         "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
         "november": 11, "december": 12, "jan": 1, "apr": 4, "aug": 8, "dec": 12}
_MES = "|".join(sorted(MESES, key=len, reverse=True))
_MES_EN = "january|february|march|april|may|june|july|august|september|october|november|december"

RE_ISO = re.compile(r"(?<![\w/.:-])(20\d\d)-(\d\d)-(\d\d)(?![\w])")
RE_NUM = re.compile(r"(?<![\w/.:-])(\d{1,2})([/.-])(\d{1,2})(?:\2(\d{4}|\d{2}))?(?![\w]|[/.-]\d)")
RE_TXT = re.compile(rf"(?<![\w])(\d{{1,2}})\s?(?:º|°)?\s*(?:de\s+)?({_MES})\b\.?(?:\s*(?:de|del|,)?\s*(\d{{4}})(?!\d))?", I)
RE_EN = re.compile(rf"\b({_MES_EN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?(?!\d)", I)

SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}
RE_SEM = re.compile(rf"(?<![\w])(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo),?\s+(?:el\s+)?(?:d[ií]a\s+)?(\d{{1,2}})(?!\d)"
                    rf"(?![/:.\-]\d)(?!\s*(?:de\s+)?(?:{_MES})\b)", I)

RE_HORA = re.compile(r"(?<![\d:.,/-])([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?(?![\d:])", I)
RE_HORA_H = re.compile(r"(?<![\d:.,/-])([01]?\d|2[0-3])\s?h(?:oras?|rs?)?(?:\s?([0-5]\d))?(?![\w])", I)
RE_A_LAS = re.compile(r"\ba las?\s+([01]?\d|2[0-3])(?:[.:h]([0-5]\d))?(?![\d]|[.,]\d)", I)
RE_PM = re.compile(r"^\s*(?:de la (?:tarde|noche)|p\.?\s?m\b\.?)", I)
RE_AM = re.compile(r"^\s*(?:de la (?:ma[ñn]ana|madrugada)|a\.?\s?m\b\.?)", I)

RE_NUMERO = r"(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
RE_IMPORTE = re.compile(rf"(?<![\d.,])({RE_NUMERO})\s?(?:€|eur\b|euros?\b)|(?:€|eur\b)\s?({RE_NUMERO})(?![\d])", I)

ES = re.compile(r"\b(el|la|los|las|de|del|su|tu|para|con|por|que|una?|factura|reserva|cita|pago|importe|fecha|hora|vencimiento|billete|usted|hola|estimado)\b", I)
EN = re.compile(r"\b(the|your|you|for|and|please|booking|invoice|payment|due|date|time|confirmation|dear|hello|thank|will|is|are)\b", I)


def idioma_es(texto):
    """True si el texto parece español (o no se puede saber); False si claramente es inglés."""
    return len(ES.findall(texto or "")) >= len(EN.findall(texto or ""))


@dataclass
class Fecha:
    fecha: date
    hora: str = None
    hora_ambigua: bool = False
    pos: bool = False
    neg: bool = False
    dm_ambiguo: bool = False
    ini: int = 0
    fin: int = 0
    horas: set = field(default_factory=set)


def _resuelve(d, m, y, hoy):
    """(date|None). Sin año → próxima ocurrencia; fuera de rango o imposible → None."""
    try:
        if m < 0:                              # «martes 13»: m codifica el día de la semana (-1 = lunes …)
            sem = -m - 1
            f = next((x for x in (hoy + timedelta(days=i) for i in range(0, 400)) if x.day == d and x.weekday() == sem), None)
            return f
        if y is None:
            f = date(hoy.year, m, d)
            if f < hoy:
                if (hoy - f).days <= 60:
                    return None
                f = date(hoy.year + 1, m, d)
        else:
            f = date(y + 2000 if y < 100 else y, m, d)
    except ValueError:
        return None
    return f if hoy <= f <= hoy + timedelta(days=400) else None


def _crudas(texto):
    """[(ini, fin, d, m, y|None, dm_ambiguo, valida_estructura)] de todas las apariciones con forma de fecha."""
    out = []
    for r in RE_ISO.finditer(texto):
        out.append((r.start(), r.end(), int(r.group(3)), int(r.group(2)), int(r.group(1)), False))
    for r in RE_NUM.finditer(texto):
        a, sep, b, y = int(r.group(1)), r.group(2), int(r.group(3)), r.group(4)
        if sep != "/" and not y:
            continue                          # «10.30» o «1-2» no son fechas
        if a > 31 or b > 12 or a == 0 or b == 0:
            continue                          # mm/dd (inglés americano) no se adivina
        out.append((r.start(), r.end(), a, b, int(y) if y else None, a <= 12 and b <= 12 and a != b))
    for r in RE_TXT.finditer(texto):
        out.append((r.start(), r.end(), int(r.group(1)), MESES[r.group(2).lower()], int(r.group(3)) if r.group(3) else None, False))
    for r in RE_EN.finditer(texto):
        out.append((r.start(), r.end(), int(r.group(2)), MESES[r.group(1).lower()], int(r.group(3)) if r.group(3) else None, False))
    for r in RE_SEM.finditer(texto):           # «el martes 13» (sin mes): el primer martes día 13 desde hoy
        out.append((r.start(), r.end(), int(r.group(2)), -SEMANA[r.group(1).lower()] - 1, None, False))
    out.sort()
    res, ult = [], -1
    for x in out:                              # sin solapes (ISO frente a numérica, etc.)
        if x[0] >= ult:
            res.append(x); ult = x[1]
    return res


def _horas(texto):
    """[(ini, fin, 'HH:MM')] sin solapes."""
    c = []
    for rx in (RE_HORA, RE_A_LAS, RE_HORA_H):
        for r in rx.finditer(texto):
            h, m = int(r.group(1)), int(r.group(2) or 0)
            resto = texto[r.end():r.end() + 22]
            if RE_PM.match(resto) and h < 12:
                h += 12
            elif RE_AM.match(resto) and h == 12:
                h = 0
            if (h, m) == (0, 0):
                continue
            c.append((r.start(), r.end(), f"{h:02d}:{m:02d}"))
    c.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out, ult = [], -1
    for x in c:
        if x[0] >= ult:
            out.append(x); ult = x[1]
    return out


def candidatos_fecha(texto, hoy, pos=None, neg=None):
    """Todas las fechas utilizables del texto (futuras, ≤400 días), unidas por día. `pos`/`neg`: regex de palabras que, justo antes
    o después de la fecha, la marcan como la buscada (p. ej. «vencimiento») o como otra cosa (p. ej. «emisión»)."""
    texto = texto or ""
    crudas = _crudas(texto)
    horas = _horas(texto)
    asignadas = {i: set() for i in range(len(crudas))}
    for hi, hf, hh in horas:                   # cada hora a la fecha más cercana (tras la fecha ≤70 car., antes ≤30)
        mejor = None
        for i, (ci, cf, *_r) in enumerate(crudas):
            d = hi - cf if hi >= cf else (ci - hf if hf <= ci else None)
            lim = 70 if hi >= cf else 30
            if d is not None and d <= lim and (mejor is None or (d, 0 if hi >= cf else 1) < mejor[0]):
                mejor = ((d, 0 if hi >= cf else 1), i)
        if mejor:
            asignadas[mejor[1]].add(hh)
    por_dia = {}
    for i, (ini, fin, d, m, y, dm) in enumerate(crudas):
        f = _resuelve(d, m, y, hoy)
        if f is None:
            continue
        ant = crudas[i - 1][1] if i else 0
        sig = crudas[i + 1][0] if i + 1 < len(crudas) else len(texto)
        pre, post = texto[max(ant, ini - 45):ini], texto[fin:min(sig, fin + 25)]
        es_pos = bool(pos and (pos.search(pre) or pos.search(post)))
        es_neg = bool(neg and neg.search(pre[-40:]))
        c = por_dia.setdefault(f, Fecha(f, ini=ini, fin=fin, neg=True))
        c.pos = c.pos or (es_pos and not es_neg)
        c.neg = c.neg and es_neg
        c.dm_ambiguo = c.dm_ambiguo or dm
        c.horas |= asignadas[i]
    for c in por_dia.values():
        if len(c.horas) == 1:
            c.hora = next(iter(c.horas))
        elif len(c.horas) > 1:
            c.hora_ambigua = True
    return sorted(por_dia.values(), key=lambda c: c.fecha)


def elegir(cands, texto=""):
    """→ (Fecha|None, motivo). motivo: ok | sin_fecha | ambigua | formato_ambiguo."""
    fuertes = [c for c in cands if c.pos and not c.neg]
    pool = fuertes or [c for c in cands if not c.neg]
    if not pool:
        return None, "sin_fecha"
    if len(pool) > 1:
        return None, "ambigua"
    c = pool[0]
    if c.dm_ambiguo and not idioma_es(texto):
        return None, "formato_ambiguo"
    return c, "ok"


def elegir_varias(cands, texto="", maxn=2):
    """Para reservas de viaje (ida y vuelta): hasta `maxn` fechas MARCADAS (palabras de viaje) o la única que haya.
    → (lista de Fecha, motivo)."""
    fuertes = [c for c in cands if c.pos and not c.neg]
    pool = fuertes or [c for c in cands if not c.neg]
    if not pool:
        return [], "sin_fecha"
    if len(pool) > maxn or (not fuertes and len(pool) > 1):
        return [], "ambigua"
    if any(c.dm_ambiguo for c in pool) and not idioma_es(texto):
        return [], "formato_ambiguo"
    return pool, "ok"


# ───────── importes ─────────
def _num(tok):
    if "," in tok:
        tok = tok.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", tok):
        tok = tok.replace(".", "")
    return Decimal(tok)


def formato_importe(v):
    """Decimal → «49,99 €» / «1.234 €» (formato español)."""
    ent, _, dec = f"{v:.2f}".partition(".")
    ent = f"{int(ent):,}".replace(",", ".")
    return f"{ent},{dec} €" if dec != "00" else f"{ent} €"


def importe(texto, pos=None, neg=None):
    """→ (texto_importe|None, motivo). motivo: ok | sin_importe | ambiguo."""
    texto = texto or ""
    cands = {}
    ant = 0
    for r in RE_IMPORTE.finditer(texto):
        ini_prev, ant = ant, r.end()
        try:
            v = _num(r.group(1) or r.group(2))
        except InvalidOperation:
            continue
        if not (0 < v < 1_000_000):
            continue
        pre = texto[max(ini_prev, r.start() - 45):r.start()]       # sin pasar por encima del importe anterior
        es_pos = bool(pos and pos.search(pre))
        es_neg = bool(neg and neg.search(pre[-30:]))
        c = cands.setdefault(v, [False, True])
        c[0] = c[0] or (es_pos and not es_neg)
        c[1] = c[1] and es_neg
    fuertes = [v for v, (p, n) in cands.items() if p and not n]
    pool = fuertes or [v for v, (p, n) in cands.items() if not n]
    if not pool:
        return None, "sin_importe"
    if len(pool) > 1:
        return None, "ambiguo"
    return formato_importe(pool[0]), "ok"


def fecha_corta(f):
    return f"{f:%d/%m}"
