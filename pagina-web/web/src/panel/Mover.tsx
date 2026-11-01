/* Cambiar de estado una tarjeta de un tablero (candidatura, proyecto…): la hoja «¿Qué ha pasado?» y la lógica de guardar, con la tarjeta ya movida
   en pantalla mientras se guarda (si el servidor dice que no, se deshace). Es el ÚNICO camino que escribe en los tableros (endpoint de siempre: mover). */
import { useState } from 'react'
import type { Ctx } from '../ctx'
import { moverTarjeta } from './api'
import type { Columna, Tablero, Tarjeta } from './api'
import type { DatosTableros } from './datos'
import { cap } from './formato'
import { diaCorto, enDias, Hoja, Icono } from './ui'

export const TERMINALES = ['hecho', 'rechazada', 'descartada', 'aparcada']
/** Cómo se dice cada estado en una frase corriente (para elegir sin pensar en columnas). */
export const FRASE: Record<string, string> = {
  'por enviar': 'Todavía no la he enviado', enviada: 'Ya la envié', prueba: 'Me han mandado una prueba',
  entrevista: 'Me han llamado a entrevista', oferta: 'Me han hecho una oferta', rechazada: 'Me han dicho que no',
  descartada: 'Ya no me interesa', activo: 'Sigo con ello', esperando: 'Estoy esperando a alguien',
  'en pausa': 'Lo dejo en pausa', hecho: 'Ya está terminado', nueva: 'Es una idea nueva', aparcada: 'La aparco',
}
export const DONDE: Record<string, string> = { 'por enviar': 'Por enviar', enviada: 'Enviadas', prueba: 'Con prueba', entrevista: 'En entrevista', oferta: 'Con oferta',
  rechazada: 'Rechazadas', descartada: 'Descartadas', activo: 'Activos', esperando: 'Esperando', 'en pausa': 'En pausa', hecho: 'Hechos', nueva: 'Nuevas', aparcada: 'Aparcadas' }

/** Pone la tarjeta (nueva versión del servidor) donde corresponde, quitándola de donde estaba. */
export function colocar(d: Tablero[], id: string, nueva: Tarjeta, antesRuta = nueva.ruta): Tablero[] {
  return d.map(b => {
    if (b.id !== id || !b.ok) return b
    if (b.clase === 'kanban') {
      const cols: Columna[] = b.columnas.map(c => ({ ...c, tarjetas: c.tarjetas.filter(t => t.ruta !== antesRuta) }))
      const i = cols.findIndex(c => c.id === nueva.estado)
      const k = i >= 0 ? i : cols.findIndex(c => c.id === '_otros')
      if (k >= 0) cols[k] = { ...cols[k], tarjetas: [...cols[k].tarjetas, nueva].sort((a, b) => (a.plazo || '9999').localeCompare(b.plazo || '9999') || a.titulo.localeCompare(b.titulo, 'es')) }
      else cols.push({ id: '_otros', titulo: 'Sin estado válido', tarjetas: [nueva] })
      return { ...b, columnas: cols }
    }
    if (b.clase === 'carnet') return { ...b, nota: nueva }
    return b
  })
}

/** Una cosa más que se puede hacer desde la hoja (p. ej. «Preparar la carta», que abre el chat con la petición escrita). */
export type AccionHoja = { texto: string; run: () => void; primaria?: boolean }
export type Abierta = { tablero: string; t: Tarjeta; acciones?: AccionHoja[]; destacar?: string; verFicha?: () => void }

