"""Publicaciones de reclutadores en LinkedIn («buscamos junior…, escribid a …@…»): ofertas que nunca llegan a ser oferta formal.
Reutiliza el rastreador de jobhunter (MIT) en un subproceso con su propio entorno (Playwright). Hace falta una sesión de LinkedIn
iniciada por Fran (linkedin_login.py); sin ella, esta fuente se salta sin ruido. Solo lectura y pocas consultas (una por pista)."""
import json, re, subprocess
from pathlib import Path
from modelo import Oferta, fecha_iso
from datetime import date

PY = Path.home() / "Spirit/experimentos/jobhunter/venv/bin/python"
WORKER = Path.home() / "Spirit/empleo-buscador/linkedin_posts_worker.py"
SESION = Path.home() / ".local/state/empleo-buscador/jobhunter/.session"
CONSULTAS = {"dev": "junior data analyst OR junior developer Valencia remote", "marketing": "marketing digital junior remoto OR digital marketing junior remote"}


def post_a_oferta(po):
    """Un post → Oferta: título = primera línea útil, empresa = autor, enlace = post (o perfil del autor), etiquetas = correos encontrados."""
    texto = re.sub(r"\s+", " ", po.get("text") or "").strip()
    primera = next((l.strip() for l in (po.get("text") or "").splitlines() if len(l.strip()) > 15), texto[:80])
    titulo = primera[:90]
    correos = [c for c in (po.get("emails_found") or []) if "@" in c]
    bajo = texto.lower()
    pais = "ES" if any(k in bajo for k in ("españa", "spain", "valencia", "madrid", "barcelona")) else ""
    remoto = any(k in bajo for k in ("remoto", "remote", "teletrabajo", "en remoto"))
    return Oferta("linkedin_posts", titulo, po.get("author_name") or "Publicación en LinkedIn", po.get("post_url") or po.get("author_url") or "https://www.linkedin.com/feed/",
                  lugar="publicación" + (" · remoto" if remoto else ""), pais=pais, remoto=remoto, fecha=date.today().isoformat(), descripcion=texto[:2000],
                  etiquetas=["publicación", "contacto: " + ", ".join(correos)] if correos else ["publicación"])


def buscar(perfil):
    if not SESION.exists() or not PY.exists():
        return []
    r = subprocess.run([str(PY), str(WORKER), "--consultas", ",".join(CONSULTAS.values()), "--tiempo", "24h", "--scroll", "3"], capture_output=True, text=True, timeout=600)
    try:
        datos = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else []
    except ValueError:
        return []
    if isinstance(datos, dict) and datos.get("error"):
        return []
    return [post_a_oferta(po) for po in datos if isinstance(po, dict) and po.get("text")]
