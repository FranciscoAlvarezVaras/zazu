# 02 · Memoria, contexto y aprendizaje: Odysseus frente a Hermes

Fecha: 2026-10-10 · Odysseus 1.0.3 (rama `main`, 934d23c, AGPL-3.0) · Hermes del servidor de Fran (config de hoy)
Alcance: solo lectura. No se ha arrancado ni ejecutado nada de Odysseus; no se ha instalado nada en `~/.hermes`.

---

## 0. Lo esencial (para decidir en un minuto)

**Conclusión honesta:** en este tema Hermes ya está por delante de Odysseus en casi todo (compresión de contexto, revisión automática de memoria y skills, curador de skills, aprobaciones, búsqueda en el historial, memorias externas). Odysseus es un proyecto de un solo autor que, según su propio `ROADMAP.md`, avanza muy deprisa y pide ayuda para "SQUASH BUGS". **No merece la pena portar su código.** Lo que sí aporta son **tres ideas** que Hermes no tiene, y las tres se pueden recrear como skills pequeñas sin tocar el núcleo:

| # | Idea de Odysseus | Skill propuesta (borrador hecho) | Valor | Esfuerzo |
|---|---|---|---|---|
| 1 | "Limpieza de memoria" con redes de seguridad (no borrar lo que el modelo solo omite, tope de borrado, avisar solo si algo cambia) | `memoria-higiene` | 4/5 | S |
| 2 | Bucle del "profesor": falla el modelo barato, uno mayor resuelve y destila una habilidad (con guardia contra instrucciones colgadas en la traza y "mejor ninguna skill que una mala") | `profesor-escalar` | 4/5 | M |
| 3 | Auditoría de skills: ¿hace falta?, ¿se confunde con otra?, ¿un modelo pequeño puede seguirla? | `auditar-skills` | 3/5 | M (el script ya está; el esfuerzo es de uso) |

**Tres hallazgos sobre el Hermes de Fran** (medidos hoy, no en Odysseus; son más valiosos que cualquier cosa que se pueda portar):

1. **La revisión automática de memoria y skills de Hermes está APAGADA** en tu `config.yaml` (`auxiliary.background_review.enabled: false`; de serie viene encendida). Es lo que más se parece a "aprender de Fran sin que lo pida". Hoy el aprendizaje depende de que el modelo barato se acuerde de guardar (solo quedan los recordatorios internos: memoria cada 10, skills cada 15).
2. **Las escrituras en memoria no pasan por ningún filtro.** `memory.write_approval` no está puesto y el hook de aprobaciones no cubre la herramienta `memory` (sí cubre `skill_manage`). `MEMORY.md` entra en el prompt de sistema como contexto de confianza, así que un correo o WhatsApp envenenado que consiguiera que Zazu "apunte" algo se quedaría guardado y cargado en cada sesión hasta que alguien lo borre. Odysseus trata memorias y skills como datos no fiables y exige aprobación para skills destiladas de trazas; ahí tiene razón.
3. **En los últimos 14 días** (81 conversaciones leídas de `state.db`, solo lectura): Fran corrigió o se quejó 6 veces, Zazu dijo "no puedo / no he podido" en 19 conversaciones y **45 acciones se frenaron por falta de aprobación**. Esas 45 no parecen fallos de capacidad sino permisos que caducan sin respuesta (la muestra que he mirado dice "Action timed out without user response"; y ya sabías que en el chat de la app la aprobación equivale a denegar). Un profesor no arregla eso.

**Decisiones que te tocan a ti:**
- ¿Instalo las 3 skills? (`memoria-higiene` es la más segura y la que empezaría hoy.)
- ¿Enciendes la revisión automática de Hermes, y con qué modelo? Mi propuesta: probar una semana con `memory.write_approval: true` y `skills.write_approval: true` (todo lo que escriba se queda en cola para tu visto bueno en el plugin `memory-review`, que ya tienes). Con el Qwen3 4B local es gratis pero dudo de su calidad con prompts tan largos; con Haiku cuesta una repetición de la conversación por turno.
- Para el profesor: ¿qué modelo (Sonnet por defecto, Opus solo si lo pides) y cuántas consultas al mes antes de avisarte (propongo 5)?

---

## 1. Qué he mirado y cómo

- **Odysseus** (`/home/server/Odysseus/src`): `src/memory.py`, `src/memory_vector.py`, `src/memory_provider.py`, `src/embedding_lanes.py`, `src/embeddings.py`, `src/chat_processor.py`, `src/context_compactor.py`, `src/context_budget.py`, `src/teacher_escalation.py`, `src/agent_tools/model_interaction_tools.py`, `services/memory/*` (extractor, skills, formato, importador), `routes/skills_routes.py`, `src/builtin_actions.py` (limpieza de memoria), `src/task_scheduler.py`, `specs/memory-skills.md`, `specs/context-building.md`, `THREAT_MODEL.md`, `ROADMAP.md`, y los tests de memoria/skills/compactación/profesor. **Cookbook:** no toca la memoria del agente (solo habla de memoria de GPU/RAM para elegir modelos); descartado.
- **Hermes** (`/home/server/.hermes/hermes-agent`, config y datos de Fran): `agent/background_review.py`, `agent/curator.py`, `agent/context_compressor*.py`, `agent/learn_prompt.py`, `agent/review_engine.py`, `tools/memory_tool*.py`, `tools/write_approval.py`, `tools/skill_manager_tool.py`, `tools/skill_linter.py`, `tools/skill_usage.py`, `tools/session_search_tool.py`, `tools/delegate_tool.py`, `plugins/memory/*`, `SOUL.md`, `memories/*.md`, `config.yaml`, `agent-hooks/movil-aprobacion.py`, las skills reales y `state.db` (solo lectura). Además `hermes curator status/usage` y `hermes cron create --help`.
- **Límite:** el repositorio de Odysseus llega con **un solo commit** (historial aplastado), así que no se ven issues ni PRs abiertos; la madurez se juzga por código, tests y su propia documentación.

