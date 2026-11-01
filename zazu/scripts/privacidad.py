#!/usr/bin/env python3
"""Filtros de privacidad de todo lo que se copia al Cerebro (lo usan exportar-zazu.py y guardar-propuestas.py). Sin IA.

tachar(texto): tacha claves y contraseñas (también dichas en lenguaje natural: «mi contraseña es…», «la clave de la
puerta es…», «Gato1234 es la contraseña», «cambié la contraseña a…», «Usuario: x / clave: …», «DB_PASS=…»), PIN y PUK,
códigos 2FA/OTP (también con el número delante: «482913 es tu código»; con un importe en medio; alfanuméricos tras «es»/«:»),
códigos de recuperación, CVV, tarjetas, cuentas, IBAN, SWIFT/BIC, DNI/NIE, cédula/RIF (también sin la palabra en los datos de
un pago móvil), pasaportes, nº de la Seguridad Social (también «Nº SS», «Seguridad Social:»), claves en listas, tablas y
enumeraciones («Claves de casa:» y debajo «- Router: …», la columna «Contraseña» de una tabla, «… y la del router …»),
tokens (también los de formato desconocido, las API keys en hex y las claves dentro de URL), frases semilla, teléfonos
(también los JID de WhatsApp, wa.me, venezolanos y de EE. UU.) y los valores de ~/.hermes/.env.
Deja intactos fechas, horas, importes, años, unidades, versiones e ids de sesión. «Clave: llevar el DNI» (una frase
normal tras «clave:»/«contraseña:») no se toca: con «:», solo se tacha un valor fuerte o que vaya solo al final de la línea.
sin_datos_ajenos(texto): quita de un mensaje de Fran lo que el sistema mete dentro (datos de correo/agenda/WhatsApp,
la descripción automática de las imágenes, el mensaje citado al responder, la transcripción de una nota de voz citada
(también cuando Fran responde con otra nota de voz: se queda la suya),
el contenido de los documentos de texto y de los adjuntos «@file:», y el contexto de otros canales).
LEE_NOTIFICACIONES: detecta una lectura de las notificaciones del móvil (en una llamada a herramienta o en su salida;
movil.py pone «[notificación del móvil]» en cada línea, así que también se reconoce la salida filtrada con grep).
DE_OTRA / HABLA_DE_NOTIFICACIONES: detectan lo que llega de otra conversación (contexto de otros canales, session_search).
Uso: from privacidad import tachar
"""
import re
from pathlib import Path

ENV = Path("/home/server/.hermes/.env")
SEP = r"[ .\-\u00a0\u202f]"                     # separadores entre grupos de cifras: espacio, punto, guion, espacio duro
SEP_T = r"[ .\-/\t\u00a0\u2009\u202f]"          # en tarjetas, también barra, tabulador y espacio fino
FECHA = r"(?!\d{4}-\d\d-\d\d|\d\d?[/.-]\d\d?[/.-]\d{2,4}(?!\d))"                     # nunca empieza en una fecha
UNIDAD = (r"(?i:ms|s|seg|segundos?|min|minutos?|h|horas?|d[ií]as?|semanas?|meses|a[nñ]os|km|kg|kb|mb|gb|tb|px|visitas|"
          r"personas|usuarios|habitantes|seguidores|veces|l[ií]neas|palabras|caracteres|p[aá]ginas|unidades|pasos)")
IMPORTE = r"\s?(?:€|\$|%|(?i:eur|euros?|usd|d[oó]lares)\b)"
FIN_NUM = rf"(?![\w/@]|[.,:]\d|{IMPORTE}|\s{UNIDAD}\b)"   # ni sigue un número, una hora, un importe o una unidad
ANO = r"(?:19|20)\d\d"


def num(a, b):
    """De a a b cifras, con separadores entre ellas; no empieza en mitad de otro número, en un importe («$49.99») ni en una fecha."""
    return rf"(?<![\d.,$€£]){FECHA}\d(?:{SEP}?\d){{{a - 1},{b - 1}}}{FIN_NUM}"


def valores_env():
    try:
        return [(m.group(1), m.group(2).strip().strip("\"'"))
                for m in re.finditer(r"^([A-Z0-9_]+)=(.+)$", ENV.read_text(), re.M)]
    except OSError:
        return []


def _secretos():
    """Valores del .env: los de 6 o más caracteres se tachan en cualquier parte (salvo rutas, que no son secretas);
    los cortos de nombre secreto (p. ej. una contraseña de sudo de 4 cifras) solo detrás de una palabra clave,
    para no tachar cualquier año o importe que coincida. De un teléfono se tachan también sus formas sin «+» y sin 34."""
    largos, cortos = set(), set()
    for k, v in valores_env():
        if len(v) >= 6 and not v.startswith(("/", "~")):
            largos.add(v)
            if re.fullmatch(r"\+\d{8,15}", v):
                largos.update({v[1:]} | ({v[3:]} if v.startswith("+34") else set()))
        elif len(v) >= 3 and re.search(r"KEY|TOKEN|SECRET|PASSW|HASH|PIN", k):
            cortos.add(v)
    return sorted(largos, key=len, reverse=True), sorted(cortos, key=len, reverse=True)


LARGOS, CORTOS = _secretos()
PALABRA_CLAVE = r"\b(?:sudo|contraseñas?|claves?|password|passwd|pwd|pass|passcode|pin)\b"
CORTO = [re.compile(rf"(?i:{PALABRA_CLAVE})[^\n]{{0,40}}?(?<!\w)(?P<v>{re.escape(v)})(?!\w)") for v in CORTOS]

YA = r"(?!\[[^\]\n]{0,25}tachad[oa]\])"                  # no volver a tachar lo ya tachado
NO_ES = (r"(?!(?:segur[oa]s?|correct[oa]|incorrect[oa]|válid[oa]|inválid[oa]|débil|fuerte|larg[oa]|cort[oa]|nuev[oa]|viej[oa]|"
         r"antigu[oa]|igual|mism[oa]|distint[oa]|diferente|obligatori[oa]|necesari[oa]|fácil|difícil|sencill[oa]|complicad[oa]|"
         r"temporal|provisional|caducad[oa]|cambiad[oa]|actualizad[oa]|olvidad[oa]|guardad[oa]|bloquead[oa]|robust[oa]|"
         r"privad[oa]|secret[oa]|personal|únic[oa]|requerid[oa]|opcional|vací[oa]|esta|este|esto|aquí|"
         r"wrong|correct|incorrect|strong|weak|same|different|required|optional)\b)")
VALOR = rf"[ \t*_`\"'«“]*(?P<v>{YA}{FECHA}{NO_ES}(?!https?://|//)[^\s`\"'»”]{{3,}}[^\s`\"'»”,;.])(?!{IMPORTE}|[ \t]{UNIDAD}\b)"   # el valor de una clave (sin comillas, negrita ni «,;.» del final; ni un importe)
VALOR_CLAVE = VALOR.replace("(?P<v>", rf"(?P<v>(?!{ANO}\b)")   # tras «clave … :», un año no («La clave para el éxito: 2026»)
FUERTE = r"(?=\S*?(?:\d|[^\w\s`\"'»”](?=[^\s`\"'»”])|(?<=\w)[A-Z]))"     # con cifra, símbolo o mayúscula por dentro
CON_CIFRA = rf"{YA}(?=\S*\d){FECHA}(?!{ANO}\b)[^\s`\"'»”]{{3,}}[^\s`\"'»”,;.]"   # valor suelto: solo si lleva alguna cifra (y no es un año)
NI_IMPORTE_NI_VERSION = rf"(?![vV]?\d+(?:[.,:]\d+)+(?!\w))"                       # «300,00», «v2.0», «10:30» no son claves
# Delante de «clave» tiene que haber un artículo, un inicio de línea (con viñeta, emoji o numeración), una flecha/barra, una
# coma o una sola palabra al principio de la línea («Netflix clave: …»): «la clave es…», «• Clave: …», «1. Clave: …»,
# «Wifi → clave: …», «usuario fran, clave …», «Wifi: X / clave: …»; no «punto clave: …» ni «palabra clave: …».
NO_ANTES = (r"(?!(?i:palabras?|puntos?|ideas?|datos?|fechas?|horas?|d[ií]as?|a[nñ]os?|momentos?|factor(?:es)?|elementos?|piezas?|"
            r"figuras?|papel(?:es)?|temas?|preguntas?|aspectos?|conceptos?|jugador\w*|pasos?|fases?|testigos?|personas?|cargos?|"
            r"puestos?|sectores?|mensajes?|informaci[oó]n|frases?|cuesti[oó]n|asuntos?|pistas?|notas?|partes?|posici[oó]n|zonas?|"
            r"lugar(?:es)?|[aá]reas?|competencias?|habilidad(?:es)?|rol(?:es)?|tareas?|objetivos?|metas?|reuni[oó]n|decisi[oó]n|"
            r"partidos?|documentos?|pruebas?|t[eé]rminos?|rasgos?|recursos?|herramientas?|lecci[oó]n|principios?|valor(?:es)?|"
            r"resumen|en|es|la|el|lo|una?|y|o|pero|como|muy|tan|m[aá]s|esa|esta|eso|esto|otra|gran|ser|era|sin|con|cada|toda|por|para)\b)")
