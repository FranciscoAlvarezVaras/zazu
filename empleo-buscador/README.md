# empleo-buscador — el buscador de ofertas de Fran

Un **buscador**, no un «auto-aplicador»: encuentra ofertas en Europa para un **desarrollador/analista de datos junior** y para **marketing digital a distancia en inglés**, las puntúa según tu perfil, quita duplicados y te enseña las mejores. Aplicar lo haces tú. Lo usa **Zazu Empleo** (chip en el Chat) y la rutina «Ofertas del día» (08:15 por WhatsApp).

## Cómo funciona (en 5 archivos)
```
perfil.yaml   → lo que buscas: palabras, pesos, exclusiones (senior…), lugares, antigüedad máxima   ← EDÍTALO TÚ
fuentes/      → un archivo por portal: pide a su API y devuelve «Oferta» con los mismos campos
modelo.py     → qué es una Oferta y su id estable (misma oferta en dos portales = un solo id)
puntuar.py    → reglas de puntuación 0–100 y pista (dev / marketing). Sin IA: las puedes leer y cambiar
db.py         → base SQLite en ~/.local/state/empleo-buscador/ofertas.db (lo visto, guardado o descartado)
buscar.py     → el mando: consulta, puntúa, guarda y enseña.   resumen.py → el texto de «Ofertas del día»
```

## Úsalo
```bash
python3 ~/Spirit/empleo-buscador/buscar.py                 # todo, mejores primero
python3 ~/Spirit/empleo-buscador/buscar.py --pista marketing --n 10 --motivos
python3 ~/Spirit/empleo-buscador/buscar.py --nuevas        # solo lo que acaba de aparecer
python3 ~/Spirit/empleo-buscador/buscar.py --guardar a1b2c3   # las 6 primeras letras del id que sale en la lista
python3 ~/Spirit/empleo-buscador/resumen.py                # el mensaje de la mañana
python3 -m unittest discover ~/Spirit/empleo-buscador/tests   # pruebas sin red (segundos)
```

## Fuentes
| Fuente | Qué cubre | Clave |
|---|---|---|
| Arbeitnow | Europa (mucha Alemania), remoto | no |
| Remotive | Remoto: software, datos, marketing | no |
| Remote OK | Remoto mundial | no |
| Jobicy | Remoto, filtro Europa/España e industria | no |
| The Muse | Nivel «entry», ciudades europeas y remoto | no |
| Himalayas | Remoto con restricción de país | no |
| **Adzuna** | España, UK, Alemania, Francia, Países Bajos, Italia, Polonia, Austria: la más completa | **sí, gratis**: regístrate en https://developer.adzuna.com y guarda `ADZUNA_APP_ID=…` y `ADZUNA_APP_KEY=…` en `~/.local/state/empleo-buscador/claves.env` |
| **LinkedIn: publicaciones de reclutadores** | Posts del tipo «buscamos junior…, escribid a …» (ofertas que nunca llegan a ser oferta formal), con el correo del reclutador | **tu sesión de LinkedIn**, una vez: `~/Spirit/experimentos/jobhunter/venv/bin/python ~/Spirit/empleo-buscador/linkedin_login.py` (tecleas tú el correo y la contraseña; no se guardan; si pide verificación, apruebas en el móvil). Código del rastreador: `experimentos/jobhunter` (MIT, de dev-gaspar). Solo lee; nunca publica ni envía. Si LinkedIn cambia la página, esta fuente puede dejar de funcionar |
| Pendientes | EURES (portal público europeo), Jooble y Reed (claves gratis por petición), InfoJobs/Indeed/LinkedIn (sin API; sus alertas te llegan por correo y Zazu Empleo las lee) | |

Lo que NO hacemos: rascar en masa webs que lo prohíben (Indeed, InfoJobs), aplicar o enviar nada, ni copiar código de productos de pago (LazyApply y similares son cerrados; lo que copiamos son sus ideas: agregar fuentes, puntuar, no repetir, recordar lo visto).

