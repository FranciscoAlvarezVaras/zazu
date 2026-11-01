# Inventario: dónde vive cada pieza

Leyenda: **AQUÍ** = el archivo real está dentro de Spirit y el sitio antiguo es un enlace. **ENLACE** = Spirit solo muestra un acceso directo; lo real está fuera por una razón. **FUERA** = no está ni enlazado a propósito.

## Código tuyo (todo AQUÍ)

| Pieza | En Spirit | Sitio antiguo (ahora enlace) |
|---|---|---|
| App HolaZazu | `pagina-web/` | `~/hermes-hub` |
| Puerta de seguridad (hook) | `hermes/agent-hooks/` | `~/.hermes/agent-hooks` |
| Plugin fran-hub (diario) | `hermes/plugins/fran-hub/` | `~/.hermes/plugins/fran-hub` |
| Scripts y rutinas | `zazu/scripts/` | `~/.hermes/scripts` |
| Vigía del correo (zv) | `zazu/vigia/` | `~/.hermes/scripts/zazu-vigia` |
| Bandeja (zb) | `zazu/bandeja/` | `~/.hermes/scripts/zazu-bandeja` |
| Órdenes (`spirit`, `zv`, `zgog`, respaldos) | `servidor/bin/` | `~/.local/bin/<orden>` |
| Servicios y temporizadores | `servidor/unidades/` | `~/.config/systemd/user/<nombre>` |
| Panel de control del servidor | `servidor/panel-servidor/` | `~/Documentos/panel-servidor` |
| Voz | `voz/` | `~/voz` |
| Odysseus (prueba) | `experimentos/odysseus/` | `~/Odysseus` |

## Enlaces a lo que vive fuera (ENLACE)

| En Spirit | Lo real | Por qué fuera |
|---|---|---|
| `hermes/ajustes/config.yaml`, `SOUL.md`, `memories/`, `skills/`, `cron/`, `profiles/`, `plugins/`, `shell-hooks-allowlist.json` | `~/.hermes/…` | Hermes los lee ahí; son datos tuyos o mezcla con lo de Hermes |
| `zazu/skills-de-zazu/` | `~/.hermes/skills/` | Mezcla tus habilidades con las que trae Hermes y se actualizan solas |
| `hermes/motor/` | `~/.hermes/hermes-agent` | Programa de Nous Research (2,9 GB); se actualiza solo. Solo para leer |
| `servidor/servicios/` | `~/Servicios` | Nextcloud, carpeta compartida, Open WebUI, red: 3,7 GB de datos y programas de terceros |
| `servidor/cloudflared/config.yml` | `~/.cloudflared/config.yml` | El túnel lo lee ahí (junto a sus credenciales, que no se copian) |
| `docs/cerebro/` | `~/Cerebro` | Tu archivo personal (Obsidian), sincronizado con el móvil |
| `docs/capturas/`, `docs/diseno/` | `~/Documentos/Capturas-Zazu-nuevo`, `~/Documentos/Diseño-Zazu-Figma` | Material de diseño |
| `hermes/parches/`, `hermes/modo-hermes/` | `pagina-web/ops/…` | Viven en el git de la app |

## Unidades de systemd que NO son enlaces

`hermes-gateway` y `hermes-dashboard` los escribe Hermes al instalarse y actualizarse; se quedan como archivos normales en `~/.config/systemd/user/`. En `servidor/unidades/gestionadas-por-hermes/` hay una copia para mirar. También son normales las de otros programas (`open-webui`, `kdeconnectd`, `cosmic-*`, `syncthing`).

## FUERA a propósito

| Qué | Dónde | Por qué |
|---|---|---|
| Claves y tokens | `~/.hermes/.env`, `~/.hermes/auth.json` | Secretos: nunca en Spirit ni en git |
| Bases de datos y estado (avisos, sesiones, kanban…) | `~/.hermes/*.db`, `~/.hermes/state/`, `~/.local/state/` | Datos |
| Herramientas instaladas (node, pyenv) | `~/.hermes/tools/` | Programas, no código tuyo |
| Binarios (cloudflared, gh, gog, op, wacli, rtk…) | `~/.local/bin/` | Programas de terceros |
| Copias de seguridad | `~/Respaldos/` | Copias |
| Restos de OpenClaw (el asistente anterior) | `~/.hermes/workspace-openclaw/` | No se toca |
| Credenciales del túnel | `~/.cloudflared/` | Secreto |

## Dos git distintos
- `~/Spirit` (git de todo menos `pagina-web`, `panel-servidor` y los programas descargados).
- `~/Spirit/pagina-web` y `~/Spirit/servidor/panel-servidor`: cada uno con su historial.
`spirit guardar "mensaje"` guarda Spirit y pagina-web; el panel se guarda entrando en su carpeta (`git commit`).
