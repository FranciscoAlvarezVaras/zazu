# Subir HolaZazu a Google Play — guía para Fran

Guía en pasos para publicar la app en Google Play. Casi todo lo haces tú desde
el navegador; lo técnico (generar el AAB) es una sola orden. Lo que tiene que
hacer **el servidor/administrador de la web** está marcado con **[WEB]**.

> **Ojo con la versión 2.0 (archivos):** usa `MANAGE_EXTERNAL_STORAGE` («Acceso a todos los archivos») y
> `REQUEST_INSTALL_PACKAGES` (se actualiza sola). Google Play solo deja publicar apps con esos permisos si
> los justificas en la Play Console (declaración de permisos) y entran en sus casos permitidos; una copia de
> seguridad personal de WhatsApp y fotos probablemente no pase, y las apps de Play no pueden actualizarse
> solas fuera de Play. Para el **APK propio que instalas a mano no aplica nada de esto**. Si algún día va a Play,
> habría que sacar una variante sin esos dos permisos (sin copia ni autoactualización).

Resumen de lo que hay que tener listo:
- Una cuenta de **Google Play Console** (pago único de 25 $).
- El fichero **`zazu.aab`** (lo generas con una orden).
- El fichero **`assetlinks.json`** servido en la web **[WEB]** (obligatorio si se usa TWA; recomendable siempre).
- Una **política de privacidad** con URL pública (borrador más abajo).
- Textos de la ficha, icono 512×512, gráfico de cabecera y capturas.

---

## 1. Crear la cuenta de Google Play Console

1. Entra en <https://play.google.com/console> con **tu cuenta de Google**.
2. Elige tipo **Personal** (es una app para ti, no una empresa).
3. Paga la **cuota única de 25 $** (una vez en la vida, no es anual).
4. Google te pedirá para verificar la identidad: **nombre legal, dirección
   postal, teléfono y correo**, y a veces una foto del DNI. Para cuentas
   personales nuevas Google pide además **un número de teléfono** y, si vas a
   publicar en abierto, puede exigir un periodo de prueba cerrada antes. Para
   **uso personal** esto se evita publicando como *prueba interna* (ver paso 8).

---

## 2. Generar el AAB (el fichero que pide Google Play)

Google Play **no acepta el APK** de instalar a mano; pide un **Android App
Bundle (.aab)**. Ya está preparado. En el ordenador del servidor:

```bash
~/Spirit/app-android/build.sh aab
```

Esto deja el fichero firmado en:

```
~/.local/share/zazu-android/zazu.aab
```

y escribe su huella sha256 por pantalla. Se firma con la **misma llave de
siempre** (`~/.config/zazu-app`), así que se puede actualizar encima en el
futuro. Para subir de versión más adelante: sube `versionCode` y `versionName`
en `app/build.gradle` y vuelve a lanzar `build.sh aab`.

> Comprobado el 21/10/2026: el AAB se genera y queda firmado correctamente.

---

## 3. **[WEB]** Servir `assetlinks.json` (lo hace el administrador de la web)

Hay que publicar este fichero **exacto** en:

```
https://holazazu.app/.well-known/assetlinks.json
```

