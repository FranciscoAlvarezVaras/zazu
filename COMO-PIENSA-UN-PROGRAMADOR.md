# Cómo piensa un programador (y cómo razono yo cuando trabajo en Spirit)

Este documento es el compañero de [`APRENDIZAJE.md`](APRENDIZAJE.md). Aquel cuenta **qué** se hizo; este cuenta **cómo se piensa** para hacerlo, con ejemplos reales de estos dos días. Está escrito para Fran, sin suponer que sepa programar. Cada apartado tiene tres partes: la idea, cómo razono yo de verdad (con lo que me pasó por la cabeza en un caso concreto) y un **Hazlo tú mismo**.

La mitad del documento es de **ciberseguridad**, porque Mi nube tiene una puerta a internet (los enlaces para compartir) y ahí es donde más vale pensar bien.

---

## Parte I: cómo se razona

### 1. Antes de tocar nada, mirar

Un programador que empieza a escribir código sin haber leído lo que hay es como un mecánico que cambia una pieza sin abrir el capó. Lo primero siempre es **mirar**: qué existe, cómo se llama, quién lo usa.

**Cómo razoné yo.** Fran dijo «quiero una web para ver Compartido». Mi primer impulso fue proponer instalar Filebrowser. Pero antes miré el servidor y encontré que la web **ya tenía** una pestaña Carpetas con subida, descarga y papelera. Si hubiera instalado otra cosa, habríamos tenido dos sistemas haciendo lo mismo. Mirar primero ahorró un día de trabajo y un servicio más que mantener.

Y al revés: cuando no miré, me costó caro. Añadí una constante `VIDEOS` sin buscar si ya existía. Existía. La web estuvo rota una hora.

**Hazlo tú mismo: las tres preguntas antes de cambiar algo.**

```bash
cd ~/Escritorio/Spirit/pagina-web

# 1. ¿Ya existe algo que haga esto?   (busca la palabra clave en todo el código)
grep -rn "duplicad" --include=*.py --include=*.tsx . | head

# 2. ¿Este nombre ya está cogido?     (antes de crear una constante, función o archivo)
grep -n "\bVIDEOS\b" server.py

# 3. ¿Quién usa lo que voy a cambiar? (si cambio una función, qué se rompe)
grep -rn "nube_mini(" --include=*.py .
```

Si la pregunta 1 devuelve algo, lee eso antes de escribir nada. Si la 3 devuelve diez sitios, el cambio es más delicado de lo que parecía.

### 2. Reproducir antes de arreglar

Un fallo que no puedes provocar a voluntad no lo puedes arreglar con seguridad. Puedes creer que lo arreglaste, y no.

**Cómo razoné yo.** Fran dijo «hay tirones donde la pantalla se pone blanca». Pude haber contestado «es la red». En vez de eso busqué en el registro cuántas veces se había pedido la página por hora, vi que coincidía con las horas en que el servidor daba 502, miré el código de la app Android y encontré que recarga la página al volver tras 15 minutos de fondo. Después miré el CSS y vi que el `<html>` no tenía color de fondo. Dos causas, las dos demostradas, no adivinadas.

Otro caso: el revisor dijo «un nombre con `%03d` da 404 en la miniatura». Antes de arreglarlo lo reproduje a mano con `ffmpeg` y una foto llamada `foto%03d.jpg`: fallaba. Probé el primer arreglo que se me ocurrió (`-pattern_type none`): arreglaba ese caso pero **rompía las fotos normales y los vídeos**. Si no lo hubiera probado, habría publicado un arreglo que estropeaba todas las miniaturas. El arreglo bueno fue otro (darle a ffmpeg un enlace con nombre seguro).

**Hazlo tú mismo: reproducir un fallo con una prueba.**

El proyecto tiene un arnés que levanta un servidor de prueba en una casa falsa, sin tocar tus datos. Una prueba de regresión es esto (está en `tests/test_nube.py`):

