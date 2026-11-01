package app.holazazu;

import android.Manifest;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.ContentValues;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.os.Build;
import android.os.Environment;
import android.os.SystemClock;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Copia sola al PC de Fran (holazazu.app → ~/Documentos/Movil-S25) los archivos de WhatsApp y las fotos de la cámara.
 * Solo sube lo NUEVO: un registro local (copia.db: ruta + tamaño + fecha) recuerda lo ya copiado, y antes de subir se pregunta
 * al servidor en lotes de 200 qué le falta (lo que ya copió el ADB no se vuelve a mandar). Los archivos van en trozos de 16 MB
 * (Cloudflare corta cada petición a 100 MB) y una subida cortada sigue desde donde se quedó.
 * Se autentica con el token de dispositivo (ver movil.py en el servidor), nunca con la sesión de la web.
 */
final class Copia {
    static final String PREFS = "zazu";
    static final int JOB_PERIODICO = 1, JOB_YA = 2, JOB_SONDEO = 3, JOB_SUBIR = 4;
    private static final long TROZO = 16L << 20;
    private static final int LOTE = 200;
    private static final String WA = "Android/media/com.whatsapp/WhatsApp/Media/";
    private static final String[] RAICES = {
            WA + "WhatsApp Images", WA + "WhatsApp Video", WA + "WhatsApp Documents", WA + "WhatsApp Voice Notes", WA + "WhatsApp Audio",
            "DCIM/Camera"};
    // el ÚNICO cerrojo de subida: lo toman la copia de fondo y la orden «subir»; dos subidas del mismo archivo a la vez lo corrompían en el PC
    private static final AtomicBoolean CORRIENDO = new AtomicBoolean(false);

    private Copia() {}

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String token(Context c) {
        return prefs(c).getString("token", null);
    }

    static boolean tieneAcceso(Context c) {
        if (Build.VERSION.SDK_INT >= 30) return Environment.isExternalStorageManager();
        return c.checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED;
    }

