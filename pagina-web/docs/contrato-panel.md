# Contrato de la API del Panel de tu día + tableros (paquete BE)

Rama `panel-be`. Todo es **solo para Fran** (rol `admin`): una invitada recibe `403 {"error":"no disponible"}` en CADA ruta de este documento.
Los POST llevan la cabecera `X-Hub: 1` (sin ella: `403 acceso denegado`) y cuerpo JSON (`Content-Type: application/json`). Sin sesión: `401`.
`GET /api/me` y los endpoints de Modo Hermes no cambian (salvo lo anotado en `docs/fusion-byte.md`: textos con «Zazu» y el campo `asistente` de Fran).

## Reglas para el front (importantes)

1. **Todo texto que llega es texto, no HTML.** Títulos de avisos, tareas, eventos y notas vienen de terceros (correos, invitaciones, chats). Píntalos con `textContent`/JSX, nunca con `dangerouslySetInnerHTML`, y no los pongas en `href`. Los únicos campos que son enlaces ya están filtrados a `http(s)://` (`enlace`) o son `obsidian://…` / rutas internas del Hub.
2. **Un error en una fuente no rompe el resto.** Cada sección del panel lleva `ok`. Si `ok:false`, enseña `error` («No pude leer X») con un botón Reintentar (`?fresco=1`); **nunca** lo pintes como «nada / todo en orden». Los contadores de `resumen` valen `null` cuando su fuente falló (null = «no sé», 0 = «ninguno»).
3. `obsoleto:true` en una sección = la fuente se atascó (>3 s) y se enseña el último dato bueno (de menos de 10 min). `actualizado` = cuándo se leyó ese dato.
4. Las fechas son ISO 8601 con zona (`2026-10-08T22:58:00+02:00`) o `AAAA-MM-DD` cuando es solo día. Zona del Hub: Europe/Madrid.
5. Los códigos de aviso (`A1`…) son por día; **usa siempre el `id` numérico** en las URLs.
6. Mensajes de error: `{"error": "frase en español"}` (+ campos extra en algunos 409). Pueden mostrarse tal cual.

---

## 1. `GET /api/panel`

Query: `fresco=1` salta las cachés (con anti-rebote de 2 s). Caché de la respuesta: 5 s. Tope de espera por fuentes: 3 s en total (se piden en paralelo).
Refresco recomendado del front: cada 60 s (pausado si la pestaña está oculta) y tras cada acción.

```jsonc
{
  "ok": true,
  "generado": "2026-10-08T22:58:12+02:00",
  "ms": 45,                                 // lo que tardó en componerse
  "fecha": "2026-10-08", "hora": "22:58", "dia_semana": "jueves",
  "saludo": {"nombre": "Fran", "fecha": "2026-10-08", "hora": "22:58", "dia_semana": "jueves"},   // la franja (buenos días/tardes/noches) la calcula el front
  "resumen": {
    "eventos_hoy": 2, "eventos_manana": 3, "llevar": 1,              // llevar = eventos de hoy/mañana con lista «llevar:»
    "tareas_vencidas": 1, "tareas_hoy": 3, "tareas_sin_fecha": 1,
    "avisos": 6, "avisos_p1": 2,
    "avisos_por_fuente": {"correo": 3, "wa": 1, "agenda": 1, "sistema": 1},
    "capturado_hoy": 1                                               // cualquiera puede ser null si su fuente falló
  },
  "ahora": [ /* «Para ti ahora»: lista mezclada, ordenada por prio (1,2,3) y luego por "cuando"; máx. 20 */ ],
  "ahora_total": 9,                         // cuántas había antes de cortar a 20
  "urgentes": {
    "eventos": {"ok": true, "items": [Evento], "parcial": [], "actualizado": "…"},
    "tareas":  {"ok": true, "items": [Tarea],  "sin_fecha": 1, "parcial": [], "actualizado": "…"},
    "avisos":  {"ok": true, "items": [Aviso],  "total": 6, "actualizado": "…"}
  },
  "recientes": {"ok": true, "items": [Capturado], "actualizado": "…"},   // lo que Zazu capturó hoy de WhatsApp (zv resumen-dia)
  "vigias": { /* ver §1.5 */ },
  "fuentes": {                              // frescura y error de cada fuente, para un «hace 3 min ✓» o un aviso rojo
    "tareas":    {"ok": true,  "actualizado": "2026-10-08T22:58:10+02:00", "edad_s": 2, "obsoleto": false, "error": null, "parcial": null},
    "eventos":   {"ok": false, "actualizado": null, "edad_s": null, "obsoleto": false, "error": "La agenda tardó más de 3 s", "parcial": null},
    "avisos": {…}, "recientes": {…}, "vigias": {…}
  },
  "errores": [{"fuente": "eventos", "error": "La agenda tardó más de 3 s"}]   // atajo: las fuentes con ok:false
}
```

