"""Remotive (remotive.com): solo remoto; categorías software-dev, data, marketing. API pública."""
from . import get_json, pais_de_lugar
from modelo import Oferta, limpiar_html, fecha_iso



def buscar(perfil):
    out = []
    # una sola petición: la API ignora «category» (las tres llamadas de antes devolvían las mismas ofertas) y pide como mucho 4 consultas al día
    d = get_json("https://remotive.com/api/remote-jobs?limit=100")
    for j in d.get("jobs", []):
        lugar = j.get("candidate_required_location", "") or "Worldwide"
        out.append(Oferta("remotive", j.get("title", ""), j.get("company_name", ""), j.get("url", ""), lugar=lugar, pais=pais_de_lugar(lugar), remoto=True,
                          fecha=fecha_iso(j.get("publication_date")), descripcion=limpiar_html(j.get("description"))[:2000],
                          etiquetas=list(j.get("tags") or []) + [j.get("category", "")], salario=j.get("salary") or ""))
    return out
