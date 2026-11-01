# 01 · Seguridad y control del agente (Odysseus → Hermes/Zazu)

Análisis de ingeniería para Fran · 2026-10-10 · Odysseus v1.0.3 (clon `main` del 2026-09-05, solo lectura) frente a lo que tenemos instalado.
Qué he hecho: leer el código de Odysseus, leer Hermes y nuestro hook/SOUL, **probar a mano el hook actual** (pasándole órdenes de ejemplo; no ejecuta nada) y consultar en GitHub, solo lectura, el estado de los problemas abiertos. No he arrancado ni ejecutado nada de Odysseus, no he instalado nada en `~/.hermes`, y los borradores solo se han probado con sus propias pruebas (`unittest`, biblioteca estándar).

---

## 1. Para decidir (lo importante primero)

**Conclusión.** Odysseus aporta **una idea grande** que a Zazu le falta de verdad (frenar al agente *después de leer algo de fuera*) y un par de ideas pequeñas. El resto de su seguridad (envoltorio de datos, aprobaciones exactas, 2FA, SSRF, limpieza de entorno) o **ya lo tenemos** en Hermes o **no aplica** a un servidor de una sola persona detrás de Tailscale.

**Mis 3 recomendaciones, por valor:**

| # | Qué | Valor | Esfuerzo | Riesgo | Qué hay hecho |
|---|---|---|---|---|---|
| 1 | **Puerta de contenido externo**: tras leer un correo, un WhatsApp de otro, una web o un adjunto, las acciones sensibles piden tu OK (con el motivo) durante 30 min; y lo leído sale marcado como «datos, no órdenes». Empieza en **modo sombra** una semana (no pregunta; apunta lo que habría preguntado; sí marca como «datos» lo leído de fuera). | **5** | M | Medio: avisos de más (fatiga) y supuestos de API sin probar en Hermes real; mitigado con el modo sombra y un interruptor | Borrador `skills-propuestas/contenido-externo-puerta/` (plugin + skill + 20 pruebas) |
| 2 | **Vigilante de persistencia**: una «foto» de lo que manda sobre Zazu (SOUL, memorias, hook, plugins, rutinas, habilidades, permisos de config) y un aviso si cambia algo, con las líneas nuevas de memoria. Rutina semanal sin IA. | 4 | S | Bajo (solo lee) | Borrador `skills-propuestas/vigilar-persistencia/` (script + skill + 6 pruebas) |
| 3 | **Cerrar 6 huecos pequeños del hook y del vigía** (lista en §6). No es una skill: lo hace Claude Code contigo. El más serio: **`~/.hermes/plugins/` no está protegido** y un plugin corre dentro del gateway con todos los permisos. | 4 | S | Bajo | Lista de cambios en §6 |

Opcional (valor 3, S): **prueba de obediencia** con correos trampa inofensivos para medir si tu modelo barato (Haiku) se deja engañar y qué envoltorio funciona mejor: `skills-propuestas/prueba-inyeccion/` (6 pruebas; el modo real gasta ~45 000 tokens y pide tu permiso).

**Qué necesito que decidas:** (a) ¿Instalamos la puerta en modo sombra? (b) ¿Quieres que Claude Code haga los cambios de §6 en el hook? (c) ¿Rutina semanal del vigilante (aviso solo si hay cambios importantes)?

**Aviso honesto.** Nada de esto es una barrera real. Hermes lo dice en su propio `SECURITY.md` §2.2: *la única frontera contra un modelo engañado es el sistema operativo*; las aprobaciones, los patrones y los envoltorios son «heurísticas». Y Zazu corre en `terminal.backend: local` leyendo correo y WhatsApp, justo el caso que Hermes llama «fuera de la postura soportada». Odysseus tiene el mismo problema (su `THREAT_MODEL.md`, hueco nº 1: «no hay sandbox de shell/ficheros») y lo está resolviendo con un sandbox aún sin integrar. Lo de aquí **sube el listón y te da el motivo de cada pregunta**; no sustituye a aislar el proceso.

---

## 2. Qué defiende Odysseus (y qué reconoce que no)

