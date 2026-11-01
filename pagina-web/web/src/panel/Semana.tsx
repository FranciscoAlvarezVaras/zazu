/* «Semana»: una tarjeta por día (lunes a domingo), con el día de hoy abierto. Cada tarea es una casilla que al marcarse se completa;
   se puede tocar el texto para editarlo, añadir micro-tareas a un día, pasarlas a mañana y arrastrar (derecha = hecho, izquierda = a mañana).
   Arriba, el progreso de hoy, una barra por día y la racha. Abajo, el Depósito (tareas sin día) y las Plantillas repetibles.
   <ParaHacer> es la versión corta para el panel de al lado de la Agenda. Todo son tus tareas de Google (/api/tareas). */
import { useEffect, useRef, useState } from 'react'
import { AVISO_CAMBIO, avisarCambio, isoDay, post, useFetch } from '../lib'
import type { Ctx } from '../ctx'
import type { Task } from '../lib'
import { Icono } from './ui'

const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado']
const INICIAL = ['D', 'L', 'M', 'X', 'J', 'V', 'S']
const masDias = (iso: string, n: number) => { const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return isoDay(d) }
/** El lunes de la semana de `iso`. */
const lunesDe = (iso: string) => { const d = new Date(iso + 'T12:00:00'); return masDias(iso, -((d.getDay() + 6) % 7)) }
const nombreDia = (iso: string, hoy: string) =>
  iso === hoy ? 'Hoy' : iso === masDias(hoy, 1) ? 'Mañana' : `${DIAS[new Date(iso + 'T12:00:00').getDay()]} ${Number(iso.slice(8, 10))}`

type Parche = { done?: boolean; due?: string; title?: string; oculta?: boolean }
type Cuerpo = { action: 'add' | 'done' | 'undo' | 'edit' | 'move'; id?: string; account?: string; title?: string; due?: string }

/** Las tareas de Google con un «parche» local encima para que el cambio se vea al instante; al llegar datos frescos los parches se olvidan. */
function useTareas() {
  const r = useFetch<Task[]>('/api/tareas', 120000)
  const [parches, setParches] = useState<Record<string, Parche>>({})
  useEffect(() => { const f = () => void r.reload(); addEventListener(AVISO_CAMBIO, f); return () => removeEventListener(AVISO_CAMBIO, f) }, [r.reload])
  useEffect(() => { if (r.data) setParches({}) }, [r.data])
  const tareas = (r.data || []).map(t => ({ ...t, ...parches[t.id] })).filter(t => !parches[t.id]?.oculta)
  const cuentaPorDefecto = (r.data || [])[0]?.account

  async function aplicar(cuerpo: Cuerpo, toast: (m: string) => void, ok: string, parche?: { id: string; cambio: Parche }) {
    if (parche) setParches(p => ({ ...p, [parche.id]: { ...p[parche.id], ...parche.cambio } }))
    try {
      await post('/api/tareas', cuerpo)
      void r.reload(); avisarCambio()
      if (ok) toast(ok)
      return true
    } catch (e) {
      if (parche) setParches(p => { const n = { ...p }; delete n[parche.id]; return n })
      toast((e as Error).message || 'No pude cambiarla')
      return false
    }
  }
  return { r, tareas, aplicar, cuentaPorDefecto }
}

/** Arrastre horizontal sencillo: derecha = completar, izquierda = pasar a mañana. No se activa sobre un control ni con «menos movimiento». */
function useArrastre(alCompletar: () => void, alMover: () => void) {
  const reduce = useRef(typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  const x0 = useRef<number | null>(null)
  const [dx, setDx] = useState(0)
  const UMBRAL = 72
  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button, input, a, textarea, label')) return
    x0.current = e.clientX
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (x0.current === null) return
    const d = e.clientX - x0.current
    if (!reduce.current) setDx(Math.max(-130, Math.min(130, d)))
  }
  const fin = (e: React.PointerEvent) => {
    if (x0.current === null) return
    const d = e.clientX - x0.current
    x0.current = null; setDx(0)
    if (d > UMBRAL) alCompletar()
    else if (d < -UMBRAL) alMover()
  }
  return { dx, props: { onPointerDown, onPointerMove, onPointerUp: fin, onPointerCancel: fin } }
}

