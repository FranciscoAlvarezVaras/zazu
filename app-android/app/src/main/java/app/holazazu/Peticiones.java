package app.holazazu;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Peticiones de Zazu: tareas de ARCHIVOS que Fran pide a Zazu y que la app solo hace si Fran pulsa «Permitir» en el móvil.
 * La app las recoge del servidor (al abrirse y cada 15 min), avisa con una notificación o un diálogo «Zazu quiere: … — motivo»,
 * y al pulsar Permitir: avisa «aprobada» (si el servidor dice que ya caducó, no hace nada), la hace con Ordenes y manda el resultado
 * («subir» va a un trabajo de fondo, ver Copia.encargarSubida). Si el resultado no llega al servidor, se reenvía en el siguiente sondeo.
 * Lo que se hace es lo que Fran VIO en el diálogo (los argumentos guardados en ese momento), no lo que el servidor diga después.
 * Todo queda en un registro local (copia.db, tabla peticiones) que se ve en «Registro de Zazu» (mantén pulsado el icono).
 */
final class Peticiones {
    private static final String CANAL = "peticiones";
    static final String EXTRA = "peticion";

    private Peticiones() {}

    /** Mira si hay peticiones pendientes. Con la app abierta (a != null) enseña el diálogo; si no, una notificación por cada nueva. */
    static void sondear(Context c, Activity a) throws IOException {
        String tok = Copia.token(c);
        if (tok == null) return;
        reenviar(c);   // resultados de tareas ya hechas cuyo aviso no llegó
        HttpURLConnection h = Copia.abrir(tok, "/api/movil/peticiones", "GET");
        int st = h.getResponseCode();
        if (st == 401) throw new Copia.SinToken();
        String cuerpo = Copia.leer(h);
        if (st != 200) throw new IOException("el servidor dijo " + st);
        try {
            JSONArray ps = new JSONObject(cuerpo).getJSONArray("peticiones");
            Set<String> avisadas = new HashSet<>(Copia.prefs(c).getStringSet("avisadas", new HashSet<>()));
            for (int i = 0; i < ps.length(); i++) {
                JSONObject p = ps.getJSONObject(i);
                if (legible(p) == null) continue;   // un tipo que esta versión no conoce: no se enseña ni se hace
                if (a != null) {
                    a.runOnUiThread(() -> dialogo(a, p));
                } else if (avisadas.add(p.getString("id"))) {
                    notificar(c, p);
                }
            }
            if (avisadas.size() > 200) avisadas.clear();
            Copia.prefs(c).edit().putStringSet("avisadas", avisadas).apply();
        } catch (org.json.JSONException e) {
            throw new IOException(e);
        }
    }

    private static String corta(String r) {
        String x = r.startsWith(Ordenes.RAIZ + "/") ? r.substring(Ordenes.RAIZ.length() + 1) : r.equals(Ordenes.RAIZ) ? "todo el almacenamiento" : r;
        return "«" + x + "»";
    }

    /** Qué quiere hacer, en español; null si el tipo no es de la lista fija. */
    static String legible(JSONObject p) {
        JSONObject a = p.optJSONObject("args");
        if (a == null) return null;
        String r = corta(a.optString("ruta", ""));
        switch (p.optString("tipo")) {
            case "listar": return "ver qué hay en " + r;
            case "tamanos": return "ver qué ocupa más en " + r;
            case "duplicados": return "buscar archivos repetidos en " + r;
            case "info": return "ver los datos de " + r;
            case "crear_carpeta": return "crear la carpeta " + r;
            case "mover": return "mover " + corta(a.optString("origen")) + " a la carpeta " + corta(a.optString("destino"));
            case "papelera": return "mandar " + r + " a la papelera de Zazu (no se borra; se puede recuperar)";
            case "subir": return "copiar " + r + " a tu PC";
            default: return null;
        }
    }