ANTES_CLAVE = (r"(?:\b(?i:la|las|tu|tus|mi|mis|su|sus|una|nueva|esa|esta)\s+|^(?:[^\w\n]{0,6}|\d{1,2}[.)][ \t]*)"
               r"|(?<=[→|•:(,])[ \t]*|(?<=[→|•\-–—:(] )|(?<=/)[ \t]+"
               rf"|^[ \t>*•\-]*{NO_ANTES}[\w.+\-]{{2,20}}[ \t]+)")
CLAVE = rf"(?:{ANTES_CLAVE}(?i:clave)\b)"
CONTRA = r"(?i:(?<!boarding )(?<!season )(?<!gestor de )(?<!gestores de )\b(?:contraseñas?|password|passwd|pwd|pw|passcode|pass)\b)"
MEDIO = r"(?:[ \t]+(?!(?i:es|era|será|sería|is|was|no|not|que|sigue)\b)[\w.\-]+|[ \t]*\([^()\n]{1,30}\)){0,4}?[ \t]*"   # «del wifi», «(wifi)»…
MEDIO_LARGO = r"(?:[ \t]+(?!(?i:es|era|será|sería|is|was|no|not|que|sigue)\b)[\w.\-]*[\w\-]|[ \t]*\([^()\n]{1,30}\)){0,8}?[ \t]*"   # con «:»: «de acceso a la banca online»
ES = (r"(?:,?[ \t]*(?i:que)[ \t]+)?\b(?i:es|era|será|sería|is|was|sigue siendo|seguirá siendo|pasa a ser)\b[ \t]*:?"
      r"(?:[ \t]*(?i:esta|la siguiente|this)[ \t]*:)?")
CRED = r"(?i:banco|wifi|wi-fi|puerta|portal|acceso|cuenta|correo|email|gmail|router|móvil|tarjeta|app|alarma|caja|usuario|sudo|servidor|ordenador|pc|portátil|red|web|casa|garaje|candado|taquilla|buzón|trastero|cajero)"
MEDIO_CRED = rf"(?:[ \t]+(?!(?i:es|era|será|sería|no)\b)[\w.\-]+){{0,3}}?[ \t]+{CRED}\b(?:[ \t]+(?!(?i:es|era|será|sería|no)\b)[\w.\-]+){{0,2}}?[ \t]*"
# sin verbo, «de» + 1-2 palabras cualesquiera: «contraseña de Netflix Gato1234», «la clave del cajero 4413»
MEDIO_SV = r"(?:[ \t]+(?i:de|del|de la|de mi|de tu|for|of)(?:[ \t]+(?!(?i:es|era|será|no|y|o|a|en|con|para)\b)[\w.+\-]+){1,2}?)"
NEGRITA = r"[*_`]*"
ADJ = r"(?:[ \t]+(?i:nuev[oa]|provisional|temporal|actual|antigu[oa]|viej[oa]|maestra|inicial|por defecto))?"
CODIGO_NO = (r"(?!\s+(?:de\s+|del\s+)?(?:la\s+|el\s+)?(?:error|postal|penal|civil|fuente|abierto|qr|barras|estado|respuesta|salida|http|"
             r"conducta|vestimenta|colores|honor|comercio|circulaci[oó]n|programa|python|java|asignatura|curso|aula|materia|cliente|"
             r"socio|alumno|empleado|producto|art[ií]culo|descuento|promocional|promoci[oó]n|cup[oó]n|reserva|invitaci[oó]n|"
             r"referencia|pedido|seguimiento|env[ií]o|vuelo|modelo|versi[oó]n|proyecto|tarifa)\b)")
NO_CODE = r"(?<!error )(?<!status )(?<!source )(?<!exit )(?<!zip )(?<!area )(?<!country )(?<!postal )(?<!qr )(?<!bar )(?<!http )(?<!dress )"
LLAVE = rf"(?i:contraseña|clave|password|pin|passcode|{NO_CODE}code|c[oó]digo{CODIGO_NO})"   # lo que nombra el valor en «Gato1234 es la contraseña»
# «4413 es la clave» solo es una clave con complemento («de acceso», «SMS», «del portal»…): «Ahorrar 1000 es la clave» no
CLAVE_COMPL = (rf"[ \t]+(?i:de[ \t]+acceso|sms|temporal|provisional|secreta|de[ \t]+un[ \t]+solo[ \t]+uso"
               rf"|de[ \t]+(?:firma|operaciones|confirmaci[oó]n|verificaci[oó]n|seguridad)\b"
               rf"|(?:de[ \t]+(?:la[ \t]+|el[ \t]+|tu[ \t]+|mi[ \t]+)?|del[ \t]+){CRED}\b)")

# WhatsApp: JID («34600111222@s.whatsapp.net», «…@lid», grupos «…@g.us»); van antes que los valores del .env
JID = re.compile(r"(?<![\w+])\+?\d{6,20}(?:-\d{6,12})?(?::\d{1,3})?@(?:s\.whatsapp\.net|lid|c\.us|g\.us)\b")


def luhn(s):
    """Las tarjetas cumplen siempre el dígito de control de Luhn; un nº de caso o de pedido casi nunca."""
    return sum(d if i % 2 == 0 else (2 * d - 9 if d > 4 else 2 * d) for i, d in enumerate(map(int, reversed(s)))) % 10 == 0


def _iban(m):
    """Un IBAN de verdad cumple el control mod 97; si no, solo se tacha si delante dice IBAN o cuenta (un nº de serie no)."""
    s = re.sub(r"[^A-Za-z0-9]", "", m.group(0)).upper()
    valido = len(s) >= 15 and int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1
    antes = m.string[max(0, m.start() - 25):m.start()]
    if m.group("pais"):                                      # «ES 91 2100…» (país separado): solo si el control cuadra
        return "[IBAN tachado]" if valido else m.group(0)
    return "[IBAN tachado]" if valido or re.search(r"(?i)\b(?:iban|cuenta|account|cta|ccc)\b", antes) else m.group(0)


def _token(m):
    """Cadena larga sin formato conocido: es una clave si mezcla mayúsculas, minúsculas y cifras (no un hash ni un id en hex)."""
    s = m.group(0)
    clases = sum(bool(re.search(p, s)) for p in (r"[A-Z].*[A-Z]", r"[a-z].*[a-z]", r"\d.*\d"))
    return "[clave tachada]" if clases == 3 else s


def _cambia(sustituto):
    """Si el patrón tiene grupo «v», tacha solo ese trozo y conserva lo de delante (la palabra clave).
    Un año (1990, 2026) tras la palabra solo se tacha si va justo detrás o tras «es»/«:» («PIN 1990», «Tu código es 2019»),
    no en «Código Penal de 1995» ni en «Pin de la chaqueta 2026»."""
    def f(m):
        if "v" in m.re.groupindex and m.group("v") is not None:
            if "k" in m.re.groupindex and re.fullmatch(ANO, m.group("v")):
                hueco = m.string[m.end("k"):m.start("v")]
                pegado = not re.sub(r"[\s*_`:=]|\b(?i:es|era|será|is|was)\b", "", hueco)
                if not pegado and not (len(hueco) <= 25 and re.search(r"(?i)(?:\b(?:es|era|será|is|was)|[:=])[\s*_`]*$", hueco)):
                    return m.group(0)
            return m.group(0)[:m.start("v") - m.start()] + sustituto + m.group(0)[m.end("v") - m.start():]
        return sustituto
    return f


REC_COD = re.compile(r"(?<![\w-])(?:[0-9A-Za-z]{4,5}(?:[ -][0-9A-Za-z]{4,5})?|[0-9A-Za-z]{6,10})(?![\w-])")


def _recuperacion(m):
    """Códigos de recuperación (2FA de respaldo): todos los de la lista, en esa línea y en las siguientes que solo llevan códigos."""
    def codigo(c):
        s = c.group(0)
        return "[código tachado]" if re.search(r"\d", s) and not re.fullmatch(ANO, s) else s
    return m.group(0)[:m.start("v") - m.start()] + REC_COD.sub(codigo, m.group("v"))


