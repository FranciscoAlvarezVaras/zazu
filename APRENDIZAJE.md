# Aprendizaje: cómo se hizo Mi nube (23 y 24 de octubre de 2026)

Este documento cuenta, para Fran, qué se construyó, cómo se trabajó y qué se aprendió por el camino. No es un manual técnico (eso está en [`pagina-web/README.md`](pagina-web/README.md)); es la historia de una jornada de trabajo, con sus aciertos y sus errores, para que la próxima vez salga mejor.

Debajo de cada titular hay un apartado **Hazlo tú mismo**: un tutorial corto, con el código tal como está en el repositorio, para que puedas repetirlo o cambiarlo sin mí. Todo el código vive en `pagina-web/`: el servidor es Python sin librerías (`server.py`, `nube.py`, `nube_geo.py`) y la web es React con TypeScript (`web/src/`).

## 1. Qué se pidió

Fran quería tres cosas, en este orden:

1. Un sitio web propio, dentro de `holazazu.app`, para ver lo que hay en `/home/server/Compartido` desde cualquier PC o desde el móvil, «como un Google Drive pero mío».
2. Que hiciera **todo lo que hace un NAS** (Synology Photos, Immich): fotos y vídeos en cuadrícula, favoritos, álbumes, duplicados, enlaces para compartir, mapa.
3. Que fuera **fácil de usar y de ver**, y que reprodujera vídeos desde la web.

Dos decisiones suyas marcaron el camino: quitar Tailscale (todo el acceso va por `holazazu.app` y nada más) y que el nombre de la pestaña fuera **Mi nube**, no «Carpetas».

### Hazlo tú mismo: convertir una petición vaga en un contrato

Antes de escribir una línea, escribe **qué devuelve cada ruta**. Así dos personas (o dos agentes) pueden trabajar a la vez sin verse. El contrato de Mi nube se escribió así, en texto plano, y fue la regla de oro de todo el trabajo:

```text
GET  /api/nube/medios?tipo=image|video&q=&fav=1&album=<id>&orden=nuevas|antiguas|tamano&desde=&n=
     -> {items:[{name,path,size,mtime,kind,fav}], total}
POST /api/nube/fav {paths:[hasta 500 rutas], on:true|false} -> {ok:true, total}
POST /api/nube/enlace {path, horas?:1..720, clave?} -> {ok, token, url, caduca}
GET  /c/<token>   PÚBLICO, SIN SESIÓN: el archivo; 404 idéntico si no existe, caducó o se revocó
```

Regla: lo que no está en el contrato no existe. Si alguien lo cambia, lo escribe en su informe y el otro lo recoge.

## 2. Qué hay ahora en holazazu.app

Al entrar en **Mi nube** hay cuatro vistas: Mis carpetas, Notas del Cerebro, WhatsApp del móvil y **Galería**. La Galería es la parte nueva:

| Qué | Cómo se usa |
|---|---|
| Fotos y vídeos por meses | Cuadrícula que carga de 90 en 90 al hacer scroll. 33.255 fotos y vídeos, 42 GB. |
| Favoritos | Corazón en cada foto y en el visor; tecla F; filtro «Favoritos». |
| Álbumes | «Nuevo álbum», añadir desde el visor, ver solo ese álbum, renombrar, borrar (las fotos no se borran), ZIP del álbum. |
| Seleccionar varias | Botón «Seleccionar» o pulsación larga en el móvil; favorito, álbum o papelera en tanda, con «Deshacer». |
| Duplicados | En «Detalles» de la tarjeta de espacio. Compara byte a byte; las copias van a la papelera (reversible). Hay 116 grupos. |
| Compartir | Enlace `holazazu.app/c/<token>` de 1 hora a 30 días, clave opcional (6 a 64 caracteres), «Dejar de compartir». La ubicación GPS se quita de la foto por defecto. |
| Mapa | Selector «Fotos \| Mapa». Sin red enseña «Lugares» (grupos de fotos por zona); el mapa de OpenStreetMap solo se carga si Fran lo activa. |
| Vídeos | Los de WhatsApp (H.264) al instante; los de la cámara (HEVC) se convierten una vez a H.264 en el PC y se guardan en caché. Se pueden adelantar sin bajarlos enteros. |
| Un día como hoy | Fotos de este mismo día en años anteriores. |
| Subir | Botón «Subir» o arrastrar y soltar en el escritorio; límite de 100 MB por archivo. |
| Presentación | Pasa fotos cada 4 segundos. |
| Zazu | Franja «Pídele a Zazu lo que quieras de tu nube» y botón «Preguntar a Zazu» en cada foto: abre el chat con la ruta ya escrita. |

