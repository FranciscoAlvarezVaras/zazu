import { useState } from 'react'
import { Icon } from '../icons'
import { hm, useFetch } from '../lib'
import type { Status } from '../lib'

type Alerta = { clave: string; gravedad: 'error' | 'aviso'; texto: string; desde: number }

/** Inicio de Fran: lo que el vigilante (cada 5 min) ve mal ahora mismo, en una línea que se despliega.
 *  También avisa si el propio vigilante se ha parado o si Zazu (el gateway) no responde. No ocupa nada si todo va bien. */
export default function AvisosHoy({ nombre = 'Zazu' }: { nombre?: string }) {
  const a = useFetch<{ activas: Alerta[]; ultima: number | null }>('/api/alertas', 60000)
  const st = useFetch<Status>('/api/status', 30000)
  const [abierto, setAbierto] = useState(false)
  const lista: Alerta[] = []
  if (st.data && st.data.gateway !== 'running') lista.push({ clave: 'gateway', gravedad: 'error', texto: `${nombre} no responde ahora mismo (el servicio de Zazu no está en marcha): puede que tus mensajes tarden o no lleguen.`, desde: 0 })
  else if (st.error && !st.data) lista.push({ clave: 'red', gravedad: 'aviso', texto: `No llego al servidor para ver cómo está ${nombre}.`, desde: 0 })
  if (a.data) {
    lista.push(...a.data.activas)
    if (!a.data.ultima || Date.now() / 1000 - a.data.ultima > 15 * 60) lista.push({ clave: 'vigilante', gravedad: 'aviso', texto: 'El vigilante de alertas no se ha ejecutado en los últimos 15 minutos.', desde: a.data.ultima || 0 })
  }
  if (!lista.length) return null
  const grave = lista.some(x => x.gravedad === 'error')
  return <section className={`avisos ${grave ? 'grave' : ''}`} role="alert" aria-label="Alertas del sistema">
    <button type="button" className="avisos-cab" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>
      <Icon name="bell" size={17} /><span>{lista.length === 1 ? 'Hay algo que revisar' : `Hay ${lista.length} cosas que revisar`}</span><Icon name="chevron" size={16} />
    </button>
    {abierto && <ul>{lista.map(x => <li key={x.clave} className={x.gravedad}><span className="visually-hidden">{x.gravedad === 'error' ? 'Error: ' : 'Aviso: '}</span>{x.texto}{x.desde ? <small> · desde las {hm(x.desde)}</small> : null}</li>)}</ul>}
  </section>
}
