# app-android — Zazu como app de Android

Una app mínima que abre la web de HolaZazu (`https://holazazu.app`) a pantalla completa, sin barra de direcciones y **sin copia guardada de la página**: cada vez que se abre baja la versión que hay en el servidor, así que un cambio en la web se ve sin instalar nada. Código en Java sin librerías de terceros (solo el WebView de Android).

## Qué hace y qué no
| Hace | No hace (todavía) |
|---|---|
| Mantiene la sesión, el micrófono y la cámara de la web, subir archivos y descargar | Avisos al instante: los recoge cada 15 min (2.5) |
| Abre en el navegador lo que no es de holazazu.app; entrar y conectar Google van por Chrome (Custom Tab) y vuelven solos | Avisos para las invitadas (ellas usan la web instalada) |
| «Compartir › Zazu» con un texto o enlace | Compartir archivos o fotos hacia Zazu |
| Pantalla «No pude conectar» con Reintentar | Funcionar sin internet |

La web distingue la app por su User-Agent (`ZazuApp/…`): dentro de la app no registra su service worker, quita el que hubiera y no ofrece Google (`web/src/lib.ts` `EN_APP`, `main.tsx`, `login.html`).

## Versión 2.0 (22 de octubre de 2026): archivos, copia al PC y se actualiza sola
Sigue siendo Java sin librerías de terceros (JobScheduler, SQLite, PackageInstaller y HttpURLConnection de Android; nada que bajar con Gradle).

- **Permiso «Acceso a todos los archivos»** (`MANAGE_EXTERNAL_STORAGE`): al abrir, si falta, sale una pantalla nativa que lo explica y lleva a Ajustes. Se concede una vez. «Ahora no» la aparca 3 días.
- **Copia sola al PC** (`Copia.java`, `CopiaJob.java`): cada ~2 h con WiFi (o red sin coste) y batería no baja, y también al abrir la app, recorre WhatsApp (`Android/media/com.whatsapp/WhatsApp/Media/` › Images, Video, Documents, Voice Notes, Audio) y `DCIM/Camera` y sube **solo lo nuevo**: un registro local (`copia.db`: ruta + tamaño + fecha) recuerda lo copiado y antes de subir se pregunta al servidor en lotes de 200 qué le falta (lo que ya trajo el ADB no se vuelve a mandar). Lo más reciente primero. Trozos de 16 MB, y una subida cortada sigue donde se quedó. Cada pasada dura como mucho 8 min; si queda algo, sigue al minuto. Se salta lo oculto (`.Statuses`, `.nomedia`) y lo modificado hace menos de 1 min.
- **Dónde cae en el PC** (`pagina-web/movil.py`): `~/Documentos/Movil-S25/` con la misma ruta que en el móvil, salvo WhatsApp, que va igual que la copia por ADB:
  `Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/x.jpg` → `Movil-S25/WhatsApp/WhatsApp Images/x.jpg`; `DCIM/Camera/y.jpg` → `Movil-S25/DCIM/Camera/y.jpg`. Si ya hay uno con el mismo nombre y tamaño, cuenta como copiado; si el tamaño es otro, el nuevo entra como `x (2).jpg`. Nunca se pisa nada.
- **Cómo se autentica: token de dispositivo.** La primera vez que abres la app con la sesión iniciada, la app pide un token a `POST /api/movil/token` con la sesión del WebView (cookie + `X-Hub`, solo Fran; las invitadas reciben 403) y lo guarda en su almacén privado. El trabajo en segundo plano usa `Authorization: Bearer …`: no caduca a los 14 días como la sesión, no depende del WebView, solo vale para `/api/movil/*` y no puede fabricar otros tokens. El servidor guarda solo su sha256 en `~/.config/hermes-hub/movil.json` (0600, como mucho 5). **Quitar el móvil:** borra su entrada (o el archivo); la app pedirá otro al abrirla con la sesión iniciada.
- **Cloudflare** corta cada petición a 100 MB y espera como mucho 100 s: por eso trozos de 16 MB (el servidor acepta hasta 64 MB por trozo y 4 GB por archivo).
- **Se actualiza sola:** al abrir, `GET /api/movil/apk-version` (va por `/api/`, Cloudflare no lo guarda). Si hay un `versionCode` mayor: «Hay una versión nueva» › Instalar → baja `/api/movil/apk`, comprueba su sha256 y que sea una versión mayor de esta app, y se la da al instalador del sistema. Android pide a Fran confirmar (la primera vez, además, «Permitir de esta fuente» para Zazu). Solo instala encima si va firmada con la misma llave. `build.sh` deja `zazu.json` al lado del APK con la versión leída del propio APK (aapt2), el sha256 y el tamaño.
- **Registro de Zazu:** mantén pulsado el icono › «Registro de Zazu»: permiso, conexión, última copia y todas las peticiones.