    /** Copia cada ~2 h con WiFi (o red sin coste) y batería no baja; y, si ahora=true, también en cuanto haya WiFi. Sobrevive a reinicios. */
    static void programar(Context c, boolean ahora) {
        if (token(c) == null) return;
        JobScheduler js = c.getSystemService(JobScheduler.class);
        ComponentName cn = new ComponentName(c, CopiaJob.class);
        // recoger avisos y peticiones de Zazu: cada 15 min (lo mínimo que deja Android), con cualquier red. 2.5: también sin el permiso
        // de archivos, porque los avisos (recordatorios, rutinas, alertas) no lo necesitan
        if (js.getPendingJob(JOB_SONDEO) == null) {
            js.schedule(new JobInfo.Builder(JOB_SONDEO, cn)
                    .setPeriodic(15 * 60_000L)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true)
                    .build());
        }
        if (!tieneAcceso(c)) return;   // la copia y las órdenes «subir» sí necesitan «Acceso a todos los archivos»
        if (js.getPendingJob(JOB_PERIODICO) == null) {
            js.schedule(new JobInfo.Builder(JOB_PERIODICO, cn)
                    .setPeriodic(2 * 3600_000L, 30 * 60_000L)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)
                    .setRequiresBatteryNotLow(true)
                    .setPersisted(true)
                    .build());
        }
        // schedule() con el id de un trabajo EN MARCHA lo para: si ya hay una pasada pendiente o corriendo, no se toca (onResume llega a menudo)
        if (ahora && js.getPendingJob(JOB_YA) == null && !CORRIENDO.get()) seguir(c, 0);
        // una orden «subir» que se quedó sin trabajo (sin token, reinicio raro…): se vuelve a lanzar
        if (hayOrdenes(c) && js.getPendingJob(JOB_SUBIR) == null) seguirSubida(c, 0);
    }

    /** Una pasada suelta (al abrir la app, o para seguir donde se quedó la anterior). */
    static void seguir(Context c, long esperaMs) {
        JobInfo.Builder b = new JobInfo.Builder(JOB_YA, new ComponentName(c, CopiaJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)
                .setPersisted(true);
        if (esperaMs > 0) b.setMinimumLatency(esperaMs);
        c.getSystemService(JobScheduler.class).schedule(b.build());
    }

    /** Una pasada. Devuelve true si no queda nada pendiente; false si se paró (tiempo, cancelada) con cosas por subir. */
    static boolean copiar(Context c, AtomicBoolean parar, long hasta) throws IOException {
        String tok = token(c);
        if (tok == null || !tieneAcceso(c)) return true;
        if (!CORRIENDO.compareAndSet(false, true)) return true;   // ya hay otra subida en marcha
        Registro reg = null;
        try {
            reg = new Registro(c);   // dentro del try: si no abre (disco lleno), el finally suelta el cerrojo igual
            File sd = Environment.getExternalStorageDirectory();
            Map<String, String> hechos = reg.todos();
            List<File> nuevos = new ArrayList<>();
            long ahora = System.currentTimeMillis();
            for (String r : RAICES) recorrer(new File(sd, r), nuevos, hechos, sd, ahora);
            nuevos.sort((a, b) -> Long.compare(b.lastModified(), a.lastModified()));   // lo más reciente primero
            if (!subirLista(tok, sd, nuevos, reg, parar, hasta, new int[5])) return false;
            prefs(c).edit().putLong("ultima_copia", System.currentTimeMillis()).apply();
            return true;
        } catch (org.json.JSONException e) {
            throw new IOException(e);
        } finally {
            if (reg != null) reg.close();
            CORRIENDO.set(false);
        }
    }

    private static boolean parado(AtomicBoolean parar, long hasta) {
        return parar.get() || SystemClock.elapsedRealtime() > hasta;
    }

    /**
     * Sube fs por lotes de 200 (antes se pregunta al servidor qué le falta), empezando en n[0]. Va contando en n:
     * [0] archivos tratados, [1] subidos, [2] ya estaban, [3] el servidor no los admite, [4] cambiaron mientras se subían.
     * true si llegó al final; false si se paró (cancelada o sin tiempo): n[0] dice por dónde seguir.
     */
    private static boolean subirLista(String tok, File sd, List<File> fs, Registro reg, AtomicBoolean parar, long hasta, int[] n)
            throws IOException, org.json.JSONException {
        while (n[0] < fs.size()) {
            List<File> lote = fs.subList(n[0], Math.min(fs.size(), n[0] + LOTE));
            // tamaño y fecha de ANTES de subir: es lo que se marca, y si el archivo cambia por el camino se nota
            long[] tam = new long[lote.size()], mtime = new long[lote.size()];
            JSONArray pide = new JSONArray();
            for (int j = 0; j < lote.size(); j++) {
                tam[j] = lote.get(j).length();
                mtime[j] = lote.get(j).lastModified();
                pide.put(new JSONObject().put("ruta", rel(sd, lote.get(j))).put("tam", tam[j]));
            }
            JSONArray resp = new JSONObject(pedir(tok, "/api/movil/estado", new JSONObject().put("archivos", pide).toString())).getJSONArray("archivos");
            for (int j = 0; j < lote.size(); j++) {
                if (parado(parar, hasta)) return false;
                File f = lote.get(j);
                JSONObject e = resp.getJSONObject(j);
                String est = e.getString("estado");
                if ("falta".equals(est)) {
                    if (!subir(tok, sd, f, tam[j], mtime[j], e.getLong("tengo"), parar, hasta)) return false;
                    if (f.length() != tam[j] || f.lastModified() != mtime[j]) {
                        // creció o cambió mientras se subía: el PC tiene la versión de antes. No se marca, así la próxima pasada lo manda entero
                        n[4]++;
                        n[0]++;
                        continue;
                    }
                    n[1]++;
                } else {
                    n["ya-estaba".equals(est) ? 2 : 3]++;
                }
                reg.marcar(rel(sd, f), tam[j], mtime[j]);   // ya-estaba, completo o inválida: no se vuelve a mirar
                n[0]++;
            }
        }
        return true;
    }

    private static void recorrer(File d, List<File> out, Map<String, String> hechos, File sd, long ahora) {
        File[] hijos = d.listFiles();
        if (hijos == null) return;
        for (File f : hijos) {
            if (f.getName().startsWith(".")) continue;   // .Statuses, .nomedia, .trashed-…
            if (f.isDirectory()) {
                recorrer(f, out, hechos, sd, ahora);
            } else if (f.isFile() && ahora - f.lastModified() > 60_000) {   // lo que se está escribiendo ahora, la próxima vez
                String v = hechos.get(rel(sd, f));
                if (!(f.length() + ":" + f.lastModified()).equals(v)) out.add(f);
            }
        }
    }

    private static String rel(File sd, File f) {
        return f.getAbsolutePath().substring(sd.getAbsolutePath().length() + 1);
    }

    // ---------- orden «subir» que Fran PERMITIÓ: un trabajo de fondo de un solo uso (JOB_SUBIR), con WiFi y los límites de la copia ----------
    // Antes corría en un hilo suelto de la pantalla: con el móvil en reposo Android lo cortaba, usaba datos móviles y no seguía.
    // Las órdenes se guardan (con lo que llevan hecho) en las preferencias; el trabajo las hace en pasadas de 8 min y avisa al terminar.
    private static final String ORDENES = "ordenes_subir";

    private static synchronized JSONArray ordenes(Context c) {
        try {
            return new JSONArray(prefs(c).getString(ORDENES, "[]"));
        } catch (org.json.JSONException e) {
            return new JSONArray();
        }
    }

    private static synchronized void guardarOrden(Context c, JSONObject o, boolean quitar) {
        JSONArray l = ordenes(c), nueva = new JSONArray();
        String id = o.optJSONObject("p").optString("id");
        boolean puesta = false;
        for (int i = 0; i < l.length(); i++) {
            JSONObject x = l.optJSONObject(i);
            if (x == null) continue;
            if (id.equals(x.optJSONObject("p").optString("id"))) {
                if (!quitar) nueva.put(o);
                puesta = true;
            } else {
                nueva.put(x);
            }
        }
        if (!puesta && !quitar) nueva.put(o);
        prefs(c).edit().putString(ORDENES, nueva.toString()).commit();
    }

    static boolean hayOrdenes(Context c) {
        return ordenes(c).length() > 0;
    }

    /** Fran pulsó Permitir en una «subir»: se guarda y se lanza el trabajo. */
    static void encargarSubida(Context c, JSONObject p) throws org.json.JSONException {
        guardarOrden(c, new JSONObject().put("p", p).put("n", new JSONArray(new int[5])).put("fallos", 0), false);
        seguirSubida(c, 0);
    }

    static void seguirSubida(Context c, long esperaMs) {
        JobInfo.Builder b = new JobInfo.Builder(JOB_SUBIR, new ComponentName(c, CopiaJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)   // como la copia: puede ser mucho, nada de datos móviles
                .setPersisted(true);
        if (esperaMs > 0) b.setMinimumLatency(esperaMs);
        c.getSystemService(JobScheduler.class).schedule(b.build());
    }

    /** Hace las órdenes «subir» guardadas. true si no queda ninguna; false si se paró (tiempo, cancelada u otra subida en marcha). */
    static boolean subirOrdenes(Context c, AtomicBoolean parar, long hasta) throws IOException {
        String tok = token(c);
        if (tok == null || !hayOrdenes(c)) return true;   // sin token se queda guardada: programar() la relanza cuando vuelva
        if (!CORRIENDO.compareAndSet(false, true)) return false;   // la copia de fondo está subiendo: se espera a que acabe
        Registro reg = null;
        try {
            reg = new Registro(c);
            File sd = Environment.getExternalStorageDirectory();
            JSONObject o;
            while ((o = ordenes(c).optJSONObject(0)) != null) {
                JSONObject p = o.getJSONObject("p");
                int[] n = new int[5];
                for (int i = 0; i < 5; i++) n[i] = o.getJSONArray("n").optInt(i);
                List<File> fs;
                try {
                    fs = Ordenes.paraSubir(c, p);
                } catch (IOException e) {   // la ruta ya no existe o no vale: no tiene arreglo, se cierra con error
                    guardarOrden(c, o, true);
                    Peticiones.terminar(c, p, "error", new JSONObject().put("error", String.valueOf(e.getMessage())), true);
                    continue;
                }
                // se sigue DESPUÉS de la última ruta tratada, no por posición: si entre pasadas se borra un archivo ya subido,
                // las posiciones se corren y el siguiente pendiente se saltaba sin subir
                String ultima = o.optString("ultima", null);
                if (ultima != null) {
                    n[0] = 0;
                    while (n[0] < fs.size() && fs.get(n[0]).getPath().compareTo(ultima) <= 0) n[0]++;
                }
                int antes = n[0];
                boolean acabada;
                try {
                    acabada = subirLista(tok, sd, fs, reg, parar, hasta, n);
                } catch (SinToken e) {
                    throw e;
                } catch (IOException e) {
                    // red o servidor: se guarda lo hecho y Android reintenta con espera creciente; tras 5 fallos seguidos se da por fallida.
                    // No cuenta como fallo si Android paró el trabajo (se fue la WiFi), y una pasada que avanzó vuelve a empezar la cuenta
                    if (n[0] > 0) o.put("ultima", fs.get(n[0] - 1).getPath());
                    o.put("n", new JSONArray(n)).put("fallos", parar.get() ? o.optInt("fallos") : n[0] > antes ? 1 : o.optInt("fallos") + 1);
                    if (o.getInt("fallos") < 5) {
                        guardarOrden(c, o, false);
                        throw e;
                    }
                    guardarOrden(c, o, true);
                    Peticiones.terminar(c, p, "error", new JSONObject().put("error", String.valueOf(e.getMessage())).put("subidos", n[1]), true);
                    continue;
                }
                o.put("n", new JSONArray(n)).put("fallos", 0);
                if (n[0] > 0) o.put("ultima", fs.get(n[0] - 1).getPath());
                if (!acabada) {
                    guardarOrden(c, o, false);
                    return false;
                }
                guardarOrden(c, o, true);
                JSONObject r = new JSONObject().put("ruta", p.getJSONObject("args").optString("ruta")).put("subidos", n[1]).put("ya_estaban", n[2])
                        .put("no_admitidos", n[3]).put("cambiaron_mientras_subian", n[4]).put("limite_alcanzado", fs.size() >= Ordenes.MAX_SUBIR);
                Peticiones.terminar(c, p, "hecha", r, true);
            }
            return true;
        } catch (org.json.JSONException e) {
            throw new IOException(e);
        } finally {
            if (reg != null) reg.close();
            CORRIENDO.set(false);
        }
    }

    /** Sube f (con el tamaño y la fecha medidos antes) desde «desde». true si el servidor ya lo tiene entero; false si se paró. */
    private static boolean subir(String tok, File sd, File f, long tam, long mtime, long desde, AtomicBoolean parar, long hasta)
            throws IOException, org.json.JSONException {
        String base = "/api/movil/subir?ruta=" + URLEncoder.encode(rel(sd, f), "UTF-8") + "&tam=" + tam + "&mtime=" + mtime;
        byte[] buf = new byte[256 * 1024];
        for (int vueltas = 0; vueltas < 1000; vueltas++) {
            if (parado(parar, hasta)) return false;
            if (desde < 0 || desde > tam) throw new IOException("el servidor tiene más de lo que mide " + f.getName());
            long n = Math.min(TROZO, tam - desde);
            HttpURLConnection h = abrir(tok, base + "&desde=" + desde, "POST");
            h.setRequestProperty("Content-Type", "application/octet-stream");
            h.setFixedLengthStreamingMode(n);
            try (RandomAccessFile in = new RandomAccessFile(f, "r"); OutputStream out = h.getOutputStream()) {
                in.seek(desde);
                long falta = n;
                while (falta > 0) {
                    int r = in.read(buf, 0, (int) Math.min(buf.length, falta));
                    if (r < 0) throw new IOException("el archivo ha cambiado");
                    out.write(buf, 0, r);
                    falta -= r;
                }
            }
            int st = h.getResponseCode();
            JSONObject r = new JSONObject(leer(h));
            if (st == 401) throw new SinToken();
            String est = r.optString("estado");
            if ("completo".equals(est) || "ya-estaba".equals(est)) return true;
            if (("parcial".equals(est) || st == 409) && r.has("tengo")) {
                desde = r.getLong("tengo");
                continue;
            }
            throw new IOException("el servidor dijo " + st + ": " + r.optString("error"));
        }
        // sin «completo» tras 1000 vueltas (p. ej. un 409 en bucle): es un fallo, nunca un archivo copiado
        throw new IOException("la subida de " + f.getName() + " no avanza");
    }

    /** POST JSON con el token; devuelve el cuerpo. */
    static String pedir(String tok, String ruta, String json) throws IOException {
        HttpURLConnection h = abrir(tok, ruta, "POST");
        h.setRequestProperty("Content-Type", "application/json");
        byte[] b = json.getBytes(StandardCharsets.UTF_8);
        h.setFixedLengthStreamingMode(b.length);
        try (OutputStream o = h.getOutputStream()) {
            o.write(b);
        }
        int st = h.getResponseCode();
        if (st == 401) throw new SinToken();
        String r = leer(h);
        if (st != 200) throw new IOException("el servidor dijo " + st);
        return r;
    }

    static HttpURLConnection abrir(String tok, String ruta, String metodo) throws IOException {
        HttpURLConnection h = (HttpURLConnection) new URL(BuildConfig.URL_BASE + ruta).openConnection();
        h.setRequestMethod(metodo);
        h.setConnectTimeout(20_000);
        h.setReadTimeout(120_000);
        h.setUseCaches(false);
        if (tok != null) h.setRequestProperty("Authorization", "Bearer " + tok);
        h.setRequestProperty("User-Agent", "ZazuApp/" + BuildConfig.VERSION_NAME);
        if ("POST".equals(metodo)) h.setDoOutput(true);
        return h;
    }

    static String leer(HttpURLConnection h) throws IOException {
        InputStream in;
        try {
            in = h.getInputStream();
        } catch (IOException e) {
            in = h.getErrorStream();
        }
        if (in == null) return "{}";
        try (InputStream i = in) {
            ByteArrayOutputStream o = new ByteArrayOutputStream();
            byte[] b = new byte[8192];
            int n;
            while ((n = i.read(b)) > 0) o.write(b, 0, n);
            String s = o.toString("UTF-8");
            return s.isEmpty() ? "{}" : s;
        } finally {
            h.disconnect();
        }
    }

    /** El servidor ya no reconoce el token (Fran quitó el móvil): se olvida y la app pedirá otro al abrirse con la sesión iniciada. */
    static final class SinToken extends IOException {
        SinToken() {
            super("token no válido");
        }
    }

    /** Lo ya copiado: ruta relativa a /sdcard → «tamaño:fecha». */
    private static final class Registro {
        private final SQLiteDatabase db;

        Registro(Context c) {
            db = SQLiteDatabase.openOrCreateDatabase(c.getDatabasePath("copia.db").getPath(), null);
            db.execSQL("CREATE TABLE IF NOT EXISTS subidos (ruta TEXT PRIMARY KEY, tam INTEGER, mtime INTEGER)");
        }

        Map<String, String> todos() {
            Map<String, String> m = new HashMap<>();
            try (Cursor k = db.rawQuery("SELECT ruta, tam, mtime FROM subidos", null)) {
                while (k.moveToNext()) m.put(k.getString(0), k.getLong(1) + ":" + k.getLong(2));
            }
            return m;
        }

        void marcar(String ruta, long tam, long mtime) {
            ContentValues v = new ContentValues();
            v.put("ruta", ruta);
            v.put("tam", tam);
            v.put("mtime", mtime);
            db.insertWithOnConflict("subidos", null, v, SQLiteDatabase.CONFLICT_REPLACE);
        }

        void close() {
            db.close();
        }
    }
}