REGLAS = [   # (patrón, sustituto o función); el grupo «v», si lo hay, es lo único que se tacha
    # menciones de WhatsApp «@34600111222»
    (re.compile(r"(?<![\w.])@\d{8,15}\b"), "@[teléfono tachado]"),
    # tokens y claves con formato conocido
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[clave tachada]"),
    (re.compile(r"\b(?:sk-(?:ant-|proj-|or-)?[\w-]{20,}|AIza[\w-]{30,}|AQ\.[\w-]{30,}|github_pat_\w{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
                r"|(?:AKIA|ASIA)[0-9A-Z]{16}|xox[abprs]-[\w-]{8,}|ya29\.[\w-]{10,}|hf_[A-Za-z0-9]{20,}|glpat-[\w-]{20,}"
                r"|gsk_[A-Za-z0-9]{20,}|[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|GOCSPX-[\w-]{20,}|xai-[A-Za-z0-9]{20,}|pplx-[A-Za-z0-9]{20,}"
                r"|npm_[A-Za-z0-9]{30,}|tvly-[\w-]{20,}|r8_[A-Za-z0-9]{20,}|SG\.[\w-]{16,}\.[\w-]{16,})"
                r"|\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}"
                r"|\b\d{8,10}:AA[\w-]{30,}"                                   # bot de Telegram
                r"|\b[MNO][\w-]{23,27}\.[\w-]{6}\.[\w-]{27,40}\b"             # bot de Discord
                r"|\b1//0[\w-]{40,}"                                          # refresh token de Google
                r"|\$(?:argon2(?:id|i|d)|2[aby]|scrypt|pbkdf2[\w-]*)\$\S{20,}"   # hash de contraseña ($argon2id$…, $2b$…)
                r"|\b(?:argon2|bcrypt(?:_sha256)?|scrypt|pbkdf2[_:]sha\d+)(?::\d+)*\$\S{20,}"   # (formato Django/Werkzeug)
                r"|(?<=hooks\.slack\.com/services/)[\w/]{20,}|(?<=/api/webhooks/)\d+/[\w-]{20,}"   # webhooks de Slack y Discord
                r"|\b[A-Za-z0-9]{5}(?:-[A-Za-z0-9]{5}){4}\b"), "[clave tachada]"),   # contraseña de aplicación (Nextcloud) / clave de producto
    (re.compile(r"(?i:\bbearer)\s+(?P<v>[\w\-.~+/]{16,}=*)"), "[clave tachada]"),
    (re.compile(r"(?i:\bauthorization:\s*basic)\s+(?P<v>[A-Za-z0-9+/]{8,}=*)"), "[clave tachada]"),
    (re.compile(r"(?i:\b[a-z][a-z0-9+.-]*)://[^/\s:@\[\]]*:(?P<v>[^/\s@\[\]]+)@"), "[clave tachada]"),   # usuario:clave@ dentro de una URL (también sin usuario)
    # contraseña de aplicación de Google (4 grupos de 4 letras): antes que las reglas de contraseña, para taparla entera
    (re.compile(r"(?i:contraseñas? de (?:la )?(?:aplicación|app)|clave de (?:la )?aplicación|app[ -]?password)[^\n]{0,30}?"
                r"(?P<v>\b[a-zA-Z]{4}(?:[ \u00a0][a-zA-Z]{4}){3}\b)"), "[clave tachada]"),
    # frase semilla (cartera de criptomonedas): en la misma línea o en las siguientes, con espacios, comas o numeración
    (re.compile(r"(?i:\b(?:seed(?: phrase)?|frase (?:semilla|de recuperación)|mnemonic|recovery phrase"
                r"|(?:las )?(?:12|24) palabras(?: de (?:recuperación|la cartera|seguridad))?)\b)[^\w\n]{0,6}"
                r"(?:\r?\n[ \t>*•\-]*(?:\d{1,2}[.)][ \t]*)?)?"
                r"(?P<v>(?:[a-z]+(?:[ \t]*,[ \t]*|[ \t]+|[ \t]*\r?\n[ \t>*•\-]*(?:\d{1,2}[.)][ \t]*)?)){11,23}[a-z]+)"), "[clave tachada]"),
    # clave privada de una cartera (0x + 64 hex) tras la palabra
    (re.compile(r"(?i:\b(?:private[ _-]?key|clave privada)\b)[^\w\n]{0,6}(?P<v>(?:0x)?[0-9a-fA-F]{64})\b"), "[clave tachada]"),
    # frase de paso (wpa_passphrase=…, «Passphrase: correct horse battery staple»): toda la línea
    (re.compile(rf"(?i:\b(?:\w*_)?passphrase\b|\bfrase de (?:paso|contraseña)\b){NEGRITA}[ \t]*[=:][ \t*_`\"'«“]*"
                rf"(?P<v>{YA}[^\n]*?[^\s`\"'»”*_.,;])[ \t*_`\"'»”.,;]*$", re.M), "[clave tachada]"),
    # códigos de recuperación de la verificación en dos pasos (Google, GitHub…): toda la lista
    (re.compile(r"(?i:c[oó]digos?\s+de\s+(?:recuperaci[oó]n|respaldo|emergencia)|c[oó]digos\s+de\s+seguridad|backup\s+codes?|recovery\s+codes?)"
                r"(?P<v>[^\n]*(?:\n[ \t>*•\-]*(?:\d{1,2}[.)][ \t]*)?(?:[0-9A-Za-z]{4,10}(?![0-9A-Za-z])[ \t,;\-]*)+(?=\n|\Z))*)"),
     _recuperacion),
]
# con «:» (o «→», «|»), un valor flojo seguido de más palabras es una frase normal: «Clave: llevar el DNI», «Contraseña: la que te dije»
FUERTE_V = re.compile(r"\S*?(?:\d|[^\w\s`\"'»”.\-](?=[^\s`\"'»”])|[a-zñáéíóú][A-ZÑÁÉÍÓÚ])")
UN_NUMERO = re.compile(r"[ \t]+\S*\d\S*[ \t]*[.,;!?)]*[ \t]*")   # «Contraseña: Gato 1234»: lo que sigue es solo un número


# en los datos de un pago móvil, una cédula: 7-8 cifras, con o sin puntos (nunca un importe en Bs/€/$, una referencia ni un teléfono)
CEDULA_PM = re.compile(r"(?<![\w.,/+$€])[VEve]?-?\d{1,2}\.?\d{3}\.?\d{3}(?!\w|[.,/-]\d|[ \t]?(?i:bs\b|bs\.|bol[ií]vares|€|\$|usd|eur|euros?\b|d[oó]lares))")
NO_CEDULA_PM = re.compile(r"(?i)(?:\b(?:bs\.?|bol[ií]vares|usd|eur|euros?|d[oó]lares|monto|importe|total|cantidad|de|por|son|ref|referencia|"
                          r"operaci[oó]n|comprobante|recibo|n[º°o]|nro)|[$€])[ \t:.#º°]*$")


def _pago_movil(m):
    bloque = m.group("v")
    tels = [x.span() for x in TELEFONO.finditer(bloque)]

    def f(c):
        if NO_CEDULA_PM.search(bloque[max(0, c.start() - 15):c.start()]) or any(a < c.end() and c.start() < b for a, b in tels):
            return c.group(0)
        return "[DNI tachado]"
    return m.group(0)[:m.start("v") - m.start()] + CEDULA_PM.sub(f, bloque)


def _clave(sustituto):
    cambia = _cambia(sustituto)

    def f(m):
        if m.group("v") is not None and m.group("sep") and m.group("sep") in ":→|" and "_" not in (m.groupdict().get("nombre") or ""):
            resto = m.string[m.end("v"):].split("\n", 1)[0]
            if not FUERTE_V.match(m.group("v")) and re.match(r"[ \t]+[^\s|]", resto) and not UN_NUMERO.fullmatch(resto):
                return m.group(0)
        return cambia(m)
    return f


def _llave(sustituto):
    """«4413 es la clave»: con «clave» sin complemento y un valor solo de cifras, es una frase normal («Ahorrar 1000 es la clave»)."""
    cambia = _cambia(sustituto)

    def f(m):
        if (m.group("ll") or "").lower() == "clave" and not m.group("nueva") and not m.group("compl") and not re.search(r"[^\W\d_]", m.group("v")):
            return m.group(0)
        return cambia(m)
    return f