Sección con error (cualquiera de `urgentes.*`, `recientes`, `vigias`): `{"ok": false, "error": "No pude leer…"}` (sin `items`).
`parcial`: etiquetas de cuentas de Google que fallaron mientras la otra sí contestó (`["alvarez"]`).

### 1.1 Evento (`urgentes.eventos.items[]`) — hoy y mañana, ya sin los terminados ni los cancelados
```json
{"id": "e1", "cuenta": "varas", "titulo": "Cita DGT", "inicio": "2026-10-09T09:50:00+02:00", "fin": "2026-10-09T10:50:00+02:00",
 "todo_dia": false, "lugar": "Tráfico", "propio": true, "tentativo": false, "llevar": ["DNI", "modelo 04", "tasa"], "dia": "mañana"}
```
`dia`: `"hoy"` | `"mañana"`. `llevar` solo se rellena en eventos que creó Fran (`propio`); en invitaciones ajenas siempre `[]`.
`tentativo`: título empieza por «¿?» (evento sin confirmar que creó el vigía). El mismo evento en las dos cuentas sale una vez.

### 1.2 Tarea (`urgentes.tareas.items[]`) — solo vencidas y de hoy (no hechas)
```json
{"id": "tv2aaaaa", "cuenta": "varas", "email": "cuenta.principal@example.com", "titulo": "Tarea atrasada", "due": "2026-10-05",
 "estado": "vencida", "dias_retraso": 3}
```
`estado`: `"vencida"` | `"hoy"`. Para marcarla hecha: el endpoint que ya existe `POST /api/tareas {"action":"done","id":"<id>","account":"<email>"}`.

### 1.3 Aviso (`urgentes.avisos.items[]`; mismo objeto en `GET /api/avisos`)
```json
{"id": 2, "codigo": "A2", "fuente": "wa", "tipo": "wa_urgente", "prio": 1,
 "titulo": "Nuria te escribe con urgencia", "detalle": "", "borrador": "Llego a las 20:30, ¿cenamos?", "tiene_borrador": true,
 "enlace": "", "cuenta": null, "chat": "Nuria", "due": null, "hora": null,
 "creado": "2026-10-08T22:50:00+02:00", "vence": null, "estado": "nuevo", "pospuesto_hasta": null, "entrega": "sombra"}
```
- `fuente`: `correo` | `wa` | `agenda` | `sistema`. `tipo` (subtipo): `seguridad, cobro, dinero, oficial, entrevista, correo, evento, llevar, despues, tarea, tarea_vence, conflicto, cumple, fallo, resuelto, wa_urgente, recordar`…
- `prio`: 1 (ya) · 2 (hoy) · 3 (puede esperar). `estado`: `nuevo | visto | luego | hecho | descartado`.
- Solo salen los **abiertos**: nuevos, vistos y los pospuestos cuya hora ya llegó; nunca los silenciosos internos, caducados ni superados.
- `borrador` ≤ 200 caracteres, ya tachado por el vigía. **No hay teléfono/JID** en ningún campo.
- `enlace`: `""` o una URL `http(s)`.

### 1.4 Capturado hoy (`recientes.items[]`)
```json
{"id": 8, "codigo": "A8", "tipo": "tarea", "titulo": "Comprar pilas", "due": "2026-10-08", "hora": null, "chat": "Mamá",
 "accion": "sombra", "accion_txt": "sombra: no creada", "creado": "2026-10-08T21:10:00+02:00"}
```
`tipo`: `tarea` | `evento` (evento tentativo). `accion`: `sombra | creado | pendiente | tope | duplicado | fallido | evento_creado` (`accion_txt` es la frase en español).

