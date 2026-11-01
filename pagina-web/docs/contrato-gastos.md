# Contrato «Gastos y suscripciones» (tablero «Suscripciones» de la app)

Rama `gastos`. Dos partes: lo que el Hub **recibe del vigía** (`zv suscripciones --json` y `zv gastos --json`, los construye el vigía en `zv/gastos.py`) y lo que el Hub **ofrece a la app**
(el tablero `suscripciones` dentro de `GET /api/tableros` y `GET /api/tableros/suscripciones`). Código del Hub: `gastos.py`; se engancha en `panel.ctx_tableros` y `tableros._tablero_suscripciones`.

## Reglas generales

* **Solo lectura y solo Fran.** No hay ninguna ruta que escriba. Una invitada recibe `403 {"error":"no disponible"}` (el guard de `/api/tableros*` ya lo hace).
* **Lista cerrada de comandos.** El Hub solo lanza `zv suscripciones --json` y `zv gastos --json [--mes AAAA-MM]` (el mes se valida con `^\d{4}-\d{2}$`). Con lista de argumentos
  (sin shell), entorno mínimo, stdin cerrado, tiempo máximo (`HUB_GASTOS_T`, 6 s por defecto) y tope de 1,5 MB de salida, como `registro.py` (comparte su tubería y su límite de 4 `zv` a la vez).
  Nunca lanza `zv gastos recalcular`.
* **El Hub no calcula nada.** Ni importes, ni totales, ni fechas de cobro. Enseña lo que dice el vigía, validado campo a campo: listas cerradas (estado, periodo, moneda, base…), números finitos
  entre 0 y 10⁷ con 2 decimales, fechas ISO reales, textos limpios (sin saltos de línea ni caracteres de control o de dirección) y recortados. Lo que no pasa la validación se descarta o queda en `null`
  (nunca un «0 €»). Los «días hasta el cobro» se cuentan con el reloj del Hub a partir de la fecha. El front pinta todo como texto, jamás como HTML.
* **Un fallo se dice, no se disfraza de «nada».** Si no se pueden leer las suscripciones, el tablero sale con `ok:false` y el motivo en español (no se repite el texto de error del CLI: podría llevar
  rutas o datos). Si solo fallan los gastos del mes, el tablero sigue y `gastos` lleva `{"ok":false,"error":…}`.
  Motivos: «el vigía tardó demasiado en contestar», «no encuentro el comando del vigía (zv)», «el vigía contestó algo que no entiendo», «el vigía contestó con demasiados datos»,
  «el vigía no pudo hacerlo», «el vigía todavía no sabe de gastos: falta actualizarlo» (un `zv` anterior a este cambio).
* **Lectura inicial.** Mientras el vigía no ha terminado de leer los últimos 90 días de correo, `estado.fase` es `inicial` y la app avisa de que las cifras pueden estar incompletas.

## 1. Lo que dice el vigía

### `zv suscripciones --json`

```jsonc
{"ok": true, "hoy": "2026-10-10",
 "items": [{"nombre": "Spotify", "comercio": "spotify", "importe": 11.99, "moneda": "EUR",       // importe: el actual (último cobro si cambió el precio, si no la mediana); null si solo hay pista de la agenda sin importe
            "periodo": "mensual",                                                                    // semanal | mensual | trimestral | anual | null (solo agenda)
            "mensual": 11.99, "anual": 143.88,                                                       // equivalentes; null si no hay periodo
            "ultimo_cobro": "2026-10-03", "proximo_cobro": "2026-11-03", "dias_para_cobro": 24,
            "proximo_fuente": "estimado",                                                            // estimado | recibo (lo decía el propio recibo) | agenda (pista del calendario)
            "estado": "activa",                                                                      // activa | nueva | posible_cancelada | solo_agenda
            "cancelar": false,                                                                       // está en suscripciones.cancelar de la config de Fran
            "cargos": 3, "base": "correo",                                                           // base: correo | agenda | correo+agenda
            "categoria": "suscripciones", "cuenta": "varas", "subida_pct": null}],                   // subida_pct: % de subida del último cobro frente al anterior (solo si >0)
 "n": 1,
 "totales": {"EUR": {"mensual": 11.99, "anual": 143.88, "n": 1}},                                    // solo activas y nuevas, por moneda
 "estado": {"fase": "al_dia", "cuentas_leidas": 2, "cuentas": 2, "pendientes": 0, "desde": "2026-07-12", "ultima_lectura": "2026-10-10T09:00:12+02:00", "habilitado": true}}
```

Detección: ≥2 cobros del mismo comercio y moneda con importe parecido (×1,35) y separación semanal (≥3 cobros), mensual, trimestral o anual. «Posible cancelada»: sin cobro desde hace más de dos
periodos. «Nueva»: 2 cobros y el primero hace ≤75 días. Los eventos «💳 …» y «Renovación suscripción …» del calendario (solo título y fecha) afinan el próximo cobro o, si no hay correo, la dejan
«solo_agenda» (sin periodo ni coste mensual: no suma a los totales).

