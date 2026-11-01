# Contrato de la API «Qué ha hecho Zazu» (registro de actividad y flujos)

Rama `registro`. Lo que el Hub **recibe del vigía** está en el contrato `zv registro --json` / `zv flujos --json` / `zv flujo <id> …` (lo construye el vigía).
Este documento es lo que el Hub **ofrece a la app**: `GET /api/registro`, `GET /api/flujos` y `POST /api/flujos/<id>`. Código: `registro.py`; rutas en `server.py` (`zazu_get` / `zazu_post`).

## Reglas generales

* **Solo Fran (rol `admin`).** Una invitada (cuentas `zi*`) recibe `403 {"error":"no disponible"}` en las tres rutas; el guard general de `/api/*` ya lo hace y hay pruebas.
* Los POST llevan `X-Hub: 1` (sin ella: `403 acceso denegado`) y cuerpo JSON; la ruta de flujos acepta como máximo **4 KB** de cuerpo. Sin sesión: `401`.
* **Todo texto es texto.** Los textos vienen del vigía (que ya los filtra), pero el Hub no se fía: cada campo se valida contra listas cerradas o se limpia (sin saltos de línea ni caracteres de control o de dirección) y se recorta. El front debe pintarlos con JSX/`textContent`, nunca como HTML.
* **Un fallo se dice, no se disfraza de «nada».** En los GET, si `zv` está caído, tarda (>10 s), contesta basura o demasiado (>1,5 MB), la respuesta es `200` con `{"ok": false, "error": "frase en español", "items": [] …}`: nunca `0 flujos` ni números inventados. El texto de error del CLI no se repite (podría llevar rutas o datos).
* `zv` se ejecuta con lista de argumentos (sin shell), entorno mínimo, stdin cerrado, tiempo máximo y como mucho 4 a la vez (`503 el vigía está ocupado` si no hay turno en 3 s).

## 1. `GET /api/registro`

Query (todo opcional): `dia=AAAA-MM-DD` (por defecto hoy en Europe/Madrid; fecha real entre 2020 y mañana), `fuente=wa|correo|agenda|tareas|sistema`, `tipo=leyo|propuso|escribio|descarto|fallo|aviso`, `n=1…200` (por defecto 100).
Un valor fuera de la lista, una fecha imposible o `n` no entero → `400 {"error"}` y **no se llama a `zv`**. Un parámetro vacío (`fuente=`) equivale a no ponerlo.

Llamada a `zv`: `registro --json --dia D -n N [--fuente F] [--tipo T]`.

```jsonc
{
  "ok": true,
  "dia": "2026-10-09", "filtros": {"fuente": null, "tipo": null}, "n_pedido": 100,
  "items": [                        // más reciente primero (el Hub reordena por ts)
    {"id": 31, "ts": "2026-10-09T13:30:12+02:00",
     "actor": "vigia" | "bandeja" | "app" | null,
     "fuente": "wa|correo|agenda|tareas|sistema", "tipo": "leyo|propuso|escribio|descarto|fallo|aviso",
     "modo": "sombra" | "vivo",    // sombra = «habría…» (no se hizo nada) · vivo = hecho de verdad
     "titulo": "…≤160", "detalle": "…≤240" | null,
     "flujo": "correo-plazo" | null,          // solo si cumple ^[a-z0-9-]{1,40}$
     "ref": "…≤200" | null,                   // texto libre (p. ej. «aviso:2»); NUNCA un enlace por sí mismo
     "enlace": "https://…" | null}            // = ref solo si es http(s) bien formado: el único campo que puede ser un <a href>
  ],
  "resumen": {"dia": "2026-10-09", "leyo": 6, "propuso": 5, "escribio": 0, "descarto": 2, "fallo": 1, "aviso": 3,
              "por_fuente": {"wa": {"leyo": 2, "propuso": 1, …}, …}}  |  null,
  "total": 16,           // items devueltos
  "omitidos": 0,         // entradas del vigía que no pasaron la validación (campo raro, fuente desconocida…) y se descartaron
  "hay_mas": false       // true si llegaron tantas como las pedidas (n): puede haberse cortado; pide más con n mayor
}
```

* `resumen` es el del **día entero**, no el del filtro (así «Hoy leí… propuse…» no cambia al filtrar). Es `null` si el vigía no lo mandó completo: el front no debe calcular uno propio.
* Un día sin actividad es `ok:true`, `items:[]` y `resumen` con ceros: eso sí es «no pasó nada».
* Error de lectura: `{"ok": false, "error": "el vigía tardó demasiado en contestar" | "no encuentro el comando del vigía (zv)" | "el vigía contestó algo que no entiendo" | "el vigía contestó con demasiados datos" | "el vigía no pudo hacerlo" | "el vigía está ocupado; …", "items": [], "resumen": null, "dia", "filtros", "n_pedido"}`.

