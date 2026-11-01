"""Puntuación de una oferta frente a perfil.yaml: pista (dev/marketing), puntos 0–100 y motivos. Sin IA: reglas que Fran puede leer y cambiar."""
import re, unicodedata
from datetime import date


def _n(t):
    """Minúsculas y sin tildes: «Júnior» = «junior», «Sénior» = «senior»."""
    return unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()


def _tiene(texto, palabra):
    """La palabra (o frase) entera en el texto ya normalizado con _n. Los espacios de los extremos del perfil («sr ») no cuentan: antes «sr » no
    podía coincidir nunca, porque después de su espacio siempre hay una letra."""
    p = _n(palabra).strip()
    return bool(p) and re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", texto) is not None


# --- Idiomas (idea de la «puerta de idioma» de MadsLorentzen/ai-job-search, MIT) ---------------------------------------------------------------
# perfil.yaml dice qué idiomas tienes (idiomas: [es, en]). Una oferta que EXIGE otro idioma se descarta; «alemán es un plus» no cuenta, y una oferta
# escrita entera en otro idioma solo baja puntos (puede ser una empresa que acepta inglés).
NOMBRES_IDIOMA = {
    "de": ["german", "deutsch", "deutschkenntnisse", "aleman", "alemand"],
    "fr": ["french", "francais", "frances", "francophone"],
    "it": ["italian", "italiano", "italien"],
    "pt": ["portuguese", "portugues"],
    "nl": ["dutch", "nederlands", "neerlandes", "holandes"],
    "da": ["danish", "dansk", "danes"],
    "sv": ["swedish", "svenska", "sueco"],
    "no": ["norwegian", "norsk", "noruego"],
    "fi": ["finnish", "suomi", "finlandes"],
    "pl": ["polski", "polaco"],
}
_EXIGE = re.compile("|".join(re.escape(_n(w)) for w in [
    "fluent", "native", "mother tongue", "proficien", "business level", "business-level", "advanced", "c1", "c2", "b2", "required", "mandatory", "must", "essential",
    "fliessend", "verhandlungssicher", "muttersprach", "sehr gute", "erforderlich", "voraussetzung", "notwendig",
    "nativo", "fluido", "imprescindible", "obligatorio", "excelente", "alto nivel", "se requiere", "requisito", "indispensable"]))
_PLUS = re.compile("|".join(re.escape(_n(w)) for w in [
    "plus", "nice to have", "nice-to-have", "advantage", "bonus", "desirable", "preferred", "an asset", "ventaja", "valorable", "valorara", "deseable", "se valora",
    "von vorteil", "wunschenswert", "ein plus", "idealmente", "optional"]))
# palabras muy comunes de cada idioma (sin las que se escriben igual en dos idiomas: «de» y «en» son españolas y holandesas a la vez)
_PALABRAS_TEXTO = {
    "es": set("el la los las del que se por con para una un es su al lo como mas pero sus este esta entre cuando muy sin sobre tu te nuestro nuestra trabajo equipo experiencia".split()),
    "en": set("the and of to is for with on that by this are be as at from your you we our will or an have has not it their they work team experience".split()),
    "de": set("und der die das mit fur von sie wir ihre unsere ein eine einen sind werden bei auf zum zur nach oder auch als im dem den nicht ihr uns du dich aufgaben".split()),
    "fr": set("les des une pour avec dans nous vous votre notre sur est sont aux par qui ou ce vos nos du".split()),
    "nl": set("het een van voor met wij jij onze bij naar zijn ook dat jouw worden wordt niet maar deze".split()),
}


def idioma_exigido(texto, perfil):
    """Nombre del primer idioma NO declarado que la oferta exige, o None. `texto` ya normalizado con _n."""
    tengo = {str(i).lower()[:2] for i in perfil.get("idiomas", [])}
    if not tengo:
        return None
    for cod, nombres in NOMBRES_IDIOMA.items():
        if cod in tengo:
            continue
        for nombre in nombres:
            for m in re.finditer(r"(?<![a-z0-9])" + re.escape(nombre) + r"(?![a-z0-9])", texto):
                ventana = texto[max(0, m.start() - 45): m.end() + 45]
                if _EXIGE.search(ventana) and not _PLUS.search(ventana):
                    return nombre
    return None


