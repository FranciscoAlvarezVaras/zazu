# 04 · Oficina: documentos, notas, tareas, calendario y correo

Informe 04 · 10-oct-2026 · Para Fran · Escrito por una IA tras leer el código de Odysseus (rama main v1.0.3, commit 934d23c, solo lectura).
No es asesoría legal. Nada de Odysseus se ha ejecutado ni instalado; nada se ha instalado en `~/.hermes`.

---

## 0. Lo esencial (leer esto basta)

**Qué he encontrado, en una frase.** Odysseus tiene muchas funciones de oficina, pero tu Hermes ya cubre casi todas con más cuidado (vigía, bandeja, `agenda-y-tareas`, flujos de correo con reglas en español, Cerebro). Lo que de verdad te falta es poco y concreto, y Odysseus solo aporta *ideas* para ello (su código está pensado para inglés y tiene fallos de calendario conocidos que no te conviene heredar).

**Mis 3 recomendaciones** (cada una ya tiene un borrador de skill probado con pruebas automáticas, sin instalar):

| # | Skill borrador | Qué te da | Valor | Esfuerzo | Riesgo |
|---|---|---|---|---|---|
| 1 | `fechas-y-recurrencias-es` | Que «el martes a las 5 de la tarde», «el último viernes de octubre» o «cada martes y jueves hasta el 20 de diciembre» se conviertan en fechas exactas **sin que el modelo haga la cuenta a ojo**, con aviso del cambio de hora del 25-10, y que puedas crear eventos que se repiten (hoy `agenda-y-tareas` no los contempla). | 4 | M (hecho) | Bajo |
| 2 | `edicion-segura-documentos` | Copia numerada antes de que Hermes cambie un archivo, edición por bloques «busco esto → pongo esto» **primero en simulación**, ver qué cambió y volver atrás en un paso. No borra nada. | 3 | S (hecho) | Bajo |
| 3 | `correo-limpio-es` | Leer hilos largos de correo gastando bastantes menos tokens (quita citas, firmas y avisos legales, también en español) y una tabla de quién te manda solo publicidad. Solo lectura. | 3 | S (hecho) | Bajo |

**Decisiones que te tocan a ti**
1. ¿Instalo las tres en tu perfil principal (`~/.hermes/skills/productivity/`) después de que las pruebes en un perfil de pruebas? Recomendado: sí, una a una, empezando por la 1.
2. ¿Quieres que `agenda-y-tareas` llame a `fecha.py` en su paso 2 («Crear el evento»)? Es un cambio de 3 líneas en una skill tuya (texto sugerido en 6.2). Sin tu «sí» no lo toco.
3. ¿Usas de verdad el calendario de Nextcloud (CalDAV)? Si no, **no merece la pena** traer el código de sincronización CalDAV de Odysseus (ver 3, idea O10).
4. ¿Guardamos una vez tu «estilo de escritura» (sacado de tus correos enviados) para no recalcularlo en cada borrador? Es la idea O4; ahorra tokens, pero es un dato personal y quiero tu permiso antes de leer tus enviados.

**Qué NO copiar de Odysseus** (y por qué): su calendario guarda las horas en UTC y tiene abiertos justo los fallos que te afectarían en España (series que se desplazan una hora con el cambio de hora, eventos de día entero un día antes si estás al este de UTC, borrado de excepciones al sincronizar). Su limpieza de documentos *borra* de verdad. Su respuesta automática de ausencia y su gestor de contraseñas son de riesgo alto. Detalle en las secciones 3 y 5.

---

## 1. Cómo lo he mirado

