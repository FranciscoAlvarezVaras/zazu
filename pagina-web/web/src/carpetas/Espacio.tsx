import { useState } from 'react'
import { Icon } from '../icons'
import { fmtSize } from '../lib'
import { useEscritorio } from '../tema'
import { Ic } from './ui'
import { plural } from './nube'
import type { Resumen } from './nube'

// los colores son fichas (--nb-t1…4 en galeria.css): en claro los verdes de siempre, en oscuro otros que se ven sobre fondo oscuro
const TRAMOS = [
  { id: 'fotos', txt: 'Fotos', kinds: ['image'] as const, color: 'var(--nb-t1)' },
  { id: 'videos', txt: 'Vídeos', kinds: ['video'] as const, color: 'var(--nb-t2)' },
  { id: 'docs', txt: 'Documentos', kinds: ['pdf', 'doc', 'sheet', 'text', 'note'] as const, color: 'var(--nb-t3)' },
]
const OTROS = { id: 'otros', txt: 'Otros', color: 'var(--nb-t4)' }

/** Cuánto ocupa la nube y en qué (barra apilada por tipo), con lo que se puede hacer a todo el conjunto: buscar duplicados y ver lo compartido.
 *  En el móvil los detalles van plegados para que las fotos salgan antes. */
export function Espacio({ r, error, onReintentar, onDuplicados, onEnlaces }: { r: Resumen | null; error: string; onReintentar: () => void; onDuplicados: () => void; onEnlaces: () => void }) {
  const escritorio = useEscritorio()
  const [detalle, setDetalleYa] = useState(() => { try { const v = localStorage.getItem('nube-detalle'); return v ? v === '1' : escritorio } catch { return escritorio } })   // lo que elija Fran se recuerda
  const setDetalle = (v: boolean) => { setDetalleYa(v); try { localStorage.setItem('nube-detalle', v ? '1' : '0') } catch { /* sin almacenamiento */ } }
  // fotos, vídeos y documentos salen de «tipos»; «otros» es lo que falta hasta el total (audio y cualquier tipo nuevo)
  const tramos = r?.tipos ? (() => {
    const t = TRAMOS.map(x => ({ ...x, bytes: x.kinds.reduce((a, k) => a + (r.tipos?.[k]?.bytes || 0), 0) }))
    return [...t, { ...OTROS, bytes: Math.max(0, r.bytes - t.reduce((a, x) => a + x.bytes, 0)) }].filter(x => x.bytes > 0)
  })() : []
  const disco = r?.disco && r.disco.total > 0 ? r.disco : null
  const cuentas = [r?.favoritos != null ? plural(r.favoritos, 'favorito', 'favoritos') : '', r?.albumes != null ? plural(r.albumes, 'álbum', 'álbumes') : ''].filter(Boolean).join(' · ')
  return <div className="nube-resumen">
    <div className="nube-linea">
      <p>{r ? <><strong>{fmtSize(r.bytes)}</strong> en tu nube{disco && <span className="nube-libre"> · {fmtSize(disco.libre)} libres de {fmtSize(disco.total)}</span>}</>
        : error ? <>No pude calcular el espacio: {error}. <button type="button" className="text-link cp-en-linea" onClick={onReintentar}>Reintentar</button></> : 'Calculando lo que ocupa tu nube…'}</p>
      <button type="button" className="nube-mas-info" aria-expanded={detalle} onClick={() => setDetalle(!detalle)}>{detalle ? 'Menos' : 'Detalles'} <Icon name="chevron" size={14} /></button></div>
    {r && r.bytes > 0 && <div className="nube-apilada" role="img" aria-label={tramos.length ? tramos.map(x => `${x.txt} ${fmtSize(x.bytes)}`).join(', ') : `Ocupa ${fmtSize(r.bytes)}`}>
      {tramos.length ? tramos.map(x => <i key={x.id} style={{ flexGrow: x.bytes, background: x.color }} />) : <i style={{ flexGrow: 1, background: TRAMOS[0].color }} />}</div>}
    {r && r.bytes === 0 && <p className="nube-sub">Todavía no hay nada en tu nube.</p>}
    {detalle && <>
      {tramos.length > 0 && <ul className="nube-leyenda">{tramos.map(x => <li key={x.id}><i style={{ background: x.color }} aria-hidden="true" />{x.txt} <b>{fmtSize(x.bytes)}</b></li>)}</ul>}
      <div className="nube-resumen-pie">{cuentas ? <p className="nube-sub">{cuentas}</p> : <span />}
        <div className="nube-resumen-acc">
          <button type="button" className="btn-secondary" onClick={onDuplicados}><Ic n="copy" size={18} /> Buscar duplicados</button>
          <button type="button" className="btn-secondary" onClick={onEnlaces}><Ic n="link" size={18} /> Mis enlaces</button></div></div></>}
  </div>
}
