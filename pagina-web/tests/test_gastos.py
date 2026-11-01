#!/usr/bin/env python3
"""Pruebas unitarias (sin servidor) de gastos.py: lo que el vigía devuelve se valida campo a campo, el Hub no calcula nada, un fallo se dice y los comandos son una lista cerrada.

    python3 tests/test_gastos.py        (TMPDIR bajo /tmp)
`registro._correr` (la tubería segura hacia `zv`) se sustituye por un doble: aquí no se lanza ningún proceso."""
import json, os, sys, unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import avisos, gastos, registro, tableros  # noqa: E402
from registro import RegistroError  # noqa: E402

HOY = avisos.ahora().date()


def d(n):
    return (HOY + timedelta(days=n)).isoformat()


def sub(**k):
    return {"nombre": "Spotify", "comercio": "spotify", "importe": 11.99, "moneda": "EUR", "periodo": "mensual", "mensual": 11.99, "anual": 143.88, "ultimo_cobro": d(-20),
            "proximo_cobro": d(10), "dias_para_cobro": 10, "proximo_fuente": "estimado", "estado": "activa", "cancelar": False, "cargos": 3, "base": "correo",
            "categoria": "suscripciones", "cuenta": "varas", "subida_pct": None, **k}


ESTADO = {"fase": "al_dia", "cuentas_leidas": 2, "cuentas": 2, "pendientes": 0, "desde": d(-90), "ultima_lectura": "2026-10-10T09:00:00+02:00", "habilitado": True}


def mes(**k):
    return {"ok": True, "mes": "2026-10", "total_eur": 925.65, "sin_convertir": {"USD": 24.99},
            "por_categoria": [{"categoria": "vivienda", "moneda": "EUR", "importe": 711.9, "importe_eur": 711.9, "n": 3}],
            "por_comercio": [{"comercio": "Alquiler", "moneda": "EUR", "importe": 650.0, "importe_eur": 650.0, "n": 1, "categoria": "vivienda"}],
            "mes_anterior": {"mes": "2026-09", "total_eur": 840.2, "sin_convertir": {}, "total_eur_a_esta_altura": 702.5}, "sin_clasificar": 1, "dudosos": 2,
            "presupuesto": {"tope_activo": True, "tope": 1000.0, "usado": 925.65, "topes_categoria": {}}, "estado": ESTADO, **k}


class Falso:
    """Sustituye registro._correr: devuelve lo que se le diga para cada consulta y anota los argumentos."""
    def __init__(self, test, susc=None, gast=None, rc=0, error=None):
        self.test, self.llamadas = test, []
        self.susc = susc if susc is not None else {"ok": True, "items": [sub()], "n": 1, "totales": {"EUR": {"mensual": 11.99, "anual": 143.88, "n": 1}}, "estado": ESTADO}
        self.gast, self.rc, self.error = gast if gast is not None else mes(), rc, error

    def __call__(self, args, timeout):
        self.llamadas.append(list(args))
        if self.error:
            raise self.error
        d_ = self.susc if args[0] == "suscripciones" else self.gast
        return self.rc, d_ if isinstance(d_, str) else json.dumps(d_)

    def __enter__(self):
        self.antes = registro._correr
        registro._correr = self
        return self

    def __exit__(self, *a):
        registro._correr = self.antes


class Comandos(unittest.TestCase):
    def test_lista_cerrada(self):
        self.assertEqual(gastos._args("suscripciones"), ["suscripciones", "--json"])
        self.assertEqual(gastos._args("gastos"), ["gastos", "--json"])
        self.assertEqual(gastos._args("gastos", "2026-09"), ["gastos", "--json", "--mes", "2026-09"])
        for malo in (("recalcular", None), ("registro", None), ("flujo", None), ("gastos", "../x"), ("gastos", "2026-9"), ("gastos", "2026-10; touch PWNED_X"), ("gastos", "2026-10 --releer"),
                     ("gastos", ["2026-10"]), ("gastos", "")):
            if malo[1] == "":
                self.assertEqual(gastos._args("gastos", ""), ["gastos", "--json"])        # vacío = sin mes
                continue
            with self.assertRaises(RegistroError, msg=str(malo)):
                gastos._args(*malo)

    def test_solo_lanza_lo_que_toca_y_nunca_recalcular(self):
        with Falso(self) as f:
            gastos.suscripciones(); gastos.gastos_mes(); gastos.gastos_mes("2026-09"); gastos.tablero()
        todas = {tuple(x) for x in f.llamadas}
        self.assertEqual(todas, {("suscripciones", "--json"), ("gastos", "--json"), ("gastos", "--json", "--mes", "2026-09")})


