#!/usr/bin/env python3
"""Buscar en el Cerebro (bóveda de Obsidian ~/Cerebro) por palabras (SQLite FTS5, BM25) y por significado (embeddings). Solo lectura.

  buscar-cerebro.py --indexar        pone al día el índice (solo lo cambiado, por fecha de modificación)
  buscar-cerebro.py "consulta" [-n 8]  los mejores resultados, con ruta y fragmento
  buscar-cerebro.py "consulta" --solo-palabras   sin la parte por significado

Índice en ~/.local/state/buscar-cerebro/indice.db. Salta .obsidian y todo lo que no sea .md.
Por significado: cada nota se parte en trozos de ~800 palabras y Ollama (127.0.0.1:11434, modelo nomic-embed-text,
en este PC) saca un vector de cada trozo; se guardan en el mismo indice.db. Las dos listas (palabras y significado)
se mezclan con Reciprocal Rank Fusion (k=60). Si Ollama no responde, busca solo por palabras como antes.
Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0
(connectors/hybrid_search.py: la parte BM25, cómo poner a salvo la consulta para FTS5 y la mezcla RRF;
connectors/embeddings.py: los embeddings con Ollama).
"""
import argparse, array, json, math, re, sqlite3, sys, urllib.request
from pathlib import Path

CEREBRO = Path.home() / "Cerebro"
DB = Path.home() / ".local/state/buscar-cerebro/indice.db"
OLLAMA = "http://127.0.0.1:11434"
MODELO = "nomic-embed-text"
TROZO = 800          # palabras por trozo
SOLAPE = 100         # palabras que se repiten entre trozos seguidos (una idea partida no se pierde)
RRF_K = 60           # el valor canónico del artículo de RRF; el mismo que OpenJarvis
CANDIDATOS = 50      # cuántos de cada lista entran en la mezcla


def abrir():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS notas(ruta TEXT PRIMARY KEY, mtime REAL)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(ruta UNINDEXED, titulo, texto,"
              " tokenize='unicode61 remove_diacritics 2')")
    # vectores: qué versión de cada nota tiene vectores (mtime) y un vector normalizado (float32) por trozo
    c.execute("CREATE TABLE IF NOT EXISTS vec_notas(ruta TEXT PRIMARY KEY, mtime REAL, modelo TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS vec(ruta TEXT, n INTEGER, ini INTEGER, v BLOB, PRIMARY KEY(ruta, n))")
    return c