/** Una tarea: casilla para completar, texto editable al tocarlo, botón «a mañana» y arrastre. */
function Fila({ t, hoy, aplicar, toast }: { t: Task; hoy: string; aplicar: ReturnType<typeof useTareas>['aplicar']; toast: (m: string) => void }) {
  const [editando, setEditando] = useState(false)
  const [texto, setTexto] = useState(t.title)
  const completar = () => aplicar(
    { action: t.done ? 'undo' : 'done', id: t.id, account: t.account }, toast,
    t.done ? 'Vuelta a pendiente' : '¡Hecho!', { id: t.id, cambio: { done: !t.done } })
  const aManana = () => aplicar(
    { action: 'move', id: t.id, account: t.account, due: masDias(hoy, 1) }, toast,
    'Pasada a mañana', { id: t.id, cambio: { due: masDias(hoy, 1), oculta: t.due === hoy || t.due < hoy ? false : true } })
  const guardar = () => {
    const limpio = texto.trim()
    setEditando(false)
    if (!limpio || limpio === t.title) { setTexto(t.title); return }
    void aplicar({ action: 'edit', id: t.id, account: t.account, title: limpio }, toast, 'Cambiada', { id: t.id, cambio: { title: limpio } })
  }
  const { dx, props } = useArrastre(() => { if (!t.done) void completar() }, () => void aManana())
  const atrasado = t.due && t.due < hoy
  return <li className="sem-fila-wrap">
    <span className="sem-hint sem-hint-si" aria-hidden="true"><Icono n="check" size={18} /></span>
    <span className="sem-hint sem-hint-no" aria-hidden="true"><Icono n="arrow" size={18} /></span>
    <div className={`sem-tarea${t.done ? ' hecha' : ''}`} style={dx ? { transform: `translateX(${dx}px)` } : undefined} {...props}>
      <input type="checkbox" className="sem-check" checked={t.done} onChange={() => void completar()} aria-label={t.done ? `Marcar como pendiente: ${t.title}` : `Completar: ${t.title}`} />
      {editando
        ? <input className="sem-editar" autoFocus value={texto} onChange={e => setTexto(e.target.value)} onBlur={guardar}
            onKeyDown={e => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') { setTexto(t.title); setEditando(false) } }} aria-label="Editar la tarea" />
        : <button type="button" className="sem-txt" onClick={() => { setTexto(t.title); setEditando(true) }} aria-label={`Editar: ${t.title}`}>
            <strong>{t.title}</strong>{atrasado && <small className="sem-antes">de antes</small>}
          </button>}
      {!t.done && <button type="button" className="sem-man" onClick={() => void aManana()} aria-label={`Pasar a mañana: ${t.title}`}><Icono n="arrow" size={18} /></button>}
    </div>
  </li>
}

/** Campo rápido para añadir una micro-tarea a un día (o al depósito, con `due=''`). */
function Anadir({ due, aplicar, toast, cuenta }: { due: string; aplicar: ReturnType<typeof useTareas>['aplicar']; toast: (m: string) => void; cuenta?: string }) {
  const [texto, setTexto] = useState('')
  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    const limpio = texto.trim()
    if (!limpio) return
    setTexto('')
    await aplicar({ action: 'add', title: limpio, ...(due ? { due } : {}), ...(cuenta ? { account: cuenta } : {}) }, toast, 'Añadida')
  }
  return <form className="sem-anadir" onSubmit={enviar}>
    <input value={texto} onChange={e => setTexto(e.target.value)} placeholder="Añadir tarea…" aria-label="Añadir una tarea nueva" />
    <button type="submit" disabled={!texto.trim()} aria-label="Añadir"><Icono n="plus" size={18} /></button>
  </form>
}