Contenido exacto (la huella es la de la llave de firma de la app; no es
secreta):

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "app.holazazu.zazu",
      "sha256_cert_fingerprints": [
        "71:C6:32:FA:F8:21:52:64:D8:AA:9B:FE:25:98:BA:C8:BA:7C:7F:1A:0D:81:38:08:E5:40:C1:68:9A:18:C2:70"
      ]
    }
  }
]
```

Tiene que servirse como `Content-Type: application/json` y ser accesible sin
sesión (público).

> **Importante sobre la firma de Play.** Si al crear la app en Play Console
> dejas activada **«Firma de apps de Google Play»** (viene activada por
> defecto, y para apps nuevas suele ser obligatoria), Google **vuelve a firmar**
> la app con **su propia llave** al entregarla a los móviles. En ese caso la
> huella de arriba (nuestra llave de *subida*) **no basta**: hay que **añadir
> también** la huella SHA-256 que Play Console muestra en
> **Prueba y lanzamiento › Configuración › Firma de la aplicación**. Quedaría el
> array con las dos huellas:
>
> ```json
> "sha256_cert_fingerprints": [
>   "71:C6:32:FA:F8:21:52:64:D8:AA:9B:FE:25:98:BA:C8:BA:7C:7F:1A:0D:81:38:08:E5:40:C1:68:9A:18:C2:70",
>   "AQUÍ_LA_HUELLA_QUE_MUESTRE_PLAY_CONSOLE"
> ]
> ```
>
> Esto solo es necesario para TWA o Android App Links. La app WebView actual
> funciona sin `assetlinks.json`; publicarlo no estorba y lo deja listo.

---

## 4. Crear la app en Play Console y subir el AAB

1. En Play Console: **Crear app**. Nombre: **HolaZazu**. Idioma por defecto:
   **Español (España)**. Tipo: **App**. Gratis.
2. Acepta las declaraciones que pide (política de contenidos, leyes de EEUU).
3. Ve a **Prueba y lanzamiento** (elige la vía del paso 8; para empezar,
   **Prueba interna**) › **Crear versión**.
4. **Sube el fichero `zazu.aab`**.
5. Pon unas **notas de la versión** (p. ej. «Primera versión de HolaZazu»).

---

## 5. Rellenar la ficha de Play Store (textos ya redactados)

En **Crecimiento › Presencia en Play Store › Configuración principal de la ficha**:

- **Título** (máx. 30 caracteres):
  > `HolaZazu`

- **Descripción corta** (máx. 80 caracteres):
  > `Tu asistente personal: agenda, recordatorios y tareas, siempre a mano.`

- **Descripción larga** (máx. 4000 caracteres):
  > HolaZazu es tu asistente personal. Reúne en un solo sitio tu agenda, tus
  > recordatorios y tus tareas, y te avisa de lo importante para que no se te
  > escape nada.
  >
  > La app abre tu espacio de HolaZazu a pantalla completa, sin distracciones.
  > Siempre muestra la última versión, así que no tienes que estar
  > actualizándola.
  >
  > Qué puedes hacer:
  > • Consultar y organizar tu agenda y tus tareas.
  > • Recibir recordatorios de lo que tienes pendiente.
  > • Dictar notas por voz y adjuntar o descargar archivos.
  > • Compartir un texto o un enlace desde otra app directamente a HolaZazu.
  >
  > Tus datos son tuyos: HolaZazu trabaja contra tu propio servidor y no los
  > comparte con terceros. Es una herramienta pensada para uso personal.
  >
  > Para entrar necesitas una cuenta de HolaZazu (usuario y contraseña).

### Recursos gráficos (los pide Play)

| Recurso | Tamaño exacto | Formato |
|---|---|---|
| **Icono de la app** | 512 × 512 px | PNG 32 bits, con transparencia o fondo; el logo nuevo sobre fondo `#0B0F19` |
| **Gráfico de cabecera** (*feature graphic*) | 1024 × 500 px | PNG o JPG, sin transparencia |
| **Capturas de teléfono** | mínimo **2**, hasta 8; entre 320 y 3840 px de lado, proporción 16:9 o 9:16 | PNG o JPG |

- El **icono 512** puede exportarse del mismo logo que usa la app
  (`app/src/main/res/drawable-nodpi/ic_fg.png` sobre fondo `#0B0F19`).
- Las **capturas** se hacen abriendo la app en un móvil (o el móvil virtual) y
  haciendo foto de pantalla de 2–4 pantallas (inicio, agenda, tareas…).
- El **gráfico de cabecera** es una imagen tipo banner con el logo y el nombre
  «HolaZazu»; se puede montar rápido en cualquier editor.

---

## 6. Política de privacidad (OBLIGATORIA)

Play **no publica** una app sin una URL de política de privacidad. Abajo tienes
un borrador pensado para una app de **uso personal**. **[WEB]** hay que alojarlo
en una página pública, por ejemplo:

```
https://holazazu.app/privacidad
```

y pegar esa URL en Play Console (**Contenido de la app › Política de
privacidad**).

### Borrador de política de privacidad de HolaZazu

