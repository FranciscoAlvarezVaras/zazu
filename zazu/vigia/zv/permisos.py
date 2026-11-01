"""Permisos que aprenden: reglas «siempre / nunca» que Fran da desde la app sobre una CLAVE ESTRECHA, y el reparto de cada propuesta
del vigía según su riesgo (bajo, medio, alto), esa regla y el escudo.

    clave estrecha   «<acción>:remitente:<id>», p. ej. apuntar_tarea:remitente:wa-1a2b3c4d · apuntar_cita:remitente:ana@empresa.es
    al proponer      regla «nunca»                          → no se enseña (la fila queda descartada, con su rastro en el registro)
                     regla «siempre» + riesgo bajo + limpia → «auto»: aceptada sin preguntar
                     lo demás (riesgo alto siempre)         → se pregunta
    sospechosa       (el escudo saltó) nunca se aplica sola ni la cubre un «siempre»; se enseña con aviso.

En modo sombra «aceptada» significa que la app la ofrece ya preparada para apuntarla con un toque: NUNCA se escribe sola en Google.
Fuera de la sombra, lo que puede escribir el vigía sigue igual, salvo que una propuesta de riesgo alto o sospechosa nunca se escribe sola.

Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: tools/approval_store.py (tabla permission_memory,
set_permission/clear_permission), tools/proactive_tools.py (parse_approval_response: «always» solo se recuerda en riesgo bajo o medio)
y agents/proactive_agent.py (reparto: always_deny se salta, always_approve se aprueba solo).
Cambios: tabla `permisos` dentro de avisos.db (sin cola propia: la propuesta es la fila de `avisos`); decisiones «siempre/nunca» en
español; «siempre» solo aprueba solo el riesgo bajo (el medio sigue preguntando); el riesgo alto y las sospechosas nunca se recuerdan
ni se aprueban solas; el riesgo lo fija el vigía (el modelo solo puede subirlo); contadores de sí/no/aplicada y fechas en epoch."""
import re

from .escudo import normalizar
from .priv import limpio

RIESGOS = ("bajo", "medio", "alto")
DECISIONES = ("siempre", "nunca")
RESPUESTAS = ("si", "no", "siempre", "nunca")
CLAVE_OK = re.compile(r"[a-z_]{3,30}:[a-z]{3,20}:[\w@.+-]{1,120}")
# dinero u organismos oficiales en el título: riesgo alto aunque sea una tarea. Se busca sobre el título normalizado (sin
# tildes, por eso «págame», «pagué» o «préstamo» casan); «€» va aparte porque no es letra y \b no lo ve tras un espacio.
ALTO = re.compile(r"€|\b(?:euros?|dinero)\b|"
                  r"\b(?:pag(?:ar|o|a|ue)|transfer|bizum|ingres(?:ar|o)|factura|recibo|multa|sancion|embargo|deuda|impago|hacienda|aeat|dgt|"
                  r"seguridad social|sepe|requerimiento|tarjeta|banco|iban|contrasena|firmar|prestamo|abon(?:ar|o)|cobr(?:ar|o))\w*", re.I)


def clave(accion, ambito, ident):
    """Clave estrecha válida o None. `ident` se limpia (minúsculas, sin espacios)."""
    ident = re.sub(r"[^\w@.+-]", "", limpio(ident, 120).lower())
    k = f"{accion}:{ambito}:{ident}"
    return k if CLAVE_OK.fullmatch(k) else None


def accion_de(tipo):
    """'tarea' | 'evento' → la acción de la clave."""
    return "apuntar_cita" if tipo == "evento" else "apuntar_tarea"


def riesgo(tipo, titulo="", modelo=None, minimo=None):
    """Riesgo de una propuesta: suelo fijo por tipo (tarea bajo, evento medio), alto si toca dinero u organismos; `minimo` y lo que
    diga el modelo solo lo SUBEN (un texto de terceros no puede bajar el riesgo)."""
    r = "medio" if tipo == "evento" else "bajo"
    if ALTO.search(normalizar(titulo)):
        r = "alto"
    for extra in (minimo, modelo):
        if extra in RIESGOS and RIESGOS.index(extra) > RIESGOS.index(r):
            r = extra
    return r


def regla(db, k):
    return db.c.execute("SELECT * FROM permisos WHERE clave=?", (k,)).fetchone() if k else None


def decidir(db, k, nivel, sospechosa=False):
    """→ 'ocultar' | 'auto' | 'preguntar'. Una sospechosa con «siempre» se pregunta; el riesgo alto se pregunta siempre."""
    r = regla(db, k)
    if r and r["decision"] == "nunca":
        return "ocultar"
    if r and r["decision"] == "siempre" and nivel == "bajo" and not sospechosa:
        return "auto"
    return "preguntar"


DECISION_REPARTO = {"ocultar": "nunca", "auto": "auto"}      # valor de avisos.decision al crear la propuesta


