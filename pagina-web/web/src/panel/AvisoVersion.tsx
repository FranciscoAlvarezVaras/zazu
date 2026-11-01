/* Aviso de versión nueva. Pregunta a /api/version (va por /api/, que Cloudflare nunca guarda en caché, así que siempre
   es la versión real del servidor) al arrancar, al volver a la app y cada 5 minutos. Si cambió desde que abriste, sale
   un aviso «Nueva versión · Actualizar» que recarga con lo último. Así las actualizaciones llegan aunque el service
   worker esté cacheado por el borde. */
import { useEffect, useState } from 'react'

async function versionServidor(): Promise<string | null> {
  try {
    const r = await fetch('/api/version', { cache: 'no-store', credentials: 'same-origin' })
    if (!r.ok) return null
    return (await r.json()).version || null
  } catch { return null }
}

/** Limpia las copias guardadas (menos lo compartido), pide el service worker nuevo y recarga. */
export async function actualizar() {
  try {
    if ('caches' in window) await Promise.all((await caches.keys()).filter(k => k !== 'compartidos').map(k => caches.delete(k)))
    await (await navigator.serviceWorker?.getRegistration())?.update()
  } catch { /* se recarga igual */ }
  location.reload()
}

export default function AvisoVersion() {
  const [hayNueva, setHayNueva] = useState(false)
  useEffect(() => {
    let inicial: string | null = null
    let parado = false
    const mirar = async () => {
      const v = await versionServidor()
      if (parado || !v) return
      if (inicial === null) inicial = v
      if (v !== __HUB_V__ || v !== inicial) setHayNueva(true)   // la app que corre es de otra versión que la del servidor
    }
    void mirar()
    const alVolver = () => { if (!document.hidden) void mirar() }
    document.addEventListener('visibilitychange', alVolver)
    const t = setInterval(() => { if (!document.hidden) void mirar() }, 5 * 60 * 1000)
    return () => { parado = true; document.removeEventListener('visibilitychange', alVolver); clearInterval(t) }
  }, [])
  const [luego, setLuego] = useState(false)
  if (!hayNueva || luego) return null
  return <div className="pz-version" role="status">
    <span aria-hidden="true" style={{ fontSize: 22 }}>✨</span>
    <span className="pz-version-txt"><strong>HolaZazu tiene novedades</strong><small>Tarda un segundo y no pierdes nada.</small></span>
    <button type="button" className="pz-version-luego" onClick={() => setLuego(true)}>Luego</button>
    <button type="button" onClick={() => void actualizar()}>Actualizar</button>
  </div>
}
