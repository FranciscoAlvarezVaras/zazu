# Zazu y Hermes se fusionan: Zazu

Rama `fusion`. Antes había dos agentes en la app (Zazu y, con la píldora de modo, «Modo Hermes»). Ahora hay **uno solo, Zazu**, y **un solo chat**.

- **Zazu** es el nombre que ve Fran. «Zazu» es el gato de Fran (y el nombre por defecto del asistente de cada invitada). «Hermes» es el motor interno: no se ve.
- El chat de Fran usa siempre la ruta que antes se llamaba «Modo Hermes»: perfil `tecnico` por el `api_server` del gateway (`pasarela.py`, `/api/hermes/aprobar`…). Es la única donde las tarjetas de permiso funcionan dentro de la app. Los permisos salen en el mismo chat donde Fran está.
- Las cuentas **invitadas (zi\*) no cambian**: su pantalla, su asistente y su nombre (`asistente` de `/api/me`, por defecto «Zazu») son los de siempre. Cada cambio del front comprueba el rol (`guest`).

## Qué ve Fran

| Antes | Ahora |
|---|---|
| Píldora «Zazu ↔ Hermes» (cabecera y menú) y botón «Abrir Hermes» | Fuera. Un solo agente |
| Pestañas Mi día · Tableros · Zazu | Mi día · **Chat** · Tableros · **Zazu** (la pestaña de avisos y vigías) |
| Wordmark «Z · Zazu», `<title>`, manifest | «B · Zazu» (`<title>Zazu</title>`, `name` y `short_name` «Zazu») |
| «Eso es cosa de Hermes», «Abrir en Hermes», «Pedirle a Hermes que lo mire» | «Eso mejor lo hablamos en el chat», «Abrir en el chat», «Pedirle a Zazu que lo mire» |
| «Zazu ha apuntado de tus chats», «Zazu la procesa»… | «Zazu ha apuntado de tus chats», «Zazu la procesa»… |
| Chat de Hermes con piel oscura propia | El chat usa los colores de la app (claro/oscuro del panel); la tarjeta «Zazu necesita tu permiso» también |
| Perfiles Charla / Escritor / Investigador en la píldora | **Ajustes › Estilos de Zazu**: cada fila abre una conversación nueva en ese estilo. El chat normal ya lo tiene todo |

### Enlaces antiguos (siguen funcionando)

- `?tab=hermes`, `?tab=chat` y `?nuevo=1` → el chat de Zazu (conversación nueva). `?tab=chat&conv=…&pf=…` abre esa conversación (de cualquier perfil).
- `?tab=zazu` → la pestaña de avisos y vigías (el id interno de la pestaña no cambia). `?tab=byte` hace lo mismo.
- `?tab=chat&perfil=charla` (o escritor, investigador) → chat nuevo en ese estilo. `?nuevo=1&perfil=…` igual.
- Una invitada que abra `?tab=chat`, `?tab=hermes`, `?tab=zazu` o `?tab=byte` va a su inicio, como siempre.

### El chat

- Todo lo que abre una conversación (`ask()`): la barra de «Mi día» («Abrir en el chat»), las tarjetas de inicio, «Resumir con Zazu» (Correo y WhatsApp), «Preguntar a Zazu» (Carpetas), «Pedirle a Zazu que lo mire» (tras subir un archivo), el menú «+»… manda al perfil `tecnico`. Un estilo (Charla…) solo se usa si Fran lo elige.
- Compartir › Zazu (texto o enlace desde otra app) abre el chat con lo compartido ya escrito en el cuadro de escribir (antes, en el inicio de Zazu). Una invitada, igual que antes.
- Barra de arriba: título · chip de modelo (solo en el chat con permisos) · «Conversaciones anteriores» · «Nueva».
- «Conversaciones anteriores» es **una sola lista** con las de todos los perfiles (las nuevas de Zazu y las de antes), con buscador.
- Una conversación de antes (perfil `default`, de un solo disparo) avisa de que no puede pedir permisos y ofrece «Nueva». «Seguir en WhatsApp» queda solo para esas.

