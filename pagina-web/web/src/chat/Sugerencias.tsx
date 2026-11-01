import { Icon } from '../icons'
import { SUGERENCIAS, SUGERENCIAS_INVITADA } from '../data'
import type { Sugerencia } from '../data'
import { isoDay, relTime, useFetch } from '../lib'
import type { Ev, Session, Task } from '../lib'
import type { Me } from '../screens/Invitada'
import { tituloSesion } from '../screens/Sessions'
import { Icono } from '../panel/ui'
import type { Ico } from '../panel/ui'

type P = { guest?: boolean; me: Me; sessions: Session[]
  enviar(prompt: string, ctx?: string): void; rellenar(prompt: string): void; abrir(s: Session): void }

/** «3 en agenda · 2 tareas hoy» para la primera tarjeta (lo mismo que contaba el antiguo Inicio). */
function useCuentasHoy(activo: boolean): string | null {
  const agenda = useFetch<Ev[]>(activo ? '/api/agenda' : null)
  const tareas = useFetch<Task[]>(activo ? '/api/tareas' : null)
  if (!agenda.data || !tareas.data) return null
  const ev = agenda.data.filter(e => e.day === 'hoy').length
  const t = tareas.data.filter(x => !x.done && x.due && x.due <= isoDay()).length
  if (!ev && !t) return 'Nada en agenda ni tareas para hoy'
  return `${ev} en agenda · ${t} ${t === 1 ? 'tarea' : 'tareas'} hoy`
}

/** Icono de cada sugerencia (por su título; si no está, un bocadillo). */
const ICONO: Record<string, Ico> = { '¿Qué tengo hoy?': 'sun', 'Apunta en mi agenda': 'calendar', 'Ofertas de empleo': 'brief', 'Pregúntame lo que quieras': 'chat',
  'Organiza mi día': 'list', 'Escribe por mí': 'pen', 'Dame ideas': 'spark', '¿Qué tengo mañana?': 'calendar' }

/** Sugerencia en forma de pastilla (como en las apps de chat): icono y título; el detalle lo lee el lector de pantalla y sale al pasar el ratón. */
function Tarjeta({ s, detalle, onClick }: { s: Sugerencia; detalle?: string | null; onClick(): void }) {
  const d = detalle || s.detalle
  return <button type="button" className="sug" onClick={onClick} title={d}>
    <Icono n={ICONO[s.titulo] || 'chat'} size={17} /><strong>{s.titulo}</strong><span>{d}</span>
  </button>
}

/** Debajo del saludo: las tarjetas de Zazu (invitadas: sus ideas) y, para Fran, sus últimas conversaciones (de cualquier tipo). */
export default function Sugerencias(p: P) {
  const cuentas = useCuentasHoy(!p.guest)
  const usar = (s: Sugerencia) => s.fill ? p.rellenar(s.prompt) : p.enviar(s.prompt, s.ctx)
  const lista = p.guest ? SUGERENCIAS_INVITADA.filter(s => !s.google || p.me.google?.includes(s.google)) : SUGERENCIAS
  const ultimas = p.guest ? [] : p.sessions.filter(s => s.source !== 'cron').slice(0, 3)
  return <div className={`sugerencias sug-zazu ${lista.length % 2 ? 'impar' : ''} ${lista.length === 6 ? 'seis' : ''}`}>
    <div className="sug-fila">{lista.map((s, i) => <Tarjeta key={s.titulo} s={s} detalle={!p.guest && i === 0 ? cuentas : null} onClick={() => usar(s)} />)}</div>
    {ultimas.length > 0 && <section className="ultimas" aria-labelledby="ultimas-h">
      <h2 id="ultimas-h">Últimas conversaciones</h2>
      <ul>{ultimas.map(s => <li key={`${s.profile}/${s.id}`}><button type="button" onClick={() => p.abrir(s)}>
        <span className="cut">{tituloSesion(s)}</span>{s.busy && <span className="sd ok pulse" role="img" aria-label="respondiendo" />}<small>{relTime(s.last * 1000)}</small><Icon name="chevron" size={16} /></button></li>)}</ul>
    </section>}
  </div>
}
