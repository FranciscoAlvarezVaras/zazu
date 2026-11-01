"""Reglas de palabras compartidas (sin IA). Español de España. Para el correo se reutilizan las de recoger.py."""
import re
import sys

from . import config

I = re.I
MESES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"

# ── WhatsApp: ¿hay algo que apuntar? ──
FECHA_HORA = re.compile(
    r"\b(hoy|ma[ñn]ana|pasado ma[ñn]ana|lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo|esta (tarde|noche|semana)|"
    r"(la )?semana que viene|(el )?fin de semana|finde|\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?|el (d[ií]a )?\d{1,2}\b|"
    rf"\d{{1,2}}\s+de\s+({MESES})|a las? \d{{1,2}}([:.h]\d{{2}})?|\d{{1,2}}:\d{{2}}|\d{{1,2}}\s?h\b)", I)
PETICION = re.compile(
    r"me dices|\bdime\b|av[ií]same|acu[ée]rdate|no te olvides|recuerda\b|tienes que|tendr[ií]as que|puedes (mandar|enviar|traer|llamar|pasar|comprar|pagar|hacer|mirar|ver|recoger)|"
    r"podr[ií]as|me (mandas|pasas|traes|env[ií]as|avisas|llamas|compras|recoges)|necesito que|hay que|"
    r"te (mando|env[ií]o|paso|llamo|aviso|traigo|pago|devuelvo|confirmo|digo|escribo)|yo (me encargo|lo (hago|miro|traigo|llevo|pago))|lo miro|me encargo|"
    r"quedamos|nos vemos|\bcita\b|reuni[óo]n|\bplazo\b|antes del|hasta el|entregar|\bpagar\b|transferencia|bizum|factura|recoger|llevar|traer|\bprometo\b|te debo", I)
IMPORTE = re.compile(r"\d+(?:[.,]\d+)?\s?(?:€|euros?)", I)
ACK = re.compile(r"^\W*(ok+|okey|vale+|gracias+|grac|thx|👍+|si+|sí+|no+|jaja+j*|jeje+|perfecto|genial|bien|de nada|entendido|claro|listo|hecho|ya|ah+|buenas?|hola|buenos d[ií]as|buenas (tardes|noches))\W*$", I)
BOT_NOMBRE = re.compile(r"\bbot\b|aviso|notific|c[oó]digo|verific|no.?reply|soporte|atenci[oó]n al cliente", I)
OTP = re.compile(r"(c[oó]digo|code|verific|otp|pin)\b", I)
SIN_TEXTO = re.compile(r"^Sent (sticker|image|video|audio|document|gif)$", I)


def hay_marca(texto):
    """¿Merece la pena que lo mire el modelo? (petición/compromiso, o fecha-hora en un mensaje con cuerpo, o importe)"""
    if not texto:
        return False
    return bool(PETICION.search(texto) or IMPORTE.search(texto) or (FECHA_HORA.search(texto) and len(texto) >= 15))


def es_otp(texto):
    return bool(OTP.search(texto or "") and re.search(r"\b\d{4,8}\b", texto or "") and len(texto) < 160)


# ── Correo ──
_recoger = None


def recoger():
    """El módulo recoger.py de los scripts de Hermes (gog() con credenciales y reintentos, P1/RUIDO/ACCION/PORTALES, limpio())."""
    global _recoger
    if _recoger is None:
        s = str(config.scripts_dir())
        if s not in sys.path:
            sys.path.insert(0, s)
        import recoger as r
        _recoger = r
    return _recoger


SEGURIDAD = re.compile(r"inicio de sesi|nuevo dispositivo|new (sign.?in|device)|sign.?in (attempt|from)|security alert|alerta de seguridad|"
                       r"actividad (inusual|sospechosa)|unusual activity|contrase[ñn]a (ha sido )?(cambiad|modificad|restablec)|password (was )?(changed|reset)|"
                       r"verificaci[óo]n en dos|acceso no autorizado|han accedido|c[óo]digo de seguridad", I)
CARGO = re.compile(r"cargo|cobro|has pagado|pago (recibido|fallido|rechazado|devuelto)|payment (received|failed|declined)|charged|"
                   r"impago|overdue|devoluci[óo]n|reembolso|transferencia (recibida|emitida)|recibo (devuelto|impagado)|domiciliaci[óo]n|adeudo|has sido cargad", I)
DINERO = re.compile(r"factura|invoice|recibo|vencimiento|vence\b|deuda|recobro|multa|sanci|renovaci|renewal|suscripci|subida de precio|price increase|billing|embargo|ASNEF|prueba gratuita|free trial", I)
OFICIAL = re.compile(r"@([\w-]+\.)*(dgt\.es|aeat\.es|agenciatributaria\.(es|gob\.es)|seg-social\.(es|gob\.es)|gva\.es|sepe\.es|policia\.es|guardiacivil\.es|"
                     r"administracion\.gob\.es|correos\.es|tributos\.|sede\.[\w.-]+|\w+\.gob\.es|\w+\.gva\.es)\b", I)
INTERVENCION = re.compile(r"entrevista|interview|prueba t[ée]cnica|technical test|assessment|siguiente paso|next steps?|pr[óo]ximos pasos|disponibilidad|availability|plazo|deadline|"
                          r"your application|tu candidatura|recruiter|reclutador|proceso de selecci", I)
AUTOMATICO = re.compile(r"hemos recibido tu candidatura|we have received your application|thank you for applying|gracias por (tu interés|aplicar|tu candidatura)|"
                        r"no respondas a este|do not reply|job alert|alerta de empleo|is hiring|est[áa]n contratando|nuevas ofertas|ofertas para", I)
NO_HUMANO = re.compile(r"no.?reply|noreply|donotreply|do-not-reply|notification|notific|mailer|newsletter|alerts?@|info@|news@|support@|billing@|updates?@|team@|hello@|bounce", I)
URL = re.compile(r"https?://[^\s<>\"')\]]+", I)
