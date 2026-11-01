"""Noticias de las invitadas: cada una elige sus países y sus temas (users.json → «noticias») y aquí se juntan los titulares
de periódicos conocidos de cada sitio, por sus RSS públicos. Sin IA: solo recoge, limpia, quita repetidos y ordena.

Reutiliza el recolector de Fran (zazu/scripts/noticias.py, cargado como copia propia): limpieza de texto, fechas, fotos
candidatas del RSS, og:image, descargas solo a direcciones públicas y miniaturas WebP. Nada de HTML: todo texto limpio.

Caché compartida por fuente: todas las que eligen «España» usan la misma. Cada RSS se refresca como mucho cada 45 min (en
hilos aparte, con tiempo máximo de espera); si una fuente cae se sirve lo último que dio. Las fotos se bajan después y
solo de las noticias que se enseñan, a <estado>/img/<sha1>.webp, y las sirve el Hub (/api/inv/noticias/img/…).

Estado en ~/.local/state/noticias-invitadas (HUB_NOTICIAS_INV para cambiarlo). HUB_NOTICIAS_INV_RSS = un archivo RSS
local que sustituye a TODAS las fuentes y apaga las fotos (solo para las pruebas: nunca salen a internet)."""
import hashlib
import importlib.util
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

# Copia propia del recolector de Fran (otro nombre de módulo): se le cambia IMG_DIR sin tocar el de Fran.
# Se carga la primera vez que se usa, no al importar: dentro de la jaula de una invitada (mcp_google.py → server → aquí)
# zazu/scripts no existe, y fallar al importar dejaba a su Zazu sin ninguna herramienta de Google.
class _Perezoso:
    _m = None
    _cerrojo = threading.Lock()

    def __getattr__(self, nombre):
        if _Perezoso._m is None:
            with _Perezoso._cerrojo:
                if _Perezoso._m is None:
                    spec = importlib.util.spec_from_file_location(
                        "_noticias_invitadas_comun", Path(__file__).resolve().parent.parent / "zazu/scripts/noticias.py")
                    m = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(m)
                    _Perezoso._m = m
        return getattr(_Perezoso._m, nombre)

    def __setattr__(self, nombre, valor):
        self.__getattr__("__name__")
        setattr(_Perezoso._m, nombre, valor)


N = _Perezoso()

REFRESCO_S = 45 * 60        # cada cuánto se vuelve a leer un RSS
REINTENTO_S = 5 * 60        # si una fuente falló, no se reintenta hasta pasado esto
ESPERA_S = 8                # lo máximo que una petición espera a que lleguen los RSS
RSS_MAX = 3 * 1024 * 1024   # tamaño máximo de un RSS
POR_FUENTE = 40             # titulares que se guardan de cada RSS
POR_APARTADO = 8            # titulares por apartado (una destacada y siete filas)
POR_MEDIO = 3               # como mucho tres del mismo medio por apartado
DIAS = 3                    # lo de hace más de tres días ya no es noticia
RESUMEN = 220               # caracteres del resumen

# ───────── Catálogo fijo: periódicos conocidos de cada país y por tema (RSS comprobados el 2026-10-22) ─────────
AMERICA = "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/america/portada"
BBC = "https://feeds.bbci.co.uk/mundo/rss.xml"


def _f(rx):
    return re.compile(rx, re.I)