---

## 2. Qué hace Odysseus en este tema (con rutas)

| Pieza | Dónde | Cómo funciona |
|---|---|---|
| **Almacén de memoria** | `src/memory.py` (clase `MemoryManager` L47; lectura estricta `load_all_for_update` L180; `save` atómico L261) | Un único `data/memory.json` con entradas `{id, text, timestamp, source (user/auto/unknown), category, uses, pinned, owner, session_id}`. Categorías: fact, identity, preference, contact, project, goal, event, instruction. Si el archivo no se puede leer, **se niega a escribir** (`MemoryStoreUnreadable`, L14) para no machacar la memoria con una lista vacía. **No hay caducidad ni olvido**: ninguna entrada expira. |
| **Memoria semántica** | `src/memory_vector.py` (L1–251), `src/embedding_lanes.py`, `src/embeddings.py` L38-39 | Chroma por HTTP (colección `odysseus_memories`), con dos "carriles" de embeddings (endpoint HTTP configurable o FastEmbed local) para no mezclar dimensiones. Modelo por defecto: **all-MiniLM-L6-v2, pensado para inglés**. Si el vector falla, degrada a palabras clave. |
| **Recuperación** | `src/chat_processor.py` `_hybrid_retrieve` L158-261, `_select_pinned_memories` L112 | Puntuación = 0,55·vector + 0,40·BM25 (sobre tokens sin palabras vacías, **lista en inglés**) + 0,05·recencia (la recencia solo desempata); umbral mínimo; máximo 5 recuerdos. Las memorias "ancladas" no se mandan todas: solo un pequeño núcleo de identidad/contacto, el resto solo si encaja con el mensaje. Lo recuperado se inyecta **como datos no fiables** (`prompt_security.py`) y se cuenta su uso (`increment_uses`, `memory.py` L297). |
| **Extracción automática** | `services/memory/memory_extractor.py` L73-100 (prompt), L152 (respaldo con regex), L278 `extract_and_store` | Tras cada respuesta: máximo **2 hechos** por conversación, frases de menos de 15 palabras, solo lo que el usuario dijo, o `[]`. Evita repetidos (vector ≥0,72 y Jaccard ≥0,6). Fija ("pin") automáticamente lo de categoría identidad. Respaldo con regex en inglés. |
| **Limpieza ("Memory Tidy")** | `services/memory/memory_extractor.py` `audit_memories` L495-660; `src/builtin_actions.py` `action_consolidate_memory` L464-745; disparo `src/task_scheduler.py` L254 (cada 5 memorias nuevas) | Dos etapas: (1) dedupe **determinista** (mismo tipo y texto idéntico/contenido/`SequenceMatcher` ≥0,88; se queda la fijada > del usuario > más usada > más corta > más nueva); (2) un modelo decide `keep`/`drop`. **Redes de seguridad:** solo se borra lo que el modelo lista expresamente en `drop` (no lo que olvida listar, L647); nunca se borra lo que el modelo vio recortado; si la limpieza quitara más del 50 % (con 8+ entradas) se rechaza (L633); una huella (hash) de lo último limpiado evita repetir la llamada si nada cambió (L34). |
| **Compactación** | `src/context_compactor.py`: umbral 85 % (L40), resumen estructurado (L45-80), `maybe_compact` L323, `trim_for_context` L224 | Cuando el contexto pasa del 85 %, resume la **mitad más antigua** con el modelo auxiliar y deja la mitad reciente; si el resumen falla, no toca nada. `trim_for_context` recorta por prioridades (memoria/RAG primero, luego turnos viejos, protege los 10 últimos, trunca el mensaje actual si es enorme) y repara pares `tool_calls`/`tool` huérfanos. |
| **Profesor** | `src/teacher_escalation.py`: fallo nivel 1 por regex L91, nivel 2 por LLM L390, prompts L147/L262, guardia de traza L133, toma de control en vivo `run_teacher_inline` L514-810, `escalate_and_learn` **retirada** L435; `src/agent_tools/model_interaction_tools.py` `ask_teacher` L73 | (a) El alumno puede **consultar** al profesor como herramienta (`ask_teacher`: análisis, enfoque en pasos, cosas a vigilar). (b) Si un turno falla (regex en inglés sobre errores de herramienta y frases tipo "no puedo"; opcionalmente un juez LLM), el profesor **repite la tarea en directo** con herramientas y, si la resuelve, destila la traza en una skill JSON (`NO_SKILL` si no es reproducible; reglas de portabilidad: nada de hosts, rutas ni IDs de una máquina). (c) La skill **solo se guarda tras aprobación exacta del usuario**; el aprendizaje en segundo plano sin pantalla fue retirado a propósito. Apagado por defecto (`teacher_enabled`). |
| **Skills: crear** | `services/memory/skill_extractor.py` (L1-305) | Si la tarea costó ≥2 rondas o ≥2 herramientas, un modelo decide si hay un procedimiento reutilizable **en el ordenador** (devuelve `null` si el trabajo fue fuera del ordenador, es un recado personal o el agente falló); confianza mínima 0,6; dedupe por título. |
| **Skills: auditar y mejorar** | `routes/skills_routes.py`: prueba con datos inventados L94-125, juez de la ejecución L128 (veredictos pass / needs_work / fail / **inconclusive**), juez de **necesidad/redundancia** L282, juez de **precisión de disparo** L362, bloqueo de duplicados L568, política de publicación L548/L680, bucle `_audit_one_skill` L853, auditoría programada L1140 | Ejecuta la skill de verdad en el agente, la juzga, si falla la reescribe el propio modelo y reintenta; si sigue fallando **la reescribe el profesor pero el reintento lo hace el alumno** (la skill tiene que servir al modelo barato). Solo se publica si pasa, es necesaria y no es duplicado; si no, vuelve a borrador. Nunca borra. |
| **Formato de skill** | `services/memory/skill_format.py` (L1-483), `services/memory/skills.py` | `SKILL.md` con frontmatter YAML (`name, description, version, category, tags, platforms, requires_toolsets, fallback_for_toolsets, status, confidence, source, teacher_model, owner`) y cuerpo con When to Use / Procedure / Pitfalls / Verification. Contadores de uso en un archivo aparte (`_usage.json`). Declara estar "inspirado en el formato de Hermes". |
| **Seguridad** | `THREAT_MODEL.md` L61, `src/prompt_security.py` | Memorias, skills, correos, webs y salidas de herramientas son **datos, nunca instrucciones**; no pueden ir al rol "system". |

