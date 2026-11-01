/* Formatos y pequeños ayudantes que comparten Inicio, Empleo, Dinero y el panel derecho. */
import type { Suscripcion, Tablero, Tarjeta } from './api'

export const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
export const mesDe = (m: string | null) => m ? MESES[Number(m.slice(5, 7)) - 1] ?? m : ''
/** 1250.5 → «1.250,50 €» (siempre con punto de millar, como en los mensajes del vigía). */
export const eur = (n: number, moneda = 'EUR') => {
  const [ent, dec] = Math.abs(n).toFixed(2).split('.')
  return `${n < 0 ? '-' : ''}${ent.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${dec} ${moneda === 'EUR' ? '€' : moneda === 'USD' ? 'US$' : moneda}`
}
export const nombreCat = (c: string) => c === 'sin_clasificar' ? 'Sin clasificar' : cap(c)
export const paraCancelar = (s: Suscripcion) => s.cancelar && s.estado !== 'posible_cancelada'
/** Día de la semana de un «AAAA-MM-DD»: «lunes». */
export const diaSemana = (f: string | null) => { if (!f) return ''; const d = new Date(f + 'T12:00'); return isNaN(d.getTime()) ? '' : d.toLocaleDateString('es', { weekday: 'long' }) }
/** «5 de octubre». */
export const fechaLarga = (f: string | null) => { if (!f) return ''; const d = /^\d{4}-\d{2}-\d{2}$/.test(f) ? new Date(f + 'T12:00') : new Date(f); return isNaN(d.getTime()) ? '' : d.toLocaleDateString('es', { day: 'numeric', month: 'long' }) }

export type TableroSus = Extract<Tablero, { clase: 'suscripciones' }>
export type TableroKanban = Extract<Tablero, { clase: 'kanban' }>
/** El tablero de suscripciones (con sus gastos) si se pudo leer; null si falta o falló: nunca se inventa. */
export const tableroSus = (t: Tablero[] | null): TableroSus | null => { const b = t?.find(x => x.id === 'suscripciones'); return b && b.ok && b.clase === 'suscripciones' ? b : null }
export const tableroKanban = (t: Tablero[] | null, id: string): TableroKanban | null => { const b = t?.find(x => x.id === id); return b && b.ok && b.clase === 'kanban' ? b : null }
export const tarjetaDe = (b: TableroKanban | null, ruta: string): Tarjeta | null => { for (const c of b?.columnas || []) { const x = c.tarjetas.find(t => t.ruta === ruta); if (x) return x } return null }

/** La inicial para el círculo o el cuadradito de una empresa, persona o suscripción. */
export const inicial = (s: string | null | undefined) => (s || '?').replace(/[^\p{L}\p{N}]/gu, '').slice(0, 1).toUpperCase() || '?'
