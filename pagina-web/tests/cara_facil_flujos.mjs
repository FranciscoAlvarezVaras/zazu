#!/usr/bin/env node
// Recorre en un navegador real (Chrome headless, protocolo CDP, sin dependencias) los flujos de la «cara fácil» de Zazu (Fran): el botón «Ordenar todo con Zazu» y su mensaje
// (va al chat de Zazu, perfil tecnico), las frases de la barra, el menú de 7 entradas, Empleo en listas (preparar la carta, «Ya la envié» con la hoja, columnas, ficha),
// el buscador, Dinero (cifras, tabla y filtros), Papeles honesto y los enlaces de siempre (?tab=hermes|byte|zazu|chat|tableros&tablero=…). Sale con código 1 si algo falla.
//
//   1) casa falsa:  bash tests/fakehome.sh /tmp/fh   (y mkdir -p /tmp/fh/.config/hermes-hub/invitadas/zitest/data && echo '{}' > …/data/credentials-web.json)
//   2) la web nueva compilada:  cd web && npx vite build --outDir /tmp/nueva --emptyOutDir
//   3) gateway falso y hub de PRUEBAS (nunca los de verdad, y nunca con los puertos por defecto):
//        python3 tests/fake_gateway.py --port 18903 --home /tmp/fh/.hermes &
//        HOME=/tmp/fh HUB_DEV=1 HUB_PORT=8903 HUB_PUBLIC_PORT=9003 HUB_GATEWAY_URL=http://127.0.0.1:18903 HUB_NO_PUSH=1 HUB_STATIC=/tmp/nueva python3 server.py &
//   4) node tests/cara_facil_flujos.mjs --base http://localhost:8903 --fh /tmp/fh [--ancho 375 --alto 812]
// Mueve una candidatura de la casa falsa (por eso se corre sobre una casa falsa recién hecha). Cada pantalla se abre en un nombre distinto (hN.localhost):
// Chrome solo abre 6 conexiones por origen y las /api/stream (SSE) de las páginas anteriores se las comerían.
import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const sleep = ms => new Promise(r => setTimeout(r, ms))
async function abrir({ ancho = 375, alto = 812, oscuro = false, url, puerto = 9333 + Math.floor(Math.random() * 500), movil = ancho < 700, galleta = '' }) {
  const dir = mkdtempSync(join(tmpdir(), 'cara-flujos-'))
  const p = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars', `--user-data-dir=${dir}`, `--remote-debugging-port=${puerto}`, 'about:blank'], { stdio: 'ignore' })
  let tabs
  for (let i = 0; i < 50; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${puerto}/json`)).json(); if (tabs.length) break } catch { } await sleep(200) }
  const t = tabs.find(x => x.type === 'page')
  const ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise(r => ws.onopen = r)
  let id = 0; const pend = new Map(); const consola = []
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { const { ok, ko } = pend.get(m.id); pend.delete(m.id); m.error ? ko(new Error(JSON.stringify(m.error))) : ok(m.result) } else if (m.method === 'Runtime.consoleAPICalled') consola.push(m.params.args.map(a => a.value ?? a.description).join(' ')); else if (m.method === 'Runtime.exceptionThrown') consola.push('EXC ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text)) }
  const send = (method, params = {}) => new Promise((ok, ko) => { const i = ++id; pend.set(i, { ok, ko }); ws.send(JSON.stringify({ id: i, method, params })) })
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable')
  
  await send('Emulation.setDeviceMetricsOverride', { width: ancho, height: alto, deviceScaleFactor: 1, mobile: movil })
  if (movil) await send('Emulation.setTouchEmulationEnabled', { enabled: true })
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: oscuro ? 'dark' : 'light' }] })
  let rot = 0
  const api = {
    consola, send, ws,
    // cada página va a un nombre distinto (hN.localhost, que apunta a esta máquina): Chrome tiene un máximo de 6 conexiones por origen en HTTP/1.1
    // y las /api/stream (SSE) de las páginas anteriores se las comerían todas
    async ir(u, espera = 1500) { await send('Page.navigate', { url: 'about:blank' }); await sleep(150); u = u.replace(/\/\/(localhost|[a-z0-9]+\.localhost):/, `//h${rot++ % 20}.localhost:`); if (galleta) await send('Network.setCookie', { name: 'hub_s', value: galleta, url: new URL(u).origin + '/' }); await send('Page.navigate', { url: u }); await sleep(espera) },
    async js(expr) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value },
    async foto(f) { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(f, Buffer.from(r.data, 'base64')) },
    async clic(sel, texto) { return api.js(`(()=>{const l=[...document.querySelectorAll(${JSON.stringify(sel)})];const e=${texto ? `l.find(x=>x.textContent.includes(${JSON.stringify(texto)}))` : 'l[0]'};if(!e)return false;e.click();return true})()`) },
    async escribir(sel, texto) {
      await api.js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.focus();const set=Object.getOwnPropertyDescriptor(e.constructor.prototype,'value').set;set.call(e,${JSON.stringify(texto)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
    },
    async tema(oscuroSi) { await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: oscuroSi ? 'dark' : 'light' }] }) },
    async esperar(ms) { await sleep(ms) },
    async cerrar() { try { ws.close() } catch { } p.kill('SIGKILL'); await sleep(400); rmSync(dir, { recursive: true, force: true }) },   // el perfil temporal se borra siempre
  }
  if (url) await api.ir(url)
  return api
}

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d }
const [ancho, alto] = [arg('ancho', '1280'), arg('alto', '800')]
const BASE = arg('base', 'http://localhost:8903') + '/'
const FH = arg('fh', '/tmp/fh') + '/'
let fallos = 0
const peticiones = () => { try { return readFileSync(FH + 'peticiones.jsonl', 'utf8').trim().split('\n').map(l => JSON.parse(l)) } catch { return [] } }
const c = await abrir({ ancho: +ancho, alto: +alto, url: BASE + '?tab=ajustes' })
await c.js(`localStorage.setItem('zazu:tema','claro')`)
const ok = (n, v, extra = '') => { if (!v) fallos++; console.log(`${v ? '✓' : '✗'} ${n}${extra ? ' · ' + extra : ''}`) }
const url = () => c.js('location.pathname+location.search')
const txt = sel => c.js(`document.querySelector(${JSON.stringify(sel)})?.innerText||''`)
const hasta = async (expr, ms = 9000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await c.js(expr)) return true; await c.esperar(250) } return false }
const movil = +ancho < 900
const ORDENA = 'Ordena todo: revisa mis tareas sin fecha o vencidas'
const envios = (desde) => peticiones().slice(desde).filter(p => p.metodo === 'POST' && p.ruta.endsWith('/v1/runs'))

