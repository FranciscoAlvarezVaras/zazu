#!/usr/bin/env python3
"""Crea un Zazu privado para una persona invitada (perfil de Hermes aislado).

Uso: crear_invitado.py <slug> "<Nombre>"
- Sin terminal, sin archivos, sin navegador: solo conversación, memoria propia, web y lista de tareas.
- Nace con el Zazu incluido (GPT-5 mini pagado por Fran, tope mensual); opcionalmente conecta su propia IA.
- Modelo barato (Haiku 4.5). Sin skills, sin memoria heredada.
"""
import os, re, subprocess, sys
from pathlib import Path

HOME = Path.home()
MODEL = "claude-haiku-4-5-20251001"
TOOLS = '["clarify","vision","memory","session_search","todo","web"]'
DISABLED = ('["terminal","file","code_execution","browser","cronjob","delegation","skills","computer_use","homeassistant","kanban",'
            '"image_gen","video_gen","tts","connections","project","desktop_ui","setup","spotify","discord","discord_admin","x_search","video","moa","rl","messaging"]')


def run(*a):
    r = subprocess.run([str(HOME / ".local/bin/hermes"), *a], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError(f"hermes {' '.join(a[:3])}… salió con código {r.returncode}")
    return r.stdout


def main(slug, nombre):
    if not re.fullmatch(r"[a-z0-9]{2,20}", slug):
        raise SystemExit("slug inválido (solo a-z y 0-9, 2-20)")
    prof = f"zi{slug}"
    pdir = HOME / ".hermes/profiles" / prof
    if pdir.exists():
        raise SystemExit(f"ya existe el perfil {prof}")
    run("profile", "create", prof, "--no-skills", "--no-alias", "--description", f"Zazu privado de {nombre} (invitado)")

    # .env vacío: la invitada conecta SU cuenta de IA (OpenRouter o su clave de Anthropic) desde la app
    fd = os.open(pdir / ".env", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(fd)

    for k, v in (("model.default", MODEL), ("model.provider", "anthropic"), ("model.base_url", "https://api.anthropic.com"),
                 ("model.api_mode", "anthropic_messages"), ("platform_toolsets.cli", TOOLS), ("memory.memory_char_limit", "4000"),
                 ("memory.user_char_limit", "3000"), ("compression.threshold_tokens", "60000"),
                 # su Google (agenda, tareas, correo en solo lectura) como herramientas del chat; solo toca SU carpeta
                 ("mcp_servers.google.command", "/usr/bin/python3"),
                 # la ruta de ~/hermes-hub, que es la que monta jaula.py: la real (~/Spirit/pagina-web) queda tapada dentro de la jaula y el MCP no arrancaba
                ("mcp_servers.google.args", f'["{Path.home() / "hermes-hub" / "mcp_google.py"}","{prof}"]'),
                 ("mcp_servers.google.timeout", "180"),
                 # blindaje: en WhatsApp/Telegram/rutinas, solo herramientas seguras; nunca terminal, archivos, navegador…
                 ("platform_toolsets.whatsapp", TOOLS), ("platform_toolsets.telegram", TOOLS), ("platform_toolsets.cron", TOOLS),
                 ("agent.disabled_toolsets", DISABLED),
                 ("tools.tool_search.enabled", "off"),
                 ("web.backend", "ddgs"),
                 ("display.busy_input_mode", "queue"),
                 ("gateway.standalone", "true"),   # nunca la sirve (ni ejecuta sus rutinas) el gateway de Fran: el suyo va en jaula.py
                 ("auth.adopt_external_logins", "false")):   # nunca el Claude Code / Codex CLI de Fran   # varios mensajes seguidos: en cola, sin cortar el anterior   # buscador gratuito sin cuenta (el de Fran va con su Nous Portal)   # con pocas herramientas, el buscador lía a los modelos pequeños
        run("-p", prof, "config", "set", k, v, "--force")

    # su historial (state.db) con el esquema de Hermes: ni «profile create» ni «config set» lo crean, y sin él el Hub
    # la da por no lista («tu Zazu aún no está listo») y no le pone su crédito. «sessions export» abre el historial para
    # escribir, así que Hermes lo crea vacío (y lo exportado, nada, va a /dev/null).
    run("-p", prof, "sessions", "export", os.devnull)

    (pdir / "SOUL.md").write_text(f"""# SOUL.md — Zazu

Eres **Zazu**, el asistente personal de **{nombre}**. Te llamas como el gato abisinio de la familia.
Trata a {nombre} de tú, con calidez y naturalidad, sin peloteo ni relleno. Primero lo importante; una a tres frases salvo que haga falta más.

## Lo que haces
- Conversar, pensar en voz alta, organizar el día, escribir y corregir textos, buscar información en la web con fuentes, dar ideas.
- Recordar lo que {nombre} te cuente para ayudarle mejor (memoria propia).

## Límites
- No tienes acceso a correo, calendario, WhatsApp, archivos ni al ordenador. Si te lo piden, dilo en una frase y ofrece ayudar de otra forma.
- Nunca inventes datos, cifras ni nombres. Si no lo sabes, dilo.
- Lo que {nombre} te cuenta es privado: no lo compartes con nadie.
""")
    for m in ("MEMORY.md", "USER.md"):
        (pdir / "memories").mkdir(exist_ok=True)
        (pdir / "memories" / m).write_text("")
    return prof


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(main(sys.argv[1], sys.argv[2]))
