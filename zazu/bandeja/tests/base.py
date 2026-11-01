"""Entorno falso para los tests: HOME, estado, config, Cerebro (con las plantillas REALES), gog y hermes falsos. No toca nada real."""
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
REAL = Path("/home/server/Cerebro")
CANARIO = "CANARIO-ZB-7f3"


def evento(id_, titulo, ini, fin, propio=True, desc=None, lugar=None, creado="2026-10-08T17:00:00Z", **extra):
    e = {"id": id_, "summary": titulo, "start": {"dateTime": ini, "timeZone": "Europe/Madrid"}, "end": {"dateTime": fin, "timeZone": "Europe/Madrid"},
         "status": "confirmed", "eventType": "default", "created": creado, "updated": creado, "CalendarID": "cal1",
         "creator": {"email": "fran@example.org", "self": True} if propio else {"email": "otro@example.org"},
         "organizer": {"email": "fran@example.org", "self": True} if propio else {"email": "otro@example.org"}}
    if desc:
        e["description"] = desc
    if lugar:
        e["location"] = lugar
    e.update(extra)
    return e


def tarea(id_, titulo, due=None, notes=None, updated="2026-10-08T17:30:00Z", **extra):
    t = {"id": id_, "title": titulo, "status": "needsAction", "updated": updated}
    if due:
        t["due"] = due + "T00:00:00.000Z"
    if notes:
        t["notes"] = notes
    t.update(extra)
    return t


class Entorno(unittest.TestCase):
    AHORA = "2026-10-08T21:00:00"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zb-test-"))
        t = self.tmp
        for d in ("home/.config", "home/.local/state", "fake"):
            (t / d).mkdir(parents=True)
        self.v = t / "Cerebro"
        for d in ("10 Bandeja", "20 Diario", "30 Notas/Ideas", "30 Notas/Proyectos", "30 Notas/Candidaturas", "90 Sistema/Plantillas", "40 Compartido/Adjuntos"):
            (self.v / d).mkdir(parents=True)
        for p in (REAL / "90 Sistema/Plantillas").glob("*.md"):
            shutil.copy(p, self.v / "90 Sistema/Plantillas" / p.name)
        shutil.copy(REAL / "90 Sistema/index.md", self.v / "90 Sistema/index.md")
        (self.v / "90 Sistema/log.md").write_text("---\ntipo: sistema\n---\n# log\n- 2026-10-07 · Claude · algo\n")
        shutil.copy(REAL / "30 Notas/Proyectos/Buscar trabajo.md", self.v / "30 Notas/Proyectos/Buscar trabajo.md")
        for k, v in {"ZB_HOME": t / "home", "ZB_ESTADO": t / "estado", "ZB_CONFIG": t / "config", "ZB_VAULT": self.v, "FAKE_DIR": t / "fake",
                     "ZB_GOG": AQUI / "fakegog.py", "ZB_HERMES": AQUI / "fakehermes.py"}.items():
            os.environ[k] = str(v)
        os.environ["ZB_SIN_ESPERA"] = "1"
        os.environ["ZB_AHORA"] = self.AHORA
        os.environ.pop("FAKE_HERMES_EVIL", None)
        self.fake = t / "fake"
        self.datos(varas={}, alvarez={})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # datos falsos
    def datos(self, varas, alvarez):
        def cuenta(d):
            return {"lists": [{"id": "L1", "title": "Mis tareas"}, {"id": "L2", "title": "Notas del asistente"}], "tasks": {"L1": d.get("tareas", []), "L2": d.get("notas", [])},
                    "events": d.get("eventos", [])}
        (self.fake / "data.json").write_text(json.dumps({"accounts": {"varas": cuenta(varas), "alvarez": cuenta(alvarez)}}))

    def leer_datos(self):
        return json.loads((self.fake / "data.json").read_text())

    def llamadas(self):
        p = self.fake / "calls.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def escrituras(self):
        return [c for c in self.llamadas() if c["extra"] == "ESCRITURA"]

    def violaciones(self):
        return [c for c in self.llamadas() if c["extra"] in ("VIOLACION", "PROHIBIDO", "DESCONOCIDO")]

    def enviados(self):
        p = self.fake / "sent.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def arbol(self):
        return {str(p.relative_to(self.v)): p.stat().st_mtime_ns for p in self.v.rglob("*") if p.is_file()}

    def modo(self, m):
        (self.tmp / "config").mkdir(exist_ok=True)
        (self.tmp / "config/MODO").write_text(m + "\n")

    def hora(self, iso):
        os.environ["ZB_AHORA"] = iso

    def correr(self, web=None, **kw):
        import ciclo
        c = ciclo.Ciclo(**kw)
        if web:
            c.web = web
        return c, c.run()


class WebFalsa:
    """Sustituye a web.py en los tests de ciclo: sin red."""
    def __init__(self, texto=None, error=None):
        self.texto, self.error, self.llamadas = texto, error, []

    def leer(self, url):
        self.llamadas.append(url)
        if self.error:
            raise self.error
        return url, self.texto
