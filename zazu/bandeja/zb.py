#!/usr/bin/python3
"""zb — bandeja de Google Tasks/Calendar de Fran (modo sombra por defecto).

  zb run                 un ciclo (lo lanza zazu-bandeja.timer cada 5 min)
  zb status              modo, pausa, último ciclo, contadores            (alias: estado)
  zb log [-n 20]         lo que HARÍA (registro de sombra)                (alias: sombra)
  zb inbox [-n 20]       avisos generados y si se entregaron
  zb pause | resume      interruptor PAUSA (el ciclo no hace nada)        (alias: pausa, reanudar)
  zb shadow on|off       on = sombra (no escribe nada) · off = VIVO (requiere --confirmo)
  zb replay <texto>      vuelve a planificar el elemento cuya clave contiene <texto>; con --run y en vivo, lo ejecuta de nuevo
  zb simular [--json]    simulacro de solo lectura sobre datos reales: solo conteos y tipos
  zb propuestas          propuestas de «Zazu: …» pendientes
  zb confirmar N         ejecuta una propuesta (solo tarea o nota; solo en vivo)
"""
import argparse, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from ciclo import Ciclo, corto
from estado import Estado

ALIAS = {"estado": "status", "sombra": "log", "pausa": "pause", "reanudar": "resume", "simulacro": "simular"}


def cmd_run(a):
    r = Ciclo().run()
    print(json.dumps(r, ensure_ascii=False))
    return 0


def cmd_status(a):
    pausa = config.pausado()
    e = Estado()
    cnt = dict(e.db.execute("SELECT modo||':'||estado, count(*) FROM acciones GROUP BY 1").fetchall())
    ent = dict(e.db.execute("SELECT modo||':'||entregado, count(*) FROM inbox GROUP BY 1").fetchall())
    print(f"modo: {config.modo().upper()}{'  (NO escribe nada: ni Google, ni Cerebro, ni WhatsApp)' if config.modo() == 'sombra' else '  (ESCRIBE de verdad)'}")
    print(f"pausa: {'SÍ' if pausa else 'no'}")
    print(f"último ciclo: {e.meta('ultimo_ciclo', 'nunca')}")
    print(f"vivo desde: {e.meta('vivo_desde', '—')}  ·  primer ciclo: {e.meta('primer_ciclo', '—')}")
    print(f"acciones (modo:estado): {cnt or '—'}")
    print(f"inbox (modo:entregado 0=pendiente 1=enviado 2=solo bandeja): {ent or '—'}")
    print(f"último resumen: {e.meta('ultimo_resumen', '—')}")
    n = e.db.execute("SELECT count(*) FROM propuestas WHERE estado='pendiente'").fetchone()[0]
    print(f"propuestas pendientes: {n}")
    return 0


def cmd_log(a):
    p = Estado().sombra_log
    if not p.exists():
        print("(registro de sombra vacío)")
        return 0
    for ln in p.read_text().splitlines()[-a.n:]:
        d = json.loads(ln)
        print(f"{d['ts']} [{d['tipo']}{' · ANTERIOR: en vivo no se tocaría' if d.get('retro') else ''}] «{d['titulo']}»")
        for x in d["plan"]:
            print(f"    - {x}")
    return 0


def cmd_inbox(a):
    e = Estado()
    for id_, ts, modo, prio, tipo, texto, ent in e.db.execute("SELECT id,ts,modo,prio,tipo,texto,entregado FROM inbox ORDER BY id DESC LIMIT ?", (a.n,)):
        print(f"#{id_} {modo} P{prio} {tipo} entregado={ent}: {texto}")
    return 0


def cmd_pause(a):
    config.asegurar_dir(config.config_dir())
    (config.config_dir() / "PAUSA").write_text("pausado\n")
    print("PAUSA activada: el ciclo no hará nada hasta `zb resume`.")
    return 0


def cmd_resume(a):
    (config.config_dir() / "PAUSA").unlink(missing_ok=True)
    print("PAUSA quitada.")
    return 0


def cmd_shadow(a):
    d = config.asegurar_dir(config.config_dir())
    if a.valor == "on":
        (d / "MODO").write_text("sombra\n")
        print("Modo SOMBRA: no escribe nada.")
    elif a.valor == "off":
        if not a.confirmo:
            print("Esto activa el modo VIVO: escribirá en Google Tasks, en tu Cerebro y te mandará WhatsApp.\nSi estás seguro: zb shadow off --confirmo")
            return 2
        (d / "MODO").write_text("vivo\n")
        print("Modo VIVO activado. Para volver: zb shadow on. Para frenar ya: zb pause.")
    else:
        print(f"modo: {config.modo()}")
    return 0


def cmd_replay(a):
    c = Ciclo(vivo=(config.modo() == "vivo" and a.run), forzar=a.texto)
    r = c.run()
    print(json.dumps(r, ensure_ascii=False))
    if not c.vivo:
        print("(sombra: mira `zb log -n 5`)")
    return 0


def cmd_simular(a):
    c = Ciclo(simular=True)
    c.run()
    inf = c.informe_simulacro()
    if a.json:
        print(json.dumps(inf, ensure_ascii=False, indent=2))
    else:
        for k, v in inf.items():
            print(f"{k}: {v}")
    return 0


def cmd_propuestas(a):
    e = Estado()
    for id_, tipo, campos, estado in e.db.execute("SELECT id,tipo,campos,estado FROM propuestas ORDER BY id DESC LIMIT 20"):
        c = json.loads(campos)
        print(f"#{id_} [{estado}] {tipo}: «{corto(c.get('titulo'), 80)}» {c.get('cuando') or ''}")
    return 0


def cmd_confirmar(a):
    if config.modo() != "vivo":
        print("Solo en modo vivo.")
        return 2
    c = Ciclo(vivo=True)
    r = c.est.db.execute("SELECT tipo, campos, estado FROM propuestas WHERE id=?", (a.n,)).fetchone()
    if not r or r[2] != "pendiente":
        print("No hay esa propuesta pendiente.")
        return 1
    tipo, campos = r[0], json.loads(r[1])
    if tipo == "tarea":
        t = c.g.tarea_crear(campos["cuenta"], "@default", campos["titulo"], campos.get("cuando"))
        print("Tarea creada:", t.get("id", "?")[-4:])
    elif tipo == "nota":
        ruta = c.vault.crear_nota("nota", f"{c.ahora:%Y-%m-%d} {campos['titulo'][:50]}", {"origen": "zazu"}, extra=campos["titulo"])
        print("Nota creada:", ruta.stem)
    else:
        print(f"Una propuesta «{tipo}» no se ejecuta desde aquí.")
        return 1
    c.est.db.execute("UPDATE propuestas SET estado='hecha' WHERE id=?", (a.n,))
    c.est.cerrar()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="zb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("run", "status", "pause", "resume", "propuestas"):
        sp.add_parser(n)
    for n in ("log", "inbox"):
        p = sp.add_parser(n)
        p.add_argument("-n", type=int, default=20)
    p = sp.add_parser("shadow")
    p.add_argument("valor", choices=["on", "off", "status"])
    p.add_argument("--confirmo", action="store_true")
    p = sp.add_parser("replay")
    p.add_argument("texto")
    p.add_argument("--run", action="store_true")
    p = sp.add_parser("simular")
    p.add_argument("--json", action="store_true")
    p = sp.add_parser("confirmar")
    p.add_argument("n", type=int)
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv:
        argv[0] = ALIAS.get(argv[0], argv[0])
    a = ap.parse_args(argv)
    return globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
