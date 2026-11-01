package app.holazazu;

import android.content.Context;
import android.os.Environment;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Las tareas de archivos que Fran ya ha PERMITIDO (las llama Peticiones tras pulsar Permitir). Lista fija; sin comandos ni shell.
 * Rutas siempre bajo /storage/emulated/0, sin «..», comprobadas con la ruta canónica (un enlace no saca de ahí) y nunca Android/data u obb.
 * Nunca se borra nada: «papelera» mueve a /sdcard/.ZazuPapelera/<fecha>/, de donde se puede recuperar a mano.
 */
final class Ordenes {
    static final String RAIZ = "/storage/emulated/0";
    static final int MAX_SUBIR = 2000;
    private static final int MAX_LISTA = 500, MAX_ARCHIVOS = 20000, MAX_RUTAS_GRUPO = 20;

    private Ordenes() {}

    static JSONObject hacer(Context c, JSONObject p) throws IOException, JSONException {
        if (!Copia.tieneAcceso(c)) throw new IOException("la app no tiene el permiso «Acceso a todos los archivos»");
        JSONObject a = p.getJSONObject("args");
        switch (p.getString("tipo")) {
            case "listar": return listar(ruta(a.getString("ruta")));
            case "tamanos": return tamanos(ruta(a.getString("ruta")));
            case "duplicados": return duplicados(ruta(a.getString("ruta")));
            case "info": return info(ruta(a.getString("ruta")));
            case "crear_carpeta": return crearCarpeta(ruta(a.getString("ruta")));
            case "mover": return mover(ruta(a.getString("origen")), ruta(a.getString("destino")));
            case "papelera": return papelera(ruta(a.getString("ruta")));
            // «subir» no pasa por aquí: va a un trabajo de fondo (Copia.encargarSubida → paraSubir)
            default: throw new IOException("tipo no permitido");
        }
    }

    private static File raiz() throws IOException {
        return Environment.getExternalStorageDirectory().getCanonicalFile();
    }

    /** Ruta del móvil comprobada: bajo la raíz, sin «..», sin escaparse por enlaces y fuera de Android/data y Android/obb. */
    static File ruta(String r) throws IOException {
        if (r == null || !(r.equals(RAIZ) || r.startsWith(RAIZ + "/"))) throw new IOException("ruta fuera del almacenamiento del móvil");
        String rel = r.substring(RAIZ.length());
        for (String x : rel.split("/")) if (x.equals("..") || x.equals(".")) throw new IOException("ruta no válida");
        File raiz = raiz(), f = new File(raiz, rel), can = f.getCanonicalFile();
        String rp = raiz.getPath();
        if (!can.equals(raiz) && !can.getPath().startsWith(rp + "/")) throw new IOException("ruta fuera del almacenamiento del móvil");
        if (can.getPath().startsWith(rp + "/Android/data") || can.getPath().startsWith(rp + "/Android/obb")) throw new IOException("Android/data y Android/obb no se tocan");
        return can;
    }

    private static String rel(File f) throws IOException {
        String rp = raiz().getPath();
        return f.getPath().equals(rp) ? "/" : f.getPath().substring(rp.length() + 1);
    }

    private static File existe(File f) throws IOException {
        if (!f.exists()) throw new IOException("no existe: " + rel(f));
        return f;
    }

    private static JSONObject listar(File d) throws IOException, JSONException {
        File[] hijos = existe(d).listFiles();
        if (hijos == null) throw new IOException("no es una carpeta: " + rel(d));
        JSONArray l = new JSONArray();
        for (File f : hijos) {
            if (l.length() >= MAX_LISTA) break;
            l.put(new JSONObject().put("nombre", f.getName()).put("carpeta", f.isDirectory()).put("tam", f.isFile() ? f.length() : 0).put("fecha", f.lastModified()));
        }
        return new JSONObject().put("ruta", rel(d)).put("total", hijos.length).put("archivos", l);
    }

    private static long[] medir(File f, long[] cuenta) {
        if (cuenta[1] > 200_000) return cuenta;
        if (f.isFile()) {
            cuenta[0] += f.length();
            cuenta[1]++;
        } else {
            File[] h = f.listFiles();
            if (h != null) for (File x : h) medir(x, cuenta);
        }
        return cuenta;
    }

    private static JSONObject tamanos(File d) throws IOException, JSONException {
        File[] hijos = existe(d).listFiles();
        if (hijos == null) throw new IOException("no es una carpeta: " + rel(d));
        List<Object[]> l = new ArrayList<>();
        long total = 0;
        for (File f : hijos) {
            long[] m = medir(f, new long[2]);
            total += m[0];
            l.add(new Object[]{f.getName(), m[0], m[1]});
        }
        l.sort((x, y) -> Long.compare((long) y[1], (long) x[1]));
        JSONArray out = new JSONArray();
        for (int i = 0; i < Math.min(50, l.size()); i++) {
            Object[] x = l.get(i);
            out.put(new JSONObject().put("nombre", x[0]).put("mb", Math.round((long) x[1] / 1048576.0 * 10) / 10.0).put("archivos", x[2]));
        }
        return new JSONObject().put("ruta", rel(d)).put("total_mb", Math.round(total / 1048576.0 * 10) / 10.0).put("mayores", out);
    }