Todo se queda en este PC. La única puerta a internet son los enlaces de compartir, y solo existen cuando Fran crea uno.

### Hazlo tú mismo: las cinco piezas, con su código

**Favoritos (la pieza más simple, y el patrón de todas las demás).** El servidor guarda un conjunto de rutas en un JSON propio (`~/.local/state/zazu-nube/nube.json`). Nunca toca las fotos. En `nube.py`:

```python
def poner_fav(paths, on):
    def f(d):
        s = set(d["fav"])
        if on:
            s.update(paths)
            if len(s) > MAX_FAV:
                raise A.Fallo(400, "Hay demasiados favoritos.")
        else:
            s.difference_update(paths)
        d["fav"] = s
    _cambiar(f)   # lee el JSON, aplica f, lo guarda de forma atómica (escribe un temporal y lo renombra)
```

Y la ruta en `server.py` solo valida y llama:

```python
if ruta == "/api/nube/fav":
    if not isinstance(d.get("on"), bool):
        return self.fail(400, "Falta on: true o false.")
    N.poner_fav(_nube_rutas(d, existir=d["on"]), d["on"])   # _nube_rutas rechaza rutas fuera de Compartido
    return self.send_json({"ok": True, "total": _nube_n_fav(_nube_indice())})
```

Para añadir otra cosa parecida (por ejemplo «ocultas»), copia estas dos funciones, cambia `fav` por tu nombre y añade el filtro en `nube_medios`.

**Duplicados (comparar sin leer 42 GB).** Tres pasos, cada uno descarta antes de que el siguiente lea más:

1. Agrupa por **tamaño**: dos archivos de tamaño distinto nunca son iguales.
2. De los que coinciden, calcula un hash **parcial** (los primeros y últimos 64 KB).
3. Solo a los que siguen coincidiendo, hash **completo**. En `nube.py`:

```python
def _sha(fp, size, parcial):
    h = hashlib.blake2b(digest_size=16)
    fd = os.open(fp, os.O_RDONLY | os.O_NOFOLLOW)   # nunca sigue accesos directos
    ...
```

Corre en un hilo aparte con prioridad baja para no frenar el servidor. Con las 33.000 fotos reales tarda 1,1 segundos y usa 44 MB.

**Enlaces para compartir (la pieza delicada: es lo único público).** Un token al azar de 128 bits, caducidad, y la clave guardada con `scrypt` (nunca en claro). En `nube.py`:

```python
def crear_enlace(path, horas=24, clave=None, copia=None):
    ahora = int(time.time())
    horas = min(max(int(horas or 24), 1), MAX_HORAS)   # entre 1 hora y 30 días
    tok = secrets.token_urlsafe(16)                    # 128 bits: imposible de adivinar
    reg = {"path": path, "creado": ahora, "caduca": ahora + horas * 3600, "visitas": 0}
    if clave:
        sal = secrets.token_hex(16)
        reg["clave"] = sal + ":" + _kdf(clave, sal)    # scrypt con sal propia
```

Reglas que lo hacen seguro: al servir `/c/<token>` se vuelve a comprobar que la ruta sigue dentro de Compartido y es un archivo; desconocido, caducado y revocado devuelven **el mismo 404** (sin pistas); 5 claves malas por IP en 10 minutos y se bloquea; el token nunca se escribe en los registros.

**Vídeos de cámara (HEVC a H.264).** Chrome y Firefox no reproducen HEVC. La primera vez que pides uno, el servidor lo convierte en segundo plano y guarda la copia en `~/.cache/zazu-videos`. La orden de `ffmpeg`, en `server.py`:

```python
subprocess.run([_FFMPEG, "-v", "error", "-y", *_ENTRADA, "-i", str(p),
    "-vf", "scale=-2:'min(1080,ih)'",          # como mucho 1080p, ancho par
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", tmp])
```

