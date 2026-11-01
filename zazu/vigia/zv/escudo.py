"""Escudo: detector de TEXTOS TRAMPA (frases que intentan dar órdenes al modelo) en lo que escriben terceros (WhatsApp, correo).
Python puro, sin red ni dependencias. Todo texto de terceros pasa por aquí ANTES de llegar al modelo del vigía.
Si salta, la propuesta que salga de ese texto queda «sospechosa»: se enseña con aviso, nunca se aplica sola y ninguna regla
«siempre» la cubre. El escudo no borra ni cambia el texto: solo avisa (el modelo sigue sin herramientas y su salida se valida igual).

Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: src/openjarvis/security/injection_scanner.py.
Cambios: sin backend en Rust ni logging; niveles en español (bajo/medio/alto/critico); reglas nuevas en español (anular
instrucciones, cambiar de papel, órdenes de borrar/reenviar/pagar, sacar datos, etiquetas de sistema); el texto se normaliza
(NFKC, sin caracteres invisibles, sin tildes) antes de buscar; se añaden las reglas que el vigía ya tenía en flujos.INYECCION."""
import re
import unicodedata
from dataclasses import dataclass, field

NIVELES = ("bajo", "medio", "alto", "critico")
MAX_TROZO = 100          # trozo coincidente que se guarda en un hallazgo (como en OpenJarvis)
I = re.I