REGLAS += [
    # NOMBRE_DE_CLAVE=valor (también ACCESS_TOKEN=, X_API_KEY=, DB_PASS=, MYSQL_PWD=, psk=, aws_secret_access_key = …, **Token**: …)
    (re.compile(rf"(?P<nombre>(?i:\b(?:\w*_)?(?:api[ _-]?key|token|secret|passw(?:or)?d|contraseña)\b|\b\w+_key\b"
                rf"|\b\w*_(?:pass|pwd|psk)\b|\bpsk\b)){NEGRITA}\s*(?P<sep>[=:])(?!\*\*\*)"
                rf"[ \t*_`\"'«“]*(?P<v>{YA}(?!(?i:true|false|none|null|yes|no|on|off)\b)(?!\d{{1,3}}\b)[^\s`\"'»”]+)"), "[clave tachada]"),   # («KEY=***» ya viene tapado por Hermes)
    # API keys y secretos de cliente con palabras en medio: «la API key de OpenWeather: 0123…», «client secret es …»
    (re.compile(rf"(?i:\bapi[ _-]?keys?\b|\bclient[ _-]?secret\b|\bsecret[ _-]?key\b|\baccess[ _-]?key\b|\bauth[ _-]?token\b)"
                rf"{MEDIO}{NEGRITA}(?:{ES}|[:=])[ \t*_`\"'«“]*{FUERTE}{VALOR}", re.M), "[clave tachada]"),
    (re.compile(rf"(?i:\bkey\b){NEGRITA}[ \t]*[=:][ \t*_`\"'«“]*(?P<v>{YA}{FECHA}{NI_IMPORTE_NI_VERSION}(?=[^\s`\"'»”]*\d)[^\s`\"'»”]{{12,}})"), "[clave tachada]"),   # «key: 0123…»
    (re.compile(r"(?i:\b(?:token|key)\b)[ \t:=]+(?P<v>[0-9a-fA-F]{32,})\b"), "[clave tachada]"),   # «token 0123…» (hex)
    # contraseñas en lenguaje natural: «mi contraseña es X», «clave: X», «la clave de la puerta es 4413», «password X1»
    (re.compile(rf"{CONTRA}{MEDIO_LARGO}{NEGRITA}(?:{ES}|[:=→])[ \t*_`]*[«“\"'](?P<v>{YA}{NO_ES}[^»”\"'\n]{{3,60}})[»”\"']", re.M),
     "[clave tachada]"),                                                    # entre comillas: «Gato 1234»
    (re.compile(rf"{CLAVE}{MEDIO_LARGO}{NEGRITA}(?:{ES}|[:=→])[ \t*_`]*[«“\"'](?P<v>{YA}(?=[^»”\"'\n]*?(?:\d|(?<=\w)[A-Z]))[^»”\"'\n]{{3,60}})[»”\"']", re.M),
     "[clave tachada]"),
    (re.compile(rf"{CONTRA}(?:{MEDIO}{NEGRITA}{ES}|{MEDIO_LARGO}{NEGRITA}(?P<sep>[:=|→])){VALOR}", re.M), "[clave tachada]"),
    (re.compile(rf"{CLAVE}{MEDIO_LARGO}{NEGRITA}(?P<sep>[:=]){VALOR_CLAVE}", re.M), "[clave tachada]"),
    (re.compile(rf"{CLAVE}{MEDIO}{ES}[ \t*_`\"'«“]*{FUERTE}{VALOR}", re.M), "[clave tachada]"),
    (re.compile(rf"(?:{CLAVE}|(?i:\bclave)){MEDIO_CRED}{NEGRITA}(?:{ES}|[:=]){VALOR}", re.M), "[clave tachada]"),   # «la clave del banco es girasol», «Y clave del wifi: X»
    (re.compile(rf"(?i:\btoken){MEDIO}{NEGRITA}(?:{ES}|[:=])[ \t*_`\"'«“]*{FUERTE}{VALOR}", re.M), "[clave tachada]"),
    # sin verbo, el valor tiene que llevar alguna cifra: «contraseña Gato1234», «la contraseña del wifi Gato1234», «Contraseña⏎Gato1234»,
    # «contraseña de Netflix Gato1234» (ni un importe, ni una versión, ni una hora)
    (re.compile(rf"(?:(?:{CONTRA}|{CLAVE}){ADJ}(?:{MEDIO_CRED}|{MEDIO_SV})?|(?i:\bclave){MEDIO_CRED}){NEGRITA}[ \t|:*→\-–—]*(?:\r?\n[ \t>*_`•\-]*)?"
                rf"{NI_IMPORTE_NI_VERSION}(?P<v>{CON_CIFRA})(?!{IMPORTE}|[ \t]{UNIDAD}\b)", re.M), "[clave tachada]"),
    # «he cambiado la contraseña (del wifi) a Gato1234», «changed my password to Sunflower2026»
    (re.compile(rf"(?i:\b(?:cambi\w*|puse|pon\w*|set|changed?|update[ds]?|actualic\w*|actualiz\w*)\b)[^\n]{{0,30}}?(?:{CONTRA}|(?i:\bclave\b))"
                rf"[^\n]{{0,25}}?\b(?i:a|to|por)[ \t]+{NI_IMPORTE_NI_VERSION}(?P<v>{CON_CIFRA})"), "[clave tachada]"),
    # el valor delante: «Gato1234 es la contraseña del wifi», «Usa Gato1234 como contraseña», «puse Gato1234 de contraseña»
    (re.compile(rf"(?<![\w@./:-])(?P<v>{CON_CIFRA})(?=[ \t]+(?i:es|era|será|is|was)[ \t]+(?i:la|tu|mi|su|el|the|your|my)[ \t]+"
                rf"(?P<nueva>(?i:nueva|new)[ \t]+)?(?P<ll>{LLAVE})\b(?P<compl>{CLAVE_COMPL})?)"), _llave("[clave tachada]")),
    (re.compile(rf"(?i:\b(?:usa|use|pon|puse|usé|uso|utiliza)\b)[ \t]+(?P<v>{CON_CIFRA})[ \t]+(?i:como|as|de)[ \t]+"
                rf"(?:(?i:la|tu|mi|su|el|the|your|my)[ \t]+)?(?:(?i:nueva|new)[ \t]+)?{LLAVE}\b"), "[clave tachada]"),
    # «Usuario: fran / clave: Gato1234», «login: fran / Gato1234»
    (re.compile(rf"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+[ \t]*/[ \t]*(?P<v>{CON_CIFRA})"), "[clave tachada]"),
    (re.compile(r"(?i:\bmysql(?:dump|admin)?\b)[^\n|;]*?[ \t]-p['\"]?(?P<v>[^\s'\"]{4,})"), "[clave tachada]"),   # mysql -u root -pGato1234
    (re.compile(r"(?i:\bsshpass)[ \t]+-p[ \t]*['\"]?(?P<v>[^\s'\"]+)"), "[clave tachada]"),
    (re.compile(r"(?i:\becho)[ \t]+['\"]?(?P<v>[^\s'\"|]{4,})['\"]?[ \t]*\|[ \t]*sudo[ \t]+-S\b"), "[clave tachada]"),
    # «la contra del wifi es Gato1234», «contra: Gato1234» (abreviatura; «contra» es también una palabra normal: valor fuerte)
    (re.compile(rf"(?:\b(?i:la|tu|mi|su)[ \t]+(?i:contra)|^[ \t>*•\-]*(?i:contra))\b{MEDIO}{NEGRITA}(?:{ES}|[:=])[ \t*_`\"'«“]*{FUERTE}{VALOR}", re.M),
     "[clave tachada]"),
    (re.compile(rf"(?i:\b(?:usuario|user(?:name)?|login)\b)[ \t:]+[^\s/:]+[ \t]*/[ \t]*"
                rf"(?:(?i:clave|contraseña|password|pass|pwd)[ \t]*:?[ \t]*)?(?P<v>{YA}(?!(?i:clave|contraseña|password|pass|pwd)\b)\S{{4,}})"), "[clave tachada]"),
    # cuentas: IBAN (con o sin separadores; un nº de serie con esa forma no), SWIFT/BIC tras la palabra
    (re.compile(rf"(?<![A-Za-z0-9])(?:[A-Za-z]{{2}}|(?P<pais>[A-Z]{{2}}){SEP})\d{{2}}(?:{SEP}?[A-Z0-9]{{4}}){{2,7}}(?:{SEP}?[A-Z0-9]{{1,3}})?(?![A-Za-z0-9])"), _iban),
    (re.compile(r"(?i:\b(?:swift|bic)\b)(?:\s*/\s*(?i:swift|bic))?(?:[^\w\n]{0,6}(?i:code|código))?[^\w\n]{0,6}"
                r"(?P<v>\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b)"), "[SWIFT tachado]"),
    # documentos: DNI/NIE (con o sin espacio antes de la letra), cédula/RIF venezolanos (también sin guion: «V12345678»,
    # «V 12.345.678»), y tras la palabra (también sin letra y seguido de coma: «cédula 12345678, Banesco»)
    (re.compile(r"\b(?:\d{8}|\d{2}\.\d{3}\.\d{3})(?:[ -]?[A-HJ-NP-TV-Z]|[a-hj-np-tv-z])\b|\b[XYZ][ -]?\d{7}[ -]?[A-Z]\b"
                r"|\b[VEJPG]-?\d{8}-?\d\b|\b[VE][- ]?\d{1,2}\.\d{3}\.\d{3}\b|\b[VE]-?\d{7,8}\b"), "[DNI tachado]"),
    (re.compile(r"(?:(?i:\b(?:dni|nie|nif|c[eé]dula(?:\s+de\s+identidad)?|rif|documento\s+(?:nacional\s+)?de\s+identidad)\b)|\bC\.?I\b)"
                r"(?:[^\w\n]{0,6}|[^\d\n]{0,30}?(?:\b(?i:es|era|is)\b|:)[^\w\n]{0,3}|[ \t]+(?i:de|del)[ \t]+[^\W\d]+(?:[ \t]+[^\W\d]+)?[^\w\n]{0,3})"
                r"(?:(?i:el)[ \t]+)?(?:(?i:n\.?\s?[º°o]\.?|número|num\.?)[^\w\n]{0,3})?"
                r"(?P<v>(?:[VEJPGXYZvejpgxyz][ -]?)?\d[\d.]{5,10}\d(?:[ -]?[A-Za-z]\b|-\d\b)?)(?!\d|,\d)"), "[DNI tachado]"),
    # pasaporte: también con palabras en medio («el pasaporte de Nuria es …», «pasaporte venezolano …»); al menos 6 cifras
    (re.compile(r"(?i:\b(?:pasaporte|passport)\b)(?:(?:[ \t]+[^\W\d_]+){1,2}?)?"
                r"(?:[^\w\n]{0,6}|[^\d\n]{0,30}?(?:\b(?i:es|era|is|was)\b|:)[^\w\n]{0,3})(?:(?i:el|the)[ \t]+)?"
                r"(?:(?i:n\.?\s?[º°o]\.?|número|number|no\.?)[^\w\n]{0,3})?(?P<v>\b(?=(?:[A-Z]*\d){6})[A-Z0-9]{6,9}\b)"), "[pasaporte tachado]"),
    # nº de la Seguridad Social: también «Seguridad Social: 28/12345678/90», «Nº SS: 281234567890», «Nº S.S. 28 1234567890»
    # (no un número con puntos de miles ni un importe: «Seguridad Social: 21.000.000 afiliados», «… 1.234.567 €»)
    (re.compile(r"(?i:\b(?:nss|nuss|naf|itin|n[úu]mero (?:de (?:la )?)?seguridad social|n[úu]m(?:ero)?\.? de afiliaci[oó]n(?: a la seguridad social)?"
                r"|ssn|social security(?: number)?|seguridad social|n[º°o]\.?[ \t]*(?:de[ \t]+(?:la[ \t]+)?)?s\.?[ \t]?s\.?)\b)[^\d\n]{0,6}"
                rf"(?!\d{{1,3}}(?:\.\d{{3}}){{2,}}(?!\d))(?P<v>\d[\d/ .-]{{7,14}}\d)(?!\d|{IMPORTE})"), "[número tachado]"),
    # pago móvil (Venezuela): la cédula va sin la palabra, en la misma línea o en las 4 siguientes («Banesco, 12.345.678, 0414…»)
    (re.compile(r"(?i:\bpago[ \t]*m[oó]vil\b)(?P<v>[^\n]*(?:\n[^\n]*){0,4})"), lambda m: _pago_movil(m)),
    # tokens sin formato conocido: una cadena suelta de 32 o más letras y cifras que mezcla mayúsculas, minúsculas y cifras
    (re.compile(r"(?<![\w/.=?&#:%@-])[A-Za-z0-9_-]{32,}(?![\w/=?&#%@-]|[.:]\w)"), _token),
]
# tarjetas (13-19 cifras) y cuentas (20-24): agrupadas o seguidas, también partidas en dos líneas o con otra agrupación
ESTRICTA = (rf"\d{{13,24}}|\d{{4}}(?:(?:{SEP_T}|\r?\n)\d{{4}}){{2,3}}(?:{SEP_T}|\r?\n)\d{{1,4}}"
            rf"|\d{{4}}{SEP_T}\d{{6}}{SEP_T}\d{{4,5}}|\d{{4}}{SEP_T}\d{{4}}{SEP_T}\d{{2}}{SEP_T}\d{{10}}")
