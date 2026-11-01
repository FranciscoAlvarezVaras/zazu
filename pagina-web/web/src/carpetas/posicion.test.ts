// Prueba de la paginación de la Galería (src/carpetas/posicion.ts): node --test web/src/carpetas/posicion.test.ts
// Node quita los tipos del .ts solo. Modela al servidor: una lista ordenada que se pide por tramos con «desde».
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { colocar, enFavoritos, siguienteDesde } from './posicion.ts'
import type { Medio } from './nube'

const m = (n: number, mtime: number, size = 1000, fav = false): Medio => ({ name: `IMG_${n}.jpg`, path: `Subidas/IMG_${n}.jpg`, size, mtime, kind: 'image', fav })
/** El servidor: 300 fotos, la 0 la más nueva */
const servidor = Array.from({ length: 300 }, (_, i) => m(i, 1_700_000_000 - i * 1000))
const pagina = (lista: Medio[], desde: number, n = 90) => lista.slice(desde, desde + n)

test('subir una foto vieja con lo nuevo ya cargado: no se mete en medio y la paginación no se salta ninguna', () => {
  const cargadas = pagina(servidor, 0)
  const vieja = m(900, 1_000_000_000)   // más antigua que todo
  const { lista, puestos } = colocar(cargadas, [vieja], 'nuevas', true)
  assert.equal(puestos.length, 0)
  assert.deepEqual(lista, cargadas)
  const despues = [...servidor, vieja].sort((a, b) => b.mtime - a.mtime)   // el servidor ya la tiene, al final
  const desde = siguienteDesde(lista, false)
  assert.equal(desde, 90)
  assert.equal(pagina(despues, desde)[0].path, servidor[90].path)   // la 91.ª sigue siendo la que se pide
})

test('el cálculo de antes (items.length) sí se saltaba una', () => {
  const cargadas = pagina(servidor, 0)
  const conVieja = [...cargadas, m(900, 1_000_000_000)]   // lo que hacía insertar(): la ponía detrás de la última cargada
  const despues = [...servidor, conVieja[90]].sort((a, b) => b.mtime - a.mtime)
  assert.notEqual(pagina(despues, conVieja.length)[0].path, servidor[90].path)
})

test('una foto nueva entra arriba y el servidor la lista dentro de lo cargado: la cuenta sigue cuadrando', () => {
  const cargadas = pagina(servidor, 0)
  const nueva = m(901, 1_800_000_000)
  const { lista, puestos } = colocar(cargadas, [nueva], 'nuevas', true)
  assert.equal(puestos.length, 1)
  assert.equal(lista[0].path, nueva.path)
  const despues = [nueva, ...servidor]
  assert.equal(pagina(despues, siguienteDesde(lista, false))[0].path, servidor[90].path)   // ni hueco ni repetida
})

test('si ya está todo cargado, la vieja va al final', () => {
  const { lista, puestos } = colocar(servidor, [m(902, 1_000_000_000)], 'nuevas', false)
  assert.equal(puestos.length, 1)
  assert.equal(lista[lista.length - 1].name, 'IMG_902.jpg')
})

test('por peso: la pequeña se queda para la paginación y la enorme entra arriba', () => {
  const porPeso = servidor.map((x, i) => ({ ...x, size: 10_000_000 - i * 1000 }))
  const cargadas = pagina(porPeso, 0)
  assert.equal(colocar(cargadas, [m(903, 1, 10)], 'tamano', true).puestos.length, 0)
  const grande = colocar(cargadas, [m(904, 1, 99_000_000)], 'tamano', true)
  assert.equal(grande.puestos.length, 1)
  assert.equal(grande.lista[0].name, 'IMG_904.jpg')
})

test('por antigüedad: la más nueva de todas va detrás de lo cargado', () => {
  const antiguas = [...servidor].reverse()
  const cargadas = pagina(antiguas, 0)
  assert.equal(colocar(cargadas, [m(905, 1_900_000_000)], 'antiguas', true).puestos.length, 0)
  assert.equal(colocar(cargadas, [m(906, 1)], 'antiguas', true).lista[0].name, 'IMG_906.jpg')
})

