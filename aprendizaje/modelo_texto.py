"""Un clasificador de texto pequeño, escrito a mano y sin librerías, para aprender decisiones de sí/no a partir de ejemplos de Fran.

Cómo funciona («Naive Bayes», el abuelo del aprendizaje automático):
  1. Entrenar: se cuenta cuántas veces sale cada palabra en los ejemplos «sí» y en los «no».
  2. Predecir: ante un texto nuevo, cada palabra empuja hacia «sí» o hacia «no» según lo que haya visto; se suman los empujones.
  3. Explicar: se pueden listar las palabras que más pesaron. Aquí nada es una caja negra.
Sirve con pocos ejemplos (decenas) y se entrena en milisegundos. Con muy pocos, desconfía de él: mira `validar_dejando_uno_fuera`.
"""
import json
import math
import re
import unicodedata
from collections import Counter

PARADA = set("el la los las un una unos unas de del al y o u en a que se por con para su sus lo le les es son fue ser mi tu me te nos si no como mas pero ya hay".split())


def palabras(texto):
    t = unicodedata.normalize("NFD", (texto or "").lower()).encode("ascii", "ignore").decode()
    return [w for w in re.findall(r"[a-z0-9]{3,}", t) if w not in PARADA]


class NaiveBayes:
    def __init__(self, alfa=1.0):
        self.alfa = alfa                           # suavizado: una palabra nunca vista en una clase no la hace imposible
        self.cuenta = {1: Counter(), 0: Counter()}
        self.docs = {1: 0, 0: 0}
        self.vocab = set()

    def entrenar(self, textos, etiquetas):
        for t, y in zip(textos, etiquetas):
            y = 1 if y else 0
            ws = set(palabras(t))                  # presencia, no repetición: «pagar pagar pagar» no pesa el triple
            self.cuenta[y].update(ws)
            self.docs[y] += 1
            self.vocab |= ws
        return self

    def _peso(self, w, y):
        total = sum(self.cuenta[y].values())
        return math.log((self.cuenta[y][w] + self.alfa) / (total + self.alfa * max(len(self.vocab), 1)))

    def puntuacion(self, texto):
        """log(P(sí)/P(no)) del texto: positivo empuja a «sí»."""
        s = math.log((self.docs[1] + 1) / (self.docs[0] + 1))
        for w in set(palabras(texto)):
            if w in self.vocab:
                s += self._peso(w, 1) - self._peso(w, 0)
        return s

    def probabilidad(self, texto):
        p = self.puntuacion(texto)
        return 1 / (1 + math.exp(-max(-30.0, min(30.0, p))))

    def explicar(self, texto, n=5):
        """Las palabras del texto que más pesaron, con su empujón (positivo = hacia «sí»)."""
        cont = [(w, self._peso(w, 1) - self._peso(w, 0)) for w in set(palabras(texto)) if w in self.vocab]
        return sorted(cont, key=lambda x: -abs(x[1]))[:n]

    def palabras_clave(self, n=8):
        """Lo que más empuja a «sí» y a «no» en general, mirando todo lo aprendido."""
        todas = [(w, self._peso(w, 1) - self._peso(w, 0)) for w in self.vocab if self.cuenta[1][w] + self.cuenta[0][w] >= 2]
        todas.sort(key=lambda x: x[1])
        return {"no": [w for w, _ in todas[:n]], "si": [w for w, _ in reversed(todas[-n:])]}

    def guardar(self, ruta):
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"alfa": self.alfa, "docs": self.docs, "cuenta": {str(k): dict(v) for k, v in self.cuenta.items()}}, f, ensure_ascii=False)

    @classmethod
    def cargar(cls, ruta):
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        m = cls(d["alfa"])
        m.docs = {int(k): v for k, v in d["docs"].items()}
        m.cuenta = {int(k): Counter(v) for k, v in d["cuenta"].items()}
        m.vocab = set(m.cuenta[1]) | set(m.cuenta[0])
        return m


