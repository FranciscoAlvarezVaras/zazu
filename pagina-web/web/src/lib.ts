import { useCallback, useEffect, useRef, useState } from 'react'
import { modoDe } from './tipos'
import type { Modo } from './tipos'

/** La web corre dentro de la app de Android de Zazu (su User-Agent lleva «ZazuApp»): sin service worker, sin Google, sin «instalar». */
export const EN_APP = typeof navigator !== 'undefined' && /ZazuApp/.test(navigator.userAgent)
/** ¿Las invitadas conectan su propia IA (su ChatGPT, su Claude…)? Por ahora no: la IA la pone Fran con un crédito al mes por persona.
 *  Con `true` vuelven el paso de la guía, la tarjeta de Tu espacio y el aviso del chat para conectarla (el código sigue ahí). */
export const IA_PROPIA = false

/* ---------- API ---------- */
/** Lo que se ve cuando no hay red (en vez del «Failed to fetch» del navegador). */
export const SIN_RED = 'Sin conexión: revisa internet y prueba otra vez'
export async function api<T = any>(path: string, opts?: RequestInit): Promise<T> {
  let r: Response
  try { r = await fetch(path, { ...opts, headers: { ...(opts?.headers || {}), 'X-Hub': '1' } }) }
  catch (e) { throw (e as Error)?.name === 'AbortError' ? e : new Error(SIN_RED) }
  if (r.status === 401) { aLogin(); throw new Error('sesión caducada') }
  if (!r.ok) {
    let m: unknown = r.status >= 500 ? 'algo falló; inténtalo otra vez' : r.status
    try { m = (await r.json()).error || m } catch { /* sin cuerpo JSON */ }
    throw new Error(String(m))
  }
  return r.json()
}
/** Sesión caducada: se guarda dónde estabas para volver ahí después de entrar (enlaces directos incluidos). */
export function aLogin() {
  const u = location.pathname + location.search
  try { if (location.search) localStorage.setItem('zazu:volver', JSON.stringify({ u, t: Date.now() })) } catch { /* sin almacenamiento */ }
  location.href = `/login?next=${encodeURIComponent(u)}`
}
export const post = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

/** GET con estado de carga; `every` (ms) recarga periódicamente. */
export function useFetch<T>(path: string | null, every = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(!!path)
  const seq = useRef(0)   // solo cuenta la respuesta más reciente (una lenta no pisa a una nueva)
  const load = useCallback(async () => {
    if (!path) return
    const n = ++seq.current
    try { const d = await api<T>(path); if (n === seq.current) { setData(d); setError('') } }
    catch (e) { if (n === seq.current) setError((e as Error).message) }
    finally { if (n === seq.current) setLoading(false) }
  }, [path])
  useEffect(() => {
    setLoading(!!path)
    load()
    const t = every ? setInterval(() => { if (!document.hidden) load() }, every) : undefined   // sin gastar batería en segundo plano
    return () => { seq.current++; if (t) clearInterval(t) }
  }, [load, every, path])
  return { data, error, loading, reload: load }
}

/** «Algo cambió en Google (una tarea, una cita)»: lo avisa quien lo cambia (la barra de órdenes) y las pantallas con datos de Google se vuelven a pedir. */
export const AVISO_CAMBIO = 'zazu:cambio'
export const avisarCambio = () => window.dispatchEvent(new Event(AVISO_CAMBIO))

/* ---------- tipos ---------- */
export type Tab = 'inicio' | 'semana' | 'noticias' | 'empleo' | 'dinero' | 'zazu' | 'chat' | 'chats' | 'tareas' | 'midia' | 'calendario' | 'cuentas' | 'correo' | 'whatsapp' | 'carpetas' | 'rutinas' | 'ajustes' | 'explorar' | 'admin'
/** ¿Esta persona tiene esa sección? Lo dice el servidor en /api/me (`capacidades`): Fran, todas; una invitada, las suyas. «Hoy» (midia) es Inicio. */
export const puede = (me: { role: string; capacidades?: Record<string, boolean> }, t: string) =>
  me.capacidades ? !!me.capacidades[t === 'midia' ? 'inicio' : t === 'chats' ? 'chat' : t] : me.role !== 'guest' || t === 'inicio' || t === 'chat' || t === 'chats' || t === 'ajustes'