---

## 3. Qué tiene ya Hermes y qué le falta de verdad

| Área | Odysseus | Hermes (ruta) | Veredicto |
|---|---|---|---|
| Memoria base | JSON de entradas con metadatos, recuperación por relevancia | `MEMORY.md` / `USER.md` (límite 9000 caracteres cada uno en tu config), herramienta `memory` (add/replace/remove/batch, separador `§`, cerrojos), **instantánea congelada** en el prompt al empezar la sesión para no romper la caché (`tools/memory_tool.py` L1-6) | Distinto, no peor. Como siempre va entera en el prompt, **no necesita recuperación**. |
| Cola de aprobación de memoria/skills | Aprobación exacta para skills del profesor | `tools/write_approval.py` + plugin `memory-review` (cola `pending/{memory,skills}`); config `memory.write_approval` / `skills.write_approval` | Hermes lo tiene, **tú no lo tienes encendido**. |
| Revisión automática tras cada turno | Extractor de hechos (2 por conversación) y de skills | `agent/background_review.py`: prompts mucho más elaborados (L357-520: dónde va cada dato, qué NO guardar, "actualiza la skill que se usó antes de crear otra", leer antes de escribir); cola para esperar a que el equipo esté libre (`review_idle_queue.py`) | **Hermes muy superior.** Está apagada en tu config. |
| Conservar skills sanas | Auditoría + bloqueo de duplicados | `agent/curator.py`: pasa a "obsoleta" a los 14 días sin uso y archiva a los 30; opcional fusión por LLM (apagada); `tools/skill_usage.py` (contadores en `.usage.json`), `skill_linter.py`, `skills_guard.py`, `hermes curator status/usage/prune/restore` | Hermes cubre el ciclo de vida. **No comprueba** referencias rotas, solapes de disparador, ni que un modelo pequeño pueda seguirla. |
| Memoria caduca | Nada | Nada en la memoria integrada. El plugin `holographic` tiene confianza y decaimiento temporal (`temporal_decay_half_life`, apagado por defecto) y detección de contradicciones. Tu convención `[revisar: AAAA-MM-DD]` en `MEMORY.md` **no la vigila nadie**. | Hueco real. |
| Memoria semántica | Chroma + embeddings (MiniLM inglés) | Proveedores externos `plugins/memory/{holographic,byterover,retaindb}` + catálogo (honcho, mem0…), un solo proveedor activo; `query_rewrite.py` con tu Qwen local. Ninguno activo en tu config | Hermes tiene la puerta abierta, sin cargar nada. No hace falta copiar nada. |
| Buscar en el historial | No tiene (usa sus propias tablas) | `tools/session_search_tool.py`: FTS5 sobre `state.db` (con tabla trigram), baja la prioridad de los trabajos programados para que no tapen tus conversaciones | Hermes superior. |
| Compactación | Resumir la mitad antigua al 85 % | `agent/context_compressor.py` (5.947 líneas): plantilla con "Active Task / Pending User Asks", poda previa de resultados de herramientas, resúmenes por herramienta, anti-bucle, **punto de control de memoria antes de comprimir** para proveedores de memoria. Tu config: umbral 0,5 / 80.000 tokens, resumen con Haiku | **Hermes muy superior.** Nada que tomar. |
| Profesor / escalado de modelo | Sí (tres formas) | **No hay bucle.** Solo `/model` manual (SOUL: "sugiere a Fran subir de modelo"), `delegate_task` con modelo **fijado por config, no elegible por el agente** (`tools/delegate_tool.py` L645), `/review`, `/learn` (`agent/learn_prompt.py` crea una skill desde lo que describas) y skills de costes | Hueco real. |
| Formato de skill | `SKILL.md` + extras (`status`, `confidence`, `owner`…) | `SKILL.md` con `name` + `description` ≤60 caracteres + `metadata.hermes.*`; linter y validador duro | Casi idéntico (ver §4-H). |

