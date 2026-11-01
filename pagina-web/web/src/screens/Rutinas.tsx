import { useState } from 'react'
import { Icon } from '../icons'
import { isoDay, post, useFetch } from '../lib'
import type { Job } from '../lib'
import type { Ctx } from '../ctx'

/** GET /api/cron: además de lo de siempre, el horario en español («cuando»), la última vez («ultimo»: {fecha, estado, texto}),
 *  adónde llega («destino», ya en español), qué hace («prompt») y, si va a hora fija, hora y días («editable»). */
type Rutina = Job & { cuando?: string; ultimo?: unknown; destino?: string; prompt?: string; editable?: boolean; hora?: string | null; dias?: number[] | null }

const pad = (n: number) => String(n).padStart(2, '0')
/** Botones L…D → día del cron (0 = domingo). */
const DIAS: [string, number, string][] = [['L', 1, 'lunes'], ['M', 2, 'martes'], ['X', 3, 'miércoles'], ['J', 4, 'jueves'], ['V', 5, 'viernes'], ['S', 6, 'sábados'], ['D', 0, 'domingos']]
const TODOS = DIAS.map(d => d[1])
const ESTADO: Record<string, string> = { ok: 'salió bien', success: 'salió bien', error: 'falló', failed: 'falló', skipped: 'no hizo falta', timeout: 'tardó demasiado' }
// los nombres de las rutinas se escribieron sin tildes: se muestran bien
const TILDES: Record<string, string> = { manana: 'mañana', mananas: 'mañanas', revision: 'revisión', vigia: 'vigía', dia: 'día', dias: 'días', informacion: 'información', analisis: 'análisis', sesion: 'sesión', reunion: 'reunión', ultimo: 'último', ultimas: 'últimas', proximo: 'próximo', proxima: 'próxima' }
const IDEAS: [string, string][] = [
  ['Noticias del día', 'Mándame las 3 noticias más importantes de España de hoy, en pocas líneas y con la fuente.'],
  ['El tiempo de mañana', 'Dime qué tiempo hará mañana donde vivo y si necesito paraguas o abrigo.'],
  ['Plan de la semana', 'Mira mi agenda y mis tareas de esta semana y dime en 5 puntos qué es lo más importante.'],
]

function bonito(s?: string | null) {
  const t = (s || 'Rutina').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/\p{L}+/gu, w => { const a = TILDES[w.toLowerCase()]; return !a ? w : w[0] === w[0].toUpperCase() ? a[0].toUpperCase() + a.slice(1) : a })
  return t[0].toUpperCase() + t.slice(1)
}