class Suscripciones(unittest.TestCase):
    def test_lo_normal_pasa_tal_cual(self):
        with Falso(self):
            r = gastos.suscripciones()
        self.assertTrue(r["ok"])
        s = r["items"][0]
        self.assertEqual(s, {"nombre": "Spotify", "importe": 11.99, "moneda": "EUR", "periodo": "mensual", "mensual": 11.99, "anual": 143.88, "proxima_fecha": d(10), "dias": 10,
                             "ultimo_cobro": d(-20), "proximo_fuente": "estimado", "estado": "activa", "cancelar": False, "cargos": 3, "base": "correo", "categoria": "suscripciones",
                             "cuenta": "varas", "subida_pct": None})
        self.assertEqual(r["totales"], {"EUR": {"mensual": 11.99, "anual": 143.88, "n": 1}})
        self.assertEqual((r["estado"]["fase"], r["estado"]["cuentas_leidas"]), ("al_dia", 2))

    def test_el_hub_no_calcula_totales_ni_importes(self):
        z = [sub(nombre="A", importe=10, mensual=10, anual=120), sub(nombre="B", importe=20, mensual=20, anual=240)]
        with Falso(self, susc={"ok": True, "items": z, "totales": {"EUR": {"mensual": 99.5, "anual": 1194.0, "n": 7}}}):
            r = gastos.suscripciones()
        self.assertEqual(r["totales"], {"EUR": {"mensual": 99.5, "anual": 1194.0, "n": 7}})      # lo que dice el vigía, aunque no cuadre con los items
        with Falso(self, susc={"ok": True, "items": z}):
            self.assertEqual(gastos.suscripciones()["totales"], {})                              # sin totales del vigía: sin totales (no se suman aquí)

    def test_dias_del_reloj_del_hub(self):
        with Falso(self, susc={"ok": True, "items": [sub(proximo_cobro=d(3), dias_para_cobro=999)]}):
            self.assertEqual(gastos.suscripciones()["items"][0]["dias"], 3)

    def test_campos_raros_se_descartan_o_se_limpian(self):
        malos = [sub(nombre=""), sub(nombre=None), sub(estado="inventado"), sub(estado=None), "texto", 7, None, [1], {}]
        raros = sub(nombre="<b>Hola</b>\n‮X" + "y" * 200, importe=float("inf"), moneda="<script>", periodo="cada tanto", proximo_cobro="mañana", cargos=-3, cuenta="../../x",
                    categoria="<img src=x>", subida_pct="mucho", cancelar="sí", base="otra", proximo_fuente="adivinado", mensual=float("nan"), anual="x")
        with Falso(self, susc={"ok": True, "items": malos + [raros]}):
            r = gastos.suscripciones()
        self.assertEqual((len(r["items"]), r["omitidos"]), (1, len(malos)))
        s = r["items"][0]
        self.assertTrue(s["nombre"].startswith("<b>Hola</b> X") and len(s["nombre"]) <= 60 and "\n" not in s["nombre"] and "‮" not in s["nombre"])
        self.assertEqual((s["importe"], s["moneda"], s["periodo"], s["proxima_fecha"], s["dias"], s["cargos"], s["cuenta"], s["categoria"], s["subida_pct"], s["cancelar"], s["base"],
                          s["proximo_fuente"], s["mensual"], s["anual"]), (None, None, None, None, None, 0, None, None, None, False, "correo", None, None, None))

    def test_numeros_y_fechas(self):
        casos = {"importe": [(True, None), (False, None), ("12", None), (-1, None), (10 ** 8, None), (float("nan"), None), (0, 0.0), (11.999, 12.0), (None, None)],
                 "proximo_cobro": [("2026-02-30", None), ("2026-13-01", None), (20261010, None), ("", None), ("2026-10-10", "2026-10-10"), ("2026-10-10T10:00:00Z", "2026-10-10")]}
        with Falso(self, susc={"ok": True, "items": [sub(importe=v) for v, _ in casos["importe"]] + [sub(nombre=f"F{i}", proximo_cobro=v) for i, (v, _) in enumerate(casos["proximo_cobro"])]}):
            items = gastos.suscripciones()["items"]
        # los primeros 9 comparten nombre y moneda: solo uno sobrevive (sin duplicados); se comprueba aparte
        self.assertEqual(len(items), 1 + len(casos["proximo_cobro"]))
        self.assertEqual([i["proxima_fecha"] for i in items[1:]], [e for _, e in casos["proximo_cobro"]])
        for v, esperado in casos["importe"]:
            with Falso(self, susc={"ok": True, "items": [sub(importe=v)]}):
                self.assertEqual(gastos.suscripciones()["items"][0]["importe"], esperado, v)

    def test_duplicados_y_tope(self):
        with Falso(self, susc={"ok": True, "items": [sub(nombre="Spotify"), sub(nombre="SPOTIFY"), sub(nombre="Spotify", moneda="USD")] + [sub(nombre=f"S{i}") for i in range(300)]}):
            r = gastos.suscripciones()
        self.assertEqual(len([i for i in r["items"] if i["nombre"].lower() == "spotify"]), 2)   # mismo nombre en otra moneda sí es otra suscripción
        self.assertLessEqual(len(r["items"]), gastos.N_MAX)

    def test_totales_raros(self):
        w = {"EUR": {"mensual": "mucho", "anual": 1, "n": 1}, "XXX": {"mensual": 1, "anual": 1, "n": 1}, "USD": {"mensual": 24.99, "anual": 299.88, "n": 1}, "GBP": "x", "EUR2": {}}
        with Falso(self, susc={"ok": True, "items": [sub()], "totales": w}):
            self.assertEqual(gastos.suscripciones()["totales"], {"USD": {"mensual": 24.99, "anual": 299.88, "n": 1}})
        with Falso(self, susc={"ok": True, "items": [sub()], "totales": "no"}):
            self.assertEqual(gastos.suscripciones()["totales"], {})


