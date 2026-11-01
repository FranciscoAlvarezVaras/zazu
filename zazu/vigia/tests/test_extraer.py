"""Extracción determinista de fecha, hora e importe: español de España, sin adivinar."""
import re
import unittest
from datetime import date

import base  # noqa: F401  (aísla HOME y prepara el path antes de importar zv)
from zv import extraer as x

HOY = date(2026, 10, 8)
POS = re.compile(r"vencimiento|vence\b|plazo|antes\s+del?|hasta\s+el|l[ií]mite", re.I)
NEG = re.compile(r"emisi[óo]n|per[ií]odo|desde|pedido", re.I)
POS_I = re.compile(r"total|importe|a\s+pagar", re.I)
NEG_I = re.compile(r"\biva\b|base|subtotal", re.I)


def una(texto, pos=POS, neg=NEG):
    c = x.candidatos_fecha(texto, HOY, pos, neg)
    f, motivo = x.elegir(c, texto)
    return f, motivo


class TestFechas(unittest.TestCase):
    def test_formatos_espanoles(self):
        for t, esperado in (("el 15/10/2026", date(2026, 10, 15)), ("el 15-10-26", date(2026, 10, 15)), ("el 15.10.2026", date(2026, 10, 15)),
                            ("2026-10-15", date(2026, 10, 15)), ("el 15 de octubre", date(2026, 10, 15)), ("el jueves 15 de octubre de 2026", date(2026, 10, 15)),
                            ("15 oct 2026", date(2026, 10, 15)), ("1 de noviembre", date(2026, 11, 1)), ("30 de octubre", date(2026, 10, 30))):
            f, m = una(t)
            self.assertEqual((f.fecha if f else None, m), (esperado, "ok"), t)

    def test_sin_ano_pasa_al_proximo_solo_si_es_antiguo(self):
        self.assertEqual(una("el 03/10")[0], None)                            # pasó hace 5 días: no se adivina
        self.assertEqual(una("el 30 sept.")[0], None)
        self.assertEqual(una("el 15 de enero")[0].fecha, date(2027, 1, 15))   # hace más de 60 días → el año que viene
        self.assertEqual(una("hoy 08/10")[0].fecha, date(2026, 10, 8))        # hoy vale

    def test_pasadas_y_lejanas_se_descartan(self):
        self.assertEqual(una("emitida el 01/09/2026")[1], "sin_fecha")
        self.assertEqual(una("vence el 15/10/2030")[1], "sin_fecha")
        self.assertEqual(una("el 31/02/2026 o el 45/13/2026")[1], "sin_fecha")

    def test_dia_de_la_semana_con_numero(self):
        self.assertEqual(una("el martes 13 a las 10:00")[0].fecha, date(2026, 10, 13))
        self.assertEqual(una("el miércoles 14 de octubre")[0].fecha, date(2026, 10, 14))

    def test_la_pista_decide_entre_varias(self):
        f, m = una("Fecha de emisión 01/10/2026. Vencimiento 20/10/2026. Fecha de emisión duplicada 05/10/2026")
        self.assertEqual((f.fecha, m), (date(2026, 10, 20), "ok"))
        f, m = una("Su factura del periodo desde 01/09/2026 hasta el 30/09/2026 vence el 25/10/2026")
        self.assertEqual(f.fecha, date(2026, 10, 25))

    def test_dos_fechas_sin_pista_es_ambiguo(self):
        self.assertEqual(una("Reunión el 12/10/2026 o el 25/10/2026"), (None, "ambigua"))
        self.assertEqual(una("antes del 12/10/2026 y antes del 25/10/2026"), (None, "ambigua"))

    def test_formato_ambiguo_en_ingles_no_se_adivina(self):
        self.assertEqual(una("Your booking on 05/11/2026, please check the date and the time")[1], "formato_ambiguo")
        self.assertEqual(una("Su reserva el 05/11/2026 con la factura")[1], "ok")
        self.assertEqual(una("Your booking on 25/11/2026, please check the date")[1], "ok")          # 25 no puede ser mes

    def test_fechas_inglesas_con_mes_en_letra(self):
        self.assertEqual(una("Due October 15, 2026, please pay")[0].fecha, date(2026, 10, 15))

    def test_numeros_que_no_son_fechas(self):
        self.assertEqual(una("Son 10.30 euros, el pedido 1-2 y la hora 10:30")[1], "sin_fecha")


class TestHoras(unittest.TestCase):
    def hora(self, t):
        f, m = una(t)
        return f.hora if f else None

    def test_formas(self):
        for t, h in (("15/10/2026 a las 10:30", "10:30"), ("15/10/2026 a las 10.30 h", "10:30"), ("15/10/2026 10h30", "10:30"), ("15/10/2026 a las 9:05h", "09:05"),
                     ("15/10/2026, 16:00h", "16:00"), ("el 15/10/2026 a las 5 de la tarde", "17:00"), ("el 15/10/2026 a las 5 pm", "17:00"),
                     ("el 15/10/2026 a las 9 de la mañana", "09:00"), ("a las 20:15 del 15/10/2026", "20:15")):
            self.assertEqual(self.hora(t), h, t)

    def test_sin_hora_o_hora_ambigua(self):
        self.assertIsNone(self.hora("el 15/10/2026"))
        f, _ = una("Check-in el 15/10/2026 desde las 15:00 hasta las 20:00")
        self.assertEqual((f.hora, f.hora_ambigua), (None, True))
        self.assertIsNone(self.hora("el 15/10/2026 a las 00:00"))

    def test_cada_hora_a_su_fecha(self):
        c = x.candidatos_fecha("Ida: 05/11/2026 07:25 Valencia. Vuelta: 08/11/2026 18:10 París", HOY)
        self.assertEqual([(f.fecha, f.hora) for f in c], [(date(2026, 11, 5), "07:25"), (date(2026, 11, 8), "18:10")])


class TestImportes(unittest.TestCase):
    def imp(self, t):
        return x.importe(t, POS_I, NEG_I)

    def test_formatos(self):
        for t, v in (("Total: 49,99 €", "49,99 €"), ("a pagar 1.234,56 euros", "1.234,56 €"), ("importe 49.99 EUR", "49,99 €"), ("Importe: € 12", "12 €"),
                     ("total 1.234 €", "1.234 €"), ("pagar 7,5 €", "7,50 €")):
            self.assertEqual(self.imp(t), (v, "ok"), t)

    def test_el_total_gana_a_la_base_y_al_iva(self):
        self.assertEqual(self.imp("Base 41,31 € IVA 8,68 € Total a pagar 49,99 €"), ("49,99 €", "ok"))

    def test_varios_sin_pista_o_ninguno(self):
        self.assertEqual(self.imp("Opciones: 10 € o 20 €"), (None, "ambiguo"))
        self.assertEqual(self.imp("sin cifras"), (None, "sin_importe"))
        self.assertEqual(self.imp("costó 0 €"), (None, "sin_importe"))


if __name__ == "__main__":
    unittest.main()
