# Zazu

**Zazu is a self-hosted personal AI assistant.** It runs on its owner's own home server instead of a third-party cloud. It reads calendar, tasks, email and messages, alerts only about what matters (a deadline, an unusual charge, an appointment) and can take actions, but **never anything sensitive without explicit human approval**. It is used daily through a web app ([holazazu.app](https://holazazu.app)) and an Android app, by its author and a small group of family and friends, each in an isolated sandbox.

Design principles:
- **Data stays at home.** What is sent to a model is limited, filtered and logged in a file the user can read.
- **External content is data, never instructions.** An email, a web page or a message cannot tell Zazu what to do (prompt-injection defence).
- **Sensitive actions need approval.** Sending messages, deleting things or anything involving money always asks first.
- **Learning with a human in the loop.** The assistant proposes "lessons" from the user's corrections; they only apply if the user approves them.

What is in this repository (documentation is in Spanish for now; English docs are on the roadmap):

| Folder | What it is |
|---|---|
| `pagina-web/` | The HolaZazu app: Python (stdlib) server + React/Vite front end |
| `zazu/` | The assistant's tools: the *vigía* (watcher for email/messages), inbox, scripts, evals |
| `aprendizaje/` | The approval-gated learning loop |
| `voz/` | Local speech-to-text service (faster-whisper) |
| `empleo-buscador/` | Job search over public APIs with profile-based scoring |
| `app-android/` | Android app (WebView wrapper) |
| `servidor/` | systemd units and server tooling |
| `hermes/`, `experimentos/`, `docs/` | Agent profiles, experiments and notes |

This is a snapshot of a personal project built by one person with Claude Code. Personal data (phone numbers, email addresses, names) has been replaced with fictitious values, so a few tests that depend on the original values may fail. Secrets, databases and user data are not included. Licensed under the [MIT License](LICENSE).

---

# Spirit

Todo el código del servidor de Fran en un solo sitio, separado por piezas que se pueden ver, entender y cambiar.

> Spirit contiene **código**. Los **datos** (claves, memorias, conversaciones, base de datos del vigía, tu Cerebro de Obsidian) se quedan donde estaban. Así puedes tocar el código sin miedo a perder tus cosas ni a subir una clave por error.

## Mapa: qué hay en cada carpeta

| Carpeta | Qué es | Lo que más vas a tocar |
|---|---|---|
| [`pagina-web/`](pagina-web/README.md) | La app **HolaZazu** (`holazazu.app`): servidor Python + pantallas React. Tiene su propio git. | `web/src/` (lo que ves), `server.py` y los `.py` de al lado (lo que hace) |
| [`hermes/`](hermes/README.md) | **Hermes**, el motor del asistente: puerta de seguridad (hooks), plugin propio, ajustes y parches. | `agent-hooks/movil-aprobacion.py`, `ajustes/SOUL.md` |
| [`zazu/`](zazu/README.md) | **Zazu**, la persona y sus oficios: vigía del correo, bandeja, rutinas, habilidades. | `scripts/`, `vigia/`, `bandeja/`, `skills-de-zazu/` |
| [`servidor/`](servidor/README.md) | Cómo se enciende todo: servicios del sistema (`unidades/`), túnel, panel del servidor, copias de seguridad, comando `spirit`. | `bin/spirit`, `unidades/` |
| [`empleo-buscador/`](empleo-buscador/README.md) | **Tu buscador de ofertas** (Europa, junior de datos/desarrollo y marketing digital remoto): 6 portales con API, puntuación según tu perfil, base local, resumen diario. Lo usa Zazu Empleo. | `perfil.yaml`, `puntuar.py`, `fuentes/` |
| [`voz/`](voz/README.md) | Voz: de audio a texto (`stt.py`) y de texto a voz (`tts.sh`). | `stt.py`, `tts.sh` |
| [`experimentos/`](experimentos/README.md) | Pruebas aisladas (Odysseus). Nada de aquí está en producción. | lo que quieras |
| [`docs/`](docs/README.md) | Apuntes y planes. | `plan-agentes.md` |
| [`APRENDIZAJE.md`](APRENDIZAJE.md) | Cómo se hizo **Mi nube** (23 y 24 de octubre de 2026): qué se construyó, cómo se trabajó con 12 agentes, qué salió mal y qué se aprendió. | léelo entero |
| [`COMO-PIENSA-UN-PROGRAMADOR.md`](COMO-PIENSA-UN-PROGRAMADOR.md) | Cómo se razona para programar y para pensar la **ciberseguridad**, con los casos reales de Mi nube y un «Hazlo tú mismo» en cada apartado. | léelo después del anterior |

Algunas carpetas contienen **enlaces** (flechitas) hacia lugares fuera de Spirit, por ejemplo `hermes/ajustes/config.yaml` apunta a `~/.hermes/config.yaml`. Editas el enlace y cambias el original; no hay copias duplicadas.

## Lo más importante: la orden `spirit`

Desde cualquier terminal:

```bash
spirit estado        # ¿está todo encendido?
spirit encender      # arranca gateway, web, túnel y vigilantes
spirit reiniciar gateway
spirit reiniciar web
spirit logs gateway  # qué está diciendo el gateway
spirit probar        # comprobaciones de salud
spirit cambios       # qué has tocado y no has guardado
spirit guardar "lo que hice"
spirit foto          # copia comprimida de Spirit
```

Si `spirit` no existe: `~/.local/bin/spirit` es un enlace a `~/Spirit/servidor/bin/spirit`.

## Cómo está montado (en 30 segundos)

```
tu móvil / navegador ──► holazazu.app ──► túnel Cloudflare ──► web (hermes-hub, puerto 8792)
                                                                   │
                                                                   ▼
                                                      gateway Hermes (puerto 8642)
                                                      ├─ el modelo de IA piensa y usa herramientas
                                                      ├─ la puerta de seguridad (hook) pide tu OK en el móvil
                                                      └─ memorias + habilidades = lo que Zazu sabe de ti
vigilantes (temporizadores): zv lee el correo, zb ordena la bandeja, archivador, rutinas de WhatsApp
```

Hay tres servicios que importan y varios temporizadores:

| Servicio | Para qué | Puerto |
|---|---|---|
| `hermes-gateway` | El cerebro: modelos, herramientas, WhatsApp, rutinas | 8642 (solo local) |
| `hermes-hub` | La página HolaZazu | 8792 (solo local) |
| `cloudflared-zazu` | Saca la página a internet como `holazazu.app` | — |

Además: `hermes-dashboard` (panel de Hermes, 9119), `syncthing` (sincroniza con el móvil), y los temporizadores `zazu-vigia`, `zazu-bandeja`, `archivador`, `zazu-estado`, `zazu-exportar`, `zazu-propuestas`, `zazu-vigilante`.

## Encender el servidor y reiniciar el gateway

El servidor **arranca solo** al encender el equipo (el sistema tiene `linger` activado, así que los servicios de usuario suben sin iniciar sesión). Para comprobarlo:

```bash
spirit estado
```

Si algo está parado:

```bash
spirit encender
```

Reiniciar solo el gateway (por ejemplo después de cambiar `config.yaml`, `SOUL.md` o un hook). **Ojo:** corta lo que Zazu esté haciendo en ese momento y cancela cualquier permiso que esté esperando tu OK en el móvil; hazlo cuando no estés hablando con ella:

```bash
spirit reiniciar gateway
spirit logs gateway 40
```

Reiniciar solo la web (por ejemplo después de cambiar un `.py` de `pagina-web`):

```bash
spirit reiniciar web
```

Si cambias algo de `pagina-web/web/src/` (las pantallas) hay que compilar y publicar:

```bash
spirit web-construir
```

Las mismas órdenes «a pelo», por si `spirit` fallara:

```bash
systemctl --user restart hermes-gateway
systemctl --user restart hermes-hub
systemctl --user restart cloudflared-zazu
journalctl --user -u hermes-gateway -n 60 --no-pager
```

## Reglas de oro para trabajar tú aquí

1. **Antes de tocar algo importante**, haz `spirit foto`. Es una copia en `~/Respaldos/`.
2. **Un cambio cada vez**, y prueba con `spirit probar` y `spirit estado`.
3. **Guarda con `spirit guardar "mensaje"`** cuando funcione. Si se rompe, `git diff` te enseña qué cambió y `git checkout -- archivo` lo deshace.
4. **Si cambias `hermes/agent-hooks/movil-aprobacion.py`** hay que renovar su consentimiento y reiniciar el gateway; mira `hermes/README.md`. Si no, Hermes lo ignora (es una medida de seguridad).
5. **Las claves nunca van en Spirit.** Viven en `~/.hermes/.env` y no se enseñan ni se copian.
6. **Mientras Zazu o Claude estén tocando `pagina-web`**, avísales: los dos editan los mismos archivos. `spirit cambios` te dice si hay cosas a medias.
7. **Tienes los vigilantes de cambios**: si modificas scripts, habilidades, hooks o memorias, el vigilante de persistencia te lo mostrará («cambiado»). Es normal; se acepta con `vigilar_persistencia.py --aceptar` cuando tú das el visto bueno.

## Cómo está organizado para poder volver atrás

- Antes de la mudanza se hizo copia completa en `~/Respaldos/spirit-antes-*/`.
- Los sitios antiguos siguen funcionando porque son **enlaces** a Spirit: `~/hermes-hub`, `~/.hermes/scripts`, `~/.hermes/agent-hooks`, `~/.hermes/plugins/fran-hub`, `~/voz`, `~/Odysseus`, `~/Documentos/panel-servidor`, las órdenes de `~/.local/bin` y los servicios de `~/.config/systemd/user`. Por eso nada ha necesitado cambios.
- Lista completa de qué vive dónde: [`docs/INVENTARIO.md`](docs/INVENTARIO.md).
- Si alguna vez quieres deshacerlo: borra el enlace y mueve la carpeta de vuelta (ejemplo: `rm ~/hermes-hub && mv ~/Spirit/pagina-web ~/hermes-hub`), o restaura el tar de `~/Respaldos`.

## Dónde está lo que NO está aquí

| Cosa | Dónde | Por qué fuera |
|---|---|---|
| Claves y tokens | `~/.hermes/.env` | Secreto. Nunca en git |
| Memorias de Zazu | `~/.hermes/memories/` (enlace en `hermes/ajustes/`) | Datos tuyos |
| Perfiles de invitados | `~/.hermes/profiles/` | Datos y permisos |
| Conversaciones y base de datos | `~/.hermes/sessions/`, `state/` | Datos |
| Motor de Hermes | `~/.hermes/hermes-agent` (enlace `hermes/motor`) | Es un programa de terceros que se actualiza solo; no lo edites |
| Tu Cerebro de Obsidian | `~/Cerebro` (enlace `docs/cerebro`) | Es tu archivo personal |
| Copias de seguridad | `~/Respaldos/` | Copias |

---

## Qué podemos aprovechar de otros asistentes (informe 2026-10-22, verificado)

> Para quién es: Fran (sin jerga) y quien toque el código (con rutas y piezas concretas).
> Cómo se hizo: fichas de 23 productos con sus fuentes (abajo) y el inventario de lo que Zazu ya tiene. El 22-10-2026 se revisaron las fuentes principales y el código de Spirit. Lo que no está confirmado en una fuente lleva **«sin confirmar»**.
> Regla de la casa: Zazu se hace **solo para Fran**. Por eso no entran aquí ideas de equipos, invitados ni multiusuario.

### 1. Resumen en 5 puntos

