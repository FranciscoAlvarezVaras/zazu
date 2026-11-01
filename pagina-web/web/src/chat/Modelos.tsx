import { useRef } from 'react'
import type { KeyboardEvent } from 'react'
import { Hoja } from '../panel/ui'
import type { ChatApi, Modelo } from '../tipos'
import { nombreCorto, useModelos } from './api'

const Flecha = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>

/** Hoja «Modelo para esta conversación» (solo Fran). Los de pago por uso van marcados (solo con la etiqueta, sin repetirlo en el texto);
 *  los que no tienen clave, desactivados.
 *  Elegir con el dedo (o Intro) cierra la hoja; las flechas cambian sin cerrar. Se cierra también con el Atrás del móvil. */
export function HojaModelos({ abierto, cerrar, chat }: { abierto: boolean; cerrar(): void; chat: ChatApi }) {
  const { modelos, cargando } = useModelos(abierto)
  const lista = useRef<HTMLDivElement>(null)
  if (!abierto) return null
  const ms = modelos?.modelos || []
  const usables = ms.filter(m => m.disponible)
  const elegir = (m: Modelo, cerrarla: boolean) => { if (!m.disponible) return; chat.setModelo(m.id); if (cerrarla) cerrar() }
  const flechas = (e: KeyboardEvent) => {
    const paso = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 0
    if (!paso || !usables.length) return
    e.preventDefault()
    const i = usables.findIndex(m => m.id === chat.modelo)
    const m = usables[(i + paso + usables.length) % usables.length]
    elegir(m, false)
    requestAnimationFrame(() => lista.current?.querySelector<HTMLElement>(`[data-modelo="${m.id}"]`)?.focus())
  }
  const activo = ms.find(m => m.id === chat.modelo)
  return <Hoja titulo="Modelo para esta conversación" id="modelos" cerrar={cerrar}>
    <div className="hz-modelos">
      {activo && <p className="hz-modelos-ahora">Ahora: <b>{activo.nombre}</b></p>}
      {modelos && !modelos.activo && <p className="hz-modelos-aviso" role="note">El chat con Zazu no está activado en el servidor: puedes elegir modelo, pero aún no responderá.</p>}
      {!modelos && (cargando ? <p className="hz-modelos-pie">Cargando modelos…</p> : <p className="hz-modelos-aviso" role="note">No se pudo cargar la lista de modelos. Cierra y vuelve a abrir para reintentar.</p>)}
      {ms.length > 0 && <div className="hz-modelos-lista" role="radiogroup" aria-label="Modelo para esta conversación" ref={lista} onKeyDown={flechas}>
        {ms.map(m => {
          const on = m.id === chat.modelo
          const foco = on || (!chat.modelo && m.id === usables[0]?.id)
          return <button key={m.id} type="button" role="radio" aria-checked={on} data-modelo={m.id} className="hz-modelo" {...(foco ? { 'data-foco': true } : {})}
            tabIndex={foco ? 0 : -1} disabled={!m.disponible} onClick={() => elegir(m, true)}>
            <span className="hz-modelo-radio" aria-hidden="true" />
            <span className="hz-modelo-txt">
              <strong>{m.nombre}</strong>
              <small>{[...new Set([...m.proveedor_nombre.split('·'), ...m.nota.split('·')].map(x => x.trim()).filter(x => x && !(m.pago === 'uso' && /pago por uso/i.test(x))))].join(' · ')}{!m.disponible ? ' · sin conectar' : ''}</small>
            </span>
            {m.pago === 'uso' && <span className="hz-uso">pago por uso</span>}
          </button>
        })}
      </div>}
      <p className="hz-modelos-pie">Se aplica desde el próximo mensaje.</p>
    </div>
  </Hoja>
}

/** Chip con el modelo de la conversación («sonnet-5.5»); al pulsarlo abre la hoja. Solo en las conversaciones con permisos (las antiguas no eligen modelo). */
export function ChipModelo({ chat, onClick }: { chat: ChatApi; onClick(): void }) {
  const { modelos } = useModelos(chat.modo === 'hermes')
  if (chat.modo !== 'hermes') return null
  const m = modelos?.modelos.find(x => x.id === chat.modelo)
  const corto = m ? nombreCorto(m.nombre) : chat.modelo || 'modelo'
  return <button type="button" className={`hz-chip hz-chip-modelo ${m?.pago === 'uso' ? 'uso' : ''}`} onClick={onClick} aria-haspopup="dialog"
    aria-label={`Modelo: ${m?.nombre || corto}${m?.pago === 'uso' ? ', pago por uso' : ''}. Cambiar de modelo`} title={m ? `${m.nombre}${m.pago === 'uso' ? ' · pago por uso' : ''}` : 'Cambiar de modelo'}>
    <span className="hz-chip-mono">{corto}</span>{m?.pago === 'uso' && <span className="hz-uso-punto" aria-hidden="true" />}<Flecha /></button>
}
