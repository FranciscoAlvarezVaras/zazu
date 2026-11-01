# Parches de seguridad del núcleo de Hermes (Modo Hermes)

El gateway de Hermes lanza procesos hijos de larga vida que heredan **todo** su entorno, con las claves dentro
(`API_SERVER_KEY`, `SUDO_PASSWORD`, claves de proveedores…). Su `/proc/<pid>/environ` lo puede leer cualquier
proceso del mismo usuario (incluido el agente), así que las claves que Fran protege tras una aprobación se podían
leer en una línea. Afectaba a dos hijos:

- `scripts/whatsapp-bridge/bridge.js` — lo lanza `plugins/platforms/whatsapp/adapter.py::_bridge_env`.
- `tools/mcp_death_supervisor.py` — lo lanza `tools/mcp_tool.py::_spawn_death_supervisor`.

(Los servidores MCP stdio, p.ej. `mcp_google.py`, ya salían con el entorno saneado.)

Estos ficheros son del **núcleo** de Hermes, que `hermes update` sobreescribe. Por eso el parche vive aquí como un
parcheador idempotente, no como un cambio en el árbol:

- `aplicar.py` — aplica los parches. Idempotente (si ya está, no toca). Guardado por **contexto exacto**: si el
  upstream cambió el código, lo salta y lo registra, nunca corrompe. Valida `ast.parse` antes de reemplazar y deja
  `.bak-fix2` la primera vez. `--comprobar` solo dice qué haría.
- `comprobar.sh` — atajo de solo-lectura (`aplicar.py --comprobar`).

## Uso

```
ops/parches-hermes/aplicar.py                 # aplica al árbol de ~/.hermes/hermes-agent
ops/parches-hermes/aplicar.py --comprobar     # solo mira
ops/parches-hermes/aplicar.py --arbol DIR     # otro árbol (p.ej. una copia de pruebas)
```

La última línea es estable para scripts: `RESULTADO aplicados=N ya=M saltados=K errores=E`.

## Nocturno

`~/.hermes/scripts/actualizar-hermes.sh` lo llama tras cada `hermes update` y, si aplicó algo, reinicia el gateway
para recogerlo. Lo apunta en la línea del log de actualizaciones del cerebro.

## Tras aplicar

Hay que **reiniciar el gateway** (lo hace la sesión principal, no este parcheador) para que los hijos se relancen
sin las claves. Comprobación: ver que `bridge.js` y el supervisor ya no tienen nombres de claves en su entorno:

```
for p in $(pgrep -f 'whatsapp-bridge/bridge.js') $(pgrep -f mcp_death_supervisor.py); do
  tr '\0' '\n' < /proc/$p/environ | grep -cE 'API_SERVER_KEY|SUDO_PASSWORD|OPENAI_API_KEY'   # debe dar 0
done
```
