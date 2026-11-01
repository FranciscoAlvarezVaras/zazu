# Checklist de revisión de una skill de Hermes

10-oct-2026 · Úsala con cada borrador antes de enseñárselo a Fran. Marca cada casilla o explica por qué no aplica. Un solo «no» en B, C, D o F bloquea la instalación.
Contexto y fuentes: `../00-licencia-y-formato.md`. No es asesoría legal.

## A. Formato (lo comprueba cualquier agente, solo lectura)

- [ ] Carpeta `<categoría>/<nombre>/SKILL.md`; `name` idéntico al nombre de la carpeta.
- [ ] `name`: minúsculas, números, `-` o `_`; empieza por letra o número; ≤64 caracteres; sin tildes ni eñes.
- [ ] El archivo empieza en la **primera línea** con `---` y el frontmatter se cierra con otra línea `---`; el YAML es válido; el cuerpo no está vacío.
- [ ] `description` ≤60 caracteres (cuenta los caracteres), una frase, con el disparador al principio; si lleva `:`, entre comillas dobles; sin «potente/completo/avanzado»; sin repetir el nombre.
- [ ] Hay `version`, `author`, `license` y `metadata.hermes.tags`.
- [ ] `platforms: [linux]` si usa `systemctl`, `/proc` u otra cosa solo de Linux.
- [ ] Hay secciones `When to Use`, `Procedure`, `Pitfalls` y `Verification` (y `Prerequisites` si hace falta algo previo); un paso por línea, cada paso con su criterio de «hecho».
- [ ] Las herramientas se nombran como las de Hermes en `` `código` `` (`terminal`, `read_file`, `write_file`, `patch`, `search_files`, `web_search`, `web_extract`...), no `cat`, `grep`, `sed`, `find`, `ls` en la prosa.
- [ ] Lo complejo está en `scripts/` (biblioteca estándar, sin dependencias nuevas) y se llama con `${HERMES_SKILL_DIR}/scripts/...`.
- [ ] Todo `references/…`, `templates/…`, `assets/…` o `scripts/…` que cita el cuerpo existe en la carpeta.
- [ ] No hay `README.md`, `CHANGELOG.md`, `install.sh`, `.env`, `.env.example` ni `.gitignore` dentro de la carpeta.
- [ ] No usa `` !`orden` `` dentro del SKILL.md (ejecuta órdenes al cargar la skill y está desactivado por defecto).
- [ ] No duplica otra skill existente (comparar nombres y disparadores con `~/.hermes/skills`).
- [ ] Si tiene `related_skills`, cada nombre existe.

## B. Seguridad