### 1.5 `vigias`
```json
{"ok": true, "actualizado": "…",
 "fuentes": {"wa": {"ultimo": "2026-10-08T22:56:00+02:00", "hace_min": 2, "ok": true, "fallos": 0, "detalle": "", "modo": "sombra"},
             "correo": {…}, "agenda": {…}, "entrega": {…}, "ciclo": {…}},
 "pausa": false, "entrega_real": false, "modo": {"wa": "sombra", "correo": "sombra", "agenda": "sombra"},
 "wacli": {"ultimo": "…", "hace_min": 4, "ok": true},
 "bandeja": {"ok": true, "modo": "sombra", "ultimo": "…", "hace_min": 1, "propuestas": 0}}
```
`ok` por vigía = último ciclo bien **y** latido de menos de 20 min. `wacli.ok` = latido de menos de 30 min. `bandeja` = bandeja de Tareas/Calendar (`zb`). `modo:"sombra"` = el vigía mira pero no entrega/escribe: enséñalo («modo sombra»). Puede venir `error` si no se pudo leer la base.

### 1.6 `ahora[]` (feed «Para ti ahora»)
Cada elemento: `clave` (única, p. ej. `aviso:2`, `evento:e1`, `tarea:tv2aaaaa`), `tipo` (`aviso | correo | whatsapp | tarea | evento`), `prio`, `titulo`, `cuando`, `acciones` y campos según tipo:

| tipo | campos extra | `acciones` |
|---|---|---|
| `aviso`/`correo`/`whatsapp` | `aviso_id`, `codigo`, `fuente`, `subtipo`, `detalle`, `cuenta`, `enlace`, `borrador`, `tiene_borrador` | `["hecho","luego","descartar"]` (+ `"borrador"` si `tiene_borrador`) |
| `tarea` | `detalle` («vencida hace 3 d» / «para hoy»), `cuenta`, `ref:{account,id}` | `["hecho"]` |
| `evento` | `fin`, `todo_dia`, `lugar`, `cuenta`, `dia`, `checklist` (la lista «llevar», o null), `tentativo` | `[]` (solo abrir) |

Reglas: eventos de hoy en `ahora`; los de mañana solo si tienen «llevar». Los avisos que el vigía de agenda deriva de un evento o tarea (`evento, llevar, despues, tarea, tarea_vence, recordar`) **no** se repiten en `ahora` mientras eventos y tareas estén `ok` (sí salen en `urgentes.avisos` y en `/api/avisos`).
`prio` de un evento: 1 si empieza en ≤ 90 min o está en curso, 2 resto de hoy o mañana con «llevar»; tareas: 2.

---

## 2. Bandeja de avisos

### `GET /api/avisos?estado=abierto&n=50`
`estado`: `abierto` (defecto) | `nuevo | visto | luego | hecho | descartado`. `n` 1–200. Orden: prio asc, más reciente primero.
```json
{"ok": true, "estado": "abierto", "total": 6, "items": [Aviso]}
```
Si el vigía aún no ha creado su base o está ocupada: `200 {"ok": false, "estado": "abierto", "items": [], "error": "…"}`. Estado inválido o `n` no numérico: `400`.

### `POST /api/avisos/{id}/hecho` · `/descartar` · `/luego`
`{id}` = entero 1–999999999 (otra cosa: `404`; `0`: `400`). Cuerpo `{}`; para `luego`: `{"horas": 3}` (0,1–168) **o** `{"cuando": "manana"}` (hoy→08:00 de mañana) / `{"cuando":"tarde"}` (17:00). Sin nada: 3 h.
Llama al CLI `zv hecho|descartar|luego <id> [horas]` (lista de argumentos, sin shell).
```json
{"ok": true, "aviso": {…Aviso con el estado nuevo…}}
```
Errores: `404` (no existe o es un aviso silencioso interno), `400` (horas no válidas), `502/503/504` (el CLI falló / no está / tardó).

### `GET|POST /api/avisos/{id}/draft`
Solo **devuelve el texto** del comando de envío; **no ejecuta nada**. Lo ejecuta Zazu como comando visible y el hook de aprobación enseña a Fran destinatario y texto.
```json
{"ok": true, "id": 2, "codigo": "A2", "comando": "wacli send text --to '34600000000@s.whatsapp.net' --message 'Llego a las 20:30, ¿cenamos? $(id) '\"'\"'x'\"'\"''", "ejecutado": false,
 "aviso": "No se ha enviado nada. Pídele a Zazu «manda A2»: te enseñará el comando completo y esperará tu OK."}
```
`404` si el aviso no tiene borrador con destinatario. Sugerencia de UI: botón «Copiar» del `borrador` (el de `Aviso`) y, si quieres, «Pedir a Zazu: manda A2»; no muestres el comando como botón de ejecución.

---

## 3. Barra de órdenes (SIN charla libre)

### `POST /api/captura`  `{"texto": "recuérdame llamar a Pepe mañana a las 10", "cuenta": "varas"}`
`texto` obligatorio (1–500 caracteres; si no: `400`). `cuenta` opcional (`varas` por defecto; `alvarez`). **No escribe nada.** La respuesta es siempre un objeto con `tipo` en la raíz:

