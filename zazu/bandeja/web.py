"""Descarga segura de una página (la oferta de «Aplicar:»). Anti-SSRF: solo http/https en 80/443, el nombre se resuelve UNA vez y
se conecta a esa IP (sin DNS-rebinding), se rechazan IPs privadas, locales, de enlace local, reservadas o multicast, cada
redirección se vuelve a comprobar (máx. 5), tope de 1 MB y 15 s. Devuelve texto plano; lo que dice la página son datos."""
import html, http.client, ipaddress, re, socket, ssl
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 1_000_000
MAX_REDIR = 5


class Bloqueada(ValueError):
    pass


def ip_publica(ip):
    a = ipaddress.ip_address(ip.split("%")[0])
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return a.is_global and not (a.is_multicast or a.is_loopback or a.is_link_local or a.is_private or a.is_reserved or a.is_unspecified)


def resolver(host):
    """→ IP pública validada (todas las respuestas del DNS deben serlo). Se puede sustituir en tests."""
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        infos = [(None, None, None, None, (str(ip), 0))]
    except ValueError:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ips = [i[4][0] for i in infos]
    if not ips or not all(ip_publica(i) for i in ips):
        raise Bloqueada("dirección no permitida")
    return ips[0]


def validar_url(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Bloqueada("solo http/https")
    if p.username or p.password:
        raise Bloqueada("sin credenciales en la URL")
    puerto = p.port or (443 if p.scheme == "https" else 80)
    if puerto not in (80, 443):
        raise Bloqueada("puerto no permitido")
    return p, puerto, resolver(p.hostname)


class _Con(http.client.HTTPConnection):
    def __init__(self, host, puerto, ip, tls):
        super().__init__(host, puerto, timeout=15)
        self._ip, self._tls = ip, tls

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), 15)
        if self._tls:
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


def descargar(url, abrir=_Con):
    """→ (url_final, bytes, content_type). Lanza Bloqueada si algo no es seguro."""
    for _ in range(MAX_REDIR + 1):
        p, puerto, ip = validar_url(url)
        con = abrir(p.hostname, puerto, ip, p.scheme == "https")
        try:
            con.request("GET", (p.path or "/") + (f"?{p.query}" if p.query else ""),
                        headers={"Host": p.netloc, "User-Agent": "Mozilla/5.0 (Zazu bandeja)", "Accept": "text/html,text/plain;q=0.9",
                                 "Accept-Encoding": "identity"})
            r = con.getresponse()
            if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
                url = urljoin(url, r.getheader("Location"))
                continue
            if r.status >= 400:
                raise Bloqueada(f"HTTP {r.status}")
            cuerpo = r.read(MAX_BYTES + 1)
            if len(cuerpo) > MAX_BYTES:
                cuerpo = cuerpo[:MAX_BYTES]
            return url, cuerpo, r.getheader("Content-Type") or ""
        finally:
            con.close()
    raise Bloqueada("demasiadas redirecciones")


def texto_plano(b, ctype=""):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    try:
        t = b.decode(m.group(1) if m else "utf-8", "replace")
    except LookupError:
        t = b.decode("utf-8", "replace")
    og = " ".join(html.unescape(x) for x in re.findall(r'(?is)<meta[^>]+(?:property|name)=["\'](?:og:title|og:description|description)["\'][^>]*content=["\']([^"\']{3,400})', t))
    tit = re.search(r"(?is)<title[^>]*>(.*?)</title>", t)
    t = re.sub(r"(?is)<(script|style|head|noscript|svg)[^>]*>.*?</\1>", " ", t)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return (f"{html.unescape(tit.group(1)).strip()} | {og} | " if tit else f"{og} | ") + t


def leer(url, abrir=_Con):
    u, b, ct = descargar(url, abrir)
    return u, texto_plano(b, ct)[:12000]
