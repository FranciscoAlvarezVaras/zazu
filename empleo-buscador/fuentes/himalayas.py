"""Himalayas (himalayas.app): remoto; API pública con restricciones de país por oferta."""
from . import get_json
from modelo import Oferta, limpiar_html, fecha_iso

EUROPA = {"spain","portugal","germany","france","netherlands","ireland","united kingdom","italy","austria","belgium","denmark","sweden","norway","finland","poland","czechia","switzerland","europe","emea","worldwide"}


def buscar(perfil, paginas=8):
    out = []
    for p in range(paginas):
        try:
            d = get_json(f"https://himalayas.app/jobs/api?limit=20&offset={p*20}")   # la API devuelve 20 por página aunque se pida 100
        except Exception:
            break
        for j in d.get("jobs", []):
            restr = [str(x).lower() for x in (j.get("locationRestrictions") or [])]
            if restr and not any(any(e in r for e in EUROPA) for r in restr):
                continue   # solo ofertas abiertas a Europa (o sin restricción)
            lugar = ", ".join(j.get("locationRestrictions") or []) or "Remote"
            pais = "ES" if any("spain" in r for r in restr) else ("EU" if restr else "REMOTE")
            sal = f"{j.get('minSalary') or ''}-{j.get('maxSalary') or ''} {j.get('currency') or ''}".strip("- ")
            out.append(Oferta("himalayas", j.get("title", ""), j.get("companyName", ""), j.get("applicationLink", ""), lugar=lugar, pais=pais, remoto=True,
                              fecha=fecha_iso(j.get("pubDate")), descripcion=limpiar_html(j.get("description") or j.get("excerpt"))[:2000],
                              etiquetas=list(j.get("categories") or []) + list(j.get("seniority") or []), salario=sal if sal and not sal.startswith("-") else ""))
    return out
