import { aLogin, etiquetaRuta, post } from '../lib'

/* ---------- tipos (contrato del servidor) ---------- */
export type Raiz = 'compartido' | 'notas' | 'whatsapp'
export type Kind = 'folder' | 'pdf' | 'image' | 'video' | 'audio' | 'doc' | 'sheet' | 'text' | 'note' | 'other'
export type Item = { name: string; path: string; dir: boolean; size: number; mtime: number; kind: Kind; folder?: string; origen?: 'whatsapp' | 'app' | ''; n?: number; inline?: boolean }   // n: cuántas cosas hay dentro (carpetas); inline: el navegador lo puede enseñar
export type Listado = { root: Raiz; path: string; readonly: boolean; items: Item[] }
export type EnPapelera = { id: string; nombre: string; origen: string; fecha: number | string; size: number; dir: boolean; caduca?: number }
/** /api/files de antes ({path, entries}): lo siguen usando las invitadas si su servidor no se ha actualizado */
export type ListadoCrudo = Partial<Listado> & { entries?: { name: string; dir: boolean; size: number; mtime: number }[] }

export const RAICES: { id: Raiz; label: string }[] = [
  { id: 'compartido', label: 'Mis carpetas' }, { id: 'notas', label: 'Notas del Cerebro' }, { id: 'whatsapp', label: 'WhatsApp del móvil' },
]
export const raizValida = (r?: string | null): Raiz => RAICES.some(x => x.id === r) ? r as Raiz : 'compartido'
export const LIMITE_SUBIDA = 100 * 1024 * 1024   // Cloudflare corta por encima de 100 MB
export const SISTEMA = ['Recibidos', 'Importante', 'Guardado', 'Adjuntos']   // carpetas de las que dependen Zazu y sus skills

const enc = encodeURIComponent
export const unir = (a: string, b: string) => a ? `${a}/${b}` : b
export const padre = (p: string) => p.split('/').slice(0, -1).join('/')
export const base = (p: string) => p.split('/').pop() || p
export const migas = (p: string) => p.split('/').filter(Boolean).join(' › ')
/** «Carpetas › Importante › Viajes»: así habla Zazu de las rutas */
export const etiqueta: (root: Raiz, p: string) => string = etiquetaRuta
/** Adjuntos (el chat y Obsidian enlazan a sus archivos) y las carpetas del sistema no se mueven, renombran ni borran */
export const protegido = (p: string) => p === 'Adjuntos' || p.startsWith('Adjuntos/') || SISTEMA.includes(p)

const EXT: Record<string, Kind> = {}
const tipos: [Kind, string][] = [
  ['pdf', 'pdf'], ['image', 'jpg jpeg png gif webp heic heif bmp svg avif'], ['video', 'mp4 mov webm mkv avi 3gp m4v'],
  ['audio', 'mp3 ogg opus m4a wav aac flac amr'], ['doc', 'doc docx odt rtf pages ppt pptx odp key epub'], ['sheet', 'xls xlsx ods csv numbers'],
  ['text', 'txt log json py js ts tf yaml yml xml html css sh ini conf'], ['note', 'md'],
]
for (const [k, l] of tipos) for (const e of l.split(' ')) EXT[e] = k
export const extension = (n: string) => { const i = n.lastIndexOf('.'); return i > 0 ? n.slice(i + 1).toLowerCase() : '' }
export const kindOf = (name: string, dir = false): Kind => dir ? 'folder' : EXT[extension(name)] || 'other'
export const KIND_LABEL: Record<Kind, string> = { folder: 'Carpeta', pdf: 'PDF', image: 'Foto', video: 'Vídeo', audio: 'Audio', doc: 'Documento', sheet: 'Hoja de cálculo', text: 'Texto', note: 'Nota', other: 'Archivo' }

/** Un archivo del que solo se sabe la ruta (enlace directo ?archivo=…) */
export const itemDe = (path: string, dir = false): Item => ({ name: base(path), path, dir, size: 0, mtime: 0, kind: kindOf(base(path), dir) })

export function normalizar(d: ListadoCrudo | null, root: Raiz): Listado | null {
  if (!d) return null
  const path = d.path || ''
  const items = d.items || (d.entries || []).map(e => ({ ...e, path: unir(path, e.name), kind: kindOf(e.name, e.dir) }))
  return { root: d.root || root, path, readonly: !!d.readonly, items: items.map(i => ({ ...i, kind: i.kind || kindOf(i.name, i.dir) })) }
}

/* ---------- URLs (las descargas: urlDescarga de lib) ---------- */
/** Sin root para Mis carpetas: las invitadas no lo mandan y el servidor usa su propio espacio */
export const urlListado = (root: Raiz, path: string) => `/api/files?path=${enc(path)}${root !== 'compartido' ? `&root=${root}` : ''}`

