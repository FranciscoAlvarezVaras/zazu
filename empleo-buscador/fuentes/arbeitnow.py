"""Arbeitnow (arbeitnow.com): tablón europeo, muchas ofertas en Alemania y remoto; API pública sin clave, paginada."""
from . import get_json, pais_de_lugar
from modelo import Oferta, limpiar_html, fecha_iso


def buscar(perfil, paginas=3):
    out = []
    for p in range(1, paginas + 1):
        d = get_json(f"https://www.arbeitnow.com/api/job-board-api?page={p}")
        for j in d.get("data", []):
            out.append(Oferta("arbeitnow", j.get("title", ""), j.get("company_name", ""), j.get("url", ""), lugar=j.get("location", ""),
                              pais=(pais_de_lugar(j.get("location")) or "DE") if j.get("location") and not j.get("remote") else ("REMOTE" if j.get("remote") else ""),   # es un tablero alemán: sin más pistas, DE
                              remoto=bool(j.get("remote")), fecha=fecha_iso(j.get("created_at")), descripcion=limpiar_html(j.get("description"))[:2000],
                              etiquetas=list(j.get("tags") or []) + list(j.get("job_types") or [])))
    return out
