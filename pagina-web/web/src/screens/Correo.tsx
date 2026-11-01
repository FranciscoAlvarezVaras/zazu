import { useState } from 'react'
import { Icon } from '../icons'
import { MAIL_ADDR } from '../data'
import { initials, nombreAsistente, post, relTime, toneOf, useFetch } from '../lib'
import type { Mail } from '../lib'
import type { Ctx } from '../ctx'

export default function Correo({ ask, toast, guest, nombre }: Ctx) {
  const quien = nombreAsistente(guest, nombre)
  const { data, error, reload } = useFetch<Mail[]>('/api/correo')
  const [sel, setSel] = useState<string | null>(null)
  const [hechos, setHechos] = useState<string[]>([])
  const mails = data || []
  const act = mails.find(m => m.id === sel) || mails[0]
  const urgentes = mails.filter(m => m.important && m.unread).length
  const fallo = !!error && !data   // sin datos: nunca decir «Bandeja tranquila»

  async function tarea(m: Mail) {
    try { await post('/api/tareas', { action: 'add', title: `Responder: ${m.subject}` }); setHechos(h => [...h, m.id]); toast('Añadido a tus tareas') }
    catch (e) { toast(`No se pudo crear la tarea: ${(e as Error).message}`) }
  }

  return <div className="extra-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">MENOS RUIDO, MÁS CLARIDAD</span><h2>Tus correos<span className="greeting-dot">.</span></h2><p>Lo importante llega primero.</p></div>
    <div className="demo-label"><Icon name="shield" size={14} /> SOLO LECTURA · {guest ? '' : 'DOS CUENTAS · '}ÚLTIMOS 3 DÍAS</div>
    <div className="insight-hero"><span className="insight-hero-icon"><Icon name="mail" size={23} /></span><span className="feature-label"><span className="feature-label-dot" /> RESUMEN DE TU BANDEJA</span>
      <h3>{fallo ? <>No pude leer<br />tu correo.</> : !data ? <>Mirando<br />tu bandeja…</> : urgentes ? <>Hay algo que<br />merece tu atención.</> : mails.length ? <>Bandeja<br />tranquila.</> : <>Nada nuevo<br />estos días.</>}</h3>
      <p>{fallo ? 'Puede ser la conexión o el permiso de Google. Pulsa Reintentar.' : !data ? 'Leyendo tus cuentas…' : `${urgentes} ${urgentes === 1 ? 'correo importante sin leer' : 'correos importantes sin leer'} de ${mails.length}.`}</p></div>
    <div className="section-heading extra-section-heading"><div><span className="section-kicker">BANDEJA EN CLARO</span><h3>Lo que ha llegado</h3></div>{data && <span className="count-pill">{mails.filter(m => m.unread).length} sin leer</span>}</div>
    {error && <div className="fallo" role="alert"><span>No pude leer el correo{data ? ': lo de abajo puede no estar al día' : ''}.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    {data && !mails.length && <div className="empty-radar">No ha llegado nada en los últimos 3 días.</div>}
    {mails.length > 0 && <div className="insight-list">{mails.map(m => <button className={`insight-row ${act?.id === m.id ? 'insight-selected' : ''}`} key={`${m.account}${m.id}`} onClick={() => setSel(m.id)}>
      <span className={`sender-avatar ${toneOf(m.from)}`}>{initials(m.from)}</span>
      <span className="insight-row-copy"><span className="insight-row-top"><strong>{m.from}</strong><small>{relTime(m.date)}</small></span><b>{m.subject}</b><small>{guest ? '' : `[${m.account}]`}{m.count > 1 ? `${guest ? '' : ' · '}${m.count} mensajes` : ''}</small></span>
      {m.unread && <span className="unread-dot" role="img" aria-label="sin leer" />}</button>)}
    </div>}
    {act && <div className="analysis-card"><span className="analysis-kicker"><Icon name="spark" size={15} /> LECTURA RÁPIDA · {act.important ? 'ALTA PRIORIDAD' : act.unread ? 'PARA REVISAR' : 'SIN PRISA'}</span>
      <h3>{act.subject}</h3><p>De {act.from}{guest ? '' : ` · cuenta ${act.account}`}. Pídele a {quien} que lo lea y te diga si espera algo de ti.</p>
      <div className="analysis-actions">
        <button onClick={() => ask(guest ? `Mira mis correos recientes con tus herramientas de Google y resúmeme en tres líneas el de «${act.subject}» de ${act.from}. Dime si espera respuesta o algo de mí.` : `Resume en tres líneas el correo de arriba («${act.subject}», de ${act.from}, cuenta ${act.account}). Dime si espera respuesta o acción mía y con qué plazo. No envíes nada.`, guest ? undefined : { ctx: `hilo:${act.account}:${act.id}` })}><Icon name="spark" size={15} /> Resumir con {quien}</button>
        <button onClick={() => void tarea(act)} disabled={hechos.includes(act.id)}><Icon name="plus" size={15} /> {hechos.includes(act.id) ? 'Tarea creada' : 'Crear tarea'}</button>
        <a className="btn-link" href={guest ? `https://mail.google.com/mail/#all/${act.id}` : `https://mail.google.com/mail/?authuser=${MAIL_ADDR[act.account]}#all/${act.id}`} target="_blank" rel="noopener noreferrer">Abrir en Gmail</a>
      </div></div>}
  </div>
}