La web pregunta a `/api/nube/video-estado` cada 2 segundos y, cuando `listo` es `true`, pide `/api/nube/video`. Con un vídeo de 5 MB tarda 2 segundos.

**Mapa (leer el GPS).** `nube_geo.py` lee las coordenadas de tres formas: JPEG con Pillow (EXIF), HEIC con un lector propio del formato (Pillow no lo abre en este PC) y vídeos con `ffprobe`, que las escribe en el formato ISO 6709:

```python
def _iso6709(txt):
    """«+40.4168-003.7038+000.000/» → (lat, lon)."""
    m = _ISO6709.fullmatch(txt) if isinstance(txt, str) else None
    return _valido(m[1], m[2]) if m else None
```

El índice se guarda en `geo.json` y es incremental: un archivo ya leído no se vuelve a abrir. `puntos(root, zoom, s, w, n, e)` devuelve grupos por celda según el zoom, para no pintar 33.000 puntos.

## 3. Cómo se trabajó

### Primero el diseño, después el código

Antes de programar la galería se hizo una maqueta en **Claude Design** (dos pantallas interactivas, móvil y escritorio) y otra en Figma. Fran aprobó la de Claude Design y dijo «no lo cambiaría». Eso fijó los colores (verdes `#294535` y `#e9eedb`, crema `#f7f5ef`), la tipografía (DM Sans) y la forma de los botones para todo lo que vino después. Tener el diseño aprobado antes ahorró discusiones: los agentes que programaron la interfaz tenían una referencia visual y no inventaron nada.

### Un workflow de 12 agentes en paralelo

Fran pidió «ultracode» y esfuerzo máximo. Se organizó así:

1. **Construir** (4 agentes a la vez, cada uno con sus archivos, sin pisarse): servidor (favoritos, álbumes, duplicados, enlaces), web (la Galería), geo (leer el GPS de JPEG, HEIC y MP4) y un cuarto que solo **investigó** si reconocer caras era viable, sin tocar nada.
2. **Integrar el mapa** (2 agentes): conectar el GPS al servidor y hacer la pantalla.
3. **Revisar** (3 agentes a la vez): uno de **seguridad** que intentó romper los enlaces públicos de todas las formas que se le ocurrieron, uno de **calidad** que comprobó que la web y el servidor hablaran el mismo idioma, y un **crítico** que comparó el resultado con Synology, Immich y Nextcloud y dijo qué faltaba.
4. **Corregir** (2 agentes): arreglaron los 27 hallazgos reales, uno por área.
5. **Verificar** (1 agente): pasó todas las pruebas, compiló, revisó el diff buscando restos y lanzó 300 peticiones hostiles contra un servidor de prueba.

La regla de oro fue el **contrato de la API** escrito antes de empezar: el agente web programó contra ese contrato mientras el del servidor lo implementaba, sin verse. Cuando el servidor cambió algo (por ejemplo, exigir claves de 6 caracteres), lo anotó en su informe y el agente web lo recogió en la siguiente fase.

### Pruebas de verdad, no de confianza

- 74 pruebas nuevas para la nube, 84 para el GPS, y las 138 que ya existían siguen en verde.
- Cada agente probó en una **casa falsa** bajo `/tmp`: nunca tocó las fotos reales de Fran ni el servidor en marcha.
- La interfaz se probó en un **Chrome real sin pantalla**, en escritorio (1280 px) y móvil (360 y 390 px), con capturas.
- El verificador final arrancó un servidor completo en casa falsa y comprobó que respondía antes de dar el visto bueno.

### Hazlo tú mismo: lanzar un trabajo así en Claude Code

**1. Escribe «ultracode» en tu petición.** Es la palabra que le permite a Claude usar la herramienta Workflow (varios agentes a la vez). Sin ella, trabaja solo.

**2. Pide que cada agente tenga sus archivos.** Dos agentes editando el mismo archivo a la vez lo rompen. El reparto de Mi nube fue: servidor → `server.py` y `nube.py`; web → `web/src/carpetas/*`; geo → `nube_geo.py`. El que necesita un cambio fuera lo apunta en «pendientes» y lo hace otro después.

