#!/usr/bin/env python3
"""Lecciones: lo que Zazu debería haber aprendido, en una frase, con la evidencia que lo respalda.
Una lección nace «propuesta» y solo vale cuando Fran la aprueba. Aquí no se aplica nada a Hermes: eso es un paso aparte.

  lecciones.py listar [propuesta|aprobada|rechazada]
  lecciones.py proponer "texto" --evidencia 3464,3465      (números de fila del almacén; se guardan como identificadores estables)
  lecciones.py aprobar N [N…]  ·  lecciones.py rechazar N [N…]
  lecciones.py ver N           (enseña los mensajes que la respaldan, recortados)
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen

# Una lección acaba en la memoria de Zazu y en notas: nada de teléfonos, correos, cuentas ni enlaces.
PRIVADO = re.compile(r"@|https?://|www\.|\d[\d\s.\-]{6,}\d|\b[A-Z]{2}\d{2}[A-Z0-9]{10,}\b", re.I)
MAX = 280


def claves_de(c, evidencia):
    """Convierte la evidencia a identificadores estables (la `clave` del hecho). Acepta claves o números de fila; las filas de
    las correcciones se rehacen cada noche, así que el número no sirve para guardar. Falla si algo no existe."""
    out = []
    for e in evidencia:
        e = str(e).strip()
        if not e:
            continue
        r = c.execute("SELECT clave FROM hecho WHERE id=?" if e.isdigit() else "SELECT clave FROM hecho WHERE clave=?", (int(e) if e.isdigit() else e,)).fetchone()
        if not r:
            raise ValueError(f"la evidencia {e} no está en el almacén")
        if r["clave"] not in out:
            out.append(r["clave"])
    return out


def proponer(c, texto, evidencia=(), origen="claude"):
    """→ id de la lección, o None si ya existía una igual (da igual su estado). ValueError si no es válida."""
    texto = " ".join((texto or "").split())
    if not 15 <= len(texto) <= MAX:
        raise ValueError(f"una lección va de 15 a {MAX} caracteres (tiene {len(texto)})")
    if PRIVADO.search(texto):
        raise ValueError("la lección parece llevar un teléfono, correo, cuenta o enlace: se queda en la evidencia, no en el texto")
    claves = claves_de(c, evidencia)
    if c.execute("SELECT 1 FROM leccion WHERE lower(texto)=lower(?)", (texto,)).fetchone():
        return None
    cur = c.execute("INSERT INTO leccion(ts,texto,evidencia,estado,origen) VALUES(?,?,?,'propuesta',?)",
                    (time.time(), texto, json.dumps(claves, ensure_ascii=False), origen))
    c.commit()
    return cur.lastrowid


def decidir(c, ids, estado):
    """Aprobar o rechazar. Solo cambia las que están pendientes: una decisión tuya no se pisa sin querer. → cuántas cambió."""
    n = 0
    for i in ids:
        n += c.execute("UPDATE leccion SET estado=?, decidida=? WHERE id=? AND estado='propuesta'", (estado, time.time(), i)).rowcount
    c.commit()
    return n


def listar(c, estado=None):
    q, a = "SELECT * FROM leccion", ()
    if estado:
        q, a = q + " WHERE estado=?", (estado,)
    return c.execute(q + " ORDER BY id", a).fetchall()


def evidencia(c, lec):
    """Los hechos que respaldan una lección: [(clave, perfil, ts, texto)]."""
    try:
        claves = json.loads(lec["evidencia"] or "[]")
    except ValueError:
        claves = []
    if not claves:
        return []
    marcas = ",".join("?" * len(claves))
    return c.execute(f"SELECT id, perfil, ts, texto FROM hecho WHERE clave IN ({marcas}) ORDER BY ts", claves).fetchall()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    s = sub.add_parser("listar")
    s.add_argument("estado", nargs="?", choices=["propuesta", "aprobada", "rechazada"])
    s = sub.add_parser("proponer")
    s.add_argument("texto")
    s.add_argument("--evidencia", default="")
    for o in ("aprobar", "rechazar", "ver"):
        s = sub.add_parser(o)
        s.add_argument("ids", nargs="+", type=int)
    a = ap.parse_args(argv)
    c = almacen.conectar()
    if a.orden == "listar":
        filas = listar(c, a.estado)
        for r in filas:
            print(f"{r['id']:3d} [{r['estado']:9}] {r['texto']}   ({len(json.loads(r['evidencia'] or '[]'))} pruebas · {r['origen']})")
        if not filas:
            print("(ninguna)")
    elif a.orden == "proponer":
        try:
            i = proponer(c, a.texto, [x for x in a.evidencia.split(",") if x.strip()])
        except ValueError as e:
            sys.exit(f"No se guardó: {e}")
        print(f"lección {i} propuesta" if i else "ya existía una igual")
    elif a.orden in ("aprobar", "rechazar"):
        n = decidir(c, a.ids, "aprobada" if a.orden == "aprobar" else "rechazada")
        print(f"{n} lección(es) {'aprobadas' if a.orden == 'aprobar' else 'rechazadas'}" + ("" if n == len(a.ids) else " (las demás no existen o ya estaban decididas)"))
    else:
        for i in a.ids:
            r = c.execute("SELECT * FROM leccion WHERE id=?", (i,)).fetchone()
            if not r:
                print(f"{i}: no existe")
                continue
            print(f"{r['id']} [{r['estado']}] {r['texto']}")
            for h in evidencia(c, r):
                print(f"    · {time.strftime('%d/%m', time.localtime(h['ts']))} {h['perfil']}: {(h['texto'] or '')[:160]!r}")


if __name__ == "__main__":
    main()
