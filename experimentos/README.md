# experimentos — pruebas aisladas

Aquí va lo que se prueba **sin ponerlo en producción**. Nada de esta carpeta es necesario para que el servidor funcione.

| Carpeta | Qué es |
|---|---|
| `odysseus/` | Espacio de trabajo con IA (https://github.com/odysseus-dev/odysseus), aislado en una jaula y parado por defecto. Está aquí de verdad; `~/Odysseus` es un enlace. Nuestro código: `bin/`, `analisis/`, `skill-odysseus/`. No va a git: `venv/`, `src/` (el programa descargado), `datos/`, `.admin`, `odysseus.env`. Arranque: `systemctl --user start odysseus` y abrir http://127.0.0.1:7011. Más en `odysseus/README.md`. |

| `jobhunter/` | Repo externo **dev-gaspar/jobhunter** (MIT, commit f1a91ec, clonado el 2026-10-12 a petición de Fran). Auto-aplicador de LinkedIn con Playwright + Gemini. Aquí **solo reutilizamos su rastreador de publicaciones de reclutadores** (`jobhunter/scraper.py`) como fuente del buscador de `~/Spirit/empleo-buscador`; nunca se ejecutan su envío de correos (`mailer.py`, `applying.py`) ni el modo `--auto`. Entorno aislado en `venv/`. No está en git (repo ajeno). |

Regla: si algo funciona y lo quieres de verdad, se **mueve** a su sitio (`zazu/`, `hermes/`, `pagina-web/`…) y se documenta. Si no, se borra.
