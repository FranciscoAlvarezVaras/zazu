#!/usr/bin/env python3
"""Visor de registros (visor.py): leer el journal de la app y los archivos de Hermes, juntar los Traceback, quitar el ruido,
tachar lo personal, agrupar errores iguales y leer solo lo nuevo. Con un journalctl FALSO en el PATH y carpetas temporales:
no toca los registros de verdad. Todos los datos son inventados.

    python3 -m unittest tests.test_visor -v"""
import importlib, json, os, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _journal(lineas):
    """Las líneas en el formato de `journalctl -o json`."""
    t0 = int(time.time() * 1e6) - 60_000_000
    return "\n".join(json.dumps({"MESSAGE": m, "__REALTIME_TIMESTAMP": str(t0 + i * 1000), "__CURSOR": f"c{i}", "PRIORITY": "6",
                                 "SYSLOG_IDENTIFIER": "python3"}) for i, m in enumerate(lineas))


class Visor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = home = Path(self.tmp.name)
        self.bin = home / "bin"
        self.bin.mkdir()
        self.path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}:{self.path}"
        (home / ".hermes/logs").mkdir(parents=True)
        (home / ".hermes/profiles/zipepa/logs").mkdir(parents=True)
        self.journal([])
        import visor
        self.v = importlib.reload(visor)
        self.v.HERMES = home / ".hermes"
        self.v.DIR = home / "visor"
        self.v.CURSOR = self.v.DIR / "cursor.json"
        self.v.INVITADOS = home / "errores-invitadas.jsonl"

    def tearDown(self):
        os.environ["PATH"] = self.path
        self.tmp.cleanup()

    def journal(self, lineas):
        datos = self.home / "journal.json"
        datos.write_text(_journal(lineas))
        f = self.bin / "journalctl"
        f.write_text(f"#!/bin/sh\ncase \"$*\" in *after-cursor*) exit 0;; esac\ncat {datos}\n")
        f.chmod(0o755)

    def test_traceback_mezclado_con_otra_peticion(self):
        self.journal(["web /index.html navigate Mozilla", "Traceback (most recent call last):",
                      '  File "/x/server.py", line 10, in do_GET', "    hola()",
                      "GET /api/x → 404 no existe",   # otra petición a la vez
                      "----------------------------------------", "[vist#0:0/webp @ 0x1] ruido de ffmpeg",
                      "TypeError: argument of type 'PosixPath' is not iterable", "", "error POST /api/subir: BrokenPipeError"])
        self.v.recoger()
        es = self.v.leer(n=50)
        tb = [e for e in es if e["x"].startswith("TypeError")]
        self.assertEqual(len(tb), 1)
        self.assertIn("do_GET", tb[0]["d"])
        self.assertEqual([e["g"] for e in es if e["x"].startswith("GET /api/x")], ["aviso"])
        self.assertFalse([e for e in es if "ffmpeg" in e["x"] or e["x"].startswith("---")])
        self.assertEqual([e["g"] for e in es if e["x"].startswith("error POST")], ["error"])

    def test_hermes_ruido_continuacion_y_privacidad(self):
        (self.home / ".hermes/logs/agent.log").write_text(
            "2026-10-24 10:00:00,1 INFO hermes_cli.mem_trim: memory trim\n"
            "2026-10-24 10:00:01,1 INFO gateway.run: inbound message: platform=whatsapp user=Pepa Pérez chat=34600111222@lid "
            "msg='mi secreto' reply_to_text='otro secreto'\n"
            "2026-10-24 10:00:02,1 ERROR __main__: falló el correo de pepa@example.com\n"
            "Traceback (most recent call last):\n  File \"/x/cron.py\", line 3, in run\nKeyError: 'p'\n"
            "2026-10-24 10:00:03,1 INFO hermes_cli.plugins: cargado\n")
        (self.home / ".hermes/profiles/zipepa/logs/agent.log").write_text("2026-10-24 10:00:04,1 WARNING tools.mcp: lento\n")
        self.v.recoger()
        es = self.v.leer(desde=0, n=50)
        textos = json.dumps(es, ensure_ascii=False)
        for secreto in ("mi secreto", "otro secreto", "Pepa", "pepa@example.com", "34600111222", "memory trim", "cargado"):
            self.assertNotIn(secreto, textos)
        err = [e for e in es if e["g"] == "error"][0]
        self.assertIn("KeyError", err["d"])
        self.assertEqual([(e["o"], e["p"]) for e in es if e["g"] == "aviso"], [("invitados", "zipepa")])

    def test_solo_lo_nuevo_y_rotacion(self):
        log = self.home / ".hermes/logs/agent.log"
        log.write_text("2026-10-24 10:00:00,1 ERROR a: uno\n")
        self.assertEqual(self.v.recoger(), 1)
        self.assertEqual(self.v.recoger(), 0)
        with open(log, "a") as f:
            f.write("2026-10-24 10:01:00,1 ERROR a: dos\n2026-10-24 10:02:00,1 ERROR a: a medio escri")
        self.assertEqual(self.v.recoger(), 1)   # la línea a medias espera
        log.rename(log.with_name("agent.log.1"))   # rota: lo que faltaba del viejo se lee de su copia
        with open(log.with_name("agent.log.1"), "a") as f:
            f.write("bir\n")
        log.write_text("2026-10-24 10:03:00,1 ERROR a: tres\n")
        self.assertEqual(self.v.recoger(), 2)
        self.assertEqual([e["x"] for e in self.v.leer(desde=0)], ["a: tres", "a: a medio escribir", "a: dos", "a: uno"])

    def test_no_toca_sys_path(self):
        """~/.hermes/scripts tiene un movil.py: si el visor la metiera en sys.path, el Hub cargaría ese en vez del suyo (2026-10-24)."""
        import subprocess
        r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); antes = list(sys.path); import visor, movil; "
                            "print(sys.path == antes, movil.__file__)", str(REPO)], capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(r.stdout.split(), ["True", str(REPO / "movil.py")], r.stderr)

    def test_agrupa_errores_iguales(self):
        for i in (7, 8, 9):
            self.v.anotar("app", "error", f"TimeoutError: job {i}a1b2c3d4 tardó {i} s")
        self.v.anotar("app", "error", "KeyError: 'x'")
        gs = self.v.grupos(time.time() - 60)
        self.assertEqual([g["n"] for g in gs], [3, 1])
        md = self.v.resumen_md({})
        self.assertIn("| 3 | 🔴 |", md)
        self.assertIn("Todo funciona", md)


if __name__ == "__main__":
    unittest.main()
