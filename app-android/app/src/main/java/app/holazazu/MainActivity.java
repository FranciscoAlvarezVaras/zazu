package app.holazazu;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.location.LocationManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.SystemClock;
import android.util.Base64;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputConnectionWrapper;
import android.view.inputmethod.InputContentInfo;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Zazu: la web de HolaZazu dentro de una app, sin barra de direcciones y sin copia guardada de la página.
 * Carga siempre la versión que hay en el servidor: al DOCUMENTO HTML se le añade un parámetro único «?_v=<ms>» (buster) para que ni el WebView ni Cloudflare
 * sirvan una copia vieja; los /assets con hash, al no llevar buster, siguen cacheándose y la app no va lenta. Así un cambio en la web se ve al abrir la app sin instalar nada.
 * Solo se habla con el servidor de Zazu: cualquier otro enlace se abre en el navegador. Aquí no hay claves ni datos guardados aparte de la sesión de la web.
 */
public class MainActivity extends Activity {
    private static final String BASE = BuildConfig.URL_BASE;
    private static final int PIDE_ARCHIVO = 1, PIDE_PERMISOS = 2, PIDE_LEER = 3, PIDE_AVISOS = 4, PIDE_UBICACION = 5, PIDE_PUENTE = 6;
    private static final List<String> TIPOS = Arrays.asList("notificaciones", "ubicacion", "microfono", "camara");
    private static final List<String> ESQUEMAS_FUERA = Arrays.asList("http", "https", "mailto", "tel");
    private static final String SIN_CONEXION = "<!doctype html><html lang=\"es\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            + "<body style=\"margin:0;padding:48px 24px;background:#f7f1e3;color:#1f3b4d;font:16px/1.5 sans-serif;text-align:center\">"
            + "<h1 style=\"font-size:22px;margin:0 0 12px\">No pude conectar con Zazu</h1>"
            + "<p>Revisa que tengas internet. Si estás con datos y falla, prueba con una WiFi.</p>"
            + "<p><a href=\"/?tab=inicio\" style=\"display:inline-block;padding:14px 28px;background:#0b6fb8;color:#fff;border-radius:8px;text-decoration:none;font-weight:600\">Reintentar</a></p></body></html>";

    private WebView web;
    private String hostBase;
    private ValueCallback<Uri[]> subida;
    private PermissionRequest pendiente;
    private String geoOrigen;
    private android.webkit.GeolocationPermissions.Callback geoCb;
    private long pausadoEn = 0;
    private long sondeoEn = 0, googleEn = 0;   // última vez que se miraron avisos y peticiones; último «Conectar con Google»
    private boolean sondeoConAcceso = false;
    private View aviso;
    private volatile boolean pidiendoToken = false;
    // 2.4 puente: la URL que se ve ahora (se actualiza en el hilo de la interfaz; el puente la lee desde su hilo, sin llamar a getUrl())
    private volatile String urlActual;
    private String tipoAlVolver;   // se abrió un Ajustes desde la web: al volver se le dice cómo quedó ese permiso
    // Android solo enseña un diálogo de permisos a la vez (si se cruzan, al segundo lo niega sin preguntar): se piden en fila
    private final java.util.ArrayDeque<Pedido> cola = new java.util.ArrayDeque<>();
    private Pedido enCurso;
    // tipos que la web pidió con el puente mientras su permiso ya estaba en la fila: se les contesta cuando salga de ella
    private final java.util.Set<String> esperanTipo = new java.util.HashSet<>();

    private static final class Pedido {
        final String[] permisos;
        final int codigo;
        final String tipo;
        boolean[] razonAntes;
        long desde;

        Pedido(String[] permisos, int codigo, String tipo) {
            this.permisos = permisos;
            this.codigo = codigo;
            this.tipo = tipo;
        }
    }

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        hostBase = Uri.parse(BASE).getHost();
        FrameLayout raiz = new FrameLayout(this);
        // El teclado de Samsung guarda las capturas en su portapapeles y las «inserta» como contenido (commitContent).
        // El WebView no lo acepta en un cuadro de texto: aquí se acepta la imagen y se le pasa a la web (zazu-imagen-pegada).
        web = new WebView(this) {
            @Override
            public InputConnection onCreateInputConnection(EditorInfo info) {
                InputConnection ic = super.onCreateInputConnection(info);
                if (ic == null || !esNuestra()) return ic;
                info.contentMimeTypes = new String[]{"image/png", "image/jpeg", "image/gif", "image/webp"};
                return new InputConnectionWrapper(ic, false) {
                    @Override
                    public boolean commitContent(InputContentInfo contenido, int flags, Bundle opciones) {
                        return recibirImagen(contenido, flags);
                    }
                };
            }
        };
        raiz.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        aviso = pantallaPermiso();
        raiz.addView(aviso, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(raiz);
        web.setBackgroundColor(0xFFF7F1E3);
        Peticiones.limpiarEnPantalla(this);
        // 2.5: las notificaciones ya no se piden nada más abrir (antes del login y de la guía): las pide la guía de bienvenida
        // o «Tus permisos» con el puente. Pedirlas dos veces seguidas hacía que, con dos «no», Android las bloqueara para siempre.

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setGeolocationEnabled(true);   // la web pide la ubicación (Tus permisos › Ubicación) y aquí se pregunta al sistema
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSupportMultipleWindows(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        // LOAD_DEFAULT (no NO_CACHE): el documento HTML ya va siempre fresco por el buster «?_v=» de la URL, y así los /assets con hash siguen cacheándose
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        // la web sabe que está dentro de la app (no registra su service worker ni ofrece «instalar»; «Entrar con Google» va por Chrome, ver entrarConGoogle)
        s.setUserAgentString(s.getUserAgentString() + " ZazuApp/" + BuildConfig.VERSION_NAME);
        if (Build.VERSION.SDK_INT >= 33) s.setAlgorithmicDarkeningAllowed(false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);
        // 2.4: window.ZazuNativo para que la web sepa el estado real de los permisos y abra los Ajustes (solo responde en páginas de Zazu)
        web.addJavascriptInterface(new Puente(), "ZazuNativo");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView v, String url, android.graphics.Bitmap icono) {
                urlActual = url;
            }

            @Override
            public void doUpdateVisitedHistory(WebView v, String url, boolean recarga) {
                urlActual = url;
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (hostBase.equals(u.getHost())) {
                    String p = u.getPath();
                    if (p != null && p.startsWith("/oauth/google")) {
                        // Google no deja hacer OAuth dentro de un WebView: el login y (2.5) «Conectar con Google» van en una Custom Tab
                        // y se vuelve a la app con un código de un solo uso
                        if (!"/oauth/google/start".equals(p)) return true;
                        if ("connect".equals(u.getQueryParameter("mode"))) conectarGoogle(u.getQueryParameter("email"));
                        else entrarConGoogle();
                        return true;
                    }
                    return false;
                }
                abrirFuera(u);
                return true;
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                urlActual = url;
                if (url != null && hostBase.equals(Uri.parse(url).getHost())) {
                    pedirToken();
                    Actualizar.comprobar(MainActivity.this);
                }
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) v.loadDataWithBaseURL(BASE + "/", SIN_CONEXION, "text/html", "utf-8", null);
            }

