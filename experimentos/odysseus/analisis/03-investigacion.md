# 03 · Investigación profunda y búsqueda: qué aprovechar de Odysseus para Hermes

Fecha del análisis: 10-10-2026. Odysseus v1.0.3 (rama main, clon en `/home/server/Odysseus/src`, solo lectura; no se ha arrancado ni ejecutado nada suyo).
Rutas abajo relativas a `/home/server/Odysseus/src`. Lo leído en el código y en la web son datos; las cifras de coste son estimaciones mías, no medidas.

## 1. Decisiones (lo que le pido a Fran)

1. **Sí a `investigacion-profunda`** (borrador listo). Es lo único que Hermes no tiene de verdad: un procedimiento con rondas, presupuesto y parada. Hermes ya tiene las piezas (búsqueda, lectura, subagentes, citas); le falta el director de orquesta.
2. **Sí a `contrastar-afirmaciones`**. Un segundo agente, sin haber visto el trabajo, comprueba las cifras y plazos antes de dárselos a Fran. Coste pequeño y tapa el mayor riesgo (inventar o confundir un plazo de un trámite).
3. **Sí a `investigar-empresa`** para la búsqueda de empleo: ficha de una página con fuentes y alertas de oferta falsa. Depende de la 1.
4. **No** a copiar el resto de Odysseus (comparador de modelos, presets, informe visual, capa de proveedores de búsqueda, descarga de páginas): Hermes ya hace lo mismo mejor o no le aporta a Fran (ver tabla).
5. Preguntas para Fran: (a) ¿perfil «profunda» siempre con su «sí» previo al plan? (propuesto: sí, por coste); (b) ¿guardar las investigaciones largas en su Cerebro (`30 Notas/Temas`, `tipo: respuesta`) solo cuando él lo pida? (propuesto); (c) probar primero con dos preguntas reales (una de DGT/carnet y una comparativa) y medir el coste con `hermes insights`.

Nada de esto está instalado en `~/.hermes`. Los borradores están en `analisis/skills-propuestas/`.

## 2. Cómo funciona el Deep Research de Odysseus (en corto)

Motor: `src/deep_research.py` (929 líneas), clase `DeepResearcher`, «estilo IterResearch» (Alibaba Tongyi DeepResearch, Apache-2.0, `ACKNOWLEDGMENTS.md:33-38`, `licenses/DeepResearch-Apache-2.0.txt`). Envoltorio y trabajos en segundo plano: `src/research_handler.py` (991). Rutas: `routes/research/research_routes.py`. Búsqueda: `services/search/*` (`src/search/*` son alias). Especificación: `specs/research.md`.

Bucle (`deep_research.py:252-376`):
1. **Plan** (399-424): una llamada al modelo devuelve JSON con 3-6 subpreguntas, temas y criterio de éxito. Clasifica la pregunta en producto / comparación / cómo hacerlo / comprobar (426-456).
2. **Ronda**: el modelo genera 4 consultas (3 en rondas siguientes) (461-502) → busca todas en paralelo (507-531) → lee hasta 3 URL por consulta con un máximo de concurrencia (539-558) → un «extractor orientado a objetivo» devuelve JSON `rational/evidence/summary` por página (609-666, prompt en `src/goal_based_extractor.py`) → actualiza un informe vivo con los últimos 10 hallazgos (671-700) → pregunta al modelo «¿basta? SÍ/NO» (705-732).
3. **Informe final** (737-783): prompt que exige ≥1500 palabras, con enlaces en línea; si salen <400 palabras, reescribe más largo. Plantillas por categoría (148-179).
4. **Límites**: `max_rounds`, `max_time` (300 s por defecto, `research_routes.py:487`), tope duro de 1800 s (`research_handler.py:274-288`), concurrencia 1-12, timeouts por fase. Si algo falla se conserva lo hecho: informe parcial por tiempo/error (356-398) y «informe de hallazgos» si la síntesis falla (`deep_research.py:355-366, 900-913`).
5. Antes de empezar, sondea el modelo con una llamada mínima (`research_handler.py:719-738`). En el chat, un primer mensaje vago provoca 2-3 preguntas de aclaración (`routes/chat_routes.py:1672-1700`). Las investigaciones se guardan en JSON y se pueden continuar sin releer URL ya vistas (`research_handler.py:601-639`, `chat_routes.py:1721-1735`).