## Versión 2.1 (22 de octubre de 2026): entrar con Google

Google no deja hacer OAuth dentro de un WebView (`disallowed_useragent`). «Entrar con Google» abre Chrome en una Custom Tab (sin librerías: el extra de sesión del protocolo de Custom Tabs) con `/oauth/google/start?mode=app&ch=<sha256 de un secreto que guarda la app>`. Al acabar, el servidor manda a `https://holazazu.app/app/entrar?c=<código de un solo uso, 2 min>`, que abre la app por App Link verificado (`autoVerify`; `verify/assetlinks.json` en pagina-web lleva la huella de la llave) o, de respaldo, por `zazu://entrar`. La app carga `/app/entrar?c=…&v=<secreto>` en su WebView y el servidor deja ahí la sesión. Sin el secreto, el código no vale (otra app que capture el enlace no puede usarlo). Comprobar la verificación: `adb shell pm get-app-links app.holazazu.zazu`. Detalle del servidor: README de pagina-web › «Cómo se entra».

## Versión 2.2 (22 de octubre de 2026): arreglos de la revisión
- **Un solo cerrojo de subida** para la copia de fondo y la orden `subir`: dos subidas del mismo archivo a la vez lo dejaban corrupto en el PC. Una subida que no termina tras 1000 vueltas es un error, nunca «copiado».
- **`subir` aprobada va a un trabajo de fondo** (JobScheduler de un solo uso, `JOB_SUBIR`): con WiFi, en pasadas de 8 min que siguen donde iban (se guarda la última ruta tratada, así borrar o añadir archivos entre pasadas no hace saltarse ninguno), aunque el móvil se bloquee. Al terminar, aviso con el resultado (tocarlo abre el Registro). Tras 5 pasadas seguidas que fallan sin avanzar se da por fallida (que Android la pare porque se fue la WiFi no cuenta).
- **Resultado de una petición:** primero se anota en el registro local (la acción ya está hecha) y luego se avisa al servidor. Si el aviso no llega, se guarda y se reenvía en el siguiente sondeo, y el mensaje lo dice. `duplicados` lista como mucho 20 rutas por grupo (`copias` dice cuántas hay) y un resultado de más de ~100 000 caracteres va recortado.
- **Un archivo que cambia mientras se sube** no se marca como copiado: la próxima pasada lo manda entero (en el PC entra como `x (2).ext`).
- Cada trabajo tiene su propio «parar»; abrir o volver a la app ya no reprograma (y con ello para) una pasada en marcha; si la base de datos local no abre, el cerrojo se suelta.
- En Android 8.x ya no se cierra al instalar una actualización (`getLongVersionCode` es de Android 9). `zazu://entrar` solo gasta el secreto del login si trae un código bien formado.

## Versión 2.5 (23 de octubre de 2026): avisos de Zazu y «Conectar con Google»
- **Avisos nativos** (`Avisos.java`, canal «Avisos de Zazu»): el WebView no admite Web Push, así que cada push que manda el servidor (`vigilante.py` › `push()`: recordatorios, rutinas, «Zazu necesita tu permiso», alertas del vigía) se deja también en una cola para cada móvil con la app (`movil.encolar_aviso`, `~/.local/state/zazu-movil/avisos.json`, 0600, por sha256 del token). `para=None` (Fran) va a los tokens que no son de una invitada. La app los recoge con su token (`GET /api/movil/avisos`) al abrirse o volver y cada 15 min (el mismo trabajo que las peticiones, `JOB_SONDEO`, que desde la 2.5 se programa aunque falte el permiso de archivos), los enseña y los confirma (`POST /api/movil/avisos/confirmar`). Tocar uno abre la app en la página del aviso (solo rutas de Zazu; un permiso de Zazu abre su tarjeta con `#aprobar=…`). El canal se crea al primer intento de recoger (sale en Ajustes antes del primer aviso); si las notificaciones de la app **o solo ese canal** están apagadas, no se recogen y esperan en el servidor (no se pierden). Al abrir o volver, los avisos y las peticiones se miran por separado (si fallan unos, se miran las otras) y como mucho una vez cada 20 s (cada diálogo de permisos pasa por `onResume`). Dos toques seguidos en «Conectar con Google» abren una sola pestaña.
  - **Sin duplicados:** mismo tag = sustituye al anterior (en la cola y en la notificación); los ids ya enseñados se recuerdan en el móvil por si la confirmación no llegó. **Tope** 30 por móvil (los más nuevos) y **caducan** en un día, como el web push. Con las notificaciones apagadas no se recogen: esperan en el servidor hasta que se activen (o caduquen).
  - **Sin botones Permitir/Rechazar en el aviso:** los avisos con `aprob` son solo de invitadas (que no tienen token de la app) y los permisos de Zazu para Fran (sudo, etc.) se deciden viendo el comando entero en la tarjeta: tocar el aviso la abre.
  - **Puede tardar hasta ~15 min** (lo mínimo que deja Android a un trabajo periódico; en Samsung, a veces más). Sin servicio en primer plano, por lo mismo que las peticiones.