/** Tarjeta de un día (acordeón): se abre y se cierra; el de hoy empieza abierto. */
function Tarjeta({ dia, hoy, tareas, aplicar, toast, cuenta, crearPlantilla }:
  { dia: string; hoy: string; tareas: Task[]; aplicar: ReturnType<typeof useTareas>['aplicar']; toast: (m: string) => void; cuenta?: string; crearPlantilla: (nombre: string, titulos: string[]) => void }) {
  const [abierto, setAbierto] = useState(dia === hoy)
  const [nombrando, setNombrando] = useState(false)
  const [nombre, setNombre] = useState('')
  const hechas = tareas.filter(t => t.done).length
  const id = `sem-d-${dia}`
  const pendientes = tareas.filter(t => !t.done).map(t => t.title)
  const guardar = (e: React.FormEvent) => {
    e.preventDefault()
    const n = nombre.trim()
    if (!n || !pendientes.length) return
    crearPlantilla(n, pendientes)
    setNombre(''); setNombrando(false)
  }
  return <section className={`sem-dia${dia === hoy ? ' hoy' : ''}`}>
    <h2>
      <button type="button" className="sem-cab" aria-expanded={abierto} aria-controls={id} onClick={() => setAbierto(v => !v)}>
        <span className={`sem-chevron${abierto ? ' abierto' : ''}`} aria-hidden="true"><Icono n="chevron" size={18} /></span>
        <span className="sem-nombre">{nombreDia(dia, hoy)}</span>
        {tareas.length > 0 && <span className="sem-cuenta">{hechas}/{tareas.length}</span>}
      </button>
    </h2>
    <div id={id} hidden={!abierto}>
      {tareas.length === 0 && <p className="sem-nada">Nada para este día.</p>}
      {tareas.length > 0 && <ul className="sem-lista">{tareas.map(t => <Fila key={t.id} t={t} hoy={hoy} aplicar={aplicar} toast={toast} />)}</ul>}
      <Anadir due={dia} aplicar={aplicar} toast={toast} cuenta={cuenta} />
      {pendientes.length > 0 && !nombrando && <button type="button" className="sem-plantilla-guardar" onClick={() => { setNombre(`Tareas de ${nombreDia(dia, hoy).toLowerCase()}`); setNombrando(true) }}>Guardar como plantilla</button>}
      {nombrando && <form className="sem-anadir sem-plantilla-form" onSubmit={guardar}>
        <input autoFocus value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Nombre de la plantilla" aria-label="Nombre de la plantilla"
          onKeyDown={e => { if (e.key === 'Escape') { setNombre(''); setNombrando(false) } }} />
        <button type="submit" disabled={!nombre.trim()}>Guardar</button>
      </form>}
    </div>
  </section>
}

type Racha = { ok: boolean; racha: number; hoy: { total: number; hechas: number } }

/** Cabecera motivadora y discreta: progreso de hoy, una barra por día de la semana y la racha de días cumplidos. */
function Progreso({ dias, hoy, tareas }: { dias: string[]; hoy: string; tareas: Task[] }) {
  const racha = useFetch<Racha>('/api/semana/racha', 120000)
  useEffect(() => { const f = () => void racha.reload(); addEventListener(AVISO_CAMBIO, f); return () => removeEventListener(AVISO_CAMBIO, f) }, [racha.reload])
  const porDia = (dia: string) => { const t = tareas.filter(x => x.due === dia); return { total: t.length, hechas: t.filter(x => x.done).length } }
  const h = porDia(hoy)
  const pct = h.total ? Math.round(100 * h.hechas / h.total) : 0
  const n = racha.data?.racha || 0
  return <section className="sem-progreso" aria-label="Tu progreso">
    <div className="sem-prog-cab">
      <div className="sem-prog-hoy">
        <span className="sem-prog-txt">{h.total ? `Hoy: ${h.hechas} de ${h.total}` : 'Hoy no tienes tareas'}</span>
        {h.total > 0 && <span className="sem-prog-barra"><i style={{ width: `${pct}%` }} /></span>}
      </div>
      {n > 0 && <span className="sem-racha" aria-label={`Racha: ${n} ${n === 1 ? 'día' : 'días'} cumplidos`}>🔥 {n}</span>}
    </div>
    <ol className="sem-barras">
      {dias.map(dia => {
        const d = porDia(dia)
        const alto = d.total ? Math.max(12, Math.round(100 * d.hechas / d.total)) : 6
        const dl = DIAS[new Date(dia + 'T12:00:00').getDay()]
        return <li key={dia} className={dia === hoy ? 'hoy' : undefined}>
          <span className="sem-barra-pista" aria-hidden="true"><i className={d.total && d.hechas === d.total ? 'full' : undefined} style={{ height: `${alto}%` }} /></span>
          <span className="sem-barra-dia" aria-label={`${dl}: ${d.hechas} de ${d.total}`}>{INICIAL[new Date(dia + 'T12:00:00').getDay()]}</span>
        </li>
      })}
    </ol>
  </section>
}

type Plantilla = { id: string; nombre: string; tareas: string[] }

