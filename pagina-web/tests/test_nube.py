#!/usr/bin/env python3
"""Pruebas de Mi nube (favoritos, álbumes, duplicados, enlaces para compartir, ZIP y el mapa) con el Hub de la casa falsa. Solo biblioteca estándar
(el mapa, además, Pillow: se salta con el python3 del .venv, que no lo trae; el Hub corre con el del sistema).

    python3 -m unittest tests.test_nube -v        (desde pagina-web/; también: python3 tests/test_nube.py)

Usa el arnés de test_api.py: un Hub con casa falsa bajo /tmp, aquí con sus dos puertos (el local, donde en pruebas se es Fran sin más, y el
público, donde sin sesión no se es nadie). Nunca toca ~/Cerebro ni ~/.local/state/zazu-nube de verdad.
"""
import glob, http.client, io, json, os, pwd, shutil, stat, subprocess, sys, tempfile, threading, time, types, unittest, urllib.parse, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from unittest import mock

try:
    from tests.test_api import Base, REPO, puerto_libre, esperar_puerto
except ImportError:   # python3 tests/test_nube.py
    from test_api import Base, REPO, puerto_libre, esperar_puerto
sys.path.insert(0, str(REPO))
import archivos as A   # noqa: E402

ADMIN = "cuenta.principal@example.com"
KINDS = {"image", "video", "audio", "pdf", "doc", "sheet", "text", "note", "other"}
FUERA = b"SECRETO-QUE-NO-ESTA-EN-COMPARTIDO"
CADUCADO = "Caducado_0123456789ab"   # un enlace caducado sembrado en el estado antes de que el Hub lo lea
IMG1, IMG2, IMG3 = "Fotos/IMG_20240117_212002.jpg", "Fotos/IMG_20230305_101500.jpg", "Fotos/IMG_20220714_090000.jpg"
CLIP = "Fotos/clip.mp4"
try:
    import PIL  # noqa: F401
    HAY_PIL = True
except ImportError:   # el Hub corre con el python3 del sistema, que sí lo trae; el .venv no
    HAY_PIL = False
CASA = Path(pwd.getpwuid(os.getuid()).pw_dir)   # la de verdad, por si HOME fuese una falsa
FFMPEG = next((p for p in [shutil.which("ffmpeg"), str(CASA / ".local/bin/ffmpeg"), *sorted(glob.glob(str(CASA / ".hermes/tools/ffmpeg-*/bin/ffmpeg")))]
               if p and os.access(p, os.X_OK)), None)


def hace_un_anio():
    h = date.today()
    for a in (1, 2, 3, 4):   # (29 de febrero: el primer año anterior que lo tenga)
        try:
            return h.replace(year=h.year - a)
        except ValueError:
            continue


def peticion(puerto, metodo, ruta, cuerpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=30)
    c.request(metodo, ruta, body=cuerpo, headers=cab or {})
    r = c.getresponse()
    datos = r.read()
    out = (r.status, {k.lower(): v for k, v in r.getheaders()}, datos)
    c.close()
    return out


class NubeBase(Base):
    """Un Hub con casa falsa y sus dos puertos, y un Compartido de pruebas."""
    n_ip = 0

    @classmethod
    def entorno(cls, puerto, gw):
        env = super().entorno(puerto, gw)
        env["HUB_PUBLIC_PORT"] = str(cls.pub_port)   # un solo proceso con los dos puertos, como en producción
        return env

    @classmethod
    def setUpClass(cls):
        cls.pub_port = puerto_libre()
        super().setUpClass()
        esperar_puerto(cls.pub_port)
        cls.compartido = cls.fh / "Cerebro/40 Compartido"
        cls.tokens = []
        cls.poner(IMG1, os.urandom(20000))
        cls.poner(IMG2, os.urandom(30000))
        cls.poner(IMG3, os.urandom(15000))
        cls.poner(f"Fotos/IMG_{hace_un_anio():%Y%m%d}_100000.jpg", os.urandom(11000))   # «un día como hoy»
        cls.poner("Fotos/Verano/IMG_0001.jpg", os.urandom(12000))
        cls.poner("Fotos/Invierno/IMG_0001.jpg", os.urandom(13000))   # mismo nombre, otra carpeta
        cls.poner(CLIP, os.urandom(300000))
        igual = os.urandom(20000)
        cls.poner("Fotos/dup.jpg", igual)
        cls.poner("Otra/dup (2).jpg", igual)   # idéntica: es la «copia»
        base = os.urandom(200000)
        cls.poner("Fotos/casi1.jpg", base)
        cls.poner("Fotos/casi2.jpg", base[:100000] + bytes([base[100000] ^ 1]) + base[100001:])   # mismo tamaño, mismo principio y final, distinta por dentro
        cls.poner("Docs/informe.pdf", b"%PDF-1.4 prueba")
        cls.poner("Docs/nota.txt", "una nota con tildes: canción".encode())
        cls.poner("Docs/hoja.xlsx", b"PK\x03\x04hoja")
        cls.poner("Docs/carta.docx", b"PK\x03\x04carta")
        cls.poner("Docs/apunte.md", "# apunte\n".encode())
        cls.poner("Docs/musica.mp3", os.urandom(2000))
        cls.poner("Docs/raro.bin", os.urandom(500))
        (cls.fh / "secreto.txt").write_bytes(FUERA)
        os.symlink(cls.fh / "secreto.txt", cls.compartido / "Fotos/atajo.jpg")   # un acceso directo hacia fuera: nunca debe entrar
        # un enlace caducado, sembrado antes de que el Hub lea el estado (lo hace la primera vez que lo necesita)
        est = cls.fh / ".local/state/zazu-nube/nube.json"
        est.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        est.write_text(json.dumps({"fav": [], "albumes": {}, "enlaces": {CADUCADO: {"path": IMG1, "creado": 1, "caduca": int(time.time()) - 5, "visitas": 3}}}))
        os.environ["HOME"] = str(cls.fh)
        import server   # noqa: E402  (con HOME = casa falsa; como el resto de pruebas)
        cfg = json.loads((cls.fh / ".config/hermes-hub/auth.json").read_text())
        cls.galleta_admin = server.make_session(cfg, ADMIN)
        cls.galleta_invitada = server.make_session(cfg, "invitada@example.com")

    @classmethod
    def poner(cls, rel, datos, mtime=None):
        p = cls.compartido / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
        if mtime:
            os.utime(p, (mtime, mtime))
        return p

    @classmethod
    def contar_disco(cls):
        t = {k: [0, 0] for k in KINDS}
        for dp, dns, fns in os.walk(cls.compartido):
            dns[:] = [d for d in dns if not A.oculto(d) and not os.path.islink(os.path.join(dp, d))]
            for f in fns:
                fp = os.path.join(dp, f)
                if A.oculto(f) or os.path.islink(fp):
                    continue
                k = A.tipo(f)
                t[k][0] += 1
                t[k][1] += os.path.getsize(fp)
        return t

    # ---------- utilidades ----------
    def sync(self):
        """Que la Nube vuelva a mirar el disco ya: crear una carpeta invalida el índice (si no, tarda hasta 60 s en enterarse)."""
        self.assertEqual(self.post("/api/mkdir", {"name": f"sync{time.time_ns()}", "path": ""})[0], 200)

    def medios(self, **p):
        st, d = self.pedir("GET", "/api/nube/medios?" + urllib.parse.urlencode(p))
        self.assertEqual(st, 200, d)
        return d

    @staticmethod
    def rutas(d):
        return [i["path"] for i in d["items"]]

    def albumes(self):
        st, d = self.pedir("GET", "/api/nube/albumes")
        self.assertEqual(st, 200, d)
        return d["items"]

    def crudo(self, metodo, ruta, cab=None, cuerpo=None, puerto=None):
        """Una petición como Fran por el puerto local (en pruebas, sin cookie, se es él): para lo que no es JSON (ZIP, archivos)."""
        h = {"X-Hub": "1"} if metodo == "POST" else {}
        return peticion(puerto or self.hub_port, metodo, ruta, cuerpo, {**h, **(cab or {})})

    def pub(self, metodo, ruta, ip=None, cab=None, cuerpo=None):
        """Una petición SIN sesión por el puerto público, como la de quien recibe un enlace. ip = lo que diría Cloudflare en CF-Connecting-IP."""
        if ip is None:
            type(self).n_ip += 1
            ip = f"198.51.100.{type(self).n_ip % 250 + 1}"
        return peticion(self.pub_port, metodo, ruta, cuerpo, {"CF-Connecting-IP": ip, **(cab or {})})

    def enlace(self, path, **kw):
        st, d = self.post("/api/nube/enlace", {"path": path, **kw})
        self.assertEqual(st, 200, d)
        type(self).tokens.append(d["token"])
        return d["token"]