- **«Conectar con Google» desde la app** (Fran e invitadas; cualquier botón que lleve a `/oauth/google/start?mode=connect`): la app no lo carga en el WebView (Google lo bloquea). Con la sesión del WebView pide `POST /api/google/enlace-app` → un **billete de un solo uso** (5 min, atado al email de la sesión; solo se guarda su hash en `~/.config/hermes-hub/google-app.json`) y abre `/oauth/google/start?mode=connect&t=<billete>` en una Custom Tab. El billete va al state firmado (`a=1`). A la vuelta, el servidor **no guarda nada en Chrome**: deja los permisos en espera con otro código de un solo uso (2 min) y manda a `/app/entrar?g=<código>` (el mismo App Link del login; si no abre la app, una página con `zazu://entrar?g=…`). La app carga `/app/google?g=…` en su WebView y **solo con la sesión del mismo email** se guardan en gog; luego enseña «Cuenta de Google conectada». Si algo falla, `/app/entrar?e=<motivo>` (lista cerrada) vuelve a la app, que lo cuenta. Así un enlace ajeno abierto por otra persona no mete su Google en tu cuenta.
- **Notificaciones: ya no se piden nada más abrir** (antes del login y de la guía). Las pide la guía de bienvenida o «Tus permisos» con el puente; pedirlas dos veces seguidas hacía que, con dos «no», Android las bloqueara para siempre.
- **Vuelta de Google o de un enlace sin recargar dos veces:** `onNewIntent` pone `pausadoEn = 0` tras cargar la URL, así `onResume` no vuelve a pedir el mismo código de un solo uso (`/app/google?g=…`, `/app/entrar?c=…`). En la debug (`RECARGA_MS` = 8 s) pasaba casi siempre.

## Peticiones de Zazu
Zazu puede pedir al móvil tareas de **archivos**, y **cada una la aprueba Fran en el móvil** antes de que se haga: la app enseña «Zazu quiere: <qué> — <motivo>» con **Permitir** y **Rechazar**. Sin pulsar Permitir no se hace nada; sin respuesta en 15 min, la petición caduca.

- **Tipos (lista fija, sin comandos ni shell):** `listar`, `tamanos`, `duplicados`, `info`, `crear_carpeta`, `mover` (a una carpeta; nunca pisa), `papelera` y `subir`. Rutas siempre bajo `/storage/emulated/0`, sin `..`, comprobadas con la ruta canónica y nunca `Android/data` ni `Android/obb`. **Nunca se borra nada:** `papelera` mueve a `/sdcard/.ZazuPapelera/<fecha>/`, de donde se recupera a mano.
- **Desde el PC** (`zazu/scripts/movil-app.py`, escribe en la misma cola que el Hub, `~/.local/state/zazu-movil/peticiones.jsonl`):
  ```bash
  movil-app.py listar /sdcard/Download --motivo "Fran pidió ver Descargas" --esperar 300
  movil-app.py tamanos /sdcard --motivo "qué ocupa más" --esperar 300
  movil-app.py duplicados /sdcard/DCIM --motivo "fotos repetidas" --esperar 600
  movil-app.py mover /sdcard/Download/factura.pdf /sdcard/Documents/Facturas --motivo "ordenar facturas"
  movil-app.py papelera /sdcard/Download/viejo.apk --motivo "limpiar Descargas"
  movil-app.py subir /sdcard/Documents/Facturas --motivo "copia en casa"
  movil-app.py estado <id>
  ```
  Sale la petición en JSON (con `resultado` cuando está hecha). Código 0 hecha, 1 rechazada/error/caducada, 2 aún pendiente.
- **En el servidor:** `POST /api/movil/peticion` (Fran con sesión; el móvil no puede crearlas), `GET /api/movil/peticiones` (la app recoge las pendientes), `GET /api/movil/peticiones/<id>`, `POST /api/movil/peticiones/<id>/resultado` (solo `pendiente → aprobada|rechazada → hecha|error`; lo caducado o ya respondido da 409).
- **En el móvil:** al pulsar Permitir la app avisa «aprobada»; si el servidor dice que ya caducó, no hace nada. Hace exactamente lo que se enseñó en el diálogo (`subir`, en segundo plano con WiFi; ver 2.2). Al tocar un aviso, la app vuelve a leer la petición del servidor (del aviso solo usa el id), así otra app no puede colar argumentos.
- **Cuándo las ve:** al abrir o volver a la app (diálogo) y con un trabajo cada 15 min (lo mínimo que deja Android) que avisa con una notificación; tocarla abre el diálogo. **No hay servicio en primer plano «Zazu conectado»** en esta versión: en Android 15 los de tipo `dataSync` tienen un tope de 6 h al día, el tipo `specialUse` pide justificarlo si algún día va a Play, y en Samsung además hay que sacar la app de la optimización de batería. Con el trabajo de 15 min, en Samsung el aviso puede llegar tarde (Android agrupa los trabajos) y alguna petición caducar: si pasa a menudo, es lo primero para la v2.

