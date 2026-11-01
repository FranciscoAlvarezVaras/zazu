import { useState } from 'react'
import { Icon } from '../icons'
import { initials, post, toneOf, useFetch } from '../lib'

type Nivel = 'familia' | 'invitada'
type Fallo = { t: number; perfil: string; nombre: string; origen: string; codigo: number | null; detalle: string; conocido?: string | null }
type Vigilante = { ultima: number | null; arreglos: { t: number; nombre: string; que: string }[]; pendientes: { nombre: string; problema: string }[] }
type Reporte = { id: string; t: number; nombre: string; tipo: 'peticion' | 'fallo' | 'idea'; texto: string; estado: 'nuevo' | 'visto' | 'hecho' }
const TIPO_TXT: Record<Reporte['tipo'], string> = { peticion: 'te pide', fallo: 'avisa de un fallo', idea: 'tiene una idea' }
type Apuntada = { email: string; nombre: string; fecha: string }
type Persona = { email: string; name: string; profile: string; propia: boolean; gasto_mes: number; tope: number; tope_max: number; hay_clave: boolean; nivel: Nivel; demo?: boolean }

const NIVEL_TXT: Record<Nivel, string> = { familia: 'Familia: su Google, y aprueba en su móvil', invitada: 'Invitado: solo charla, web y carpetas' }
const LAB = { display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 4, marginTop: 8 } as const
const dolares = (n: number) => `${n.toFixed(2).replace('.', ',')} $`