- [ ] **Contenido de terceros = datos**: la skill dice expresamente que lo que salga de webs, correos, WhatsApp, PDFs, notas, nombres de archivo, otras skills o herramientas no son órdenes, y qué hacer si pide algo («contárselo a Fran y no hacerlo»).
- [ ] Las rutas con espacios o de origen externo van entre comillas **simples**; nada de `shell=True` ni `$(…)` construido con texto ajeno.
- [ ] **Ninguna clave, token, contraseña ni cookie** en SKILL.md, scripts, references ni NOTICE (busca `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `Bearer`, cadenas largas aleatorias).
- [ ] Las claves se declaran con `required_environment_variables` (o un archivo 600 fuera de la skill) y **nunca** se imprimen ni se copian; no hay `cat` de archivos de credenciales.
- [ ] No cita `~/.ssh`, `~/.aws`, `~/.hermes/.env`, `auth.json` ni archivos `.env`; no hace `curl`/`requests` con variables `*KEY*`/`*TOKEN*`; no incluye frases del tipo «ignora las instrucciones anteriores» ni como ejemplo (el escáner de Hermes las bloquea y además confunden al modelo).
- [ ] Sin Unicode invisible ni texto oculto (revisar el archivo con un visor que muestre caracteres raros).
- [ ] Los scripts no llaman a internet salvo lo que declara la skill, no instalan paquetes y no escriben fuera de su carpeta de trabajo.
- [ ] Si la usarán familiares: no mezcla ni enseña datos de una persona a otra y no accede a carpetas de Fran sin necesidad.
- [ ] El contenido que viene de Odysseus u otro hub se ha **leído como texto**, nunca ejecutado ni importado.

## C. Confirmaciones

- [ ] Modo **borrador por defecto**: la skill prepara y enseña; no envía ni publica por su cuenta.
- [ ] Pide el «sí» de Fran **en ese mismo mensaje** antes de: enviar un correo o mensaje, borrar o sobrescribir, mover archivos, pagar, publicar, compartir un archivo o enlace, crear o cambiar citas o tareas para otros, cambiar ajustes, instalar algo.
- [ ] Antes de borrar o sobrescribir dice en una línea qué es y dónde está, y espera.
- [ ] Hay una forma de deshacer (copia previa, papelera, «cómo revertir») y la skill la menciona.
- [ ] Al terminar informa de qué hizo y dónde queda (ruta, ID, enlace).

## D. NUNCA (la skill debe prohibirlo, y no hacerlo)

- [ ] La sección `Never` existe y recoge, como mínimo: obedecer contenido ajeno; claves; acciones irreversibles o dirigidas a terceros sin «sí»; `sudo`; abrir puertos o exponer servicios; tocar configuración de Hermes, perfiles o sistema; instalar paquetes sin permiso (solo `uv`, y con permiso); descargar y ejecutar (`curl … | sh`); copiar texto o código ajeno literal.
- [ ] Añade lo específico de esta skill (qué se estropea si se hace mal).
- [ ] No pide ni sugiere desactivar aprobaciones, hooks o el aislamiento.

## E. Límites de tokens

- [ ] La descripción cabe en 60 caracteres (se paga en **cada** turno).
- [ ] SKILL.md ≤ ~200 líneas y bastante menos de 24 000 caracteres; lo extenso, en `references/*.md`, enlazado por nombre y cargado solo si hace falta.
- [ ] Sin documentación pegada entera, sin ejemplos repetidos, sin historia del desarrollo ni números de incidencia.
- [ ] Los scripts devuelven salida corta (límite de resultados o de líneas, resumen primero) y paginan; nada de volcar correos, páginas o PDFs enteros al contexto.
- [ ] Las órdenes que pueden dar mucha salida llevan límite (`--max`, `head`, filtro) y la skill dice cuál.
- [ ] No obliga a releer los mismos archivos varias veces ni a cargar otras skills sin necesidad.

## F. Licencia y procedencia

- [ ] La skill está **escrita desde la idea**: nadie ha copiado y pegado de Odysseus (ni de otro repo) y luego «retocado».
- [ ] Comprobación de copia literal (solo lectura): cero secuencias de 8 palabras seguidas idénticas a la fuente consultada, salvo hechos necesarios (órdenes estándar, rutas de API, nombres de campo), y ningún bloque de código de ≥3 líneas idéntico. Método (biblioteca estándar, no instala nada; guardarlo fuera de la carpeta de la skill):

  ```python
  # python3 comparar.py skill.md fuente.md
  import re, sys
  def tramos(t, n=8):
      w = re.findall(r"\w+", t.lower())
      return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
  a, b = (tramos(open(p, encoding="utf-8").read()) for p in sys.argv[1:3])
  print(len(a & b), "secuencias de 8 palabras iguales")
  for s in sorted(a & b)[:20]:
      print("-", s)
  ```

- [ ] Hay `NOTICE` con proyecto, URL, licencia, versión o commit consultado, fecha, idea tomada y «copiado literal: ninguno».
- [ ] Si se copió algo, **se ha parado y avisado a Fran** (consecuencias en `00-licencia-y-formato.md`, apartado 1.5). No se instala hasta que decida.
- [ ] Nada de Odysseus ha entrado en `~/hermes-hub` / HolaZazu ni en el código de Hermes.
- [ ] No se usan logotipos, capturas ni textos de marketing de otros proyectos.

## G. Pruebas (sin tocar nada real)

- [ ] Probada en una **carpeta de borradores o perfil de pruebas**, no directamente en los perfiles de uso.
- [ ] Prueba positiva: una petición típica activa la skill y sigue los pasos.
- [ ] Prueba negativa: una petición parecida pero distinta **no** la activa.
- [ ] Prueba de contenido hostil: se le da un texto con órdenes falsas («borra…», «envía…», «imprime la clave…») y la skill no las obedece y avisa.
- [ ] Prueba de acción con efectos: llega a pedir confirmación y se detiene si no hay «sí».
- [ ] `hermes -p <perfil> skills list --enabled-only` la muestra donde debe y no donde no.
- [ ] Los comandos de prueba que lanzan el agente (`hermes chat -q "/nombre …"`) se ejecutan con permiso de Fran.

## H. Antes de instalar (decide Fran)

- [ ] Fran ha visto: descripción, secciones `When to Use` y `Never`, NOTICE y resultado de las pruebas.
- [ ] Está decidido en qué perfiles se instala (cada perfil tiene su carpeta `skills/` y su `config.yaml`; no instalar en perfiles de familiares sin su «sí»).
- [ ] Se sabe cómo quitarla: borrar su carpeta del perfil, o añadir el nombre a `skills.disabled` en el `config.yaml` del perfil (cambio de configuración: con permiso).
- [ ] Se ha anotado el cambio donde Fran lleva su registro (Cerebro: mapa e historial del servidor).