VEN = _f(r"venezuel|caracas|maracaibo|chavis|maduro")
# país: nombre y fuentes (medio, RSS, filtro). Con filtro, de ese medio general solo entra lo que habla de ese país.
PAISES = {
    "ES": {"nombre": "España", "fuentes": [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", None),
        ("El Mundo", "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml", None),
        ("20minutos", "https://www.20minutos.es/rss/", None),
        ("eldiario.es", "https://www.eldiario.es/rss/", None),
        ("Europa Press", "https://www.europapress.es/rss/rss.aspx?ch=00066", None)]},
    "VE": {"nombre": "Venezuela", "fuentes": [
        ("Tal Cual", "https://talcualdigital.com/feed/", None),
        ("El Pitazo", "https://elpitazo.net/feed/", None),
        ("Crónica Uno", "https://cronica.uno/feed/", None),
        ("El Nacional", "https://www.elnacional.com/feed/", VEN),   # también publica mucho de España: solo lo de Venezuela
        ("BBC Mundo", BBC, VEN)]},
    "CO": {"nombre": "Colombia", "fuentes": [
        ("El Tiempo", "https://www.eltiempo.com/rss/colombia.xml", None),
        ("Semana", "https://www.semana.com/arc/outboundfeeds/rss/?outputType=xml", None),
        ("El Colombiano", "https://www.elcolombiano.com/rss/portada.xml", None),
        ("El País", AMERICA, _f(r"colombi|bogot|petro\b|medell[ií]n"))]},
    "MX": {"nombre": "México", "fuentes": [
        ("El Universal", "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/?outputType=xml", None),
        ("El País México", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/mexico/portada", None),
        ("El Financiero", "https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml", None),
        ("Expansión", "https://expansion.mx/rss", None),
        ("La Jornada", "https://www.jornada.com.mx/rss/edicion.xml", None)]},
    "AR": {"nombre": "Argentina", "fuentes": [
        ("Clarín", "https://www.clarin.com/rss/lo-ultimo/", None),
        ("La Nación", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", None),
        ("Infobae", "https://www.infobae.com/arc/outboundfeeds/rss/", _f(r"argentin|buenos aires|milei|kicillof")),
        ("El País", AMERICA, _f(r"argentin|buenos aires|milei"))]},
    "CL": {"nombre": "Chile", "fuentes": [
        ("La Tercera", "https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml", None),
        ("Cooperativa", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_3___1.xml", None),
        ("El País", AMERICA, _f(r"\bchile|santiago de chile|boric|kast\b"))]},
    "PE": {"nombre": "Perú", "fuentes": [
        ("El Comercio", "https://elcomercio.pe/arc/outboundfeeds/rss/?outputType=xml", None),
        ("RPP", "https://rpp.pe/rss", None),
        ("Infobae Perú", "https://www.infobae.com/arc/outboundfeeds/rss/category/peru/", None),
        ("El País", AMERICA, _f(r"per[uú]\b|peruan|lima\b"))]},
    "EC": {"nombre": "Ecuador", "fuentes": [
        ("El Universo", "https://www.eluniverso.com/arc/outboundfeeds/rss/?outputType=xml", None),
        ("El Comercio", "https://www.elcomercio.com/feed/", None),
        ("El País", AMERICA, _f(r"ecuador|quito|guayaquil|noboa"))]},
    "UY": {"nombre": "Uruguay", "fuentes": [
        ("Montevideo Portal", "https://www.montevideo.com.uy/anxml.aspx?59", None),
        ("El País", AMERICA, _f(r"urugua|montevideo|orsi\b"))]},
    "DO": {"nombre": "República Dominicana", "fuentes": [
        ("Diario Libre", "https://www.diariolibre.com/rss/portada.xml", None),
        ("El País", AMERICA, _f(r"dominican|santo domingo|abinader"))]},
    "CU": {"nombre": "Cuba", "fuentes": [
        ("14ymedio", "https://www.14ymedio.com/rss/", None),
        ("El País", AMERICA, _f(r"\bcuba|habana"))]},
    "US": {"nombre": "Estados Unidos", "fuentes": [
        ("La Opinión", "https://laopinion.com/feed/", None),
        ("El Diario NY", "https://eldiariony.com/feed/", None),
        ("BBC Mundo", BBC, _f(r"estados unidos|ee\.? ?uu|washington|casa blanca|trump"))]},
}

# tema: nombre y fuentes (medio, RSS, país). País None = para todas; con país, solo si ella eligió ese país.
TEMAS = {
    "mundo": {"nombre": "Mundo", "fuentes": [
        ("BBC Mundo", BBC, None),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada", None),
        ("France 24", "https://www.france24.com/es/rss", None),
        ("Europa Press", "https://www.europapress.es/rss/rss.aspx?ch=00069", None),
        ("DW", "https://rss.dw.com/xml/rss-sp-all", None)]},
    "ia": {"nombre": "IA y tecnología", "fuentes": [
        ("Xataka", "https://www.xataka.com/tag/inteligencia-artificial/rss2.xml", None),
        ("Xataka", "https://www.xataka.com/index.xml", None),
        ("Genbeta", "https://www.genbeta.com/index.xml", None),
        ("Hipertextual", "https://hipertextual.com/feed", None),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada", None),
        ("Infobae", "https://www.infobae.com/arc/outboundfeeds/rss/category/tecno/", None),
        ("Xataka México", "https://www.xataka.com.mx/index.xml", "MX"),
        ("Clarín", "https://www.clarin.com/rss/tecnologia/", "AR"),
        ("El Tiempo", "https://www.eltiempo.com/rss/tecnosfera.xml", "CO")]},
    "deportes": {"nombre": "Deportes", "fuentes": [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/deportes/portada", None),
        ("Marca", "https://e00-marca.uecdn.es/rss/portada.xml", "ES"),
        ("AS", "https://feeds.as.com/mrss-s/pages/as/site/as.com/portada", "ES"),
        ("Mundo Deportivo", "https://www.mundodeportivo.com/rss/home", "ES"),
        ("El Nacional", "https://www.elnacional.com/deportes/feed/", "VE"),
        ("AS Colombia", "https://feeds.as.com/mrss-s/pages/as/site/colombia.as.com/portada", "CO"),
        ("El Tiempo", "https://www.eltiempo.com/rss/deportes.xml", "CO"),
        ("AS México", "https://feeds.as.com/mrss-s/pages/as/site/mexico.as.com/portada", "MX"),
        ("El Universal", "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/category/deportes/?outputType=xml", "MX"),
        ("Olé", "https://www.ole.com.ar/rss/ultimas-noticias/", "AR"),
        ("Clarín", "https://www.clarin.com/rss/deportes/", "AR"),
        ("AS Chile", "https://feeds.as.com/mrss-s/pages/as/site/chile.as.com/portada", "CL"),
        ("El Deportivo", "https://www.latercera.com/arc/outboundfeeds/rss/category/el-deportivo/?outputType=xml", "CL"),
        ("Depor", "https://depor.com/arc/outboundfeeds/rss/?outputType=xml", "PE")]},
    "economia": {"nombre": "Economía", "fuentes": [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/economia/portada", None),
        ("Expansión", "https://e00-expansion.uecdn.es/rss/portada.xml", "ES"),
        ("Cinco Días", "https://feeds.elpais.com/mrss-s/pages/ep/site/cincodias.elpais.com/portada", "ES"),
        ("El Nacional", "https://www.elnacional.com/economia/feed/", "VE"),
        ("Portafolio", "https://www.portafolio.co/rss/economia.xml", "CO"),
        ("El Tiempo", "https://www.eltiempo.com/rss/economia.xml", "CO"),
        ("El Economista", "https://www.eleconomista.com.mx/rss/ultimas-noticias", "MX"),
        ("El Financiero", "https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/category/economia/?outputType=xml", "MX"),
        ("Ámbito", "https://www.ambito.com/rss/pages/home.xml", "AR"),
        ("La Nación", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/economia/?outputType=xml", "AR"),
        ("Pulso", "https://www.latercera.com/arc/outboundfeeds/rss/category/pulso/?outputType=xml", "CL"),
        ("Gestión", "https://gestion.pe/arc/outboundfeeds/rss/?outputType=xml", "PE"),
        ("El Comercio", "https://elcomercio.pe/arc/outboundfeeds/rss/category/economia/?outputType=xml", "PE")]},
    "cultura": {"nombre": "Cultura y espectáculos", "fuentes": [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/cultura/portada", None),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/gente/portada", None),
        ("Infobae", "https://www.infobae.com/arc/outboundfeeds/rss/category/teleshow/", None),
        ("El Tiempo", "https://www.eltiempo.com/rss/cultura.xml", "CO"),
        ("El Universal", "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/category/espectaculos/?outputType=xml", "MX"),
        ("Europa Press", "https://www.europapress.es/rss/rss.aspx?ch=00129", "ES"),
        ("Clarín", "https://www.clarin.com/rss/espectaculos/", "AR"),
        ("Culto", "https://www.latercera.com/arc/outboundfeeds/rss/category/culto/?outputType=xml", "CL"),
        ("Luces", "https://elcomercio.pe/arc/outboundfeeds/rss/category/luces/?outputType=xml", "PE")]},
    "salud": {"nombre": "Salud y ciencia", "fuentes": [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/ciencia/portada", None),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/salud-y-bienestar/portada", None),
        ("Infobae", "https://www.infobae.com/arc/outboundfeeds/rss/category/salud/", None),
        ("Europa Press", "https://www.europapress.es/rss/rss.aspx?ch=00668", "ES"),
        ("El Tiempo", "https://www.eltiempo.com/rss/salud.xml", "CO")]},
}


def catalogo():
    return {"paises": [{"clave": k, "nombre": v["nombre"]} for k, v in PAISES.items()],
            "temas": [{"clave": k, "nombre": v["nombre"]} for k, v in TEMAS.items()]}


def _lista(v):
    return [str(x) for x in v] if isinstance(v, list) else []


def validar(d):
    """Lo que manda la app → {"paises", "temas", "elegido"} solo con claves del catálogo, en su orden; None si no hay nada."""
    d = d if isinstance(d, dict) else {}
    p, t = set(_lista(d.get("paises"))), set(_lista(d.get("temas")))
    el = {"paises": [k for k in PAISES if k in p], "temas": [k for k in TEMAS if k in t], "elegido": True}
    return el if el["paises"] or el["temas"] else None


# ───────── Caché compartida de cada RSS (memoria + disco) ─────────
def estado_dir():
    return Path(os.environ.get("HUB_NOTICIAS_INV") or Path.home() / ".local/state/noticias-invitadas")


def _falso():
    return os.environ.get("HUB_NOTICIAS_INV_RSS") or ""


_LOCK = threading.RLock()
_CACHE = {}       # url → {"t": hora de la última lectura buena, "items": [...]}
_FALLO = {}       # url → hora del último fallo
_EN_CURSO = {}    # url → Future del refresco
_POOL = ThreadPoolExecutor(8, thread_name_prefix="noticias-inv")
_FOTOS = ThreadPoolExecutor(4, thread_name_prefix="noticias-inv-foto")
_LIMPIEZA = [0.0]


def _archivo(url):
    return estado_dir() / "rss" / (hashlib.sha1(url.encode()).hexdigest() + ".json")


def _cache(url):
    """La caché de un RSS (la carga del disco la primera vez). Llamar con _LOCK."""
    if url not in _CACHE:
        try:
            d = json.loads(_archivo(url).read_text(encoding="utf-8"))
            _CACHE[url] = {"t": float(d["t"]), "items": [it for it in d["items"] if isinstance(it, dict)]}
        except (OSError, ValueError, KeyError, TypeError):
            _CACHE[url] = None
    return _CACHE[url]


def _guardar(url):
    """Escribe la caché de un RSS al disco (atómico). Llamar con _LOCK."""
    c = _CACHE.get(url)
    if not c:
        return
    f = _archivo(url)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.stem}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        pass


_COLA = re.compile(r"\s*(the post\b.*\bappeared first on\b.*|la entrada\b.*\bse public[oó] primero en\b.*|\[(…|\.\.\.)\].*"
                   r"|(leer|seguir leyendo|sigue leyendo|ver) m[aá]s\W*)$", re.I)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u2028-\u202e\u2066-\u2069]")   # control y marcas de dirección (texto que se haría pasar por otro)