FIN_TARJETA = r"(?!\d|[.,]\d|\s?(?:€|\$|%|(?i:eur|euros?|usd|d[oó]lares)\b))"
TARJETA = re.compile(rf"(?<![\d/-])(?:{ESTRICTA}|(?P<otra>{FECHA}\d{{2,4}}(?:{SEP_T}\d{{2,6}}){{2,6}})){FIN_TARJETA}")
SOLO_ESTRICTA = re.compile(rf"(?<![\d/-])(?:{ESTRICTA})(?P<otra>(?!)x)?{FIN_TARJETA}")
REFERENCIA = re.compile(r"(?i)\b(?:pedido|order|ref|referencia|factura|localizador|reserva|booking|expediente|caso|case|ticket|informe|report|id)\W{0,4}$")
OTP_KW = (rf"(?<!\[)(?i:\b(?:c[oó]digo{CODIGO_NO}|{NO_CODE}code|pin|otp|contraseña|password|passcode|verif\w*)\b"
          rf"|\b(?:tu|su|la|una|your|the)[ \t]+(?:(?:nueva|temporal|provisional|secreta)[ \t]+clave\b|clave\b(?={CLAVE_COMPL})))")
ES_O_DOS_PUNTOS = r"(?:\b(?i:es|era|será|is|was|son)\b|[:=])"
# entre la palabra y el número: hasta 25 letras (pero no si lo que sigue es «1234 es 4413»: el valor es el segundo); o hasta
# 80 caracteres cualesquiera (importes, «S25», «5 min») si acaba en «es»/«:»; o el número en la línea siguiente
GAP = (rf"(?:[^\d\n]{{0,25}}?(?!\d[\d \-.]{{0,10}}[ \t]*{ES_O_DOS_PUNTOS}[ \t*_`]*\d)"
       rf"|[^\n]{{0,80}}?{ES_O_DOS_PUNTOS}[ \t*_`]*|[ \t*_:`]*\r?\n[ \t>*_`•\-]*)")
GAP_ES = rf"[^\n]{{0,80}}?{ES_O_DOS_PUNTOS}[ \t*_`]*"
CODIGO_KW = (rf"(?i:\b(?:c[oó]digos?(?!\s+postal){CODIGO_NO}|{NO_CODE}codes?|otp|2fa|verificaci[oó]n|verification"
             r"|clave\s+(?:sms|de\s+(?:firma|operaciones|la\s+operaci[oó]n|confirmaci[oó]n))|firma\s+digital)\b)")
NUMEROS = [   # números que se tachan por la palabra que llevan delante (el grupo «v»; «k» es la palabra)
    (re.compile(rf"(?i:\b(?:cuenta|account|acct|routing|aba|ccc)\b)[^\d\n]{{0,25}}?(?P<v>{num(6, 24)})"), "[número tachado]"),
    (re.compile(rf"(?P<k>(?i:\b(?:cvv2?|cvc2?|ccv|csc|c[oó]digo de seguridad|security code|n[úu]meros? de (?:detr[aá]s|atr[aá]s)"
                rf"|(?:tres|3) (?:(?:n[úu]meros|d[ií]gitos|cifras) )?de (?:detr[aá]s|atr[aá]s))\b))[^\d\n]{{0,12}}?(?P<v>(?!{ANO}\b){num(3, 4)})"), "[CVV tachado]"),
    (re.compile(rf"(?P<k>(?i:\bp\.?i\.?n\.?(?![a-zñáéíóú])|\bpuk\b|\bn[úu]mero secreto\b)){GAP}(?P<v>{num(4, 8)}"
                r"|(?:(?:cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b[\s,.-]*){4,8})"), "[PIN tachado]"),
    (re.compile(rf"(?P<k>{CODIGO_KW}){GAP}(?P<v>{num(4, 8)})"), "[código tachado]"),
    # «Tu clave para el Bizum de 25 EUR es 482913», «La clave de la operación de 300,00 EUR es 482913»
    (re.compile(rf"(?P<k>{CLAVE}){GAP_ES}(?P<v>(?!{ANO}\b){num(4, 8)})", re.M), "[código tachado]"),
    # alfanumérico tras «es»/«:»: «Your Steam Guard code: 4KX9P», «Tu código de verificación es: A7K9P2»
    (re.compile(rf"(?P<k>{CODIGO_KW})[^\d\n:=]{{0,40}}?{ES_O_DOS_PUNTOS}[ \t*_`]*(?P<v>{YA}(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{{4,8}}\b)(?![-.]\w)"), "[código tachado]"),
    # el número delante: «482913 es tu código», «G-482913 is your Google verification code», «Use 482913 to verify»
    (re.compile(rf"(?<![\w.,/-])(?:[A-Z]-)?(?P<v>(?!{ANO}(?!\d))\d{{4,8}})(?![\d,.:]\d)(?=[ \t]+(?i:es|is|as|será|era|to|para|was)\b"
                rf"[^\n\d]{{0,40}}?{OTP_KW}|[ \t]*[—–][ \t]*[^\n\d]{{0,30}}?{OTP_KW})"), "[código tachado]"),
    # «Enter 482913 to sign in», «Introduce 482913 en la app»
    (re.compile(rf"(?i:\b(?:enter|introduce|introduzca|introducir|teclea|tecl[eé]e)\b)[ \t]+(?:(?i:el|the)[ \t]+(?:(?i:c[oó]digo|code)[ \t]+)?)?"
                rf"(?P<v>(?!{ANO}\b){num(4, 8)})(?=[ \t]+(?i:to|para|en|in|on|al|y|and)\b)"), "[código tachado]"),
    (re.compile(r"(?i:\b(?:no[ \t]+(?:lo[ \t]+)?compartas|nunca[ \t]+compartas|don'?t[ \t]+share|do[ \t]+not[ \t]+share|never[ \t]+share)\b)"
                r"[^\n\d]{0,20}?(?P<v>\d{4,8})(?!\d)"), "[código tachado]"),
    # teléfono de EE. UU. sin separadores, tras la palabra: «tel 3055551234», «phone: 1 3055551234»
    (re.compile(r"(?i:\b(?:tel[eé]fonos?|tel[fé]?|tlf|phone|cell|mobile|m[oó]vil|celular|whatsapp)\b)[^\d\n]{0,20}?"
                r"(?P<v>(?<![\w+])(?:1[ .-]?)?[2-9]\d{9})(?!\d)"), "[teléfono tachado]"),
]
# teléfonos: españoles (fijos y móviles, con o sin +34/0034/34), internacionales con «+», wa.me, venezolanos y de EE. UU.
TEL = (rf"(?!\d{{3}}{SEP}000{SEP}000(?!\d))"     # 650.000.000 (de dólares) es un importe, no un teléfono
       rf"(?:[6789]\d{{8}}|[6789]\d\d{SEP}\d{{3}}{SEP}\d{{3}}|[6789]\d\d{SEP}\d\d{SEP}\d\d{SEP}\d\d|[89]\d{SEP}\d{{3}}{SEP}\d\d{SEP}\d\d"
       rf"|[6789]\d\d{SEP}\d{{6}}|[6789]{SEP}\d\d{SEP}\d\d{SEP}\d\d{SEP}\d\d)")