```python
def test_miniatura_de_un_nombre_con_patron_de_ffmpeg(self):
    """«foto%03d.jpg» no es una secuencia: sale su miniatura."""
    self.poner("Raras/foto%03d.jpg", jpeg())        # crea la foto en la casa falsa
    self.sync()
    st, h, c = self.crudo("GET", "/api/nube/mini?path=" + urllib.parse.quote("Raras/foto%03d.jpg"))
    self.assertEqual((st, c[:2]), (200, b"\xff\xd8"))   # 200 y los dos bytes con que empieza un JPEG
```

Primero escribes la prueba, la ejecutas y **falla** (eso demuestra que reproduce el fallo). Luego arreglas el código y la ejecutas otra vez: pasa. Esa prueba queda para siempre; si alguien rompe eso en el futuro, la prueba avisa.

```bash
python3 -m unittest tests.test_nube.NubeApi.test_miniatura_de_un_nombre_con_patron_de_ffmpeg
```

### 3. Descartar por orden de coste

Cuando algo puede tener varias causas, se comprueban primero las **baratas de descartar**, no las más probables.

**Cómo razoné yo.** El registro mostraba dos miniaturas que fallaban con «Invalid argument» una y otra vez. Hipótesis: (a) formato de píxel raro, (b) dimensiones impares, (c) archivo corrupto, (d) no es una foto. La (a) se descarta añadiendo `-pix_fmt yuvj420p` y probando: era barata y la hice. Pero seguía fallando. Entonces busqué **qué archivos eran** (dos SVG, dibujos vectoriales, no fotos): era la (d). ffmpeg no sabe pintar SVG; el arreglo correcto no era tocar ffmpeg sino no mandarle SVG.

La lección: el primer arreglo barato no era el bueno, pero costó un minuto descartarlo, y el camino hasta la causa real fue corto porque no me casé con la primera hipótesis.

**Hazlo tú mismo: leer el registro del servidor.**

```bash
# errores del hub desde el último reinicio, agrupados y contados (los más repetidos arriba)
journalctl --user -u hermes-hub --since "-6h" --no-pager | grep -E "Error|Traceback" \
  | sed 's/.*python3\[[0-9]*\]: //' | sort | uniq -c | sort -rn | head

# el contexto de un error concreto (10 líneas antes)
journalctl --user -u hermes-hub --since "-6h" --no-pager | grep -B10 "Invalid argument" | head -30
```

El `uniq -c` es la clave: un error que sale 30 veces y otro que sale 1 no se tratan igual.

### 4. El cambio mínimo que resuelve el problema

Cada línea que escribes es una línea que puede fallar y que alguien tendrá que leer. Un buen arreglo cambia lo menos posible.

**Cómo razoné yo.** Las invitadas creían que necesitaban la app. Pude rehacer el sistema de permisos. Pero la tarjeta de «Permitir / Rechazar» de la web **ya funcionaba**; lo que fallaba era el texto que les decía Zazu («te llega un aviso al móvil»). El arreglo fueron ocho frases y un parpadeo del título de la pestaña. Cero riesgo, problema resuelto.

A los agentes que corrigieron la revisión se les dio esta regla: «los hallazgos de severidad baja solo si el cambio es de 1 a 3 líneas». Descartaron 11 de 27 por eso, y lo explicaron. Está bien dejar cosas sin hacer si el coste no compensa.

**Hazlo tú mismo: medir un cambio antes de darlo por bueno.**

```bash
git diff --stat pagina-web/server.py       # cuántas líneas cambian
git diff pagina-web/server.py | head -60   # y cuáles, una a una
```

Si para arreglar una cosa pequeña el diff tiene 200 líneas, algo va mal: o el arreglo es otro, o estás haciendo dos cosas a la vez.

### 5. Separar lo que sé de lo que supongo

Cuando informo, distingo tres cosas: lo que **comprobé**, lo que **supongo** y lo que **no pude probar**. Mezclarlas es la forma más rápida de perder la confianza de quien te lee.

**Cómo razoné yo.** Dije a Fran: «el ffmpeg 7 saca bien las miniaturas HEIC y el 9 falla». Era verdad a medias: el 7 «sacaba algo», pero era una esquina de 512×512, no la foto. Un agente lo descubrió después mirando la imagen, no el tamaño del archivo. Lo corregí en el siguiente mensaje y lo apunté en APRENDIZAJE.md como error mío. Esconderlo habría sido peor: Fran habría visto miniaturas raras sin saber por qué.