- Código: `routes/calendar_routes.py`, `src/caldav_sync.py`, `src/caldav_writeback.py`, `routes/document/*`, `src/agent_tools/document_tools.py`, `src/document_actions.py`, `routes/email_routes.py`, `routes/email_helpers.py`, `routes/email_pollers.py`, `src/email_thread_parser.py`, `routes/note/note_routes.py`, `src/tools/{notes,calendar,contacts,vault}.py`, `src/task_scheduler.py`, `routes/task/task_routes.py`, `src/builtin_actions.py`, `routes/contacts/*`, `routes/vault/*`. Los números de línea de abajo son aproximados.
- Lo tuyo: skills `agenda-y-tareas` (y su `comprobar.py`), `email-inbox-triage`, `document-to-action-items`, `weekly-review-planning`; `zazu-vigia` (`correo.py`, `reglas.py`, `extraer.py`, `flujos.py`) y `zazu-bandeja`; `cerebro-ordenar.py`; `zgog` (gogcli v0.41, solo leí su ayuda).
- Madurez: tests del repo (`tests/`), y las incidencias abiertas de GitHub leídas hoy a través de una herramienta de lectura web que resume la página (por tanto **cifras aproximadas y a confirmar**).
- Tras leer cada idea, **escribí el borrador desde la idea, sin copiar**. Comprobación de copia literal con el método de la checklist (secuencias de 8 palabras): 8 coincidencias en total entre las tres skills y 15 archivos de Odysseus, todas código estándar (importaciones, `super().__init__`, una expresión de RFC). Cada skill lleva su `NOTICE`.
- El linter de Hermes (solo lectura) da a las tres los mismos 2 avisos de formato que da a tus skills ya instaladas (es una limitación de su lector de YAML); ningún aviso de contenido.

**Madurez general de Odysseus (para ponderar):** proyecto de un mantenedor principal que se describe a sí mismo como en movimiento rápido («SQUASH BUGS» es su prioridad nº 1, `ROADMAP.md`). 812 archivos de tests (calendario/CalDAV 29, correo 39, documentos 21, notas/tareas/recordatorios 35, contactos/vault 8): casi todos son pruebas de regresión de fallos concretos, lo cual es buena señal de que lo que cubren funciona, pero también de cuántos fallos ha habido. Incidencias abiertas hoy: unas 1.150 en total; la búsqueda de «calendar/caldav/recurring» devuelve ~135 y la de «email/imap/smtp» ~220 (incluyen falsos positivos). Su propia hoja de ruta reconoce que el correo va lento y que «Notas y tareas» necesitan mejor integración con la IA.

---

## 2. Lo que ya tienes (para saber qué falta de verdad)

| Área | Ya existe en tu Hermes | Hueco real |
|---|---|---|
| Agenda y tareas | `agenda-y-tareas` (reglas de zona Europe/Madrid, día entero = día siguiente, tarea gemela, comprobar duplicados, releer) | Convertir frases relativas a fecha de forma determinista; **eventos que se repiten**; aviso de **solape de horarios** (`comprobar.py` busca parecidos, no choques) |
| Fechas en textos de terceros | `zv/extraer.py` (fechas absolutas, horas, importes en español, sin adivinar) | No resuelve lo relativo («el martes», «dentro de 3 días») ni repeticiones |
| Correo | vigía (reglas: seguridad, cargos, oficial, entrevista, dinero; juicio del modelo solo si es ambiguo), flujos (`correo-plazo`, `correo-pago`, `viaje-reserva`…), `email-inbox-triage` | Quitar citas/firmas (ahorro de tokens); clasificar por cabeceras; estilo de escritura guardado |
| Documentos | `docx`, `pdf`, `xlsx`, `markitdown-uv`, `document-to-action-items` | Copia/versión **antes** de editar y volver atrás (el Cerebro tiene `.stversions` de Syncthing; lo demás, no) |
| Notas | Cerebro + `cerebro-ordenar.py` (archiva, no borra) | Detector de duplicados (solo informe) |
| Tareas programadas | cron de Hermes (con `[SILENT]` cuando no hay nada que contar), rutinas, timers del vigía | Nada que merezca copiarse |
| Nextcloud | instalado en local | Ninguna integración CalDAV/CardDAV en Hermes (no la he visto necesaria) |

---

## 3. Fichas de ideas

Formato: (1) qué hace y cómo, con rutas y líneas · (2) qué tienes ya y qué falta · (3) ¿recreable como skill/script?, qué serviría casi tal cual y qué hay que reescribir (AGPL: solo fragmentos pequeños o genéricos; en la práctica he reescrito todo desde la idea) · (4) valor 1-5, esfuerzo S/M/L, riesgo · (5) madurez.

