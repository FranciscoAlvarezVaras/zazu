#!/usr/bin/env python3
"""Lo que Fran manda a Zazu por WhatsApp → HolaZazu › Carpetas › Recibidos (sin IA). Lo lanza recibidos-whatsapp.timer cada 5 min
(así llega a Recibidos a los 10-15 min).
Los documentos y fotos que llegan por WhatsApp caen en ~/.hermes/cache/{documents,images}, y Hermes los borra a las 24 h.
Este script los COPIA (nunca mueve: la caché es del gateway) a «40 Compartido/Recibidos/AAAA-MM-DD <nombre>.ext»
(fotos: «AAAA-MM-DD HH.MM Foto de WhatsApp.jpg») si:
- tienen más de 10 min (a Zazu le da tiempo a guardarlos donde diga Fran: entonces ya están y no se duplican);
- los mandó Fran: su mensaje en ~/.hermes/state.db nombra el archivo. Lo que Zazu le manda a él también cae en la caché
  (es su propio chat y el puente lo descarga), y eso no se copia;
- su contenido (sha256) no está ya en 40 Compartido ni se copió antes (si Fran lo borra, no vuelve).
Audios, vídeos y stickers no se copian. Nunca sobrescribe (« (2)»): escribe en un temporal fuera del Cerebro y lo enlaza
con su nombre definitivo. Los nombres pasan por tachar() de privacidad.py: ningún número sensible en el Cerebro.
Si state.db no se puede leer, copia todo lo que cumpla lo demás (mejor una copia de más que perder algo) y lo avisa.
El puente de WhatsApp cambia por «_» los espacios y también cada letra con tilde o ñ («Nómina» → «N_mina»): donde casi seguro
faltaba una letra se queda «_» («N_mina», «Canci_n», «D_A»); lo demás pasa a espacio. buscar.py los encuentra igual.
Cada archivo copiado se apunta (ruta dentro de 40 Compartido) en ~/.local/state/recibidos-whatsapp-origen.txt: HolaZazu lo
usa para marcar «por WhatsApp» solo lo que vino de WhatsApp (sin repetidos, las últimas 2000 líneas).
Estado e índice de hashes: ~/.local/state/recibidos-whatsapp.json. Uso: recibidos-whatsapp.py [--simular]"""
import fcntl, hashlib, json, os, re, shutil, sqlite3, stat, sys, time, unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from privacidad import tachar  # noqa: E402

HOME = Path("/home/server")
CACHE = HOME / ".hermes/cache"
DB = HOME / ".hermes/state.db"
SHARE = HOME / "Cerebro/40 Compartido"
DESTINO = SHARE / "Recibidos"
ESTADO = HOME / ".local/state/recibidos-whatsapp.json"
ORIGEN = HOME / ".local/state/recibidos-whatsapp-origen.txt"   # lo que vino de WhatsApp (lo lee HolaZazu)
TMP = HOME / ".local/state/recibidos-whatsapp.tmp"     # mismo disco que el Cerebro y fuera de Syncthing
ESPERA = 600                                            # 10 min
RECUERDA = 30 * 86400                                   # lo ya copiado no se vuelve a copiar en 30 días
FUERA = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac", ".amr", ".flac",                    # audios
         ".mp4", ".mov", ".3gp", ".mkv", ".avi", ".webm", ".m4v"}                             # vídeos
PREFIJO = {"documents": "doc_", "images": "img_"}      # nombres del puente de WhatsApp (vid_, aud_ y sticker_ no)
NOMBRADO = re.compile(r"cache/(?:images|documents)/([A-Za-z0-9._-]+)")
CORTAS = {"del", "las", "los", "por", "con", "sin", "mis", "tus", "sus", "una", "que"}   # «del n_mero», no «del_n mero»
PROHIBIDO = re.compile(r'[\\/:*?"<>|#^\x00-\x1f]')       # SCHEMA: sin / \ : * ? " < > | # ^ [ ]