            @Override
            public boolean onRenderProcessGone(WebView v, RenderProcessGoneDetail d) {
                recreate();
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (subida != null) subida.onReceiveValue(null);
                subida = cb;
                try {
                    startActivityForResult(p.createIntent(), PIDE_ARCHIVO);
                } catch (ActivityNotFoundException e) {
                    subida = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onGeolocationPermissionsShowPrompt(String origen, android.webkit.GeolocationPermissions.Callback cb) {
                if (!hostBase.equals(Uri.parse(origen).getHost())) { cb.invoke(origen, false, false); return; }   // solo nuestra web
                // con el permiso del sistema dado, el WebView lo recuerda (retain): así la web lo ve «concedido»; si Android lo quita, onResume lo borra
                if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) { cb.invoke(origen, true, true); return; }
                if (geoCb != null) geoCb.invoke(geoOrigen, false, false);   // una petición anterior sin contestar: no se queda colgada
                geoOrigen = origen;
                geoCb = cb;
                if (!pidiendo(Manifest.permission.ACCESS_COARSE_LOCATION))
                    pedirSistema(new String[]{Manifest.permission.ACCESS_COARSE_LOCATION}, PIDE_UBICACION, "ubicacion");
            }

            @Override
            public void onGeolocationPermissionsHidePrompt() {
                geoCb = null;   // la web ya no espera respuesta
            }

            @Override
            public void onPermissionRequestCanceled(PermissionRequest r) {
                if (pendiente == r) pendiente = null;
            }

            @Override
            public void onPermissionRequest(PermissionRequest r) {
                if (!hostBase.equals(r.getOrigin().getHost())) {
                    r.deny();
                    return;
                }
                List<String> recursos = new ArrayList<>(), permisos = new ArrayList<>();
                for (String x : r.getResources()) {
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(x)) {
                        recursos.add(x);
                        permisos.add(Manifest.permission.RECORD_AUDIO);
                    } else if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(x)) {
                        recursos.add(x);
                        permisos.add(Manifest.permission.CAMERA);
                    }
                }
                if (recursos.isEmpty()) {
                    r.deny();
                    return;
                }
                boolean todos = true;
                for (String p : permisos) if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) todos = false;
                if (todos) {
                    r.grant(recursos.toArray(new String[0]));
                } else {
                    if (pendiente != null) pendiente.deny();
                    pendiente = r;
                    List<String> faltan = new ArrayList<>();
                    for (String p : permisos) if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED && !pidiendo(p)) faltan.add(p);
                    if (!faltan.isEmpty()) pedirSistema(faltan.toArray(new String[0]), PIDE_PERMISOS,
                            faltan.contains(Manifest.permission.RECORD_AUDIO) ? "microfono" : "camara");
                }
            }
        });

        web.setDownloadListener((url, ua, cd, mime, largo) -> {
            try {
                String nombre = URLUtil.guessFileName(url, cd, mime);
                DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
                r.setMimeType(mime);
                String galletas = CookieManager.getInstance().getCookie(url);
                if (galletas != null) r.addRequestHeader("Cookie", galletas);
                r.addRequestHeader("User-Agent", ua);
                r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nombre);
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
                Toast.makeText(this, "Descargando " + nombre, Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                abrirFuera(Uri.parse(url));
            }
        });

        if (estado != null && !esVueltaDeGoogle(getIntent())) web.restoreState(estado);
        else cargar(getIntent());
        peticionDelAviso(getIntent());
    }

    // ---------- v2: archivos, copia al PC, peticiones de Zazu ----------

    /** Pantalla nativa «Zazu necesita acceso a tus archivos» (encima de la web; se quita en cuanto hay permiso o con «Ahora no»). */
    private View pantallaPermiso() {
        float dp = getResources().getDisplayMetrics().density;
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setGravity(Gravity.CENTER);
        l.setBackgroundColor(0xFFF7F1E3);
        l.setPadding((int) (28 * dp), (int) (28 * dp), (int) (28 * dp), (int) (28 * dp));
        l.setClickable(true);   // que los toques no lleguen a la web de debajo
        TextView t = new TextView(this);
        t.setText("Zazu necesita acceso a tus archivos");
        t.setTextSize(22);
        t.setTextColor(0xFF1F3B4D);
        t.setGravity(Gravity.CENTER);
        TextView x = new TextView(this);
        x.setText("Así Zazu copia sola a tu PC, en casa, las fotos de la cámara y lo que te llega por WhatsApp (solo lo nuevo, con WiFi), "
                + "y puede ayudarte a ordenar carpetas: cada cosa que te pida la verás antes y solo se hace si pulsas «Permitir».\n\n"
                + "Android lo pide una sola vez: en la pantalla que se abre, activa «Permitir acceso para gestionar todos los archivos» y vuelve.");
        x.setTextSize(16);
        x.setTextColor(0xFF1F3B4D);
        x.setPadding(0, (int) (16 * dp), 0, (int) (24 * dp));
        Button si = new Button(this);
        si.setText("Dar permiso");
        si.setOnClickListener(v -> pedirAcceso());
        Button no = new Button(this);
        no.setText("Ahora no");
        no.setOnClickListener(v -> {
            Copia.prefs(this).edit().putLong("aviso_hasta", System.currentTimeMillis() + 3 * 86400_000L).apply();   // se vuelve a ofrecer en 3 días
            aviso.setVisibility(View.GONE);
        });
        l.addView(t);
        l.addView(x);
        l.addView(si);
        l.addView(no);
        l.setVisibility(View.GONE);
        return l;
    }

    private void pedirAcceso() {
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:" + getPackageName())));
            } catch (ActivityNotFoundException e) {
                startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION));
            }
        } else {
            // en la fila, como los demás: si se cruzara con otro diálogo, Android lo negaría sin preguntar
            pedirSistema(new String[]{Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE}, PIDE_LEER, null);
        }
    }

    private void revisarAcceso() {
        boolean tiene = Copia.tieneAcceso(this);
        boolean ofrecer = !tiene && System.currentTimeMillis() > Copia.prefs(this).getLong("aviso_hasta", 0);
        aviso.setVisibility(ofrecer ? View.VISIBLE : View.GONE);
        if (Copia.token(this) != null) {
            Copia.programar(this, true);   // avisos cada 15 min; con el permiso de archivos, también la copia (al abrir, si hay WiFi)
            // cada diálogo de permisos pasa por onResume: no se pregunta al servidor más de una vez cada 20 s (salvo si cambió el permiso de archivos)
            long ahora = SystemClock.elapsedRealtime();
            if (sondeoEn > 0 && ahora - sondeoEn < 20_000 && tiene == sondeoConAcceso) return;
            sondeoEn = ahora;
            sondeoConAcceso = tiene;
            new Thread(() -> {
                // por separado, como en CopiaJob: si los avisos fallan (red, 5xx, un Hub viejo sin la ruta), las peticiones se miran igual
                try {
                    Avisos.recoger(this);   // 2.5: los avisos de Zazu que llegaron con la app cerrada
                } catch (Copia.SinToken e) {
                    Copia.prefs(this).edit().remove("token").apply();
                    return;
                } catch (Exception ignorado) {
                    // sin red: ya se mirará
                }
                try {
                    if (tiene) Peticiones.sondear(this, this);
                } catch (Copia.SinToken e) {
                    Copia.prefs(this).edit().remove("token").apply();
                } catch (Exception ignorado) {
                    // sin red: ya se mirará
                }
            }, "zazu-sondeo").start();
        }
    }

    /**
     * Token de dispositivo: se pide UNA vez con la sesión de Fran del WebView (cookie hub_s + X-Hub) y queda en el almacén privado de la app.
     * Con él trabaja la copia en segundo plano sin depender de la sesión (que caduca a los 14 días). Las invitadas reciben 403: no se guarda nada.
     */
    private void pedirToken() {
        if (Copia.token(this) != null || pidiendoToken) return;
        String g = CookieManager.getInstance().getCookie(BASE);
        if (g == null || !g.contains("hub_s=")) return;
        pidiendoToken = true;
        new Thread(() -> {
            try {
                HttpURLConnection h = Copia.abrir(null, "/api/movil/token", "POST");
                h.setRequestProperty("Cookie", g);
                h.setRequestProperty("X-Hub", "1");
                h.setRequestProperty("Content-Type", "application/json");
                byte[] b = new JSONObject().put("nombre", Build.MANUFACTURER + " " + Build.MODEL).toString().getBytes("UTF-8");
                h.setFixedLengthStreamingMode(b.length);
                try (OutputStream o = h.getOutputStream()) {
                    o.write(b);
                }
                int st = h.getResponseCode();
                String r = Copia.leer(h);
                if (st == 200) {
                    Copia.prefs(this).edit().putString("token", new JSONObject(r).getString("token")).apply();
                    runOnUiThread(this::revisarAcceso);
                }
            } catch (Exception ignorado) {
                // sin red: se intenta en la próxima carga
            }
            pidiendoToken = false;
        }, "zazu-token").start();
    }

    /** Si se abrió tocando el aviso de una petición de Zazu, enseña su diálogo (Permitir / Rechazar). Del aviso solo se usa el id:
     *  la petición se vuelve a leer del servidor, así otra app que abra esta pantalla no puede colar sus propios argumentos. */
    private void peticionDelAviso(Intent in) {
        String id = in != null ? in.getStringExtra(Peticiones.EXTRA) : null;
        if (id == null || !id.matches("[0-9a-f]{12}") || Copia.token(this) == null) return;
        in.removeExtra(Peticiones.EXTRA);
        new Thread(() -> {
            try {
                HttpURLConnection h = Copia.abrir(Copia.token(this), "/api/movil/peticiones/" + id, "GET");
                int st = h.getResponseCode();
                JSONObject p = new JSONObject(Copia.leer(h));
                if (st == 200 && "pendiente".equals(p.optString("estado"))) runOnUiThread(() -> Peticiones.dialogo(this, p));
                else runOnUiThread(() -> Toast.makeText(this, "Esa petición de Zazu ya no está pendiente.", Toast.LENGTH_LONG).show());
            } catch (Exception ignorado) {
                // sin red: no se enseña nada
            }
        }, "zazu-peticion").start();
    }

    /** Abre la web; si llega un texto o un enlace desde «Compartir», lo pasa a la web como ya hace la web instalada. */
    private void cargar(Intent in) {
        Uri enlace = in != null ? in.getData() : null;
        if (esVueltaDeGoogle(in)) {   // https://holazazu.app/app/entrar?c=… (App Link) o zazu://entrar?c=… (respaldo)
            // 2.5 vuelta de «Conectar con Google»: g=<código> o e=<motivo>. El servidor solo guarda los permisos con la sesión de quien empezó
            String g = enlace.getQueryParameter("g"), e = enlace.getQueryParameter("e");
            if (g != null && g.matches("[A-Za-z0-9_-]{43}")) {
                web.loadUrl(BASE + "/app/google?g=" + g);
                return;
            }
            if (e != null && e.matches("[a-z_]{1,20}")) {
                web.loadUrl(BASE + "/app/google?e=" + e);
                return;
            }
            // el secreto solo se gasta con un código bien formado: zazu:// lo puede abrir cualquier web o app, y uno vacío cortaba el login en curso
            String c = enlace.getQueryParameter("c");
            String v = c != null && c.matches("[A-Za-z0-9_-]{43}") ? secretoPendiente() : null;
            if (v != null) {
                web.loadUrl(BASE + "/app/entrar?c=" + c + "&v=" + v);   // el servidor canjea el código con el secreto y deja la sesión aquí
            } else {
                web.loadUrl(conBuster(Uri.parse(BASE + "/")));   // sin secreto (otra vuelta, o ya usado): la web dice si hay sesión o enseña el login
            }
            return;
        }
        if (in != null && Intent.ACTION_VIEW.equals(in.getAction()) && enlace != null && esDeZazu(enlace)) {   // un enlace a Zazu (https y el host y puerto de BASE: nunca javascript: ni otro esquema)
            web.loadUrl(conBuster(enlace));
            return;
        }
        Uri.Builder u = Uri.parse(BASE + "/").buildUpon();
        if (in != null && Intent.ACTION_SEND.equals(in.getAction()) && "text/plain".equals(in.getType())) {
            String texto = in.getStringExtra(Intent.EXTRA_TEXT), titulo = in.getStringExtra(Intent.EXTRA_SUBJECT);
            if (titulo != null) u.appendQueryParameter("title", titulo.length() > 300 ? titulo.substring(0, 300) : titulo);
            if (texto != null) u.appendQueryParameter("text", texto.length() > 4000 ? texto.substring(0, 4000) : texto);
        } else {
            u.appendQueryParameter("tab", "inicio");
        }
        web.loadUrl(conBuster(u.build()));
    }

    /** Añade (o renueva) el parámetro anti-caché «?_v=<ms>» a la URL del DOCUMENTO, conservando los demás parámetros (tab, title/text/url del compartir, conv…)
     *  y el #fragmento. Cada carga pide así un HTML distinto, que ni Cloudflare ni el WebView tienen cacheado; los /assets con hash van aparte y sí se cachean. */
    private static String conBuster(Uri u) {
        Uri.Builder b = u.buildUpon().clearQuery();
        for (String k : u.getQueryParameterNames()) {
            if ("_v".equals(k)) continue;
            for (String v : u.getQueryParameters(k)) b.appendQueryParameter(k, v);
        }
        b.appendQueryParameter("_v", Long.toString(System.currentTimeMillis()));
        return b.build().toString();
    }

    // ---------- 2.1: «Entrar con Google» en Chrome y vuelta a la app ----------
    private static final long SECRETO_MS = 10 * 60_000L;   // el login en Chrome tiene 10 minutos; el código del servidor, 2

    private boolean esVueltaDeGoogle(Intent in) {
        Uri u = in != null && Intent.ACTION_VIEW.equals(in.getAction()) ? in.getData() : null;
        if (u == null) return false;
        return ("https".equals(u.getScheme()) && "holazazu.app".equals(u.getHost()) && "/app/entrar".equals(u.getPath()))
                || ("zazu".equals(u.getScheme()) && "entrar".equals(u.getHost()));
    }

    /** Secreto de 32 bytes que solo conoce la app: al servidor va su sha256 (ch) y, a la vuelta, el secreto (v). Sin él el código no vale. */
    private void entrarConGoogle() {
        byte[] b = new byte[32];
        new java.security.SecureRandom().nextBytes(b);
        String v = android.util.Base64.encodeToString(b, android.util.Base64.URL_SAFE | android.util.Base64.NO_PADDING | android.util.Base64.NO_WRAP);
        String ch;
        try {
            ch = android.util.Base64.encodeToString(java.security.MessageDigest.getInstance("SHA-256").digest(v.getBytes("US-ASCII")),
                    android.util.Base64.URL_SAFE | android.util.Base64.NO_PADDING | android.util.Base64.NO_WRAP);
        } catch (Exception e) {
            return;
        }
        getSharedPreferences("entrar", MODE_PRIVATE).edit().putString("v", v).putLong("t", System.currentTimeMillis()).commit();
        pestana(Uri.parse(BASE + "/oauth/google/start").buildUpon().appendQueryParameter("mode", "app").appendQueryParameter("ch", ch).build());
    }

    /**
     * 2.5 «Conectar con Google» (Fran e invitadas): con la sesión del WebView se pide al servidor un billete de un solo uso (5 min, atado
     * a tu email) y se abre Google en una Custom Tab con él. Al terminar, el App Link /app/entrar?g=… trae de vuelta la app, que confirma
     * en su WebView (con tu sesión) y enseña «Cuenta de Google conectada». Solo se abre la ruta fija /oauth/google/start de Zazu.
     */
    private void conectarGoogle(String email) {
        String galletas = CookieManager.getInstance().getCookie(BASE);
        if (galletas == null || !galletas.contains("hub_s=")) {
            Toast.makeText(this, "Entra primero en tu cuenta de Zazu.", Toast.LENGTH_LONG).show();
            return;
        }
        long ahora = SystemClock.elapsedRealtime();
        if (googleEn > 0 && ahora - googleEn < 4000) return;   // dos toques seguidos: una sola pestaña y un solo billete
        googleEn = ahora;
        Toast.makeText(this, "Abriendo Google…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            String error = "No pude empezar la conexión con Google. Revisa que tengas internet y vuelve a probar.";
            try {
                HttpURLConnection h = Copia.abrir(null, "/api/google/enlace-app", "POST");
                h.setRequestProperty("Cookie", galletas);
                h.setRequestProperty("X-Hub", "1");
                h.setRequestProperty("Content-Type", "application/json");
                JSONObject cuerpo = new JSONObject();
                if (email != null) cuerpo.put("email", email);
                byte[] b = cuerpo.toString().getBytes("UTF-8");
                h.setFixedLengthStreamingMode(b.length);
                try (OutputStream o = h.getOutputStream()) {
                    o.write(b);
                }
                int st = h.getResponseCode();
                JSONObject r = new JSONObject(Copia.leer(h));
                String url = r.optString("url");
                if (st == 200 && url.startsWith("/oauth/google/start?")) {
                    runOnUiThread(() -> pestana(Uri.parse(BASE + url)));
                    return;
                }
                if (r.optString("error").length() > 0) error = r.optString("error");
            } catch (Exception ignorado) {
                // sin red: se dice abajo
            }
            final String t = error;
            runOnUiThread(() -> Toast.makeText(this, t, Toast.LENGTH_LONG).show());
        }, "zazu-google").start();
    }

    /** Abre una página de Zazu en una Custom Tab (Chrome) y no en el WebView: Google no deja hacer OAuth dentro de un WebView. */
    private void pestana(Uri u) {
        // Custom Tab sin librerías: basta el extra de sesión (vacío) del protocolo de Custom Tabs; si el navegador no lo entiende, se abre normal
        Intent i = new Intent(Intent.ACTION_VIEW, u);
        Bundle extras = new Bundle();
        extras.putBinder("android.support.customtabs.extra.SESSION", null);
        i.putExtras(extras);
        i.putExtra("android.support.customtabs.extra.TOOLBAR_COLOR", 0xFFFAF9F5);
        try {
            startActivity(i);
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "Necesitas Chrome u otro navegador para Google", Toast.LENGTH_LONG).show();
        }
    }

    /** El secreto del último «Entrar con Google», una sola vez y si no es viejo. */
    private String secretoPendiente() {
        android.content.SharedPreferences p = getSharedPreferences("entrar", MODE_PRIVATE);
        String v = p.getString("v", null);
        long t = p.getLong("t", 0);
        p.edit().clear().commit();
        return v != null && System.currentTimeMillis() - t < SECRETO_MS ? v : null;
    }

    private void abrirFuera(Uri u) {
        if (u == null || u.getScheme() == null || !ESQUEMAS_FUERA.contains(u.getScheme())) return;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "No encuentro con qué abrir este enlace", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onNewIntent(Intent in) {
        super.onNewIntent(in);
        setIntent(in);
        if (Intent.ACTION_SEND.equals(in.getAction()) || Intent.ACTION_VIEW.equals(in.getAction())) {
            cargar(in);
            pausadoEn = 0;   // ya se carga de nuevo: que onResume no la recargue (pediría otra vez el mismo código de un solo uso de /app/google o /app/entrar)
        }
        peticionDelAviso(in);
    }

    @Override
    protected void onActivityResult(int codigo, int resultado, Intent datos) {
        if (codigo == PIDE_ARCHIVO && subida != null) {
            subida.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultado, datos));
            subida = null;
            return;
        }
        super.onActivityResult(codigo, resultado, datos);
    }

    @Override
    public void onRequestPermissionsResult(int codigo, String[] permisos, int[] resultados) {
        if (codigo == PIDE_LEER) {
            enCurso = null;
            revisarAcceso();
            siguientePedido();
            return;
        }
        Pedido p = enCurso;
        enCurso = null;
        boolean rapido = p != null && SystemClock.elapsedRealtime() - p.desde < 600;   // contestó sin enseñar el diálogo
        boolean bloqueado = false;
        android.content.SharedPreferences prefs = Copia.prefs(this);
        android.content.SharedPreferences.Editor ed = prefs.edit();
        for (int i = 0; i < permisos.length && i < resultados.length; i++) {
            boolean yaPedido = prefs.getBoolean("pedido_" + permisos[i], false);   // la primera vez nunca es «para siempre»
            ed.putBoolean("pedido_" + permisos[i], true);
            if (resultados[i] == PackageManager.PERMISSION_GRANTED) {
                ed.remove("bloq_" + permisos[i]);
                continue;
            }
            boolean ahora = shouldShowRequestPermissionRationale(permisos[i]);
            boolean antes = p != null && i < p.razonAntes.length && p.razonAntes[i];
            // «negado para siempre»: Android ya no lo vuelve a preguntar (lo negó dos veces o marcó «No volver a preguntar»).
            // Lo rápido solo cuenta si ya se había preguntado antes: si no, era alguien que cerró el diálogo deprisa.
            if (!ahora && (antes || (rapido && yaPedido))) {
                ed.putBoolean("bloq_" + permisos[i], true);
                bloqueado = true;
            } else if (ahora) ed.remove("bloq_" + permisos[i]);
        }
        ed.apply();
        // lo que espera la web se contesta en cuanto su permiso ya no está en la fila (da igual quién lo pidió: el puente o la propia web)
        if (pendiente != null) {
            boolean todos = true, falta = false;
            List<String> recursos = new ArrayList<>();
            for (String x : pendiente.getResources()) {
                String perm = PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(x) ? Manifest.permission.RECORD_AUDIO
                        : PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(x) ? Manifest.permission.CAMERA : null;
                if (perm == null) continue;
                recursos.add(x);
                if (checkSelfPermission(perm) != PackageManager.PERMISSION_GRANTED) todos = false;
                if (pidiendo(perm)) falta = true;
            }
            if (!falta) {
                if (todos && !recursos.isEmpty()) pendiente.grant(recursos.toArray(new String[0]));
                else pendiente.deny();
                pendiente = null;
            }
        }
        if (geoCb != null && !pidiendo(Manifest.permission.ACCESS_COARSE_LOCATION)) {
            boolean si = checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
            geoCb.invoke(geoOrigen, si, si);
            geoCb = null;
        }
        if (p != null) {
            // Android no enseñó nada: se explica cómo darlo en Ajustes. Solo si lo pidió la web por su cuenta (getUserMedia):
            // cuando lo pide el puente, la web ya enseña su propia guía con «Abrir ajustes» y saldrían dos explicaciones.
            if (bloqueado && rapido && p.codigo == PIDE_PERMISOS) explicarAjustes(p.tipo);
            avisarPermiso(p.tipo);
            esperanTipo.remove(p.tipo);
        }
        for (java.util.Iterator<String> it = esperanTipo.iterator(); it.hasNext(); ) {   // los que esperaban a que su permiso saliera de la fila
            String t = it.next(), perm = permisoDe(t);
            if (perm != null && pidiendo(perm)) continue;
            it.remove();
            avisarPermiso(t);
        }
        avisarWeb();
        siguientePedido();
    }

    // ---------- 2.4: permisos en fila y puente con la web (window.ZazuNativo) ----------

    private void pedirSistema(String[] permisos, int codigo, String tipo) {
        cola.add(new Pedido(permisos, codigo, tipo));
        siguientePedido();
    }

    private void siguientePedido() {
        if (enCurso != null || cola.isEmpty() || isFinishing()) return;
        enCurso = cola.poll();
        enCurso.razonAntes = new boolean[enCurso.permisos.length];
        for (int i = 0; i < enCurso.permisos.length; i++) enCurso.razonAntes[i] = shouldShowRequestPermissionRationale(enCurso.permisos[i]);
        enCurso.desde = SystemClock.elapsedRealtime();
        requestPermissions(enCurso.permisos, enCurso.codigo);
    }

    /** Ya está en la fila (o preguntándose) este permiso: no se pide dos veces. */
    private boolean pidiendo(String permiso) {
        if (enCurso != null && Arrays.asList(enCurso.permisos).contains(permiso)) return true;
        for (Pedido x : cola) if (Arrays.asList(x.permisos).contains(permiso)) return true;
        return false;
    }

    private static String permisoDe(String tipo) {
        switch (tipo) {
            case "notificaciones": return Manifest.permission.POST_NOTIFICATIONS;
            case "ubicacion": return Manifest.permission.ACCESS_COARSE_LOCATION;
            case "microfono": return Manifest.permission.RECORD_AUDIO;
            case "camara": return Manifest.permission.CAMERA;
            default: return null;
        }
    }

    /** "granted" | "denied" (negado para siempre: solo se arregla en Ajustes) | "prompt" (se puede preguntar). */
    private String estadoDe(String permiso) {
        if (checkSelfPermission(permiso) == PackageManager.PERMISSION_GRANTED) return "granted";
        if (Copia.prefs(this).getBoolean("bloq_" + permiso, false) && !shouldShowRequestPermissionRationale(permiso)) return "denied";
        return "prompt";
    }

    private boolean avisosActivos() {
        return getSystemService(NotificationManager.class).areNotificationsEnabled();
    }

    private String estadoTipo(String tipo) {
        if ("notificaciones".equals(tipo)) {
            if (avisosActivos()) return "granted";
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
                return estadoDe(Manifest.permission.POST_NOTIFICATIONS);
            return "denied";   // el permiso está, pero las notificaciones de la app están apagadas en Ajustes
        }
        return estadoDe(permisoDe(tipo));
    }

    /** El interruptor general de «Ubicación» del móvil. */
    @SuppressWarnings("deprecation")   // LOCATION_MODE solo se usa en Android 8 (antes de isLocationEnabled)
    private boolean ubicacionEncendida() {
        if (Build.VERSION.SDK_INT >= 28) {
            LocationManager lm = getSystemService(LocationManager.class);
            return lm != null && lm.isLocationEnabled();
        }
        return Settings.Secure.getInt(getContentResolver(), Settings.Secure.LOCATION_MODE, Settings.Secure.LOCATION_MODE_OFF) != Settings.Secure.LOCATION_MODE_OFF;
    }

    private String estadoJson() {
        try {
            JSONObject o = new JSONObject();
            for (String t : TIPOS) o.put(t, estadoTipo(t));
            o.put("ubicacionSistema", ubicacionEncendida() ? "on" : "off");
            return o.toString();
        } catch (Exception e) {
            return "{}";
        }
    }

    /** La página que se ve es de Zazu (mismo esquema, servidor y puerto que BASE). */
    /** ¿Es una dirección de Zazu de verdad? El mismo esquema, host y puerto que BASE (un intent con javascript://holazazu.app/… tiene ese host). */
    private boolean esDeZazu(Uri x) {
        Uri b = Uri.parse(BASE);
        return x != null && hostBase.equals(x.getHost()) && b.getScheme().equals(x.getScheme()) && b.getPort() == x.getPort();
    }

    private volatile String imagenPegada;   // JSON {"tipo","imagen"} que espera a que la web lo recoja (ZazuNativo.imagenPegada)

    /** Una imagen que inserta el teclado: se lee en segundo plano y se avisa a la web para que la adjunte. */
    private boolean recibirImagen(InputContentInfo contenido, int flags) {
        if (!esNuestra()) return false;
        String tipo = contenido.getDescription().getMimeTypeCount() > 0 ? contenido.getDescription().getMimeType(0) : "image/png";
        if (!tipo.startsWith("image/")) return false;
        try {
            if ((flags & InputConnection.INPUT_CONTENT_GRANT_READ_URI_PERMISSION) != 0) contenido.requestPermission();
        } catch (Exception e) {
            return false;
        }
        new Thread(() -> {
            JSONObject o = leerImagen(contenido.getContentUri(), tipo);
            contenido.releasePermission();
            imagenPegada = o.toString();
            runOnUiThread(() -> js("window.dispatchEvent(new Event('zazu-imagen-pegada'))"));
        }).start();
        return true;
    }

    /** Los bytes de una imagen (content://) en base64, o {"error"} si no se puede o es demasiado grande. */
    private JSONObject leerImagen(Uri u, String tipo) {
        JSONObject o = new JSONObject();
        try (InputStream in = getContentResolver().openInputStream(u)) {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while (in != null && (n = in.read(buf)) > 0 && b.size() <= MAX_PEGAR) b.write(buf, 0, n);
            if (b.size() > MAX_PEGAR) o.put("error", "La imagen es demasiado grande para pegarla. Usa el clip.");
            else if (b.size() == 0) o.put("error", "La imagen está vacía");
            else { o.put("tipo", tipo); o.put("imagen", Base64.encodeToString(b.toByteArray(), Base64.NO_WRAP)); }
        } catch (Exception e) {
            try { o.put("error", "No pude leer la imagen"); } catch (Exception ignorado) { }
        }
        return o;
    }

    private boolean esNuestra() {
        String u = urlActual;
        if (u == null) return false;
        Uri x = Uri.parse(u), b = Uri.parse(BASE);
        return hostBase.equals(x.getHost()) && b.getScheme().equals(x.getScheme()) && b.getPort() == x.getPort();
    }

    /** Ejecuta JS solo en páginas de Zazu (el texto es siempre fijo: tipos y estados de listas cerradas). */
    private void js(String codigo) {
        if (web != null && esNuestra()) web.evaluateJavascript(codigo, null);
    }

    private void avisarPermiso(String tipo) {
        if (tipo == null || !TIPOS.contains(tipo)) return;
        js("window.dispatchEvent(new CustomEvent('zazu-permiso',{detail:{tipo:'" + tipo + "',estado:'" + estadoTipo(tipo) + "'}}))");
    }

    private void avisarWeb() {
        js("window.dispatchEvent(new Event('zazu-permisos'))");
    }

    private void pedirTipo(String tipo) {
        if ("notificaciones".equals(tipo)) {
            if (avisosActivos()) avisarPermiso(tipo);
            else if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                if (!pidiendo(Manifest.permission.POST_NOTIFICATIONS)) pedirSistema(new String[]{Manifest.permission.POST_NOTIFICATIONS}, PIDE_PUENTE, tipo);
                else esperanTipo.add(tipo);
            } else abrirAjustesDe(tipo);   // apagadas en Ajustes: no hay diálogo que valga, se abren sus ajustes
            return;
        }
        String perm = permisoDe(tipo);
        if (checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED) avisarPermiso(tipo);
        else if (!pidiendo(perm)) pedirSistema(new String[]{perm}, PIDE_PUENTE, tipo);
        else esperanTipo.add(tipo);   // ya se está preguntando (p. ej. lo pidió getUserMedia): se le contesta al acabar
    }

    private Intent fichaApp() {
        return new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName()));
    }

    /** Abre la pantalla de Ajustes que toca. Solo pantallas fijas del sistema o WhatsApp: nunca una URL que llegue de la web. */
    private void abrirAjustesDe(String tipo) {
        Intent i;
        switch (tipo) {
            case "notificaciones":
                i = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName());
                break;
            case "ubicacion":
                i = ubicacionEncendida() ? fichaApp() : new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS);
                break;
            case "ubicacion_sistema":
                i = new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS);
                break;
            case "microfono":
            case "camara":
            case "app":
                i = fichaApp();
                break;
            case "whatsapp":
                abrirWhatsApp();
                return;
            default:
                return;
        }
        if (TIPOS.contains(tipo)) tipoAlVolver = tipo;
        else if ("ubicacion_sistema".equals(tipo)) tipoAlVolver = "ubicacion";
        try {
            startActivity(i);
        } catch (ActivityNotFoundException e) {
            try {
                startActivity(fichaApp());
            } catch (ActivityNotFoundException e2) {
                Toast.makeText(this, "No pude abrir los Ajustes. Ve a Ajustes › Aplicaciones › HolaZazu.", Toast.LENGTH_LONG).show();
            }
        }
    }

    private void abrirWhatsApp() {
        for (String paquete : new String[]{"com.whatsapp", "com.whatsapp.w4b"}) {
            Intent i = getPackageManager().getLaunchIntentForPackage(paquete);
            if (i == null) continue;
            try {
                startActivity(i);
                return;
            } catch (ActivityNotFoundException ignorado) {
                // se prueba el siguiente
            }
        }
        Toast.makeText(this, "No tienes WhatsApp en este móvil.", Toast.LENGTH_LONG).show();
    }

    /** Android ya no enseña el diálogo de ese permiso: se explica dónde darlo y se ofrece el botón que lleva allí. */
    private void explicarAjustes(String tipo) {
        if (isFinishing() || tipo == null) return;
        String que, pasos;
        switch (tipo) {
            case "microfono": que = "el micrófono"; pasos = "Permisos › Micrófono › «Permitir solo mientras se usa la app»"; break;
            case "camara": que = "la cámara"; pasos = "Permisos › Cámara › «Permitir solo mientras se usa la app»"; break;
            case "ubicacion": que = "tu ubicación"; pasos = "Permisos › Ubicación › «Permitir solo mientras se usa la app»"; break;
            case "notificaciones": que = "mandarte avisos"; pasos = "activa «Mostrar notificaciones»"; break;
            default: return;
        }
        new AlertDialog.Builder(this)
                .setTitle("Falta un permiso")
                .setMessage("Android no deja a HolaZazu usar " + que + " y ya no lo vuelve a preguntar.\n\n"
                        + "Pulsa «Abrir Ajustes» y ahí: " + pasos + ". Luego vuelve a la app.")
                .setPositiveButton("Abrir Ajustes", (d, w) -> abrirAjustesDe(tipo))
                .setNegativeButton("Ahora no", null)
                .show();
    }

    /** window.ZazuNativo. Sus métodos llegan en otro hilo: solo leen estados y, en el hilo de la interfaz, piden permisos o abren Ajustes. */
    private static final int MAX_PEGAR = 15_000_000;   // bytes de una imagen pegada (la subida admite más, pero el puente va en texto)

    private final class Puente {
        @JavascriptInterface
        public String version() {
            return esNuestra() ? BuildConfig.VERSION_NAME : "";
        }

        @JavascriptInterface
        public String estado() {
            return esNuestra() ? estadoJson() : "{}";
        }

        @JavascriptInterface
        public void pedir(String tipo) {
            if (!esNuestra() || tipo == null || !TIPOS.contains(tipo)) return;
            runOnUiThread(() -> {
                if (esNuestra()) pedirTipo(tipo);
            });
        }

        /** El portapapeles para el botón «Pegar»: el WebView no deja a la web leerlo (navigator.clipboard.read falla).
         *  Devuelve {"texto": "...", "tipo": "image/png", "imagen": "<base64>"} (lo que haya) o {"error": "..."}. */
        @JavascriptInterface
        public String portapapeles() {
            JSONObject o = new JSONObject();
            if (!esNuestra()) return "{}";
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                ClipData cd = cm == null ? null : cm.getPrimaryClip();
                if (cd == null || cd.getItemCount() == 0) return o.toString();
                ClipData.Item it = cd.getItemAt(0);
                Uri u = it.getUri();
                String tipo = u != null ? getContentResolver().getType(u) : null;
                if (u != null && (tipo == null || !tipo.startsWith("image/")) && cd.getDescription().hasMimeType("image/*"))
                    tipo = cd.getDescription().filterMimeTypes("image/*")[0];   // algunos portapapeles no dicen el tipo del archivo
                if (u != null && tipo != null && tipo.startsWith("image/")) return leerImagen(u, tipo.contains("*") ? "image/png" : tipo).toString();
                CharSequence t = it.coerceToText(MainActivity.this);
                if (t != null && t.length() > 0) o.put("texto", t.toString());
            } catch (Exception e) {
                try { o.put("error", "No pude leer el portapapeles"); } catch (Exception ignorado) { }
            }
            return o.toString();
        }

        /** La imagen que acaba de insertar el teclado (una sola vez). */
        @JavascriptInterface
        public String imagenPegada() {
            String x = imagenPegada;
            imagenPegada = null;
            return esNuestra() && x != null ? x : "{}";
        }

        @JavascriptInterface
        public void abrirAjustes(String tipo) {
            if (!esNuestra() || tipo == null) return;
            runOnUiThread(() -> {
                if (esNuestra()) abrirAjustesDe(tipo);
            });
        }
    }

    @Override
    @SuppressWarnings("deprecation")   // la app es Activity simple; el gesto atrás nuevo es para targetSdk 35
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onSaveInstanceState(Bundle estado) {
        super.onSaveInstanceState(estado);
        web.saveState(estado);
    }

    @Override
    protected void onPause() {
        CookieManager.getInstance().flush();   // la sesión llega a disco: al volver a abrir la app sigues dentro
        pausadoEn = SystemClock.elapsedRealtime();
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        revisarAcceso();   // al volver de Ajustes con el permiso dado, se quita el aviso y empieza la copia
        // 2.4: si Android ya no da la ubicación, el WebView no se queda con un «sí» viejo
        if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED)
            android.webkit.GeolocationPermissions.getInstance().clearAll();
        avisarWeb();   // la web vuelve a mirar los permisos (p. ej. al volver de Ajustes)
        if (tipoAlVolver != null) {
            avisarPermiso(tipoAlVolver);
            tipoAlVolver = null;
        }
        // la app estuvo un buen rato de fondo: la página que se ve puede ser vieja, así que se vuelve a pedir al servidor (un permiso o un selector de archivos duran segundos y no la recargan)
        // se recarga con un buster NUEVO sobre la misma URL (misma pestaña/conversación), para saltarse la copia vieja del WebView y de Cloudflare; si no hay URL de Zazu, un reload normal
        if (pausadoEn > 0 && SystemClock.elapsedRealtime() - pausadoEn > BuildConfig.RECARGA_MS) {
            String url = web.getUrl();
            if (url != null && url.startsWith(BASE)) web.loadUrl(conBuster(Uri.parse(url)));
            else web.reload();
        }
        pausadoEn = 0;
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