- **La memoria que gusta es la que se puede ver y corregir.** Lindy guarda su memoria en archivos con historial de versiones. Claude la ordena por temas que se editan uno a uno. Bee lleva una lista de «datos sobre ti»; que se confirmen o rechacen deslizando está sin confirmar. Zazu ya guarda su memoria en archivos (`MEMORY.md`, `USER.md`) y ya propone hechos («Recuerda: …»), pero **Fran no tiene una pantalla para verlos y aprobarlos**. Eso es lo primero que conviene hacer.
- **La privacidad se vende con promesas que se pueden comprobar.** Apple deja ver y exportar un registro (`Apple_Intelligence_Report.json`) de cada petición que sale hacia su nube privada. Ese registro solo lleva el tamaño, la función usada y la duración, no el contenido. Samsung tiene un interruptor de «solo en el dispositivo». Proton cifra el historial para que solo lo lea el titular. Zazu ya va más lejos que casi todos porque vive en un servidor propio (Spirit), pero **no enseña qué sale hacia Anthropic** ni cuánto tiempo guarda cada cosa. Además, **el disco de Spirit no está cifrado**.
- **En el móvil ganan los avisos y el «compartir».** ChatGPT y AnythingLLM avisan en la pantalla de bloqueo cuando termina una tarea. Open WebUI y AnythingLLM reciben texto, enlaces y archivos desde cualquier app. A la app de Zazu le faltan justo dos cosas: **avisos que lleguen al momento desde el servidor** (hoy recoge cada 15 minutos) y **compartir archivos** (hoy solo recibe texto).
- **Para la casa, el ejemplo es Home Assistant.** Primero resuelve en local lo sencillo y solo llama a la IA si hace falta. Usa voz local (Whisper y Piper) y deja que la app de Android sea el asistente del teléfono. Zazu ya tiene Whisper y Kokoro, y el complemento de Home Assistant está instalado pero apagado.
- **Lo que no hay que copiar:**
  - Grabar todo el día (Limitless, Bee, Friend).
  - Depender de una nube que puede cerrar. Dot cerró el 5-10-2025. Limitless, tras comprarla Meta, dejó de funcionar en la UE el 5-12-2025 y borró las cuentas de allí.
  - Mandar cosas en tu nombre (Martin; su documentación no dice si pide confirmación).

  Estos tres fallos dan la razón al diseño de Zazu: servidor propio y aprobación en el móvil.

### 2. Tabla comparativa

| Producto | Cómo recuerda | Privacidad | Móvil | ¿Zazu ya lo tiene? |
|---|---|---|---|---|
| **Lindy** | Archivos `.memory/` y `.skills/` que se ven (pestañas Preview, Raw e History) y se editan. «Cada guardado es una versión» | Solo nube. Dice que no vende ni entrena con tus datos. SOC 2 y RGPD | Sin app («No app to install»). iMessage, SMS, llamadas y web en el móvil | **En parte.** Memoria en archivos sí (Hermes, con copias `.bak`). Pantalla para verlos y versiones a la vista, no. Canal de mensajería sí (WhatsApp) |
| **Dot** (cerró el 5-10-2025) | Historial vivo con «tarjetas» de recuerdos | Nube. Al cerrar dejó exportar los datos | Solo iOS | **En parte.** `fran-hub` es un diario de turnos compartido entre la web, WhatsApp y otras vías, no un historial de la vida de Fran. Su cierre es un aviso de lo que pasa si dependes de la nube |
| **Limitless / Rewind** (Meta) | Graba audio (y la pantalla en Rewind) y luego busca en ello | Rewind: todo local. Limitless: nube cifrada | El colgante pasa el audio al iPhone. Rewind dejó de grabar el 19-12-2025 | **No**, y no conviene (ver §4). Sí vale su idea de elegir cuánto tiempo se guarda cada cosa |
| **Bee** (Amazon) | Lista de «datos sobre ti», resúmenes, 14 días de memoria en el plan gratis | El audio se transcribe y se descarta. Claves que controla el dispositivo. Computación confidencial en AWS Nitro | App y Alexa+ (con Bee Pro, 11,99 $/mes). Android sin confirmar | **En parte.** `hechos.py` ya propone hechos, pero no hay pantalla para aprobarlos |
| **Proton Lumo** | Memoria que eliges (qué guarda, qué olvida y qué no aprende nunca) y Proyectos | Cifrado de acceso cero, sin registros, modelos de código abierto en servidores de Proton en Europa | iOS, Android y web | **En parte.** Sus datos ya se quedan en Spirit. No hay cifrado en reposo (el disco no está cifrado) ni interruptores de memoria |
| **Apple Intelligence** | Contexto del dispositivo; memoria editable sin confirmar | En el dispositivo, o en PCC sin estado. Registro exportable de lo que sale (solo metadatos) | Integrado en el sistema e intents de apps | **No**: falta el registro de «qué salió de Spirit» y el reparto local/nube |
| **Home Assistant Assist** | Sin memoria a largo plazo, solo el historial de la conversación | Totalmente local si se quiere | La app Companion puede ser el asistente del teléfono (pulsación larga del botón de encendido, también con la pantalla bloqueada) | **En parte.** Whisper y Kokoro sí. El complemento de HA está instalado pero **desactivado** (`plugins.disabled`). No hay palabra de activación |
| **ChatGPT** | Datos guardados más historial. «Dreaming» (junio de 2026) rehace la memoria por su cuenta | Nube. Borrar un chat no borra lo aprendido de él | Avisos push de tareas, Pulse | **En parte.** Reflexión nocturna sí (`reflexion.py`, 04:25). Avisos push en la app y chat temporal, no |
| **Claude** | Temas editables. Búsqueda en chats con citas que enlazan al chat original | Nunca guarda documentos de identidad, antecedentes, cuentas bancarias ni situación de residencia. Lo sensible (salud, religión, política) solo se guarda si se activa | Igual en web y en la app | **En parte.** Hermes ya trae la herramienta `session_search` (activa en `config.yaml`). Faltan la cita con enlace en la web y el filtro de datos sensibles |
| **Gemini en Android** | Interruptor «chats anteriores» | Retiene hasta 72 h aunque desactives la actividad | Lee y responde notificaciones (WhatsApp incluido; no lee notas de voz, imágenes ni vídeos). «Nunca paga sin ti»: sin confirmar | **En parte.** La aprobación en el móvil ya existe (`movil-aprobacion.py`). Leer notificaciones, no |
| **Galaxy AI** | Motor de datos personales en el teléfono (sin confirmar en las fuentes revisadas) | Interruptor «Procesar datos solo en el dispositivo» (algunas funciones dejan de ir). Que al apagarlo **borre** lo analizado: sin confirmar | Resumen diario (Now Brief) | **En parte.** Resumen diario sí (`resumen-hoy`). Interruptor «solo local», no |
| **Copilot / Recall** | Capturas de pantalla con OCR, más memoria «recuerda que…» | Claves protegidas por el TPM. Windows Hello con autorización que caduca. Filtro de datos sensibles activado por defecto | App Copilot. Recall solo en Windows | **No**: falta el filtro de datos sensibles. No conviene copiar las capturas |
| **AnythingLLM** | Un «Observador» propone hasta 3 hechos con su nivel de confianza y un «Reflector» quita duplicados, cada 3 h | Local primero. Avisa de que la memoria viaja al proveedor del modelo | App Android: avisos en la pantalla de bloqueo, compartir, barra de texto seleccionado | **En parte.** Propone hechos (y compara con lo ya aprobado o rechazado), pero no los muestra. Compartir solo texto |
| **Open WebUI / Jan / Khoj** | Memorias como herramientas (`add_memory`, `search_memories`, `delete_memory`). Jan separa `AGENTS.md` (lo escribe la persona) de la memoria (la escribe el agente). Búsqueda con citas | Autoalojados | PWA con compartir texto, enlaces y archivos; WhatsApp (Khoj) | **En parte.** Obsidian (`~/Cerebro`) y la búsqueda de sesiones de Hermes sí. Herramientas de memoria con citas a la vista, no |

Otros revisados (están en las fichas y en Fuentes): Martin, Ohai, Poke, Friend, Plaud, Ollama y LM Studio.

### 3. Ideas concretas para Zazu

Escala: **esfuerzo** bajo (horas), medio (días) o alto (semanas). **Prioridad** alta, media o baja.

#### 3.1 Memoria