### O1 · Fechas en lenguaje natural y recurrencias (RRULE) · **Borrador hecho**
1. **Qué hace.** `routes/calendar_routes.py`: `_parse_dt` (~491-621) y `parse_due_for_user` (~360-464) interpretan frases por capas (hoy/mañana, «próximo lunes», «dentro de N horas», hora suelta) y, si fallan, usan `dateutil`. `_expand_rrule` (~686-800) expande una regla RRULE solo dentro de una ventana, con tope de 1.000 apariciones, exclusiones (EXDATE) y un identificador compuesto por aparición. Hay fallos corregidos con prueba: un `UNTIL=…Z` con inicio sin zona convertía una serie en un evento suelto (`tests/test_calendar_rrule_until_utc.py`); un evento de duración cero desaparecía (`_ensure_positive_duration`, ~41-55; `tests/test_calendar_import_zero_duration.py`). `quick_parse` (~1619-1775) es la versión con IA (una frase → JSON).
2. **Tienes / falta.** Tienes las reglas de zona y día entero en `agenda-y-tareas` y `extraer.py` para fechas escritas en correos. Falta: resolver lo **relativo** («el martes», «el último viernes de octubre», «a las 6 menos cuarto») sin depender del cálculo mental del modelo; crear **series repetidas** (`zgog calendar create --rrule` existe, pero nadie genera ni verifica la regla); avisar del cambio de hora.
3. **Recreable.** Sí, como script (`fecha.py`) + skill. **Nada serviría tal cual:** el parser de Odysseus solo entiende inglés. Se aprovecha la *idea* de las capas, el tope de apariciones y las lecciones de UNTIL/duración. Reescrito: parser en español, RRULE a partir de frases, vista previa de fechas, cálculo con hora de reloj de Madrid (**no** en UTC: la expansión de Odysseus sobre horas guardadas en UTC se desplaza una hora tras el cambio, incidencia abierta nº 6512), y negarse a adivinar. Comprobado en Python con una simulación mía de ambos enfoques (no con su código): una serie semanal «sábados a las 09:00» sale a las 09:00 locales el 31-10, mientras que el enfoque UTC sale a las 08:00.
4. **Valor 4, esfuerzo M, riesgo bajo** (solo calcula; crear sigue pasando por `agenda-y-tareas` y su aprobación). No he medido cuántas veces lo pides; no he leído tus conversaciones.
5. **Madurez de la idea en Odysseus:** cobertura razonable de la expansión (21 pruebas de recurrencia/RRULE), pero las incidencias abiertas apuntan justo aquí (nº 6512 series importadas que derivan con el cambio de hora y caen en el día de la semana equivocado; nº 6290 eventos de día entero un día antes al este de UTC; nº 6340 se pierden las excepciones al escribir en CalDAV). **Mi borrador:** 21 pruebas automáticas pasan; falta probarlo con ~20 frases reales tuyas.

### O2 · Versiones, edición por bloques y «sugerencias» · **Borrador hecho**
1. **Qué hace.** `routes/document/document_routes.py` `update_document` (~623-696): cada guardado es una versión completa con su origen (`user` o `ai`); guardados de la persona en menos de 60 s se funden (const. ~621); `restore_version` (~811-850) **crea una versión nueva** en vez de borrar historia. `src/agent_tools/document_tools.py`: `parse_edit_blocks` (~256) y `EditDocumentTool` (~560-712) aplican bloques FIND/REPLACE (cuenta aplicados y omitidos; reintenta quitando el «número de línea + tabulador» que se cuela al copiar); `parse_suggest_blocks` (~264-285) y `SuggestDocumentTool` (~714-760) generan **sugerencias que no modifican** el documento (con motivo, descartando las «sin cambios»); `_approved_document_version_error` (~84-120) rechaza una acción ya aprobada si el documento cambió entretanto (versión + huella).
2. **Tienes / falta.** Tienes `docx`, `pdf`, `xlsx` para editar y, en el Cerebro, el historial de Syncthing. Falta una red de seguridad común para *cualquier* archivo: copia previa, simulación, deshacer, y detección de «cambió mientras se aprobaba» (con Syncthing moviendo ficheros, pasa).
3. **Recreable.** Sí (`versiones.py`, solo biblioteca estándar). La **idea** sirve entera (versión por edición con origen, restaurar sin destruir, fundir ediciones seguidas, bloques, huella para detectar cambios, quitar números de línea). Reescrito: sirve para archivos sueltos y binarios, simulación por defecto, un BUSCAR repetido se rechaza (Odysseus cambia la primera aparición sin avisar), jamás borra, copias fuera del Cerebro, rechaza archivos con claves.
4. **Valor 3** (4 para documentos fuera de lo sincronizado), **esfuerzo S, riesgo bajo/medio** (`--aplicar` y `restaurar --aplicar` escriben en el archivo: van tras tu «sí»; las copias no se borran nunca).
5. **Madurez Odysseus:** 21 tests de documentos, pero son de permisos/dueño, PDF y pantalla; **no hay pruebas directas** de la edición por bloques ni de la fusión/restauración de versiones (solo aparecen como piezas simuladas en pruebas de seguridad). **Mi borrador:** 13 pruebas pasan (simulación, aplicar+restaurar, ambiguo, huella ajena, números de línea, stdin).

