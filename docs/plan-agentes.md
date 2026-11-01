# Plan: los agentes de un solo oficio (acordado el 2026-10-12)

Fran pidió montarlos todos; se montaron la noche del 2026-10-12 con la misma receta, y cada pieza está explicada en [`aprender/agentes.md`](aprender/agentes.md) para repasarla juntos. Receta: la de [`aprender/primer-agente-viajes.md`](aprender/primer-agente-viajes.md) (perfil clonado de `charla`, SOUL con trabajo + límite, una habilidad con pasos y formato, solo las herramientas y claves necesarias, hook de permisos, prueba medida). Cada uno aparece solo en la app como chip del Chat.

| Orden | Agente | Perfil | Qué hace | Límite | Herramientas | Modelo | Lo que ya tenemos | Estado |
|---|---|---|---|---|---|---|---|---|
| 1 | **Empleo** | `empleo` | Adapta CV y carta a una oferta con tu tono; simulacro de entrevista; qué preguntar | No envía ni se inscribe: tú envías | web, navegador (leer ofertas), lectura de `40 Compartido/Empleo` (CV, cartas) | Sonnet 5.5 | CV y 3 cartas en el Cerebro; vigía de empleo y de entrevistas; tablero Candidaturas | **Montado** 2026-10-12 |
| 2 | **Profe del teórico** | `teorico` | 10 preguntas tipo test al día (DGT), explica fallos, lleva la racha hasta el examen | Solo estudia | ninguna (o web para la normativa) | Haiku 5.5 | Rutina 19:30 `estudio-teorico.sh` (aviso sin IA) y la cita de la DGT del 13 oct | **Montado** 2026-10-12 |
| 3 | **Comidas y compra** | `comidas` | Menú de la semana y lista de la compra en la Casa con Nuria | No compra | `casa.py` (lista y tareas), memoria de gustos | Haiku 5.5 | La Casa (`casa.py`, calendario Casa, skill `casa-compartida`) | **Montado** 2026-10-12 |
| 4 | **Dinero** | `dinero` | Revisión mensual de gastos y suscripciones; detecta subidas y duplicados; redacta bajas/reclamaciones | Nunca paga ni cancela | lectura de la base del vigía (`zv gastos`, `zv suscripciones`) | Haiku 5.5 | Vigía de gastos y suscripciones (aplicado), pantalla Dinero | **Montado** 2026-10-12 |
| 5 | **Papeles** | `papeles` | Qué caduca (DNI, ITV, seguro), trámites pendientes (Cl@ve) y la lista para cada gestión | No rellena formularios oficiales | lectura del archivador y de `40 Compartido/Importante` | Haiku 5.5 | Archivador (sombra), Índice de papeles | **Montado** 2026-10-12 (solo nombres y fechas, con filtro de privacidad) |
| 6 | **Compras** | `compras` | Compara precios y opiniones; vigila un precio hasta que baje | No compra | web, navegador | Sonnet 5.5 | Navegador local activo | **Montado** 2026-10-12 |
| 7 | **Salud** | `salud` | Citas, recordatorio de medicación, qué contarle al médico | No decide nada médico | agenda (lectura), memoria propia | Haiku 5.5 | Agenda del vigía | **Montado** 2026-10-12 (sin Google ni WhatsApp) |
| 8 | **Profe de Spirit** | `profe` | Explica tu propio código paso a paso y propone el siguiente ejercicio | Solo lee `~/Spirit` | `file` (solo lectura, ruta acotada) | Sonnet 5.5 | Spirit y `docs/aprender` | **Montado** 2026-10-12 |
| 9 | **Casa** | `casa` | Luces, enchufes, altavoz, recordatorios por lugar | Nada que abra puertas | Home Assistant | Haiku 5.5 | Plugin `homeassistant` sin configurar | Pendiente: instalar Home Assistant primero |

Reglas comunes
- Un perfil por agente; su `.env` solo con la clave de Anthropic (Regla de Dos: el que lee contenido ajeno no tiene acciones externas ni datos privados fuera de lo suyo).
- Cada uno con su `SKILL.md` y una prueba medida (`--usage-file`) anotada en su guía.
- Al terminar cada uno: nombre y pista en `pagina-web/web/src/data.ts` (`PROFILE_NAMES`, `PROFILE_HINTS`), guía en `docs/aprender/`, nota en el Cerebro.