_BLOQUES = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1\s*>")


def _sin_html(v):
    """Sin etiquetas ni lo que va dentro de <script>/<style>, en dos pasadas: la 2.ª quita lo que sale al deshacer «&lt;»."""
    return N.limpiar(_BLOQUES.sub(" ", N.limpiar(_BLOQUES.sub(" ", v or ""))))


def texto(v, maximo):
    """Texto limpio de un tercero: sin HTML, sin caracteres de control ni de dirección, y como mucho `maximo`
    caracteres cortando en una palabra."""
    t = _CONTROL.sub("", _sin_html(v))
    if len(t) > maximo:
        t = t[:maximo].rsplit(" ", 1)[0].rstrip(",.;:-–— ") + "…"
    return t


def _resumen(desc, titulo):
    t = _COLA.sub("", _sin_html(desc)).strip()
    if not t or N.norm(titulo).startswith(N.norm(t)[:60]):
        return ""                      # vacío o que solo repite el titular
    return texto(t, RESUMEN)


def _fecha(v):
    return N.cuando(v) or N.cuando_iso(v)


def _leer_rss(url):
    """Los titulares de un RSS: titular, enlace, fecha, resumen y fotos candidatas. Lanza si la fuente falla."""
    datos = Path(_falso()).read_bytes() if _falso() else N.bajar_ajeno(url, RSS_MAX, timeout=8)[0]
    raiz = ET.fromstring(datos)
    limite = datetime.now(ZoneInfo("Europe/Madrid")) - timedelta(days=DIAS)
    items = []
    for it in raiz.iterfind(".//item"):
        titulo = texto(it.findtext("title"), 300)
        enlace = (it.findtext("link") or "").strip()
        if not titulo or not re.match(r"https?://[^\s]+$", enlace, re.I) or len(enlace) > 2000:
            continue
        fecha = _fecha(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"))
        try:
            if fecha and datetime.fromisoformat(fecha) < limite:
                continue
        except ValueError:
            fecha = ""
        items.append({"titulo": titulo, "url": enlace, "fecha": fecha,
                      "resumen": _resumen(it.findtext("description") or it.findtext(N.CONTENIDO), titulo),
                      "_imgs": [] if _falso() else N.imagenes_de(it)[:2]})
    items.sort(key=lambda x: x["fecha"], reverse=True)
    return items[:POR_FUENTE]


def _refrescar(url):
    try:
        items = _leer_rss(url)
    except Exception:          # red, XML roto, tipo raro…: se sirve lo último bueno y se reintenta más tarde
        with _LOCK:
            _FALLO[url] = time.time()
        return
    with _LOCK:
        viejo = {it["url"]: it for it in ((_cache(url) or {}).get("items") or [])}
        for it in items:       # las fotos que ya se bajaron no se vuelven a bajar
            v = viejo.get(it["url"])
            if v and v.get("_fv"):
                it.update(img=v.get("img", ""), _fv=1)
        _CACHE[url] = {"t": time.time(), "items": items}
        _FALLO.pop(url, None)
        _guardar(url)


def _pedir(url):
    """Lanza el refresco de un RSS si toca. Devuelve su Future (o None si la caché sirve). Llamar con _LOCK."""
    c, ahora = _cache(url), time.time()
    if (c and ahora - c["t"] < REFRESCO_S) or ahora - _FALLO.get(url, 0) < REINTENTO_S:
        return None
    f = _EN_CURSO.get(url)
    if f is None or f.done():
        f = _EN_CURSO[url] = _POOL.submit(_refrescar, url)
    return f


# ───────── Fotos: solo de lo que se enseña, después y en segundo plano ─────────
def img_valida(clave):
    clave = str(clave or "")
    return clave if re.fullmatch(r"[0-9a-f]{40}", clave) and (estado_dir() / "img" / f"{clave}.webp").is_file() else ""


def imagen(nombre):
    """Los bytes de una miniatura «<sha1>.webp», o None."""
    m = re.fullmatch(r"([0-9a-f]{40})\.webp", str(nombre or ""))
    try:
        return (estado_dir() / "img" / f"{m.group(1)}.webp").read_bytes() if m else None
    except OSError:
        return None


def _foto(url_rss, it):
    """La foto de una noticia: la del RSS y, si no hay o es pequeña, la og:image del artículo. Nunca lanza."""
    N.IMG_DIR = estado_dir() / "img"
    mejor = None
    try:
        N.IMG_DIR.mkdir(parents=True, exist_ok=True)
        for c in it.get("_imgs") or []:
            try:
                mejor = N.guardar_img(c)
            except Exception:
                mejor = None
            if mejor:
                break
        if mejor is None or mejor[1] < 480:
            try:
                og = N.og_imagen(it["url"])
                otra = N.guardar_img(og) if og else None
                if otra and (mejor is None or otra[1] > mejor[1]):
                    mejor = otra
            except Exception:
                pass
    except Exception:
        pass
    with _LOCK:
        it["img"] = mejor[0] if mejor else ""
        _guardar(url_rss)
    if time.time() - _LIMPIEZA[0] > 6 * 3600:   # las miniaturas sin usar en 3 días se borran
        _LIMPIEZA[0] = time.time()
        N.limpiar_imgs()


# ───────── Las noticias de una invitada ─────────
def _secciones(el):
    """[(clave, título, [(medio, url, filtro)])]: primero sus países y luego sus temas, cada tema con los medios de sus países."""
    out = [("p-" + p.lower(), PAISES[p]["nombre"], PAISES[p]["fuentes"]) for p in el["paises"]]
    for t in el["temas"]:
        out.append((t, TEMAS[t]["nombre"], [(m, u, None) for m, u, p in TEMAS[t]["fuentes"] if p is None or p in el["paises"]]))
    return out


def _parecido(a, b):
    return a == b or (SequenceMatcher(None, a, b).real_quick_ratio() > .8 and SequenceMatcher(None, a, b).ratio() > .8)


def noticias(el, espera=ESPERA_S):
    """Sus apartados ya armados, sin repetidos entre apartados. `pendiente` = aún llegan fuentes o fotos (la app vuelve a pedir)."""
    secciones = _secciones(el)
    urls = list(dict.fromkeys(u for _, _, fs in secciones for _, u, _ in fs))
    with _LOCK:
        futuros = [f for f in (_pedir(u) for u in urls) if f]
    if futuros:
        wait(futuros, timeout=espera)
    vistos_url, vistos_tit, apartados, caidas, horas, fotos = set(), [], [], [], [], []
    with _LOCK:
        for clave, titulo, fuentes in secciones:
            cands = []
            for medio, url, filtro in fuentes:
                c = _cache(url)
                if not c:
                    if url in _FALLO and medio not in caidas:
                        caidas.append(medio)
                    continue
                horas.append(c["t"])
                cands += [(it, medio, url) for it in c["items"] if not filtro or filtro.search(it["titulo"] + " " + it.get("resumen", ""))]
            cands.sort(key=lambda x: x[0]["fecha"], reverse=True)
            items, cuenta = [], {}
            for it, medio, url in cands:
                if len(items) >= POR_APARTADO:
                    break
                k = N.norm(it["titulo"])
                if not k or it["url"] in vistos_url or cuenta.get(medio, 0) >= POR_MEDIO or any(_parecido(k, v) for v in vistos_tit):
                    continue
                vistos_url.add(it["url"])
                vistos_tit.append(k)
                cuenta[medio] = cuenta.get(medio, 0) + 1
                if not it.get("_fv") and not _falso():
                    it["_fv"] = 1
                    fotos.append((url, it))
                items.append({"titulo": it["titulo"], "fuente": medio, "url": it["url"], "fecha": it["fecha"],
                              "resumen": it.get("resumen", ""), "img": img_valida(it.get("img"))})
            apartados.append({"clave": clave, "titulo": titulo, "items": items})
    for url, it in fotos:
        _FOTOS.submit(_foto, url, it)
    hora = datetime.fromtimestamp(max(horas), ZoneInfo("Europe/Madrid")) if horas else None
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    return {"apartados": apartados, "fuentes_caidas": caidas, "pendiente": bool(fotos) or any(not f.done() for f in futuros),
            "generado": hora.isoformat(timespec="seconds") if hora else None, "hoy": bool(hora) and hora.date() == hoy}


def para(guardado, prefs, espera=ESPERA_S):
    """Lo que ve la invitada en Noticias. Sin elegir aún: el selector, con su país (de Tu espacio) y «Mundo» ya marcados."""
    el = validar(guardado) if isinstance(guardado, dict) and guardado.get("elegido") else None
    base = {"ok": True, "catalogo": catalogo()}
    if not el:
        pais = str((prefs or {}).get("pais") or "").upper()
        return {**base, "elegido": False, "paises": [pais] if pais in PAISES else [], "temas": ["mundo"],
                "apartados": [], "fuentes_caidas": [], "pendiente": False}
    return {**base, **el, **noticias(el, espera)}
