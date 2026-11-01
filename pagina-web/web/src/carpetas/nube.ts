import { useEffect, useState } from 'react'
import { api, post, urlDescarga } from '../lib'
import { aPapelera, base, kindOf, restaurar } from './api'
import type { Kind } from './api'
import { textoCaja } from './mapa'
import type { Caja, Geo } from './mapa'

/* Mi nube: lo que habla la Galería con /api/nube/* (solo Fran). Las rutas son siempre relativas a Compartido. */
const enc = encodeURIComponent

/* ---------- tipos (contrato del servidor) ---------- */
export type Orden = 'nuevas' | 'antiguas' | 'tamano'
export const ORDENES: [Orden, string][] = [['nuevas', 'Más nuevas'], ['antiguas', 'Más antiguas'], ['tamano', 'Más pesadas']]
export type Medio = { name: string; path: string; size: number; mtime: number; kind: Kind; fav: boolean }
export type Resumen = { bytes: number; fotos: number; videos: number; disco: { total: number; libre: number }
  tipos?: Partial<Record<Kind, { n: number; bytes: number }>>; favoritos?: number; albumes?: number; geo?: Geo }
export type Album = { id: string; nombre: string; n: number; portada: string | null; creado: number }
export type Copia = { path: string; name: string; mtime: number }
export type GrupoDup = { size: number; items: Copia[] }
export type Duplicados = { estado: 'calculando' | 'listo' | 'error'; grupos: GrupoDup[]; ahorro: number; vistos: number; total?: number }   // total: los grupos que hay en realidad (el servidor manda 200 como mucho)
export type Enlace = { id: string; token: string; path: string; caduca: number; visitas: number; clave: boolean; url?: string }
export type Filtros = { tipo: '' | 'image' | 'video'; en: string; q: string; dia: boolean; fav: boolean; album: string; orden: Orden; caja: Caja | null }   // caja: solo lo que tiene GPS dentro de ese recuadro (una zona del mapa)

/* ---------- utilidades ---------- */
/** Un medio del servidor, o null si no trae ni ruta (una respuesta rara no rompe la pantalla) */
export function medioDe(x: unknown): Medio | null {
  const m = x as Partial<Medio> | null
  if (!m || typeof m.path !== 'string' || !m.path) return null
  return { path: m.path, name: typeof m.name === 'string' && m.name ? m.name : base(m.path), size: Number(m.size) || 0, mtime: Number(m.mtime) || 0, kind: m.kind === 'video' ? 'video' : 'image', fav: !!m.fav }
}
/** El texto de un error para enseñarlo tal cual: el del servidor, o uno claro si llegó algo que no era JSON o solo un código */
export function msg(e: unknown): string {
  const t = e instanceof Error ? e.message : ''
  if (e instanceof SyntaxError) return 'el servidor respondió algo inesperado'
  if (/^\d{3}$/.test(t)) return t === '404' ? 'no se encontró' : t === '403' ? 'no tienes permiso' : t === '429' ? 'demasiadas peticiones; espera un minuto' : `error ${t}`
  return t || 'algo falló; inténtalo otra vez'
}
const F_DIA = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })
const F_MES = new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric' })
const F_HORA = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const ok = (t: number) => Number.isFinite(t) && t > 0
export const fecha = (t: number) => ok(t) ? F_DIA.format(t * 1000) : ''
export const fechaHora = (t: number) => ok(t) ? F_HORA.format(t * 1000) : ''
export const mesDe = (t: number) => { if (!ok(t)) return 'Sin fecha'; const s = F_MES.format(t * 1000); return s[0].toUpperCase() + s.slice(1) }
export const num = (x: number) => x.toLocaleString('es-ES')
export const plural = (x: number, uno: string, varios: string) => `${num(x)} ${x === 1 ? uno : varios}`
/** «en 5 horas», «en 3 días», «ya caducó» */
export function enCuanto(t: number) {
  const h = Math.round((t * 1000 - Date.now()) / 36e5)
  return h < 0 ? 'ya caducó' : h < 1 ? 'en menos de una hora' : h < 48 ? `en ${plural(h, 'hora', 'horas')}` : `en ${plural(Math.round(h / 24), 'día', 'días')}`
}
/** La fecha de una foto está en su nombre (IMG_20240117_…): se saca de ahí, como hace el servidor */
const FECHA_NOMBRE = /(?:^|\D)(20\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)/
export function fechaDeNombre(nombre: string, mtime: number) {
  const m = FECHA_NOMBRE.exec(nombre)
  if (!m) return mtime
  const t = new Date(+m[1], +m[2] - 1, +m[3], 12).getTime() / 1000
  return Number.isFinite(t) ? Math.floor(t) : mtime
}
/** Un archivo recién subido, como lo enseña la cuadrícula (el servidor lo verá en su índice en un minuto); null si no es foto ni vídeo */
export function medioSubido(ruta: string, size: number): Medio | null {
  const k = kindOf(base(ruta))
  return k === 'image' || k === 'video' ? { path: ruta, name: base(ruta), size, mtime: fechaDeNombre(base(ruta), Math.floor(Date.now() / 1000)), kind: k, fav: false } : null
}