### O3 · Correo: quitar citas/firmas y clasificar por cabeceras · **Borrador hecho** (dos mitades)
1. **Qué hace.**
   - *Hilos* (`src/email_thread_parser.py`, 614 líneas): separa los turnos citados de un mensaje usando atribuciones («On … wrote:»), bloques Outlook («De:/Enviado:/Asunto:», con tablas en ~20 idiomas, líneas ~35-80), separadores «Original Message», citas `>` (texto plano ~257-390) y `<blockquote>` (HTML ~432-603). **Detalle clave:** en texto plano la línea de atribución debe empezar por «On …», así que el «El jue, 8 oct 2026 a las 10:11, Ana <…> escribió:» de Gmail en español **no se reconoce**; con HTML sí (se apoya en `<blockquote>`). Solo hay tests de entrada no válida y de «reenviado».
   - *Boletines* (`routes/email_routes.py`): `_parse_list_unsubscribe_header` (~546-595) y `_email_unsubscribe_candidate_from_msg` (~597-617) puntúan por cabeceras (List-Unsubscribe +45, List-Id +20, Precedence bulk/list +20, Auto-Submitted +10, spam previo +35); `_dedupe_unsubscribe_candidates` (~632) agrupa por lista; `scan` (~2525-2583) es solo revisión; `execute` (~2604-2675) envía el correo de baja solo si la cabecera es `mailto:` y **nunca abre enlaces web**; `cleanup` (~2677) mueve a Junk/Trash. `_sender_is_automated` (`email_pollers.py` ~230-245) usa las mismas cabeceras.
2. **Tienes / falta.** El vigía descarta ruido por **palabras del asunto/remitente** (`RUIDO`, `NO_HUMANO`) y protege seguridad, cargos y oficiales; `email-inbox-triage` lee hilos completos. No hay nada que quite citas (ahorro de tokens) ni que mire cabeceras ni que te diga «de quién recibes más publicidad».
3. **Recreable.** Sí (`correo.py`, biblioteca estándar). La **idea** de puntuación sirve casi tal cual (son hechos del estándar de correo); el analizador de hilos hay que **reescribirlo para español** (atribución «El … escribió:» incluso partida en dos líneas, cabeceras De/Enviado/Para/Asunto, avisos legales, «Enviado desde mi iPhone», HTML de Gmail y de Outlook web). Mi versión añade una red: si al limpiar no queda texto, devuelve el original; y marca como «protegido» seguridad, cargos y organismos oficiales. **No ejecuta bajas.**
4. **Valor 3 (limpiar hilos) y 2 (boletines), esfuerzo S, riesgo bajo** (solo lectura). La baja por correo sería enviar un correo en tu nombre: no incluida.
5. **Madurez Odysseus:** unsubscribe 4 tests; hilos casi sin tests; urgencia 20 tests; incidencias abiertas: el borrado en bloque puede borrar para siempre si Trash rechaza el movimiento (nº 6632), la lista local muestra correos viejos (nº 6602), sin freno contra servidores IMAP/SMTP internos (nº 6352). **Mi borrador:** 19 pruebas pasan con correos inventados. **Pendiente:** confirmar el formato de salida de `zgog gmail get --format=metadata --headers=… --json` con UN mensaje real (leí solo la ayuda; el script busca las cabeceras donde estén) y medir el ahorro real de tokens (no lo he medido).

