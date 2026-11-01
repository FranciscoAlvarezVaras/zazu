#!/usr/bin/env python3
"""Habilidades por repetición: lo que pides una y otra vez, o las mismas herramientas en el mismo orden, en 3 o más conversaciones que
salieron bien (sin una corrección tuya en esa conversación). Se propone como lección: «Podría crear una habilidad para X (lo pediste N veces: …)».
Sin IA y sin red: solo cuenta lo que ya hay en el almacén (lo que ingerir.py copia de los state.db de Hermes). No crea ninguna habilidad:
solo la propone, y solo vale si Fran la aprueba. Como mucho 2 propuestas por noche; no repite una que ya se propuso (aunque la rechazaras).
Va dentro de la reflexión nocturna (reflexion.py); apagar con datos/reflexion.apagada o datos/habilidades.apagada.

Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: src/openjarvis/learning/agents/skill_discovery.py
(SkillDiscovery.analyze_traces). Cambios: una «traza» es una conversación de Hermes; el resultado es 1 si no la corregiste y 0 si sí;
una secuencia cuenta una vez por conversación; se juntan las llamadas seguidas a la misma herramienta («terminal, terminal» = «terminal»);
se quitan las secuencias contenidas en otra más larga con las mismas conversaciones; además de herramientas, se buscan peticiones parecidas
(conversaciones.repetidas) y lo que se guarda es una lección propuesta, no una habilidad registrada.
Uso: habilidades.py [--ver]   (--ver: dice qué propondría, sin guardar)
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen
import conversaciones
import lecciones

MIN_VECES, MIN_LARGO, MAX_LARGO, MIN_BUEN, MAX_PROPUESTAS = 3, 2, 4, 0.5, 2
ORIGEN = "habilidades"
NO_SON_HERRAMIENTAS = {"", "tool_call", "clarify"}        # nombres genéricos o preguntas a Fran: no dicen qué se hizo
YA_HABILIDAD = {"skill_view", "skill_manage"}             # si ya usó una habilidad, no hace falta crearla
# Saludos para probar un asistente nuevo y adjuntos sin texto: se repiten, pero no son trabajo que automatizar.
RUIDO = re.compile(r"presentate|que sabes hacer|quien eres|en una (frase|linea)\W*$|^\W*(hola|buenas|hey)\W*(zazu)?\W*$|\[(imagen|audio|archivo|documento|video) adjunt|^\W*\[(system|session)\b")


def corregidas(c):
    """Conversaciones donde corregiste a Zazu (no salieron bien)."""
    return {r[0] for r in c.execute("SELECT json_extract(meta,'$.sesion') FROM hecho WHERE tipo='correccion'")}


def trazas(c):
    """Por conversación: {sesion: {"herramientas": [...], "pide": [(clave, texto) de tu último mensaje antes de cada herramienta]}}."""
    out = defaultdict(lambda: {"herramientas": [], "pide": [], "ultimo": None})
    for r in c.execute("SELECT clave, tipo, texto, json_extract(meta,'$.sesion') s, json_extract(meta,'$.origen') o, json_extract(meta,'$.herramientas') h "
                       "FROM hecho WHERE fuente='hermes' AND tipo IN ('user','assistant') ORDER BY s, json_extract(meta,'$.msg')"):
        if conversaciones.es_rutina(r["o"]):
            continue
        t = out[r["s"]]
        if r["tipo"] == "user":
            t["ultimo"] = (r["clave"], r["texto"] or "")
        for h in json.loads(r["h"] or "[]"):
            if h and h not in NO_SON_HERRAMIENTAS and (not t["herramientas"] or t["herramientas"][-1] != h) and t["ultimo"]:
                t["herramientas"].append(h)
                t["pide"].append(t["ultimo"])
    return out


def secuencias(c, min_veces=MIN_VECES):
    """Herramientas en el mismo orden en `min_veces` conversaciones o más, casi siempre sin corrección → [dict] de la mejor a la peor."""
    malas = corregidas(c)
    vistas, pide = defaultdict(set), defaultdict(dict)
    for ses, t in trazas(c).items():
        hs = t["herramientas"]
        for largo in range(MIN_LARGO, min(MAX_LARGO, len(hs)) + 1):
            for i in range(len(hs) - largo + 1):
                seq = tuple(hs[i:i + largo])
                vistas[seq].add(ses)
                pide[seq].setdefault(ses, t["pide"][i])          # una vez por conversación: la primera
    out = []
    for seq, ses in vistas.items():
        buen = sum(s not in malas for s in ses) / len(ses)
        if len(ses) >= min_veces and buen >= MIN_BUEN and not YA_HABILIDAD & set(seq):
            out.append({"seq": seq, "sesiones": ses, "buen": buen})
    # una secuencia dentro de otra más larga con las mismas conversaciones no aporta nada
    largas = [x for x in out if not any(len(y["seq"]) > len(x["seq"]) and y["sesiones"] == x["sesiones"] and _dentro(x["seq"], y["seq"]) for y in out)]
    for x in largas:
        x["evidencia"] = [pide[x["seq"]][s][0] for s in sorted(x["sesiones"])][:10]
        x["ejemplos"] = [pide[x["seq"]][s][1] for s in sorted(x["sesiones"])]
    return sorted(largas, key=lambda x: (-len(x["sesiones"]) * x["buen"], -len(x["seq"])))


def _dentro(corta, larga):
    return any(larga[i:i + len(corta)] == corta for i in range(len(larga) - len(corta) + 1))


def peticiones(c, min_veces=MIN_VECES):
    """Peticiones tuyas parecidas en `min_veces` conversaciones o más, casi siempre sin corrección."""
    malas = corregidas(c)
    msgs, _ = conversaciones.sin_botones(conversaciones.cargar(c, con_clave=True))
    out = []
    for g in conversaciones.repetidas(msgs, min_veces):
        buen = sum(s not in malas for s in g[1]) / len(g[1])
        if buen >= MIN_BUEN and not RUIDO.search(g[0]):
            out.append({"texto": g[3], "veces": g[2], "sesiones": g[1], "buen": buen, "evidencia": g[4][:10]})
    return out


def _corto(t, n=60):
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _texto(base, ejemplos, escudo):
    """La frase de la lección, con ejemplos solo si no llevan datos privados ni parecen órdenes para un modelo."""
    ej = [f"«{_corto(e)}»" for e in ejemplos if e and not lecciones.PRIVADO.search(e) and not escudo.sospechoso(e, "medio")][:2]
    return base.format(ej=(": " + ", ".join(ej)) if ej else "")


def candidatas(c, escudo):
    out = []
    for p in peticiones(c):
        if not lecciones.PRIVADO.search(p["texto"]) and not escudo.sospechoso(p["texto"], "medio"):
            out.append((f"Podría crear una habilidad para «{_corto(p['texto'], 90)}» (lo pediste {p['veces']} veces en {len(p['sesiones'])} conversaciones)", p["evidencia"]))
    for s in secuencias(c):
        out.append((_texto(f"Podría crear una habilidad que haga {' → '.join(s['seq'])} de una vez (pasó en {len(s['sesiones'])} conversaciones{{ej}})",
                           s["ejemplos"], escudo), s["evidencia"]))
    return [(t, ev) for t, ev in out if t and ev]


def ya_propuesta(c, evidencia):
    """True si una lección de habilidades (en cualquier estado) ya se apoya en la mitad o más de esta evidencia."""
    nueva = set(evidencia)
    for r in c.execute("SELECT evidencia FROM leccion WHERE origen=?", (ORIGEN,)):
        if len(nueva & set(json.loads(r[0] or "[]"))) * 2 >= len(nueva):
            return True
    return False


def proponer(c, guardar=True, datos=None, maximo=MAX_PROPUESTAS):
    """→ dict: estado ('apagada', 'hecho'), propuestas (ids) o propondria (textos si guardar=False)."""
    datos = Path(datos or almacen.RAIZ)
    if (datos / "reflexion.apagada").exists() or (datos / "habilidades.apagada").exists():
        return {"estado": "apagada"}
    import hechos
    escudo = hechos._escudo()
    propuestas, propondria = [], []
    for texto, ev in candidatas(c, escudo):
        if len(propuestas) + len(propondria) >= maximo:
            break
        if ya_propuesta(c, ev) or any(len(set(ev) & set(p["evidencia"])) * 2 >= len(ev) for p in propondria):
            continue
        if not guardar:
            propondria.append({"texto": texto, "evidencia": ev})
            continue
        try:
            i = lecciones.proponer(c, texto, ev, origen=ORIGEN)
        except ValueError:
            continue
        if i:
            propuestas.append(i)
    return {"estado": "hecho", "propuestas": propuestas, "propondria": propondria}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ver", action="store_true", help="dice qué propondría, sin guardar")
    a = ap.parse_args(argv)
    c = almacen.conectar()
    print(json.dumps(proponer(c, guardar=not a.ver), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
