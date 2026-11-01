#!/usr/bin/env node
// «Una sola app»: una invitada ve el MISMO marco que Fran (menú, Inicio, chat, barra de Zazu), con sus secciones y sus datos.
// Chrome headless por CDP, sin dependencias. Comprueba: su Inicio con su agenda y sus tareas (nada de Fran), su menú, el logo de bits,
// los enlaces a secciones que no tiene (vuelven a Inicio), sus ajustes y rutinas, que la barra de Zazu manda un mensaje a SU chat
// y que la web nunca pide nada que le dé 403. Sale con código 1 si algo falla.
// El mensaje de la barra se corta en el navegador (CDP Fetch): nunca llega al hub, así que no arranca el Hermes de la invitada
// (jaula.py trabaja siempre sobre /home/server, no sobre la casa falsa).
//
//   1) casa falsa:  bash tests/fakehome.sh /tmp/fh  y la carpeta de gog de la invitada con sus datos falsos (tests/fakegog.py, --home):
//        /tmp/fh/.config/hermes-hub/invitadas/zitest/accounts.json  ([{"email":"invi@example.com","services":["calendar","tasks"],"error":false}])
//        /tmp/fh/.config/hermes-hub/invitadas/zitest/gogdata/invitada.{tasks,events}.json  (una «Tarea de Invi» y una «Cita de Invi» de hoy)
//   2) la web compilada (dist/) y un hub de PRUEBAS (nunca el de verdad):
//        python3 tests/fake_gateway.py --port 18893 --home /tmp/fh/.hermes &
//        HOME=/tmp/fh HUB_DEV=1 HUB_PORT=8893 HUB_PUBLIC_PORT=9893 HUB_GATEWAY_URL=http://127.0.0.1:18893 HUB_NO_PUSH=1 HUB_STATIC=$PWD/dist python3 server.py &
//   3) la galleta de la invitada:  HOME=/tmp/fh python3 -c "import json,server;print(server.make_session(json.load(open('/tmp/fh/.config/hermes-hub/auth.json')),'invitada@example.com'))"
//   4) node tests/una_app_invitada.mjs --base http://localhost:8893 --galleta <la galleta> [--ancho 375 --alto 812]   (FOTOS=<carpeta>: guarda una captura del Inicio con «Más»)
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const arg = (k, d = '') => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d }
const BASE = arg('base', 'http://localhost:8893'), GAL = arg('galleta', process.env.GALLETA || '')
const ancho = +arg('ancho', '1280'), alto = +arg('alto', '800'), movil = ancho < 900
if (!GAL) { console.error('falta --galleta (la sesión de la invitada de la casa falsa)'); process.exit(2) }
const sleep = ms => new Promise(r => setTimeout(r, ms))
const FRAN = ['Pagar seguro', 'Tarea atrasada', 'Renovar dominio', 'Cita DGT', 'Invitación ajena', 'Cumple de Ana', 'Dinero', 'Papeles', 'Empleo', 'WhatsApp', 'Ordenar todo', 'Avisos de Zazu']

const dir = mkdtempSync(join(tmpdir(), 'una-app-')), puerto = 9400 + Math.floor(Math.random() * 500)
const chrome = spawn(process.env.CHROME || 'google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars', `--user-data-dir=${dir}`, `--remote-debugging-port=${puerto}`, 'about:blank'], { stdio: 'ignore' })
let tabs
for (let i = 0; i < 60; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${puerto}/json`)).json(); if (tabs.length) break } catch { } await sleep(200) }
const ws = new WebSocket(tabs.find(x => x.type === 'page').webSocketDebuggerUrl)
await new Promise(r => ws.onopen = r)
let id = 0; const pend = new Map(), consola = [], api = [], cortados = []
ws.onmessage = e => {
  const m = JSON.parse(e.data)
  if (m.id && pend.has(m.id)) { const { ok, ko } = pend.get(m.id); pend.delete(m.id); m.error ? ko(new Error(JSON.stringify(m.error))) : ok(m.result) }
  else if (m.method === 'Network.requestWillBeSent' && m.params.request.url.includes('/api/')) api.push({ id: m.params.requestId, metodo: m.params.request.method, url: m.params.request.url, cuerpo: m.params.request.postData || '' })
  else if (m.method === 'Network.responseReceived') { const r = api.find(x => x.id === m.params.requestId); if (r) r.status = m.params.response.status }
  else if (m.method === 'Fetch.requestPaused') { cortados.push(m.params.request); void send('Fetch.failRequest', { requestId: m.params.requestId, errorReason: 'BlockedByClient' }) }
  else if (m.method === 'Runtime.exceptionThrown') consola.push('EXC ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text))
  else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consola.push(m.params.args.map(a => a.value ?? a.description).join(' '))
}
const send = (method, params = {}) => new Promise((ok, ko) => { const i = ++id; pend.set(i, { ok, ko }); ws.send(JSON.stringify({ id: i, method, params })) })
await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable')
await send('Emulation.setDeviceMetricsOverride', { width: ancho, height: alto, deviceScaleFactor: 1, mobile: movil })
let rot = 0
// cada página en un nombre distinto (hN.localhost): las /api/stream (SSE) de las anteriores no se comen las 6 conexiones por origen
const ir = async (q, espera = 2500) => {
  await send('Page.navigate', { url: 'about:blank' }); await sleep(150)
  const u = BASE.replace(/\/\/(localhost|127\.0\.0\.1):/, `//h${rot++ % 20}.localhost:`) + '/' + q
  await send('Network.setCookie', { name: 'hub_s', value: GAL, url: new URL(u).origin + '/' })
  await send('Page.navigate', { url: u }); await sleep(espera)
}
const js = async expr => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
const hasta = async (expr, ms = 9000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(expr)) return true; await sleep(250) } return false }
const pantalla = () => js(`document.querySelector('.pz-app')?.dataset.pantalla || ''`)
const texto = () => js('document.body.innerText')
const foto = async f => { if (!process.env.FOTOS) return; const r = await send('Page.captureScreenshot', { format: 'png' }); (await import('node:fs')).writeFileSync(join(process.env.FOTOS, f), Buffer.from(r.data, 'base64')) }
let fallos = 0
const ok = (n, v, extra = '') => { if (!v) fallos++; console.log(`${v ? '✓' : '✗'} ${n}${extra ? ' · ' + extra : ''}`) }