Búsqueda: seis proveedores (SearXNG, Brave, DuckDuckGo, Google PSE, Tavily, Serper) con cadena de reserva (`services/search/providers.py:19-27`, `core.py:96-130`), caché de 30 min (noticias) o 24 h (`query.py:144-149`), ranking propio por título/fragmento/dominio/recencia (`ranking.py:99-164`) y una lectura de páginas con tope de bytes, PDF y texto plano (`content.py:181-389`) sobre una descarga anti-SSRF (`src/outbound_fetch.py`).

## 3. Qué tiene ya Hermes y qué le falta de verdad

| Capacidad | Odysseus | Hermes hoy | Hueco real |
|---|---|---|---|
| Buscar | 6 proveedores + reserva + caché | `web_search` con ~11 backends, rotación sin clave con reintento, caché 20 min (`website/docs/user-guide/features/web-search.md`) | Ninguno |
| Leer páginas | BeautifulSoup + pdfminer, tope 2/20 MB | `web_extract` (Firecrawl, etc.), recorte con aviso `[TRUNCATED]`, caché en disco; `markitdown-uv`, `ocr-local`, `blocked-page-recovery`, navegador | Ninguno |
| Subagentes en paralelo | semáforo propio | `delegate_task` hasta 10, `output_schema` validado con 1 reintento, `delegation.model` global | Ninguno (coste por hijo: ver §7) |
| Citas | enlaces escritos por el modelo, sin comprobar | `grounded-citations`: registro `url→[n]`, citas literales comprobadas, `verify` | Ninguno: Hermes va por delante |
| Procedimiento de investigación (plan, rondas, huecos, parada, presupuesto) | sí (en Python) | **No hay** skill; el agente improvisa cada vez | **Sí** → `investigacion-profunda` |
| Lectura aislada con salida estructurada y saneada | solo la primera lectura | no | **Sí** (incluido en la anterior) |
| Verificación semántica (¿la evidencia dice eso?) | no en investigación (solo verificador de tareas, apagado por defecto) | `grounded-citations verify` es sintáctico | **Sí** → `contrastar-afirmaciones` |
| Plantillas de informe por categoría | 4, en inglés, largas | no | **Sí** (en español, cortas) |
| Estado persistente y continuar | JSON por investigación | no | **Sí** (`inv.py`, `--desde`) |
| Vigilar un tema en el tiempo | tarea programada de investigación | `cronjob`, `blogwatcher`, `competitor-news-monitor`, Vigías | Cubierto |

Dato de Hermes que condiciona el diseño: los hijos de `delegate_task` heredan las herramientas del padre (terminal, archivos, web) y no se les puede restringir por tarea; solo `delegation.subagent_auto_approve: false` (valor por defecto, confirmado en `tools/delegate_tool_config.py`) los frena si una página les manda ejecutar algo. Y no encontré en las herramientas web de Hermes ningún envoltorio de «contenido no fiable» equivalente al de Odysseus (solo escaneo de ficheros de contexto): conviene aplicar la idea desde la skill.

## 4. Ideas valiosas, una a una

Escala: valor para Fran 1-5 (busca empleo, estudia el carnet, gestiona vida y servidor) · esfuerzo S/M/L · riesgo = inyección desde páginas web.

