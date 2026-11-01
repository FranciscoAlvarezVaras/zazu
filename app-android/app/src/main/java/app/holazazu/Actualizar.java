package app.holazazu;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.webkit.CookieManager;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.security.MessageDigest;

/**
 * Se actualiza sola: al abrir, pregunta al servidor qué versión hay publicada (GET /api/movil/apk-version, va por /api/: Cloudflare no la guarda).
 * Si es mayor que la instalada: «Hay una versión nueva» → la baja, comprueba su sha256 y su versión, y se la da al instalador del sistema
 * (PackageInstaller). Android enseña su pantalla y Fran confirma; el sistema exige que vaya firmada con la MISMA llave.
 */
final class Actualizar {
    private static boolean preguntado = false;

    private Actualizar() {}

    static void comprobar(Activity a) {
        if (preguntado) return;
        preguntado = true;
        new Thread(() -> {
            try {
                HttpURLConnection h = conectar(a, "/api/movil/apk-version");
                if (h.getResponseCode() != 200) {
                    Copia.leer(h);
                    return;
                }
                JSONObject v = new JSONObject(Copia.leer(h));
                if (v.getInt("versionCode") <= BuildConfig.VERSION_CODE) return;
                a.runOnUiThread(() -> {
                    if (a.isFinishing()) return;
                    new AlertDialog.Builder(a)
                            .setTitle("Hay una versión nueva")
                            .setMessage("Zazu " + v.optString("versionName") + " está lista (tienes la " + BuildConfig.VERSION_NAME + "). ¿La instalo ahora?")
                            .setPositiveButton("Instalar", (d, w) -> instalar(a, v))
                            .setNegativeButton("Luego", null)
                            .show();
                });
            } catch (Exception ignorado) {
                // sin red: ya preguntará la próxima vez
            }
        }, "zazu-version").start();
    }

    /** Con el token si ya lo tiene; si no, con la sesión del WebView (GET no necesita X-Hub). */
    private static HttpURLConnection conectar(Context c, String ruta) throws IOException {
        String tok = Copia.token(c);
        HttpURLConnection h = Copia.abrir(tok, ruta, "GET");
        if (tok == null) {
            String g = CookieManager.getInstance().getCookie(BuildConfig.URL_BASE);
            if (g != null) h.setRequestProperty("Cookie", g);
        }
        return h;
    }

    private static void instalar(Activity a, JSONObject v) {
        if (Build.VERSION.SDK_INT >= 26 && !a.getPackageManager().canRequestPackageInstalls()) {
            Toast.makeText(a, "Activa «Permitir de esta fuente» para Zazu y vuelve: te lo preguntaré otra vez.", Toast.LENGTH_LONG).show();
            preguntado = false;
            a.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + a.getPackageName())));
            return;
        }
        Toast.makeText(a, "Bajando la versión nueva…", Toast.LENGTH_SHORT).show();
        Context c = a.getApplicationContext();
        new Thread(() -> {
            String error = null;
            try {
                File apk = new File(c.getCacheDir(), "zazu-nueva.apk");
                HttpURLConnection h = conectar(c, v.optString("url", "/api/movil/apk"));
                if (h.getResponseCode() != 200) throw new IOException("el servidor dijo " + h.getResponseCode());
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                try (InputStream in = h.getInputStream(); OutputStream out = new FileOutputStream(apk)) {
                    byte[] b = new byte[64 * 1024];
                    int n;
                    while ((n = in.read(b)) > 0) {
                        out.write(b, 0, n);
                        md.update(b, 0, n);
                    }
                } finally {
                    h.disconnect();
                }
                StringBuilder hex = new StringBuilder();
                for (byte x : md.digest()) hex.append(String.format("%02x", x));
                if (!hex.toString().equals(v.optString("sha256"))) throw new IOException("la descarga no coincide (sha256)");
                PackageInfo pi = c.getPackageManager().getPackageArchiveInfo(apk.getPath(), 0);
                if (pi == null || !c.getPackageName().equals(pi.packageName) || codigoVersion(pi) <= BuildConfig.VERSION_CODE)
                    throw new IOException("el APK no es una versión nueva de Zazu");
                PackageInstaller pki = c.getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams sp = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                sp.setAppPackageName(c.getPackageName());
                int id = pki.createSession(sp);
                try (PackageInstaller.Session s = pki.openSession(id)) {
                    try (InputStream in = new FileInputStream(apk); OutputStream out = s.openWrite("zazu.apk", 0, apk.length())) {
                        byte[] b = new byte[64 * 1024];
                        int n;
                        while ((n = in.read(b)) > 0) out.write(b, 0, n);
                        s.fsync(out);
                    }
                    Intent fin = new Intent(c, Instalado.class);
                    int fl = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                    s.commit(PendingIntent.getBroadcast(c, id, fin, fl).getIntentSender());
                }
                apk.delete();
            } catch (Exception e) {
                error = e.getMessage();
            }
            if (error != null) {
                String t = "No pude actualizar: " + error;
                a.runOnUiThread(() -> Toast.makeText(c, t, Toast.LENGTH_LONG).show());
            }
        }, "zazu-actualizar").start();
    }

    /** getLongVersionCode es de Android 9: en 8.x lanzaba NoSuchMethodError (un Error, no lo atrapaba nadie) y se cerraba la app. */
    @SuppressWarnings("deprecation")
    private static long codigoVersion(PackageInfo pi) {
        return Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
    }

    /** Respuesta del instalador del sistema: si pide confirmación, se la enseña a Fran. */
    public static class Instalado extends BroadcastReceiver {
        @Override
        @SuppressWarnings("deprecation")   // getParcelableExtra viejo solo antes de Android 13
        public void onReceive(Context c, Intent in) {
            int st = in.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            if (st == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirmar = Build.VERSION.SDK_INT >= 33 ? in.getParcelableExtra(Intent.EXTRA_INTENT, Intent.class) : in.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirmar != null) c.startActivity(confirmar.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } else if (st != PackageInstaller.STATUS_SUCCESS) {
                Toast.makeText(c, "No se instaló: " + in.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE), Toast.LENGTH_LONG).show();
            }
        }
    }
}
