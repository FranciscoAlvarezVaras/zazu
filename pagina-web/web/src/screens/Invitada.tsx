import { Icon } from '../icons'
import type { IconName } from '../icons'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { EN_APP, IA_PROPIA, irA, post, useFetch, useParams } from '../lib'
import AgendaChats from './AgendaChats'
import { FormPreferencias, type Prefs } from './Preferencias'
import { PanelPermisos, TuMenu } from './Permisos'
import type { Ctx } from '../ctx'
import { AlertasPush } from './Ajustes'
import { avisarCanales, TarjetaWhatsApp, useCanales } from './WhatsAppVincular'
import Bienvenida from './Bienvenida'
import '../conversacion.css'   // .campo (selectores y cuadros de texto con los colores del tema)
import { copiar } from '../chat/Acciones'

export type Me = { user: string; name: string; role: 'admin' | 'guest'; profile: string | null; demo?: boolean; prefs?: Prefs; menu_posible?: string[]; ocultas?: string[]; portada?: string | null; asistente?: string; onboarded?: boolean; menu_visto?: boolean; ia?: boolean; google?: string[] | null
  /** Solo en invitadas. «familia»: puede conectar su Google (y lo que apunte Zazu se aprueba en el móvil); «invitada»: sin Google. */
  nivel?: 'familia' | 'invitada'
  /** Crédito de IA del mes en curso (euros), el que pone Fran. */
  credito?: { tope: number; gastado: number }
  /** Qué secciones ve (lib.puede). */
  capacidades?: Record<string, boolean> }
function Reintentar({ error, reload }: { error: string; reload: () => void }) {
  return <div className="empty-radar" role="alert">No se pudo cargar ({error}). <button className="text-link" onClick={reload}>Reintentar</button></div>
}

type IA = { incluido: { pct: number; modelo: string } | null; connected: boolean; provider: string | null; model: string | null; models: Record<string, string>
  login: { state: 'esperando' | 'conectado' | 'error'; url: string | null; code: string | null } | null
  claude: { state: 'esperando' | 'conectado' | 'error'; url: string | null } | null }