/** Plantillas de micro-tareas repetibles: guardarlas y aplicarlas a un día con un toque (crea esas tareas en ese día). */
function Plantillas({ plantillas, dias, hoy, guardar, aplicar, toast, cuenta }:
  { plantillas: Plantilla[]; dias: string[]; hoy: string; guardar: (p: Plantilla[]) => void; aplicar: ReturnType<typeof useTareas>['aplicar']; toast: (m: string) => void; cuenta?: string }) {
  const [destino, setDestino] = useState<Record<string, string>>({})
  const aplicarA = async (p: Plantilla) => {
    const dia = destino[p.id] || hoy
    for (const titulo of p.tareas) await aplicar({ action: 'add', title: titulo, due: dia, ...(cuenta ? { account: cuenta } : {}) }, toast, '')
    toast(`«${p.nombre}» aplicada a ${nombreDia(dia, hoy).toLowerCase()}`)
  }
  const borrar = (id: string) => guardar(plantillas.filter(p => p.id !== id))
  return <section className="sem-plantillas" aria-label="Plantillas">
    <h2>Plantillas</h2>
    {plantillas.length === 0 && <p className="sem-nada">Aún no tienes plantillas. Guarda las micro-tareas de un día desde su tarjeta («Guardar como plantilla») y reutilízalas aquí.</p>}
    <ul className="sem-pl-lista">
      {plantillas.map(p => <li key={p.id} className="sem-pl">
        <div className="sem-pl-txt"><strong>{p.nombre}</strong><small>{p.tareas.length} {p.tareas.length === 1 ? 'tarea' : 'tareas'}</small></div>
        <div className="sem-pl-bts">
          <label className="sem-pl-sel"><span className="sr-only">Día para «{p.nombre}»</span>
            <select value={destino[p.id] || hoy} onChange={e => setDestino(d => ({ ...d, [p.id]: e.target.value }))}>
              {dias.map(dia => <option key={dia} value={dia}>{nombreDia(dia, hoy)}</option>)}
            </select>
          </label>
          <button type="button" className="sem-pl-aplicar" onClick={() => void aplicarA(p)}>Aplicar</button>
          <button type="button" className="sem-pl-x" onClick={() => borrar(p.id)} aria-label={`Borrar la plantilla ${p.nombre}`}><Icono n="close" size={16} /></button>
        </div>
      </li>)}
    </ul>
  </section>
}

export default function Semana(ctx: Ctx) {
  const { r, tareas, aplicar, cuentaPorDefecto } = useTareas()
  const hoy = isoDay()
  const lunes = lunesDe(hoy)
  const dias = Array.from({ length: 7 }, (_, i) => masDias(lunes, i))
  const finSemana = dias[6]

  const pl = useFetch<{ plantillas: Plantilla[] }>('/api/semana/plantillas')
  const [plantillas, setPlantillas] = useState<Plantilla[]>([])
  useEffect(() => { if (pl.data?.plantillas) setPlantillas(pl.data.plantillas) }, [pl.data])
  const guardarPlantillas = async (next: Plantilla[]) => {
    const antes = plantillas
    setPlantillas(next)
    try { const d = await post<{ plantillas: Plantilla[] }>('/api/semana/plantillas', { plantillas: next }); if (d.plantillas) setPlantillas(d.plantillas) }
    catch (e) { setPlantillas(antes); ctx.toast((e as Error).message || 'No pude guardar la plantilla') }
  }
  const crearPlantilla = (nombre: string, titulos: string[]) => {
    void guardarPlantillas([...plantillas, { id: Math.random().toString(36).slice(2, 12), nombre, tareas: titulos }])
    ctx.toast(`Plantilla «${nombre}» guardada`)
  }

  // qué tareas van en cada día: lo de hoy incluye lo atrasado aún pendiente; un día pasado solo enseña lo ya hecho (lo pendiente sube a Hoy)
  const delDia = (dia: string) => tareas.filter(t => {
    if (!t.due || t.due > finSemana) return false
    if (dia === hoy) return t.due === hoy || (t.due < hoy && !t.done)
    if (dia < hoy) return t.due === dia && t.done
    return t.due === dia
  })
  const inbox = tareas.filter(t => !t.due && !t.done)

  return <div className="sem">
    <h1>Tu semana</h1>
    {r.error && !r.data && <p className="pz-nota" role="alert">No pude leer tus tareas. <button type="button" className="pz-enlace" onClick={() => void r.reload()}>Reintentar</button></p>}
    {!r.data && !r.error && <p className="sem-vacio">Cargando…</p>}
    {r.data && <>
      <Progreso dias={dias} hoy={hoy} tareas={tareas} />
      <div className="sem-dias">
        {dias.map(dia => <Tarjeta key={dia} dia={dia} hoy={hoy} tareas={delDia(dia)} aplicar={aplicar} toast={ctx.toast} cuenta={cuentaPorDefecto} crearPlantilla={crearPlantilla} />)}
      </div>
      <section className="sem-dia sem-inbox" aria-label="Depósito">
        <h2><span className="sem-nombre">Depósito</span>{inbox.length > 0 && <span className="sem-cuenta">{inbox.length}</span>}</h2>
        <p className="sem-inbox-ayuda">Ideas y pendientes sin día. Pásalos a un día cuando quieras.</p>
        {inbox.length > 0 && <ul className="sem-lista">{inbox.map(t => <FilaInbox key={t.id} t={t} dias={dias} hoy={hoy} aplicar={aplicar} toast={ctx.toast} />)}</ul>}
        <Anadir due="" aplicar={aplicar} toast={ctx.toast} cuenta={cuentaPorDefecto} />
      </section>
      <Plantillas plantillas={plantillas} dias={dias} hoy={hoy} guardar={guardarPlantillas} aplicar={aplicar} toast={ctx.toast} cuenta={cuentaPorDefecto} />
    </>}
  </div>
}

