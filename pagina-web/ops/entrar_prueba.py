#!/usr/bin/env python3
"""Invitada de PRUEBA de Fran («Fran (prueba)», fran-prueba@holazazu.app) y un enlace de un solo uso (15 min) para entrar como ella.
Uso: python3 ops/entrar_prueba.py            → crea la cuenta si falta y da el enlace
     python3 ops/entrar_prueba.py --borrar   → le quita el acceso (sus datos quedan en el PC hasta que se borren)"""
import hashlib, json, os, secrets, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

EMAIL = "fran-prueba@holazazu.app"


class Shim:
    _credito = staticmethod(server.H._credito)
    def fail(self, code, msg): raise SystemExit(f"No se pudo ({code}): {msg}")
    def send_json(self, obj, code=200): self.out = obj


if "--borrar" in sys.argv:
    server.H.personas_write(Shim(), {"action": "remove", "email": EMAIL}); print("acceso de prueba quitado"); sys.exit()
if EMAIL not in server.users():
    server.H.personas_write(Shim(), {"action": "add", "email": EMAIL, "name": "Fran (prueba)", "nivel": "familia", "credito": 15})
with server.USERS_LOCK:
    us = server.users(); us[EMAIL].update(prueba=True, onboarded=True); server.save_users(us)
server.aplicar_credito(EMAIL)
t = secrets.token_urlsafe(24)
f = server.HOME / ".config/hermes-hub/prueba-tokens.json"
try:
    tok = json.loads(f.read_text())
except (OSError, ValueError):
    tok = {}
tok[hashlib.sha256(t.encode()).hexdigest()] = {"email": EMAIL, "exp": time.time() + 900}
fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.write(fd, json.dumps(tok).encode()); os.close(fd)
print(f"{server.HUB_URL}/entrar-prueba?t={t}")