/** Su propio ChatGPT (opción "ChatGPT or Codex Subscription" de Hermes): enlace + código, sin claves. */
export function CuentaIA({ toast, nombre = 'Zazu', onConnected }: { toast: (m: string) => void; nombre?: string; onConnected?: () => void }) {
  const [poll, setPoll] = useState(false)
  const ia = useFetch<IA>('/api/ia', poll ? 3000 : undefined)
  const [busy, setBusy] = useState(false); const [login, setLogin] = useState<{ url: string; code: string } | null>(null)
  const [claude, setClaude] = useState<string | null>(null); const [codigo, setCodigo] = useState(''); const [pegado, setPegado] = useState(false)
  const d = ia.data
  useEffect(() => {   // Claude: esperar a que Hermes cambie el código por el acceso
    if (!pegado || !d?.claude) return
    if (d.claude.state === 'conectado') { setPoll(false); setPegado(false); setClaude(null); setCodigo(''); toast('¡Claude conectado!'); onConnected?.() }
    if (d.claude.state === 'error') { setPoll(false); setPegado(false); setClaude(null); toast('Claude no aceptó el código. Vuelve a empezar.') }
  }, [d?.claude?.state, pegado]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {   // si ya había un código en marcha (volvió a esta pantalla), retomarlo en vez de pedir otro
    if (!login && d?.login?.state === 'esperando' && d.login.code) { setLogin({ url: d.login.url || 'https://auth.openai.com/codex/device', code: d.login.code }); setPoll(true) }
  }, [d?.login?.state]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!poll || !d?.login) return
    if (d.login.state === 'conectado') { setPoll(false); setLogin(null); toast('¡ChatGPT conectado!'); onConnected?.() }
    if (d.login.state === 'error') { setPoll(false); setLogin(null); toast('No se completó. Inténtalo otra vez.') }
  }, [d, poll]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (body: object, ok?: string) => {
    setBusy(true)
    try { const r = await post<{ url?: string; code?: string }>('/api/ia', body); if (ok) toast(ok); await ia.reload(); return r } catch (e) { toast((e as Error).message) } finally { setBusy(false) }
  }
  const empezarClaude = async () => { const r = await act({ action: 'claude' }); if (r?.url) setClaude(r.url) }
  const pegarCodigo = async () => { const r = await act({ action: 'claude_codigo', codigo }); if (r) { setPegado(true); setPoll(true) } }
  const empezar = async () => { const r = await act({ action: 'chatgpt' }); if (r?.code) { setLogin({ url: r.url || 'https://auth.openai.com/codex/device', code: r.code }); setPoll(true) } }
  if (ia.loading && !d) return <div className="empty-radar">Cargando…</div>
  if (login) return <div className="acc-card chatgpt-login">
    <strong>Conecta tu ChatGPT</strong>
    <ol className="onb-list num"><li>Pulsa <b>Abrir ChatGPT</b> e inicia sesión con tu cuenta.</li><li>Escribe este código:</li></ol>
    <button type="button" className="chatgpt-code" onClick={() => { copiar(login.code).then(() => toast('Código copiado'), () => toast(`Apunta el código: ${login.code}`)) }} aria-label={`Código ${login.code}. Toca para copiar`}>{login.code}<small>toca para copiar</small></button>
    <a className="btn-primary" href={login.url} target="_blank" rel="noopener noreferrer">Abrir ChatGPT <Icon name="arrow" size={17} /></a>
    <p className="onb-note"><Icon name="clock" size={16} /> Esperando a que lo autorices… Esta pantalla se actualiza sola.</p>
    <button className="text-link" onClick={() => { setLogin(null); setPoll(false) }}>Cancelar</button>
  </div>
  if (claude) return <div className="acc-card chatgpt-login">
    <strong>Conecta tu Claude</strong>
    <ol className="onb-list num"><li>Pulsa <b>Abrir Claude</b>, entra con tu cuenta (Pro o Max) y pulsa <b>Authorize</b>.</li><li>Claude te enseñará un <b>código</b>: cópialo entero.</li><li>Vuelve aquí y pégalo:</li></ol>
    <a className="btn-secondary" href={claude} target="_blank" rel="noopener noreferrer">Abrir Claude <Icon name="arrow" size={17} /></a>
    <form className="ev-form" onSubmit={e => { e.preventDefault(); void pegarCodigo() }}>
      <input value={codigo} onChange={e => setCodigo(e.target.value)} placeholder="Pega aquí el código de Claude" aria-label="Código de Claude" autoComplete="off" spellCheck={false} />
      <div className="actions"><button className="btn-primary" disabled={!codigo.includes('#') || busy || pegado}>{pegado ? 'Comprobando…' : 'Conectar'}</button></div></form>
    <button className="text-link" onClick={() => { setClaude(null); setCodigo(''); setPegado(false); setPoll(false) }}>Cancelar</button>
  </div>
  if (!d?.connected) return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="lightbulb" size={19} /></span><div><strong>Conecta tu IA</strong><small>{nombre} funciona con tu propia cuenta de ChatGPT (Plus o superior) o de Claude (Pro o Max). Sin claves: solo un código. Mientras no la conectes, no podrá responderte.</small></div></div>
    <button className="btn-primary" disabled={busy} onClick={() => void empezar()}>{busy ? 'Preparando…' : 'Conectar mi ChatGPT'} <Icon name="arrow" size={17} /></button>
    <button className="btn-secondary" disabled={busy} onClick={() => void empezarClaude()}>Conectar mi Claude <Icon name="arrow" size={17} /></button>
  </div>
  return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="check" size={19} /></span><div><strong>{d.provider === 'claude' ? 'Claude' : 'ChatGPT'} conectado</strong><small>{nombre} usa tu cuenta de {d.provider === 'claude' ? 'Claude' : 'ChatGPT'}.</small></div></div>
    <label className="check" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6, fontSize: 14 }}>Modelo
      <select className="campo" value={d.model || ''} onChange={e => void act({ action: 'model', model: e.target.value }, 'Modelo cambiado')} disabled={busy}>
        {Object.entries(d.models).map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
    <button className="btn-secondary" onClick={() => { if (confirm(`¿Desconectar tu ${d.provider === 'claude' ? 'Claude' : 'ChatGPT'}? Tu asistente no podrá responderte hasta que conectes otra.`)) void act({ action: 'disconnect' }, 'Desconectado') }}>Desconectar {d.provider === 'claude' ? 'Claude' : 'ChatGPT'}</button>
  </div>
}