**M1. Una pantalla «Memoria» en holazazu.app para ver, editar y deshacer**
- *Qué hacen ellos:*
  - Lindy tiene un explorador de memoria con pestañas Preview, Raw e History, y «cada guardado es una versión» ([docs.lindy.ai/teammate/memory](https://docs.lindy.ai/teammate/memory)).
  - Claude ordena la memoria por temas que se editan uno a uno ([support.claude.com](https://support.claude.com/en/articles/11817273-use-claudes-chat-search-and-memory-to-build-on-previous-context)).
  - Jan separa las reglas que escribe la persona (`AGENTS.md`) de los hechos que aprende el agente ([docs.jan.ai/agent/memory](https://docs.jan.ai/agent/memory)).
- *Aquí:* `MEMORY.md` y `USER.md` (en `~/.hermes/memories/`) ya son archivos y ya tienen copias `.bak`. Basta una pestaña en `pagina-web/web/` (pantallas React) que los muestre por secciones, deje editarlos y enseñe las versiones anteriores. Para las versiones se puede usar git en `~/.hermes/memories/` o guardar copias con fecha. Al tocar la configuración de Hermes, el hook `movil-aprobacion.py` ya pide el OK, así que no hace falta inventar otra puerta.
- *Pieza reutilizable:* ninguna externa; basta con código propio del hub. Opcional: git (GPL-2.0, se usa como programa, no se incluye en el código).
- *Esfuerzo:* medio. *Prioridad:* **alta**.

**M2. Aprobar los «Recuerda: …» deslizando, como los «facts» de Bee**
- *Qué hacen ellos:*
  - Bee lleva una lista de datos sobre ti; en la prueba de TWiT había reunido 477 ([twit.tv](https://twit.tv/posts/tech/future-personal-ai-inside-beecomputers-always-digital-memory-device)). Confirmarlos o rechazarlos deslizando está **sin confirmar**.
  - AnythingLLM: un «Observador» propone como mucho 3 hechos con su nivel de confianza y un «Reflector» quita duplicados y descarta lo dudoso ([docs.anythingllm.com/features/memories](https://docs.anythingllm.com/features/memories)).
- *Aquí:* `aprendizaje/hechos.py` ya propone hasta 3 hechos por noche y nunca escribe en `MEMORY.md` ni en `USER.md`. También compara con lo ya propuesto, aprobado o rechazado. Falta el último paso: enseñarlos en la pantalla M1 o en la app de Android con ✅ y ❌. Lo aprobado entra en `MEMORY.md` y lo rechazado se apunta en la tabla `feedback` de `almacen.db`, que ya existe, para no volver a proponerlo. Además conviene comprobar si el plugin `memory-review` (está en `~/.hermes/plugins/` pero no en `plugins.enabled`) hace ya parte de esto antes de escribir nada nuevo.
- *Pieza reutilizable:* la lógica Observador/Reflector de AnythingLLM (licencia MIT), como referencia.
- *Esfuerzo:* bajo-medio. *Prioridad:* **alta**.

**M3. Filtro de datos sensibles antes de guardar**
- *Qué hacen ellos:*
  - Claude no guarda nunca documentos de identidad, antecedentes penales, números de cuentas bancarias ni situación de residencia. Salud, religión y política solo los guarda si se activa «Include sensitive topics in memory» ([support.claude.com](https://support.claude.com/en/articles/11817273-use-claudes-chat-search-and-memory-to-build-on-previous-context)).
  - Recall filtra contraseñas y tarjetas por defecto ([support.microsoft.com](https://support.microsoft.com/en-us/windows/retrace-your-steps-with-recall-aa03f8a0-a78b-4b3e-b0a1-2eb8ac48701c)).
  - AnythingLLM avisa de que la memoria viaja al proveedor del modelo y pide no guardar contraseñas ni claves.
- *Aquí:* poner una revisión con patrones (IBAN, DNI/NIE, tarjetas, contraseñas, claves de API) antes de cualquier escritura en la memoria. Puede ir en `hechos.py` y en un hook de Hermes. Importa porque lo que hay en `MEMORY.md` se manda a Anthropic en cada conversación. La skill `memoria-higiene` (`~/.hermes/skills/productivity/`) puede usar esas mismas reglas.
- *Pieza reutilizable:* expresiones regulares propias; no hace falta ninguna librería.
- *Esfuerzo:* bajo. *Prioridad:* **alta**.

**M4. Buscar en conversaciones pasadas con cita y enlace**
- *Qué hacen ellos:*
  - Claude busca en los chats anteriores y responde con citas que enlazan al chat original.
  - Plaud dice responder con una cita que lleva al trozo original (**sin confirmar**: su página no lo muestra) ([plaud.ai](https://www.plaud.ai/pages/plaud-intelligence)).
  - Khoj indexa tus notas para responder con citas ([docs.khoj.dev](https://docs.khoj.dev/)).
- *Aquí:*
  1. Hermes **ya trae** la herramienta `session_search`, activa en `config.yaml`, con búsqueda FTS5 sobre `~/.hermes/state.db`. No hace falta crear otro índice de sesiones.
  2. Falta enseñar el resultado como cita con fecha y enlace a la conversación en la web.
  3. Falta sumar `~/Cerebro`, con un índice SQLite FTS5 propio o una skill.
  4. Más adelante, añadir búsqueda por significado con embeddings de Ollama (ya instalado) y sqlite-vec.

  Mejor esto que meter todo en el contexto, porque gasta menos tokens y manda menos datos fuera.
- *Pieza reutilizable:* SQLite FTS5 (dominio público). [sqlite-vec](https://github.com/asg017/sqlite-vec), con licencia doble MIT o Apache-2.0; va por versiones previas a la 1.0.
- *Esfuerzo:* bajo-medio (lo hace más barato que ya exista `session_search`). *Prioridad:* **alta**.

**M5. Consolidación nocturna con fechas y caducidad**
- *Qué hacen ellos:*
  - ChatGPT tiene «Dreaming» (desde junio de 2026): la memoria se reescribe en segundo plano y convierte los planes en hechos pasados («vas a ir a Singapur en julio» pasa a «fuiste a Singapur en julio de 2026») ([digitalcitizen.life](https://www.digitalcitizen.life/chatgpts-dreaming-feature-makes-its-memory-more-useful-and-easier-to-manage/), [tomsguide.com](https://tomsguide.com/ai/chatgpts-new-memory-builds-a-profile-of-you-on-its-own-and-openai-admits-you-cant-see-all-of-it); fuentes secundarias).
  - Bee guarda 14 días en el plan gratis ([techcrunch.com](https://techcrunch.com/2026/10/15/amazons-bee-launches-two-new-personal-ai-devices-starting-at-75/)). Friend, 30 días por defecto, con un pago de 10 $/mes para más tiempo ([the-gadgeteer.com](https://the-gadgeteer.com/2026/07/31/friend-ai-pendant-voice-wearable-249-price/)). Rewind dejaba elegir de 1 semana a siempre (**sin confirmar**).
- *Aquí:* `zazu-aprende` (04:10) y `zazu-reflexiona` (04:25) ya corren de noche. Se puede añadir un paso **local y sin IA** que marque con fecha las entradas del diario de `fran-hub` y que proponga en M2 tanto pasar a pasado lo que ya ocurrió como borrar lo que lleva más de N días sin usarse. Lo fijo (lo que está en `USER.md`) no caduca.
- *Pieza reutilizable:* código propio dentro de `aprendizaje/`.
- *Esfuerzo:* medio. *Prioridad:* media.

**M6. Chat temporal y «olvidar de verdad»**
- *Qué hacen ellos:*
  - Los chats de incógnito de Claude no entran en la memoria ni en la búsqueda de chats. ChatGPT tiene chats temporales.
  - En ChatGPT y en Claude, borrar un chat no borra lo aprendido de él. Claude lo dice así: «related memory entries generated from it won't be removed».
  - Que Samsung borre lo analizado al apagar la función está **sin confirmar**: no aparece en las fuentes revisadas.
  - Lumo deja decidir qué guarda, qué olvida y qué no aprende nunca ([proton.me/blog/lumo-2](https://proton.me/blog/lumo-2)).
- *Aquí:*
  - Un botón «chat sin memoria» en la web. Hermes tiene por dentro una opción `skip_memory` (la usa en procesos por lotes), pero queda **sin confirmar** si se puede activar en cada sesión desde la web. La otra vía es un perfil con `memory_enabled: false`.
  - Al borrar una conversación, preguntar «¿borro también lo que aprendí de ella?».
  - Una lista de «no aprender nunca» que lea `hechos.py`.
- *Pieza reutilizable:* la configuración de perfiles de Hermes que ya existe.
- *Esfuerzo:* bajo-medio. *Prioridad:* media.

#### 3.2 Privacidad

**P1. Informe «qué ha salido de Spirit»**
- *Qué hacen ellos:* Apple deja ver y exportar el «Informe de Apple Intelligence» (Ajustes > Privacidad y seguridad), con cada petición que salió hacia Private Cloud Compute en los últimos 15 minutos o 7 días. Solo guarda metadatos (tamaño, función, duración), nunca el contenido ([support.apple.com](https://support.apple.com/guide/mac-help/mchlfc0d4779), [apple.com](https://www.apple.com/legal/privacy/data/en/intelligence-engine/)).
- *Aquí:* registrar cada llamada a un modelo externo con fecha, perfil, modelo, tamaño en tokens y motivo (chat, reflexión, vigía…), **sin guardar el contenido**, y enseñarlo en una página del hub con totales por día. Hermes ya guarda el uso **por sesión y modelo** en la tabla `session_model_usage` de `~/.hermes/state.db`; ese es el punto de partida. Le falta el detalle por llamada y el motivo. La reflexión nocturna ya guarda su texto en `aprendizaje/datos/salidas/`.
- *Pieza reutilizable:* la tabla de Hermes más código propio o un hook.
- *Esfuerzo:* medio. *Prioridad:* **alta**.

**P2. Una tabla corta de qué se guarda, cuánto tiempo y qué sale fuera**
- *Qué hacen ellos:*
  - LM Studio tiene una política de privacidad con un resumen («TL;DR») y una lista de qué sale de tu equipo y cuándo ([lmstudio.ai/app-privacy](https://lmstudio.ai/app-privacy)).
  - Google explica que guarda las conversaciones hasta 72 h aunque desactives la actividad ([support.google.com](https://support.google.com/gemini/answer/13278892?hl=en)).
- *Aquí:* añadir a `pagina-web/publica/seguridad.html` y `/privacidad` una tabla con cada dato (memoria, sesiones, audios, copias del móvil, `almacen.db`, copias de seguridad), dónde vive y cuánto tiempo se guarda. Las «Cuatro promesas, sin letra pequeña» ya existen en `seguridad.html`; esto las hace comprobables.
- *Pieza reutilizable:* ninguna.
- *Esfuerzo:* bajo. *Prioridad:* **alta**.

**P3. Interruptor «solo local» y reparto por niveles**
- *Qué hacen ellos:*
  - Samsung tiene el interruptor «Procesar datos solo en el dispositivo» y algunas funciones quedan limitadas ([tomsguide.com](https://www.tomsguide.com/phones/you-can-turn-off-galaxy-ai-on-your-samsung-phone-heres-how)).
  - Home Assistant tiene «Prefer handling commands locally» ([home-assistant.io](https://www.home-assistant.io/blog/2025/02/13/voice-chapter-9-speech-to-phrase/)).
  - Apple procesa en el dispositivo lo que puede y manda el resto a PCC.
- *Aquí:* Ollama con `qwen3:4b-instruct-2507-q4_K_M` ya está en `custom_providers` y existe la skill `modelo-local-conviene`.
  - Un perfil o interruptor «solo local» que fuerce Ollama y diga claramente qué se pierde (calidad, herramientas).
  - Mandar al modelo local las tareas privadas y sencillas: clasificar correos del vigía y resumir WhatsApp.

  Ojo: Open WebUI avisa de que «los modelos locales pequeños pueden guardar o recuperar la información de forma irregular» ([docs.openwebui.com](https://docs.openwebui.com/features/chat-conversations/memory/)), así que hay que medirlo con `zazu/evals/correr.py` antes de mover nada.
- *Pieza reutilizable:* [Ollama](https://github.com/ollama/ollama), licencia MIT, ya instalado.
- *Esfuerzo:* medio. *Prioridad:* media.

**P4. Cifrar en reposo la memoria y las sesiones**
- *Qué hacen ellos:*
  - Lumo cifra el historial con cifrado de acceso cero.
  - Samsung usa Knox Vault (KEEP: sin confirmar en las fuentes revisadas).
  - Recall protege sus claves con el TPM y pide Windows Hello ([blogs.windows.com](https://blogs.windows.com/windowsexperience/2024/09/27/update-on-recall-security-and-privacy-architecture/)).
- *Aquí:* **el disco de Spirit no está cifrado.** La raíz es `ext4` directamente sobre `nvme0n1p2`, sin LUKS. Cifrar el disco es lo más sencillo y protege si roban el equipo o el disco, pero exige reinstalar o migrar con cuidado y desbloquear al arrancar (con TPM, o con clave por red). Cifrar solo `~/.hermes/` con una clave en el TPM es más fino, pero Hermes necesita leer esos archivos mientras funciona, así que no protege frente a alguien con sesión abierta. Las copias de seguridad diarias ya van cifradas.
- *Pieza reutilizable:* LUKS/cryptsetup (GPL-2.0), `systemd-creds` con TPM (LGPL-2.1), gocryptfs (MIT). Son herramientas del sistema, no se incluyen en el código.
- *Esfuerzo:* medio-alto. *Prioridad:* **media-alta**, porque el disco no está cifrado.

**P5. Pedir de nuevo la identidad para ver la memoria**
- *Qué hacen ellos:* Recall pide Windows Hello y la autorización caduca ([blogs.windows.com](https://blogs.windows.com/windowsexperience/2024/09/27/update-on-recall-security-and-privacy-architecture/)).
- *Aquí:* que la pantalla M1 pida otra vez Google, o el TOTP en local, si la sesión tiene más de X minutos. Hoy las sesiones duran 14 días (`SESSION_DAYS = 14` en `pagina-web/server.py`).
- *Esfuerzo:* bajo. *Prioridad:* baja, porque solo la usa Fran.

> **Ya lo tenemos (no tocar):** el «paso final humano» antes de enviar o pagar ya existe en `hermes/agent-hooks/movil-aprobacion.py`, con 113 casos de prueba en `modo-hermes/` según `hermes/README.md`. Gemini, Lindy («You review, and you send») y ChatGPT agent lo venden como novedad. Tampoco hay que copiar el agente con cuenta propia de Copilot Actions: la Regla de Dos (`platform_toolsets.cron: []`) y los perfiles con distintos permisos ya cubren lo importante.

#### 3.3 Móvil

**Mo1. Avisos que lleguen al móvil desde Spirit, sin depender de Google**
- *Qué hacen ellos:*
  - ChatGPT envía un aviso cuando acaba una tarea programada ([help.openai.com](https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt); la página no se pudo abrir el 22-10-2026, sin reconfirmar).
  - AnythingLLM avisa con el móvil bloqueado cuando termina una respuesta o una tarea programada ([docs.anythingllm.com/mobile](https://docs.anythingllm.com/mobile/overview)).
  - Que Open WebUI solo avise con la app abierta está **sin confirmar**.
- *Aquí:* hoy los avisos llegan por WhatsApp, y la app recoge las peticiones al abrirse y con un trabajo cada 15 minutos (`Copia.java`, `CopiaJob.java`), que en Samsung puede llegar tarde. La vía más corta es **montar ntfy en Spirit**, detrás del túnel o de Tailscale, y usar su app de Android. Su documentación dice que con servidores propios **no usa Firebase**, y su «entrega instantánea» funciona con un servicio en primer plano y una notificación fija ([docs.ntfy.sh](https://docs.ntfy.sh/subscribe/phone/)). Después, los temporizadores (`zazu-vigia`, `resumen-hoy`…) hacen un `curl` al tema de ntfy. Más adelante se podría avisar a la app de Zazu para que recoja las peticiones al momento (UnifiedPush; detalle **sin confirmar**).
- *Pieza reutilizable:* [ntfy](https://github.com/binwiederhier/ntfy), con licencia doble Apache-2.0 o GPLv2.
- *Esfuerzo:* bajo-medio. *Prioridad:* **alta**.

**Mo2. Compartir archivos y «Preguntar a Zazu» sobre texto seleccionado**
- *Qué hacen ellos:*
  - AnythingLLM Mobile aparece en la barra de selección de cualquier app (pulir, acortar, corregir, resumir, explicar) y en el menú de compartir, con fotos, documentos y enlaces ([docs.anythingllm.com/mobile](https://docs.anythingllm.com/mobile/overview)).
  - Open WebUI admite compartir texto, enlaces y archivos donde el sistema y el navegador lo permiten ([docs.openwebui.com](https://docs.openwebui.com/ecosystem/computer/phone-and-remote/phone-app/)).
- *Aquí:* la app 2.1 ya recibe `ACTION_SEND` con `text/plain` (`MainActivity.java`). Faltan dos cosas:
  - Recibir `ACTION_SEND` y `ACTION_SEND_MULTIPLE` con imágenes, PDF y audio, y subirlos por la misma vía que `movil.py`.
  - Registrar `ACTION_PROCESS_TEXT`, para que «Zazu» salga en el menú al seleccionar texto en cualquier app.

  Ambas son de Android y no necesitan librerías, lo que encaja con «Java sin librerías».
- *Pieza reutilizable:* las propias de Android ([Intent.ACTION_PROCESS_TEXT](https://developer.android.com/reference/android/content/Intent#ACTION_PROCESS_TEXT)).
- *Esfuerzo:* bajo-medio. *Prioridad:* **alta**.

**Mo3. Resumen de la mañana en tarjetas que se acaban**
- *Qué hacen ellos:*
  - ChatGPT Pulse da cada mañana una tanda de tarjetas (de 5 a 10, según la prensa; el número está **sin confirmar**). Termina con «That's all for today» y deja valorarlas con 👍 o 👎 ([openai.com](https://openai.com/index/introducing-chatgpt-pulse/)).
  - Galaxy AI tiene Now Brief.
  - Lindy y Ohai mandan un resumen diario (el de Lindy está **sin confirmar**; su anuncio habla de una rutina de bandeja de entrada por la mañana).
- *Aquí:* `resumen-hoy` y `zazu-dia.py` ya existen. Se trata de darles forma de tarjetas en el hub, con 👍 o 👎 que se guarden en `feedback` de `almacen.db`, y de mandar un aviso con Mo1.
- *Esfuerzo:* bajo-medio. *Prioridad:* media.

**Mo4. Que Zazu sea el «asistente digital» del teléfono**
- *Qué hacen ellos:* la app Companion de Home Assistant se puede poner como asistente predeterminado y se abre con una pulsación larga del botón de encendido; también se puede lanzar desde la pantalla bloqueada ([home-assistant.io/voice_control/android](https://home-assistant.io/voice_control/android/)). Gemini hace lo mismo.
- *Aquí:* declarar en la app el rol de asistente ([RoleManager.ROLE_ASSISTANT](https://developer.android.com/reference/android/app/role/RoleManager#ROLE_ASSISTANT)) para que abra Zazu con el micrófono listo. Queda **sin confirmar** si basta con una actividad que responda a `ACTION_ASSIST` o si hace falta un `VoiceInteractionService` completo. Hay que probarlo en el S25.
- *Esfuerzo:* medio. *Prioridad:* media.

**Mo5. Leer las notificaciones del móvil**
- *Qué hacen ellos:* Gemini lee y responde las notificaciones de apps de mensajería, WhatsApp incluido, pero no lee notas de voz, imágenes ni vídeos ([support.google.com](https://support.google.com/gemini/answer/15235441)). Si lee también el historial de la app está sin confirmar.
- *Aquí:* usar `NotificationListenerService` con un permiso explícito y una lista de apps permitidas. Zazu ya lee WhatsApp por su cuenta, así que aporta poco y pone mucho al alcance de la app.
- *Esfuerzo:* medio. *Prioridad:* **baja**.

**Mo6. Probar Conduit como cliente nativo**
- *Qué hacen ellos:* Conduit (iOS y Android, GPL-3.0) es un cliente de Open WebUI que también se conecta directamente a un servidor Hermes Agent, con la URL y `API_SERVER_KEY`. Pide aprobar los pasos sensibles antes de ejecutarlos ([github.com/cogwheel0/conduit](https://github.com/cogwheel0/conduit)).
- *Aquí:* solo como prueba, para comparar. No sustituye a la app propia, que ya tiene Google, copias de seguridad y peticiones. Está **sin confirmar** que funcione con la versión de Hermes de Spirit; en `platform_toolsets`, `api_server` está vacío.
- *Esfuerzo:* bajo. *Prioridad:* baja.

> **Ya lo tenemos:**
> - Un canal de mensajería como entrada principal. Lindy, Poke, Martin y Khoj lo venden; Zazu usa WhatsApp.
> - Acceso privado por VPN, el patrón LM Link de LM Studio. Descartado: Tailscale se quitó de Spirit (2026-10-23); el acceso remoto es solo por holazazu.app.
> - Instalar la web en iPhone como PWA.

#### 3.4 Casa y voz

**C1. Activar el complemento de Home Assistant (si hay domótica)**
- *Qué hacen ellos:* Home Assistant expone el estado de la casa y sus acciones a un LLM, con Ollama, OpenAI o Anthropic ([home-assistant.io/integrations/ollama](https://home-assistant.io/integrations/ollama)).
- *Aquí:* el complemento `~/.hermes/plugins/homeassistant/` ya está instalado y figura en `plugins.disabled`. Daría 4 herramientas a Zazu (número sin reconfirmar). Queda **sin confirmar** si Fran tiene Home Assistant funcionando. Si lo tiene: activarlo solo en un perfil, exponer pocas entidades (la documentación recomienda «menos de 25» con modelos locales) y que `ha_call_service` pase por `movil-aprobacion.py` en todo lo que no sea luces.
- *Esfuerzo:* bajo. *Prioridad:* depende de si hay domótica.

**C2. Local primero: resolver sin IA lo sencillo**
- *Qué hacen ellos:* con «Prefer handling commands locally», Home Assistant prueba primero su agente local y solo pasa al LLM lo que no entiende. Además comparte el historial para que el LLM entienda los seguimientos ([home-assistant.io](https://www.home-assistant.io/blog/2025/02/13/voice-chapter-9-speech-to-phrase/)).
- *Aquí:* `zazu/scripts/zazu-rapido.py` ya responde sin IA a `/hoy`, `/manana`, `/semana` y `/tareas`, como «quick_command» del gateway. Se puede extender delante del chat para temporizadores, recordatorios y «¿cómo está el servidor?», con reglas simples. Si no reconoce la orden, pasa a Hermes con lo dicho incluido.
- *Pieza reutilizable:* código propio. Como referencia, la sintaxis de frases de Speech-to-Phrase o hassil (licencia **sin confirmar**).
- *Esfuerzo:* medio. *Prioridad:* media.

**C3. Voz local compatible con Wyoming (para un altavoz en casa)**
- *Qué hacen ellos:* Wyoming conecta el reconocimiento de voz, la voz sintetizada y la palabra de activación sobre TCP. Con él, el altavoz Voice PE puede hacer de micrófono y altavoz ([home-assistant.io/integrations/wyoming](https://www.home-assistant.io/integrations/wyoming/)). Voice PE salió por 59 $ (sin reconfirmar); The Pi Hut lo lista a 55,80 £ y agotado.
- *Aquí:* Zazu ya tiene Whisper `small` (`stt.provider: whisper_local`) y Kokoro. `tts.providers.piper-local` llama a `tts-kokoro.sh`, así que Kokoro está activo aunque el README de `voz/` diga «sin activar»; conviene corregir ese README. Envolverlos en Wyoming permitiría un altavoz en el salón sin usar la nube. Solo merece la pena si Fran quiere hablar con Zazu sin el móvil.
- *Pieza reutilizable:*
  - [wyoming-faster-whisper](https://github.com/rhasspy/wyoming-faster-whisper): MIT.
  - Piper: el [original](https://github.com/rhasspy/piper) era MIT y se archivó el 6-10-2025; el [actual](https://github.com/OHF-Voice/piper1-gpl) es **GPL-3.0**.
  - [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M): Apache-2.0.
- *Esfuerzo:* medio-alto. *Prioridad:* baja.

**C4. Palabra de activación («Oye Zazu»)**
- *Qué hacen ellos:* Voice PE usa microWakeWord en el propio aparato, con «Okay Nabu», «Hey Jarvis» y «Hey Mycroft» (la lista de palabras está sin reconfirmar).
- *Aquí:* encaja con la idea «Jarvis», pero entrenar una palabra propia es difícil (su README dice «Training a model that works well is still very difficult») y exige un micrófono siempre escuchando.
- *Pieza reutilizable:*
  - [microWakeWord](https://github.com/kahrendt/microWakeWord): Apache-2.0.
  - [openWakeWord](https://github.com/dscripka/openWakeWord): el código es Apache-2.0, pero **los modelos ya entrenados son CC BY-NC-SA 4.0, no comerciales**. Valen para uso personal, no para una app de pago en Google Play.
- *Esfuerzo:* alto. *Prioridad:* baja.

### 4. Lo que NO conviene copiar

| Qué | Quién lo hace | Por qué no |
|---|---|---|
| Grabar todo el día (audio o pantalla) | Limitless, Bee, Friend, Rewind, Recall | **Privacidad y ley.** Graba a terceros que no han dado permiso; Limitless sacó un «modo consentimiento» y aun así acabó saliendo de la UE tras la compra de Meta. **Rechazo social:** las reseñas de Friend hablan de gente incómoda. **Valor dudoso:** Vice dice que Bee «se equivoca en casi todo». **Coste:** disco y CPU de Spirit |
| Depender de una nube ajena para la memoria | Dot, Limitless, Poke | Dot cerró el 5-10-2025. Limitless dejó de funcionar en la UE, el Reino Unido y otros países el 5-12-2025 y borró esas cuentas después del 19-12-2025. Rewind dejó de grabar. Poke pasó a Cognition (julio de 2026). Que Zazu viva en Spirit es justo la defensa contra esto |
| Actuar o enviar en tu nombre | Martin (lee, envía y responde en Slack y escribe o llama a otros «on your behalf»; no dice si pide confirmación) | Va contra la puerta de aprobación de Zazu, que ya funciona |
| «Computación confidencial» con chips especiales | Apple PCC, Bee en AWS Nitro, Google Private AI Compute | Resuelve un problema que Spirit no tiene, porque el servidor ya es de Fran. Es complejidad enorme sin ganancia. Lo que sí sale fuera (a Anthropic) no se arregla con esto, sino con P1 y P3 |
| Que personas lean tus datos o se entrene con ellos | Ohai (revisión humana de parte de los correos y entrenamiento de sus algoritmos), Gemini (revisión humana hasta 3 años, según la prensa), Poke (entrena salvo con «Maximum Privacy») | Rompe la promesa «Nada para terceros» de `seguridad.html` |
| Miles de integraciones o usar el navegador para todo | Lindy (el número de integraciones está sin confirmar), Gemini (automatizar apps de terceros) | Más ataque por textos trampa, más mantenimiento. Hermes ya tiene 95 skills y el navegador solo está en el perfil `tecnico`, que es lo correcto |
| Un «compañero» con personalidad | Friend, Dot | Dot cerró y Friend recibió malas reseñas. Zazu debe ser útil antes que «amigo» |
| Leer las notificaciones de todo el móvil | Gemini | Aporta poco frente a lo que ya hay (WhatsApp) y da a la app acceso a todo (ver Mo5) |
| Modelos de palabra de activación ya entrenados de openWakeWord en una app de pago | — | Su licencia es no comercial (CC BY-NC-SA 4.0) |
| Usar Open WebUI con otra marca | — | Desde la v0.6.6 (19-4-2025) su licencia prohíbe quitar la marca salvo con 50 usuarios o menos en 30 días. A Fran le valdría, pero mejor no atarse |

### 5. Las 5 primeras cosas a hacer, en orden

1. **Filtro de datos sensibles en la memoria** (M3). Son unas horas, no depende de nada y protege lo que ya se manda a Anthropic en cada conversación. De paso, decidir si se activa el plugin `memory-review` o se borra.
2. **Pantalla «Memoria» con aprobación de los «Recuerda: …»** (M1 y M2). Convierte lo que `hechos.py` ya propone en algo que Fran ve, aprueba y deshace. Es la diferencia principal frente a Lindy, Bee y Claude.
3. **Avisos al móvil con ntfy en Spirit** (Mo1). Cubre la falta más clara de la app (hoy recoge cada 15 minutos) sin Firebase ni librerías en la app.
4. **Compartir archivos y texto seleccionado hacia Zazu** (Mo2). Son cambios pequeños en la app de Android que se usan a diario.
5. **«Qué ha salido de Spirit» y la tabla de qué se guarda y cuánto tiempo** (P1 y P2). Hace comprobables las «Cuatro promesas» de la web. Se puede partir de `session_model_usage` en `~/.hermes/state.db`.

Después:
- Decidir si se cifra el disco de Spirit (P4); hoy no lo está.
- Citas a la vista sobre `session_search` y sumar `~/Cerebro` (M4).
- Consolidación con fechas (M5).
- Local primero (C2 y P3), midiendo con `zazu/evals`.

La parte de casa y voz (C1, C3 y C4) va solo si Fran confirma que tiene domótica o quiere un altavoz.

### Cómo lo hacen en su código (lectura de repos, 22-10-2026)

> Cómo se hizo: clones superficiales y parciales, **solo leídos**. No se ejecutó ni se instaló nada. Commits leídos: mem0 `2c81af3`, letta `56ba9c2` (rama `archive`), letta-code `035bb8c`, Open WebUI `91ea4e3`, Khoj `ae229ca`, Presidio `4f0e236`, litellm `f2118fc`, ntfy `fe03769`, ntfy-android `a8427f5`, UnifiedPush `eaa0fc5` y `1442733`, Home Assistant Android `023390b` y AnythingLLM Mobile `e863681`. Los números de línea son de esos commits y pueden cambiar en `main`.
>
> Lo que cambia respecto a lo de arriba:
> - **Hermes ya trae la cola de aprobación de la memoria.** La opción es `memory.write_approval`, que hoy está apagada en `~/.hermes/config.yaml`.
> - **Spirit ya tiene el filtro de M3:** `zazu/scripts/privacidad.py`, función `tachar()`. Lo que falta en los dos casos es conectarlos.
> - **mem0 v3 ya no hace ADD/UPDATE/DELETE.** Solo añade recuerdos y enlaza las contradicciones.
> - **En `main` de letta-ai/letta ya no está el servidor.** Está en la rama `archive`; lo actual es letta-code, que guarda la memoria como un repositorio git de archivos `.md`.

**M1/M2 · Ver la memoria y aprobar lo que entra**

| Proyecto | Archivo clave | Patrón | Licencia |
|---|---|---|---|
| Hermes (ya en Spirit) | `~/.hermes/hermes-agent/tools/write_approval.py` (`stage_write`, `list_pending`) y `tools/memory_tool.py` (`apply_memory_pending`) | Con `memory.write_approval: true`, cada escritura del agente se aparca en `~/.hermes/pending/memory/<id8hex>.json`. Al aprobarla, comprueba antes que el recuerdo no haya cambiado. Se maneja con `/memory pending`, `/memory approve <id>` y `/memory reject <id>` | Ya instalado; no se copia nada |
| mem0 | [mem0/memory/main.py](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py#L881-L1220) (`_add_to_vector_store`) y [mem0/configs/prompts.py](https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py#L176-L460) (`get_update_memory_messages`) | **v2:** dos llamadas al modelo, una que saca los hechos y otra que decide `ADD/UPDATE/DELETE/NONE` frente a los recuerdos numerados 0..n (números, no UUID, para que no se invente identificadores). **v3:** solo añade, quita los duplicados exactos con un MD5 del texto y apunta cada cambio (antes y después) en una tabla `history` | Apache-2.0 |
| Letta (rama `archive`) | [letta/functions/function_sets/base.py](https://github.com/letta-ai/letta/blob/archive/letta/functions/function_sets/base.py#L311-L388) (`memory_replace`, `memory_insert`) | Para reemplazar exige que el texto viejo aparezca **exactamente una vez**. Si aparece cero o varias veces, falla y dice en qué líneas está | Apache-2.0 |
| letta-code | [reflection.md](https://github.com/letta-ai/letta-code/blob/main/src/agent/subagents/builtin/reflection.md), [generate-memory-viewer.ts](https://github.com/letta-ai/letta-code/blob/main/src/web/generate-memory-viewer.ts) y [memory-constraints.ts](https://github.com/letta-ai/letta-code/blob/main/src/memory-constraints.ts) | La memoria es un repositorio git. El visor saca el historial con `git log`, `--stat` y `-p` (los 50 últimos) y marca lo que hizo la IA. Antes de cada commit, un validador comprueba el tope de caracteres y los archivos de solo lectura. La reflexión arregla lo viejo **en su sitio**, sin añadir la versión nueva al lado | Apache-2.0 |
| Open WebUI | [models/memories.py](https://github.com/open-webui/open-webui/blob/main/backend/open_webui/models/memories.py) (`apply_memory_operations`) y [Personalization.svelte](https://github.com/open-webui/open-webui/blob/main/src/lib/components/chat/Settings/Personalization.svelte) | Aplica un lote de cambios `add/replace/move/remove` y salta los duplicados exactos. En `meta.created_by` guarda de dónde salió cada recuerdo. La pantalla tiene buscador local y Editar y Quitar en cada fila; antes de borrar, la confirmación enseña el texto | Open WebUI License (BSD-3 más una cláusula de marca): solo la idea |
| Khoj | [routers/helpers.py](https://github.com/khoj-ai/khoj/blob/master/src/khoj/routers/helpers.py) (`ai_update_memories`) y [userMemory.tsx](https://github.com/khoj-ai/khoj/blob/master/src/interface/web/app/components/userMemory/userMemory.tsx) | El modelo devuelve dos listas: `create` y `delete` (los ids de lo que ya no es cierto). Se edita en el mismo campo, con ✏️ y luego 💾. Su orden de mantenimiento solo enseña lo que haría, salvo con `--apply` | AGPL-3.0: solo la idea |

Cómo lo haríamos en Zazu:
- **Encender la cola de Hermes, sin reescribirla.**
  - Poner `memory.write_approval: true` en `~/.hermes/config.yaml`. Como es configuración, pasa por `movil-aprobacion.py`.
  - En `pagina-web/server.py`, añadir `GET /api/memoria/pendientes` y `POST /api/memoria/pendientes/<id>/(si|no)`. Deben validar el id con `^[0-9a-f]{8}$`, como el plugin `memory-review`, y aplicar con `apply_memory_pending`.
  - En la web, las tarjetas Sí/No pueden reutilizar las de `web/src/panel/ResumenHoy.tsx`.
  - Esfuerzo: **bajo**.
- **Que aprobar una lección escriba de verdad.** Hoy `decidir_leccion` (`server.py`) solo cambia el estado.
  - Al aprobar, añadir el texto a `MEMORY.md` con reemplazo único, como Letta.
  - Saltar el duplicado exacto comparando un hash del texto normalizado, como mem0.
  - Apuntar el antes y el después en una tabla `historial_memoria` de `aprendizaje/almacen.py`. Sirve para «deshacer».
  - Esfuerzo: **bajo**.
- **Pantalla M1** en `pagina-web/web/src/screens/`, con la forma de Open WebUI: buscador, orden por fecha, Editar y Quitar, y confirmación que enseña el texto.
  - Ojo: hoy `/api/mi-zazu` usa como id la posición (`u3`, `m5`). Si Hermes escribe entretanto, se puede borrar el recuerdo equivocado. Hay que usar `sha1(texto)[:10]` o comprobar el texto antes de borrar.
  - Versiones: `difflib` sobre los `.bak` que ya genera Hermes, o git en `~/.hermes/memories/` si Fran lo aprueba.
  - Esfuerzo: **bajo-medio**.
- **Proponer también cambios y borrados** en `aprendizaje/hechos.py`.
  - Pasar al modelo las líneas conocidas numeradas y pedir `{"hecho", "reemplaza": n|null, "contradice": n|null}`. Es mem0 v2 más Khoj, pero **con Fran aprobando**.
  - Añadir a `SISTEMA` las reglas del prompt de mem0: fechas relativas → absolutas, no deducir atributos (género, edad, origen) y no mezclar detalles de recuerdos anteriores.
  - Esfuerzo: **medio**; solo las reglas, muy bajo.

**M3 · Filtro de datos sensibles en la memoria**

| Proyecto | Archivo clave | Patrón | Licencia |
|---|---|---|---|
| Presidio | [es_nif_recognizer.py](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/presidio_analyzer/predefined_recognizers/country_specific/spain/es_nif_recognizer.py), [es_nie_recognizer.py](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/presidio_analyzer/predefined_recognizers/country_specific/spain/es_nie_recognizer.py), [iban_recognizer.py](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/presidio_analyzer/predefined_recognizers/generic/iban_recognizer.py) y [pattern_recognizer.py](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/presidio_analyzer/pattern_recognizer.py) | Cada regla tiene una expresión, un validador y palabras de contexto. Si el validador acierta, la puntuación pasa a 1.0; si falla, se descarta. DNI: la letra es `"TRWAGMYFPDXBNJZSQVHLCKE"[número % 23]`. NIE: X/Y/Z pasan a 0/1/2 antes de calcular. IBAN: control mod 97 y formato de cada país. Tarjeta: Luhn. Al final junta los solapes y sustituye de derecha a izquierda | MIT |
| litellm | [content_filter.py](https://github.com/BerriAI/litellm/blob/main/litellm/proxy/guardrails/guardrail_hooks/litellm_content_filter/content_filter.py) y [patterns.json](https://github.com/BerriAI/litellm/blob/main/litellm/proxy/guardrails/guardrail_hooks/litellm_content_filter/patterns.json) | 82 reglas, cada una con la acción `BLOCK` (rechaza) o `MASK` (tacha). Para el contexto no usa spaCy: solo acepta la coincidencia si entre la palabra clave y el valor hay como mucho una palabra y ninguna cifra | MIT (salvo `enterprise/`) |
| mem0, Letta y Open WebUI | — | Ninguno filtra con patrones antes de guardar; solo lo piden en el prompt | — |

Cómo lo haríamos en Zazu:
- **Sin librerías:** `privacidad.py` ya cubre IBAN (mod 97), tarjetas (Luhn), DNI/NIE, teléfonos, contraseñas, tokens y los valores de `~/.hermes/.env`.
  - Falta comprobar la letra del DNI/NIE con mod 23, como Presidio. La regla de la línea ~299 acepta cualquier `\d{8}[A-Z]`. Para tachar no importa, pero para **bloquear** evita falsos positivos.
  - Esfuerzo: **30 min**.
- **`detectar(texto) -> [(tipo, ini, fin)]`** en `zazu/scripts/privacidad.py`, con las mismas reglas que `tachar()`, para bloquear o contar sin reescribir el texto. Esfuerzo: **½ día**.
- **Bloquear la escritura** con el patrón `BLOCK` de litellm.
  - Va en un plugin nuevo, `hermes/plugins/memoria-escudo/__init__.py`, con `pre_tool_call`. Si la herramienta es `memory`, la acción es add o replace y `detectar()` encuentra algo, devuelve `{"action": "block", "message": …}`. Hermes ya admite ese formato (`hermes_cli/plugins_dispatch.py`).
  - Activarlo en `plugins.enabled` pasa por `movil-aprobacion.py`.
  - Esfuerzo: **2-3 h**.
- **En `aprendizaje/hechos.py`**, después de `_parse()`, descartar los hechos en los que `detectar()` encuentre algo. Hoy se tacha lo que entra, pero nada comprueba lo que sale. Esfuerzo: **1 h**.

**Mo1 · Avisos al móvil sin Google**

| Proyecto | Archivo clave | Patrón | Licencia |
|---|---|---|---|
| ntfy (servidor) | [server/server.go](https://github.com/binwiederhier/ntfy/blob/main/server/server.go#L987) (`handlePublishInternal`, `parsePublishParams`), [server_auth.go](https://github.com/binwiederhier/ntfy/blob/main/server/server_auth.go#L24) y [user/manager.go](https://github.com/binwiederhier/ntfy/blob/main/user/manager.go#L702) (`Authorize`) | Publicar es un POST con las cabeceras `X-Title`, `X-Priority`, `X-Click` y `X-Sequence-Id`. El mismo aviso se actualiza con `/<tema>/<seq>` y se quita con `/clear`. Autenticación con tokens `tk_…` (Bearer). Permisos por tema con patrones (`fran:zazu-*:rw`) y `deny-all` por defecto. Guarda los mensajes 12 h | Apache-2.0 o GPLv2 |
| ntfy-android | [SubscriberService.kt](https://github.com/binwiederhier/ntfy-android/blob/main/app/src/main/java/io/heckel/ntfy/service/SubscriberService.kt) y [JsonConnection.kt](https://github.com/binwiederhier/ntfy-android/blob/main/app/src/main/java/io/heckel/ntfy/service/JsonConnection.kt) | Servicio en primer plano con una sola conexión por servidor. Lee un stream JSON desde `since=` y, si falla, reintenta esperando de 5 s a 120 s. El servidor manda una señal de vida cada 45 s | Apache-2.0 |
| UnifiedPush | [specifications/android.md](https://github.com/UnifiedPush/specifications/blob/main/specifications/android.md) y [ntfy-android up/BroadcastReceiver.kt](https://github.com/binwiederhier/ntfy-android/blob/main/app/src/main/java/io/heckel/ntfy/up/BroadcastReceiver.kt#L38) | Broadcasts explícitos: `REGISTER` → `NEW_ENDPOINT` → `MESSAGE` → `MESSAGE_ACK`. La especificación pide cifrar (RFC 8291), pero el conector acepta texto plano | Apache-2.0 |
| Home Assistant Android | [websocket/WebsocketManager.kt](https://github.com/home-assistant/android/blob/main/app/src/main/kotlin/io/homeassistant/companion/android/websocket/WebsocketManager.kt) | La versión sin Google lanza un trabajo cada 15 min que pasa a primer plano, abre un websocket con ping cada 30 s y confirma cada aviso. Se elige cuándo funciona: nunca, con la pantalla encendida, en el wifi de casa o siempre | Apache-2.0 |

Cómo lo haríamos en Zazu:
- **ntfy en Spirit** como servicio de systemd en `127.0.0.1:2586`, con `deny-all`, el usuario `fran` con permiso `zazu-*:rw` y un token guardado en un archivo con permisos 600 bajo `~/.config`. Se publica por cloudflared o por Tailscale, y Fran instala la app ntfy. Esfuerzo: **1-2 h**.
- **`avisar(titulo, texto, click=None, prio=3, seq=None)`** con `urllib`, en un `pagina-web/ntfy.py` nuevo. Ojo: el `avisos.py` que ya existe es el del vigía.
  - Se llama al final de `crear_peticion` (`pagina-web/movil.py`) con `X-Sequence-Id` igual al id de la petición. Al resolverla, un `PUT …/clear` quita el aviso.
  - Los temporizadores usan `curl`.
  - El aviso lleva solo un texto genérico, porque ntfy lo guarda 12 h en disco.
  - Esfuerzo: **~1 h**.
- **Después, un receptor UnifiedPush en `app-android`**, sin librerías: un `Push.java` nuevo y el manifiesto, unas 80 líneas.
  - Llega un mensaje vacío que solo dice «sondea ya», y la app llama a `Peticiones.sondear()` y pide el detalle al hub con su token.
  - El trabajo de 15 min se queda como respaldo.
  - Esfuerzo: **~1 día** con la prueba en el S25.
- **No copiar el servicio de ntfy-android dentro de la app.** Son más de 600 líneas y añadiría una segunda notificación fija.

**Mo2 · Compartir hacia Zazu y «Preguntar a Zazu»**

| Proyecto | Archivo clave | Patrón | Licencia |
|---|---|---|---|
| AnythingLLM Mobile | [AndroidManifest.xml](https://github.com/Mintplex-Labs/anythingllm-mobile/blob/main/android/app/src/main/AndroidManifest.xml#L150-L165) y [QuickContextActivity.kt](https://github.com/Mintplex-Labs/anythingllm-mobile/blob/main/android/app/src/main/java/com/anythingllm/quickcontext/QuickContextActivity.kt) | Para `PROCESS_TEXT` usa una actividad transparente en su propia tarea, que lee `EXTRA_PROCESS_TEXT`. No devuelve nada a la app de origen; copia el resultado al portapapeles | GPL-3.0: solo la idea |
| AnythingLLM Mobile | [SharedContentModule.kt](https://github.com/Mintplex-Labs/anythingllm-mobile/blob/main/android/app/src/main/java/com/anythingllm/sharedcontent/SharedContentModule.kt) (`extractItems`, `copyToShared`) | Copia cada `content://` enseguida a `cacheDir/shared/<uuid>/`, porque el permiso caduca. Saca nombre y tamaño con `OpenableColumns` y el tipo con `resolver.getType`. Ignora los intents con `FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY` y, después de usar uno, lo cambia por `MAIN` | GPL-3.0: solo la idea |
| Home Assistant Android | [share/ShareActivity.kt](https://github.com/home-assistant/android/blob/main/app/src/main/kotlin/io/homeassistant/companion/android/share/ShareActivity.kt) | Solo recibe `text/*`. Distingue un enlace de un texto y apunta qué app lo compartió (`getReferrer`) | Apache-2.0 |

Cómo lo haríamos en Zazu:
- **Texto seleccionado:**
  - En `app-android/app/src/main/AndroidManifest.xml`, un `<activity-alias android:name=".PreguntarAZazu">` con el filtro `PROCESS_TEXT`.
  - En `MainActivity.java`, `cargar()` y `onNewIntent` leen `EXTRA_PROCESS_TEXT` y reutilizan el `?text=` que ya existe.
  - Esfuerzo: **1-2 h**.
- **Archivos:**
  - Un segundo filtro `SEND`/`SEND_MULTIPLE` para imágenes, audio, vídeo y PDF.
  - Copiar cada archivo a `getCacheDir()/compartido/`, subirlo con `Copia.abrir` a `/api/movil/subir` (ya existe en `server.py`) y abrir `BASE/?adjunto=<ruta>`.
  - Esfuerzo: **½ día**.
- **Posible fallo, sin probar:** reabrir la app desde Recientes puede repetir el `?text=`. Se arregla comprobando `LAUNCHED_FROM_HISTORY` y haciendo `setIntent(MAIN)` después de usar el intent. Esfuerzo: **minutos**.

**P1 · «Qué ha salido de Spirit»**

| Proyecto | Archivo clave | Patrón | Licencia |
|---|---|---|---|
| litellm | [types/utils.py](https://github.com/BerriAI/litellm/blob/main/litellm/types/utils.py) (`StandardLoggingPayload`) y [redact_messages.py](https://github.com/BerriAI/litellm/blob/main/litellm/litellm_core_utils/redact_messages.py) | Guarda una fila por llamada con modelo, proveedor, tokens, coste, duración y estado. Cambia el contenido por `redacted-by-litellm` y solo guarda los prompts si se activa. Cuenta lo tachado por tipo (`masked_entity_count`) | MIT |
| Open WebUI | [utils/audit.py](https://github.com/open-webui/open-webui/blob/main/backend/open_webui/utils/audit.py) | Niveles `NONE`, `METADATA`, `REQUEST` y `REQUEST_RESPONSE`. Por defecto `NONE`, y las rutas de chat quedan fuera | Open WebUI License: solo la idea |
| Hermes (ya en Spirit) | `~/.hermes/hermes-agent/agent/turn_response_intake.py` (evento `post_api_request`) | Lanza un evento por cada llamada con `session_id`, `platform`, `model`, `provider`, `base_url`, la duración y `usage` | Ya instalado |

Cómo lo haríamos en Zazu:
- **Un plugin `hermes/plugins/salidas/__init__.py`** que registre `post_api_request` y guarde una fila en la tabla `salida` de `aprendizaje/datos/almacen.db`: fecha, sesión, motivo (`platform`), modelo, proveedor, host, número de mensajes, tokens y duración.
  - **Nunca el contenido:** el nivel `METADATA` queda fijo.
  - Opcional: en `pre_api_request`, pasar `detectar()` y guardar solo el recuento por tipo.
  - Esfuerzo: **2-3 h**.
- **`/api/salidas`** en `pagina-web/server.py`, que agrupe por día y proveedor, y una pestaña en `pagina-web/web/`. Esfuerzo: **½ día**.
- **Lo que llama a la IA fuera de Hermes** (`reflexion.py`, `hechos.py`, `bandeja/llm.py`) apunta en la misma tabla con una función común. Esfuerzo: **2-3 h**.

**Piezas que podemos reutilizar tal cual**
- Validadores de DNI/NIE (mod 23) y formatos de IBAN por país de **Presidio**: MIT, **compatible** si se conserva el aviso de copyright.
- Reglas de `patterns.json` de **litellm** (claves `AKIA…`, claves de API genéricas): MIT, **compatible** (no usar nada de `enterprise/`).
- Reglas del prompt de extracción de **mem0** y fases de `reflection.md` de **letta-code**: Apache-2.0, **compatible**. Hay que conservar el aviso y decir qué se cambió.
- `recognition_service.xml` (v31, con `selectableAsDefault=false`) y la sesión de asistente de **Home Assistant Android**, para Mo4: Apache-2.0, **compatible** con atribución y NOTICE.
- **ntfy** (servidor y app) y la especificación **UnifiedPush**: Apache-2.0. ntfy se usa como programa, sin meterlo en el código, y el receptor se escribe a mano.
- Cola `write_approval` de **Hermes** y plugin `memory-review` (MIT): ya instalados.
- **No reutilizar código** de Khoj (AGPL-3.0), AnythingLLM Mobile (GPL-3.0) ni Open WebUI (licencia con cláusula de marca). De ellos solo se toman ideas.

### 6. Fuentes

**Agentes**
- https://www.lindy.ai
- https://lindy.ai/pricing
- https://docs.lindy.ai/
- https://docs.lindy.ai/teammate/memory
- https://docs.lindy.ai/features/imessage-sms
- https://docs.lindy.ai/resources/security
- https://wf.lindy.ai/blog/lindy-assistant-launch
- https://www.vellum.ai/blog/best-lindy-ai-alternatives-2026
- https://rywalker.com/research/lindy
- https://new.computer
- https://techcrunch.com/2025/09/05/personalized-ai-companion-app-dot-is-shutting-down
- https://notes.andymatuschak.org/zBmgU9c2rjvApZvTa68YfAr
- https://justuseapp.com/en/app/6450016041/dot-living-history/reviews
- https://www.woshipm.com/evaluating/5941252.html
- https://tooldirectory.ai/tools/dot-new-computer
- https://docs.trymartin.com/
- https://www.eesel.ai/blog/martin-ai-review
- https://www.eesel.ai/blog/martin-ai-alternatives
- https://aiagentrank.io/blog/martin-ai-review-2026
- https://www.producthunt.com/p/martin/martin-2
- https://ai.g2.com/marketplace/tools/martin-martin
- https://www.ohai.ai/how-it-works/
- https://www.ohai.ai/privacy-policy/
- https://en.wikipedia.org/wiki/Ohai.ai
- https://fortune.com/2024/02/02/ohai-ai-care-personal-assistant-organizer/
- https://apps.apple.com/us/app/id6477802468
- https://poke.com
- https://poke.com/privacy
- https://rywalker.com/research/poke
- https://startupfortune.com/apple-gives-poke-a-rare-lane-into-imessage-for-ai-agents/
- https://blog.saner.ai/poke-reviews/
- https://dealroom.co/companies/poke/

**Memoria**
- https://9to5mac.com/2025/12/05/rewind-limitless-meta-acquisition/
- https://techinformed.com/meta-acquires-limitless-pendant-users-moved-to-free-unlimited-plan/
- https://techcrunch.com/2024/04/17/a16z-backed-rewind-pivots-to-build-ai-powered-pendant-to-record-your-conversations/
- https://limitless.ai/privacy
- https://help.limitless.ai/en/articles/9130680-privacy-with-limitless
- https://help.limitless.ai/en/articles/9124757-pendant-faq
- https://9to5mac.com/2022/11/02/rewind-ai-records-everything-you-do-mac/
- https://appleinsider.com/articles/22/11/01/rewind-app-wants-your-mac-to-record-every-moment-of-your-life
- https://www.yankodesign.com/2025/07/16/the-limitless-ai-pendant-feels-like-spiritual-predecessor-to-the-inevitable-openai-wearable-device/amp/
- https://techcrunch.com/2026/10/15/amazons-bee-launches-two-new-personal-ai-devices-starting-at-75/
- https://www.aboutamazon.com/news/devices/bee-private-compute-data-protection
- https://docs.bee.computer/
- https://github.com/bee-computer/bee-cli
- https://vice.com/en/article/this-ai-memory-device-records-your-life-and-gets-most-of-it-wrong
- https://twit.tv/posts/tech/future-personal-ai-inside-beecomputers-always-digital-memory-device
- https://www.consumeraffairs.com/news/amazon-acquires-a-wearable-company-whose-product-is-always-listening-072425.html
- https://geekwire.com/2026/amazons-new-ai-devices-can-listen-to-conversations-and-suggest-things-to-buy-if-you-opt-in
- https://blog.pebblous.ai/blog/amazon-bee-audio-deleted-transcript-kept/en/
- https://the-gadgeteer.com/2026/07/31/friend-ai-pendant-voice-wearable-249-price/
- https://dnyuz.com/2026/07/30/the-new-friend-ai-pendant-can-now-talk-back-to-you/
- https://fortune.com/2025/10/03/friend-ai-necklace-review-avi-schiffmann/
- https://getcoai.com/news/wired-tested-the-129-ai-necklace-that-alienates-users-and-fails-technically
- https://tomsguide.com/ai/friend-is-a-dollar99-ai-necklace-that-wants-to-help-you-remake-the-movie-her
- https://www.plaud.ai/pages/plaud-intelligence
- https://global.plaud.ai/blogs/news/plaudai-achieves-full-gdpr-compliance-reinforcing-commitment-to-global-data-privacy-standards
- https://nextpit.com/plaud-notepin-review
- https://cyberguy.com/ai/ai-wearable-promises-to-help-you-remember-everything-but-is-your-privacy-safe/
- https://laxis.com/blog/plaud-note-pro/
- https://uk.plaud.ai/products/plaud-ai-unlimited-plan
- https://help.openai.com/en/articles/8590148-memory-faq
- https://help.openai.com/en/articles/11146739-how-does-reference-saved-memories-work
- https://www.thurrott.com/a-i/337052/openai-is-improving-how-chatgpts-memory-works
- https://www.digitalcitizen.life/chatgpts-dreaming-feature-makes-its-memory-more-useful-and-easier-to-manage/
- https://tomsguide.com/ai/chatgpts-new-memory-builds-a-profile-of-you-on-its-own-and-openai-admits-you-cant-see-all-of-it
- https://releases.sh/release/rel_9SyecKQN7LP70s8pMzJzj-memory-now-updates-automatically-plus-pro-get-2x-capacity
- https://openai.com/blog/memory-and-new-controls-for-chatgpt
- https://letsdatascience.com/news/openai-upgrades-chatgpt-memory-architecture-for-fresher-pers-b26b51d5
- https://support.claude.com/en/articles/11817273-use-claudes-chat-search-and-memory-to-build-on-previous-context

**Privados y locales**
- https://proton.me/support/lumo-privacy
- https://proton.me/blog/lumo-2
- https://macrumors.com/2026/06/30/proton-lumo-version-2-new-features
- https://betanews.com/2026/01/13/proton-updates-its-lumo-ai-tool-with-new-projects-feature/
- https://alternativeto.net/news/2026/6/proton-launches-lumo-2-0-with-image-generation-advanced-reasoning-and-improved-memory/
- https://security.apple.com/blog/private-cloud-compute/
- https://support.apple.com/guide/mac-help/mchlfc0d4779
- https://www.apple.com/legal/privacy/data/en/intelligence-engine/
- https://www.apple.com/newsroom/2026/06/apple-introduces-siri-ai-a-profoundly-more-capable-and-personal-assistant/
- https://www.apple.com/newsroom/2026/06/due-to-dma-siri-ai-delayed-in-eu-for-ios-27-and-ipados-27/
- https://mer.vin/2026/06/apple-wwdc26-siri-ai-and-gemini-backed-foundation-models-on-device-and-private-cloud-compute/
- https://www.jan.ai/
- https://github.com/janhq/jan
- https://docs.jan.ai/agent
- https://docs.jan.ai/agent/memory
- https://docs.jan.ai/mobile
- https://flathub.org/oc/apps/ai.jan.Jan
- https://docs.ollama.com/
- https://ollama.com/pricing
- https://github.com/ollama/ollama
- https://docs.openwebui.com/features/
- https://docs.openwebui.com/features/chat-conversations/memory/
- https://docs.openwebui.com/ecosystem/computer/phone-and-remote/phone-app/
- https://docs.openwebui.com/license/
- https://github.com/cogwheel0/conduit
- https://lmstudio.ai/
- https://lmstudio.ai/docs/app
- https://lmstudio.ai/app-privacy
- https://tailscale.com/blog/lm-link-remote-llm-access
- https://letsdatascience.com/news/lm-studio-adds-iphone-to-mac-link-for-local-llms-97175e03
- https://build.nvidia.com/spark/lm-studio/overview
- https://docs.anythingllm.com/
- https://docs.anythingllm.com/features/memories
- https://docs.anythingllm.com/mobile/overview
- https://anythingllm.com/mobile
- https://www.promptquorum.com/power-local-llm/anythingllm-mobile-review
- https://github.com/khoj-ai/khoj
- https://docs.khoj.dev/
- https://docs.khoj.dev/features/automations
- https://docs.khoj.dev/clients/whatsapp
- https://app.khoj.dev/
- https://www.mintlify.com/khoj-ai/khoj/privacy-security
- https://railway.com/deploy/khoj

**Móvil y casa**
- https://www.home-assistant.io/voice_control/voice_remote_local_assistant/
- https://www.home-assistant.io/blog/2025/02/13/voice-chapter-9-speech-to-phrase/
- https://www.home-assistant.io/voice_control/assist_create_open_ai_personality/
- https://home-assistant.io/integrations/ollama
- https://www.home-assistant.io/integrations/wyoming/
- https://pypi.org/project/wyoming/
- https://home-assistant.io/voice_control/android/
- https://www.home-assistant.io/blog/2025/07/23/companion-app-for-android/
- https://github.com/home-assistant/core/issues/162768
- https://thepihut.com/products/home-assistant-voice-preview-edition
- https://forums.developer.nvidia.com/t/jetson-ai-lab-home-assistant-integration/288225
- https://support.google.com/gemini/answer/15235441
- https://support.google.com/gemini/answer/13695044?hl=en
- https://support.google.com/gemini/answer/13278892?hl=en
- https://9to5google.com/2025/08/13/gemini-personal-context/
- https://9to5google.com/2026/02/26/gemini-past-chats-free/
- https://www.androidauthority.com/p-3679235/
- https://www.techradar.com/ai-platforms-assistants/gemini/gemini-is-about-to-remember-everything-unless-you-tell-it-not-to
- https://9to5google.com/2026/02/25/gemini-automation-android/
- https://9to5google.com/2026/03/12/gemini-android-app-automation-galaxy-s26-rollout/
- https://www.neowin.net/news/googles-new-gemini-agent-on-android-can-now-use-3rd-party-apps-to-run-errands-for-you/
- https://blog.google/technology/ai/google-private-ai-compute/
- https://9to5google.com/2025/11/11/google-private-ai-compute-pixel/
- https://cyberinsider.com/google-debuts-private-ai-compute-to-bridge-cloud-power-and-local-privacy/
- https://www.kaspersky.com/blog/how-to-disable-gemini-on-android/53771/
- https://geotoolbox.ai/es/blog/precio-gemini
- https://www.digitalcitizen.life/how-to-connect-apps-to-gemini-a-complete-setup-guide/
- https://news.samsung.com/uk/your-privacy-secured-how-galaxy-ai-protects-privacy-with-samsung-knox-vault
- https://news.samsung.com/au/your-privacy-secured-how-knox-vault-protects-you-in-the-era-of-ai
- https://www.androidauthority.com/samsung-galaxy-ai-on-device-only-3488445
- https://9to5google.com/2025/02/20/how-to-turn-on-galaxy-ai-on-device-processing/
- https://getcoai.com/news/samsungs-hidden-setting-disables-all-cloud-ai-features
- https://www.tomsguide.com/phones/you-can-turn-off-galaxy-ai-on-your-samsung-phone-heres-how
- https://gadgets.beebom.com/stories/i-use-on-device-ai-setting-on-samsung-phones-google-should-copy-it
- https://www.androidauthority.com/samsung-galaxy-ai-features-free-3632510
- https://www.phonearena.com/news/galaxy-ai-policy-changes_id177350
- https://gigazine.net/gsc_news/en/20260223-samsung-add-perplexity-galaxy-ai
- https://androidauthority.com/samsung-bixby-renew-perplexity-ai-3628037/
- https://m.gsmarena.com/samsung_galaxy_s26_plus-review-2941p4.php
- https://support.microsoft.com/en-us/windows/retrace-your-steps-with-recall-aa03f8a0-a78b-4b3e-b0a1-2eb8ac48701c
- https://blogs.windows.com/windowsexperience/2024/09/27/update-on-recall-security-and-privacy-architecture/
- https://redmondmag.com/Articles/2024/09/27/Windows-Recall-Security-Guardrails.aspx
- https://blogs.windows.com/windows-insider/2025/11/17/copilot-on-windows-copilot-actions-begins-rolling-out-to-windows-insiders/
- https://blogs.windows.com/windowsexperience/2025/10/16/securing-ai-agents-on-windows/
- https://support.microsoft.com/en-us/windows/ai/ai-features/experimental-agentic-features
- https://learn.microsoft.com/en-au/windows/security/book/operating-system-agentic-security
- https://www.infoq.com/news/2025/11/microsoft-copilot-fall-release/
- https://venturebeat.com/ai/microsoft-copilot-gets-12-big-updates-for-fall-including-new-ai-assistant
- https://searchenginejournal.com/microsoft-updates-copilot-with-memory-search-connectors-more/559129
- https://tech.yahoo.com/articles/microsofts-copilot-vision-lands-android-211723113.html
- https://www.thurrott.com/?p=327639
- https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt
- https://help-lb.openai.com/en/articles/10291617-tasks-in-chatgpt
- https://help.openai.com/en/articles/11752874-chatgpt-agent
- https://openai.com/index/introducing-chatgpt-pulse/
- https://www.tomsguide.com/ai/chatgpt-pulse-is-here-now-ai-starts-the-chat-and-curates-your-feed
- https://yourstory.com/ai-story/openai-chatgpt-pulse-pro-daily-briefings
- https://www.cometapi.com/chatgpt-pricing-2026-free-vs-go-vs-plus-vs-pro/
- https://pricepertoken.com/subscriptions/chatgpt

**Piezas reutilizables (licencias comprobadas el 22-10-2026 con la API de GitHub y Hugging Face)**
- https://docs.ntfy.sh/subscribe/phone/ (sin Firebase con servidores propios)
- https://github.com/binwiederhier/ntfy (Apache-2.0 / GPLv2)
- https://github.com/asg017/sqlite-vec (MIT / Apache-2.0, previa a la 1.0)
- https://github.com/rhasspy/wyoming-faster-whisper (MIT)
- https://github.com/rhasspy/piper (MIT, archivado el 6-10-2025)
- https://github.com/OHF-Voice/piper1-gpl (GPL-3.0)
- https://huggingface.co/hexgrad/Kokoro-82M (Apache-2.0)
- https://github.com/kahrendt/microWakeWord (Apache-2.0)
- https://github.com/dscripka/openWakeWord (código Apache-2.0; modelos CC BY-NC-SA 4.0)
- https://developer.android.com/reference/android/content/Intent#ACTION_PROCESS_TEXT
- https://developer.android.com/reference/android/app/role/RoleManager#ROLE_ASSISTANT

**Repos leídos (código, 22-10-2026)**
- https://github.com/mem0ai/mem0 (Apache-2.0)
- https://github.com/letta-ai/letta/tree/archive (Apache-2.0)
- https://github.com/letta-ai/letta-code (Apache-2.0)
- https://github.com/open-webui/open-webui (Open WebUI License)
- https://github.com/microsoft/presidio (MIT)
- https://github.com/BerriAI/litellm (MIT, salvo `enterprise/`)
- https://github.com/binwiederhier/ntfy-android (Apache-2.0)
- https://github.com/UnifiedPush/specifications (Apache-2.0)
- https://github.com/UnifiedPush/android-connector (Apache-2.0)
- https://github.com/home-assistant/android (Apache-2.0)
- https://github.com/Mintplex-Labs/anythingllm-mobile (GPL-3.0)

<!-- verificación:
CÓDIGO (Spirit, 22-10-2026):
- CORREGIDO: el disco NO está cifrado (lsblk: nvme0n1p2 ext4 en /, sin crypt). P4 pasa de «sin confirmar» a «no cifrado» y su prioridad sube a media-alta. Se añade al resumen y al orden.
- CORREGIDO: Hermes ya trae session_search (activo en config.yaml; FTS5 sobre ~/.hermes/state.db). Fila de Claude: «No» → «En parte». M4: quitado el «sin confirmar» y el plan de crear un índice de sesiones; esfuerzo bajo-medio.
- CORREGIDO: P1. Hermes ya guarda uso por sesión y modelo en la tabla session_model_usage (state.db). Se quita el «sin confirmar» de ~/.hermes/state/.
- CORREGIDO: Dot «Sí» → «En parte». fran-hub es un diario de turnos entre superficies, no un historial de vida.
- PRECISADO: zazu-rapido.py solo cubre /hoy /manana /semana /tareas como quick_command; «¿qué tengo hoy?» ya está.
- PRECISADO: la app recibe ACTION_SEND solo con text/plain (MainActivity.java). La recogida cada 15 min es un JobScheduler (Copia.java, CopiaJob.java).
- CONFIRMADO: hechos.py (máx. 3 hechos, nunca escribe MEMORY/USER); tabla feedback en almacen.db; .bak de la memoria; homeassistant en plugins.disabled; memory-review instalado y no habilitado; Kokoro activo vía piper-local → tts-kokoro.sh mientras voz/README dice «sin activar»; Whisper small local; Ollama qwen3:4b en custom_providers; skills modelo-local-conviene y memoria-higiene; 95 SKILL.md; platform_toolsets.cron: []; navegador solo en el perfil tecnico; timers 04:10 y 04:25; resumen-hoy, zazu-vigia; SESSION_DAYS = 14; «Cuatro promesas» y «Nada para terceros» en seguridad.html; ruta /privacidad; 113 casos en hermes/README.md; copia diaria cifrada; Tailscale activo; ~/Cerebro existe.
WEB:
- CORREGIDO: «Dreaming V3». La fuente releases.sh no lo menciona. Queda «Dreaming» (junio de 2026) con fuentes digitalcitizen.life y tomsguide.
- CORREGIDO: el informe de Apple no está en el blog de PCC; se cita support.apple.com (mchlfc0d4779). Solo lleva metadatos.
- CORREGIDO: Pulse «3 a 5 tarjetas» → 5-10 según la prensa (sin confirmar). El cierre es «That's all for today».
- CORREGIDO: la barra de texto seleccionado de AnythingLLM está en docs.anythingllm.com/mobile/overview, no en anythingllm.com/mobile. El enlace de Mo2 se cambia.
- CORREGIDO: Voice PE «59 €» → 59 $ (sin reconfirmar); The Pi Hut lo lista a 55,80 £ y agotado.
- CORREGIDO: la fuente del interruptor de Samsung pasa a tomsguide (androidauthority da 403).
- CORREGIDO: Martin. «Sin preguntar» no consta; la documentación dice «on your behalf» y no dice si confirma.
- CORREGIDO: Limitless. Fechas exactas: fin el 5-12-2025 en la UE, el Reino Unido y otros; borrado tras el 19-12-2025; Rewind dejó de grabar.
- CORREGIDO: Dot y Friend «no funcionaron» se suaviza.
- MARCADO «sin confirmar»: Samsung borra al apagar; KEEP y motor de datos personales; deslizar los facts de Bee; citas de Plaud; Open WebUI avisa solo con la app abierta; Gemini «nunca paga sin ti»; Rewind 1 semana-siempre; número de integraciones de Lindy; resumen diario de Lindy; scheduled tasks de ChatGPT (403); 4 herramientas de HA; lista de palabras de Voice PE.
- CONFIRMADO: Lindy (Preview/Raw/History, «Every save is a version», .memory/.skills, iMessage+SMS+llamadas, sin app, SOC 2, no vende ni entrena, «You review, and you send»); Claude (categorías nunca guardadas, temas sensibles opcionales, borrar un chat no borra memorias, citas, incógnito); AnythingLLM (Observador hasta 3 hechos con confianza, Reflector, 3 h, aviso al proveedor, MIT); ntfy (sin Firebase con servidores propios, servicio en primer plano); Lumo (memoria, acceso cero, sin registros, modelos de código abierto, Europa); Dot 5-10-2025, exportación, solo iOS; Bee (audio descartado, AWS Nitro, 14 días gratis, Alexa+, Pro 11,99 $); Friend 30 días; Poke comprada por Cognition (23-7-2026) y entrena salvo Maximum Privacy; Ohai revisión humana y entrenamiento; Recall (filtro por defecto, TPM, Hello, autorización que caduca); Gemini 72 h y lectura de notificaciones de WhatsApp; HA (local primero, historial compartido, <25 entidades, Companion con botón de encendido y pantalla bloqueada); Jan AGENTS.md/memoria; Open WebUI (herramientas de memoria, aviso de modelos pequeños, licencia v0.6.6 ≤50 usuarios/30 días, compartir en PWA); Conduit GPL-3.0 con Hermes y aprobación; LM Studio; Piper archivado el 6-10-2025 → piper1-gpl GPL-3.0; licencias por API (microWakeWord Apache-2.0, wyoming-faster-whisper MIT, ollama MIT, ntfy, Kokoro apache-2.0, openWakeWord código Apache y modelos CC BY-NC-SA).
ENLACES:
- QUITADO: geekflare.com/news/samsung-rolls-out-new-on-device-ai-privacy-protections/ (404).
- QUITADO: support.claude.com/.../11817273-manage-memory (mismo id que el otro artículo; duplicado).
- AÑADIDOS: support.apple.com mchlfc0d4779, digitalcitizen (Dreaming), tomsguide (Dreaming), 9to5google (Samsung en el dispositivo).
- Con 403 por bloqueo de bots, se mantienen: androidauthority, openai.com, help.openai.com.
-->