**Propuesta** (`tipo` ∈ `nota | idea | tarea | evento | aplicar | investigar | proyecto`):
```json
{"ok": true, "id": "p_Qx3v…", "tipo": "tarea", "titulo": "Llamar a Pepe (10:00)", "fecha": "2026-10-09", "hora": "10:00",
 "destino": "Google Tareas [varas]", "resumen": "Tarea: Llamar a Pepe (10:00) · vie 9/10", "confirmable": true, "falta": [], "aviso": null,
 "cuenta": "varas", "campos": {"titulo": "Llamar a Pepe (10:00)", "due": "2026-10-09", "cuenta": "varas"}}
```
- `titulo/fecha/hora/destino/resumen` es lo que se enseña en el chip de confirmación. `fecha` `null` = sin fecha.
- `aviso`: frase a mostrar bajo el chip (p. ej. «No dijiste el día: lo he puesto para mañana…», «Sin hora: lo apunto de todo el día.»).
- `confirmable:false` + `falta:["fecha"]` (evento sin día): enseña `aviso` y que reescriba; no se puede confirmar (`400`).
- `evento` añade `fin` (`"11:00"`) y `todo_dia` (bool). `nota`/`idea` añaden `texto`. Destinos: nota → `Cerebro › 10 Bandeja`; idea → `Cerebro › 10 Bandeja (Zazu la pasa a Ideas)`; tarea → `Google Tareas [varas]`; evento → `Google Calendar [varas]`; aplicar/investigar/proyecto → `Google Tareas [varas] · Zazu la procesa` (crean la tarea `Aplicar: …` y la bandeja de Zazu hace el resto).
- Reglas de respaldo (deterministas, sin IA; se usan si la IA no está o falla): «apunta…/anota…/nota: …» → nota; «idea: …»; «recuérdame/acuérdame/tengo que/tarea: … [hoy|mañana|pasado mañana|el lunes|el 15|el 15 de octubre|13/10|en 3 días|a las 10|a las 5 de la tarde]» → tarea (la hora, si la hay, va en el título entre paréntesis porque Google Tareas solo guarda el día); «cita/evento/reunión/quedada … [día] a las … [de 10 a 11:30 | durante 2 horas]» → evento (1 h por defecto); «aplicar|investigar|proyecto: …».
- La propuesta caduca a los 15 minutos o al reiniciar el Hub (`410` al confirmar).

**Fuera de ámbito** (no es una orden de organizador): 
```json
{"ok": true, "tipo": "fuera_de_ambito", "mensaje": "Eso mejor lo hablamos en el chat", "abrir": "hermes", "texto": "cómo configuro nginx"}
```
→ botón «Abrir en el chat» con `texto` precargado (`abrir: "hermes"` es el nombre interno del campo; la app abre el chat de Zazu, que por dentro es el perfil `tecnico`). No se genera ninguna respuesta de IA.

**Privado**: `{"ok": true, "tipo": "privado", "mensaje": "Eso lleva datos que no guardo (claves, cuentas, DNI…). No he apuntado nada."}`

### `POST /api/captura/confirmar`  `{"id": "p_Qx3v…", "marcados": [0, 2]}`
`marcados` es opcional: posiciones (desde 0) de los elementos de `items` que Fran dejó marcados en la hoja. Sin él se apuntan todos los `confirmable`. Con él: lista de enteros únicos y dentro de rango, todos confirmables y no vacía (si no, `400`).
Ejecuta **exactamente** lo mostrado, elemento a elemento, por una lista cerrada (`tasks add` con `--title/--due`; `calendar create` con `--summary/--from/--to/--start-timezone/--end-timezone/--all-day`; notas por `nota_rapida` en 10 Bandeja; y, solo sobre una tarea ya existente elegida del listado que se le dio al modelo, `tasks done @default <id>` y `tasks update @default <id> --due=AAAA-MM-DD`). Nunca envía, borra ni invita.
```json
{"ok": true,
 "creado":  {"tipo": "tarea", "donde": "Google Tareas [varas]", "titulo": "Llamar a Pepe (10:00)", "id": "9f3a", "indice": 0},
 "creados": [{"tipo": "tarea", "donde": "Google Tareas [varas]", "titulo": "Llamar a Pepe (10:00)", "id": "9f3a", "indice": 0}],
 "fallos":  []}
```
- `creado` = el primero de `creados` (contrato antiguo de un solo elemento). `id` = últimos 4 caracteres del id de Google (o `null` en notas). `indice` = posición en `items`.
- **Fallo parcial**: si algo falla y algo no, `200` con `fallos: [{"indice": 1, "error": "No he podido apuntarlo (Google no contestó)…"}]`; la propuesta sigue viva y un nuevo `confirmar` reintenta SOLO lo que falló (lo hecho no se repite). Si no se pudo apuntar nada: `502` (un elemento) o `502 {"error": "No he podido apuntar nada…", "fallos": [...]}`.
- Errores: `410` caducada/no es tuya · `409 {"error":"Ya lo hice.","creado":{…}}` (doble toque: no se repite) o «Ya lo estoy haciendo» · `400` no confirmable / marcados inválidos · `503` ninguna cuenta con permiso.

