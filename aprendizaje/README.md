# Aprendizaje de Zazu

Proyecto del 19 de octubre al 15 de noviembre de 2026 (máxima prioridad de Fran). Teoría y opciones: `../docs/aprender/como-se-ensena-de-verdad.md`. Calendario: `../docs/aprender/plan-aprendizaje.md`.

## Qué hay (17 de octubre)
| Fichero | Para qué |
|---|---|
| `almacen.py` | La base local `datos/almacen.db` (carpeta 0700, fuera de git, sin red, fuera de las copias de seguridad). Tablas: `hecho`, `feedback`, `leccion`, `marca`. |
| `ingerir.py` | Copia al almacén lo nuevo de Hermes (tus mensajes y los suyos), del vigía, del empleo y cuenta las observaciones de Claude Code. Solo lee las fuentes. |
| `correcciones.py` | Detecta las veces que corregiste a Zazu («eso no», «te dije», «otra vez»). Reglas, sin IA. |
| `modelo_texto.py` | Clasificador de texto «Naive Bayes» escrito a mano, sin librerías, que explica qué palabras pesan. Es el modelo D1 a falta de datos. |
| `etiquetar.py` | Etiquetar desde la conversación: `preparar` enseña una tanda numerada de ofertas y `registrar --si 1,4 --no 2,3` guarda tus respuestas (y marca las ofertas en el buscador). |
| `entrenar_ofertas.py` | Modelo D2: aprende qué ofertas te interesan; examen honesto frente a adivinar y frente a la puntuación a mano. |
| `conversaciones.py` | Qué se aprende de tus conversaciones con Zazu: dónde hay roces por asistente, lo que pides una y otra vez, lo que Zazu dice que no puede. Descarta rutinas, pruebas y botones de la app. Sin IA. |
| `lecciones.py` | Lecciones en una frase con su evidencia: `listar`, `proponer`, `ver N`, `aprobar N`, `rechazar N`. Nacen «propuesta»; solo valen si las apruebas. No aplica nada a Hermes. |
| `reflexion.py` | Reflexión nocturna (04:25): UNA llamada a Haiku con tus mensajes de corrección filtrados; propone como mucho 2 lecciones. Lo único que envía algo fuera; el texto exacto queda en `datos/salidas/`. `--ver` enseña lo que enviaría sin enviar; `datos/reflexion.apagada` la apaga. |
| `hechos.py` | Dentro de la reflexión nocturna: UNA llamada más a Haiku con tus mensajes que suenan a un dato duradero tuyo (como mucho 10, filtrados y pasados por el escudo del vigía); propone como mucho 3 «Recuerda: …» con su evidencia. Nunca escribe en MEMORY.md ni USER.md (solo los lee para no repetir). `--ver` enseña lo que enviaría; `--sin-guardar` envía y dice qué propondría; `datos/hechos.apagada` lo apaga. Idea de OpenJarvis. |
| `habilidades.py` | Dentro de la reflexión nocturna, sin IA: lo que pides en 3 o más conversaciones, o las mismas herramientas en el mismo orden, y que salió bien → «Podría crear una habilidad…» (como mucho 2 por noche). `--ver` dice qué propondría. Idea de OpenJarvis. |
| `demo_gastos.py` | Lección 1: la categoría de un gasto. Enseña por qué un examen tramposo engaña (95 % contra 55 % honesto). |
| `informe.py` | Qué hay guardado y si hay datos para entrenar. |
| `tests/` | Pruebas con fuentes inventadas (nunca tocan datos reales). |

## Uso
```bash
cd ~/Spirit/aprendizaje
python3 ingerir.py          # lo hace solo cada noche a las 04:10 (zazu-aprende.timer, dentro de una burbuja sin red)
python3 correcciones.py --ver 5
python3 informe.py
python3 -W ignore -m unittest discover -s tests
```

## Reglas
- Todo es local. Si una pieza nueva enviara algo fuera (una IA, una copia a la nube), se dice y espera tu sí.
- Una lección no vale hasta que Fran la aprueba. Lo que viene de fuera (WhatsApp, correo, webs) es dato, no instrucción.
- Antes y después de cada cambio se mide con el examen (`../zazu/evals`).