def oculto(n):
    return n.startswith(".") or n.endswith(".subiendo") or ".syncthing." in n


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def hashes_compartido(viejo):
    """{ruta relativa: [tamaño, mtime_ns, sha256]} de todo 40 Compartido; solo recalcula lo que cambió."""
    nuevo = {}
    for raiz, dirs, archivos in os.walk(SHARE):
        dirs[:] = [d for d in dirs if not oculto(d)]
        for n in archivos:
            p = Path(raiz, n)
            try:
                st = p.lstat()
                if oculto(n) or not stat.S_ISREG(st.st_mode):
                    continue
                rel = str(p.relative_to(SHARE))
                firma = [st.st_size, st.st_mtime_ns]
                nuevo[rel] = viejo[rel] if viejo.get(rel, [])[:2] == firma else firma + [sha(p)]
            except OSError:
                continue
    return nuevo


def nombrados():
    """Nombres de la caché que salen en mensajes de Fran por WhatsApp (últimos 3 días); None si no se puede leer."""
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=15)
        try:
            filas = con.execute(
                "SELECT m.content, m.api_content FROM messages m JOIN sessions s ON s.id = m.session_id "
                "WHERE m.role = 'user' AND s.source = 'whatsapp' AND m.timestamp > ? AND ("
                "m.content LIKE '%cache/images/%' OR m.content LIKE '%cache/documents/%' OR "
                "m.api_content LIKE '%cache/images/%' OR m.api_content LIKE '%cache/documents/%')",
                (time.time() - 3 * 86400,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return {n.rstrip(".") for fila in filas for c in fila if c for n in NOMBRADO.findall(c)}


def sin_letra(trozos):
    """Huecos «_» que casi seguro eran una letra con tilde o ñ: junto a una letra suelta que no es palabra
    (no a/e/o/u/y). «-ón/-ás» pegan a la izquierda («Canci_n»); las demás, a la derecha («N_mina», «D_A»); al final,
    nada («Anexo B»)."""
    pares = []
    for i, t in enumerate(trozos):
        if not (len(t) == 1 and t.isascii() and t.isalpha() and t.lower() not in "aeouy"):
            continue
        izq = trozos[i - 1] if i else ""
        der = trozos[i + 1] if i + 1 < len(trozos) else ""
        final = t.lower() in "ns" and (t.islower() or izq.isupper()) and len(izq) > 2 and izq.lower() not in CORTAS
        if final and izq[-1:].isalpha():
            pares.append((izq, t))
        elif der[:1].isalpha():
            pares.append((t, der))
    return pares


def nombre_final(p, st):
    llegada = datetime.fromtimestamp(st.st_mtime)
    if p.parent.name == "images":
        return f"{llegada:%Y-%m-%d %H.%M} Foto de WhatsApp{p.suffix.lower()}"
    m = re.match(r"doc_[0-9a-f]+_(.+)", p.name)                   # doc_<hex>_<nombre original>
    base, ext = os.path.splitext(m[1]) if m else ("", p.suffix)
    base, pares = tachar(base.replace("_", " ")), sin_letra(base.split("_"))   # el puente cambia espacios por «_»
    for a, b in pares:              # después de tachar: lo tachado ya no tiene el par y no se toca
        base = re.sub(rf"(?<!\S){re.escape(a)} {re.escape(b)}(?!\S)", lambda _: f"{a}_{b}", base, count=1)
    base = base.replace("[", "(").replace("]", ")")
    base = re.sub(r"\s+", " ", PROHIBIDO.sub(" ", base)).strip(" .-")[:120].strip() or "Documento de WhatsApp"
    if not re.match(r"\d{4}-\d\d-\d\d\b", base):
        base = f"{llegada:%Y-%m-%d} {base}"
    return base + ext.lower()


def clave(n):
    """Como compara Android/Windows: sin distinguir mayúsculas ni cómo se guardan las tildes."""
    return unicodedata.normalize("NFC", n).casefold()


def copiar(origen, st, nombre):
    """Copia sin pisar nada: temporal fuera del Cerebro → enlace con el primer nombre libre (« (2)», « (3)»…)."""
    DESTINO.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    tmp = TMP / f"{os.getpid()}.parcial"
    shutil.copyfile(origen, tmp)
    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))          # la fecha es la de llegada
    ocupados = {clave(x.name) for x in DESTINO.iterdir()}
    raiz, ext = os.path.splitext(nombre)
    try:
        for n in range(1, 1000):
            final = DESTINO / (nombre if n == 1 else f"{raiz} ({n}){ext}")
            if clave(final.name) in ocupados:
                continue
            try:
                os.link(tmp, final)
                return final
            except FileExistsError:
                continue
        raise OSError("no hay nombre libre")
    finally:
        tmp.unlink(missing_ok=True)