export type Task = { id: string; account: string; tag: string; title: string; notes: string; due: string; done: boolean; link?: string }
export type Ev = { id: string; account: string; tag: string; title: string; day?: 'hoy' | 'mañana' | null; start: string | null; end: string | null; allDay: boolean; location: string; link: string }
export type Mail = { account: 'varas' | 'alvarez'; id: string; from: string; subject: string; date: string | null; unread: boolean; important: boolean; count: number }
export type WaChat = { jid: string; name: string; kind: string; unread: number; ts: string | number | null; text: string; fromMe: boolean }
export type Hoy = { resumen: { titulo: string; cuando: number; texto: string } | null; gasto: number; archivos: { name: string; size: number; mtime: number }[] }
export type Job = { id: string; name: string; when: string; enabled: boolean; state: string; next: string | null; last: string | null; status: string | null }
export type Status = { gateway: string; platforms: Record<string, string>; version: string; active_agents: number; disk_free: number; disk_total: number }
export type FileEntry = { name: string; dir: boolean; size: number; mtime: number }
/** `modo` y `modelo` (id de MODELOS) los añade el servidor; `modelo` solo en las del chat con permisos (perfil «tecnico»). */
export type Session = { id: string; profile: string; title?: string; display_name?: string; source: string; preview?: string; busy?: boolean; last: number; modo?: Modo; modelo?: string | null }
export type Usage = { days: { d: string; calls: number; inp: number; usd: number }[]; top: { id: string; source: string; title: string; calls: number; usd: number; avg_ctx: number }[] }

/* ---------- utilidades ---------- */
/** Cómo se llama en pantalla el asistente de Fran (se llama como su gato). Por dentro es el motor «Hermes» (perfil «tecnico»); «Zazu» es también
 *  el nombre por defecto del asistente de cada invitada (ella puede cambiarlo: campo `asistente` de /api/me). */
export const AGENTE = 'Zazu'
/** El nombre que se ve: el de la asistente de una invitada (por defecto «Zazu») o, para Fran, Zazu. Antes (2026-10-10 → 10-11) se llamó Byte. */
export const nombreAsistente = (guest?: boolean, asistente?: string) => guest ? asistente || 'Zazu' : AGENTE
/** El servidor y el motor a veces nombran a «Hermes» (el motor de Zazu): en pantalla, para Fran, todo es Zazu. Solo para frases, nunca para un comando. */
export const deHermes = (t: string) => t.replace(/\bModo Hermes\b/g, 'El chat con Zazu').replace(/\bmodo Hermes\b/g, 'el chat con Zazu').replace(/\bHermes\b/g, AGENTE)
export const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' } as Record<string, string>)[c])
const pad = (n: number) => String(n).padStart(2, '0')
export const isoDay = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const hm = (v: string | number | Date | null | undefined) => {
  if (v === null || v === undefined || v === '') return ''
  const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v)
  return isNaN(d.getTime()) ? '' : `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export function relTime(v: string | number | null | undefined) {
  if (v === null || v === undefined || v === '') return ''
  const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v)
  if (isNaN(d.getTime())) return ''
  const days = Math.round((new Date(isoDay()).getTime() - new Date(isoDay(d)).getTime()) / 864e5)
  if (days <= 0) return hm(d)
  if (days === 1) return 'Ayer'
  return d.toLocaleDateString('es', { day: 'numeric', month: 'short' })
}
export function dueLabel(due: string) {
  if (!due) return 'Sin fecha'
  const t = isoDay()
  if (due === t) return 'Hoy'
  const diff = Math.round((new Date(due).getTime() - new Date(t).getTime()) / 864e5)
  if (diff === 1) return 'Mañana'
  if (diff < 0) return `Vencida · ${-diff} d`
  return new Date(due + 'T12:00').toLocaleDateString('es', { day: 'numeric', month: 'short' })
}
export const fmtSize = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`
export const initials = (name: string) => (name.replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('') || '?').toUpperCase()
export const TONES = ['peach', 'lavender', 'mint', 'butter'] as const
export const toneOf = (s: string) => TONES[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % 4]
export const greeting = () => { const h = new Date().getHours(); return h < 6 ? 'Buenas noches' : h < 13 ? 'Buenos días' : h < 21 ? 'Buenas tardes' : 'Buenas noches' }
export const fechaLarga = () => {
  const t = new Intl.DateTimeFormat('es', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())
  return t[0].toUpperCase() + t.slice(1)
}

