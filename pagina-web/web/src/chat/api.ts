/* Motor del chat con Zazu (perfil «tecnico»): llamadas al hub, códigos de permiso guardados en este navegador, lista de modelos
   y cómo se leen los pasos (herramientas) para enseñarlos. */
import { useEffect, useState } from 'react'
import { api, post } from '../lib'
import type { Decision, Modelos } from '../tipos'

/* ---------- llamadas ---------- */
/** Responde a un permiso pendiente. `token` es el código que el hub dio solo a este navegador (o a la notificación). */
export const aprobar = (job: string, id: string, decision: Decision, token: string) =>
  post<{ ok: boolean; decision: Decision }>('/api/hermes/aprobar', { job, id, decision, token })
/** Para la respuesta en marcha (en el chat con permisos, el hub deniega antes el permiso pendiente). */
export const parar = (job: string) => post<{ ok: boolean }>('/api/parar', { job })
/** Un fallo del chat, al registro del hub (solo dónde y el error, nunca lo que escribiste): para poder arreglarlo sin preguntarte. */
export const diag = (donde: string, detalle: string, perfil?: string) => post('/api/diag', { donde, detalle: String(detalle || '').slice(0, 300), perfil }).catch(() => { })

/* ---------- lo que se guarda en este navegador ---------- */
const JOBS = 'zazu:jobs', TOK = 'zazu:aprob:', MODELO = 'zazu:hermes-modelo'
type Jobs = Record<string, { job: string; t: number }>   // «<perfil>/<sesión>» → trabajo en marcha

export function leerJobs(): Jobs {
  try { const v = JSON.parse(localStorage.getItem(JOBS) || '{}'); return v && typeof v === 'object' ? v as Jobs : {} } catch { return {} }
}
function escribirJobs(j: Jobs) { try { localStorage.setItem(JOBS, JSON.stringify(j)) } catch { /* sin almacenamiento */ } }
export function registrarJob(k: string, job: string) { const j = leerJobs(); j[k] = { job, t: Date.now() }; escribirJobs(j) }
/** Quita la entrada de esa conversación (solo si sigue siendo ese trabajo). */
export function olvidarJob(k: string, job: string) { const j = leerJobs(); if (j[k]?.job === job) { delete j[k]; escribirJobs(j) } }

export function tokenDe(job: string): string | null { try { return localStorage.getItem(TOK + job) } catch { return null } }
export function guardarToken(job: string, tok: string) { try { localStorage.setItem(TOK + job, tok) } catch { /* sin almacenamiento */ } }
export function borrarToken(job: string) { try { localStorage.removeItem(TOK + job) } catch { /* sin almacenamiento */ } }

export function modeloGuardado(): string | null { try { return localStorage.getItem(MODELO) } catch { return null } }
export function guardarModelo(id: string | null) { try { if (id) localStorage.setItem(MODELO, id); else localStorage.removeItem(MODELO) } catch { /* sin almacenamiento */ } }

/** Limpieza al cargar: trabajos de hace más de 3 h y códigos sin trabajo. */
function limpiar() {
  try {
    const j = leerJobs(), vivos = new Set<string>()
    for (const [k, v] of Object.entries(j)) { if (!v?.job || Date.now() - (v.t || 0) > 3 * 3600e3) delete j[k]; else vivos.add(v.job) }
    escribirJobs(j)
    for (let i = localStorage.length - 1; i >= 0; i--) { const k = localStorage.key(i); if (k?.startsWith(TOK) && !vivos.has(k.slice(TOK.length))) localStorage.removeItem(k) }
  } catch { /* sin almacenamiento */ }
}

/** Enlace de la notificación: /?tab=chat&conv=<sesión>&pf=<perfil>#aprobar=<trabajo>.<código>.
 *  Guarda el código, apunta el trabajo para esa conversación y quita el fragmento de la URL (no se queda en el historial). */
export function tomarHash(): { k: string; job: string } | null {
  try {
    if (!location.hash.startsWith('#aprobar=')) return null
    const m = /^#aprobar=([\w-]{1,64})\.([\w-]{8,256})$/.exec(location.hash)
    history.replaceState(history.state, '', location.pathname + location.search)
    if (!m) return null
    guardarToken(m[1], m[2])
    const q = new URLSearchParams(location.search), conv = q.get('conv')
    if (!conv) return null
    const k = `${q.get('pf') || 'default'}/${conv}`
    registrarJob(k, m[1])
    return { k, job: m[1] }
  } catch { return null }
}
// al cargar la página, antes de que App limpie la URL
limpiar()
tomarHash()