**I1 · Bucle iterativo con presupuesto y parada** (`deep_research.py:252-376`, `research_handler.py:240-405`)
- Qué hace: planifica, busca, lee, sintetiza y decide parar; con tope de rondas, tiempo, concurrencia y resultado parcial siempre.
- Hermes: tiene las piezas, no el procedimiento. Falta de verdad: que el tope lo haga cumplir un script (el modelo tiende a seguir buscando).
- Skill: **sí**. Procedimiento en `SKILL.md` + `inv.py` (estado, consultas nuevas, URL canónicas, tope, hallazgos, decisión de parar). Casi tal cual: la forma del bucle (idea genérica). Reescrito: todo lo demás; no hay código portable (es `asyncio` ligado a sus llamadas internas) y los prompts están en inglés.
- Valor 5 · esfuerzo M · coste: Odysseus ≈ 70-90 k tokens por ronda (9-12 páginas de hasta 15 000 caracteres cada una, más síntesis y parada) y 2-5 rondas dentro de 300 s ⇒ 0,3-0,45 M tokens por investigación (estimado del código). El borrador: 0,5 / 2 / 5 M tokens (rápida/estándar/profunda), casi todo releído de caché ⇒ 0,10-0,25 / 0,4-1,0 / 1,5-3,5 USD con Haiku 4.5 (supuesto ~1 y ~5 USD por millón; estimación). Riesgo: medio, mitigado (I5).
- Madurez: 21 tests propios del motor + 130 de manejador/rutas/CLI; todos de regresión y seguridad (rutas, propietarios, JSON mal formado, tiempos). **Ninguno mide la calidad del informe.** Incidencias abiertas relacionadas: #6392, #6351, #6493 (ver §8).

**I2 · Verificador de contexto limpio** (`src/agent_loop.py:3256-3338, 5432-5470`)
- Qué hace: un segundo modelo, sin historial, recibe la petición y un registro de lo hecho y responde `VERIFICATION: SUCCESS/FAIL`; máximo 2 vueltas (`_VERIFIER_MAX_ROUNDS`). La idea explícita: quien revisa su propio trabajo se autojustifica.
- Hermes: `grounded-citations verify` comprueba citas y que las citas literales están en la página; no comprueba que la cita diga lo que la frase afirma.
- Skill: **sí**. Idea casi tal cual (verificador frío, máx. 2 vueltas); reescrito: aplicarlo a afirmaciones, no a tareas; fallar «cerrado» (Odysseus ante un error devuelve «sin fallos», `agent_loop.py:3321-3323`); `reclamaciones.py` elige solo las afirmaciones de riesgo (cifra, fecha, plazo/norma, absoluto) y arma el paquete.
- Valor 4 · esfuerzo S · coste +8-15 k tokens por informe (~0,02-0,05 USD) · riesgo bajo (el paquete se declara «datos»).
- Madurez: en Odysseus está **apagado por defecto** (`agent_verifier_subagent`, `agent_loop.py:5443-5447`: en modelos locales débiles no juzga bien). Tres tests alrededor, ninguno de eficacia. Es una idea, no una función probada.

**I3 · Plantillas por categoría** (`deep_research.py:148-179`)
- Producto, comparación, cómo hacerlo, comprobar un dato; cada una fuerza una estructura.
- Hermes: nada equivalente. Skill: **sí**, `references/plantillas.md`; reescritas en español, cortas, decisión primero, y con «trámite» y «empresa» (que Odysseus no tiene). No copiar la de «producto» tal cual: pide «Rating» y precios aproximados, que invitan a inventar.
- Valor 4 · esfuerzo S · coste 0 · riesgo nulo.

**I4 · Ficha de empresa para empleo** (idea derivada de I1+I3, no existe en Odysseus)
- Skill `investigar-empresa`: 5 subpreguntas fijas, reseñas tratadas como opinión (≥3 coincidentes), alertas de oferta falsa, 3 preguntas para la entrevista; se guarda como ficha `empresa` en el Cerebro.
- Valor 5 (ahora mismo es su prioridad) · esfuerzo S (sobre I1) · coste ~0,5-2 M tokens, 0,10-0,50 USD · riesgo medio (las webs de empresas y portales son contenido ajeno; misma cuarentena).