/* ---------- navegación con historial (el gesto Atrás de Android vuelve atrás) y enlaces directos ---------- */
export type Params = { tab?: string; root?: string; ruta?: string; archivo?: string; recibido?: string; conv?: string; pf?: string; perfil?: string; contacto?: string; tablero?: string; vista?: string; tarjeta?: string; nuevo?: string }
/** Se lanza en cada cambio de pantalla, carpeta o archivo, también con Atrás/Adelante del navegador. */
export const NAV = 'hub:nav'
const CLAVES = ['tab', 'root', 'ruta', 'archivo', 'recibido', 'conv', 'pf', 'perfil', 'contacto', 'tablero', 'vista', 'tarjeta', 'nuevo'] as const

/** Lo que pide la URL ahora mismo: ?tab=&root=&ruta=&archivo=&recibido=&conv=&pf=&perfil= (conv y pf: conversación abierta y su perfil;
 *  perfil: el estilo elegido para el chat, p. ej. Charla, para que no se pierda al recargar) */
export function leerParams(): Params {
  const q = new URLSearchParams(location.search), p: Params = {}
  for (const k of CLAVES) { const v = q.get(k); if (v) p[k] = v }
  return p
}
/** ?perfil= del chat si es un estilo (Charla, Escritor…) y no el motor ni «default»; si no, null. */
export function perfilDeUrl(): string | null {
  const p = leerParams().perfil
  return p && /^[a-z0-9_-]{1,40}$/i.test(p) && p !== 'default' && modoDe(p) === 'zazu' ? p : null
}
/** URL interna para unos parámetros («/» es Inicio). */
export function urlApp(p: Params): string {
  const q = new URLSearchParams()
  for (const k of CLAVES) { const v = p[k]; if (v) q.set(k, v) }
  const s = q.toString()
  return !s || s === 'tab=inicio' ? '/' : `/?${s}`
}
/** La misma pantalla aunque la URL se escriba distinto: root=compartido es la raíz por defecto de Carpetas. */
function canon(url: string): string {
  const q = new URLSearchParams(url.split('?')[1] || ''), p: Params = {}
  for (const k of CLAVES) { const v = q.get(k); if (v) p[k] = v }
  if (p.tab === 'files') p.tab = 'carpetas'
  if (p.tab === 'carpetas' && p.root === 'compartido') delete p.root
  return urlApp(p)
}
/** Ir a una pantalla, carpeta o archivo dejando rastro en el historial (o sustituyendo la entrada actual). Sin tab: Carpetas si hay ruta, si no la pestaña actual. */
export function irA(p: Params, reemplazar?: boolean): void {
  if (volviendo) { volviendo.push(() => irA(p, reemplazar)); return }   // una hoja acaba de quitar su entrada: se navega cuando termine
  const tab = p.tab || (p.root || p.ruta || p.archivo ? 'carpetas' : leerParams().tab)
  const url = urlApp({ tab, root: p.root, ruta: p.ruta, archivo: p.archivo, conv: p.conv, pf: p.pf, perfil: p.perfil, contacto: p.contacto, tablero: p.tablero, vista: p.vista, tarjeta: p.tarjeta, nuevo: p.nuevo }), ahora = location.pathname + location.search
  // desde una hoja abierta, su entrada se sustituye; y si es la misma pantalla escrita de otra forma, no se duplica
  if (url !== ahora) history[reemplazar || hojaEnCurso() || canon(url) === canon(ahora) ? 'replaceState' : 'pushState'](null, '', url)
  dispatchEvent(new Event(NAV))
}

/* ---------- hojas y menús que se cierran con el Atrás del móvil ---------- */
let hojaN = 0, hojasAbiertas = 0
let volviendo: (() => void)[] | null = null   // history.back() de una hoja en marcha (es asíncrono)
const hojaEnCurso = () => hojasAbiertas > 0 && typeof history.state?.hoja === 'number'
function soltar() { const q = volviendo; volviendo = null; q?.forEach(f => f()) }
/** Mientras `abierta`, la hoja (o el menú) tiene su propia entrada en el historial: el Atrás del móvil la cierra
 *  en vez de salir de la pantalla. Si se cierra con un botón, se quita esa entrada. */
export function useAtrasCierra(abierta: boolean, cerrar: () => void) {
  const fin = useRef(cerrar)
  fin.current = cerrar
  useEffect(() => {
    if (!abierta) return
    const id = ++hojaN
    history.pushState({ ...(history.state || {}), hoja: id }, '', location.href)
    hojasAbiertas++
    let atras = false
    const pop = () => { if (history.state?.hoja !== id) { atras = true; fin.current() } }
    addEventListener('popstate', pop)
    return () => {
      hojasAbiertas--
      removeEventListener('popstate', pop)
      if (!atras && history.state?.hoja === id) {
        const q = volviendo = volviendo || []
        history.back()
        setTimeout(() => { if (volviendo === q) soltar() }, 700)   // por si el navegador no avisa
      }
    }
  }, [abierta])
}
if (typeof window !== 'undefined') addEventListener('popstate', () => { if (volviendo) soltar(); else dispatchEvent(new Event(NAV)) })
/** Parámetros de la URL que se actualizan con irA() y con Atrás/Adelante. */
export function useParams() {
  const [p, setP] = useState(leerParams)
  useEffect(() => { const f = () => setP(leerParams()); addEventListener(NAV, f); return () => removeEventListener(NAV, f) }, [])
  return p
}