#### Entender con IA (Claude Haiku): campos nuevos de `POST /api/captura`
La respuesta de `/api/captura` conserva TODO lo anterior y añade, siempre:
- `entendido_con`: `"haiku"` | `"reglas"`. Con `reglas` tras un intento de IA, `motivo_reglas` ∈ `sin_ia | tope | fallo | invalido` (sin IA disponible, tope diario de 300 llamadas, el modelo falló o tardó más de 28 s, o su respuesta no pasó la validación). Los prefijos con dos puntos (`aplicar:`, `investigar:`, `proyecto:`, `idea:`, `nota:`) y el texto privado no llaman al modelo.
- `items`: lista de propuestas (1 a 5), una por cosa de la frase. Cada elemento tiene los mismos campos que una propuesta (`tipo`, `titulo`, `fecha`, `hora`, `fin`, `todo_dia`, `destino`, `resumen`, `confirmable`, `falta`, `aviso`, `cuenta`, `campos`, `texto`…) más `destino_txt`, `relacionado` y `duplicado`. Con un solo elemento, los campos de la raíz son los de `items[0]` (contrato antiguo). Con varios la raíz es `{"tipo": "varios", "titulo": "3 cosas", "confirmable": <alguno lo es>, …}`.
- `destino_txt`: el destino en lenguaje llano: «Irá a: tus tareas de Google, para el sáb 17 oct» · «Irá a: tu calendario de Google, el sáb 10 oct a las 21:00» · «Irá a: tus notas (Cerebro › Bandeja)» · «Se marcará como hecha tu tarea de Google «X»».
- `relacionado`: `null` o `{"tipo": "evento"|"tarea", "titulo", "fecha", "hora", "etiqueta": "«Boda de Chufi» · sáb 17 oct"}`: lo ya existente con lo que enlaza (la web enseña «Relacionado con: …»). Una tarea relacionada con un evento NO crea otro evento y, si Fran no dio día, toma el del evento (el `aviso` lo dice).
- `duplicado`: `true` si ya existe lo mismo (la misma tarea abierta, o el mismo evento ese día): sigue siendo `confirmable`, con `aviso` «Ya tienes esta tarea…/este evento…». Con varias cosas, la hoja deja desmarcado lo repetido.
- `aviso_general` (solo con varias cosas o recortes): «Una parte de la frase mejor la hablamos en el chat: no la he apuntado.» · «Solo he cogido las 5 primeras cosas.»
- Tipos nuevos en `tipo`: `completar` (marcar como hecha una tarea que ya existe) y `reprogramar` (cambiar su fecha; `fecha` es la nueva). Solo esas dos acciones sobre tareas existentes; nunca borrar. `campos` lleva el id de la tarea; el correo de la cuenta NO se envía al navegador. Si Fran no dice expresamente «hecha/terminada…», el servidor lo convierte en una tarea nueva marcada como repetida.
- Evento sin día: `confirmable: false`, `falta: ["fecha"]` y en `aviso` la pregunta de la IA (o la genérica).
- `fuera_de_ambito` (la IA lo ve como cosa del chat; su `tipo` interno sigue siendo `hermes`) y `privado` llevan también `entendido_con`.
- Al modelo solo van la orden (ya filtrada, enlaces sustituidos por «[enlace]»), la fecha y hora de ahora y, para enlazar sin duplicar, hasta 80 eventos (hoy → +120 días: título, día, hora) y 60 tareas abiertas (título, fecha), tachados. Nunca descripciones, correos, teléfonos, cuentas ni ids. Si no se puede leer eso a tiempo, la orden sigue y el `aviso` dice «No pude comprobar si ya existe…». Tiempo máximo ~35 s (lectura ≤5 s + modelo ≤28 s): la web enseña «Entendiendo…» con Cancelar.
- La salida del modelo es dato no fiable: se descarta TODO (y se usan las reglas) si hay tipos fuera de la lista, fechas imposibles o fuera de [ayer, +800 días], horas mal formadas, títulos vacíos, de más de 200 caracteres, con enlaces o patrones peligrosos (`wacli`, `gog`, `sudo`, `rm -`, `$(`, comillas invertidas, «ignora lo anterior», `<datos>`…) o privados, o índices fuera de rango.
- Configuración: `HUB_LLM=0` apaga la IA; `HUB_LLM_CMD` (ejecutable de pruebas), `HUB_LLM_TIMEOUT` (≤30 s), `HUB_ORDEN_ESPERA` (lectura de agenda/tareas, 5 s). Contador diario solo con cifras en `~/.local/state/hermes-hub/llm-orden.json`.