/** ¿Está escribiendo en un campo? (entonces los atajos de teclado no valen) */
export const escribiendo = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))

/** Copia al portapapeles (si la web no tiene permiso, con el truco del cuadro de texto) */
export async function copiar(texto: string) {
  try { await navigator.clipboard.writeText(texto); return true } catch { /* sin permiso o sin HTTPS */ }
  const antes = document.activeElement as HTMLElement | null
  const t = document.createElement('textarea')
  t.value = texto; t.setAttribute('readonly', ''); t.style.cssText = 'position:fixed;top:0;left:0;opacity:0'
  document.body.appendChild(t); t.select()
  let hecho = false
  try { hecho = document.execCommand('copy') } catch { /* sin portapapeles */ }
  t.remove(); antes?.focus?.()
  return hecho
}

/* ---------- direcciones ---------- */
export const mini = (path: string) => `/api/nube/mini?path=${enc(path)}`
/** Lo que baja el visor para una foto, por orden: un JPEG de ~1600 px que prepara el servidor (los JPEG de varios MB y los HEIC, que el navegador no sabe poner), el original y, por fin, la miniatura */
const REDUCIBLES = /\.(jpe?g|heic|heif)$/i
export const fuentesDe = (m: Pick<Medio, 'name' | 'path'>) => [...REDUCIBLES.test(m.name) ? [`/api/nube/vista?path=${enc(m.path)}&w=1600`] : [], urlDescarga('compartido', m.path, true), mini(m.path)]
export const urlZipAlbum = (id: string) => `/api/nube/zip?album=${enc(id)}`
export const urlZipFav = '/api/nube/zip?fav=1'
/** Lo que se pide a /api/nube/medios (sin desde ni n): solo lo que hace falta, para que un servidor más viejo no se líe con parámetros vacíos */
export function consulta(f: Filtros) {
  const p: [string, string][] = [['tipo', f.tipo], ['en', f.en], ['q', f.q], ['dia', f.dia ? 'hoy' : ''], ['fav', f.fav ? '1' : ''], ['album', f.album], ['orden', f.orden === 'nuevas' ? '' : f.orden], ['bbox', f.caja ? textoCaja(f.caja) : '']]
  return p.filter(([, v]) => v).map(([k, v]) => `${k}=${enc(v)}`).join('&')
}
/** La dirección que ve quien recibe un enlace: la que mande el servidor y, si no, la de la web pública de Zazu */
const PUBLICA = /(^|\.)holazazu\.app$/.test(location.hostname) ? location.origin : 'https://holazazu.app'
export const urlEnlace = (e: Pick<Enlace, 'token' | 'url'>) => e.url || `${PUBLICA}/c/${e.token}`

/* ---------- llamadas ---------- */
export const ponerFav = async (paths: string[], on: boolean) => {
  for (let i = 0; i < paths.length; i += 500) await post<{ ok: boolean; total: number }>('/api/nube/fav', { paths: paths.slice(i, i + 500), on })   // el servidor admite hasta 500 por vez
}
type AccionAlbum = { accion: 'crear' | 'renombrar' | 'borrar' | 'añadir' | 'quitar'; id?: string; nombre?: string; paths?: string[] }
export const accionAlbum = (a: AccionAlbum) => post<{ ok: boolean; id?: string }>('/api/nube/album', a)
/** Añadir o quitar fotos de un álbum: el servidor admite hasta 500 por vez, así que se manda en tandas */
export async function albumLote(accion: 'añadir' | 'quitar', id: string, paths: string[]) {
  for (let i = 0; i < paths.length; i += 500) await accionAlbum({ accion, id, paths: paths.slice(i, i + 500) })
}
/** Crea el álbum de una vez con sus primeras 500 fotos (si falla algo, no queda un álbum a medias) y añade el resto */
export async function crearAlbumCon(nombre: string, paths: string[]) {
  const d = await accionAlbum(paths.length ? { accion: 'crear', nombre, paths: paths.slice(0, 500) } : { accion: 'crear', nombre })
  if (!d || typeof d.id !== 'string' || !d.id) throw new Error('el servidor no devolvió el álbum')
  if (paths.length > 500) await albumLote('añadir', d.id, paths.slice(500))
  return d.id
}
export const verDuplicados = (rehacer = false) => api<Duplicados>(`/api/nube/duplicados${rehacer ? '?rehacer=1' : ''}`)
export const crearEnlace = (path: string, horas: number, clave: string, sinGps: boolean) =>   // gps: el archivo trae ubicación; sin_gps: el enlace sirve una copia sin ella (el servidor la quita salvo que se mande sin_gps: false)
  post<{ ok: boolean; token: string; url: string; caduca: number; gps?: boolean; sin_gps?: boolean }>('/api/nube/enlace', { path, horas, ...(clave ? { clave } : {}), sin_gps: sinGps })
