# pagina-web — la app HolaZazu

Es lo que ves en `holazazu.app` y en el móvil: Mi día, Tableros, Chat, Carpetas, Ajustes. Tiene **servidor** (Python, sin frameworks) y **pantallas** (React + Vite).

Esta carpeta es un repositorio git propio (`git log` muestra la historia completa). Spirit la guarda tal cual.

## Dónde está cada cosa

| Quiero cambiar… | Toco… |
|---|---|
| Cómo se **ve** la app (textos, colores, pantallas) | `web/src/` |
| Colores y tamaños globales | `web/src/tokens.css`, `theme.css`, `design.css` |
| El chat con Zazu | `web/src/chat/` |
| Mi día / Tableros / Dinero | `web/src/panel/` (cada pantalla es un `.tsx`: `Hoy.tsx`, `Tableros.tsx`, `Dinero.tsx`…) |
| Carpetas (la parte de WhatsApp y archivos) | `web/src/carpetas/` |
| Lo que hace el **servidor** (rutas, login, permisos) | `server.py` |
| El botón «Ordenar todo» | `orden.py` y `entender.py` (usa Haiku) |
| Avisos, registro, gastos | `avisos.py`, `registro.py`, `gastos.py` |
| Ofertas de empleo (lista, ficha, guardar, «no me interesa», pasar a candidaturas) | `ofertas.py` (servidor) y `web/src/panel/Ofertas.tsx` + `ofertas.css`. Diseño en Figma «HolaZazu · Ofertas de empleo (estilo LinkedIn)» |
| Invitados (Nuria y otros) y su jaula de seguridad | `crear_invitado.py`, `jaula.py`, `pasarela.py`, `guardia.py` |
| Contratos entre pantalla y servidor | `web/contrato-*.md` |
| La **web pública** (lo que se ve sin iniciar sesión): portada comercial, `/descargar`, `/novedades` | `publica/` (ver abajo); `/privacidad` y `/terminos` en `legal/` |

## Web pública (`publica/`)

HTML y CSS propios, sin compilar: se leen del disco en cada visita, así que **editar el HTML basta** (sin reiniciar ni `web-construir`).

| Ruta | Archivo | Notas |
|---|---|---|
| `/` sin sesión | `publica/inicio.html` | Inicio: héroe con Zazu como muñeco 3D, «Así se ve» (capturas), tarjetas a cada página y lista de espera (`#lista-espera`, el único formulario). Con sesión, `/` sigue siendo la app. |
| `/funciones` | `publica/funciones.html` | Qué hace (6 tarjetas con su gato), cómo funciona y preguntas frecuentes. |
| `/movil` | `publica/movil.html` | La app de Android 2.0 (en el menú, «App móvil»). |
| `/seguridad` | `publica/seguridad.html` | Por qué es privado. La política legal sigue en `/privacidad`. |
| `/conoce-a-zazu` | `publica/conoce-a-zazu.html` | El logo, las 12 caras de Zazu enteras y la hoja 3D (frente de medio cuerpo, perfil y espalda). |
| `/descargar` | `publica/descargar.html` | Pestañas **Android** (`#android`, guía del APK) y **iPhone, iPad y Mac** (`#apple`, instalar desde Safari como app web). Las pestañas son solo CSS (`:target`); `zazu.js` marca la actual y abre la de Apple en iPhone/iPad/Mac. `{{version}}`, `{{tam}}` y `{{sha256}}` los rellena `server.py` con `zazu.json` (lo deja `app-android/build.sh`). |
| `/novedades` | `publica/novedades.html` | **Para añadir una novedad:** copia un `<article class="novedad">` y pégalo encima del primero (lo nuevo arriba); cambia `id`, `<time datetime>`, etiqueta, título y puntos. Hay un comentario en el HTML con el molde. |
| `/publica/zazu.css`, `/publica/zazu.js`, `/publica/img/*`, `/publica/fonts/*` | estilos, envío de la lista de espera, capturas (webp), gatos, logo, `og.jpg` (1200×630) y fuentes (Inter, Source Serif 4, Cinzel) | css/js: `no-cache`; imágenes y fuentes: 1 día. Si cambias una imagen o el CSS, sube su `?v=N` en los HTML (Cloudflare guarda copias). |
| `/zazu.apk`, `/robots.txt`, `/sitemap.xml` | `server.py` | El APK es público (no lleva datos ni claves). HEAD solo vale en estas rutas públicas. |

