#!/usr/bin/env python3
"""Worker de UNA llamada al modelo, sin herramientas ni sesión (spike P0-1).
Se ejecuta con el Python de Hermes (que tiene sus librerías y credenciales):
  ~/.hermes/tools/python-3.14.7+*/bin/python3 -I llm_worker.py < entrada.json > salida.json
Entrada JSON: {"system": str, "user": str, "model": str, "provider": str, "max_tokens": int}
Salida JSON: {"ok": bool, "text": str, "usage": {...}, "error": str}
No pasa `tools` a call_llm: el modelo NO puede ejecutar nada. No toca state.db ni sesiones."""
import json, os, sys

HERMES = os.environ.get("ZV_HERMES_AGENT", "/home/server/.hermes/hermes-agent")


def main():
    req = json.load(sys.stdin)
    os.environ.setdefault("HERMES_HOME", "/home/server/.hermes")
    sys.path.insert(0, HERMES)
    try:
        import hermes_bootstrap  # noqa: F401
        from agent.auxiliary_client import call_llm, extract_content_or_reasoning
        resp = call_llm(provider=req.get("provider") or "anthropic", model=req["model"],
                        messages=[{"role": "system", "content": req.get("system", "")},
                                  {"role": "user", "content": req["user"]}],
                        max_tokens=int(req.get("max_tokens", 300)), temperature=0.2, timeout=45.0)
        text = (extract_content_or_reasoning(resp) or "").strip()
        u = getattr(resp, "usage", None)
        usage = {k: getattr(u, k, None) for k in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens")} if u else {}
        print(json.dumps({"ok": True, "text": text, "usage": usage}))
    except Exception as e:  # nunca imprime claves: solo el tipo y un mensaje corto
        print(json.dumps({"ok": False, "text": "", "error": f"{type(e).__name__}: {str(e)[:200]}"}))


if __name__ == "__main__":
    main()
