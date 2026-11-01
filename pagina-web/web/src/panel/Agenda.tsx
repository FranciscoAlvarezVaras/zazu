/* Agenda: tu calendario, como el del móvil. Arriba la tira de la semana (toca un día), debajo ese día hora a hora con las citas
   como bloques (las de todo el día, como pastillas) y la hora actual marcada; encima, las tareas de ese día con su casilla.
   La barra de abajo (la pone el marco) es para decirle a Zazu qué apuntar: «mañana dentista a las 10», «apunta: …», «recuérdame…».
   «Planificar»: Zazu reparte las tareas pendientes en los huecos libres y lo apunta cuando das el OK.
   ?vista=tareas y ?vista=notas: la lista completa de tareas y tus notas del Cerebro; ?vista=hoy: el resumen del día de antes. */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Ctx } from '../ctx'
import { Icon } from '../icons'
import { AVISO_CAMBIO, hm, irA, isoDay, post, puede, useFetch, useParams } from '../lib'
import type { Ev, Task } from '../lib'
import Tareas from '../screens/Tareas'
import { PLANIFICA_DIA } from './acciones'
import Hoy from './Hoy'
import ResumenHoy from './ResumenHoy'
import { Icono } from './ui'
import { TarjetaAgendaChats } from '../screens/AgendaChats'

const PX_H = 56   // 56 px por hora; la línea de horas va de 7:00 a 22:00 y se ensancha si ese día hay algo antes o después
const FIN_DIA = 24 * 60
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const deIso = (k: string) => new Date(`${k}T12:00:00`)
const lunesDe = (k: string) => { const d = deIso(k); return addDays(d, -((d.getDay() + 6) % 7)) }
const cap = (s: string) => s[0].toUpperCase() + s.slice(1)
const mins = (d: Date) => d.getHours() * 60 + d.getMinutes()
type Seg = { e: Ev; a: number; b: number }   // el trozo de un evento que cae en un día, en minutos desde las 0:00

/** Los días que toca un evento y el trozo de cada uno. Uno de todo el día que dura varios sale en todos (el fin de Google es exclusivo);
 *  uno con hora que cruza la medianoche, en los dos días. Antes salía solo el día en que empezaba. */
function trozos(e: Ev): [string, Seg][] {
  const out: [string, Seg][] = []
  if (e.allDay) {
    const ini = (e.start || '').slice(0, 10), fin = (e.end || '').slice(0, 10)
    for (let k = ini, n = 0; k && n < 31 && (n === 0 || k < fin); n++, k = isoDay(addDays(deIso(k), 1))) out.push([k, { e, a: 0, b: FIN_DIA }])
    return out
  }
  const s = new Date(e.start || 0), f = e.end ? new Date(e.end) : s
  const d0 = isoDay(s), d1 = isoDay(f)
  if (d1 <= d0 || f <= s) return [[d0, { e, a: mins(s), b: f > s ? mins(f) : mins(s) + 60 }]]
  for (let k = d0, n = 0; k <= d1 && n < 7; n++, k = isoDay(addDays(deIso(k), 1))) {
    const a = k === d0 ? mins(s) : 0, b = k === d1 ? mins(f) : FIN_DIA
    if (b > a) out.push([k, { e, a, b }])
  }
  return out
}
const DOW = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

export default function Agenda(ctx: Ctx) {
  const params = useParams()
  const vista = params.vista
  const conNotas = puede(ctx.me, 'tableros')
  if (vista === 'hoy') return <div className="pz-agenda"><Volver /><Hoy {...ctx} /></div>
  if (vista === 'tareas') return <div className="pz-agenda"><Volver /><div className="pz-legado pz-agenda-legado"><div className="content-wrap"><Tareas {...ctx} /></div></div></div>
  if (vista === 'notas' && conNotas) return <div className="pz-agenda"><Volver /><Notas {...ctx} /></div>
  return <Calendario {...ctx} />
}

function Volver() {
  return <button type="button" className="pz-enlace ag-volver" onClick={() => irA({ tab: 'inicio' }, true)}><Icon name="back" size={16} /> Agenda</button>
}