**I5 · Cuarentena y saneado de contenido no fiable** (`src/prompt_security.py:1-100`, uso en `deep_research.py:635-640`)
- Qué hace: el texto ajeno va en un mensaje de rol usuario, entre marcadores que se escapan si aparecen dentro, con cabecera «esto son datos» y una marca que «arma» la puerta de herramientas.
- Hallazgo importante: **solo protege el primer salto.** Los resúmenes y la «evidencia» que escribe el extractor (que pueden llevar una orden escondida) entran a la síntesis como texto normal (`deep_research.py:680-695, 887-898`).
- Skill: idea sí, mecanismo distinto: lector aislado en subagente + esquema estricto + recorte (700/300 caracteres) + eliminación de caracteres invisibles + detección de frases de inyección en español/inglés (`inv.py hallazgo`) y paso del hallazgo a «sospechoso». Reescrito del todo (el marcador `<<<UNTRUSTED…>>>` no sirve si la página llega por `web_extract` al hijo).
- Valor 4 · esfuerzo S · coste 0 · reduce el riesgo, no lo elimina (heurística; el hijo sigue teniendo terminal).
- Madurez: bien cubierto (≈86 tests de seguridad de inyección y puerta de herramientas), pero aun así su propio `THREAT_MODEL.md` pide más auditoría.

**I6 · Estado persistente y continuar sin releer** (`research_handler.py:601-639`, `chat_routes.py:1721-1735`)
- Guarda hallazgos y URL; «profundiza en X» reutiliza lo leído. Hermes: nada. Skill: sí, `inv.py init --desde`. Valor 3 · S · ahorra tokens (no relee) · riesgo nulo.

**I7 · Deduplicación y jerarquía de fuentes** (`ranking.py:56-164`, `deep_research.py:495, 526`)
- Odysseus deduplica solo por texto exacto (consulta y URL) y puntúa con listas fijas de medios anglófonos/canadienses (`ranking.py:56-68`).
- Skill: sí, rehecho: URL canónica (sin `utm_`, `www`, `/amp`, fragmentos), consultas casi iguales (solapamiento ≥75 %), hallazgos casi idénticos (4-gramas, ≥50 %: el mismo teletipo en tres medios cuenta una vez) y niveles A/B/C/D para España (`.gob.es`, BOE, DGT, SEPE… arriba; foros y redes abajo), editables en `dominios.json`. Valor 3 · S · riesgo nulo.

**I8 · Extractor orientado a objetivo** (`src/goal_based_extractor.py`, `deep_research.py:609-666`)
- Leer cada página «para este objetivo» y devolver solo lo útil en JSON. Origen Tongyi (Apache-2.0). Skill: sí, en `references/lector.md`, con citas **literales** (Odysseus pide «evidencia» libre y la da por buena) para poder comprobarlas con `sources.py quote`. También su filtro de «baja calidad» por frases (`research_utils.py:32-49`) NO se copia: funciona solo en inglés y descarta resúmenes legítimos que contengan «does not contain»; aquí el lector marca `relevante` en el esquema.
- Valor 4 · S · coste: es el grueso del gasto (una página ≈ 15-25 k tokens procesados por el hijo) · riesgo: el más alto (lee la web), de ahí la cuarentena.

**I9 · Aclaración previa y plan a la vista** (`chat_routes.py:1672-1700`, `research_handler.py:92-171, 173-218`)
- Pregunta 2-3 cosas si la petición es vaga; reescribe la conversación en una sola pregunta (con el fallo clásico de investigar la palabra «sí», líneas 105-134). El «plan para revisar» (`generate_plan`) **no está conectado a ninguna ruta** (solo definido en la 173).
- Skill: sí, pasos 1-2; en `profunda` se enseña el plan y se espera el «sí». Los subagentes no ven la conversación, así que la pregunta completa es obligatoria. Valor 3 · S · coste 0.

