"""Pruebas rápidas y sin red del buscador: modelo, puntuación, base y adaptadores con respuestas guardadas."""
import json, os, sys, tempfile, time, unittest
from datetime import date
from pathlib import Path
AQUI = Path(__file__).resolve().parent; RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
os.environ["EMPLEO_DB"] = str(Path(tempfile.mkdtemp()) / "ofertas.db"); os.environ["EMPLEO_CACHE"] = tempfile.mkdtemp()
import yaml, db, fuentes
from modelo import Oferta, limpiar_html, fecha_iso
from puntuar import puntuar
PERFIL = yaml.safe_load((RAIZ / "perfil.yaml").read_text())
HOY = date.today().isoformat()   # antes «2026-10-12» fijo: pasados 14 días las pruebas fallaban solas


class Modelo(unittest.TestCase):
    def test_id_estable_entre_fuentes(self):
        a = Oferta("x", "Junior Data Analyst", "Acme S.L.", "https://a"); b = Oferta("y", "junior data analyst", "ACME S.L.", "https://b")
        self.assertEqual(a.id, b.id)
    def test_limpiar_html_y_fecha(self):
        self.assertEqual(limpiar_html("<p>Hola&nbsp;<b>mundo</b></p>"), "Hola mundo")
        self.assertEqual(limpiar_html("Gesti&oacute;n &#225;gil &quot;BI&quot; &amp; datos"), 'Gestión ágil "BI" & datos')   # antes se quedaban sin convertir
        self.assertEqual(fecha_iso("2026-10-12T07:02:38+00:00"), "2026-10-12"); self.assertEqual(fecha_iso(1791705606), "2026-10-11"); self.assertEqual(fecha_iso("rara"), "")


class Puntuar(unittest.TestCase):
    def test_junior_valencia_puntua_alto(self):
        o = Oferta("t", "Junior Data Analyst", "Acme", "u", lugar="Valencia, España", pais="ES", fecha=HOY, descripcion="SQL, Python y Power BI")
        pista, puntos, _ = puntuar(o, PERFIL); self.assertEqual(pista, "dev"); self.assertGreaterEqual(puntos, 60)
    def test_senior_excluido(self):
        o = Oferta("t", "Senior Data Engineer", "Acme", "u", pais="ES"); self.assertEqual(puntuar(o, PERFIL)[0], "")
    def test_marketing_remoto_europa(self):
        o = Oferta("t", "Digital Marketing Specialist (remote)", "Acme", "u", lugar="Europe", pais="EU", remoto=True, fecha=HOY, descripcion="SEO, Google Ads, HubSpot")
        pista, puntos, _ = puntuar(o, PERFIL); self.assertEqual(pista, "marketing"); self.assertGreaterEqual(puntos, 40)
    def test_fuera_de_europa_baja(self):
        a = Oferta("t", "Junior Data Analyst", "Acme", "u", lugar="Austin, TX", pais="US", fecha=HOY); b = Oferta("t", "Junior Data Analyst", "Acme", "u", lugar="Berlin", pais="DE", fecha=HOY)
        self.assertLess(puntuar(a, PERFIL)[1], puntuar(b, PERFIL)[1])
    def test_vieja_excluida(self):
        o = Oferta("t", "Junior Data Analyst", "Acme", "u", pais="ES", fecha="2025-01-01"); self.assertEqual(puntuar(o, PERFIL)[0], "")


