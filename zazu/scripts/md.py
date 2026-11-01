#!/home/servidor/.hermes/tools/pyenv/bin/python
"""Convierte archivos y URLs a Markdown con MarkItDown (Microsoft) antes de dárselos al modelo.
Uso:  md.py <ruta|url> [--max N] [--no-cache]      (imprime el Markdown por stdout)
Módulo: from md import to_markdown
Entorno: ~/.hermes/tools/pyenv (gestionado con uv). Instalar paquetes: uv pip install --python ~/.hermes/tools/pyenv/bin/python <paquete>
"""
import hashlib, sys, time
from pathlib import Path

CACHE = Path.home() / ".hermes/cache/markitdown"
_md = None


def _converter():
    global _md
    if _md is None:
        from markitdown import MarkItDown
        _md = MarkItDown(enable_plugins=False)
    return _md


def _key(src: str) -> str:
    p = Path(src).expanduser()
    if p.exists():
        st = p.stat()
        base = f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    else:
        base = src
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def _convert_url_as_browser(url: str, first_error: Exception) -> str:
    """Algunos sitios devuelven 4xx/5xx al cliente de MarkItDown: reintenta con cabecera de navegador."""
    import tempfile, urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                                               "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data, ctype = r.read(20_000_000), r.headers.get("Content-Type", "")
    except Exception as e:
        raise RuntimeError(f"falló MarkItDown ({first_error}) y el reintento como navegador ({e})")
    ext = ".pdf" if "pdf" in ctype else ".html"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(data)
    try:
        return _converter().convert(f.name).markdown or ""
    finally:
        Path(f.name).unlink(missing_ok=True)


def to_markdown(src: str, max_chars: int = 0, use_cache: bool = True) -> str:
    """Devuelve el Markdown de src (ruta local o URL http/https). max_chars>0 recorta y lo indica."""
    is_url = src.startswith(("http://", "https://"))
    if not is_url:
        src = str(Path(src).expanduser())
        if not Path(src).exists():
            raise FileNotFoundError(src)
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{_key(src)}.md"
    if use_cache and f.exists() and (not is_url or time.time() - f.stat().st_mtime < 3600):
        text = f.read_text()
    else:
        try:
            text = _converter().convert(src).markdown or ""
        except Exception as e:
            if not is_url:
                raise
            text = _convert_url_as_browser(src, e)
        if use_cache:
            f.write_text(text)
    if not text.strip():
        text = "[MarkItDown no extrajo texto: probablemente un PDF/imagen escaneado que necesita OCR]"
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... recortado: {len(text) - max_chars} caracteres más; usa --max mayor o lee el archivo en {f}]"
    return text


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    mx = int(a[a.index("--max") + 1]) if "--max" in a else 0
    try:
        print(to_markdown(a[0], mx, "--no-cache" not in a))
    except Exception as e:
        print(f"ERROR md.py: {type(e).__name__}: {e}", file=sys.stderr); sys.exit(1)