/** La tira de la semana y el día hora a hora. */
function Calendario(ctx: Ctx) {
  const { toast, ask, me } = ctx
  // la hora actual, en marcha (y «hoy» con ella: pasada la medianoche, el día que estabas mirando pasa al nuevo)
  const [ahora, setAhora] = useState(() => new Date())
  const hoy = isoDay(ahora)
  const [sel, setSel] = useState(hoy)
  const hoyAntes = useRef(hoy)
  useEffect(() => {
    const t = setInterval(() => setAhora(new Date()), 60000)
    const volver = () => { if (!document.hidden) setAhora(new Date()) }
    document.addEventListener('visibilitychange', volver)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', volver) }
  }, [])
  useEffect(() => { const antes = hoyAntes.current; hoyAntes.current = hoy; if (antes !== hoy) setSel(s => s === antes ? hoy : s) }, [hoy])
  const lunes = useMemo(() => lunesDe(sel), [sel])
  const desde = isoDay(addDays(lunes, -7))
  const ev = useFetch<Ev[]>(`/api/calendario?desde=${desde}&dias=21`, 300000)
  const ta = useFetch<Task[]>('/api/tareas', 300000)
  // lo que apuntas en la barra o completas en otro sitio: se vuelve a pedir (antes la agenda no se enteraba hasta recargar)
  useEffect(() => {
    const otra = () => { void ev.reload(); void ta.reload() }
    const alVolver = () => { if (!document.hidden) otra() }
    window.addEventListener(AVISO_CAMBIO, otra); document.addEventListener('visibilitychange', alVolver)
    return () => { window.removeEventListener(AVISO_CAMBIO, otra); document.removeEventListener('visibilitychange', alVolver) }
  }, [ev.reload, ta.reload]) // eslint-disable-line react-hooks/exhaustive-deps
  const [hechas, setHechas] = useState<string[]>([])
  const [ocupada, setOcupada] = useState('')
  const semana = Array.from({ length: 7 }, (_, i) => isoDay(addDays(lunes, i)))
  const porDia = useMemo(() => { const m = new Map<string, Seg[]>(); for (const e of ev.data || []) for (const [k, sg] of trozos(e)) m.set(k, [...(m.get(k) || []), sg]); return m }, [ev.data])
  const tareas = (ta.data || []).filter(t => !t.done && !hechas.includes(t.id))
  const delDia = porDia.get(sel) || []
  const todoDia = delDia.filter(x => x.e.allDay), conHora = delDia.filter(x => !x.e.allDay).sort((x, y) => x.a - y.a || y.b - x.b)
  // la línea de horas: de 7:00 a 22:00, y más si ese día hay algo antes o después (antes se escondía lo de las 22:30)
  const h0 = Math.min(7, ...conHora.map(x => Math.floor(x.a / 60))), h1 = Math.max(22, ...conHora.map(x => Math.ceil(x.b / 60)))
  const tareasDia = tareas.filter(t => t.due === sel)
  const esHoy = sel === hoy
  const titulo = cap(deIso(sel).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' }))
  const mes = cap(lunes.toLocaleDateString('es', { month: 'long', year: 'numeric' }))

  async function hecha(t: Task) {
    setOcupada(t.id)
    try { await post('/api/tareas', { action: 'done', id: t.id, account: t.account }); setHechas(h => [...h, t.id]); toast('Tarea completada') }
    catch (e) { toast(`No se pudo completar: ${(e as Error).message}`) } finally { setOcupada('') }
  }

  // el día de hoy empieza enseñando la mañana (no las 7:00)
  const lineas = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = lineas.current; if (!el) return
    const h = esHoy ? Math.max(h0, ahora.getHours() - 1) : conHora.length ? Math.max(h0, conHora[0].a / 60 - 1) : Math.max(h0, 9)
    const ir = () => el.scrollTo({ top: (h - h0) * PX_H })
    ir(); const r = requestAnimationFrame(ir); const t = setTimeout(ir, 350)   // por si la caja aún no tenía su alto
    return () => { cancelAnimationFrame(r); clearTimeout(t) }
  }, [sel, ev.data, ta.data, h0]) // eslint-disable-line react-hooks/exhaustive-deps

  // bloques: posición por hora; los que se solapan se reparten en columnas
  const bloques = useMemo(() => {
    const bs = conHora.map(({ e, a, b }) => ({ e, a, b: Math.min(Math.max(a + 25, b), Math.max(h1 * 60, a + 25)), col: 0, cols: 1 }))
    const grupo: typeof bs = []
    const cerrar = () => { grupo.forEach(x => { x.cols = Math.max(...grupo.map(g => g.col)) + 1 }); grupo.length = 0 }
    let fin = -1
    for (const x of bs) {
      if (grupo.length && x.a >= fin) cerrar()
      const usadas = new Set(grupo.filter(g => g.b > x.a).map(g => g.col))
      let c = 0; while (usadas.has(c)) c++
      x.col = c; grupo.push(x); fin = Math.max(fin, x.b)
    }
    cerrar()
    return bs
  }, [conHora, h1])

  const minAhora = ahora.getHours() * 60 + ahora.getMinutes()
  const sinGoogle = ctx.guest && !puede(ctx.me, 'calendario') && ctx.me.nivel !== 'invitada' && !ctx.me.demo
  // Fran sin ninguna cuenta de Google que funcione (p. ej. tras reiniciar con --google): la agenda saldría vacía sin pista
  const gFran = useFetch<{ google: { email: string; error?: boolean }[]; google_web?: boolean }>(ctx.me.role === 'admin' && !ctx.me.demo ? '/api/cuentas' : null)
  const franSinGoogle = !!gFran.data && !gFran.data.google.some(x => !x.error)
  return <div className="pz-page pz-agenda ag">
    {sinGoogle && <div className="acc-card" style={{ margin: '12px 16px' }}>
      <strong>📅 Conecta tu Gmail y tu agenda se llena sola</strong>
      <small>Verás aquí tus citas y tareas de Google, {ctx.nombre || 'Zazu'} te las recordará y con «Organizar mi agenda» te propondrá cómo repartir tu semana. Solo lee: antes de apuntarte nada, te pide permiso en el móvil.</small>
      <div className="actions"><button type="button" className="btn-primary" onClick={() => { location.href = '/oauth/google/start?mode=connect' }}>Conectar mi Gmail (1 minuto)</button></div></div>}
    {franSinGoogle && <div className="acc-card" style={{ margin: '12px 16px' }}>
      <strong>📅 Conecta tu Google y tu agenda se llena sola</strong>
      <small>{gFran.data!.google.length ? 'Tu Google necesita volver a conectarse: ahora Zazu no ve tus citas ni tus tareas.' : 'Ahora no hay ninguna cuenta de Google conectada: Zazu no ve tus citas, tus tareas ni tu correo.'}</small>
      <div className="actions">{gFran.data!.google_web
        ? <button type="button" className="btn-primary" onClick={() => { location.href = '/oauth/google/start?mode=connect' }}>Conectar mi Google</button>
        : <button type="button" className="btn-primary" onClick={() => ctx.go('cuentas')}>Abrir Tus cuentas</button>}</div></div>}
    {ctx.guest && !ctx.me.demo && <TarjetaAgendaChats nombre={ctx.nombre} />}
    {ctx.me.role === 'admin' && <TarjetaAgendaChats fran />}
    <div className="ag-cab">
      <div className="ag-mes"><strong>{mes}</strong>{!esHoy && <button type="button" className="pz-enlace" onClick={() => setSel(hoy)}>Hoy</button>}</div>
      <div className="ag-acc">
        <button type="button" className="ag-btn" onClick={() => setSel(isoDay(addDays(lunes, -7)))} aria-label="Semana anterior"><Icon name="back" size={18} /></button>
        <button type="button" className="ag-btn" onClick={() => setSel(isoDay(addDays(lunes, 7)))} aria-label="Semana siguiente"><Icon name="chevron" size={18} /></button>
        {puede(me, 'tableros') && <button type="button" className="ag-btn" onClick={() => irA({ tab: 'inicio', vista: 'notas' })} aria-label="Notas" title="Notas"><Icono n="pen" size={20} /></button>}
      </div>
    </div>
    <div className="ag-semana" role="group" aria-label="Días de la semana">
      {semana.map((k, i) => {
        const n = (porDia.get(k) || []).length + tareas.filter(t => t.due === k).length   // lo mismo que se dibuja ese día
        return <button key={k} type="button" className={`ag-dia ${k === sel ? 'sel' : ''} ${k === hoy ? 'hoy' : ''}`} onClick={() => setSel(k)} aria-pressed={k === sel} aria-label={`${cap(deIso(k).toLocaleDateString('es', { weekday: 'long', day: 'numeric' }))}${n ? `, ${n} cosas` : ''}`}>
          <small>{DOW[i]}</small><b>{Number(k.slice(8, 10))}</b><i className={n ? 'con' : ''} aria-hidden="true" />
        </button>
      })}
    </div>
    {esHoy && me.role === 'admin' && <ResumenHoy toast={toast} />}
    <h2 className="ag-titulo">{esHoy ? 'Hoy' : sel === isoDay(addDays(new Date(), 1)) ? 'Mañana' : ''}{esHoy || sel === isoDay(addDays(new Date(), 1)) ? ' · ' : ''}{titulo}</h2>
    {ev.error && <p className="pz-nota" role="alert">{ev.data ? 'No pude actualizar el calendario: lo que ves puede estar desfasado.' : 'No pude leer el calendario.'} <button type="button" className="pz-enlace" onClick={() => void ev.reload()}>Reintentar</button></p>}
    {ta.error && <p className="pz-nota" role="alert">{ta.data ? 'No pude actualizar tus tareas.' : 'No pude leer tus tareas.'} <button type="button" className="pz-enlace" onClick={() => void ta.reload()}>Reintentar</button></p>}

    {tareasDia.length > 0 && <section className="ag-tareas" aria-label="Tareas del día">
      {tareasDia.slice(0, 3).map(t => <div key={t.id} className="ag-tarea">
        <button type="button" className="pz-casilla" disabled={ocupada === t.id} onClick={() => void hecha(t)} aria-label={`Marcar hecha: ${t.title}`}><span /></button>
        {t.link ? <a href={t.link} target="_blank" rel="noopener noreferrer" title={`${t.title} · abrir en Google Tasks`}>{t.title}</a> : <span title={t.title}>{t.title}</span>}
      </div>)}
      {tareasDia.length > 3 && <span className="ag-mas">y {tareasDia.length - 3} más</span>}
      <div className="ag-pills">
        {esHoy && puede(me, 'tableros') && tareasDia.length > 0 && <button type="button" className="ag-planificar" onClick={() => ask(PLANIFICA_DIA)}><Icono n="spark" size={16} /> Planifícame el día</button>}
      </div>
    </section>}

    {todoDia.length > 0 && <div className="ag-tododia">{todoDia.map(({ e }) => <a key={e.account + e.id} className="ag-pastilla" href={e.link || undefined} target="_blank" rel="noopener noreferrer">{e.title}</a>)}</div>}

    <div className="ag-lineas" ref={lineas}>
      <div className="ag-horas" style={{ height: (h1 - h0) * PX_H }}>
        {Array.from({ length: h1 - h0 }, (_, i) => <div key={i} className="ag-hora" style={{ top: i * PX_H }}><span>{String(h0 + i).padStart(2, '0')}:00</span></div>)}
        {esHoy && minAhora >= h0 * 60 && minAhora <= h1 * 60 && <div className="ag-ahora" style={{ top: (minAhora - h0 * 60) * PX_H / 60 }}><i /><span>{hm(ahora)}</span></div>}
        {bloques.map(({ e, a, b, col, cols }) => {
          const zazu = e.title.startsWith('⏱')
          const estilo = { top: (a - h0 * 60) * PX_H / 60, height: Math.max(26, (b - a) * PX_H / 60 - 2), left: `calc(56px + ${col} * (100% - 64px) / ${cols})`, width: `calc((100% - 64px) / ${cols} - 4px)` }
          return <a key={e.account + e.id} className={`ag-bloque ${zazu ? 'zazu' : ''} ${b - a < 45 ? 'corto' : ''}`} style={estilo} href={e.link || undefined} target="_blank" rel="noopener noreferrer" title={`${e.title} · ${hm(e.start)}–${hm(e.end)}`}>
            <strong>{e.title}</strong><span>{hm(e.start)}–{hm(e.end)}{e.location ? ` · ${e.location}` : ''}</span>
          </a>
        })}
        {!conHora.length && !ev.loading && <p className="ag-libre">{todoDia.length || tareasDia.length ? 'Sin citas con hora.' : 'Día libre.'}</p>}
      </div>
    </div>
  </div>
}