/* ---------- rutas del servidor → carpetas de la app ---------- */
const padreDe = (p: string) => p.split('/').slice(0, -1).join('/')
const esArchivo = (p: string) => /\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{1,6}$/.test(p.split('/').pop() || '')
export const RAIZ_TXT: Record<string, string> = { compartido: 'Carpetas', notas: 'Cerebro', whatsapp: 'WhatsApp del móvil' }
/** «Carpetas › Importante › Viajes» */
export const etiquetaRuta = (root: string, path: string) => [RAIZ_TXT[root] || 'Carpetas', ...path.split('/').filter(Boolean)].join(' › ')
/** Ruta absoluta (o ~/…) → raíz y ruta dentro de la app; null si la app no la enseña (p. ej. WhatsApp › Privados). */
export function rutaApp(abs: string): { root: string; path: string } | null {
  const s = abs.trim().replace(/^(?:\/home\/(?:server|servidor)|~)(?=\/)/, '~').replace(/\/+$/, '')
  let m: RegExpMatchArray | null
  if ((m = s.match(/^~\/(?:Cerebro\/40 Compartido|Compartido)(?:\/(.*))?$/))) return { root: 'compartido', path: m[1] || '' }
  if ((m = s.match(/^~\/Documentos\/WhatsApp(?:\/(.*))?$/))) return /^Privados(\/|$)/.test(m[1] || '') ? null : { root: 'whatsapp', path: m[1] || '' }
  if ((m = s.match(/^~\/Cerebro\/((?:10 Bandeja|20 Diario|30 Notas)(?:\/.*)?)$/))) return { root: 'notas', path: m[1] }
  return null
}
const paramsDe = (root: string, path: string, dir?: boolean): Params =>
  (dir === undefined ? esArchivo(path) : !dir) ? { tab: 'carpetas', root, ruta: padreDe(path), archivo: path } : { tab: 'carpetas', root, ruta: path }
/** Enlace directo a una carpeta o archivo (?tab=carpetas&root=…&ruta=…&archivo=…; archivo es la ruta completa desde la raíz). */
export const enlaceA = (root: string, path: string, dir?: boolean) => urlApp(paramsDe(root, path, dir))
/** Abre esa carpeta (o la vista previa de ese archivo) en Carpetas. */
export const abrirEnCarpetas = (root: string, path: string, dir?: boolean) => irA(paramsDe(root, path, dir))
/** URL de descarga/vista; sin root para la raíz por defecto (las invitadas no la mandan). */
export const urlDescarga = (root: string, path: string, inline = false) =>
  `/api/download?path=${encodeURIComponent(path)}${root && root !== 'compartido' ? `&root=${root}` : ''}${inline ? '&inline=1' : ''}`

/** Copia de seguridad: la carpeta (o toda la raíz si path va vacío) en un ZIP. */
export const urlZip = (root: string, path: string) =>
  `/api/zip?path=${encodeURIComponent(path)}${root && root !== 'compartido' ? `&root=${root}` : ''}`

