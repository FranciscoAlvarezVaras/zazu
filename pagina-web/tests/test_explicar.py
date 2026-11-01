#!/usr/bin/env python3
"""«Explícamelo» (explicar.py) con un Claude FALSO (HUB_LLM_CMD): nada llama a un modelo real ni toca el APRENDIZAJE.md de verdad.
Guardar y no volver a pagar, gasto y tope de 15 $, lo que se manda (tachado, con el código donde saltó), «Lo he entendido» una vez
en APRENDIZAJE.md con el nivel, y que solo se explica lo que está en el visor. Todos los datos son inventados.

    python3 -m unittest tests.test_explicar -v"""
import json, os, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import explicar as X  # noqa: E402
import visor as V  # noqa: E402

FALSO = """#!/usr/bin/env python3
import json, sys
from pathlib import Path
aqui = Path(__file__).resolve().parent
e = json.load(sys.stdin)
with open(aqui / "llamadas.jsonl", "a") as f:
    f.write(json.dumps(e, ensure_ascii=False) + "\\n")
texto = "### Qué ha pasado\\nAlgo falló.\\n### Por qué ha pasado\\nPor una ruta.\\n### ¿Es grave?\\nUn poco.\\n### Pista para arreglarlo\\nMira tramo.\\n### Palabras nuevas\\n- **Path**: una ruta."
if "MINI EXAMEN" in e["system"]:
    texto = 'Aquí va: {"preguntas": ["¿Qué falló?", "¿Por qué falló?"]}'
elif "CORRIGES" in e["system"]:
    todo_bien = (aqui / "todo_bien").exists()   # el modelo «se equivoca» y aprueba todo
    resp = e["user"].split("<respuestas>")[1]
    bien = [todo_bien or "ruta" in r.lower() for r in resp.split("Respuesta de Fran:")[1:]]
    texto = json.dumps({"notas": [{"bien": b, "comentario": "ok" if b else "falta la causa"} for b in bien], "resumen": "fin"})
print(json.dumps({"ok": True, "text": texto, "usage": {"prompt_tokens": 100000, "completion_tokens": 50000}}))
"""