Y al escribir **este mismo documento** me pasó otra vez: cité una función llamada `_copia_sin_gps`. Antes de publicar comprobé que cada nombre existiera en el código. Ese no existía (se llama `_sin_gps`). Lo corregí. Un documento que cita funciones inventadas enseña a buscar donde no hay nada.

**Hazlo tú mismo.** Al final de cualquier trabajo, escribe tres líneas: «Comprobado: …», «No probado: …», «Supongo que: …». En este proyecto, por ejemplo: comprobado en Chrome de escritorio y móvil emulado; **no probado** en un S25 real ni con la app instalada; supongo que Cloudflare no corta los ZIP grandes, pero no lo he medido.

---

## Parte II: cómo se piensa la seguridad

La seguridad no es una lista de trucos. Es **una forma de mirar**: en vez de preguntar «¿funciona?», preguntar «¿cómo lo rompería alguien con malas intenciones?». Esto es lo que hizo el agente de seguridad con los enlaces públicos de Mi nube, paso a paso, con el código real.

### 6. Primero: ¿qué hay que proteger y de quién?

Antes de defender hay que saber qué está en juego. En Mi nube:

- **Lo que se protege:** 42 GB de fotos y vídeos de Fran y su familia, y por extensión todo su PC (el servidor corre en él).
- **De quién:** de cualquiera en internet, porque `holazazu.app/c/<token>` se abre **sin sesión**. Es la única puerta pública: todo lo demás exige entrar con Google.
- **Qué quiere el atacante:** ver fotos que no le han compartido, salir de la carpeta Compartido a otras del PC, adivinar enlaces, saltarse la clave, o tumbar el servidor.

Con eso claro, cada defensa responde a un ataque concreto. Sin eso, se protegen cosas que no importan y se olvidan las que sí.

**Hazlo tú mismo.** Para cualquier función nueva que se vea desde internet, escribe en una línea: «Si esto falla, ¿qué puede ver o hacer un desconocido?». Si la respuesta es «nada», no hace falta más. Si es «mis fotos» o «mi PC», sigue leyendo.

### 7. Nunca fiarse de lo que llega de fuera

Todo lo que viene del navegador (la URL, el cuerpo, las cabeceras, el nombre de un archivo) lo ha podido escribir un atacante. El código **valida** antes de usar.

**El ataque clásico: salirse de la carpeta.** Si el servidor hace «dame el archivo `Compartido/` + lo que me pidan», alguien pide `../../.ssh/id_rsa` y se lleva las claves del PC. La defensa en `archivos.py` es esta, y **toda** ruta de Mi nube pasa por ella:

```python
def ruta(self, rel):
    """Ruta absoluta y comprobada de rel. Nunca sale de la raíz ni pasa por un acceso directo."""
    rel = str(rel or "")
    if "\x00" in rel:
        raise PermissionError("ruta no válida")          # un byte nulo corta la ruta en C: fuera
    partes = [x for x in rel.split("/") if x not in ("", ".")]
    if ".." in partes:
        raise PermissionError("ruta fuera de tus carpetas")   # subir de carpeta: fuera
    for i, x in enumerate(partes):
        if not self.visible(x, i == 0):
            raise PermissionError("ruta reservada")       # carpetas ocultas o del sistema: fuera
    p = self.real.joinpath(*partes)
    if p.resolve() != p:
        raise PermissionError("ruta no permitida")        # hay un acceso directo por medio: no se sigue
    return p
```

Fíjate en la última comprobación: aunque la ruta esté dentro de Compartido, si en medio hay un **enlace simbólico** que apunta fuera (alguien crea `Compartido/x → /home`), no se sigue. Y se comprueba **al servir**, no solo al crear el enlace: un archivo puede cambiarse por un enlace simbólico después (es el ataque llamado TOCTOU, «time of check, time of use»). El agente de seguridad probó exactamente eso y obtuvo 404.

**Hazlo tú mismo: pensar como el que ataca.** Toma cualquier parámetro que llegue de fuera y pregúntate qué pasa si vale:

