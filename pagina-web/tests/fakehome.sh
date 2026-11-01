#!/usr/bin/env bash
# Casa FALSA para probar el Hub sin tocar ~/.hermes ni mandar nada de verdad (plan §8.1).
# Uso: tests/fakehome.sh <directorio bajo /tmp>   (se borra y se crea de nuevo)
#   .hermes/state.db y .hermes/profiles/{tecnico,zitest}/state.db  (esquema real de sessions, messages, session_model_usage)
#   .hermes/profiles/tecnico/.env      API_SERVER_KEY falsa
#   .hermes/auth.json                  credential_pool falso (solo nombres de proveedor, sin valores)
#   .config/hermes-hub/{users.json (una invitada), auth.json (session_key de prueba)}
#   .local/bin/{gog,zv}                gog y zv FALSOS (tests/fakegog.py, fakezv.py); datos en gogdata/, avisos.db en .local/state/zazu-vigia
#   Cerebro/                           bóveda de pruebas (SCHEMA, Proyectos, Candidaturas, Ideas, enlaces simbólicos) — tests/fake_zazu.py
#   .local/bin/hermes                  GUARDIA: «send» → sent.log y sale 0; «chat» → emisor stream-json falso;
#                                      cualquier otra cosa sale 97: NUNCA ejecuta el hermes real (con un HOME falso, su arranque
#                                      reescribe los lanzadores REALES de ~/.hermes/hermes-agent/.hermes/bin con rutas de la casa falsa)
set -euo pipefail
FH="${1:?uso: fakehome.sh <directorio bajo /tmp>}"
FH="$(realpath -m "$FH")"
case "$FH" in /tmp/?*) ;; *) echo "fakehome: solo bajo /tmp (me diste $FH)" >&2; exit 2 ;; esac
AQUI="$(cd "$(dirname "$0")" && pwd)"

rm -rf "$FH"
mkdir -p "$FH/.hermes/profiles/tecnico" "$FH/.hermes/profiles/zitest" "$FH/.config/hermes-hub" "$FH/.local/bin" \
         "$FH/Cerebro/40 Compartido" "$FH/Cerebro/10 Bandeja" "$FH/static"
chmod 700 "$FH/.hermes" "$FH/.config/hermes-hub"

python3 - "$FH" <<'EOF'
import json, secrets, sqlite3, sys
from pathlib import Path
fh = Path(sys.argv[1])
ESQUEMA = """
CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL, user_id TEXT, session_key TEXT, chat_id TEXT, chat_type TEXT,
  thread_id TEXT, display_name TEXT, model TEXT, parent_session_id TEXT, started_at REAL NOT NULL, ended_at REAL, end_reason TEXT,
  message_count INTEGER DEFAULT 0, tool_call_count INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
  cache_read_tokens INTEGER DEFAULT 0, cache_write_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
  billing_provider TEXT, estimated_cost_usd REAL, actual_cost_usd REAL, title TEXT, last_activity_at REAL, api_call_count INTEGER DEFAULT 0,
  handoff_state TEXT, handoff_platform TEXT, handoff_error TEXT, profile_name TEXT,
  archived INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL,
  content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, timestamp REAL NOT NULL, token_count INTEGER, finish_reason TEXT,
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE session_model_usage (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, model TEXT NOT NULL,
  billing_provider TEXT NOT NULL DEFAULT '', billing_base_url TEXT NOT NULL DEFAULT '', billing_mode TEXT NOT NULL DEFAULT '',
  task TEXT NOT NULL DEFAULT '', api_call_count INTEGER NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, cache_read_tokens INTEGER NOT NULL DEFAULT 0, cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens INTEGER NOT NULL DEFAULT 0, estimated_cost_usd REAL NOT NULL DEFAULT 0, actual_cost_usd REAL NOT NULL DEFAULT 0,
  cost_status TEXT, cost_source TEXT, first_seen REAL, last_seen REAL,
  PRIMARY KEY (session_id, model, billing_provider, billing_base_url, billing_mode, task));
"""
for d in (fh / ".hermes", fh / ".hermes/profiles/tecnico", fh / ".hermes/profiles/zitest"):
    c = sqlite3.connect(d / "state.db"); c.executescript(ESQUEMA); c.commit(); c.close()