---

## 4. Las ideas, una a una

Cada ficha responde: (1) qué hace y dónde, (2) qué tiene Hermes y qué le falta, (3) ¿se puede hacer como skill? qué se reutiliza y qué se reescribe, (4) valor / esfuerzo / riesgo, (5) madurez.

### A · Higiene de memoria con redes de seguridad → `memoria-higiene` (borrador hecho)

1. **Qué hace.** Ver §2 "Limpieza". Lo valioso no es el modelo que decide, sino las **reglas de seguridad** alrededor: borrar solo lo expresamente listado, no tocar lo que no se vio entero, tope del 50 %, huella para no repetir trabajo, y orden de preferencia entre duplicados.
2. **Hermes.** Al llenarse, la herramienta `memory` rechaza escribir y el plugin `memory-review` ofrece "Consolidar". Falta lo proactivo: caducados, fechas pasadas, repetidos entre `MEMORY.md` y `USER.md` o con `SOUL.md`, y datos que tu regla prohíbe. Hoy `MEMORY.md` lleva un correo y un teléfono de terceros (contra "nunca guardes teléfonos" de SOUL) y una cita con fecha (2026-10-13) que se quedará vieja sin marca `[revisar]`.
3. **Como skill.** Sí, sin tocar el núcleo. `scripts/memoria_higiene.py` (stdlib, solo lectura, 0 llamadas a modelos) saca el informe; Zazu aplica los cambios con la herramienta `memory` y tu visto bueno. **Reutilizable tal cual de Odysseus: nada** (su código está atado a `memory.json` con propietarios). **Reescrito desde la idea:** orden de preferencia, umbrales (Jaccard 0,6; parecido por letras 0,88; contenido ≥24 caracteres), "solo borra lo listado", tope (yo lo bajo al 30 %), huella anti-ruido. Añadidos propios: caducidad `[revisar:]`, fechas pasadas, solape con SOUL, datos sensibles (solo el tipo).
4. **Valor 4 · Esfuerzo S · Riesgo bajo.** No escribe; no usa red ni modelos. Riesgo residual: falsos positivos del detector de teléfonos/tarjetas (probado con fechas, versiones e importes).
5. **Madurez.** Odysseus: el comportamiento está cubierto por 3 tests de "tidy" y 1 de borrados explícitos, más `test_memory_store_unreadable_no_wipe`. La skill nueva: 12 pruebas propias, y se ha ejecutado en solo lectura sobre tu memoria real.

### B · El profesor: escalar, resolver y destilar → `profesor-escalar` (borrador hecho)

1. **Qué hace.** Ver §2 "Profesor". Ideas con más sustancia: (i) **detección barata de fallo primero** (regex sobre errores y frases de rendición) y juez LLM solo si se activa; (ii) el profesor ve la traza **envuelta como datos no fiables** y la skill nunca puede copiar órdenes de ahí (segunda inyección: un correo envenenado que acabe destilado en una skill "autoritativa"); (iii) `NO_SKILL` como salida válida y regla "una skill mala es peor que ninguna"; (iv) reglas de **portabilidad** (nada de rutas, hosts ni IDs concretos); (v) la skill solo se guarda tras aprobación exacta; (vi) en la auditoría, **el reintento lo hace el alumno** con la skill reescrita por el profesor.
2. **Hermes.** Nada equivalente. `/learn` crea skills a partir de lo que tú describes, pero no hay "mi modelo falló → consulta a uno mayor". `delegate_task` no deja elegir modelo desde la conversación (solo `delegation.model` en config).
3. **Como skill.** Sí, **sin hook ni plugin**: el disparo es manual o "ofrecido" por Zazu tras dos fallos. El profesor es un **asesor sin herramientas** (más seguro que la toma de control de Odysseus): `claude -p --tools ""` (tu plan de Claude Code) como vía preferida; `hermes chat --query-file … --oneshot` solo como alternativa probada, porque el modo oneshot **salta las aprobaciones** (`hermes --help`: "approvals are auto-bypassed"). `scripts/profesor.py` hace lo mecánico: tapa datos personales y claves, arma el briefing con la guardia de datos no fiables, valida la respuesta y la skill propuesta (formato Hermes, descripción ≤60, sin datos personales, sin frases que salten permisos), y repasa `state.db` para elegir qué enseñar. **Reutilizable tal cual: nada.** **Reescrito:** prompts del profesor (en español, para las herramientas de Hermes), la guardia de traza, `NO_SKILL`, la prueba del alumno (en seco), y los patrones de fallo en español. Si algún día quieres detección automática, existe el hook `post_tool_call`/`on_session_end` de Hermes (VALID_HOOKS en `hermes_cli/plugins.py`); no lo recomiendo todavía.
4. **Valor 4 · Esfuerzo M · Riesgo medio.** Coste por consulta (unos miles de tokens; con Sonnet céntimos, con Opus bastante más), el tope `--max-budget-usd` y el contador `resumen` lo acotan; el caso viaja a Anthropic (el mismo proveedor que ya usa Zazu) con datos tapados; el consejo del profesor puede ser incorrecto (manda la prueba real, regla L1); `claude -p` usa tu plan (hay que confirmar que `claude` arranca bajo Hermes en el servidor).
5. **Madurez.** Odysseus: 14 tests del profesor (mocks de plumbing), el camino de "aprender en segundo plano" está **retirado** (`teacher_escalation.py` L435-447) y el detector de fallos es solo regex en inglés; la parte de toma de control en vivo sí está terminada pero atada a su bucle de agente. La skill nueva: 12 pruebas propias; **no probada con un modelo real** (hay que hacer una consulta de ensayo inofensiva).

