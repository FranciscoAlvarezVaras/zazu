"""The Muse (themuse.com): API pública; sobre todo EE. UU., pero permite filtrar por nivel y ubicación («Flexible / Remote», ciudades europeas)."""
from . import get_json, q
from modelo import Oferta, limpiar_html, fecha_iso

CONSULTAS = [("Data and Analytics", "Entry Level"), ("Software Engineering", "Entry Level"), ("Marketing", "Entry Level"), ("Marketing", "Mid Level")]
UBICACIONES = ["Flexible / Remote", "Madrid, Spain", "Barcelona, Spain", "Valencia, Spain", "Lisbon, Portugal", "Berlin, Germany", "Amsterdam, Netherlands", "Dublin, Ireland", "London, United Kingdom"]


def buscar(perfil):
    out = []; vistos = set()
    for cat, nivel in CONSULTAS:
        for ub in UBICACIONES[:4]:
            try:
                d = get_json("https://www.themuse.com/api/public/jobs?" + q(category=cat, level=nivel, location=ub, page=0))
            except Exception:
                continue
            for j in d.get("results", []):
                if j.get("id") in vistos: continue
                vistos.add(j.get("id"))
                lugares = ", ".join(l.get("name", "") for l in j.get("locations", []))
                remoto = "remote" in lugares.lower() or "flexible" in lugares.lower()
                pais = "REMOTE" if remoto else ("ES" if "spain" in lugares.lower() else ("EU" if any(k in lugares.lower() for k in ("portugal", "germany", "netherlands", "ireland", "united kingdom", "france", "italy")) else "US"))
                out.append(Oferta("themuse", j.get("name", ""), (j.get("company") or {}).get("name", ""), (j.get("refs") or {}).get("landing_page", ""), lugar=lugares, pais=pais, remoto=remoto,
                                  fecha=fecha_iso(j.get("publication_date")), descripcion=limpiar_html(j.get("contents"))[:2000],
                                  etiquetas=[c.get("name", "") for c in j.get("categories", [])] + [l.get("name", "") for l in j.get("levels", [])]))
    return out
