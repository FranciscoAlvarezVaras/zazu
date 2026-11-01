"""Remote OK (remoteok.com): remoto mundial; API pública (el primer elemento es un aviso legal, no una oferta)."""
from . import get_json, pais_de_lugar
from modelo import Oferta, limpiar_html, fecha_iso


def buscar(perfil):
    d = get_json("https://remoteok.com/api")
    out = []
    for j in d:
        if not isinstance(j, dict) or not j.get("position"):
            continue
        lugar = j.get("location") or "Remote"
        pais = "REMOTE" if lugar.strip().lower() in ("", "remote", "worldwide", "anywhere") else pais_de_lugar(lugar)
        sal = f"{j.get('salary_min') or ''}-{j.get('salary_max') or ''}".strip("-")
        out.append(Oferta("remoteok", j["position"], j.get("company", ""), j.get("url", ""), lugar=lugar, pais=pais, remoto=True,
                          fecha=fecha_iso(j.get("epoch") or j.get("date")), descripcion=limpiar_html(j.get("description"))[:2000],
                          etiquetas=list(j.get("tags") or []), salario=sal if sal and sal != "0-0" else ""))
    return out