- vacío, o muy largo (un millón de caracteres),
- con `../`, con `/` al principio, con un byte nulo,
- con caracteres raros (tildes, emojis, saltos de línea),
- un número negativo, enorme, o `NaN`,
- el mismo valor repetido mil veces por segundo.

El agente de calidad lanzó 300 peticiones así contra el servidor de prueba. Ninguna dio error 500. Esa es la prueba de que se valida bien.

### 8. No dar pistas

Un servidor que dice «el enlace caducó» le dice al atacante que el enlace existió. Uno que dice «clave incorrecta» le dice que el enlace existe y lleva clave. Cada mensaje distinto es información.

La defensa en `server.py`:

```python
def _enlace_404(self):
    """Siempre lo mismo (código, cuerpo y cabeceras): enlace desconocido, caducado, revocado o con el archivo ya sin sitio. Sin pistas."""
    b = b"No encontrado"
    self.send_response(404)
    self.send_header("Content-Type", "text/plain; charset=utf-8")
    self.send_header("Content-Length", str(len(b)))
    self.send_header("Cache-Control", "private, no-store")
    self.send_header("X-Robots-Tag", "noindex, nofollow")
```

Cuatro situaciones distintas, **una sola respuesta**, byte a byte igual. El auditor comprobó además que el **tiempo** de respuesta no cambia entre ellas (si «caducado» tardara 2 ms más que «desconocido», también sería una pista).

**Hazlo tú mismo.** Pide tres enlaces inventados y compara:

```bash
for t in AAAAAAAAAAAAAAAAAAAAAA BBBBBBBBBBBBBBBBBBBBBB CCCCCCCCCCCCCCCCCCCCCC; do
  curl -s -o /dev/null -w "%{http_code} %{size_download} bytes %{time_total}s\n" "https://holazazu.app/c/$t"
done
```

Las tres líneas deben ser idénticas salvo el tiempo, y el tiempo casi igual.

### 9. Hacer que adivinar sea imposible, no difícil

Un enlace es seguro si nadie puede adivinarlo. La diferencia entre «difícil» e «imposible» es el número de posibilidades.

```python
tok = secrets.token_urlsafe(16)   # 16 bytes = 128 bits al azar
```

128 bits son 340 sextillones de combinaciones. Probando mil millones por segundo, se tardarían más años que la edad del universo. Por eso se usa `secrets` (azar criptográfico) y no `random` (azar predecible, pensado para juegos).

**La clave de un enlace se guarda cifrada, nunca en claro.** Si alguien leyera el archivo de estado del servidor, no vería las claves:

```python
def _kdf(clave, sal):
    clave = unicodedata.normalize("NFC", clave)   # «contraseña» es la misma venga el teclado como venga
    return hashlib.scrypt(clave.encode(), salt=sal.encode(), n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024).hex()
```

`scrypt` está hecho **a propósito para ser lento** (unos 50 ms): a ti no te importa al escribir la clave una vez, pero al que intenta un millón de claves le cuesta 14 horas. Y la **sal** (un valor al azar por enlace) hace que dos enlaces con la misma clave se guarden distinto, así que no sirven tablas precalculadas.

**Hazlo tú mismo.** La regla para cualquier secreto: generar con `secrets`, guardar solo un hash lento con sal (`scrypt` o `argon2`), comparar con `hmac.compare_digest` (tiempo constante). Nunca `random`, nunca MD5 o SHA-1 para contraseñas, nunca `==` para comparar secretos.

### 10. Limitar los intentos, y hacerlo bien

Aunque la clave esté bien guardada, hay que impedir que alguien pruebe miles. El límite: 5 fallos por IP y 30 por enlace cada 10 minutos.

**Aquí hubo un fallo real que encontró el auditor**, y es la mejor lección del documento. La primera versión apuntaba el intento **después** de comprobar la clave. Con 20 peticiones **a la vez**, las 20 comprobaban «¿cuántos fallos llevas? cero» antes de que ninguna hubiera apuntado el suyo. Las 20 pasaban. El límite no limitaba nada.

El arreglo, en `nube.py`:

```python
def clave_intento(tok, ip):
    """Apunta un intento de clave ANTES de mirarla: con peticiones a la vez, apuntar solo los fallos
    (después de gastar scrypt) dejaba pasar todas. -> 0 si puede probar, o los segundos que faltan."""
    ahora = time.time()
    claves = ((tok, ip), (tok, None))
    with _FALLOS_LOCK:                                   # un cerrojo: una petición cada vez entra aquí
        vs = [[t for t in _FALLOS.get(k, ()) if ahora - t < VENTANA] for k in claves]
        for v, tope in zip(vs, (POR_IP, POR_ENLACE)):
            if len(v) >= tope:
                return int(VENTANA - (ahora - v[0])) + 1   # bloqueado: cuántos segundos faltan
        for k, v in zip(claves, vs):
            _FALLOS[k] = v + [ahora]                      # se apunta YA, antes de comprobar nada
    return 0
```

Dos ideas: el **cerrojo** (`_FALLOS_LOCK`) hace que las peticiones entren de una en una a esa parte, y el intento se apunta **antes** de gastar tiempo en `scrypt`. Si la clave resulta buena, `clave_acierto()` lo descuenta.

**Y una segunda trampa, también encontrada por el auditor:** el límite «por IP» con IPv6 no servía, porque un atacante tiene millones de direcciones IPv6 propias. Arreglo en `server.py`:

```python
a = ipaddress.ip_address(ip)
return str(a.ipv4_mapped or ipaddress.ip_network((a, 64), strict=False)) if a.version == 6 else ip
# IPv6: todo un /64 cuenta como un solo cliente
```

**Hazlo tú mismo: la prueba de concurrencia.** Es la que reprodujo el fallo. Lanza 20 claves malas a la vez y cuenta cuántas devuelven 429 (bloqueado):

```python
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(20) as ex:
    codigos = list(ex.map(lambda _: post(f"/c/{token}", {"clave": "mala"}).status, range(20)))
assert codigos.count(429) >= 15     # con el fallo, ninguna se bloqueaba
```

Cualquier límite (de intentos, de peticiones, de subidas) hay que probarlo **en paralelo**, no en fila. En fila siempre parece que funciona.

### 11. Pensar en lo que se filtra sin querer

A veces la fuga no está en el código sino en los **datos**. Una foto del móvil lleva dentro, en el EXIF, la latitud y longitud de dónde se hizo. Compartir «una foto de la playa» era compartir **qué playa, con precisión de metros**, y por extensión dónde vive quien la hizo si era en casa.

El arreglo: al crear un enlace de una foto con GPS, el servidor hace una **copia sin metadatos** (`_sin_gps` en `server.py`) y sirve esa, no el original. La web avisa y la casilla «Quitar la ubicación» viene marcada.

Otras fugas de este tipo que se revisaron: el **token** nunca se escribe en los registros del servidor (si alguien lee el log no se lleva enlaces); el nombre del archivo en la cabecera `Content-Disposition` se codifica para que un nombre con saltos de línea no pueda **inyectar cabeceras** (`filename*=UTF-8''...`); y el service worker de la web no guarda en caché las respuestas de `/c/` (cabecera `Vary: *` y exclusión en `sw.js`), para que una foto compartida no se quede en el navegador de quien la vio.

**Hazlo tú mismo.** Mira qué lleva dentro una foto tuya:

```bash
~/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffprobe -v error -show_entries format_tags -of json "foto.jpg" | head -30
```

Si ves `location` o `GPS`, esa foto cuenta dónde se hizo. Para quitarlo a mano: `ffmpeg -i foto.jpg -map_metadata -1 -c copy limpia.jpg`.

### 12. Defensa en profundidad: varias capas, por si una falla

Ninguna defensa es perfecta. Se ponen varias, de forma que para hacer daño haya que saltarse todas.

Para un enlace `/c/<token>` en Mi nube, las capas son:

1. **Cloudflare** delante: filtra ataques masivos antes de que lleguen al PC.
2. **La guardia** (`guardia.py`): límite de peticiones por IP y bloqueo de escáneres (quien pide `/wp-admin` o `/.env` se bloquea).
3. **El token** imposible de adivinar.
4. **La caducidad**: como mucho 30 días; y revocable en cualquier momento.
5. **La clave opcional**, con límite de intentos.
6. **La ruta validada al servir** (`Raiz.ruta`), aunque el enlace ya existiera.
7. **Solo un archivo**, nunca una carpeta ni un listado.
8. **Cabeceras** que impiden que el navegador ejecute nada: `Content-Security-Policy: sandbox`, `X-Content-Type-Options: nosniff`.

Si el token se filtrara (capa 3), siguen la caducidad y la clave. Si alguien lograra meter una ruta rara en el estado, la capa 6 lo para. Ninguna capa confía en que la anterior haya funcionado.

**Hazlo tú mismo.** Para cualquier función expuesta, cuenta sus capas. Si solo tiene una («la URL es secreta»), falta trabajo.

### 13. Cómo se hizo la auditoría (para que la repitas)

El agente de seguridad no leyó el código buscando errores al azar. Siguió una lista, probó cada punto contra un servidor de prueba y anotó **lo que falló y lo que resistió**. La lista, resumida, fue:

| Ataque | Cómo se probó | Resultado |
|---|---|---|
| Salir de Compartido | rutas con `../`, absolutas, ocultas, con enlaces simbólicos sembrados a mano en el estado | 404 en todas |
| TOCTOU | cambiar el archivo por un enlace simbólico después de crear el enlace | 404 |
| Enumerar enlaces | comparar cuerpo, cabeceras y tiempo de 4 clases de 404 | idénticos |
| Fuerza bruta de clave | 20 peticiones a la vez | **fallaba** → arreglado |
| Saltar el límite por IP | cabeceras `X-Forwarded-For` falsas; IPv6 distintas | la cabecera se ignora; IPv6 **fallaba** → arreglado |
| Inyectar cabeceras | nombres de archivo con `\r\n`, comillas, `;` | codificados |
| Agotar recursos | Range con 4.300 dígitos, JSON anidado a fondo, ZIP enormes | **tres fallos menores** → arreglados |
| Fuga en logs | crear enlaces y claves, luego leer `hub.log` y `seguridad.log` | ni tokens ni claves |
| CSRF | POST con la cookie pero sin la cabecera `X-Hub` | 403 |

Lo importante no es la lista exacta, sino el método: **una hipótesis de ataque, una prueba que la ejecuta, un resultado anotado**. Y anotar también lo que resiste: así la próxima auditoría no repite lo ya probado.

**Hazlo tú mismo: pedir una auditoría a Claude.** Cuando añadas algo que se vea desde internet, la orden que funcionó fue, literalmente:

> «Haz una auditoría adversaria de `<la función>`. Intenta romperla de verdad contra un hub de prueba con casa falsa: path traversal y enlaces simbólicos, TOCTOU, enumeración y tiempos, adivinar tokens, fuerza bruta en paralelo, cabeceras falsificadas, inyección de cabeceras, Range malicioso, cuerpos enormes, fugas en logs, CSRF. Para cada hallazgo real: severidad, archivo:línea, reproducción ejecutada y arreglo. No incluyas nada que no puedas fundamentar. Incluye también lo que probaste y está bien.»

---

## Parte III: la actitud

Tres cosas que no son técnicas y que importan más que cualquier comando.

**Decir lo que no sé.** Cuando Fran preguntó por qué las invitadas pedían la app, no sabía la respuesta. Lo dije, busqué en el código y en los registros durante veinte minutos, y la encontré. Inventar una respuesta plausible habría sido más rápido y habría llevado a arreglar lo que no estaba roto.

**Parar cuando hay que parar.** Cuando Fran dijo que iba a reiniciar el PC, lo primero fue detener los agentes que estaban escribiendo en `server.py`, no seguir «un minuto más». Un archivo a medio escribir en un reinicio es un servidor que no arranca.

**Apuntar lo aprendido donde se vaya a leer.** El error de `VIDEOS` está en la memoria del proyecto con la regla que lo evita («tras reiniciar, probar `/manifest.json`»). Se cumplió en los siete reinicios siguientes. Un error que se apunta se comete una vez; uno que no, se comete cada mes.