**Lista de espera:** `POST /api/lista-espera` (pública), JSON `{email, nombre?, web}` o formulario sin JS (→ 303 a `/#gracias`). `web` es un campo trampa oculto: si llega relleno, responde igual y no guarda. Máx. 2 KB, 10 envíos por IP y hora (además de `guardia.py`); nunca dice si el email ya estaba. Se guarda en `~/.local/state/zazu-web/lista-espera.jsonl` (0600; `{email, nombre, fecha}` por línea, sin IP, sin repetir emails). Solo para avisar del lanzamiento (párrafo en `/privacidad#lista-espera`).

CSP de estas páginas: todo de `'self'` (también `manifest-src`, para poder instalar Zazu desde Safari o Chrome), nada en línea (ni `style=` ni `<script>` dentro del HTML). Pruebas: `tests/test_api.py` › `PaginasPublicas`. **Página nueva:** su `publica/<nombre>.html` y su ruta en `PAGINAS_PUBLICAS` de `server.py` (de ahí salen la ruta, HEAD y el sitemap). Todas comparten la misma cabecera (marca la página actual con `aria-current`; en el móvil, menú «Menú» con `<details>`) y el mismo pie.

**Marca: un solo logo.** El gato del icono (`brand/zazu-logo-nuevo.png`). En la cabecera y el pie de la web pública, en `legal/` y en `/login` va en **pixel art** (`brand/zazu-logo-pixel-{40,80,120,160}.png`: rejilla 40×40, 15 colores, escalado con vecino más cercano; en CSS `image-rendering: pixelated`). En grande (lista de espera, Conoce a Zazu) va el original en alta (`zazu-icono-{150,300,420}.webp`). El logotipo antiguo «Hola Zazu» (`brand/holazazu-logo-2048.jpg`) **no se usa**. El muñeco 3D (`muneco-zazu-*.webp`, recorte de `brand/zazu-3d-referencia.jpg`) y los gatos temáticos (`cara-*`, `retrato-*`, recortados de las hojas de 2400×1792 en claro y oscuro) son ilustraciones, no logos.

`dist/` es la web ya compilada: es lo que se sirve. **Se genera**, no se edita a mano. Está dentro de git a propósito para poder volver atrás.

## Cómo se prueba un cambio

Cambio en `server.py` o en otro `.py`:

```bash
spirit reiniciar web
spirit logs web 30
```

Cambio en `web/src/…` (lo que ves):

```bash
spirit web-construir
```

Eso compila (`npm run build`) y reinicia el hub. La versión (`hub-v` + fecha y hora) **sube sola en cada construcción** (`web/vite.config.ts`). Al abrir la app, antes de enseñar nada, se pregunta a `/api/version`: si el servidor tiene otra, se borran las copias del móvil y se recarga. Vale para el navegador, la web instalada y la app de Android.

Probar sin tocar producción: hay pruebas en `tests/`:

```bash
cd ~/Spirit/pagina-web && python3 -m unittest discover tests 2>&1 | tail -5   # tarda ~1,5 min; debe acabar en OK
```

## Para guardar

```bash
cd ~/Spirit/pagina-web && git status --short     # qué cambió
git diff                                         # ver los cambios
git add -A && git commit -m "qué hice"           # guardar
```

(O `spirit guardar "qué hice"`, que guarda también Spirit.)

## Cómo se entra (22 de octubre de 2026)

- **Por internet (holazazu.app, puerto 8792 tras Cloudflare): solo «Entrar con Google».** El acceso por usuario + contraseña + código TOTP ya no existe ahí: `/login` no lo enseña y `POST /api/login` responde 404. Las sesiones ya abiertas siguen valiendo hasta que caducan (14 días) o se cierran con «Salir».
- **En la app de Android (2.1 o más):** «Entrar con Google» abre Chrome (Custom Tab) con `/oauth/google/start?mode=app&ch=<reto>`. Tras Google, el servidor no deja sesión en Chrome: crea un código de un solo uso (2 min, guardado como hash en `~/.config/hermes-hub/codigos-app.json`, 0600) y manda a `https://holazazu.app/app/entrar?c=<código>`. Ese enlace abre la app (App Link verificado con `verify/assetlinks.json`; si no, la página ofrece `zazu://entrar`). La app lo canjea en su WebView con su secreto (`v`, del que el reto es el sha256): sin el secreto el código no vale, y se quema al primer intento. Los fallos cuentan para el límite de 8 intentos en 15 min por IP. En un navegador, `/app/entrar` sin secreto solo dice «Abre esto en la app» y no gasta el código.
- **«Conectar con Google» en la app (2.5 o más):** la app pide con su sesión `POST /api/google/enlace-app` (billete de un solo uso, 5 min, atado al email de la sesión; hash en `~/.config/hermes-hub/google-app.json`) y abre `/oauth/google/start?mode=connect&t=<billete>` en una Custom Tab. Tras Google no se guarda nada en Chrome: los permisos quedan en espera (2 min) y `/app/entrar?g=<código>` vuelve a la app, que los confirma en `/app/google` **solo con la sesión del mismo email**. Detalle en `app-android/README.md` › 2.5. Pruebas: `tests/test_app_nativa.py`.
- **Avisos en la app (2.5 o más):** cada push (`vigilante.py` › `push()`) queda también en la cola de los móviles con la app (`movil.encolar_aviso`); la app los recoge con su token en `GET /api/movil/avisos` y los confirma en `POST /api/movil/avisos/confirmar`.
- **Si Google falla:** en el propio PC abre **http://127.0.0.1:8790/login** › «Acceso del administrador (solo en el PC)» y entra con usuario, contraseña y TOTP. Esa entrada (8790) es la privada: también llega por Tailscale en `https://server-a8-max.tail45ff64.ts.net:8443`, donde Tailscale ya te identifica sin contraseña. El 8792 es el público y nunca acepta contraseña, aunque se abra desde el PC.

