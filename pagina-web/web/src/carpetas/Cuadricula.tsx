import { memo, useRef } from 'react'
import type { KeyboardEvent, MouseEvent, PointerEvent, SyntheticEvent } from 'react'
import { Icon } from '../icons'
import { fmtSize } from '../lib'
import { Ic } from './ui'
import { fecha, mesDe, mini } from './nube'
import type { Medio, Orden } from './nube'

/** Un mes de la cuadrícula; i es el sitio de cada medio en la lista entera (el visor y la selección van por ahí) */
export type Grupo = { clave: string; titulo: string; ms: { m: Medio; i: number }[] }

/** Por meses (la fecha es la de la foto). Ordenadas por peso no tiene sentido agrupar por meses. Se llama una vez por cambio de lista, no en cada pintado. */
export function agrupar(items: Medio[], orden: Orden): Grupo[] {
  if (orden === 'tamano') return items.length ? [{ clave: 'todo', titulo: '', ms: items.map((m, i) => ({ m, i })) }] : []
  const out: Grupo[] = []
  let k0 = NaN
  items.forEach((m, i) => {
    const d = new Date(m.mtime * 1000), k = m.mtime > 0 ? d.getFullYear() * 12 + d.getMonth() : -1
    if (k !== k0 || !out.length) { k0 = k; out.push({ clave: out.some(g => g.clave === String(k)) ? `${k}-${out.length}` : String(k), titulo: mesDe(m.mtime), ms: [] }) }
    out[out.length - 1].ms.push({ m, i })
  })
  return out
}

const roto = (e: SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.visibility = 'hidden'; e.currentTarget.parentElement?.setAttribute('data-roto', '') }

/** Una miniatura. Sin manejadores propios: los clics y la pulsación larga los recoge la cuadrícula (miles de celdas, ni un closure por celda) */
const Celda = memo(function Celda({ m, i, marcada, selec, peso }: { m: Medio; i: number; marcada: boolean; selec: boolean; peso: boolean }) {
  return <div className={`nube-celda${marcada ? ' sel' : ''}`} data-i={i}>
    <button type="button" className="nube-abrir" title={m.name} aria-pressed={selec ? marcada : undefined}
      aria-label={`${m.kind === 'video' ? 'Vídeo' : 'Foto'} ${m.name}${m.mtime > 0 ? `, ${fecha(m.mtime)}` : ''}`}>
      <img src={mini(m.path)} alt="" loading="lazy" decoding="async" draggable={false} onError={roto} />
      {m.kind === 'video' && <span className="nube-play" aria-hidden="true"><Ic n="video" size={14} /></span>}
      {peso && <span className="nube-peso" aria-hidden="true">{fmtSize(m.size)}</span>}
    </button>
    {selec
      ? <span className="nube-marca" aria-hidden="true">{marcada && <Icon name="check" size={14} strokeWidth={3} />}</span>
      // tabIndex -1: con el teclado se marca desde el visor (tecla F) o en «Seleccionar»; con lector de pantalla se llega igual
      : <button type="button" className={`nube-corazon${m.fav ? ' on' : ''}`} tabIndex={-1} aria-pressed={m.fav}
        aria-label={`Favorita: ${m.name}`}><Ic n="heart" size={19} lleno={m.fav} /></button>}
  </div>
})

type Props = { grupos: Grupo[]; sel: Set<string>; selec: boolean; peso: boolean
  onAbrir: (i: number, mayus: boolean) => void; onFav: (i: number) => void; onLargo: (i: number) => void; onMes: (g: Grupo) => void }

/** Las fotos por meses. Memoizada: escribir en el buscador o un aviso no la vuelven a pintar. */
export const Cuadricula = memo(function Cuadricula({ grupos, sel, selec, peso, onAbrir, onFav, onLargo, onMes }: Props) {
  const reloj = useRef(0), inicio = useRef<{ x: number; y: number } | null>(null), largo = useRef(false)
  const de = (t: EventTarget) => (t as Element).closest<HTMLElement>('[data-i]')
  const soltar = () => { clearTimeout(reloj.current); inicio.current = null }

  const clic = (e: MouseEvent) => {
    if (largo.current) { largo.current = false; return }   // el clic que sigue a una pulsación larga no abre nada
    const t = e.target as Element, mes = t.closest<HTMLElement>('[data-mes]')
    if (mes) { const g = grupos.find(x => x.clave === mes.dataset.mes); if (g) onMes(g); return }
    const c = de(t)
    if (!c) return
    if (t.closest('.nube-corazon')) onFav(+c.dataset.i!)
    else if (t.closest('.nube-abrir')) onAbrir(+c.dataset.i!, e.shiftKey)
  }
  const abajo = (e: PointerEvent) => {   // pulsación larga (móvil): empieza a marcar
    if (selec || e.pointerType === 'mouse' || !e.isPrimary) return
    const t = e.target as Element, c = de(t)
    if (!c || t.closest('.nube-corazon')) return
    inicio.current = { x: e.clientX, y: e.clientY }
    clearTimeout(reloj.current)
    reloj.current = window.setTimeout(() => {
      largo.current = true; setTimeout(() => { largo.current = false }, 800)   // por si el clic no llega
      onLargo(+c.dataset.i!); navigator.vibrate?.(12)
    }, 450)
  }
  const tecla = (e: KeyboardEvent) => {   // con el teclado: F en una foto enfocada la marca o desmarca como favorita
    if ((e.key !== 'f' && e.key !== 'F') || e.ctrlKey || e.metaKey || e.altKey || e.repeat || selec) return
    const c = de(e.target)
    if (c && (e.target as Element).closest('.nube-abrir')) { e.preventDefault(); onFav(+c.dataset.i!) }
  }
  const mueve = (e: PointerEvent) => { if (inicio.current && Math.hypot(e.clientX - inicio.current.x, e.clientY - inicio.current.y) > 10) soltar() }   // es un desplazamiento, no una pulsación

  return <div className={`nube-lista${selec ? ' selec' : ''}`} role="group" aria-label="Fotos y vídeos" aria-describedby="nube-ayuda" onClick={clic} onKeyDown={tecla} onPointerDown={abajo} onPointerMove={mueve} onPointerUp={soltar} onPointerCancel={soltar}
    onContextMenu={e => { if (largo.current || selec) e.preventDefault() }}>
    <p id="nube-ayuda" className="visually-hidden">Con el teclado: Intro abre la foto o el vídeo y la tecla F lo marca como favorito.</p>
    {grupos.map(g => {
      const todas = selec && g.ms.every(({ m }) => sel.has(m.path))
      return <section key={g.clave} className="nube-mes">
        {g.titulo && <h3><span>{g.titulo}</span>{selec && <button type="button" className="nube-mes-sel" data-mes={g.clave}>{todas ? 'Quitar marcas' : 'Marcar todo'}</button>}</h3>}
        <div className="nube-grid">{g.ms.map(({ m, i }) => <Celda key={m.path} m={m} i={i} marcada={sel.has(m.path)} selec={selec} peso={peso} />)}</div></section>
    })}
  </div>
})