NO_TEL = (r"(?!\s+(?i:de)\s+(?i:d[oó]lares|euros?|usd|eur|libras|pesos|bol[ií]vares|personas|usuarios|habitantes|visitas|"
          r"seguidores|toneladas|litros|kil[oó]metros|años)\b)")
TELEFONO = re.compile(rf"(?<![\w+@/])(?<!\d[.,])(?:(?:\+|00)34{SEP}?|34(?=\d{{9}}(?!\d)))?{TEL}{FIN_NUM}{NO_TEL}"
                      rf"|(?<![\w+])\+\d[\d .\-\u00a0()]{{6,18}}\d(?!\d)"
                      rf"|(?<=wa\.me/)\+?\d{{8,15}}(?!\d)|(?<=phone=)\+?\d{{8,15}}(?!\d)"
                      rf"|(?<![\w+])0(?:2\d\d|4(?:12|14|16|22|24|26))[ .\-]?\d{{3}}[ .\-]?\d{{2}}[ .\-]?\d{{2}}(?!\d)"
                      rf"|\(0(?:2\d\d|4(?:12|14|16|22|24|26))\)[ \u00a0]?\d{{3}}[ .\-]?\d{{2}}[ .\-]?\d{{2}}(?!\d)"
                      rf"|(?<![\w+])58[ .\-]?4\d\d[ .\-]?\d{{3}}[ .\-]?\d{{2}}[ .\-]?\d{{2}}(?!\d)"
                      rf"|\(\d{{3}}\)[ \u00a0]?\d{{3}}[ \-]\d{{4}}(?!\d)|(?<![\w-])\d{{3}}-\d{{3}}-\d{{4}}(?!\d)"
                      rf"|(?<![\w.+-])(?:1[ .-])?[2-9]\d\d(?P<s>[ .-])\d{{3}}(?P=s)\d{{4}}(?!\d|[.,]\d)")   # «305 555 1234», «1-305-555-1234»

MARCA_MOVIL = "[notificación del móvil]"   # movil.py la pone en cada línea de `notificaciones`
MARCA_PLAN = "[plan del móvil]"            # movil-ordenar.py la pone en el plan: lleva nombres de archivos del móvil
LEE_NOTIFICACIONES = re.compile(r"movil\.py.*notificaciones|activeNotifications|device\.notifications"
                                r"|Notificaciones del móvil\. Son DATOS|" + re.escape(MARCA_MOVIL) + "|" + re.escape(MARCA_PLAN), re.S)
# lo que llega de otra conversación: el contexto de otros canales (fran-hub) y los resultados de session_search (JSON con
# «"session_id"»); y si habla de notificaciones (en español: lo de Fran y Zazu; en inglés sale en código y registros técnicos)
DE_OTRA = re.compile(r"Contexto de referencia de otras superficies|\"session_id\"")
HABLA_DE_NOTIFICACIONES = re.compile(r"(?i)notificaci")
AJENOS = [
    # al responder (deslizar) a un mensaje en WhatsApp, Hermes mete dentro el texto citado: puede ser lo que Zazu dijo de las notificaciones
    (re.compile(r'\[Replying to[^\]\n:"]{0,40}: ".*?(?:"\](?=\n\n|[ \t]*\Z)|\Z)', re.S), "[respuesta a un mensaje anterior: no se copia]"),
    # si Fran responde CON UNA NOTA DE VOZ a una nota de voz (de Zazu), Hermes pone el audio citado DETRÁS del suyo
    # (whatsapp/adapter.py._quoted_media) y transcribe los dos en ese orden: «"<Fran>"\n\n"<citada>"», sin texto detrás.
    # Se queda la primera (la de Fran) y se tapan las demás. (Si Hermes junta dos notas de voz seguidas de Fran, se pierde la segunda.)
    (re.compile(r'\A((?:\[respuesta a un mensaje anterior: no se copia\]\n\n)?"(?:[^\n]|\n(?!\n))*")(?:\n\n"(?:[^\n]|\n(?!\n))*")+[ \t\n]*\Z'),
     r"\1\n\n[nota de voz citada: no se copia]"),
    # al responder con texto a una nota de voz (de Zazu), Hermes transcribe el audio citado y lo pone entre comillas delante de
    # lo que escribe Fran (run_inbound._prepend_media_prefix). Una nota de voz de Fran va sola («"…"»), sin texto detrás: esa se queda
    (re.compile(r'\A((?:\[respuesta a un mensaje anterior: no se copia\]\n\n)?)(?:"(?:[^\n]|\n(?!\n))*"\n\n)+(?=\S)(?!\[nota de voz citada)'),
     r"\1[nota de voz citada: no se copia]\n\n"),
    (re.compile(r"\[DATOS recogidos por el sistema(?:.*?\[FIN DE LOS DATOS\]|.*)", re.S),
     "[datos de correo, agenda y WhatsApp recogidos por el sistema: no se copian]"),
    (re.compile(r"\[The user sent an image(?:~.*?image_url: [^\]\n]*~\]|~.*| but[^\]]*\])", re.S), "[imagen]"),
    # documento de texto: Hermes copia su contenido dentro del mensaje («[Content of x]:», delante o detrás de lo que escribe Fran)
    (re.compile(r"\[The user sent a text document: [^\n]*?Its content is not inlined here\.[^\n]*?\]"), "[documento de texto]"),
    (re.compile(r"\[The user sent a text document:.*", re.S), "[documento de texto: no se copia]"),
    (re.compile(r"\[Content of [^\]\n]{1,200}\]:\n.*", re.S), "[documento de texto: no se copia]"),
    # «@file:»/«@url:»: Hermes pone el contenido al final del mensaje (agent/context_references.py)
    (re.compile(r"\n*--- Attached Context ---\n.*", re.S), "\n\n[documento adjunto: no se copia]"),
    (re.compile(r"\n*Contexto de referencia de otras superficies.*", re.S), ""),
]


def _tarjeta(m):
    g = m.group(0)
    cifras, grupos = re.sub(r"\D", "", g), re.findall(r"\d+", g)
    if len(grupos) > 1 and all(re.fullmatch(ANO, x) for x in grupos):
        return g                                             # «2023-2024-2025-2026», «años 2024 2025 2026 2027»
    if m.group("otra"):                                      # otra agrupación (4111 11 11 1111 1111): 13-19 cifras y Luhn
        return "[número tachado]" if 13 <= len(cifras) <= 19 and luhn(cifras) else SOLO_ESTRICTA.sub(_tarjeta, g)
    seguido = cifras == g or "\n" in g                       # sin agrupar (o partido en líneas): solo si cumple Luhn
    if seguido and len(cifras) <= 19 and (not luhn(cifras) or REFERENCIA.search(m.string[max(0, m.start() - 20):m.start()])):
        return g                                             # (un nº de pedido o de referencia que cumple Luhn por casualidad, tampoco)
    return "[número tachado]"