### C · Auditoría de skills → `auditar-skills` (borrador hecho)

1. **Qué hace.** Ver §2 "Skills: auditar". Tres jueces separados (¿funciona?, ¿hace falta?, ¿su disparador es preciso?) con una **regla de justicia** valiosa: si la prueba no dio un dato que el uso real sí tendría, el veredicto es "inconcluso", no "falla".
2. **Hermes.** El curador solo mira uso y edad; el linter mira forma. **Faltan**: archivos que la skill manda ejecutar y ya no existen, solapes (el índice enseña solo 60 caracteres de cada descripción, así que disparadores parecidos se confunden), triviales, y la prueba "¿puede seguirla el modelo barato?".
3. **Como skill.** Sí. `scripts/auditar_skills.py` (stdlib, solo lectura) hace lo determinista; `references/jueces.md` trae los tres jueces en español para que Zazu los aplique sobre las fichas (`--ficha a,b`). La prueba del alumno es **en seco** (lista de llamadas, sin ejecutar): ejecutar de verdad skills que tocan correo, WhatsApp o calendario no es aceptable aquí; Odysseus las ejecuta con aprobaciones, Hermes no tiene ese sandbox. **Reutilizable tal cual: nada.** **Reescrito:** los jueces, la escala de veredictos, la política "solo dar por buena si pasa los tres", el parecido por palabras con dos umbrales (0,15 y 0,30; Odysseus bloquea duplicados a 0,38).
4. **Valor 3 · Esfuerzo M · Riesgo bajo.** Ejecutado sobre tus 22 skills propias/del hub: 2 por arreglar, 2 muy parcheadas (`jarvis-asistente-personal-ops` 17 parches, `hermes-host-maintenance` 7), 2 pares parecidos (`hermes-cost-control` ~ `hermes-model-cost-routing`, 0,18; `agenda-y-tareas` ~ `guardar-en-holazazu`, 0,17). Es poco, porque tu biblioteca es pequeña y joven: la auditoría rinde más cuando haya 40+ skills propias.
5. **Madurez.** Odysseus: 84 tests de skills (casi todos de robustez/seguridad: propietarios, importación SSRF, frontmatter); para el bucle de auditoría solo hay 2, de ámbito de propietario (`test_teacher_audit_owner_scope.py`). La skill nueva: 7 pruebas propias. Calibrada contra tu biblioteca real (primera pasada: 22 avisos de "sin Cuándo usarla" porque tus skills usan otro estilo, y 2 rutas que apuntaban a otras skills; corregido).

### D · Búsqueda híbrida (BM25 + vectores + recencia) → `buscar-en-cerebro` (sin borrador)

1. **Qué hace.** `_hybrid_retrieve` (§2). Las ideas útiles: ponderar palabras clave y significado, que la recencia solo desempate, y exigir relevancia mínima para no meter ruido.
2. **Hermes.** `session_search` cubre el historial. Para el Cerebro (Obsidian) Zazu usa búsqueda de archivos. **Medido hoy:** el Cerebro son **215 notas y 0,8 MB de texto**; un índice SQLite FTS5 (viene con Python, sin instalar nada) se construye en 0,04 s y responde en menos de 1 ms, y con `remove_diacritics` encuentra "teorico" en "teórico". Con ese tamaño **los vectores no aportan**: son una solución para decenas de miles de notas.
3. **Como skill.** Sí, pequeña (S): índice FTS5 en memoria o en `cache/`, tokenización sin acentos, puntuación `bm25()`, fragmentos. Sin dependencias. Reescribir desde cero (la parte de Odysseus está atada a Chroma).
4. **Valor 3 · Esfuerzo S · Riesgo bajo** (FTS5). **Vectores: valor 2 · esfuerzo L · riesgo alto** (ver F).
5. **Madurez.** La recuperación híbrida de Odysseus tiene 4 tests de memorias ancladas; no hay evaluación de calidad. Se puede ofrecer más adelante si el Cerebro crece (la carpeta `50 Zazu` crece cada noche).