def apuntar_origen(rutas):
    """Añade a ORIGEN las rutas (dentro de 40 Compartido) de lo copiado: sin repetidos, las últimas 2000."""
    try:
        viejas = ORIGEN.read_text().splitlines()
    except FileNotFoundError:
        viejas = []
    nuevas = dict.fromkeys(rutas)
    lineas = list(dict.fromkeys(r for r in viejas if r and r not in nuevas)) + list(nuevas)
    tmp = ORIGEN.with_suffix(".txt.tmp")
    tmp.write_text("".join(f"{r}\n" for r in lineas[-2000:]))
    os.replace(tmp, ORIGEN)


def main():
    simular = "--simular" in sys.argv[1:]
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    cerrojo = open(ESTADO.with_suffix(".lock"), "w")
    try:
        fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Recibidos de WhatsApp: ya hay otra pasada en marcha.")
        return 0
    if not SHARE.is_dir():
        print(f"Recibidos de WhatsApp: no encuentro {SHARE}; no copio nada.")
        return 1
    try:
        e = json.loads(ESTADO.read_text())
    except (OSError, ValueError):
        e = {}
    ahora = time.time()
    indice = hashes_compartido(e.get("indice", {}))
    en_carpetas = {v[2] for v in indice.values()}
    copiados = {h: v for h, v in e.get("copiados", {}).items() if ahora - v[0] < RECUERDA}
    vistos_cache, cache_viejo = {}, e.get("cache", {})
    de_fran = nombrados()
    hechos, ya, esperando, de_zazu, fallos, de_whatsapp = [], 0, 0, 0, [], []

    for sub, prefijo in PREFIJO.items():
        carpeta = CACHE / sub
        for p in sorted(carpeta.iterdir()) if carpeta.is_dir() else []:
            try:
                st = p.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or not p.name.startswith(prefijo) or p.suffix.lower() in FUERA:
                continue
            if ahora - st.st_mtime < ESPERA:
                esperando += 1
                continue
            if de_fran is not None and p.name not in de_fran:
                de_zazu += 1
                continue
            firma = [st.st_size, st.st_mtime_ns]
            try:
                h = cache_viejo[p.name][2] if cache_viejo.get(p.name, [])[:2] == firma else sha(p)
            except OSError:
                continue
            vistos_cache[p.name] = firma + [h]
            if h in en_carpetas or h in copiados:
                ya += 1
                continue
            nombre = nombre_final(p, st)
            if simular:
                hechos.append(nombre)
                en_carpetas.add(h)
                continue
            try:
                final = copiar(p, st, nombre)
            except OSError as err:
                fallos.append(f"{nombre} ({type(err).__name__})")
                continue
            hechos.append(final.name)
            en_carpetas.add(h)
            copiados[h] = [ahora, str(final.relative_to(SHARE))]
            de_whatsapp.append(copiados[h][1])

    if not simular and not ORIGEN.exists():     # la primera vez, también lo copiado antes (últimos 30 días)
        de_whatsapp = [r for _, r in sorted(copiados.values())]
    if de_whatsapp:
        try:
            apuntar_origen(de_whatsapp)
        except OSError as err:
            fallos.append(f"{ORIGEN.name} ({type(err).__name__})")

    verbo = "se copiarían" if simular else "copiados"
    partes = [f"{len(hechos)} {verbo}" + (f" ({'; '.join(hechos)})" if hechos else ""),
              f"{ya} ya estaban en Carpetas", f"{esperando} esperando 10 min", f"{de_zazu} enviados por Zazu (no se copian)"]
    if fallos:
        partes.append(f"{len(fallos)} fallos: {'; '.join(fallos)}")
    if de_fran is None:
        partes.append("aviso: no pude leer state.db y copio sin saber quién lo mandó")
    resumen = ("[simulación] " if simular else "") + "Recibidos de WhatsApp: " + ", ".join(partes) + "."
    print(resumen)
    if not simular:
        if hechos:   # el índice incluye ya lo recién copiado en la próxima pasada (por tamaño y fecha)
            indice = hashes_compartido(indice)
        e.update(indice=indice, cache=vistos_cache, copiados=copiados,
                 ultimo={"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "copiados": len(hechos), "resumen": resumen})
        tmp = ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1))
        os.replace(tmp, ESTADO)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