// 1) «Ordenar todo con Zazu»: en el móvil, la tarjeta de Inicio; en el ordenador (2026-10-22), dentro de «Más» del menú de la izquierda.
//    Abre el chat de Zazu (perfil tecnico) con el mensaje YA enviado
await c.ir(BASE + '?tab=inicio&vista=hoy', 2000)
let n0 = peticiones().length
if (movil) ok('Inicio (móvil): tarjeta «Ordenar todo con Zazu» con su ayuda', /Ordenar todo con Zazu/.test(await txt('.pz-ordena')) && /los apruebas/.test(await txt('.pz-ordena')))
else {
  ok('Inicio (ordenador): la tarjeta de Inicio NO se duplica', (await c.js(`getComputedStyle(document.querySelector('.pz-ordena')).display`)) === 'none')
  await c.js(`document.querySelector('.pz-lado-mas').open=true`); await c.esperar(200)
  ok('menú lateral › Más: «Ordenar todo con Zazu»', await c.js(`!![...document.querySelectorAll('.pz-lado-mas .pz-mas-it')].find(b=>b.textContent.includes('Ordenar todo con Zazu'))`))
}
if (movil) await c.clic('.pz-ordena button'); else await c.clic('.pz-lado-mas .pz-mas-it', 'Ordenar todo')
await c.esperar(3500)
let e = envios(n0)
ok('«Ordenar todo» manda el mensaje al gateway (perfil tecnico)', e.length === 1 && e[0].ruta.includes('/p/tecnico/') && (e[0].cuerpo.input || '').startsWith(ORDENA), e[0] ? e[0].ruta : 'sin envío')
ok('…y abre el chat', (await url()).startsWith('/?tab=chat'), await url())
// 2) (la barra de órdenes de Inicio ya no existe: se escribe solo en el chat)
// 3) «Todo» (móvil: el cajón) › Más › Ordenar
if (movil) {
  await c.ir(BASE + '?tab=tareas', 1800); n0 = peticiones().length
  await c.clic('.pz-tabs button', 'Todo'); await c.esperar(500)
  ok('«Todo» (móvil) abre el cajón con «Nuevo chat»', await c.js(`!!document.querySelector('.pz-cajon .pz-nuevo')`))
  await c.js(`document.querySelector('.pz-cajon .pz-lado-mas').open=true`); await c.esperar(200)
  ok('el cajón › Más enseña «Ordenar todo con Zazu»', await c.js(`!![...document.querySelectorAll('.pz-cajon .pz-mas-it')].find(b=>b.textContent.includes('Ordenar'))`))
  await c.clic('.pz-cajon .pz-mas-it', 'Ordenar'); await c.esperar(3500)
  e = envios(n0)
  ok('«Más › Ordenar» manda el mismo mensaje', e.length === 1 && (e[0].cuerpo.input || '').startsWith(ORDENA))
  ok('…y el cajón se cierra', !(await c.js(`!!document.querySelector('.pz-cajon')`)))
}
// 4) menú de la izquierda (ordenador): «Nuevo chat», «Buscar», las secciones (Agenda la primera, con Chats) y «Más» plegado
if (!movil) {
  await c.ir(BASE + '?tab=inicio', 1800)
  const acc = await c.js(`[...document.querySelectorAll('.pz-lado .pz-lado-acc .pz-nv')].map(b=>b.innerText.trim())`)
  ok('menú lateral: «Nuevo chat» y «Buscar» arriba', acc[0] === 'Nuevo chat' && acc[1] === 'Buscar', acc.join(' | '))
  const ent = await c.js(`[...document.querySelectorAll('.pz-lado-nav > .pz-nv')].map(b=>b.innerText.replace(/\\s+/g,' ').trim())`)
  ok('menú lateral: Agenda la primera, con Chats', ent[0] === 'Agenda' && ent.includes('Chats') && (await c.js(`!!document.querySelector('.pz-lado-mas > summary')`)), ent.join(' | '))
}
// 5) Empleo: listas, preparar carta, ya la envié, ficha, columnas
await c.ir(BASE + '?tab=empleo', 800); await hasta(`!!document.querySelector('.pz-lista-card')`)
ok('Empleo: frase resumen', /Tienes \d+ candidaturas? abiertas?/.test(await txt('.pz-resumen')), await txt('.pz-resumen'))
ok('Empleo: grupos con frases claras', /Para hacer ahora/.test(await txt('.pz-page')) && /Prueba o entrevista/.test(await txt('.pz-page')))
if (!movil) {
  await c.clic('.pz-lf-acc button', 'Preparar la carta'); await c.esperar(1500)
  ok('«Preparar la carta» abre el chat con la petición escrita (sin enviar)', (await url()).startsWith('/?tab=chat') && /Prepárame la carta/.test(await c.js(`document.querySelector('.composer textarea')?.value||''`)))
  await c.ir(BASE + '?tab=empleo', 800); await hasta(`!!document.querySelector('.pz-lista-card')`)
  await c.clic('.pz-lf-acc button', 'Ya la envié'); await c.esperar(600)
  ok('«Ya la envié» abre la hoja «¿Qué ha pasado?» con «Ya la envié» el primero', /¿Qué ha pasado\?/.test(await txt('.pz-hoja')) && /^Ya la envié/.test(await c.js(`document.querySelector('.pz-hoja .pz-opcion')?.innerText||''`)), await c.js(`document.querySelector('.pz-hoja .pz-opcion')?.innerText.replace(/\\s+/g,' ')`))
  await c.js(`document.querySelector('.pz-hoja .pz-opcion').click()`); await c.esperar(1800)
  ok('mover actualiza la lista', /1 candidatura enviada|Esperando respuesta/.test(await txt('.pz-page')), '')
  await c.clic('.pz-cab-acc .pz-enlace', 'columnas'); await c.esperar(600)
  ok('«Ver como columnas» enseña el tablero de siempre', (await c.js(`document.querySelectorAll('.pz-columna').length`)) >= 5 && /vista=columnas/.test(await url()), await url())
  await c.ir(BASE + '?tab=tableros&tablero=candidaturas', 800); await hasta(`!!document.querySelector('.pz-lista-card')`)
  ok('enlace viejo ?tab=tableros&tablero=candidaturas sigue funcionando', /Para hacer ahora|Esperando respuesta/.test(await txt('.pz-page')))
}
// 6) buscador
if (!movil) {
  await c.ir(BASE + '?tab=inicio', 1800)
  await c.clic('.pz-lado-acc .pz-nv', 'Buscar'); await c.esperar(400)   // 2026-10-22: «Buscar» del menú abre la hoja con el buscador
  await c.escribir('.pz-buscador input', 'Acme'); await c.esperar(500)
  const r = await c.js(`[...document.querySelectorAll('.pz-buscador-lista li')].map(l=>l.innerText.replace(/\\s+/g,' '))`)
  ok('buscador: encuentra la candidatura', r.some(x => /Dev|Acme/.test(x)), r.join(' | '))
  await c.js(`document.querySelector('.pz-buscador-lista li button').click()`); await c.esperar(1200)
  ok('buscador: abre la ficha', /tab=empleo&tarjeta=/.test(await url()) && /Qué toca ahora/.test(await txt('.pz-page')), await url())
}
// 7) Dinero
await c.ir(BASE + '?tab=dinero', 800); await hasta(`document.querySelectorAll('.pz-tabla tbody tr').length>3`)
ok('Dinero: cifras + tabla', (await c.js(`document.querySelectorAll('.pz-cifra-card').length`)) >= 3 && (await c.js(`document.querySelectorAll('.pz-tabla tbody tr').length`)) > 3)
await c.clic('.pz-pestanas button', 'Para cancelar'); await c.esperar(300)
ok('Dinero: filtro «Para cancelar»', (await c.js(`[...document.querySelectorAll('.pz-tabla tbody tr')].every(r=>/Para cancelar/.test(r.innerText))`)))
await c.ir(BASE + '?tab=tableros&tablero=suscripciones', 800); await hasta(`document.querySelectorAll('.pz-tabla').length===1`)
ok('enlace viejo ?tablero=suscripciones enseña Dinero', /Suscripciones/.test(await txt('.pz-page')) && (await c.js(`document.querySelectorAll('.pz-tabla').length`)) === 1)
// 8) Papeles (sin archivador en la casa falsa: pantalla honesta)
await c.ir(BASE + '?tab=papeles', 800); await hasta(`!/Mirando/.test(document.body.innerText)`)
ok('Papeles: pantalla honesta sin datos inventados', /Todavía no hay nada que enseñar|Zazu revisa tus papeles/.test(await txt('.pz-page')) && !/\d+ papeles? por revisar/.test(await txt('.pz-page')), (await txt('.pz-resumen')))
// 9) enlaces profundos de siempre
for (const q of ['?tab=hermes', '?tab=byte', '?tab=zazu', '?tab=chat', '?tab=tableros&tablero=proyectos', '?tab=tableros&tablero=carnet', '?tab=tableros&tablero=personas', '?tab=tableros', '?tab=zazu&vista=registro', '?tab=midia', '?tab=hoy']) {
  await c.ir(BASE + q, 1800)
  const pant = await c.js(`document.querySelector('.pz-app')?.dataset.pantalla`)
  const hay = await c.js(`!!document.querySelector('#pz-main h1, #pz-main h2, #pz-main .chatbar')`)
  ok(`enlace ${q}`, !!pant && hay, `pantalla=${pant}`)
}
console.log(c.consola.filter(x => !/favicon|Failed to load resource|fonts/.test(x)).join('\n') || '(consola limpia)')
await c.cerrar()
console.log(fallos ? `${fallos} comprobaciones fallan` : 'Todo en orden')
process.exit(fallos ? 1 : 0)