### E · Extracción automática de hechos y skills → no portar (encender lo que Hermes ya trae)

1. `memory_extractor.py` L73 y `skill_extractor.py`: pocos hechos, cortos, solo lo que dijo el usuario; devolver `null` si el trabajo fue fuera del ordenador.
2. Hermes lo hace **mejor** (`background_review.py` L357-520: separa USER.md de MEMORY.md "un dato, un sitio", prohíbe guardar errores de entorno como reglas permanentes, no apuntar fracasos como "flujo fiable", parchear la skill que se usó en vez de crear otra, leer antes de escribir).
3. No es una skill: es config. Decisión de §0.
4. **Valor 4 si se enciende bien · Esfuerzo S · Riesgo:** coste (una réplica de la conversación por turno con Haiku), ruido, y calidad con el Qwen 4B local.
5. Madurez (Odysseus): 29 tests de parseo y robustez (14 del extractor de memoria, 15 del de skills); ninguno mide si extrae bien. Su prompt avisa de que sin aplanar la conversación en un solo mensaje "0/6" extracciones funcionaban, lección útil pero que Hermes ya incorpora.

### F · Memoria vectorial completa (Chroma + FastEmbed) → descartar

Necesita servicio Chroma aparte, `onnxruntime` y `fastembed` (~cientos de MB, 14 GB de RAM te alcanzan pero 6 GB disponibles hoy no sobran), y su modelo por defecto es de **inglés** (all-MiniLM-L6-v2), malo para el español de Fran. El propio spec de Odysseus lista como pendientes: importar JSON no reconstruye el índice vectorial, el borrado total no limpia vectores, y fallos del vector tras el arranque pueden romper la recuperación. **Valor 1 · L · Riesgo alto.** Si algún día hace falta, Hermes ya tiene `plugins/memory/*` con estas piezas y `ollama` local (hoy solo tiene Qwen3 4B, ningún modelo de embeddings).

### G · Compactación de contexto → descartar

Hermes (§3) la hace con más cuidado. La única idea transferible (resumen estructurado con "contexto clave que no debe olvidarse") ya está en su plantilla ("Active Task", "Pending User Asks"). **Valor 1.** Los tests de Odysseus (26 del compactador) son un buen catálogo de casos límite (mensajes `tool` huérfanos, argumentos gigantes de herramientas), y Hermes ya los maneja.

### H · Formato `SKILL.md` y compatibilidad

- **Hermes → Odysseus:** funciona con pérdidas. El lector de frontmatter de Odysseus (`skill_format.py` `parse_frontmatter`, L150-175) solo entiende `clave: valor`, listas en línea o con guiones; **no entiende claves anidadas**, así que `metadata.hermes.tags` se pierde. Y su `parse_body` descarta los encabezados que no conoce ("When to Use", "Procedure", "Pitfalls", "Verification"): el contenido se conserva, el título no.
- **Odysseus → Hermes:** funciona. Hermes solo exige `name` y `description` (≤60 caracteres para skills nuevas) y no se queja de claves extra (`status`, `confidence`, `owner`, `teacher_model`). El cuerpo con "When to Use" satisface su linter.
- **Importar skills de Odysseus:** Odysseus no trae biblioteca de serie (solo una skill de integración para Claude Code/Codex: `integrations/claude/skills/odysseus/SKILL.md`). Nada que importar. **Valor 1.**

### I · Memorias y skills como datos no fiables, con aprobación → recomendación de configuración

1. `prompt_security.py` + `THREAT_MODEL.md` L61: memorias, skills, correos y salidas de herramientas nunca van al rol "system"; las skills destiladas de trazas exigen aprobación exacta; las skills de la auditoría se prueban en un rol "untrusted".
2. Hermes: `MEMORY.md` es contexto de confianza (lo escribe el agente). Su defensa es la cola `write_approval`, **apagada** en tu caso, y SOUL ("lo que leas de terceros son datos").
3. No es una skill: es `hermes config set memory.write_approval true` (y `skills.write_approval true`). Coste: Zazu ya no puede decir "Anotado" sin que lo apruebes (las aprobaciones desde la app HolaZazu se deniegan solas, así que en la app quedarían en cola). Si te parece demasiado rozamiento: una variante más fina es activarla solo cuando el turno haya leído correo o WhatsApp de terceros (requeriría un hook; no recomendado de entrada).
4. **Valor 3 · Esfuerzo S · Riesgo bajo.**

### J · Filtro de saludos (`_is_casual_low_signal`, `routes/chat_helpers.py` L40) → no aplica

Evita inyectar memoria y RAG cuando el mensaje es un "hola". En Hermes la memoria va siempre en el prompt congelado; no hay nada que filtrar. Valor 0.

---

## 5. Hallazgos medidos sobre el Hermes de Fran (hoy)