/** WhatsApp (código con su número o QR; la tarjeta está en WhatsAppVincular) y Telegram (su bot): cada una con su propio gateway de Hermes. */
export function CanalesInvitada({ toast, nombre = 'Zazu', soloWhatsApp = false }: { toast: (m: string) => void; nombre?: string; /** la guía: sin Telegram */ soloWhatsApp?: boolean }) {
  const [poll, setPoll] = useState(false)
  const c = useCanales(poll ? 2500 : 0)
  const [busy, setBusy] = useState(''); const [token, setToken] = useState('')
  const d = c.data
  const esperando = d?.whatsapp.emparejando === 'esperando' || !!d?.telegram.codigo || (!!d?.whatsapp.conectado && d.gateway !== 'active')   // y hasta que su Zazu arranque
  useEffect(() => { setPoll(esperando) }, [esperando])
  const antes = useRef(d?.whatsapp.emparejando)
  useEffect(() => {   // avisar solo al pasar de "esperando" a "conectado", no cada vez que se abre la pantalla
    if (antes.current === 'esperando' && d?.whatsapp.conectado) toast('¡WhatsApp conectado!')
    antes.current = d?.whatsapp.emparejando
  }, [d?.whatsapp.emparejando, d?.whatsapp.conectado]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (body: object, ok?: string) => {
    setBusy(String((body as { action: string }).action))
    try { await post('/api/canales', body); if (ok) toast(ok); await c.reload(); avisarCanales(); return true } catch (e) { toast((e as Error).message); await c.reload(); return false } finally { setBusy('') }
  }
  if (!d) return c.error ? <Reintentar error={c.error} reload={c.reload} /> : <div className="empty-radar">Cargando…</div>
  const tg = d.telegram
  return <>
    <TarjetaWhatsApp d={d} act={act} busy={busy} toast={toast} nombre={nombre} />
    {!soloWhatsApp && <div className="acc-card">
      <div className="acc-top"><span className="setting-icon"><Icon name="arrowUp" size={19} /></span><div><strong>Telegram</strong>
        <small>{tg.conectado ? `Conectado: @${tg.bot}` : `Crea tu propio contacto de ${nombre} en Telegram (unos 3 minutos).`}</small></div></div>
      {tg.conectado ? <button className="btn-secondary" disabled={!!busy} onClick={() => { if (confirm('¿Desconectar Telegram?')) void act({ action: 'telegram_off' }, 'Telegram desconectado') }}>Desconectar Telegram</button>
        : tg.codigo ? <div className="chatgpt-login">
          <p>Último paso: abre tu bot y pulsa <b>Iniciar</b>. Nosotros hacemos el resto.</p>
          <a className="btn-primary" href={`https://t.me/${tg.bot}?start=${tg.codigo}`} target="_blank" rel="noopener noreferrer">Abrir @{tg.bot} <Icon name="arrow" size={17} /></a>
          <p className="onb-note"><Icon name="clock" size={16} /> Esperando tu mensaje… (si no funciona el botón, envíale: {tg.codigo})</p></div>
          : <form className="ev-form" onSubmit={e => { e.preventDefault(); void act({ action: 'telegram', token: token.trim() }).then(ok => ok && setToken('')) }}>
            <ol className="onb-list num"><li>Abre <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer"><b>@BotFather</b></a> y envíale <b>/newbot</b>.</li><li>Ponle un nombre (por ejemplo «{nombre}») y un usuario que acabe en «bot».</li><li>Te contestará con un código largo (la «clave», con dos puntos «:» en medio). Cópialo y pégalo aquí:</li></ol>
            <input value={token} onChange={e => setToken(e.target.value)} placeholder="123456789:AA…" aria-label="Clave de tu bot de Telegram" autoComplete="off" spellCheck={false} className="campo" />
            <div className="actions"><button className="btn-primary" disabled={!token.includes(':') || !!busy}>{busy === 'telegram' ? 'Comprobando…' : 'Conectar'}</button></div></form>}
    </div>}
  </>
}

type Rut = { id: string; name: string; expr: string; deliver: string; enabled: boolean; prompt: string; next: string | null }
const DIAS_TXT: Record<string, string> = { diario: 'Todos los días', laborables: 'De lunes a viernes', finde: 'Fines de semana', lun: 'Lunes', mar: 'Martes', mie: 'Miércoles', jue: 'Jueves', vie: 'Viernes', sab: 'Sábados', dom: 'Domingos' }
const DEST_TXT: Record<string, string> = { local: 'En la app', whatsapp: 'Por WhatsApp', telegram: 'Por Telegram' }
const cuando = (expr: string) => {
  const [m, h, , , dw] = expr.split(' ')
  const dias = Object.entries({ '*': 'todos los días', '1-5': 'de lunes a viernes', '0,6': 'fines de semana', 1: 'lunes', 2: 'martes', 3: 'miércoles', 4: 'jueves', 5: 'viernes', 6: 'sábados', 0: 'domingos' }).find(([k]) => k === dw)?.[1] || dw
  return `${dias} a las ${h.padStart(2, '0')}:${m.padStart(2, '0')}`
}

/** Rutinas (cron de Hermes) solo con texto: nada de scripts. */
export function RutinasInvitada({ toast }: { toast: (m: string) => void }) {
  const r = useFetch<{ rutinas: Rut[]; plantillas: Record<string, string>; canales: string[] }>('/api/rutinas')
  const [f, setF] = useState({ plantilla: 'manana', texto: '', hora: '08:00', dias: 'diario', destino: 'local' })
  const [busy, setBusy] = useState(false); const [abierto, setAbierto] = useState(false)
  const act = async (body: object, ok: string) => {
    setBusy(true)
    try { await post('/api/rutinas', body); toast(ok); await r.reload(); return true } catch (e) { toast((e as Error).message); return false } finally { setBusy(false) }
  }
  const d = r.data
  if (!d) return r.error ? <Reintentar error={r.error} reload={r.reload} /> : <div className="empty-radar">Cargando…</div>
  return <div className="acc-card">
    {d.rutinas.length ? <div className="settings-list">{d.rutinas.map(x => <div key={x.id} className="setting-row informational">
      <span className="setting-copy"><strong style={{ opacity: x.enabled ? 1 : 0.5 }}>{x.name}</strong><small>{cuando(x.expr)} · {DEST_TXT[x.deliver.split(':')[0]] || x.deliver}{x.enabled ? '' : ' · en pausa'}</small></span>
      <button className="text-link" disabled={busy} onClick={() => void act({ action: x.enabled ? 'pause' : 'resume', id: x.id }, x.enabled ? 'Rutina en pausa' : 'Rutina activada')}>{x.enabled ? 'Pausar' : 'Activar'}</button>
      <button className="text-link" disabled={busy} onClick={() => { if (confirm(`¿Borrar «${x.name}»?`)) void act({ action: 'remove', id: x.id }, 'Rutina borrada') }}>Borrar</button></div>)}</div>
      : <small>Aún no tienes rutinas. Elige una y te llegará sola.</small>}
    {!abierto ? <button className="btn-secondary" onClick={() => setAbierto(true)}><Icon name="plus" size={17} /> Añadir rutina</button> : <form className="ev-form" onSubmit={e => { e.preventDefault(); void act({ action: 'add', ...f }, 'Rutina creada').then(ok => { if (ok) { setAbierto(false); setF({ plantilla: 'manana', texto: '', hora: '08:00', dias: 'diario', destino: 'local' }) } }) }}>
      <div className="onb-options">{[...Object.entries(d.plantillas), ['propia', '✨ Crear la mía']].map(([k, n]) => <button key={k} type="button" className={`onb-option ${f.plantilla === k ? 'on' : ''}`} aria-pressed={f.plantilla === k} onClick={() => setF({ ...f, plantilla: k })}><strong>{n}</strong></button>)}</div>
      {f.plantilla === 'propia' && <textarea value={f.texto} maxLength={500} rows={3} onChange={e => setF({ ...f, texto: e.target.value })} placeholder="Ej.: Mándame una receta fácil para cenar" aria-label="Qué quieres que te mande" className="campo" style={{ padding: 10 }} />}
      <div style={{ display: 'flex', gap: 8 }}><input type="time" value={f.hora} onChange={e => setF({ ...f, hora: e.target.value })} aria-label="Hora" className="campo" style={{ flex: '0 0 124px' }} />
        <select value={f.dias} onChange={e => setF({ ...f, dias: e.target.value })} aria-label="Días" className="campo" style={{ flex: 2 }}>{Object.entries(DIAS_TXT).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></div>
      <select value={f.destino} onChange={e => setF({ ...f, destino: e.target.value })} aria-label="Dónde te llega" className="campo">{['local', ...d.canales].map(k => <option key={k} value={k}>{DEST_TXT[k]}</option>)}</select>
      <div className="actions"><button type="button" className="text-link" onClick={() => setAbierto(false)}>Cancelar</button><button className="btn-primary" disabled={busy}>{busy ? 'Creando…' : 'Crear rutina'}</button></div></form>}
  </div>
}

/** Rutinas de una invitada como pantalla del menú (las mismas que en Tu espacio). */
export function PantallaRutinas({ toast, me }: Ctx) {
  return <div className="extra-screen screen-enter rut">
    <div className="screen-heading"><span className="section-kicker">{(me.asistente || 'Zazu').toUpperCase()} TRABAJA SOLO</span><h2>Rutinas<span className="greeting-dot">.</span></h2><p>Mensajes automáticos a tu hora.</p></div>
    <div className="acc-card"><strong>Crea las tuyas, a tu medida</strong>
      <small>Escribe lo que quieres que {me.asistente || 'Zazu'} te mande, elige la hora y los días, y listo. Algunas ideas:</small>
      <div className="onb-ej">
        <span>«Cada mañana a las 8: el tiempo de hoy y una frase bonita»</span>
        <span>«Los lunes a las 19:00: 3 ideas de cena fáciles para la semana»</span>
        <span>«Todos los días a las 22:00: pregúntame cómo me ha ido el día»</span>
        <span>«Los viernes: recuérdame regar las plantas»</span>
      </div>
      <small>{EN_APP ? 'En esta app todavía no llegan como aviso: te llegan por WhatsApp si lo tienes vinculado (Tu espacio › Tus permisos), o abre holazazu.app en Chrome y activa allí las notificaciones.'
        : 'Te llegan como aviso al móvil (activa las notificaciones en Tu espacio › Tus permisos) o por WhatsApp si lo tienes conectado.'}</small></div>
    <RutinasInvitada toast={toast} />
  </div>
}

type Op = Record<string, string>
type MiZazu = { asistente: string; tono: string; largo: string; web: boolean; sobre_mi: string; recuerdos: { id: string; texto: string }[]
  modelo: string; razonar: string; personalidad: string; tools: string[]; zona: string; propia: boolean
  opciones: { razonar: Op; personalidad: Op; tools: Op; zonas: string[]; modelos: Record<string, { nombre: string; desc: string }> } }
const TONO: Op = { cercano: 'Cercano', formal: 'Formal', divertido: 'Divertido', directo: 'Directo' }
const LARGO: Op = { cortas: 'Cortas', normales: 'Normales', detalladas: 'Detalladas' }
const lab = { flexDirection: 'column', alignItems: 'stretch', gap: 6, fontSize: 14 } as const

/** Configurar su propio Hermes, por secciones como Hermes Desktop. Solo las opciones seguras. */
function Configurar({ toast, onSaved, me }: { toast: (m: string) => void; onSaved: () => void; me: Me }) {
  const z = useFetch<MiZazu>('/api/mi-zazu')
  const [f, setF] = useState<MiZazu | null>(null); const [busy, setBusy] = useState(false)
  const d = f || z.data
  if (!d) return z.error ? <Reintentar error={z.error} reload={z.reload} /> : <div className="empty-radar">Cargando…</div>
  const set = (k: Partial<MiZazu>) => setF({ ...d, ...k })
  const guardar = async () => {   // guarda TODO lo cambiado, sea cual sea el botón (antes cada uno guardaba una parte)
    setBusy(true)
    try {
      await post('/api/mi-zazu', { action: 'save', ...d, web: d.tools.includes('web') })
      await post('/api/mi-zazu', { action: 'hermes', ...d })
      toast(`Guardado: ${d.asistente || 'Zazu'} ya lo tiene en cuenta`); setF(null); await z.reload(); onSaved()
    } catch (e) { toast((e as Error).message) } finally { setBusy(false) }
  }
  const olvidar = async (id: string) => {
    if (!confirm('¿Olvidar este recuerdo?')) return
    try { await post('/api/mi-zazu', { action: 'olvidar', id }); toast('Olvidado'); await z.reload() } catch (e) { toast((e as Error).message) }
  }
  const sel = (label: string, k: 'tono' | 'largo' | 'personalidad' | 'razonar' | 'zona', o: Op) => <label className="check" style={lab}>{label}
    <select value={d[k]} onChange={e => set({ [k]: e.target.value })} className="campo">{Object.entries(o).map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
  const btn = f ? <div className="actions"><button className="btn-primary" disabled={busy} onClick={() => void guardar()}>{busy ? 'Guardando…' : 'Guardar cambios'}</button></div> : null
  const sec = (icon: IconName, title: string, sub: string, body: ReactNode) => <details className="cfg-sec"><summary><span className="setting-icon"><Icon name={icon} size={19} /></span>
    <span className="setting-copy"><strong>{title}</strong><small>{sub}</small></span><Icon name="chevron" size={17} /></summary><div className="cfg-body">{body}</div></details>
  const o = d.opciones
  return <div className="cfg">
    {sec('spark', 'Tu asistente', `${d.asistente} · ${TONO[d.tono] || d.tono} · ${o.personalidad[d.personalidad] || 'Sin personalidad extra'}`, <>
      <label className="check" style={lab}>Nombre<input value={d.asistente} maxLength={24} onChange={e => set({ asistente: e.target.value })} placeholder="Zazu" className="campo" /></label>
      {sel('Tono', 'tono', TONO)}{sel('Largo de las respuestas', 'largo', LARGO)}
      {sel('Personalidad extra (opcional)', 'personalidad', o.personalidad)}{btn}</>)}
    {IA_PROPIA ? sec('lightbulb', 'Inteligencia (IA)', d.propia ? 'Tu propia cuenta' : 'Sin conectar: conéctala para empezar', <>
      <CuentaIA toast={toast} nombre={d.asistente} onConnected={() => { void z.reload(); onSaved() }} />
      {sel('Forma de pensar', 'razonar', o.razonar)}{btn}</>)
      : sec('lightbulb', 'Inteligencia (IA)', me.ia === false ? 'Todavía no está activa' : 'Activa', <>
        <IAIncluida me={me} nombre={d.asistente} />
        {sel('Forma de pensar', 'razonar', o.razonar)}{btn}</>)}
    {sec('grid', 'Qué puede hacer', `${d.tools.length} cosas activadas`, <>
      {Object.entries(o.tools).map(([id, n]) => <label key={id} className="check"><input type="checkbox" checked={d.tools.includes(id)} onChange={e => set({ tools: e.target.checked ? [...d.tools, id] : d.tools.filter(t => t !== id) })} /> {n}</label>)}
      <small>Por seguridad, {d.asistente} no puede tocar el ordenador donde vive: ni sus archivos ni sus programas. Para buscar cosas ya tiene «Buscar en internet».</small>{btn}</>)}
    {sec('bell', 'Memoria', `${d.recuerdos.length} recuerdos`, <>
      <label className="check" style={lab}>Sobre mí (lo que quieres que sepa siempre)
        <textarea value={d.sobre_mi} maxLength={800} rows={4} onChange={e => set({ sobre_mi: e.target.value })} placeholder="Ej.: trabajo de enfermera, tengo dos gatos, me gusta que me hablen claro…" className="campo" style={{ padding: 10, minHeight: 96 }} /></label>{btn}
      <span className="section-kicker">LO QUE RECUERDA DE TI</span>
      {d.recuerdos.length ? <div className="settings-list">{d.recuerdos.map(r => <div key={r.id} className="setting-row informational">
        <span className="setting-copy"><small>{r.texto}</small></span><button className="text-link" onClick={() => void olvidar(r.id)}>Olvidar</button></div>)}</div>
        : <small>Todavía nada. Lo que le cuentes en el chat lo irá recordando.</small>}</>)}
    {me.nivel === 'invitada' ? <p className="muted-note">{SIN_GOOGLE}</p>
      : sec('shield', 'Google', me.google?.length ? 'Conectado' : 'Agenda, tareas y correo', <>
        <TuGoogle toast={toast} onChange={onSaved} nombre={d.asistente} />
        {me.nivel === 'familia' && <small>Si {d.asistente} quiere apuntarte una cita o una tarea, {EN_APP ? 'te lo pregunta aquí, en la app, al abrirla,' : 'te llega un aviso al móvil'} para <b>Permitir</b> o <b>Rechazar</b>. Sin tu permiso, no se apunta.</small>}</>)}
    <span className="section-kicker">TU MENÚ · LO QUE QUIERES VER</span>
    <TuMenu me={me} toast={toast} cambio={onSaved} />
    <span className="section-kicker">TUS PERMISOS · TÚ DECIDES</span>
    <PanelPermisos prefs={me.prefs} nivel={me.nivel} asistente={d.asistente} toast={toast} cambio={onSaved} irWhatsApp={() => {
      const el = [...document.querySelectorAll<HTMLDetailsElement>('details.cfg-sec')].find(x => x.textContent?.includes('WhatsApp y Telegram'))
      if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth' }); setTimeout(() => el.querySelector<HTMLElement>('input[type=tel], .btn-primary')?.focus({ preventScroll: true }), 400) } }} />
    <p className="muted-note">Cada interruptor vale para este dispositivo o para tu cuenta. Puedes cambiarlo cuando quieras.</p>
    {sec('calendar', 'Tú, tu país y tu hora', me.prefs?.preguntado ? `${me.prefs.apodo || me.name} · ${(me.prefs.zona || '').replace(/_/g, ' ')}${me.prefs.ciudad ? ` · ${me.prefs.ciudad}` : ''} · °${me.prefs.unidad || 'C'}` : 'Cómo te llamo, dónde estás y °C o °F',
      <FormPreferencias nombre={me.name} prefs={me.prefs} asistente={d.asistente} toast={toast} guardado={onSaved} />)}
    {sec('chat', 'WhatsApp y Telegram', 'Háblale desde donde ya chateas', <CanalesInvitada toast={toast} nombre={d.asistente} />)}
    {sec('clock', 'Rutinas', 'Mensajes automáticos a tu hora', <RutinasInvitada toast={toast} />)}
    {sec('clock', 'Zona horaria', d.zona.replace(/_/g, ' '), <>{sel('Dónde estás', 'zona', Object.fromEntries(o.zonas.map(x => [x, x.replace(/_/g, ' ')])))}{btn}</>)}
  </div>
}

/** La IA la pone Fran (crédito al mes por persona): aquí solo se ve si está activa y cuánto lleva gastado. */
function IAIncluida({ me, nombre }: { me: Me; nombre: string }) {
  const eur = (n: number) => `${n.toFixed(2).replace('.', ',')} $`   // el crédito va en dólares (lo que cobra la API)
  const c = me.credito
  return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name={me.ia === false ? 'clock' : 'check'} size={19} /></span><div>
      <strong>{me.ia === false ? `Tu ${nombre} todavía no está activo` : 'Lista para usar'}</strong>
      <small>{me.ia === false ? 'Fran lo activará pronto. No tienes que conectar nada.' : `No tienes que conectar nada: la IA de ${nombre} la pone Fran.`}</small>
      {c && c.tope > 0 && <small>Este mes: {eur(c.gastado)} de {eur(c.tope)}.</small>}</div></div>
  </div>
}

/** Línea para el nivel «invitada» (su acceso no trae Google). */
export const SIN_GOOGLE = 'Tu acceso no incluye Google. Si lo necesitas, díselo a Fran.'

type G = { google: { email: string; services: string[]; error: boolean }[] }
const SERV: Record<string, string> = { calendar: 'Agenda', tasks: 'Tareas', gmail: 'Correo (leer)' }

/** Sus cuentas de Google: se guardan aparte de las de Fran. */
function TuGoogle({ toast, onChange, nombre = 'Zazu' }: { toast: (m: string) => void; onChange: () => void; nombre?: string }) {
  const g = useFetch<G>('/api/cuentas')
  const quitar = async (email: string) => {
    if (!confirm(`¿Desconectar ${email}? ${nombre} dejará de ver su agenda, tareas y correo.`)) return
    try { await post('/api/mi-zazu', { action: 'desconectar_google', email }); toast('Cuenta desconectada'); await g.reload(); onChange() } catch (e) { toast((e as Error).message) }
  }
  return <div className="acc-card">
    {g.data?.google.length ? g.data.google.map(c => <div key={c.email} className="acc-top"><span className="setting-icon"><Icon name={c.error ? 'close' : 'check'} size={19} /></span>
      <div style={{ flex: 1, minWidth: 0 }}><strong style={{ overflowWrap: 'anywhere' }}>{c.email}</strong><small>{c.error ? 'Hay que volver a conectarla' : c.services.map(s => SERV[s] || s).join(' · ')}</small></div>
      <button className="text-link" onClick={() => void quitar(c.email)}>Quitar</button></div>)
      : <div className="acc-top"><span className="setting-icon"><Icon name="calendar" size={19} /></span><div><strong>Sin conectar</strong><small>Conecta tu Google para ver tu agenda, tus tareas y tus correos aquí.</small></div></div>}
    {(g.data?.google || []).some(c => !c.error && Object.keys(SERV).some(k => !c.services.includes(k))) &&
      <p className="onb-note"><Icon name="lightbulb" size={16} /> Falta algún permiso ({Object.keys(SERV).filter(k => !(g.data!.google[0]?.services || []).includes(k)).map(k => SERV[k]).join(', ')}). Pulsa «Conectar otra cuenta o reconectar» y, en la pantalla de Google, <b>marca todas las casillas</b>.</p>}
    <details className="onb-note" open={!g.data?.google.length}><summary>Cómo es, paso a paso (1 minuto)</summary>
      <ol className="onb-list num" style={{ marginTop: 6 }}>
        <li>Pulsa el botón y elige tu cuenta de Gmail.</li>
        <li>Si Google dice <b>«Google no ha verificado esta aplicación»</b>, es normal: pulsa <b>Configuración avanzada</b> y luego <b>Ir a holazazu.app</b>.</li>
        <li>Marca <b>todas las casillas</b> (agenda, tareas y correo) y pulsa <b>Continuar</b>.</li>
        <li>Vuelves aquí solo. {nombre} solo lee tu correo, nunca lo envía, y antes de apuntarte algo te pide permiso en el móvil.</li>
      </ol><small>Si Google dice <b>«Acceso bloqueado»</b>, díselo a Fran: tiene que darte de alta en Google una vez y luego ya funciona.</small></details>
    <a className="btn-primary" href="/oauth/google/start?mode=connect"><Icon name="plus" size={17} /> {g.data?.google.length ? 'Conectar otra cuenta o reconectar' : 'Conectar mi Google'}</a>
  </div>
}

const TIPOS_REPORTE = { peticion: 'Quiero pedirle algo', fallo: 'Algo no funciona bien', idea: 'Tengo una idea' } as const
type TipoReporte = keyof typeof TIPOS_REPORTE

/** «Contarle algo a Fran»: una petición, un fallo o una idea, a mano (lo mismo que hace su Zazu cuando ella se lo pide en el chat). */
export function ContarleAFran({ toast, nombre = 'Zazu' }: { toast: (m: string) => void; nombre?: string }) {
  const [abierto, setAbierto] = useState(false)
  const [tipo, setTipo] = useState<TipoReporte>('peticion')
  const [texto, setTexto] = useState('')
  const [busy, setBusy] = useState(false)
  async function enviar() {
    setBusy(true)
    try { await post('/api/reportes-invitadas', { tipo, texto: texto.trim() }); toast('Reporte enviado al desarrollador. Gracias'); setTexto(''); setAbierto(false) }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  return <div className="acc-card">
    <small>¿Echas algo en falta, algo no va bien o se te ocurre una mejora? Envía un reporte al desarrollador. También puedes decírselo a {nombre} en el chat y lo envía por ti.</small>
    {!abierto ? <div className="actions"><button type="button" className="btn-secondary" onClick={() => setAbierto(true)}><Icon name="mail" size={16} /> Enviar un reporte al desarrollador</button></div>
      : <form className="ev-form" onSubmit={e => { e.preventDefault(); void enviar() }}>
        <select className="campo" value={tipo} onChange={e => setTipo(e.target.value as TipoReporte)} aria-label="Qué es">
          {(Object.keys(TIPOS_REPORTE) as TipoReporte[]).map(k => <option key={k} value={k}>{TIPOS_REPORTE[k]}</option>)}</select>
        <textarea className="campo" rows={4} maxLength={600} value={texto} onChange={e => setTexto(e.target.value)} aria-label="Qué quieres contar en el reporte"
          placeholder="Cuéntaselo con tus palabras. Ej.: me gustaría que Zazu pudiera borrar mis tareas." />
        <small>No pongas contraseñas ni números de cuenta. {texto.length > 500 ? `Te quedan ${600 - texto.length} letras.` : ''}</small>
        <div className="actions"><button className="btn-primary" disabled={busy || texto.trim().length < 2}>{busy ? 'Enviando…' : 'Enviar reporte'}</button>
          <button type="button" className="btn-secondary" onClick={() => setAbierto(false)}>Cancelar</button></div>
      </form>}
  </div>
}

export function EspacioInvitada({ me, toast, onSaved }: Ctx & { me: Me; onSaved: () => void }) {
  const [guia, setGuia] = useState(() => new URLSearchParams(location.search).get('vista') === 'guia')   // «Ver la guía otra vez» (también desde el menú «Todo»), sin tocar `onboarded`
  const vista = useParams().vista
  if (guia) return <div className="onb-capa"><Bienvenida me={me} toast={toast} repaso done={() => { setGuia(false); onSaved() }} /></div>
  if (vista === 'agenda-chats' && !me.demo) return <div className="settings-screen screen-enter">   {/* desde la tarjeta de la Agenda */}
    <button className="text-link" style={{ alignSelf: 'flex-start' }} onClick={() => irA({ tab: 'ajustes' }, true)}><Icon name="back" size={16} /> Tu espacio</button>
    <div className="screen-heading"><span className="section-kicker">TU AGENDA</span><h2>Tus chats, a tu agenda<span className="greeting-dot">.</span></h2></div>
    <AgendaChats toast={toast} nombre={me.asistente || 'Zazu'} />
  </div>
  return <div className="settings-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">HECHO A TU MEDIDA</span><h2>Tu espacio<span className="greeting-dot">.</span></h2><p>{me.asistente || 'Zazu'} es solo para ti.</p></div>
    <div className="profile-card"><span className="profile-avatar">{me.name.slice(0, 1).toUpperCase()}</span><div><strong>{me.name}</strong><small>{me.user}</small></div><span className="profile-spark"><Icon name="spark" size={23} /></span></div>
    <div className="settings-group"><span className="section-kicker">CONFIGURA A {(me.asistente || 'Zazu').toUpperCase()}</span><Configurar toast={toast} onSaved={onSaved} me={me} /></div>
    <div className="settings-group"><span className="section-kicker">NOTIFICACIONES</span><AlertasPush toast={toast} guest /></div>
    {!me.demo && <div className="settings-group"><span className="section-kicker">TU AGENDA CON TUS CHATS</span><AgendaChats toast={toast} nombre={me.asistente || 'Zazu'} /></div>}
    {!me.demo && <div className="settings-group"><span className="section-kicker">REPORTES AL DESARROLLADOR</span><ContarleAFran toast={toast} nombre={me.asistente || 'Zazu'} /></div>}
    <div className="settings-group"><span className="section-kicker">PRIVACIDAD</span><div className="settings-list">
      <div className="setting-row informational"><span className="setting-icon"><Icon name="shield" size={19} /></span><span className="setting-copy"><strong>Tus chats son privados</strong><small>Nadie más los ve, tampoco Fran.</small></span></div>
      <div className="setting-row informational"><span className="setting-icon"><Icon name="spark" size={19} /></span><span className="setting-copy"><strong>Lo que {me.asistente || 'Zazu'} nunca hace</strong><small>Enviar correos en tu nombre, leer tus otros chats de WhatsApp sin tu permiso o compartir lo que le cuentas.</small></span></div>
    </div></div>
    <button className="text-link" style={{ alignSelf: 'center', margin: '0 auto 14px', fontSize: 13 }} onClick={() => setGuia(true)}><Icon name="lightbulb" size={15} /> Ver la guía otra vez</button>
    <button className="btn-secondary" onClick={() => { if (confirm('¿Cerrar sesión en este dispositivo?')) void fetch('/api/logout', { method: 'POST', headers: { 'X-Hub': '1' } }).finally(() => location.replace('/login')) }}>Cerrar sesión</button>
    <div className="settings-signature">Un poco de calma en cada día. <Icon name="spark" size={15} /></div>
  </div>
}
