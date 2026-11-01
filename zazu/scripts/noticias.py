#!/usr/bin/env python3
"""Noticias del día para Zazu, SIN IA: solo recoge y ordena titulares de fuentes públicas y gratuitas (sin clave).
Cuatro apartados: Venezuela, España, IA (modelos y repos nuevos) y Mundo. No opina ni inventa: solo lo que traen las fuentes.
Fuentes: RSS directos de medios que traen foto (El País, BBC Mundo, Europa Press, eldiario.es, France 24, Tal Cual,
El Pitazo, Xataka) más Google News RSS para dar variedad; Hugging Face API, GitHub Search y Hacker News (Algolia) para IA.
Si una fuente se cae, se omite y se anota; nunca rompe.

Fotos: cada noticia lleva, si se puede, una miniatura DESCARGADA AL SERVIDOR (~/.local/state/noticias/img/<sha1>.webp,
640 px de ancho como mucho), para que la app no cargue nada de terceros. Orden: la imagen del RSS (media:content,
media:thumbnail, enclosure o <img> de la descripción); si no hay o es pequeña, la og:image del artículo. Los enlaces de
Google News se decodifican (batchexecute) al enlace real del medio, que es el que se guarda y abre la app. Solo http(s)
a direcciones públicas, timeouts cortos, tamaño máximo y solo JPEG/PNG/WebP; las miniaturas de más de 3 días se borran.
Sin Pillow o sin imagen, la noticia va sin foto y no pasa nada.

Guarda ~/.local/state/noticias/hoy.json. Sin argumentos genera y guarda; con --ver imprime sin guardar (y sin fotos).
Lo lanza el temporizador noticias.timer (07:00, 14:00, 21:00) y se puede ejecutar a mano."""
import hashlib
import html
import http.client
import io
import ipaddress
import json
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from PIL import Image, ImageOps
except ImportError:          # sin Pillow: noticias sin foto
    Image = ImageOps = None

TZ = ZoneInfo("Europe/Madrid")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
DESTINO = Path.home() / ".local/state/noticias/hoy.json"
IMG_DIR = DESTINO.parent / "img"
IMG_ANCHO = 640                      # ancho máximo de la miniatura guardada
IMG_MAX_BYTES = 6 * 1024 * 1024      # lo máximo que se descarga de una imagen
HTML_MAX_BYTES = 768 * 1024          # de una página solo se lee el principio (las <meta> van en <head>)
IMG_DIAS = 3                         # las miniaturas sin usar más de 3 días se borran
# Un PNG/WebP de pocos KB puede medir 9000×9000 y gastar ~400 MB al decodificarlo (y van 8 hilos a la vez): se descarta
# antes de decodificar. El aviso de bomba de Pillow (89 Mpx) llega tarde para esto.
IMG_MAX_PIXELES = 25_000_000
DESCARGA_MAX_S = 20                  # tope de tiempo TOTAL de una descarga (el timeout de urllib es por cada lectura)
POR_APARTADO = 6                     # una destacada + cinco filas
POR_MEDIO = 2                        # como mucho dos titulares del mismo medio por apartado