/** «hoy a las 07:30», «mañana a las 21:00», «lun, 12 oct a las 07:30». Lo que no es fecha se deja tal cual. */
function fecha(v: unknown) {
  if (v === null || v === undefined || v === '') return ''
  const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(String(v))
  if (isNaN(d.getTime())) return String(v)
  const n = Math.round((new Date(isoDay(d)).getTime() - new Date(isoDay()).getTime()) / 864e5)
  const dia = n === 0 ? 'hoy' : n === -1 ? 'ayer' : n === 1 ? 'mañana' : d.toLocaleDateString('es', { weekday: 'short', day: 'numeric', month: 'short' })
  return `${dia} a las ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Lo que dijo la rutina la última vez (el servidor lo da cortado a 160 letras): sin la palabra a medias. */
function dijo(j: Rutina) {
  const u = j.ultimo, o = u && typeof u === 'object' ? u as Record<string, unknown> : null
  const t = typeof u === 'string' ? u : typeof o?.texto === 'string' ? o.texto : typeof o?.resultado === 'string' ? o.resultado : ''
  return t.trim().replace(/\s+\S*…$/, '…').replace(/([.!?])…$/, '$1')
}
/** «Última vez: hoy a las 07:30 · salió bien»: fecha y estado; una frase corta («Sin novedades») sí cabe; lo largo va en «Qué dijo». */
function ultimo(j: Rutina) {
  const u = j.ultimo, o = u && typeof u === 'object' ? u as Record<string, unknown> : null
  const t = dijo(j), corto = t && t.length <= 40 && !t.endsWith('…') ? t[0].toLowerCase() + t.slice(1) : ''   // «sin novedades»
  if (o) {
    const e = String(o.estado ?? o.status ?? '')
    const txt = [fecha(o.cuando ?? o.fecha ?? o.hora ?? o.ts), corto || ESTADO[e] || (/error|fail/i.test(e) ? 'falló' : '')].filter(Boolean).join(' · ')
    if (txt) return txt
  }
  if (corto && !j.last) return corto
  return j.last ? `${fecha(j.last)}${j.status ? ` · ${ESTADO[j.status] || 'hecha'}` : ''}` : 'Aún no se ha hecho nunca'
}

/** «Te llega: tu WhatsApp», «Te llega: en la app»… (el servidor ya lo da en español; por si llega en crudo, se traduce). */
function destino(d?: string) {
  if (!d) return ''
  const t = /^whatsapp(:|$)/.test(d) ? 'tu WhatsApp' : /^telegram(:|$)/.test(d) ? 'Telegram' : d === 'local' ? 'en la app' : d === 'origin' ? 'donde la pediste'
    : /^(En|Donde|Tu|Tus|Un|Una|Otro|Otra|El|La|Los|Las)\s/.test(d) ? d[0].toLowerCase() + d.slice(1) : d   // «Telegram» se queda con mayúscula
  return `Te llega: ${t}`
}

/** Hora y días de una rutina que va a hora fija («M H * * D»); null si es otra cosa (una vez, cada 15 min, varias veces
 *  al día, una vez al mes…): esas no se cambian aquí, porque pasarían a hacerse todos los días a esa hora. */
function horario(j: Rutina): { hora: string; dias: number[] } | null {
  if (j.editable === false) return null
  if (j.hora && j.dias?.length) return { hora: j.hora, dias: j.dias }   // el servidor ya lo da
  if (j.editable !== undefined) return null
  const m = /^(\d{1,2}) (\d{1,2}) \* \* (\S+)$/.exec((j.when || '').trim())   // servidor antiguo: se lee del cron
  if (!m) return null
  const dias = m[3] === '*' ? TODOS : m[3].split(',').flatMap(p => {
    const [a, b] = p.split('-').map(Number)
    return isNaN(b) ? [a % 7] : Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => (a + i) % 7)
  }).filter(n => !isNaN(n))
  return dias.length ? { hora: `${pad(+m[2])}:${pad(+m[1])}`, dias: [...new Set(dias)] } : null
}

function resumenDias(d: number[]) {
  const s = [...new Set(d)].sort((a, b) => ((a + 6) % 7) - ((b + 6) % 7))   // lunes primero
  if (s.length === 7) return 'Todos los días'
  if (s.join() === '1,2,3,4,5') return 'De lunes a viernes'
  if (s.join() === '6,0') return 'Sábados y domingos'
  const n = s.map(x => DIAS.find(y => y[1] === x)![2])
  const t = n.length > 1 ? `${n.slice(0, -1).join(', ')} y ${n[n.length - 1]}` : n[0] || ''
  return t ? t[0].toUpperCase() + t.slice(1) : ''
}
const diasApi = (d: number[]) => d.length === 7 ? 'todos' : [...new Set(d)].sort()

/** Hora + días (L M X J V S D) con atajos. */
function Cuando({ hora, dias, setHora, setDias }: { hora: string; dias: number[]; setHora: (h: string) => void; setDias: (d: number[]) => void }) {
  return <>
    <label>¿A qué hora?<input type="time" value={hora} onChange={e => setHora(e.target.value)} required /></label>
    <div className="rut-campo"><span>¿Qué días?</span>
      <div className="rut-dias" role="group" aria-label="Días de la semana">{DIAS.map(([l, n, nombre]) => {
        const on = dias.includes(n)
        return <button key={n} type="button" className={on ? 'on' : ''} aria-pressed={on} aria-label={nombre} onClick={() => setDias(on ? dias.filter(x => x !== n) : [...dias, n])}>{l}</button>
      })}</div>
      <div className="rut-atajos"><button type="button" onClick={() => setDias(TODOS)}>Todos</button><button type="button" onClick={() => setDias([1, 2, 3, 4, 5])}>Lunes a viernes</button><button type="button" onClick={() => setDias([6, 0])}>Fin de semana</button></div>
    </div>
    <small className="rut-resumen" role="status">{dias.length && hora ? `Se hará: ${resumenDias(dias)} a las ${hora}` : 'Elige al menos un día.'}</small>
  </>
}

type Act = (body: Record<string, unknown>, ok: string, clave: string) => Promise<boolean>

function Nueva({ act, busy, cerrar }: { act: Act; busy: boolean; cerrar: () => void }) {
  const [nombre, setNombre] = useState(''); const [prompt, setPrompt] = useState('')
  const [hora, setHora] = useState('08:00'); const [dias, setDias] = useState<number[]>(TODOS)
  const ok = nombre.trim() && prompt.trim() && dias.length && /^\d\d:\d\d$/.test(hora)
  return <form className="ev-form rut-form" onSubmit={e => { e.preventDefault(); if (ok) void act({ action: 'crear', nombre: nombre.trim(), prompt: prompt.trim(), hora, dias: diasApi(dias) }, 'Rutina creada', 'nueva').then(b => b && cerrar()) }}>
    <strong className="rut-titulo">Nueva rutina</strong>
    <div className="rut-campo"><span>Ideas para empezar</span><div className="rut-atajos">{IDEAS.map(([n, p]) => <button key={n} type="button" onClick={() => { setNombre(n); setPrompt(p) }}>{n}</button>)}</div></div>
    <label>Nombre<input autoFocus value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej.: Noticias del día" maxLength={60} /></label>
    <label>¿Qué tiene que hacer Zazu?<textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} maxLength={1000} placeholder="Ej.: Mándame las 3 noticias más importantes de hoy en pocas líneas." /></label>
    <Cuando hora={hora} dias={dias} setHora={setHora} setDias={setDias} />
    <small className="rut-nota">Lo verás en la app.</small>
    <div className="actions"><button type="button" className="btn-secondary" onClick={cerrar}>Cancelar</button>
      <button className="btn-primary" disabled={!ok || busy}><Icon name="check" size={17} /> {busy ? 'Creando…' : 'Crear rutina'}</button></div>
  </form>
}

function CambiarHora({ j, h, act, busy, cerrar }: { j: Rutina; h: { hora: string; dias: number[] }; act: Act; busy: boolean; cerrar: () => void }) {
  const [hora, setHora] = useState(h.hora); const [dias, setDias] = useState<number[]>(h.dias)
  return <form className="ev-form rut-form rut-editar" onSubmit={e => { e.preventDefault(); if (dias.length && hora) void act({ action: 'cambiar_hora', id: j.id, hora, dias: diasApi(dias) }, 'Horario cambiado', j.id).then(b => b && cerrar()) }}>
    <Cuando hora={hora} dias={dias} setHora={setHora} setDias={setDias} />
    <div className="actions"><button type="button" className="btn-secondary" onClick={cerrar}>Cancelar</button>
      <button className="btn-primary" disabled={!dias.length || !hora || busy}><Icon name="check" size={17} /> Guardar</button></div>
  </form>
}

export default function Rutinas({ toast, ask }: Ctx) {
  const { data, loading, error, reload } = useFetch<Rutina[] | { items: Rutina[] }>('/api/cron')
  const jobs = Array.isArray(data) ? data : data?.items || []
  const [busy, setBusy] = useState('')            // rutina (o 'nueva') con una acción en marcha
  const [editar, setEditar] = useState<string | null>(null)
  const [nueva, setNueva] = useState(false)

  const act: Act = async (body, ok, clave) => {
    setBusy(clave)
    try { await post('/api/cron', body); toast(ok); await reload(); return true }
    catch (e) { toast((e as Error).message); return false } finally { setBusy('') }
  }
  const hacer = (j: Rutina) => { if (confirm(`¿Quieres que Zazu haga «${bonito(j.name)}» ahora?`)) void act({ id: j.id, action: 'run' }, 'Zazu se pone con ello en un momento', j.id) }
  const borrar = (j: Rutina) => { if (confirm(`¿Borrar la rutina «${bonito(j.name)}»? Zazu dejará de hacerla.`)) void act({ id: j.id, action: 'borrar' }, 'Rutina borrada', j.id) }
  const pedirCambio = (j: Rutina) => ask(`Quiero cambiar cuándo se hace la rutina «${bonito(j.name)}»${j.cuando ? ` (ahora: ${j.cuando})` : ''}. Que pase a `, { fill: true })

  return <div className="extra-screen screen-enter rut">
    <div className="screen-heading"><span className="section-kicker">ZAZU TRABAJA SOLO</span><h2>Rutinas<span className="greeting-dot">.</span></h2><p>Lo que Zazu hace sin que se lo pidas.</p></div>
    {error && <div className="fallo" role="alert"><span>No pude leer tus rutinas.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    <div className="job-list">{jobs.map(j => {
      const mal = !!(j.last || j.ultimo) && /error|fail|fall/i.test(String(j.status || (j.ultimo as { estado?: string } | null)?.estado || '')), dest = destino(j.destino), b = busy === j.id
      const h = horario(j), dicho = dijo(j)
      return <div className="job-card" key={j.id}>
        <div className="job-top"><strong>{bonito(j.name)}</strong><span className={`count-pill ${j.enabled ? '' : 'off'}`}>{j.enabled ? 'Activa' : 'En pausa'}</span></div>
        <span className="rut-cuando"><Icon name="clock" size={15} /> {j.cuando || j.when}</span>
        {j.enabled && j.next && <small>Próxima vez: {fecha(j.next)}</small>}
        {dest && <small>{dest}</small>}
        <small className={`rut-ultimo ${mal ? 'rut-mal' : ''}`}>Última vez: {ultimo(j)}</small>
        {j.prompt && <details className="rut-prompt"><summary>Qué hace</summary><p>{j.prompt}</p></details>}
        {dicho.length > 40 && <details className="rut-prompt"><summary>Qué dijo la última vez</summary><p>{dicho}</p></details>}
        <div className="job-actions">
          <button disabled={!!busy} onClick={() => hacer(j)}><Icon name="play" size={14} /> Hacer ahora</button>
          <button disabled={!!busy} onClick={() => void act({ id: j.id, action: j.enabled ? 'pause' : 'resume' }, j.enabled ? 'Rutina en pausa' : 'Rutina activada', j.id)}><Icon name={j.enabled ? 'pause' : 'play'} size={14} /> {j.enabled ? 'Pausar' : 'Reanudar'}</button>
          {h ? <button disabled={!!busy} aria-expanded={editar === j.id} onClick={() => setEditar(editar === j.id ? null : j.id)}><Icon name="clock" size={14} /> Cambiar hora</button>
            : <button onClick={() => pedirCambio(j)}><Icon name="chat" size={14} /> Pedírselo a Zazu</button>}
          <button className="rut-borrar" disabled={!!busy} onClick={() => borrar(j)}><Icon name="close" size={14} /> Borrar</button>
        </div>
        {!h && <small className="rut-nota">No va a una hora fija. Para cambiarla, pídeselo a Zazu.</small>}
        {b && <small role="status">Un momento…</small>}
        {editar === j.id && h && <CambiarHora j={j} h={h} act={act} busy={b} cerrar={() => setEditar(null)} />}
      </div>
    })}
      {loading && !data && <div className="empty-radar">Cargando…</div>}
      {!loading && !error && !jobs.length && <div className="empty-radar">Aún no tienes rutinas. Crea la primera aquí abajo.</div>}
    </div>
    {nueva ? <Nueva act={act} busy={busy === 'nueva'} cerrar={() => setNueva(false)} />
      : <button className="btn-secondary rut-nueva" onClick={() => setNueva(true)}><Icon name="plus" size={17} /> Nueva rutina</button>}
  </div>
}