/* ---------- Markdown mínimo y seguro (se escapa todo antes de transformar) ---------- */
// Dónde acaba una ruta escrita en prosa: en la puntuación de la frase o, si no es un archivo, antes de «como», «para»…
const DURO = /[.,;:!?»”"')\]]+(?=\s|$)|[«“"`*<>\u0001]|\p{Extended_Pictographic}/u
const BLANDO = /\s[-–—]\s|\s(?=(?:como|para|con|que|porque|donde|cuando|pero|si|ya|aquí|ahí|también|y (?:lo|la|los|las|te|ya|así|luego))(?:\s|$|[.,;:!?]))/
// Si el nombre llega hasta el final de la frase o es el título de una nota («Viaje a Roma con Nuria», «Codex con IA local (David Ragel)»),
// «con» y «para» pueden ser parte del nombre: solo se corta donde empieza otra frase («… para que…», «… y lo…», «… con tus cosas»)
const FIN = '(?=\\s|$|[.,;:!?])'
const FRASE = `(?:(?:para|como|con)\\s+)?(?:que|porque|donde|cuando|pero|si|ya|aquí|ahí|también|y (?:lo|la|los|las|te|ya|así|luego))${FIN}`
const CLITICO = `(?:para|como|con)\\s+(?:(?:me|te|se|nos|os|lo|le|les|mí|ti)${FIN}|\\p{L}+(?:ar|er|ir|ár|ér|ír)(?:lo|la|los|las|le|les|me|te|se|nos)${FIN})`
const ARTICULO = `(?:para|como|con)\\s+(?:el|la|los|las|un|una|unos|unas|tu|tus|su|sus|mi|mis|este|esta|estos|estas|eso|esto|todo|toda|todos|todas)${FIN}`
const COMO = `como\\s+(?:siempre|pediste|querías|quieras|dijiste|quedamos|acordamos|hablamos|habíamos|sueles|ves)${FIN}`
const FUERTE = new RegExp(`\\s[–—]\\s|\\s(?=${FRASE}|${CLITICO}|${COMO})`, 'u')                 // nombre de una nota: casi todo es nombre
const PROSA = new RegExp(`\\s[-–—]\\s|\\s(?=como${FIN}|${FRASE}|${CLITICO}|${ARTICULO})`, 'u')     // carpeta al final de la frase («como» nunca es nombre)
const EXT = /^.*?\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{1,6}(?=[\s,;:!?»”"')\]*`<]|$)/
/** Archivos de verdad dentro del Cerebro (lo demás con punto es parte del título: «Node.js»). */
const EXT_CEREBRO = /\.(md|pdf|png|jpe?g|gif|webp|avif|svg|txt|csv|json|docx?|xlsx?|pptx?|odt|ods|mp3|m4a|ogg|opus|wav|mp4|mov|webm|zip|canvas|base|html?)$/i
/** Último trozo de una ruta. `titulo`: es el nombre de una nota del Cerebro. */
function cola(t: string, titulo = false): string {
  const d = t.search(DURO)
  let s = d < 0 ? t : t.slice(0, d)
  const e = s.match(EXT)
  const alFinal = d < 0 || /^[.,;:!?»”"')\]\u0001]/.test(t.slice(d))   // llega al final de la línea o de la frase
  if (e && (!titulo || EXT_CEREBRO.test(e[0]))) s = e[0]
  else {
    const corte = (re: RegExp) => { const b = s.search(re); return b >= 0 ? s.slice(0, b) : s }
    const largo = titulo || alFinal ? corte(titulo ? FUERTE : PROSA) : ''
    s = largo && largo.trim().split(/\s+/).length <= 10 ? largo : corte(BLANDO)
  }
  if ((s.match(/\(/g) || []).length > (s.match(/\)/g) || []).length && t[s.length] === ')') s += ')'   // «Viajes (Omio)»
  return s.replace(/\s+$/, '')
}
/** Trozos de una ruta a partir de un separador («›» o «/»): nombres y cuánto texto ocupan.
 *  `titulo(previos)`: si el trozo que va detrás de esos es el nombre de una nota. */
function tramo(t: string, sep: '›' | '/', titulo?: (previos: string[]) => boolean): { segs: string[]; len: number } {
  const re = sep === '›' ? /\s*›\s*/y : /\//y, sig = sep === '›' ? /\s*›/ : /\//
  const segs: string[] = []
  let i = 0, len = 0
  for (;;) {
    re.lastIndex = i
    const m = re.exec(t)
    if (!m) break
    const j = i + m[0].length, resto = t.slice(j), k = resto.search(sig)
    const trozo = k < 0 ? resto : resto.slice(0, k)
    // un trozo seguido de otro «›» es parte de la ruta salvo que empiece otra frase u otra ruta («… y en Cerebro › …»)
    const otraRuta = /\s(?:[Cc]arpetas|[Cc]erebro)$/.test(trozo) && !/^notas del cerebro$/i.test(trozo.trim())
    if (k >= 0 && trozo.trim() && !/^\s/.test(trozo) && !DURO.test(trozo) && !PROSA.test(trozo) && !otraRuta && trozo.length <= 120) { segs.push(trozo.trim()); i = len = j + trozo.length; continue }
    const c = cola(trozo, !!titulo?.(segs))
    if (c.trim()) { segs.push(c.trim()); len = j + c.length }
    break
  }
  return { segs, len }
}
type Destino = { root: string; path: string; dir?: boolean }
const AREA: Record<string, string> = { bandeja: '10 Bandeja', diario: '20 Diario', notas: '30 Notas', '10 bandeja': '10 Bandeja', '20 diario': '20 Diario', '30 notas': '30 Notas' }
/** «Cerebro › Ideas › Título» es la nota 30 Notas/Ideas/Título.md (Ideas, Proyectos, Lecturas… viven en 30 Notas).
 *  La app solo enseña 10 Bandeja, 20 Diario y 30 Notas (y 40 Compartido, que es Carpetas): lo demás no se enlaza. */
function cerebroA(segs: string[]): Destino | null {
  const [a = '', ...r] = segs, k = a.toLowerCase()
  if (k === '40 compartido') return { root: 'compartido', path: r.join('/') }
  if (/^\d\d\s/.test(a) && !AREA[k]) return null   // 00 Inicio, 50 Zazu, 60 Servidor, 90 Sistema…
  const area = AREA[k] || '30 Notas', resto = AREA[k] ? r : segs
  const nota = resto.length >= (area === '30 Notas' ? 2 : 1)   // en Bandeja y Diario las notas van sueltas
  if (nota && !EXT_CEREBRO.test(resto[resto.length - 1])) resto[resto.length - 1] += '.md'
  return { root: 'notas', path: [area, ...resto].join('/'), dir: !nota }
}
/** «Carpetas › …» / «Cerebro › …» (como habla Zazu) → raíz y ruta de la app; null si la app no lo enseña. */
function destinoMigas(ini: string, segs: string[]): Destino | null {
  if (!segs.length) return null
  if (ini.toLowerCase() === 'cerebro') return cerebroA(segs)
  const [a, ...r] = segs, k = a.toLowerCase()
  if (k === 'whatsapp del móvil') return /^privados$/i.test(r[0] || '') ? null : { root: 'whatsapp', path: r.join('/'), dir: r.length ? undefined : true }
  if (k === 'notas del cerebro' || k === 'cerebro') return r.length ? cerebroA(r) : { root: 'notas', path: '', dir: true }
  if (k === 'mis carpetas') return { root: 'compartido', path: r.join('/'), dir: r.length ? undefined : true }
  return { root: 'compartido', path: segs.join('/') }
}
/** ¿Lo que va detrás de estos trozos es el nombre de una nota? (entonces «con», «para»… son parte del nombre) */
function tituloMigas(ini: string, previos: string[]): boolean {
  return !!previos.length && destinoMigas(ini, [...previos, 'x'])?.dir === false && destinoMigas(ini, [...previos, 'x'])?.root === 'notas'
}
const enlaceInterno = (href: string, txt: string, title = '') => `<a href="${esc(href)}" data-nav="1"${title ? ` title="${esc(title)}"` : ''}>${esc(txt)}</a>`
const PANTALLA: Record<string, string> = { inicio: 'Inicio', hermes: 'el chat', chat: 'el chat', tareas: 'Tareas', calendario: 'la agenda', rutinas: 'Rutinas', correo: 'Correos', whatsapp: 'WhatsApp', ajustes: 'Tu espacio', cuentas: 'Cuentas', midia: 'Hoy', explorar: 'Explorar', tableros: 'Tableros', zazu: 'Zazu', byte: 'Zazu' }
/** Texto de un enlace a la propia app que llegó como URL desnuda: «Abrir en Carpetas › Importante › Viajes». */
function textoApp(q: URLSearchParams): string {
  const tab = q.get('tab') || 'inicio'
  if (tab === 'carpetas' || tab === 'files') return `Abrir en ${etiquetaRuta(q.get('root') || 'compartido', q.get('archivo') || q.get('ruta') || '')}`
  return PANTALLA[tab] ? `Abrir ${PANTALLA[tab]}` : 'Abrir en la app'
}
/** `desnuda`: la URL venía sin texto (se escribió tal cual) y se enseña más corta. */
function urlALink(url: string, txt: string, desnuda = false): string {
  try {
    const u = new URL(url)
    if ((u.host === location.host || u.host === 'holazazu.app') && u.pathname === '/' && u.searchParams.has('tab'))   // enlace a la propia app: se abre aquí
      return enlaceInterno(`/${u.search}`, desnuda ? textoApp(u.searchParams) : txt)
    if (desnuda && url.length > 60) {   // web larga: dominio y principio de la ruta
      const p = decodeURI(u.pathname + u.search).replace(/\/$/, '')
      txt = u.host.replace(/^www\./, '') + (p.length > 28 ? `${p.slice(0, 26)}…` : p)
    }
  } catch { /* URL rara: enlace normal */ }
  return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer"${desnuda && txt !== url ? ` title="${esc(url)}"` : ''}>${esc(txt)}</a>`
}
const ICONO_ARCHIVO = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/></svg>'
/** «MEDIA:/ruta» (lo que Zazu manda por WhatsApp) → ficha que abre el archivo en Carpetas. */
function ficha(abs: string): string {
  const r = rutaApp(abs), nombre = esc(abs.replace(/\/+$/, '').split('/').pop() || abs)
  const foto = r && /\.(jpe?g|png|gif|webp|avif)$/i.test(abs) ? `<img src="${esc(urlDescarga(r.root, r.path, true))}" alt="" loading="lazy">` : ICONO_ARCHIVO
  return r ? `<a class="file-chip" href="${esc(enlaceA(r.root, r.path, false))}" data-nav="1" title="${esc(etiquetaRuta(r.root, r.path))}">${foto}<span>${nombre}</span></a>`
    : `<span class="file-chip">${ICONO_ARCHIVO}<span>${nombre}</span></span>`
}
const MEDIA = /[`"'*_]{0,3}MEDIA:\s*(?:`([^`\n]+?)`|"([^"\n]+?)"|'([^'\n]+?)'|((?:~\/|\/)\S+?(?:[^\S\n]+\S+?)*?\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{1,6}(?=[\s`"'*_,;:)\]}]|MEDIA:|\.(?:\s|$)|$)|(?:~\/|\/)\S+))[`"'*_]{0,3}/g
const ABS = /(?:\/home\/(?:server|servidor)|~)\/(?:Cerebro\/(?:40 Compartido|10 Bandeja|20 Diario|30 Notas)|Compartido|Documentos\/WhatsApp)(?![\p{L}\p{N}_-])/gu
const MIGAS = /(?<![\p{L}\p{N}])([Cc]arpetas|[Cc]erebro)(?=\s*›)/gu
/** Textos cortos (vista previa de una conversación): «MEDIA:/ruta/billete.pdf» y «[Imagen adjunta: /ruta/foto.jpg]» → «📎 billete.pdf». */
export function vistaPrevia(t: string): string {
  const nombre = (p: string) => `📎 ${p.replace(/\/+$/, '').split('/').pop() || 'archivo'}`
  return t
    .replace(/\[(?:Imagen adjunta|Archivo adjunto): ([^\]\n]+)\]/g, (_m, p: string) => nombre(p))
    .replace(/\[Archivo guardado en mis carpetas › ([^\]\n]+)\]/g, (_m, p: string) => nombre(p.split(' › ').join('/')))
    // la vista previa viene cortada: una ruta sin terminar no se enseña
    .replace(/[`"'*_]{0,3}MEDIA:\s*[`"']?(?:~\/|\/)[^\n]*$/, m => /\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{1,6}(?=[\s`"'*_,;:)\]}]|$)/.test(m) ? m : '📎 archivo')
    .replace(MEDIA, (_m, a?: string, b?: string, c?: string, d?: string) => nombre(a || b || c || d || ''))
}
/** Sustituye cada coincidencia de `re` + su ruta por un enlace guardado aparte (no se vuelve a transformar). */
function enlazar(t: string, re: RegExp, sep: '›' | '/', crear: (ini: string, segs: string[], texto: string) => string | null, titulo?: (ini: string, previos: string[]) => boolean): string {
  let out = '', i = 0, m: RegExpExecArray | null
  re.lastIndex = 0
  while ((m = re.exec(t))) {
    const ini = m[0], fin0 = m.index + ini.length, { segs, len } = tramo(t.slice(fin0), sep, titulo && (p => titulo(ini, p)))
    const fin = fin0 + len, h = crear(ini, segs, t.slice(m.index, fin))
    if (h === null) continue
    out += t.slice(i, m.index) + h; i = fin; re.lastIndex = fin
  }
  return out + t.slice(i)
}

export function md(src: string): string {
  const blocks: string[] = []
  src = src.replace(/[\u0000\u0001]/g, '').replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _l, c: string) => { blocks.push(`<pre><code>${esc(c.replace(/\n$/, ''))}</code></pre>`); return `\u0000${blocks.length - 1}\u0000` })
  const inl = (t: string) => {
    const held: string[] = []
    const hold = (h: string) => `\u0001${held.push(h) - 1}\u0001`
    t = t.replace(/\[([^\]\n]+)\]\(([^)\n]+)\)/g, (m, txt: string, url: string) => {
      if (/^https?:/.test(url)) return hold(urlALink(url.trim(), txt))
      const r = rutaApp(url)
      return r ? hold(enlaceInterno(enlaceA(r.root, r.path), txt, url)) : m
    })
      .replace(/(^|[\s(«"'])(https?:\/\/[^\s<>"«»]+)/g, (_m, pre: string, url: string) => {
        const fin = (url.match(/[.,;:!?)\]]+$/) || [''])[0]
        const u = url.slice(0, url.length - fin.length)
        return pre + hold(urlALink(u, u, true)) + fin
      })
      .replace(MEDIA, (_m, a?: string, b?: string, c?: string, d?: string) => hold(ficha(a || b || c || d || '')))
    t = enlazar(t, ABS, '/', (ini, segs, texto) => {
      const abs = [ini, ...segs].join('/'), r = rutaApp(abs)
      return r ? hold(enlaceInterno(enlaceA(r.root, r.path), etiquetaRuta(r.root, r.path), texto)) : null
    })
    t = enlazar(t, MIGAS, '›', (ini, segs, texto) => {
      const d = destinoMigas(ini, segs)
      return d ? hold(enlaceInterno(enlaceA(d.root, d.path, d.dir), texto)) : null
    }, tituloMigas)
    return esc(t)
      .replace(/`(\u0001\d+\u0001)`/g, '$1')   // una ruta entre comillas de código se ve como enlace normal
      .replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
      .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<i>$2</i>')
      .replace(/\u0001(\d+)\u0001/g, (_m, i: string) => held[+i])
  }
  const out: string[] = []
  let list: 'ul' | 'ol' | null = null
  const close = () => { if (list) { out.push(`</${list}>`); list = null } }
  const lns = src.split('\n')
  const FILA = /^\s*\|.*\|\s*$/, SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/
  const celdas = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
  for (let i = 0; i < lns.length; i++) {
    const ln = lns[i]
    let m: RegExpMatchArray | null
    // una tabla («| Día | Comida |» con su «|---|---|» debajo) se pinta como tabla, no como barras sueltas
    if (FILA.test(ln) && i + 1 < lns.length && SEP.test(lns[i + 1])) {
      close()
      const cab = celdas(ln), filas: string[][] = []
      for (i += 2; i < lns.length && FILA.test(lns[i]); i++) filas.push(celdas(lns[i]))
      i--
      out.push(`<div class="md-tabla"><table><thead><tr>${cab.map(c => `<th>${inl(c)}</th>`).join('')}</tr></thead><tbody>${filas.map(f => `<tr>${cab.map((_c, j) => `<td>${inl(f[j] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`)
      continue
    }
    if ((m = ln.match(/^\s*[-*]\s+(.*)/))) { if (list !== 'ul') { close(); out.push('<ul>'); list = 'ul' } out.push(`<li>${inl(m[1])}</li>`); continue }
    if ((m = ln.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== 'ol') { close(); out.push('<ol>'); list = 'ol' } out.push(`<li>${inl(m[1])}</li>`); continue }
    close()
    // títulos de verdad (# y ## → h3; ### o más → h4), con su aire: no se pegan al párrafo de después (2026-10-22)
    if ((m = ln.match(/^(#{1,6})\s+(.*)/))) { const h = m[1].length < 3 ? 'h3' : 'h4'; out.push(`<${h} class="md-h">${inl(m[2])}</${h}>`); continue }
    if (!ln.trim()) { out.push(''); continue }
    out.push(`<p>${inl(ln)}</p>`)
  }
  close()
  return out.join('').replace(/<\/p><p>/g, '<br>').replace(/\u0000(\d+)\u0000/g, (_m, i: string) => blocks[+i])
}

/* ---------- archivos recientes (Inicio › Guardado hace poco) ---------- */
export type Kind = 'folder' | 'pdf' | 'image' | 'video' | 'audio' | 'doc' | 'sheet' | 'text' | 'note' | 'other'
export type Reciente = { path: string; name: string; folder: string; size: number; mtime: number; kind: Kind; origen: 'whatsapp' | 'app' | '' }

export type Cuentas = { google: { email: string; services: string[]; error: boolean }[]; google_web: boolean
  /** Fran: su WhatsApp de solo lectura (wacli): connected | fatal | disconnected | null (no se pudo comprobar). */
  whatsapp: string | null; whatsapp_sync?: string | null
  /** el repaso (wacli-sync) está en marcha; null si no se sabe */ whatsapp_vivo?: boolean | null }
