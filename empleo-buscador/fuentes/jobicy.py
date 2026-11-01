"""Jobicy (jobicy.com): remoto con filtro geográfico (europe, spain) e industria. API pública v2."""
from . import get_json
from modelo import Oferta, limpiar_html, fecha_iso

CONSULTAS = [("europe", "marketing"), ("europe", "dev"), ("europe", "data-science"), ("spain", ""), ("europe", "")]


def buscar(perfil):
    out = []; vistos = set()
    for geo, ind in CONSULTAS:
        url = f"https://jobicy.com/api/v2/remote-jobs?count=50&geo={geo}" + (f"&industry={ind}" if ind else "")
        try:
            d = get_json(url)
        except Exception:
            continue
        for j in d.get("jobs", []):
            if j.get("id") in vistos: continue
            vistos.add(j.get("id"))
            geo_txt = j.get("jobGeo") or "Remote"
            pais = "ES" if "spain" in geo_txt.lower() else "EU"
            sal = f"{j.get('salaryMin') or ''}-{j.get('salaryMax') or ''} {j.get('salaryCurrency') or ''}".strip("- ")
            out.append(Oferta("jobicy", j.get("jobTitle", ""), j.get("companyName", ""), j.get("url", ""), lugar=geo_txt, pais=pais, remoto=True,
                              fecha=fecha_iso(j.get("pubDate")), descripcion=limpiar_html(j.get("jobDescription") or j.get("jobExcerpt"))[:2000],
                              etiquetas=list(j.get("jobIndustry") or []) + list(j.get("jobLevel") and [j["jobLevel"]] or []), salario=sal if sal and not sal.startswith("-") else ""))
    return out
