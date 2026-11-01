#!/usr/bin/env python3
"""Crea (o rellena otra vez) la cuenta de DEMO pública de HolaZazu: «Lucía», con datos inventados.

Uso: cd ~/Spirit/pagina-web && python3 ops/crear_demo.py
- Se entra desde holazazu.app/demo sin Google. Es de solo lectura: el servidor rechaza cualquier cambio (server.py, DEMO_EMAIL).
- Sin Google y sin crédito: no gasta nada de la clave de Fran.
- Todo lo que hay dentro es inventado: conversaciones, notas, carpetas y recuerdos. Ninguna persona real.
Volver a ejecutarlo borra y rehace las conversaciones de la demo (solo las de la demo).
"""
import sqlite3, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

NOMBRE = "Lucía"
AHORA = time.time()
H = 3600
D = 24 * H

CHATS = [
    ("Organizar la semana", 2 * H, [
        ("user", "Hola Zazu, ¿me ayudas a organizar la semana? Tengo mucho lío."),
        ("assistant", "¡Claro, Lucía! Cuéntame lo fijo que tienes (trabajo, citas, entregas) y lo que te gustaría encajar, y te lo ordeno por días."),
        ("user", "Trabajo de 9 a 15. El martes dentista a las 17:30, el jueves tengo que entregar el informe trimestral y quiero ir al gimnasio 3 días."),
        ("assistant", "Te propongo esto:\n\n- **Lunes:** gimnasio a las 18:00 y repasar el informe 30 min.\n- **Martes:** dentista a las 17:30. Día tranquilo.\n- **Miércoles:** gimnasio a las 18:00 y terminar el borrador del informe.\n- **Jueves:** entregar el informe por la mañana. Tarde libre.\n- **Viernes:** gimnasio a las 18:00.\n\n¿Te lo guardo en tus notas para tenerlo a mano?"),
        ("user", "Sí, guárdalo como importante."),
        ("assistant", "Hecho: lo tienes en Carpetas › Importante › Notas.md, como «Plan de la semana»."),
    ]),
    ("Cena rápida con lo que hay en la nevera", 1 * D + 3 * H, [
        ("user", "Tengo huevos, espinacas, queso y medio pimiento. ¿Qué ceno en 15 minutos?"),
        ("assistant", "Una tortilla abierta de espinacas, pimiento y queso:\n\n1. Saltea el pimiento en tiras 3 min y añade las espinacas hasta que bajen.\n2. Bate 3 huevos con sal y échalos por encima.\n3. Pon el queso, tapa y deja 4-5 min a fuego bajo.\n\nCon una tostada, lista en 15 minutos. ¿Quieres que te apunte en la lista de la compra lo que se te esté acabando?"),
        ("user", "Apunta huevos y pan."),
        ("assistant", "Apuntado en tu lista de la compra: huevos y pan."),
    ]),
    ("Correo al casero por la caldera", 3 * D, [
        ("user", "Ayúdame a escribir un correo educado al casero: la caldera no calienta desde el lunes."),
        ("assistant", "Aquí tienes un borrador:\n\n**Asunto:** Avería de la caldera\n\nHola, Andrés:\n\nTe escribo porque desde el lunes la caldera no calienta el agua ni la calefacción. He probado a reiniciarla siguiendo las instrucciones, sin resultado.\n\n¿Podrías avisar a un técnico esta semana? Estoy en casa por las tardes a partir de las 16:00.\n\nGracias de antemano,\nLucía\n\n¿Lo quieres más formal o así está bien?"),
        ("user", "Perfecto así, gracias."),
        ("assistant", "¡De nada! Si en tres días no te contesta, dímelo y te preparo un recordatorio más firme."),
    ]),
    ("Maleta para Lisboa", 6 * D, [
        ("user", "Me voy 4 días a Lisboa en noviembre. ¿Qué meto en la maleta de mano?"),
        ("assistant", "Para 4 días en noviembre (unos 12-18 °C y alguna lluvia):\n\n- Chaqueta impermeable ligera y un jersey.\n- Calzado cómodo y que agarre: las cuestas y el empedrado resbalan.\n- 2 pantalones y 4 camisetas.\n- Paraguas plegable.\n- Neceser con líquidos de menos de 100 ml en bolsa transparente.\n- DNI, cargador y adaptador (no hace falta: usan el mismo enchufe que en España).\n\n¿Te busco qué ver en el barrio de Alfama?"),
    ]),
]