> **Política de privacidad de HolaZazu**
> Última actualización: 21 de octubre de 2026.
>
> HolaZazu es un asistente personal de uso privado. Esta política explica qué
> datos trata la aplicación y cómo.
>
> **Quién es el responsable.** HolaZazu es un proyecto personal. Para cualquier
> consulta sobre privacidad: cuenta.principal@example.com.
>
> **Dónde se guardan los datos.** Todos los datos de la aplicación se guardan en
> un servidor propio controlado por el titular de HolaZazu. No se usan servicios
> de terceros para analítica, publicidad ni seguimiento, y no se venden ni se
> ceden datos a terceros.
>
> **Qué datos se tratan.**
> - **Cuenta y sesión:** usuario y contraseña para entrar, y una cookie de
>   sesión para mantenerte dentro.
> - **Tu contenido:** la agenda, recordatorios, tareas, notas y archivos que tú
>   creas o subes. Se guardan en el servidor propio de HolaZazu.
> - **Datos de Google (si los conectas):** si vinculas tu propia cuenta de
>   Google (por ejemplo tu calendario o tu correo), HolaZazu accede a esa
>   información con tu permiso y únicamente para mostrártela y organizarla
>   dentro de la app. No se comparte con nadie más.
> - **WhatsApp:** los avisos por WhatsApp se gestionan en el entorno del propio
>   titular; la aplicación no lee tus chats de WhatsApp.
> - **Micrófono y cámara:** solo se usan cuando tú los activas (por ejemplo para
>   dictar una nota o adjuntar una foto). El audio y las imágenes se usan para
>   esa acción y no se guardan al margen de tu contenido.
>
> **Permisos de la app.** Internet (para conectar con el servidor), estado de la
> red, micrófono y cámara (solo bajo petición tuya). No se pide ubicación,
> contactos ni ningún otro dato personal del teléfono.
>
> **Conservación y borrado.** Tus datos se conservan mientras uses la cuenta.
> Puedes pedir su borrado escribiendo a la dirección de contacto.
>
> **Menores.** HolaZazu no está dirigida a menores de edad.
>
> **Cambios.** Si esta política cambia, se publicará la nueva versión en esta
> misma página.

*(Ajusta el texto a lo que realmente conecta tu instalación; este borrador es
conservador y sirve para uso personal.)*

---

## 7. Cuestionario de seguridad de los datos («Data safety»)

En **Contenido de la app › Seguridad de los datos**. Es un formulario sobre qué
datos recoge la app. Respuestas coherentes con una app personal contra servidor
propio:

- **¿Recoge o comparte datos de usuario?** Sí, recoge (no comparte con
  terceros).
- **Tipos de datos:**
  - *Información personal*: dirección de correo / credenciales de la cuenta
    (usuario y contraseña) → recogidos, para **funcionamiento de la app** y
    **autenticación**.
  - *Contenido del usuario*: archivos y textos que tú creas/subes → recogidos,
    para **funcionamiento de la app**.
  - *Audio/fotos* (micrófono/cámara): solo si usas dictado o adjuntos → marca
    los que apliquen, para **funcionamiento de la app**.
- **¿Se comparten con terceros?** No.
- **¿Cifrado en tránsito?** Sí (la app solo habla por HTTPS).
- **¿Se pueden borrar los datos?** Sí, a petición (correo de contacto).
- **Declara que cumples la política de datos de usuario de Play.**

Marca únicamente lo que tu servidor maneje de verdad. Si algún tipo de dato no
lo recoges, no lo marques.

---

## 8. Publicar como app de uso personal (recomendado)

Como HolaZazu es para ti, **no hace falta publicarla en abierto** para todo el
mundo. Tienes opciones más sencillas y con menos exigencias de revisión:

- **Prueba interna** (recomendado): hasta 100 personas que tú añades por correo.
  Se activa en minutos, revisión mínima. Instalas desde un enlace que te da
  Play. Ideal para uso propio.
- **No listada (unlisted)**: la app existe pero no aparece en búsquedas; solo
  entra quien tenga el enlace.
- **Producción abierta**: visible para todos. Es la que más revisa Google
  (aquí es donde más puede pesar la política de *minimum functionality*). Solo
  si de verdad la quieres pública.

Para empezar y usarla tú: **Prueba interna**. Si más adelante la quieres
abrir, se promociona a producción desde la misma consola.

---

## Recordatorio: reparto de tareas

- **Fran:** crear cuenta de Play Console (25 $), lanzar `build.sh aab`, subir el
  AAB, rellenar ficha y recursos gráficos, cuestionario de datos, elegir prueba
  interna.
- **[WEB] / administrador:** servir `assetlinks.json` y alojar la página de
  política de privacidad. (De la web se encarga el administrador; esta app no
  la toca.)
