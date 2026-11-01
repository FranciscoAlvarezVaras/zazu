import { useState } from 'react'
import { Icon } from '../icons'
import { dueLabel, isoDay, post, useFetch } from '../lib'
import type { Task } from '../lib'
import type { Ctx } from '../ctx'
import { Entendiendo, HojasOrden, useOrden } from '../panel/Propuesta'

export default function Tareas({ go, toast, guest, ask }: Ctx) {
  const { data, loading, error, reload } = useFetch<Task[]>('/api/tareas')
  const [hechas, setHechas] = useState<Task[]>([])
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const [busy, setBusy] = useState(false)
  // Fran (no las invitadas): «Añadir tarea» pasa por el mismo intérprete que la barra de «Mi día» y enseña la misma hoja de confirmación
  const o = useOrden({ toast, alApuntar: () => void reload() })

  const ids = new Set(hechas.map(t => t.id))
  const pend = (data || []).filter(t => !t.done && !ids.has(t.id))
  const total = pend.length + hechas.length
  const pct = total ? Math.round((hechas.length / total) * 100) : 100
  const fallo = !!error && !data   // sin la lista no se puede decir «todo hecho»

  async function act(action: 'done' | 'undo', t: Task) {
    setBusy(true)
    try {
      await post('/api/tareas', { action, id: t.id, account: t.account })
      setHechas(h => action === 'done' ? [...h, t] : h.filter(x => x.id !== t.id))
      if (action === 'undo') await reload()
    } catch (e) { toast(`No se pudo actualizar: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  async function add() {
    const t = title.trim(); if (!t) return
    if (!guest) { void o.enviar(due ? `${t} para el ${due}` : t); return }
    await guardar(t)
  }
  /** Guarda el texto tal cual como tarea (lo único que hacen las invitadas, y lo que Fran elige si Zazu no lo entiende). */
  async function guardar(t: string) {
    setBusy(true)
    try { await post('/api/tareas', { action: 'add', title: t, due }); setTitle(''); setDue(''); setAdding(false); toast('Tarea añadida a Google Tasks'); await reload() }
    catch (e) { toast(`No se pudo añadir: ${(e as Error).message}`); throw e } finally { setBusy(false) }
  }

  return <div className="tasks-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">UN PASO A LA VEZ</span><h2>Tus tareas<span className="greeting-dot">.</span></h2><p>De tu lista «Mis tareas» de Google.</p></div>
    <div className="task-progress"><div className="progress-top"><span>PROGRESO DE ESTA SESIÓN</span><strong>{loading || fallo ? '…' : `${pct}%`}</strong></div><div className="progress-track"><div style={{ width: `${pct}%` }} /></div>
      <p>{loading ? 'Cargando…' : fallo ? 'No pude leer tu lista.' : pend.length ? `${pend.length} ${pend.length === 1 ? 'tarea pendiente' : 'tareas pendientes'}.` : '¡Todo hecho! Buen trabajo.'}</p></div>
    <div className="tasks-header"><div><span className="section-kicker">EN TU LISTA</span><h3>Pendientes <span>{String(pend.length).padStart(2, '0')}</span></h3></div>
      <button className="add-task-button" onClick={() => setAdding(true)} aria-label="Añadir tarea"><Icon name="plus" size={21} /></button></div>
    {adding && <form className="add-task-form" onSubmit={e => { e.preventDefault(); void add() }}>
      <input autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="¿Qué necesitas hacer?" aria-label="Nueva tarea" maxLength={guest ? 200 : 500} disabled={o.fase?.k === 'pensando'} />
      <input type="date" value={due} min={isoDay()} onChange={e => setDue(e.target.value)} aria-label="Fecha límite" className="date-input" />
      <button type="button" onClick={() => { setAdding(false); setTitle('') }} aria-label="Cancelar"><Icon name="close" size={18} /></button>
      <button className="save-task" type="submit" disabled={!title.trim() || busy || o.ocupado} aria-label="Guardar tarea"><Icon name="check" size={18} /></button>
    </form>}
    {!guest && adding && <Entendiendo o={o} />}
    {!guest && <HojasOrden o={o} texto={due ? `${title.trim()} para el ${due}` : title.trim()} editar={o.cerrar} limpiar={() => { setTitle(''); setDue(''); setAdding(false) }}
      abrirChat={t => ask(t, { fill: true })} guardarTalCual={() => guardar(title.trim())} />}
    {error && <div className="fallo" role="alert"><span>No pude leer tus tareas{data ? ': puede que falte alguna' : ''}.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    <div className="task-list">{pend.map(t => <div className="task-row" key={t.id}>
      <button className="task-checkbox" disabled={busy} onClick={() => void act('done', t)} aria-label={`Completar ${t.title}`} />
      <div><strong>{t.title}</strong><small className={t.due && t.due < isoDay() ? 'late' : ''}><span className="acc-tag">{t.tag}</span>{dueLabel(t.due)}{t.notes ? ` · ${t.notes.slice(0, 40)}` : ''}{t.link && <> · <a href={t.link} target="_blank" rel="noopener noreferrer">Abrir en Google ↗</a></>}</small></div>
    </div>)}
      {!pend.length && !loading && !fallo && <div className="empty-tasks"><span className="empty-tasks-icon"><Icon name="check" size={26} /></span><strong>Todo en orden.</strong><p>No tienes tareas pendientes.</p></div>}
    </div>
    {hechas.length > 0 && <div className="completed-section"><span className="section-kicker">COMPLETADAS ESTA SESIÓN</span>
      {hechas.map(t => <div className="task-row completed" key={t.id}>
        <button className="task-checkbox checked" disabled={busy} onClick={() => void act('undo', t)} aria-label={`Marcar ${t.title} como pendiente`}><Icon name="check" size={14} /></button>
        <div><strong>{t.title}</strong><small>Completada</small></div></div>)}</div>}
    {!guest && <button className="inline-link-card" onClick={() => go('calendario')}><span className="inline-link-icon"><Icon name="calendar" size={19} /></span><span><strong>Ver mi día</strong><small>Tu agenda, hora por hora</small></span><Icon name="arrow" size={17} /></button>}
  </div>
}