GOOGLE = {
    "venezuela": "https://news.google.com/rss/search?q=Venezuela&hl=es-419&gl=VE&ceid=VE:es-419",
    "espana": "https://news.google.com/rss/search?q=Espa%C3%B1a%20when%3A1d&hl=es&gl=ES&ceid=ES:es",
    "mundo": "https://news.google.com/rss/search?q=internacional%20OR%20mundo%20when%3A1d&hl=es-419&gl=US&ceid=US:es",
}
VEN = re.compile(r"venezuel|caracas|chavis|maduro", re.I)    # para quedarse solo con lo de Venezuela en medios generales
# (medio, RSS, filtro). Medio None = el que diga el propio RSS (Google News trae <source> en cada titular).
FUENTES = {
    "venezuela": [
        (None, GOOGLE["venezuela"], None),
        ("Tal Cual", "https://talcualdigital.com/feed/", None),
        ("El Pitazo", "https://elpitazo.net/feed/", None),
        ("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml", VEN),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/america/portada", VEN),
    ],
    "espana": [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/espana/portada", None),
        ("Europa Press", "https://www.europapress.es/rss/rss.aspx?ch=00066", None),
        ("eldiario.es", "https://www.eldiario.es/rss/", None),
        (None, GOOGLE["espana"], None),
    ],
    "mundo": [
        ("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml", None),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada", None),
        ("Europa Press", "https://www.europapress.es/rss/rss.aspx?ch=00069", None),
        ("France 24", "https://www.france24.com/es/rss", None),
        (None, GOOGLE["mundo"], None),
    ],
}
# Cuántos titulares pone Google News en cada apartado (además rellena si un medio falla). España y Mundo: sus búsquedas
# traen mucho medio pequeño y fuera de tema, así que ahí solo rellena.
DE_GOOGLE = {"venezuela": 2}
XATAKA_IA = "https://www.xataka.com/tag/inteligencia-artificial/rss2.xml"
HF_MODELOS = "https://huggingface.co/api/models?sort=trendingScore&limit=15"
# Repos ordenados por ESTRELLAS (con descripción) vía GitHub Search; se filtran por actividad reciente (pushed en ~30 días).
GH_API = "https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=8"
GH_TEMAS = ("llm", "ai-agents", "agents")
HN_BUSCAR = "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=LLM&hitsPerPage=12"
FALLOS = (urllib.error.URLError, OSError, ValueError, ET.ParseError)


def _leer(r, maximo=None, tope=DESCARGA_MAX_S):
    """Lee la respuesta por bloques, como mucho `maximo` bytes (None = todo), y corta si pasa de `tope` segundos en total:
    el timeout de urllib vale para CADA lectura, así que un servidor que manda 1 byte cada pocos segundos colgaba el hilo
    hasta que systemd mataba la tanda entera (y se perdía hoy.json)."""
    fin = time.monotonic() + tope
    # read1 y no read: read(65536) de http.client no vuelve hasta juntar los 65536 bytes, así que con un goteo nunca se
    # llegaba a mirar el reloj. read1 vuelve con lo que haya llegado en cada lectura del socket.
    leer = getattr(r, "read1", r.read)
    trozos, n = [], 0
    while maximo is None or n < maximo:
        b = leer(65536 if maximo is None else min(65536, maximo - n))
        if not b:
            break
        trozos.append(b)
        n += len(b)
        if time.monotonic() > fin:
            raise ValueError("descarga demasiado lenta")
    return b"".join(trozos)


def bajar(url, timeout=12, cabeceras=None):
    """Descarga el contenido con un User-Agent normal. Devuelve bytes o lanza la excepción (quien llama la anota)."""
    h = {"User-Agent": UA, "Accept-Language": "es,en;q=0.8"}
    if cabeceras:
        h.update(cabeceras)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _leer(r)


# ───────── Descargas «de terceros» (imágenes y páginas de artículos): solo http(s) a IPs públicas ─────────
def publica(url):
    """True si la URL es http(s) y su host resuelve SOLO a direcciones públicas (nada de localhost ni la red de casa)."""
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        ips = {ai[4][0] for ai in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))}
    except (OSError, UnicodeError):
        return False
    return bool(ips) and all(_es_publica(ip) for ip in ips)


def _es_publica(ip):
    return ipaddress.ip_address(ip.split("%")[0]).is_global


def _conectar_publica(direccion, *a, **k):
    """Como socket.create_connection, pero comprueba la IP a la que de verdad se ha conectado. publica() resuelve el nombre
    y la conexión lo vuelve a resolver: un DNS con «rebinding» puede dar una IP pública la 1.ª vez y 127.0.0.1 o la red de
    casa la 2.ª. Se comprueba antes de mandar nada (ni la petición ni el saludo TLS)."""
    s = socket.create_connection(direccion, *a, **k)
    try:
        if not _es_publica(s.getpeername()[0]):
            raise OSError("conexión a una dirección no pública")
    except BaseException:
        s.close()
        raise
    return s


