/* «Crear mi agenda con mis chats» (solo invitadas): con su permiso, su Zazu lee sus chats de WhatsApp del periodo que elija,
   le propone citas, recordatorios y tareas, y ella decide cuáles apuntar. Puede borrarlo todo del servidor cuando quiera.
   Pasos (los dice el servidor, /api/inv/whatsapp): permiso → vincular → esperando (código) → leyendo/pensando → listo (o error).
   Variante de Fran (`fran`, /api/whatsapp-agenda): sin vincular. Lee en solo lectura el WhatsApp que ya sincroniza su vigía; al aceptar,
   busca. Borrar quita solo las propuestas y lo leído: sus chats siguen donde estaban. */
import { useEffect, useRef, useState } from 'react'
import { Icon } from '../icons'
import { irA, post, useFetch, useParams } from '../lib'
import { copiar } from '../chat/Acciones'

type Prop = { id: string; que: string; fecha: string; hora: string | null; con: string | null; tipo: 'cita' | 'recordatorio' | 'tarea'; chat: string | null }
export type EstadoAgendaChats = {
  paso: 'permiso' | 'vincular' | 'esperando' | 'leyendo' | 'pensando' | 'listo' | 'error'
  permiso: { periodo: 'semana' | 'mes'; grupos: boolean } | null
  borrado: number | null
  vinculo: { estado: string; codigo: string | null; error: string | null; id?: string | null }
  cuentas?: CuentaWa[]; max_cuentas?: number
  lectura: { leidos: number | null; con_pistas: number | null; tope: boolean | null; error: string | null; nuevas: number | null; ocupado?: boolean | null }
  propuestas: Prop[]; hechas: number; descartadas: number
  topes: { mensajes: number; usd: number }
  google: boolean
  fran?: boolean
}
export type CuentaWa = { id: string; numero: string | null; estado: 'conectado' | 'esperando' | 'error' | 'nada'; error: string | null; codigo: string | null }
const URL_INV = '/api/inv/whatsapp', URL_FRAN = '/api/whatsapp-agenda'
const TIPO = { cita: 'Cita', recordatorio: 'Recordatorio', tarea: 'Tarea' }
const cuando = (p: Prop) => {
  const d = new Date(`${p.fecha}T12:00:00`).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' })
  return d[0].toUpperCase() + d.slice(1) + (p.hora ? `, a las ${p.hora}` : '')
}
const dolares = (n: number) => `${n.toFixed(2).replace('.', ',')} $`
export const numeroWa = (n: string | null) => !n ? 'Tu WhatsApp' : n.startsWith('34') && n.length === 11 ? `+34 ${n.slice(2, 5)} ${n.slice(5, 8)} ${n.slice(8)}` : `+${n}`

const PASOS_CODIGO = <ol className="onb-list num"><li>Abre <b>WhatsApp</b> en el móvil de ese número.</li><li>Ve a <b>Ajustes → Dispositivos vinculados → Vincular un dispositivo</b>.</li>
  <li>Abajo, pulsa <b>«Vincular con el número de teléfono»</b>.</li><li>Escribe el código. Esta pantalla se pone al día sola.</li></ol>

