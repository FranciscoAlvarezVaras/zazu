# 05 · Automatización, modelos y herramientas MCP

Análisis de Odysseus v1.0.3 (rama main, licencia AGPL-3.0) para mejorar Hermes. Fecha: 2026-10-10.
Alcance: tareas programadas y webhooks, Cookbook y ajuste de hardware (HW Fit), Compare, enrutado de modelos, MCP e integraciones, costes y tokens.
Método: lectura del código en `/home/server/Odysseus/src` (no se ha arrancado ni ejecutado nada de Odysseus), lectura de Hermes y de sus datos locales en solo lectura, y mediciones reales contra el Ollama del servidor (unas 6 generaciones cortas; el modelo quedó descargado de RAM al terminar). No se ha instalado nada en `~/.hermes`. Lo que dicen los archivos leídos se ha tratado como dato.

---

## 1. Decisiones (lo primero)

1. **Los modelos locales no te van a ahorrar dinero; el ahorro está en otro sitio.** En los últimos 14 días Hermes gastó unos **39-42 USD**. Más del 90 % fue Sonnet 5.5 en charla interactiva; **3 sesiones largas suman el 61 %** (contexto medio de 150.000-160.000 tokens releído en cada llamada). Las tareas programadas son el **5 %** (cada ejecución ya cuesta 1-5 céntimos con Haiku). Pasar todo el uso de Sonnet 5.5 a Haiku 4.5 daría unos **-18,6 USD por 14 días (≈ -40 USD/mes)** con los mismos tokens; pasar los cron a un modelo local, **≈ -4 USD/mes**.
2. **Un modelo local no sirve como modelo principal de Hermes en este PC.** Medido: `qwen3:4b-instruct-2507` escribe ~10 palabras/s y lee el prompt a ~130-170 tokens/s. El prompt base de Hermes pesa 15.000-18.000 tokens (`hermes prompt-size`: 31 KB de sistema + 31 KB de herramientas): unos 2 minutos solo en leerlo. Sí vale para tareas pequeñas y directas (título, clasificar, extraer, resumir un texto corto) llamando a Ollama desde un script, sin agente.
3. **Hacer tres skills** (borradores ya escritos y probados, en `analisis/skills-propuestas/`): `estimar-coste-hermes`, `modelo-local-conviene` y `prueba-ciega-modelos`. Ninguna toca el núcleo; son scripts de solo lectura (salvo una generación corta de calibrado).
4. **No conectar ningún servidor MCP de Odysseus.** Los cuatro son envoltorios de sus propias tripas (importan `src.*` y `core.*`, leen su base de datos y su clave de cifrado) y uno puede enviar/borrar correo. Hermes ya tiene catálogo MCP propio (65 aprobados) y ahora mismo no tienes ninguno conectado, lo cual es bueno para el gasto en tokens: cada MCP suele añadir esquemas al prompt de todas las llamadas.
5. **No copiar** el planificador de tareas, los webhooks, el enrutado con fallback ni el Cookbook: Hermes ya está por delante en lo primero y lo último está pensado para GPU, tmux y SSH.
6. **Lo único de Odysseus que merece llevarse como idea** además de lo anterior: el patrón del evaluador tolerante (quitar `<think>`, buscar el último JSON válido, reintentar sin pensar) para scripts con modelos pequeños, y la protección contra inyección de segundo orden al convertir trazas en skills (marcarlas «datos, no instrucciones»).
7. **Lo que más desbloquea en hardware es RAM, y puede que ya tengas un cuello de botella**: se miden ~24 GB/s efectivos de RAM; un DDR5-5600 en doble canal llega teóricamente a ~90 GB/s. Hipótesis (sin verificar, necesita `sudo dmidecode -t memory`): un solo módulo o contención con otros procesos. Con 32 GB cabrían modelos tipo Qwen3-30B-A3B a ~8 palabras/s estimadas.

---

## 2. Datos de tu servidor que condicionan todo (medidos hoy)