type Archivo = { name: string; path: string; dir: boolean; mtime: number; inline: boolean }
const tituloNota = (n: string) => n.replace(/\.md$/, '').replace(/^\d{4}-\d{2}-\d{2}\s+/, '')
const sinCabecera = (t: string) => t.replace(/^---\n[\s\S]*?\n---\n?/, '').trim()

/** Tus notas del Cerebro: la Bandeja (lo que apuntas al vuelo) y las Ideas. Tocar una la abre; «+ Nota» apunta otra (como «Apunta: …» en la barra). */
function Notas(ctx: Ctx) {
  const { toast } = ctx
  const bandeja = useFetch<{ items: Archivo[] }>('/api/files?root=notas&path=10%20Bandeja')
  const ideas = useFetch<{ items: Archivo[] }>('/api/files?root=notas&path=30%20Notas%2FIdeas')
  const [abierta, setAbierta] = useState<string | null>(null)
  const [texto, setTexto] = useState<Record<string, string>>({})
  const [nueva, setNueva] = useState(false)
  const [borrador, setBorrador] = useState('')
  const [ocupado, setOcupado] = useState(false)
  useEffect(() => {
    if (!abierta || texto[abierta] !== undefined) return
    let vivo = true
    fetch(`/api/download?root=notas&path=${encodeURIComponent(abierta)}&inline=1`, { headers: { 'X-Hub': '1' } }).then(r => r.ok ? r.text() : Promise.reject(new Error(String(r.status))))
      .then(t => { if (vivo) setTexto(x => ({ ...x, [abierta]: sinCabecera(t) })) })
      .catch(() => { if (vivo) setTexto(x => ({ ...x, [abierta]: 'No pude leer la nota.' })) })
    return () => { vivo = false }
  }, [abierta]) // eslint-disable-line react-hooks/exhaustive-deps
  async function apuntar() {
    const t = borrador.trim(); if (!t) return
    setOcupado(true)
    try { await post('/api/nota', { texto: t }); setBorrador(''); setNueva(false); toast('Apuntado en tu Cerebro'); await bandeja.reload() }
    catch (e) { toast(`No se pudo apuntar: ${(e as Error).message}`) } finally { setOcupado(false) }
  }
  const lista = (titulo: string, f: typeof bandeja, vacio: string) => <section className="pz-tarjeta-g pz-notas-grupo" aria-label={titulo}>
    <h2>{titulo}{f.data && <small>{f.data.items.filter(i => !i.dir).length}</small>}</h2>
    {f.error && !f.data && <p className="pz-nota">No pude leer estas notas.</p>}
    {!f.data && !f.error && <p className="pz-sem-libre">Cargando…</p>}
    {f.data && !f.data.items.some(i => !i.dir) && <p className="pz-sem-libre">{vacio}</p>}
    <ul>{(f.data?.items || []).filter(i => !i.dir).sort((a, b) => b.mtime - a.mtime).slice(0, 30).map(i => <li key={i.path} className={`pz-nota-fila ${abierta === i.path ? 'abierta' : ''}`}>
      <button type="button" onClick={() => setAbierta(abierta === i.path ? null : i.path)} aria-expanded={abierta === i.path}>
        <span className="pz-nota-ico" aria-hidden="true"><Icono n="file" size={16} /></span>
        <span className="pz-imp-txt"><strong>{tituloNota(i.name)}</strong><span>{new Date(i.mtime * 1000).toLocaleDateString('es', { day: 'numeric', month: 'short' })}</span></span>
      </button>
      {abierta === i.path && <pre className="pz-nota-txt">{texto[i.path] ?? 'Cargando…'}</pre>}
    </li>)}</ul>
  </section>
  return <div className="pz-page pz-notas">
    <div className="pz-notas-cab">
      <p>Lo que apuntas al vuelo va a la Bandeja; el domingo Zazu lo ordena en tu Cerebro.</p>
      <button type="button" className="pz-btn pz-btn-primario" onClick={() => setNueva(!nueva)} aria-expanded={nueva}><Icono n="plus" size={18} /> Nota</button>
    </div>
    {nueva && <form className="pz-nota-nueva" onSubmit={e => { e.preventDefault(); void apuntar() }}>
      <textarea autoFocus value={borrador} onChange={e => setBorrador(e.target.value)} placeholder="¿Qué apunto?" aria-label="Nota nueva" rows={3} maxLength={2000} />
      <div className="pz-hoja-acc"><button type="button" className="pz-btn pz-btn-texto" onClick={() => { setNueva(false); setBorrador('') }}>Cancelar</button>
        <button type="submit" className="pz-btn pz-btn-primario" disabled={!borrador.trim() || ocupado}>Apuntar</button></div>
    </form>}
    {lista('Bandeja', bandeja, 'Nada pendiente de ordenar.')}
    {lista('Ideas', ideas, 'Sin ideas apuntadas todavía.')}
  </div>
}