class NubeApi(NubeBase):
    def setUp(self):
        d = self.medios(fav="1", n=200)
        if d["items"]:
            self.post("/api/nube/fav", {"paths": self.rutas(d), "on": False})
        for a in self.albumes():
            self.post("/api/nube/album", {"accion": "borrar", "id": a["id"]})

    # ---------- permisos ----------
    def test_permisos(self):
        gets = ["/api/nube", "/api/nube/medios", "/api/nube/albumes", "/api/nube/duplicados", "/api/nube/enlaces", "/api/nube/zip?fav=1",
                "/api/nube/mini?path=x", "/api/nube/vista?path=x", "/api/nube/video-estado?path=x", "/api/nube/mapa?z=3", "/api/nube/medios?bbox=0,0,1,1"]
        posts = [("/api/nube/fav", {"paths": [IMG1], "on": True}), ("/api/nube/album", {"accion": "crear", "nombre": "x"}),
                 ("/api/nube/enlace", {"path": IMG1}), ("/api/nube/enlace/revocar", {"token": "x" * 22})]
        for r in gets:
            self.assertEqual(self.pub("GET", r)[0], 401, r)   # sin sesión
            self.assertEqual(self.pub("GET", r, cab={"Cookie": f"hub_s={self.galleta_invitada}"})[0], 403, r)   # una invitada no es Fran
            self.assertEqual(self.pedir("GET", r, cookie=self.galleta_invitada)[0], 403, r)   # tampoco por el puerto local
        for r, c in posts:
            cab = {"X-Hub": "1", "Content-Type": "application/json"}
            sin = peticion(self.pub_port, "POST", r, json.dumps(c).encode(), {**cab, "CF-Connecting-IP": "198.51.100.250"})[0]
            self.assertIn(sin, (401, 403), r)   # (un POST sin sesión da 403 «acceso denegado», como todos los demás)
            self.assertEqual(self.post(r, c, cookie=self.galleta_invitada)[0], 403, r)
            self.assertEqual(peticion(self.pub_port, "POST", r, json.dumps(c).encode(), {**cab, "Cookie": f"hub_s={self.galleta_invitada}", "CF-Connecting-IP": "198.51.100.250"})[0], 403, r)
        st, h, d = self.pub("GET", "/api/nube", cab={"Cookie": f"hub_s={self.galleta_admin}"})   # Fran con su sesión, también por el puerto público
        self.assertEqual(st, 200)
        self.assertIn("tipos", json.loads(d))
        self.assertEqual(self.pub("GET", "/api/nube/rarisima", cab={"Cookie": f"hub_s={self.galleta_admin}"})[0], 404)

    # ---------- resumen ----------
    def test_resumen_por_tipo(self):
        self.sync()
        esperado = self.contar_disco()
        st, r = self.pedir("GET", "/api/nube")
        self.assertEqual(st, 200)
        self.assertEqual(set(r["tipos"]), KINDS)
        self.assertEqual({k: [v["n"], v["bytes"]] for k, v in r["tipos"].items()}, esperado)
        self.assertEqual(r["bytes"], sum(b for _, b in esperado.values()))
        self.assertEqual((r["fotos"], r["videos"]), (esperado["image"][0], esperado["video"][0]))
        self.assertEqual((r["favoritos"], r["albumes"]), (0, 0))
        self.assertTrue(r["disco"]["total"] > r["disco"]["libre"] > 0)
        self.assertTrue(all(esperado[k][0] >= 1 for k in KINDS))   # los nueve tipos están en las pruebas
        self.post("/api/nube/fav", {"paths": [IMG1, IMG2], "on": True})
        self.post("/api/nube/album", {"accion": "crear", "nombre": "A"})
        r = self.pedir("GET", "/api/nube")[1]
        self.assertEqual((r["favoritos"], r["albumes"]), (2, 1))

    # ---------- favoritos ----------
    def test_favoritos(self):
        st, r = self.post("/api/nube/fav", {"paths": [IMG1, IMG2], "on": True})
        self.assertEqual((st, r), (200, {"ok": True, "total": 2}))
        d = self.medios(fav="1")
        self.assertEqual((sorted(self.rutas(d)), d["total"]), (sorted([IMG1, IMG2]), 2))
        self.assertTrue(all(i["fav"] is True for i in d["items"]))
        todo = self.medios(n=200)
        self.assertEqual({i["path"] for i in todo["items"] if i["fav"]}, {IMG1, IMG2})
        self.assertTrue(all(isinstance(i["fav"], bool) for i in todo["items"]))
        self.assertEqual(self.pedir("GET", "/api/nube")[1]["favoritos"], 2)
        self.assertEqual(self.post("/api/nube/fav", {"paths": [IMG1, IMG1], "on": True})[1]["total"], 2)   # repetir no suma
        self.assertEqual(self.post("/api/nube/fav", {"paths": [IMG1, CLIP], "on": False})[1]["total"], 1)   # quitar uno (y otro que nunca lo fue)
        self.assertEqual(self.rutas(self.medios(fav="1")), [IMG2])
        self.assertEqual(self.medios(fav="1", tipo="video")["total"], 0)   # se combina con los demás filtros
        self.assertEqual(self.post("/api/nube/fav", {"paths": [IMG1] * 500, "on": True})[1]["total"], 2)   # 500 es el tope

    def test_favoritos_validacion(self):
        for cuerpo, esperado in (
                ({"paths": [IMG1]}, 400), ({"paths": [IMG1], "on": "si"}, 400), ({"paths": [IMG1], "on": 1}, 400),   # on tiene que ser true o false
                ({"on": True}, 400), ({"paths": IMG1, "on": True}, 400), ({"paths": [], "on": True}, 400),
                ({"paths": [IMG1] * 501, "on": True}, 400), ({"paths": [5], "on": True}, 400), ({"paths": [None], "on": True}, 400),
                ({"paths": ["../fuera.jpg"], "on": True}, 403), ({"paths": ["Fotos/../../secreto.txt"], "on": True}, 403),
                ({"paths": ["Fotos/atajo.jpg"], "on": True}, 403), ({"paths": [".stfolder/x.jpg"], "on": True}, 403),   # acceso directo y carpeta reservada
                ({"paths": ["Fotos/no_existe.jpg"], "on": True}, 404), ({"paths": ["Fotos"], "on": True}, 404),   # ni existe ni es un archivo
                ({"paths": ["Docs/informe.pdf"], "on": True}, 400), ({"paths": ["a" * 1001], "on": True}, 400)):
            self.assertEqual(self.post("/api/nube/fav", cuerpo)[0], esperado, cuerpo)
        self.assertEqual(self.post("/api/nube/fav", {"paths": [IMG1, "Fotos/no_existe.jpg"], "on": True})[0], 404)
        self.assertEqual(self.medios(fav="1")["total"], 0)   # una mala y no se aplica ninguna
        st, h, _ = self.crudo("POST", "/api/nube/fav", {"Content-Type": "application/json"}, b"[1, 2]")
        self.assertEqual(st, 400)   # el cuerpo tiene que ser un objeto

    def test_favorito_de_un_archivo_que_desaparece(self):
        p = self.poner("Fotos/fantasma.jpg", os.urandom(3000))
        self.sync()
        self.assertEqual(self.post("/api/nube/fav", {"paths": ["Fotos/fantasma.jpg"], "on": True})[1]["total"], 1)
        p.unlink()
        self.sync()
        self.assertEqual(self.medios(fav="1")["total"], 0)   # lo que ya no existe no cuenta
        self.assertEqual(self.pedir("GET", "/api/nube")[1]["favoritos"], 0)
        self.assertEqual(self.post("/api/nube/fav", {"paths": ["Fotos/fantasma.jpg"], "on": False})[0], 200)   # y se puede quitar igualmente

    # ---------- álbumes ----------
    def test_albumes(self):
        st, r = self.post("/api/nube/album", {"accion": "crear", "nombre": "  Navidad   2025 ", "paths": [IMG1, IMG2]})
        self.assertEqual(st, 200)
        aid = r["id"]
        self.assertRegex(aid, r"^[0-9a-f]{8}$")
        al, = self.albumes()
        self.assertEqual((al["id"], al["nombre"], al["n"], al["portada"]), (aid, "Navidad 2025", 2, IMG1))   # la portada es la más nueva
        self.assertIsInstance(al["creado"], int)
        self.assertEqual(sorted(self.rutas(self.medios(album=aid))), sorted([IMG1, IMG2]))
        self.assertEqual(self.post("/api/nube/album", {"accion": "crear", "nombre": "navidad 2025"})[0], 409)   # nombre repetido (sin mirar mayúsculas)
        self.assertEqual(self.post("/api/nube/album", {"accion": "añadir", "id": aid, "paths": [IMG2, IMG3]})[0], 200)   # IMG2 ya estaba
        self.assertEqual(self.albumes()[0]["n"], 3)
        self.assertEqual(self.post("/api/nube/album", {"accion": "quitar", "id": aid, "paths": [IMG1, "Fotos/nunca_estuvo.jpg"]})[0], 200)
        al, = self.albumes()
        self.assertEqual((al["n"], al["portada"]), (2, IMG2))
        otro = self.post("/api/nube/album", {"accion": "crear", "nombre": "Otro"})[1]["id"]
        self.assertEqual(self.albumes()[0]["id"], otro)   # el más nuevo primero
        self.assertEqual(self.albumes()[0]["portada"], None)   # vacío: sin portada
        self.assertEqual(self.post("/api/nube/album", {"accion": "renombrar", "id": otro, "nombre": "navidad 2025"})[0], 409)   # tampoco renombrando
        self.assertEqual(self.post("/api/nube/album", {"accion": "renombrar", "id": aid, "nombre": "NAVIDAD 2025"})[0], 200)   # a sí mismo, sí
        self.assertEqual(self.post("/api/nube/album", {"accion": "renombrar", "id": otro, "nombre": "Verano"})[0], 200)
        self.assertEqual({a["nombre"] for a in self.albumes()}, {"NAVIDAD 2025", "Verano"})
        self.assertEqual(self.post("/api/nube/album", {"accion": "borrar", "id": aid})[0], 200)
        self.assertEqual([a["id"] for a in self.albumes()], [otro])
        self.assertEqual(self.pedir("GET", f"/api/nube/medios?album={aid}")[0], 404)   # ya no existe
        self.assertEqual(self.post("/api/nube/album", {"accion": "borrar", "id": aid})[0], 404)

    def test_albumes_validacion(self):
        for cuerpo, esperado in (
                ({"accion": "crear"}, 400), ({"accion": "crear", "nombre": ""}, 400), ({"accion": "crear", "nombre": "   "}, 400),
                ({"accion": "crear", "nombre": 5}, 400), ({"accion": "crear", "nombre": "x" * 61}, 400),
                ({"accion": "crear", "nombre": "Bien", "paths": ["../x.jpg"]}, 403), ({"accion": "crear", "nombre": "Bien", "paths": ["Fotos/no.jpg"]}, 404),
                ({"accion": "crear", "nombre": "Bien", "paths": ["Docs/nota.txt"]}, 400), ({"accion": "crear", "nombre": "Bien", "paths": "x"}, 400),
                ({"accion": "volar"}, 400), ({}, 400), ({"accion": "borrar"}, 400), ({"accion": "borrar", "id": "ZZ"}, 400),
                ({"accion": "borrar", "id": 12345678}, 400), ({"accion": "borrar", "id": "../../etc"}, 400), ({"accion": "borrar", "id": "0" * 8}, 404),
                ({"accion": "renombrar", "id": "0" * 8, "nombre": "x"}, 404)):
            self.assertEqual(self.post("/api/nube/album", cuerpo)[0], esperado, cuerpo)
        self.assertEqual(self.albumes(), [])   # nada de lo malo se guardó
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "x" * 60})[1]["id"]   # 60 es el tope
        self.assertEqual(len(self.albumes()[0]["nombre"]), 60)
        for cuerpo, esperado in (({"accion": "añadir", "id": aid}, 400), ({"accion": "añadir", "id": aid, "paths": ["Fotos/no.jpg"]}, 404),
                                 ({"accion": "añadir", "id": aid, "paths": ["Fotos"]}, 404), ({"accion": "renombrar", "id": aid}, 400),
                                 ({"accion": "renombrar", "id": aid, "nombre": "y" * 61}, 400), ({"accion": "quitar", "id": aid, "paths": ["../x"]}, 403)):
            self.assertEqual(self.post("/api/nube/album", cuerpo)[0], esperado, cuerpo)
        self.assertEqual(self.post("/api/nube/album", {"accion": "renombrar", "id": aid, "nombre": "  Con\tespacios \n raros "})[0], 200)
        self.assertEqual(self.albumes()[0]["nombre"], "Con espacios raros")

    def test_album_con_archivos_que_desaparecen(self):
        p = self.poner("Fotos/IMG_20250101_000000.jpg", os.urandom(4000))
        self.sync()
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "Efímero", "paths": ["Fotos/IMG_20250101_000000.jpg", IMG2]})[1]["id"]
        self.assertEqual((self.albumes()[0]["n"], self.albumes()[0]["portada"]), (2, "Fotos/IMG_20250101_000000.jpg"))
        p.unlink()
        self.sync()
        self.assertEqual((self.albumes()[0]["n"], self.albumes()[0]["portada"]), (1, IMG2))   # n y portada solo cuentan lo que existe
        self.assertEqual(self.rutas(self.medios(album=aid)), [IMG2])

    # ---------- filtros y orden ----------
    def test_filtros_y_orden(self):
        todo = self.medios(n=200)
        nuevas = self.rutas(todo)
        self.assertEqual(todo["total"], len(nuevas))
        mt = [i["mtime"] for i in todo["items"]]
        self.assertEqual(mt, sorted(mt, reverse=True))   # por defecto, las más nuevas primero
        self.assertEqual(self.rutas(self.medios(n=200, orden="nuevas")), nuevas)
        self.assertEqual(self.rutas(self.medios(n=200, orden="antiguas")), nuevas[::-1])
        tam = [i["size"] for i in self.medios(n=200, orden="tamano")["items"]]
        self.assertEqual(tam, sorted(tam, reverse=True))
        self.assertEqual(tam[0], 300000)
        self.assertEqual(self.pedir("GET", "/api/nube/medios?orden=raro")[0], 400)
        self.assertEqual(set(i["kind"] for i in self.medios(tipo="video", n=200)["items"]), {"video"})
        self.assertEqual(set(i["kind"] for i in self.medios(tipo="image", n=200)["items"]), {"image"})
        self.assertEqual(self.medios(tipo="", n=200)["total"], todo["total"])   # (la web manda tipo= vacío para «todo»)
        self.assertEqual(sorted(self.rutas(self.medios(q="img_0001"))), ["Fotos/Invierno/IMG_0001.jpg", "Fotos/Verano/IMG_0001.jpg"])
        self.assertEqual(self.rutas(self.medios(en="verano")), ["Fotos/Verano/IMG_0001.jpg"])
        self.assertEqual(self.medios(q="no-existe-nada")["total"], 0)
        # fechas del nombre y paginación
        self.assertEqual(self.medios(q="212002")["items"][0]["mtime"], int(datetime(2024, 1, 17, 12).timestamp()))   # la fecha del nombre, no la del archivo
        p1, p2 = self.medios(n=3, desde=0), self.medios(n=3, desde=3)
        self.assertEqual((len(p1["items"]), p1["total"]), (3, todo["total"]))
        self.assertEqual(self.rutas(p1) + self.rutas(p2), nuevas[:6])
        self.assertEqual(len(self.medios(n=0)["items"]), 1)   # n sin sentido se queda en 1
        self.assertEqual(len(self.medios(n=99999)["items"]), len(nuevas))
        self.assertEqual(self.medios(desde=-5, n=2)["items"][0]["path"], nuevas[0])
        self.assertEqual(self.pedir("GET", "/api/nube/medios?desde=abc")[0], 400)
        hoy = self.medios(dia="hoy", n=200)
        self.assertIn(f"Fotos/IMG_{hace_un_anio():%Y%m%d}_100000.jpg", self.rutas(hoy))
        self.assertTrue(all(date.fromtimestamp(i["mtime"]).strftime("%m%d") == date.today().strftime("%m%d") for i in hoy["items"]))
        self.assertEqual(self.pedir("GET", "/api/nube/medios?album=zz")[0], 400)

    def test_listado_de_un_album_con_orden_y_filtros(self):
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "Mezcla", "paths": [IMG1, IMG2, CLIP]})[1]["id"]
        self.assertEqual(self.rutas(self.medios(album=aid, orden="tamano")), [CLIP, IMG2, IMG1])
        self.assertEqual(self.rutas(self.medios(album=aid, tipo="video")), [CLIP])
        self.post("/api/nube/fav", {"paths": [IMG2], "on": True})
        self.assertEqual(self.rutas(self.medios(album=aid, fav="1")), [IMG2])

    # ---------- duplicados ----------
    def esperar_dup(self, rehacer=False):
        fin = time.time() + 30
        while time.time() < fin:
            st, d = self.pedir("GET", "/api/nube/duplicados" + ("?rehacer=1" if rehacer else ""))
            rehacer = False
            self.assertEqual(st, 200, d)
            if d["estado"] != "calculando":
                return d
            time.sleep(0.2)
        self.fail("los duplicados no terminaron")

    @staticmethod
    def grupo(d, nombre):
        return next((g for g in d["grupos"] if any(i["name"] == nombre for i in g["items"])), None)

    def test_duplicados(self):
        d = self.esperar_dup(rehacer=True)
        self.assertEqual(d["estado"], "listo")
        g = self.grupo(d, "dup.jpg")
        self.assertEqual((g["size"], [i["path"] for i in g["items"]]), (20000, ["Fotos/dup.jpg", "Otra/dup (2).jpg"]))   # la primera es la que se conserva
        self.assertTrue(all(set(i) == {"path", "name", "mtime", "kind"} for i in g["items"]))   # (kind: para elegir miniatura o icono; puede ser audio, un PDF…)
        self.assertEqual({i["kind"] for i in g["items"]}, {"image"})
        self.assertGreaterEqual(d["ahorro"], 20000)
        self.assertIsNone(self.grupo(d, "casi1.jpg"))   # casi idénticos: mismo tamaño, mismo principio y final… pero no son lo mismo
        self.assertIsNone(self.grupo(d, "atajo.jpg"))   # el acceso directo ni se mira
        self.assertEqual(d["total"], len(d["grupos"]))
        self.assertGreaterEqual(d["vistos"], sum(n for n, _ in self.contar_disco().values()))
        self.assertEqual(d["ahorro"], sum(x["size"] * (len(x["items"]) - 1) for x in d["grupos"]))
        # un enlace duro es el mismo archivo con dos nombres: borrarlo no ahorra nada
        os.link(self.compartido / "Fotos/casi1.jpg", self.compartido / "Fotos/casi1_enlace_duro.jpg")
        self.sync()
        d = self.esperar_dup()
        self.assertIsNone(self.grupo(d, "casi1_enlace_duro.jpg") or self.grupo(d, "casi1.jpg"))
        # tirar la copia: el grupo desaparece (sin esperar a la hora de caducidad)
        self.assertEqual(self.post("/api/papelera", {"path": "Otra/dup (2).jpg"})[0], 200)
        antes = self.pedir("GET", "/api/nube/duplicados")[1]
        self.assertIsNone(self.grupo(antes, "dup.jpg"))   # ni siquiera lo anterior: lo que ya no existe no se enseña mientras rehace
        self.assertIsNone(self.grupo(self.esperar_dup(), "dup.jpg"))
        # y al restaurarla vuelve
        _, pap = self.pedir("GET", "/api/papelera")
        pid = next(x["id"] for x in pap["items"] if x["nombre"] == "dup (2).jpg")
        self.assertEqual(self.post("/api/restaurar", {"id": pid})[0], 200)
        self.assertIsNotNone(self.grupo(self.esperar_dup(), "dup.jpg"))
        # los archivos de pocos KB no cuentan
        pequeno = os.urandom(5000)
        self.poner("Docs/pequeno1.bin", pequeno)
        self.poner("Docs/pequeno2.bin", pequeno)
        self.sync()
        self.assertIsNone(self.grupo(self.esperar_dup(), "pequeno1.bin"))

    # ---------- ZIP ----------
    def zip_de(self, ruta):
        st, h, datos = self.crudo("GET", ruta)
        self.assertEqual(st, 200, datos[:200])
        self.assertEqual(h["content-type"], "application/zip")
        self.assertEqual((h["transfer-encoding"], "content-length" in h), ("chunked", False))   # sale mientras se hace: no se sabe cuánto va a pesar
        return h, zipfile.ZipFile(io.BytesIO(datos))

    def test_zip_de_album_y_favoritos(self):
        a, b = "Fotos/Verano/IMG_0001.jpg", "Fotos/Invierno/IMG_0001.jpg"   # mismo nombre en dos carpetas
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": 'Ve/ra"no: 2024*', "paths": [a, b, CLIP]})[1]["id"]
        h, z = self.zip_de(f"/api/nube/zip?album={aid}")
        self.assertEqual(z.namelist(), ["IMG_0001.jpg", "IMG_0001 (2).jpg", "clip.mp4"])   # en el orden del álbum; el segundo IMG_0001 no pisa al primero
        self.assertIsNone(z.testzip())
        self.assertEqual([z.read(n) for n in z.namelist()], [(self.compartido / x).read_bytes() for x in (a, b, CLIP)])
        self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()))   # fotos y vídeos ya vienen comprimidos
        disp = h["content-disposition"]
        self.assertRegex(disp, r"^attachment; filename\*=UTF-8''[^/\"\\]+-\d{4}-\d{2}-\d{2}\.zip$")   # un nombre de álbum nunca se cuela como ruta o comilla
        self.assertNotRegex(urllib.parse.unquote(disp.split("''", 1)[1]), r'[/\\:*?"<>|]')
        # favoritos
        self.post("/api/nube/fav", {"paths": [IMG1, IMG2], "on": True})
        h, z = self.zip_de("/api/nube/zip?fav=1")
        self.assertEqual(sorted(z.namelist()), sorted(Path(x).name for x in (IMG1, IMG2)))
        self.assertIn("Favoritos-", urllib.parse.unquote(h["content-disposition"]))
        # lo que ya no existe se queda fuera, y un acceso directo puesto después también (nunca entra el contenido de fuera)
        (self.compartido / IMG2).unlink()
        os.symlink(self.fh / "secreto.txt", self.compartido / IMG2)
        h, z = self.zip_de("/api/nube/zip?fav=1")
        self.assertEqual(z.namelist(), [Path(IMG1).name])
        self.assertNotIn(FUERA, b"".join(z.read(n) for n in z.namelist()))
        (self.compartido / IMG2).unlink()
        (self.compartido / IMG2).write_bytes(os.urandom(30000))
        self.assertFalse((self.fh / ".cache/zazu-zip").exists())   # sin fichero temporal: ni se prepara en el disco ni hace falta sitio en él

    def test_zip_errores(self):
        self.assertEqual(self.crudo("GET", "/api/nube/zip")[0], 400)
        self.assertEqual(self.crudo("GET", "/api/nube/zip?album=zz")[0], 400)
        self.assertEqual(self.crudo("GET", "/api/nube/zip?album=" + "0" * 8)[0], 404)   # no existe
        self.assertEqual(self.crudo("GET", "/api/nube/zip?fav=1")[0], 404)   # sin favoritos: nada que bajar
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "Vacío"})[1]["id"]
        self.assertEqual(self.crudo("GET", f"/api/nube/zip?album={aid}")[0], 404)

    def test_zip_de_carpeta_de_siempre(self):
        """/api/zip (la copia de una carpeta) sigue igual de bien, ahora al vuelo y aguantando fechas de 1970."""
        self.poner("Vieja/foto.jpg", os.urandom(1500), mtime=0)   # un ZIP no admite fechas anteriores a 1980
        st, h, datos = self.crudo("GET", "/api/zip?path=Vieja")
        self.assertEqual((st, h["content-type"]), (200, "application/zip"))
        z = zipfile.ZipFile(io.BytesIO(datos))
        self.assertEqual(z.namelist(), ["Vieja/foto.jpg"])
        self.assertEqual(z.read("Vieja/foto.jpg"), (self.compartido / "Vieja/foto.jpg").read_bytes())
        st, h, datos = self.crudo("GET", "/api/zip?path=Fotos")
        nombres = zipfile.ZipFile(io.BytesIO(datos)).namelist()
        self.assertIn("Fotos/dup.jpg", nombres)
        self.assertNotIn("Fotos/atajo.jpg", nombres)   # los accesos directos no entran
        self.assertFalse((self.fh / ".cache/zazu-zip").exists())
        z = zipfile.ZipFile(io.BytesIO(datos))
        self.assertIsNone(z.testzip())
        tipos = {i.filename: i.compress_type for i in z.infolist()}
        self.assertEqual((tipos["Fotos/dup.jpg"], tipos["Fotos/clip.mp4"]), (zipfile.ZIP_STORED, zipfile.ZIP_STORED))   # fotos y vídeos ya vienen comprimidos

    def test_el_hub_sigue_sirviendo_su_pagina(self):
        """Regresión: VIDEOS (los sufijos que se sirven por tramos) se pisó una vez con la carpeta de la caché de vídeos y tumbó todo lo estático."""
        import server
        self.assertIsInstance(server.VIDEOS, tuple)
        self.assertEqual(server.VIDEOS_CACHE.name, "zazu-videos")
        st, h, d = self.crudo("GET", "/index.html")
        self.assertEqual((st, h["content-type"]), (200, "text/html"))
        self.assertIn(b"HolaZazu", d)
        self.assertIn(b"Disallow: /c/", self.crudo("GET", "/robots.txt")[2])   # nada de indexar los enlaces compartidos

    def test_rutas_larguisimas_no_dan_500(self):
        for ruta in ("Fotos/" + "a" * 300 + ".jpg", "a/" * 400 + "x.jpg", "ñ" * 200 + ".jpg"):
            self.assertEqual(self.post("/api/nube/fav", {"paths": [ruta], "on": True})[0], 404, ruta[:20])
            self.assertEqual(self.post("/api/nube/enlace", {"path": ruta})[0], 404, ruta[:20])
        self.assertEqual(self.post("/api/nube/fav", {"paths": ["Fotos/" + "a" * 300 + ".jpg"], "on": False})[0], 200)

    def test_peticiones_a_la_vez(self):
        from concurrent.futures import ThreadPoolExecutor
        fotos = [IMG1, IMG2, IMG3, CLIP, "Fotos/dup.jpg", "Fotos/casi1.jpg", "Fotos/casi2.jpg", "Fotos/Verano/IMG_0001.jpg"]
        with ThreadPoolExecutor(8) as ex:
            # cada hilo marca y desmarca lo suyo muchas veces: al final tiene que quedar exactamente lo que dejó cada uno
            def trabajo(i):
                for _ in range(10):
                    self.assertEqual(self.post("/api/nube/fav", {"paths": [fotos[i]], "on": True})[0], 200)
                    self.assertEqual(self.post("/api/nube/fav", {"paths": [fotos[i]], "on": False})[0], 200)
                return self.post("/api/nube/fav", {"paths": [fotos[i]], "on": i % 2 == 0})[0]
            self.assertEqual(list(ex.map(trabajo, range(8))), [200] * 8)
            self.assertEqual(sorted(self.rutas(self.medios(fav="1"))), sorted(fotos[i] for i in range(0, 8, 2)))
            # el mismo nombre de álbum a la vez desde ocho sitios: gana uno solo
            codigos = list(ex.map(lambda _: self.post("/api/nube/album", {"accion": "crear", "nombre": "Carrera"})[0], range(8)))
            self.assertEqual(sorted(codigos), [200] + [409] * 7)
            self.assertEqual(len(self.albumes()), 1)
            # y 20 visitas a la vez a un enlace cuentan las 20
            tok = self.enlace(IMG1)
            antes = [e for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"] if e["token"] == tok][0]["visitas"]
            self.assertEqual(list(ex.map(lambda i: self.pub("GET", f"/c/{tok}", ip=f"203.0.113.{i + 1}")[0], range(20))), [200] * 20)
            despues = [e for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"] if e["token"] == tok][0]["visitas"]
            self.assertEqual(despues - antes, 20)
            # varias lecturas a la vez con el índice recién invalidado: todas ven lo mismo
            self.sync()
            totales = list(ex.map(lambda _: self.medios()["total"], range(8)))
            self.assertEqual(len(set(totales)), 1)

    # ---------- coherencia al cambiar archivos ----------
    def test_invalidacion_del_indice(self):
        self.sync()
        total0 = self.medios()["total"]
        self.poner("Fotos/sin_avisar.jpg", os.urandom(1000))   # directo al disco: la Nube no se entera sola hasta pasar 60 s
        self.assertEqual(self.medios()["total"], total0)
        self.sync()
        self.assertEqual(self.medios()["total"], total0 + 1)
        r = self.post("/api/mover", {"path": "Fotos/sin_avisar.jpg", "destino": "Otra"})[1]
        self.assertEqual(r["path"], "Otra/sin_avisar.jpg")
        self.assertEqual(self.rutas(self.medios(q="sin_avisar")), ["Otra/sin_avisar.jpg"])   # ya, sin esperar
        r = self.post("/api/renombrar", {"path": "Otra/sin_avisar.jpg", "nombre": "avisada.jpg"})[1]
        self.assertEqual(self.rutas(self.medios(q="avisada")), [r["path"]])
        self.assertEqual(self.medios(q="sin_avisar")["total"], 0)
        pid = self.post("/api/papelera", {"path": r["path"]})[1]["id"]
        self.assertEqual(self.medios(q="avisada")["total"], 0)
        self.assertEqual(self.post("/api/restaurar", {"id": pid})[1]["path"], "Otra/avisada.jpg")
        self.assertEqual(self.medios(q="avisada")["total"], 1)
        cuerpo = os.urandom(2500)
        st, h, d = self.crudo("POST", "/api/upload?name=subida.jpg&path=Otra", None, cuerpo)
        self.assertEqual(st, 200, d)
        self.assertEqual(self.rutas(self.medios(q="subida")), ["Otra/subida.jpg"])
        self.assertEqual(self.pedir("GET", "/api/nube")[1]["tipos"]["image"]["n"], self.contar_disco()["image"][0])

    def test_favoritos_albumes_y_enlaces_siguen_al_archivo(self):
        for rel in ("Mov/uno.jpg", "Mov/Sub/dos.jpg", "Otra/uno.jpg"):
            self.poner(rel, os.urandom(3000))
        self.sync()
        uno, dos = "Mov/uno.jpg", "Mov/Sub/dos.jpg"
        self.post("/api/nube/fav", {"paths": [uno, dos], "on": True})
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "Sigue", "paths": [uno, dos]})[1]["id"]
        t_uno, t_dos = self.enlace(uno), self.enlace(dos)
        datos_uno = (self.compartido / uno).read_bytes()
        # mover un archivo donde ya hay otro con ese nombre: llega como «uno (2).jpg» y lo suyo lo sigue
        nuevo = self.post("/api/mover", {"path": uno, "destino": "Otra"})[1]["path"]
        self.assertEqual(nuevo, "Otra/uno (2).jpg")
        self.assertEqual(sorted(self.rutas(self.medios(fav="1"))), sorted([nuevo, dos]))
        self.assertEqual(sorted(self.rutas(self.medios(album=aid))), sorted([nuevo, dos]))
        self.assertEqual({e["path"] for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"] if e["token"] == t_uno}, {nuevo})
        self.assertEqual(self.pub("GET", f"/c/{t_uno}")[2], datos_uno)   # el enlace sigue funcionando en su nuevo sitio
        # renombrar la carpeta: todo lo de dentro cambia de prefijo
        self.assertEqual(self.post("/api/renombrar", {"path": "Mov", "nombre": "Movido"})[1]["path"], "Movido")
        dos = "Movido/Sub/dos.jpg"
        self.assertEqual(sorted(self.rutas(self.medios(fav="1"))), sorted([nuevo, dos]))
        self.assertIn(dos, self.rutas(self.medios(album=aid)))
        self.assertEqual(self.pub("GET", f"/c/{t_dos}")[0], 200)
        # un nombre que solo se parece al prefijo no se toca
        self.poner("Movido2/ajeno.jpg", os.urandom(2000))
        self.sync()
        self.post("/api/nube/fav", {"paths": ["Movido2/ajeno.jpg"], "on": True})
        self.assertEqual(self.post("/api/renombrar", {"path": "Movido", "nombre": "Mov"})[0], 200)
        self.assertIn("Movido2/ajeno.jpg", self.rutas(self.medios(fav="1")))
        dos = "Mov/Sub/dos.jpg"
        # a la papelera: el enlace muere (y no resucita), el favorito y el álbum vuelven con el archivo
        pid = self.post("/api/papelera", {"path": dos})[1]["id"]
        self.assertEqual(self.pub("GET", f"/c/{t_dos}")[0], 404)
        self.assertNotIn(t_dos, [e["token"] for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"]])
        self.assertNotIn(dos, self.rutas(self.medios(fav="1")))
        self.assertEqual(self.albumes()[0]["n"], 1)
        self.assertEqual(self.post("/api/restaurar", {"id": pid})[1]["path"], dos)
        self.assertIn(dos, self.rutas(self.medios(fav="1")))
        self.assertEqual(self.albumes()[0]["n"], 2)
        self.assertEqual(self.pub("GET", f"/c/{t_dos}")[0], 404)   # compartirlo otra vez es decisión de Fran
        # mover a la misma carpeta no cambia nada
        self.assertEqual(self.post("/api/mover", {"path": dos, "destino": "Mov/Sub"})[1]["path"], dos)
        self.assertIn(dos, self.rutas(self.medios(fav="1")))

    # ---------- arreglos de la revisión ----------
    def test_mas_nuevas_ordena_por_la_hora_el_mismo_dia(self):
        """La fecha del listado es la del nombre (a las 12:00): el mismo día salían en el orden del disco, y la portada de un álbum no era la más reciente."""
        dia = [f"Orden/IMG_20240601_{h}.jpg" for h in ("081500", "235900", "120000")] + ["Orden/IMG-20240601-WA0002.jpg", "Orden/IMG-20240601-WA0010.jpg"]
        for r in dia:
            self.poner(r, os.urandom(1200))
        self.sync()
        esperado = sorted(dia, reverse=True)   # el mismo día, la ruta mayor primero: la hora (o el contador de WhatsApp) va en el nombre
        self.assertEqual(self.rutas(self.medios(en="orden/", n=200)), esperado)
        self.assertEqual(self.rutas(self.medios(en="orden/", n=200, orden="antiguas")), esperado[::-1])
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "Orden", "paths": dia})[1]["id"]
        al, = [a for a in self.albumes() if a["id"] == aid]
        self.assertEqual(al["portada"], esperado[0])   # la portada es la primera del listado
        self.assertEqual(self.rutas(self.medios(album=aid, n=200))[0], al["portada"])

    def test_miniaturas_a_la_vez_de_la_misma_foto(self):
        """Dos peticiones a la vez por una miniatura aún sin hacer se pisaban el temporal y la que perdía daba 404 (el icono de roto hasta recargar)."""
        if not (FFMPEG and HAY_PIL):
            self.skipTest("hacen falta ffmpeg y Pillow")
        from PIL import Image
        rutas = []
        for i in range(6):
            b = io.BytesIO()
            Image.new("RGB", (1200 + i, 900), (i * 30, 90, 160)).save(b, "JPEG")
            rutas.append(f"Minis/IMG_20240602_1{i}0000.jpg")
            self.poner(rutas[-1], b.getvalue())
        self.sync()
        with ThreadPoolExecutor(24) as ex:
            res = list(ex.map(lambda r: self.crudo("GET", "/api/nube/mini?path=" + urllib.parse.quote(r)), [r for r in rutas for _ in range(8)]))
        self.assertEqual([st for st, _, _ in res], [200] * 48)
        self.assertTrue(all(c[:2] == b"\xff\xd8" for _, _, c in res))
        self.assertEqual(list((self.fh / ".cache/zazu-miniaturas").glob("*.tmp.jpg")), [])   # sin temporales sueltos

    def test_busca_sin_tildes_ni_mayusculas(self):
        """«valencia» encuentra «València» y «VALENCIA», como en Carpetas."""
        self.poner("Viajes/València.jpg", os.urandom(3000))
        self.poner("Viajes/VALENCIA 2.jpg", os.urandom(3000))
        self.sync()
        self.assertEqual(sorted(m["name"] for m in self.medios(q="valencia")["items"]), ["VALENCIA 2.jpg", "València.jpg"])
        self.assertEqual(self.medios(q="valéncia")["total"], 2)

    def test_una_fecha_absurda_no_tumba_un_dia_como_hoy(self):
        """Un archivo con mtime del año 20000 (o negativo) se ignora: «Un día como hoy» sigue respondiendo."""
        self.poner("Raras/futuro.jpg", os.urandom(3000), mtime=600_000_000_000)
        self.poner("Raras/pasado.jpg", os.urandom(3000), mtime=-5)
        self.sync()
        self.assertEqual(self.pedir("GET", "/api/nube/medios?dia=hoy")[0], 200)

    def test_miniatura_de_un_nombre_con_patron_de_ffmpeg(self):
        """«foto%03d.jpg» no es una secuencia: sale su miniatura."""
        if not (FFMPEG and HAY_PIL):
            self.skipTest("hacen falta ffmpeg y Pillow")
        self.poner("Raras/foto%03d.jpg", jpeg())
        self.sync()
        st, h, c = self.crudo("GET", "/api/nube/mini?path=" + urllib.parse.quote("Raras/foto%03d.jpg"))
        self.assertEqual((st, c[:2]), (200, b"\xff\xd8"))   # un JPEG de verdad, no un 404

    def test_miniaturas_de_los_formatos_de_verdad(self):
        """ffmpeg solo abre contenedores de fotos y vídeos (lista blanca), pero los de verdad siguen saliendo, aunque la extensión mienta."""
        if not (FFMPEG and HAY_PIL):
            self.skipTest("hacen falta ffmpeg y Pillow")
        from PIL import Image
        im = Image.new("RGB", (320, 240), (30, 120, 60))
        casos = [("a.jpg", "JPEG"), ("a.png", "PNG"), ("a.webp", "WEBP"), ("a.bmp", "BMP"), ("a.tif", "TIFF"), ("a.gif", "GIF"), ("png_como.jpg", "PNG"), ("webp_como.jpg", "WEBP")]
        for nombre, formato in casos:
            b = io.BytesIO()
            im.save(b, formato)
            self.poner("Formatos/" + nombre, b.getvalue())
        for nombre in ("v.mp4", "v.mkv", "v.avi", "v.mov"):
            r = subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=5", "-c:v", "mpeg4", str(self.compartido / "Formatos" / nombre)],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0, r.stderr)
            casos.append((nombre, None))
        self.sync()
        for nombre, _ in casos:
            st, h, c = self.crudo("GET", "/api/nube/mini?path=Formatos/" + nombre)
            self.assertEqual((st, c[:2]), (200, b"\xff\xd8"), nombre)

    def test_un_manifiesto_disfrazado_no_hace_pedir_urls(self):
        """Un «vídeo» o una «foto» que en realidad es un manifiesto DASH hacía que ffmpeg pidiera URLs (internet o la red de casa) al sacar su miniatura o convertirlo."""
        if not FFMPEG:
            self.skipTest("sin ffmpeg")
        import http.server
        golpes = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(s):
                golpes.append(s.path)
                s.send_response(404)
                s.send_header("Content-Length", "0")
                s.end_headers()
            do_HEAD = do_GET

            def log_message(s, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            mpd = (f'<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT1S" minBufferTime="PT1S" '
                   f'profiles="urn:mpeg:dash:profile:isoff-on-demand:2011"><BaseURL>http://127.0.0.1:{srv.server_address[1]}/dash/</BaseURL><Period>'
                   f'<AdaptationSet mimeType="video/mp4"><Representation id="1" bandwidth="1000" width="64" height="48" codecs="avc1.42c01e"><BaseURL>seg.mp4</BaseURL>'
                   f'<SegmentBase indexRange="0-100"/></Representation></AdaptationSet></Period></MPD>')
            for n in ("dash.mp4", "dash.jpg"):
                self.poner("Fotos/" + n, mpd.encode())
            self.sync()
            for n in ("dash.mp4", "dash.jpg"):
                self.assertEqual(self.crudo("GET", "/api/nube/mini?path=Fotos/" + n)[0], 404)
            self.pedir("GET", "/api/nube/video-estado?path=Fotos/dash.mp4")
            time.sleep(1.5)   # la conversión va en segundo plano
            self.assertEqual(golpes, [])
        finally:
            srv.shutdown()
            srv.server_close()

    def test_vista_para_el_visor(self):
        """/api/nube/vista: la foto en JPEG de hasta w px por su lado largo (sin ampliar), en vez del original (varios MB) o de la miniatura de 360 px."""
        if not (FFMPEG and HAY_PIL):
            self.skipTest("hacen falta ffmpeg y Pillow")
        from PIL import Image
        for nombre, tam in (("grande_h", (2400, 1800)), ("grande_v", (1800, 2400)), ("chica", (800, 600))):
            b = io.BytesIO()
            Image.new("RGB", tam, (20, 90, 60)).save(b, "JPEG")
            self.poner(f"Vista/{nombre}.jpg", b.getvalue())
        self.sync()
        vista = lambda rel, **p: self.crudo("GET", "/api/nube/vista?" + urllib.parse.urlencode({"path": rel, **p}))
        dims = lambda c: Image.open(io.BytesIO(c)).size
        st, h, c = vista("Vista/grande_h.jpg")
        self.assertEqual((st, h["content-type"], dims(c)), (200, "image/jpeg", (1600, 1200)))   # 1600 por el lado largo
        self.assertEqual(dims(vista("Vista/grande_v.jpg")[2]), (1200, 1600))
        self.assertEqual(dims(vista("Vista/chica.jpg")[2]), (800, 600))   # lo pequeño no se amplía
        self.assertEqual(dims(vista("Vista/grande_h.jpg", w=800)[2]), (800, 600))
        self.assertEqual(dims(vista("Vista/grande_h.jpg", w=99999)[2]), (2400, 1800))   # con un tope
        self.assertEqual(dims(vista("Vista/grande_h.jpg", w=1)[2]), (400, 300))   # y un mínimo
        self.assertEqual(dims(self.crudo("GET", "/api/nube/mini?path=Vista/grande_h.jpg")[2]), (360, 270))   # la miniatura de siempre no cambia
        self.assertEqual(vista("Vista/grande_h.jpg", w="x")[0], 400)
        for malo in (CLIP, "Docs/informe.pdf", "Fotos", "../secreto.txt", "Fotos/atajo.jpg"):   # solo fotos de Compartido
            self.assertIn(vista(malo)[0], (403, 404), malo)

    def test_un_nombre_que_no_es_utf8_o_una_fecha_absurda_no_rompen_la_galeria(self):
        raro = os.fsencode(str(self.compartido / "Fotos")) + b"/IMG_20991231_\xff\xfe.jpg"
        with open(raro, "wb") as f:
            f.write(b"\xff\xd8\xff" + os.urandom(900))
        futuro = self.poner("Fotos/futuro_raro.jpg", os.urandom(1200))
        try:
            os.utime(futuro, (4e11, 4e11))   # el año 14600
            absurda = True
        except OSError:   # un sistema de archivos que no admite esa fecha
            absurda = False
        try:
            self.sync()
            st, d = self.pedir("GET", "/api/nube/medios?n=200")
            self.assertEqual(st, 200, d)
            self.assertEqual(self.pedir("GET", "/api/nube/medios?dia=hoy")[0], 200)   # (con el de la fecha absurda daba 400)
            self.assertEqual(self.pedir("GET", "/api/nube/medios?orden=antiguas&n=200")[0], 200)
            self.assertEqual(self.pedir("GET", "/api/files?path=Fotos")[0], 200)   # Carpetas, con ese nombre, también daba 400
            if absurda:
                self.assertEqual({i["name"]: i["mtime"] for i in d["items"]}["futuro_raro.jpg"], 0)
        finally:
            os.unlink(raro)
            futuro.unlink()
            self.sync()

    def test_la_web_deja_pedir_los_mosaicos_de_openstreetmap(self):
        for ruta in ("/index.html", "/"):
            csp = self.crudo("GET", ruta)[1]["content-security-policy"]
            self.assertIn("img-src 'self' data: blob: https://tile.openstreetmap.org;", csp)   # sin esto el navegador bloqueaba todos los mosaicos del mapa
            self.assertIn("connect-src 'self';", csp)   # y nada más se abre

    def test_json_anidado_a_lo_loco_es_una_peticion_mala(self):
        cuerpo = b"[" * 120000 + b"]" * 120000
        for r in ("/api/nube/fav", "/api/nube/album", "/api/nube/enlace", "/api/nube/enlace/revocar"):
            st, h, d = self.crudo("POST", r, cab={"Content-Type": "application/json"}, cuerpo=cuerpo)
            self.assertEqual(st, 400, r)   # (daba 500 con el texto de Python)
            self.assertNotIn(b"Recursion", d)

    def test_otra_web_no_dispara_lo_caro(self):
        """Una web ajena puede mandar tu navegador a /api/zip o a /api/nube/duplicados?rehacer=1 (la galleta viaja en una navegación): se corta por Sec-Fetch-Site."""
        for r in ("/api/nube/duplicados?rehacer=1", "/api/zip?path=Fotos", "/api/nube/zip?fav=1", "/api/nube/video-estado?path=" + CLIP, "/api/nube/mini?path=" + IMG1, "/api/nube"):
            self.assertEqual(self.crudo("GET", r, cab={"Sec-Fetch-Site": "cross-site"})[0], 403, r)
        for r in ("/api/nube/duplicados?rehacer=1", "/api/zip?path=Fotos", "/api/nube", "/api/files?path=Fotos"):
            for ok in ("same-origin", "none", "same-site"):   # la propia web, la barra de direcciones y un subdominio
                self.assertEqual(self.crudo("GET", r, cab={"Sec-Fetch-Site": ok})[0], 200, (r, ok))
            self.assertEqual(self.crudo("GET", r)[0], 200, r)   # y quien no manda la cabecera (la app de Android, curl)

    def test_un_video_se_convierte_y_se_sirve_por_tramos(self):
        """La conversión a H.264 (la que usan los HEVC del móvil) sigue andando con la lista blanca de formatos de ffmpeg."""
        if not FFMPEG:
            self.skipTest("sin ffmpeg")
        r = subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10", "-c:v", "mpeg4", str(self.compartido / "Fotos/conv.mkv")],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sync()
        fin = time.time() + 60
        while True:   # (en la casa falsa no hay ffprobe: todo vídeo pasa por la conversión)
            st, d = self.pedir("GET", "/api/nube/video-estado?path=Fotos/conv.mkv")
            if d.get("listo") or time.time() > fin:
                break
            time.sleep(0.3)
        self.assertEqual((st, d["listo"], d.get("error")), (200, True, None))
        st, h, c = self.crudo("GET", "/api/nube/video?path=Fotos/conv.mkv")
        self.assertEqual((st, h["content-type"], c[4:8]), (200, "video/mp4", b"ftyp"))
        st, h, c2 = self.crudo("GET", "/api/nube/video?path=Fotos/conv.mkv", cab={"Range": "bytes=0-99"})
        self.assertEqual((st, c2), (206, c[:100]))

    def test_un_video_que_no_se_puede_convertir_no_se_reintenta(self):
        """Un .mp4 estropeado relanzaba ffmpeg en cada sondeo del visor (cada 2-5 s) y la pantalla se quedaba en «Preparando el vídeo…» para siempre."""
        self.poner("Fotos/roto.mp4", os.urandom(50000))
        self.sync()
        estado = lambda: self.pedir("GET", "/api/nube/video-estado?path=Fotos/roto.mp4")
        fin = time.time() + 30
        while True:
            st, d = estado()
            if d.get("error") or time.time() > fin:
                break
            time.sleep(0.3)
        self.assertEqual((st, d["listo"], d.get("error")), (200, False, True))
        veces = lambda: (self.dir / "hub.log").read_text(errors="replace").count("no pude convertir roto.mp4")
        antes = veces()
        self.assertEqual(antes, 1)
        for _ in range(5):
            self.assertTrue(estado()[1].get("error"))
            time.sleep(0.1)
        self.assertEqual(veces(), antes)   # no se ha vuelto a lanzar ffmpeg
        self.assertEqual(self.pedir("GET", "/api/nube/video-estado?path=Docs/nota.txt")[0], 400)   # lo que no es un vídeo ni se intenta
        self.assertEqual(self.pedir("GET", "/api/nube/video-estado?path=Fotos/IMG_20240117_212002.jpg")[0], 400)


class NubeEnlaces(NubeBase):
    def firma(self, r):
        st, h, cuerpo = r
        return st, cuerpo, {k: h.get(k) for k in ("content-type", "content-length", "cache-control", "x-robots-tag", "referrer-policy")}

    def test_crear_y_abrir_sin_sesion(self):
        antes = time.time()
        st, d = self.post("/api/nube/enlace", {"path": IMG1})
        self.assertEqual(st, 200)
        tok = d["token"]
        type(self).tokens.append(tok)
        self.assertRegex(tok, r"^[A-Za-z0-9_-]{22}$")   # 128 bits
        self.assertEqual(d["url"], f"https://holazazu.app/c/{tok}")
        self.assertAlmostEqual(d["caduca"], antes + 24 * 3600, delta=30)   # 24 horas por defecto
        self.assertEqual(set(d), {"ok", "token", "url", "caduca", "gps", "sin_gps"})
        self.assertEqual((d["gps"], d["sin_gps"]), (False, False))   # una foto sin ubicación se comparte tal cual
        datos = (self.compartido / IMG1).read_bytes()
        for puerto in (self.pub_port, self.hub_port):   # por internet y por el puerto local, con las mismas reglas
            st, h, cuerpo = peticion(puerto, "GET", f"/c/{tok}", cab={"CF-Connecting-IP": "203.0.113.50"})
            self.assertEqual((st, cuerpo), (200, datos))
            self.assertEqual(h["content-type"], "image/jpeg")
            self.assertTrue(h["content-disposition"].startswith("inline;"))   # una foto se ve en el navegador
            self.assertEqual(h["cache-control"], "private, no-store")
            self.assertEqual(h["vary"], "*")   # el service worker de la web no puede guardarlo en su caché
            self.assertEqual(h["x-robots-tag"], "noindex, nofollow")
            self.assertEqual(h["referrer-policy"], "no-referrer")
            self.assertEqual(h["x-content-type-options"], "nosniff")
            self.assertIn("sandbox", h["content-security-policy"])
            self.assertEqual(h["accept-ranges"], "bytes")
        # solo se ve en el navegador lo seguro (imagen, audio, vídeo); lo demás se descarga
        for rel, tipo, disp in (("Docs/informe.pdf", "application/pdf", "attachment"), ("Docs/nota.txt", "text/plain; charset=utf-8", "attachment"),
                                ("Docs/raro.bin", "application/octet-stream", "attachment"), ("Docs/musica.mp3", "audio/mpeg", "inline"), (CLIP, "video/mp4", "inline")):
            t = self.enlace(rel)
            st, h, _ = self.pub("GET", f"/c/{t}")
            self.assertEqual((st, h["content-type"], h["content-disposition"].split(";")[0]), (200, tipo, disp), rel)
            if tipo.startswith(("video/", "audio/")):   # abierto directamente, el navegador carga su propio archivo como medio: con «sandbox» o sin media-src no se reproduce (visto en Chrome)
                self.assertIn("media-src 'self'", h["content-security-policy"], rel)
                self.assertNotIn("sandbox", h["content-security-policy"], rel)
                self.assertTrue(h["content-security-policy"].startswith("default-src 'none'"), rel)   # y lo demás sigue cerrado
        # HEAD: las cabeceras del GET y ningún cuerpo
        st, h, cuerpo = self.pub("HEAD", f"/c/{tok}")
        self.assertEqual((st, cuerpo, int(h["content-length"]), h["content-type"]), (200, b"", len(datos), "image/jpeg"))
        self.assertEqual(h["cache-control"], "private, no-store")
        # una foto que se llama con tildes y espacios
        self.poner("Fotos/Año nuevo ñ.jpg", os.urandom(1500))
        self.sync()
        st, h, _ = self.pub("GET", f"/c/{self.enlace('Fotos/Año nuevo ñ.jpg')}")
        self.assertEqual((st, h["content-disposition"]), (200, "inline; filename*=UTF-8''A%C3%B1o%20nuevo%20%C3%B1.jpg"))

    def test_rangos_y_visitas(self):
        tok = self.enlace(CLIP, horas=2)
        datos = (self.compartido / CLIP).read_bytes()
        n = len(datos)
        st, h, c = self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=0-99"})
        self.assertEqual((st, c, h["content-range"], h["content-length"]), (206, datos[:100], f"bytes 0-99/{n}", "100"))
        st, h, c = self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=1000-1999"})
        self.assertEqual((st, c, h["content-range"]), (206, datos[1000:2000], f"bytes 1000-1999/{n}"))
        self.assertEqual(self.pub("GET", f"/c/{tok}", cab={"Range": f"bytes={n - 10}-"})[2], datos[-10:])
        self.assertEqual(self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=-25"})[2], datos[-25:])
        st, h, c = self.pub("GET", f"/c/{tok}", cab={"Range": f"bytes={n + 5}-"})
        self.assertEqual((st, c, h["content-range"], h["content-length"]), (416, b"", f"bytes */{n}", "0"))   # (con Content-Length: 0 para que no se quede esperando)
        self.assertEqual(self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=0-1,5-9"})[0], 200)   # varios tramos: se manda entero
        self.assertEqual(self.pub("HEAD", f"/c/{tok}", cab={"Range": "bytes=0-9"})[1]["content-range"], f"bytes 0-9/{n}")
        # visitas: abrirlo cuenta; los trozos siguientes de un reproductor y los HEAD no
        def visitas():
            it, = [e for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"] if e["token"] == tok]
            return it["visitas"]
        base = visitas()
        self.pub("GET", f"/c/{tok}")
        self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=0-"})
        self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=5000-6000"})
        self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=-100"})
        self.pub("HEAD", f"/c/{tok}")
        self.assertEqual(visitas() - base, 2)
        it, = [e for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"] if e["token"] == tok]
        self.assertEqual(set(it), {"id", "token", "path", "creado", "caduca", "visitas", "clave", "url"})
        self.assertEqual((it["path"], it["clave"], it["url"]), (CLIP, False, f"https://holazazu.app/c/{tok}"))
        self.assertAlmostEqual(it["caduca"], time.time() + 2 * 3600, delta=30)

    def test_validacion_al_crear(self):
        for cuerpo, esperado in (
                ({}, 400), ({"path": 5}, 400), ({"path": None}, 400), ({"path": "Fotos"}, 400), ({"path": ""}, 400),   # una carpeta no se comparte
                ({"path": "Fotos/no_existe.jpg"}, 404), ({"path": "../../etc/passwd"}, 403), ({"path": "/etc/passwd"}, 404),
                ({"path": "Fotos/atajo.jpg"}, 403), ({"path": ".stfolder/x"}, 403), ({"path": "a\x00b"}, 403),
                ({"path": IMG1, "horas": 0}, 400), ({"path": IMG1, "horas": -3}, 400), ({"path": IMG1, "horas": 721}, 400), ({"path": IMG1, "horas": "2"}, 400),
                ({"path": IMG1, "horas": True}, 400), ({"path": IMG1, "horas": 1.5}, 400), ({"path": IMG1, "horas": [1]}, 400),
                ({"path": IMG1, "clave": "x" * 65}, 400), ({"path": IMG1, "clave": 1234}, 400), ({"path": IMG1, "clave": ["a"]}, 400),
                ({"path": IMG1, "clave": "x"}, 400), ({"path": IMG1, "clave": "12345"}, 400),   # una clave de una letra se adivina en un minuto: 6 como mínimo
                ({"path": IMG1, "sin_gps": "no"}, 400), ({"path": IMG1, "sin_gps": 0}, 400)):
            self.assertEqual(self.post("/api/nube/enlace", cuerpo)[0], esperado, cuerpo)
        antes = len(self.pedir("GET", "/api/nube/enlaces")[1]["items"])
        for horas in (1, 720, None):
            st, d = self.post("/api/nube/enlace", {"path": IMG1, "horas": horas, "clave": "x" * 64 if horas == 720 else None})
            self.assertEqual(st, 200, horas)
            type(self).tokens.append(d["token"])
            esperado = {1: 1, 720: 720, None: 24}[horas]
            self.assertAlmostEqual(d["caduca"], time.time() + esperado * 3600, delta=30)
        self.assertEqual(len(self.pedir("GET", "/api/nube/enlaces")[1]["items"]), antes + 3)
        self.assertEqual(self.post("/api/nube/enlace/revocar", {"token": "corto"})[0], 400)
        self.assertEqual(self.post("/api/nube/enlace/revocar", {})[0], 400)
        self.assertEqual(self.post("/api/nube/enlace/revocar", {"token": "z" * 22})[0], 200)   # idempotente

    def test_lista_y_revocar(self):
        t1, t2 = self.enlace(IMG2), self.enlace(IMG3, clave="zxq-clave-que-no-sale")
        todos = {e["token"]: e for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"]}
        self.assertEqual((todos[t1]["path"], todos[t1]["clave"], todos[t2]["clave"]), (IMG2, False, True))
        self.assertEqual(len({e["id"] for e in todos.values()}), len(todos))
        self.assertNotIn(CADUCADO, todos)   # los caducados no se listan
        self.assertNotIn("zxq-clave", json.dumps(todos))   # ni la clave ni su hash viajan
        self.assertTrue(all(len(e["id"]) == 8 and e["id"] not in e["token"] for e in todos.values()))   # el id no es un trozo del token
        sol = self.pedir("GET", "/api/nube/enlaces?path=" + urllib.parse.quote(IMG3))[1]["items"]
        self.assertIn(t2, [e["token"] for e in sol])
        self.assertNotIn(t1, [e["token"] for e in sol])
        self.assertEqual({e["path"] for e in sol}, {IMG3})   # solo los de ese archivo
        self.assertEqual(self.pedir("GET", "/api/nube/enlaces?path=" + urllib.parse.quote("../x"))[0], 403)
        self.assertEqual(self.pub("GET", f"/c/{t1}")[0], 200)
        self.assertEqual(self.post("/api/nube/enlace/revocar", {"token": t1})[0], 200)
        self.assertEqual(self.pub("GET", f"/c/{t1}")[0], 404)
        self.assertNotIn(t1, [e["token"] for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"]])

    def test_404_identico(self):
        desconocido = self.firma(self.pub("GET", "/c/" + "x" * 22))
        self.assertEqual(desconocido[0], 404)
        self.assertEqual(desconocido[1], b"No encontrado")
        self.assertEqual(self.firma(self.pub("GET", f"/c/{CADUCADO}")), desconocido)   # caducado
        t = self.enlace(IMG3)
        self.post("/api/nube/enlace/revocar", {"token": t})
        self.assertEqual(self.firma(self.pub("GET", f"/c/{t}")), desconocido)   # revocado
        self.poner("Fotos/efimera.jpg", os.urandom(2000))
        self.sync()
        t = self.enlace("Fotos/efimera.jpg")
        self.assertEqual(self.pub("GET", f"/c/{t}")[0], 200)
        (self.compartido / "Fotos/efimera.jpg").unlink()   # borrado a mano
        self.assertEqual(self.firma(self.pub("GET", f"/c/{t}")), desconocido)
        for malo in ("corto", "x" * 15, "x" * 41, "a b" + "c" * 20, "../" * 8, "%2e%2e%2f" * 4, "ñ" * 20, "x" * 22 + "/", "x" * 22 + "/mas", ""):
            ruta = "/c/" + urllib.parse.quote(malo, safe="/%")
            self.assertEqual(self.firma(self.pub("GET", ruta)), desconocido, malo)   # ni con una forma rara hay pistas
        st, h, c = self.pub("HEAD", "/c/" + "x" * 22)
        self.assertEqual((st, c, h["content-length"]), (404, b"", str(len(b"No encontrado"))))
        st, h, c = self.pub("POST", "/c/" + "x" * 22, cab={"Content-Type": "application/x-www-form-urlencoded"}, cuerpo=b"clave=1")
        self.assertEqual((st, c), (404, b"No encontrado"))
        self.assertEqual(self.pub("POST", f"/c/{CADUCADO}", cuerpo=b"clave=1")[:3:2], (404, b"No encontrado"))
        self.assertEqual(self.pub("PUT", "/c/" + "x" * 22)[0], 405)   # nada de escribir por aquí

    def test_con_clave(self):
        tok = self.enlace(IMG1, clave="Secreta 1")
        datos = (self.compartido / IMG1).read_bytes()
        st, h, c = self.pub("GET", f"/c/{tok}")
        self.assertEqual((st, h["content-type"]), (200, "text/html; charset=utf-8"))
        self.assertNotIn(datos[:50], c)
        self.assertNotIn(b"IMG_", c)   # el formulario no dice cómo se llama el archivo
        self.assertIn(b'method="post"', c)
        self.assertIn(b'type="password"', c)
        self.assertNotIn(tok.encode(), c)
        self.assertEqual((h["cache-control"], h["vary"]), ("private, no-store", "*"))
        self.assertIn("default-src 'none'", h["content-security-policy"])
        self.assertIn("form-action 'self'", h["content-security-policy"])
        self.assertNotIn(b"<script", c)
        self.assertEqual(self.pub("HEAD", f"/c/{tok}")[:2][0], 200)
        # la clave nunca en la dirección
        self.assertEqual(self.pub("GET", f"/c/{tok}?clave=Secreta%201")[2], c)
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        enviar = lambda clave, ip, cab=None: self.pub("POST", f"/c/{tok}", ip=ip, cab={**form, **(cab or {})}, cuerpo=urllib.parse.urlencode({"clave": clave}).encode())
        st, h, c = enviar("mala", "203.0.113.60")
        self.assertEqual(st, 403)
        self.assertIn("Esa clave no es correcta".encode(), c)
        self.assertNotIn("set-cookie", h)
        st, h, c = enviar("Secreta 1", "203.0.113.60")
        self.assertEqual((st, h["location"], c), (303, f"/c/{tok}", b""))
        galleta = h["set-cookie"]
        self.assertTrue(galleta.startswith("cz="))
        for parte in (f"Path=/c/{tok}", "HttpOnly", "Secure", "SameSite=Lax", "Max-Age="):
            self.assertIn(parte, galleta)
        pase = galleta.split(";")[0]
        st, h, c = self.pub("GET", f"/c/{tok}", cab={"Cookie": pase})
        self.assertEqual((st, c), (200, datos))   # con el pase, el archivo
        self.assertEqual(self.pub("GET", f"/c/{tok}", cab={"Cookie": pase, "Range": "bytes=0-9"})[2], datos[:10])
        self.assertEqual(self.pub("HEAD", f"/c/{tok}", cab={"Cookie": pase})[1]["content-length"], str(len(datos)))
        # un pase estropeado, de otro enlace, caducado o inventado no vale
        valor = pase[3:]
        otro = self.enlace(IMG2, clave="Secreta 1")
        for malo in (valor[:-1] + ("0" if valor[-1] != "0" else "1"), "1." + valor.split(".", 1)[1], "abc", "", "9999999999." + "0" * 32, "é.é", valor + "x"):
            st, h, c = self.pub("GET", f"/c/{tok}", cab={"Cookie": "cz=" + malo})
            self.assertEqual((st, h["content-type"]), (200, "text/html; charset=utf-8"), malo)
        self.assertEqual(self.pub("GET", f"/c/{otro}", cab={"Cookie": pase})[1]["content-type"], "text/html; charset=utf-8")   # el pase es de ese enlace
        # si se revoca, el pase ya no sirve de nada
        self.post("/api/nube/enlace/revocar", {"token": tok})
        self.assertEqual(self.pub("GET", f"/c/{tok}", cab={"Cookie": pase})[0], 404)
        # POST sin clave que pedir: de vuelta al GET
        libre = self.enlace(IMG3)
        st, h, _ = self.pub("POST", f"/c/{libre}", cab=form, cuerpo=b"clave=lo+que+sea")
        self.assertEqual((st, h["location"]), (303, f"/c/{libre}"))
        self.assertNotIn("set-cookie", h)
        # cuerpo vacío o enorme
        t2 = self.enlace(IMG2, clave="clave2")
        self.assertEqual(self.pub("POST", f"/c/{t2}", cab=form, cuerpo=b"")[0], 400)   # sin clave
        self.assertEqual(self.pub("POST", f"/c/{t2}", cab=form, cuerpo=b"otra=cosa")[0], 400)
        st, h, c = self.pub("POST", f"/c/{t2}", cab=form, cuerpo=b"clave=" + b"a" * 5000)   # un cuerpo enorme ni se lee
        self.assertEqual((st, c), (404, b"No encontrado"))

    def test_limite_de_intentos(self):
        tok = self.enlace(IMG1, clave="buena-clave")
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        probar = lambda clave, ip: self.pub("POST", f"/c/{tok}", ip=ip, cab=form, cuerpo=urllib.parse.urlencode({"clave": clave}).encode())
        for i in range(5):
            self.assertEqual(probar(f"mala{i}", "203.0.113.70")[0], 403, i)
        st, h, c = probar("mala5", "203.0.113.70")   # a la sexta, 429
        self.assertEqual(st, 429)
        self.assertTrue(0 < int(h["retry-after"]) <= 601)
        self.assertEqual(probar("buena-clave", "203.0.113.70")[0], 429)   # ni acertando: espera
        self.assertEqual(self.pub("GET", f"/c/{tok}", ip="203.0.113.70")[0], 200)   # (ver el formulario no cuenta)
        self.assertEqual(probar("buena-clave", "203.0.113.71")[0], 303)   # otra IP no está castigada
        # y entre todas las IP, 30 en total
        tok2 = self.enlace(IMG2, clave="otra-buena")
        probar2 = lambda clave, ip: self.pub("POST", f"/c/{tok2}", ip=ip, cab=form, cuerpo=urllib.parse.urlencode({"clave": clave}).encode())
        for i in range(30):
            self.assertEqual(probar2("mala", f"203.0.113.{100 + i // 5}")[0], 403, i)
        self.assertEqual(probar2("otra-buena", "203.0.113.200")[0], 429)   # una IP nueva con la clave buena también espera
        self.assertEqual(probar("buena-clave", "203.0.113.201")[0], 303)   # los demás enlaces no se ven afectados

    def test_rutas_peligrosas(self):
        # un acceso directo hacia fuera no se puede compartir; ni siquiera con el nombre de uno de verdad
        self.assertEqual(self.post("/api/nube/enlace", {"path": "Fotos/atajo.jpg"})[0], 403)
        # un archivo de verdad que luego se cambia por un acceso directo hacia fuera: 404, nunca el contenido de fuera
        p = self.poner("Fotos/cambiante.jpg", os.urandom(2000))
        self.sync()
        tok = self.enlace("Fotos/cambiante.jpg")
        self.assertEqual(self.pub("GET", f"/c/{tok}")[0], 200)
        p.unlink()
        os.symlink(self.fh / "secreto.txt", p)
        st, h, c = self.pub("GET", f"/c/{tok}")
        self.assertEqual((st, c), (404, b"No encontrado"))
        self.assertNotIn(FUERA, c)
        # una carpeta intermedia que pasa a ser un acceso directo hacia fuera
        self.poner("Zona/dentro.jpg", os.urandom(2000))
        self.sync()
        tok = self.enlace("Zona/dentro.jpg")
        shutil.move(str(self.compartido / "Zona"), str(self.fh / "ZonaFuera"))
        os.symlink(self.fh / "ZonaFuera", self.compartido / "Zona")
        self.assertEqual(self.pub("GET", f"/c/{tok}")[0], 404)
        # el archivo pasa a ser una carpeta
        self.poner("Fotos/seraDir.jpg", os.urandom(1000))
        self.sync()
        tok = self.enlace("Fotos/seraDir.jpg")
        (self.compartido / "Fotos/seraDir.jpg").unlink()
        (self.compartido / "Fotos/seraDir.jpg").mkdir()
        self.assertEqual(self.pub("GET", f"/c/{tok}")[0], 404)
        # movido a mano (sin pasar por la app): no se sabe dónde está → 404; movido con la app: el enlace lo sigue (ver test de coherencia)
        self.poner("Fotos/ala.jpg", os.urandom(1000))
        self.sync()
        tok = self.enlace("Fotos/ala.jpg")
        os.rename(self.compartido / "Fotos/ala.jpg", self.compartido / "Fotos/ala_movida.jpg")
        self.assertEqual(self.pub("GET", f"/c/{tok}")[0], 404)

    def test_guardia_de_escaneos(self):
        # 30 enlaces inventados por minuto desde la misma IP: bloqueada una hora; otra IP sigue bien
        ip = "203.0.113.150"
        codigos = [self.pub("GET", "/c/" + f"inventado{i:02d}".ljust(22, "q"), ip=ip)[0] for i in range(32)]
        self.assertEqual(codigos[:29], [404] * 29)
        self.assertEqual(codigos[-1], 403)   # bloqueada
        self.assertEqual(self.pub("GET", "/c/" + "x" * 22, ip="203.0.113.151")[0], 404)   # la otra, no
        tok = self.enlace(IMG1)
        self.assertEqual(self.pub("GET", f"/c/{tok}", ip=ip)[0], 403)   # la bloqueada tampoco ve los enlaces buenos
        self.assertEqual(self.pub("GET", f"/c/{tok}", ip="203.0.113.152")[0], 200)
        # un token con pinta de ruta de escáner no se confunde con uno (letras al azar que forman «/eval…» o «pma-»)
        for raro in ("evalAAAAAAAAAAAAAAAAAA", "pma-AAAAAAAAAAAAAAAAAA", "shellAAAAAAAAAAAAAAAAA", "cmdAAAAAAAAAAAAAAAAAAA"):
            self.assertEqual(self.pub("GET", f"/c/{raro}", ip="203.0.113.153")[0], 404, raro)
        self.assertEqual(self.pub("GET", "/c/" + "x" * 22, ip="203.0.113.153")[0], 404)   # (y 404 normal: no bloqueada tras 6 seguidas)
        log = self.fh / ".local/state/hermes-hub/seguridad.log"
        self.assertTrue(log.exists())
        suyas = [l for l in log.read_text().splitlines() if "203.0.113.153" in l]
        self.assertTrue(suyas)
        self.assertTrue(all("/c/…" in l and "respuesta 404" in l for l in suyas), suyas)   # «respuesta 404» a un enlace inexistente, no «ruta de escáner»
        self.assertTrue(any("/c/…" in l for l in log.read_text().splitlines()))
        self.assertNotIn("inventado", log.read_text())   # el token nunca va al registro de seguridad
        self.assertNotIn("evalAAAA", log.read_text())

    def test_intentos_de_clave_a_la_vez(self):
        """Peticiones simultáneas no esquivan el límite: el intento se apunta antes de gastar scrypt (antes pasaban todas y la clave buena abría el enlace)."""
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        tok = self.enlace(IMG1, clave="Buena-clave-1")
        intento = lambda a: self.pub("POST", f"/c/{tok}", ip=a[1], cab=form, cuerpo=urllib.parse.urlencode({"clave": a[0]}).encode())[0]
        with ThreadPoolExecutor(40) as ex:
            r = list(ex.map(intento, [(f"mala{i}", "203.0.113.31") for i in range(40)]))   # 40 a la vez desde una IP
        self.assertEqual((r.count(403), r.count(429)), (5, 35))   # solo se miraron 5
        self.assertEqual(intento(("Buena-clave-1", "203.0.113.31")), 429)   # y ni acertando
        self.assertEqual(intento(("Buena-clave-1", "203.0.113.32")), 303)
        tok2 = self.enlace(IMG2, clave="Buena-clave-2")
        intento2 = lambda a: self.pub("POST", f"/c/{tok2}", ip=a[1], cab=form, cuerpo=urllib.parse.urlencode({"clave": a[0]}).encode())[0]
        with ThreadPoolExecutor(40) as ex:
            r = list(ex.map(intento2, [(f"mala{i}", f"203.0.113.{40 + i % 10}") for i in range(40)]))   # 40 a la vez desde 10 IP: 4 cada una
        self.assertEqual((r.count(403), r.count(429)), (30, 10))   # 30 por enlace, no más
        self.assertEqual(intento2(("Buena-clave-2", "203.0.113.99")), 429)

    def test_ipv6_un_64_es_un_solo_cliente(self):
        """Con un /64 de IPv6 se puede usar una dirección distinta en cada petición: los límites por IP no frenaban nada."""
        import server
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        tok = self.enlace(IMG1, clave="Secreta-ip6")
        malas = lambda ip: self.pub("POST", f"/c/{tok}", ip=ip, cab=form, cuerpo=b"clave=mala")[0]
        self.assertEqual([malas(f"2001:db8:aa:bb:{i:x}::{i + 1:x}") for i in range(8)], [403] * 5 + [429] * 3)
        self.assertEqual(malas("2001:db8:aa:cc::1"), 403)   # otra red /64 no está castigada
        self.assertEqual(malas("203.0.113.77"), 403)
        falso = lambda cab, dir="127.0.0.1", ts=False: types.SimpleNamespace(headers=cab, client_address=(dir, 1), server=types.SimpleNamespace(trust_tailscale=ts))
        ip = lambda *a, **k: server.H.ip(falso(*a, **k))
        self.assertEqual(ip({"CF-Connecting-IP": "2001:db8:1:2:3:4:5:6"}), "2001:db8:1:2::/64")
        self.assertEqual(ip({"CF-Connecting-IP": "2001:DB8:1:2::9"}), "2001:db8:1:2::/64")
        self.assertEqual(ip({"CF-Connecting-IP": "203.0.113.5"}), "203.0.113.5")   # IPv4 sin tocar
        self.assertEqual(ip({"CF-Connecting-IP": "::ffff:203.0.113.5"}), "203.0.113.5")   # una IPv4 «mapeada» sigue siendo IPv4 (no todas juntas en un «::/64»)
        self.assertEqual(ip({"CF-Connecting-IP": "no es una ip"}), "no es una ip")
        self.assertEqual(ip({}, "127.0.0.1"), "127.0.0.1")
        self.assertEqual(ip({"CF-Connecting-IP": "2001:db8::1"}, ts=True), "127.0.0.1")   # por Tailscale manda la conexión, no la cabecera

    def test_digitos_enormes_no_rompen_la_conexion(self):
        """Un Range o una galleta cz con más de 4300 dígitos lanzaba ValueError en int(): la conexión se cortaba sin respuesta y el registro se llenaba de trazas."""
        libre, prot = self.enlace(CLIP), self.enlace(IMG1, clave="Secreta 9")
        st, h, c = self.pub("GET", f"/c/{libre}", cab={"Range": "bytes=" + "9" * 5000 + "-"})
        self.assertEqual(st, 200)   # (un Range que no es de verdad se ignora: se manda entero)
        self.assertEqual(self.pub("GET", f"/c/{libre}", cab={"Range": "bytes=0-" + "9" * 5000})[0], 200)
        self.assertEqual(self.pub("GET", f"/c/{libre}", cab={"Range": "bytes=0-99999999999999"})[0], 206)   # uno enorme pero posible, sí
        st, h, c = self.pub("GET", f"/c/{prot}", cab={"Cookie": "cz=" + "9" * 5000 + ".aaaa"})
        self.assertEqual((st, h["content-type"]), (200, "text/html; charset=utf-8"))   # el formulario de la clave
        (self.fh / "static/prueba.mp4").write_bytes(os.urandom(2000))   # y los vídeos estáticos de la web (se sirven por tramos) tenían lo mismo
        self.assertEqual(self.crudo("GET", "/prueba.mp4", cab={"Range": "bytes=" + "9" * 5000 + "-"})[0], 200)
        self.assertEqual(self.crudo("GET", "/prueba.mp4", cab={"Range": "bytes=0-9"})[0], 206)
        self.assertNotIn("Traceback", (self.dir / "hub.log").read_text(errors="replace"))

    def test_enlace_a_un_archivo_que_ya_no_esta_no_sirve_otro(self):
        """El enlace seguía a la RUTA: si el archivo desaparecía por fuera de la app y otro ocupaba su nombre, el enlace antiguo servía el nuevo."""
        self.poner("Fotos/factura.jpg", b"\xff\xd8\xff" + b"FACTURA-DE-AGOSTO" + os.urandom(500))
        self.sync()
        tok = self.enlace("Fotos/factura.jpg", horas=720)
        self.assertIn(b"FACTURA-DE-AGOSTO", self.pub("GET", f"/c/{tok}")[2])
        (self.compartido / "Fotos/factura.jpg").unlink()   # borrado desde el móvil o Syncthing (la app sí habría revocado el enlace)
        self.assertEqual(self.pub("GET", f"/c/{tok}")[0], 404)
        self.poner("Fotos/factura.jpg", b"\xff\xd8\xff" + b"OTRA-FACTURA-PRIVADA" + os.urandom(500))
        st, h, c = self.pub("GET", f"/c/{tok}")
        self.assertEqual((st, c), (404, b"No encontrado"))
        self.assertNotIn(tok, [e["token"] for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"]])   # el enlace quedó revocado

    def copias(self):
        d = self.fh / ".cache/zazu-enlaces"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []

    def test_enlace_a_una_foto_con_ubicacion_la_quita(self):
        """El enlace público de una foto conservaba su EXIF con la ubicación: quien lo recibe podía saber dónde se hizo."""
        if not (HAY_PIL and FFMPEG):
            self.skipTest("hacen falta Pillow y ffmpeg")
        from PIL import Image
        con, sin = jpeg((40.4168, -3.7038)), jpeg()
        self.poner("Ubic/con_gps.jpg", con)
        self.poner("Ubic/sin_gps.jpg", sin)
        self.sync()
        gps_de = lambda c: Image.open(io.BytesIO(c)).getexif().get_ifd(0x8825)
        self.assertTrue(gps_de(con))
        # sin ubicación: se comparte tal cual
        st, d = self.post("/api/nube/enlace", {"path": "Ubic/sin_gps.jpg"})
        self.assertEqual((st, d["gps"], d["sin_gps"]), (200, False, False))
        type(self).tokens.append(d["token"])
        self.assertEqual(self.pub("GET", f"/c/{d['token']}")[2], sin)
        # con ubicación: por defecto se sirve una copia sin ella
        antes = self.copias()
        st, d = self.post("/api/nube/enlace", {"path": "Ubic/con_gps.jpg"})
        self.assertEqual((st, d["gps"], d["sin_gps"]), (200, True, True))
        tok = d["token"]
        type(self).tokens.append(tok)
        nueva, = set(self.copias()) - set(antes)
        self.assertRegex(nueva, r"^[0-9a-f]{16}\.jpg$")
        st, h, c = self.pub("GET", f"/c/{tok}")
        self.assertEqual((st, h["content-type"], h["content-disposition"]), (200, "image/jpeg", "inline; filename*=UTF-8''con_gps.jpg"))
        self.assertEqual(gps_de(c), {})   # sin GPS en el archivo que se baja
        self.assertEqual(Image.open(io.BytesIO(c)).size, (8, 8))
        self.assertEqual((self.compartido / "Ubic/con_gps.jpg").read_bytes(), con)   # el original no se toca
        self.assertEqual(self.pub("GET", f"/c/{tok}", cab={"Range": "bytes=0-9"})[2], c[:10])   # y tramos, como siempre
        self.assertEqual(self.pub("HEAD", f"/c/{tok}")[1]["content-length"], str(len(c)))
        st, h, e = self.crudo("GET", "/api/nube/enlaces?path=Ubic/con_gps.jpg")
        self.assertNotIn(b"zazu-enlaces", e)   # el nombre de la copia no sale de aquí
        # pedir el original tal cual
        st, d = self.post("/api/nube/enlace", {"path": "Ubic/con_gps.jpg", "sin_gps": False})
        self.assertEqual((st, d["gps"], d["sin_gps"]), (200, True, False))
        type(self).tokens.append(d["token"])
        self.assertEqual(self.pub("GET", f"/c/{d['token']}")[2], con)
        # sin la copia, el enlace NO sirve el original: nunca se comparte creyendo que no lleva ubicación
        for f in (self.fh / ".cache/zazu-enlaces").iterdir():
            f.unlink()
        self.assertEqual(self.pub("GET", f"/c/{tok}")[0], 404)
        # revocar borra la copia
        antes = self.copias()
        st, d = self.post("/api/nube/enlace", {"path": "Ubic/con_gps.jpg"})
        otra, = set(self.copias()) - set(antes)
        self.assertEqual(self.post("/api/nube/enlace/revocar", {"token": d["token"]})[0], 200)
        self.assertEqual(self.copias(), antes)
        self.assertNotIn(otra, self.copias())
        # con clave y ubicación: las dos cosas
        st, d = self.post("/api/nube/enlace", {"path": "Ubic/con_gps.jpg", "clave": "seis-letras"})
        self.assertEqual((st, d["sin_gps"]), (200, True))
        type(self).tokens.append(d["token"])
        self.assertIn(b'type="password"', self.pub("GET", f"/c/{d['token']}")[2])

    def test_enlace_a_un_video_con_ubicacion_la_quita(self):
        import nube_geo
        if not (FFMPEG and nube_geo._ffprobe()):
            self.skipTest("hacen falta ffmpeg y ffprobe")
        video_con_ubicacion(self.compartido / "Ubic/v.mp4", (41.3900, 2.1700))
        self.sync()
        st, d = self.post("/api/nube/enlace", {"path": "Ubic/v.mp4"})
        self.assertEqual((st, d["gps"], d["sin_gps"]), (200, True, True))
        type(self).tokens.append(d["token"])
        st, h, c = self.pub("GET", f"/c/{d['token']}")
        self.assertEqual((st, h["content-type"], h["content-disposition"].split(";")[0]), (200, "video/mp4", "inline"))
        copia = self.dir / "copia.mp4"
        copia.write_bytes(c)
        self.assertIsNone(nube_geo.gps_de(copia))   # la copia no lleva ubicación...
        self.assertIsNotNone(nube_geo.gps_de(self.compartido / "Ubic/v.mp4"))   # ...y el original sí (no se toca)
        self.assertIsNotNone(subprocess.run([str(nube_geo._ffprobe()), "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(copia)],
                                            capture_output=True, text=True).stdout.strip())   # y sigue siendo un vídeo
        self.assertEqual(self.pub("GET", f"/c/{d['token']}", cab={"Range": "bytes=0-99"})[0], 206)

    def test_si_no_se_puede_quitar_la_ubicacion_no_se_crea_el_enlace(self):
        import server
        antes = self.copias()
        with mock.patch.object(server, "_FFMPEG_NUEVO", None), self.assertRaises(A.Fallo) as cm:   # un HEIC sin el ffmpeg que junta sus teselas
            server._sin_gps(Path("IMG_20240101_100000.heic"))
        self.assertEqual(cm.exception.code, 400)
        with mock.patch.object(server, "_FFMPEG", "/no/existe/ffmpeg"), self.assertRaises(A.Fallo) as cm:
            server._sin_gps(self.compartido / IMG1)
        self.assertEqual(cm.exception.code, 500)
        self.assertEqual(self.copias(), antes)   # sin restos

    def test_zz_el_token_nunca_va_a_un_registro(self):
        self.assertGreater(len(self.tokens), 8)
        registros = ""
        for f in (self.dir / "hub.log", self.fh / ".local/state/hermes-hub/seguridad.log"):
            if f.exists():
                registros += f.read_text(errors="replace")
        for t in self.tokens + [CADUCADO]:
            self.assertNotIn(t, registros)
        self.assertNotIn("Traceback", registros)


class NubePersistencia(NubeBase):
    def reiniciar(self):
        cls = type(self)
        cls.hub.terminate()
        cls.hub.wait(10)
        cls.hub = cls.lanzar_hub(cls.hub_port, f"http://127.0.0.1:{cls.gw_port}", "hub2.log")
        esperar_puerto(cls.pub_port)

    def test_se_guarda_y_sobrevive_a_un_reinicio(self):
        self.post("/api/nube/fav", {"paths": [IMG1, IMG2], "on": True})
        aid = self.post("/api/nube/album", {"accion": "crear", "nombre": "Dura", "paths": [IMG1]})[1]["id"]
        tok = self.enlace(IMG3, horas=5, clave="persistente")
        est = self.fh / ".local/state/zazu-nube/nube.json"
        self.assertEqual(stat.S_IMODE(est.stat().st_mode), 0o600)   # lleva enlaces secretos: nadie más lo lee
        self.assertEqual(stat.S_IMODE(est.parent.stat().st_mode), 0o700)
        self.assertNotIn("persistente", est.read_text())   # la clave se guarda con hash, nunca en claro
        self.assertEqual([p.name for p in est.parent.iterdir()], ["nube.json"])   # sin restos del guardado atómico
        self.reiniciar()
        self.assertEqual(sorted(self.rutas(self.medios(fav="1"))), sorted([IMG1, IMG2]))
        al, = self.albumes()
        self.assertEqual((al["id"], al["nombre"], al["n"]), (aid, "Dura", 1))
        it, = [e for e in self.pedir("GET", "/api/nube/enlaces")[1]["items"] if e["token"] == tok]
        self.assertEqual((it["path"], it["clave"]), (IMG3, True))
        self.assertIn(b'type="password"', self.pub("GET", f"/c/{tok}")[2])   # sigue pidiendo su clave
        self.assertEqual(self.pub("GET", f"/c/{CADUCADO}")[0], 404)
        # un estado estropeado no tumba nada ni se pisa: se aparta y se empieza de cero
        est.write_text("{esto no es json")
        self.reiniciar()
        self.assertEqual(self.pedir("GET", "/api/nube")[1]["favoritos"], 0)
        self.assertEqual(self.albumes(), [])
        self.assertTrue((est.parent / "nube.json.estropeado").exists())
        self.assertEqual((est.parent / "nube.json.estropeado").read_text(), "{esto no es json")
        self.assertEqual(self.post("/api/nube/fav", {"paths": [IMG1], "on": True})[0], 200)
        self.assertEqual(json.loads(est.read_text())["fav"], [IMG1])


def jpeg(gps=None):
    """Un JPEG de verdad (8x8) con su ubicación (lat, lon) en el EXIF si se da: lo que lee el índice del mapa."""
    from PIL import Image
    ex = Image.Exif()
    if gps:
        dms = lambda x: (float(int(abs(x))), float(int(abs(x) % 1 * 60)), abs(x) % 1 * 60 % 1 * 60)
        ex[0x8825] = {1: "N" if gps[0] >= 0 else "S", 2: dms(gps[0]), 3: "E" if gps[1] >= 0 else "W", 4: dms(gps[1])}
    b = io.BytesIO()
    Image.new("RGB", (8, 8), "navy").save(b, "JPEG", exif=ex)
    return b.getvalue()


def video_con_ubicacion(ruta, gps):
    """Un MP4 de 0,2 s con la etiqueta de ubicación (ISO 6709) que ponen Android e iPhone."""
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=0.2:r=5", "-c:v", "mpeg4",
                        "-metadata", f"location={gps[0]:+08.4f}{gps[1]:+09.4f}/", str(ruta)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr


class NubeMapaBase(NubeBase):
    """Un Hub con un Compartido que, además, tiene fotos con GPS de verdad (JPEG con EXIF) y, si hay ffmpeg y ffprobe, un vídeo con ubicación.
    Tres con GPS que NO deben entrar en el mapa (una oculta, otra en una carpeta reservada y un acceso directo a una de fuera) y una foto de verdad sin GPS."""
    MADRID, TOLEDO, BARNA, SYDNEY = (40.4168, -3.7038), (39.8628, -4.0273), (41.3874, 2.1686), (-33.8688, 151.2093)
    FIJI_E, FIJI_O = (-17.75, 179.95), (-17.75, -179.95)   # a cada lado del antimeridiano
    SANTIAGO = (42.8782, -8.5448)
    M1, M2, M3 = "Mapa/Madrid/IMG_20240110_100000.jpg", "Mapa/Madrid/IMG_20240111_100000.jpg", "Mapa/Madrid/IMG_20240112_100000.jpg"
    TOL, B1, S1 = "Mapa/Toledo/IMG_20230801_090000.jpg", "Mapa/Barcelona/IMG_20230601_100000.jpg", "Mapa/Sydney/IMG_20220101_100000.jpg"
    F1, F2 = "Mapa/Fiji/IMG_20210101_100000.jpg", "Mapa/Fiji/IMG_20210102_100000.jpg"
    V1 = "Mapa/Barcelona/VID_20230602_100000.mp4"

    @classmethod
    def setUpClass(cls):
        if not HAY_PIL:
            raise unittest.SkipTest("hacen falta Pillow y el python3 del sistema (no el .venv)")
        super().setUpClass()
        fotos = {cls.M1: cls.MADRID, cls.M2: cls.MADRID, cls.M3: (40.4268, -3.7138), cls.TOL: cls.TOLEDO, cls.B1: cls.BARNA, cls.S1: cls.SYDNEY,
                 cls.F1: cls.FIJI_E, cls.F2: cls.FIJI_O}
        for rel, gps in fotos.items():
            cls.poner(rel, jpeg(gps))
        cls.con_gps = len(fotos)
        import nube_geo
        cls.hay_video = bool(FFMPEG and nube_geo._ffprobe())
        if cls.hay_video:
            video_con_ubicacion(cls.compartido / cls.V1, (41.3900, 2.1700))
            cls.con_gps += 1
        cls.poner("Mapa/sin_gps.jpg", jpeg())
        cls.poner("Mapa/.oculta.jpg", jpeg(cls.SANTIAGO))
        cls.poner("Mapa/.stversions/IMG_20240101_000000.jpg", jpeg(cls.SANTIAGO))
        (cls.fh / "fuera_gps.jpg").write_bytes(jpeg(cls.SANTIAGO))
        os.symlink(cls.fh / "fuera_gps.jpg", cls.compartido / "Mapa/atajo_gps.jpg")

    def mapa(self, z=3, **caja):
        st, d = self.pedir("GET", "/api/nube/mapa?" + urllib.parse.urlencode({"z": z, **caja}))
        self.assertEqual(st, 200, d)
        return d

    def hasta(self, cond, segundos=20, **p):
        """El mapa en cuanto cumple cond: el índice del GPS lo hace el Hub en segundo plano."""
        fin = time.time() + segundos
        while True:
            d = self.mapa(**p)
            if cond(d):
                return d
            if time.time() > fin:
                self.fail(f"el mapa no llegó al estado esperado: {({k: v for k, v in d.items() if k != 'puntos'})} con {len(d['puntos'])} celdas")
            time.sleep(0.2)

    def listo(self, con=None, **p):
        """El mapa con el índice ya hecho (y con `con` medios con GPS, si se dice)."""
        return self.hasta(lambda d: not d["indexando"] and (con is None or d["conGps"] == con), **p)

    @staticmethod
    def rutas_de(d):
        return [p["path"] for p in d["puntos"]]


class NubeMapa(NubeMapaBase):
    def test_permisos(self):
        for r in ("/api/nube/mapa?z=3", "/api/nube/mapa?z=99", "/api/nube/medios?bbox=0,0,1,1", "/api/nube/medios?bbox=malo"):
            self.assertEqual(self.pub("GET", r)[0], 401, r)   # sin sesión
            self.assertEqual(self.pub("GET", r, cab={"Cookie": f"hub_s={self.galleta_invitada}"})[0], 403, r)   # una invitada no es Fran (ni para decirle que el recuadro está mal)
            self.assertEqual(self.pedir("GET", r, cookie=self.galleta_invitada)[0], 403, r)
        st, h, d = self.pub("GET", "/api/nube/mapa?z=3", cab={"Cookie": f"hub_s={self.galleta_admin}"})   # Fran con su sesión, también por el puerto público
        self.assertEqual(st, 200)
        self.assertIn("puntos", json.loads(d))

    def test_celdas_por_zoom(self):
        d = self.listo(con=self.con_gps, z=18)
        self.assertEqual(set(d), {"puntos", "conGps", "sinGps", "indexando", "progreso"})
        self.assertEqual((d["indexando"], d["progreso"]), (False, 1))
        self.assertGreaterEqual(d["sinGps"], 2)   # la foto sin ubicación y los JPEG estropeados de las demás pruebas también se leyeron
        v = int(self.hay_video)
        fino = d["puntos"]
        self.assertEqual(len(fino), 7 + v)   # a zoom 18 solo se juntan las dos de Madrid que están en el mismo punto
        self.assertEqual(sum(p["n"] for p in fino), self.con_gps)
        for p in fino:
            self.assertEqual(set(p), {"lat", "lon", "n", "path", "kind", "caja"})
            self.assertTrue((self.compartido / p["path"]).is_file(), p)   # la portada existe y es relativa a Compartido
        mad = fino[0]   # la más llena primero
        self.assertEqual((mad["n"], mad["kind"], mad["path"]), (2, "image", self.M2))   # de portada, la más nueva de las dos
        self.assertAlmostEqual(mad["lat"], self.MADRID[0], 4)
        self.assertAlmostEqual(mad["lon"], self.MADRID[1], 4)
        medio = self.mapa(z=3)["puntos"]   # a zoom 3, Madrid con Toledo y Barcelona con su vídeo
        self.assertEqual([p["n"] for p in medio], [4, 2, 1, 1, 1] if v else [4, 1, 1, 1, 1])
        self.assertEqual(medio[0]["path"], self.M3)   # la portada es la más nueva por su fecha real (la del nombre)
        self.assertAlmostEqual(medio[0]["lat"], 40.2808, 3)   # el centro de lo que agrupa
        self.assertAlmostEqual(medio[0]["lon"], -3.7872, 3)
        self.assertEqual([round(x, 3) for x in medio[0]["caja"]], [39.863, -4.027, 40.427, -3.704])   # [sur, oeste, norte, este] de lo que agrupa
        if v:
            self.assertEqual((medio[1]["kind"], medio[1]["path"]), ("video", self.V1))
        mundo = self.mapa(z=0)["puntos"]
        self.assertEqual(sum(p["n"] for p in mundo), self.con_gps)   # a cualquier zoom la suma es la misma
        self.assertLess(len(mundo), len(medio))
        self.assertLess(len(medio), len(fino))
        self.assertEqual(self.mapa(z=18, s=-90, w=-180, n=90, e=180)["puntos"], fino)   # sin recuadro = el mundo entero
        self.assertEqual(self.mapa(z=18)["puntos"], fino)
        self.assertEqual(self.mapa(z="3.4")["puntos"], medio)   # el zoom se redondea

    def test_recuadro_del_mapa(self):
        self.listo(con=self.con_gps)
        d = self.mapa(z=18, s=39, w=-5, n=41, e=-3)   # Madrid y Toledo
        self.assertEqual(sorted(p["n"] for p in d["puntos"]), [1, 1, 2])
        self.assertEqual(d["conGps"], self.con_gps)   # los números de arriba son los de todo el índice, no los del recuadro
        self.assertEqual(self.mapa(z=18, s=-5, w=-30, n=5, e=-25)["puntos"], [])   # en medio del Atlántico no hay nada
        d = self.mapa(z=18, s=-20, w=170, n=-15, e=-170)   # w mayor que e: cruza el antimeridiano y trae las dos de Fiji
        self.assertEqual(sorted(self.rutas_de(d)), [self.F1, self.F2])
        self.assertEqual(self.mapa(z=18, s=-20, w=-170, n=-15, e=170)["puntos"], [])   # el otro lado del mundo no las tiene
        self.assertEqual(sorted(self.rutas_de(self.mapa(z=18, s=-15, w=170, n=-20, e=-170))), [self.F1, self.F2])   # s y n al revés valen lo mismo

    def test_la_caja_de_cada_celda_da_justo_sus_medios(self):
        """Lo que la web hace al pulsar una celda: pedir /medios con su caja trae exactamente los n medios que se ven en ella."""
        self.listo(con=self.con_gps)
        for z in (0, 3, 18):
            for p in self.mapa(z=z)["puntos"]:
                d = self.medios(bbox=",".join(map(str, p["caja"])), n=200)
                self.assertEqual(d["total"], p["n"], (z, p))
                self.assertIn(p["path"], self.rutas(d))

    def test_bbox_en_medios(self):
        self.listo(con=self.con_gps)
        centro = [self.M1, self.M2, self.M3, self.TOL]
        d = self.medios(bbox="39,-5,41,-3", n=200)   # s,w,n,e: Madrid y Toledo
        self.assertEqual((sorted(self.rutas(d)), d["total"]), (sorted(centro), 4))
        self.assertTrue(all(isinstance(i["fav"], bool) and i["kind"] == "image" for i in d["items"]))
        self.assertEqual(self.rutas(self.medios(bbox="39,-5,41,-3", n=200)), [self.M3, self.M2, self.M1, self.TOL])   # más nuevas primero, como siempre
        self.assertEqual(self.rutas(self.medios(bbox="39,-5,41,-3", orden="antiguas", n=200)), [self.TOL, self.M1, self.M2, self.M3])
        pag = self.medios(bbox="39,-5,41,-3", n=2, desde=2)
        self.assertEqual((self.rutas(pag), pag["total"]), ([self.M1, self.TOL], 4))
        # se combina con el resto de filtros
        self.assertEqual(self.medios(bbox="39,-5,41,-3", tipo="video")["total"], 0)
        self.assertEqual(self.rutas(self.medios(bbox="39,-5,41,-3", en="toledo")), [self.TOL])
        self.assertEqual(self.rutas(self.medios(bbox="39,-5,41,-3", q="20240111")), [self.M2])
        self.assertIn(self.rutas(self.medios(bbox="39,-5,41,-3", en="madrid", orden="tamano", n=1))[0], (self.M1, self.M2, self.M3))
        self.post("/api/nube/fav", {"paths": [self.M2, self.S1], "on": True})
        try:
            self.assertEqual(self.rutas(self.medios(bbox="39,-5,41,-3", fav="1")), [self.M2])   # (la de Sydney es favorita pero está fuera del recuadro)
        finally:
            self.post("/api/nube/fav", {"paths": [self.M2, self.S1], "on": False})
        # el mundo entero son los medios con GPS (los demás, sin ubicación, no salen); sin recuadro o con él vacío, no se filtra
        self.assertEqual(self.medios(bbox="-90,-180,90,180")["total"], self.con_gps)
        self.assertEqual(self.medios(bbox="")["total"], self.medios()["total"])
        self.assertGreater(self.medios()["total"], self.con_gps)
        self.assertEqual(sorted(self.rutas(self.medios(bbox="-20,170,-15,-170"))), [self.F1, self.F2])   # antimeridiano
        self.assertEqual(self.medios(bbox="-20,-170,-15,170")["total"], 0)
        if self.hay_video:
            self.assertEqual(self.rutas(self.medios(bbox="41,2,42,3", tipo="video")), [self.V1])
            self.assertEqual(self.rutas(self.medios(bbox="41,2,42,3", tipo="image")), [self.B1])

    def test_validacion(self):
        def mapa(**p):
            return self.pedir("GET", "/api/nube/mapa?" + urllib.parse.urlencode(p))

        mundo = {"s": -90, "w": -180, "n": 90, "e": 180}
        for p in ({}, {"z": ""}, {"z": "x"}, {"z": "nan"}, {"z": "inf"}, {"z": -1}, {"z": 18.5}, {"z": 19}, {"z": 99}, {"z": "3,5"}):   # el zoom va de 0 a 18
            st, d = mapa(**p)
            self.assertEqual(st, 400, p)
            self.assertIn("zoom", d["error"])
        for k, v in (("s", "abc"), ("s", -90.5), ("n", 91), ("w", -180.5), ("e", 181), ("s", "nan"), ("w", "inf"), ("n", "-inf"), ("e", "1e999"), ("s", ""), ("w", " ")):
            st, d = mapa(z=3, **{**mundo, k: v})
            self.assertEqual(st, 400, (k, v))
            self.assertIn("recuadro", d["error"])
        for quitar in "swne":   # o está entero o no está
            st, d = mapa(z=3, **{k: v for k, v in mundo.items() if k != quitar})
            self.assertEqual(st, 400, quitar)
        for p in ({"z": 0}, {"z": 18}, {"z": "3.6"}, {"z": 3, **mundo}, {"z": 3, "s": 90, "w": 180, "n": -90, "e": -180}, {"z": 3, "s": 0, "w": 0, "n": 0, "e": 0},
                  {"z": 3, "s": 10, "w": 170, "n": 20, "e": -170}, {"z": " 5 "}, {"z": 3, "s": "-0", "w": "1e1", "n": "+5.5", "e": 20}):
            self.assertEqual(mapa(**p)[0], 200, p)
        for malo in ("1,2,3", "1,2,3,4,5", "a,b,c,d", "91,0,0,0", "0,0,-91,0", "0,0,0,181", "0,-181,0,0", "nan,0,0,0", "0,inf,0,0", ",,,", "1,2,3,", "1;2;3;4"):
            st, d = self.pedir("GET", "/api/nube/medios?" + urllib.parse.urlencode({"bbox": malo}))
            self.assertEqual(st, 400, malo)
            self.assertIn("recuadro", d["error"])
        for bien in ("0,0,0,0", "-90,-180,90,180", "10,170,20,-170", "20,10,10,20", " 1 , 2 , 3 , 4 "):
            self.assertEqual(self.pedir("GET", "/api/nube/medios?" + urllib.parse.urlencode({"bbox": bien}))[0], 200, bien)

    def test_resumen_con_el_estado_del_mapa(self):
        d = self.listo(con=self.con_gps)
        geo = self.pedir("GET", "/api/nube")[1]["geo"]
        self.assertEqual(set(geo), {"conGps", "sinGps", "indexando", "progreso"})
        self.assertEqual(geo, {k: d[k] for k in geo})
        self.assertEqual((geo["conGps"], geo["indexando"], geo["progreso"]), (self.con_gps, False, 1))

    def test_lo_oculto_los_atajos_y_lo_roto_no_entran(self):
        d = self.listo(con=self.con_gps, z=18)
        self.assertEqual(self.medios(bbox="42,-9,43,-8")["total"], 0)   # las tres de Santiago (oculta, reservada y acceso directo a una de fuera)
        self.assertEqual(self.mapa(z=18, s=42, w=-9, n=43, e=-8)["puntos"], [])
        self.assertTrue(all(not any(x.startswith(".") or x == "atajo_gps.jpg" for x in p["path"].split("/")) for p in d["puntos"]))

    def test_sin_errores_en_el_registro(self):
        self.listo(con=self.con_gps)
        log = (self.dir / "hub.log").read_text(errors="replace")
        for malo in ("Traceback", "nube_geo:", "error GET"):
            self.assertNotIn(malo, log)


class NubeMapaVivo(NubeMapaBase):
    """La vida del índice del GPS en un Hub, en orden: no arranca solo, arranca al abrir Mi nube, se entera de los cambios y sobrevive a un reinicio."""
    def geo(self):
        return self.fh / ".local/state/zazu-nube/geo.json"

    def reiniciar(self):
        cls = type(self)
        cls.hub.terminate()
        cls.hub.wait(10)
        cls.hub = cls.lanzar_hub(cls.hub_port, f"http://127.0.0.1:{cls.gw_port}", "hub2.log")
        esperar_puerto(cls.pub_port)

    def test_1_no_arranca_si_nadie_lo_pide(self):
        self.assertFalse(self.geo().exists())
        st, h, b = self.crudo("POST", "/api/upload?path=Mapa&name=nota.txt", {"Content-Type": "application/octet-stream"}, b"hola")
        self.assertEqual(st, 200, b)
        self.sync()
        time.sleep(1)
        self.assertFalse(self.geo().exists())   # subir o crear una carpeta no lo pone en marcha: el primer recorrido lo hará al abrir Mi nube

    def test_2_arranca_al_abrir_mi_nube(self):
        geo = self.pedir("GET", "/api/nube")[1]["geo"]   # el resumen que carga la pantalla de Mi nube
        self.assertEqual(set(geo), {"conGps", "sinGps", "indexando", "progreso"})
        fin = time.time() + 20
        while not self.geo().exists() and time.time() < fin:   # sin haber pedido el mapa todavía: lo puso en marcha el resumen
            time.sleep(0.1)
        self.assertTrue(self.geo().exists())
        self.listo(con=self.con_gps)
        self.assertEqual(self.pedir("GET", "/api/nube")[1]["geo"]["conGps"], self.con_gps)

    def test_3_cambios_en_vivo(self):
        """Subir, mover, tirar y restaurar avisan al mapa: se ve sin esperar al minuto del reescaneo."""
        self.listo(con=self.con_gps)
        lisboa, nombre = (38.7223, -9.1393), "IMG_20250101_120000.jpg"
        rel = f"Mapa/{nombre}"
        st, h, b = self.crudo("POST", f"/api/upload?path=Mapa&name={nombre}", {"Content-Type": "application/octet-stream"}, jpeg(lisboa))
        self.assertEqual(st, 200, b)
        d = self.hasta(lambda d: rel in self.rutas_de(d) and d["conGps"] == self.con_gps + 1, z=18)
        p, = [p for p in d["puntos"] if p["path"] == rel]
        self.assertEqual((p["n"], p["kind"]), (1, "image"))
        self.assertAlmostEqual(p["lat"], lisboa[0], 4)
        self.assertAlmostEqual(p["lon"], lisboa[1], 4)
        self.assertEqual(self.rutas(self.medios(bbox="38,-10,39,-9")), [rel])   # y el filtro del listado también la ve
        st, r = self.post("/api/mover", {"path": rel, "destino": "Mapa/Madrid"})   # moverla: el mapa la sigue
        self.assertEqual(st, 200, r)
        nuevo = r["path"]
        self.assertEqual(nuevo, f"Mapa/Madrid/{nombre}")
        d = self.hasta(lambda d: nuevo in self.rutas_de(d) and d["conGps"] == self.con_gps + 1 and not d["indexando"], z=18)
        self.assertNotIn(rel, self.rutas_de(d))
        st, r = self.post("/api/papelera", {"path": nuevo})   # tirarla: desaparece
        self.assertEqual(st, 200, r)
        d = self.hasta(lambda d: nuevo not in self.rutas_de(d) and d["conGps"] == self.con_gps and not d["indexando"], z=18)
        self.assertEqual(self.medios(bbox="38,-10,39,-9")["total"], 0)
        st, r = self.post("/api/restaurar", {"id": r["id"]})   # restaurarla: vuelve
        self.assertEqual((st, r["path"]), (200, nuevo))
        self.hasta(lambda d: nuevo in self.rutas_de(d) and d["conGps"] == self.con_gps + 1 and not d["indexando"], z=18)
        self.post("/api/papelera", {"path": nuevo})   # y se deja como estaba
        self.listo(con=self.con_gps)
        fin = time.time() + 20
        while nombre in self.geo().read_text() and time.time() < fin:   # (también en disco: lo guarda al acabar el recorrido)
            time.sleep(0.1)
        self.assertNotIn(nombre, self.geo().read_text())

    def test_4_reinicio(self):
        self.listo(con=self.con_gps)
        geo = self.geo()
        self.assertEqual(stat.S_IMODE(geo.stat().st_mode), 0o600)   # lleva dónde se hizo cada foto: nadie más lo lee
        self.assertEqual(stat.S_IMODE(geo.parent.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in geo.parent.iterdir()), ["geo.json", "nube.json"])   # sin restos del guardado atómico
        self.reiniciar()
        d = self.mapa(z=18)   # lo primero que se pregunta tras reiniciar, sin esperar a nada
        self.assertEqual((d["conGps"], d["indexando"]), (self.con_gps, False))   # lo leyó del disco: no empieza de cero
        self.assertEqual(sum(p["n"] for p in d["puntos"]), self.con_gps)
        geo.write_text("{esto no es json")   # estropeado: se rehace sin tumbar nada
        self.reiniciar()
        self.listo(con=self.con_gps)
        self.assertEqual(json.loads(geo.read_text())["v"], 1)

    def test_5_registro_limpio(self):
        for nombre in ("hub.log", "hub2.log"):
            log = (self.dir / nombre).read_text(errors="replace")
            for malo in ("Traceback", "nube_geo:", "error GET"):
                self.assertNotIn(malo, log, nombre)


class NubeGeoModulo(unittest.TestCase):
    """nube_geo.py en lo que toca al Hub (avisar y dónde guarda), sin Hub y con un estado propio bajo /tmp: nunca el de verdad."""
    def setUp(self):
        import nube_geo as G
        self.G = G
        self.dir = Path(tempfile.mkdtemp(prefix="nube-geo-mod-"))
        if not os.path.realpath(self.dir).startswith("/tmp/"):
            raise SystemExit("las pruebas solo corren bajo /tmp")
        self.antes = G.ESTADO, G._INDICES
        G.ESTADO, G._INDICES = self.dir / "estado/geo.json", {}
        (self.dir / "c").mkdir()
        self.root = A.Raiz("c", self.dir / "c")

    def tearDown(self):
        for ix in self.G._INDICES.values():
            ix.detener()
        self.G.ESTADO, self.G._INDICES = self.antes
        shutil.rmtree(self.dir, ignore_errors=True)

    def hasta(self, con):
        fin = time.time() + 20
        while time.time() < fin:
            e = self.G.estado(self.root)
            if e["conGps"] == con and not e["indexando"]:
                return e
            time.sleep(0.1)
        self.fail(f"el índice no llegó a {con}: {self.G.estado(self.root)}")

    @unittest.skipUnless(HAY_PIL, "hacen falta Pillow y el python3 del sistema (no el .venv)")
    def test_avisar_solo_si_el_mapa_ya_corre(self):
        G = self.G
        (self.dir / "c/IMG_20240101_100000.jpg").write_bytes(jpeg((40.4168, -3.7038)))
        G.avisar(self.root)   # nadie ha pedido el mapa: ni se crea el índice, ni su hilo, ni su carpeta
        self.assertEqual(G._INDICES, {})
        self.assertFalse((self.dir / "estado").exists())
        G.arrancar(self.root)
        self.hasta(1)
        (self.dir / "c/IMG_20240102_100000.jpg").write_bytes(jpeg((41.3874, 2.1686)))
        G.avisar(self.root)   # ya corre: recorre ya (si no, tardaría hasta 5 minutos)
        self.hasta(2)

    @unittest.skipUnless(HAY_PIL, "hacen falta Pillow y el python3 del sistema (no el .venv)")
    def test_el_estado_se_guarda_en_privado(self):
        G = self.G
        (self.dir / "c/IMG_20240101_100000.jpg").write_bytes(jpeg((40.4168, -3.7038)))
        G.arrancar(self.root)
        self.hasta(1)
        geo = G.ESTADO
        self.assertEqual(stat.S_IMODE(geo.stat().st_mode), 0o600)   # lleva dónde se hizo cada foto
        self.assertEqual(stat.S_IMODE(geo.parent.stat().st_mode), 0o700)   # y su carpeta es la de nube.json: privada también si la crea el mapa primero
        self.assertEqual([p.name for p in geo.parent.iterdir()], ["geo.json"])

    def test_donde_guarda(self):
        def ruta(**env):
            e = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
            e.update(env)
            r = subprocess.run([sys.executable, "-c", "import nube_geo; print(nube_geo.ESTADO)"], env=e, cwd=str(REPO), capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()

        self.assertEqual(ruta(HOME="/tmp/nube-casa"), "/tmp/nube-casa/.local/state/zazu-nube/geo.json")
        self.assertEqual(ruta(HOME="/tmp/nube-casa", HUB_NUBE="/tmp/otro/nube.json"), "/tmp/otro/geo.json")   # junto a nube.json: quien aparta uno aparta los dos
        self.assertEqual(ruta(HOME="/tmp/nube-casa", HUB_NUBE="/tmp/otro/nube.json", HUB_NUBE_GEO="/tmp/aparte/g.json"), "/tmp/aparte/g.json")


class NubeModulo(unittest.TestCase):
    """nube.py solo, sin Hub."""
    def setUp(self):
        import nube as N
        self.N = N
        self.dir = Path(tempfile.mkdtemp(prefix="nube-mod-"))
        if not os.path.realpath(self.dir).startswith("/tmp/"):
            raise SystemExit("las pruebas solo corren bajo /tmp")
        N.ESTADO, N._E = self.dir / "zazu-nube/nube.json", None
        N._FALLOS.clear()

    def tearDown(self):
        self.N._E = None
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_mover_rutas(self):
        N = self.N
        N.poner_fav(["a/b/uno.jpg", "a/b2/dos.jpg", "a/b", "c.jpg"], True)
        aid = N.album_nuevo("X", ["a/b/uno.jpg", "a/b/sub/tres.jpg", "z.jpg", "c.jpg"])
        tok, _ = N.crear_enlace("a/b/uno.jpg")
        N.mover_rutas("a/b", "q/b")
        self.assertEqual(sorted(N.favoritos()), ["a/b2/dos.jpg", "c.jpg", "q/b", "q/b/uno.jpg"])   # «a/b2» no empieza por «a/b/»
        self.assertEqual(N.album(aid)["items"], ["q/b/uno.jpg", "q/b/sub/tres.jpg", "z.jpg", "c.jpg"])
        self.assertEqual(N.enlace(tok)["path"], "q/b/uno.jpg")
        N.mover_rutas("z.jpg", "c.jpg")   # al juntarse dos, no se repite
        self.assertEqual(N.album(aid)["items"], ["q/b/uno.jpg", "q/b/sub/tres.jpg", "c.jpg"])
        N.mover_rutas("q/b", None)   # a la papelera: los enlaces se van, lo demás se queda
        self.assertIsNone(N.enlace(tok))
        self.assertIn("q/b/uno.jpg", N.favoritos())
        self.assertIn("q/b/uno.jpg", N.album(aid)["items"])

    def test_estado_en_disco(self):
        N = self.N
        N.poner_fav(["a.jpg"], True)
        self.assertEqual(json.loads(N.ESTADO.read_text())["fav"], ["a.jpg"])
        self.assertEqual(stat.S_IMODE(N.ESTADO.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(N.ESTADO.parent.stat().st_mode), 0o700)   # la carpeta que crea el Hub, también privada
        self.assertEqual([p.name for p in N.ESTADO.parent.iterdir()], ["nube.json"])   # sin restos del guardado atómico
        N._E = None   # como tras un reinicio
        self.assertEqual(N.favoritos(), {"a.jpg"})
        N.ESTADO.write_text('{"fav": 5}')   # JSON bueno pero con lo que no es
        N._E = None
        self.assertEqual(N.favoritos(), set())
        self.assertTrue(N.ESTADO.with_name("nube.json.estropeado").exists())
        # si no se puede guardar, la memoria vuelve a lo de disco en vez de quedarse con lo que no se guardó
        N.poner_fav(["b.jpg"], True)
        N.ESTADO.parent.chmod(0o500)
        try:
            if os.access(N.ESTADO.parent, os.W_OK):
                self.skipTest("se ejecuta como root: no se puede impedir escribir")
            with self.assertRaises(OSError):
                N.poner_fav(["c.jpg"], True)
        finally:
            N.ESTADO.parent.chmod(0o700)
        self.assertEqual(N.favoritos(), {"b.jpg"})

    def test_enlaces(self):
        N = self.N
        tok, caduca = N.crear_enlace("a.jpg", 99999, "pw")   # el tope es 30 días
        self.assertAlmostEqual(caduca, time.time() + 720 * 3600, delta=5)
        self.assertEqual(N.enlace(tok), {"path": "a.jpg", "caduca": caduca, "protegido": True, "copia": None})
        guardado = N.ESTADO.read_text()
        self.assertNotIn('"pw"', guardado)
        self.assertRegex(json.loads(guardado)["enlaces"][tok]["clave"], r"^[0-9a-f]{32}:[0-9a-f]{128}$")   # sal + scrypt
        self.assertTrue(N.clave_vale(tok, "pw"))
        for mala in ("", "PW", "pw ", None, 5, "p" * 100):
            self.assertFalse(N.clave_vale(tok, mala), mala)
        nfc, nfd = "contraseña", "contraseña"   # la misma palabra con la ñ de una pieza o con la tilde aparte
        t2, _ = N.crear_enlace("a.jpg", 1, nfc)
        self.assertTrue(N.clave_vale(t2, nfd) and N.clave_vale(t2, nfc))
        self.assertFalse(N.clave_vale("no-existe-" + "x" * 12, "pw"))
        sin, _ = N.crear_enlace("b.jpg")
        self.assertFalse(N.clave_vale(sin, ""))   # sin clave no hay clave que valga
        self.assertFalse(N.enlace(sin)["protegido"])
        N._estado()["enlaces"][tok]["caduca"] = int(time.time()) - 1   # caducado
        self.assertIsNone(N.enlace(tok))
        self.assertNotIn(tok, [e["token"] for e in N.enlaces_de()])
        for k in ("", "x", None, 5):
            self.assertIsNone(N.enlace(k))
        self.assertEqual(N.revocar_enlace(sin)["path"], "b.jpg")   # devuelve el registro (server.py borra con él la copia sin ubicación)
        self.assertIsNone(N.enlace(sin))
        self.assertIsNone(N.revocar_enlace(sin))   # otra vez: sin error
        con, _ = N.crear_enlace("g.jpg", 1, None, "0123456789abcdef.jpg")
        self.assertEqual(N.enlace(con)["copia"], "0123456789abcdef.jpg")
        self.assertEqual(N.revocar_enlace(con)["copia"], "0123456789abcdef.jpg")
        # los caducados hace más de un día se limpian al crear otro
        viejo, _ = N.crear_enlace("c.jpg")
        N._estado()["enlaces"][viejo]["caduca"] = int(time.time()) - 2 * 86400
        N.crear_enlace("d.jpg")
        self.assertNotIn(viejo, N._estado()["enlaces"])
        # tope de enlaces activos
        for i in range(N.MAX_ENLACES):
            N._estado()["enlaces"][f"t{i}"] = {"path": "x", "creado": 1, "caduca": int(time.time()) + 100, "visitas": 0}
        with self.assertRaises(N.A.Fallo):
            N.crear_enlace("e.jpg")

    def test_pase_e_intentos(self):
        N = self.N
        hasta = int(time.time()) + 60
        p = N.pase("tok", hasta)
        self.assertTrue(N.pase_vale("tok", p))
        self.assertFalse(N.pase_vale("otro", p))
        self.assertFalse(N.pase_vale("tok", N.pase("tok", int(time.time()) - 1)))   # caducado
        for malo in (None, "", "x", "1.2", p + "0", "é.é", "-5." + p.split(".")[1], p.replace(".", ".."),
                     "9" * 5000 + "." + "a" * 32, "9" * 13 + "." + p.split(".")[1]):   # miles de dígitos: int() lanzaba (límite de 4300) y cortaba la conexión
            self.assertFalse(N.pase_vale("tok", malo), malo[:20] if isinstance(malo, str) else malo)
        # el intento se apunta al PEDIRLO, no al fallar: así peticiones a la vez no esquivan el límite
        for i in range(4):
            self.assertEqual(N.clave_intento("t", "1.1.1.1"), 0, i)
        N.clave_acierto("t", "1.1.1.1")   # una acertó: ese intento no cuenta
        self.assertEqual(N.clave_intento("t", "1.1.1.1"), 0)
        self.assertEqual(N.clave_intento("t", "1.1.1.1"), 0)   # el quinto que cuenta
        self.assertGreater(N.clave_intento("t", "1.1.1.1"), 0)   # el sexto, no
        self.assertEqual(N.clave_intento("t", "2.2.2.2"), 0)   # otra IP
        self.assertEqual(N.clave_intento("otro", "1.1.1.1"), 0)   # otro enlace
        for i in range(24):
            self.assertEqual(N.clave_intento("t", f"9.9.9.{i}"), 0, i)
        self.assertGreater(N.clave_intento("t", "3.3.3.3"), 0)   # 30 en total
        N.clave_acierto("t", "2.2.2.2")
        self.assertEqual(N.clave_intento("t", "3.3.3.3"), 0)   # el acierto devolvió un hueco
        N.clave_acierto("nadie", "0.0.0.0")   # sin nada apuntado: no pasa nada

    def test_scrypt_a_la_vez_con_tope(self):
        """Cada scrypt reserva 16 MB: 100 claves a la vez eran 1,6 GB. Ahora, como mucho 4 a la vez."""
        N = self.N
        tok, _ = N.crear_enlace("a.jpg", 1, "una-clave")
        lock, activos, maximo, real = threading.Lock(), [0], [0], N._kdf

        def lenta(clave, sal):
            with lock:
                activos[0] += 1
                maximo[0] = max(maximo[0], activos[0])
            time.sleep(0.05)
            with lock:
                activos[0] -= 1
            return real(clave, sal)
        N._kdf = lenta
        try:
            with ThreadPoolExecutor(16) as ex:
                bien = list(ex.map(lambda _: N.clave_vale(tok, "una-clave"), range(32)))
        finally:
            N._kdf = real
        self.assertTrue(all(bien))
        self.assertLessEqual(maximo[0], 4)
        self.assertGreater(maximo[0], 1)   # (y sí van de varias en varias)

    def test_el_estado_se_guarda_a_disco_antes_del_cambio_de_nombre(self):
        N = self.N
        with mock.patch.object(N.os, "fsync") as f:
            N.poner_fav(["a.jpg"], True)
        self.assertTrue(f.called)   # sin fsync, tras un corte de luz podía quedar un nube.json vacío (y con él, todos los enlaces, favoritos y álbumes)

    def test_albumes(self):
        N, A_ = self.N, self.N.A
        i = N.album_nuevo("  Uno  ")
        self.assertEqual(N.album(i)["nombre"], "Uno")
        for nombre, codigo in (("uno", 409), ("UNO", 409), ("", 400), ("x" * 61, 400), (None, 400), (7, 400)):
            with self.assertRaises(A_.Fallo) as cm:
                N.album_nuevo(nombre)
            self.assertEqual(cm.exception.code, codigo, nombre)
        with self.assertRaises(A_.Fallo):
            N.album_cambiar("00000000", "borrar")
        with self.assertRaises(A_.Fallo):
            N.album_cambiar(i, "volar")
        N.album_cambiar(i, "añadir", paths=["a", "b", "a"])
        self.assertEqual(N.album(i)["items"], ["a", "b"])
        N.MAX_ALBUM = 3
        try:
            with self.assertRaises(A_.Fallo):
                N.album_cambiar(i, "añadir", paths=["c", "d"])
            self.assertEqual(N.album(i)["items"], ["a", "b"])   # no se aplicó
        finally:
            N.MAX_ALBUM = 20000
        N.album_cambiar(i, "quitar", paths=["a"])
        self.assertEqual(N.album(i)["items"], ["b"])
        self.assertEqual(N.albumes().keys(), {i})

    def test_zip_al_vuelo_con_archivos_que_cambian_o_un_cliente_que_se_va(self):
        """H.zip_nube con un manejador de pega, en un proceso aparte con casa falsa (server tiene estado global). El ZIP sale por trozos mientras se hace."""
        import subprocess, textwrap
        script = textwrap.dedent('''
            import errno, io, json, os, sys, zipfile
            from pathlib import Path
            sys.path.insert(0, %r)
            import server, nube as N
            c = Path(os.environ["HOME"]) / "Cerebro/40 Compartido/F"
            c.mkdir(parents=True)
            for n in ("a.jpg", "b.jpg", "c.jpg"):
                (c / n).write_bytes(os.urandom(3000))
            N.poner_fav(["F/a.jpg", "F/b.jpg", "F/c.jpg"], True)
            class Mano:
                close_connection = False
                def __init__(self, wfile=None): self.log, self.wfile = [], wfile or io.BytesIO()
                def fail(self, code, msg): self.log.append([code, msg])
                def send_response(self, code): self.log.append(code)
                def send_header(self, k, v): self.log.append([k, v])
                def end_headers(self): pass
                def _zip_enviar(self, *a): return server.H._zip_enviar(self, *a)
            def dechunk(b):
                out = b""
                while True:
                    n, _, b = b.partition(b"\\r\\n")
                    n = int(n, 16)
                    if n == 0:
                        return out, b == b"\\r\\n"   # (y el trozo final bien cerrado)
                    out, b = out + b[:n], b[n + 2:]
            def zipear(wfile=None):
                m = Mano(wfile)
                server.H.zip_nube(m, {"fav": "1"})
                return m
            def leer(m):
                datos, cerrado = dechunk(m.wfile.getvalue())
                z = zipfile.ZipFile(io.BytesIO(datos))
                return [sorted(z.namelist()), z.testzip(), cerrado]
            real, out = zipfile.ZipFile.write, {}
            m = zipear(); out["entero"] = [m.log[0], ["Transfer-Encoding", "chunked"] in m.log, leer(m), m.close_connection]
            def borra(self, filename, arcname=None, *a, **k):
                if str(filename).endswith("b.jpg"): os.unlink(filename)
                return real(self, filename, arcname, *a, **k)
            zipfile.ZipFile.write = borra
            m = zipear(); out["borrado"] = [leer(m), m.close_connection]
            (c / "b.jpg").write_bytes(os.urandom(3000)); zipfile.ZipFile.write = real
            os.chmod(c / "c.jpg", 0)
            m = zipear(); out["ilegible"] = [leer(m), os.geteuid() == 0]
            os.chmod(c / "c.jpg", 0o644)
            def eio(self, *a, **k): raise OSError(errno.EIO, "Input/output error")
            zipfile.ZipFile.write = eio
            m = zipear(); out["eio"] = [m.close_connection, m.wfile.getvalue().endswith(b"0\\r\\n\\r\\n")]   # un fallo de verdad: se corta SIN el trozo final
            zipfile.ZipFile.write = real
            # un cliente que se va: la primera escritura falla y el trabajo no sigue con el resto
            for i in range(5):
                (c / f"grande{i}.jpg").write_bytes(os.urandom(300000))
            N.poner_fav([f"F/grande{i}.jpg" for i in range(5)], True)
            llamadas = [0]
            def cuenta(self, *a, **k):
                llamadas[0] += 1
                return real(self, *a, **k)
            class Roto(io.BytesIO):
                def write(self, b): raise BrokenPipeError(errno.EPIPE, "Broken pipe")
            zipfile.ZipFile.write = cuenta
            m = zipear(Roto())
            zipfile.ZipFile.write = real
            out["se_fue"] = [llamadas[0], m.close_connection]
            out["restos"] = (Path(os.environ["HOME"]) / ".cache/zazu-zip").exists()
            print(json.dumps(out))
        ''' % str(REPO))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HUB_", "HERMES"))}
        env.update(HOME=str(self.dir / "casa"), HUB_NO_PUSH="1")
        r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120, cwd=str(REPO))
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["entero"], [200, True, [["a.jpg", "b.jpg", "c.jpg"], None, True], False])   # por trozos, ZIP bueno y cerrado
        self.assertEqual(out["borrado"], [[["a.jpg", "c.jpg"], None, True], False])   # lo borrado a mitad se omite y el ZIP sale entero
        if not out["ilegible"][1]:
            self.assertEqual(out["ilegible"][0], [["a.jpg", "b.jpg"], None, True])   # lo que el Hub no puede leer se omite
        self.assertEqual(out["eio"], [True, False])   # un fallo al leer que no es de los de arriba nunca se esconde: la descarga queda incompleta, no un ZIP que parece bueno
        self.assertLessEqual(out["se_fue"][0], 5)   # de los 8 favoritos, ni se intentan: se corta en la primera escritura que falla
        self.assertTrue(out["se_fue"][1])
        self.assertFalse(out["restos"])   # y no hay ningún fichero temporal

    def test_duplicados_unitario(self):
        N = self.N
        A_ = N.A
        raiz_dir = self.dir / "c"
        for rel, datos in (("uno/a.jpg", b"A" * 20000), ("dos/a (2).jpg", b"A" * 20000), ("dos/b.jpg", b"A" * 20000), ("tres/c.jpg", b"A" * 19999 + b"B"),
                           ("tres/d.jpg", b"s" * 100), ("tres/e.jpg", b"s" * 100), ("uno/.oculto.jpg", b"A" * 20000)):
            p = raiz_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(datos)
        os.utime(raiz_dir / "dos/b.jpg", (1000, 1000))   # la más antigua
        os.symlink(raiz_dir / "uno/a.jpg", raiz_dir / "uno/atajo.jpg")
        os.link(raiz_dir / "uno/a.jpg", raiz_dir / "uno/duro.jpg")
        raiz = A_.Raiz("c", raiz_dir)
        llamadas = []
        real = N._sha
        N._sha = lambda *a: (llamadas.append(a), real(*a))[1]
        try:
            grupos, vistos, usados = N._escanear(raiz, {})
            self.assertEqual(len(grupos), 1)   # c.jpg tiene el mismo tamaño pero no es igual; d y e son demasiado pequeños
            nombres = [i["name"] for i in grupos[0]["items"]]
            self.assertEqual(nombres[0], "b.jpg")   # no es «(2)» y es la más antigua: es la que se conserva
            self.assertEqual(nombres[-1], "a (2).jpg")   # la «copia» al final
            self.assertEqual(len(nombres), 3)   # a.jpg y duro.jpg son el mismo archivo con dos nombres: cuenta uno solo
            self.assertEqual(sum(n in nombres for n in ("a.jpg", "duro.jpg")), 1)
            self.assertEqual(grupos[0]["items"][0]["mtime"], 1000)
            self.assertEqual(vistos, 7)   # (el acceso directo y el oculto no se miran)
            n1 = len(llamadas)
            self.assertGreater(n1, 0)
            grupos2, _, _ = N._escanear(raiz, usados)   # con lo ya leído, no se lee nada más
            self.assertEqual(len(llamadas), n1)
            self.assertEqual(grupos2, grupos)
            (raiz_dir / "dos/b.jpg").write_bytes(b"A" * 20000)   # cambia (mtime) → se vuelve a leer
            N._escanear(raiz, usados)
            self.assertGreater(len(llamadas), n1)
        finally:
            N._sha = real
        self.assertEqual(N._ahorro(grupos), 20000 * 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
