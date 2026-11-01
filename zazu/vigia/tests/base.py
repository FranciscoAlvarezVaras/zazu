"""Base de las pruebas: casa falsa (HOME temporal) con dobles de wacli/gog/hermes/modelo. Nunca toca datos reales:
HOME apunta a un directorio temporal ANTES de importar zv ni recoger. Mensajes y correos son inventados."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
REAL_SCRIPTS = Path("/home/server/.hermes/scripts")
TMP = Path(tempfile.mkdtemp(prefix="zv-casa-"))
FH = TMP / "fh"
FIX = TMP / "fix"
os.environ["HOME"] = str(FH)
os.environ["ZV_FIX"] = str(FIX)
os.environ["ZV_LLM_CMD"] = str(AQUI / "shims/llm_stub")
os.environ["ZV_SCRIPTS"] = str(FH / ".hermes/scripts")
os.environ.pop("ZV_ENTREGA", None)
(FH / ".hermes").mkdir(parents=True)
(FH / ".local/bin").mkdir(parents=True)
(FH / ".hermes/.env").write_text("GOG_KEYRING_PASSWORD=falsa\nGOG_ACCOUNT=falsa@example.com\n")
(FH / ".hermes/scripts").symlink_to(REAL_SCRIPTS)
for n in ("wacli", "gog", "hermes"):
    (FH / ".local/bin" / n).symlink_to(AQUI / "shims" / n)
sys.path.insert(0, str(RAIZ))

from zv import config  # noqa: E402

config.DEFECTO["entrega"]["canal"] = "whatsapp"   # las pruebas de siempre miran `hermes send`; las del canal «app» lo cambian
os.environ["ZV_VIGILANTE"] = str(AQUI / "shims/vigilante")

CANARIO = "CANARIO-WA-9a1"
YO = "34600000099@s.whatsapp.net"


def iso(s):
    return datetime.fromisoformat(s).replace(tzinfo=config.TZ).astimezone(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chat(jid, name, kind="dm", unread=1, muted=0):
    return {"jid": jid, "kind": kind, "name": name, "last_message_ts": "2026-10-08T10:00:00Z", "archived": False, "pinned": False,
            "muted_until": muted, "unread": bool(unread), "unread_count": unread}


_n = [0]


def msg(jid, texto, hora, yo=False, nombre="Nuria", kind_name=None, media=None, reaccion=None, sender_name=None):
    _n[0] += 1
    return {"ChatJID": jid, "ChatName": kind_name or nombre, "MsgID": f"M{_n[0]:05d}", "SenderJID": YO if yo else jid, "SenderName": sender_name if sender_name is not None else ("" if yo else nombre),
            "Timestamp": iso(hora), "FromMe": yo, "Text": texto, "DisplayText": texto, "MediaType": media or "", "MediaCaption": "",
            "ReactionToID": reaccion or "", "ReactionEmoji": "", "Revoked": False, "DeletedForMe": False}


class ZVTest(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(FIX, ignore_errors=True)
        FIX.mkdir(parents=True)
        self.estado = TMP / "estado"
        self.conf = TMP / "conf"
        for d in (self.estado, self.conf):
            shutil.rmtree(d, ignore_errors=True)
        os.environ["ZV_ESTADO"], os.environ["ZV_CONFIG"] = str(self.estado), str(self.conf)
        os.environ.pop("ZV_ENTREGA", None)
        self.ahora("2026-10-08T18:00")
        shutil.rmtree(FH / ".local/state/zazu-bandeja", ignore_errors=True)       # la bandeja falsa de otras pruebas no debe colarse
        # Cerebro falso: no debe cambiar nunca
        shutil.rmtree(FH / "Cerebro", ignore_errors=True)
        (FH / "Cerebro/10 Bandeja").mkdir(parents=True)
        (FH / "Cerebro/10 Bandeja/nota.md").write_text("---\ntipo: nota\n---\nhola\n")
        self.arbol0 = self.snapshot(FH / "Cerebro")
        from zv import llm, priv
        self.addCleanup(lambda: self.assertEqual(self.arbol0, self.snapshot(FH / "Cerebro"), "el Cerebro cambió"))

    # ───── utilidades ─────
    @staticmethod
    def snapshot(d):
        return {str(p.relative_to(d)): p.stat().st_mtime_ns for p in sorted(Path(d).rglob("*")) if p.is_file()}

    def ahora(self, s):
        os.environ["ZV_AHORA"] = s

    def escribir(self, nombre, obj):
        (FIX / nombre).write_text(json.dumps(obj))

    def cfg_set(self, **cambios):
        """Cambia la config en disco: cfg_set(**{'modo.wa': 'activo', 'llm.max_por_dia': 2})"""
        cfg = config.cargar()
        for k, v in cambios.items():
            d = cfg
            *ks, ult = k.split(".")
            for x in ks:
                d = d[x]
            d[ult] = v
        config.guardar_cfg(cfg)

    def ciclo(self, solo=None):
        from zv import ciclo
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ciclo.ciclo(solo)
        return out.getvalue()

    def db(self):
        from zv.db import DB
        return DB()

    def filas(self, sql="SELECT * FROM avisos ORDER BY id", args=()):
        db = self.db()
        try:
            return db.c.execute(sql, args).fetchall()
        finally:
            db.close()

    def log(self, nombre):
        p = FIX / nombre
        return p.read_text() if p.exists() else ""

    def todo_el_texto(self):
        """Todo lo que queda en disco de zv (estado, config, logs, bandeja volcada) para buscar canarios."""
        partes = []
        for base in (self.estado, self.conf):
            for p in Path(base).rglob("*"):
                if p.is_file() and not p.name.endswith("-wal"):
                    partes.append(p.read_bytes().decode("utf-8", "replace"))
        db = self.db()
        for t in ("avisos", "entregas", "latidos", "uso_llm", "contadores", "kv", "registro", "gasto", "suscripcion"):
            partes.append(json.dumps([dict(r) for r in db.c.execute(f"SELECT * FROM {t}")], ensure_ascii=False))
        return "\n".join(partes)