class _SoloPublicaMixin:
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._create_connection = _conectar_publica


class _ConexionPublica(_SoloPublicaMixin, http.client.HTTPConnection):
    pass


class _ConexionPublicaS(_SoloPublicaMixin, http.client.HTTPSConnection):
    pass


class _HTTPPublico(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_ConexionPublica, req)


class _HTTPSPublico(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_ConexionPublicaS, req, context=self._context)


class _SoloPublicas(urllib.request.HTTPRedirectHandler):
    """Sigue redirecciones solo hacia direcciones públicas."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not publica(newurl):
            raise urllib.error.URLError("redirección a una dirección no pública")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ABRIR = urllib.request.build_opener(_SoloPublicas, _HTTPPublico, _HTTPSPublico)


def bajar_ajeno(url, maximo, timeout=8, tipos=None):
    """Descarga como mucho `maximo` bytes de una URL pública. Devuelve (bytes, url_final, content-type).
    Si `tipos` se da, el Content-Type debe empezar por alguno; si no, ValueError."""
    if not publica(url):
        raise ValueError("dirección no pública")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es,en;q=0.8"})
    with _ABRIR.open(req, timeout=timeout) as r:
        tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if tipos and not tipo.startswith(tipos):
            raise ValueError(f"tipo no válido: {tipo}")
        largo = r.headers.get("Content-Length")
        if largo and largo.isdigit() and int(largo) > maximo:
            raise ValueError("demasiado grande")
        datos = _leer(r, maximo + 1)
        if len(datos) > maximo and tipos:
            raise ValueError("demasiado grande")
        return datos[:maximo], r.geturl(), tipo


def limpiar(texto):
    """Quita etiquetas HTML y normaliza espacios; deshace entidades (&amp; → &)."""
    sin_tags = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(sin_tags)).strip()


def quitar_medio(titulo, fuente):
    """Google añade « - Medio» al final del título. Lo quita si coincide con la fuente o parece un medio."""
    t = titulo.strip()
    if fuente and t.endswith(" - " + fuente):
        return t[: -(len(fuente) + 3)].strip()
    # si no sabemos la fuente, quita el último « - algo» corto (los medios suelen ser breves)
    m = re.match(r"^(.*) - ([^-]{2,40})$", t)
    if m and not fuente:
        return m.group(1).strip()
    return t


def cuando(pub):
    """Convierte la fecha RFC-822 del RSS a ISO en hora de Madrid; si no se puede, cadena vacía."""
    if not pub:
        return ""
    try:
        d = parsedate_to_datetime(pub)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(TZ).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        return ""


def norm(t):
    """Clave para comparar títulos parecidos: minúsculas, sin signos ni espacios de más."""
    return re.sub(r"[^a-z0-9áéíóúñü ]", "", (t or "").lower()).strip()


def sin_duplicados(items):
    """Quita títulos iguales o muy parecidos (ratio > 0.8), conservando el primero (el más reciente)."""
    salida = []
    claves = []
    for it in items:
        k = norm(it["titulo"])
        if not k:
            continue
        if any(k == c or SequenceMatcher(None, k, c).ratio() > 0.8 for c in claves):
            continue
        claves.append(k)
        salida.append(it)
    return salida


MEDIA = "{http://search.yahoo.com/mrss/}"
CONTENIDO = "{http://purl.org/rss/1.0/modules/content/}encoded"
_IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_NO_IMAGEN = re.compile(r"\.(mp4|m3u8|mp3|webm|mov)(\?|$)", re.I)


def imagenes_de(it):
    """URLs candidatas a foto de un <item> de RSS, la más ancha primero: <media:content>/<media:thumbnail>
    (también dentro de <media:group>), <enclosure type="image/..."> o el primer <img src> de la descripción.
    Se saltan vídeos y audios; lo que no sea una imagen de verdad lo descarta luego la descarga."""
    cands = []
    for el in it.iter():
        if el.tag not in (MEDIA + "content", MEDIA + "thumbnail"):
            continue
        url = (el.get("url") or "").strip()
        tipo, medio = (el.get("type") or "").lower(), (el.get("medium") or "").lower()
        if not url or _NO_IMAGEN.search(url) or (tipo and not tipo.startswith("image")) or (medio and medio != "image"):
            continue
        ancho = int(el.get("width")) if (el.get("width") or "").isdigit() else 0
        cands.append((ancho, url))
    enc = it.find("enclosure")
    if enc is not None and (enc.get("type") or "").startswith("image") and (enc.get("url") or "").strip():
        cands.append((0, enc.get("url").strip()))
    for texto in (it.findtext("description"), it.findtext(CONTENIDO)):
        m = _IMG_SRC.search(texto or "")
        if m:
            cands.append((0, html.unescape(m.group(1)).strip()))
    vistos, salida = set(), []
    for _, url in sorted(cands, key=lambda c: -c[0]):
        if url not in vistos:
            vistos.add(url)
            salida.append(url)
    return salida


def rss(url, medio=None, filtro=None, n=4):
    """Los n titulares más recientes de un RSS: titular, medio, enlace, fecha y fotos candidatas (campo interno _imgs).
    `medio` None toma el <source> del propio RSS (Google News) y le quita el « - Medio» al titular.
    `filtro` (regex) deja solo los titulares cuyo título o entradilla encajan."""
    raiz = ET.fromstring(bajar(url))
    items = []
    for it in raiz.iterfind(".//item"):
        titulo_bruto = limpiar((it.findtext("title") or ""))
        enlace = (it.findtext("link") or "").strip()
        if not titulo_bruto or not enlace:
            continue
        if filtro and not filtro.search(titulo_bruto + " " + limpiar(it.findtext("description") or "")):
            continue
        fuente = medio
        if fuente is None:
            fuente_el = it.find("source")
            fuente = limpiar(fuente_el.text) if fuente_el is not None and fuente_el.text else ""
            titulo_bruto = quitar_medio(titulo_bruto, fuente)
        items.append({
            "titulo": titulo_bruto,
            "fuente": fuente,
            "url": enlace,
            "fecha": cuando(it.findtext("pubDate")),
            "_imgs": imagenes_de(it),
        })
    items.sort(key=lambda x: x["fecha"], reverse=True)
    return sin_duplicados(items)[:n]


def tomar(cands, k, ya):
    """Hasta k titulares de `cands`, los más recientes primero, sin repetir lo que ya hay en `ya` (ni títulos casi
    iguales) y como mucho POR_MEDIO del mismo medio contando los de `ya`."""
    claves = [norm(x["titulo"]) for x in ya]
    cuenta = {}
    for x in ya:
        cuenta[x["fuente"].lower()] = cuenta.get(x["fuente"].lower(), 0) + 1
    salida = []
    for it in sorted(cands, key=lambda x: x["fecha"], reverse=True):
        if len(salida) >= k:
            break
        clave, medio = norm(it["titulo"]), it["fuente"].lower()
        if not clave or cuenta.get(medio, 0) >= POR_MEDIO or any(clave == c or SequenceMatcher(None, clave, c).ratio() > 0.8 for c in claves):
            continue
        claves.append(clave)
        cuenta[medio] = cuenta.get(medio, 0) + 1
        salida.append(it)
    return salida


def elegir(directos, google, de_google=0, n=POR_APARTADO):
    """Los medios con RSS propio (traen foto y son medios conocidos) van primero; Google News pone `de_google`
    titulares para dar variedad y rellena si algún medio no respondió. El resultado, del más reciente al más viejo."""
    sel = tomar(directos, n - min(de_google, len(google)), [])
    sel += tomar(google, n - len(sel), sel)
    sel += tomar(directos, n - len(sel), sel)
    return sorted(sel, key=lambda x: x["fecha"], reverse=True)


def apartado_rss(clave, titulo, caidas):
    """Un apartado de noticias generales: junta sus RSS (cada uno en su try) y elige los mejores."""
    directos, google = [], []
    for medio, url, filtro in FUENTES[clave]:
        try:
            (directos if medio else google).extend(rss(url, medio, filtro))
        except FALLOS as e:
            caidas.append(f"{titulo}/{medio or 'Google News'}: {type(e).__name__}")
    return {"clave": clave, "titulo": titulo, "items": elegir(directos, google, DE_GOOGLE.get(clave, 0))}


def hugging_face(n=3):
    """Modelos en tendencia de Hugging Face: id → enlace https://huggingface.co/<id>."""
    datos = json.loads(bajar(HF_MODELOS))
    items = []
    for m in datos:
        ident = (m.get("id") or m.get("modelId") or "").strip()
        if not ident:
            continue
        items.append({
            "titulo": ident,
            "fuente": "Hugging Face",
            "url": "https://huggingface.co/" + ident,
            "fecha": cuando_iso(m.get("lastModified")),
        })
        if len(items) >= n:
            break
    return items


