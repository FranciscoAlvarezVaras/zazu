# Idea para el futuro: TWA en vez de WebView (NO está activo)

> Esto es una **rama de ideas**, no código en uso. Hoy la app es el WebView de
> `MainActivity.java` y **funciona**. Este fichero explica cómo sería migrar a
> un TWA (Trusted Web Activity) **si algún día Google Play rechaza el WebView**.
> No toques el código que funciona salvo que haya que hacerlo.

## Decisión actual: se mantiene el WebView

Google Play rechaza apps que son «solo un WebView» que abre una web y nada más
(política de *minimum functionality* / *repackaging*). **Nuestro WebView no es
«solo un WebView»**: tiene funcionalidad propia de Android que un reviewer puede
ver y que justifica la app:

- objetivo de **«Compartir › HolaZazu»** (recibe texto y enlaces de otras apps),
- **subida y descarga** de archivos con el gestor de descargas de Android,
- gestión de permisos de **micrófono y cámara**,
- pantalla propia de **«No pude conectar»** con reintento (sin internet),
- **recarga al volver** tras un rato de fondo,
- apertura de enlaces externos en el navegador del sistema.

Además es una **app de uso personal**: puede publicarse como *prueba interna* o
*no listada*, donde la revisión de la política de minimum functionality es mucho
más laxa. Por todo esto **la recomendación es mantener el WebView** y tener el
TWA preparado como plan B.

### WebView vs TWA — pros y contras

| | WebView (lo que hay hoy) | TWA (plan B) |
|---|---|---|
| Estado | Funciona y está probado | Habría que montarlo y probarlo |
| Motor | WebView del sistema | Chrome del teléfono (mismo que la PWA) |
| Minimum functionality de Play | Aceptable por las funciones propias de arriba, pero un reviewer estricto podría discutirlo | Vía bendecida por Google para PWAs; no se discute |
| Dependencias | Ninguna (solo WebView) | `com.google.androidbrowserhelper` (una librería más) |
| Digital Asset Links | No lo necesita | **Obligatorio** (`assetlinks.json` servido en la web) |
| Micrófono / cámara / subida / descarga | Lo gestiona nuestro código | Lo gestiona Chrome (funciona, menos control) |
| «Compartir › HolaZazu» | Ya hecho en `MainActivity` | Se configura aparte (share_target del manifest + intent-filter) |
| Pantalla sin conexión propia | Sí (la nuestra) | La de Chrome |
| Control del User-Agent `ZazuApp/…` | Nuestro (la web se adapta) | Hay que replicarlo con `additionalTrustedOrigins`/cabeceras; más difícil |

## Si hubiera que migrar (sin cambiar applicationId ni la llave)

`applicationId` sigue siendo `app.holazazu.zazu` y la firma sigue siendo la de
`~/.config/zazu-app` (si cambian, Fran no puede actualizar encima).

1. `app/build.gradle` → añadir la dependencia:

   ```gradle
   dependencies {
       implementation 'com.google.androidbrowserhelper:androidbrowserhelper:2.5.0'
   }
   ```

2. `AndroidManifest.xml` → sustituir la `MainActivity` por la del helper:

   ```xml
   <activity android:name="com.google.androidbrowserhelper.trusted.LauncherActivity"
             android:exported="true">
       <meta-data android:name="android.support.customtabs.trusted.DEFAULT_URL"
                  android:value="https://holazazu.app/" />
       <meta-data android:name="android.support.customtabs.trusted.STATUS_BAR_COLOR"
                  android:resource="@color/ic_bg" />
       <intent-filter>
           <action android:name="android.intent.action.MAIN" />
           <category android:name="android.intent.category.LAUNCHER" />
       </intent-filter>
       <!-- Android App Links: abre holazazu.app dentro del TWA (necesita assetlinks.json) -->
       <intent-filter android:autoVerify="true">
           <action android:name="android.intent.action.VIEW" />
           <category android:name="android.intent.category.DEFAULT" />
           <category android:name="android.intent.category.BROWSABLE" />
           <data android:scheme="https" android:host="holazazu.app" />
       </intent-filter>
   </activity>
   ```

3. Servir `assetlinks.json` en `https://holazazu.app/.well-known/assetlinks.json`
   (ver `PLAY-STORE.md`). Sin eso el TWA abre con barra de direcciones de Chrome.

4. La `MainActivity.java` actual se quedaría sin usar (guardarla, no borrarla,
   por si hay que volver al WebView).

El `assetlinks.json` hace falta **sí o sí** para el TWA, y es **recomendable
igualmente** con el WebView actual (habilita los Android App Links: que un
enlace `https://holazazu.app/...` abra la app en vez del navegador).
