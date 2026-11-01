import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, hm, isoDay, post } from './lib'
import type { Session } from './lib'
import { modoDe } from './tipos'
import type { Aprobacion, ChatApi, Cur, Decision, Item, Modo, Paso, PasoVivo, PreguntaChat, Rutina, Vivo } from './tipos'
import * as H from './chat/api'
import './hermes.css'

// calls[].id y call_id: el servidor los añade para emparejar cada llamada con su resultado
type ApiMsg = { id: number; profile?: string; session: string; role: string; content: string; tool?: string; call_id?: string; calls?: { name: string; args: string; id?: string; cortado?: number }[]; ts: number }
/** /api/job: lo que el hub cuenta de un trabajo (nunca trae el código de permiso). */
type JobApi = { done?: boolean; error?: string | null; session_id?: string | null; profile?: string; modo?: Modo; modelo?: string | null; estado?: string; texto?: string; pasos?: PasoVivo[]; aprobacion?: Aprobacion | null; ultima?: Vivo['ultima'] }
type Envio = { job: string | null; nota?: string; token?: string; session?: string }

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
/** /api/job de un trabajo. Sin su código (lo empezó otro navegador) va con ajeno=1: mirarlo no cuenta como «Fran está mirando»
 *  y el hub sigue mandando la notificación del permiso. */
const urlJob = (job: string) => `/api/job?id=${encodeURIComponent(job)}${H.tokenDe(job) ? '' : '&ajeno=1'}`
/** Espera a que la app esté a la vista: en segundo plano no se pregunta, así el hub sabe que nadie mira y avisa con una notificación. */
const aLaVista = () => new Promise<void>(r => {
  if (!document.hidden) return r()
  const f = () => { if (!document.hidden) { document.removeEventListener('visibilitychange', f); r() } }
  document.addEventListener('visibilitychange', f)
})
const key = (c: Cur) => `${c.profile}/${c.id}`
const FIN = new Set(['terminado', 'fallo', 'parado', 'sin_respuesta'])
/** Orígenes de la app (lo que una respuesta que no llegó se puede reintentar desde aquí). */
const DE_LA_APP = new Set(['', 'hub', 'api_server'])
const PERDIDO = 'job desconocido'   // el hub ya no lo conoce (reinicio o purga): la respuesta, si llegó, está en el historial
const SIN_CODIGO = 'Aprueba desde el dispositivo donde lo pediste o desde la notificación'
/** Las conversaciones de WhatsApp se leen aquí, pero se siguen en WhatsApp (el servidor responde 409). */
export const SOLO_WA = 'Esta conversación es de WhatsApp: sigue en WhatsApp.'

/** Añade un mensaje de la API a la lista visible; los pasos de herramientas consecutivos se agrupan.
 *  El texto de una respuesta va antes de sus pasos («Voy a mirarlo.» y luego lo que hizo).
 *  Cada resultado va con su llamada: por call_id (aunque esté en un grupo anterior); si no, la primera de ese nombre sin resultado. */