class PuntuarMejor(unittest.TestCase):
    """Los fallos de puntuación que encontró la revisión del 17 de octubre."""
    def pts(self, titulo, **k):
        k.setdefault("fecha", HOY); k.setdefault("pais", "ES")
        return puntuar(Oferta("t", titulo, "Acme", "u", **k), PERFIL)

    def test_tildes_no_cambian_nada(self):
        self.assertEqual(self.pts("Júnior Data Analyst")[1], self.pts("Junior Data Analyst")[1])      # antes «Júnior» perdía el bonus (54 → 36)
        self.assertEqual(self.pts("Sénior Data Engineer")[0], "")                                    # antes pasaba
        self.assertEqual(self.pts("Directora de Marketing")[0], "")
        self.assertEqual(self.pts("Responsable de Marketing Digital")[0], "")

    def test_sr_y_niveles_intermedios_fuera(self):
        for t in ("Sr Data Engineer", "Sr. BI Analyst", "Data Analyst II", "Mid-Level Python Developer", "Data Analyst III"):
            self.assertEqual(self.pts(t)[0], "", t)
        self.assertEqual(self.pts("Data Analyst", descripcion="Requires 3+ years of experience with SQL")[0], "")
        self.assertNotEqual(self.pts("Junior Data Analyst", descripcion="1-3 years of experience")[0], "")   # «1-3 años» sí es de junior
        self.assertNotEqual(self.pts("Junior Data Analyst")[0], "")

    def test_ubicacion_remota(self):
        mundo = self.pts("Junior Data Analyst", lugar="Worldwide", pais="REMOTE", remoto=True)[1]
        eu = self.pts("Junior Data Analyst", lugar="Europe", pais="EU", remoto=True)[1]
        solo_usa = self.pts("Junior Data Analyst", lugar="USA Only", pais="", remoto=True)
        solo_nl = self.pts("Junior Data Analyst", lugar="Netherlands", pais="NL", remoto=True)[1]
        self.assertEqual(solo_usa[0], "")                                        # «USA Only» en la ubicación excluye (antes solo se miraba el texto)
        self.assertLess(solo_nl, eu); self.assertGreaterEqual(eu, mundo)         # limitado a un país europeo: +4, no +10
        raro = self.pts("Junior Data Analyst", lugar="Remote - Atlantis", pais="", remoto=True)
        self.assertLess(raro[1], mundo)                                          # remoto con una restricción sin confirmar: baja
        self.assertIn("-10", " ".join(raro[2]))

    def test_pais_de_lugar(self):
        from fuentes import pais_de_lugar as pl
        self.assertEqual([pl(x) for x in ("Worldwide", "Anywhere", "Europe", "EMEA", "Spain", "Madrid", "Paris", "Netherlands", "USA Only", "Remote - US", "Boston, MA", "")],
                         ["REMOTE", "REMOTE", "EU", "EU", "ES", "ES", "FR", "NL", "US", "US", "US", ""])
        self.assertEqual(pl("USA, UK, India, Australia"), "")                    # una lista que no incluye España ni Europa: sin confirmar (antes «uk» la hacía EU)
        self.assertEqual(pl("Germany, France and Spain"), "ES")
        self.assertEqual(pl("Ukraine"), "")                                      # «uk» dentro de otra palabra no cuenta


class BaseMejor(unittest.TestCase):
    def nueva(self, titulo, **k):
        o = Oferta("t", titulo, "Acme", "https://" + titulo.replace(" ", ""), pais="ES", fecha=HOY, **k); o.pista, o.puntos = "dev", 50; return o

    def test_marcar_solo_con_un_id_de_verdad(self):
        c = db.conectar(); a, b = self.nueva("Junior Uno"), self.nueva("Junior Dos"); db.guardar(c, [a, b], {})
        for malo in ("_", "%", "", "3", "zz", "ab"):
            self.assertEqual(db.marcar(c, malo, "descartada"), 0, malo)           # antes «_» o «%» marcaban TODAS
        self.assertEqual(db.marcar(c, a.id[:8], "guardada"), 1)
        self.assertEqual(sorted(r["estado"] for r in c.execute("SELECT estado FROM ofertas WHERE id IN (?,?)", (a.id, b.id))), ["guardada", "nueva"])

    def test_guardadas_no_se_borran_al_envejecer(self):
        c = db.conectar(); o = self.nueva("Junior Guardada"); db.guardar(c, [o], {}); db.marcar(c, o.id[:8], "guardada")
        c.execute("UPDATE ofertas SET fecha='2020-01-01' WHERE id=?", (o.id,)); c.commit()
        db.repuntuar(c, PERFIL, puntuar, Oferta)
        r = c.execute("SELECT estado, puntos, pista FROM ofertas WHERE id=?", (o.id,)).fetchone()
        self.assertEqual((r["estado"], r["puntos"], r["pista"]), ("guardada", 50, "dev"))     # antes: puntos 0 y pista vacía (desaparecía de las listas)

    def test_listar_quita_estados_antes_del_limite(self):
        c = db.conectar(); xs = [self.nueva(f"Junior Lote{i}") for i in range(5)]
        for i, x in enumerate(xs): x.puntos = 90 - i
        db.guardar(c, xs, {})
        for x in xs[:4]: db.marcar(c, x.id[:8], "descartada")
        r = db.listar(c, n=50, sin_estados=("descartada", "excluida"))
        self.assertIn("Junior Lote4", [x["titulo"] for x in r])                              # el que queda sale
        self.assertFalse([x for x in r if x["estado"] in ("descartada", "excluida")])
        self.assertEqual(db.listar(c, n=1, sin_estados=("descartada", "excluida"))[0]["estado"], "nueva")   # con el filtro después del límite, n=1 salía vacío

    def test_la_oferta_repetida_refresca_ubicacion_y_fecha(self):
        c = db.conectar(); o = self.nueva("Junior Repost", lugar="Remote"); o.fecha = "2020-01-01"; db.guardar(c, [o], {})
        o2 = self.nueva("Junior Repost", lugar="Valencia"); db.guardar(c, [o2], {})
        r = c.execute("SELECT lugar, fecha FROM ofertas WHERE id=?", (o.id,)).fetchone()
        self.assertEqual((r["lugar"], r["fecha"]), ("Valencia", HOY))


