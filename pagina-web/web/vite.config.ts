import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { readFileSync, writeFileSync } from 'node:fs'
import type { Plugin } from 'vite'

// La versión sube SOLA en cada construcción (hub-v + AAMMDDhhmm): se graba en dist/sw.js (el móvil ve un service worker nuevo
// y borra las copias viejas), en la app (__HUB_V__, se enseña en «Tu espacio») y en index.html, que antes de enseñar nada
// pregunta a /api/version y, si el servidor ya tiene otra, limpia y recarga. Así nadie se queda con una versión vieja.
const HUB_V = 'hub-v' + new Date().toISOString().replace(/\D/g, '').slice(2, 12)
const versionHub = (): Plugin => ({
  name: 'version-hub',
  transformIndexHtml: h => h.replace(/%HUB_V%/g, HUB_V),
  writeBundle(opts) {   // en el dir de salida de ESTA construcción (con --outDir no toca dist/ de producción)
    const f = path.join(opts.dir || path.resolve(__dirname, '../dist'), 'sw.js')
    writeFileSync(f, readFileSync(f, 'utf8').replace(/const V='hub-v\d+'/, `const V='${HUB_V}'`))
  },
})

// 2026-10-25 (Fran): la letra, «una talla menos» para que quepa más en el móvil. En vez de tocar los ~720 font-size del CSS uno a uno,
// al construir se multiplica por ESCALA_LETRA cada tamaño en px de `font-size` (también dentro de clamp()) y el tamaño del atajo `font:`.
// Solo la letra: iconos, márgenes y botones no cambian. Nunca baja de 11 px (lo que ya era menor se queda igual).
const ESCALA_LETRA = 0.94
const letraMenor = (): Plugin => {
  const px = (n: string) => { const v = parseFloat(n); return `${v < 11 ? v : Math.max(11, Math.round(v * ESCALA_LETRA * 10) / 10)}px` }
  return {
    name: 'letra-una-talla-menos',
    enforce: 'pre',
    transform(code, id) {
      if (!/\.css($|\?)/.test(id)) return
      return code
        .replace(/(font-size\s*:\s*)([^;}]+)/g, (_, k: string, v: string) => k + v.replace(/(\d+(?:\.\d+)?)px/g, (_m, n: string) => px(n)))
        .replace(/(\bfont\s*:\s*)([^;}]+)/g, (_, k: string, v: string) => k + v.replace(/(\d+(?:\.\d+)?)px(?=\s*[/\s])/, (_m, n: string) => px(n)))
    },
  }
}

export default defineConfig({
  define: { __HUB_V__: JSON.stringify(HUB_V) },
  plugins: [letraMenor(), react(), tailwindcss(), versionHub()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  build: { outDir: '../dist', emptyOutDir: true },
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8791' } },
})