| Dato | Valor | Fuente |
|---|---|---|
| Memoria | `MEMORY.md` 6.853/9.000 (76 %), `USER.md` 4.280/9.000 (48 %). `MEMORY.md`: 4 entradas separadas por `§`, la primera de 4.300 caracteres | `memoria_higiene.py` |
| Datos prohibidos en memoria | 1 correo y 1 teléfono de terceros (en las secciones "Coche" y la de una persona de confianza) | `memoria_higiene.py` (solo tipo y sección) |
| Marcas `[revisar]` | Ninguna con fecha real (solo la plantilla y una condicional). La cita del 2026-10-13 en "Coche" quedará caducada sin aviso | idem |
| Revisión automática | Apagada (`auxiliary.background_review.enabled: false`); `memory.nudge_interval: 10`; `skills.creation_nudge_interval: 15` | `config.yaml` |
| Aprobación de escrituras | `memory.write_approval` y `skills.write_approval` sin definir (libres); el hook cubre `skill_manage` y no `memory` | `config.yaml`, `agent-hooks/movil-aprobacion.py` |
| Curador | Activo; 1 ejecución, "sin cambios; fusión LLM apagada"; 5 skills gestionadas, 14 sin marca de procedencia | `hermes curator status` |
| Skills | 80 en total (19 creadas por el agente, 58 de serie, 3 del hub). Se han creado y parcheado solas: `jarvis-asistente-personal-ops` 17 parches | `hermes curator usage` |
| Últimos 14 días | 81 conversaciones; 6 correcciones/quejas de Fran; 19 conversaciones con "no puedo/no he podido"; 45 acciones frenadas por falta de aprobación; errores de herramienta: terminal 27, text_to_speech 6, write_file 3 | `profesor.py repaso` (solo lectura) |
| Ollama | Solo `qwen3:4b-instruct-2507-q4_K_M`; ningún modelo de embeddings | `ollama list` |
| Cerebro | 215 notas, 0,8 MB de texto; FTS5 disponible en el Python del sistema (SQLite 3.46) | prueba en memoria |

---

## 6. Tabla final, ordenada por valor/esfuerzo

| Pos. | Idea | Origen | ¿Skill sin tocar el núcleo? | Valor | Esfuerzo | Riesgo | Madurez (origen) | Qué se reutiliza |
|---|---|---|---|---|---|---|---|---|
| 1 | **Higiene de memoria** (`memoria-higiene`) | Odysseus (idea) + propio | Sí. Borrador + script + 12 pruebas | 4 | S | Bajo | Media (tidy con 4 tests) | Idea y umbrales; código nuevo |
| 2 | **Encender revisión automática + `write_approval`** | **Hermes** (ya existe) | No es skill: config | 4 | S | Medio (coste/ruido; probar 1 semana) | Alta (código de Hermes) | Nada de Odysseus |
| 3 | **Profesor** (`profesor-escalar`) | Odysseus (idea) + propio | Sí. Borrador + script + 12 pruebas; sin hook | 4 | M | Medio (coste, inyección, `claude -p`) | Baja-media (la parte "segundo plano" está retirada) | Flujo, guardia de traza, `NO_SKILL`, portabilidad; prompts nuevos |
| 4 | **Auditoría de skills** (`auditar-skills`) | Odysseus (idea) + propio | Sí. Borrador + script + 7 pruebas | 3 | M | Bajo | Media (muchos tests de robustez, pocos del bucle) | Jueces y regla de "inconcluso"; código nuevo |
| 5 | **Buscar en el Cerebro con FTS5** | Odysseus (idea) | Sí, sin dependencias | 3 | S | Bajo | n/a | Ponderación y umbral; código nuevo |
| 6 | **Memorias/skills como datos no fiables + aprobación** | Odysseus (política) | Config (`write_approval`) | 3 | S | Bajo | Alta (documentado en su `THREAT_MODEL`) | Principio |
| 7 | Memoria vectorial completa (Chroma + FastEmbed) | Odysseus | No recomendable | 1 | L | Alto (dependencias, inglés) | Media (con huecos propios listados) | Nada |
| 8 | Extractor propio de hechos/skills | Odysseus | Innecesario | 1 | S | Bajo | Media | Nada (Hermes lo hace mejor) |
| 9 | Compactación de contexto | Odysseus | Innecesario | 1 | — | — | Media | Nada |
| 10 | Importar skills / formato | Odysseus | Compatible, sin biblioteca | 1 | S | Bajo | n/a | Nada |
| 11 | Filtro anti-saludos | Odysseus | No aplica | 0 | — | — | — | Nada |

---

## 7. Mis tres recomendaciones y cómo instalarlas

1. **Empieza por `memoria-higiene`** (la más segura: no escribe nada). Copiar `skills-propuestas/memoria-higiene/` a `~/.hermes/skills/productivity/`; si quieres el aviso semanal, copiar también `scripts/memoria_higiene.py` y `scripts/rutina.sh` a `~/.hermes/scripts/` y crear la rutina `hermes cron create '0 9 * * 1' --name 'Higiene de memoria' --no-agent --script rutina.sh --deliver <destino>` (sin IA: solo habla si hay novedad). Con el informe de hoy ya tendrías dos cosas que corregir (los datos de terceros) y una cita que avisar cuando caduque.
2. **Decide el apagado/encendido de la revisión automática y la cola de aprobación** (§0). Es la palanca real de "aprender de Fran". Pruébala una semana con `write_approval` en `true` y mira cuánto basura sale; no hace falta código de Odysseus.
3. **Instala `profesor-escalar` solo después de una prueba de ensayo** (un caso inofensivo, por ejemplo "cómo ordeno mejor X", con `claude -p --tools ""` y su tope de gasto) y confirma que `claude` arranca desde la terminal de Hermes. Luego `auditar-skills` cuando pases de 40 skills propias.