class Resumen(unittest.TestCase):
    def test_no_repite_lo_ya_enseñado(self):
        import subprocess
        env = dict(os.environ, EMPLEO_DB=str(Path(tempfile.mkdtemp()) / "r.db"), EMPLEO_CACHE=tempfile.mkdtemp())
        sys.path.insert(0, str(RAIZ)); import importlib
        antes = db.RUTA; db.RUTA = Path(env["EMPLEO_DB"])
        try:
            c = db.conectar(); o = Oferta("t", "Junior Resumen Unico", "Acme", "https://r", pais="ES", fecha=HOY); o.pista, o.puntos = "dev", 60; db.guardar(c, [o], {}); c.close()
            # buscar.py sin red falla al importar las fuentes con red? se lanza el resumen real pero con las fuentes sustituidas por una lista vacía
            codigo = ("import sys, runpy; sys.argv=['resumen.py']\nimport subprocess as sp\n"
                      "_run = sp.run\nsp.run = lambda *a, **k: sp.CompletedProcess(a, 0, stdout='', stderr='')\n"
                      "runpy.run_path('resumen.py', run_name='__main__')")
            salidas = [subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), env=env, capture_output=True, text=True, timeout=60).stdout for _ in range(2)]
        finally:
            db.RUTA = antes
        self.assertIn("Junior Resumen Unico", salidas[0]); self.assertIn("[", salidas[0])
        self.assertNotIn("Junior Resumen Unico", salidas[1])                      # la segunda vez ya no sale (antes salía dos días seguidos)


class Base(unittest.TestCase):
    def test_guardar_y_marcar(self):
        c = db.conectar(); o = Oferta("t", "Junior BI Analyst", "Acme", "https://a", pais="ES", fecha=HOY); o.pista, o.puntos = "dev", 50
        self.assertEqual(db.guardar(c, [o], {o.id: ["+x"]}), 1); self.assertEqual(db.guardar(c, [o], {}), 0)
        self.assertEqual(len(db.listar(c, pista="dev")), 1); db.marcar(c, o.id[:6], "guardada"); self.assertEqual(db.listar(c, estado="guardada")[0]["titulo"], "Junior BI Analyst")


class Adaptadores(unittest.TestCase):
    """Cada fuente convierte su JSON (guardado en fixtures/) en Ofertas con título, empresa y url."""
    def _con_fixture(self, nombre):
        datos = json.loads((AQUI / "fixtures" / f"{nombre}.json").read_text())
        original = fuentes.get_json; fuentes.get_json = lambda *a, **k: datos
        try:
            mod = __import__(f"fuentes.{nombre}", fromlist=["buscar"]); mod.get_json = fuentes.get_json
            return mod.buscar(PERFIL)
        finally:
            fuentes.get_json = original
    def test_todas(self):
        for nombre in ("arbeitnow", "remotive", "remoteok", "jobicy", "themuse", "himalayas"):
            with self.subTest(fuente=nombre):
                ofs = self._con_fixture(nombre); self.assertTrue(ofs, nombre)
                for o in ofs: self.assertTrue(o.titulo and o.url, nombre); self.assertEqual(o.fuente, nombre)
    def test_adzuna_sin_claves_se_salta(self):
        import fuentes.adzuna as az; az.CLAVES = Path("/no/existe"); os.environ.pop("ADZUNA_APP_ID", None); self.assertEqual(az.buscar(PERFIL), [])


