"""Extracción DETERMINISTA (sin IA) de gastos en correos: importe con moneda, fecha del cargo, comercio, categoría y tipo.
Lo usa gastos.py. Es una biblioteca PURA: no lee Google, no escribe nada y no llama al modelo. El texto es dato de terceros: aquí solo
se leen números, fechas y palabras; nada se interpreta como orden y no se devuelve ningún trozo del cuerpo (solo el nombre del comercio,
ya limpio, y cifras).

Regla de oro: si hay ambigüedad NO se adivina. Sin importe claro → no es un gasto. Sin veredicto claro (recibo o publicidad) → «dudoso»
(solo el modelo, con su presupuesto, puede deshacer la duda; sin presupuesto queda como «sin clasificar»).

  · Importes: «27,12 €», «€27.12», «24,99 USD», «EUR 9,99», «US$30,24», «1.250,00 €», «€1,250.00», «9,99€», «$9.99», «1250 euros».
    Entre varios se elige el marcado como pagado/total; si siguen siendo varios distintos, es ambiguo.
  · Fecha del cargo: la del correo, salvo que el texto traiga una «fecha de pago/cargo» pasada y clara. «Próximo pago» → `proximo`.
  · Comercio: tabla de comercios conocidos (remitente/dominio), procesadores (Stripe, PayPal…: se mira el asunto), bancos (se mira «en X»).
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from . import extraer

I = re.I

CATEGORIAS = ("suscripciones", "vivienda", "coche", "comida", "salud", "ocio", "trámites", "otros")
SIN_CLASIFICAR = "sin_clasificar"
TIPOS = ("cargo", "renovacion", "factura", "reembolso")
MONEDAS = ("EUR", "USD", "GBP")

# ───────────────────────── importes ─────────────────────────
_NUM = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_PRE = re.compile(r"(?<![\w$€£.,])(?P<m>US\$|[€$£]|EUR|USD|GBP)(?![A-Za-z])\s?(?P<s>[-−–])?\s?(?P<n>" + _NUM + r")(?!\d|[.,]\d)", I)
_POST = re.compile(r"(?<![\w.,])(?P<s>[-−–]\s?)?(?P<n>" + _NUM + r")\s?(?P<m>US\$(?!\s?\d)|[$£](?!\s?\d)|€(?!\d)|EUR\b|USD\b|GBP\b|euros?\b|d[óo]lares?\b|libras?\b)", I)
_MON = {"€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "$": "USD", "us$": "USD", "usd": "USD", "dolar": "USD", "dolares": "USD", "dólar": "USD",
        "dólares": "USD", "£": "GBP", "gbp": "GBP", "libra": "GBP", "libras": "GBP"}

_PAGADO = re.compile(r"amount\s+paid|\bpaid\b|has\s+pagado|pagaste|you\s+paid|importe\s+(?:pagado|cobrado|cargado|abonado)|total\s+(?:pagado|cobrado|cargado|abonado|charged|paid)|"
                     r"\bcobrad[oa]|\bcargad[oa]|\bcharged\b|pago\s+(?:de|realizado|recibido|por)|payment\s+(?:of|received|successful|amount)|cargo\s+(?:de|por|en)|"
                     r"cobro\s+(?:de|por)|se\s+ha\s+(?:cargado|cobrado)|hemos\s+(?:cobrado|cargado)|abonad[oa]|adeudo\s+(?:de|por)|reembolso\s+de|refund\s+of", I)
_TOTAL = re.compile(r"total|importe|amount|monto|a\s+pagar|\bcuota\b|\bprice\b|precio|billed|facturad[oa]|\bpvp\b", I)
_NEG_FUERTE = re.compile(r"aprox\w*|\bapprox\w*|[≈~]|equivalente|equivalent|convertid\w*|conversi[oó]n|tipo\s+de\s+cambio|exchange\s+rate|\bi\.?v\.?a\b(?!\s*(?:incl|included))|\bvat\b(?!\s*(?:incl|included))|\btax(?:es)?\b(?!\s*(?:incl|included))|impuestos?(?!\s*(?:incl|included))|"
                         r"subtotal|sub-total|base\s+imponible|descuentos?|discount|ahorr\w*|saving|env[ií]o|shipping|propina|saldo|balance|disponible|available|l[ií]mite|"
                         r"puntos|points|cashback|cup[oó]n|coupon|\bcr[eé]dito\b|\bcredit\b|regalo|\bgift\b", I)
_NEG_DEBIL = re.compile(r"\bdesde\b|\bfrom\b|a\s+partir\s+de|starting|\bhasta\b|up\s+to|antes\s+de|before|\bsave\b", I)
_POST_PAGADO = re.compile(r"^\s*(?:paid|pagado|cobrado|charged)\b", I)
_POST_NEG = re.compile(r"^\s*(?:de\s+|of\s+)?(?:i\.?v\.?a|vat|tax|impuestos?)\b(?!\s*(?:incl|included))", I)


@dataclass
class Importe:
    valor: Decimal
    moneda: str
    negativo: bool
    ini: int
    fin: int
    nivel: int = 0          # 2 = «pagado/cobrado/cargo de», 1 = «total/importe», 0 = suelto
    neg: bool = False       # IVA, subtotal, ahorro, saldo…: no es el importe del cargo


def a_decimal(tok):
    """«1.250,00» «1,250.00» «27.12» «27,12» «1.250» → Decimal, o None si no tiene forma de dinero."""
    t = tok.strip()
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        mil = "." if dec == "," else ","
        if t.count(dec) != 1 or any(len(p) != 3 for p in t.split(dec)[0].split(mil)[1:]):
            return None
        t = t.replace(mil, "").replace(dec, ".")
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        partes = t.split(sep)
        if len(partes) > 2:                                   # 1.250.000 → miles
            if len(partes[0]) > 3 or any(len(p) != 3 for p in partes[1:]):
                return None
            t = "".join(partes)
        else:
            ent, frac = partes
            if len(frac) == 3 and 1 <= len(ent) <= 3 and ent != "0":
                t = ent + frac                                # 1.250 / 1,250 → mil doscientos cincuenta
            elif len(frac) in (1, 2):
                t = f"{ent}.{frac}"
            else:
                return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def importes(texto):
    """Todos los importes con moneda del texto, sin solapes y con su contexto ya valorado (nivel, neg)."""
    texto = texto or ""
    crudos = []
    for rx in (_PRE, _POST):
        for r in rx.finditer(texto):
            v = a_decimal(r.group("n"))
            mon = _MON.get(r.group("m").lower())
            if v is None or mon is None or not (0 < v < 1_000_000):
                continue
            crudos.append(Importe(v, mon, bool(r.group("s")), r.start(), r.end()))
    crudos.sort(key=lambda c: (c.ini, -(c.fin - c.ini)))
    out, ult = [], -1
    for c in crudos:
        if c.ini >= ult:
            out.append(c)
            ult = c.fin
    prev = 0
    for c in out:
        pre = texto[max(prev, c.ini - 50):c.ini]
        post = texto[c.fin:c.fin + 30]
        prev = c.fin
        c.neg = bool(_NEG_FUERTE.search(pre[-30:]) or _NEG_DEBIL.search(pre[-14:]) or _POST_NEG.search(post))
        c.nivel = 2 if (_PAGADO.search(pre) or _POST_PAGADO.search(post)) else 1 if _TOTAL.search(pre[-30:]) else 0
    return out


def elegir_importe(cands):
    """→ (Importe|None, motivo). motivo: ok | sin_importe | ambiguo. Sin adivinar: primero el nivel más fuerte (pagado, luego total); entre varios valores distintos del
    mismo nivel solo se decide si UNO se repite claramente más que los demás (el total sale en el resumen, en la línea y en «importe pagado»; un IVA, una sola vez)."""
    pool = [c for c in cands if not c.neg]
    if not pool:
        return None, "sin_importe"
    for nivel in (2, 1, 0):
        grupo = [c for c in pool if c.nivel == nivel]
        cuenta = {}
        for c in grupo:
            cuenta[(c.valor, c.moneda)] = cuenta.get((c.valor, c.moneda), 0) + 1
        if len(cuenta) == 1:
            return grupo[0], "ok"
        if len(cuenta) > 1:
            orden = sorted(cuenta.values(), reverse=True)
            if orden[0] >= 3 and orden[0] >= 2 * orden[1]:
                clave = max(cuenta, key=cuenta.get)
                return next(c for c in grupo if (c.valor, c.moneda) == clave), "ok"
            return None, "ambiguo"
    return None, "sin_importe"


def a_cent(v):
    return int((v * 100).to_integral_value())


def formato(cent, moneda="EUR"):
    """1250 → «12,50 €», 125000 → «1.250,00 €»; otras monedas con su código («24,99 USD»)."""
    ent, dec = divmod(abs(int(cent)), 100)
    txt = f"{ent:,}".replace(",", ".") + f",{dec:02d}"
    return f"{'-' if cent < 0 else ''}{txt} €" if moneda == "EUR" else f"{'-' if cent < 0 else ''}{txt} {moneda}"


# ───────────────────────── fechas ─────────────────────────
ETQ_CARGO = re.compile(r"fecha\s+(?:de(?:l)?\s+)?(?:pago|cargo|cobro|factura|emisi[oó]n|operaci[oó]n|compra|pedido)|pagad[oa]\s+(?:el|en)|cargad[oa]\s+(?:el|en)|"
                       r"cobrad[oa]\s+(?:el|en)|\bpaid\b(?:\s+on)?|payment\s+date|date\s+(?:paid|of\s+(?:payment|charge|purchase|issue))|charged\s+on|billed\s+on|"
                       r"invoice\s+date|order\s+date|purchased\s+on|\bfecha\s*:", I)
ETQ_PROXIMO = re.compile(r"pr[oó]xim[oa]\s+(?:pago|cobro|cargo|factura|renovaci[oó]n|facturaci[oó]n)|siguiente\s+(?:pago|cobro|cargo)|"
                         r"next\s+(?:billing|payment|charge|invoice|renewal)(?:\s+date)?|renews?\s+(?:on|automatically\s+on)|"
                         r"se\s+renovar[aá]\s+(?:autom[aá]ticamente\s+)?(?:el)?|renovaci[oó]n\s+(?:el|prevista|autom[aá]tica\s+el)|renewal\s+date|"
                         r"will\s+(?:be\s+)?(?:charged|billed|renew)\s+on|fecha\s+de\s+renovaci[oó]n", I)


MADRID = ZoneInfo("Europe/Madrid")


def fecha_del_hilo(h, hoy):
    """Fecha del correo (internalDateIso | date), EN HORA DE MADRID. Si no se entiende, hoy.
    internalDateIso viene en UTC («…Z»): un recibo de las 00:30 del 1 de octubre en Madrid llega como 22:30Z del 30 de septiembre y
    contaba en el mes anterior (y movía el día de la suscripción y su próximo cobro)."""
    for k in ("internalDateIso", "date"):
        v = str(h.get(k) or "")
        if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", v):
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return (d.astimezone(MADRID) if d.tzinfo else d).date()
            except ValueError:
                pass
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        if v:
            try:
                from email.utils import parsedate_to_datetime
                d = parsedate_to_datetime(v)
                return (d.astimezone(MADRID) if d.tzinfo else d).date()
            except (TypeError, ValueError, IndexError):
                pass
    return hoy


def _resolver(d, m, y, ref, futuro):
    try:
        if y:
            return date(y + 2000 if y < 100 else y, m, d)
        f = date(ref.year, m, d)
        if futuro:
            return f if f >= ref - timedelta(days=3) else date(ref.year + 1, m, d)
        return f if f <= ref + timedelta(days=3) else date(ref.year - 1, m, d)
    except ValueError:
        return None


def fechas_etiquetadas(texto, ref):
    """→ (fecha_del_cargo|None, proximo_cobro|None). Solo fechas con etiqueta clara: «fecha de pago», «paid on», «próximo pago», «renews on»…
    La del cargo ha de ser pasada (hasta 45 días antes del correo); la del próximo cobro, posterior al correo y a menos de 400 días."""
    crudas = [x for x in extraer._crudas(texto or "") if x[3] > 0]
    ing = not extraer.idioma_es(texto)
    cargos, prox = set(), set()
    ant = 0
    for ini, fin, d, m, y, dm in crudas:
        pre = texto[max(ant, ini - 45):ini]
        ant = fin
        if dm and ing:
            continue
        if ETQ_PROXIMO.search(pre):
            f = _resolver(d, m, y, ref, True)
            if f and ref < f <= ref + timedelta(days=400):
                prox.add(f)
        elif ETQ_CARGO.search(pre[-35:]):
            f = _resolver(d, m, y, ref, False)
            if f and ref - timedelta(days=45) <= f <= ref + timedelta(days=1):
                cargos.add(f)
    return (next(iter(cargos)) if len(cargos) == 1 else None), (next(iter(prox)) if len(prox) == 1 else None)


# ───────────────────────── nombres ─────────────────────────
def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c))


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+& ]+", " ", sin_acentos(s).lower())).strip()


SUFIJOS = {"inc", "ltd", "llc", "sl", "slu", "sa", "gmbh", "bv", "ab", "corp", "co", "limited", "sas", "srl", "plc", "pty", "oy", "ag", "spain", "espana", "europe",
           "payments", "payment", "billing", "receipts", "receipt", "invoices", "invoice", "facturacion", "factura", "noreply", "no", "reply", "team", "support", "notifications",
           "notificaciones", "info", "service", "services", "servicio", "servicios", "atencion", "cliente", "customer", "the", "via", "pagos", "recibos", "online", "mail", "email"}


def clave_de(nombre):
    """«Tienda Rara, S.L.» → «tienda rara». Hasta 2 palabras; sin sufijos de empresa ni palabras de facturación."""
    toks = [t for t in norm(nombre).split() if t not in SUFIJOS]
    return " ".join(toks[:2])


def titulo(clave):
    return " ".join(w.capitalize() if len(w) > 2 or not w.isalpha() else w.upper() if w in ("ai", "tv") else w.capitalize() for w in clave.split())


# (patrón sobre «dominio nombre_remitente» sin acentos y en minúsculas, clave, nombre visible, categoría). El primero que casa gana.
CONOCIDOS = [
    (r"mainfunc|genspark", "genspark", "Genspark", "suscripciones"),
    (r"spotify", "spotify", "Spotify", "suscripciones"),
    (r"netflix", "netflix", "Netflix", "suscripciones"),
    (r"disneyplus|disney\+|disney plus|\bdisney\b", "disney", "Disney+", "suscripciones"),
    (r"hbomax|\bhbo\b|max\.com", "hbo max", "HBO Max", "suscripciones"),
    (r"crunchyroll", "crunchyroll", "Crunchyroll", "suscripciones"),
    (r"twitch", "twitch", "Twitch", "suscripciones"),
    (r"\bkick\.com|\bkick streaming|\bkick\b", "kick", "Kick", "suscripciones"),
    (r"linkedin", "linkedin", "LinkedIn", "suscripciones"),
    (r"classpass", "classpass", "ClassPass", "salud"),
    (r"nintendo", "nintendo", "Nintendo", "ocio"),
    (r"steampowered|steam support|\bvalve\b", "steam", "Steam", "ocio"),
    (r"playstation|sony interactive", "playstation", "PlayStation", "ocio"),
    (r"xbox", "xbox", "Xbox", "ocio"),
    (r"microsoft", "microsoft", "Microsoft", "suscripciones"),
    (r"apple\.com|itunes|\bicloud\b|\bapple\b", "apple", "Apple", "suscripciones"),
    (r"youtube", "youtube", "YouTube", "suscripciones"),
    (r"google", "google", "Google", "suscripciones"),
    (r"openai|chatgpt", "openai", "OpenAI", "suscripciones"),
    (r"anthropic|claude\.ai", "anthropic", "Anthropic", "suscripciones"),
    (r"github", "github", "GitHub", "suscripciones"),
    (r"adobe", "adobe", "Adobe", "suscripciones"),
    (r"dropbox", "dropbox", "Dropbox", "suscripciones"),
    (r"notion", "notion", "Notion", "suscripciones"),
    (r"duolingo", "duolingo", "Duolingo", "suscripciones"),
    (r"patreon", "patreon", "Patreon", "suscripciones"),
    (r"nordvpn|proton", "vpn", "VPN", "suscripciones"),
    (r"amazon web services|\baws\b", "aws", "AWS", "suscripciones"),
    (r"cloudflare", "cloudflare", "Cloudflare", "suscripciones"),
    (r"namecheap|godaddy|hetzner|digitalocean|vercel|netlify|heroku|ovhcloud|\bovh\b|ionos|squarespace|\bwix\b|railway\.app|fly\.io", "hosting", "Hosting y dominios", "suscripciones"),
    (r"figma|canva|\bzoom\b|slack|atlassian|jetbrains|1password|bitwarden|lastpass|evernote|todoist|grammarly|midjourney|perplexity|mistral|nous research|elevenlabs|"
     r"replicate|huggingface|cursor\.com|windsurf|obsidian|tailscale", "software", "Software", "suscripciones"),
    (r"samsung", "samsung", "Samsung", "otros"),
    (r"amazon", "amazon", "Amazon", "otros"),
    (r"aliexpress", "aliexpress", "AliExpress", "otros"),
    (r"zalando", "zalando", "Zalando", "otros"),
    (r"klarna", "klarna", "Klarna", "otros"),
    (r"vueling", "vueling", "Vueling", "ocio"),
    (r"ryanair", "ryanair", "Ryanair", "ocio"),
    (r"iberia(?!n)\.com|\biberia\b", "iberia", "Iberia", "ocio"),
    (r"renfe", "renfe", "Renfe", "ocio"),
    (r"booking\.com|\bbooking\b", "booking", "Booking", "ocio"),
    (r"airbnb", "airbnb", "Airbnb", "ocio"),
    (r"trainline|ouigo|iryo|flixbus|\balsa\b|easyjet|volotea", "viajes", "Viajes", "ocio"),
    (r"iberdrola", "iberdrola", "Iberdrola", "vivienda"),
    (r"endesa", "endesa", "Endesa", "vivienda"),
    (r"naturgy", "naturgy", "Naturgy", "vivienda"),
    (r"holaluz|octopus|som energia|som energía", "luz", "Luz", "vivienda"),
    (r"canal de isabel|emasesa|agbar|aigues|emivasa|aguas de|\bemaya\b|\bacciona agua\b", "agua", "Agua", "vivienda"),
    (r"movistar|telefonica", "movistar", "Movistar", "vivienda"),
    (r"orange\.es|\borange\b", "orange", "Orange", "vivienda"),
    (r"vodafone", "vodafone", "Vodafone", "vivienda"),
    (r"\bdigi\b|digimobil", "digi", "Digi", "vivienda"),
    (r"masmovil|másmóvil|yoigo|pepephone|lowi|jazztel|simyo|\bo2\b", "internet", "Internet", "vivienda"),
    (r"mercadona", "mercadona", "Mercadona", "comida"),
    (r"carrefour", "carrefour", "Carrefour", "comida"),
    (r"lidl|alcampo|\bdia\.es\b|consum|eroski", "supermercado", "Supermercado", "comida"),
    (r"glovo", "glovo", "Glovo", "comida"),
    (r"just ?eat|justeat", "just eat", "Just Eat", "comida"),
    (r"uber ?eats|ubereats|deliveroo|pedidosya", "reparto", "Comida a domicilio", "comida"),
    (r"repsol", "repsol", "Repsol", "coche"),
    (r"cepsa|moeve|\bbp\b|\bshell\b|galp|ballenoil|plenoil", "gasolina", "Gasolina", "coche"),
    (r"telpark|parkia|\bemt\b|via ?t\b|cabify|\buber\b|\bbolt\b|freenow", "movilidad", "Movilidad", "coche"),
    (r"sanitas|adeslas|asisa|\bdkv\b|cigna", "seguro de salud", "Seguro de salud", "salud"),
    (r"agenciatributaria|aeat|\bdgt\b|seg-social|seguridad social|ayuntamiento", "tramites", "Trámites", "trámites"),
    (r"paypal", "paypal", "PayPal", "otros"),
    (r"stripe|paddle", "pasarela", "Pasarela de pago", "otros"),
]
BANCOS = re.compile(r"santander|bbva|caixabank|caixa|sabadell|bankinter|\bing\b|openbank|revolut|\bn26\b|unicaja|abanca|kutxabank|ibercaja|cajamar|evobanco|myinvestor|"
                    r"\bwise\b|bizum|\bbanco\b|\bbank\b|banca|banc\b", I)
PROCESADORES = re.compile(r"stripe|paddle|paypal|apple\.com|itunes|google\.com|googlemail|klarna|fastspring|2checkout|gumroad|lemonsqueezy|braintree|adyen|mollie|redsys", I)
_CONOCIDOS = [(re.compile(p, I), k, n, c) for p, k, n, c in CONOCIDOS]

# Palabras que sitúan una categoría cuando el comercio no está en la tabla (asunto + remitente + comercio).
CAT_PALABRAS = [
    ("trámites", re.compile(r"\btasa\b|ayuntamiento|notar[ií]a|registro\s+(?:civil|mercantil)|certificado|multa|sanci[oó]n|hacienda|tr[aá]mite|gestor[ií]a|abogad", I)),
    ("vivienda", re.compile(r"electricidad|\bluz\b|\bgas\b|\bagua\b|fibra|internet|alquiler|renta\s+mensual|comunidad\s+de\s+propietarios|hipoteca|\bibi\b|basura|hogar|"
                            r"seguro\s+del?\s+hogar|calefacci[oó]n|router", I)),
    ("coche", re.compile(r"gasolin|combustible|\bitv\b|parking|aparcamiento|peaje|seguro\s+(?:del?\s+)?(?:coche|auto|veh[ií]culo)|neum[aá]tic|taller|matr[ií]cula|circulaci[oó]n", I)),
    ("comida", re.compile(r"supermercado|restaurante|pizzer|hamburgues|comida|cena\b|delivery|a\s+domicilio|cafeter|panader|takeaway|food", I)),
    ("salud", re.compile(r"farmacia|cl[ií]nica|m[eé]dico|dental|dentista|fisio|[oó]ptica|seguro\s+(?:de\s+)?salud|sanitario|psic[oó]log|gimnasio|gym\b|fitness", I)),
    ("ocio", re.compile(r"cine|teatro|entradas|concierto|ticket|hotel|vuelo|billete|reserva|viaje|museo|parque|festival|videojuego|juego", I)),
    ("suscripciones", re.compile(r"suscripci|subscription|membres[ií]a|membership|premium|\bplus\b|\bpro\b|mensualidad|monthly\s+plan|annual\s+plan|plan\s+(?:mensual|anual)", I)),
]


def categoria_por_palabras(texto):
    for cat, rx in CAT_PALABRAS:
        if rx.search(texto or ""):
            return cat
    return None


# ───────────────────────── clasificar el correo ─────────────────────────
_FUERTE = re.compile(r"recibo|receipt|factura|invoice|\bpago\b.{0,60}\b(?:recibido|realizado|confirmado|aceptado|procesado)|recibido\s+tu\s+pago|"
                     r"payment\s+(?:received|confirm\w*|successful|processed|receipt|accepted)|thanks?\s+for\s+your\s+(?:payment|purchase|order)|"
                     r"gracias\s+por\s+(?:tu\s+|su\s+)?(?:pago|compra|comprar|pedido|reserva)|thank\s+you\s+for\s+(?:your\s+)?(?:purchase|order|payment|purchasing)|pedido\s*[:#]|has\s+pagado|you\s+paid|you.?ve\s+paid|\bcharged\b|\bcargo\b|\bcobro\b|adeudo|domiciliaci[oó]n|"
                     r"order\s+(?:confirmation|receipt)|confirmaci[oó]n\s+de\s+(?:tu\s+)?(?:pedido|pago|compra)|tu\s+pedido|your\s+order|pedido\s+realizado|"
                     r"billing\s+statement|reembolso|refund|devoluci[oó]n|abono|nota\s+de\s+cr[eé]dito|credit\s+note", I)
_RECIBO_REAL = re.compile(r"recibo|receipt|factura|invoice|pago\s+(?:recibido|realizado|confirmado)|payment\s+(?:received|successful|confirm\w*)|has\s+pagado|you\s+paid|reembolso|refund", I)
_DEBIL = re.compile(r"renovaci|renewal|renewed|suscripci|subscription|membres[ií]a|membership|\bcuota\b|billing|facturaci|\bpago\b|payment|pedido|\border\b|\bcompra\b|"
                    r"purchase|reserva|booking|billete|e-?ticket|localizador", I)
_ANUNCIO = re.compile(r"\boferta|descuento|\bdto\b|\d+\s?%\s*(?:de\s+)?(?:dto|descuento|off|menos)|hasta\s+(?:el\s+)?\d+\s?%|rebajas|\bsale\b|promo|cup[oó]n|coupon|ahorra|"
                      r"\bsave\s+\d|black\s?friday|cyber\s?monday|solo\s+hoy|[uú]ltim[oa]s?\s+(?:\d+\s+)?(?:horas|d[ií]as|oportunidad|plazas|unidades)|hasta\s+[\d.,]+\s?[€$]\s+de\s+(?:reembolso|descuento|ahorro|dto)|no\s+te\s+lo\s+pierdas|gratis|\bfree\b|"
                      r"prueba\s+gratuita|free\s+trial|descubre|novedades|newsletter|bolet[ií]n|webinar|est[aá]s?\s+invitad|\bregalo|sorteo|premio|\bgana\b|exclusiv|te\s+echamos|"
                      r"te\s+extra[ñn]amos|encuesta|survey|valora|rate\s+your|mejora\s+tu|actualiza\s+(?:a|tu\s+plan)|upgrade|suscr[ií]bete|subscribe\s+(?:now|today)|"
                      r"renueva\s+(?:ya|ahora|tu\s+\w+\s+con)|aprovecha|\bpor\s+solo\b|\bonly\s+\$|\bsolo\s+\d|mes(?:es)?\s+gratis", I)
_ANUNCIO_CUERPO = re.compile(r"\boferta\b|descuento|\d+\s?%\s*(?:de\s+)?(?:dto|descuento|off|menos)|ahorra|rebajas|promoci[oó]n|promo\b|cup[oó]n|c[oó]digo\s+promocional|"
                             r"black\s?friday|solo\s+hoy|hasta\s+agotar|prueba\s+gratis|prueba\s+gratuita|free\s+trial|suscr[ií]bete|subscribe\s+now|sorteo|aprovecha|"
                             r"v[aá]lid[oa]\s+hasta|limited\s+time|sale\s+ends|\bsave\s+\d|gratis\b", I)
_NO_GASTO = re.compile(r"cancelad[oa]|cancelled|canceled|cancelaci[oó]n|anulad[oa]|unsuccessful|\bfailed\b|fallid[oa]|rechazad[oa]|declined|no\s+se\s+(?:pudo|ha\s+podido)|could\s+not|"
                       r"suspendid|suspended|\bpausad[oa]|\bpaused\b|se\s+pausó|(?:no|n.t)\s+(?:has|have)\s+(?:been\s+)?(?:cobrad|charged)|haven.?t\s+been\s+charged|"
                       r"enviado|ha\s+salido|en\s+camino|shipped|dispatched|out\s+for\s+delivery|entregado|delivered|llegar[aá]|arriving|seguimiento|tracking|"
                       r"se\s+renovar[aá]|will\s+(?:be\s+)?renew|renews?\s+(?:on|soon)|pr[oó]xim[oa]\s+(?:renovaci|cobro|pago)\s+(?:el|en)|upcoming\s+(?:renewal|payment|charge)|"
                       r"(?:va\s+a|est[aá]\s+a\s+punto\s+de)\s+renovar|renovaci[oó]n\s+pr[oó]xima|recordatorio|reminder|trial\s+(?:ends|ending)|"
                       r"prueba\s+(?:gratuita\s+)?(?:termina|finaliza)|vence\s+pronto|expires?\s+(?:soon|on)|caducar[aá]|bienvenid|welcome|verifica|verify|restablec|reset\s+your|"
                       r"inicio\s+de\s+sesi|sign.?in|c[oó]digo\s+de|verification|security\s+alert|alerta\s+de\s+seguridad|valoraci[oó]n|rese[ñn]a", I)
_FACTURACION_REM = re.compile(r"billing|invoice|receipt|facturaci|factura|payments?@|pagos?@|recibos?@|stripe\.com|paddle\.com|paypal|invoice\+statements", I)
_METODO = re.compile(r"\bvisa\b|mastercard|master\s*card|amex|american\s+express|paypal|tarjeta|\bcard\s+ending|ending\s+in|terminad[ao]\s+en|forma\s+de\s+pago|payment\s+method|"
                     r"m[eé]todo\s+de\s+pago|domiciliad|d[eé]bito|débito|direct\s+debit|bizum|apple\s+pay|google\s+pay", I)
_NUM_DOC = re.compile(r"(?:factura|invoice|pedido|order|recibo|receipt|localizador|locator|booking\s+ref\w*|referencia)\s*(?:n[ºo°.]?|num\w*|number|#|:)?\s*[#:]?\s*[A-Z0-9][A-Z0-9\-/]{4,}", I)
_REEMBOLSO = re.compile(r"reembolso|refund|devoluci[oó]n|abono|nota\s+de\s+cr[eé]dito|credit\s+note", I)
_RENOVACION = re.compile(r"renovaci|renewal|renewed|suscripci|subscription|membres[ií]a|membership|\bcuota\b|mensualidad|monthly|annual\s+plan|plan\s+(?:mensual|anual)", I)
_FACTURA = re.compile(r"factura|invoice", I)


def correo_de(de):
    """(nombre_remitente, email, dominio) de «Nombre <a@b.c>»."""
    de = str(de or "")
    m = re.search(r"<([^>]+)>", de)
    email = (m.group(1) if m else de).strip().lower()
    nombre = re.sub(r"\s*<.*", "", de).strip().strip("\"'") if m else ""
    return nombre, email, email.rpartition("@")[2]


def candidato(asunto, de):
    """¿Merece la pena abrir el correo? Barato: solo asunto y remitente. → (bool, motivo)."""
    asunto = asunto or ""
    if _NO_GASTO.search(asunto):
        return False, "no_es_cargo"
    if _ANUNCIO.search(asunto) and not _RECIBO_REAL.search(asunto):
        return False, "publicidad"
    if _FUERTE.search(asunto) or _DEBIL.search(asunto):
        return True, "asunto"
    if _FACTURACION_REM.search(de or ""):
        return True, "remitente"
    return False, "sin_pistas"


# ───────────────────────── comercio ─────────────────────────
_EN_PROCESADOR = [
    re.compile(r"receipt\s+from\s+(?P<m>[^#\[\(\n]{2,50}?)\s*(?:#|\[|\(|$)", I),
    re.compile(r"(?:invoice|payment)\s+(?:from|to)\s+(?P<m>[^#\[\(\n]{2,50}?)\s*(?:#|\[|\(|$)", I),
    re.compile(r"recibo\s+de\s+tu\s+pago\s+a\s+(?P<m>[^#\[\(\n.,]{2,50}?)\s*(?:#|\[|\(|$|\.|,)", I),
    re.compile(r"(?:pago|payment)\s+(?:a|to)\s+(?P<m>[^#\[\(\n.,]{2,50}?)\s*(?:#|\[|\(|$|\.|,| ha | has | was )", I),
    re.compile(r"(?:compra|purchase)\s+(?:en|a|from|at)\s+(?P<m>[^#\[\(\n.,]{2,50}?)\s*(?:#|\[|\(|$|\.|,)", I),
    re.compile(r"(?:de|from)\s+(?P<m>[A-Z][\w&.'-]+(?:\s+[A-Z][\w&.'-]+){0,2})\s*(?:#|\[|\(|$)"),
]
_EN_BANCO = re.compile(r"(?:\ben\b|\bat\b|comercio:?|establecimiento:?|beneficiario:?|a\s+favor\s+de|recibo\s+de|adeudo\s+de|pago\s+a)\s+"
                       r"(?P<m>[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 &.*'-]{2,38}[A-ZÁÉÍÓÚÑ0-9])(?![a-záéíóúñ])")
_GENERICO = re.compile(r"^(?:no.?reply|noreply|info|hello|hola|support|ayuda|team|notifications?|notificaciones|mail|email|news|contact|contacto|billing|invoice|receipts?|"
                       r"payments?|pagos|facturaci[oó]n|recibos|service|servicio|cliente|customer|atenci[oó]n)\b", I)


def _desde_tabla(texto, extra=None):
    """(clave, nombre, categoria) del primer comercio conocido que aparece en el texto, o None. `extra`: {clave: {nombre, categoria, alias}} de la config."""
    t = sin_acentos(texto or "").lower()
    for clave, ent in (extra or {}).items():
        alias = [clave] + [norm(a) for a in (ent.get("alias") or []) if isinstance(a, str)]
        if any(a and re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", norm(t)) for a in alias):
            return clave, str(ent.get("nombre") or titulo(clave))[:40], (ent.get("categoria") if ent.get("categoria") in CATEGORIAS else None)
    for rx, clave, nombre, cat in _CONOCIDOS:
        if rx.search(t):
            return clave, nombre, cat
    return None


def _limpiar_nombre(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip(" .,:;-–—\"'")
    s = re.sub(r"\b(?:via|vía)\b.*$", "", s, flags=I).strip(" .,:;-")
    return s


def _plausible(nombre):
    from .llm import PELIGRO
    from .flujos import sospechoso
    n = _limpiar_nombre(nombre)
    return bool(n) and 2 <= len(n) <= 40 and not PELIGRO.search(n) and not sospechoso(n) and not re.search(r"[<>{}\[\]|\\]|\d{5,}", n) and bool(re.search(r"[A-Za-zÁ-ú]", n))


@dataclass
class Comercio:
    clave: str
    nombre: str
    categoria: str = None
    confianza: str = "alta"       # alta (tabla o config) | media (nombre del remitente o «recibo de X») | baja (dominio / banco sin comercio)
    banco: bool = False


def comercio(asunto, de, texto, extra=None):
    """Comercio del correo. Nunca devuelve texto sin comprobar: pasa por `_plausible` (sin enlaces, órdenes ni caracteres raros)."""
    nombre_rem, email, dom = correo_de(de)
    base = f"{dom} {nombre_rem}"
    es_banco = bool(BANCOS.search(sin_acentos(base)))
    es_proc = bool(PROCESADORES.search(email)) or bool(re.search(r"stripe|paddle|paypal", sin_acentos(nombre_rem), I))
    if es_banco:
        # el comercio del cargo está en el texto («en MERCADONA»); el banco solo es el emisor
        for m in _EN_BANCO.finditer(texto or ""):
            cand = _limpiar_nombre(m.group("m"))
            if _plausible(cand):
                t = _desde_tabla(cand, extra)
                if t:
                    return Comercio(t[0], t[1], t[2], "alta")
                return Comercio(clave_de(cand) or norm(cand)[:20], titulo(clave_de(cand)) or cand.title()[:40], None, "media")
        n = _limpiar_nombre(nombre_rem) or titulo(clave_de(dom.split(".")[0]))
        return Comercio(clave_de(n) or "banco", n[:40] or "Banco", "otros", "baja", banco=True)
    if es_proc and not re.search(r"apple|google|klarna", base, I):
        for rx in _EN_PROCESADOR:
            m = rx.search(asunto or "") or rx.search((texto or "")[:1500])
            if m and _plausible(m.group("m")):
                cand = _limpiar_nombre(m.group("m"))
                t = _desde_tabla(cand, extra)
                if t:
                    return Comercio(t[0], t[1], t[2], "alta")
                return Comercio(clave_de(cand), titulo(clave_de(cand)), None, "media")
    t = _desde_tabla(base, extra) or _desde_tabla(asunto, extra)
    if t:
        return Comercio(t[0], t[1], t[2], "alta")
    if nombre_rem and not _GENERICO.match(nombre_rem) and _plausible(nombre_rem):
        c = clave_de(nombre_rem)
        if c:
            return Comercio(c, titulo(c), None, "media")
    lab = dom.split(".")
    base_dom = lab[-3] if len(lab) >= 3 and lab[-2] in ("co", "com", "org", "gob") else (lab[-2] if len(lab) >= 2 else lab[0] if lab and lab[0] else "")
    if base_dom and base_dom not in ("gmail", "googlemail", "hotmail", "outlook", "yahoo", "icloud", "mail", "email") and _plausible(base_dom):
        c = clave_de(base_dom)
        if c:
            return Comercio(c, titulo(c), None, "baja")
    return Comercio("desconocido", "Comercio sin identificar", None, "baja")


# ───────────────────────── análisis completo ─────────────────────────
@dataclass
class Recibo:
    veredicto: str                  # recibo | publicidad | dudoso | ninguno
    motivo: str = ""
    importe_cent: int = 0
    moneda: str = "EUR"
    fecha: date = None
    tipo: str = "cargo"
    proximo: date = None
    comercio: Comercio = None
    puntos: int = 0
    anuncio: int = 0


def analizar(h, texto, hoy, extra=None):
    """Un correo (cabeceras `h` de gog + texto plano) → Recibo. Puro: no escribe ni llama a nada."""
    asunto = re.sub(r"\s+", " ", str(h.get("subject") or "")).strip()
    de = str(h.get("from") or "")
    texto = texto or ""
    ok, motivo = candidato(asunto, de)
    if not ok:
        return Recibo("ninguno", motivo)
    ref = fecha_del_hilo(h, hoy)
    cands = importes(texto)
    imp, mot = elegir_importe(cands)
    if imp is None:
        return Recibo("ninguno", mot)
    # ── puntos de «esto es un recibo» frente a «esto es publicidad»
    s_fuerte, s_debil, s_ad = bool(_FUERTE.search(asunto)), bool(_DEBIL.search(asunto)), bool(_ANUNCIO.search(asunto))
    base = 3 if s_fuerte else 1 if s_debil else 0
    if s_ad:
        base = min(base, 1)
    if _FACTURACION_REM.search(de):
        base += 1
    com = comercio(asunto, de, texto, extra)
    if com.confianza == "alta" and not com.banco and (s_debil or s_fuerte) and not s_ad:
        base += 1                                  # un comercio que ya conocemos, con un asunto de pedido o pago, es más fiable que un remitente cualquiera
    cargo, proximo = fechas_etiquetadas(texto, ref)
    cuerpo = {"nivel": 2 if imp.nivel == 2 else 1 if imp.nivel == 1 else 0, "metodo": 1 if _METODO.search(texto) else 0,
              "doc": 1 if _NUM_DOC.search(texto) else 0, "fecha": 1 if cargo else 0}
    puntos = base + min(sum(cuerpo.values()), 4)
    anuncio = (2 if s_ad else 0) + min(len(set(m.group(0).lower() for m in _ANUNCIO_CUERPO.finditer(texto))), 3)
    if puntos >= 4 and puntos - anuncio >= 2:
        veredicto = "recibo"
    elif anuncio >= 2 and anuncio >= puntos:
        veredicto = "publicidad"
    elif puntos >= 2:
        veredicto = "dudoso"
    else:
        veredicto = "ninguno"
    reembolso = imp.negativo or bool(_REEMBOLSO.search(asunto))
    tipo = ("reembolso" if reembolso else "renovacion" if (_RENOVACION.search(asunto) or proximo) else "factura" if _FACTURA.search(asunto) else "cargo")
    return Recibo(veredicto, "ok", a_cent(imp.valor), imp.moneda, cargo or ref, tipo, proximo, com, puntos, anuncio)