---

## 4. Tableros

### `GET /api/tableros`  (query: `eventos=0` no pide el calendario; `fresco=1` salta cachés)
```jsonc
{"ok": true, "leido": "2026-10-08T22:58:12+02:00",
 "tableros": [ Kanban(proyectos), Kanban(candidaturas), Kanban(programacion), Carnet, Personas, Viajes, FechasClave, Suscripciones ]}
```
Cada tablero se lee por separado: uno roto sale `{"id": "personas", "titulo": "Personas", "ok": false, "error": "No encuentro la carpeta «30 Notas/Personas y empresas»"}` y los demás siguen. También `GET /api/tableros/{id}` (`proyectos | candidaturas | programacion | carnet | personas | viajes | fechas | suscripciones`; otro id → `404`) devuelve solo ese objeto.
Origen: frontmatter de las notas del Cerebro; los estados y su orden salen de `90 Sistema/SCHEMA.md`.

#### Kanban — `proyectos`, `candidaturas`, `programacion`
```jsonc
{"id": "proyectos", "titulo": "Proyectos", "tipo": "kanban", "ok": true, "total": 5,
 "columnas": [{"id": "activo", "titulo": "Activo", "tarjetas": [Tarjeta]}, {"id": "esperando", …}, {"id": "en pausa", …}, {"id": "hecho", …},
              {"id": "_otros", "titulo": "Sin estado válido", "tarjetas": [...]}]}   // _otros solo si hay notas rotas o con estado fuera del SCHEMA
```
- `proyectos`: columnas `activo | esperando | en pausa | hecho`. `candidaturas`: `por enviar | enviada | prueba | entrevista | oferta | rechazada | descartada`.
- `programacion`: notas de `30 Notas` con tipo `proyecto` o `idea` y una etiqueta `programación`/`programacion`/`código`/`codigo`/`dev` (sin distinguir tildes ni mayúsculas, ni `dev/python`). Las etiquetas `programación` y `código` ya están permitidas en SCHEMA. Columnas `nueva | aparcada | activo | esperando | en pausa | hecho`.
- Las columnas vacías salen igualmente (para poder soltar tarjetas). Dentro de cada columna: por `plazo` y luego por nombre.

```json
Tarjeta = {"ruta": "30 Notas/Proyectos/Alfa.md", "titulo": "Alfa", "tipo": "proyecto", "estado": "activo", "siguiente": "Llamar al gestor",
 "plazo": "2026-10-13", "dias": 5, "vencido": false, "empresa": null, "puesto": null, "ciudad": null, "enlace": null,
 "tags": ["trabajo", "dev"], "pasos": {"hechos": 1, "total": 3}, "mtime": 1791459902105,
 "mover_a": ["activo", "esperando", "en pausa", "hecho"], "aviso": null, "obsidian": "obsidian://open?vault=Cerebro&file=30%20Notas%2FProyectos%2FAlfa"}
```
- `mtime`: versión de la nota (ms). **Devuélvelo tal cual** al mover. `mover_a`: estados válidos para esa tarjeta (una `idea` solo `nueva|aparcada`: ponerla en marcha = convertirla en proyecto desde Obsidian). Usa `mover_a` para activar/desactivar destinos al arrastrar.
- `aviso`: `null` o una frase («propiedades ilegibles», «estado no válido: «X»»). `enlace` solo `http(s)`.
- `vencido`: `plazo` pasado y estado no terminal. `dias`: días hasta el plazo (negativo = vencido).