def cuando_iso(valor):
    """Fecha ISO (como la de Hugging Face, 2026-01-02T...Z) a ISO en hora de Madrid; vacío si no se puede."""
    if not valor:
        return ""
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(TZ).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        return ""


def github_repos(n=3):
    """Repos ordenados por ESTRELLAS (GitHub Search API, sin clave): «N★ owner/repo» + descripción (qué hace) + enlace.
    Combina varios temas (llm, ai-agents, agents) para dar variedad, filtra por actividad reciente y ordena por estrellas."""
    desde = (datetime.now(TZ).date().replace(day=1)).isoformat()   # actividad desde el día 1 del mes en curso
    por_repo = {}
    for tema in GH_TEMAS:
        consulta = urllib.parse.quote(f"topic:{tema} pushed:>{desde}")
        datos = json.loads(bajar(GH_API.format(q=consulta), cabeceras={"Accept": "application/vnd.github+json"}))
        for r in datos.get("items", []):
            nombre = r.get("full_name")
            if not nombre or nombre in por_repo:
                continue
            por_repo[nombre] = {
                "full_name": nombre,
                "estrellas": int(r.get("stargazers_count") or 0),
                "descripcion": limpiar(r.get("description") or ""),
                "url": r.get("html_url") or f"https://github.com/{nombre}",
            }
    mejores = sorted(por_repo.values(), key=lambda x: -x["estrellas"])[:n]
    return [{
        "titulo": f"{r['estrellas']}★ {r['full_name']}",
        "fuente": r["descripcion"] or "GitHub",
        "url": r["url"],
        "fecha": "",
    } for r in mejores]