## Contrato de la API

No cambia ninguna ruta, campo ni id. Cambia esto:

- **`GET /api/me`**: `asistente` de Fran vale `"Zazu"` (antes `"Zazu"`). El de una invitada, el que haya puesto.
- **`POST /api/send` con `profile: "tecnico"`** ahora entiende también `ctx` (los datos de una acción rápida: `manana`, `correo`, `agenda`, `wa:…`, `hilo:…`) y la frase «Apunta en mis notas: …» (se resuelve sin IA y devuelve `{"job": null, "nota": …}`). Antes solo lo hacía la ruta antigua; al ser el chat único de Fran, tenía que valer aquí. El bloque de datos va delante del mensaje (igual que en la ruta antigua) y la app no lo enseña.
- **Textos** (no son campos): `fuera_de_ambito` → `mensaje: "Eso mejor lo hablamos en el chat"` (`abrir: "hermes"` queda como nombre interno del campo); avisos de la barra de órdenes y destinos («Zazu la procesa», «Zazu la pasa a Ideas»…); errores del chat («Zazu no responde», «El chat con Zazu no está activado en el servidor», «Zazu se reinició; vuelve a enviarlo»); push «Zazu necesita tu permiso»; textos del vigilante (`vigilante.py`).
- La barra de órdenes entiende también «Zazu, …» / «Oye Zazu, …» (además de «Zazu, …») delante de la frase.
- El hook de aprobaciones, la pasarela y la guardia **no se tocan**.

## Marca e iconos

- `web/scripts/generar-iconos.py` (se puede volver a ejecutar: `/usr/bin/python3 web/scripts/generar-iconos.py`): «B» crema `#f3f2ee` en Instrument Serif (la fuente de los títulos de la app, la de `@fontsource`; si no está, DejaVu Serif Bold) sobre azul marino `#203b73`, esquinas redondeadas. Escribe `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (a sangre, letra dentro del 80 % de seguridad), `apple-touch-icon.png` (180, a sangre: iOS pone las esquinas) e `icon.svg` (favicon; la «B» va como trazado, sin depender de fuentes).
- Las notificaciones push usan `/icon-192.png` (icono y badge, `sw.js`).
- `manifest.json`: `name`/`short_name` «Zazu»; el acceso directo «Hermes» pasa a «Chat con Zazu»; `theme_color`/`background_color` `#f3f2ee` (el fondo del panel).
- `sw.js`: `const V='hub-v12'` (el siguiente al hub-v11 de main) para que el móvil recargue cabecera, iconos y manifest.
- **Falta compilar**: `dist/` de esta rama es el de main (hub-v11); al integrar hay que compilar la web (`npx vite build`) para que se vea todo esto.
- **Nota para invitadas**: manifest e iconos son los mismos para todos (se sirven sin sesión). Una invitada que instale la app la verá con el nombre «Zazu» y la «B» en el icono; dentro, su pantalla es la de siempre.

## Cómo probarlo

```
python3 -m unittest discover -s tests -q          # 156 pruebas (con las de main)
cd web && npx tsc --noEmit && node scripts/contraste-panel.mjs
```

A mano: compilar a una carpeta de prueba (`npx vite build --outDir /tmp/dist-prueba`) y servir una copia del hub sobre una casa falsa (`HUB_STATIC=/tmp/dist-prueba`, `HUB_GATEWAY_URL` apuntando a `tests/fake_gateway.py`). Comprobar: Mi día, Chat, Zazu y Ajustes en 375×812 y 1280×800 (claro y oscuro); «PERMISO: ejecuta sudo -n true» saca la tarjeta «Zazu necesita tu permiso» dentro del chat; los enlaces antiguos; y que una cuenta invitada se ve igual que antes.
