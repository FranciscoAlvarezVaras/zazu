import { useMemo, useState } from 'react'
import { Icon } from '../icons'
import { hm, isoDay, post, useFetch } from '../lib'
import type { Cuentas, Ev } from '../lib'
import type { Ctx } from '../ctx'

const DOW = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
/** Día (YYYY-MM-DD) en que empieza un evento, en hora local. */
const dayOf = (e: Ev) => e.allDay ? (e.start || '').slice(0, 10) : isoDay(new Date(e.start || 0))

export default function Calendario({ toast, go, guest }: Ctx) {
  const [mes, setMes] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const [sel, setSel] = useState(isoDay())
  const [form, setForm] = useState(false)
  const inicio = useMemo(() => addDays(mes, -((mes.getDay() + 6) % 7)), [mes])  // lunes de la primera semana
  const { data, loading, error, reload } = useFetch<Ev[]>(`/api/calendario?desde=${isoDay(inicio)}&dias=42`)
  const cuentas = useFetch<Cuentas>('/api/cuentas')
  const conCal = (cuentas.data?.google || []).filter(c => c.services.includes('calendar')).map(c => c.email)
  const sinCal = (cuentas.data?.google || []).filter(c => !c.services.includes('calendar')).length

  const porDia = useMemo(() => {
    const m = new Map<string, Ev[]>()
    for (const e of data || []) { const k = dayOf(e); m.set(k, [...(m.get(k) || []), e]) }
    return m
  }, [data])
  const dias = Array.from({ length: 42 }, (_, i) => addDays(inicio, i))
  const delDia = porDia.get(sel) || []
  const cap = (x: string) => x[0].toUpperCase() + x.slice(1)
  const titulo = cap(mes.toLocaleDateString('es', { month: 'long', year: 'numeric' }))
  const selTxt = cap(new Date(sel + 'T12:00').toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' }))

  // formulario de nuevo evento
  const [t, setT] = useState(''); const [ini, setIni] = useState('10:00'); const [fin, setFin] = useState('11:00')
  const [allDay, setAllDay] = useState(false); const [loc, setLoc] = useState(''); const [acc, setAcc] = useState('')
  const [busy, setBusy] = useState(false)
  async function crear() {
    setBusy(true)
    try {
      await post('/api/calendario', { action: 'add', title: t, date: sel, start: ini, end: fin, allDay, location: loc, account: acc || conCal[0] })
      toast('Evento creado en Google Calendar'); setForm(false); setT(''); setLoc(''); setAllDay(false); setIni('10:00'); setFin('11:00'); await reload()
    } catch (e) { toast(`No se pudo crear: ${(e as Error).message}`) } finally { setBusy(false) }
  }

  return <div className="extra-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">GOOGLE CALENDAR</span><h2>Calendario<span className="greeting-dot">.</span></h2><p>Tu mes de un vistazo.</p></div>

    <div className="cal-head"><h3>{titulo}</h3><div className="cal-nav">
      <button onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))} aria-label="Mes anterior"><Icon name="back" size={18} /></button>
      <button onClick={() => { const d = new Date(); setMes(new Date(d.getFullYear(), d.getMonth(), 1)); setSel(isoDay()) }} aria-label="Hoy"><Icon name="calendar" size={17} /></button>
      <button onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))} aria-label="Mes siguiente"><Icon name="chevron" size={18} /></button>
    </div></div>

    <div className="cal-grid" role="grid" aria-label={titulo}>
      {DOW.map(d => <span key={d} className="cal-dow">{d}</span>)}
      {dias.map(d => {
        const k = isoDay(d), n = (porDia.get(k) || []).length
        const cls = ['cal-day', d.getMonth() !== mes.getMonth() ? 'out' : '', k === isoDay() ? 'today' : '', k === sel ? 'sel' : ''].join(' ')
        return <button key={k} className={cls} onClick={() => setSel(k)} aria-label={`${d.getDate()}${n ? `, ${n} eventos` : ''}`} aria-pressed={k === sel}>
          {d.getDate()}<span className="cal-dots">{Array.from({ length: Math.min(n, 3) }, (_, i) => <i key={i} />)}</span></button>
      })}
    </div>

    <div className="section-heading extra-section-heading"><div><span className="section-kicker">{loading ? 'CARGANDO…' : error && !data ? 'SIN DATOS' : `${delDia.length} ${delDia.length === 1 ? 'EVENTO' : 'EVENTOS'}`}</span><h3>{selTxt}</h3></div>
      <button className="add-task-button" onClick={() => setForm(!form)} aria-label="Nuevo evento" disabled={!conCal.length}><Icon name={form ? 'close' : 'plus'} size={21} /></button></div>

    {form && <form className="ev-form" onSubmit={e => { e.preventDefault(); void crear() }}>
      <input autoFocus value={t} onChange={e => setT(e.target.value)} placeholder="¿Qué tienes?" aria-label="Título del evento" maxLength={200} />
      <div className="row"><input type="date" value={sel} onChange={e => e.target.value && setSel(e.target.value)} aria-label="Fecha" /></div>
      <label className="check"><input type="checkbox" checked={allDay} onChange={e => setAllDay(e.target.checked)} /> Todo el día</label>
      {!allDay && <div className="row"><input type="time" value={ini} onChange={e => setIni(e.target.value)} aria-label="Hora de inicio" /><input type="time" value={fin} onChange={e => setFin(e.target.value)} aria-label="Hora de fin" /></div>}
      <input value={loc} onChange={e => setLoc(e.target.value)} placeholder="Lugar (opcional)" aria-label="Lugar" maxLength={200} />
      {conCal.length > 1 && <select value={acc || conCal[0]} onChange={e => setAcc(e.target.value)} aria-label="Cuenta">{conCal.map(c => <option key={c} value={c}>{c}</option>)}</select>}
      <div className="actions"><button type="button" className="btn-secondary" onClick={() => setForm(false)}>Cancelar</button>
        <button className="btn-primary" disabled={!t.trim() || busy || (!allDay && fin <= ini)}><Icon name="check" size={17} /> Crear evento</button></div>
        {!allDay && fin <= ini && <small role="status" style={{ color: '#9a4b2c' }}>La hora de fin tiene que ser después de la de inicio.</small>}
    </form>}

    {error && <div className="fallo" role="alert"><span>No pude leer el calendario{data ? ': puede que falte algo' : ''}.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    <div className="ev-list">{delDia.map(e => <a className="ev" key={e.account + e.id} href={e.link || undefined} target="_blank" rel="noopener noreferrer">
      <time>{e.allDay ? 'Día' : hm(e.start)}</time>
      <span><strong>{e.title}</strong><small><span className="acc-tag">{e.tag}</span>{e.allDay ? 'Todo el día' : `${hm(e.start)}–${hm(e.end)}`}{e.location ? ` · ${e.location}` : ''}</small></span>
    </a>)}
      {!delDia.length && !loading && !(error && !data) && <div className="empty-radar">Día libre.</div>}
    </div>

    {sinCal > 0 && <button className="inline-link-card" onClick={() => go('cuentas')}><span className="inline-link-icon"><Icon name="shield" size={19} /></span>
      <span><strong>{guest ? 'Dale permiso de calendario' : 'Conecta tu otra cuenta'}</strong><small>{sinCal === 1 ? 'Una cuenta' : `${sinCal} cuentas`} sin permiso de calendario</small></span><Icon name="arrow" size={17} /></button>}
  </div>
}
