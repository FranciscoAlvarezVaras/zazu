import { useState } from 'react'
import { Icon } from '../icons'
import { fmtSize, useFetch } from '../lib'
import { base, etiqueta, itemDe, padre, restaurar } from './api'
import type { EnPapelera } from './api'
import { Ficha, Ic } from './ui'
import type { Aviso } from './ui'

const DIAS = 30
const ms = (f: number | string) => typeof f === 'number' ? (f < 1e12 ? f * 1000 : f) : Date.parse(f)
/** El servidor guarda la ruta original; si llega absoluta, se queda con lo que va tras «40 Compartido/» */
const relativa = (o: string) => o.replace(/^.*?40 Compartido\/?/, '')
/** origen puede ser la ruta del archivo o la de su carpeta */
const carpetaDe = (x: EnPapelera) => { const o = relativa(x.origen || ''); return base(o) === x.nombre ? padre(o) : o }
function quedan(x: EnPapelera) {
  const d = x.caduca ? Math.ceil((x.caduca * 1000 - Date.now()) / 864e5) : DIAS - Math.floor((Date.now() - ms(x.fecha)) / 864e5)
  return isNaN(d) ? '' : d <= 0 ? 'se borra hoy' : d === 1 ? 'se borra mañana' : `se borra en ${d} días`
}

/** Papelera de la app: nada se borra de verdad hasta pasados 30 días */
export function Papelera({ avisar, volver, abrir }: { avisar: (a: Aviso) => void; volver: () => void; abrir: (ruta: string) => void }) {
  const { data, error, loading, reload } = useFetch<{ items: EnPapelera[] }>('/api/papelera')
  const [busy, setBusy] = useState('')
  const items = [...(data?.items || [])].sort((a, b) => ms(b.fecha) - ms(a.fecha))
  async function recuperar(x: EnPapelera) {
    setBusy(x.id)
    try {
      const r = await restaurar(x.id)
      const donde = r.path ? padre(relativa(r.path)) : carpetaDe(x)
      avisar({ texto: `«${x.nombre}» ha vuelto a ${etiqueta('compartido', donde)}`, accion: { label: 'Abrir', fn: () => abrir(donde) } })
      await reload()
    } catch (e) { avisar({ texto: `No se pudo recuperar: ${(e as Error).message}` }) }
    finally { setBusy('') }
  }
  return <>
    <button className="back-link" onClick={volver}><Icon name="back" size={16} /> Volver a tus carpetas</button>
    <div className="cp-papelera-cab"><span className="cp-ficha other"><Ic n="trash" /></span><div><strong>Papelera</strong>
      <small>Se vacía sola a los 30 días. Hasta entonces, puedes recuperar lo que quieras.</small></div></div>
    {error && <p className="cp-vacio" role="alert">No pude abrir la papelera: {error}. <button className="text-link cp-en-linea" onClick={() => void reload()}>Reintentar</button></p>}
    {!error && !items.length && <p className="cp-vacio">{loading ? 'Cargando…' : 'La papelera está vacía.'}</p>}
    {!!items.length && <div className="cp-lista">{items.map(x => <div className="cp-fila" key={x.id}>
      <div className="cp-fila-main"><Ficha it={itemDe(x.nombre, x.dir)} root="compartido" foto={false} />
        <span className="cp-fila-txt"><strong>{x.nombre}</strong>
          <small>{[x.dir ? 'Carpeta' : fmtSize(x.size), `estaba en ${etiqueta('compartido', carpetaDe(x))}`, quedan(x)].filter(Boolean).join(' · ')}</small></span></div>
      <button className="cp-guardar" disabled={busy === x.id} onClick={() => void recuperar(x)}><Ic n="restore" size={16} /> {busy === x.id ? 'Recuperando…' : 'Recuperar'}</button>
    </div>)}</div>}
  </>
}