### O4 · Estilo de escritura guardado y reglas para borradores
1. **Qué hace.** `routes/email_routes.py` `extract-style` (~4774-4881): lee ~20 correos enviados y pide a un modelo un párrafo de estilo («saludo, despedida, longitud, giros»), que se guarda y se añade a cada borrador. `email_helpers.py` `_EMAIL_REPLY_SYS_PROMPT_BASE` (~1948-1980): reglas de borrador (el estilo guardado manda; **escribir solo como el dueño del buzón**; **no inventar** datos que no estén en el correo ni el contexto; no rellenar con «te contesto pronto»; texto final entre marcadores para extraerlo sin ruido, `_extract_reply` ~253-278). `_pre_retrieve_context` (~1785-1944): antes de redactar, busca correos y contactos previos **solo si el remitente ya es conocido** (defensa contra que un desconocido arrastre datos privados a la respuesta).
2. **Tienes / falta.** `email-inbox-triage` pide calibrar el tono con 20-50 enviados **en cada ejecución** (gasta tokens y varía). Falta: guardarlo una vez, y las reglas de identidad / no inventar / «solo remitentes conocidos» para el contexto.
3. **Recreable.** Como mejora de texto de la skill existente (no hace falta script): perfil de estilo en una nota del Cerebro (30 Notas), sin direcciones ni teléfonos, y 3-4 reglas de redacción. Reescribir desde la idea.
4. **Valor 3, esfuerzo S, riesgo bajo** (borradores; la privacidad del perfil de estilo es lo único a cuidar). Requiere tu permiso para leer los enviados.
5. **Madurez Odysseus:** media; incidencias abiertas de respuestas en blanco con modelos locales (nº 6423) y de que «AI Reply» acepta texto de planificación como respuesta (nº 6516).

### O5 · Aviso de solape de horarios (hueco tuyo; Odysseus aporta solo la regla de solape)
1. Odysseus no avisa de choques al crear un evento. Su única aportación útil: la regla de solape correcta, «empieza antes de que acabe lo otro **y** acaba después de que empiece» (`list_events`; `tests/test_calendar_cli_overlap.py`), que incluye lo que ya empezó antes de la ventana.
2. `comprobar.py` busca eventos *parecidos* (título) en ±3 días, pero no dice «a esa hora ya tienes X».
3. Mejora pequeña a `comprobar.py` (parámetro de horas y la regla de solape). **No es una skill nueva.**
4. Valor 3, esfuerzo S, riesgo bajo. 5. No aplica.

### O6 · Importar invitaciones .ics a Google
1. `import_ics` (`calendar_routes.py` ~1411-1559) y `export_ics` (~1561-1617): lee VEVENT, normaliza a UTC, deduplica por (título, inicio) al reimportar, corrige finales no positivos, escapa texto según RFC 5545 (`_ics_escape` ~107-122). Tiene errores arreglados con tests (duplicados de TZID, series con UNTIL en UTC).
2. Tienes que un `.ics` adjunto (médico, reserva, evento) hay que traducirlo a mano. No hay lector de `.ics`.
3. Recreable como script (parser mínimo `.ics` con la biblioteca estándar: desplegar líneas, TZID → Madrid, DTEND exclusivo en día entero, duración cero → 1 h / 1 día, RRULE → vista previa de O1) que proponga el comando `zgog`. Reescribir todo.
4. Valor 3, esfuerzo M, riesgo medio (crea eventos; duplicados; el contenido del `.ics` es dato de terceros). Recomendado hacerlo **después** de O1.
5. Madurez Odysseus: 6 tests específicos de importación; funciona, pero guarda en UTC con los problemas de arriba.

### O7 · Clasificar eventos por tipo e importancia
1. `src/builtin_actions.py` ~1300-1510: primero palabras clave (salud, viaje, comida, social, gestiones, trabajo; «vuelo», «entrevista»… = alta), y el modelo solo para los dudosos, en lotes de 10, con memoria personal como contexto.
2. Tienes: nada equivalente (el color/tipo lo pones tú). `weekly-review-planning` podría usarlo.
3. Recreable como lista de palabras en español dentro de la revisión semanal; no hace falta la parte del modelo. Reescribir.
4. Valor 2, esfuerzo S, riesgo bajo. 5. Un test (que la memoria llegue al clasificador).

### O8 · Extraer reservas desde el correo, actualizando o cancelando lo que ya existe
1. `email_pollers.py` ~866-1100: el modelo recibe el correo **y** los 40 eventos de los próximos 60 días y devuelve `crear / actualizar / cancelar`; conserva «identificadores» (localizador, nº de vuelo, puerta, código de seguimiento…) con expresiones regulares de respaldo (~1004-1050).
2. Tienes: el vigía ya hace esto **con reglas deterministas y eventos tentativos** (`flujos.py`: `viaje-reserva`, `correo-oficial`, `entrevista`) y es más prudente. Falta: **actualizar o cancelar** un evento que ya existe cuando llega el cambio, y guardar el localizador en la descripción.
3. No traer la parte de Odysseus que *cancela* o *cambia* eventos por lo que dice un correo (un tercero movería tu agenda): solo como **propuesta** para tu aprobación. Reescribir en español dentro del flujo existente (cambio del vigía, no skill).
4. Valor 3, esfuerzo M, riesgo medio-alto si actuara solo; bajo como propuesta.
5. Madurez: la incidencia nº 6398 indica que las revisiones periódicas no recogen bien el correo.