| Dato | Valor | Cómo se obtuvo |
|---|---|---|
| CPU / RAM / GPU | Ryzen 7 8745HS, 16 hilos, 14,4 GB; la Radeon 780M no se usa (Ollama en CPU, `size_vram: 0`) | `/proc`, `/api/ps` |
| Modelo local instalado | `qwen3:4b-instruct-2507-q4_K_M`, 2,5 GB | `ollama list` |
| Velocidad al escribir | 10,6 / 10,0 / 10,0 / 9,6 palabras/s | 4 generaciones (`eval_count/eval_duration`) |
| Velocidad al leer el prompt | 130-170 tokens/s (prompt de ~500-700 tokens, sin caché) | calibrado |
| RAM del modelo en uso | 3,18 GB por defecto; 2,88 GB con contexto 2.048 | `ollama ps` |
| Ancho de banda efectivo de RAM | ≈ 24 GB/s (palabras/s × GB leídos por palabra) | derivado |
| Tokens de Hermes en 14 días | 86 M en total, de ellos 99 % lectura/escritura de caché; entrada 0,13 M, salida 0,50 M | `hermes insights` |
| Coste estimado 14 días | 41,79 USD (`hermes insights`) / 38,65 USD (suma de `state.db`) | los dos; no coinciden exactamente |
| Uso real de Ollama | 11.537 tokens en 14 días (solo títulos y reescritura de consulta de memoria) | `hermes insights` |
| Prompt de un cron hoy | 1 llamada, ~8.000 tokens, 0,01-0,02 USD | `state.db` |

Consecuencia: el contexto largo manda sobre el modelo. La palanca es el tamaño del contexto y el modelo por defecto, no la tecnología local.

Ollama 0.40.0 corre sin variables de entorno (unidad systemd sin `Environment=` de Ollama). Con el modelo cargado, 3,18 GB = 2,5 GB de pesos + ~0,6 GB de caché de atención, que corresponde a un contexto de ~4.096 tokens. Es decir, Ollama parece usar 4k por defecto y **recortaría en silencio** un prompt de 16k. (Dato inferido de la aritmética de memoria, no probado con un prompt largo.)

---

## 3. Fichas de ideas

### A. HW Fit: «qué modelo cabe en mi hardware y a qué velocidad»

1. **Qué hace y cómo.** Detecta hardware (`services/hwfit/hardware.py`, `detect_system` L792-907: RAM de `/proc/meminfo`, CPU, NVIDIA/AMD/Apple), recorre un catálogo de modelos (`data/hf_models.json`, 924 entradas) y para cada uno calcula memoria = parámetros × bytes por cuantización + caché de contexto (`models.py` `QUANT_BPP` L7-24, `estimate_memory_gb` L192-199: `0,000008 × params_activos × contexto`), elige la mejor cuantización que quepa (`best_quant_for_budget` L210-243, recorta contexto a la mitad si hace falta) y estima velocidad: en GPU = ancho de banda ÷ tamaño del modelo × 0,55 (`fit.py` `_estimate_speed` L184-235, tabla `GPU_BANDWIDTH` L9-26); en CPU = constante 70 ÷ parámetros × factor de cuantización (`FALLBACK_K` L52). La puntuación final mezcla calidad (cubo por tamaño + bonus por familia, `_quality_score` L259-306), velocidad, ajuste y contexto con pesos por uso (`analyze_model` L431-624, `rank_models` L708-876). `profiles.py` (L91-238) propone perfiles Quality/Balanced/Speed con tipo de caché KV (q8/q4) y capas MoE en CPU. `hf_discovery.py` refresca el catálogo desde colecciones de Hugging Face (caché de 24 h).
2. **Qué tiene Hermes y qué falta.** Nada equivalente. `hermes-model-cost-routing` solo lista modelos de Nous y precios; no hay ninguna ayuda para elegir un modelo local. Falta de verdad.
3. **¿Skill sin tocar el núcleo?** Sí. Hecho: `modelo-local-conviene` (solo CPU/Ollama, catálogo de 21 modelos). Casi tal cual (hechos numéricos, no expresión): tabla de bits por peso de las cuantizaciones y la idea «ancho de banda ÷ pesos activos». Reescrito: detección, catálogo, ranking. **Cambio clave respecto a Odysseus: la constante de velocidad se mide** (`calibrar`) en lugar de suponerla. Comprobado contra tus mediciones: la constante de CPU de Odysseus daría 20 palabras/s para tu modelo de 4B (real: 10), y su estimación de caché de contexto es 0,13 GB a 4k y 1,05 GB a 32k frente a 0,60 y 4,83 GB reales (36 capas × 8 cabezas KV × 128 × 2 × 2 bytes). El script lee la arquitectura real de `/api/show` cuando el modelo está instalado.
   - Licencia: HW Fit es una adaptación de **llmfit (MIT)**, así que la idea es reutilizable con atribución; los cambios de Odysseus son AGPL. No hay texto de Odysseus en el borrador.