function addMsg(items: Item[], m: ApiMsg): Item[] {
  const out = [...items]
  const ultimoGrupo = () => { const l = out[out.length - 1]; return l && l.kind === 'work' ? out.length - 1 : -1 }
  const conPasos = (i: number, pasos: Paso[]) => { out[i] = { ...(out[i] as Extract<Item, { kind: 'work' }>), pasos } }
  if (m.role === 'tool') {
    const nombre = m.tool || 'herramienta', r = H.leerResultado(m.content || ''), resultado = r.texto.slice(0, 4000)
    const libre = (p: Paso) => p.resultado === undefined
    // 1) por call_id, del grupo más reciente hacia atrás
    if (m.call_id) for (let g = out.length - 1; g >= 0; g--) {
      const it = out[g]
      if (it.kind !== 'work') continue
      const j = it.pasos.findIndex(p => p.id === m.call_id && libre(p))
      if (j >= 0) { const ps = [...it.pasos]; ps[j] = { ...ps[j], resultado, error: r.error }; conPasos(g, ps); return out }
    }
    // 2) por nombre en el último grupo; 3) si no, paso suelto
    const g = ultimoGrupo()
    const ps = g >= 0 ? [...(out[g] as Extract<Item, { kind: 'work' }>).pasos] : []
    const j = ps.findIndex(p => p.herramienta === nombre && libre(p))
    if (j >= 0) ps[j] = { ...ps[j], resultado, error: r.error }
    else ps.push({ id: m.call_id, herramienta: nombre, args: '', resultado, error: r.error })
    if (g >= 0) conPasos(g, ps); else out.push({ kind: 'work', id: m.id, pasos: ps })
    return out
  }
  const texto = m.role === 'user' && /^\[Session was just handed off/.test(m.content || '') ? '↪ Conversación pasada a WhatsApp'
    : m.role === 'user' && (m.content || '').startsWith('[DATOS recogidos') ? (m.content.split('[FIN DE LOS DATOS]')[1] || '').trim() : m.content   // avisos internos / datos inyectados
  if ((texto || '').trim()) out.push({ kind: 'msg', id: m.id, role: m.role === 'user' ? 'user' : 'assistant', text: texto, time: hm(m.ts), dia: diaDe(m.ts), ts: segundos(m.ts) })
  if (m.calls?.length) {
    const nuevos = m.calls.map(c => ({ id: c.id, herramienta: c.name, args: c.args, ...(c.cortado ? { cortado: c.cortado } : {}) }))
    const g = ultimoGrupo()
    if (g >= 0) conPasos(g, [...(out[g] as Extract<Item, { kind: 'work' }>).pasos, ...nuevos])
    else out.push({ kind: 'work', id: m.id, pasos: nuevos })
  }
  return out
}

/** Día (AAAA-MM-DD) de un mensaje, para los separadores del hilo. */
const diaDe = (v: string | number | null | undefined) => {
  if (v === null || v === undefined || v === '') return undefined
  const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v)
  return isNaN(d.getTime()) ? undefined : isoDay(d)
}
const segundos = (v: string | number | null | undefined) => { if (v === null || v === undefined || v === '') return undefined; const n = typeof v === 'number' ? v : new Date(v).getTime() / 1000; return isNaN(n) ? undefined : n >= 1e12 ? n / 1000 : n }
/** El hilo seguido de un chat, tal como lo da /api/hilo. */
type Hilo = { profile: string; sesion: string | null; abrir: boolean; fuente: string | null; anteriores: ApiMsg[]; rutinas?: Rutina[]; nuevos?: number }
/** A partir de cuánto sin actividad (segundos) se pregunta «¿seguimos o empiezas una nueva?» al volver a un chat. */
const PAUSA_PREGUNTA = 30 * 60

/** De dónde viene la conversación actual (hub, whatsapp, cli…). */
const fuenteDe = (c: Cur, ss: Session[]) => c.id ? c.source ?? ss.find(s => s.id === c.id && (s.profile || 'default') === c.profile)?.source ?? '' : ''

const plano = (s: string) => s.replace(/\s+/g, ' ').trim()
/** Quita del texto en directo lo que ya está guardado al principio (sin mirar espacios): p. ej. tras un permiso denegado
 *  el hub no empieza segmento nuevo y el texto trae delante el mensaje anterior. */
function sinPrefijo(raw: string, prefijo: string): string | null {
  const p = prefijo.replace(/\s+/g, '')
  if (!p) return null
  let i = 0, j = 0
  while (j < p.length && i < raw.length) { if (/\s/.test(raw[i])) { i++; continue } if (raw[i] !== p[j]) return null; i++; j++ }
  return j === p.length ? raw.slice(i) : null
}
/** ¿Tu último mensaje se quedó sin respuesta? (después solo hay pasos, o nada) */
function sinRespuesta(items: Item[]): boolean {
  let u = items.length - 1
  while (u >= 0) { const it = items[u]; if (it.kind === 'msg' && it.role === 'user') break; u-- }
  return u >= 0 && !items.slice(u + 1).some(i => i.kind === 'msg')
}
/** Lo que se ve en directo, quitando lo que ya está guardado: el texto provisional se oculta cuando el último mensaje
 *  guardado de la respuesta empieza igual (o, al terminar, cuando ya hay respuesta guardada). Terminado y guardado: nada;
 *  parado o fallido: queda la nota (con «Reintentar») aunque no haya texto. */
function aLaVistaDe(v: Vivo | null, items: Item[]): Vivo | null {
  if (!v) return null
  if (v.estado === 'sin_respuesta') return sinRespuesta(items) ? v : null   // llegó la respuesta: fuera la nota
  let u = items.length - 1
  while (u >= 0) { const it = items[u]; if (it.kind === 'msg' && it.role === 'user') break; u-- }
  const suyas = items.slice(u + 1).filter((i): i is Extract<Item, { kind: 'msg' }> => i.kind === 'msg' && i.role === 'assistant')
  let texto = v.texto
  for (const m of suyas) { const r = sinPrefijo(texto, m.text); if (r !== null) texto = r.replace(/^\s+/, '') }
  const fin = FIN.has(v.estado), t = plano(texto)
  const ultima = suyas[suyas.length - 1]
  const guardado = !t || (fin ? suyas.length > 0 : !!ultima && plano(ultima.text).startsWith(t.slice(0, 40)))
  if (fin && guardado) return v.estado === 'parado' || v.estado === 'fallo' ? (v.texto ? { ...v, texto: '' } : v) : null
  return guardado ? (v.texto ? { ...v, texto: '' } : v) : texto === v.texto ? v : { ...v, texto }
}