class Mes(unittest.TestCase):
    def test_normal(self):
        with Falso(self):
            g = gastos.gastos_mes()
        self.assertEqual((g["ok"], g["mes"], g["total_eur"], g["sin_convertir"], g["sin_clasificar"], g["dudosos"]), (True, "2026-10", 925.65, {"USD": 24.99}, 1, 2))
        self.assertEqual(g["por_categoria"], [{"categoria": "vivienda", "moneda": "EUR", "importe": 711.9, "importe_eur": 711.9, "n": 3}])
        self.assertEqual(g["por_comercio"][0]["comercio"], "Alquiler")
        self.assertEqual(g["anterior"], {"mes": "2026-09", "total_eur": 840.2, "total_eur_a_esta_altura": 702.5})
        self.assertEqual(g["presupuesto"], {"tope_activo": True, "tope": 1000.0, "usado": 925.65})

    def test_mes_con_mas_reembolsos_que_cargos_es_un_dato_valido(self):
        """Neto negativo (devoluciones > gastos): antes se tiraba como «no entiendo al vigía» y caía todo el bloque de gastos."""
        neg = mes(total_eur=-12.5, por_categoria=[{"categoria": "ocio", "moneda": "EUR", "importe": -12.5, "importe_eur": -12.5, "n": 0},
                                                  {"categoria": "comida", "moneda": "EUR", "importe": 30.0, "importe_eur": 30.0, "n": 2}],
                  mes_anterior={"mes": "2026-09", "total_eur": -3.0, "sin_convertir": {}, "total_eur_a_esta_altura": -1.0})
        with Falso(self, gast=neg):
            g = gastos.gastos_mes()
        self.assertEqual((g["ok"], g["total_eur"]), (True, -12.5))
        self.assertEqual([(c["categoria"], c["importe"]) for c in g["por_categoria"]], [("ocio", -12.5), ("comida", 30.0)])
        self.assertEqual((g["anterior"]["total_eur"], g["anterior"]["total_eur_a_esta_altura"]), (-3.0, -1.0))
        with Falso(self, gast=mes(total_eur=-10 ** 9)):          # pero lo absurdo se sigue descartando
            with self.assertRaises(RegistroError):
                gastos.gastos_mes()

    def test_tope_apagado_no_enseña_tope(self):
        with Falso(self, gast=mes(presupuesto={"tope_activo": False, "tope": 500, "usado": 3})):
            self.assertEqual(gastos.gastos_mes()["presupuesto"], {"tope_activo": False, "tope": None, "usado": 3.0})

    def test_sin_total_o_sin_mes_es_un_fallo_no_un_cero(self):
        for k, v in (("total_eur", None), ("total_eur", "mil"), ("total_eur", float("inf")), ("total_eur", True), ("mes", "octubre"), ("mes", None)):
            with Falso(self, gast=mes(**{k: v})):
                with self.assertRaises(RegistroError, msg=(k, v)) as e:
                    gastos.gastos_mes()
                self.assertEqual(e.exception.code, 502)

    def test_hostil(self):
        sucio = mes(por_categoria=[{"categoria": "ok", "moneda": "ZZZ", "importe": 5}, {"categoria": "<img src=x onerror=alert(1)>", "moneda": "EUR", "importe": 5, "importe_eur": 5, "n": 1}, "x",
                                   {"categoria": "vivienda", "moneda": "EUR", "importe": "mil"}, {"categoria": "ocio", "moneda": "EUR", "importe": 7, "importe_eur": "nada", "n": -1}],
                    por_comercio=[{"comercio": "<b>x</b>\n" + "y" * 300, "moneda": "EUR", "importe": 5, "importe_eur": 5, "n": 1}, None, 7], presupuesto="no", mes_anterior=[1],
                    sin_convertir={"USD": "x", "XXX": 1, "GBP": 3.5}, estado="raro", sin_clasificar=-1, dudosos=True)
        with Falso(self, gast=sucio):
            g = gastos.gastos_mes()
        self.assertEqual([c["categoria"] for c in g["por_categoria"]], ["ocio"])             # «<img…>» no es una categoría legible (lleva < > =)
        self.assertEqual(g["por_categoria"][0], {"categoria": "ocio", "importe": 7.0, "moneda": "EUR", "importe_eur": None, "n": 0})
        self.assertEqual(len(g["por_comercio"]), 1)
        self.assertLessEqual(len(g["por_comercio"][0]["comercio"]), 60)
        self.assertNotIn("\n", g["por_comercio"][0]["comercio"])
        self.assertEqual(g["sin_convertir"], {"GBP": 3.5})
        self.assertEqual((g["anterior"], g["presupuesto"], g["sin_clasificar"], g["dudosos"]),
                         ({"mes": None, "total_eur": None, "total_eur_a_esta_altura": None}, {"tope_activo": False, "tope": None, "usado": None}, None, None))
        self.assertEqual(g["estado"], {"fase": None, "pendientes": None, "ultima_lectura": None, "desde": None, "cuentas_leidas": None, "cuentas": None})


