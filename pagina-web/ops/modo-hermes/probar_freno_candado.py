#!/usr/bin/env python3
"""Pruebas de las dos mejoras de seguridad de movil-aprobacion.py (auditoría 2026-10-21):
  A) Freno de bucles: la MISMA acción repetida 3 veces en una sesión se bloquea.
  B) Candado de claves: leer/escribir/buscar en rutas sensibles (resolviendo symlinks) se bloquea.

Comprueba SOLO la decisión del hook (acción + mensaje); NUNCA imprime el contenido de un .env ni de ningún
fichero sensible. Aísla el estado del freno con XDG_STATE_HOME en un directorio temporal, para no tocar
~/.local/state real ni interferir con sesiones de verdad.

Uso:  python3 probar_freno_candado.py [--hook RUTA]
"""
import argparse, json, os, subprocess, sys, tempfile

HOOK_POR_DEFECTO = os.path.expanduser("~/.hermes/agent-hooks/movil-aprobacion.py")


def correr(hook, payload, entorno):
    r = subprocess.run([sys.executable, hook], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, timeout=20, env=entorno)
    assert r.returncode == 0, f"rc={r.returncode} stderr={r.stderr[:200]}"
    out = r.stdout.strip()
    if not out:
        return None                       # sin salida = permitir
    data = json.loads(out)                # debe ser SIEMPRE JSON válido
    assert isinstance(data, dict) and data.get("action") in ("approve", "block", "modify"), f"salida rara: {out[:200]}"
    return data


def accion(d):
    return d.get("action") if isinstance(d, dict) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hook", default=HOOK_POR_DEFECTO)
    a = ap.parse_args()
    hook = os.path.abspath(a.hook)
    assert os.path.exists(hook), f"no existe el hook: {hook}"

    fallos = []
    with tempfile.TemporaryDirectory(prefix="freno-candado-") as tmp:
        env = dict(os.environ, XDG_STATE_HOME=tmp)   # estado del freno aislado

        def T(cmd, sid="pruebaA"):
            return {"tool_name": "terminal", "tool_input": {"command": cmd}, "session_id": sid}

        def R(path, sid="pruebaB"):
            return {"tool_name": "read_file", "tool_input": {"path": path}, "session_id": sid}

        def chk(nombre, cond):
            print(("OK    " if cond else "FALLA ") + nombre)
            if not cond:
                fallos.append(nombre)

        # (1) la MISMA acción 3 veces -> freno (bloqueo en la 3ª); la 1ª y 2ª pasan
        d1 = correr(hook, T("ls -la /tmp"), env)
        d2 = correr(hook, T("ls -la /tmp"), env)
        d3 = correr(hook, T("ls -la /tmp"), env)
        chk("(1) misma acción 1ª vez no frena", accion(d1) != "block")
        chk("(1) misma acción 2ª vez no frena", accion(d2) != "block")
        chk("(1) misma acción 3ª vez -> FRENO (block)",
            accion(d3) == "block" and "Freno" in (d3 or {}).get("message", ""))

        # (2) leer ~/.hermes/profiles/tecnico/.env -> candado (NO se imprime el contenido)
        d = correr(hook, R("~/.hermes/profiles/tecnico/.env"), env)
        chk("(2) read_file .env de perfil -> CANDADO (block)",
            accion(d) == "block" and "Candado" in (d or {}).get("message", ""))
        # y por el enlace simbólico hermes/ajustes/profiles -> ~/.hermes/profiles
        d = correr(hook, R(os.path.expanduser("~/Escritorio/Spirit/hermes/ajustes/profiles/tecnico/.env")), env)
        chk("(2b) read_file .env por el symlink de ajustes -> CANDADO (block)", accion(d) == "block")

        # (3) leer un fichero normal de ~/Spirit -> permitido
        normal = os.path.expanduser("~/Escritorio/Spirit/README.md")
        d = correr(hook, R(normal), env)
        chk("(3) read_file de un fichero normal de ~/Spirit -> permitido", d is None)

        # (4) leer DOS archivos distintos muchas veces -> permitido (la huella incluye los argumentos)
        ok4 = True
        for i in range(8):
            da = correr(hook, R(f"/home/server/Escritorio/Spirit/doc_{i}.md", "pruebaC"), env)
            db = correr(hook, R(f"/home/server/Escritorio/Spirit/otro_{i}.md", "pruebaC"), env)
            ok4 = ok4 and da is None and db is None
        chk("(4) leer archivos DISTINTOS muchas veces -> permitido (no frena)", ok4)

        # Extra robustez: entradas raras siguen devolviendo JSON válido o nada, sin caerse
        for raro in (
            {"tool_name": "terminal", "tool_input": "no-es-un-dict", "session_id": "x"},
            {"tool_name": "", "tool_input": {}, "session_id": "x"},
            {"tool_input": {"command": "echo hola"}},                       # sin tool_name ni session_id
            {"tool_name": "read_file", "tool_input": {"path": ""}, "session_id": "x"},
        ):
            try:
                correr(hook, raro, env)                                     # no debe lanzar ni devolver basura
                chk(f"(5) entrada rara no rompe el hook: {json.dumps(raro)[:40]}", True)
            except Exception as e:
                chk(f"(5) entrada rara no rompe el hook: {json.dumps(raro)[:40]} ({e})", False)

    print(f"\n{'TODO OK' if not fallos else str(len(fallos)) + ' FALLOS: ' + ', '.join(fallos)}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