## Visor de registros (24 de octubre de 2026)

- `visor.py` junta los registros de la app (journal de `hermes-hub`), de Zazu (`~/.hermes/logs/agent.log`) y de cada perfil
  (`~/.hermes/profiles/*/logs/agent.log`; `zi…` = invitados) más `errores-invitadas.jsonl`, sin ruido y tachados, en
  `~/.local/state/zazu-web/visor/AAAA-MM-DD.jsonl` (30 días). Solo lee lo nuevo (cursor + posición por archivo).
- `vigilante.py` lo llama cada 5 min, guarda ahí sus avisos y reescribe `../VISOR.md` (resumen de 24 h; está en `.gitignore`).
- `visor_terminal.py` es el comando `visor` (servidor/bin/visor): pantalla completa en vivo con filtros, gráfico, agrupados y detalle.
- Pestaña **Administrador** (solo Fran, capacidad `admin`): `web/src/panel/Administrador.tsx` sobre `GET /api/admin/registros`
  (`?desde=&hasta=&origen=&gravedad=&q=&firma=`; con `&despues=<t>` solo lo nuevo, para el «en vivo») y `/api/admin/registros/cerca?t=&origen=&perfil=`.
- **Explícamelo** (`explicar.py`): Claude Opus 5.5 explica un registro como un profesor (qué pasó, por qué, si es grave, una PISTA y
  palabras nuevas; la solución solo si se pide; dudas con historial). Va por el worker de Hermes (`entender._comando()`, sin herramientas),
  con el registro, lo de 2 min antes y después y el código donde saltó (si el archivo cambió después, la función actual), todo tachado.
  Se guarda por firma (no se paga dos veces) y hay tope de 15 $/mes (4 $ / 20 $ por millón). «Entendido» SOLO se gana aprobando el
  **mini examen** (2 preguntas que pone y corrige Claude; `POST /api/admin/examen` y `/api/admin/examen/corregir`); «Lo he arreglado»
  solo con el examen aprobado. Los dos suben el nivel y se apuntan en `../APRENDIZAJE.md` (en pruebas, `VISOR_APRENDIZAJE`).
  Nada se apunta desde el chat de Claude Code (decisión de Fran, 2026-10-24). Rutas: `GET /api/admin/aprendizaje`, `POST /api/admin/explicar`
  `{t, f, modo, pregunta?, historial?, otra_vez?}` y `POST /api/admin/aprender {t, f, que}` (el registro se busca en el visor por hora y firma).
  En la terminal: `x` explica, `s` solución, `m` mini examen, `r` arreglado. En Claude Code: la skill `/visor` (`.claude/skills/visor`).
- **Cuidado:** visor.py carga `~/.hermes/scripts/privacidad.py` por su ruta; nunca metas `~/.hermes/scripts` en `sys.path` desde el Hub:
  allí hay un `movil.py` que tapa el del Hub (el 2026-10-24 rompió `/api/movil/…` unos minutos).
- Pruebas: `python3 -m unittest tests.test_visor tests.test_explicar -v` (y `tests.test_api` para la pestaña).

## Cuidado

- Otra sesión (Claude) puede estar editando aquí a la vez. Mira `git status` antes de empezar.
- Los datos que usa la web (avisos.db, sesiones, etc.) **no están aquí**; están en `~/.hermes/`.
- Nunca pongas claves en estos archivos.
- `ops/` guarda herramientas de operación (parches de Hermes y pruebas del hook); no son parte de la web.