try {
  await ir('')
  ok('la invitada entra en el marco de Zazu (Inicio)', await pantalla() === 'inicio')
  ok('Inicio: su tarea y su cita', await hasta(`/Tarea de Invi/.test(document.body.innerText) && /Cita de Invi/.test(document.body.innerText)`))
  const t = await texto()
  ok('Inicio: nada de Fran', !FRAN.some(x => t.includes(x)), FRAN.filter(x => t.includes(x)).join(', '))
  ok('el logo de bits (no el gato)', await js(`!!document.querySelector('.pz-marca svg[aria-label="Zazu"]') && !document.querySelector('img[src*="zazu"]')`))
  if (!movil) {
    const menu = await js(`[...document.querySelectorAll('.pz-lado .pz-nv')].map(b => b.innerText.trim().split('\\n')[0]).join(' | ')`)
    ok('menú: solo sus secciones', menu === 'Agenda | Chats | Hoy y agenda | Tareas | Carpetas | Más', menu)
    ok('sin campana de avisos (son del vigía de Fran)', await js(`!document.querySelector('.pz-top-btn [aria-label^="Avisos"], .pz-top button[aria-label^="Avisos"]')`))
  } else {
    const tabsM = await js(`[...document.querySelectorAll('.pz-tabs .pz-tab')].map(b => b.innerText.trim()).join(' | ')`)
    ok('pestañas del móvil: Chats, Agenda, Carpetas y Más', tabsM === 'Chats | Agenda | Carpetas | Más', tabsM)
  }
  await js(`document.querySelector(${JSON.stringify(movil ? '.pz-tabs button[aria-haspopup="dialog"]' : '.pz-nv-mas')}).click()`); await sleep(500)
  const mas = await js(`[...document.querySelectorAll('.pz-mas-it')].map(b => b.innerText.trim()).join(' | ')`)
  ok('«Más»: solo lo suyo', mas === (movil ? 'Hoy y agenda | Tareas | Rutinas | Ajustes' : 'Rutinas | Ajustes'), mas)
  await foto(`una-app-invitada-${ancho}.png`)
  for (const q of ['?tab=dinero', '?tab=whatsapp', '?tab=zazu', '?tab=empleo', '?tab=tableros&tablero=personas', '?tab=correo', '?tab=explorar', '?tab=cuentas']) {
    await ir(q, 1800)
    const busca = await js('location.search')
    ok(`enlace ${q} vuelve a Inicio`, await pantalla() === 'inicio' && !busca.includes(q.slice(1, q.indexOf('&') > 0 ? q.indexOf('&') : undefined)), busca || '/')
  }
  await ir('?tab=ajustes')
  ok('Ajustes: su espacio (su IA, canales, su Zazu y cerrar sesión) dentro del marco', await pantalla() === 'ajustes' && /Tu espacio/.test(await texto()) && /Cerrar sesión/.test(await texto()))
  await ir('?tab=rutinas')
  ok('Rutinas: las suyas', await pantalla() === 'rutinas' && await hasta(`/Añadir rutina|Aún no tienes rutinas/.test(document.body.innerText)`))
  await ir('?tab=chat')
  ok('Chat: su asistente', await pantalla() === 'chat' && /Soy Zazu/.test(await texto()))
  await ir('?tab=carpetas')
  ok('Carpetas: las suyas', await pantalla() === 'carpetas')
  // escribir en su chat: un mensaje a SU asistente (su perfil), nunca al de Fran
  await ir('?tab=chat', 1800)
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/send*', requestStage: 'Request' }] })   // no llega al hub
  const antes = api.length
  await js(`(()=>{const e=document.querySelector('.composer textarea');e.focus();const set=Object.getOwnPropertyDescriptor(e.constructor.prototype,'value').set;set.call(e,'Hola, ¿qué tal?');e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await js(`document.querySelector('.composer').requestSubmit()`)
  await sleep(2500)
  const env = api.slice(antes).filter(x => x.metodo === 'POST')
  const s = cortados.find(x => x.url.includes('/api/send'))
  const cuerpo = s ? JSON.parse(s.postData || '{}') : {}
  ok('chat: manda el texto a su asistente (perfil zitest)', cuerpo.profile === 'zitest' && cuerpo.text === 'Hola, ¿qué tal?', s ? s.postData.slice(0, 80) : env.map(x => x.url).join(' '))
  ok('chat: nada de /api/captura', !env.some(x => x.url.includes('/api/captura')))
  ok('…y abre el chat', await pantalla() === 'chat', await js('location.search'))
  const prohibidas = api.filter(x => x.status === 403).map(x => new URL(x.url).pathname)
  ok('la web nunca pide algo que no es suyo (ningún 403)', !prohibidas.length, [...new Set(prohibidas)].join(' '))
  ok('consola limpia', !consola.length, consola.slice(0, 3).join(' | '))
} finally {
  try { ws.close() } catch { }
  chrome.kill('SIGKILL'); await sleep(400); rmSync(dir, { recursive: true, force: true })
}
console.log(fallos ? `${fallos} fallo(s)` : 'Todo en orden')
process.exit(fallos ? 1 : 0)