export function useChat(): ChatApi {
  const [sessions, setSessions] = useState<Session[]>([])
  const [cur, setCur] = useState<Cur>({ id: null, profile: 'default', modo: 'zazu' })
  const [items, setItems] = useState<Item[]>([])
  const [pending, setPending] = useState(false)
  const [profiles, setProfiles] = useState<string[]>(['default'])
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [vivos, setVivos] = useState<Record<string, Vivo>>({})              // conversación → lo que pasa ahora en su respuesta
  const [elegido, setElegido] = useState<{ k: string; id: string } | null>(null)   // modelo elegido en esta conversación
  const [contacto, setContacto] = useState<string | null>(null)   // chat seguido abierto (tecnico, whatsapp, viajes…); null = conversación suelta
  const [anteriores, setAnteriores] = useState<Item[]>([])        // lo dicho en las conversaciones anteriores de ese chat (se ve encima)
  const [rutinas, setRutinas] = useState<Rutina[]>([])            // lo que ese asistente te escribió por su cuenta
  const [pregunta, setPregunta] = useState<PreguntaChat | null>(null)   // «¿seguimos con la anterior o empiezas una nueva?» al volver tras un rato
  const contactoRef = useRef<string | null>(null)
  const abriendo = useRef<{ id: string; token: object; p: Promise<void> } | null>(null)
  const { modelos } = H.useModelos(cur.modo === 'hermes')
  const curRef = useRef(cur)
  const sessRef = useRef<Session[]>([])
  sessRef.current = sessions
  const vivosRef = useRef(vivos)
  vivosRef.current = vivos
  const itemsRef = useRef(items)
  itemsRef.current = items
  const lastId = useRef(0)
  const gen = useRef(0)                                  // cada conversación nueva es otra (aunque su clave sea «perfil/null»)
  const busy = useRef(new Set<string>())                 // conversaciones con respuesta en marcha
  const jobs = useRef<Record<string, string>>({})        // conversación → trabajo en marcha
  const siguiendo = useRef(new Set<string>())            // trabajos que ya se están preguntando
  const parando = useRef(new Set<string>())
  const pararAlEmpezar = useRef(new Set<string>())       // «Parar» antes de que el hub diera el número de trabajo
  const resueltas = useRef(new Set<string>())            // permisos ya respondidos desde aquí (una pregunta lenta no los resucita)
  const esperaSesion = useRef<Record<string, { ok: () => void; ko: (e: Error) => void }>>({})
  const ctxDe = useRef(new Map<string, string>())        // texto enviado → sus datos (ctx), para «Reintentar»
  const modeloRef = useRef<string | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const catchRef = useRef<(() => Promise<void>) | null>(null)   // «ponerse al día» con lo que llegó mientras no había conexión (se asigna más abajo)

  /** Clave de la conversación que se ve: las nuevas llevan su número para no mezclarse entre sí. */
  const kDe = (c: Cur, g = gen.current) => c.id ? key(c) : `${key(c)}#${g}`
  const kActual = () => kDe(curRef.current)

  const loadSessions = useCallback(async () => { try { setSessions(await api<Session[]>('/api/sessions')) } catch { /* se reintenta */ } }, [])
  const soon = useCallback(() => { clearTimeout(timer.current); timer.current = window.setTimeout(loadSessions, 600) }, [loadSessions])

  const loadProfiles = useCallback(async () => { try { setProfiles(await api<string[]>('/api/profiles')) } catch { /* se reintenta al volver a la app */ } }, [])

  useEffect(() => {
    void loadProfiles()
    loadSessions()
    const t = setInterval(() => { if (!document.hidden) loadSessions() }, 20000)   // en segundo plano no se pregunta (batería)
    const vis = () => { if (!document.hidden) { loadSessions(); void loadProfiles(); void catchRef.current?.().catch(() => { /* llegará por /api/stream */ }) } }   // al volver a la app, la lista al día (y los asistentes, por si la primera carga falló)
    document.addEventListener('visibilitychange', vis)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', vis) }
  }, [loadSessions, loadProfiles])

  const push = useCallback((m: ApiMsg) => {
    const c = curRef.current
    if ((m.profile || 'default') !== c.profile || m.session !== c.id || m.id <= lastId.current) return
    lastId.current = m.id
    setItems(prev => addMsg(prev.filter(i => i.id > 0), m))   // llega lo guardado: fuera el mensaje provisional
  }, [])

  // mensajes en vivo
  useEffect(() => {
    let es: EventSource | null = null
    let t: number | undefined
    let dead = false, abierto = false
    const connect = () => {
      es = new EventSource('/api/stream')
      // la conexión en vivo empieza en lo último que hay: tras una caída (el móvil dormido, un túnel que se corta) lo ocurrido entre medias no llegaba hasta reabrir la conversación
      es.onopen = () => { if (abierto) void catchRef.current?.().catch(() => { /* se verá al reabrir */ }); abierto = true }
      es.onmessage = e => { push(JSON.parse(e.data)); soon() }
      // con la sesión caducada el stream da 401 en bucle (y el guardia lo cuenta como escáner y bloquea la IP): se comprueba con /api/me, que sí lleva a «entrar»
      es.onerror = () => { es?.close(); void api('/api/me').catch(() => { /* si es 401, ya se va a la pantalla de entrar */ }); if (!dead) t = window.setTimeout(connect, 3000) }
    }
    connect()
    return () => { dead = true; es?.close(); clearTimeout(t) }
  }, [push, soon])

  const setCurrent = (c: Cur) => { curRef.current = c; setCur(c) }
  const marcar = (k: string, on: boolean) => { if (on) busy.current.add(k); else busy.current.delete(k); if (k === kActual()) setPending(on) }
  const quitarVivo = (k: string, job?: string) => setVivos(v => { if (!v[k] || (job && v[k].job !== job && v[k].job)) return v; const n = { ...v }; delete n[k]; return n })

  /** Lo último que dijo el hub de un trabajo → lo que se ve en directo. */
  const ponerVivo = useCallback((k: string, job: string, j: JobApi) => {
    const a = j.aprobacion && !resueltas.current.has(j.aprobacion.id) ? j.aprobacion : null
    const estado = parando.current.has(job) && !j.done ? 'parando' : j.estado || (j.done ? (j.error ? 'fallo' : 'terminado') : 'en_marcha')
    setVivos(v => ({ ...v, [k]: { job, modo: j.modo || modoDe(j.profile), estado: a ? 'esperando_permiso' : estado === 'esperando_permiso' ? 'en_marcha' : estado, texto: j.texto || '', pasos: j.pasos || [], aprobacion: a, ultima: j.ultima ?? v[k]?.ultima ?? null, puedeAprobar: !!H.tokenDe(job), error: j.error ?? null } }))
  }, [])

  /** Una conversación nueva ya tiene sesión: todo lo de su clave provisional pasa a la definitiva. */
  const moverClave = (de: string, a: string) => {
    if (de === a) return
    if (busy.current.delete(de)) busy.current.add(a)
    if (jobs.current[de]) { jobs.current[a] = jobs.current[de]; delete jobs.current[de] }
    if (pararAlEmpezar.current.delete(de)) pararAlEmpezar.current.add(a)
    setVivos(v => { if (!v[de]) return v; const n = { ...v, [a]: v[de] }; delete n[de]; return n })
    setElegido(e => e?.k === de ? { k: a, id: e.id } : e)
  }

  /** Abre una conversación. `conservar`: lo que ya se veía (el mensaje recién enviado) mientras no haya nada guardado. */
  const abrir = useCallback(async (c: Cur, conservar?: Item[]): Promise<ApiMsg[] | undefined> => {
    gen.current++
    const k = kDe(c)
    setCurrent(c); lastId.current = 0; setItems(conservar || []); setPending(busy.current.has(k))
    let ms: ApiMsg[]
    try { ms = await api<ApiMsg[]>(`/api/messages?session=${encodeURIComponent(c.id || '')}&profile=${encodeURIComponent(c.profile)}`) }
    catch (e) { if (conservar) return; throw e }
    if (kActual() !== k) return
    let acc: Item[] = []
    for (const m of ms) { acc = addMsg(acc, m); lastId.current = Math.max(lastId.current, m.id) }
    setItems(acc.length || !conservar ? acc : conservar)
    void reanudar(k, sinRespuesta(acc))
    return ms
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /** Si no se puede abrir, se avisa y se vuelve a lo que se veía: así tocarla otra vez lo reintenta. */
  const open = useCallback(async (id: string, profile = 'default', source?: string) => {
    setContacto(null); contactoRef.current = null; setAnteriores([]); setRutinas([]); setPregunta(null)   // una conversación suelta: fuera del chat seguido
    const antes = { c: curRef.current, items: itemsRef.current, last: lastId.current, g: gen.current }
    try { await abrir({ id, profile, source, modo: modoDe(profile) }) }
    catch (e) {
      const c = curRef.current
      if (c.id !== id || c.profile !== profile) return   // ya se abrió otra cosa
      gen.current = antes.g; setCurrent(antes.c); lastId.current = antes.last; setItems(antes.items); setPending(busy.current.has(kDe(antes.c)))
      setError(`No se pudo abrir la conversación: ${(e as Error).message}`)
    }
  }, [abrir]) // eslint-disable-line react-hooks/exhaustive-deps

  const nuevaInterna = useCallback((profile = 'default') => {
    gen.current++
    setCurrent({ id: null, profile, modo: modoDe(profile) }); lastId.current = 0; setItems([]); setPending(false)
    if (modoDe(profile) === 'zazu') void reanudarNueva(profile, kActual())   // una respuesta que quedó en marcha al cerrarse la app se retoma
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  /** Conversación nueva suelta (fuera del chat seguido). */
  const newChat = useCallback((profile = 'default') => { setContacto(null); contactoRef.current = null; setAnteriores([]); setRutinas([]); setPregunta(null); nuevaInterna(profile) }, [nuevaInterna])

  /** El chat seguido con un contacto: se cargan sus conversaciones anteriores (quedan encima) y se abre la última si es reciente
   *  (o de WhatsApp, solo lectura); si no, lo siguiente que escribas empieza conversación nueva sin que se note. */
  const abrirContacto = useCallback((id: string, o?: { preguntar?: boolean }): Promise<void> => {
    if (abriendo.current?.id === id) return abriendo.current.p   // ya se está abriendo (p. ej. la URL y una petición a la vez): la misma espera
    if (contactoRef.current === id && kActual().startsWith(`${id === 'whatsapp' ? 'default' : id}/`)) return Promise.resolve()
    const token = {}
    const p = (async () => {
      try {
        const h = await api<Hilo>(`/api/hilo?contacto=${encodeURIComponent(id)}`)
        if (abriendo.current?.token !== token) return   // mientras tanto se pidió otro
        setPregunta(null)
        let acc: Item[] = []
        for (const m of h.anteriores) acc = addMsg(acc, m)
        const abiertos = h.abrir && h.sesion ? await abrir({ id: h.sesion, profile: h.profile, source: h.fuente || undefined, modo: modoDe(h.profile) }) : undefined
        if (!(h.abrir && h.sesion)) nuevaInterna(h.profile)
        contactoRef.current = id; setContacto(id); setAnteriores(acc); setRutinas(h.rutinas || [])
        // al entrar en el chat (no al mandar algo desde otra pantalla): si la última conversación lleva un rato parada, se pregunta antes de seguir en ella
        if (o?.preguntar && h.sesion && id !== 'whatsapp' && h.fuente !== 'whatsapp' && !busy.current.has(kActual())) {
          const suyos = [...(abiertos || []), ...h.anteriores].filter(m => m.session === h.sesion)
          const desde = Math.max(0, ...suyos.map(m => segundos(m.ts) || 0))
          const primero = suyos.find(m => m.role === 'user' && (m.content || '').trim() && !m.content.startsWith('['))?.content || ''
          if (desde && Date.now() / 1000 - desde > PAUSA_PREGUNTA) setPregunta({ contacto: id, sesion: h.sesion, profile: h.profile, desde, titulo: plano(primero).slice(0, 60) })
        }
        if (h.nuevos) post('/api/hilo/visto', { contacto: id }).catch(() => { /* se marcará la próxima vez */ })   // ya lo has visto
      } finally { if (abriendo.current?.token === token) abriendo.current = null }
    })()
    abriendo.current = { id, token, p }
    return p
  }, [abrir, nuevaInterna]) // eslint-disable-line react-hooks/exhaustive-deps

  const catchUp = useCallback(async () => {
    const c = curRef.current
    if (!c.id) return
    const ms = await api<ApiMsg[]>(`/api/messages?session=${encodeURIComponent(c.id)}&profile=${encodeURIComponent(c.profile)}&after=${lastId.current}`)
    ms.forEach(push)
  }, [push])
  catchRef.current = catchUp

  /** El trabajo terminó (bien, con error, parado o perdido). */
  const terminar = useCallback(async (job: string, k: string, j: JobApi) => {
    marcar(k, false); delete jobs.current[k]; parando.current.delete(job); pararAlEmpezar.current.delete(k)
    H.olvidarJob(k, job)
    if (k.includes('/null#')) H.olvidarJob(`${k.split('/')[0]}/null`, job)   // la conversación nueva que no llegó a tener sesión
    H.borrarToken(job)
    const espera = esperaSesion.current[job]; delete esperaSesion.current[job]
    const perdido = j.error === PERDIDO
    if (perdido) quitarVivo(k, job)
    if (kActual() === k) { try { await catchUp() } catch { /* llegará por /api/stream */ } }
    if (espera && !j.session_id) { espera.ko(new Error(j.error && !perdido ? j.error : 'No se pudo crear la conversación')); quitarVivo(k, job); void H.diag('sesion', j.error || 'sin sesión', k.split('/')[0]) }
    else if (j.error && !perdido && j.estado !== 'parado') { setError(`No se pudo responder: ${j.error}`); void H.diag('responder', j.error, k.split('/')[0]) }
    loadSessions()
  }, [catchUp, loadSessions]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Pregunta al hub cada segundo (solo con la app a la vista) hasta que el trabajo termina. */
  const seguir = useCallback(async (job: string, k0: string, perfil: string) => {
    if (siguiendo.current.has(job)) return
    siguiendo.current.add(job)
    let k = k0, fallos = 0, n = 0
    const t0 = Date.now()
    try {
      while (Date.now() - t0 < 3 * 3600e3) {
        await sleep(1000); await aLaVista()
        let j: JobApi
        try { j = await api<JobApi>(urlJob(job)); fallos = 0 }
        catch { if (++fallos > 600) break; continue }
        // conversación nueva de un perfil de un solo disparo: en cuanto existe la sesión, se abre (si sigues en ella)
        if (k.includes('/null#') && j.session_id) {
          const nueva = `${j.profile || perfil}/${j.session_id}`, eraLaActual = kActual() === k
          moverClave(k, nueva); k = nueva
          H.olvidarJob(`${perfil}/null`, job); H.registrarJob(k, job)
          esperaSesion.current[job]?.ok(); delete esperaSesion.current[job]
          if (eraLaActual) await abrir({ id: j.session_id, profile: j.profile || perfil, modo: modoDe(j.profile || perfil) }, itemsRef.current)
        }
        if (j.error !== PERDIDO) ponerVivo(k, job, j)
        if (j.done) { await terminar(job, k, j); return }
        if (++n % 60 === 0 && !k.includes('/null#')) H.registrarJob(k, job)   // sigue vivo: que se pueda retomar al recargar
      }
      await terminar(job, k, { done: true })
    } finally { siguiendo.current.delete(job) }
  }, [abrir, ponerVivo, terminar]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Tu último mensaje no tiene respuesta y no hay nada en marcha: nota «sin respuesta» con «Reintentar» (solo en conversaciones de la app). */
  const notaSinRespuesta = async (k: string) => {
    const c = curRef.current
    if (kActual() !== k || !c.id) return
    const de = (ss: Session[]) => ss.find(s => s.id === c.id && (s.profile || 'default') === c.profile)
    let s = de(sessRef.current)
    if (!s) { try { s = de(await api<Session[]>('/api/sessions')) } catch { return } }
    if (!s || !DE_LA_APP.has(s.source || '') || kActual() !== k || busy.current.has(k)) return
    setVivos(v => v[k] && v[k].estado !== 'terminado' ? v : { ...v, [k]: { job: '', modo: modoDe(c.profile), estado: 'sin_respuesta', texto: '', pasos: [], aprobacion: null, ultima: null, puedeAprobar: false } })
  }

  /** Al abrir una conversación (o al verla ocupada): retoma la respuesta en marcha. Primero la que lanzó este navegador
   *  (o la de la notificación) si es de hace menos de 30 min; si no, la pregunta al hub por la conversación, que da el trabajo
   *  sin el código: se ve en directo y se puede parar, pero el permiso se aprueba donde se pidió. `huerfana`: tu último
   *  mensaje no tiene respuesta (si no hay nada en marcha, queda la nota para reintentar). */
  const reanudar = useCallback(async (k: string, huerfana = false) => {
    if (busy.current.has(k) || k.includes('/null#')) return
    let job: string | null = null, j: JobApi | null = null
    const e = H.leerJobs()[k]
    if (e && Date.now() - e.t <= 30 * 60e3) {
      if (siguiendo.current.has(e.job)) return
      try { j = await api<JobApi>(urlJob(e.job)) } catch { return }
      if (j.done) { H.olvidarJob(k, e.job); H.borrarToken(e.job) } else job = e.job
    }
    if (!job) {
      const i = k.indexOf('/')
      let r: JobApi & { id?: string | null }
      try { r = await api<JobApi & { id?: string | null }>(`/api/job?session=${encodeURIComponent(k.slice(i + 1))}&profile=${encodeURIComponent(k.slice(0, i))}`) } catch { return }
      if (!r.id || r.done) { if (huerfana) void notaSinRespuesta(k); return }
      job = r.id; j = r
    }
    if (!j || busy.current.has(k) || siguiendo.current.has(job)) return
    jobs.current[k] = job; marcar(k, true); ponerVivo(k, job, j)
    void seguir(job, k, k.split('/')[0])
  }, [ponerVivo, seguir]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Conversación nueva de un asistente de un solo oficio que ya tenía una respuesta en marcha (la app se cerró o se recargó antes
   *  de que existiera la sesión): se retoma por el trabajo apuntado para «<perfil>/null». Si ya hay sesión, se abre directamente. */
  const reanudarNueva = useCallback(async (perfil: string, k: string) => {
    const e = H.leerJobs()[`${perfil}/null`]
    if (!e || Date.now() - e.t > 30 * 60e3 || siguiendo.current.has(e.job)) return
    let j: JobApi
    try { j = await api<JobApi>(urlJob(e.job)) } catch { return }
    if (kActual() !== k) return   // ya se abrió otra cosa
    if (j.error === PERDIDO || (j.done && !j.session_id)) { H.olvidarJob(`${perfil}/null`, e.job); return }
    if (j.session_id) {
      H.olvidarJob(`${perfil}/null`, e.job)
      if (!j.done) H.registrarJob(`${j.profile || perfil}/${j.session_id}`, e.job)   // abrir() la retoma por aquí
      await abrir({ id: j.session_id, profile: j.profile || perfil, modo: modoDe(j.profile || perfil) })
      return
    }
    jobs.current[k] = e.job; marcar(k, true); ponerVivo(k, e.job, j)
    void seguir(e.job, k, perfil)
  }, [abrir, ponerVivo, seguir]) // eslint-disable-line react-hooks/exhaustive-deps

  // la conversación que ves está ocupada y aquí no se sabía (se pidió desde otro dispositivo): se retoma
  useEffect(() => {
    const c = curRef.current, k = kActual()
    if (!c.id || busy.current.has(k)) return
    if (sessions.find(s => s.id === c.id && (s.profile || 'default') === c.profile)?.busy) void reanudar(k)
  }, [sessions, reanudar]) // eslint-disable-line react-hooks/exhaustive-deps

  // el enlace de una notificación con la app ya abierta solo cambia el fragmento (#aprobar=…)
  useEffect(() => {
    const f = () => { const r = H.tomarHash(); if (r && r.k === kActual()) void reanudar(r.k) }
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [reanudar]) // eslint-disable-line react-hooks/exhaustive-deps

  const send = useCallback(async (text: string, ctx?: string) => {
    // Escribes con una respuesta en marcha: se para (Hermes guarda lo que lleve) y tu mensaje sigue la misma conversación, con su contexto
    const kv = kActual()
    if (busy.current.has(kv)) {
      const job = jobs.current[kv]
      if (!job) pararAlEmpezar.current.add(kv)
      else if (!parando.current.has(job)) { parando.current.add(job); await H.parar(job).catch(() => parando.current.delete(job)) }
      for (let i = 0; i < 60 && busy.current.has(kActual()); i++) await sleep(500)
      if (busy.current.has(kActual())) throw new Error('Zazu sigue terminando la respuesta anterior; prueba en unos segundos')
    }
    const c = curRef.current, g = gen.current, k0 = kDe(c, g)
    if (fuenteDe(c, sessRef.current) === 'whatsapp') throw new Error(SOLO_WA)
    const hermes = c.modo === 'hermes'
    if (ctx) ctxDe.current.set(text, ctx)
    marcar(k0, true)
    const provisional: Item = { kind: 'msg', id: -Date.now(), role: 'user', text, time: hm(Date.now() / 1000) }
    if (!c.id) setItems(prev => [...prev, provisional])   // se ve al instante
    setVivos(v => ({ ...v, [k0]: { job: '', modo: c.modo, estado: 'en_marcha', texto: '', pasos: [], aprobacion: null, ultima: null, puedeAprobar: false } }))
    let r: Envio
    try {
      r = await post<Envio>('/api/send', { text, session: c.id, profile: c.profile, ctx, ...(hermes && modeloRef.current ? { modelo: modeloRef.current } : {}) })   // ctx: los datos de una acción rápida (correo, WhatsApp…) valen en las dos rutas
    } catch (e) {
      marcar(k0, false); pararAlEmpezar.current.delete(k0); quitarVivo(k0, '')
      if (!c.id) setItems(prev => prev.filter(i => i.id !== provisional.id))
      void H.diag('enviar', (e as Error).message, c.profile)
      throw e   // el cuadro de escribir devuelve lo escrito
    }
    if (!r.job) {   // lo resolvió el servidor sin IA (p. ej. «Apunta en mis notas: …»)
      marcar(k0, false); quitarVivo(k0, '')
      setItems(prev => prev.filter(i => i.id > 0)); setInfo(r.nota || 'Hecho'); return
    }
    const job = r.job
    if (r.token) H.guardarToken(job, r.token)
    let k = k0
    if (hermes && r.session && r.session !== c.id) {
      // el motor da la sesión al momento (en una conversación larga puede ser otra: la que sigue tras resumirla)
      k = `${c.profile}/${r.session}`
      moverClave(k0, k)
      if (kActual() === k0) void abrir({ id: r.session, profile: c.profile, modo: 'hermes' }, c.id ? undefined : [provisional])
    }
    jobs.current[k] = job
    setVivos(v => v[k] ? { ...v, [k]: { ...v[k], job, puedeAprobar: !!r.token } } : v)
    if (!k.includes('/null#')) H.registrarJob(k, job)
    if (pararAlEmpezar.current.delete(k)) { parando.current.add(job); H.parar(job).catch(() => parando.current.delete(job)) }
    if (k.includes('/null#')) {
      // conversación nueva de un perfil de un solo disparo: se espera (hasta 30 s) a que exista la sesión; si falla antes, el error vuelve al cuadro de escribir
      H.registrarJob(`${c.profile}/null`, job)   // si la app se cierra antes de que haya sesión, la siguiente conversación nueva con él la retoma
      const lista = new Promise<void>((ok, ko) => { esperaSesion.current[job] = { ok, ko } })
      void seguir(job, k, c.profile)
      try { await Promise.race([lista, sleep(30000)]) }
      catch (e) { setItems(prev => prev.filter(i => i.id !== provisional.id)); throw e }
      finally { delete esperaSesion.current[job] }
    } else void seguir(job, k, c.profile)
  }, [abrir, seguir]) // eslint-disable-line react-hooks/exhaustive-deps

  const aprobar = useCallback(async (d: Decision) => {
    const k = kActual(), v = vivosRef.current[k], a = v?.aprobacion
    if (!v?.job || !a) return
    const tok = H.tokenDe(v.job)
    if (!tok) { setError(SIN_CODIGO); return }
    try {
      await H.aprobar(v.job, a.id, d, tok)
      resueltas.current.add(a.id)
      setVivos(x => x[k]?.job === v.job ? { ...x, [k]: { ...x[k], aprobacion: null, estado: 'en_marcha', ultima: { id: a.id, decision: d, cuando: Date.now() / 1000 } } } : x)
    } catch (e) { setError(`No se pudo ${d === 'deny' ? 'denegar' : 'aprobar'}: ${(e as Error).message}`) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /** «Reintentar»: vuelve a mandar tu último mensaje (con sus datos, si los llevaba). */
  const reintentar = useCallback(async () => {
    const u = [...itemsRef.current].reverse().find((i): i is Extract<Item, { kind: 'msg' }> => i.kind === 'msg' && i.role === 'user')
    if (!u || busy.current.has(kActual())) return
    await send(u.text, ctxDe.current.get(u.text))
  }, [send]) // eslint-disable-line react-hooks/exhaustive-deps

  const parar = useCallback(async () => {
    const k = kActual(), job = jobs.current[k]
    if (!job) { if (busy.current.has(k)) pararAlEmpezar.current.add(k); return }
    if (parando.current.has(job)) return
    parando.current.add(job)
    setVivos(x => x[k] ? { ...x, [k]: { ...x[k], estado: 'parando' } } : x)
    try { await H.parar(job) }
    catch (e) { parando.current.delete(job); setVivos(x => x[k]?.estado === 'parando' ? { ...x, [k]: { ...x[k], estado: 'en_marcha' } } : x); setError(`No se pudo parar: ${(e as Error).message}`) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // modelo de la conversación con permisos (perfil «tecnico»): el elegido aquí → el de la sesión → el último que elegiste → el del servidor
  const k = kDe(cur)
  const sesion = cur.id ? sessions.find(s => s.id === cur.id && (s.profile || 'default') === cur.profile) : undefined
  const usable = (id?: string | null): id is string => !!id && (!modelos || modelos.modelos.some(m => m.id === id && m.disponible))
  const modelo = cur.modo !== 'hermes' ? null : [elegido?.k === k ? elegido.id : null, sesion?.modelo, H.modeloGuardado(), modelos?.defecto].find(usable) ?? null
  modeloRef.current = modelo
  const setModelo = useCallback((id: string | null) => {
    const c = curRef.current
    if (c.modo !== 'hermes') return
    setElegido(id ? { k: kDe(c), id } : null)
    H.guardarModelo(id)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const vivo = useMemo(() => aLaVistaDe(vivos[k] || null, items), [vivos, k, items])
  const soloLectura = fuenteDe(cur, sessions) === 'whatsapp'
  return { sessions, cur, modo: cur.modo, soloLectura, items, pending, profiles, vivo, modelo, setModelo, error, clearError: () => setError(''), info, clearInfo: () => setInfo(''), open, newChat, send, aprobar, parar, reintentar, reload: loadSessions, contacto, anteriores, rutinas, abrirContacto, pregunta, cerrarPregunta: () => setPregunta(null) }
}
