"""Adzuna (developer.adzuna.com): el agregador más completo de Europa (España, Reino Unido, Alemania, Francia, Países Bajos, Italia, Polonia, Austria).
Necesita claves gratuitas de Fran: ADZUNA_APP_ID y ADZUNA_APP_KEY en ~/.local/state/empleo-buscador/claves.env. Sin claves, esta fuente se salta."""
import os
from pathlib import Path
from . import get_json, q, claves_de_perfil
from modelo import Oferta, limpiar_html, fecha_iso

CLAVES = Path.home() / ".local/state/empleo-buscador/claves.env"
PAISES = {"es": "ES", "gb": "GB", "de": "DE", "fr": "FR", "nl": "NL", "it": "IT", "pl": "PL", "at": "AT"}


def _claves():
    env = dict(os.environ)
    if CLAVES.exists():
        for l in CLAVES.read_text().splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1); env[k.strip()] = v.strip().strip('"')
    return env.get("ADZUNA_APP_ID"), env.get("ADZUNA_APP_KEY")


def buscar(perfil):
    app_id, app_key = _claves()
    if not app_id or not app_key:
        return []
    out = []; vistos = set()
    consultas = [("es", "junior data analyst"), ("es", "marketing digital junior"), ("es", "desarrollador junior"), ("gb", "junior digital marketing remote"), ("de", "junior data analyst english"), ("nl", "junior data analyst"), ("ie", "junior marketing")]
    for pais, texto in consultas:
        if pais not in PAISES: continue
        try:
            d = get_json(f"https://api.adzuna.com/v1/api/jobs/{pais}/search/1?" + q(app_id=app_id, app_key=app_key, what=texto, max_days_old=perfil.get("max_dias", 14), results_per_page=50, content_type="application/json"))
        except Exception:
            continue
        for j in d.get("results", []):
            if j.get("id") in vistos: continue
            vistos.add(j.get("id"))
            lugar = (j.get("location") or {}).get("display_name", "")
            sal = f"{int(j.get('salary_min') or 0) or ''}-{int(j.get('salary_max') or 0) or ''}".strip("-")
            out.append(Oferta("adzuna", j.get("title", ""), (j.get("company") or {}).get("display_name", ""), j.get("redirect_url", ""), lugar=lugar, pais=PAISES[pais],
                              remoto="remot" in (j.get("title", "") + lugar).lower(), fecha=fecha_iso(j.get("created")), descripcion=limpiar_html(j.get("description"))[:2000],
                              etiquetas=[(j.get("category") or {}).get("label", "")], salario=sal if sal and sal != "0-0" else ""))
    return out