NOTAS = {
    "Importante": "# Notas\n\n## Plan de la semana\nLunes: gimnasio 18:00 + repasar informe.\nMartes: dentista 17:30.\nMiércoles: gimnasio 18:00 + borrador del informe.\nJueves: entregar informe.\nViernes: gimnasio 18:00.\n",
    "Guardado": "# Notas\n\n## Lista de la compra\n- Huevos\n- Pan\n- Tomates\n- Café\n\n## Ideas para el viaje a Lisboa\n- Tranvía 28 temprano, antes de que se llene.\n- Pastéis de Belém.\n- Mirador de Santa Luzia al atardecer.\n",
}
SOBRE_LUCIA = ["Lucía trabaja de 9 a 15 y va al gimnasio tres días por semana.",
               "Lucía prefiere respuestas cortas y con listas.",
               "Lucía viaja a Lisboa en noviembre."]


class Shim:
    _credito = staticmethod(server.H._credito)

    def fail(self, code, msg):
        raise SystemExit(f"No se pudo crear la demo ({code}): {msg}")

    def send_json(self, obj, code=200):
        self.out = obj


def main():
    us = server.users()
    if server.DEMO_EMAIL not in us:
        server.H.personas_write(Shim(), {"action": "add", "email": server.DEMO_EMAIL, "name": NOMBRE, "nivel": "invitada", "credito": 0})
        us = server.users()
    prof = us[server.DEMO_EMAIL]["profile"]
    with server.USERS_LOCK:
        us = server.users()
        us[server.DEMO_EMAIL].update(onboarded=True)
        us[server.DEMO_EMAIL].setdefault("zazu", {}).update(asistente="Zazu")
        import noticias_invitadas as N   # noticias ya elegidas: en la demo no se puede guardar, así que vienen puestas
        us[server.DEMO_EMAIL]["noticias"] = N.validar({"paises": ["ES"], "temas": [t for t in N.TEMAS if t in ("mundo", "ia")]})
        server.save_users(us)

    # conversaciones inventadas (solo en el perfil de la demo)
    db = server.prof_dir(prof) / "state.db"
    c = sqlite3.connect(db, timeout=10)
    try:
        cols_s = {r[1] for r in c.execute("pragma table_info(sessions)")}
        cols_m = {r[1] for r in c.execute("pragma table_info(messages)")}
        viejas = [r[0] for r in c.execute("select id from sessions where id like 'demo_%'")]
        for sid in viejas:
            c.execute("delete from messages where session_id=?", (sid,))
            c.execute("delete from sessions where id=?", (sid,))
        for i, (titulo, hace, msgs) in enumerate(CHATS):
            sid, t0 = f"demo_{i + 1}", AHORA - hace
            fila = {"id": sid, "source": "cli", "started_at": t0, "title": titulo, "message_count": len(msgs),
                    "last_activity_at": t0 + 60 * len(msgs), "archived": 0, "hidden": 0, "model": server.SHARED["model"]}
            fila = {k: v for k, v in fila.items() if k in cols_s}
            c.execute(f"insert into sessions ({','.join(fila)}) values ({','.join('?' * len(fila))})", list(fila.values()))
            for j, (rol, texto) in enumerate(msgs):
                m = {"session_id": sid, "role": rol, "content": texto, "timestamp": t0 + 60 * j, "active": 1}
                m = {k: v for k, v in m.items() if k in cols_m}
                c.execute(f"insert into messages ({','.join(m)}) values ({','.join('?' * len(m))})", list(m.values()))
        c.commit()
    finally:
        c.close()

    # carpetas y recuerdos inventados
    raiz = server.GUEST_FILES / prof
    for carpeta, texto in NOTAS.items():
        (raiz / carpeta).mkdir(parents=True, exist_ok=True)
        (raiz / carpeta / "Notas.md").write_text(texto)
    (server.prof_dir(prof) / "memories").mkdir(exist_ok=True)
    (server.prof_dir(prof) / "memories" / "USER.md").write_text(server.MEM_SEP.join(SOBRE_LUCIA))
    print(f"Demo lista: perfil {prof}, {len(CHATS)} conversaciones, carpetas {', '.join(NOTAS)}. Se entra en holazazu.app/demo")


if __name__ == "__main__":
    main()
