// Comprueba el contraste (WCAG 2.x) de las fichas de color de Zazu: node web/scripts/contraste-panel.mjs [-v]
// Lee los dos bloques de color de src/panel/panel.css (claro y oscuro) y falla (exit 1) si algún par de texto baja de 4,5:1
// o algún control o gráfico (bordes de casillas, puntos, contornos) baja de 3:1.
import { readFileSync } from 'node:fs'
const css = readFileSync(new URL('../src/panel/panel.css', import.meta.url), 'utf8')
const bloque = (sel) => {
  const i = css.indexOf(sel); if (i < 0) throw new Error('no encuentro ' + sel)
  const j = css.indexOf('}', i); const t = {}
  for (const m of css.slice(i, j).matchAll(/--pz-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b/g)) t[m[1]] = m[2]
  return t
}
const lum = (h) => { const c = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(v => v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4); return .2126 * c[0] + .7152 * c[1] + .0722 * c[2] }
const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05) }
const claro = bloque(':root {'), oscuro = { ...claro, ...bloque(':root[data-pz-tema="oscuro"]') }

const superficies = ['background', 'surface', 'surface-subtle', 'primary-soft', 'secondary-soft', 'success-soft']
const pares = [
  // texto normal sobre todas las superficies
  ...['text', 'text-muted', 'text-soft'].flatMap(f => superficies.map(b => [f, b])),
  ['text', 'surface-hover'], ['text-muted', 'surface-hover'],
  // enlaces, menú activo, filtros (turquesa) y lo urgente (coral)
  ['primary', 'background'], ['primary', 'surface'], ['primary', 'primary-soft'], ['primary', 'surface-subtle'],
  ['secondary-dark', 'secondary-soft'], ['secondary-dark', 'surface'], ['secondary-dark', 'background'], ['danger', 'surface'], ['danger', 'background'], ['danger', 'danger-soft'],
  ['success', 'surface'], ['success', 'background'], ['success', 'success-soft'],
  // texto sobre botones rellenos
  ['accion-ink', 'accion'], ['accion-ink', 'accion-hover'], ['primary-contrast', 'primary'], ['primary-contrast', 'primary-hover'], ['secondary-contrast', 'secondary'],
  ['accion', 'surface'], ['accion', 'background'],   // el azul de acción como texto (enlaces de botones suaves)
  // barra de arriba
  ['barra-ink', 'barra'], ['barra-ink', 'barra-hover'], ['barra-campo-ink', 'barra-campo'], ['insignia-ink', 'insignia'], ['avatar-ink', 'avatar'],
  // tarjeta de permiso y avisos
  ['aviso', 'aviso-bg'], ['aviso-contraste', 'aviso-relleno'], ['text', 'aviso-bg'], ['text-muted', 'aviso-bg'],
  // lo que se pinta sobre el hover de las listas
  ['text-muted', 'surface-subtle'],
  // menú lateral / cajón y la burbuja de tus mensajes (2026-10-22, chat de lectura)
  ['text', 'lateral'], ['text-muted', 'lateral'], ['primary', 'lateral'], ['text', 'burbuja'], ['text-muted', 'burbuja'],
]
// componentes y gráficos sin texto (bordes de casillas y campos, puntos, contornos del logo): WCAG 1.4.11 pide 3:1
const graficos = [
  ['control', 'surface'], ['control', 'background'], ['control', 'surface-subtle'], ['border-control', 'surface'], ['border-control', 'background'], ['border-control', 'surface-subtle'],
  ['background', 'text'],   // aviso de versión (lectura.css): el botón va en --pz-background sobre la píldora en --pz-text (con --pz-accion daba 1,75:1 en oscuro)
  ['neutral-accent', 'surface'], ['neutral-accent', 'background'], ['accion', 'surface'], ['primary', 'surface'],   // (--pz-secondary, el rojo decorativo, solo acompaña a texto: no se mide)
  
  ['cat-1', 'surface'], ['cat-2', 'surface'], ['cat-3', 'surface'], ['cat-4', 'surface'], ['cat-5', 'surface'], ['vivo', 'surface'],
  ['logo-cero', 'logo-baldosa'], ['logo-cero-chico', 'logo-baldosa'], ['logo-uno', 'logo-baldosa'], ['barra-borde', 'barra'], ['barra-ink', 'barra'],
]
let mal = 0
for (const [nombre, t] of [['claro', claro], ['oscuro', oscuro]]) for (const [f, b] of pares) {
  if (!t[f] || !t[b]) { console.log(`?? ${nombre}: falta ${!t[f] ? f : b}`); mal++; continue }
  const r = cr(t[f], t[b]); const ok = r >= 4.5
  if (!ok) mal++
  if (process.argv.includes('-v') || !ok) console.log(`${ok ? 'ok ' : 'MAL'} ${nombre.padEnd(6)} ${f} (${t[f]}) sobre ${b} (${t[b]}): ${r.toFixed(2)}:1`)
}
for (const [nombre, t] of [['claro', claro], ['oscuro', oscuro]]) for (const [f, b] of graficos) {
  if (!t[f] || !t[b]) { console.log(`?? ${nombre}: falta ${!t[f] ? f : b}`); mal++; continue }
  const r = cr(t[f], t[b]); const ok = r >= 3
  if (!ok) mal++
  if (process.argv.includes('-v') || !ok) console.log(`${ok ? 'ok ' : 'MAL'} ${nombre.padEnd(6)} gráfico ${f} (${t[f]}) sobre ${b} (${t[b]}): ${r.toFixed(2)}:1 (mínimo 3:1)`)
}
console.log(mal ? `${mal} pares por debajo del mínimo` : `Todos los pares cumplen (${pares.length * 2} de texto ≥ 4,5:1 y ${graficos.length * 2} de controles/gráficos ≥ 3:1)`)
process.exit(mal ? 1 : 0)
