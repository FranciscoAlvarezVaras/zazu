// Prueba de la fecha relativa de las noticias (src/panel/relativa.ts): node --test web/scripts/relativa.test.mjs
// Node quita los tipos del .ts solo (22.18+). Hora local fija para que «hoy» y «ayer» no dependan del PC.
process.env.TZ = 'Europe/Madrid'
import { test } from 'node:test'
import assert from 'node:assert/strict'
const { relativa } = await import('../src/panel/relativa.ts')

const ahora = new Date('2026-10-22T23:50:00').getTime()
test('una de hoy a las 00:20 vista a las 23:50 no es «ayer»', () => assert.equal(relativa('2026-10-22T00:20:00', ahora), 'hace 23 h'))
test('una de ayer a las 22:00 es «ayer»', () => assert.equal(relativa('2026-10-21T22:00:00', ahora), 'ayer'))
test('una de ayer a las 09:00 es «ayer», no «hace 2 días»', () => assert.equal(relativa('2026-10-21T09:00:00', ahora), 'ayer'))
test('de ayer a última hora vista de madrugada: en horas', () => assert.equal(relativa('2026-10-21T23:00:00', new Date('2026-10-22T01:00:00').getTime()), 'hace 2 h'))
test('cuenta días del calendario', () => assert.equal(relativa('2026-10-19T23:00:00', ahora), 'hace 3 días'))
test('cruzando el cambio de hora (25 de octubre)', () => assert.equal(relativa('2026-10-24T20:00:00', new Date('2026-10-25T21:00:00').getTime()), 'ayer'))
test('minutos, futuro y basura', () => {
  assert.equal(relativa('2026-10-22T23:20:00', ahora), 'hace 30 min')
  assert.equal(relativa('2026-10-22T23:49:30', ahora), 'hace un momento')
  assert.equal(relativa('2026-10-23T00:10:00', ahora), '')
  assert.equal(relativa('no es fecha', ahora), '')
  assert.equal(relativa('', ahora), '')
})
