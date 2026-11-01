import { useEffect, useMemo, useState } from 'react'
import { Icon } from '../icons'
import { post, useFetch } from '../lib'
import { estadoPermiso, mensajePedido, pedirPosicion, type Pedido } from './PermisosDispositivo'

/** Lo que una invitada elige una vez: cómo llamarla, país, zona horaria, °C/°F y si su Zazu sigue su ubicación al viajar. */
export type Prefs = { apodo?: string; pais?: string; zona?: string; unidad?: 'C' | 'F'; auto?: boolean; preguntado?: boolean; ciudad?: string; t_ubic?: number }

const zonaDelMovil = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Madrid' } catch { return 'Europe/Madrid' } }
const ZONAS = (() => { try { return (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone') || [] } catch { return [] } })()
const PAIS_DE_ZONA: Record<string, string> = { 'Europe/Madrid': 'ES', 'Atlantic/Canary': 'ES', 'Africa/Ceuta': 'ES', 'America/Caracas': 'VE', 'America/Bogota': 'CO',
  'America/Mexico_City': 'MX', 'America/Argentina/Buenos_Aires': 'AR', 'America/Santiago': 'CL', 'America/Lima': 'PE', 'America/Guayaquil': 'EC',
  'America/Montevideo': 'UY', 'America/Asuncion': 'PY', 'America/La_Paz': 'BO', 'America/Santo_Domingo': 'DO', 'America/Havana': 'CU', 'America/Panama': 'PA',
  'America/Costa_Rica': 'CR', 'America/Guatemala': 'GT', 'America/Puerto_Rico': 'PR', 'America/New_York': 'US', 'America/Chicago': 'US', 'America/Denver': 'US',
  'America/Los_Angeles': 'US', 'Europe/Lisbon': 'PT', 'Europe/Paris': 'FR', 'Europe/Rome': 'IT', 'Europe/Berlin': 'DE', 'Europe/London': 'GB' }
const conF = (pais: string) => pais === 'US' || pais === 'PR'
/** «Madrid · hora de España» en vez de «Europe/Madrid»: la ciudad y el nombre de la hora en español. */
function nombreZona(z: string): string {
  const c = (z.split('/').pop() || z).replace(/_/g, ' ')
  try {
    const g = new Intl.DateTimeFormat('es-ES', { timeZone: z, timeZoneName: 'longGeneric' }).formatToParts(new Date()).find(x => x.type === 'timeZoneName')?.value
    return g && !/^GMT|^UTC/.test(g) ? `${c} · ${g}` : g ? `${c} (${g})` : c
  } catch { return c }
}

type Ubic = { zona?: string; ciudad?: string; cambio?: boolean }
/** Manda una posición; el servidor la redondea a la ciudad (solo si ella activó que siga su ubicación). */
export const enviarPosicion = (pos: GeolocationPosition) => post<Ubic>('/api/mi-zazu', { action: 'ubicacion', lat: pos.coords.latitude, lon: pos.coords.longitude, zona: zonaDelMovil() })
/** Pide la ubicación al móvil (con su permiso; en la app, también el del sistema) y la manda.
 *  Si no hay posición, `fallo` dice por qué (bloqueada, sin elegir, sin señal…) en vez de tragárselo. */
export async function mandarUbicacion(): Promise<(Ubic & { fallo?: undefined }) | { fallo: Pedido }> {
  const p = await pedirPosicion()
  if (!p.pos) return { fallo: p }
  return enviarPosicion(p.pos)
}

export function FormPreferencias({ nombre, prefs, asistente = 'Zazu', toast, guardado, boton = 'Guardar', autoInicial = true, alCambiar }:
  { nombre: string; prefs?: Prefs; asistente?: string; toast: (m: string) => void; guardado: () => void; boton?: string
    /** lo escrito sin guardar (la guía lo conserva al ir Atrás y volver) */ alCambiar?: (p: Partial<Prefs>) => void
    /** «seguir mi ubicación» marcado de entrada si aún no lo ha elegido (la guía solo lo marca si la ubicación ya está permitida: así no se pide dos veces) */ autoInicial?: boolean }) {
  const info = useFetch<{ paises: Record<string, string> }>('/api/mi-zazu')
  const zMovil = zonaDelMovil()
  const [apodo, setApodo] = useState(prefs?.apodo || nombre)
  const [pais, setPais] = useState(prefs?.pais || PAIS_DE_ZONA[zMovil] || 'ES')
  const [zona, setZona] = useState(prefs?.zona || zMovil)
  const [unidad, setUnidad] = useState<'C' | 'F'>(prefs?.unidad || (conF(prefs?.pais || PAIS_DE_ZONA[zMovil] || '') ? 'F' : 'C'))
  const [auto, setAuto] = useState(prefs?.preguntado ? !!prefs.auto : autoInicial)
  const [busy, setBusy] = useState(false)
  const paises = info.data?.paises || {}
  // las zonas por su nombre en español, ordenadas; la del móvil, la primera
  const zonas = useMemo(() => (ZONAS.length ? ZONAS : [zona]).map(z => [z, nombreZona(z)] as const)
    .sort((a, b) => a[0] === zMovil ? -1 : b[0] === zMovil ? 1 : a[1].localeCompare(b[1], 'es')), [zMovil]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { alCambiar?.({ apodo, pais, zona, unidad }) }, [apodo, pais, zona, unidad]) // eslint-disable-line react-hooks/exhaustive-deps
  async function guardar() {
    setBusy(true)
    try {
      // primero la posición: «seguir mi ubicación» solo se guarda si el móvil la ha dado (si no, saldría «activada» sin serlo)
      const p = auto ? await pedirPosicion() : null
      const sigue = !!p?.pos
      await post('/api/mi-zazu', { action: 'preferencias', apodo: apodo.trim(), pais, zona, unidad, auto: sigue })
      if (p?.pos) {
        const r = await enviarPosicion(p.pos).catch(() => null)
        toast(r?.ciudad ? `Listo. ${asistente} sabe que estás en ${r.ciudad}.` : 'Guardado')
      } else if (p) {
        setAuto(false)
        toast(p.silenciado ? 'Guardado. El navegador no me ha dejado preguntar por la ubicación: puedes activarla luego en «Tus permisos».'
          : p.sistema ? 'Guardado. Zazu tiene permiso, pero el navegador no tiene el de la ubicación del móvil: en «Tus permisos» › Ubicación te digo cómo dárselo.'
          : p.estado === 'denied' ? 'Guardado. La ubicación está bloqueada en este móvil: tu hora la cambias aquí, o actívala luego en «Tus permisos».'
          : p.error ? `Guardado. ${mensajePedido('ubicacion', p)}` : 'Guardado sin tu ubicación (no le diste permiso). Puedes activarla luego en «Tus permisos».')
      }
      else toast('Guardado')
      guardado()
    } catch (e) { toast(`No se pudo: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  const lab = { display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 4, marginTop: 10 } as const
  return <div>
    <label className="check" style={lab}>¿Cómo quieres que te llame?
      <input className="campo" value={apodo} maxLength={40} onChange={e => setApodo(e.target.value)} placeholder="Tu nombre o como te gusta que te digan" /></label>
    <label className="check" style={lab}>¿En qué país vives?
      <select className="campo" value={pais} onChange={e => { setPais(e.target.value); setUnidad(conF(e.target.value) ? 'F' : 'C') }}>
        {Object.entries(paises).map(([k, n]) => <option key={k} value={k}>{n}</option>)}
        {!paises[pais] && <option value={pais}>{pais}</option>}</select></label>
    <label className="check" style={lab}>Tu hora (zona horaria)
      <select className="campo" value={zona} onChange={e => setZona(e.target.value)}>
        {zonas.map(([z, n]) => <option key={z} value={z}>{n}</option>)}
        {!zonas.some(([z]) => z === zona) && <option value={zona}>{nombreZona(zona)}</option>}</select>
      {zMovil && <small>{zona === zMovil ? 'Es la de este móvil.' : `La de este móvil: ${nombreZona(zMovil)}.`}</small>}</label>
    <div className="check" style={lab}>Temperatura
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <button type="button" aria-pressed={unidad === 'C'} className={unidad === 'C' ? 'btn-primary' : 'btn-secondary'} style={{ padding: '0 6px', whiteSpace: 'nowrap' }} onClick={() => setUnidad('C')}>°C · Celsius</button>
        <button type="button" aria-pressed={unidad === 'F'} className={unidad === 'F' ? 'btn-primary' : 'btn-secondary'} style={{ padding: '0 6px', whiteSpace: 'nowrap' }} onClick={() => setUnidad('F')}>°F · Fahrenheit</button></div></div>
    <label className="check" style={{ marginTop: 12, alignItems: 'flex-start', gap: 8 }}>
      <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} />
      <span><b>Cuando viaje, cambia mi hora y mi ciudad solas.</b> El móvil te pedirá permiso de ubicación. Se guarda solo la ciudad aproximada, nunca tu dirección.</span></label>
    {prefs?.ciudad && <small>Ahora mismo: {prefs.ciudad}{prefs.zona ? ` · ${nombreZona(prefs.zona)}` : ''}</small>}
    <div className="actions"><button className="btn-primary" disabled={busy} onClick={() => void guardar()}>{busy ? 'Guardando…' : boton} <Icon name="arrow" size={17} /></button></div>
  </div>
}

/** La pregunta de una vez (también a quien ya tenía cuenta antes de esto). */
export function PreguntaPreferencias({ nombre, asistente, toast, done }: { nombre: string; asistente: string; toast: (m: string) => void; done: () => void }) {
  return <div role="dialog" aria-modal="true" aria-label="Unos datos para tu asistente" style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 16, paddingBottom: 'calc(24px + env(safe-area-inset-bottom))' }}>
    <div className="acc-card" style={{ width: '100%', maxWidth: 480, maxHeight: 'calc(100dvh - 56px)', overflowY: 'auto', paddingBottom: 24 }}>
      <strong style={{ fontSize: 18 }}>Unos datos para que {asistente} te trate bien</strong>
      <small>Solo te lo pregunto una vez. Lo puedes cambiar cuando quieras en Tu espacio.</small>
      <FormPreferencias nombre={nombre} asistente={asistente} toast={toast} guardado={done} boton="Listo" />
    </div></div>
}

/** Si eligió que siga su ubicación: al abrir la app, si el móvil cambió de hora o hace más de 6 h, se pone al día sola. */
export function SeguirUbicacion({ prefs, asistente, toast, cambio }: { prefs: Prefs; asistente: string; toast: (m: string) => void; cambio: () => void }) {
  useEffect(() => {
    let vivo = true
    const viaje = zonaDelMovil() !== prefs.zona
    if (!viaje && prefs.t_ubic && Date.now() / 1000 - prefs.t_ubic < 6 * 3600) return
    const ir = async () => {
      try {
        const p = await estadoPermiso('ubicacion')   // el de verdad (en la app, el del sistema; si no, lo que funcionó la última vez)
        if (p !== 'granted') {   // sin permiso dado no se pregunta solo: la hora se pone igual si cambió
          if (viaje) { await post('/api/mi-zazu', { action: 'preferencias', ...prefs, zona: zonaDelMovil() }); if (vivo) { toast(`He cambiado tu hora a ${zonaDelMovil().replace(/_/g, ' ')}.`); cambio() } }
          return
        }
        const r = await mandarUbicacion()
        if (r.fallo) return
        if (vivo && r.cambio) { toast(`Estás en ${r.ciudad || r.zona}: ${asistente} ya usa tu hora de allí.`); cambio() }
      } catch { /* sin conexión: otra vez será */ }
    }
    void ir()
    return () => { vivo = false }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}
