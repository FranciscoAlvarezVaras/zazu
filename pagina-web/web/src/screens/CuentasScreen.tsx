import { useState } from 'react'
import { Icon } from '../icons'
import { initials, post, toneOf, useFetch } from '../lib'
import type { Cuentas } from '../lib'
import type { Ctx } from '../ctx'
import Personas from './Personas'
import { TarjetaWhatsAppFran } from './WhatsAppVincular'

const SERV: [string, string][] = [['gmail', 'Correo'], ['calendar', 'Calendario'], ['tasks', 'Tareas'], ['contacts', 'Contactos'], ['drive', 'Drive']]
const TODOS = SERV.map(s => s[0])

/** Flujo de permiso de Google en dos pasos (gog --remote): abrir la URL de Google y pegar la dirección de vuelta. */
function Permiso({ email, onDone, toast, web }: { email: string; onDone: () => void; toast: (m: string) => void; web?: boolean }) {
  const [url, setUrl] = useState(''); const [back, setBack] = useState(''); const [busy, setBusy] = useState(false)
  async function empezar() {
    setBusy(true)
    try { const r = await post<{ url: string }>('/api/cuentas', { action: 'start', email, services: TODOS }); setUrl(r.url) }
    catch (e) { toast(`No se pudo iniciar: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  async function terminar() {
    setBusy(true)
    try { await post('/api/cuentas', { action: 'finish', email, services: TODOS, url: back }); toast('Permisos concedidos'); setUrl(''); setBack(''); onDone() }
    catch (e) { toast(`No se pudo terminar: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  if (web) return <a className="btn-primary" href={`/oauth/google/start?mode=connect&email=${encodeURIComponent(email)}`}><Icon name="shield" size={17} /> Conectar con Google</a>
  if (!url) return <button className="btn-primary" onClick={() => void empezar()} disabled={busy}><Icon name="shield" size={17} /> {busy ? 'Preparando…' : 'Dar permisos'}</button>
  return <div className="steps-box">
    <ol>
      <li>Abre Google y acepta los permisos con <b>{email}</b>.</li>
      <li>Al terminar, el navegador irá a una página que <b>no carga</b> (empieza por <code>127.0.0.1</code>). Es normal.</li>
      <li>Copia la dirección completa de esa página y pégala aquí.</li>
    </ol>
    <a className="btn-secondary" href={url} target="_blank" rel="noopener noreferrer"><Icon name="arrow" size={16} /> Abrir Google</a>
    <input value={back} onChange={e => setBack(e.target.value)} placeholder="http://127.0.0.1:…/oauth…?code=…" aria-label="Dirección de vuelta de Google" inputMode="url" />
    <div style={{ display: 'flex', gap: 8 }}><button className="btn-secondary" onClick={() => { setUrl(''); setBack('') }}>Cancelar</button>
      <button className="btn-primary" disabled={!back.includes('code=') || busy} onClick={() => void terminar()}><Icon name="check" size={17} /> Terminar</button></div>
  </div>
}

/** soloGoogle: dentro de la guía de bienvenida (sin personas, sin WhatsApp: ahí ya sale su tarjeta). */
export default function CuentasScreen({ toast, soloGoogle = false }: Ctx & { soloGoogle?: boolean }) {
  const { data, loading, error, reload } = useFetch<Cuentas>('/api/cuentas')
  const [nueva, setNueva] = useState(''); const [adding, setAdding] = useState(false)
  const ok = /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(nueva.trim())
  const anadir = data?.google.length ? 'Añadir otra cuenta de Google' : 'Conectar una cuenta de Google'

  return <div className="settings-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">CONEXIONES</span><h2>Tus cuentas<span className="greeting-dot">.</span></h2><p>Lo que Zazu y esta app pueden usar.</p></div>
    {error && <div className="fallo" role="alert"><span>No pude leer tus cuentas.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    {loading && !data && <div className="empty-radar">Cargando…</div>}

    <div className="settings-group"><span className="section-kicker">GOOGLE</span>
      {(data?.google || []).map(c => {
        const falta = SERV.filter(([k]) => !c.services.includes(k))
        return <div className="acc-card" key={c.email}>
          <div className="acc-top"><span className={`sender-avatar ${toneOf(c.email)}`}>{initials(c.email.split('@')[0])}</span><div><strong>{c.email}</strong><small>{c.error ? 'Hay un problema con el acceso' : falta.length ? `Le faltan ${falta.length} permisos` : 'Todo conectado'}</small></div></div>
          <div className="chips">{SERV.map(([k, n]) => <span key={k} className={`chip ${c.services.includes(k) ? '' : 'no'}`}>{c.services.includes(k) ? '✓' : '＋'} {n}</span>)}</div>
          {(falta.length > 0 || c.error) ? <Permiso email={c.email} onDone={reload} toast={toast} web={data?.google_web} />
            : data?.google_web && <a className="text-link" href={`/oauth/google/start?mode=connect&email=${encodeURIComponent(c.email)}`}>Reconectar con Google <Icon name="arrow" size={15} /></a>}
        </div>
      })}
      {data?.google_web ? <a className="btn-secondary" href="/oauth/google/start?mode=connect"><Icon name="plus" size={17} /> {anadir}</a> : !adding ? <button className="btn-secondary" onClick={() => setAdding(true)}><Icon name="plus" size={17} /> {anadir}</button>
        : <div className="acc-card"><input className="date-input" style={{ minHeight: 44, border: '1px solid #dbe5d2', borderRadius: 12, padding: '0 12px', fontSize: 15 }} value={nueva} onChange={e => setNueva(e.target.value)} placeholder="tu.correo@gmail.com" type="email" aria-label="Correo de la cuenta" />
          {ok ? <Permiso email={nueva.trim().toLowerCase()} onDone={() => { setAdding(false); setNueva(''); void reload() }} toast={toast} /> : <small>Escribe el correo de la cuenta.</small>}</div>}
    </div>

    {!soloGoogle && <><Personas toast={toast} />

    <div className="settings-group"><span className="section-kicker">WHATSAPP</span>
      <TarjetaWhatsAppFran toast={toast} />
      <p className="muted-note">Zazu solo lee tu WhatsApp: no envía nada sin que tú lo pidas. Al vincularlo o desconectarlo, lo de antes se guarda en Respaldos.</p></div>

    <div className="settings-group"><span className="section-kicker">CÓMO LO USA ZAZU</span><div className="settings-list">
      <div className="setting-row informational"><span className="setting-icon"><Icon name="spark" size={19} /></span><span className="setting-copy"><strong>Mismas cuentas, mismas reglas</strong>
        <small>Zazu usa estos permisos para tus resúmenes y rutinas. El correo nunca se envía solo: solo lee y deja borradores.</small></span></div>
    </div></div></>}
  </div>
}