/** «Tus WhatsApp»: cada número con su estado (conectado, esperando el código, falló), quitar uno, y añadir otro. */
function MisWhatsApp({ d, act, busy, toast }: { d: EstadoAgendaChats; act: (body: Record<string, unknown>, ok?: string) => Promise<unknown>; busy: string; toast: (m: string) => void }) {
  const [abierto, setAbierto] = useState(false); const [tel, setTel] = useState('+34 ')
  const cs = d.cuentas || [], max = d.max_cuentas || 4
  const enCurso = cs.some(c => c.estado === 'esperando')
  const quitar = async (c: CuentaWa) => {
    if (c.estado === 'esperando') { await act({ accion: 'cancelar' }, 'Cancelado'); return }
    if (!confirm(`¿Quitar ${numeroWa(c.numero)}? Dejo de leer sus chats y los borro del servidor. Lo que ya apuntaste se queda en tu agenda.`)) return
    const r = await act({ accion: 'quitar', cuenta: c.id }) as { logout?: boolean } | null
    if (r) toast(r.logout ? `Quitado. Si sigue saliendo en WhatsApp › Dispositivos vinculados, quítalo también allí.` : 'Quitado del servidor. Quítalo también en WhatsApp › Dispositivos vinculados.')
  }
  return <div className="acc-card" style={{ margin: 0, gap: 10 }}>
    <strong>Tus WhatsApp</strong>
    {cs.length === 0 && <small>Ninguno conectado.</small>}
    {cs.map(c => <div key={c.id} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="setting-icon" aria-hidden="true"><Icon name={c.estado === 'conectado' ? 'check' : c.estado === 'esperando' ? 'clock' : 'close'} size={17} /></span>
        <span style={{ flex: 1, minWidth: 0 }}><b>{numeroWa(c.numero)}</b>
          <small style={{ display: 'block', color: c.estado === 'conectado' ? 'var(--ok, #2e7d32)' : c.estado === 'error' ? 'var(--danger, #c62828)' : undefined }}>
            {c.estado === 'conectado' ? 'Conectado ✓ · leo sus chats para tu agenda' : c.estado === 'esperando' ? 'Esperando el código…' : c.error || 'No se conectó'}</small></span>
        <button className="btn-secondary" style={{ padding: '6px 12px' }} disabled={!!busy} onClick={() => void quitar(c)}>{busy === 'quitar' || (busy === 'cancelar' && c.estado === 'esperando') ? '…' : c.estado === 'esperando' ? 'Cancelar' : 'Quitar'}</button>
      </div>
      {c.estado === 'esperando' && c.codigo && <div className="chatgpt-login">
        <p style={{ fontSize: 28, fontWeight: 700, letterSpacing: 3, textAlign: 'center', margin: '4px 0' }}>{c.codigo}</p>
        <button className="btn-secondary" onClick={() => { copiar(c.codigo!.replace('-', '')).then(() => toast('Código copiado'), () => toast(`Apunta el código: ${c.codigo}`)) }}>Copiar el código</button>
        {PASOS_CODIGO}</div>}
    </div>)}
    {!enCurso && cs.length < max && (abierto ? <div className="chatgpt-login">
      <p>Escribe el número del otro WhatsApp. Te doy un <b>código de 8 letras</b> para vincularlo.</p>
      <input className="campo" type="tel" inputMode="tel" autoComplete="tel" value={tel} onChange={ev => setTel(ev.target.value)} aria-label="Número del otro WhatsApp" placeholder="+34 600 111 222" />
      <div className="actions" style={{ display: 'flex', gap: 8 }}>
        <button className="btn-primary" disabled={!!busy || tel.replace(/\D/g, '').length < 9} onClick={() => void act({ accion: 'vincular', telefono: tel }).then(r => { if (r) { setAbierto(false); setTel('+34 ') } })}>
          {busy === 'vincular' ? 'Pidiendo el código…' : 'Conseguir el código'}</button>
        <button className="btn-secondary" disabled={!!busy} onClick={() => setAbierto(false)}>Cancelar</button></div>
    </div> : <button className="text-link" disabled={!!busy} onClick={() => setAbierto(true)}>+ Añadir otro WhatsApp</button>)}
    {cs.length >= max && <small>Ya tienes {max}: quita uno para añadir otro.</small>}
  </div>
}

