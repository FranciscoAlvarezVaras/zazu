# Mejoras del mercado que podemos añadir (investigadas el 2026-10-11)

Cómo leerlo: **Verificado** = lo comprobé yo en la fuente oficial; **Pendiente de probar** = lo dice una fuente pero hay que probarlo en este servidor.

## Lo mejor por valor / esfuerzo

| # | Mejora | Qué aporta a Fran | Esfuerzo | Estado |
|---|---|---|---|---|
| 1 ✅ 2026-10-12 | **Pasar rutinas y clasificación a Claude Haiku 5.5** (hoy todo va con Haiku 4.5) | Precio en la documentación oficial: Haiku 4.5 = 1 $ entrada / 5 $ salida por millón de tokens; **Haiku 5.5 = 0,10 $ / 0,50 $** (hasta 100 000 tokens de prompt). Unas 10 veces más barato. Sonnet 5.5 = 2 $ / 10 $. | Bajo (cambiar el modelo y probar con casos reales) | Precio **verificado**; calidad **pendiente de probar** |
| 2 ✅ 2026-10-12 | **Aprobaciones más fiables**: la «aprobación inteligente» usa un modelo gratuito de otro proveedor que hoy dio «sin capacidad» (429) y entonces te pregunta a ti | Menos avisos cancelados; coste casi cero con Haiku 5.5 | Bajo | Hallazgo propio (ver `revision-2026-10-11.md`) |
| 3 ✅ 2026-10-12 (rutinas sin herramientas) | **Regla de Dos** en el perfil que lee correo/web: nunca a la vez contenido no fiable + datos privados + acciones externas | La defensa más práctica contra inyección de prompts; complementa el hook | Bajo-medio | Pendiente |
| 4 ✅ 2026-10-12 | **Mini-evals de regresión**: 20 casos de oro (correo → categoría, gasto → importe) tras cada actualización o cambio de modelo | Detectan roturas por céntimos | Bajo-medio | Pendiente |
| 5 ✅ 2026-10-12 | **Protocolo de actualización de Hermes**: copia de `state.db`, versión fijada, prueba (`spirit probar`), vuelta atrás. Ya hay actualización automática diaria | Una actualización mala no te deja sin asistente | Bajo | Pendiente |
| 6 ✅ 2026-10-12 | **Resumen de costes semanal** sin IA (`hermes usage` + registros) por WhatsApp | Ver el gasto por modelo | Bajo | Pendiente |
| 7 | **Memoria bajo git + consolidación nocturna** (fusionar duplicados con Haiku; la memoria es Markdown, sin servicios nuevos) | Memoria ordenada y reversible | Bajo-medio | Pendiente |
| 8 | **Recordatorios por lugar** (geovallas de Home Assistant → webhook de Zazu: «al llegar al súper, la lista de la compra») | Contexto real, como los asistentes comerciales | Medio | Pendiente; datos de ubicación = solo local |
| 9 | **Voz: probar Parakeet TDT 0.6B v3** (25 idiomas, incluye español, ~680 MB, sin GPU) frente al reconocimiento actual con 20 notas de voz reales | Notas de voz más fiables | Medio | Sin cifras de error en español: probar |
| 10 | **Voz en casa**: Home Assistant Voice PE + Assist local para luces/enchufes | Controlar la casa por voz | Medio | Pendiente |
| 11 | **Modelo local pequeño** (Qwen3/Gemma 4, llama.cpp) solo para correo/gastos sensibles | Privacidad (no sale de casa), no ahorro | Medio | Ya hay `qwen3:4b` en Ollama para títulos y reescritura de memoria |
| 12 | **Banca solo lectura (PSD2)** para gastos y suscripciones | Quitaría trabajo manual | Alto | Muy nuevo y sin auditar: de momento exportar CSV al archivador |

## Otto One (myotto.ai) frente a lo que ya tienes — comprobado el 2026-10-11

Otto One es un mini-PC de 599–799 $ que ejecuta agentes en casa con modelos en la nube. Comparación pieza a pieza, verificada en este servidor:

| Lo que vende Otto | Aquí | Estado |
|---|---|---|
| Corre en tu casa, el modelo piensa en la nube | Geekom + Hermes + Claude | **Ya** |
| Navegador propio en tu máquina (el agente navega «como una persona», no como bot en la nube) | Hermes trae `agent-browser` 0.26 + Chromium 145 instalados y sanos (`hermes pm doctor`). Probado: `browser_exec` abrió una web desde el servidor. | **Activado en `tecnico`** (terminal y chat de la app) el 2026-10-11 con el «vale» de Fran; el hook pide permiso para iniciar sesión, rellenar, enviar, comprar o descargar |
| Plantillas de agentes (asistente personal, coordinador familiar, viajes…) | Perfiles de Hermes (`charla`, `escritor`, `investigador`, `tecnico`, invitadas) + SOUL + skills | **Ya** (guía: `aprender/construir-un-agente.md`) |
| 5–10 agentes a la vez | El gateway sirve 5 perfiles a la vez; las invitadas van aparte en jaula | **Ya** |
| «2000+ integraciones» | Google (gog), WhatsApp, Nextcloud, Obsidian, móvil (adb), Home Assistant (plugin), y catálogo MCP de Hermes con 65 servicios a una orden (`hermes mcp catalog`: Notion, Todoist, Stripe, PayPal, Dropbox, Linear…) | **Parcial**: menos «a un clic», pero lo que usas de verdad ya está |
| Chat cifrado de extremo a extremo | HTTPS por Cloudflare + sesión con login + guardia anti-escáner. No es cifrado de extremo a extremo. | **Distinto** (suficiente para uso personal) |
| Inferencia sin retención de datos | Depende de la política de Anthropic para cuentas normales; no es «cero retención» garantizado | **No garantizado** |
| Credenciales guardadas en local | `~/.hermes/.env`, llavero de `gog`, vault del navegador de Hermes | **Ya** |
| Precio | 0 € (el servidor ya existe) frente a 599–799 $ + 15 $ envío | — |

Conclusión: no comprar. El navegador local del agente, lo único que faltaba, quedó activado en el perfil `tecnico` el 2026-10-11 con la puerta de permisos delante.

## Probado: Headroom (proxy de compresión de contexto), 2026-10-12
Instalado aislado y activo solo en el perfil `viajes`. Mismo plan de viaje: −27 % de tokens y −10 % de coste, sin perder calidad. Costó dos parches en el núcleo de Hermes (tu acceso es por suscripción OAuth y Hermes no la usa con proxies). Detalle y cómo quitarlo: `~/Spirit/experimentos/headroom/README.md`.

## Lo que NO recomiendo (de momento)
- **Servicios de memoria aparte (Mem0, Zep, Letta):** Hermes ya trae memoria y búsqueda de sesiones; añadir otro sistema es más cosas que mantener con 14 GB.
- **Langfuse/SigNoz autoalojados:** piden bases de datos pesadas; con `hermes usage` basta.
- **Doble modelo estilo CaMeL completo:** es investigación; la «Regla de Dos» da el 80 % del beneficio.
- **Agentes que se hablan entre sí, automatización de ratón y navegador con tus sesiones:** más coste y más superficie de ataque, y no resuelven nada pendiente.
- **Opus/Fable por defecto:** entre 20 y 100 veces más caros que Haiku 5.5. Solo para tareas difíciles puntuales.

## Incertidumbres (no verificadas)
- Si Hermes acepta un servidor de voz propio compatible con OpenAI, y el error de palabras de Parakeet en español.
- Topes de gasto nativos de Hermes (solo aparecen en tutoriales de terceros).
- Cómo conectar Home Assistant como agente conversacional de Hermes.
- El nombre exacto del modelo Haiku 5.5 en la API (comprobar en `platform.claude.com/docs/en/models/overview` antes de configurarlo).

Fuente principal de precios (oficial): https://platform.claude.com/docs/en/about-claude/pricing · releases de Hermes: https://github.com/NousResearch/hermes-agent/releases