**I10 · Límites de coste y tiempo; resultado parcial siempre** (`research_handler.py:274-288, 356-398`, `deep_research.py:296-298, 326-336`)
- Skill: sí, como perfiles `rapida/estandar/profunda` que `inv.py` hace cumplir (rondas, páginas, consultas, minutos, páginas por ronda, saturación tras 2 rondas sin novedades). Pega con `hermes-cost-control`. Valor 4 · S.
- Trampa a evitar: en modo «Auto» Odysseus pone `max_rounds=20` y `min_rounds=max_rounds-2` (`research_routes.py:562`, `research_handler.py:822`), y solo pregunta «¿basta?» desde la ronda 18 (`deep_research.py:346`): el «el modelo decide cuándo parar» no ocurre; manda el reloj de 300 s.

**I11 · Investigación programada** (`src/task_scheduler.py:2014-2120`)
- Tarea periódica que ejecuta el mismo motor (10 min). En Hermes ya se hace con `cronjob` + skills de vigilancia. Valor 2-3 · S: se podrá lanzar `investigacion-profunda` en perfil `rapida` desde un cron cuando haya un tema concreto (p. ej. cambios en normas de examen). No requiere nada nuevo ahora.

**I12 · Capa de proveedores de búsqueda** (`services/search/providers.py`, `core.py`)
- Abstracción simple (`{title,url,snippet,age}`), cadena de reserva, SafeSearch por proveedor. Hermes ya tiene más backends, rotación y caché. Valor 1. Lección: Odysseus fija `language=en` en SearXNG (`providers.py:154-159`; incidencia abierta #6392) y devuelve basura para consultas en español. Si algún día Fran monta SearXNG, fijar `es-ES`.

**I13 · Descarga y limpieza de páginas** (`content.py:181-389`, `outbound_fetch.py`)
- Heurística de «contenido principal», PDF, tope de bytes, defensa SSRF con DNS fijado. Hermes: `web_extract` + `markitdown-uv` + `blocked-page-recovery` + política de URLs privadas. Valor 1. Nada que copiar; mis scripts no descargan nada (así no hay superficie SSRF).

**I14 · Compare (comparación ciega de modelos)** (`routes/compare/compare_routes.py`, `static/js/compare/*`, `specs/compare.md`)
- Es una interfaz de paneles lado a lado con voto, marcador, modo ciego (aleatoriza izquierda/derecha, `compare_routes.py:95-99`), «preguntas de evaluación» con respuesta esperada que se auto-califica por **subcadena o número** (`stream.js:878-919`), y comparar proveedores de búsqueda con un análisis por modelo (`index.js:777`). El modo ciego es solo enmascarado de interfaz (`specs/compare.md`, «Policy Notes»).
- Para verificar respuestas no ayuda: no cruza ni sintetiza respuestas entre sí con rigor. Lo útil ya está en I2. Una versión mínima (banco de 10 preguntas con respuesta conocida para vigilar si la búsqueda empeora) tendría valor 2 · S; no la propongo ahora. Hermes tiene MoA, apagado por coste.

**I15 · Presets** (`src/preset_manager.py:9-60`)
- Cuatro personajes (`code_analyze`, `brainstorm`, `reason`, `custom`) con temperatura, tope de tokens y prompt. Son personalidades, no perfiles de investigación. Hermes tiene `SOUL.md` y skills. Valor 1. Lo aprovechable —perfiles de esfuerzo— ya va en I10. (El «ROADMAP» de Odysseus habla de presets por hardware para modelos locales: no aplica.)

**I16 · Informe visual en HTML** (`src/visual_report.py`, 1933 líneas)
- Markdown → página con índice, imágenes y filtro `nh3`. Hermes ya tiene `pdf`, `docx` y artefactos. Superficie de XSS propia (`specs/research.md`, «Security Policy»). Valor 2 · M · no.

## 5. Trampas del código de Odysseus que NO se deben copiar

1. Citas = enlaces que escribe el modelo, sin registro ni comprobación (`deep_research.py:141`): puede inventar URL. Hermes ya lo resuelve mejor.
2. Informe «de revista» de ≥1500 palabras y reescritura si salen menos de 400 (136, 755-780): lo contrario de lo que Fran necesita (decisión primero).
3. Segundo salto de inyección sin envolver (I5).
4. Filtro de calidad por frases en inglés (I8) y búsqueda fijada en inglés (I12).
5. Parada «inteligente» que no actúa antes de la ronda 18 (I10).
6. `generate_plan` sin conectar y verificador apagado por defecto: partes anunciadas que no están en marcha.
7. Código duplicado (`services/research/research_handler.py` y `src/research_handler.py`; `src/search/*` a medias) que su propio modelo de amenazas reconoce como deuda (`THREAT_MODEL.md`, «Known Gaps» 3).

## 6. Tabla final, ordenada por valor/esfuerzo

| # | Idea | Valor | Esfuerzo | Tokens por uso (estim.) | Riesgo inyección | Va en | Veredicto |
|---|---|---|---|---|---|---|---|
| 1 | I2 Verificador de contexto limpio | 4 | S | +8-15 k | bajo | `contrastar-afirmaciones` | Hacer |
| 2 | I5 Cuarentena y saneado | 4 | S | 0 | reduce | `investigacion-profunda` | Hacer |
| 3 | I10 Presupuesto y parcial siempre | 4 | S | ahorra | reduce coste | `investigacion-profunda` | Hacer |
| 4 | I3 Plantillas por categoría | 4 | S | 0 | nulo | `investigacion-profunda` | Hacer |
| 5 | I4 Ficha de empresa (empleo) | 5 | S (tras I1) | 0,5-2 M | medio | `investigar-empresa` | Hacer |
| 6 | I6 Estado y continuar | 3 | S | ahorra | nulo | `investigacion-profunda` | Hacer |
| 7 | I9 Aclaración y plan a la vista | 3 | S | 0 | nulo | `investigacion-profunda` | Hacer |
| 8 | I7 Dedupe y niveles de fuente | 3 | S | ahorra | nulo | `investigacion-profunda` | Hacer |
| 9 | I1 Bucle iterativo completo | 5 | M | 0,5 / 2 / 5 M | medio | `investigacion-profunda` | **Hacer primero** (base de las demás) |
| 10 | I8 Lector orientado a objetivo | 4 | S | es el grueso | alto, aislado | `investigacion-profunda` | Hacer |
| 11 | I11 Investigación programada | 2-3 | S | repetido | medio | cron + skill 1 | Más adelante |
| 12 | I14 Compare / banco de evaluación | 2 | S-L | pequeño | bajo | — | No ahora |
| 13 | I16 Informe visual | 2 | M | — | XSS | — | No |
| 14 | I12 Proveedores de búsqueda | 1 | — | — | — | — | No (Hermes ya lo tiene) |
| 15 | I13 Descarga/limpieza de páginas | 1 | — | — | — | — | No |
| 16 | I15 Presets | 1 | — | — | — | — | No |

Nota sobre el orden: I1 es la base y las demás filas «Hacer» son componentes suyos o dependen de ella; por eso se instala primero aunque su esfuerzo sea M.

## 7. Los borradores (`analisis/skills-propuestas/`)

| Skill | Archivos | Qué hace | Probado |
|---|---|---|---|
| `investigacion-profunda` | `SKILL.md` (93 líneas), `scripts/inv.py`, `references/lector.md`, `references/plantillas.md`, `dominios.json` | Procedimiento de 8 pasos con perfiles; el script guarda estado, filtra consultas/URL repetidas, puntúa fuentes, sanea hallazgos y dice cuándo parar | `inv.py` probado a mano en un directorio temporal: tope por ronda, URL canónicas, duplicados, frases de inyección, saturación, `--desde`. El procedimiento completo (subagentes reales) **no** se ha ejecutado |
| `contrastar-afirmaciones` | `SKILL.md` (66 líneas), `scripts/reclamaciones.py` | Elige afirmaciones de riesgo, arma el paquete para el verificador y resume su veredicto (falla cerrado) | Probado el script con un borrador y un registro de ejemplo; el verificador real no |
| `investigar-empresa` | `SKILL.md` (61 líneas) | Ficha de una página para candidatura/entrevista sobre la skill 1 | Solo texto |

Todas con descripción ≤60 caracteres, sin tocar el núcleo, Python estándar, nada de claves. Coste de los subagentes: cada «lector» arrastra el sistema y las herramientas de Hermes (no medido); por eso van 1-2 páginas por tarea y tope de 5 tareas por tanda. El motivo principal de usar lectores no es ahorrar (leer en el contexto principal costaría parecido por las relecturas) sino **seguridad**: la página nunca llega al agente que tiene las llaves.

Para instalarlas (cuando Fran diga que sí): copiar las carpetas a `~/.hermes/skills/research/` (las dos primeras) y `~/.hermes/skills/productivity/` (la tercera), abrir sesión nueva (el cargador se cachea) y probar con las dos preguntas de §1. Revisar antes que la primera ejecución no deje nada en `~/.hermes/cache/investigacion/` más allá de los JSON de estado.

## 8. Madurez y licencia

- Proyecto joven y muy activo: según la página de GitHub (consultada hoy, resumen de WebFetch, no verificado a mano) ≈92 600 estrellas, ≈1 100 incidencias abiertas y ≈317 PR abiertas. El clon local es un único commit («Merge commit from fork»), así que no se puede medir historial de errores. ROADMAP: «SQUASH BUGS» es la prioridad alta.
- Incidencias abiertas relevantes (títulos de la página): #6392 SearXNG fija `language=en` y rompe consultas no inglesas; #6493 `web_fetch` no devuelve texto de PDF en Docker (falta pdfminer); #6351 la «derivación» de un informe lo siembra como mensaje de sistema (superficie de inyección); #6618 y #6431 piden más proveedores.
- Tests: ≈4 933 funciones de test en 826 ficheros. Investigación 151 (21 del motor + 130 de manejador/rutas/utilidades), búsqueda 64, descarga y herramientas web 39, seguridad de inyección 86, comparar 32, presets 11. Cubren robustez, rutas y propietarios. No hay evaluación de calidad de las respuestas ni de la búsqueda.
- Licencia: Odysseus es AGPL-3.0; su núcleo de investigación se adapta de Tongyi DeepResearch (Apache-2.0). Los borradores están escritos desde la idea: ni código ni prompts copiados (reescritos en español, otra estructura, otros nombres de campos, otros umbrales y listas de dominios). Lo que sirve «tal cual» son ideas no protegibles (bucle plan-buscar-leer-sintetizar, verificador sin historial, límite de 2 vueltas). Si en el futuro se quisiera reutilizar un fragmento literal (p. ej. el prompt del extractor), habría que revisar la licencia (Apache-2.0 es permisiva; AGPL no) y su atribución. No es asesoría legal.

## 9. Límites de este análisis

- No se ejecutó Odysseus ni sus pruebas: todo lo dicho de su comportamiento sale de leer el código y las especificaciones.
- Las estimaciones de tokens y dólares salen del código (Odysseus) y de supuestos de tamaño (Hermes: sistema y herramientas por hijo, relecturas de caché, precios de Haiku 4.5). Hay que medir la primera ejecución real con `hermes insights --days 1` y ajustar los perfiles.
- La eficacia anti-inyección del diseño es una mejora por capas, no una garantía; lo decisivo sigue siendo que el principal no ejecute nada porque lo diga una página y que los subagentes mantengan la aprobación manual.
