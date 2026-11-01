/* Inicio: saludo, «Lo importante hoy» (máx. 3 filas, cada una con su SIGUIENTE ACCIÓN en lenguaje normal) y «Zazu propone apuntar N cosas» (de tus chats y tu correo).
   Sin indicadores ni tablas. La barra de Zazu (grande) y el panel de la derecha los pone el marco (Shell).
   Solo se pinta lo que esta persona tiene (Panel.hay): una invitada ve su agenda y sus tareas, nunca avisos ni capturas de Fran. */
import { useMemo, useState } from 'react'
import { fechaLarga, greeting, puede } from '../lib'
import type { Ctx } from '../ctx'
import { accionDeTarea, organizarAgenda } from './acciones'
import type { Accion } from './acciones'
import { tareaHecha } from './api'
import type { Aviso, Evento, Panel, TareaHoy } from './api'
import { Capturas, nombreFuente, useAccionAviso } from './Avisos'
import { useDatosPanel, usePanelDerecho } from './datos'
import { PanelInicio } from './Derecha'
import { diaSemana, fechaLarga as dia } from './formato'
import { Esqueleto, Fallo, horaDe, Hoja, Icono, Obsoleto, plural } from './ui'

/** «Tu tarde está libre»: solo si la agenda de hoy se leyó entera y no hay nada con hora entre las 15:00 y las 20:00 (o desde ahora). Lo usa la pestaña Zazu. */
export function tardeLibre(p: Panel, ahora = new Date()): { hora: string } | null {
  if (!p.eventos.ok || p.eventos.parcial.length || p.eventos.obsoleto) return null
  const h = ahora.getHours()
  if (h < 7 || h >= 18) return null
  const ini = new Date(ahora); ini.setHours(Math.max(15, h + 1), 0, 0, 0)
  const fin = new Date(ahora); fin.setHours(20, 0, 0, 0)
  if (fin.getTime() - ini.getTime() < 60 * 60000) return null
  const choca = p.eventos.items.some(e => {
    if (e.dia !== 'hoy' || e.todoDia) return false
    const a = new Date(e.inicio), b = e.fin ? new Date(e.fin) : new Date(a.getTime() + 3600e3)
    return a < fin && b > ini
  })
  return choca ? null : { hora: `${String(ini.getHours()).padStart(2, '0')}:00` }
}

type Fila = { clave: string; titulo: string; sub: string; urgente: boolean; accion: Accion | 'hecho' | 'agenda'; tarea?: TareaHoy; aviso?: Aviso; evento?: Evento }

/** «sábado 10» si fue esta semana; si no, «2 de octubre». */
const cuandoFue = (t: TareaHoy) => t.diasRetraso <= 6 && t.due ? `${diaSemana(t.due)} ${Number(t.due.slice(8, 10))}` : dia(t.due)

/** Hasta 3 cosas: primero las tareas vencidas (la más antigua delante) y las de hoy; si sobra sitio, avisos «ya» y la próxima cita de hoy. */
export function filasImportantes(p: Panel, hechas: Set<string>, ahora = new Date()): Fila[] {
  const tareas = p.tareas.ok ? p.tareas.items.filter(t => !hechas.has(t.id)) : []
  const venc = tareas.filter(t => t.vencida).sort((a, b) => a.due.localeCompare(b.due))
  const hoy = tareas.filter(t => !t.vencida)
  const filas: Fila[] = [...venc, ...hoy].map(t => ({ clave: 't' + t.id, titulo: t.titulo, urgente: t.vencida, tarea: t, accion: accionDeTarea(t.titulo),
    sub: t.vencida ? `Se pasó el ${cuandoFue(t)}` : 'Para hoy' }))
  if (filas.length < 3 && p.avisos.ok) for (const a of p.avisos.items.filter(x => x.prio === 1)) filas.push({ clave: 'a' + a.id, titulo: a.titulo, sub: `${nombreFuente(a.fuente)}${a.chat ? ` · ${a.chat}` : ''}`, urgente: true, aviso: a, accion: 'hecho' })
  if (filas.length < 3 && p.eventos.ok) {
    const prox = p.eventos.items.filter(e => e.dia === 'hoy' && !e.todoDia && new Date(e.fin || e.inicio) > ahora).sort((a, b) => a.inicio.localeCompare(b.inicio))[0]
    if (prox) filas.push({ clave: 'e' + prox.id, titulo: prox.titulo, sub: `Hoy a las ${horaDe(prox.inicio)}${prox.lugar ? ` · ${prox.lugar}` : ''}`, urgente: false, evento: prox, accion: 'agenda' })
  }
  return filas.slice(0, 3)
}