#### `carnet` (tipo `lista`; la nota «Carnet de conducir» + su plan)
```jsonc
{"id": "carnet", "titulo": "Carnet", "tipo": "lista", "ok": true, "total": 4,
 "nota": Tarjeta, "pasos": [{"linea": 14, "texto": "Repetir los test", "hecho": false}],
 "llevar": ["NIE o DNI original."], "estudio": ["Cada día a las 19:30 tests oficiales…"],
 "eventos": {"ok": true, "items": [{"id": "…", "cuenta": "varas", "titulo": "Cita DGT Valencia 09:50", "inicio": "…", "fin": "…", "todo_dia": false, "lugar": "…"}], "parcial": [], "actualizado": "…"}}
```
`eventos` = próximos 43 días con Tráfico/DGT/examen/teórico/carnet en el título; si Google falla, `eventos:{ok:false,error}` y el resto del tablero sale. El recuento de tarjetas de repaso (Memento) **no** está incluido.

#### `personas` (solo lectura; `30 Notas/Personas y empresas`)
```jsonc
{"id": "personas", "titulo": "Personas", "tipo": "lista", "ok": true, "total": 3, "avisos": ["1 VIP sin nombre de chat resuelto"],
 "items": [{"ruta": "30 Notas/Personas y empresas/Nuria Navarro.md", "titulo": "Nuria Navarro", "tipo": "persona", "relacion": "prometida",
            "cumple": "10-11", "proximo_cumple": "2026-10-11", "dias_cumple": 3, "edad": 36, "siguiente": null, "plazo": null, "tags": ["familia"],
            "vip": true,                                   // true / false / null (null = no se sabe: la config guarda JIDs y no se pudieron resolver a nombre, o falló wacli)
            "pendientes": {"tareas": ["Llamar a Nuria por lo del piso"], "avisos": ["Nuria te escribe con urgencia"], "total": 2},   // SOLO títulos; null si no se pudo mirar
            "aviso": null, "mtime": 1791459902105, "obsidian": "obsidian://open?vault=Cerebro&file=…", "mover_a": []}]}
```
Orden: VIP primero, luego con más pendientes, luego por nombre. `cumple` = `MM-DD` (año 1900 = año desconocido → `edad:null`). VIP: se compara el **nombre** del chat (wacli) con el título/alias de la nota; los JID/teléfonos nunca se devuelven. «Pendiente con» = tareas y avisos abiertos cuyo título nombra a la persona (nombre completo, alias o nombre de pila ≥ 4 letras; los animales solo por nombre completo).

#### `viajes` (solo lectura)
```jsonc
{"id": "viajes", "titulo": "Viajes", "tipo": "lista", "ok": true, "total": 2, "pasados": 5, "nota": null,
 "items": [{"tipo": "proyecto", "fecha": "2026-10-28", "dias": 20, "titulo": "Viaje a Varsovia", "ruta": "30 Notas/Proyectos/Viaje a Varsovia.md",
            "estado": "activo", "siguiente": "Reservar vuelo", "obsidian": "obsidian://…", "checklist": ["Pasaporte.", "Cargador."], "archivo": null, "enlace": null},
           {"tipo": "archivo", "fecha": "2026-11-07", "dias": 30, "titulo": "Billete Omio Alicante", "archivo": "2026-11-07 Billete Omio Alicante.pdf",
            "enlace": "/?tab=carpetas&ruta=Importante/Viajes&archivo=2026-11-07%20Billete%20Omio%20Alicante.pdf", "ruta": null, "checklist": []}]}
```
Fuentes: archivos/carpetas de `40 Compartido/Importante/Viajes` con prefijo `AAAA-MM-DD` **de hoy en adelante** (los pasados solo se cuentan en `pasados`) y proyectos con etiqueta `viajes`/`viaje` no terminados (fecha = su `plazo`). `checklist` = viñetas de su sección «Qué llevar/Equipaje/Maleta». Orden por fecha; sin fecha al final. `nota` explica una carpeta ausente.

#### `fechas` (solo lectura)
```jsonc
{"id": "fechas", "titulo": "Fechas clave", "tipo": "lista", "ok": true, "total": 8, "avisos": [],
 "grupos": [{"id": "vencidas", "titulo": "Vencidas", "items": [FechaClave]}, {"id": "esta_semana", …}, {"id": "este_mes", …}, {"id": "despues", …}]}
FechaClave = {"fecha": "2026-10-11", "dias": 3, "tipo": "cumple|plazo|evento", "titulo": "Cumple de Nuria Navarro (36)", "vencido": false,
              "ruta": "30 Notas/…md", "obsidian": "obsidian://…"}          // ruta/obsidian en cumple y plazo; "cuenta" en evento; "estado" en plazo
```
Sale: cumpleaños (Personas), `plazo:` de proyectos y candidaturas no terminados (vencidos hasta 14 días atrás) y eventos de calendario (próximos 43 días) con plazo/entrega/vence/vencimiento/caduca/deadline en el título. `esta_semana` = hoy…+6 días; `este_mes` = el resto del mes; `despues` = más allá. Si falla el calendario, `avisos:["No pude mirar el calendario: …"]` y el resto sale. «Abrir nota» = `obsidian` (no hay edición en la app).

