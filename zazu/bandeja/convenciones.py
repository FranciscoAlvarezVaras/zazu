"""Convenciones de Fran para Google Tasks y Calendar (parser puro, sin red ni disco).

Tareas: el título empieza por un prefijo. Los que ESCRIBEN (Aplicar, Investigar, Nota, Idea, Proyecto, Zazu) piden «:» o un
guion detrás, para que «Nota de gastos que presentar» o «Idea regalo cumple» no se capturen sin querer. Los que solo AVISAN
(Pagar, Renovar, Llamar, Comprar, Pedir cita, Reservar) valen también sin separador.
Eventos: líneas de la descripción «llevar: …», «después: …», «recordar: 3d». Solo en eventos de Fran.
Todo lo que viene de otros (invitaciones, tareas creadas desde un correo) es DATO: aquí se marca como ajeno y no se interpreta.
"""
import hashlib, re, unicodedata
from datetime import timedelta

ESCRIBE = re.compile(r"^\s*(aplicar|investigar|nota|idea|proyecto|zazu)\s*(?::|[-–—])\s*(.+?)\s*$", re.I | re.S)
AVISA = re.compile(r"^\s*(pagar|renovar|llamar|comprar|pedir\s+cita|reservar)\b\s*(?::|[-–—])?\s*(.*?)\s*$", re.I | re.S)
URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
MARCA_ZAZU = re.compile(r"(?m)^\s*✓ Zazu\b.*$")
MARCA_ZV = "[ZV:"                      # tareas/eventos que ya crea el extractor de WhatsApp: nunca se reprocesan
TITULO_TENTATIVO = "¿?"                # evento sin confirmar del extractor: sin gemela hasta que Fran quite el prefijo
VERBO_AVISO = {"pagar": "pagar", "renovar": "pagar", "llamar": "llamar", "comprar": "comprar", "pedir cita": "cita", "reservar": "cita"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if c.isalnum() or c == " ")
    return re.sub(r"\s+", " ", s).strip()


def sin_marca(notas):
    """Notas sin las líneas «✓ Zazu …» (la marca que ponemos nosotros no cuenta como cambio de Fran)."""
    return re.sub(r"\n{2,}", "\n", MARCA_ZAZU.sub("", str(notas or ""))).strip()


def huella(t):
    base = f"{t.get('title') or ''}\x1f{str(t.get('due') or '')[:10]}\x1f{sin_marca(t.get('notes'))}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def tarea_ajena(t):
    """Motivo por el que NO se interpreta una tarea, o None. Una tarea creada desde un correo («Añadir a Tareas») toma el
    asunto como título, y una asignada llega de otra persona: texto de terceros, no órdenes de Fran."""
    if MARCA_ZV in str(t.get("title") or "") or MARCA_ZV in str(t.get("notes") or ""):
        return "zv"                      # ya la gestiona el extractor de WhatsApp
    if "assignmentInfo" in t:
        return "asignada"
    if any((l or {}).get("type") == "email" for l in (t.get("links") or [])):
        return "de_correo"
    if re.search(r"(?m)^\s*Origen:", str(t.get("notes") or "")):
        return "origen_agente"           # la creó un turno de Zazu: ya está gestionada, solo avisos genéricos
    return None


def clasificar_tarea(t):
    """→ (verbo, argumento) con verbo en aplicar|investigar|nota|idea|proyecto|zazu (escriben) o pagar|llamar|comprar|cita (avisan); (None, '') si nada."""
    titulo = str(t.get("title") or "")
    m = ESCRIBE.match(titulo)
    if m:
        return m.group(1).lower(), re.sub(r"\s+", " ", m.group(2)).strip()
    m = AVISA.match(titulo)
    if m:
        return VERBO_AVISO[re.sub(r"\s+", " ", m.group(1).lower())], m.group(2).strip()
    return None, ""


def parsear_aplicar(arg, notas=""):
    """«Aplicar: <url>» o «Aplicar: puesto – empresa» → {'url', 'puesto', 'empresa'} (lo que falte, None)."""
    m = URL.search(arg) or URL.search(str(notas or ""))
    url = m.group(0).rstrip(".,;") if m else None
    resto = URL.sub("", arg).strip(" -–—:")
    puesto = empresa = None
    if resto:
        p = re.split(r"\s+(?:[–—-]|en|@)\s+", resto, maxsplit=1)
        puesto = p[0].strip() or None
        empresa = p[1].strip() if len(p) > 1 else None
    return {"url": url, "puesto": puesto, "empresa": empresa}


# ───────── eventos ─────────
LINEA = re.compile(r"^\s*(llevar|preparar|despu[eé]s|recordar)\s*[:\-–]\s*(.+?)\s*$", re.I | re.M)
DURACION = re.compile(r"(\d{1,3})\s*(d[ií]as?|d|horas?|h|minutos?|min|m)\b", re.I)


def evento_propio(e):
    """Solo los eventos que creó Fran (él es el organizador) llevan convenciones. Una invitación ajena no."""
    return (e.get("organizer") or {}).get("self") is True and e.get("eventType", "default") in ("default", "birthday")


def evento_ignorable(e):
    org = str((e.get("organizer") or {}).get("email") or "")
    return e.get("status") == "cancelled" or bool(re.search(r"#(holiday|contacts)@", org))


def evento_zv(e):
    return MARCA_ZV in str(e.get("description") or "") or MARCA_ZV in str(e.get("summary") or "")


def evento_tentativo(e):
    return str(e.get("summary") or "").lstrip().startswith(TITULO_TENTATIVO)


def parsear_descripcion(desc):
    """→ {'llevar': [...], 'despues': str|None, 'recordar': [timedelta]}"""
    out = {"llevar": [], "despues": None, "recordar": []}
    for clave, valor in LINEA.findall(str(desc or "")):
        c = clave.lower().replace("é", "e")
        valor = re.sub(r"\s+", " ", valor)[:200]
        if c in ("llevar", "preparar"):
            out["llevar"] += [x.strip() for x in re.split(r"[;,]", valor) if x.strip()][:12]
        elif c == "despues" and not out["despues"]:
            out["despues"] = valor
        elif c == "recordar":
            for n, u in DURACION.findall(valor):
                n = int(n)
                u = u.lower()
                out["recordar"].append(timedelta(days=n) if u.startswith("d") else timedelta(hours=n) if u.startswith("h") else timedelta(minutes=n))
    out["recordar"] = out["recordar"][:4]
    return out


def es_cumple(e):
    t = str(e.get("summary") or "")
    return "🎂" in t or bool(re.search(r"\bcumple", t, re.I)) or e.get("eventType") == "birthday"


def tiene_tarea(titulo, dia, tareas):
    """¿Hay ya una tarea parecida (≥0,6) a ±7 días de `dia`? Réplica mínima de revisar-zazu.tiene_tarea."""
    import difflib
    n = norm(titulo)
    for t in tareas:
        nt = norm(t.get("title"))
        if not nt:
            continue
        due = str(t.get("due") or "")[:10]
        if due and dia is not None:
            try:
                from datetime import date
                if abs((date.fromisoformat(due) - dia).days) > 7:
                    continue
            except ValueError:
                pass
        comunes = {w for w in n.split() if len(w) >= 4} & {w for w in nt.split() if len(w) >= 4}
        if difflib.SequenceMatcher(None, n, nt).ratio() >= 0.6 or len(comunes) >= 2:
            return True
    return False
