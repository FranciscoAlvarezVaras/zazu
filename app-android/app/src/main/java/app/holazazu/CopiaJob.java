package app.holazazu;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.os.SystemClock;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Trabajo en segundo plano (JobScheduler de Android, sin librerías): copia de WhatsApp y fotos (cada ~2 h con WiFi, y al abrir la app),
 * recogida de avisos (2.5) y peticiones de Zazu (cada 15 min; solo AVISA con una notificación, nunca hace nada sin que Fran pulse Permitir)
 * y las órdenes «subir» que Fran ya permitió (JOB_SUBIR, con WiFi).
 * Cada pasada de subida dura como mucho 8 minutos; si queda algo, se programa otra en un minuto. Android puede pararla (onStopJob) y se sigue luego.
 */
public class CopiaJob extends JobService {
    // un «parar» POR TRABAJO: Android usa esta misma instancia para todos los que corren a la vez, y uno compartido mezclaba sus paradas
    private final Map<Integer, AtomicBoolean> paradas = new ConcurrentHashMap<>();

    @Override
    public boolean onStartJob(JobParameters p) {
        AtomicBoolean parar = new AtomicBoolean(false);
        paradas.put(p.getJobId(), parar);
        new Thread(() -> {
            boolean otraVez = false;
            long hasta = SystemClock.elapsedRealtime() + 8 * 60_000L;
            try {
                if (p.getJobId() == Copia.JOB_SONDEO) {
                    java.io.IOException fallo = null;
                    try {
                        Avisos.recoger(this);   // 2.5: recordatorios, rutinas, permisos y alertas como notificación
                    } catch (Copia.SinToken e) {
                        throw e;
                    } catch (java.io.IOException e) {
                        fallo = e;   // las peticiones se miran igual
                    }
                    if (Copia.tieneAcceso(this)) Peticiones.sondear(this, null);
                    if (fallo != null) throw fallo;
                } else if (p.getJobId() == Copia.JOB_SUBIR) {
                    if (!Copia.subirOrdenes(this, parar, hasta) && !parar.get()) Copia.seguirSubida(this, 60_000L);
                } else if (!Copia.copiar(this, parar, hasta) && !parar.get()) {
                    Copia.seguir(this, 60_000L);
                }
            } catch (Copia.SinToken e) {
                Copia.prefs(this).edit().remove("token").apply();   // Fran quitó el móvil en el servidor: al abrir la app se pide otro
            } catch (Exception e) {
                otraVez = true;   // sin red, servidor caído…: Android lo reintenta con espera creciente
            }
            paradas.remove(p.getJobId(), parar);
            if (!parar.get()) jobFinished(p, otraVez);
        }, "zazu-copia").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters p) {
        AtomicBoolean parar = paradas.get(p.getJobId());
        if (parar != null) parar.set(true);
        return true;
    }
}
