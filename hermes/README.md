# hermes — el motor del asistente

**Hermes** (de Nous Research) es el programa que piensa, usa herramientas, habla por WhatsApp y programa rutinas. Zazu es la persona que le damos encima. Aquí está lo que tocamos nosotros; el programa en sí NO se edita.

## Qué hay

| Carpeta | Qué es |
|---|---|
| `agent-hooks/movil-aprobacion.py` | **La puerta de seguridad.** Antes de que Zazu haga algo delicado (sudo, borrar, tocar su propia configuración, enviar…), pide tu OK en el móvil. Es la pieza más importante para que no se desmande. |
| `plugins/fran-hub/` | Nuestro único plugin: el **diario compartido** entre superficies (WhatsApp, terminal, dashboard). `~/.hermes/plugins/fran-hub` es un enlace a esta carpeta. Los demás plugins (homeassistant, memory-review, rtk-rewrite) son de terceros y siguen en `~/.hermes/plugins/`. |
| `ajustes/` | Enlaces a los ajustes reales en `~/.hermes/`: `config.yaml` (modelos y herramientas), `SOUL.md` (quién es Zazu), `memories/`, `skills/`, `cron/`, `profiles/`, `shell-hooks-allowlist.json` (consentimiento de los hooks). **No incluye `.env`** (las claves). |
| `motor/` | Enlace al programa Hermes (`~/.hermes/hermes-agent`). Solo para leer. Se actualiza solo con `hermes-actualizar`. |
| `parches/` | Cambios nuestros sobre el motor, por si una actualización los borra (viven en `pagina-web/ops/parches-hermes`). |
| `modo-hermes/` | Pruebas del hook (113 casos). Sirven para comprobar que un cambio en la puerta de seguridad no rompe nada. |

## Órdenes de todos los días

```bash
spirit reiniciar gateway        # tras cambiar config.yaml, SOUL.md o un hook
spirit logs gateway 50
hermes status                   # estado de Hermes
hermes hooks doctor             # ¿los hooks están sanos y con consentimiento?
hermes cron list                # las rutinas programadas
```

## Si editas el hook de seguridad

1. Haz copia: `cp hermes/agent-hooks/movil-aprobacion.py ~/Respaldos/movil-aprobacion.py.antes`
2. Edita `agent-hooks/movil-aprobacion.py`.
3. Comprueba que sigue bien comparando con la copia:
   ```bash
   python3 hermes/modo-hermes/probar_hook.py --viejo ~/Respaldos/movil-aprobacion.py.antes --nuevo hermes/agent-hooks/movil-aprobacion.py
   ```
   (Te dirá en qué casos cambia el comportamiento; revisa que sean los que querías.)
4. Hermes solo ejecuta un hook si has dado tu consentimiento y el archivo no ha cambiado desde entonces. Tras editar hay que **renovarlo** en cada perfil (`default`, `charla`, `escritor`, `investigador`, `tecnico`): se actualiza `script_mtime_at_approval` en cada `shell-hooks-allowlist.json` con la fecha de modificación del hook, y se comprueba con `hermes hooks doctor` (y `hermes -p <perfil> hooks doctor`). Si no sabes cómo, pídeselo a Claude.
5. `systemctl --user reload hermes-gateway` (recarga suave; corta menos que un reinicio).

## El navegador del agente (desde 2026-10-11)

Hermes trae un navegador propio (`agent-browser` + Chromium, en `~/.hermes/tools`; salud: `hermes pm doctor`). Con la configuración actual (`browser.backend` sin fijar) la herramienta se llama **`browser_exec`** y solo aparece en perfiles que tengan los toolsets `browser` **y** `terminal`. Está activado en el perfil `tecnico` (terminal y chat de la app). El hook lo vigila: navegar y leer es libre; rellenar formularios, iniciar sesión, enviar, comprar, subir/bajar archivos o usar el almacén de contraseñas piden tu OK (regla `NAVEGA_ACTUA`). Para activarlo en otro perfil: añadir `- browser` a sus listas de `platform_toolsets` y recargar el gateway.

## Regla de Dos para rutinas
`platform_toolsets.cron: []` en `~/.hermes/config.yaml`: las rutinas con agente no tienen herramientas (leen correo y WhatsApp, que son contenido ajeno). Si algún día una rutina necesita una herramienta, dásela solo a esa rutina (campo `enabled_toolsets` del trabajo), no a todas.

## Perfiles

Hermes tiene varios «Zazu» con distintos permisos: `default` (el tuyo), `charla`, `escritor`, `investigador`, `tecnico`, **`viajes`** (agente de un solo oficio, ver `docs/aprender/primer-agente-viajes.md`) y perfiles de invitados (`zi…`) con menos poder. Viven en `~/.hermes/profiles/`.

## Lo que NO hacer

- No edites `motor/`: se actualiza y perderías el cambio.
- No leas ni copies `~/.hermes/.env`.
- No quites el hook «para probar»: sin él, Zazu no pide permiso.