#### `suscripciones` (forma y estado vacío; el vigía de correo escribirá los datos)
```json
{"id": "suscripciones", "titulo": "Suscripciones", "tipo": "lista", "ok": true, "items": [], "total": 0, "nota": "pendiente del vigilante de correo"}
```
Cuando la base del vigía (`~/.local/state/zazu-vigia/avisos.db`) tenga una tabla `suscripciones(nombre, importe, moneda, proxima_fecha, cuenta)` (o `suscripcion`), el lector la usa sin cambios: `items:[{"nombre":"Spotify","importe":10.99,"moneda":"EUR","proxima_fecha":"2026-11-03","cuenta":"varas"}]`, `nota:null`, orden por `proxima_fecha`. Faltan columnas opcionales → `null`; falta `nombre` o la tabla → vacío con la nota.

### `POST /api/tableros/mover`  — solo Proyectos, Candidaturas, Programación y Carnet
`{"path": "30 Notas/Proyectos/Alfa.md", "estado": "esperando", "mtime": 1791459902105}`  (`ruta` se acepta como alias de `path`)
Reescribe **solo** la línea `estado:` de la nota (guardada de forma atómica), añade `- AAAA-MM-DD · Estado: activo → esperando (desde HolaZazu).` arriba de «## Historial» (si la nota lo tiene) y una línea en `90 Sistema/log.md`. Conserva CRLF y BOM.
**Candidaturas:** al pasar a `enviada` (el estado de SCHEMA; el nombre coloquial `aplicada` se acepta como alias y se guarda como `enviada`) se pone además `enviada: AAAA-MM-DD` (hoy, Europe/Madrid) en la MISMA escritura atómica, solo si el campo falta (se añade detrás de `estado:`) o está vacío; una fecha ya existente nunca se pisa. `enviada_puesta:true` indica que se escribió. Otros estados u otros tipos no tocan `enviada`.
```json
{"ok": true, "sin_cambios": false, "antes": "activo", "despues": "esperando", "historial": true, "registro": true, "enviada_puesta": false, "tarjeta": Tarjeta}
```
`tarjeta.mtime` es la versión nueva: úsala en el siguiente movimiento. `sin_cambios:true` si ya estaba en ese estado.
Errores: **`409 {"error":"La nota cambió mientras tanto. He recargado el tablero.","tarjeta":Tarjeta|null}`** (la versión no coincide, o alguien la tocó durante la escritura: repinta con `tarjeta` o recarga) · `400` (estado fuera de SCHEMA para ese tipo — el mensaje lista los válidos —, ruta no válida, fuera de `30 Notas`, nota que no es de un tablero —incluidas personas y empresas—, falta `mtime`) · `403` (acceso directo/ruta prohibida) · `404` (ya no existe).

### `POST /api/tableros/paso`  (casillas de «## Pasos»)
`{"path": "30 Notas/Proyectos/Alfa.md", "linea": 14, "texto": "Repetir los test", "hecho": true, "mtime": 1791459902105}` → `{"ok": true, "sin_cambios": false, "tarjeta": Tarjeta}`.
`linea` (1-based) y `texto` salen de `carnet.pasos[]`; si esa línea ya no es ese paso: `409` con `tarjeta`. Mismos errores que `mover`.

---

## 5. Lo que NO hace este paquete (para que el front no lo prometa)
- No envía mensajes ni correos, no borra nada, no invita a nadie. `draft` solo da texto.
- El briefing de las rutinas (texto de «Resumen de la mañana/Repaso de la noche») sigue en `GET /api/hoy` (`resumen`), sin cambios; el panel no lo duplica.
- No hay chat libre: lo que no es una orden de organizador vuelve como `fuera_de_ambito` → el chat de Zazu.
- Los datos de Suscripciones aún no existen; Carnet no trae el recuento de tarjetas Memento; en Programación solo salen las notas que lleven una de esas etiquetas (hoy ninguna).
