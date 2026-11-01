"""Acceso a Google (gog). Lecturas siempre con --readonly: Google bloquea cualquier escritura. Las ÚNICAS escrituras posibles
son tasks add / tasks update / tasks done (lista cerrada, flags cerrados) y solo si el cliente se creó con vivo=True.
Nunca: gmail send, calendar create/update/delete/respond, tasks delete, invitar. --gmail-no-send siempre."""
import json, os, re, subprocess, time
from datetime import timedelta
from pathlib import Path

import config

ESCRITURAS = {("tasks", "add"), ("tasks", "update"), ("tasks", "done")}
FLAGS_OK = {"--title", "--due", "--notes"}
ID_OK = re.compile(r"^[A-Za-z0-9_@.\-]{1,200}$")


class GogError(RuntimeError):
    def __init__(self, msg, codigo=1):
        super().__init__(msg)
        self.codigo = codigo            # 4 = hay que volver a autorizar


def _entorno():
    env = dict(os.environ, PATH=f"{config.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin")
    try:
        for linea in (config.home() / ".hermes/.env").read_text().splitlines():
            m = re.match(r"^(GOG_KEYRING_PASSWORD|GOG_ACCOUNT)=(.*)$", linea.strip())
            if m:
                env[m.group(1)] = m.group(2).strip().strip("\"'")
    except OSError:
        pass
    return env


class Google:
    def __init__(self, vivo=False):
        self.vivo = vivo
        self.env = _entorno()
        self.cuentas = config.reglas()["cuentas"]
        self.llamadas = []              # (verbo, escritura) para tests e informes

    def _run(self, cuenta, args, escribir=False, intentos=2):
        if escribir:
            if not self.vivo:
                raise PermissionError("modo sombra: no se escribe en Google")
            if tuple(args[:2]) not in ESCRITURAS:
                raise PermissionError(f"acción fuera de la lista cerrada: {args[:2]}")
            for a in args[2:]:
                if a.startswith("--") and a.split("=", 1)[0] not in FLAGS_OK:
                    raise PermissionError(f"flag fuera de la lista cerrada: {a.split('=', 1)[0]}")
                if not a.startswith("--") and not ID_OK.match(a):
                    raise PermissionError("identificador raro")
        acc = self.cuentas.get(cuenta)
        cmd = [config.gog_bin()] + ([f"--account={acc}"] if acc else []) + ["--gmail-no-send", "--no-input", "--json"]
        if not escribir:
            cmd.append("--readonly")
        cmd += args
        self.llamadas.append((" ".join(args[:2]), escribir))
        for i in range(intentos):
            r = subprocess.run(cmd, env=self.env, capture_output=True, text=True, timeout=90)
            if r.returncode in (0, 3) or r.returncode == 4 or i == intentos - 1:
                break
            time.sleep(0 if os.environ.get("ZB_SIN_ESPERA") else 8)
        if r.returncode not in (0, 3):
            raise GogError(f"gog {args[0]} {args[1]} falló (código {r.returncode})", r.returncode)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    @staticmethod
    def _lista(d, *claves):
        if isinstance(d, list):
            return d
        for k in claves:
            if isinstance(d, dict) and isinstance(d.get(k), list):
                return d[k]
        return []

    # ── lecturas ──
    def listas(self, cuenta):
        excl = {x.lower() for x in config.reglas()["listas_excluidas"]}
        return [l for l in self._lista(self._run(cuenta, ["tasks", "lists", "list"]), "tasklists", "lists", "items")
                if str(l.get("title") or "").lower() not in excl]

    def tareas(self, cuenta, lista_id):
        ts = self._lista(self._run(cuenta, ["tasks", "list", lista_id, "--max=100", "--all"]), "tasks", "items")
        return [t for t in ts if t.get("status", "needsAction") == "needsAction" and not t.get("deleted")]

    def tareas_todas(self, cuenta):
        """@default con las hechas: una gemela ya completada también cuenta como gemela."""
        return self._lista(self._run(cuenta, ["tasks", "list", "@default", "--max=100", "--all", "--show-completed", "--show-hidden"]), "tasks", "items")

    def eventos(self, cuenta, desde, dias):
        hasta = desde + timedelta(days=dias)
        d = self._run(cuenta, ["calendar", "events", "--all", f"--from={desde}", f"--to={hasta}", "--max=250", "--all-pages"])
        try:
            cals = self._lista(self._run(cuenta, ["calendar", "calendars"]), "calendars", "items")
            propios = {c.get("id") for c in cals if c.get("accessRole") == "owner"}
        except GogError:
            propios = None
        out = []
        for e in self._lista(d, "events", "items"):
            cid = e.get("CalendarID")
            if propios is not None and cid is not None and cid not in propios:
                continue
            out.append(e)
        return out

    # ── escrituras (lista cerrada) ──
    def tarea_crear(self, cuenta, lista_id, titulo, due=None):
        a = ["tasks", "add", lista_id, f"--title={titulo}"] + ([f"--due={due}"] if due else [])
        d = self._run(cuenta, a, escribir=True, intentos=1)
        return d.get("task", d) if isinstance(d, dict) else {}

    def tarea_notas(self, cuenta, lista_id, tid, notas):
        d = self._run(cuenta, ["tasks", "update", lista_id, tid, f"--notes={notas}"], escribir=True, intentos=1)
        return d.get("task", d) if isinstance(d, dict) else {}

    def tarea_due(self, cuenta, lista_id, tid, due):
        d = self._run(cuenta, ["tasks", "update", lista_id, tid, f"--due={due}"], escribir=True, intentos=1)
        return d.get("task", d) if isinstance(d, dict) else {}

    def tarea_hecha(self, cuenta, lista_id, tid):
        return self._run(cuenta, ["tasks", "done", lista_id, tid], escribir=True, intentos=1)
