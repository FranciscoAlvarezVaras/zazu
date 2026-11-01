import { useState } from 'react'
import { Icon } from '../icons'
import type { IconName } from '../icons'
import { QUICK } from '../data'
import { abrirEnCarpetas, dueLabel, fechaLarga, hm, irA, isoDay, md, relTime, urlDescarga, useFetch } from '../lib'
import type { Ev, Hoy, Kind, Reciente, Task } from '../lib'
import type { Ctx } from '../ctx'

/** Error honesto con botón para volver a intentarlo (nunca «no hay nada» si en realidad falló). */
function Fallo({ texto, reintentar }: { texto: string; reintentar: () => void }) {
  return <div className="fallo" role="alert"><span>{texto}</span><button type="button" className="reintentar" onClick={reintentar}>Reintentar</button></div>
}

/** «08:00» si es de hoy; «Ayer 08:00» o «15 oct 08:00» si no (antes un resumen de hace tres días se leía como el de hoy). */
const hmDia = (v: string | number | null) => { const t = relTime(v), h = hm(v); return t === h ? h : `${t} ${h}` }

/** El resumen de la mañana (rutina de Zazu): plegado, con «Ver completo». */
function Resumen() {
  const hoy = useFetch<Hoy>('/api/hoy')
  const [full, setFull] = useState(false)
  const r = hoy.data?.resumen
  if (!r) return null
  return <section className="analysis-card summary-card">
    <span className="analysis-kicker"><Icon name="spark" size={15} /> {r.titulo.toUpperCase()} · {hmDia(r.cuando)}</span>
    <div className={`md ${full ? '' : 'collapsed'}`} dangerouslySetInnerHTML={{ __html: md(r.texto) }} />
    <button className="text-link" onClick={() => setFull(!full)} aria-expanded={full}>{full ? 'Ver menos' : 'Ver completo'} <Icon name="arrow" size={16} /></button>
  </section>
}

const ICONO: Partial<Record<Kind, IconName>> = { folder: 'folder', video: 'play', audio: 'volume', note: 'pen' }
function Miniatura({ f }: { f: Reciente }) {
  const [roto, setRoto] = useState(false)
  if (f.kind === 'image' && !roto) return <span className="radar-icon reciente-mini"><img src={urlDescarga('compartido', f.path, true)} alt="" loading="lazy" onError={() => setRoto(true)} /></span>
  return <span className="radar-icon">{f.kind === 'pdf' ? <b className="reciente-ext">PDF</b> : <Icon name={ICONO[f.kind] || 'file'} size={18} />}</span>
}

/** Lo último que ha entrado en Carpetas (lo que mandas por WhatsApp va solo a Recibidos). */
function Recientes() {
  const r = useFetch<{ items: Reciente[] }>('/api/recientes?n=5')
  const items = (r.data?.items || []).slice(0, 5)
  return <section className="section recientes-section">
    <div className="section-heading"><div><span className="section-kicker">TUS ARCHIVOS</span><h3>Guardado hace poco</h3></div><button className="text-link" onClick={() => irA({ tab: 'carpetas' })}>Ver carpetas <Icon name="arrow" size={16} /></button></div>
    {r.error && !r.data ? <Fallo texto="No pude ver lo último que has guardado." reintentar={() => void r.reload()} />
      : <div className="radar-list">{items.map(f => <button className="radar-item" key={f.path} onClick={() => abrirEnCarpetas('compartido', f.path, false)}>
        <Miniatura f={f} />
        <span className="radar-info"><strong>{f.name}</strong><small>{f.origen === 'whatsapp' && <span className="tag-wa">por WhatsApp</span>}{(f.folder || 'Carpetas').split('/').join(' › ')} · {relTime(f.mtime)}</small></span><Icon name="chevron" size={18} />
      </button>)}
        {!items.length && <div className="empty-radar">{r.loading ? 'Cargando…' : 'Aún no hay nada. Mándale a Zazu un archivo o una foto por WhatsApp y aparecerá aquí.'}</div>}</div>}
  </section>
}

/** «Hoy»: el resumen de la mañana, la agenda y las tareas del día, mañana y lo último guardado (antes repartido con Inicio). */

