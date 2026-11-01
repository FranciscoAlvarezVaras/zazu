/* Tema del panel (claro / oscuro): se guarda en este dispositivo y se pone en <html data-pz-tema> (index.html lo adelanta para que no haya destello). */
import { useSyncExternalStore } from 'react'

export type TemaPz = 'claro' | 'oscuro'
const CLAVE = 'zazu:tema'
const oyentes = new Set<() => void>()
const leer = (): TemaPz => { try { return localStorage.getItem(CLAVE) === 'oscuro' ? 'oscuro' : 'claro' } catch { return 'claro' } }
let actual: TemaPz = typeof localStorage === 'undefined' ? 'claro' : leer()
if (typeof document !== 'undefined') document.documentElement.dataset.pzTema = actual

export function ponerTema(t: TemaPz) {
  actual = t
  document.documentElement.dataset.pzTema = t
  try { localStorage.setItem(CLAVE, t) } catch { /* sin almacenamiento: vale para esta visita */ }
  oyentes.forEach(f => f())
}
export function useTemaPz(): [TemaPz, (t: TemaPz) => void] {
  const t = useSyncExternalStore(f => { oyentes.add(f); return () => { oyentes.delete(f) } }, () => actual, () => 'claro' as TemaPz)
  return [t, ponerTema]
}