# una conversación de Zazu ya hecha, para que /api/sessions tenga de los dos modos
c = sqlite3.connect(fh / ".hermes/state.db")
c.execute("insert into sessions (id, source, started_at, title, message_count, last_activity_at) values ('zazu_previa','cli',1,'Charla previa',2,2)")
c.execute("insert into messages (session_id, role, content, timestamp) values ('zazu_previa','user','hola',1), ('zazu_previa','assistant','¡Hola, Fran!',2)")
c.commit(); c.close()

def secreto(p, texto):
    p.write_text(texto); p.chmod(0o600)
secreto(fh / ".hermes/.env", f"API_SERVER_KEY=falsa-raiz-{secrets.token_hex(8)}\n")
secreto(fh / ".hermes/profiles/tecnico/.env", f"API_SERVER_KEY=falsa-tecnico-{secrets.token_hex(8)}\n")
# solo nombres de proveedor (gemini falta a propósito: sale «no disponible»)
secreto(fh / ".hermes/auth.json", json.dumps({"version": 1, "credential_pool": {"anthropic": [], "openai-codex": [], "openai-api": []}}))
secreto(fh / ".config/hermes-hub/auth.json", json.dumps({"session_key": secrets.token_hex(32)}))
secreto(fh / ".config/hermes-hub/users.json", json.dumps({"invitada@example.com": {"name": "Invi", "role": "guest", "profile": "zitest",
                                                                                     "onboarded": True, "ai": {"provider": "chatgpt", "model": "gpt-5.5"}}}))
(fh / "static/index.html").write_text("<!doctype html><title>HolaZazu (pruebas)</title>")
EOF

cat > "$FH/.local/bin/hermes" <<EOF
#!/usr/bin/env bash
# hermes FALSO del banco de pruebas del Hub: nunca manda nada de verdad ni toca el ~/.hermes real.
FH='$FH'
EOF
cat >> "$FH/.local/bin/hermes" <<'EOF'
args=("$@"); i=0
while [ $i -lt ${#args[@]} ]; do
  case "${args[$i]}" in -p|--profile) i=$((i+2)) ;; -*) i=$((i+1)) ;; *) break ;; esac
done
sub="${args[$i]:-}"
if [ "$sub" = "send" ]; then
  printf '%s\t%s\n' "$(date +%s)" "$(printf '%q ' "$@")" >> "$FH/sent.log"
  exit 0
fi
if [ "$sub" = "chat" ]; then
  exec python3 "$FH/.local/bin/fake_chat.py" "$@"
fi
echo "hermes falso: «$sub» bloqueado (el hermes real nunca se ejecuta con una casa falsa)" >&2
exit 97
EOF
chmod 755 "$FH/.local/bin/hermes"
install -m 755 "$AQUI/fake_chat.py" "$FH/.local/bin/fake_chat.py"
# Panel de Zazu: gog y zv FALSOS, bóveda del Cerebro, avisos.db del vigía y datos de Google inventados (nada real)
install -m 755 "$AQUI/fakegog.py" "$FH/.local/bin/gog"
install -m 755 "$AQUI/fakezv.py" "$FH/.local/bin/zv"
HOME="$FH" python3 "$AQUI/fake_zazu.py" "$FH"
# el SOUL de la invitada de pruebas, con la plantilla de hoy (vigilante_errores.py rehace los que no llevan server.SOUL_MARCAS)
HOME="$FH" python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import server
(server.prof_dir("zitest") / "SOUL.md").write_text(server.soul_invitada("Invi", "Zazu", "cercano", "cortas", True))' "$AQUI/.."
echo "casa falsa lista en $FH"