    private static void canal(Context c) {
        NotificationChannel ch = new NotificationChannel(CANAL, "Peticiones de Zazu", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Zazu pide permiso para una tarea con tus archivos");
        c.getSystemService(NotificationManager.class).createNotificationChannel(ch);
    }

    /** Aviso: tocarlo abre la app con el diálogo (Permitir solo se puede pulsar dentro de la app, con el móvil desbloqueado). */
    private static void notificar(Context c, JSONObject p) {
        canal(c);
        Intent abrir = new Intent(c, MainActivity.class).putExtra(EXTRA, p.optString("id")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);   // solo el id: se relee del servidor
        int n = p.optString("id").hashCode();
        PendingIntent pi = PendingIntent.getActivity(c, n, abrir, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification no = new Notification.Builder(c, CANAL)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("Zazu quiere: " + legible(p))
                .setContentText(p.optString("motivo"))
                .setStyle(new Notification.BigTextStyle().bigText(legible(p) + "\n" + p.optString("motivo") + "\nToca para Permitir o Rechazar."))
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .setTimeoutAfter(Math.max(1000L, p.optLong("caduca") * 1000 - System.currentTimeMillis()))
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build();
        c.getSystemService(NotificationManager.class).notify(n, no);
    }

    /** El diálogo de aprobación. Nada se hace sin pulsar Permitir. */
    static void dialogo(Activity a, JSONObject p) {
        if (a.isFinishing() || legible(p) == null) return;
        String id = p.optString("id");
        if (Copia.prefs(a).getStringSet("en_pantalla", new HashSet<>()).contains(id)) return;   // ya está en pantalla
        marcarEnPantalla(a, id, true);
        a.getSystemService(NotificationManager.class).cancel(id.hashCode());
        final JSONObject vista = p;   // lo que Fran ve es exactamente lo que se hará
        new AlertDialog.Builder(a)
                .setTitle("Zazu quiere:")
                .setMessage(legible(vista) + "\n\nMotivo: " + vista.optString("motivo"))
                .setCancelable(false)
                .setPositiveButton("Permitir", (d, w) -> {
                    marcarEnPantalla(a, id, false);
                    responder(a, vista, true);
                })
                .setNegativeButton("Rechazar", (d, w) -> {
                    marcarEnPantalla(a, id, false);
                    responder(a, vista, false);
                })
                .show();
    }

    private static void marcarEnPantalla(Context c, String id, boolean si) {
        Set<String> s = new HashSet<>(Copia.prefs(c).getStringSet("en_pantalla", new HashSet<>()));
        if (si) s.add(id);
        else s.remove(id);
        Copia.prefs(c).edit().putStringSet("en_pantalla", s).apply();
    }

    static void limpiarEnPantalla(Context c) {
        Copia.prefs(c).edit().remove("en_pantalla").apply();
    }

    private static void responder(Activity a, JSONObject p, boolean permitir) {
        Context c = a.getApplicationContext();
        new Thread(() -> {
            String id = p.optString("id"), aviso;
            try {
                if (!permitir) {
                    estado(c, id, "rechazada", null);
                    anotar(c, p, "rechazada", null);
                    aviso = "Rechazado";
                } else if (!estado(c, id, "aprobada", null)) {
                    anotar(c, p, "caducada", "no se hizo: ya había caducado o se respondió desde otro sitio");
                    aviso = "Esa petición ya no vale (caducó). No se ha hecho nada.";
                } else if ("subir".equals(p.optString("tipo"))) {
                    // puede ser mucho y largo: va a un trabajo de fondo con WiFi, que sigue aunque el móvil se bloquee, y avisa al terminar
                    anotar(c, p, "aprobada", "se copia en segundo plano cuando haya WiFi");
                    Copia.encargarSubida(c, p);
                    aviso = "Permitido: lo copio a tu PC en segundo plano cuando haya WiFi. Te aviso al terminar.";
                } else {
                    anotar(c, p, "aprobada", null);
                    JSONObject r;
                    String fin;
                    try {
                        r = Ordenes.hacer(c, p);
                        fin = "hecha";
                    } catch (Exception e) {
                        r = new JSONObject().put("error", String.valueOf(e.getMessage()));
                        fin = "error";
                    }
                    aviso = terminar(c, p, fin, r, false);
                }
            } catch (Exception e) {
                aviso = "No pude hablar con el servidor: " + e.getMessage();
            }
            final String t = aviso;
            a.runOnUiThread(() -> Toast.makeText(c, t, Toast.LENGTH_LONG).show());
        }, "zazu-peticion").start();
    }

    /**
     * Cierra una petición ya hecha (o fallida). PRIMERO se anota en el registro local, porque la acción ya ocurrió, y luego se avisa al servidor;
     * si el aviso no llega se guarda y se reenvía en el próximo sondeo. Devuelve el texto para Fran (y, con notificar, se lo enseña en un aviso).
     */
    static String terminar(Context c, JSONObject p, String fin, JSONObject r, boolean notificar) {
        String id = p.optString("id");
        r = recortado(r);
        anotar(c, p, fin, r.toString());
        String txt = "hecha".equals(fin) ? "Hecho: " + legible(p) : "No se pudo: " + r.optString("error");
        if (!entregar(c, id, fin, r)) {
            porAvisar(c, id, fin, r);
            txt += ". Aún no he podido avisar a Zazu; lo reintento solo.";
        }
        if (notificar) avisoFin(c, id, txt);
        return txt;
    }

    /** El servidor acepta como mucho 512 KB por resultado: lo que pase de ~100 000 caracteres va recortado (si no, Zazu no recibía nada). */
    private static JSONObject recortado(JSONObject r) {
        String s = r.toString();
        if (s.length() <= 100_000) return r;
        try {
            JSONObject x = new JSONObject().put("recortado", true).put("texto", s.substring(0, 100_000));
            if (r.has("error")) x.put("error", r.optString("error"));
            return x;
        } catch (org.json.JSONException e) {
            return r;
        }
    }

    /** true si el servidor ya sabe el resultado: lo aceptó, o lo rechaza para siempre (ya cerrada, no existe…), y reintentar no cambia nada. */
    private static boolean entregar(Context c, String id, String fin, JSONObject r) {
        try {
            int st = estadoHttp(c, id, fin, r);
            return st < 500;
        } catch (Exception e) {
            return false;   // sin red o token caducado: queda para el próximo sondeo
        }
    }

    // resultados que no llegaron al servidor: id → {estado, resultado}. Se reenvían en cada sondeo.
    private static final String POR_AVISAR = "por_avisar";
    private static final Object AVISOS = new Object();   // cerrojo propio: reenviar habla con la red y no debe frenar anotar/registro

    private static void porAvisar(Context c, String id, String fin, JSONObject r) {
        synchronized (AVISOS) {
            try {
                JSONObject t = new JSONObject(Copia.prefs(c).getString(POR_AVISAR, "{}"));
                if (t.length() < 50) t.put(id, new JSONObject().put("estado", fin).put("resultado", r));
                Copia.prefs(c).edit().putString(POR_AVISAR, t.toString()).commit();
            } catch (org.json.JSONException ignorado) {
                // no se pudo guardar: queda al menos en el registro local
            }
        }
    }

    private static void reenviar(Context c) {
        synchronized (AVISOS) {
            try {
                JSONObject t = new JSONObject(Copia.prefs(c).getString(POR_AVISAR, "{}"));
                if (t.length() == 0) return;
                JSONObject quedan = new JSONObject();
                for (java.util.Iterator<String> it = t.keys(); it.hasNext(); ) {
                    String id = it.next();
                    JSONObject x = t.getJSONObject(id);
                    if (!entregar(c, id, x.getString("estado"), x.getJSONObject("resultado"))) quedan.put(id, x);
                }
                Copia.prefs(c).edit().putString(POR_AVISAR, quedan.toString()).commit();
            } catch (org.json.JSONException e) {
                Copia.prefs(c).edit().remove(POR_AVISAR).apply();   // dañado: no se reintenta en bucle
            }
        }
    }

    /** Aviso del resultado cuando la tarea acabó en segundo plano (no hay pantalla para el mensaje); tocarlo abre el «Registro de Zazu». */
    private static void avisoFin(Context c, String id, String txt) {
        canal(c);
        PendingIntent pi = PendingIntent.getActivity(c, id.hashCode(), new Intent(c, RegistroActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification no = new Notification.Builder(c, CANAL)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("Zazu")
                .setContentText(txt)
                .setStyle(new Notification.BigTextStyle().bigText(txt))
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build();
        c.getSystemService(NotificationManager.class).notify(id.hashCode(), no);
    }

    /** Avisa al servidor; false si el servidor no acepta el cambio (caducada, ya respondida). */
    private static boolean estado(Context c, String id, String estado, JSONObject resultado) throws Exception {
        return estadoHttp(c, id, estado, resultado) == 200;
    }

    /** POST del estado; devuelve el código HTTP (lanza si no hay red o el token ya no vale). */
    private static int estadoHttp(Context c, String id, String estado, JSONObject resultado) throws Exception {
        JSONObject b = new JSONObject().put("estado", estado);
        if (resultado != null) b.put("resultado", resultado);
        HttpURLConnection h = Copia.abrir(Copia.token(c), "/api/movil/peticiones/" + id + "/resultado", "POST");
        h.setRequestProperty("Content-Type", "application/json");
        byte[] d = b.toString().getBytes("UTF-8");
        h.setFixedLengthStreamingMode(d.length);
        try (java.io.OutputStream o = h.getOutputStream()) {
            o.write(d);
        }
        int st = h.getResponseCode();
        Copia.leer(h);
        if (st == 401) throw new Copia.SinToken();
        return st;
    }

    // ---------- registro local visible («Registro de Zazu») ----------
    private static SQLiteDatabase db(Context c) {
        SQLiteDatabase db = SQLiteDatabase.openOrCreateDatabase(c.getDatabasePath("copia.db").getPath(), null);
        db.execSQL("CREATE TABLE IF NOT EXISTS peticiones (n INTEGER PRIMARY KEY AUTOINCREMENT, cuando INTEGER, id TEXT, que TEXT, motivo TEXT, estado TEXT, resultado TEXT)");
        return db;
    }

    static synchronized void anotar(Context c, JSONObject p, String estado, String resultado) {
        try (SQLiteDatabase db = db(c)) {
            ContentValues v = new ContentValues();
            v.put("cuando", System.currentTimeMillis());
            v.put("id", p.optString("id"));
            v.put("que", legible(p));
            v.put("motivo", p.optString("motivo"));
            v.put("estado", estado);
            v.put("resultado", resultado == null ? null : resultado.length() > 2000 ? resultado.substring(0, 2000) + "…" : resultado);
            db.insert("peticiones", null, v);
        }
    }

    static synchronized String registro(Context c) {
        StringBuilder s = new StringBuilder();
        SimpleDateFormat f = new SimpleDateFormat("d MMM HH:mm", new Locale("es", "ES"));
        try (SQLiteDatabase db = db(c); Cursor k = db.rawQuery("SELECT cuando, que, motivo, estado, resultado FROM peticiones ORDER BY n DESC LIMIT 200", null)) {
            while (k.moveToNext()) {
                s.append(f.format(new Date(k.getLong(0)))).append(" · ").append(k.getString(3).toUpperCase(Locale.ROOT)).append('\n')
                        .append(k.getString(1)).append("\nMotivo: ").append(k.getString(2)).append('\n');
                if (k.getString(4) != null) s.append(k.getString(4)).append('\n');
                s.append('\n');
            }
        }
        return s.length() == 0 ? "Aún no hay peticiones de Zazu." : s.toString();
    }
}