/** Fila del Depósito: casilla para completar y un selector para mandarla a un día de la semana. */
function FilaInbox({ t, dias, hoy, aplicar, toast }: { t: Task; dias: string[]; hoy: string; aplicar: ReturnType<typeof useTareas>['aplicar']; toast: (m: string) => void }) {
  const mover = (dia: string) => aplicar({ action: 'move', id: t.id, account: t.account, due: dia }, toast, `Movida a ${nombreDia(dia, hoy).toLowerCase()}`, { id: t.id, cambio: { oculta: true } })
  const completar = () => aplicar({ action: 'done', id: t.id, account: t.account }, toast, '¡Hecho!', { id: t.id, cambio: { done: true } })
  return <li className="sem-fila-wrap">
    <div className="sem-tarea">
      <input type="checkbox" className="sem-check" checked={false} onChange={() => void completar()} aria-label={`Completar: ${t.title}`} />
      <span className="sem-txt sem-txt-inbox"><strong>{t.title}</strong></span>
      <label className="sem-pl-sel sem-inbox-sel"><span className="sr-only">Mover «{t.title}» a un día</span>
        <select value="" onChange={e => { if (e.target.value) void mover(e.target.value) }}>
          <option value="">A un día…</option>
          {dias.map(dia => <option key={dia} value={dia}>{nombreDia(dia, hoy)}</option>)}
        </select>
      </label>
    </div>
  </li>
}

/** Versión corta, al lado de la Agenda: hoy (con lo atrasado) y los 2 días siguientes, con casilla y «a mañana». */
export function ParaHacer({ ctx }: { ctx: Ctx }) {
  const { r, tareas, aplicar } = useTareas()
  const hoy = isoDay()
  const fin = masDias(hoy, 2)
  const grupos = [hoy, masDias(hoy, 1), masDias(hoy, 2)].map(dia => ({
    dia, nombre: nombreDia(dia, hoy),
    tareas: tareas.filter(t => !t.done && t.due && t.due <= fin && (dia === hoy ? t.due <= hoy : t.due === dia)).slice(0, 4),
  })).filter(g => g.tareas.length)
  return <section aria-labelledby="pz-d-ph">
    <div className="pz-der-cab"><h2 id="pz-d-ph">Para hacer</h2><button type="button" className="pz-enlace" onClick={() => ctx.go('semana')}>Ver semana</button></div>
    {!r.data ? <p className="pz-vacio">{r.error ? 'No pude leer tus tareas.' : 'Cargando…'}</p>
      : !grupos.length ? <p className="pz-vacio">Nada pendiente hoy ni los próximos días.</p>
        : grupos.map(g => <div key={g.dia} className="sem-dia corta"><h3>{g.nombre}</h3>
          <ul className="sem-lista">{g.tareas.map(t => <FilaCorta key={t.id} t={t} hoy={hoy} aplicar={aplicar} toast={ctx.toast} />)}</ul></div>)}
  </section>
}

function FilaCorta({ t, hoy, aplicar, toast }: { t: Task; hoy: string; aplicar: ReturnType<typeof useTareas>['aplicar']; toast: (m: string) => void }) {
  return <li className="sem-fila-wrap corta">
    <div className="sem-tarea corta">
      <input type="checkbox" className="sem-check" checked={false} onChange={() => void aplicar({ action: 'done', id: t.id, account: t.account }, toast, '¡Hecho!', { id: t.id, cambio: { done: true } })} aria-label={`Completar: ${t.title}`} />
      <span className="sem-txt"><strong>{t.title}</strong>{t.due < hoy && <small className="sem-antes">de antes</small>}</span>
      <button type="button" className="sem-man" onClick={() => void aplicar({ action: 'move', id: t.id, account: t.account, due: masDias(hoy, 1) }, toast, 'Pasada a mañana', { id: t.id, cambio: { oculta: true } })} aria-label={`Pasar a mañana: ${t.title}`}><Icono n="arrow" size={16} /></button>
    </div>
  </li>
}