/* ---------- acciones ---------- */
export const mover = (path: string, destino: string) => post<{ ok: boolean; path: string }>('/api/mover', { path, destino })
export const renombrar = (path: string, nombre: string) => post<{ ok: boolean; path: string }>('/api/renombrar', { path, nombre })
export const aPapelera = (path: string) => post<{ ok: boolean; id: string }>('/api/papelera', { path })
export const restaurar = (id: string) => post<{ ok: boolean; path: string }>('/api/restaurar', { id })
export const aMiWhatsApp = (path: string, root: Raiz) => post<{ ok: boolean }>('/api/enviar-whatsapp', { path, root })
export const crearCarpeta = (path: string, name: string) => post<{ ok: boolean }>('/api/mkdir', { path, name })

/** Subida con progreso (fetch no lo da). El servidor añade « (2)» si el nombre ya existe y devuelve el nombre final. */
export function subir(ruta: string, cuerpo: Blob, nombre: string, progreso?: (pct: number) => void) {
  return new Promise<{ ok: boolean; name: string }>((res, rej) => {
    const x = new XMLHttpRequest()
    x.open('POST', `/api/upload?path=${enc(ruta)}&name=${enc(nombre)}`)
    x.setRequestHeader('X-Hub', '1')
    x.upload.onprogress = e => { if (e.lengthComputable && progreso) progreso(Math.round(e.loaded / e.total * 100)) }
    x.onload = () => {
      if (x.status === 401) { aLogin(); return rej(new Error('sesión caducada')) }
      let d: { error?: string; ok?: boolean; name?: string } = {}
      try { d = JSON.parse(x.responseText) } catch { /* Cloudflare responde HTML */ }
      if (x.status >= 200 && x.status < 300) return res({ ok: true, name: d.name || nombre })
      rej(new Error(d.error || (x.status === 413 ? 'pesa demasiado para subirlo por internet' : x.status >= 500 ? 'algo falló; inténtalo otra vez' : String(x.status))))
    }
    x.onerror = () => rej(Object.assign(new Error('se cortó la conexión'), { red: true }))
    x.send(cuerpo)
  })
}

/* Compartir › Zazu: el service worker deja cada archivo en la caché «compartidos» (/compartido/<n>, cabeceras X-Nombre
   y X-Tam). Nada se sube sin que Fran lo confirme: cualquier web podría mandar archivos a /compartir. */
const COMPARTIDOS = 'compartidos'
export type Pendiente = { key: string; nombre: string; size: number }

/** Lo que espera en la caché, sin subir nada */
export async function pendientesCompartidos(): Promise<Pendiente[]> {
  if (!('caches' in window) || !(await caches.has(COMPARTIDOS))) return []
  const c = await caches.open(COMPARTIDOS), out: Pendiente[] = []
  for (const k of await c.keys()) {
    if (!new URL(k.url).pathname.startsWith('/compartido/')) continue
    const r = await c.match(k)
    if (!r) continue
    let nombre = 'archivo compartido'
    try { nombre = decodeURIComponent(r.headers.get('X-Nombre') || '') || nombre } catch { /* nombre mal codificado */ }
    out.push({ key: k.url, nombre, size: Number(r.headers.get('X-Tam')) || (await r.blob()).size })
  }
  if (!out.length) await caches.delete(COMPARTIDOS)
  return out
}

async function limpiar(c: Cache) { if (!(await c.keys()).length) await caches.delete(COMPARTIDOS) }

/** «Descartar» (o cerrar sin guardar): se borran de la caché sin subirlos */
export async function descartarCompartidos(ps: Pendiente[]) {
  if (!('caches' in window) || !(await caches.has(COMPARTIDOS))) return
  const c = await caches.open(COMPARTIDOS)
  for (const p of ps) await c.delete(p.key)
  await limpiar(c)
}

/** «Guardar»: sube solo los que Fran ha visto en la lista. Devuelve cuántos había (-1 si ya se están subiendo). */
let recogiendo = false   // un segundo toque no sube nada repetido
type Avisos = { antes: () => Promise<void>; alSubir: (nombreFinal: string, size: number) => void; alFallar: (nombre: string, e: Error) => void }
export async function recogerCompartidos(destino: string, ps: Pendiente[], { antes, alSubir, alFallar }: Avisos) {
  if (recogiendo) return -1
  if (!('caches' in window) || !ps.length) return 0
  recogiendo = true   // antes de cualquier await
  try {
    if (!(await caches.has(COMPARTIDOS))) return 0
    const c = await caches.open(COMPARTIDOS)
    await antes()
    for (const p of ps) {
      const r = await c.match(p.key)
      if (!r) continue
      const blob = await r.blob()
      try { const d = await subir(destino, blob, p.nombre); alSubir(d.name, blob.size); await c.delete(p.key) }
      catch (e) { alFallar(p.nombre, e as Error); if (!(e as { red?: boolean }).red) await c.delete(p.key) }   // sin red: se queda y se vuelve a preguntar la próxima vez
    }
    await limpiar(c)
    return ps.length
  } finally { recogiendo = false }
}
