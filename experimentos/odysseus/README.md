# Odysseus (espiga de prueba, 10-oct-2026)

Programa probado: **Odysseus 1.0.3** (https://github.com/odysseus-dev/odysseus, rama `main`, licencia AGPL-3.0). Instalado **solo para evaluar**, aislado y parado.
Informe completo: lo que te dio Claude Code al terminar; resumen en `60 Servidor/mapa.md` del Cerebro.

## Probarlo
1. `systemctl --user start odysseus` (tarda unos 5 s).
2. Abre **http://127.0.0.1:7011** en el navegador **de este PC**. Desde otro equipo: `ssh -L 7011:127.0.0.1:7011 server@server-a8-max` y luego esa misma dirección en tu navegador.
3. Usuario y contraseña: abre el archivo `~/Odysseus/.admin` (sólo tú; permisos 600). `admin` es el administrador; `prueba` es un usuario normal sin permisos peligrosos.
4. La interfaz está en inglés. Ya hay un modelo configurado: «Ollama local (prueba)» (Qwen3 4B, el de este PC; en CPU contesta en unos segundos).
5. Cuando termines: `systemctl --user stop odysseus`.

## Arrancar, parar, mirar
| Qué | Orden |
|---|---|
| Arrancar | `systemctl --user start odysseus` |
| Parar | `systemctl --user stop odysseus` |
| ¿Está encendido? | `systemctl --user is-active odysseus` |
| Registro | `journalctl --user -u odysseus -n 80 --no-pager` |
| Gasto | `systemctl --user show odysseus -p MemoryCurrent -p MemoryPeak` |

No arranca con el PC (la unidad no está habilitada). Límite: 3 GB de memoria; reposo: unos 400 MB y casi 0 % de CPU.

## Dónde está cada cosa
| Ruta | Qué es |
|---|---|
| `src/` | El programa (clon con `git`, rama `main`, 934d23c) |
| `venv/` | Python 3.14 con las dependencias (`requirements.lock` = versiones exactas; hecho con `uv`) |
| `datos/` | **Todo lo que guarda Odysseus**: chats, notas, ajustes, claves cifradas (`.app_key`) |
| `odysseus.env` | Ajustes sin secretos (puerto 7011, solo 127.0.0.1, login obligatorio, red de la jaula) |
| `bin/` | `arrancar.sh` (jaula), `dentro.sh`, `puente.py` (puentes) |
| `run/` | Sockets de los puentes (se crean al arrancar) |
| `pruebas/` | `falso-hermes.py`: Hermes de mentira para probar la conexión sin tocar el de verdad |
| `skill-odysseus/SKILL.md` | Skill para que Hermes lo maneje (sin instalar en `~/.hermes`) |
| `.admin` | Contraseñas (no se imprimen ni se copian) |
| `~/.config/systemd/user/odysseus.service` | La unidad (sin `[Install]`: no se puede habilitar) |

## Cómo está encerrado
- Escucha solo en `127.0.0.1:7011`. Login obligatorio (`AUTH_ENABLED=true`, `LOCALHOST_BYPASS=false`), registro abierto desactivado.
- Corre dentro de **bubblewrap**: ve `/usr` (solo lectura) y `~/Odysseus`. No ve `~/.hermes`, `~/Cerebro`, `~/.config` ni `~/.ssh`; entorno vacío (sin claves).
- La jaula **no tiene red**. Solo salen los puertos de `ODYSSEUS_PUENTES` (ahora solo `11434`, Ollama) por un puente: no llega a internet, a Hermes, al puente de WhatsApp ni a la app.
- Herramientas peligrosas apagadas para el agente (shell, Python, ficheros, MCP, enviar correo, web). El **Terminal de administrador** de Ajustes sigue existiendo: ejecuta en el PC pero dentro de la jaula.
- Sin claves reales, sin correo, sin Google, sin WhatsApp. Nada publicado (ni Cloudflare ni Tailscale).

## Desinstalar
```
systemctl --user stop odysseus
rm ~/.config/systemd/user/odysseus.service && systemctl --user daemon-reload
rm -rf ~/Odysseus
```
Todo vive dentro de `~/Odysseus` (más la unidad). Si quieres conservar los chats, copia antes `~/Odysseus/datos`.

## Llave para Hermes (para que Odysseus sea su herramienta)
1. `systemctl --user start odysseus` y abre http://127.0.0.1:7011 (usuario `admin`, contraseña en `~/Odysseus/.admin`).
2. Ajustes › API tokens (llaves de acceso) › crear una nueva con nombre «Hermes» y SOLO estos permisos: `documents:read`, `documents:write`, `calendar:read`, `calendar:write`. Copia la llave que aparece (solo se muestra una vez).
3. En una terminal: `sh ~/Odysseus/bin/guardar-token.sh`, pega la llave y Enter.
4. Para quitarle el acceso a Hermes: borra la llave en Odysseus (Ajustes › API tokens) y `rm ~/Odysseus/.token-hermes`.
