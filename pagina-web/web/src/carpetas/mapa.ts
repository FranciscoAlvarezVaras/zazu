import { api } from '../lib'
import type { Kind } from './api'

/* El mapa de Mi nube: lo que habla la Galería con /api/nube/mapa y las cuentas del mapa (Mercator de teselas de 256 px). */

/* ---------- tipos (contrato del servidor) ---------- */
/** [sur, oeste, norte, este] en grados. Si oeste > este, cruza los 180° */
export type Caja = [number, number, number, number]
export type Geo = { conGps: number; sinGps: number; indexando: boolean; progreso: number }
/** Una celda del mapa: cuántos medios agrupa (n), su sitio medio, la portada (el más nuevo) y, si el servidor la manda, el recuadro justo de lo que agrupa */
export type Punto = { lat: number; lon: number; n: number; path: string; kind: Kind; caja?: Caja }
export type RespMapa = Geo & { puntos: Punto[] }

const fin = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x)
/** Un punto del servidor, o null si no sirve (una respuesta rara no rompe la pantalla) */
export function puntoDe(x: unknown): Punto | null {
  const p = x as Partial<Punto> | null
  if (!p || !fin(p.lat) || !fin(p.lon) || Math.abs(p.lat) > 90 || Math.abs(p.lon) > 180 || typeof p.path !== 'string' || !p.path) return null
  const c = p.caja
  return { lat: p.lat, lon: p.lon, n: fin(p.n) && p.n >= 1 ? Math.floor(p.n) : 1, path: p.path, kind: p.kind === 'video' ? 'video' : 'image',
    caja: Array.isArray(c) && c.length === 4 && c.every(fin) ? c as Caja : undefined }
}
export function geoDe(x: unknown): Geo {
  const g = (x || {}) as Partial<Geo>
  return { conGps: fin(g.conGps) ? g.conGps : 0, sinGps: fin(g.sinGps) ? g.sinGps : 0, indexando: !!g.indexando, progreso: fin(g.progreso) ? Math.min(1, Math.max(0, g.progreso)) : 0 }
}

/* ---------- llamadas ---------- */
const r6 = (v: number) => +v.toFixed(6)
/** ?bbox= de /api/nube/medios: s,w,n,e (el servidor no admite números fuera de -90..90 y -180..180) */
export const textoCaja = ([s, w, n, e]: Caja) => [acotar(s, -90, 90), acotar(w, -180, 180), acotar(n, -90, 90), acotar(e, -180, 180)].map(r6).join(',')
/** Las celdas con GPS dentro de la caja (el mundo entero si no se da) para ese zoom (0 a 18), y cómo va el índice del GPS */
export async function leerMapa(z: number, c?: Caja, signal?: AbortSignal): Promise<RespMapa> {
  const [s, w, n, e] = c ? textoCaja(c).split(',') : []
  const d = await api<{ puntos?: unknown } & Partial<Geo>>(`/api/nube/mapa?z=${z}${c ? `&s=${s}&w=${w}&n=${n}&e=${e}` : ''}`, { signal })
  return { ...geoDe(d), puntos: (Array.isArray(d?.puntos) ? d.puntos : []).map(puntoDe).filter((p): p is Punto => !!p) }
}

/** Cuántas fotos y vídeos con GPS hay dentro de la caja: el total exacto que da /api/nube/medios (una sola foto de muestra) */
export async function contarZona(c: Caja, signal?: AbortSignal): Promise<number> {
  const d = await api<{ total?: unknown }>(`/api/nube/medios?bbox=${textoCaja(c)}&n=1`, { signal })
  return fin(d?.total) ? d.total : 0
}

/* ---------- cuentas del mapa ---------- */
export const T = 256        // lado de una tesela
export const ZMAX = 18      // el servidor agrupa hasta el zoom 18
const LAT_MAX = 85.0511287798
const RAD = Math.PI / 180
export const acotar = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v))
/** Posición 0..1 en el mapa (x de oeste a este, y de norte a sur) y al revés */
export const mx = (lon: number) => (lon + 180) / 360
export const my = (lat: number) => { const s = Math.sin(acotar(lat, -LAT_MAX, LAT_MAX) * RAD); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI) }
export const lonDe = (x: number) => x * 360 - 180
export const latDe = (y: number) => Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) / RAD