def idioma_del_texto(texto, perfil):
    """Si la oferta está escrita en un idioma que no declaraste (alemán, francés u holandés) devuelve su código; si no, None.
    Compara todos los idiomas, español e inglés incluidos, y exige que el ganador saque ventaja clara: así un texto en español no se toma por holandés."""
    tengo = {str(i).lower()[:2] for i in perfil.get("idiomas", [])}
    palabras = re.findall(r"[a-z]+", texto)
    if len(palabras) < 40:
        return None
    puntos = sorted(((sum(1 for w in palabras if w in conj) / len(palabras), cod) for cod, conj in _PALABRAS_TEXTO.items()), reverse=True)
    (mejor, cod), (segundo, _) = puntos[0], puntos[1]
    return cod if cod not in tengo and mejor >= 0.10 and mejor >= 1.5 * segundo else None


def puntuar(o, perfil):
    """Devuelve (pista, puntos, motivos). pista '' y puntos 0 si está excluida."""
    titulo = _n(o.titulo); texto = _n((o.titulo or "") + " " + (o.descripcion or "")); lugar = _n(o.lugar)
    motivos = []
    for p in perfil.get("excluir_titulo", []):
        if _tiene(titulo, p):
            return "", 0, [f"excluida: «{p}» en el título"]
    for p in perfil.get("excluir_texto", []):
        if _n(p) in texto:
            return "", 0, [f"excluida: «{p}»"]
    for p in perfil.get("excluir_texto_ubicacion", []):
        if _n(p) in texto or _n(p) in lugar:   # también en el lugar: antes «USA Only» en la ubicación no excluía nada
            return "", 0, [f"excluida: «{p}»"]
    ex = idioma_exigido(texto, perfil)
    if ex:
        return "", 0, [f"excluida: exige {ex}, que no está en tus idiomas"]
    mejor = ("", 0, [])
    for pista, cfg in perfil["pistas"].items():
        nucleo = cfg.get("nucleo", [])
        en_titulo = sum(1 for w in nucleo if _tiene(titulo, w)); en_texto = sum(1 for w in nucleo if _tiene(texto, w))
        if nucleo and en_titulo == 0 and en_texto < 2:
            continue   # no es de esta pista: ni una palabra del núcleo en el título ni dos en el texto
        puntos = 0; m = []
        for palabra, peso in cfg.get("pesos_titulo", {}).items():
            if _tiene(titulo, palabra):
                puntos += peso; m.append(f"+{peso} «{palabra}» en título")
        n = sum(1 for palabra in cfg.get("palabras", []) if _tiene(texto, palabra))
        if n:
            puntos += min(n * 3, 21); m.append(f"+{min(n*3,21)} {n} palabras clave")
        if puntos > mejor[1]:
            mejor = (pista, puntos, m)
    pista, puntos, m = mejor
    if not pista:
        return "", 0, ["sin palabras del perfil"]
    esc = idioma_del_texto(texto, perfil)
    if esc:
        puntos -= 20; m.append(f"-20 escrita en {esc}")
    ub = perfil.get("ubicacion", {}); pais = (o.pais or "").upper()
    if any(_n(c) in lugar for c in ub.get("ciudades", [])):
        puntos += 20; m.append("+20 Valencia")
    elif pais == ub.get("pais_prioritario", "ES") or "spain" in lugar or "espana" in lugar:
        puntos += 12; m.append("+12 España")
    elif o.remoto and ub.get("europa_remoto") and pais in ("EU", "REMOTE"):
        puntos += 10; m.append("+10 remoto Europa")      # solo si se puede hacer desde Europa (o desde cualquier sitio); antes, TODO lo remoto
    elif pais in ub.get("paises_ok", []) or pais == "EU":
        puntos += 4; m.append("+4 Europa" + (f" (solo {pais})" if o.remoto and pais != "EU" else ""))
    elif pais and pais != "REMOTE":
        puntos -= 15; m.append(f"-15 fuera de Europa ({pais})")
    elif o.remoto and not pais and lugar.strip() and lugar.strip() not in ("remote", "remoto", "worldwide", "anywhere"):
        puntos -= 10; m.append(f"-10 remoto sin confirmar para España ({(o.lugar or '')[:30]})")
    if pista == "marketing" and not o.remoto and pais not in ("ES", ""):
        puntos -= 10; m.append("-10 marketing presencial fuera de España")
    if o.fecha:
        try:
            dias = (date.today() - date.fromisoformat(o.fecha)).days
            if dias > perfil.get("max_dias", 14):
                return "", 0, [f"excluida: {dias} días"]
            if dias <= 2: puntos += 5; m.append("+5 reciente")
        except ValueError:
            pass
    return pista, max(0, min(100, puntos)), m