export default function Hoy(ctx: Ctx) {
  const { data, error, loading, recargar, refrescar } = useDatosPanel()
  const derecho = usePanelDerecho()
  const { toast, go, me } = ctx
  const [hechas, setHechas] = useState<TareaHoy[]>([])
  const [ocupado, setOcupado] = useState('')
  const [revisar, setRevisar] = useState(false)
  const idsHechas = useMemo(() => new Set(hechas.map(t => t.id)), [hechas])
  const aviso = useAccionAviso(toast, refrescar)
  const nombre = data?.nombre || me.name || me.user || ''
  const asistente = ctx.nombre || 'Zazu'

  async function completar(t: TareaHoy) {
    setOcupado(t.id)
    try { await tareaHecha(t, true); setHechas(h => [...h, t]); toast('Tarea completada'); void refrescar() }
    catch (e) { toast(`No se pudo completar: ${(e as Error).message}`) } finally { setOcupado('') }
  }
  async function deshacer(t: TareaHoy) {
    setOcupado(t.id)
    try { await tareaHecha(t, false); setHechas(h => h.filter(x => x.id !== t.id)); await refrescar() }
    catch (e) { toast(`No se pudo deshacer: ${(e as Error).message}`) } finally { setOcupado('') }
  }
  const pedir = (a: Accion) => { ctx.setDraft(''); ctx.ask(a.peticion, { fill: true }) }   // el chat se abre con la petición escrita; la mandas tú

  const encabezado = <header className="pz-hoy-cab">
    <p className="pz-fecha">{fechaLarga().toLowerCase()}</p>
    <h1>{greeting()}{nombre ? `, ${nombre}` : ''}</h1>
  </header>

  if (!data) return <div className="pz-page pz-hoy">
    {encabezado}
    {loading ? <Esqueleto filas={4} alto={64} /> : <Fallo texto={`No pude leer tu día${error ? `: ${error}` : ''}.`} reintentar={() => void recargar()} />}
  </div>

  const filas = filasImportantes(data, idsHechas)
  const tareas = data.tareas.ok ? data.tareas.items.filter(t => !idsHechas.has(t.id)) : []
  const nVenc = tareas.filter(t => t.vencida).length, nHoy = tareas.length - nVenc
  const masAntigua = tareas.filter(t => t.vencida).sort((a, b) => a.due.localeCompare(b.due))[0]
  const capturas = data.capturas.ok ? data.capturas.items : []
  const completas = data.eventos.ok && data.tareas.ok && (!data.hay.avisos || data.avisos.ok)   // sin poder leer los avisos no se puede decir «todo en orden»
  const sinNada = completas && !filas.length && !hechas.length
  const hay = data.hay
  const importante = hay.eventos || hay.tareas || hay.avisos
  const preparar = (t: string) => { setRevisar(false); ctx.setDraft(t); go('inicio') }   // «Sí»: la frase queda en la barra de Zazu; la apuntas tú
  const resumenCap = capturas.slice(0, 2).map(c => `${c.chat ? `${c.chat}: ` : ''}${c.titulo}`).join(' · ')

  const botonAccion = (f: Fila) => {
    const cls = `pz-btn pz-btn-fila ${f.urgente ? 'urgente' : ''}`
    if (f.accion === 'hecho') return <button type="button" className={cls} disabled={aviso.ocupado === f.aviso!.id} onClick={() => void aviso.hacer(f.aviso!, 'hecho')}>Marcar hecho</button>
    if (f.accion === 'agenda') return <button type="button" className={cls} onClick={() => go('calendario')}>Ver la agenda</button>
    const a = f.accion
    return <button type="button" className={cls} onClick={() => pedir(a)}>{a.texto}</button>
  }

  return <div className="pz-page pz-hoy">
    {encabezado}
    {(!data.eventos.ok || !data.tareas.ok || (hay.avisos && !data.avisos.ok)) && <Fallo texto={[!data.eventos.ok && `No pude leer la agenda: ${data.eventos.error}.`, !data.tareas.ok && `No pude leer las tareas: ${data.tareas.error}.`, hay.avisos && !data.avisos.ok && `No pude leer tus avisos: ${data.avisos.error}.`].filter(Boolean).join(' ')} reintentar={() => void refrescar()} />}
    {data.eventos.ok && data.eventos.obsoleto && <Obsoleto actualizado={data.eventos.actualizado} />}
    {data.eventos.ok && data.eventos.parcial.length > 0 && <p className="pz-nota" role="status">No pude leer la agenda de {data.eventos.parcial.join(' ni ')}: puede que falte alguna cita.</p>}
    {data.tareas.ok && data.tareas.parcial.length > 0 && <p className="pz-nota" role="status">No pude leer las tareas de {data.tareas.parcial.join(' ni ')}: puede que falte alguna.</p>}

    {hay.tareas && data.tareas.ok && (nVenc > 0 || nHoy > 0) && <div className="pz-mini" aria-label="Resumen de tareas">
      <button type="button" onClick={() => go('tareas')}><span>Hoy</span><b>{nHoy}</b><small className="ok">{nHoy === 1 ? 'tarea' : 'tareas'}</small></button>
      <button type="button" onClick={() => go('tareas')}><span>Vencidas</span><b className={nVenc ? 'mal' : ''}>{nVenc}</b><small>{masAntigua ? `desde el ${dia(masAntigua.due)}` : 'ninguna'}</small></button>
    </div>}

    {importante ? <section className="pz-tarjeta-g" aria-labelledby="pz-imp-t">
      <div className="pz-tarjeta-cab"><h2 id="pz-imp-t">Lo importante hoy</h2>{hay.tareas && puede(me, 'tareas') && <button type="button" className="pz-enlace" onClick={() => go('tareas')}>Ver todas</button>}</div>
      {filas.length > 0 && <ul className="pz-imp">{filas.map(f => <li key={f.clave} className="pz-imp-fila">
        {f.tarea ? <button type="button" className="pz-casilla" disabled={ocupado === f.tarea.id} onClick={() => void completar(f.tarea!)} aria-label={`Marcar hecha: ${f.titulo}`}><span /></button>
          : <span className="pz-imp-ico" aria-hidden="true"><Icono n={f.evento ? 'calendar' : 'alert'} size={18} /></span>}
        <div className="pz-imp-txt"><strong>{f.titulo}</strong><span className={f.urgente ? 'pz-mal' : ''}>{f.sub}</span></div>
        {botonAccion(f)}
      </li>)}
        {hechas.filter(t => !tareas.some(x => x.id === t.id)).map(t => <li key={'h' + t.id} className="pz-imp-fila pz-hecha">
          <button type="button" className="pz-casilla on" disabled={ocupado === t.id} onClick={() => void deshacer(t)} aria-label={`Marcar como pendiente: ${t.titulo}`}><span><Icono n="check" size={14} /></span></button>
          <div className="pz-imp-txt"><strong>{t.titulo}</strong><span>Hecha ahora · toca el círculo para deshacer</span></div></li>)}
      </ul>}
      {sinNada && <div className="pz-calma"><Icono n="check" size={22} /><div><strong>Todo en orden.</strong><p>No tienes nada urgente para hoy.</p></div></div>}
      {!completas && !filas.length && <p className="pz-vacio">No pude leerlo todo: mira de nuevo en un momento.</p>}
    </section>
      : <section className="pz-tarjeta-g pz-vio" aria-labelledby="pz-goo-t">
        <span className="pz-vio-ico" aria-hidden="true"><Icono n="calendar" size={22} /></span>
        <div className="pz-vio-txt"><strong id="pz-goo-t">Tu agenda y tus tareas, aquí</strong><span>Conecta tu Google y {asistente} te enseñará cada mañana lo importante del día.</span></div>
        <button type="button" className="pz-btn pz-btn-primario pz-btn-grande" onClick={() => go('ajustes')}>Conectar Google</button>
      </section>}

    {puede(me, 'tableros') && <section className="pz-tarjeta-g pz-vio pz-ordena" aria-labelledby="pz-ord-t">
      <span className="pz-vio-ico" aria-hidden="true"><Icono n="spark" size={22} /></span>
      <div className="pz-vio-txt"><strong id="pz-ord-t">Ordenar todo con Zazu</strong><span>Zazu te propone los cambios y tú los apruebas.</span></div>
      <button type="button" className="pz-btn pz-btn-primario pz-btn-grande" onClick={() => ctx.ask(organizarAgenda(!!ctx.guest), { nueva: true })}>Organizar mi agenda</button>
    </section>}

    {!hay.capturas ? null : data.capturas.ok
      ? capturas.length > 0 && <section className="pz-tarjeta-g pz-vio" aria-label="Lo que Zazu propone apuntar">
        <span className="pz-vio-ico" aria-hidden="true"><Icono n="spark" size={22} /></span>
        <div className="pz-vio-txt"><strong>Zazu propone apuntar {plural(capturas.length, 'cosa', 'cosas')}</strong><span>{resumenCap}</span></div>
        <button type="button" className="pz-btn pz-btn-primario pz-btn-grande" onClick={() => setRevisar(true)}>Revisar</button>
      </section>
      : <Fallo texto={`No pude ver lo que Zazu apuntó de tus chats: ${data.capturas.error}.`} reintentar={() => void refrescar()} />}

    {!derecho && <div className="pz-inicio-extra"><PanelInicio ctx={ctx} /></div>}
    {aviso.hoja}
    {revisar && <Hoja titulo={`Zazu propone ${plural(capturas.length, 'cosa', 'cosas')}`} id="capturas" cerrar={() => setRevisar(false)}>
      <p className="pz-hoja-sub">Lo que Zazu propone apuntar de tus chats y tu correo. «Sí, siempre» y «No, nunca» hacen que no te lo vuelva a preguntar.</p>
      <Capturas items={capturas} toast={toast} alCambiar={refrescar} preparar={preparar} vacio="Ya está todo revisado." />
      <div className="pz-hoja-acc"><button type="button" className="pz-btn pz-btn-texto" data-foco onClick={() => setRevisar(false)}>Cerrar</button></div>
    </Hoja>}
  </div>
}
