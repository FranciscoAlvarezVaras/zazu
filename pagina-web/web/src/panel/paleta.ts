/* Paleta de acento del panel: cada persona elige la suya y se guarda en SU dispositivo (localStorage), junto al tema claro/oscuro.
   Solo toca las fichas de acento (--pz-primary y --pz-accion); fondos, rojos y verdes siguen el tema. «ambar» es la de siempre: no pone nada. */
import { useSyncExternalStore } from 'react'
import { useTemaPz } from './tema'

export type Paleta = { id: string; nombre: string; h: number; s: number }
export const PALETAS: Paleta[] = [
  { id: 'ambar', nombre: 'Ámbar', h: 38, s: 75 },
  { id: 'mar', nombre: 'Mar', h: 205, s: 70 },
  { id: 'bosque', nombre: 'Bosque', h: 145, s: 45 },
  { id: 'ciruela', nombre: 'Ciruela', h: 280, s: 40 },
  { id: 'coral', nombre: 'Coral', h: 10, s: 70 },
  { id: 'grafito', nombre: 'Grafito', h: 215, s: 12 },
]
const CLAVE = 'zazu:paleta'      // «ambar» | id de una paleta | «#rrggbb» (color propio)
const FICHAS = ['--pz-primary', '--pz-primary-hover', '--pz-primary-soft', '--pz-primary-contrast', '--pz-accion', '--pz-accion-hover', '--pz-accion-ink']
const oyentes = new Set<() => void>()

const valida = (v: unknown): string => typeof v === 'string' && (PALETAS.some(p => p.id === v) || /^#[0-9a-f]{6}$/i.test(v)) ? v : 'ambar'
const leer = () => { try { return valida(localStorage.getItem(CLAVE)) } catch { return 'ambar' } }
let actual = typeof localStorage === 'undefined' ? 'ambar' : leer()

function hsl(hex: string): [number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn
  if (!d) return [0, 0]
  const h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4
  const l = (mx + mn) / 2
  return [Math.round(((h * 60) + 360) % 360), Math.round(d / (1 - Math.abs(2 * l - 1)) * 100)]
}

export function aplicar(id: string, oscuro: boolean) {
  const st = document.documentElement.style
  if (id === 'ambar') { FICHAS.forEach(f => st.removeProperty(f)); return }
  const [h, s0] = id.startsWith('#') ? hsl(id) : (() => { const p = PALETAS.find(x => x.id === id)!; return [p.h, p.s] as [number, number] })()
  const s = Math.max(10, Math.min(85, s0))
  const c = (l: number, sat = s) => `hsl(${h} ${sat}% ${l}%)`
  const v = oscuro
    ? [c(66), c(76), c(17, Math.min(s, 35)), '#1f1e1c', c(66), c(76), '#1f1e1c']
    : [c(32), c(25), c(93, Math.min(s, 60)), '#ffffff', c(32), c(25), '#ffffff']
  FICHAS.forEach((f, i) => st.setProperty(f, v[i]))
}

export function ponerPaleta(id: string) {
  actual = valida(id)
  try { actual === 'ambar' ? localStorage.removeItem(CLAVE) : localStorage.setItem(CLAVE, actual) } catch { /* vale para esta visita */ }
  aplicar(actual, document.documentElement.dataset.pzTema === 'oscuro')
  oyentes.forEach(f => f())
}

if (typeof document !== 'undefined') aplicar(actual, document.documentElement.dataset.pzTema === 'oscuro')

export function usePaleta(): [string, (id: string) => void] {
  const [tema] = useTemaPz()
  const p = useSyncExternalStore(f => { oyentes.add(f); return () => { oyentes.delete(f) } }, () => actual, () => 'ambar')
  // al cambiar claro/oscuro hay que recalcular los tonos de la paleta elegida
  if (typeof document !== 'undefined') aplicar(p, tema === 'oscuro')
  return [p, ponerPaleta]
}