Quien instale esto (Claude Code, con tu permiso, porque tocar `~/.hermes/skills` pide aprobación) debe: copiar las carpetas, ejecutar los tres comandos de `_pruebas-02` (31 pruebas) y volver a lanzar el linter de Hermes sobre cada `SKILL.md`. Detalles de verificación en §9.

**Cosas que NO conviene hacer:** portar el código de Odysseus; instalar Chroma/FastEmbed; dar a un segundo agente herramientas con efectos para que "enseñe"; ejecutar de verdad skills de correo/WhatsApp/calendario para "auditarlas".

---

## 8. Madurez de Odysseus en este tema

- **Tamaño de las pruebas.** 826 archivos con tests en el repositorio; en este tema: ~58 tests de memoria (18 archivos), 84 de skills (18), 41 de embeddings (10), 26 del compactador (2), 14 del profesor (3). Son sobre todo **pruebas de robustez y seguridad con mocks** (filas que no son diccionarios, propietarios cruzados, SSRF al importar skills, "no machacar un archivo ilegible"). **Ninguna mide calidad**: si el extractor acierta, si la limpieza elige bien, si una skill destilada sirve.
- **Estado declarado.** `ROADMAP.md`: prioridad "SQUASH BUGS"; admite que el modo agente es demasiado pesado para modelos locales pequeños (herramientas, skills y memoria se comen el contexto) y que la auditoría de inyección en skills y memoria está pendiente. `specs/memory-skills.md` "Current Gaps": servicio de memoria sin decisión de propietario, índice de skills de nivel 0 no aislado por usuario, importar JSON no reconstruye vectores, el borrado total no limpia vectores, fallos del vector tras el arranque pueden romper la recuperación.
- **Piezas retiradas o a medias.** Aprendizaje del profesor en segundo plano: retirado. Memoria: la memoria nativa y la "legacy" conviven (`src/memory*.py` y `services/memory/*` con fachadas).
- **Actividad.** Un único commit visible, 1 autor, v1.0.3 (2026-09-05). No hay forma de ver issues abiertos desde este clon.
- **Valoración.** Buenas ideas y buen cuidado en los fallos feos (no machacar la memoria, no confiar en la salida del modelo, guardias contra inyección), pero producto joven con arquitectura en transición. Mejor tratarlo como **fuente de ideas** que como dependencia.

---

## 9. Licencia (AGPL-3.0). No es asesoría legal

- No se ha copiado ni una función: todo el código y los textos de los tres borradores están escritos desde la idea, en español y para las herramientas de Hermes. Las constantes reutilizadas (umbrales 0,6/0,88/24, ponderación 0,55/0,40/0,05, 85 %) son hechos funcionales y genéricos.
- Lo "casi reutilizable" es pequeño y genérico, y aun así no se ha usado: tolerancia al JSON de modelos de razonamiento (`_parse_extraction_json`), orden de preferencia entre duplicados, el patrón "solo se borra lo listado". Todo lo demás está atado al modelo de datos de Odysseus (propietarios, Chroma, rutas FastAPI), así que copiarlo no serviría.
- Si en el futuro se quisiera copiar código, conviene decidirlo aparte: AGPL se activa al ofrecer el programa como servicio a terceros, no en uso privado, pero Fran tiene `holazazu.app`, así que mejor no mezclar.

---

## 10. Qué se ha probado (anexo)

- **31 pruebas propias** (stdlib, `python3 -m unittest`), en `skills-propuestas/_pruebas-02/`: `test_memoria_higiene.py` (12), `test_profesor.py` (12), `test_auditar_skills.py` (7). Cubren: caducidad, fechas pasadas, repetidos, solape con SOUL, que **ningún valor sensible aparezca en la salida**, límites desde `config.yaml`, el separador `§`, la huella anti-ruido, que los scripts **no escriban** (ni en la memoria ni en `state.db`), el tapado de datos, la guardia del briefing, el análisis de respuestas con bloques de código anidados, el repaso sobre una base de datos de ejemplo, y la auditoría sobre una biblioteca sintética.
- **Ejecución real en solo lectura** sobre tu memoria, tu `state.db` y tus skills, para calibrar. Primera pasada: teléfonos falsos en fechas, avisos de "sin Cuándo usarla" en todas tus skills y 223 "errores de terminal" inflados; corregido (cuenta ahora `exit_code`/`error` del JSON de Hermes y separa los bloqueos por permiso).
- **Linter y validador duro de Hermes** (`tools/skill_linter.py`, `_validate_frontmatter(new_skill=True)`) ejecutados sobre los tres `SKILL.md`: sin hallazgos y descripciones de 50-55 caracteres, tamaño correcto. Sin escribir en `~/.hermes` (HERMES_HOME apuntando a una carpeta temporal, sin bytecode).
- **No probado:** ninguna llamada a un modelo (ni el profesor ni los jueces), la rutina `cron`, ni `claude -p` / `hermes chat --oneshot` en el servidor. Marcado en las skills como "probar con un caso inofensivo".