export default function MiDia({ go, ask }: Ctx) {
  const agenda = useFetch<Ev[]>('/api/agenda')
  const tareas = useFetch<Task[]>('/api/tareas')
  const ahora = new Date()
  const evs = agenda.data || []
  const hoyEv = evs.filter(e => e.day === 'hoy')
  const mañana = evs.filter(e => e.day === 'mañana')
  const vencen = (tareas.data || []).filter(t => !t.done && t.due && t.due <= isoDay())
  const pasados = hoyEv.filter(e => !e.allDay && e.end && new Date(e.end) < ahora).length
  const prox = hoyEv.find(e => !e.allDay && e.start && new Date(e.start) > ahora)
  const n = hoyEv.length + vencen.length
  const pct = hoyEv.length ? (pasados / hoyEv.length) * 100 : 0
  const cargando = agenda.loading || tareas.loading
  const falta = [agenda.error && !agenda.data ? 'la agenda' : '', tareas.error && !tareas.data ? 'las tareas' : ''].filter(Boolean)   // sin datos no se puede decir «día despejado»

  const item = (e: Ev) => <div className="timeline-item" key={e.id}>
    <span className="timeline-time">{e.allDay ? 'Día' : hm(e.start)}</span><span className="timeline-line"><span /></span>
    <div className="timeline-card"><span className="timeline-category">Agenda{e.location ? ` · ${e.location.slice(0, 28)}` : ''}</span><strong>{e.title}</strong></div></div>

  return <div className="extra-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">{fechaLarga().toUpperCase()}</span><h2>Hoy<span className="greeting-dot">.</span></h2><p>Una cosa a la vez, sin perder el rumbo.</p></div>
    <div className="day-hero"><div className="day-hero-top"><span>EL DÍA DE HOY</span><span className="day-hero-icon"><Icon name="sun" size={21} /></span></div>
      <strong>{cargando ? 'Mirando tu día…' : falta.length ? 'No pude leerlo todo' : n ? `${n} ${n === 1 ? 'cosa' : 'cosas'} hoy` : 'Día despejado'}</strong>
      <p>{cargando ? 'Leyendo agenda y tareas.' : falta.length ? `Me falta ${falta.join(' y ')}.` : prox ? `Lo próximo: ${hm(prox.start)} · ${prox.title}` : n ? 'Sin más citas por hoy.' : 'Nada en agenda ni tareas que venzan hoy.'}</p>
      <div className="day-progress"><div style={{ width: `${pct}%` }} /></div><small>{falta.length ? 'Faltan datos' : `${pasados} de ${hoyEv.length} citas ya pasadas`}</small></div>

    {falta.length > 0 && !cargando && <Fallo texto={`No pude leer ${falta.join(' ni ')}.`} reintentar={() => { void agenda.reload(); void tareas.reload() }} />}
    <Resumen />
    <div className="section-heading extra-section-heading"><div><span className="section-kicker">TU AGENDA</span><h3>Agenda y tareas</h3></div><button className="text-link" onClick={() => go('calendario')}>Calendario <Icon name="arrow" size={15} /></button></div>
    <div className="timeline">{hoyEv.map(item)}
      {vencen.map(t => <div className="timeline-item" key={t.id}><span className="timeline-time">Tarea</span><span className="timeline-line"><span /></span>
        <div className="timeline-card"><span className="timeline-category">{dueLabel(t.due)}</span><strong>{t.title}</strong></div></div>)}
      {!hoyEv.length && !vencen.length && <div className="empty-radar">{agenda.loading ? 'Cargando…' : falta.length ? 'Sin datos por ahora.' : 'Tu agenda de hoy está libre.'}</div>}
    </div>

    {mañana.length > 0 && <><div className="section-heading extra-section-heading"><div><span className="section-kicker">LO SIGUIENTE</span><h3>Mañana</h3></div></div><div className="timeline">{mañana.map(item)}</div></>}

    <Recientes />

    <button className="inline-link-card" onClick={() => ask(QUICK[0].prompt, { ctx: QUICK[0].ctx })}><span className="inline-link-icon"><Icon name="spark" size={19} /></span><span><strong>Organizar con Zazu</strong><small>Un plan a partir de tu agenda y tus tareas</small></span><Icon name="arrow" size={17} /></button>
  </div>
}