class Fallos(unittest.TestCase):
    def test_cada_fallo_se_dice(self):
        casos = [(RegistroError(504, "el vigía tardó demasiado en contestar"), "el vigía tardó demasiado en contestar"), (RegistroError(503, "no encuentro el comando del vigía (zv)"), "no encuentro el comando del vigía (zv)"),
                 (RegistroError(502, "el vigía contestó con demasiados datos"), "el vigía contestó con demasiados datos")]
        for e, frase in casos:
            with Falso(self, error=e):
                t = gastos.tablero()
            self.assertEqual((t["ok"], t["error"]), (False, frase))
            self.assertNotIn("items", t)

    def test_salida_basura_codigos_y_vigia_viejo(self):
        for susc, rc, frase in (("esto no es json {{{", 0, "el vigía contestó algo que no entiendo"), ("", 2, gastos.VIGIA_VIEJO), ("[]", 0, "el vigía contestó algo que no entiendo"),
                                ({"ok": False, "error": "base ocupada /home/secreta <b>x</b>"}, 0, "el vigía no pudo hacerlo"), ({"ok": True, "items": []}, 1, "el vigía no pudo hacerlo"),
                                ({"ok": True, "items": "no"}, 0, "el vigía contestó algo que no entiendo")):
            with Falso(self, susc=susc, rc=rc):
                t = gastos.tablero()
            self.assertEqual((t["ok"], t["error"]), (False, frase), (susc, rc))
            self.assertNotIn("secreta", json.dumps(t))

    def test_si_solo_fallan_los_gastos_el_tablero_sigue(self):
        for gast, rc in (("basura", 0), ({"ok": False}, 0), (mes(total_eur=None), 0)):
            with Falso(self, gast=gast, rc=rc):
                t = gastos.tablero()
            self.assertTrue(t["ok"], (gast, rc))
            self.assertEqual(len(t["items"]), 1)
            self.assertFalse(t["gastos"]["ok"])
            self.assertIn("vigía", t["gastos"]["error"])
            self.assertNotIn("total_eur", t["gastos"])                       # ni un 0 € disfrazado

    def test_excepcion_inesperada_no_tumba_nada(self):
        with Falso(self, error=KeyError("x")):
            t = gastos.tablero()
        self.assertFalse(t["ok"])
        self.assertIn("KeyError", t["error"])

    def test_notas_cuando_no_hay_suscripciones(self):
        vacio = {"ok": True, "items": [], "totales": {}, "estado": {**ESTADO, "fase": "inicial", "pendientes": 12, "cuentas_leidas": 0}}
        with Falso(self, susc=vacio):
            t = gastos.tablero()
        self.assertEqual((t["ok"], t["items"], t["nota"]), (True, [], "todavía estoy leyendo tu correo de los últimos meses"))
        with Falso(self, susc={**vacio, "estado": ESTADO}):
            self.assertEqual(gastos.tablero()["nota"], "no he detectado suscripciones en tu correo")
        with Falso(self):
            self.assertIsNone(gastos.tablero()["nota"])


class EnElTablero(unittest.TestCase):
    def test_el_tablero_suma_las_partes_sin_inventar(self):
        with Falso(self):
            t = tableros._tablero_suscripciones(None, None, {"suscripciones": gastos.tablero})
        self.assertEqual((t["id"], t["ok"], t["total"], t["nota"]), ("suscripciones", True, 1, None))
        self.assertEqual(set(t), {"id", "titulo", "tipo", "ok", "items", "total", "nota", "totales", "estado", "gastos"})
        self.assertTrue(t["gastos"]["ok"])

    def test_error_del_vigia_es_error_del_tablero(self):
        with Falso(self, error=RegistroError(504, "el vigía tardó demasiado en contestar")):
            t = tableros._tablero_suscripciones(None, None, {"suscripciones": gastos.tablero})
        self.assertEqual((t["ok"], t["error"], t["items"], t["total"]), (False, "el vigía tardó demasiado en contestar", [], 0))

    def test_sin_fuente_conserva_la_nota_de_antes(self):
        t = tableros._tablero_suscripciones(None, None, {})
        self.assertEqual((t["ok"], t["items"], t["nota"]), (True, [], tableros.SIN_SUSCRIPCIONES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