### O9 · Detector de duplicados de documentos/notas
1. `src/document_actions.py` (~53-197): título normalizado + «huella» del contenido (sin ids volátiles); conserva el más completo. **Pero borra de verdad.**
2. `cerebro-ordenar.py` no detecta duplicados (lo he buscado).
3. Solo como **informe** (nunca borrar: en el Cerebro se archiva, ver `AGENTS.md`). Reescribir.
4. Valor 2, esfuerzo S, riesgo bajo si solo informa. 5. Hay test de timestamps nulos.

### O10 · Cliente CalDAV/CardDAV (Nextcloud)
1. `src/caldav_sync.py` (722 líneas) y `src/caldav_writeback.py` (311): sincronización de ida (90 días atrás, 1 año adelante), escritura de vuelta, validación de URL contra SSRF (~51-130), sin redirecciones, caso especial de Google (~185-218), «no podar si hubo fallo de lectura» (~257-269). Usa las librerías `caldav` e `icalendar` (**no están instaladas** en tu Python).
2. Tienes Google como fuente de verdad; Nextcloud no está conectado a Hermes.
3. Recrearlo con la biblioteca estándar es posible (PROPFIND/REPORT), pero es L y escribe credenciales. Aprovechable solo como lista de cautelas.
4. Valor 2 (hoy), esfuerzo L, riesgo medio-alto. **No recomendado** salvo que uses Nextcloud como agenda.
5. 57 tests de CalDAV (sincronización, escritura, seguridad de URL), pero con fallos abiertos como los citados (nº 6340, nº 6290, nº 6464 autenticación).

### O11-O14 · Descartadas o ya cubiertas
- **O11 Recordatorios de notas** (`note_routes.py` `dispatch_reminder` ~140-575; evita repetir el aviso en 25 min; canales navegador/correo/ntfy/webhook; `tools/notes.py` evita recordatorios duplicados por título+hora): Google Tasks + cron de Hermes ya lo hacen; valor 1.
- **O12 Tareas programadas del agente** (`task_scheduler.py`: cálculo de próxima ejecución con clamp de fin de mes ~113-230, encadenadas con detección de ciclos ~2159, disparo «cada N documentos»; `routes/task/task_routes.py` `/parse` ~1089-1181 convierte una frase en tarea programada y **solo devuelve borrador**): el cron de Hermes ya tiene `[SILENT]` y blueprints; valor 1-2. De rescatar: el principio «lo interpretado se enseña como borrador».
- **O13 Respuesta automática de ausencia** (`email_pollers.py` ~146-370; periodo, enfriamiento por remitente, excluye automáticos): envía correo solo; Gmail ya tiene respuesta de vacaciones nativa. **Descartar.**
- **O14 Vault (Bitwarden)** (`src/tools/vault.py`, `routes/vault/*`): contraseñas con una herramienta del agente. **Descartar** (tus reglas prohíben claves en el Cerebro y el riesgo es alto).
- También ya cubierto: la cola «el agente deja el correo en borrador y tú lo apruebas» (`email_routes.py` ~4406-4468) equivale a tu aprobación por hook + `--gmail-no-send` de `zgog`.

### O15 · Plantilla de resumen de correo
1. `email_helpers.py` `_build_email_summary_messages` (~281-308): pide **1-3 viñetas** con lo principal, las acciones y los plazos; si hay adjuntos, usar **su contenido** (importes de la factura, cláusulas, fechas) y no solo el cuerpo; salida entre marcadores para que no se cuele razonamiento (`_normalize_email_summary` ~366-388).
2. Tienes: el vigía resume en 90 caracteres con plazo; `email-inbox-triage` no fija un formato de resumen.
3. Recreable como 3 líneas en la sección «Output Shape» de `email-inbox-triage`; nada que copiar (la plantilla es genérica y corta).
4. Valor 2, esfuerzo S, riesgo bajo. 5. 6 tests de resumen; incidencia nº 6423 (respuestas en blanco con modelos locales, no aplica a ti).

