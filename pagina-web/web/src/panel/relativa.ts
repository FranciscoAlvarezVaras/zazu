/** «hace un momento» / «hace 2 h» / «ayer» / la fecha corta, a partir de una fecha ISO. Vacío si no se puede.
 *  «ayer» y «hace N días» cuentan días del calendario (no bloques de 24 h): una noticia de hoy a las 00:20 vista
 *  a las 23:50 no es «ayer», y una de ayer a las 09:00 no es «hace 2 días». Va aparte (sin React) para poder
 *  probarla con node: web/scripts/relativa.test.mjs. */
export function relativa(iso: string, ahora: number = Date.now()): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const min = Math.round((ahora - d.getTime()) / 60000)
  if (min < 0) return ''
  if (min < 2) return 'hace un momento'
  if (min < 60) return `hace ${min} min`
  const h = Math.round(min / 60)
  const medianoche = (t: Date) => new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime()
  const dias = Math.round((medianoche(new Date(ahora)) - medianoche(d)) / 86400000)   // round: los días de cambio de hora duran 23 o 25 h
  if (h < 24 || dias === 0) return `hace ${Math.min(h, 23)} h`
  if (dias === 1) return 'ayer'
  if (dias < 7) return `hace ${dias} días`
  return d.toLocaleDateString('es', { day: 'numeric', month: 'short' })
}