### `zv gastos --json [--mes AAAA-MM]`

```jsonc
{"ok": true, "mes": "2026-10", "hoy": "2026-10-10",
 "totales": {"EUR": {"cargos": 925.65, "reembolsos": 0.0, "neto": 925.65, "n": 15}, "USD": {…}},
 "total_eur": 925.65,                       // EUR + las monedas con tipo de cambio en gastos.cambio de la config; si no hay tipo, NO se convierten
 "sin_convertir": {"USD": 24.99},
 "por_categoria": [{"categoria": "vivienda", "moneda": "EUR", "importe": 711.9, "importe_eur": 711.9, "n": 3}],     // importe_eur: null si no se puede pasar a euros
 "por_comercio": [{"comercio": "Alquiler", "moneda": "EUR", "importe": 650.0, "importe_eur": 650.0, "n": 1, "categoria": "vivienda"}],
 "items": [{"id": 1, "fecha": "2026-10-03", "comercio": "Spotify", "importe": 11.99, "moneda": "EUR", "tipo": "renovacion", "categoria": "suscripciones", "cuenta": "varas"}],   // el Hub no lo usa
 "mes_anterior": {"mes": "2026-09", "total_eur": 840.2, "sin_convertir": {}, "total_eur_a_esta_altura": 702.5},       // a_esta_altura: solo para el mes en curso
 "sin_clasificar": 1, "dudosos": 2,        // los dudosos (¿cargo o publicidad?, importe enorme, comercio desconocido) NO suman
 "presupuesto": {"tope_activo": false, "tope": null, "usado": 925.65, "topes_categoria": {}},
 "estado": {…}}                              // igual que arriba
```

Errores: `{"ok": false, "error": "…"}` con código 2 si el mes no es AAAA-MM; un código distinto de 0 o `ok` distinto de `true` es un fallo para el Hub.

## 2. Lo que ofrece el Hub

`GET /api/tableros` (y `/api/tableros/suscripciones`) incluye el tablero:

```jsonc
{"id": "suscripciones", "titulo": "Suscripciones", "tipo": "lista", "ok": true, "total": 8, "nota": null,        // nota: texto si no hay ninguna («todavía estoy leyendo tu correo…» o «no he detectado suscripciones…»)
 "items": [{"nombre": "Spotify", "importe": 11.99, "moneda": "EUR", "periodo": "mensual", "mensual": 11.99, "anual": 143.88,
            "proxima_fecha": "2026-11-03", "dias": 24, "ultimo_cobro": "2026-10-03", "proximo_fuente": "estimado", "estado": "activa",
            "cancelar": false, "cargos": 3, "base": "correo", "categoria": "suscripciones", "cuenta": "varas", "subida_pct": null}],   // ≤200, sin duplicados (nombre+moneda)
 "totales": {"EUR": {"mensual": 11.99, "anual": 143.88, "n": 1}},
 "estado": {"fase": "al_dia" | "inicial" | null, "pendientes": 0, "ultima_lectura": "…" | null, "desde": "2026-07-12" | null, "cuentas_leidas": 2, "cuentas": 2},
 "gastos": {"ok": true, "mes": "2026-10", "total_eur": 925.65, "sin_convertir": {"USD": 24.99},
            "por_categoria": [{"categoria": "vivienda", "moneda": "EUR", "importe": 711.9, "importe_eur": 711.9, "n": 3}],       // ≤12
            "por_comercio": [{"comercio": "Alquiler", "moneda": "EUR", "importe": 650.0, "importe_eur": 650.0, "n": 1}],         // ≤5
            "anterior": {"mes": "2026-09", "total_eur": 840.2, "total_eur_a_esta_altura": 702.5},
            "sin_clasificar": 1, "dudosos": 2, "presupuesto": {"tope_activo": true, "tope": 1000.0, "usado": 925.65}, "estado": {…}}
           | {"ok": false, "error": "el vigía tardó demasiado en contestar"}}
```
Con `ok:false` en el tablero: `{"id", "titulo", "tipo": "lista", "ok": false, "error": "…", "items": [], "total": 0}`.

## 3. La pantalla

Tablero «Suscripciones» (solo lectura, `web/src/panel/Tableros.tsx`): arriba **Gastos de <mes>** (total, comparación con el mes anterior —«a estas alturas llevabas…»—, tope si está activo,
barras por categoría, avisos de «sin clasificar / dudosos» y de «sin convertir»); debajo la lista agrupada: **Para cancelar** (destacado, con la etiqueta de texto «PARA CANCELAR»), **Próximas
renovaciones**, **Solo en tu agenda** y **Posiblemente canceladas**. Etiquetas: NUEVA, SUBE n %, SOLO AGENDA, ¿CANCELADA?, YA NO COBRAN. En la lista de tableros: «5 activas · 54,45 € al mes · 2 para cancelar».
`?demo=1` (y `&caso=vacio|parcial`) muestra datos de ejemplo.