/** Solo para Fran (el único admin): quién entra, con qué nivel y cuánto crédito de tu clave de Claude tiene al mes. */
export default function Personas({ toast }: { toast: (m: string) => void }) {
  const { data, error, reload } = useFetch<Persona[]>('/api/personas')
  const espera = useFetch<Apuntada[]>('/api/lista-espera')
  const fallos = useFetch<{ errores: Fallo[] }>('/api/errores-invitadas')
  const [verFallos, setVerFallos] = useState('')
  const vig = useFetch<Vigilante>('/api/vigilante-errores')
  const reps = useFetch<{ reportes: Reporte[] }>('/api/reportes-invitadas')
  const [verHechos, setVerHechos] = useState(false)
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [nivel, setNivel] = useState<Nivel>('invitada'); const [busy, setBusy] = useState(false)
  const ok = name.trim() && /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email.trim())
  const max = data?.[0]?.tope_max ?? 15
  async function add() {
    setBusy(true)
    try { await post('/api/personas', { action: 'add', name: name.trim(), email: email.trim(), nivel }); toast(`El asistente de ${name.trim()} está listo`); setName(''); setEmail(''); await reload() }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  async function darAcceso(a: Apuntada) {
    const nombre = (a.nombre || prompt(`¿Cómo se llama ${a.email}?`, a.email.split('@')[0]) || '').trim()
    if (!nombre) return
    setBusy(true)
    try { await post('/api/personas', { action: 'add', name: nombre, email: a.email, nivel: 'invitada' }); toast(`${nombre} ya puede entrar con su Google`); await Promise.all([reload(), espera.reload()]) }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  async function editar(p: Persona, cambio: { nivel?: Nivel; credito?: number }, msg: string) {
    if (cambio.nivel === 'invitada' && p.nivel !== 'invitada' && !confirm(`${p.name} pasará a Invitado y se desconectará su Google. ¿Seguro?`)) return
    try { await post('/api/personas', { action: 'editar', email: p.email, ...cambio }); toast(msg); await reload() } catch (e) { toast(`No se pudo: ${(e as Error).message}`) }
  }
  async function hecho(r: Reporte) {
    try { await post('/api/reportes-invitadas', { id: r.id, estado: 'hecho' }); toast('Marcado como hecho'); await reps.reload() } catch (e) { toast(`No se pudo: ${(e as Error).message}`) }
  }
  async function quitar(p: Persona) {
    if (!confirm(`¿Quitar el acceso a ${p.name}? Sus chats se conservan en el PC.`)) return
    try { await post('/api/personas', { action: 'remove', email: p.email }); toast('Acceso retirado'); await reload() } catch (e) { toast((e as Error).message) }
  }
  return <div className="settings-group" id="personas">
    {(espera.data || []).length > 0 && <><span className="section-kicker">SE HAN APUNTADO EN LA WEB · {espera.data!.length}</span>
      {espera.data!.map(a => <div className="acc-card" key={a.email}><div className="acc-top"><span className={`sender-avatar ${toneOf(a.nombre || a.email)}`}>{initials(a.nombre || a.email)}</span>
        <div><strong>{a.nombre || a.email.split('@')[0]}</strong><small>{a.email}{a.fecha ? ` · se apuntó el ${a.fecha.split('-').reverse().join('/')}` : ''}</small></div></div>
        <div className="actions"><button className="btn-primary" disabled={busy} onClick={() => void darAcceso(a)}><Icon name="plus" size={16} /> Dar acceso</button></div></div>)}
      <p className="muted-note">Al darle acceso entra como Invitado (charla, web y carpetas). Luego puedes pasarlo a Familia aquí abajo. Para que entre, que use «Entrar con Google» con ese mismo correo.</p></>}
    {(reps.data?.reportes || []).length > 0 && (() => {
      const todos = reps.data!.reportes, pend = todos.filter(r => r.estado !== 'hecho'), hechos = todos.filter(r => r.estado === 'hecho')
      return <><span className="section-kicker">LO QUE TE PIDEN{pend.length ? ` · ${pend.length}` : ''}</span>
        {pend.length === 0 && <p className="muted-note">✓ Todo hecho.</p>}
        {[...pend, ...(verHechos ? hechos : [])].slice(0, 60).map(r => <div className="acc-card" key={r.id}><div className="acc-top"><span className={`sender-avatar ${toneOf(r.nombre)}`}>{initials(r.nombre)}</span>
          <div><strong>{r.nombre.split(' ')[0]} {TIPO_TXT[r.tipo] || 'te pide'}</strong>
            <small>{new Date(r.t * 1000).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}{r.estado === 'hecho' ? ' · hecho' : r.estado === 'nuevo' ? ' · nuevo' : ''}</small></div></div>
          <p style={{ margin: '6px 0', whiteSpace: 'pre-wrap' }}>{r.texto}</p>
          {r.estado !== 'hecho' && <div className="actions"><button className="btn-secondary" onClick={() => void hecho(r)}><Icon name="check" size={16} /> Hecho</button></div>}</div>)}
        {hechos.length > 0 && <button type="button" className="text-link" onClick={() => setVerHechos(!verHechos)}>{verHechos ? 'Ocultar' : 'Ver'} los hechos ({hechos.length})</button>}</>
    })()}
    {vig.data?.ultima && <div className="acc-card"><strong>Vigilante de errores</strong>
      <small>Revisa a todas cada 10 minutos y arregla lo que puede solo. Última vez: {new Date(vig.data.ultima * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}.</small>
      {vig.data.pendientes.length ? <ul style={{ margin: '6px 0', paddingLeft: 18, fontSize: 13 }}>{vig.data.pendientes.map((p, i) => <li key={i}><strong>{p.nombre || 'General'}</strong>: {p.problema}</li>)}</ul>
        : <small>✓ Nada pendiente.</small>}
      {vig.data.arreglos.length > 0 && <small>Últimos arreglos: {vig.data.arreglos.slice(0, 3).map(a => `${a.nombre}: ${a.que}`).join(' · ')}</small>}</div>}
    <span className="section-kicker">PERSONAS CON SU PROPIO ASISTENTE{fallos.data ? (() => { const n = fallos.data.errores.filter(f => !f.conocido).length; return ` · ${n ? `${n} errores pendientes en 7 días` : 'sin errores pendientes en 7 días'}` })() : ''}</span>
    {error && <div className="fallo" role="alert"><span>No pude leer quién tiene acceso.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    {data && data.length > 0 && !data[0].hay_clave && <div className="fallo" role="note"><span>Falta tu clave de la API de Claude: hasta que la pongas, sus asistentes no pueden contestar.</span></div>}
    {(data || []).map(p => <div className="acc-card" key={p.email}><div className="acc-top"><span className={`sender-avatar ${toneOf(p.name)}`}>{initials(p.name)}</span>
      <div><strong>{p.name}{p.demo ? ' · demo pública' : ''}</strong><small>{p.demo ? 'Cuenta de demo con datos inventados: se entra en holazazu.app/demo y solo se mira. «Quitar acceso» la apaga.' : `${p.email} · entra con «Entrar con Google»`}</small>
        <small>{p.propia ? '✓ Usa su propia IA (no gasta de lo tuyo)' : `Este mes: ${dolares(p.gasto_mes)} de ${dolares(p.tope)}${p.gasto_mes >= p.tope && p.tope > 0 ? ' · se le acabó el crédito' : ''}`}</small></div></div>
      <label className="check" style={LAB}>Nivel
        <select className="campo" value={p.nivel} onChange={e => void editar(p, { nivel: e.target.value as Nivel }, 'Nivel cambiado')}>
          {(Object.keys(NIVEL_TXT) as Nivel[]).map(k => <option key={k} value={k}>{NIVEL_TXT[k]}</option>)}</select></label>
      <label className="check" style={LAB}>Crédito al mes (máximo {dolares(max)})
        <input className="campo" type="number" min={0} max={max} step={1} defaultValue={p.tope} key={`${p.email}-${p.tope}`}
          onBlur={e => { const v = Number(e.target.value); if (v !== p.tope && v >= 0 && v <= max) void editar(p, { credito: v }, 'Crédito cambiado') }} /></label>
      {!p.demo && (() => { const mios = (fallos.data?.errores || []).filter(f => f.perfil === p.profile); return mios.length > 0 && <>
        <button type="button" className="text-link" onClick={() => setVerFallos(verFallos === p.profile ? '' : p.profile)}>{verFallos === p.profile ? 'Ocultar' : 'Ver'} sus errores (7 días): {(() => { const n = mios.filter(f => !f.conocido).length; return n ? `${n} pendientes` : 'ninguno pendiente' })()}{mios.some(f => f.conocido) ? ` · ${mios.filter(f => f.conocido).length} ya explicados` : ''}</button>
        {verFallos === p.profile && <ul style={{ margin: '6px 0', paddingLeft: 18, fontSize: 13 }}>{mios.slice(0, 40).map((f, i) => <li key={i} style={f.conocido ? { opacity: 0.6 } : undefined}>
          <strong>{new Date(f.t * 1000).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</strong> · {f.origen}{f.codigo ? ` (${f.codigo})` : ''}: {f.detalle}{f.conocido && <em> — {f.conocido}</em>}</li>)}</ul>}</> })()}
      <button className="btn-secondary" onClick={() => void quitar(p)}><Icon name="close" size={16} /> Quitar acceso</button></div>)}
    <form className="ev-form" onSubmit={e => { e.preventDefault(); void add() }}>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="Nombre (p. ej. Nuria)" aria-label="Nombre" maxLength={40} />
      <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Su Gmail" type="email" aria-label="Su Gmail" />
      <select className="campo" value={nivel} onChange={e => setNivel(e.target.value as Nivel)} aria-label="Nivel">
        {(Object.keys(NIVEL_TXT) as Nivel[]).map(k => <option key={k} value={k}>{NIVEL_TXT[k]}</option>)}</select>
      <div className="actions"><button className="btn-primary" disabled={!ok || busy}><Icon name="plus" size={17} /> {busy ? 'Creando su asistente…' : 'Dar acceso'}</button></div>
    </form>
    <p className="muted-note">Tú eres el único administrador: nadie más puede cambiar la app ni sus ajustes. Cada persona tiene su asistente privado, que funciona con tu clave de Claude hasta su crédito del mes (empieza en {dolares(max)}; puedes bajarlo). No ve nada tuyo y tú no ves sus chats. Con nivel Familia, cuando su asistente quiera apuntarle algo en su Google, le llega un aviso al móvil para Permitir o Rechazar.</p>
    <p className="muted-note">Si a alguien de Familia Google le dice «Acceso bloqueado» al conectar su Gmail, añade su correo en <a href="https://console.cloud.google.com/auth/audience" target="_blank" rel="noopener">Google Cloud › Público › Usuarios de prueba</a> (hasta 100 personas). WhatsApp lo conectan solas desde Tu espacio con un código de 8 letras, sin escanear nada.</p>
  </div>
}
