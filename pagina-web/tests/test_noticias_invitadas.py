#!/usr/bin/env python3
"""Noticias de las invitadas (noticias_invitadas.py y /api/inv/noticias…): eligen países y temas y ven titulares de periódicos.
Todo con un RSS FALSO en un archivo local (HUB_NOTICIAS_INV_RSS sustituye a todas las fuentes y apaga las fotos): nunca se sale a internet.

    python3 -m unittest tests.test_noticias_invitadas -v      (TMPDIR bajo /tmp)"""
import json, os, sys, tempfile, unittest, urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
import noticias_invitadas as NI  # noqa: E402
import test_api  # noqa: E402


def hace(horas):
    return format_datetime(datetime.now(timezone.utc) - timedelta(hours=horas))


def rss(*items):
    cuerpo = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{f}</pubDate><description>{d}</description></item>" for t, l, f, d in items)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Falso</title>{cuerpo}</channel></rss>'


RSS = rss(
    ("Sube el precio del pan en todo el país", "https://ejemplo.com/pan", hace(1),
     "&lt;p&gt;Los panaderos lo explican.&lt;/p&gt; The post Sube el pan appeared first on Ejemplo."),
    ("&lt;b&gt;Gana&lt;/b&gt; el equipo local &amp; lo celebra", "https://ejemplo.com/equipo", hace(2),
     "&lt;script&gt;alert(1)&lt;/script&gt;La afición salió a la calle " + "muy contenta " * 40),
    ("Sube el precio del pan en todo el pais", "https://ejemplo.com/pan-2", hace(3), "Repetida casi igual: no debe salir dos veces."),
    ("Enlace peligroso", "javascript:alert(1)", hace(1), "No debe salir."),
    ("Noticia de hace diez días", "https://ejemplo.com/vieja", hace(240), "Ya no es noticia."),
    ("Abre un museo nuevo", "https://ejemplo.com/museo", hace(5), "Abre un museo nuevo"),
)