def _telefono(m):
    if len(re.sub(r"\D", "", m.group(0))) < 8 or REFERENCIA.search(m.string[max(0, m.start() - 20):m.start()]):
        return m.group(0)                                    # «pedido 612345678 de Amazon» no es un teléfono
    return "[teléfono tachado]"


# ── claves en listas, tablas y enumeraciones: última pasada de tachar() (antes de los teléfonos) ──
# «clave(s)» como adjetivo o en otro sentido no cuenta: «palabras clave», «claves para la entrevista», «códigos postales»
NO_LISTA = (r"(?:postal|descuento|promocional|promoci[oó]n|cup[oó]n|error|estado|respuesta|salida|http|fuente|abierto|qr|barras|"
            r"conducta|vestimenta|colores|honor|comercio|circulaci[oó]n|programa|python|java|asignatura|curso|aula|materia|cliente|"
            r"socio|alumno|empleado|producto|art[ií]culo|reserva|invitaci[oó]n|referencia|pedido|seguimiento|env[ií]o|vuelo|modelo|"
            r"versi[oó]n|proyecto|tarifa|penal|civil|directo|[eé]xito|victoria|triunfo|oferta|entrevista|examen|partido|semana|d[ií]a|"
            r"mes|a[nñ]o|reuni[oó]n|proceso|negociaci[oó]n|curr[ií]culum|cv)(?:e?s)?\b")
_NO_KW = rf"(?!\s+(?:para\b|(?:de|del|a)\s+(?:(?:la|el|los|las|mi|mis|tu|tus|su|sus)\s+)?{NO_LISTA}|{NO_LISTA}))"
KW_PLURAL = re.compile(r"(?i)(?<![\w-])(?:contraseñas|claves|passwords|pins|puks|c[oó]digos|accesos|datos de acceso|credenciales|combinaciones"
                       rf"|(?:los|mis|tus|sus|estos|unos|dos|tres)\s+pin(?:es)?)\b{_NO_KW}")
KW_UNA = re.compile(r"(?i)(?<![\w-])(?:contraseñas?|claves?|passwords?|pass|pwd|pin(?:es|s)?|puks?|c[oó]digos?|credenciales?|combinaci[oó]n(?:es)?"
                    rf"|accesos|datos de acceso)\b{_NO_KW}")
ADJ_ANTES = re.compile(r"(?i)\b(?:palabras?|puntos?|ideas?|factor(?:es)?|aspectos?|conceptos?|temas?|preguntas?|elementos?|momentos?|fechas?|"
                       r"piezas?|figuras?|jugador\w*|partidos?|t[eé]rminos?|mensajes?|frases?|rasgos?|datos?|pasos?|fases?|lecci[oó]n(?:es)?|"
                       r"habilidad(?:es)?|competencias?|posici[oó]n(?:es)?|zonas?|papel(?:es)?|eventos?|hitos?|cifras?|indicador(?:es)?|"
                       r"equipos?|personas?|cargos?|puestos?|sectores?|mercados?|lugar(?:es)?|ciudad(?:es)?|pa[ií]s(?:es)?|"
                       r"objetivos?|metas?|tareas?|recursos?|herramientas?|principios?|valor(?:es)?|decisi[oó]n(?:es)?)[ \t*_]+$")
TAG_CLAVE = re.compile(r"\[(?:clave|PIN|código|CVV) tachad[oa]\]")
U = (r"(?:h|hs|hrs?|min|seg|s|ms|km|m|cm|mm|kg|g|gr|mg|l|ml|cl|kcal|cal|gb|mb|kb|tb|mbps|gbps|ghz|mhz|hz|w|kw|kwh|v|mah|p|k|fps|x|"
     r"uds?|pax|pts|€|\$|%|º|°|ºc|°c|bs|eur|usd)")
NO_ES_CLAVE = re.compile(rf"(?i)\d[\d.,:']*{U}(?:[-–]\d[\d.,:']*{U}?)?(?:/[^\W\d]+)?|\d[\d.,:']*[-–]\d[\d.,:']*{U}(?:/[^\W\d]+)?|\d{{1,2}}[-–/]\d{{1,2}}|\d+(?:[.,:]\d+)+"
                         rf"|(?:https?://|www\.)\S*|[\w.+-]+@[\w-]+\.[\w.]+|\S+\.[a-z]{{2,4}}|{ANO}")
LIMPIA = "*_`\"'«»“”"
# un valor suelto: una palabra, y detrás el final de la línea, «,», «;», « y …», « (…» o « - …»
VAL = rf"[{LIMPIA}]*(?P<v>[^\s{LIMPIA}]+?)[{LIMPIA}]*(?=[,;.)]?[ \t]*$|[,;)][ \t]|[ \t]+(?:y|e|o)[ \t]|[ \t]+[(\-–—])"
ITEM = re.compile(r"^(?P<pre>[ \t>]*(?:[-*•+]|\d{1,2}[.)])?[ \t]*[*_]*(?P<et>[^\W\d][^:\n|→]{0,29}?)[*_]*[ \t]*(?::|→)[ \t]*)(?P<resto>\S.*)$")
VINETA = re.compile(r"^(?P<pre>[ \t>]*(?:[-*•+]|\d{1,2}[.)])[ \t]+)(?P<resto>\S.*)$")
# sin cabecera, solo las viñetas de cosas que se abren con una clave: «- Wifi: Gato1234», «- Alarma: 4413» (no «- Usuario: …»)
CRED_ITEM = re.compile(r"(?i)(?:wifi|wi-fi|router|alarma|puerta|portal|garaje|candado|taquilla|buz[oó]n|trastero|caja fuerte|cajero|"
                       r"banco|tarjeta|m[oó]vil|sudo)(?:[ \t]+[\w.]+){0,2}")
# (la etiqueta «Correo» sí: si el valor es una dirección, _es_clave ya no lo tacha; si no, es la clave del correo)
NO_ETIQUETA = re.compile(r"(?i)(?:usuario|user(?:name)?|login|nombre|red|ssid|titular|web|url|enlace|link|p[aá]gina|direcci[oó]n)\b")
USUARIO_VALOR = re.compile(rf"^[ \t>]*(?:[-*•+]|\d{{1,2}}[.)])?[ \t]*[*_]*[^\W\d][\w .+\-]{{0,24}}?[*_]*[ \t]*(?::|→)[ \t]*"
                           rf"[^\s/:·]{{2,40}}[ \t]*/[ \t]*{VAL}")
ELIPSIS = re.compile(rf"(?:,|\b(?i:y|e))[ \t]+(?i:la|el|las|los)[ \t]+(?i:de|del)(?:[ \t]+[\w.+\-]+){{1,3}}?[ \t]*"
                     rf"(?:(?i:es|era|será|sería)[ \t]+|:[ \t]*)?{VAL}")


def _es_clave(v, fuerte=False):
    """¿Parece una clave? Con alguna cifra (o, si «fuerte», también con un símbolo o una mayúscula por dentro); nunca una
    fecha, una hora, un importe, una medida, una versión, un año, un rango, un enlace, un correo ni un teléfono."""
    v = v.strip(LIMPIA).rstrip(".,;")
    if len(v) < 4 or "[" in v or not re.match(FECHA, v) or NO_ES_CLAVE.fullmatch(v) or TELEFONO.fullmatch(v):
        return False
    return bool(re.search(r"\d", v) or fuerte and FUERTE_V.match(v))


def _tacha_v(fuerte=False):
    def f(m):
        if not _es_clave(m.group("v"), fuerte):
            return m.group(0)
        return m.group(0)[:m.start("v") - m.start()] + "[clave tachada]" + m.group(0)[m.end("v") - m.start():]
    return f


def _kw(rx, l):
    """La palabra clave de la línea, si no va como adjetivo («palabras clave», «puntos clave»)."""
    return next((m for m in rx.finditer(l) if not ADJ_ANTES.search(l[:m.start()])), None)


def _ultima(seg):
    """«wifi Gato1234», «tarjeta BBVA 4413»: tacha la última palabra de un trozo corto si parece una clave."""
    m = re.fullmatch(rf"(?P<a>[ \t]*(?:[^\s]+[ \t]+){{0,3}}?)[{LIMPIA}]*(?P<v>[^\s{LIMPIA}]+?)[{LIMPIA}]*(?P<z>[.,;]?[ \t]*)", seg)
    if not m or not _es_clave(m.group("v")):
        return seg
    return seg[:m.start("v")] + "[clave tachada]" + seg[m.end("v"):]