/* ---------- modelos (solo Fran; se piden al abrir el chat) ---------- */
let cache: { t: number; m: Modelos } | null = null
let enCurso: Promise<Modelos | null> | null = null
export function cargarModelos(forzar = false): Promise<Modelos | null> {
  if (cache && !forzar && Date.now() - cache.t < 60e3) return Promise.resolve(cache.m)
  if (!enCurso) enCurso = api<Modelos>('/api/modelos').then(m => { cache = { t: Date.now(), m }; return m }).catch(() => cache?.m ?? null).finally(() => { enCurso = null })
  return enCurso
}
/** Lista de modelos; `cargar=false` no pide nada (p. ej. en las conversaciones antiguas o para invitadas). */
export function useModelos(cargar = true): { modelos: Modelos | null; cargando: boolean } {
  const [m, setM] = useState<Modelos | null>(cache?.m ?? null)
  const [cargando, setCargando] = useState(false)
  useEffect(() => {
    if (!cargar) return
    let vivo = true
    setCargando(true)
    cargarModelos().then(x => { if (vivo) { if (x) setM(x); setCargando(false) } })
    return () => { vivo = false }
  }, [cargar])
  return { modelos: m, cargando }
}
/** «Claude Sonnet 5.5» → «sonnet-5.5» (la etiqueta corta del chip). */
export const nombreCorto = (nombre: string) => nombre.replace(/^(Claude|Google)\s+/i, '').trim().toLowerCase().replace(/\s+/g, '-')

/** Hora del reloj que avanza sola (cuentas atrás, segundos de un paso). */
export function useAhora(cada = 1000, activo = true): number {
  const [t, setT] = useState(Date.now)
  useEffect(() => {
    if (!activo) return
    setT(Date.now())
    const i = setInterval(() => setT(Date.now()), cada)
    return () => clearInterval(i)
  }, [cada, activo])
  return t
}

/* ---------- cómo se enseña cada herramienta ---------- */
const CLAVES_ARGS = ['command', 'path', 'query', 'url', 'goal', 'name', 'pattern', 'action'] as const
/** Una línea con lo esencial de los argumentos (el comando, la ruta, la búsqueda…). Aguanta argumentos recortados. */
export function resumenArgs(args: string): string {
  const s = (args || '').trim()
  if (!s) return ''
  try {
    const d = JSON.parse(s)
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      for (const k of CLAVES_ARGS) if (typeof d[k] === 'string' && d[k].trim()) return linea(d[k])
      const v = Object.values(d).find(x => typeof x === 'string' && x.trim()) as string | undefined
      return v ? linea(v) : linea(JSON.stringify(d))
    }
  } catch {
    for (const k of CLAVES_ARGS) {
      const m = new RegExp(`"${k}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`).exec(s)
      if (m) return linea(desescapar(m[1]))
    }
  }
  return linea(s)
}
/** Argumentos legibles para el detalle desplegado. */
export function argsBonitos(args: string): string {
  try { const d = JSON.parse(args); if (d && typeof d === 'object') return Object.keys(d).length === 1 && typeof Object.values(d)[0] === 'string' ? String(Object.values(d)[0]) : JSON.stringify(d, null, 2) } catch { /* recortados */ }
  return args
}
const desescapar = (x: string) => { try { return JSON.parse(`"${x}"`) as string } catch { return x.replace(/\\n/g, '\n').replace(/\\"/g, '"') } }
/** Primera línea con texto; «…» si hay más líneas detrás (que nada quede escondido debajo) y los espacios largos a la vista. */
const linea = (x: string) => {
  const ls = x.split('\n').map(y => y.trim()).filter(Boolean)
  const l = (ls[0] || '').replace(/[ \t]{10,}/g, m => ` ␠×${m.length} `)
  return l.length > 160 ? `${l.slice(0, 159)}…` : ls.length > 1 ? `${l} …` : l
}

/** Resultado de una herramienta: texto para leer y si fue un error (salida ≠ 0, «error», BLOCKED…).
 *  Entiende el JSON de Hermes ({output, exit_code, error}, {content}, {success}…) aunque venga recortado. */
export function leerResultado(r: string): { texto: string; error: boolean } {
  const s = r || ''
  try {
    const d = JSON.parse(s)
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const err = d.error ? (typeof d.error === 'string' ? d.error : JSON.stringify(d.error)) : ''
      const codigo = typeof d.exit_code === 'number' ? d.exit_code : 0
      const cuerpo = ['output', 'content', 'analysis', 'message', 'result'].map(k => d[k]).find(v => typeof v === 'string' && v.trim()) as string | undefined
      const extra = !cuerpo && typeof d.bytes_written === 'number' ? `${d.bytes_written} bytes escritos${d.resolved_path ? ` en ${d.resolved_path}` : ''}` : ''
      const texto = [cuerpo || extra, err && `error: ${err}`, codigo && !err ? `código de salida ${codigo}` : ''].filter(Boolean).join('\n')
      return { texto: texto || (d.success === true ? 'hecho' : JSON.stringify(d, null, 2)), error: !!err || codigo !== 0 || d.success === false }
    }
  } catch {
    if (s.startsWith('{')) {   // JSON recortado: se saca lo que se pueda
      const out = /"output"\s*:\s*"((?:[^"\\]|\\.)*)/.exec(s), err = /"error"\s*:\s*"((?:[^"\\]|\\.)*)/.exec(s), cod = /"exit_code"\s*:\s*(-?\d+)/.exec(s)
      if (out || err) return { texto: [out && desescapar(out[1]), err && `error: ${desescapar(err[1])}`].filter(Boolean).join('\n'), error: !!err || (!!cod && cod[1] !== '0') }
    }
  }
  return { texto: s, error: /^\s*(BLOCKED|Error:|Traceback)/.test(s) }
}
/** Primera línea útil de un resultado (lo que se ve sin desplegar). */
export const primeraLinea = (texto: string) => linea(texto)
