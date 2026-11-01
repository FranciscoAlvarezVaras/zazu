"""Fuentes de ofertas. Cada módulo expone buscar(perfil) -> list[Oferta]. Todas usan APIs públicas o con clave propia de Fran.
Reglas: solo lectura, un User-Agent honesto, tiempo límite, nada de iniciar sesión ni de rascar webs que lo prohíben (Indeed, LinkedIn, InfoJobs)."""
import json, os, re, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

UA = "ZazuEmpleo/0.1 (buscador personal de ofertas; contacto en el perfil)"
CACHE = Path(os.environ.get("EMPLEO_CACHE") or Path.home() / ".local/state/empleo-buscador/cache"); CACHE.mkdir(parents=True, exist_ok=True)


def get_json(url, minutos=10, cabeceras=None, datos=None):
    """GET (o POST si datos) con caché en disco de `minutos` para no machacar las APIs al probar."""
    import hashlib
    clave = CACHE / hashlib.sha1((url + (json.dumps(datos, sort_keys=True) if datos else "")).encode()).hexdigest()
    if clave.exists() and time.time() - clave.stat().st_mtime < minutos * 60:
        return json.loads(clave.read_text())
    h = {"User-Agent": UA, "Accept": "application/json"}; h.update(cabeceras or {})
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    if cuerpo is not None: h["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo, headers=h), timeout=30) as r:
        texto = r.read().decode("utf-8", "replace")
    d = json.loads(texto); clave.write_text(texto); return d


def q(**kv):
    return urllib.parse.urlencode({k: v for k, v in kv.items() if v not in (None, "")})


def claves_de_perfil(perfil, pista=None):
    """Palabras de búsqueda para APIs que aceptan texto: las más representativas de cada pista."""
    pistas = perfil["pistas"] if not pista else {pista: perfil["pistas"][pista]}
    out = []
    for p in pistas.values():
        out += [w for w in p["palabras"] if " " in w or len(w) > 3][:6]
    return out


FUENTES = ["arbeitnow", "remotive", "remoteok", "jobicy", "themuse", "himalayas", "adzuna", "linkedin_posts"]


# ───────── de «Remote - USA», «Europe», «Paris, France»… a un país ─────────
def _plano(t):
    return unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()


PAISES_TXT = {"spain": "ES", "espana": "ES", "portugal": "PT", "germany": "DE", "deutschland": "DE", "france": "FR", "netherlands": "NL", "holland": "NL", "ireland": "IE",
              "italy": "IT", "austria": "AT", "belgium": "BE", "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI", "poland": "PL", "switzerland": "CH",
              "czechia": "CZ", "czech republic": "CZ", "greece": "GR", "united kingdom": "GB", "uk": "GB", "england": "GB", "scotland": "GB",
              "usa": "US", "u.s.": "US", "us": "US", "united states": "US", "america": "US", "canada": "CA", "india": "IN", "australia": "AU", "new zealand": "NZ",
              "brazil": "BR", "mexico": "MX", "argentina": "AR", "colombia": "CO", "philippines": "PH", "singapore": "SG", "japan": "JP", "china": "CN", "pakistan": "PK",
              "nigeria": "NG", "south africa": "ZA", "israel": "IL", "uae": "AE", "dubai": "AE", "latam": "LATAM", "latin america": "LATAM", "apac": "APAC", "asia": "APAC", "africa": "AF"}
CIUDADES_TXT = {"madrid": "ES", "barcelona": "ES", "valencia": "ES", "sevilla": "ES", "malaga": "ES", "bilbao": "ES", "lisbon": "PT", "lisboa": "PT", "porto": "PT",
                "berlin": "DE", "munich": "DE", "hamburg": "DE", "frankfurt": "DE", "cologne": "DE", "paris": "FR", "lyon": "FR", "amsterdam": "NL", "rotterdam": "NL",
                "dublin": "IE", "london": "GB", "manchester": "GB", "edinburgh": "GB", "zurich": "CH", "geneva": "CH", "vienna": "AT", "wien": "AT", "brussels": "BE",
                "milan": "IT", "rome": "IT", "warsaw": "PL", "krakow": "PL", "prague": "CZ", "copenhagen": "DK", "stockholm": "SE", "oslo": "NO", "helsinki": "FI",
                "boston": "US", "new york": "US", "san francisco": "US", "austin": "US", "seattle": "US", "chicago": "US", "toronto": "CA", "sydney": "AU", "bangalore": "IN"}
EUROPA_TXT = ("europe", "european", "emea", "eu only", "eu-based", "within the eu", "european union")
MUNDO_TXT = ("worldwide", "anywhere", "global", "world wide", "any location", "everywhere")
EUROPEOS = {"ES", "PT", "DE", "FR", "NL", "IE", "IT", "AT", "BE", "DK", "SE", "NO", "FI", "PL", "CH", "CZ", "GR", "GB"}


def pais_de_lugar(lugar):
    """Qué país es un texto de ubicación: 'ES' si nombra España; 'EU' si dice Europa/EMEA; 'REMOTE' si dice «worldwide/anywhere»; el código de un país si es
    solo uno (y entonces la oferta está LIMITADA a él); '' si no se sabe o es una lista de países que no incluye España ni Europa (p. ej. «USA, UK, India»)."""
    t = _plano(lugar)
    palabra = lambda k: re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) is not None
    codigos = {c for k, c in {**PAISES_TXT, **CIUDADES_TXT}.items() if palabra(k)}
    if "ES" in codigos:
        return "ES"
    if any(palabra(k) for k in EUROPA_TXT):
        return "EU"
    if any(palabra(k) for k in MUNDO_TXT) and not (codigos - EUROPEOS):
        return "REMOTE"
    if len(codigos) == 1:
        return next(iter(codigos))
    return ""