def embeber(textos, timeout=120):
    """Lista de vectores normalizados (array 'f'), o None si Ollama no responde."""
    req = urllib.request.Request(f"{OLLAMA}/api/embed", data=json.dumps({"model": MODELO, "input": textos}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            vs = json.load(r)["embeddings"]
    except (OSError, ValueError, KeyError):
        return None
    out = []
    for v in vs:
        norma = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append(array.array("f", (x / norma for x in v)))
    return out


def trozos(palabras):
    """(inicio, texto) de cada trozo de ~TROZO palabras."""
    if not palabras:
        return []
    paso = TROZO - SOLAPE
    return [(i, " ".join(palabras[i:i + TROZO])) for i in range(0, max(len(palabras) - SOLAPE, 1), paso)]


def indexar(c):
    vistas, nuevas = set(), 0
    previas = dict(c.execute("SELECT ruta, mtime FROM notas"))
    for p in CEREBRO.rglob("*.md"):
        rel = p.relative_to(CEREBRO)
        if ".obsidian" in rel.parts or not p.is_file():
            continue
        ruta, mtime = str(rel), p.stat().st_mtime
        vistas.add(ruta)
        if previas.get(ruta) == mtime:
            continue
        texto = p.read_text(encoding="utf-8", errors="replace")
        c.execute("DELETE FROM fts WHERE ruta=?", (ruta,))
        c.execute("INSERT INTO fts(ruta, titulo, texto) VALUES(?,?,?)", (ruta, p.stem, texto))
        c.execute("INSERT OR REPLACE INTO notas VALUES(?,?)", (ruta, mtime))
        nuevas += 1
    borradas = set(previas) - vistas
    for ruta in borradas:
        c.execute("DELETE FROM fts WHERE ruta=?", (ruta,))
        c.execute("DELETE FROM notas WHERE ruta=?", (ruta,))
    c.execute("DELETE FROM vec WHERE ruta NOT IN (SELECT ruta FROM notas)")
    c.execute("DELETE FROM vec_notas WHERE ruta NOT IN (SELECT ruta FROM notas)")
    c.commit()
    print(f"{len(vistas)} notas · {nuevas} (re)indexadas · {len(borradas)} quitadas")
    indexar_vectores(c)


def indexar_vectores(c):
    """Vectores de las notas nuevas o cambiadas. Se guarda nota a nota: si se corta, la próxima vez sigue donde quedó."""
    pendientes = c.execute("SELECT n.ruta, n.mtime FROM notas n LEFT JOIN vec_notas v ON v.ruta=n.ruta"
                           " WHERE v.mtime IS NOT n.mtime OR v.modelo IS NOT ?", (MODELO,)).fetchall()
    if not pendientes:
        print("vectores: al día")
        return
    hechas = 0
    for ruta, mtime in pendientes:
        (titulo, texto), = c.execute("SELECT titulo, texto FROM fts WHERE ruta=?", (ruta,)).fetchall() or [(None, None)]
        if texto is None:
            continue
        ts = trozos(texto.split())
        vs = embeber([f"search_document: {titulo}\n{t}" for _, t in ts]) if ts else []
        if vs is None:
            print(f"vectores: Ollama no responde; {hechas} de {len(pendientes)} hechas (la búsqueda sigue por palabras)")
            return
        c.execute("DELETE FROM vec WHERE ruta=?", (ruta,))
        c.executemany("INSERT INTO vec VALUES(?,?,?,?)", [(ruta, i, ini, v.tobytes()) for i, ((ini, _), v) in enumerate(zip(ts, vs))])
        c.execute("INSERT OR REPLACE INTO vec_notas VALUES(?,?,?)", (ruta, mtime, MODELO))
        c.commit()
        hechas += 1
    print(f"vectores: {hechas} notas con vectores nuevos · {c.execute('SELECT count(*) FROM vec').fetchone()[0]} trozos en total")


def a_fts(consulta):
    # Cada palabra entre comillas y unidas con OR: así «-», «:» o «"» no rompen la sintaxis de FTS5.
    palabras = re.findall(r"\w+", consulta)
    return " OR ".join(f'"{w}"' for w in palabras)


def por_palabras(c, consulta, n):
    """[(ruta, fragmento)] por BM25: menor = mejor; el título pesa 5 veces más que el texto."""
    q = a_fts(consulta)
    if not q:
        return []
    return [(r, f) for r, f, _ in c.execute(
        "SELECT ruta, snippet(fts, 2, '«', '»', ' … ', 24), bm25(fts, 0, 5.0, 1.0) AS s"
        " FROM fts WHERE fts MATCH ? ORDER BY s LIMIT ?", (q, n))]


def por_significado(c, consulta, n):
    """[(ruta, inicio del trozo más parecido)] por similitud de coseno (vectores ya normalizados), o None sin Ollama."""
    if not c.execute("SELECT 1 FROM vec LIMIT 1").fetchone():
        return None
    q = embeber([f"search_query: {consulta}"], timeout=20)
    if not q:
        return None
    q = q[0]
    mejor = {}
    for ruta, ini, blob in c.execute("SELECT ruta, ini, v FROM vec"):
        v = array.array("f")
        v.frombytes(blob)
        s = sum(a * b for a, b in zip(q, v))
        if s > mejor.get(ruta, (-2, 0))[0]:
            mejor[ruta] = (s, ini)
    orden = sorted(mejor.items(), key=lambda x: -x[1][0])[:n]
    return [(ruta, ini) for ruta, (_, ini) in orden]


def buscar(c, consulta, n, solo_palabras=False):
    """[(ruta, fragmento)] mezclando las dos listas con RRF; el segundo valor dice si se usó el significado."""
    pal = por_palabras(c, consulta, CANDIDATOS)
    sig = None if solo_palabras else por_significado(c, consulta, CANDIDATOS)
    if sig is None:
        return pal[:n], False
    puntos = {}
    for lista in (pal, sig):
        for i, (ruta, _) in enumerate(lista, 1):
            puntos[ruta] = puntos.get(ruta, 0.0) + 1.0 / (RRF_K + i)
    frag = dict(pal)
    inicio = dict(sig)
    out = []
    for ruta in sorted(puntos, key=lambda r: -puntos[r])[:n]:
        if ruta not in frag:   # solo por significado: el comienzo del trozo que más se parece
            (texto,), = c.execute("SELECT texto FROM fts WHERE ruta=?", (ruta,)).fetchall()
            ini = inicio[ruta]
            frag[ruta] = " ".join(texto.split()[ini:ini + 30]) + " …"
        out.append((ruta, frag[ruta]))
    return out, True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("consulta", nargs="?")
    ap.add_argument("--indexar", action="store_true")
    ap.add_argument("--solo-palabras", action="store_true", help="sin la parte por significado (Ollama)")
    ap.add_argument("-n", type=int, default=8)
    a = ap.parse_args()
    c = abrir()
    if a.indexar:
        indexar(c)
    if not a.consulta:
        if not a.indexar:
            ap.error("falta la consulta (o --indexar)")
        return
    if not c.execute("SELECT 1 FROM notas LIMIT 1").fetchone():
        indexar(c)
    filas, mezcla = buscar(c, a.consulta, a.n, a.solo_palabras)
    if not mezcla and not a.solo_palabras:
        print("(solo por palabras: la búsqueda por significado no está disponible ahora)", file=sys.stderr)
    if not filas:
        print("Sin resultados.")
    for i, (ruta, frag) in enumerate(filas, 1):
        print(f"{i}. ~/Cerebro/{ruta}\n   {' '.join(frag.split())}")


if __name__ == "__main__":
    sys.exit(main())