class Unidad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.rss = t / "falso.xml"
        self.rss.write_text(RSS, encoding="utf-8")
        os.environ.update(HUB_NOTICIAS_INV=str(t / "estado"), HUB_NOTICIAS_INV_RSS=str(self.rss))
        for d in (NI._CACHE, NI._FALLO, NI._EN_CURSO):
            d.clear()

    def tearDown(self):
        for k in ("HUB_NOTICIAS_INV", "HUB_NOTICIAS_INV_RSS"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_validar_y_selector_la_primera_vez(self):
        self.assertIsNone(NI.validar({}))
        self.assertIsNone(NI.validar({"paises": ["XX"], "temas": "mundo"}))
        self.assertEqual(NI.validar({"paises": ["VE", "ES", "XX", "ES"], "temas": ["salud", "mundo", "<b>"]}),
                         {"paises": ["ES", "VE"], "temas": ["mundo", "salud"], "elegido": True})   # solo el catálogo, en su orden
        d = NI.para(None, {"pais": "ve"})
        self.assertEqual((d["elegido"], d["paises"], d["temas"], d["apartados"]), (False, ["VE"], ["mundo"], []))   # su país ya marcado
        self.assertEqual(NI.para({"paises": ["ES"], "elegido": False}, {"pais": "JP"})["paises"], [])
        cat = NI.catalogo()
        self.assertIn({"clave": "ES", "nombre": "España"}, cat["paises"])
        self.assertEqual([t["nombre"] for t in cat["temas"]], ["Mundo", "IA y tecnología", "Deportes", "Economía", "Cultura y espectáculos", "Salud y ciencia"])
        for p in NI.PAISES.values():
            for _, url, _ in p["fuentes"]:
                self.assertTrue(url.startswith("https://"), url)
        for t in NI.TEMAS.values():
            for _, url, pais in t["fuentes"]:
                self.assertTrue(url.startswith("https://") and (pais is None or pais in NI.PAISES), url)

    def test_texto_limpio_sin_repetidos_y_cache_compartida(self):
        el = NI.validar({"paises": ["ES"], "temas": ["mundo"]})
        d = NI.para(el, {})
        self.assertEqual([a["titulo"] for a in d["apartados"]], ["España", "Mundo"])
        es, mundo = d["apartados"][0]["items"], d["apartados"][1]["items"]
        self.assertEqual([it["url"] for it in es], ["https://ejemplo.com/pan", "https://ejemplo.com/equipo", "https://ejemplo.com/museo"])
        self.assertEqual(mundo, [])                                       # lo mismo no sale en dos apartados
        crudo = json.dumps(d, ensure_ascii=False)
        for malo in ("<", "javascript", "diez días", "appeared first", "pais\"", "alert"):
            self.assertNotIn(malo, crudo, malo)
        self.assertEqual(es[1]["titulo"], "Gana el equipo local & lo celebra")
        self.assertEqual(es[0]["resumen"], "Los panaderos lo explican.")
        self.assertTrue(es[1]["resumen"].endswith("…") and len(es[1]["resumen"]) <= NI.RESUMEN + 1)
        self.assertEqual(es[2]["resumen"], "")                            # solo repetía el titular
        self.assertEqual({it["img"] for it in es}, {""})                  # con el RSS falso no se baja ninguna foto
        self.assertTrue(all(it["fuente"] and it["fecha"] for it in es))
        self.assertTrue(d["hoy"] and d["generado"] and not d["pendiente"] and d["fuentes_caidas"] == [])
        # caché compartida: otra invitada con España no vuelve a leer el RSS (aunque haya cambiado), y queda en disco
        self.rss.write_text(rss(("Otra cosa", "https://ejemplo.com/otra", hace(0), "")), encoding="utf-8")
        otra = NI.para(NI.validar({"paises": ["ES"]}), {})
        self.assertEqual([it["url"] for it in otra["apartados"][0]["items"]], [it["url"] for it in es])
        self.assertTrue(list((Path(os.environ["HUB_NOTICIAS_INV"]) / "rss").glob("*.json")))
        NI._CACHE.clear()                                                 # tras reiniciar el Hub, se lee del disco
        self.assertEqual(len(NI.para(NI.validar({"paises": ["ES"]}), {})["apartados"][0]["items"]), 3)

    def test_fuente_caida(self):
        self.rss.write_text("<rss><channel><item>roto", encoding="utf-8")
        d = NI.para(NI.validar({"paises": ["UY"]}), {})
        self.assertEqual(d["apartados"], [{"clave": "p-uy", "titulo": "Uruguay", "items": []}])
        self.assertEqual(d["fuentes_caidas"], ["Montevideo Portal", "El País"])
        self.assertIsNone(d["generado"])

    def test_imagen_solo_con_nombre_valido(self):
        img = Path(os.environ["HUB_NOTICIAS_INV"]) / "img"
        img.mkdir(parents=True)
        (img / ("a" * 40 + ".webp")).write_bytes(b"RIFF....WEBP")
        self.assertEqual(NI.imagen("a" * 40 + ".webp"), b"RIFF....WEBP")
        for malo in ("../../etc/passwd", "a" * 40 + ".png", "b" * 40 + ".webp", "A" * 40 + ".webp", ""):
            self.assertIsNone(NI.imagen(malo), malo)
        self.assertEqual(NI.img_valida("a" * 40), "a" * 40)
        self.assertEqual(NI.img_valida("../x"), "")


class Api(test_api.ZazuBase):
    """La invitada por la API del Hub de pruebas: la primera vez se le pregunta, elige y ve lo suyo. Fran sigue con lo suyo."""
    @classmethod
    def entorno(cls, puerto, gw):
        e = super().entorno(puerto, gw)
        e.update(HUB_NOTICIAS_INV_RSS=str(cls.dir / "rss-falso.xml"))
        return e

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.dir / "rss-falso.xml").write_text(RSS, encoding="utf-8")

    def test_01_pregunta_elige_y_ve_lo_suyo(self):
        g = self.galleta_invitada()
        self.assertIs(self.pedir("GET", "/api/me", cookie=g)[1]["capacidades"]["noticias"], True)
        self.assertEqual(self.pedir("GET", "/api/inv/noticias")[0], 403)                 # Fran tiene las suyas
        self.assertEqual(self.pedir("GET", "/api/noticias")[0], 200)
        st, d = self.pedir("GET", "/api/inv/noticias", cookie=g)
        self.assertEqual((st, d["elegido"], d["temas"], d["apartados"]), (200, False, ["mundo"], []))   # primero, el selector
        self.assertTrue(d["catalogo"]["paises"] and d["catalogo"]["temas"])
        self.assertEqual(self.post("/api/inv/noticias/elegir", {"paises": ["XX"]}, cookie=g)[0], 400)
        st, r = self.post("/api/inv/noticias/elegir", {"paises": ["ES", "XX"], "temas": ["deportes"]}, cookie=g)
        self.assertEqual((st, r), (200, {"ok": True, "paises": ["ES"], "temas": ["deportes"], "elegido": True}))
        us = json.loads((self.fh / ".config/hermes-hub/users.json").read_text())
        self.assertEqual(us["invitada@example.com"]["noticias"], {"paises": ["ES"], "temas": ["deportes"], "elegido": True})
        st, d = self.pedir("GET", "/api/inv/noticias", cookie=g)
        self.assertEqual((st, d["elegido"], [a["titulo"] for a in d["apartados"]]), (200, True, ["España", "Deportes"]))
        self.assertEqual(len(d["apartados"][0]["items"]), 3)
        self.assertNotIn("<", json.dumps(d["apartados"], ensure_ascii=False))
        self.assertEqual(self.post("/api/inv/noticias/elegir", {"paises": ["ES"]})[0], 403)   # Fran no elige por ella

    def test_02_miniaturas(self):
        g = self.galleta_invitada()
        img = self.fh / ".local/state/noticias-invitadas/img"
        img.mkdir(parents=True, exist_ok=True)
        clave = "c" * 40
        (img / f"{clave}.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        r = urllib.request.Request(f"http://127.0.0.1:{self.hub_port}/api/inv/noticias/img/{clave}.webp", headers={"Cookie": "hub_s=" + g})
        with urllib.request.urlopen(r, timeout=10) as f:
            self.assertEqual((f.status, f.headers["Content-Type"], f.read()[:4]), (200, "image/webp", b"RIFF"))
        for malo in ("d" * 40 + ".webp", "x.webp", "..%2F..%2Fusers.json"):
            self.assertEqual(self.pedir("GET", f"/api/inv/noticias/img/{malo}", cookie=g)[0], 404, malo)
        self.assertEqual(self.pedir("GET", f"/api/inv/noticias/img/{clave}.webp")[0], 403)


if __name__ == "__main__":
    unittest.main()