def hacker_news(n=3):
    """Titulares recientes de Hacker News sobre LLM (Algolia): title, enlace (url del artículo o del hilo), puntos."""
    datos = json.loads(bajar(HN_BUSCAR))
    items = []
    for h in datos.get("hits", []):
        titulo = limpiar(h.get("title") or "")
        if not titulo:
            continue
        hilo = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        puntos = h.get("points") or 0
        items.append({
            "titulo": titulo,
            "fuente": f"Hacker News · {puntos} puntos",
            "url": h.get("url") or hilo,
            "fecha": cuando_iso(h.get("created_at")),
        })
        if len(items) >= n:
            break
    return items


def apartado_ia(caidas):
    """IA junta: noticias de IA en español (Xataka), modelos nuevos (Hugging Face), repos (GitHub) y Hacker News."""
    items = []
    for clave, fn in (("Xataka", lambda: rss(XATAKA_IA, "Xataka", n=3)),
                      ("Hugging Face", lambda: hugging_face(3)),
                      ("GitHub", lambda: github_repos(3)),
                      ("Hacker News", lambda: hacker_news(3))):
        try:
            items += fn()
        except FALLOS as e:
            caidas.append(f"IA/{clave}: {type(e).__name__}")
    return {"clave": "ia", "titulo": "IA", "items": sin_duplicados(items)}