4. **Valor 4/5 · Esfuerzo S (borrador listo) · Riesgo bajo.** Riesgo: catálogo con etiquetas de Ollama sin verificar (las de modelos posteriores a 2025 van a `null` y exigen búsqueda); «nivel» de calidad subjetivo.
5. **Madurez en Odysseus.** 17 archivos de tests / ~99 pruebas de hwfit y 26 / ~186 de Cookbook, pero su propio `ROADMAP.md` dice que el ranking «puntúa casi todo igual» y que Cookbook es lo más probable que falle en otros equipos. Catálogo: de 924 entradas, 705 son autodescubiertas, 42 son modelos de prueba de <0,2B y solo 127 traen GGUF. Issues abiertas (GitHub, página de issues): 1.149; entre las recientes, «llama.cpp solo-CPU se cae con Vulkan sin CUDA» (#6656) y «el escaneo de hardware elige la GPU integrada» (#6612), justo tu caso (APU AMD).

**Predicción para tu PC** (salida del borrador, contexto 8k, reserva 5 GB, calibrado hoy): Qwen3 4B 2507 ~8,4 palabras/s; Phi-4 mini ~8,5; Gemma 3 4B ~6,6; Qwen3 1,7B ~14; LFM2 8B-A1B (MoE, tamaño estimado) ~16; los de 8-9B caben pero van a 4 palabras/s o menos; Qwen3 14B, Gemma 3 12B, gpt-oss 20B y los MoE de 30B+ no caben. Con `--simular-ram 32`: Qwen3 30B-A3B ~8,3 palabras/s y 20 GB.

### B. Compare: prueba ciega de modelos

1. **Qué hace y cómo.** Lanza el mismo mensaje a 2-N modelos en paneles (`static/js/compare/*`, ~5.400 líneas de JS: `index.js` orquesta, `panes.js`, `stream.js`, `selector.js`, `vote.js`, `scoreboard.js`). Modo ciego: sesiones `[CMP] Model A/B…` con nombre neutro (`index.js` L248-250, `panes.js` L385-406) y barajado de posiciones (`index.js` L514). El usuario vota y `scoreboard.js` L81-176 saca victorias/derrotas/empates, % de victorias y coste medio por 1.000 respuestas. El backend (`routes/compare/compare_routes.py`, 365 líneas) solo guarda votos (`/api/compare/record`); las rutas `/start` y `/vote` son antiguas y ya no las usa la interfaz.
2. **Hermes.** `moa` (mezcla de agentes, desactivado y caro) y evals internos de desarrollo; nada para que un usuario compare modelos con sus frases. Falta de verdad.
3. **¿Skill?** Sí, sin interfaz: hoja numerada para votar por chat. Hecho: `prueba-ciega-modelos` (`preparar` → hoja anónima + clave aparte; `votar "1A 2B 3= 4-"`; `revelar` con victorias, segundos, palabras/s, tokens y coste). Del código de Odysseus no se aprovecha nada (es interfaz); solo la idea, que es genérica. Concursantes: `ollama:<etiqueta>` (gratis) y `hermes:<modelo>@<proveedor>` (usa `hermes -z --usage-file`, de modo que Hermes gestiona las claves y calcula el coste).
   - Avisos de diseño: (a) `hermes -z` **aprueba acciones automáticamente** (modo YOLO) y carga tus herramientas; el script lo limita a la herramienta inofensiva `clarify`. (b) Cada llamada a la nube arrastra el prompt base de Hermes (~15.000 tokens), así que 10 frases × 2 modelos ≈ 300.000 tokens de entrada: pide permiso y estima antes. (c) Comparar `ollama:` con `hermes:` no es del todo justo (distinto prompt y personalidad).
4. **Valor 4/5 · Esfuerzo M (borrador listo; falta probar el camino `hermes:` con tu autorización) · Riesgo bajo-medio** (nube = coste y envío de frases a un tercero).
5. **Madurez en Odysseus.** Su especificación admite que el modo ciego «no es una frontera de confidencialidad» (la identidad sigue en el estado del cliente), que las rutas antiguas aceptan URL de endpoint sin las mismas reglas y que la gestión de errores de los paneles es más floja que la del chat. 6 archivos de tests (ayudantes y redacción del modo ciego, no el flujo completo). No hay modelo-juez automático; yo tampoco lo he puesto (un 4B puntuando es poco fiable).

### C. Costes y tokens

1. **Qué hace Odysseus.** Solo mostrar: tabla fija `MODEL_INFO` en JavaScript (`static/js/chatRenderer.js` L495-583, ~85 modelos con entrada/salida/contexto), `getModelCost` L812-818 = `(entrada×p_in + salida×p_out)/1e6`, y `isLocalEndpoint` L829-849 (loopback, LAN, Tailscale o nombre sin punto = gratis). En Python solo hay una bandera `endpoint_cost_tracked` (`src/endpoint_resolver.py` L31). **No distingue caché**, y para ti la caché es el 99 % de los tokens. La tabla ya está anticuada (Haiku «4» a 0,80/4; no conoce Sonnet 5 ni Opus 5). No hay estimación previa de tareas.
2. **Hermes.** Mucho mejor: `agent/usage_pricing.py` (precios con caché, modelos.dev, vigencias), `hermes insights`, `--usage-file` en `hermes -z`, `cron/usage_audit.jsonl`, y las skills `hermes-cost-control` y `hermes-model-cost-routing`. Lo que falta de verdad: desglose por origen y por tarea programada, simulación «qué pasaría si», y estimación previa de una tarea.
3. **¿Skill?** Sí. Hecho: `estimar-coste-hermes` (`resumen`, `que-pasaria-si`, `tarea`; lee `state.db` en solo lectura). De Odysseus solo la idea de que lo local es gratis. Precios copiados de lo que ya usa Hermes (`references/precios.json`, marcado «no oficial»).
4. **Valor 4/5 · Esfuerzo S · Riesgo bajo** (solo lectura; riesgo de precio desactualizado).
5. **Madurez.** Sin tests propios de precios en Odysseus; irrelevante porque no se reutiliza código.
- Dos detalles de Hermes a revisar (no son de Odysseus): `claude-sonnet-5` aparece con precio de lanzamiento (2/10 USD) que el propio comentario del código da por terminado el 2026-08-31 (4 sesiones, 2 USD); y `model.default` es Haiku 4.5, pero las sesiones del hub, de WhatsApp y de la CLI constan con Sonnet 5.5: alguien lo cambió con `/model` o un perfil.

### D. Enrutado «modelo pequeño → profesor grande»

1. **Qué hace y cómo.** `src/teacher_escalation.py` (810 líneas): tras cada turno de agente en un modelo «alumno», detecta fallo con expresiones regulares sobre las salidas de herramientas y la respuesta (L52-105; «Unknown action», «I don't have a tool»…) o con un evaluador LLM barato (Nivel 2, `evaluate_turn_llm`); si falla, `run_teacher_inline` (≈L530-810) deja que un modelo grande **tome el control en directo**, y si lo consigue destila lo que funcionó en un SKILL.md que el usuario debe aprobar de forma exacta antes de guardarlo. Hay una protección útil: la traza se marca `<<<UNTRUSTED_TRACE>>>` como datos para que una inyección de prompt no acabe grabada en una skill (L127-141). Además existe la herramienta de agente `ask_teacher` (`agent_tools/model_interaction_tools.py`). Ajustes: `teacher_enabled`, `teacher_model`, `teacher_tier2_enabled`. Aparte, `src/foreground_model_routing.py` (206 líneas): cadena de fallback ordenada, solo ante fallos de disponibilidad (408, 425, 429, 5xx, 529) y antes de producir contenido, con consentimiento explícito, tope de 10 y ruta «anclada» una vez hay respuesta.
2. **Hermes.** Cubre casi todo: `delegation.model` (subagentes con modelo barato), `auxiliary.*` (ya tienes título y reescritura de memoria en Ollama), `hermes fallback`, `moa` y el aprendizaje de skills (curator, `creation_nudge_interval`). Falta la detección automática «el modelo barato falló, sube al grande». Pero eso solo importa si el modelo barato es el principal, y hemos visto que en local no lo es.
3. **¿Skill?** Un hook en cada turno sería la forma técnica, pero no compensa. Otro analista ya tiene un borrador `profesor-escalar`; no lo duplico. Versión manual barata: si un script local falla con las reglas simples, avisar a Fran para pasar a Haiku con `/model`. Reescribir desde la idea: los prompts del profesor son expresivos y no se copian.
4. **Valor 2/5 · Esfuerzo L (hook/plugin) · Riesgo medio** (coste oculto por turno, inyección de segundo orden).
5. **Madurez.** El aprendizaje en segundo plano está **retirado** en el propio código (`escalate_and_learn` devuelve `None`, L≈434); solo queda el modo en directo con aprobación. Su `ROADMAP.md` admite que el modo agente es «demasiado pesado para modelos locales pequeños» (esquemas, skills y memoria se comen el contexto): confirma lo medido aquí.

### E. Tareas programadas de agente y webhooks

1. **Qué hace y cómo.** `src/task_scheduler.py` (2.675 líneas) + `routes/task/task_routes.py` (1.181): tareas LLM, de investigación y «de acción» (`BUILTIN_ACTIONS`, `builtin_actions.py` L3394-3436: 18 acciones como ordenar sesiones, resumir correo, `daily_brief`, `run_script`, `ssh_command`, `cookbook_serve`, `test_skills`/`audit_skills`), disparadores `schedule | event | webhook` (L151; webhook con token en la URL, L1045-1084), cadenas `then_task_id` validadas (mismo dueño, sin ciclos), estados `queued/running/success/error/skipped/aborted` (un «nada que hacer» queda como `skipped` con su motivo), aplazamiento si no es el momento, y **puerta de primer plano** (`interactive_gate.py`: el trabajo de fondo espera a que la interfaz esté quieta y se cancela si el usuario vuelve). Webhooks salientes: `src/webhook_manager.py` (455 líneas), 4 eventos, firma HMAC y bloqueo de redes privadas con fijación de DNS.
2. **Hermes.** Por delante: cron con `--no-agent --script`, `monitor_script`/`monitor_url` (despierta al agente solo si algo cambió; ya lo usas en «Vigía de entrevistas»), `context_from`, `[SILENT]`, `hermes webhook subscribe`, ledger de entregas, `hermes pause`, bloqueos de ciclo de vida, incidentes. Tus 10 tareas ya siguen el patrón correcto (un script recoge los datos, Haiku los resume, sin herramientas).
3. **¿Skill?** Nada que portar salvo, quizá, la puerta de primer plano para trabajos pesados con modelo local: un script de 10 líneas que no arranque si la carga es alta o `ollama ps` muestra algo cargado.
4. **Valor 1-2/5 · Esfuerzo S · Riesgo bajo.**
5. **Madurez.** 22 archivos / ~57 pruebas de tareas y webhooks; su especificación reconoce poca cobertura de rutas, y entre sus issues recientes hay borrados peligrosos («Chats Tidy borra respuestas largas», «Bulk Delete puede borrar correo definitivamente», #6609, #6632). Razón de más para no importar sus acciones.

### F. Cookbook (descargar y servir modelos)

Lo que hace: descarga desde Hugging Face, sirve con vLLM/SGLang/llama.cpp/Ollama/MLX dentro de sesiones tmux (local o por SSH), diagnostica fallos, programa arranques (`cookbook_serve`) y guarda estado en `data/cookbook_state.json` (`routes/cookbook_routes.py` 4.583 líneas, `cookbook_helpers.py` 1.482, ~17.600 líneas de JS). Es una superficie de ejecución de comandos solo para administradores, orientada a GPU. Para ti, con Ollama en CPU, `ollama pull` ya hace lo necesario. **Valor 1 · Esfuerzo L · No hacer.**
Una pieza pequeña sí es aprovechable: `/api/cookbook/hf-latest` (`cookbook_routes.py` L3518-3620) consulta la API pública de Hugging Face (tendencias), estima tamaño por el nombre del repo (×1,3 de margen) y filtra lo que cabe. En Hermes sería un cron mensual `--no-agent` que te avise por WhatsApp de modelos nuevos que caben en tu RAM, a coste cero de tokens. **Valor 2 · Esfuerzo S-M.** Mejor que usar el MCP oficial de Hugging Face del catálogo de Hermes, que añadiría esquemas al prompt.

### G. MCP e integraciones: qué hay y qué se puede conectar

| Servidor (`mcp_servers/`) | Qué hace | Hallazgos | Veredicto |
|---|---|---|---|
| `email_server.py` (2.912 líneas, 16 herramientas) | Lista/lee/busca correo, **envía, responde, borra, archiva, desuscribe, acciones en lote** | Lee las cuentas de `data/app.db` y descifra con `src.secret_storage`; importa `src.*`, `core.*`, `routes.*`; sin anotaciones de solo lectura. Issue abierta de borrado definitivo de correo (#6632) | **No.** Duplica Google Workspace (`zgog`) y expone envío/borrado |
| `memory_server.py` (285) | `manage_memory` (listar, añadir, editar, borrar, buscar) | Usa `src.memory` y `memory.json` de Odysseus | **No.** Crearía una segunda memoria divergente de la de Hermes/Cerebro |
| `rag_server.py` (160) | `manage_rag`: indexar o quitar **directorios** | Usa su ChromaDB; `add_directory` indexa rutas arbitrarias | **No.** Fuga de documentos a un índice paralelo |
| `image_gen_server.py` (184) | `generate_image` por API compatible con OpenAI | Depende de sus ajustes y de un endpoint de imagen | **No.** Hermes ya tiene `image_gen` |
| `builtin_mcp.py`: navegador | `npx -y @playwright/mcp@latest` | Versión sin fijar (cadena de suministro); Hermes ya trae navegador | **No** |

Los cuatro hacen `sys.path.insert(<raíz de Odysseus>)`: «conectarlos tal cual» obliga a ejecutar el código y las dependencias de Odysseus (SQLAlchemy, ChromaDB…), justo lo que no debe hacerse, y «aislados» no funcionarían sin su base de datos. `integrations/` **no son MCP**: paquetes de skill para Claude Code/Codex que llaman a `/api/codex/*` con un token por permisos; ya usas lo equivalente (`odysseus-herramienta`, token de documentos y calendario). Nunca concedas el permiso `cookbook:launch`: ejecuta comandos de shell por SSH.
Idea útil dentro de `src/mcp_manager.py` L107-132: `mcp_tool_is_readonly` clasifica una herramienta como solo-lectura por su anotación `readOnlyHint` o, si falta, por el verbo del nombre (`list/get/read/search/fetch/query/find…`), y **falla cerrado** (dudoso = escritura). Si algún día conectas un MCP, un pequeño auditor así te diría qué herramientas pueden modificar cosas (Hermes ya permite activarlas una a una con `hermes mcp configure`). Valor 2 si hubiese MCPs; hoy 0 conectados.

### H. Otras piezas pequeñas

- **Evaluador tolerante** (`routes/skills_routes.py` `_eval_skill_run` L127-282): quita bloques `<think>` aunque queden abiertos, recorre todos los `{…}` y se queda con el último que trae `verdict`, y reintenta pidiendo «sin pensar». Útil para cualquier script con un 4B. Ya incorporado en `prueba_ciega.limpiar()`. Un «ayudante para llamar a Ollama desde un cron sin agente» (límite de tiempo, JSON tolerante, un solo modelo a la vez, descarga de RAM) tendría **valor 3, esfuerzo S**; no he escrito borrador para no pasar de tres.
- **Presets** (`preset_manager.py`, 190 líneas): prompts de sistema con temperatura. Hermes tiene personalidades, perfiles y skills. Valor 1.
- **`test_skills`/`audit_skills`** (juez LLM nocturno sobre las skills, `builtin_actions.py`, `app.py` L1232): lo cubre otro analista (`auditar-skills`).

---

## 4. Madurez de Odysseus en este tema (resumen)

- Código: v1.0.3, ~138.000 líneas; en el clon solo se ve 1 commit, así que no se puede medir el ritmo.
- Tests: 812 archivos en total; en este tema ~17 (hwfit), 26 (cookbook), 22 (tareas y webhooks), 6 (compare), 16 (mcp). Los de hwfit cubren bien la lógica numérica; las rutas HTTP, Cookbook admin y la interfaz tienen poca cobertura (según sus propias especificaciones).
- Estado declarado: `ROADMAP.md` abre con «SQUASH BUGS», «¿funcionan las integraciones?» y «Cookbook es lo más frágil en otros equipos». Página de issues: 1.149 abiertas (cifra de la web, no verificada de otra forma).
- Conclusión: buenas ideas y buena documentación interna (`specs/*.md`), pero no es una base que importar. Conviene tomar ideas y escribir código propio pequeño.

## 5. Licencia (no es asesoría legal)

Odysseus es AGPL-3.0: copiar código suyo a Hermes y compartirlo arrastra esas obligaciones. Los tres borradores están escritos de cero desde la idea. Lo que podría servir «casi tal cual» por ser hecho o idea genérica y no expresión: la tabla de bits por peso de las cuantizaciones, la fórmula pesos + caché, la lista de códigos HTTP de disponibilidad, la lista de verbos de solo-lectura. Lo que hay que reescribir siempre: detección de hardware, ranking, catálogo, parser del juez, prompts del profesor, la interfaz Compare. HW Fit viene de llmfit (MIT, Alex Jones): citarlo si algún día se comparte. Para uso privado en tu servidor no hay problema práctico.

---

## 6. Tabla final, ordenada por valor/esfuerzo

| # | Idea | Valor (1-5) | Esfuerzo | Riesgo | Madurez en Odysseus | Acción |
|---|---|---|---|---|---|---|
| 1 | Coste real por origen/tarea, «qué pasaría si» y estimación previa (`estimar-coste-hermes`) | 4 | S | Bajo | No aplica (Hermes es mejor) | **Hacer** (borrador probado con tus datos) |
| 2 | Qué modelo local cabe y a qué velocidad, con calibrado (`modelo-local-conviene`) | 4 | S | Bajo | Media (tests sí; ranking crudo; 1.149 issues) | **Hacer** (borrador probado) |
| 3 | Prueba ciega con tus frases (`prueba-ciega-modelos`) | 4 | M | Bajo-medio (nube) | Baja-media (solo UI) | **Hacer**; probar el camino `hermes:` con tu permiso |
| 4 | Ayudante para llamar a Ollama desde cron sin agente (JSON/`<think>`/RAM) | 3 | S | Bajo | Idea suelta del juez | Después de 1-3 |
| 5 | Aviso mensual de modelos nuevos que caben (cron sin IA, API de Hugging Face) | 2 | S-M | Bajo | Media | Opcional |
| 6 | Puerta de primer plano para trabajos locales pesados | 2 | S | Bajo | Alta | Solo si lanzas lotes locales |
| 7 | Auditor de herramientas MCP solo-lectura | 2 (0 hoy) | S | Bajo | Alta | Solo cuando conectes un MCP |
| 8 | Escalado automático alumno→profesor con hook | 2 | L | Medio | Baja (aprendizaje en 2.º plano retirado) | No hacer; ya hay `profesor-escalar` de otro analista |
| 9 | Tareas y webhooks de Odysseus | 1 | M | Medio | Media | No: Hermes ya los supera |
| 10 | Fallback de rutas de modelos | 1 | M | Bajo | Alta | No: `hermes fallback` ya lo cubre |
| 11 | Presets de prompt | 1 | S | Bajo | Alta | No |
| 12 | Cookbook completo | 1 | L | Alto (ejecuta shell, GPU) | Baja | No |
| 13 | Los 4 servidores MCP de Odysseus | 0-1 | M | **Alto** (correo, índice paralelo, dependencias) | Baja | **No conectar** |
| 14 | Tabla de precios de la interfaz de Odysseus | 0 | S | Medio (datos viejos) | Baja | No |

## 7. Borradores y pruebas realizadas

Carpeta: `/home/server/Odysseus/analisis/skills-propuestas/`. Solo biblioteca estándar de Python 3 (el del sistema es 3.14). Ninguna se ha instalado en `~/.hermes`; las pruebas escribieron solo en la carpeta temporal de la sesión.

| Skill | Archivos | Probado |
|---|---|---|
| `modelo-local-conviene` | `SKILL.md`, `scripts/ajuste_hardware.py`, `references/catalogo.json` | `sistema`, `calibrar` (generación real en tu Ollama, ~30 s), `recomendar`, `cabe` y `--simular-ram 32`: correcto. Resultado: 9,6 palabras/s, 24 GB/s efectivos, RAM prevista 3,3 GB frente a 2,9 real (conservador) |
| `prueba-ciega-modelos` | `SKILL.md`, `scripts/prueba_ciega.py`, `references/frases-ejemplo.json` | Llamada real a Ollama (1 frase) y flujo completo `preparar → votar → revelar` con 3 concursantes simulados (servidor Ollama falso): barajado, votos, marcador y negativas correctas. **No probado:** el camino `hermes:` (no se ha gastado dinero ni se ha usado `hermes -z`); solo se comprobó que sin `--permitir-nube` se niega |
| `estimar-coste-hermes` | `SKILL.md`, `scripts/coste.py`, `references/precios.json` | `resumen`, `que-pasaria-si` (con y sin `--origen`) y `tarea` contra tu `state.db` real en solo lectura |

## 8. Pendientes y cosas a verificar

- Etiquetas de Ollama de los modelos nuevos (Qwen3.5, Gemma 4, LFM2, Qwen3.6): el catálogo las deja en `null` a propósito; los tamaños son estimados (marcados `*`).
- Si Ollama recorta a 4k: probar con un prompt largo y `OLLAMA_CONTEXT_LENGTH`; decidir antes de usar cualquier modelo local con prompts grandes. (Variables como `OLLAMA_KV_CACHE_TYPE` y `OLLAMA_FLASH_ATTENTION` existen en versiones recientes; comprobar en la 0.40.)
- Canal de memoria: `sudo dmidecode -t memory | grep -E "Size|Speed|Locator"` (lo ejecutas tú). Si solo hay un módulo, el segundo podría duplicar la velocidad local.
- La GPU integrada (780M) no se usa; no se ha probado Vulkan/ROCm y las issues de Odysseus sobre APU AMD aconsejan no tocarlo ahora.
- Los precios de `precios.json` son una copia de Hermes, no oficiales; `hermes insights` (41,79 USD) y `state.db` (38,65 USD) difieren; conviene saber por qué.
- Quién cambió el modelo de las sesiones de Haiku (predeterminado) a Sonnet 5.5.
