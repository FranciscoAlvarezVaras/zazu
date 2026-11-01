#!/usr/bin/env python3
"""LLM FALSO del banco de pruebas (gancho HUB_LLM_CMD de entender.py). Nunca llama a nada real.
Lee el JSON de entrada por stdin ({"system","user","model","provider","max_tokens"}), anota la llamada en «llm_calls.jsonl» y contesta
{"ok":true,"text":...} según «llm_cfg.json» (los dos junto a ESTE fichero: las pruebas lo copian a una carpeta propia):
  {"reglas": [{"si": "trozo de la orden en minúsculas", "resp": {…json…} | "texto crudo", "dormir": segundos, "salir": código, "ok": false}], "defecto": …}
La primera regla cuyo «si» esté dentro de la orden (lo que va entre <orden> y </orden>, en minúsculas) gana."""
import json, re, sys, time
from pathlib import Path

aqui = Path(__file__).resolve().parent
entrada = json.load(sys.stdin)
user = entrada.get("user", "")
m = re.search(r"<orden>(.*?)</orden>", user, re.S)
orden = (m.group(1) if m else "").lower()
with open(aqui / "llm_calls.jsonl", "a") as f:
    f.write(json.dumps({"orden": orden, "user": user, "system": entrada.get("system", "")[:60], "model": entrada.get("model"), "provider": entrada.get("provider")}, ensure_ascii=False) + "\n")
try:
    cfg = json.loads((aqui / "llm_cfg.json").read_text())
except (OSError, ValueError):
    cfg = {}
regla = next((r for r in cfg.get("reglas", []) if r["si"] in orden), None) or {"resp": cfg.get("defecto", {"items": [{"tipo": "hermes", "titulo": "x"}]})}
if regla.get("dormir"):
    time.sleep(regla["dormir"])
if regla.get("salir"):
    sys.exit(regla["salir"])
resp = regla["resp"]


def resolver(x):
    """«indice»: "@Boda" → el número de la fila de <eventos>/<tareas> del mensaje cuyo título contiene «Boda» (para pruebas con datos que cambian)."""
    if isinstance(x, dict):
        if isinstance(x.get("indice"), str) and x["indice"].startswith("@"):
            tabla = "eventos" if x.get("tipo") == "evento" else "tareas"
            bloque = (re.search(rf"<{tabla}>(.*?)</{tabla}>", user, re.S) or [None, ""])[1]
            fila = next((l for l in bloque.splitlines() if x["indice"][1:].lower() in l.lower()), "")
            x["indice"] = int(fila.split("|")[0]) if fila else 999
        return {k: resolver(v) for k, v in x.items()}
    return [resolver(v) for v in x] if isinstance(x, list) else x


if not isinstance(resp, str):
    resp = resolver(resp)
print(json.dumps({"ok": regla.get("ok", True), "text": resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False), "usage": {"input_tokens": 100, "output_tokens": 20}}))
