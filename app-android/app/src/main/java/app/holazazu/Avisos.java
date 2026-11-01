package app.holazazu;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;

/**
 * 2.5 Avisos de Zazu: recordatorios, rutinas, permisos de Zazu y alertas del servidor. El WebView no admite Web Push, así que el servidor
 * deja cada aviso en una cola para este móvil (movil.encolar_aviso) y la app la recoge con su token: al abrirse o volver, y cada 15 min
 * con el mismo trabajo que las peticiones (CopiaJob, JOB_SONDEO). Cada aviso sale como notificación del canal «Avisos de Zazu»;
 * tocarla abre la app en la página del aviso (siempre de Zazu: solo rutas que empiezan por «/»). Luego se confirman al servidor.
 * Sin duplicados: los ids ya enseñados se recuerdan aquí (por si la confirmación no llegó) y el mismo tag sustituye a la notificación anterior.
 */
final class Avisos {
    private static final String CANAL = "avisos";
    private static final String VISTOS = "avisos_vistos";   // ids ya enseñados, los últimos 200 (JSON)
    private static final Object CERROJO = new Object();      // al abrir la app y el trabajo de fondo pueden coincidir

    private Avisos() {}

    /** Recoge los avisos pendientes, los enseña y los confirma. Lanza Copia.SinToken si el servidor ya no reconoce el token. */
    static void recoger(Context c) throws IOException {
        String tok = Copia.token(c);
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        // con las notificaciones apagadas no se recogen: se quedan en el servidor (un día) hasta que Fran las active
        if (tok == null || !nm.areNotificationsEnabled()) return;
        canal(c);   // que «Avisos de Zazu» salga ya en los ajustes de la app, antes del primer aviso
        NotificationChannel ch = nm.getNotificationChannel(CANAL);
        if (ch != null && ch.getImportance() == NotificationManager.IMPORTANCE_NONE) return;   // apagó solo este canal: tampoco se recogen
        synchronized (CERROJO) {
            HttpURLConnection h = Copia.abrir(tok, "/api/movil/avisos", "GET");
            int st = h.getResponseCode();
            if (st == 401) throw new Copia.SinToken();
            String cuerpo = Copia.leer(h);
            if (st != 200) throw new IOException("el servidor dijo " + st);
            try {
                JSONArray as = new JSONObject(cuerpo).getJSONArray("avisos");
                if (as.length() == 0) return;
                JSONArray vistos = new JSONArray(Copia.prefs(c).getString(VISTOS, "[]"));
                java.util.Set<String> ya = new java.util.HashSet<>();
                for (int i = 0; i < vistos.length(); i++) ya.add(vistos.getString(i));
                JSONArray ids = new JSONArray();
                for (int i = 0; i < as.length() && i < 100; i++) {
                    JSONObject a = as.getJSONObject(i);
                    String id = a.optString("id");
                    if (!id.matches("[0-9a-f]{12}")) continue;
                    ids.put(id);
                    if (ya.add(id)) {
                        notificar(c, a);
                        vistos.put(id);
                    }
                }
                JSONArray quedan = new JSONArray();
                for (int i = Math.max(0, vistos.length() - 200); i < vistos.length(); i++) quedan.put(vistos.getString(i));
                Copia.prefs(c).edit().putString(VISTOS, quedan.toString()).commit();
                confirmar(tok, ids);
            } catch (org.json.JSONException e) {
                throw new IOException(e);
            }
        }
    }

    private static void confirmar(String tok, JSONArray ids) throws IOException, org.json.JSONException {
        HttpURLConnection h = Copia.abrir(tok, "/api/movil/avisos/confirmar", "POST");
        h.setRequestProperty("Content-Type", "application/json");
        byte[] b = new JSONObject().put("ids", ids).toString().getBytes(StandardCharsets.UTF_8);
        h.setFixedLengthStreamingMode(b.length);
        try (OutputStream o = h.getOutputStream()) {
            o.write(b);
        }
        h.getResponseCode();
        Copia.leer(h);   // si no llega, el servidor los vuelve a dar y aquí se saltan (ya vistos)
    }

    private static void canal(Context c) {
        NotificationChannel ch = new NotificationChannel(CANAL, "Avisos de Zazu", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Recordatorios, rutinas, permisos de Zazu y alertas del servidor");
        c.getSystemService(NotificationManager.class).createNotificationChannel(ch);
    }

    private static void notificar(Context c, JSONObject a) {
        canal(c);
        String url = a.optString("url", "/");
        if (!url.startsWith("/") || url.startsWith("//")) url = "/?tab=inicio";   // solo páginas de Zazu
        // explícito a MainActivity con un enlace de Zazu: cargar() lo abre en el WebView (conserva #aprobar=… de los permisos de Zazu)
        Intent abrir = new Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.URL_BASE + url), c, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        String tag = a.optString("tag", a.optString("id"));
        int n = ("aviso:" + tag).hashCode();   // mismo tag, misma notificación (como el web push): un recordatorio repetido no se acumula
        PendingIntent pi = PendingIntent.getActivity(c, n, abrir, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String cuerpo = a.optString("body");
        Notification.Builder b = new Notification.Builder(c, CANAL)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(a.optString("title", "Zazu"))
                .setContentText(cuerpo)
                .setStyle(new Notification.BigTextStyle().bigText(cuerpo))
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .setAutoCancel(true)
                .setContentIntent(pi);
        long t = a.optLong("t") * 1000, x = a.optLong("x") * 1000;
        if (t > 0) b.setWhen(t).setShowWhen(true);
        if (x > System.currentTimeMillis()) b.setTimeoutAfter(x - System.currentTimeMillis());   // caduca como en el servidor
        c.getSystemService(NotificationManager.class).notify(n, b.build());
    }
}