/** Qué se ve: el centro (0..1 en el mapa) y el zoom, con decimales mientras se pellizca */
export type Vista = { x: number; y: number; z: number }
export type Tam = { w: number; h: number }
/** Lo que cabe en pantalla: el zoom no baja de donde el mundo llena el recuadro (sin copias repetidas) ni pasa de 18, y no se sale por arriba ni por abajo; por los lados da la vuelta */
export function limitar(v: Vista, t: Tam): Vista {
  const z = acotar(v.z, Math.max(0, Math.log2(Math.max(t.w, t.h, 1) / T)), ZMAX), mitad = t.h / 2 / (T * 2 ** z)
  return { x: ((v.x % 1) + 1) % 1, y: acotar(v.y, mitad, 1 - mitad), z }
}
/** La vista que encuadra una caja (tope: hasta dónde acercar si es muy pequeña) */
export function ajustar(c: Caja, t: Tam, relleno = 40, tope = 14): Vista {
  const [s, w, n, e] = c
  const dx = Math.abs(mx(e) - mx(w)), dy = Math.abs(my(s) - my(n))
  const zx = dx > 1e-9 ? Math.log2(Math.max(40, t.w - 2 * relleno) / (T * dx)) : tope, zy = dy > 1e-9 ? Math.log2(Math.max(40, t.h - 2 * relleno) / (T * dy)) : tope
  return limitar({ x: (mx(w) + mx(e)) / 2, y: (my(s) + my(n)) / 2, z: Math.min(zx, zy, tope) }, t)
}
/** La caja del mundo que se ve (margen: fracción de la pantalla que se añade por cada lado). Pasa de -180 a 180 si el mundo cabe entero. */
export function cajaVista(v: Vista, t: Tam, margen = 0): Caja {
  const S = T * 2 ** v.z, dx = t.w * (0.5 + margen) / S, dy = t.h * (0.5 + margen) / S
  const n = latDe(acotar(v.y - dy, 0, 1)), s = latDe(acotar(v.y + dy, 0, 1))
  if (2 * dx >= 1) return [s, -180, n, 180]
  return [s, lonDe((((v.x - dx) % 1) + 1) % 1), n, lonDe((((v.x + dx) % 1) + 1) % 1)]
}
/** ¿Está la caja `a` entera dentro de `b`? (con cajas que cruzan los 180° no se sabe: false) */
export const cabe = (a: Caja, b: Caja) => a[1] <= a[3] && b[1] <= b[3] && a[0] >= b[0] && a[2] <= b[2] && a[1] >= b[1] && a[3] <= b[3]
/** Lo que agrupa un punto: el recuadro que manda el servidor o, si no lo manda, su celda de la rejilla (64 px de un mapa de teselas de 256) */
export function cajaDe(p: Punto, z: number): Caja {
  if (p.caja) return p.caja
  const N = Math.max(1, Math.floor(T * 2 ** Math.round(z) / 64)), cx = Math.min(N - 1, Math.floor(mx(p.lon) * N)), cy = Math.min(N - 1, Math.floor(my(p.lat) * N))
  return [latDe((cy + 1) / N), lonDe(cx / N), latDe(cy / N), lonDe((cx + 1) / N)]
}
/** La caja que reúne a todas las demás (null si no hay ninguna) */
export const unir = (cs: Caja[]): Caja | null => cs.length ? cs.reduce<Caja>((a, c) => [Math.min(a[0], c[0]), Math.min(a[1], c[1]), Math.max(a[2], c[2]), Math.max(a[3], c[3])], [...cs[0]]) : null

/* ---------- textos ---------- */
const F_GRADOS = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
/** «39,5° N · 0,4° O», redondeado a un decimal (unos 11 km): para un lugar basta y no dice dónde vives */
export const coordenadas = (lat: number, lon: number) => `${F_GRADOS.format(Math.abs(lat))}° ${lat < 0 ? 'S' : 'N'} · ${F_GRADOS.format(Math.abs(lon))}° ${lon < 0 ? 'O' : 'E'}`
/** El centro de una caja, en el mismo formato */
export function centroDe(c: Caja) {
  const lon = c[1] <= c[3] ? (c[1] + c[3]) / 2 : (c[1] + c[3] + 360) / 2   // (cruzando los 180° la mitad cae al otro lado)
  return coordenadas((c[0] + c[2]) / 2, lon > 180 ? lon - 360 : lon)
}
/** 1.234 → «1,2 mil» (para que quepa en una burbuja) */
export const corto = (n: number) => n < 1000 ? String(n) : `${(n / 1000).toLocaleString('es-ES', { maximumFractionDigits: n < 10000 ? 1 : 0 })} mil`