### Otras lecciones aprovechables (sin skill)
- Técnica de «extracción positiva»: pedir al modelo que ponga su resultado entre marcadores (`<<<…>>>`) y quedarse solo con eso (`email_helpers.py` ~253-278) evita basura de razonamiento; ya lo haces con JSON en `zv/llm.py`.
- Cubos de agenda **contiguos** en un resumen (hoy-mañana / esta semana / 30 días): una versión antigua dejaba un hueco entre el día 7 y el 8 (`task_scheduler.py` ~272-283); revisa que tu parte diaria/semanal no deje huecos.
- Un lote de seguridad: que cada consulta de agenda/correo esté limitada a su dueño (varias correcciones de Odysseus eran fugas entre usuarios). En tu caso: las dos cuentas (varas/alvarez) no se mezclan; ya lo cuidas.

---

## 4. Tabla final (ordenada por valor/esfuerzo; S=1, M=2, L=3)

| Orden | Idea | Valor | Esfuerzo | Valor/esf. | Riesgo | Estado y qué hacer |
|---|---|---|---|---|---|---|
| 1 | O2 Edición segura con versiones y simulación | 3 | S | 3,0 | Bajo/medio | **Borrador hecho** (13 pruebas). Instalar tras tu «sí» |
| 2 | O3a Quitar citas/firmas del correo (ahorro de tokens) | 3 | S | 3,0 | Bajo | **Borrador hecho** (en `correo-limpio-es`) |
| 3 | O4 Estilo de escritura guardado + reglas de borrador | 3 | S | 3,0 | Bajo | Mejora de texto de `email-inbox-triage`; pide tu permiso para leer enviados |
| 4 | O5 Aviso de solape de horarios | 3 | S | 3,0 | Bajo | Mejora de `comprobar.py` (no es skill) |
| 5 | **O1 Fechas y recurrencias en español** | 4 | M | 2,0 | Bajo | **Borrador hecho** (21 pruebas). Mi nº 1 por ser la única capacidad nueva (repeticiones) |
| 6 | O3b Informe de boletines por cabeceras | 2 | S | 2,0 | Bajo | **Borrador hecho** (en `correo-limpio-es`); sin ejecutar bajas |
| 7 | O15 Plantilla de resumen de correo | 2 | S | 2,0 | Bajo | 3 líneas en `email-inbox-triage` |
| 8 | O7 Tipo/importancia de eventos | 2 | S | 2,0 | Bajo | Opcional, dentro de la revisión semanal |
| 9 | O9 Duplicados de notas (solo informe) | 2 | S | 2,0 | Bajo | Opcional; nunca borrar |
| 10 | O6 Importar .ics a Google | 3 | M | 1,5 | Medio | Después de O1 |
| 11 | O8 Reservas con actualizar/cancelar (solo propuesta) | 3 | M | 1,5 | Medio/alto | Cambio del vigía; con tu aprobación siempre |
| 12 | O12 Tareas programadas | 1-2 | S | ~1,5 | Bajo | Ya cubierto por el cron de Hermes |
| 13 | O11 Recordatorios de notas | 1 | S | 1,0 | Bajo | Ya cubierto |
| 14 | O10 CalDAV/Nextcloud | 2 | L | 0,7 | Medio/alto | No, salvo que uses Nextcloud como agenda |
| 15 | O13 Respuesta automática de ausencia | 1 | M | 0,5 | **Alto** | Descartar |
| 16 | O14 Vault de contraseñas | 1 | M | 0,5 | **Alto** | Descartar |

(Ordenada por valor dividido por esfuerzo; a igualdad, por valor. Mis tres recomendaciones son O1, O2 y O3 porque tienen borrador probado y cubren huecos que hoy no se resuelven de otra forma; O1 va primero en las recomendaciones por su valor, aunque en la tabla caiga al 5.º puesto por ser la de más esfuerzo.)

---

## 5. Fallos de Odysseus que conviene no heredar (por si algún día miras su código)