class Idiomas(unittest.TestCase):
    """Puerta de idioma: perfil.yaml declara [es, en]."""
    def _o(self, desc, titulo="Junior Data Analyst"):
        return Oferta("t", titulo, "Acme", "u", lugar="Valencia", pais="ES", fecha=HOY, descripcion=desc)
    def test_exige_otro_idioma_se_descarta(self):
        for d in ("Requirements: fluent German required, SQL.", "Sehr gute Deutschkenntnisse erforderlich. SQL y Python.",
                  "Nivel alto de alemán imprescindible, SQL.", "You speak French at C1 level. SQL, Python."):
            pista, puntos, m = puntuar(self._o(d), PERFIL)
            self.assertEqual((pista, puntos), ("", 0), d); self.assertIn("exige", m[0])
    def test_plus_o_idioma_declarado_no_descarta(self):
        for d in ("German is a plus. SQL, Python, Power BI.", "Se valorará alemán. SQL y Python.", "Fluent English required. SQL, Python.",
                  "Inglés fluido imprescindible, SQL, Python.", "Trabajarás con Germany y la Deutsche Bank en SQL y Python."):
            self.assertNotEqual(puntuar(self._o(d), PERFIL)[0], "", d)
    def test_escrita_en_aleman_solo_baja_puntos(self):
        de = ("Wir suchen einen Junior Data Analyst für unser Team. Sie arbeiten mit SQL und Python und werden von uns eingearbeitet. "
              "Ihre Aufgaben sind die Analyse der Daten und die Erstellung von Berichten für die Kunden und das Management im Unternehmen.")
        en = ("We are looking for a Junior Data Analyst for our team. You will work with SQL and Python and we will train you. "
              "Your tasks are analysing the data and building reports for the customers and the management in the company.")
        a, b = puntuar(self._o(de), PERFIL), puntuar(self._o(en), PERFIL)
        self.assertNotEqual(a[0], ""); self.assertEqual(b[1] - a[1], 20); self.assertTrue(any("escrita en de" in x for x in a[2]))
    def test_texto_en_espanol_no_se_toma_por_otro_idioma(self):
        es = ("Buscamos un analista de datos junior para incorporarse a nuestro equipo en Valencia. Trabajarás con SQL y Python en la creación de informes para los clientes "
              "y el equipo directivo de la empresa. Ofrecemos formación, contrato indefinido y la posibilidad de teletrabajar dos días a la semana con un horario flexible.")
        pista, puntos, m = puntuar(self._o(es), PERFIL)
        self.assertNotEqual(pista, ""); self.assertFalse(any("escrita en" in x for x in m))
    def test_sin_idiomas_en_el_perfil_no_filtra(self):
        p = dict(PERFIL); p.pop("idiomas")
        self.assertNotEqual(puntuar(self._o("Fluent German required. SQL, Python."), p)[0], "")


if __name__ == "__main__":
    unittest.main()


class LinkedInPosts(unittest.TestCase):
    def test_post_a_oferta(self):
        from fuentes.linkedin_posts import post_a_oferta
        po = {"text": "Buscamos Junior Data Analyst para Valencia (remoto posible).\nEscribid a seleccion@empresa.es", "emails_found": ["seleccion@empresa.es"], "author_name": "Ana Pérez", "post_url": "https://lnkd.in/x"}
        o = post_a_oferta(po); self.assertEqual(o.fuente, "linkedin_posts"); self.assertTrue(o.titulo.startswith("Buscamos Junior Data Analyst")); self.assertEqual(o.pais, "ES"); self.assertTrue(o.remoto)
        self.assertIn("contacto: seleccion@empresa.es", o.etiquetas); pista, puntos, _ = puntuar(o, PERFIL); self.assertEqual(pista, "dev")
    def test_sin_sesion_se_salta(self):
        import fuentes.linkedin_posts as lp; lp.SESION = Path("/no/existe"); self.assertEqual(lp.buscar(PERFIL), [])
