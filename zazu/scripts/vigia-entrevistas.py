#!/usr/bin/env python3
"""Monitor de cron (no usa el modelo): detecta hilos NUEVOS de Gmail que piden una acción de Fran
(entrevista, prueba, siguiente paso…) en sus dos cuentas, los ABRE él mismo y solo imprime los que de verdad
piden algo, con el texto ya recortado. Hermes despierta al agente (Haiku) solo cuando esta salida cambia.
Estado: vistos.txt (todo lo visto, para no reabrir) y accion.txt (lo impreso, lista que solo crece).
Si gog falla, sale con código 1: Hermes avisa de que el monitor está roto. Solo lectura."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import recoger  # noqa: E402  (gog con credenciales, cuerpo(), reglas ACCION/RUIDO, limpio())

ESTADO = Path.home() / ".local/state/vigia-empleo"
VISTOS, ACCIONES = ESTADO / "vistos.txt", ESTADO / "accion.txt"
MAX_LINEAS = 200
KW = ('(entrevista OR interview OR "prueba técnica" OR "prueba tecnica" OR assessment OR "proceso de selección" '
      'OR "proceso de seleccion" OR "siguiente paso" OR "next steps" OR "próximos pasos" OR "proximos pasos" '
      'OR disponibilidad OR availability OR candidatura OR "your application" OR reclutador OR recruiter)')
QUERY = f"newer_than:3d -category:promotions -category:social {KW}"
# Jev decide mejor en inglés (el correo puede ir en español). Solo se usa si hay TYPESAFE_API_KEY en ~/.hermes/.env.
PREGUNTA_JEV = ("This email asks the recipient, a job candidate, to take a concrete action in a hiring process: "
                "schedule or attend an interview, complete a test or assessment, confirm availability, or reply about next steps.")
AUTOMATICO = re.compile(r"hemos recibido tu candidatura|we have received your application|thank you for applying|gracias por (tu interés|aplicar|tu candidatura)|"
                        r"no respondas a este|do not reply|job alert|alerta de empleo|is hiring|están contratando|nuevas ofertas|ofertas para", re.I)


def buscar(cuenta):   # recoger.gog ya reintenta si al arrancar el PC aún no hay red
    return recoger.lista(recoger.gog(["gmail", "search", QUERY, "--max", "100"], cuenta), "threads", "messages", "items")


def guardar(path, lineas):
    tmp = tempfile.NamedTemporaryFile("w", dir=ESTADO, delete=False)
    tmp.write("\n".join(lineas) + ("\n" if lineas else ""))
    tmp.close()
    os.replace(tmp.name, path)


FALLO = ESTADO / "gmail-fallo.json"          # desde cuándo falla Gmail (y si ya se avisó)
AVISAR_TRAS_S = 2 * 3600                       # un corte corto (Google, red al arrancar) no merece aviso
VIGILANTE = Path.home() / "hermes-hub/vigilante.py"


def fallo_gmail(e, acciones):
    """Gmail no responde: NO romper el monitor (Hermes anotaría un error cada media hora). Se imprime la lista anterior
    tal cual (sin cambio → el agente no despierta) y se apunta desde cuándo falla. Pasadas 2 h seguidas, un único aviso
    en la app (push del vigilante, sin IA). Al volver, se borra la marca."""
    import time
    print(f"vigia-entrevistas: fallo al consultar Gmail ({type(e).__name__}: {str(e)[:120]})", file=sys.stderr)
    ahora = time.time()
    try:
        st = json.loads(FALLO.read_text()) if FALLO.exists() else {}
    except ValueError:
        st = {}
    st.setdefault("desde", ahora)
    if ahora - st["desde"] >= AVISAR_TRAS_S and not st.get("avisado"):
        desde = time.strftime("%H:%M", time.localtime(st["desde"]))
        cuerpo = json.dumps({"titulo": "Zazu: Gmail no responde", "cuerpo": f"El vigía de entrevistas no puede leer el correo desde las {desde}. Lo sigo intentando cada media hora.",
                             "url": "/?tab=inicio", "tag": "vigia-gmail"})
        py = Path.home() / "hermes-hub/.venv/bin/python"
        try:
            subprocess.run([str(py if py.exists() else "python3"), str(VIGILANTE), "--push-json"], input=cuerpo, text=True, timeout=60, capture_output=True)
            st["avisado"] = True
        except Exception as e2:
            print(f"vigia-entrevistas: no pude avisar ({type(e2).__name__})", file=sys.stderr)
    FALLO.write_text(json.dumps(st))
    print("\n".join(acciones))   # misma salida que la última vez: sin cambio, sin despertar al agente
    return 0


def main():
    ESTADO.mkdir(parents=True, exist_ok=True)
    vistos = VISTOS.read_text().splitlines() if VISTOS.exists() else []
    acciones = ACCIONES.read_text().splitlines() if ACCIONES.exists() else []
    conocidos = set(vistos)
    try:
        por_cuenta = {et: buscar(acc) for et, acc in recoger.CUENTAS}
    except Exception as e:   # nunca imprimir claves: solo el tipo de error
        return fallo_gmail(e, acciones)
    FALLO.unlink(missing_ok=True)
    primera_vez = not vistos
    for et, acc in recoger.CUENTAS:
        for h in reversed(por_cuenta[et]):   # de más antiguo a más nuevo
            hid = str(h.get("id") or "")
            clave = f"{et}:{hid}"
            if not hid or clave in conocidos:
                continue
            vistos.append(clave)
            conocidos.add(clave)
            if primera_vez:
                continue   # línea base: no abrir nada
            de = re.sub(r"\s*<.*", "", h.get("from") or "").strip().strip('"')
            asunto = h.get("subject") or ""
            if recoger.RUIDO.search(asunto + " " + de) or recoger.PORTALES.search(de) or AUTOMATICO.search(asunto):
                continue
            texto = recoger.cuerpo(hid, acc)
            if AUTOMATICO.search(texto[:300]):
                continue
            p = recoger.jev_noul(f"Subject: {asunto}\nFrom: {de}\n\n{texto}", PREGUNTA_JEV)   # None sin clave o si falla
            if (p < 0.6) if p is not None else not recoger.ACCION.search(asunto + " " + texto):
                continue
            acciones.append(f"{clave} · [{et}] {recoger.limpio(de, 40)} · {recoger.limpio(asunto, 90)} ↳ {recoger.limpio(texto, 350)}")
    vistos, acciones = vistos[-MAX_LINEAS:], acciones[-MAX_LINEAS:]
    guardar(VISTOS, vistos)
    guardar(ACCIONES, acciones)
    print("\n".join(acciones))
    return 0


if __name__ == "__main__":
    sys.exit(main())