- **Horas guardadas en UTC sin zona** (`calendar_routes.py` `_event_to_dict`/`_expand_rrule`, `caldav_sync.py` `_to_utc_naive` ~154): las series de más de un cambio de hora se desplazan; su incidencia nº 6512. Además día entero «un día antes» al este de UTC (nº 6290). En España afecta tal cual.
- **Analizadores solo en inglés**: fechas («tomorrow», «next monday»), atribución de hilos («On … wrote:»), heurísticas de eventos. Hay que reescribir, no copiar.
- **Borrado real** en la limpieza de documentos (`document_actions.py` ~53-197, `db.delete`) y en las limpiezas de correo; en tu sistema, siempre archivar.
- **Edición silenciosa de «la primera coincidencia»** cuando el texto buscado aparece varias veces (`document_tools.py`): mi versión lo rechaza.
- **Correo en bloque**: el borrado puede ser definitivo si la papelera rechaza el movimiento (nº 6632).
- **Demasiada IA para lo que son reglas**: tags, spam y urgencia con un modelo por correo (`email_pollers.py` ~1103-1310). Tu vigía hace lo mismo con reglas y llama al modelo solo en lo ambiguo: es mejor diseño.

---

## 6. Los tres borradores

Ubicación (nada instalado): `/home/server/Odysseus/analisis/skills-propuestas/`

| Carpeta | Contenido | Pruebas |
|---|---|---|
| `fechas-y-recurrencias-es/` | `SKILL.md`, `NOTICE`, `scripts/fecha.py` (`resolver`, `repetir`, `proximas`), `tests/test_fecha.py` | 21 OK |
| `edicion-segura-documentos/` | `SKILL.md`, `NOTICE`, `scripts/versiones.py` (`copia`, `lista`, `hash`, `diff`, `editar`, `restaurar`), `tests/test_versiones.py` | 13 OK |
| `correo-limpio-es/` | `SKILL.md`, `NOTICE`, `scripts/correo.py` (`limpiar`, `cabeceras`), `tests/test_correo.py` | 19 OK |

Ejecutar las pruebas (sin tocar nada real): `cd <carpeta> && /usr/bin/python3 -m unittest discover -s tests`.
Descripciones de 52-55 caracteres (límite 60). Solo biblioteca estándar; `fecha.py` usa además `python-dateutil` (ya está en `/usr/bin/python3`, 2.9.0). No he instalado, ni ejecutado con datos tuyos, ni leído tu correo ni tu agenda para probarlas.

### 6.1 Si dices que sí (pasos, no ejecutados)
1. Probar primero en un perfil de pruebas (la checklist `plantilla-skill/CHECKLIST-revision.md`, apartados G y H).
2. Copiar cada carpeta a `~/.hermes/skills/productivity/<nombre>/` y comprobar con `hermes skills list --enabled-only`.
3. Anotar el cambio en el Cerebro (`60 Servidor/mapa.md`, `historial-geekom.md`, `90 Sistema/log.md`).
4. Retirarla si algo va mal: borrar su carpeta o ponerla en `skills.disabled`.

### 6.2 Cambio sugerido (no aplicado) en `agenda-y-tareas`, paso 2
> Antes de crear un evento con fecha relativa («el martes», «dentro de 3 días», «el último viernes…»), resuélvela con `fechas-y-recurrencias-es` (`fecha.py resolver '<frase>' --humano`) y dile a Fran la fecha resuelta. Si repite, usa `fecha.py repetir` y añade `--rrule` al crear.

### 6.3 Qué falta probar con datos reales
- 20 frases reales tuyas para `fecha.py` (especialmente «a las 5», «el lunes que viene», «a finales de mes»).
- Un par de hilos reales (tus correos) para `correo.py limpiar`, y UN mensaje real con las cabeceras de `zgog` para `cabeceras`; medir caracteres antes/después.
- Un archivo de prueba tuyo con `versiones.py` (la ruta de copias `~/.hermes/cache/versiones/` es nueva).

---

## 7. Límites de este análisis
- No ejecuté Odysseus ni su código; no toqué `~/Odysseus/datos` ni `.admin`. Todo lo que he leído en el repositorio lo he tratado como dato.
- Las cifras de incidencias de GitHub salen de una lectura web resumida por un modelo pequeño, a fecha de hoy: úsalas como orientación.
- No he medido tu demanda real (cuántas veces pides repeticiones o ediciones) ni el ahorro de tokens del correo.
- El formato exacto del JSON de `zgog gmail get --format=metadata` no está comprobado (solo la ayuda del programa).
- Sobre licencia: he trabajado «desde la idea» y anotado la procedencia en cada `NOTICE`; AGPL-3.0 exige cuidado si alguna vez se copiara código. Esto no es asesoría legal.