## Para aprender (el plan de mañana)
1. Lee `perfil.yaml` y cambia un peso; ejecuta `buscar.py --motivos` y mira cómo cambia el orden.
2. Lee `fuentes/remotive.py` (30 líneas): así se habla con una API. Ejercicio: añade la categoría «product» o «customer-support».
3. Regístrate en Adzuna, guarda las claves y verás España de verdad.
4. Añade una fuente nueva copiando `fuentes/jobicy.py` (por ejemplo Jooble cuando tengas clave).
5. La pestaña «Ofertas» de la app (Empleo › Ofertas) ya existe: lista con filtros, ficha, Guardar, «No me interesa» y «Pasar a candidaturas». Está en `pagina-web/ofertas.py` y `web/src/panel/Ofertas.tsx`. Lo que marcas ahí es lo que aprende el modelo de ofertas (`aprendizaje/entrenar_ofertas.py`).

## Ideas de `MadsLorentzen/ai-job-search` (licencia MIT, hecho para Claude Code)
Revisado el 19 de octubre de 2026 leyendo su README, su lista de archivos y sus reglas de evaluación. No se ha descargado ni ejecutado nada de él. Lo que tomamos son ideas, no código.

| Idea del repo | Estado aquí | Qué hace falta |
|---|---|---|
| **Puerta de idioma:** descartar lo que exige un idioma que no tienes; «es un plus» no cuenta | **Hecho** (`puntuar.py`, lee `idiomas` de `perfil.yaml`). Con las 134 ofertas guardadas: 5 pasan a excluidas y 30 bajan 20 puntos por estar escritas en alemán, francés u holandés | Nada |
| **Resultados de cada candidatura** (entrevista, oferta, rechazo, sin respuesta) | Propuesto | Local. Son las etiquetas que faltan para el modelo D2 de ofertas |
| **Puerta de elegibilidad:** permiso de trabajo o ciudadanía exigidos («el silencio no es permiso») | Propuesto | Local. Un campo `permiso_trabajo` en el perfil y reglas para UK, Suiza y similares |
| **Huecos de habilidades:** cruzar lo que piden las ofertas con tu perfil y sacar un plan de estudio | Propuesto | Local y sin IA; enlaza con el plan de Profe |
| **Rúbrica por dimensiones** (encaje técnico, experiencia, alineación, logística, filtros propios) con puntos fuertes y huecos | Propuesto | Un modelo (Haiku) con tu perfil: sale un resumen de tu perfil y el texto público de la oferta. Necesita el OK de Fran |
| **Borradores de CV y carta adaptados**, con un segundo agente que los critica | Propuesto, más adelante | Sale tu CV a un modelo. OK de Fran. Él revisa y envía; Zazu no envía nada |
| **Guardia de ofertas:** quitar texto oculto y líneas con forma de instrucción antes de dárselas a un modelo | Obligatoria si se añade cualquiera de las dos anteriores | Local |
| **Fuente freehire.me** (API pública sin clave, unas 387.000 ofertas) | Por probar | Mi primera consulta con `country=ES` no filtró (salieron Israel y Londres): faltan los parámetros correctos. Sin garantía de servicio |

Lo que **no** tomamos: el acceso a LinkedIn por su dirección pública de invitados (el propio repo avisa de que es «solo uso personal» y va contra sus condiciones), y las candidaturas en volumen (el autor cuenta 69 para un contrato). Lo que más falta hoy no está en el repo: **España**. De las 134 ofertas guardadas, ninguna está escrita en español. Hacen falta las claves gratis de Adzuna.

**LinkedIn, comprobado el 19 de octubre de 2026:** su dirección pública de búsqueda para invitados contestó «demasiadas peticiones» (429) a la primera petición desde este servidor, con un User-Agent honesto. No se insiste ni se disfraza el cliente: va contra sus condiciones, y el buscador solo usa lo permitido. Lo que sí hay de LinkedIn: las alertas de empleo que te llegan por correo (Zazu Empleo las apunta como candidaturas «por enviar») y la fuente de publicaciones de reclutadores con tu propia sesión. Siguiente paso posible: leer esas alertas también en la lista de Ofertas.
