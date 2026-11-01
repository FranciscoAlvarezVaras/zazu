#!/usr/bin/env python3
"""Hook espía para la casa de pruebas: apunta qué perfil disparó cada pre_tool_call y no decide nada.

Va el primero en hooks.pre_tool_call de la raíz de pruebas (instalar.sh lo copia a los perfiles como el resto del bloque),
así se ve que el hook de verdad corre también en tecnico, escritor, investigador… Uso: espia.py <registro.jsonl>
"""
import json, sys, time

try:
    d = json.load(sys.stdin)
    entrada = d.get("tool_input") or {}
    with open(sys.argv[1], "a") as f:
        f.write(json.dumps({"t": time.time(), "profile": d.get("profile"), "tool_name": d.get("tool_name"),
                            "session_id": d.get("session_id"),
                            "command": str(entrada.get("command") or "")[:200] if isinstance(entrada, dict) else ""},
                           ensure_ascii=False) + "\n")
except Exception:
    pass
