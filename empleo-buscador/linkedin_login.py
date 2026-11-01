#!/usr/bin/env python3
"""Inicio de sesión en LinkedIn para el rastreador de publicaciones, SIN pantalla (el servidor no tiene escritorio).
Fran teclea su correo y contraseña aquí (no se guardan en ningún sitio: solo se escriben en el formulario); si LinkedIn pide
verificación en dos pasos, aprueba en el móvil o teclea el código. La sesión queda guardada en
~/.local/state/empleo-buscador/jobhunter/.session (solo tuya). Ejecutar con el Python del entorno de jobhunter:
  ~/Spirit/experimentos/jobhunter/venv/bin/python ~/Spirit/empleo-buscador/linkedin_login.py"""
import getpass, os, sys, time
from pathlib import Path

ESTADO = Path.home() / ".local/state/empleo-buscador/jobhunter"
os.environ.setdefault("JOBHUNTER_HOME", str(ESTADO)); ESTADO.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path.home() / "Spirit/experimentos/jobhunter"))
from jobhunter.constants import SESSION_DIR  # noqa: E402
from jobhunter.scraper import linkedin_session_ready, wait_for_linkedin_session, kill_playwright_zombies  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def main():
    kill_playwright_zombies(); os.makedirs(SESSION_DIR, exist_ok=True)
    print("Inicio de sesión en LinkedIn (sin pantalla). Nada se guarda salvo la sesión del navegador.")
    correo = input("Correo de LinkedIn: ").strip(); clave = getpass.getpass("Contraseña (no se muestra): ")
    with sync_playwright() as p:
        b = p.chromium.launch_persistent_context(user_data_dir=SESSION_DIR, headless=True, executable_path="/usr/bin/google-chrome", viewport={"width": 1300, "height": 850})
        page = b.pages[0] if b.pages else b.new_page()
        if linkedin_session_ready(b, None):
            print("Ya había sesión válida."); b.close(); return
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=60000)
        page.fill("#username", correo); page.fill("#password", clave); del clave
        page.click('button[type="submit"]'); page.wait_for_timeout(5000)
        for _ in range(3):
            if linkedin_session_ready(b, page): break
            url = page.url; print(f"Ahora estoy en: {url[:80]}")
            if "checkpoint" in url or "challenge" in url:
                codigo = input("LinkedIn pide verificación. Aprueba en el móvil, o teclea aquí el código (Enter si ya aprobaste): ").strip()
                if codigo:
                    for sel in ("input[name='pin']", "#input__email_verification_pin", "input[type='text']"):
                        try:
                            page.fill(sel, codigo); page.keyboard.press("Enter"); break
                        except Exception:
                            continue
                page.wait_for_timeout(6000)
            else:
                input("Si ves que falta algo (captcha…), hazlo desde tu PC en linkedin.com y pulsa Enter para comprobar de nuevo: ")
        ok = wait_for_linkedin_session(b, page, timeout_s=120)
        page.wait_for_timeout(3000); b.close()
    print("Sesión guardada. Ya puedes usar la fuente linkedin_posts." if ok else "No se completó el inicio de sesión. Inténtalo otra vez o pide ayuda a Claude.")


if __name__ == "__main__":
    main()