export const verEnlaces = (path?: string) => api<{ items: Enlace[] }>(`/api/nube/enlaces${path ? `?path=${enc(path)}` : ''}`)
export const revocarEnlace = (token: string) => post<{ ok: boolean }>('/api/nube/enlace/revocar', { token })

/* ---------- papelera en tandas (con Deshacer) ---------- */
const espera = (ms: number) => new Promise<void>(r => setTimeout(r, ms))
export type Tirada = { path: string; id: string }
/** Uno a uno, como en Carpetas. Si el servidor frena (demasiadas peticiones) se espera y se sigue. `parar.current = true` corta la tanda. */
export async function tirarTodos(paths: string[], avance?: (hechos: number) => void, parar?: { current: boolean }) {
  const hechos: Tirada[] = [], fallos: { path: string; error: string }[] = []
  for (const [k, p] of paths.entries()) {
    if (parar?.current) break
    for (let intento = 0; ; intento++) {
      try { hechos.push({ path: p, id: (await aPapelera(p)).id }); break }
      catch (e) {
        const m = msg(e)
        if (intento < 3 && /demasiadas/i.test(m)) { await espera(15000); continue }
        fallos.push({ path: p, error: m }); break
      }
    }
    avance?.(k + 1)
  }
  return { hechos, fallos }
}
/** Deshacer: cada uno vuelve a su sitio (si el nombre estaba ocupado, con otro nombre: por eso se devuelve la ruta nueva) */
export async function restaurarTodos(ts: Tirada[]) {
  const vueltos: { path: string; nuevo: string }[] = []
  let fallos = 0
  for (const t of ts) {
    try { const r = await restaurar(t.id); vueltos.push({ path: t.path, nuevo: typeof r.path === 'string' && r.path ? r.path : t.path }) } catch { fallos++ }
  }
  return { vueltos, fallos }
}

/* ---------- vídeos del móvil (HEVC) ---------- */
/** El servidor convierte una vez a H.264 los vídeos que el navegador no sabe poner (la primera vez se espera) y los demás suenan al momento.
 *  null mientras se pregunta; `listo: false` mientras se convierte. Se usa en la Galería y en la vista previa de Carpetas. */
export function useVideo(path: string | null) {
  const [v, setV] = useState<{ path: string; src: string; listo: boolean; error?: boolean } | null>(null)
  useEffect(() => {
    if (!path) return
    let vivo = true, t = 0, vez = 0
    const mirar = async () => {
      try {
        const e = await api<{ listo?: boolean; directo?: boolean; error?: boolean }>(`/api/nube/video-estado?path=${enc(path)}`)
        if (!vivo) return
        if (e.listo) setV({ path, src: e.directo ? urlDescarga('compartido', path, true) : `/api/nube/video?path=${enc(path)}`, listo: true })
        else if (e.error) setV({ path, src: '', listo: false, error: true })   // el servidor no pudo convertirlo: no se espera más
        else { setV({ path, src: '', listo: false }); t = window.setTimeout(mirar, ++vez < 30 ? 2000 : 5000) }   // a la larga, sin machacar al servidor
      } catch { if (vivo) setV({ path, src: urlDescarga('compartido', path, true), listo: true }) }   // sin saber nada: el original
    }
    void mirar()
    return () => { vivo = false; clearTimeout(t) }
  }, [path])
  return v && v.path === path ? v : null   // el de la ruta anterior no vale mientras llega el nuevo
}