**3. Pide siempre una fase de revisión adversaria.** Es la que más vale. La orden al agente de seguridad fue literalmente: «intenta romper los enlaces públicos: path traversal, enlaces simbólicos, adivinar tokens, fuerza bruta de la clave, cabeceras falsificadas, Range malicioso. Para cada hallazgo real: severidad, reproducción y arreglo». Volvió con 10 hallazgos, ninguno grave, y 18 comprobaciones en verde.

**4. Prueba en casa falsa, nunca en producción.** El arnés ya existe. Desde `pagina-web/`:

```bash
python3 tests/test_nube.py          # 74 pruebas, arranca un hub de prueba en /tmp con casa falsa
python3 tests/test_nube_geo.py      # 84 pruebas del GPS
python3 tests/test_api.py           # las 138 de siempre
```

**5. Compila la web sin tocar lo que se sirve.** `dist/` es lo que ve la gente; los agentes compilaron a un directorio temporal:

```bash
cd pagina-web/web
export PATH="$HOME/.hermes/tools/node-26.7.0-linux-x64/bin:$PATH"
npx tsc --noEmit && npx vite build --outDir /tmp/mi-prueba --emptyOutDir
```

Y solo al final, el build real: `npm run build` (sube solo la versión de caché del service worker).

**6. Reinicia el hub solo con Zazu libre, y comprueba después.**

```bash
systemctl --user restart hermes-hub
curl -s -o /dev/null -w "%{http_code}\n" https://holazazu.app/manifest.json   # tiene que dar 200
journalctl --user -u hermes-hub --since -1min | grep -E "Error|Traceback"     # tiene que estar vacío
```

## 4. Qué salió mal y qué se aprendió

Esta es la parte útil. Cuatro errores, los cuatro míos, y la lección de cada uno.

### El 502 de una hora (de 17:45 a 18:44)

Al activar los vídeos HEVC definí una constante `VIDEOS` para la carpeta de caché. En `server.py` ya existía otra `VIDEOS` con los sufijos `.mp4` y `.webm` que usa la función que sirve **cualquier archivo** de la web. La mía pisó a la vieja y, desde ese momento, quien entraba con sesión recibía un error en vez de la página. Yo no lo vi porque, al comprobar, solo probé la portada pública, que no pasa por esa función.

**Lección:** antes de añadir una constante a `server.py` (6.300 líneas), buscar si el nombre ya existe. Y tras reiniciar el hub, probar `/manifest.json` y `/icon-192.png`, no solo la portada. Está apuntado en la memoria del proyecto y ya se cumplió en los reinicios siguientes.

### /tmp se llenó y rompió las herramientas

`/tmp` en este PC es memoria RAM (7,5 GB, con cuota por usuario). Otra sesión había dejado 4,4 GB de restos, y los agentes de prueba añadieron casas falsas y perfiles de Chrome. Cuando se llenó, los comandos perdían su salida y los tests fallaban de forma intermitente. Fran reinició el PC y quedó limpio.

**Lección:** a los agentes de las fases siguientes se les dijo que usaran un solo directorio temporal y lo borraran al acabar. Funcionó: `/tmp` no volvió a pasar de 600 MB.

### Deshice un cambio sin querer

Al limpiar la versión de caché de `sw.js` usé `git checkout` sobre el archivo entero y borré, además de mi cambio, la exclusión de `/c/` que había hecho el agente web y los botones Permitir/Rechazar de las notificaciones. Lo recuperé de la copia compilada en `dist/` y volví a publicar.

**Lección:** `git checkout <archivo>` deshace **todo** lo no guardado de ese archivo, no solo lo último. Para quitar una línea, se edita la línea.

### Me equivoqué al diagnosticar las miniaturas HEIC

Dije que el ffmpeg 7.0.2 leía bien los HEIC y el 9.0.1 no. Era al revés en lo importante: el 7 solo saca una tesela de 512×512 (una esquina de la foto), y el 9 lee la cuadrícula entera pero falla al escalar. El agente del servidor lo descubrió y resolvió los dos pasos (decodificar con el 9, escalar aparte).

**Lección:** una miniatura que «sale» no es una miniatura correcta. Hay que mirar la imagen, no solo el tamaño del archivo.

