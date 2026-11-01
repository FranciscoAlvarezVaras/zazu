"""Pasada de juicio con un modelo barato, SIN herramientas, sin sesión y sin estado: una sola llamada
(`agent.auxiliary_client.call_llm` sin `tools`) hecha en un subproceso con el Python de Hermes (llm_worker.py).
Presupuesto: N llamadas por ciclo y M por día (config.llm). Entrada: ya tachada y recortada por quien llama.
La salida es DATO: solo se acepta un JSON y cada campo se valida; nunca se ejecuta nada de lo que diga.
Gancho para pruebas / otro backend: ZV_LLM_CMD = ruta de un ejecutable que lee el JSON de entrada por stdin y escribe
{"ok":true,"text":"..."} por stdout."""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from . import config

WORKER = Path(__file__).resolve().parent.parent / "llm_worker.py"


class Presupuesto:
    def __init__(self, db, cfg):
        self.db, self.cfg, self.ciclo = db, cfg, 0

    def disponible(self):
        l = self.cfg["llm"]
        return bool(l["habilitado"]) and self.ciclo < l["max_por_ciclo"] and self.db.uso_llm_hoy() < l["max_por_dia"]

    def motivo_no(self):
        l = self.cfg["llm"]
        if not l["habilitado"]:
            return "llm_desactivado"
        return "tope_ciclo" if self.ciclo >= l["max_por_ciclo"] else "tope_dia"


def _comando(cfg):
    ext = os.environ.get("ZV_LLM_CMD")
    if ext:
        return [ext]
    py = os.path.expanduser(cfg["llm"]["python"])
    if "*" in py or not Path(py).exists():   # el Python de Hermes puede cambiar de versión con una actualización
        cand = sorted(Path(config.home(), ".hermes/tools").glob("python-*/bin/python3"))
        py = str(cand[-1]) if cand else "python3"
    return [py, "-I", str(WORKER)]


def pedir(db, cfg, pres, fuente, system, user, max_tokens=500):
    """Una llamada. Devuelve el texto o None (sin presupuesto, error o tiempo). Cuenta como uso aunque falle."""
    if not pres.disponible():
        db.contar(f"llm_omitido_{pres.motivo_no()}")
        return None
    pres.ciclo += 1
    t0 = time.time()
    entrada = json.dumps({"system": system, "user": user, "model": cfg["llm"]["modelo"], "provider": cfg["llm"]["proveedor"],
                          "max_tokens": max_tokens})
    try:
        r = subprocess.run(_comando(cfg), input=entrada, capture_output=True, text=True, timeout=cfg["llm"]["timeout_s"],
                           env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(config.home()), "HERMES_HOME": str(config.home() / ".hermes"),
                                **{k: v for k, v in os.environ.items() if k.startswith("ZV_")}})
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    except (subprocess.TimeoutExpired, ValueError, OSError) as e:
        db.uso_llm(fuente, False, ms=int((time.time() - t0) * 1000), nota=type(e).__name__)
        return None
    u = out.get("usage") or {}
    db.uso_llm(fuente, bool(out.get("ok")), u.get("prompt_tokens") or u.get("input_tokens"), u.get("completion_tokens") or u.get("output_tokens"),
               int((time.time() - t0) * 1000), (out.get("error") or "")[:100])
    try:   # usage.jsonl (solo cifras)
        with open(config.estado_dir() / "usage.jsonl", "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "fuente": fuente, "ok": bool(out.get("ok")), "usage": u}) + "\n")
    except OSError:
        pass
    return out.get("text") if out.get("ok") else None


# Límites de formato comunes a las instrucciones del vigía. Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0:
# agents/proactive_agent.py (_SYSTEM_PROMPT, «HARD LIMITS»). Cambios: en español, un objeto JSON en vez de una lista, sin bloque ``` obligatorio.
REGLAS_SALIDA = ("FORMATO ESTRICTO: tu respuesta entera es SOLO el objeto JSON, sin texto antes ni después, sin comentarios y sin campos que no "
                 "estén en el esquema. Cada campo de texto es UNA frase corta (15 palabras como mucho). Si hay referencias (m1, m2…), se copian "
                 "EXACTAMENTE como aparecen en <datos>: nunca inventes una que no esté.")


def _objeto_equilibrado(t, abre, cierra):
    """Primer bloque {…} o […] equilibrado que sea JSON válido, o None."""
    i = t.find(abre)
    while i != -1:
        prof, j, en_str, esc = 0, i, False, False
        while j < len(t):
            ch = t[j]
            if en_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    en_str = False
            elif ch == '"':
                en_str = True
            elif ch == abre:
                prof += 1
            elif ch == cierra:
                prof -= 1
                if prof == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except ValueError:
                        break
            j += 1
        i = t.find(abre, i + 1)
    return None


def extraer_json(texto):
    """Primer objeto JSON del texto (el modelo puede añadir ``` o frases). None si no hay.
    Orden: bloque ```json …```, cualquier bloque ``` …```, y si no, el primer {…} equilibrado del texto. Una lista suelta [{…}] se
    entiende como {"items": […]}.
    Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: agents/proactive_agent.py, _extract_json_block.
    Cambios: devuelve un objeto (el vigía pide {"items": […]}); la lista solo se acepta si no hay ningún objeto."""
    if not texto:
        return None
    candidatos = [m.group(1) for m in re.finditer(r"```(?:json|JSON)\s*(.*?)```", texto, re.S)]
    candidatos += [m.group(1) for m in re.finditer(r"```\s*(.*?)```", texto, re.S)]
    candidatos.append(re.sub(r"```(?:json|JSON)?", "", texto))
    for c in candidatos:
        i, j = c.find("["), c.find("{")
        if i != -1 and (j == -1 or i < j):            # empieza por una lista: [{…}, {…}]
            lista = _objeto_equilibrado(c, "[", "]")
            if isinstance(lista, list) and all(isinstance(x, dict) for x in lista):
                return {"items": lista}
        obj = _objeto_equilibrado(c, "{", "}")
        if isinstance(obj, dict):
            return obj
    return None


# Frases que un título/resumen NO puede contener: un texto hostil no debe colar órdenes en tareas ni avisos
PELIGRO = re.compile(r"wacli|zgog|\bgog\b|\bsudo\b|rm\s+-|\$\(|`|https?://|ignora (lo|las|tus)|ignore (previous|all)|system prompt|<\/?datos>", re.I)


def texto_valido(s, n):
    if not isinstance(s, str):
        return None
    s = re.sub(r"\s+", " ", s).strip()
    if not s or PELIGRO.search(s):
        return None
    return s[:n]