## Fabricarla
```bash
~/Spirit/app-android/build.sh            # versión real, firmada (APK) → ~/.local/share/zazu-android/zazu.apk (instalar a mano)
~/Spirit/app-android/build.sh aab        # Android App Bundle firmado → ~/.local/share/zazu-android/zazu.aab (subir a Google Play)
~/Spirit/app-android/build.sh debug      # de pruebas: habla con http://localhost:8931 (móvil por USB + `adb reverse tcp:8931 tcp:8931` hacia un Hub de pruebas)
```
El Hub ofrece el APK en `https://holazazu.app/zazu.apk` (público desde el 22-10-2026, con la guía de instalación en `https://holazazu.app/descargar`) y en Tu espacio › App de Android. El APK y el AAB se firman con la **misma llave** (`~/.config/zazu-app`), así que ambos valen para actualizar encima.

**Subir a Google Play:** ver [`PLAY-STORE.md`](PLAY-STORE.md) (guía en pasos para Fran). La valoración TWA vs WebView y cómo sería migrar está en [`twa-idea.md`](twa-idea.md).

**Herramientas** (de tu usuario, no del sistema): `~/.local/share/zazu-android/` con Java 17 (Temurin), Gradle 8.7 y el kit de Android (plataforma 34 y herramientas de compilación). Se bajaron de las fuentes oficiales y se comprobaron sus huellas. `source ~/.local/share/zazu-android/env.sh` las pone en el PATH.

**Llave de firma:** `~/.config/zazu-app/` (creada la primera vez; entra en la copia diaria cifrada). Si se pierde, el móvil no deja actualizar encima y habría que desinstalar y volver a instalar. Para subir de versión: `versionCode` y `versionName` en `app/build.gradle`.

## Qué está comprobado (19 de octubre de 2026)
- **La app abre y carga la web:** en un móvil virtual Android 14 arrancó y enseñó la agenda desde un servidor de pruebas (versión 1.0).
- **La web, vista como la app** (un Chrome con el identificador `ZazuApp/1.1`): no registra service worker ni guarda copias, no ofrece descargar la app, avisa de que las alertas no llegan y enseña la versión de la web. Un navegador normal registra el service worker y ofrece la descarga.
- **Se actualiza con el servidor:** la web manda `Cache-Control: no-cache` en la página y en sus archivos. Cambiando el archivo en el servidor, la siguiente carga trajo el cambio (hub-v40 → una marca de prueba → hub-v41) sin tocar la app.
- **Al volver tras un rato:** si la app estuvo de fondo más de 15 minutos, al volver recarga la página (en las pruebas son 8 segundos). **Este paso NO se ha podido probar en el móvil virtual.**
- **No comprobado en Android:** cookie de sesión tras cerrar la app, micrófono, cámara, subir y bajar archivos, «Compartir › Zazu», ocultar el botón de Google en el login real.

**Versión 2.0 (22 de octubre de 2026): compila (APK y AAB firmados con la misma llave) y las pruebas del servidor pasan (`tests/test_api.py` › `Movil`). NO se ha probado en un móvil todavía:** permiso de archivos en el S25, copia real de WhatsApp, avisos y diálogos de peticiones, actualización con el instalador del sistema.

## Instalarla en el móvil
1. En Chrome abre `holazazu.app/zazu.apk` (o Tu espacio › Descargar la app de Android) y descarga.
2. Ábrela. El móvil pedirá permitir instalar desde Chrome. Si aparece «App no verificada» de Play Protect: Instalar de todos modos. En Samsung, si no deja, Ajustes › Seguridad y privacidad › Bloqueador automático: desactívalo mientras instalas.
3. Entra con tu usuario y contraseña.

## Trampas
- **No probar con el móvil virtual a la vez que Zazu**: el emulador pide 2,5 GB y con todo lo demás el servidor se queda sin memoria (la carga llegó a 78 y el gateway tardó en contestar). Si hay que usarlo, solo con el resto parado o con poca carga, y apagarlo en cuanto se vea la pantalla (`adb emu kill`).
- Cambios de la web: no hace falta tocar la app. Cambios de la app (este código): `build.sh`, y reinstalar el APK.