class Explicar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.antes = (V.DIR, X.ESTADO, X.GUARDADAS, X.APRENDIZAJE_MD, os.environ.get("HUB_LLM_CMD"))
        V.DIR = d / "visor"
        X.ESTADO, X.GUARDADAS, X.APRENDIZAJE_MD = V.DIR / "aprendizaje.json", V.DIR / "explicaciones", d / "APRENDIZAJE.md"
        X.APRENDIZAJE_MD.write_text("# Aprendizaje\n\nLo de antes.\n")
        falso = d / "falso.py"
        falso.write_text(FALSO)
        falso.chmod(0o755)
        os.environ["HUB_LLM_CMD"] = str(falso)
        self.llamadas = d / "llamadas.jsonl"
        codigo = d / "cosa.py"   # un «archivo del Hub» de pega para el trozo de código
        codigo.write_text("".join(f"linea {i}\n" for i in range(1, 30)))
        os.utime(codigo, (time.time() - 3600, time.time() - 3600))   # anterior al error: se enseña por número de línea
        self.antes_raices, X.RAICES = X.RAICES, (d,)
        V.anotar("app", "error", "TypeError: no vale, de pepa@example.com", d=f'Traceback (most recent call last):\n  File "{codigo}", line 12, in tramo\nTypeError: no vale')
        self.e = V.leer(n=1)[0]

    def tearDown(self):
        V.DIR, X.ESTADO, X.GUARDADAS, X.APRENDIZAJE_MD, cmd = self.antes
        X.RAICES = self.antes_raices
        if cmd is None:
            os.environ.pop("HUB_LLM_CMD", None)
        else:
            os.environ["HUB_LLM_CMD"] = cmd
        self.tmp.cleanup()

    def n_llamadas(self):
        return len(self.llamadas.read_text().splitlines()) if self.llamadas.exists() else 0

    def test_explica_guarda_y_no_vuelve_a_pagar(self):
        r = X.explicar(self.e)
        self.assertTrue(r["ok"])
        self.assertEqual((r["guardada"], r["coste"], r["gasto_mes"]), (False, 1.4, 1.4))   # 100k × 4 $ + 50k × 20 $ por millón
        enviado = json.loads(self.llamadas.read_text().splitlines()[0])
        self.assertEqual(enviado["model"], "claude-opus-5-5")
        self.assertNotIn("pepa@example.com", enviado["user"])
        self.assertIn("→    12  linea 12", enviado["user"])   # el código donde saltó
        self.assertIn("Empezando", enviado["system"])
        r2 = X.explicar(self.e)
        self.assertEqual((r2["guardada"], r2["coste"], self.n_llamadas()), (True, 0.0, 1))   # guardada: no se vuelve a pagar
        X.explicar(self.e, otra_vez=True)
        self.assertEqual(self.n_llamadas(), 2)

    def test_tope_del_mes(self):
        X._guardar_estado({"gasto": {time.strftime("%Y-%m"): 15.0}, "entendidos": {}, "arreglados": {}})
        r = X.explicar(self.e)
        self.assertEqual((r["ok"], r["motivo"], self.n_llamadas()), (False, "tope", 0))

    def test_pregunta_lleva_el_historial_y_no_se_guarda(self):
        X.explicar(self.e, "pregunta", "¿Qué es una ruta?", [{"q": "Explícamelo", "a": "Algo falló."}])
        enviado = json.loads(self.llamadas.read_text().splitlines()[0])
        self.assertIn("<historial>", enviado["user"])
        self.assertIn("¿Qué es una ruta?", enviado["user"])
        self.assertFalse(list(X.GUARDADAS.glob("*-pregunta.json")))

    def test_entendido_solo_aprobando_el_mini_examen(self):
        self.assertEqual(X.examen(self.e)["motivo"], "sin_explicacion")   # primero la explicación
        X.explicar(self.e)
        self.assertTrue(X.aprender(self.e, "arreglado")["falta_examen"])   # «arreglado» sin aprobar no cuenta
        ex = X.examen(self.e)
        self.assertEqual(ex["preguntas"], ["¿Qué falló?", "¿Por qué falló?"])
        self.assertEqual(X.examen(self.e)["preguntas"], ex["preguntas"])   # guardado: no se paga otra vez
        mal = X.corregir(self.e, ["no sé", "ni idea"])
        self.assertEqual((mal["aprobado"], mal["entendido"], mal["puntos"]), (False, False, 0))
        self.assertNotIn("Errores que ya sé leer", X.APRENDIZAJE_MD.read_text())   # suspender no apunta nada
        bien = X.corregir(self.e, ["falló al mirar dentro de una ruta", "porque una ruta no es una lista"])
        self.assertEqual((bien["aprobado"], bien["entendido"], bien["puntos"]), (True, True, 1))
        md = X.APRENDIZAJE_MD.read_text()
        self.assertTrue(md.startswith("# Aprendizaje\n\nLo de antes."))
        self.assertEqual(md.count("## Errores que ya sé leer"), 1)
        self.assertIn("Lo entendí (mini examen aprobado)", md)
        self.assertIn("¿Por qué falló?", md)
        self.assertEqual(X.estado()["examenes"][self.e["f"]]["intentos"], 2)
        r = X.aprender(self.e, "arreglado")
        self.assertEqual((r["puntos"], r["arreglados"]), (3, 1))   # entendido 1 + arreglado 2
        self.assertEqual((r["nivel"], r["nombre"]), (2, "Aprendiz"))

    def test_en_blanco_nunca_aprueba(self):
        X.explicar(self.e)
        X.examen(self.e)
        self.assertEqual(X.corregir(self.e, ["", ""])["motivo"], "vacio")
        (Path(self.tmp.name) / "todo_bien").touch()   # aunque el modelo diga que todo está bien
        r = X.corregir(self.e, ["una ruta", ""])
        self.assertEqual(([n["bien"] for n in r["notas"]], r["aprobado"]), ([True, False], False))

    def test_buscar_solo_lo_del_visor(self):
        self.assertEqual(X.buscar(self.e["t"], self.e["f"])["x"], self.e["x"])
        for t, f in ((self.e["t"], "zz"), ("x", self.e["f"]), (self.e["t"] + 60, self.e["f"])):
            self.assertIsNone(X.buscar(t, f))


if __name__ == "__main__":
    unittest.main()