## 2. `GET /api/flujos`

Llamada a `zv`: `flujos --json`. Además se lee, solo lectura, el interruptor general del vigía (ficheros `PAUSA` y `ENTREGA_ACTIVA` y `modo` de `config.json`).

```jsonc
{
  "ok": true,
  "flujos": [
    {"id": "correo-plazo", "nombre": "…≤80", "descripcion": "…≤240",
     "fuente": "correo" | null, "acciones": ["tarea", "evento", "aviso"],     // ≤8, cada una ^[a-z_-]{1,20}$
     "modo": "sombra" | "activo", "pausado": false,
     "ultimo": "2026-10-09T10:05:00+02:00" | null,       // null = nunca ha disparado
     "disparos_7d": 12 | null,                           // null = dato raro; 0 = de verdad ninguno
     "efectivo": "prueba" | "vivo" | "pausado" | "desconocido",
     "motivo": "el interruptor general del vigía está apagado" | … | null}    // por qué un flujo «activo» sigue sin escribir
  ],
  "general": {"pausa": false, "entrega_real": false, "modo": {"wa": "sombra", "correo": "sombra", "agenda": "activo"}} | null,
  "omitidos": 0           // flujos del vigía descartados por tener id o modo no válidos o estar repetidos
}
```

* `efectivo` aplica la regla del vigía: **PAUSA ausente + ENTREGA_ACTIVA + modo de la fuente `activo`** (y flujo no pausado) ⇒ `vivo`; si el flujo está en `activo` pero falla alguna, es `prueba` y `motivo` dice cuál. `desconocido` = no se puede afirmar (no se pudo leer el interruptor general, o la fuente del flujo no tiene interruptor propio: `tareas`, `sistema`).
* Fallo: `{"ok": false, "error": "…", "flujos": [], "general": null}` (200).

## 3. `POST /api/flujos/<id>`

`<id>` debe cumplir `^[a-z0-9-]{1,40}$` (si no: `400`). Un id bien formado que el vigía no lista → `404 {"error":"ese flujo no existe"}` (se comprueba con `zv flujos` **antes** de escribir).

Cuerpo:

| `accion` | extra | llamada a `zv` |
|---|---|---|
| `"pausa"` | – | `flujo <id> pausa` |
| `"reanuda"` | – | `flujo <id> reanuda` |
| `"modo"` | `"modo":"sombra"` | `flujo <id> modo sombra` |
| `"modo"` | `"modo":"activo"` y **`"confirmo": true`** (booleano estricto) | `flujo <id> modo activo --confirmo` |

* `modo:"activo"` sin `confirmo:true` → `400 «Para pasar un flujo a Activo hay que confirmarlo»` y no se llama a `zv`. Solo el rol `admin` puede (el resto no llega ni a la ruta: `403`).
* Respuesta `200`: `{"ok": true, "flujo": {…como en GET…}, "general": {…}}` — el flujo se vuelve a leer del vigía tras el cambio (nunca se inventa el estado). Si el cambio se envió pero no se pudo comprobar: `502 «el cambio se envió al vigía pero no he podido comprobarlo; recarga la lista»`.
* Errores: `400` (id, acción, modo o cuerpo no válidos, cuerpo que no es un objeto o de más de 4 KB), `403`, `404`, `502 «el vigía no pudo hacerlo»`, `503` (sin `zv` / ocupado), `504 «el vigía tardó demasiado en contestar»`. Forma: `{"error": "frase en español"}`.
* Los cambios van de uno en uno (cerrojo). El Hub **no escribe nunca en Google**: eso solo lo hace el vigía y solo si el interruptor general lo permite.

## Qué depende del vigía real

* Que `zv registro --json`, `zv flujos --json` y `zv flujo …` existan con la forma del contrato (el Hub las ha probado contra `tests/fakezv.py`, no contra el `zv` real).
* Que `zv flujo <id> modo activo` rechace sin `--confirmo` (el Hub ya lo exige, pero el CLI es la segunda barrera).
* Si el vigía añade valores nuevos a `fuente`, `tipo`, `modo` o `actor`, el Hub **descarta esa entrada** (cuenta en `omitidos`) hasta que se amplíen las listas cerradas de `registro.py` y del front.