export function HojaMover({ x, cerrar, elegir, acciones, destacar, verFicha }: { x: Tarjeta; cerrar: () => void; elegir: (estado: string) => void; acciones?: AccionHoja[]; destacar?: string; verFicha?: () => void }) {
  // el cambio más probable va el primero (p. ej. «Ya la envié» desde el botón de ese nombre)
  const opciones = destacar && x.moverA.includes(destacar) ? [destacar, ...x.moverA.filter(e => e !== destacar)] : x.moverA
  return <Hoja titulo={x.titulo} id="mover" cerrar={cerrar}>
    {acciones && acciones.length > 0 && <div className="pz-hoja-acc pz-hoja-acc-ya">{acciones.map(a => <button key={a.texto} type="button" className={`pz-btn ${a.primaria ? 'pz-btn-primario' : 'pz-btn-suave'}`} onClick={() => { cerrar(); a.run() }}>{a.texto}</button>)}</div>}
    <p className="pz-hoja-sub">Ahora está en <b>{DONDE[x.estado] ?? (cap(x.estado) || 'sin estado')}</b>.{x.moverA.length ? ' ¿Qué ha pasado?' : ''}</p>
    {opciones.length > 0
      ? <div className="pz-opciones" role="radiogroup" aria-label="¿Qué ha pasado?">{opciones.map(e => <button key={e} type="button" role="radio" aria-checked={e === x.estado} className={`pz-opcion ${e === destacar ? 'sugerida' : ''}`} disabled={e === x.estado} data-foco={e !== x.estado && (e === opciones[0] || e === destacar) ? true : undefined} onClick={() => elegir(e)}>
        <span>{FRASE[e] ?? cap(e)}{FRASE[e] && <small className="pz-opcion-est">{cap(e)}</small>}</span>{e === x.estado && <small>Aquí</small>}</button>)}</div>
      : <p className="pz-hoja-texto">Esta tarjeta no se puede mover desde la app. Si es una idea, conviértela en proyecto desde Obsidian.</p>}
    <dl className="pz-detalle">
      {x.siguiente && <><dt>Siguiente</dt><dd>{x.siguiente}</dd></>}
      {x.plazo && <><dt>Plazo</dt><dd>{diaCorto(x.plazo)} · {enDias(x.dias)}</dd></>}
      {(x.puesto || x.empresa) && <><dt>Puesto</dt><dd>{[x.puesto, x.empresa].filter(Boolean).join(' · ')}</dd></>}
      {x.pasos.total > 0 && <><dt>Pasos</dt><dd>{x.pasos.hechos} de {x.pasos.total}</dd></>}
      {x.tags.length > 0 && <><dt>Etiquetas</dt><dd>{x.tags.join(', ')}</dd></>}
    </dl>
    <div className="pz-hoja-acc">
      {verFicha && <button type="button" className="pz-btn pz-btn-suave" onClick={() => { cerrar(); verFicha() }}>Ver la ficha</button>}
      {x.enlace && <a className="pz-btn pz-btn-suave" href={x.enlace} target="_blank" rel="noopener noreferrer">Abrir enlace <Icono n="link" size={15} /></a>}
      {x.obsidian && <a className="pz-btn pz-btn-texto" href={x.obsidian}>Abrir en Obsidian</a>}
      <button type="button" className="pz-btn pz-btn-texto" onClick={cerrar}>Cerrar</button>
    </div>
    <p className="pz-nota">Mover solo cambia el estado de la nota; el resto no se toca.</p>
  </Hoja>
}

/** La hoja y el guardado, juntos: `abrir(...)` enseña «¿Qué ha pasado?» y, al elegir, mueve la tarjeta. */
export function useMover(datos: Tablero[], t: DatosTableros, ctx: Ctx) {
  const [sel, setSel] = useState<Abierta | null>(null)
  const guardar = async (id: string, x: Tarjeta, estado: string) => {
    const antes = datos
    const nueva = { ...x, estado }
    t.setData(colocar(datos, id, nueva, x.ruta))
    try {
      const r = await moverTarjeta(x, estado)
      if (r.ok) {
        if (r.tarjeta) t.setData(d => d && colocar(d, id, r.tarjeta!, x.ruta))
        ctx.toast(`«${x.titulo}» está ahora en ${cap(estado)}`)
      } else {
        if (r.conflicto && r.tarjeta) t.setData(d => d && colocar(d, id, r.tarjeta!, x.ruta)); else t.setData(antes)
        ctx.toast(r.error)
        if (r.conflicto) void t.reload()
      }
    } catch (e) { t.setData(antes); ctx.toast(`No se pudo mover: ${(e as Error).message}`) }
  }
  const hoja = sel && <HojaMover x={sel.t} acciones={sel.acciones} destacar={sel.destacar} verFicha={sel.verFicha} cerrar={() => setSel(null)} elegir={e => { const m = sel; setSel(null); void guardar(m.tablero, m.t, e) }} />
  return { abrir: setSel, hoja }
}