    private static JSONObject duplicados(File d) throws IOException, JSONException {
        existe(d);
        Map<Long, List<File>> porTam = new HashMap<>();
        ArrayDeque<File> pila = new ArrayDeque<>();
        pila.push(d);
        int n = 0;
        while (!pila.isEmpty() && n < MAX_ARCHIVOS) {
            File[] h = pila.pop().listFiles();
            if (h == null) continue;
            for (File f : h) {
                if (f.getName().startsWith(".")) continue;
                if (f.isDirectory()) pila.push(f);
                else if (f.length() > 0) {
                    porTam.computeIfAbsent(f.length(), k -> new ArrayList<>()).add(f);
                    n++;
                }
            }
        }
        Map<String, List<File>> porHash = new HashMap<>();
        long leido = 0;
        for (List<File> g : porTam.values()) {
            if (g.size() < 2) continue;
            for (File f : g) {
                if (leido > 4L << 30) break;   // como mucho 4 GB leídos por petición
                porHash.computeIfAbsent(f.length() + ":" + sha256(f), k -> new ArrayList<>()).add(f);
                leido += f.length();
            }
        }
        JSONArray grupos = new JSONArray();
        long sobra = 0;
        for (List<File> g : porHash.values()) {
            if (g.size() < 2) continue;
            sobra += g.get(0).length() * (g.size() - 1);
            if (grupos.length() >= 100) continue;
            // tope de rutas por grupo: un grupo de miles de copias hacía pasar el resultado del límite del servidor y Zazu nunca lo recibía
            JSONArray rutas = new JSONArray();
            for (int i = 0; i < Math.min(g.size(), MAX_RUTAS_GRUPO); i++) rutas.put(rel(g.get(i)));
            JSONObject grupo = new JSONObject().put("tam", g.get(0).length()).put("copias", g.size()).put("rutas", rutas);
            if (g.size() > MAX_RUTAS_GRUPO) grupo.put("rutas_sin_listar", g.size() - MAX_RUTAS_GRUPO);
            grupos.put(grupo);
        }
        return new JSONObject().put("ruta", rel(d)).put("revisados", n).put("se_liberarian_mb", Math.round(sobra / 1048576.0 * 10) / 10.0).put("grupos", grupos);
    }

    private static String sha256(File f) throws IOException {
        try (InputStream in = new FileInputStream(f)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] b = new byte[256 * 1024];
            int r;
            while ((r = in.read(b)) > 0) md.update(b, 0, r);
            StringBuilder s = new StringBuilder();
            for (byte x : md.digest()) s.append(String.format("%02x", x));
            return s.toString();
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }

    private static JSONObject info(File f) throws IOException, JSONException {
        JSONObject o = new JSONObject().put("ruta", rel(f)).put("existe", f.exists());
        if (!f.exists()) return o;
        long[] m = medir(f, new long[2]);
        return o.put("carpeta", f.isDirectory()).put("tam", m[0]).put("archivos", m[1]).put("fecha", f.lastModified());
    }

    private static JSONObject crearCarpeta(File d) throws IOException, JSONException {
        if (d.isFile()) throw new IOException("ya hay un archivo con ese nombre");
        boolean nueva = !d.exists();
        if (nueva && !d.mkdirs()) throw new IOException("no se pudo crear");
        return new JSONObject().put("ruta", rel(d)).put("creada", nueva);
    }

    private static JSONObject mover(File o, File destino) throws IOException, JSONException {
        existe(o);
        if (o.equals(raiz())) throw new IOException("no se mueve todo el almacenamiento");
        if (destino.isFile()) throw new IOException("el destino debe ser una carpeta");
        if (destino.getPath().startsWith(o.getPath() + "/") || destino.equals(o)) throw new IOException("no se mueve una carpeta dentro de sí misma");
        if (!destino.exists() && !destino.mkdirs()) throw new IOException("no se pudo crear la carpeta destino");
        File fin = new File(destino, o.getName());
        if (fin.exists()) throw new IOException("ya hay algo con ese nombre en el destino: no se pisa");
        if (!o.renameTo(fin)) throw new IOException("no se pudo mover");
        return new JSONObject().put("de", rel(o)).put("a", rel(fin));
    }

    private static JSONObject papelera(File f) throws IOException, JSONException {
        existe(f);
        File raiz = raiz(), pap = new File(raiz, ".ZazuPapelera");
        if (f.equals(raiz) || f.equals(pap) || f.getPath().startsWith(pap.getPath() + "/")) throw new IOException("eso no se manda a la papelera");
        File dia = new File(pap, new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date()));
        if (!dia.exists() && !dia.mkdirs()) throw new IOException("no se pudo crear la papelera");
        String nombre = f.getName();
        File fin = new File(dia, nombre);
        for (int i = 2; fin.exists(); i++) fin = new File(dia, nombre + " (" + i + ")");
        if (!f.renameTo(fin)) throw new IOException("no se pudo mover a la papelera");
        return new JSONObject().put("de", rel(f)).put("a", rel(fin)).put("nota", "no se ha borrado: se puede devolver desde .ZazuPapelera");
    }

    /** Los archivos de una orden «subir» (como mucho MAX_SUBIR), ordenados por ruta para que cada pasada del trabajo siga donde iba. */
    static List<File> paraSubir(Context c, JSONObject p) throws IOException {
        if (!Copia.tieneAcceso(c)) throw new IOException("la app no tiene el permiso «Acceso a todos los archivos»");
        JSONObject a = p.optJSONObject("args");
        File f = existe(ruta(a == null ? null : a.optString("ruta", null)));
        List<File> todos = new ArrayList<>();
        ArrayDeque<File> pila = new ArrayDeque<>();
        pila.push(f);
        while (!pila.isEmpty() && todos.size() < MAX_SUBIR) {
            File x = pila.pop();
            if (x.isFile()) todos.add(x);
            else {
                File[] h = x.listFiles();
                if (h != null) for (File y : h) if (!y.getName().startsWith(".")) pila.push(y);
            }
        }
        todos.sort((x, y) -> x.getPath().compareTo(y.getPath()));
        return todos;
    }
}