test('una que estaba y salió (Deshacer, o un favorito que falla) vuelve aunque sea la última de lo cargado', () => {
  const cargadas = pagina(servidor, 0)
  const ultima = cargadas[89], sin = cargadas.slice(0, 89)
  assert.equal(colocar(sin, [ultima], 'nuevas', true).puestos.length, 0)   // sin saber que estuvo, se queda para la paginación
  const vuelta = colocar(sin, [ultima], 'nuevas', true, p => p === ultima.path)
  assert.equal(vuelta.puestos.length, 1)
  assert.equal(vuelta.lista[89].path, ultima.path)
  assert.equal(siguienteDesde(vuelta.lista, false), 90)
})

test('el mismo día (misma fecha) se ordena por ruta, como el servidor: vuelve exactamente a su hueco', () => {
  const dia = Array.from({ length: 12 }, (_, i) => ({ ...m(100 + i, 1_700_000_000), path: `Movil/IMG_20231114_${String(235900 - i * 100).padStart(6, '0')}.jpg`, name: `IMG_${i}.jpg` }))   // la ruta baja: ya van de más nueva a más vieja
  const otras = [m(1, 1_700_086_400), m(2, 1_699_900_000)]
  const todo = [otras[0], ...dia, otras[1]]
  const sin = todo.filter(x => x !== dia[5])
  const { lista } = colocar(sin, [dia[5]], 'nuevas', true)
  assert.deepEqual(lista.map(x => x.path), todo.map(x => x.path))
  // y por antigüedad, también (es el orden contrario, al pie de la letra)
  const rev = [...todo].reverse(), sinRev = rev.filter(x => x !== dia[5])
  assert.deepEqual(colocar(sinRev, [dia[5]], 'antiguas', true).lista.map(x => x.path), rev.map(x => x.path))
})

test('una nueva del mismo día que la última cargada entra donde dice el servidor (si no, se perdería)', () => {
  const dia = Array.from({ length: 5 }, (_, i) => ({ ...m(200 + i, 1_700_000_000), path: `Movil/IMG_20231114_${String(235900 - i * 100).padStart(6, '0')}.jpg` }))
  const cargadas = dia.slice(0, 3)   // la última cargada es la 3.ª del día
  const nueva = { ...m(300, 1_700_000_000), path: 'Movil/IMG_20231114_235950.jpg' }   // por ruta va la primera del día
  const { lista, puestos } = colocar(cargadas, [nueva], 'nuevas', true)
  assert.equal(puestos.length, 1)
  assert.equal(lista[0].path, nueva.path)
})

test('no repite lo que ya está', () => {
  const cargadas = pagina(servidor, 0)
  assert.equal(colocar(cargadas, [cargadas[3]], 'nuevas', true).puestos.length, 0)
})

test('Favoritos: lo desmarcado desde el visor aún se ve pero el servidor ya no lo lista', () => {
  const favs = Array.from({ length: 200 }, (_, i) => m(i, 1_700_000_000 - i * 1000, 1000, true))
  const cargadas = pagina(favs, 0).map((x, i) => i === 3 || i === 10 ? { ...x, fav: false } : x)
  assert.equal(siguienteDesde(cargadas, true), 88)
  const servidorAhora = favs.filter((_, i) => i !== 3 && i !== 10)
  assert.equal(pagina(servidorAhora, siguienteDesde(cargadas, true))[0].path, favs[90].path)   // ni se salta ni repite
  assert.equal(siguienteDesde(cargadas, false), 90)   // fuera de Favoritos, un corazón apagado no quita nada
})

test('enFavoritos mira el parámetro entero', () => {
  assert.equal(enFavoritos('fav=1'), true)
  assert.equal(enFavoritos('tipo=image&fav=1&orden=tamano'), true)
  assert.equal(enFavoritos('fav=10'), false)
  assert.equal(enFavoritos('xfav=1'), false)
  assert.equal(enFavoritos(''), false)
})