# (regex, nombre, nivel, descripción). Se buscan sobre el texto normalizado y SIN tildes («ignora» ≡ «ignóra»).
_REGLAS = (
    # ── anular las instrucciones (OpenJarvis: prompt_override) ──
    (r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)(?:\s+(?:instructions?|prompts?|rules?))?", "anular_instrucciones", "alto",
     "Intenta anular las instrucciones (inglés)"),
    (r"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|your)(?:\s+(?:instructions?|programming|rules?))?", "anular_instrucciones", "alto",
     "Intenta que se desoigan las instrucciones (inglés)"),
    (r"forget\s+(?:everything|all|your\s+instructions)", "anular_instrucciones", "alto", "Intenta borrar las instrucciones (inglés)"),
    # «todo» además de «todas»: «Ignora todo lo anterior» es la frase de inyección más típica en español y pasaba limpia
    (r"ignor(?:a|e|en|ad)\s+(?:tod[oa]s?\s+)?(?:las\s+|tus\s+|mis\s+|lo\s+)?(?:instrucciones|ordenes|indicaciones|reglas|anterior|previo|dicho)",
     "anular_instrucciones", "alto", "Intenta anular las instrucciones"),
    (r"(?:haz\s+caso\s+omiso|no\s+hagas\s+caso)\s+(?:a|de)\s+(?:todo\s+)?(?:lo\s+(?:anterior|previo|dicho)|(?:las|tus)\s+(?:instrucciones|ordenes|reglas))",
     "anular_instrucciones", "alto", "Intenta anular las instrucciones"),
    (r"olvida(?:te)?\s+(?:de\s+)?(?:todo|lo\s+anterior|las\s+instrucciones|tus\s+(?:instrucciones|reglas))", "anular_instrucciones", "alto",
     "Intenta borrar las instrucciones"),
    (r"nuevas?\s+instrucciones|new\s+instructions", "anular_instrucciones", "medio", "Trae «instrucciones nuevas»"),
    (r"a\s+partir\s+de\s+ahora[\s,]+(?:eres|debes|responde)", "anular_instrucciones", "bajo", "Pide cambiar lo que hace a partir de ahora"),
    (r"(?:system\s*prompt|prompt\s+del\s+sistema|instrucciones\s+del\s+sistema|mensaje\s+de\s+sistema)", "anular_instrucciones", "medio",
     "Nombra las instrucciones del sistema"),
    # ── cambiar de papel (OpenJarvis: identity_override, jailbreak) ──
    (r"you\s+are\s+now\s+(?:a\s+|an\s+)?(?:different|new|my)|you\s+are\s+(?:now\s+)?(?:an?\s+)?(?:assistant|ai\b|language\s+model)", "cambio_de_papel", "alto", "Intenta cambiar el papel del modelo (inglés)"),
    (r"(?:ahora\s+)?eres\s+(?:ahora\s+)?(?:un|una|mi)\s+(?:nuevo\s+|nueva\s+)?(?:asistente|modelo|ia\b|inteligencia|agente|bot)", "cambio_de_papel", "alto",
     "Intenta cambiar el papel del modelo"),
    (r"(?:actua|haz)\s+como\s+(?:si\s+fueras\s+)?(?:un|una|el|la)\s+(?:administrador|admin|desarrollador|sistema|asistente\s+sin)", "cambio_de_papel", "medio",
     "Pide actuar como otro"),
    (r"(?:\bDAN\b|do\s+anything\s+now)\s+(?:mode|prompt|jailbreak)|modo\s+(?:desarrollador|developer|dios|sin\s+(?:filtros|restricciones|limites))", "jailbreak", "alto",
     "Intento de saltarse los límites"),
    (r"pretend\s+(?:you\s+)?(?:have\s+)?no\s+(?:restrictions?|limitations?|rules?|filters?)|(?:finge|imagina)\s+que\s+no\s+tienes\s+(?:reglas|limites|restricciones|filtros)",
     "jailbreak", "medio", "Pide fingir que no hay límites"),
    # ── órdenes de actuar sobre las cuentas de Fran ──
    (r"borra\s+(?:todo|todos|todas|los\s+(?:correos|mensajes|archivos|eventos|tareas))|elimina\s+(?:todo|todos|todas)|delete\s+(?:all|everything)",
     "orden_destructiva", "alto", "Pide borrar cosas"),
    (r"reenvia\s+(?:este|todos|el|los)|forward\s+(?:this|all)", "orden_reenviar", "alto", "Pide reenviar correos o mensajes"),
    (r"(?:envia|manda|escribe)\s+(?:un\s+)?(?:correo|mensaje|whatsapp|email)\s+a\b", "orden_enviar", "bajo", "Pide mandar un mensaje en nombre de Fran"),
    (r"haz\s+(?:una\s+)?(?:transferencia|bizum)|transfiere\s+\d|(?:send|wire)\s+(?:the\s+)?money", "orden_pago", "alto", "Pide mover dinero"),
    # ── sacar datos (OpenJarvis: exfiltration) ──
    (r"(?:send|post|upload|exfiltrate|transmit)\s+(?:(?:to|data|all|everything)\s+)*(?:to\s+)?(?:https?://|my\s+server)", "sacar_datos", "alto",
     "Pide sacar datos fuera (inglés)"),
    # «tus?»/«mis?»: en singular («pásame tu contraseña») también
    (r"(?:envia|manda|sube|pega|copia|dame|pasa)(?:me|nos)?\s+(?:aqui\s+)?(?:(?:todas?|todos?)\s+)?(?:tus?|las|mis?|los|el|la)\s+(?:instrucciones|contrasenas?|claves?|tokens?|codigos?|credenciales|historial|conversacion)",
     "sacar_datos", "alto", "Pide sacar datos o instrucciones"),
    (r"base64\s+encode\s+(?:and\s+)?(?:send|include|append)|codifica\s+en\s+base64", "sacar_datos", "medio", "Pide codificar datos para sacarlos"),
    # ── código y comandos (OpenJarvis: code_injection, shell_injection) ──
    (r"(?:execute|run|eval)\s*\(\s*['\"]", "codigo", "alto", "Intenta ejecutar código"),
    # \b y no \s al final: «wget x.sh | bash» con el comando al final del texto también cuenta
    (r"(?:;|\||&&)\s*(?:rm|curl|wget|nc|ncat|bash|sh|zsh|python3?|perl)\b", "comando", "alto", "Comando de terminal encadenado"),
    (r"ejecuta\s+(?:el\s+|este\s+)?(?:comando|script|codigo)|run\s+(?:the\s+)?(?:command|script)|\bsudo\b|rm\s+-rf|curl\s+https?", "comando", "alto",
     "Pide ejecutar un comando"),
    # ── delimitadores de chat (OpenJarvis: delimiter_injection) ──
    (r"```(?:system|assistant)\b|</?(?:system|assistant|datos)>|\[/?(?:system|inst)\]", "delimitador", "medio", "Etiqueta de sistema o de rol"),
    (r"<\|(?:im_start|im_end|system|assistant|user)\|>", "delimitador", "alto", "Etiqueta de plantilla de chat"),
)
_PATRONES = tuple((re.compile(rx, I), nombre, nivel, desc) for rx, nombre, nivel, desc in _REGLAS)
_INVISIBLES = re.compile(r"[­​-‏‪-‮⁠-⁤﻿]")