def validar_dejando_uno_fuera(textos, etiquetas):
    """El examen honesto con pocos datos: para cada ejemplo, entrena con todos los demás y comprueba si acierta ese. → (aciertos, total, base)
    `base` = lo que acertaría quien dijera siempre la clase más frecuente: si el modelo no la supera, no ha aprendido nada."""
    aciertos = 0
    n = len(textos)
    for i in range(n):
        m = NaiveBayes().entrenar(textos[:i] + textos[i + 1:], etiquetas[:i] + etiquetas[i + 1:])
        aciertos += (m.probabilidad(textos[i]) >= 0.5) == bool(etiquetas[i])
    unos = sum(1 for y in etiquetas if y)
    return aciertos, n, max(unos, n - unos)


class Clasificador:
    """Lo mismo que NaiveBayes pero para varias clases a la vez (p. ej. la categoría de un gasto: suscripciones, comida, ocio…)."""
    def __init__(self, alfa=1.0):
        self.alfa = alfa
        self.cuenta = {}                 # clase -> Counter de palabras
        self.docs = Counter()            # clase -> nº de ejemplos
        self.vocab = set()

    def entrenar(self, textos, etiquetas):
        for t, y in zip(textos, etiquetas):
            ws = set(palabras(t))
            self.cuenta.setdefault(y, Counter()).update(ws)
            self.docs[y] += 1
            self.vocab |= ws
        return self

    def _logp(self, texto, y):
        total = sum(self.cuenta[y].values())
        den = total + self.alfa * max(len(self.vocab), 1)
        s = math.log((self.docs[y] + 1) / (sum(self.docs.values()) + len(self.docs)))
        for w in set(palabras(texto)):
            if w in self.vocab:
                s += math.log((self.cuenta[y][w] + self.alfa) / den)
        return s

    def predecir(self, texto):
        """→ (la clase más probable, {clase: probabilidad})."""
        if not self.cuenta:
            return None, {}
        logs = {y: self._logp(texto, y) for y in self.cuenta}
        m = max(logs.values())
        exp = {y: math.exp(v - m) for y, v in logs.items()}
        z = sum(exp.values())
        probs = {y: v / z for y, v in exp.items()}
        return max(probs, key=probs.get), probs

    def palabras_de(self, clase, n=6):
        """Las palabras que más distinguen a esta clase de las demás."""
        otras = [y for y in self.cuenta if y != clase]
        puntos = []
        for w in self.vocab:
            a = self.cuenta[clase][w] / max(self.docs[clase], 1)
            b = max((self.cuenta[y][w] / max(self.docs[y], 1) for y in otras), default=0)
            if self.cuenta[clase][w] >= 2:
                puntos.append((a - b, w))
        return [w for _, w in sorted(puntos, reverse=True)[:n]]


def validar_por_grupos(textos, etiquetas, grupos, modelo=Clasificador):
    """Examen honesto cuando hay repetidos: se aparta un GRUPO entero (p. ej. todos los cargos de un mismo comercio), se entrena con el resto y se
    prueba con ese grupo. Si se apartara una fila suelta, el modelo vería a su «gemela» en el entrenamiento y haría trampa sin querer.
    → (aciertos, total, base, fallos[(texto, real, predicho)]); `base` = acertar siempre con la clase más frecuente."""
    aciertos, fallos = 0, []
    for g in sorted(set(grupos)):
        ent = [i for i, x in enumerate(grupos) if x != g]
        m = modelo().entrenar([textos[i] for i in ent], [etiquetas[i] for i in ent])
        for i, x in enumerate(grupos):
            if x == g:
                pred, _ = m.predecir(textos[i])
                if pred == etiquetas[i]:
                    aciertos += 1
                else:
                    fallos.append((textos[i], etiquetas[i], pred))
    base = Counter(etiquetas).most_common(1)[0][1]
    return aciertos, len(textos), base, fallos
