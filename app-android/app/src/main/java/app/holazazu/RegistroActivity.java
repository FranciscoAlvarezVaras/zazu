package app.holazazu;

import android.app.Activity;
import android.os.Bundle;
import android.widget.ScrollView;
import android.widget.TextView;

import java.text.DateFormat;
import java.util.Date;

/** «Registro de Zazu» (mantén pulsado el icono de la app): todo lo que Zazu pidió, qué respondió Fran y qué se hizo; y la última copia. */
public class RegistroActivity extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        TextView t = new TextView(this);
        int p = (int) (20 * getResources().getDisplayMetrics().density);
        t.setPadding(p, p, p, p);
        t.setTextSize(15);
        t.setTextColor(0xFF1F3B4D);
        t.setTextIsSelectable(true);
        long ultima = Copia.prefs(this).getLong("ultima_copia", 0);
        String cabecera = "Registro de Zazu\n\n"
                + "Acceso a archivos: " + (Copia.tieneAcceso(this) ? "sí" : "NO (ábrela y pulsa «Dar permiso»)") + "\n"
                + "Conectada al servidor: " + (Copia.token(this) != null ? "sí" : "aún no (ábrela con la sesión iniciada)") + "\n"
                + "Última copia completa de WhatsApp y fotos: " + (ultima > 0 ? DateFormat.getDateTimeInstance().format(new Date(ultima)) : "todavía ninguna") + "\n\n"
                + "Peticiones (lo más nuevo arriba):\n\n";
        new Thread(() -> {
            String r = Peticiones.registro(this);
            runOnUiThread(() -> t.setText(cabecera + r));
        }).start();
        ScrollView s = new ScrollView(this);
        s.setBackgroundColor(0xFFF7F1E3);
        s.addView(t);
        setContentView(s);
    }
}