# ───────── Fotos ─────────
def enlace_real(url):
    """Enlace de Google News (news.google.com/rss/articles/<id>) → enlace del medio, como hace la propia web de
    Google: lee la firma y la hora de la página del artículo y pregunta a su endpoint batchexecute. "" si falla."""
    p = urllib.parse.urlsplit(url)
    if p.hostname != "news.google.com" or "/articles/" not in p.path:
        return ""
    gid = p.path.rstrip("/").split("/")[-1]
    pagina = bajar(f"https://news.google.com/rss/articles/{gid}", timeout=8).decode("utf-8", "replace")
    sg, ts = re.search(r'data-n-a-sg="([^"]+)"', pagina), re.search(r'data-n-a-ts="(\d+)"', pagina)
    if not sg or not ts:
        return ""
    peticion = ["Fbv4je", json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None,
                                                      None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                                      gid, int(ts.group(1)), sg.group(1)])]
    cuerpo = ("f.req=" + urllib.parse.quote(json.dumps([[peticion]]))).encode()
    req = urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=cuerpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=8) as r:
        texto = _leer(r, 200_000).decode("utf-8", "replace")
    real = json.loads(json.loads(texto.split("\n\n")[1])[0][2])[1]
    return real if isinstance(real, str) and real.startswith(("https://", "http://")) else ""


_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATRIB = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
_OG = ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src")


def og_imagen(url):
    """La og:image (o twitter:image) de una página: lee solo el principio del HTML. "" si no hay."""
    datos, final, tipo = bajar_ajeno(url, HTML_MAX_BYTES)
    if tipo and "html" not in tipo:
        return ""
    texto = datos.decode("utf-8", "replace")
    halladas = {}
    for meta in _META.findall(texto):
        at = {k.lower(): (a or b) for k, a, b in _ATRIB.findall(meta)}
        nombre = (at.get("property") or at.get("name") or "").lower()
        if nombre in _OG and at.get("content") and nombre not in halladas:
            halladas[nombre] = html.unescape(at["content"]).strip()
    for nombre in _OG:
        if halladas.get(nombre):
            return urllib.parse.urljoin(final, halladas[nombre])
    return ""


def guardar_img(url):
    """Descarga una imagen (JPEG/PNG/WebP), la reduce a 640 px de ancho y la guarda como WebP en IMG_DIR/<sha1>.webp.
    Devuelve (sha1, ancho_original) o None. Si ya estaba, solo la «toca» para que la limpieza no la borre."""
    if Image is None or not url.startswith(("http://", "https://")):
        return None
    clave = hashlib.sha1(url.encode()).hexdigest()
    destino = IMG_DIR / f"{clave}.webp"
    if destino.is_file():
        destino.touch()
        with Image.open(destino) as ya:
            return clave, ya.width          # min(original, 640): basta para saber si era pequeña (< 480)
    datos, _, _ = bajar_ajeno(url, IMG_MAX_BYTES, tipos=("image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp"))
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        im = Image.open(io.BytesIO(datos))
        if im.format not in ("JPEG", "PNG", "WEBP"):
            return None
        ancho, alto = im.size                     # Image.open solo lee la cabecera: aún no se ha decodificado nada
        if ancho < 160 or alto < 90:              # píxeles de seguimiento, iconos y logos diminutos
            return None
        im.draft("RGB", (IMG_ANCHO, IMG_ANCHO))  # un JPEG grande se decodifica ya reducido (hasta 1/8); PNG y WebP no
        if im.width * im.height > IMG_MAX_PIXELES:   # «bomba» pequeña en bytes pero enorme en memoria (tras el draft, para
            return None                              # no tirar las fotos JPEG grandes, que se decodifican ya pequeñas)
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            fondo = Image.new("RGB", im.size, (255, 255, 255))
            fondo.paste(im, mask=im.getchannel("A"))
            im = fondo
        else:
            im = im.convert("RGB")
        im.thumbnail((IMG_ANCHO, IMG_ANCHO * 2))
        # .tmp propio de cada hilo: dos noticias con la misma foto (un logo del medio) se pisaban el mismo <sha1>.tmp y
        # la segunda fallaba al moverlo (y se quedaba sin foto)
        tmp = destino.with_name(f"{clave}.{threading.get_ident()}.tmp")
        im.save(tmp, "WEBP", quality=72, method=4)
        tmp.replace(destino)
    return clave, ancho