def tras_alta(db, cfg, id_, k, reparto, fuente, titulo, flujo):
    """Tras crear la fila de una propuesta nueva: «ocultar» la cierra y lo anota en el registro (→ True: no hay más que hacer);
    «auto» suma un uso a la regla. → False si la propuesta sigue su curso normal."""
    if reparto == "auto":
        aplicada(db, k)
    if reparto != "ocultar":
        return False
    from . import registro
    db.set(id_, estado="descartado")
    aplicada(db, k)
    registro.anota(db, "descarto", fuente, f"No te lo enseño: dijiste «No, nunca» a propuestas como esta: {titulo}", None, flujo=flujo,
                   ref=f"aviso:{id_}", modo="sombra", clave=f"nunca:{id_}", cfg=cfg)
    return True


def aplicada(db, k):
    db.c.execute("UPDATE permisos SET aplicada=aplicada+1, usado=? WHERE clave=?", (db.ts(), k))
    db.c.commit()


def anotar_respuesta(db, k, si):
    """Un «sí» o «no» suelto suma en la regla de esa clave si existe (no crea ninguna)."""
    if k:
        db.c.execute(f"UPDATE permisos SET {'veces_si' if si else 'veces_no'}={'veces_si' if si else 'veces_no'}+1, actualizado=? WHERE clave=?", (db.ts(), k))
        db.c.commit()


def recordar(db, k, decision, ejemplo=""):
    """Crea o cambia la regla de `k` (siempre | nunca) y suma el sí o el no."""
    if decision not in DECISIONES or not (k and CLAVE_OK.fullmatch(k)):
        raise ValueError("regla no válida")
    si, ahora = decision == "siempre", db.ts()
    db.c.execute("INSERT INTO permisos(clave,decision,veces_si,veces_no,creado,actualizado,ejemplo) VALUES(?,?,?,?,?,?,?) "
                 "ON CONFLICT(clave) DO UPDATE SET decision=excluded.decision, veces_si=veces_si+?, veces_no=veces_no+?, actualizado=excluded.actualizado, "
                 "ejemplo=COALESCE(NULLIF(excluded.ejemplo,''), ejemplo)",
                 (k, decision, int(si), int(not si), ahora, ahora, limpio(ejemplo, 90), int(si), int(not si)))
    db.c.commit()


def quitar(db, k):
    cur = db.c.execute("DELETE FROM permisos WHERE clave=?", (k,))
    db.c.commit()
    return cur.rowcount > 0


def listar(db):
    return [dict(r) for r in db.c.execute("SELECT * FROM permisos ORDER BY actualizado DESC")]


def puede_sola(nivel, sospechosa):
    """¿Puede el vigía escribirla en Google sin preguntar (cuando no está en sombra)? Nunca si es de riesgo alto o sospechosa."""
    return nivel != "alto" and not sospechosa


def es_propuesta(fila):
    return (fila["tipo"] or "").startswith(("item_", "flujo_"))


def responder(db, fila, que):
    """Respuesta de Fran a una propuesta: si | no | siempre | nunca. → (ok, mensaje). Lo de «siempre/nunca» solo en riesgo bajo o medio,
    y «siempre» nunca en una sospechosa. Con «nunca» se cierran también las demás abiertas de la misma clave; con «siempre», las de riesgo
    bajo y limpias de esa clave quedan aceptadas (la app se ordena sola)."""
    if que not in RESPUESTAS:
        return False, "respuesta no válida: si, no, siempre o nunca"
    if not es_propuesta(fila):
        return False, "ese aviso no es una propuesta del vigía"
    nivel, k, sosp = fila["riesgo"] or "medio", fila["permiso"], bool(fila["sospechoso"])
    if que in DECISIONES:
        if nivel == "alto":
            return False, "esta propuesta es de riesgo alto: se pregunta siempre, no se puede recordar"
        if que == "siempre" and sosp:
            return False, "esta propuesta viene de un texto sospechoso: no se puede aceptar «siempre»"
        if not k:
            return False, "esta propuesta no tiene clave para recordar la decisión"
        recordar(db, k, que, fila["titulo"])
    else:
        anotar_respuesta(db, k, que == "si")
    si = que in ("si", "siempre")
    db.set(fila["id"], estado="hecho" if si else "descartado", decision="si" if si else "no")
    abiertas = "estado IN ('nuevo','visto') AND (tipo LIKE 'item\\_%' ESCAPE '\\' OR tipo LIKE 'flujo\\_%' ESCAPE '\\')"
    if que == "nunca":
        db.c.execute(f"UPDATE avisos SET estado='descartado', decision='nunca' WHERE permiso=? AND id<>? AND {abiertas}", (k, fila["id"]))
    elif que == "siempre":
        db.c.execute(f"UPDATE avisos SET decision='auto' WHERE permiso=? AND id<>? AND riesgo='bajo' AND COALESCE(sospechoso,0)=0 "
                     f"AND decision IS NULL AND {abiertas}", (k, fila["id"]))
    db.c.commit()
    return True, {"si": "Aceptada", "no": "Descartada", "siempre": "Aceptada: las próximas parecidas las dejo preparadas",
                  "nunca": "Descartada: no te enseño más como esta"}[que]
