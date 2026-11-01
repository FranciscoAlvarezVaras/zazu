#!/usr/bin/env python3
"""Rastreador de PUBLICACIONES de reclutadores en LinkedIn (reutiliza jobhunter/scraper.py, MIT, de dev-gaspar/jobhunter).
Se ejecuta con el Python del entorno de jobhunter (tiene Playwright) y devuelve JSON por stdout. Necesita una sesión de LinkedIn
guardada con linkedin_login.py (la inicia Fran). Solo lee: nunca publica, comenta, conecta ni envía nada.
Uso: linkedin_posts_worker.py --consultas "junior data analyst,marketing digital junior" [--tiempo 24h|week] [--scroll 3]"""
import argparse, json, os, sys
from pathlib import Path

ESTADO = Path.home() / ".local/state/empleo-buscador/jobhunter"
os.environ.setdefault("JOBHUNTER_HOME", str(ESTADO)); ESTADO.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path.home() / "Spirit/experimentos/jobhunter"))
from jobhunter.constants import SESSION_DIR  # noqa: E402
from jobhunter.scraper import scrape_posts, linkedin_session_ready, kill_playwright_zombies  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
import jobhunter.ui, jobhunter.scraper  # noqa: E402
from rich.console import Console  # noqa: E402
jobhunter.ui.console = jobhunter.scraper.console = Console(file=sys.stderr)   # sus mensajes no deben mezclarse con el JSON de stdout

CHROME = "/usr/bin/google-chrome"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--consultas", required=True); ap.add_argument("--tiempo", default="24h"); ap.add_argument("--scroll", type=int, default=3)
    a = ap.parse_args()
    if not Path(SESSION_DIR).exists():
        print(json.dumps({"error": "sin_sesion", "detalle": "Inicia sesión una vez con linkedin_login.py"})); sys.exit(2)
    kill_playwright_zombies(); salida = []
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(user_data_dir=SESSION_DIR, headless=True, executable_path=CHROME,
                                                       viewport={"width": 1300, "height": 850}, permissions=["clipboard-read", "clipboard-write"])
        page = browser.pages[0] if browser.pages else browser.new_page()
        if not linkedin_session_ready(browser, None):
            browser.close(); print(json.dumps({"error": "sesion_caducada", "detalle": "Vuelve a iniciar sesión con linkedin_login.py"})); sys.exit(2)
        for consulta in [c.strip() for c in a.consultas.split(",") if c.strip()]:
            try:
                posts = scrape_posts(page, consulta, max_scroll=a.scroll, time_filter=a.tiempo)
            except Exception as e:
                posts = []; salida.append({"consulta": consulta, "error": type(e).__name__})
                continue
            for po in posts:
                po["consulta"] = consulta; salida.append(po)
        browser.close()
    print(json.dumps(salida, ensure_ascii=False))


if __name__ == "__main__":
    main()