def vestir(it):
    """Pone a una noticia su enlace real (si era de Google News) y su foto `img` (sha1). Nunca lanza."""
    cands = it.pop("_imgs", None) or []
    try:
        real = enlace_real(it["url"])
        if real:
            it["url"] = real
    except (*FALLOS, KeyError, IndexError, TypeError):
        pass
    mejor = None
    for c in cands[:2]:
        try:
            mejor = guardar_img(c)
        except Exception:     # imagen rota, tipo raro, bomba de descompresión, red… → se prueba la siguiente
            mejor = None
        if mejor:
            break
    if (mejor is None or mejor[1] < 480) and "news.google.com" not in it["url"]:   # sin foto o pequeña: la del artículo
        try:
            og = og_imagen(it["url"])
            otra = guardar_img(og) if og and og not in cands[:1] else None
            if otra and (mejor is None or otra[1] > mejor[1]):
                mejor = otra
        except Exception:
            pass
    if mejor:
        it["img"] = mejor[0]
    return it


def limpiar_imgs():
    """Borra miniaturas sin usar desde hace más de IMG_DIAS días, y restos .tmp."""
    limite = time.time() - IMG_DIAS * 86400
    for f in IMG_DIR.glob("*"):
        try:
            if f.suffix == ".tmp" or (f.suffix == ".webp" and f.stat().st_mtime < limite):
                f.unlink()
        except OSError:
            pass


def con_fotos(apartados):
    """Viste todas las noticias en paralelo (8 a la vez) y luego limpia las miniaturas viejas."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    todos = [it for a in apartados for it in a["items"]]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(vestir, todos))
    limpiar_imgs()


def generar(fotos=True):
    """Arma el JSON completo. Cada fuente va en su try: si cae, se anota en `fuentes_caidas` y sigue."""
    ahora = datetime.now(TZ)
    caidas = []
    apartados = [apartado_rss("venezuela", "Venezuela", caidas),
                 apartado_rss("espana", "España", caidas),
                 apartado_ia(caidas),
                 apartado_rss("mundo", "Mundo", caidas)]
    if fotos:
        con_fotos(apartados)
    for a in apartados:
        for it in a["items"]:
            it.pop("_imgs", None)
    return {
        "fecha": ahora.date().isoformat(),
        "generado": ahora.isoformat(timespec="seconds"),
        "apartados": apartados,
        "fuentes_caidas": caidas,
    }


def main():
    ver = "--ver" in sys.argv[1:]
    datos = generar(fotos=not ver)
    if ver:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0
    total = sum(len(a["items"]) for a in datos["apartados"])
    if total == 0:
        # sin red (p. ej. al encender el PC) caen todas las fuentes: mejor dejar las noticias de la tanda anterior que
        # dejar la app vacía. El código 1 hace que systemd lo reintente (Restart=on-failure en noticias.service).
        print("Ningún titular (¿sin red?); no se toca " + str(DESTINO) + ". Fuentes caídas: " + ", ".join(datos["fuentes_caidas"]),
              file=sys.stderr)
        return 1
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    tmp = DESTINO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DESTINO)
    fotos = sum(1 for a in datos["apartados"] for it in a["items"] if it.get("img"))
    print(f"Noticias guardadas en {DESTINO}: {total} titulares, {fotos} con foto"
          + (f"; fuentes caídas: {', '.join(datos['fuentes_caidas'])}" if datos["fuentes_caidas"] else "; todas las fuentes respondieron"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