export default function AgendaChats({ toast, nombre = 'Zazu', fran = false }: { toast: (m: string) => void; nombre?: string; fran?: boolean }) {
  const URL = fran ? URL_FRAN : URL_INV
  const [poll, setPoll] = useState(false)
  const e = useFetch<EstadoAgendaChats>(URL, poll ? 2500 : 0)
  const [busy, setBusy] = useState(''); const [tel, setTel] = useState('+34 ')
  const [periodo, setPeriodo] = useState<'semana' | 'mes'>('semana'); const [grupos, setGrupos] = useState(false)
  const d = e.data
  const enMarcha = d?.paso === 'esperando' || d?.paso === 'leyendo' || d?.paso === 'pensando' || !!d?.cuentas?.some(c => c.estado === 'esperando')
  useEffect(() => { setPoll(enMarcha) }, [enMarcha])
  const antes = useRef(d?.paso)
  useEffect(() => {   // avisar solo al terminar de buscar, no cada vez que se abre la pantalla
    if ((antes.current === 'leyendo' || antes.current === 'pensando') && d?.paso === 'listo') toast(d.propuestas.length ? `Tengo ${d.propuestas.length} propuestas para ti` : 'No encontré nada nuevo que apuntar')
    antes.current = d?.paso
  }, [d?.paso]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (body: Record<string, unknown>, ok?: string) => {
    setBusy(String(body.id || body.accion))
    try { const r = await post<EstadoAgendaChats & { apuntada?: string; logout?: boolean }>(URL, body); if (ok) toast(ok); await e.reload(); return r }
    catch (err) { toast((err as Error).message); return null } finally { setBusy('') }
  }
  const borrar = async () => {
    if (fran) {
      if (!confirm('¿Borrar las propuestas y lo leído? Se borran las propuestas pendientes y las cifras de lo que miré. Tus chats siguen donde estaban, porque los usa tu vigía. Lo que ya apuntaste se queda en tu agenda.')) return
      if (await act({ accion: 'borrar' })) toast('Borrado. Tus chats siguen en tu WhatsApp y en el vigía.')
      return
    }
    if (!confirm('¿Borrar tus chats del servidor? Se borra todo lo que se leyó y se cierra la conexión. Lo que ya apuntaste se queda en tu agenda.')) return
    const r = await act({ accion: 'borrar' })
    if (r) toast(r.logout ? 'Borrado. Quita también el dispositivo en WhatsApp › Dispositivos vinculados.' : 'Borrado del servidor. Quita el dispositivo en WhatsApp › Dispositivos vinculados.')
  }
  if (!d) return e.error ? <div className="empty-radar" role="alert">No se pudo cargar ({e.error}). <button className="text-link" onClick={() => void e.reload()}>Reintentar</button></div>
    : <div className="empty-radar">Cargando…</div>

  const mios = !fran && (d.cuentas?.length ?? 0) > 0 && <MisWhatsApp d={d} act={act} busy={busy} toast={toast} />
  const botonBorrar = d.paso !== 'permiso' && <button className="btn-secondary" disabled={!!busy} onClick={() => void borrar()}>
    {busy === 'borrar' ? 'Borrando…' : fran ? 'Borrar las propuestas y lo leído' : 'Quitar todos y borrar mis chats del servidor'}</button>

  const opciones = <fieldset className="ac-opciones" style={{ border: 0, padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
    <legend style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>¿Qué chats miro?</legend>
    <label className="check"><input type="radio" name="ac-periodo" checked={periodo === 'semana'} onChange={() => setPeriodo('semana')} /> La última semana</label>
    <label className="check"><input type="radio" name="ac-periodo" checked={periodo === 'mes'} onChange={() => setPeriodo('mes')} /> El último mes</label>
    <label className="check"><input type="checkbox" checked={grupos} onChange={ev => setGrupos(ev.target.checked)} /> Incluir también los grupos</label>
  </fieldset>

  if (d.paso === 'permiso' && fran) return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="calendar" size={19} /></span><div><strong>Crear mi agenda con mis chats</strong>
      <small>{nombre} mira tus chats de WhatsApp, busca citas, cumpleaños, quedadas y recados, y te los propone. Tú decides cuáles apuntar: nada se apunta sin que lo toques.</small></div></div>
    {d.borrado && <p className="onb-note" role="status"><Icon name="check" size={16} /> Propuestas y lecturas borradas. Tus chats siguen donde estaban.</p>}
    <ul className="onb-list">
      <li><Icon name="chat" size={17} /><span><b>No hay que vincular nada:</b> uso el WhatsApp que ya lee tu vigía, solo para leer. Nunca escribo a nadie ni toco su conexión.</span></li>
      <li><Icon name="spark" size={17} /><span><b>Qué pasa a la IA:</b> solo los mensajes con fechas u horas, a tu Zazu sin herramientas, y luego se borran de su historial. Como mucho {dolares(d.topes.usd)} cada vez que busca.</span></li>
      <li><Icon name="shield" size={17} /><span><b>Qué se guarda:</b> solo las propuestas y cuántos mensajes miré, nunca el texto de los chats.</span></li>
    </ul>
    {opciones}
    <button className="btn-primary" disabled={!!busy} onClick={() => void act({ accion: 'aceptar', periodo, grupos })}>
      {busy === 'aceptar' ? 'Un momento…' : 'Acepto y buscar'} <Icon name="arrow" size={17} /></button>
  </div>

  if (d.paso === 'permiso') return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="calendar" size={19} /></span><div><strong>Crear mi agenda con mis chats</strong>
      <small>{nombre} lee tus chats de WhatsApp, busca citas, cumpleaños, quedadas y recados, y te los propone. Tú decides cuáles apuntar: nada se apunta sin que lo toques.</small></div></div>
    {d.borrado && <p className="onb-note" role="status"><Icon name="check" size={16} /> Tus chats ya están borrados del servidor. Si no lo has hecho, quita el dispositivo en WhatsApp › Ajustes › Dispositivos vinculados.</p>}
    <ul className="onb-list">
      <li><Icon name="chat" size={17} /><span><b>Qué se lee:</b> tus chats del periodo que elijas. Solo los mensajes con fechas u horas («el jueves a las 8», «mañana», «el 15»…) pasan a la IA, y solo para sacar las propuestas.</span></li>
      <li><Icon name="shield" size={17} /><span><b>Dónde se guardan:</b> solo en tu carpeta del servidor, aparte de todo lo demás. Puedes borrarlos cuando quieras.</span></li>
      <li><Icon name="spark" size={17} /><span><b>Lo que cuesta:</b> gasta un poco de tu crédito de IA (como mucho {dolares(d.topes.usd)} cada vez que busca).</span></li>
      <li><Icon name="lightbulb" size={17} /><span>En tu WhatsApp saldrá como un <b>dispositivo vinculado</b> más. {nombre} nunca escribe a nadie.</span></li>
    </ul>
    {opciones}
    <button className="btn-primary" disabled={!!busy} onClick={() => void act({ accion: 'aceptar', periodo, grupos })}>
      {busy === 'aceptar' ? 'Un momento…' : 'Acepto y conectar'} <Icon name="arrow" size={17} /></button>
  </div>

  if (d.paso === 'vincular') return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="chat" size={19} /></span><div><strong>Conecta tu WhatsApp para leer tus chats</strong>
      <small>Es una conexión aparte de la que usas para hablar con {nombre}. Miro {d.permiso?.periodo === 'mes' ? 'el último mes' : 'la última semana'}{d.permiso?.grupos ? ', grupos incluidos' : ', sin grupos'}.</small></div></div>
    {d.vinculo.error && <p className="onb-note" role="alert"><Icon name="close" size={16} /> {d.vinculo.error}</p>}
    <div className="chatgpt-login">
      <p>Escribe tu número de WhatsApp y te damos un <b>código de 8 letras</b> para vincularlo desde este mismo móvil.</p>
      <input className="campo" type="tel" inputMode="tel" autoComplete="tel" value={tel} onChange={ev => setTel(ev.target.value)} aria-label="Tu número de WhatsApp" placeholder="+34 600 111 222" />
      <button className="btn-primary" disabled={!!busy || tel.replace(/\D/g, '').length < 9} onClick={() => void act({ accion: 'vincular', telefono: tel })}>
        {busy === 'vincular' ? 'Pidiendo el código a WhatsApp…' : 'Conseguir mi código'} <Icon name="arrow" size={17} /></button>
    </div>
    <button className="text-link" disabled={!!busy} onClick={() => void borrar()}>No quiero seguir: borrar lo que elegí</button>
  </div>

  if (d.paso === 'esperando') return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="clock" size={19} /></span><div><strong>Escribe este código en WhatsApp</strong></div></div>
    {d.vinculo.codigo ? <div className="chatgpt-login">
      <p style={{ fontSize: 30, fontWeight: 700, letterSpacing: 3, textAlign: 'center', margin: '6px 0' }}>{d.vinculo.codigo}</p>
      <button className="btn-secondary" onClick={() => { copiar(d.vinculo.codigo!.replace('-', '')).then(() => toast('Código copiado'), () => toast(`Apunta el código: ${d.vinculo.codigo}`)) }}>Copiar el código</button>
      <ol className="onb-list num"><li>Abre <b>WhatsApp</b> en este móvil.</li><li>Ve a <b>Ajustes → Dispositivos vinculados → Vincular un dispositivo</b>.</li>
        <li>Abajo, pulsa <b>«Vincular con el número de teléfono»</b>.</li><li>Escribe este código. Después, esta pantalla empieza a leer sola.</li></ol>
      <p className="onb-note"><Icon name="lightbulb" size={16} /> El código vale unos minutos. Si caduca, pide otro.</p></div>
      : <p className="onb-note"><Icon name="clock" size={16} /> Conectando…</p>}
    <button className="text-link" disabled={!!busy} onClick={() => void act({ accion: 'cancelar' })}>Cancelar</button>
  </div>

  if (d.paso === 'leyendo' || d.paso === 'pensando') return <div className="acc-card" aria-live="polite">
    <div className="acc-top"><span className="setting-icon"><Icon name="clock" size={19} /></span><div>
      <strong>{d.paso === 'leyendo' ? 'Leyendo tus chats…' : 'Buscando citas y recados…'}</strong>
      <small>{d.paso === 'pensando' && d.lectura.con_pistas != null ? `${d.lectura.con_pistas} mensajes con fechas u horas. ` : ''}{fran ? 'Solo leo: tu vigía sigue a lo suyo. ' : ''}Tarda un par de minutos. Puedes salir de aquí: te lo dejo preparado.</small></div></div>
    {mios}
    {botonBorrar}
  </div>

  if (d.paso === 'error') return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="close" size={19} /></span><div><strong>No pude terminar</strong>
      <small>{d.lectura.error || 'Algo falló. Prueba otra vez en un rato.'}</small></div></div>
    <button className="btn-primary" disabled={!!busy} onClick={() => void act({ accion: 'buscar' })}>{busy === 'buscar' ? 'Empezando…' : 'Buscar otra vez'}</button>
    {mios}
    {botonBorrar}
  </div>

  // listo: sus propuestas
  return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="calendar" size={19} /></span><div><strong>Propuestas de tus chats</strong>
      <small>{d.google ? 'Lo que apuntes va a tu Google (agenda o tareas).' : 'Lo que apuntes te llegará como aviso al móvil.'}
        {d.lectura.leidos != null && ` Miré ${d.lectura.leidos} mensajes; ${d.lectura.con_pistas ?? 0} tenían fechas u horas.`}
        {d.lectura.tope && (fran ? ' Paré antes de acabar para no gastar demasiado de una vez.' : ' Paré antes de acabar para no gastar demasiado crédito.')}</small></div></div>
    {d.propuestas.length === 0 ? <p className="onb-note"><Icon name="check" size={16} /> {d.hechas || d.descartadas ? 'Ya has revisado todas.' : d.lectura.leidos == null ? 'Aún no he buscado.' : 'No encontré nada que apuntar.'}</p>
      : d.propuestas.map(p => <div key={p.id} className="acc-card" style={{ margin: 0, gap: 8 }}>
        <div><strong style={{ overflowWrap: 'anywhere' }}>{p.que}</strong>
          <small style={{ display: 'block' }}>{TIPO[p.tipo]} · {cuando(p)}{p.con ? ` · con ${p.con}` : ''}</small>
          {p.chat && <small style={{ display: 'block', opacity: 0.75 }}>Del chat «{p.chat}»</small>}</div>
        <div className="actions" style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" disabled={!!busy} onClick={() => void act({ accion: 'apuntar', id: p.id }).then(r => r && toast(r.apuntada === 'google' ? 'Apuntado en tu Google' : 'Apuntado: te avisaré en el móvil'))}>
            {busy === p.id ? 'Apuntando…' : 'Apuntar'}</button>
          <button className="btn-secondary" disabled={!!busy} onClick={() => void act({ accion: 'descartar', id: p.id })}>Descartar</button>
        </div></div>)}
    {(d.hechas > 0 || d.descartadas > 0) && <small>{d.hechas} apuntadas · {d.descartadas} descartadas</small>}
    <button className="btn-secondary" disabled={!!busy} onClick={() => void act({ accion: 'buscar' }, 'Buscando lo nuevo…')}>{busy === 'buscar' ? 'Empezando…' : d.lectura.leidos == null ? 'Buscar' : 'Buscar otra vez'}</button>
    {mios}
    {botonBorrar}
  </div>
}

const NO_GRACIAS = 'zazu:agenda-chats-no'

/** En la Agenda de una invitada: la invitación (si aún no lo ha hecho) o el aviso de que tiene propuestas por revisar. */
export function TarjetaAgendaChats({ nombre = 'Zazu', fran = false }: { nombre?: string; fran?: boolean }) {
  const e = useFetch<EstadoAgendaChats>(fran ? URL_FRAN : URL_INV)
  const [oculta, setOculta] = useState(() => { try { return localStorage.getItem(NO_GRACIAS) === '1' } catch { return false } })
  const d = e.data
  if (!d) return null
  const ir = () => irA({ tab: 'ajustes', vista: 'agenda-chats' })   // Fran: su Tu espacio baja solo a la sección (AgendaChatsFran)
  if (d.paso === 'listo' && d.propuestas.length > 0) return <div className="acc-card" style={{ margin: '12px 16px' }}>
    <strong>💬 Tienes {d.propuestas.length} {d.propuestas.length === 1 ? 'propuesta' : 'propuestas'} de tus chats</strong>
    <small>Citas y recados que encontré en {fran ? 'tus chats' : 'tu WhatsApp'}. Tú decides cuáles apuntar.</small>
    <div className="actions"><button type="button" className="btn-primary" onClick={ir}>Verlas</button></div></div>
  if (d.paso !== 'permiso' || d.borrado || oculta) return null
  return <div className="acc-card" style={{ margin: '12px 16px' }}>
    <strong>💬 Crear mi agenda con mis chats</strong>
    <small>{nombre} mira tus chats de WhatsApp (con tu permiso{fran ? ', sin vincular nada' : ''}), encuentra citas, cumpleaños y quedadas, y te propone apuntarlas. Puedes borrarlo todo cuando quieras.</small>
    <div className="actions" style={{ display: 'flex', gap: 8 }}><button type="button" className="btn-primary" onClick={ir}>Empezar</button>
      <button type="button" className="btn-secondary" onClick={() => { try { localStorage.setItem(NO_GRACIAS, '1') } catch { /* sin almacenamiento */ } setOculta(true) }}>Ahora no</button></div>
  </div>
}

/** En el Tu espacio de Fran: la sección entera. Si llega desde la tarjeta de su Agenda (?vista=agenda-chats), baja hasta ella. */
export function AgendaChatsFran({ toast }: { toast: (m: string) => void }) {
  const { vista } = useParams()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { if (vista === 'agenda-chats') setTimeout(() => ref.current?.scrollIntoView({ behavior: 'smooth' }), 300) }, [vista])
  return <div className="settings-group" id="agenda-chats" ref={ref}><span className="section-kicker">CREAR MI AGENDA CON MIS CHATS</span>
    <AgendaChats toast={toast} fran /></div>
}