### Hazlo tú mismo: las cuatro comprobaciones que evitan estos errores

```bash
# 1. Antes de crear una constante en server.py: ¿ya existe el nombre?
grep -n "\bVIDEOS\b" pagina-web/server.py

# 2. Antes de lanzar pruebas grandes: ¿cuánto queda en /tmp?  (si hay menos de 1,5 GB, limpia lo tuyo)
df -h /tmp

# 3. Antes de deshacer un archivo: ¿qué perderías?
git diff pagina-web/web/public/sw.js        # mira TODO lo que hay sin guardar, no solo tu línea

# 4. Una miniatura HEIC con el ffmpeg correcto (el 9 decodifica la cuadrícula entera)
~/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg -i foto.heic -frames:v 1 -q:v 2 grande.jpg
~/.local/bin/ffmpeg -i grande.jpg -vf scale=360:-2 -frames:v 1 mini.jpg     # y luego se escala aparte
```

## 5. Lo que descubrieron los revisores

- **Seguridad:** ningún fallo crítico ni alto. Lo más valioso que arreglaron: el límite de intentos de la clave de un enlace se podía saltar con peticiones simultáneas; un enlace público de una foto llevaba dentro el GPS de dónde se hizo; los ZIP se preparaban enteros en disco antes de enviarse (ahora salen en streaming).
- **Calidad:** el mapa salía en blanco porque la política de seguridad de la página bloqueaba los mosaicos de OpenStreetMap; un doble toque en «A la papelera» tiraba dos fotos; subir una foto antigua descolocaba la paginación. Todo corregido.
- **Crítico:** 16 ideas para seguir, ordenadas por valor. Las de más valor: saltar a una fecha concreta en la galería, copia de seguridad de este PC a otro disco, ver en la web el estado de la copia del móvil, y «seleccionar todo lo filtrado» con ZIP de la selección.

### Hazlo tú mismo: reproducir un hallazgo antes de arreglarlo

A los agentes de arreglos se les exigió **reproducir cada hallazgo** antes de tocarlo, y descartarlo si no era real. Así se descartaron 3 de 27. Tú puedes hacer lo mismo con una prueba de dos líneas. Ejemplo real: «el límite de intentos de la clave se salta con peticiones simultáneas». La prueba lanza 20 claves malas a la vez y cuenta cuántas pasaron del límite:

```python
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(20) as ex:
    codigos = list(ex.map(lambda _: post(f"/c/{token}", {"clave": "mala"}).status, range(20)))
assert codigos.count(429) >= 15    # con el fallo, casi ninguna daba 429: todas se colaban
```

El arreglo fue anotar el intento **antes** de comprobar la clave, bajo un cerrojo (`nube.clave_intento()`), y no después.

## 6. Dos arreglos de hoy fuera de Mi nube

**Las invitadas creían que necesitaban la app.** Cuando su Zazu quiere tocar su Google, la web ya enseña sola una tarjeta con «Permitir / Rechazar». Pero el texto que les decía Zazu hablaba de «te llega un aviso al móvil» y «toca Permitir en el aviso del móvil». Buscaban una notificación que no existía y entendían que había que instalar la app. Se cambiaron el prompt y las 7 descripciones de herramientas para que digan «tarjeta de permiso en pantalla (web o app)», y la pestaña del navegador ahora parpadea mientras hay un permiso pendiente.

**Los fogonazos blancos de la app.** La app recarga la página cada vez que vuelves a ella tras 15 minutos de fondo, y también al abrir una notificación. Mientras la página se vuelve a montar, el WebView enseña blanco porque la web no definía color de fondo en el `<html>`, solo en el `body`. Ahora el fondo (crema, o el oscuro del panel) está fijado desde el primer byte del HTML. La recarga sigue existiendo, pero ya no es un fogonazo.

### Hazlo tú mismo: las dos piezas

**La tarjeta de permisos** (`web/src/chat/PermisosInvitada.tsx`) pregunta al servidor cada 3 segundos, solo mientras la pestaña está a la vista:

```ts
const mirar = () => { if (document.visibilityState === 'visible') api('/api/aprobaciones').then(d => setLista(d.pendientes)) }
mirar()
const t = setInterval(mirar, 3000)
```