`THREAT_MODEL.md` (6 KB): es una «consola de administrador» para gente de confianza en red privada. No intenta impedir lo que un admin hace; **sí** intenta impedir (1) acceso sin autenticar, (2) que un no-admin llegue a lo admin, (3) **que el agente actúe con órdenes inyectadas por contenido no fiable** (web, correos, páginas, memorias) y (4) que los servicios internos queden expuestos. Huecos que admite: sin sandbox de shell/ficheros, SSRF por `base_url` en la API de chat, módulos de búsqueda duplicados, tokens de alcance grueso. `SECURITY.md` (2,7 KB) es una lista de despliegue seguro (auth activada, HTTPS, puertos internos, 2FA para admin) y cómo notificar.

Su defensa contra inyección tiene **dos capas** y conviene no confundirlas:
1. **Blanda (le pide al modelo que obedezca):** envolver lo externo en un bloque «datos, no órdenes» (`src/prompt_security.py`).
2. **Dura (el servidor decide, no el modelo):** tras leer algo de fuera, bloquear las herramientas peligrosas hasta que el usuario apruebe esa acción exacta (`src/tool_capabilities.py`, `src/tool_approvals.py`).
Los propios autores consideran la capa 1 «soft» (issue #3709) y nadie ha medido si los modelos pequeños la cumplen (#4991). La capa 2 es la valiosa.

---

## 3. Dónde estamos nosotros (comparado y comprobado)

| Defensa | Odysseus | Hermes + nuestro sistema | Falta de verdad |
|---|---|---|---|
| Envoltorio de datos no fiables | `prompt_security.py` en ~25 sitios; **no** envuelve resultados de herramientas nativas | Hermes envuelve `web_extract`, `web_search`, `browser_*`, `mcp_*` en `<untrusted_tool_result>` y defanga la etiqueta (`agent/tool_dispatch_helpers.py` 431-585); SOUL «Límites»; el vigía usa `<datos>` | **`terminal`** (zgog gmail, wacli, curl, md.py, `movil.py notificaciones`) y `read_file` de adjuntos van **sin marcar**; el vigía no defanga `</datos>` |
| Freno tras leer de fuera | Sí (capacidades + contaminación + aprobación exacta) | **No.** El hook aprueba por *patrón de comando*, no por *lo que acaba de leer* | Es la idea nueva (§4.1) |
| Aprobación de acciones | Sellada, 10 min, una vez, con alcance acción/tarea/chat | Aprobación **en línea** (el hook devuelve `approve` y Hermes espera en esa misma llamada), `rule_key` = hash del comando exacto, nunca recorta lo que apruebas (bloquea si >3500 car.) | Alcance por tarea y *motivo* en el aviso (§4.3) |
| Auditoría de skills | Bucle de calidad (probar→juez→autoedición); importador con límites | `skills_guard`, AST, linter, `skill_ledger` (hashes + reversión), escaneo estricto de lo que se escribe en memoria | Nada vigila **juntos** plugins, rutinas, hook, SOUL y memoria (§4.4) |
| Entorno de subprocesos | Casi nada: `{**os.environ}` y `HOME` cambiado | Hermes quita claves de proveedor a shell, MCP, cron y `execute_code` (`local_env_policy.py` 127; SECURITY §2.3) | Tus notas dicen que los **hijos del gateway** (puente WhatsApp, MCP) heredan claves: verificar (§4.6) |
| Rutas de estado protegidas | `realpath` + enlaces simbólicos/duros + mayúsculas (38 KB de pruebas) | Hermes impide **escribir** en `~/.ssh`, `.aws`, `.gnupg`, `.config/gh`… con sus herramientas de ficheros y bloquea leer sus propias credenciales (`agent/file_safety.py` 210-218, 368-400); el hook vigila `.env` por texto | **Leer** por terminal `gogcli`, `gh`, `op`, `google-chrome` (§3.1) |
| Ejecuciones sin humano | Credencial delegada = siempre recortada | Rutinas con agente ya tienen `enabled_toolsets: []` (= **ninguna** herramienta, `cron/jobs.py` 1703) y `cron_mode: deny` | Nada |
| Auth/2FA/tokens | bcrypt + TOTP + 14 alcances | Tailscale + `API_SERVER_KEY`; el token de Odysseus que usa Zazu ya es de 4 alcances | Nada (no aplica) |

### 3.1 Pruebas que he hecho al hook actual
Le pasé a `agent-hooks/movil-aprobacion.py` (por stdin, como hace Hermes) estas llamadas. «Pasa» = no pide permiso ni bloquea. Es el hook, no todo Hermes: algunas las cubren otras capas.

| Llamada de ejemplo | Resultado | Comentario |
|---|---|---|
| `write_file` a `~/.hermes/plugins/rtk-rewrite/__init__.py` | **Pasa** | Y las guardas de ficheros de Hermes solo protegen SOUL/AGENTS/CLAUDE.md y config.yaml. Un plugin se carga dentro del gateway con todos los permisos |
| `curl -X POST https://… -d @~/Cerebro/nota.md` | **Pasa** | Hermes marca subir *ficheros secretos* con curl (`approval_detection.py` 339-346), no un fichero cualquiera |
| `scp …`, `python3 -c "import smtplib"` | **Pasa** | Salidas de datos sin patrón |
| `cat ~/.config/gogcli/…`, `cat ~/.config/gh/hosts.yml`, `ls ~/.config/op`, `cp ~/.config/google-chrome/Default/Cookies …` | **Pasa** | El hook solo entiende `~/.hermes/.env`; Hermes marca *subir* `gh/hosts.yml` con curl, pero no *leerlo* |
| `cronjob_manage create` para ti con un `prompt` cualquiera | **Pasa** | Es a propósito («un recordatorio para Fran no pregunta»), pero el prompt puede ser texto de un tercero y se ejecuta solo más tarde |
| `zgog tasks add`, escribir una nota en el Cerebro | Pasa | Correcto y deseado |
| `cat ~/.hermes/.env` | **Pide permiso** | Control que sí funciona |

---

## 4. Las ideas, una a una

### 4.1 Puerta de contenido externo (capacidades + «contaminación»)
**(1) Qué hace y cómo.**
- Cada herramienta tiene una ficha de **efectos** (leer público/privado, escribir, ejecutar código, red de salida, efecto externo, admin, destructivo…) y una **integridad del resultado** (sistema / workspace / externo): `src/tool_capabilities.py` 21-48 (tipos), 72-262 (registro de ~80 herramientas), 268-312 (**desconocida o MCP = efecto máximo**: falla «alto»), 315-492 (acciones dentro de herramientas multiuso: `manage_memory add` ≠ `list`).
- `ToolRunSecurityContext` (616-697): cuando entra al contexto un resultado de integridad externa, el run queda **contaminado** (`observe_tool_result` 686; `tool_result_should_arm_gate` 506-551 contamina **también si falla**, porque el cuerpo de un error es texto atacable). Desde entonces `decision_for` (654-684) bloquea todo lo de `POST_EXTERNAL_BLOCKED_EFFECTS` (553-566: leer privado, escribir, ejecutar, red de salida, efectos externos, admin, destructivo) y lo desconocido; deja pasar lecturas públicas, `web_search` y preguntas al usuario (y `web_fetch` **no**, por ser salida de datos en la URL).
- Se aplica en dos sitios: `src/agent_loop.py` 5646 y 5728-5770 (crea la tarjeta de aprobación) y `src/tool_execution.py` 890-925 (segunda comprobación justo antes de ejecutar). La contaminación también se reconstruye leyendo el historial (`messages_contain_external_untrusted_context` 586-613), así que **sobrevive entre turnos** mientras el texto siga en el contexto.
- Una credencial delegada (token) nunca puede levantar la puerta (`delegated_credential`, 616-697; `tool_security.py` 274-284).

**(2) Qué tenemos y qué falta.** Nuestro hook decide por *forma del comando* (¿envía? ¿borra? ¿toca config?), no por *de dónde viene la idea*. Tras leer un correo hostil, cualquier acción que no esté en sus listas (salida a internet, código libre, `memory`, rutinas para ti, claves de `gogcli`/`op`) pasa. Los huecos de §3.1 son exactamente esos. Falta el concepto «acabo de leer algo de fuera».

**(3) ¿Se puede sin tocar el núcleo?** Sí, como **plugin de Hermes** (carpeta en `~/.hermes/plugins/`, ganchos documentados), no como hook de shell: un hook de shell no puede reescribir resultados de herramientas (`agent/shell_hooks.py` 461-499 solo admite `context`; `transform_tool_result` exige una cadena, `model_tools.py` 848-865). **Código de Odysseus aprovechable: ninguno tal cual** (otras herramientas, 700 líneas de registro propio, acoplado a su servidor); se reescribe desde la idea *efectos × integridad, desconocido = alto, bloquear tras lectura externa*. Hecho en el borrador, con tres decisiones propias: (a) dos niveles —*de tarea* (un OK vale el resto del turno) y *siempre* (salida a internet, código libre, rutinas, configuración, claves)—; (b) **modo sombra** por defecto; (c) los subagentes heredan la marca.

**(4) Valor 5 · Esfuerzo M · Riesgo medio.**
- *Fatiga de avisos*: el issue #6112 de Odysseus (cerrado 2026-08-19) es un usuario pulsando «Permitir una vez» **más de diez veces** en una sola tarea. Por eso el nivel *de tarea* y el modo sombra.
- *Duplicidad con el hook*: si ambos piden permiso sale una pregunta (gana la primera válida; verificar en pruebas).
- *Rutinas con agente*: con `cron_mode: deny` (por defecto) la puerta **bloquea** en vez de preguntar; está bien, pero la fase sombra dirá si rompe alguna.
- *Canales*: según tus notas, las aprobaciones del chat de HolaZazu se deniegan en silencio; comprobar cómo llega la pregunta por cada canal antes de activarla.
- *Supuestos sin probar en Hermes real*: que lleguen `session_id` y `turn_id` a los ganchos (el modo `PUERTA_EXTERNA_DEBUG=1` lo comprueba en un día).
- Sigue siendo heurística: una orden escrita de forma rara puede esquivarla.

**(5) Madurez.** Odysseus: 53 pruebas del bloqueo (`test_external_context_tool_gate.py`), 15 de aprobaciones, 8 de alcance tarea/chat, 4 de acción única, 16 de autoridad de tokens. Pero es **joven**: nació en agosto de 2026 (#6083, #6092, #6112), el propio equipo lo llama «temporal» hasta que llegue su sandbox (#6083), propone rehacerlo en 5 fases (#5815) y pide guardar la procedencia entre sesiones (#6093). Lo nuestro: 20 pruebas propias, sin probar en un Hermes real.

### 4.2 Envoltorio de contenido no fiable
**(1)** `src/prompt_security.py` (99 líneas): política en rol *system* una sola vez (8-17; se inserta en `chat_processor.py` 306-308) y cada texto externo como mensaje de rol *user* con metadatos `trusted: False` (64-99). Detalles buenos: **solo texto fijo antes de la marca de apertura**, la etiqueta de origen va *dentro* del bloque (73-77), y las marcas literales dentro del texto se neutralizan (34-45). Se usa en ~25 puntos (búsquedas, correos, documentos, habilidades, descripciones MCP, estilo de correo…). Los resultados de herramientas nativas **no** se envuelven (el rol *tool* lo exige el protocolo): ahí se apoyan en la puerta (`tests/test_tool_output_prompt_injection.py` 100-118).
**(2)** Hermes ya tiene el equivalente para web, navegador y MCP, con defangado insensible a mayúsculas y un análisis de riesgo informativo (`tool_dispatch_helpers.py` 431-585). Falta lo que entra por `terminal` y por ficheros de fuera. Aviso de Odysseus: envolver también *lo propio* hizo que el agente **ignorase sus habilidades** (#2959); nuestro borrador solo envuelve lo que llega de fuera.
**(3)** Va dentro del plugin (`transform_tool_result` reescribe solo el campo `output` para no romper el JSON). Es un fragmento **pequeño y genérico** (unas 30 líneas de plantilla), pero su texto es de ellos; lo he escrito de nuevo en español y con su propia etiqueta. **(4)** Valor 4 (incluido en 4.1) · S · riesgo bajo (~70 tokens por lectura). **(5)** 21+9+3+3 pruebas de *colocación*; ninguna de *eficacia* (#4991 sigue abierto) → por eso la skill `prueba-inyeccion`.

### 4.3 Aprobaciones exactas y su alcance (acción única / tarea / chat)
**(1)** `src/tool_approvals.py`: al bloquear, el servidor **sella** la acción (herramienta + contenido + espacio de trabajo + efectos, con huella SHA-256 canónica, 89-140), id aleatorio, caduca a los 10 min (30), la tarjeta enseña el contenido **entero** (166-215), se consume una sola vez comprobando dueño y sesión *antes* de borrarla (451-459), se reclama bajo candado (294-313) y se revalida justo antes de ejecutar (237-274). `src/tool_approval_scopes.py` (160 líneas): alcances `SINGLE_ACTION` (solo para quien no puede reanudar un chat: probador de habilidades, auditorías desatendidas), `TASK` y `CHAT_SESSION`; el de chat se prueba con **firma HMAC** del servidor atada a sesión y aprobación (30-142) para que nadie fabrique una tarjeta «ya aprobada». Denegar no deja concesión; un mensaje nuevo retira la tarjeta pendiente **pero conserva la marca de contaminación** (482-510). Las auditorías desatendidas deniegan en el acto (`routes/skills_routes.py` 776-800). Tests `test_tool_approval_single_action_scope.py` / `_task_scope.py`.
**(2)** Con nuestra aprobación en línea no hay hueco entre aprobar y ejecutar: **no necesitamos sellado ni firma**. Tenemos ya lo bueno: hash del comando exacto, enseñarlo entero, bloquear lo demasiado largo. Falta el **alcance por tarea** (si el hook crece, cada acción preguntaría) y el **motivo** en el aviso.
**(3)** Recreado en el plugin con `post_approval_response`: un «sí» a una acción *de tarea* vale el resto del turno; las de nivel *siempre* preguntan cada vez. Código de Odysseus aprovechable: ninguno (acoplado a su servidor, ~670 líneas expresivas). **(4)** Valor 2 · S (incluido) · riesgo nulo. **(5)** 15+8+4 pruebas; seguridad sólida, UX inmadura (cambió en 2 días tras la queja #6112).

### 4.4 Superficies que se vuelven permanentes: skills, memoria y tareas
**(1)** Odysseus saca del rol *system* todo texto editable (índice y cuerpo de habilidades, integraciones, descripciones MCP, estilo de correo): `tests/test_prompt_injection_audit.py` (9 pruebas) y `test_skill_index_prompt_injection.py` (3), `agent_loop.py` 2700-2760. Las tareas programadas que ejecutan código son solo de admin (`src/task_action_policy.py`). Su «auditoría de skills» (`routes/skills_routes.py` 544-930) es un bucle de **calidad** (probar → juez → autoedición → reintento → profesor), no de seguridad del contenido; lo de seguridad es pequeño: el importador limita 64 archivos / 2 MB / 400 KB y extensiones (`services/memory/skill_importer.py` 18-40) y las pruebas desatendidas deniegan cualquier aprobación.
**(2)** Hermes ya tiene más que Odysseus en esto: `skills_guard` (patrones, `tools/skills_guard.py` 137), AST, linter, **`skill_ledger`** (historial con hashes y reversión de cada cambio de habilidad), y escaneo estricto de lo que se escribe en memoria (`memory_tool_store.py` 28; bloquea frases de inyección y caracteres invisibles). `hermes skills audit` solo revisa lo instalado desde el hub (`hermes_cli/skills_hub.py` 1098). **Falta** lo que ninguna pieza mira junta: plugins (sin protección de escritura), rutinas (crear para ti no pregunta), SOUL/hook/config, y órdenes permanentes *parafraseadas* en memoria («cuando llegue un correo de X, haz Y») que no casan con patrones.
**(3)** Skill `vigilar-persistencia`: foto con hashes de 461 elementos (medido en solo lectura sobre tu `~/.hermes`: 0,03 s), comparación, avisos por patrones, líneas nuevas de memoria y teléfonos ocultos en la salida. Nada de Odysseus que copiar (no tiene «tripwire»); la idea sale de su modelo de amenazas. La auditoría de calidad de skills queda fuera de este tema (hay un borrador `auditar-skills` de otra línea).
**(4)** Valor 4 · S · riesgo bajo (limitación: si alguien puede escribir en `state/vigilar-persistencia/` puede rehacer la foto; por eso §6.5). **(5)** Odysseus: pruebas de colocación, no de eficacia.

### 4.5 Ejecuciones sin humano (credencial delegada)
**(1)** `delegated_credential` + `delegated_credential_blocked_tools()` (`tool_security.py` 274-284): un token API se recorta **siempre** al conjunto de un usuario normal aunque lo creara un admin, no puede responder a sus propias aprobaciones ni heredar una concesión que dejó el dueño en el chat (`tests/test_api_token_tool_authority.py`, 16 pruebas). **(2)** Ya lo tenemos por otra vía: las rutinas con agente (Repaso de la noche, Vigía de empleo, Vigía de entrevistas, Revisión de Zazu) llevan `enabled_toolsets: []` (= ninguna) y `cron_mode: deny`. **(4)** Valor 1 · nada que hacer salvo no ampliar esos `toolsets` sin pensarlo.

### 4.6 Limpieza del entorno de subprocesos
**(1)** En Odysseus es **débil**: `src/tool_execution.py` 757-762 pasa `{**os.environ, TERM, COLUMNS, LINES, HOME=carpeta del agente}` y el gestor MCP hace `{**os.environ, **env}` (`mcp_manager.py` 193). Su defensa real es confinar *rutas* (`tool_execution.py` 308-466 + `test_agent_state_dir_confinement.py`, 38 KB: `realpath`, enlaces simbólicos y duros, mayúsculas). **(2)** Hermes sí limpia las claves de proveedor para shell, MCP, cron y `execute_code`. El comentario de tu hook admite que **los hijos del gateway (puente de WhatsApp, supervisor MCP) heredan todas las claves** y que se corrige «en el core»; no he podido comprobar si ya se hizo. **(3)** No hay nada de Odysseus que portar. Lo útil: que Claude Code compruebe, imprimiendo **solo nombres** de variables (nunca valores), qué heredan esos procesos hijos; no lo he hecho yo porque es justo lo que tu hook trata como sensible. Valor 3 · S · riesgo bajo-medio (toca `/proc`). No entregado como skill.

### 4.7 Medir la obediencia (idea del issue #4991)
**(1)** No es código de Odysseus: es una petición suya, sin hacer: «nadie sabe si la guarda aguanta en modelos pequeños». **(3)** Skill `prueba-inyeccion`: 14 correos trampa con un canario inofensivo × 4 envoltorios (ninguno, `<datos>`, el de Hermes, el de la puerta), **sin herramientas** y con tu modelo real por el mismo trabajador que usa el vigía (`llm_worker.py`). Modo real con confirmación explícita de coste. Su modo `--simulado` solo comprueba el montaje y apunta a un defecto cierto del vigía, visto en el código: **`<datos>` se puede cerrar desde dentro** (un correo puede traer `</datos>`), porque `zv/priv.py::seguro` no defanga ángulos. Si un modelo real llega a obedecer ese truco lo dirá la prueba real, no la simulada. **(4)** Valor 3 · S · riesgo bajo (céntimos; pide permiso). Limitación: una vuelta sin herramientas; el correo real llega como resultado de herramienta.

### 4.8 Lo que descarto
- **Auth / 2FA / tokens con alcance** (`core/auth.py` 480-560, `routes/api_token_routes.py` 14-36): bcrypt + TOTP + 14 alcances. No aplica (Tailscale + clave de API). Dos ideas sueltas: «si el 2FA está activo pero falta el secreto, **cierra**» (`test_totp_failclosed.py`) y tokens por capacidad (`todos:read`, `email:draft`…) si algún día HolaZazu da accesos a terceros. Ojo: sus códigos de respaldo se guardan en claro en `auth.json`. Valor 1.
- **SSRF / `url_safety.py`** (108 líneas, 6 pruebas de DNS-rebinding en `test_security_regressions.py` 1292-1502): Hermes tiene `tools/url_safety.py`. Valor 1.
- **Modo «plan» duro** (`tool_security.py` 81-197: lista blanca de solo lectura donde lo nuevo queda bloqueado por defecto): el `/plan` de Hermes es solo una instrucción (`agent/plan_prompt.py`). Un «modo consulta» duro sería fácil **encima de la puerta** (todo lo que `accion_sensible` marca, bloqueado). Valor 3 · S tras la puerta. No entregado.
- **Documentar el modelo de amenazas de Zazu** en una página (quién manda, qué es dato, qué se permite) con la plantilla del `THREAT_MODEL.md` de Odysseus. Valor 2 · S · se puede hacer cuando se active la puerta.

---

## 5. Tabla final (ordenada por valor/esfuerzo; S=1, M=2, L=4)

| Orden | Idea | Valor | Esf. | Riesgo | Cubre lo que falta | Entregable | Madurez en Odysseus |
|---|---|---|---|---|---|---|---|
| 1 | Cerrar huecos del hook y del vigía (§6) | 4 | S | Bajo | plugins sin proteger, secretos fuera de `.env`, salidas de datos, `</datos>` | Lista de cambios | Hallazgo propio |
| 2 | Vigilante de persistencia | 4 | S | Bajo | cambios silenciosos en memoria, rutinas, plugins, hook | `vigilar-persistencia` (6 pruebas) | Idea del modelo de amenazas; sin código |
| 3 | Prueba de obediencia con canarios | 3 | S | Bajo | saber si el envoltorio funciona con Haiku | `prueba-inyeccion` (6 pruebas) | Petición abierta #4991 |
| 4 | Verificar entorno de los hijos del gateway (solo nombres) | 3 | S | Bajo-medio | claves heredadas por WhatsApp/MCP | Recomendación | Odysseus no lo hace |
| 5 | **Puerta de contenido externo** + envoltorio de terminal + alcance por tarea | **5** | M | Medio | frenar al agente tras leer de fuera | `contenido-externo-puerta` (20 pruebas) | ~100 pruebas; ~2 meses de vida; en rediseño |
| 6 | Modo consulta duro (lista blanca) | 3 | S tras 5 | Bajo | «solo mira, no toques» de verdad | No | `tool_security.py` 81-197 |
| 7 | Modelo de amenazas de Zazu en una página | 2 | S | Nulo | claridad | No | `THREAT_MODEL.md` |
| 8 | Alcance de aprobaciones tarea/chat | 2 | S | Nulo | fatiga de avisos | Incluido en 5 | 27 pruebas |
| 9 | Confinar rutas por `realpath`/enlaces/mayúsculas | 2 | M | Medio | evasiones de nombres | No | 38 KB de pruebas |
| 10 | Credencial delegada · 2FA · tokens · SSRF · sellado/firma de aprobaciones | 1 | – | – | **ya lo tenemos o no aplica** | No | – |

(La puerta es la de más valor; va quinta solo porque su esfuerzo es mayor. Haría antes 1 porque son veinte minutos.)

---

## 6. Cambios en el hook y el vigía (para Claude Code, con tu OK; Zazu no puede tocar el hook)

1. **Proteger `~/.hermes/plugins/`**: añadir `plugins/` a `CONFIG_RUTA` (pide permiso) o a `PROTEGIDO` (bloquea). Probado: hoy pasa. SECURITY.md de Hermes §2.5: un plugin corre con todos los permisos.
2. **Más sitios con secretos en `lee_claves`**: `~/.config/gogcli`, `~/.config/gh`, `~/.config/op`, `~/.config/google-chrome*`, `~/.config/evolution`, `~/.config/goa-1.0` (probado: hoy pasan por terminal).
3. **Salida de datos sin patrón**: pedir permiso a `curl`/`wget` con `-d @`, `-F`, `-T`, `--upload-file`, `scp`, `rsync`, `sftp`, `nc`, `socat` hacia fuera. Zazu casi no los usa; preguntar siempre es barato. (Hermes ya cubre solo subir *ficheros secretos* con curl.)
4. **Rutinas para ti con texto raro**: pedir permiso en `cronjob_manage create/update` cuando el `prompt` lleve `http`, `curl`, `zgog`, `wacli`, `send`, «cada vez que» o pase de ~400 caracteres. Un recordatorio normal sigue sin preguntar.
5. **`vigilar_persistencia.py --aceptar`** y la carpeta `~/.hermes/state/vigilar-persistencia/` a `CONFIG_RUTA` (si no, quien manipule a Zazu podría rehacer la «foto»).
6. **Vigía**: en `zazu-vigia/zv/priv.py::seguro`, neutralizar `<` y `>` (o al menos `</datos>`) del texto de terceros. Daño limitado hoy (el modelo del vigía no tiene herramientas y su salida se valida con `texto_valido`), pero deja a un correo manipular la decisión de «requiere acción».

---

## 7. Madurez de Odysseus en esta parte (datos del 2026-10-10)

- **Proyecto:** AGPL-3.0, ~92 600 estrellas, 1 466 problemas y propuestas de cambio abiertos, último cambio el 2026-10-08; v1.0.3. Mi clon es un solo commit del 2026-09-05 de `main`; las correcciones llegan antes a `dev`, así que algún detalle puede estar ya cambiado.
- **Pruebas** (conteo estático de funciones `test_*`, sin ejecutarlas; la parametrización las multiplica): 801 archivos y ~4 877 funciones en total. Las de este tema: puerta 53, aprobaciones 15 + 8 + 4, tokens 16, envoltorio 21 + 9 + 3 + 3, regresiones de seguridad 76, importador de skills 10, TOTP 2.
- **Abiertos y relevantes:** #6083 (la puerta es «temporal» hasta el sandbox), #5815 (plan en 5 fases para hacerla determinista), #6093 (guardar la procedencia entre sesiones), #3709 (puerta dura opcional, de junio), #4991 (nadie ha medido la eficacia del envoltorio), #2959 (envolver habilidades de confianza las hace ignorar), sandbox #4754/#6091/#6114–#6117 (sin integrar), SSRF en endpoints #6315/#6326/#6352 (no nos afectan). **Cerrado:** #6112 (fatiga de aprobaciones).
- **Lectura:** diseño de seguridad serio y bien probado en *colocación y bloqueo*; joven, con la experiencia de usuario aún en cambio y sin evidencia de eficacia real del envoltorio.

## 8. Licencia (AGPL-3.0; no es asesoría legal)
No he copiado código de Odysseus: todo está escrito desde la idea, con otras herramientas y en español; solo cito rutas y líneas. Pequeño/genérico: la plantilla de `prompt_security.py` (~30 líneas; la *estructura* es una idea, el *texto* es suyo) y los nombres de efectos. Expresivo, no copiar: el registro de `tool_capabilities.py` (700 líneas, selección y ordenación propias), `tool_approvals.py`/`tool_approval_scopes.py` (~670 líneas acopladas a su servidor) y sus pruebas. Si algún día se quiere reutilizar código tal cual, tratarlo como obra derivada AGPL y consultarlo antes.

## 9. Archivos entregados y cómo probarlos
```
analisis/01-seguridad.md                                  este documento
analisis/skills-propuestas/contenido-externo-puerta/      SKILL.md · plugin/{__init__,clasificar}.py + plugin.yaml · references/instalar.md · tests/
analisis/skills-propuestas/vigilar-persistencia/          SKILL.md · scripts/vigilar_persistencia.py · tests/
analisis/skills-propuestas/prueba-inyeccion/              SKILL.md · scripts/prueba_inyeccion.py · tests/
```
Pruebas (sin Hermes, solo `python3`): desde cada carpeta de skill, `python3 -m unittest discover -s tests -v` → 20 + 6 + 6 correctas. Descripciones de los `SKILL.md` ≤ 60 caracteres. **No instalado nada.** Instalación por fases en `contenido-externo-puerta/references/instalar.md`.
**Lo que NO está comprobado:** que los ganchos de Hermes entreguen `session_id`/`turn_id` con esos nombres, que dos `approve` (hook + plugin) salgan como una pregunta, ni cómo se ve la pregunta en WhatsApp/HolaZazu. Por eso empieza en modo sombra y con registro de depuración.