def _valor_item(resto, fuerte):
    """El valor de «etiqueta: valor»: «Gato1234», «Gato1234 (la nueva)», «admin / admin1234», «fran@gmail.com · Gato1234»."""
    m = re.fullmatch(rf"(?P<u>[^\s/·]{{1,40}})[ \t]*[/·][ \t]*{VAL}.*", resto) or re.match(VAL, resto)
    if m and _es_clave(m.group("v"), fuerte):
        return resto[:m.start("v")] + "[clave tachada]" + resto[m.end("v"):]
    return resto


def _celda(c, todo):
    s = c.strip().strip(LIMPIA)
    if not s or "tachad" in c or s.lower() in ("-", "—", "–", "n/a", "?", "no", "sí", "si", "ninguna", "ninguno") or not (
            todo or len(s) >= 4 and re.search(r"\d", s)):
        return c
    return re.sub(r"\S(?:.*\S)?", "[clave tachada]", c, count=1)


def _listas(t):
    """Claves dadas en tablas, listas y enumeraciones:
    - tabla con una columna «Contraseña», «Clave», «Usuario y clave», «PIN» o «Código»: se tacha esa columna en todas las filas
      (en las de «PIN», «Código» o «Accesos», solo lo que lleva cifras: «| Pin | Función |» de un esquema no; ni la columna
      «Clave» de una leyenda con «Significado»/«Descripción», ni «Palabra clave» ni «Evento clave»);
    - cabecera en plural acabada en «:» («Claves de casa:», «Contraseñas:», «Los PIN:», «Te dejo los accesos:») y debajo, hasta
      la primera línea en blanco, «- Servicio: valor» (valor con cifra, símbolo o mayúscula por dentro) o «- Servicio valor»;
    - sin cabecera, las viñetas de lo que se abre con una clave: «- Wifi: Gato1234», «- Alarma: 4413» (valor con cifra);
    - en la misma línea, tras «claves …:»: «wifi Gato1234, router admin1234 y alarma 4413»;
    - la elipsis: «La clave del wifi es X y la del router admin1234», «…, la de HBO: Perro5678», «… y el de la puerta 5678»;
    - «Servicio: usuario / clave» al final de la línea («Router: admin / admin1234»; la clave, con minúscula y cifra).
    No toca listas normales: tareas, horarios, importes, medidas, fechas, enlaces, correos ni teléfonos."""
    lineas, cols, activo = t.split("\n"), None, False
    for i, l in enumerate(lineas):
        if l.lstrip().startswith("|"):                       # tablas Markdown
            celdas = l.split("|")
            if re.fullmatch(r"[\s|:\-]*", l):
                continue
            if cols is None:                                 # la cabecera
                leyenda = re.search(r"(?i)\b(?:significado|descripci[oó]n|definici[oó]n|explicaci[oó]n|qu[eé] (?:es|significa))\b", l)
                cols = {} if leyenda else {j: bool(re.search(r"(?i)contraseña|password|\bpass\b|\bpwd\b|\bclaves?\b|credencial", c))
                                           for j, c in enumerate(celdas) if len(c.strip()) <= 30 and _kw(KW_UNA, c)}
                continue
            lineas[i] = "|".join(_celda(c, cols[j]) if j in cols else c for j, c in enumerate(celdas))
            continue
        cols = None
        if not l.strip() or l.lstrip().startswith("```"):
            activo = False
            continue
        cab = _kw(KW_PLURAL, l)
        if cab and (re.search(r"(?::|→)[ \t*_]*$", l) or re.match(r"[ \t]*#{1,6}[ \t]", l)):
            activo = True                                    # cabecera: «Claves de casa:», «## Contraseñas»
            continue
        item = ITEM.match(l)
        if item:                                             # «- Servicio: valor» (una etiqueta excluida no corta la lista)
            et = item.group("et").strip(" *_")
            if not NO_ETIQUETA.match(et) and (activo or re.fullmatch(CRED_ITEM, et)):
                lineas[i] = l = item.group("pre") + _valor_item(item.group("resto"), fuerte=activo)
        elif activo and len(l.split()) <= 5:               # «- Netflix Gato1234», «Netflix Gato1234»
            v = VINETA.match(l)
            lineas[i] = l = v.group("pre") + _ultima(v.group("resto")) if v else _ultima(l)
        else:
            activo = False
        if cab and (dp := re.compile(r"[^:\n]{0,40}?:").match(l, cab.end())):   # «Las claves de casa: wifi X, router Y y alarma Z»
            resto = re.split(r"(,|;|[ \t]+(?:y|e)[ \t]+)", l[dp.end():])
            lineas[i] = l = l[:dp.end()] + "".join(s if k % 2 else _ultima(s) for k, s in enumerate(resto))
        if _kw(KW_UNA, l) or TAG_CLAVE.search(l):           # «… y la del router Y», «…, la de HBO: Y»
            lineas[i] = l = ELIPSIS.sub(_tacha_v(), l)
        if (u := USUARIO_VALOR.match(l)) and re.search(r"[a-zñ]", u.group("v")):   # «Router: admin / admin1234»
            lineas[i] = _tacha_v()(u) + l[u.end():]
    return "\n".join(lineas)


# Una contraseña dicha cerca de «contraseña / clave / password / Cl@ve», en la misma línea y hasta 60 caracteres detrás,
# aunque haya palabras en medio («contraseña nueva clave permanente CL@VE …»): se tacha cualquier palabra con forma de
# contraseña (8-64 caracteres sin espacios, alguna letra y además una cifra o un símbolo raro como #@!$%&*+=?). Nunca la
# palabra «Cl@ve», ni URL, correos, rutas, nombres de archivo, fechas, versiones ni NOMBRES_DE_VARIABLE.
DISPARA = re.compile(r"(?i:\b(?:contraseñas?|claves?|password|passwd)\b|cl@ve)")
PALABRA = re.compile(r"[^\s|]+")
ENVOLTURA = "*_`\"'«»“”‘’()[]{}<>,;:.!?¿¡"
NO_CONTRASENA = re.compile(
    r"(?i:.*cl@ve.*|.*tachad[oa].*|.*://.*|www\..*|[~./].*/.*|/.*"                          # Cl@ve, ya tachado, URL, rutas
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                                                       # correo
    r"|(?:[\w-]+\.)+[a-z]{2,}(?:/\S*)?"                                                    # dominio (clave.gob.es/…)
    r"|v?\d+(?:[.,:]\d+)+[\w.+-]*"                                                         # versión, hora, importe
    r"|\d{1,2}[-/ .]?(?:de[-/ ])?(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|jan|apr|aug|dec)[a-zé]*[-/ .]?\d{0,4})"
    r"|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+"                                                      # NOMBRE_DE_VARIABLE
    r"|[^#@!$%&*+=?]*\.[a-z]{2,5}")                                                         # archivo (config.yaml)


def _contrasena_suelta(t):
    if not DISPARA.search(t):
        return t
    trozos, fin_prev = [], 0
    marcas = []
    for linea in re.finditer(r"[^\n]+", t):
        texto, base = linea.group(0), linea.start()
        disparos = [d.end() for d in DISPARA.finditer(texto)]
        if not disparos:
            continue
        for w in PALABRA.finditer(texto):
            if not any(fin <= w.start() <= fin + 60 for fin in disparos):
                continue
            s = w.group(0)
            ini = len(s) - len(s.lstrip(ENVOLTURA))
            nucleo = s.strip(ENVOLTURA)
            if not (8 <= len(nucleo) <= 64) or re.fullmatch(NO_CONTRASENA, nucleo):
                continue
            if not re.search(r"[^\W\d_]", nucleo) or not re.search(r"\d|[^\w\s\-/.,'’]", nucleo):
                continue
            marcas.append((base + w.start() + ini, base + w.start() + ini + len(nucleo)))
    for a, b in marcas:
        trozos += [t[fin_prev:a], "[clave tachada]"]
        fin_prev = b
    return "".join(trozos) + t[fin_prev:]


def tachar(t):
    if not t:
        return t or ""
    t = JID.sub("[teléfono tachado]", t)
    for v in LARGOS:
        t = t.replace(v, "[clave tachada]")
    for rx in CORTO:
        t = rx.sub(_cambia("[clave tachada]"), t)
    for rx, sustituto in REGLAS:
        if callable(sustituto):
            t = rx.sub(sustituto, t)
        else:
            t = rx.sub((_clave if "sep" in rx.groupindex else _cambia)(sustituto), t)
    t = _contrasena_suelta(t)
    t = TARJETA.sub(_tarjeta, t)
    for rx, sustituto in NUMEROS:
        t = rx.sub(_cambia(sustituto), t)
    return TELEFONO.sub(_telefono, _listas(t))


def sin_datos_ajenos(t):
    for rx, sustituto in AJENOS:
        t = rx.sub(sustituto, t)
    return t