Y lo añadido hoy, para que se note desde otra pestaña: mientras haya permisos, el título parpadea y vuelve al suyo al responder.

```ts
useEffect(() => {
  if (!lista.length) return
  const antes = document.title
  let on = false
  const t = setInterval(() => { on = !on; document.title = on ? `🔔 ${nombre} necesita tu permiso` : antes }, 1200)
  return () => { clearInterval(t); document.title = antes }
}, [lista.length, nombre])
```

Si quieres cambiar lo que Zazu les dice, está en `server.py`, función `soul_invitada` (busca «tarjeta con «Permitir»»), y las descripciones de sus herramientas en `mcp_google.py` (busca «tarjeta de permiso»). Después, `python3 -m unittest tests.test_reportes` comprueba que el texto sigue siendo el esperado.

**El fondo desde el primer byte** (`web/index.html`, dentro de `<head>`, antes de cualquier CSS). Dos colores: el claro y el del panel oscuro, que se marca con `data-pz-tema="oscuro"` en `<html>`:

```html
<style>html{background:#faf9f5}html[data-pz-tema="oscuro"]{background:#262624}</style>
```

Es la regla general para cualquier web: **el fondo va en `<html>`, no solo en `<body>`**, porque el navegador pinta el `<html>` antes de que llegue el CSS.

## 7. Qué queda por decidir

- **Commit:** nada de lo de estos dos días está guardado en git (111 archivos en `pagina-web/`). Fran decide cuándo.
- **Personas (caras):** es viable en local (unos 27 minutos de CPU para todas las fotos, modelos de licencia libre), pero son datos biométricos. Parado hasta que Fran lo pida.
- **Copia de seguridad a otro disco:** hace falta un segundo disco; ahora solo hay uno.
- **Recargar menos la app:** subir los 15 minutos o recargar solo si la sesión caducó. Es cambio de Android y requiere publicar un APK.

### Hazlo tú mismo: guardar el trabajo y cambiar la recarga de la app

**El commit.** `pagina-web/` tiene su propio git. Mira primero, guarda después:

```bash
cd ~/Escritorio/Spirit/pagina-web
git status --short | grep -v "^D "      # lo nuevo y lo cambiado (los D son borrados anteriores, de otro día)
git add nube.py nube_geo.py server.py guardia.py mcp_google.py tests/ web/src web/public/sw.js web/index.html dist
git commit -m "Mi nube: favoritos, álbumes, duplicados, enlaces, mapa y vídeos HEVC; permisos de invitadas en la web; fondo sin fogonazo"
```

**La recarga de la app.** El umbral está en `app-android/app/build.gradle`:

```groovy
buildConfigField 'long', 'RECARGA_MS', '900000L'   // 15 minutos; súbelo a 3600000L para una hora
```

Y la condición en `MainActivity.java`, función `onResume`. Si prefieres que solo recargue cuando la sesión haya caducado, ahí es donde se cambia. Después, `app-android/build.sh` genera el APK y hay que publicarlo.

## 8. Cifras

| | |
|---|---|
| Agentes del workflow | 12, ninguno falló |
| Tiempo del workflow | 3 h 49 min (con una interrupción por el reinicio del PC) |
| Código nuevo del servidor | `nube.py` (414 líneas), `nube_geo.py` (585), sección Nube de `server.py` |
| Pantallas nuevas de la web | 19 archivos en `web/src/carpetas/` |
| Rutas nuevas de la API | 16 bajo `/api/nube/*` y la pública `/c/<token>` |
| Pruebas | 74 + 84 nuevas, 138 anteriores, todas en verde |
| Hallazgos de la revisión | 27 reales, 24 arreglados, 3 descartados con motivo |
| Versiones de la web publicadas | 7 entre el 23 y el 24 |

### Hazlo tú mismo: sacar estas cifras cuando quieras

```bash
cd ~/Escritorio/Spirit/pagina-web
wc -l nube.py nube_geo.py                                   # líneas del servidor nuevo
grep -c "def test" tests/test_nube.py tests/test_nube_geo.py # pruebas
ls web/src/carpetas/ | wc -l                                 # archivos de la Galería
grep -o '"/api/nube[a-z/-]*"' server.py | sort -u | wc -l    # rutas de la API
```