@dataclass
class Hallazgo:
    nombre: str
    nivel: str
    descripcion: str
    trozo: str


@dataclass
class Resultado:
    limpio: bool
    nivel: str = "ninguno"                    # el más alto encontrado
    hallazgos: list = field(default_factory=list)

    @property
    def nombres(self):
        return sorted({h.nombre for h in self.hallazgos})


# homóglifos: letras cirílicas y griegas que se ven como latinas (truco para evadir las reglas)
_HOMOGLIFOS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "к": "k", "ѕ": "s", "і": "i", "ј": "j", "ԁ": "d", "һ": "h", "ӏ": "l", "ν": "v", "т": "t", "в": "b", "м": "m", "н": "h",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "Х": "X", "У": "Y", "К": "K", "І": "I", "Ј": "J", "В": "B", "М": "M", "Н": "H", "Т": "T",
    "α": "a", "ο": "o", "ρ": "p", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "τ": "t", "υ": "u", "χ": "x", "Α": "A", "Ο": "O", "Ε": "E", "Ι": "I", "Κ": "K", "Τ": "T",
})


def _colapsar(t):
    """«i g n o r a» o «i-g-n-o-r-e» → «ignora»; «holaaa» → «holaa». Deja intactas las palabras normales."""
    t = re.sub(r"\b([a-z])(?:[\s._/\-]+([a-z])){2,}\b", lambda m: re.sub(r"[\s._/\-]+", "", m.group(0)), t, flags=re.I)
    return re.sub(r"([a-z])\1{2,}", r"\1", t, flags=re.I)   # 3+ repetidas → 1 (el español no tiene triples; «olvidaaa»→«olvida»)


def normalizar(texto):
    """NFKC (ancho completo → normal), homóglifos → latín, sin invisibles ni tildes, letras espaciadas/repetidas colapsadas, en una línea."""
    t = unicodedata.normalize("NFKC", str(texto or "")).translate(_HOMOGLIFOS)
    t = _INVISIBLES.sub("", t)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return _colapsar(re.sub(r"\s+", " ", t))


def escanear(texto):
    """→ Resultado. Busca todas las reglas sobre el texto normalizado."""
    t = normalizar(texto)
    hallazgos = []
    for rx, nombre, nivel, desc in _PATRONES:
        m = rx.search(t)
        if m:
            hallazgos.append(Hallazgo(nombre, nivel, desc, m.group(0)[:MAX_TROZO]))
    if not hallazgos:
        return Resultado(True)
    peor = max((h.nivel for h in hallazgos), key=NIVELES.index)
    return Resultado(False, peor, hallazgos)


def sospechoso(texto, minimo="bajo"):
    """True si el texto trae algo que parece una orden para el modelo, de nivel `minimo` o más. El correo usa «bajo» (cualquier
    regla); WhatsApp usa «medio», porque entre amigos «escribe un mensaje a tu madre» es charla, no una trampa."""
    r = escanear(texto)
    return not r.limpio and NIVELES.index(r.nivel) >= NIVELES.index(minimo)
