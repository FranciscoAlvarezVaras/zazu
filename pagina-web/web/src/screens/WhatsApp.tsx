import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Icon } from '../icons'
import { api, initials, post, relTime, toneOf, useAtrasCierra, useFetch } from '../lib'
import type { WaChat } from '../lib'
import type { Ctx } from '../ctx'
import { copiar } from '../chat/Acciones'

const TIPO: Record<string, string> = { dm: 'Chat', group: 'Grupo', newsletter: 'Canal', broadcast: 'Difusión', status: 'Estados' }
const tipo = (c: WaChat) => TIPO[c.kind] || (/@g\.us$/.test(c.jid) ? 'Grupo' : /@newsletter$/.test(c.jid) ? 'Canal' : /@broadcast$/.test(c.jid) ? 'Difusión' : /@call$/.test(c.jid) ? 'Llamadas' : /@(s\.whatsapp\.net|lid)$/.test(c.jid) ? 'Chat' : 'Otro')
/** Número de teléfono (solo chats individuales; los @lid no llevan número). */
const numero = (c: WaChat) => /^(\d{6,15})(?::\d+)?@s\.whatsapp\.net$/.exec(c.jid)?.[1] || ''
/** Chats que Zazu puede leer (lo mismo que acepta el servidor en ctx «wa:»); canales y llamadas, no. */
const legible = (c: WaChat) => /^\d{5,20}@(s\.whatsapp\.net|g\.us|lid)$/.test(c.jid)
/** wa.me abre WhatsApp con el texto puesto; nunca envía nada. Sin número, WhatsApp deja elegir el chat. */
const waLink = (c: WaChat, txt: string) => `https://wa.me/${numero(c)}?text=${encodeURIComponent(txt)}`

const PIDE = 'Con el chat de WhatsApp de arriba, escribe la respuesta que yo mandaría: breve y en mi tono. Contesta SOLO con el texto del mensaje, listo para enviar: sin comillas, sin explicaciones y sin varias opciones. No envíes nada.'
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
type JobR = { session_id?: string | null; profile?: string; done?: boolean; error?: string | null }

/** Pide a Zazu un borrador y espera la respuesta aquí mismo, sin salir de la pantalla. */
async function pedirBorrador(c: WaChat) {
  const r = await post<{ job: string | null; nota?: string }>('/api/send', { text: PIDE, session: null, profile: 'default', ctx: `wa:${c.jid}` })
  if (!r.job) throw new Error(r.nota || 'Zazu no pudo prepararlo')
  for (let i = 0; i < 150; i++) {
    await sleep(2000)
    let j: JobR
    try { j = await api<JobR>(`/api/job?id=${r.job}`) } catch { continue }
    if (!j.done) continue
    if (j.error || !j.session_id) throw new Error(j.error || 'Zazu no pudo prepararlo')
    const ms = await api<{ role: string; content: string }[]>(`/api/messages?session=${encodeURIComponent(j.session_id)}&profile=${encodeURIComponent(j.profile || 'default')}`)
    const t = [...ms].reverse().find(m => m.role === 'assistant' && (m.content || '').trim())?.content || ''
    const limpio = t.replace(/^MEDIA:.*$/gm, '').trim().replace(/^["«“]+|["»”]+$/g, '').trim()
    if (!limpio) throw new Error('Zazu no devolvió texto')
    return limpio
  }
  throw new Error('Zazu está tardando; lo verás luego en Chat')
}

// los borradores sobreviven a cambiar de pantalla (no al recargar)
const BORR: Record<string, string> = {}
const DE_ZAZU: Record<string, string> = {}   // el último borrador que escribió Zazu (si Fran lo cambia, ya es suyo)
const PENSANDO = new Set<string>()

/** Hoja inferior (en el móvil) o diálogo centrado (en el ordenador). Va en <body> para no heredar la animación de la pantalla. */
function Hoja({ titulo, cerrar, children }: { titulo: string; cerrar: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const fin = useRef(cerrar); fin.current = cerrar
  const y0 = useRef<number | null>(null)
  useEffect(() => {
    const antes = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') fin.current() }
    addEventListener('keydown', k)
    return () => { removeEventListener('keydown', k); antes?.focus?.() }
  }, [])
  return createPortal(<div className="wa-hoja-fondo" onClick={cerrar}>
    <div className="wa-hoja" role="dialog" aria-modal="true" aria-label={titulo} tabIndex={-1} ref={ref} onClick={e => e.stopPropagation()}>
      <div className="wa-hoja-arrastre" onTouchStart={e => { y0.current = e.touches[0].clientY }} onTouchEnd={e => { if (y0.current !== null && e.changedTouches[0].clientY - y0.current > 70) cerrar(); y0.current = null }}><span className="wa-hoja-asa" aria-hidden="true" /></div>
      <button className="wa-hoja-cerrar" onClick={cerrar} aria-label="Cerrar"><Icon name="close" size={18} /></button>
      {children}
    </div></div>, document.body)
}

export default function WhatsApp({ ask, toast }: Ctx) {
  const [n, setN] = useState(8)
  const { data, loading, error, reload } = useFetch<WaChat[]>(`/api/whatsapp?n=${n}`)
  const [sel, setSel] = useState<string | null>(null)
  const [borr, setBorr] = useState<Record<string, string>>(() => ({ ...BORR }))
  const [pensando, setPensando] = useState<string[]>(() => [...PENSANDO])
  const chats = data || []
  const act = chats.find(c => c.jid === sel)
  const sin = chats.filter(c => c.unread > 0).length
  const fallo = !!error && !data
  useAtrasCierra(!!act, () => setSel(null))   // el Atrás del móvil cierra la hoja del chat, no la pantalla

  const escribir = (jid: string, t: string) => { BORR[jid] = t; setBorr(b => ({ ...b, [jid]: t })) }
  /** Lo escrito a mano por Fran (no es el borrador de Zazu tal cual). */
  const suyo = (jid: string) => !!(borr[jid] || '').trim() && borr[jid] !== DE_ZAZU[jid]
  async function preparar(c: WaChat) {
    if (suyo(c.jid) && !confirm('Zazu escribirá un borrador nuevo en lugar de lo que has escrito tú. ¿Seguimos?')) return
    PENSANDO.add(c.jid); setPensando([...PENSANDO])
    try { const t = await pedirBorrador(c); DE_ZAZU[c.jid] = t; escribir(c.jid, t); toast(`Borrador listo para ${c.name}`) }
    catch (e) { toast(`No se pudo preparar: ${(e as Error).message}`) }
    finally { PENSANDO.delete(c.jid); setPensando([...PENSANDO]) }
  }
  async function copiarBorrador(t: string) {
    try { await copiar(t); toast('Borrador copiado') } catch { toast('No se pudo copiar') }
  }

  return <div className="extra-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">CONVERSACIONES EN ORDEN</span><h2>WhatsApp<span className="greeting-dot">.</span></h2><p>Ponte al día sin perder el hilo.</p></div>
    <div className="demo-label"><Icon name="shield" size={14} /> SOLO LECTURA · NADA SE ENVÍA SOLO</div>
    <div className="whatsapp-hero"><span className="whatsapp-hero-icon"><Icon name="chat" size={25} /></span><span className="feature-label"><span className="feature-label-dot" /> TU RESUMEN</span>
      <h3>Conecta con<br />lo importante.</h3><p>{fallo ? 'Ahora mismo no puedo leer tus chats.' : loading && !data ? 'Leyendo tus chats…' : `${sin} ${sin === 1 ? 'conversación con mensajes' : 'conversaciones con mensajes'} sin leer.`}</p></div>
    <div className="section-heading extra-section-heading"><div><span className="section-kicker">CONVERSACIONES</span><h3>Lo más reciente</h3></div>{!fallo && <span className="count-pill">{chats.length} chats</span>}</div>
    {error && <div className="fallo" role="alert"><span>No pude leer WhatsApp{data ? ': lo de abajo puede no estar al día' : ''}.</span><button type="button" className="reintentar" onClick={() => void reload()}>Reintentar</button></div>}
    {chats.length > 0 && <div className="insight-list">{chats.map(c => <button className="insight-row" key={c.jid} onClick={() => setSel(c.jid)} aria-haspopup="dialog">
      <span className={`sender-avatar ${toneOf(c.name)}`}>{initials(c.name)}</span>
      <span className="insight-row-copy"><span className="insight-row-top"><strong>{c.name}</strong><small>{relTime(c.ts)}</small></span><b>{c.text ? `${c.fromMe ? 'Tú: ' : ''}${c.text}` : '(sin texto)'}</b>
        <small>{tipo(c) !== 'Chat' && <span className="acc-tag">{tipo(c)}</span>}{c.unread ? `${c.unread} sin leer` : tipo(c) === 'Chat' ? 'Chat' : ''}{borr[c.jid] ? ' · borrador guardado' : ''}</small></span>
      {c.unread > 0 ? <span className="unread-dot" role="img" aria-label="sin leer" /> : <Icon name="chevron" size={16} />}</button>)}</div>}
    {!loading && !error && !chats.length && <div className="empty-radar">No hay conversaciones recientes.</div>}
    {chats.length >= n && n < 50 && <button className="btn-secondary wa-mas" disabled={loading} onClick={() => setN(Math.min(50, n + 12))}>{loading ? 'Cargando…' : 'Ver más chats'}</button>}

    {act && <Hoja titulo={`Chat con ${act.name}`} cerrar={() => setSel(null)}>
      <div className="wa-hoja-cab"><span className={`sender-avatar ${toneOf(act.name)}`}>{initials(act.name)}</span>
        <div><h3>{act.name}</h3><small>{tipo(act)}{act.ts ? ` · ${relTime(act.ts)}` : ''}{act.unread ? ` · ${act.unread} sin leer` : ''}</small></div></div>
      <div className="wa-hoja-caja"><span className="section-kicker">ÚLTIMO MENSAJE</span>
        <p>{act.text ? `${act.fromMe ? 'Tú: ' : ''}${act.text}` : 'Sin texto (puede ser una foto, un audio o una llamada).'}</p></div>
      {!legible(act) ? <p className="muted-note">{tipo(act) === 'Canal' ? 'Es un canal: solo se puede leer en WhatsApp.' : 'Zazu no puede leer este chat.'}</p> : <>
        <div className="wa-hoja-acciones">
          <button onClick={() => { setSel(null); ask('Resume en pocas líneas el chat de WhatsApp de arriba y dime si espera respuesta mía. No envíes nada.', { ctx: `wa:${act.jid}` }) }}><Icon name="spark" size={15} /> Resumir con Zazu</button>
          <button className="claro" disabled={pensando.includes(act.jid)} onClick={() => void preparar(act)}><Icon name="pen" size={15} /> {pensando.includes(act.jid) ? 'Zazu está escribiendo…' : borr[act.jid] && !suyo(act.jid) ? 'Otro borrador' : 'Preparar respuesta'}</button>
        </div>
        <label className="wa-hoja-borrador">Tu borrador
          <textarea value={borr[act.jid] || ''} onChange={e => escribir(act.jid, e.target.value)} readOnly={pensando.includes(act.jid)} rows={4} maxLength={4000} placeholder="Escribe aquí o pulsa «Preparar respuesta» y Zazu te lo deja escrito." /></label>
        {(borr[act.jid] || '').trim() && <>
          <a className="btn-primary" href={waLink(act, borr[act.jid].trim())} target="_blank" rel="noopener noreferrer"><Icon name="arrow" size={17} /> {numero(act) ? 'Abrir en WhatsApp con este borrador' : 'Abrir WhatsApp con este borrador'}</a>
          <button className="text-link wa-hoja-copiar" onClick={() => void copiarBorrador(borr[act.jid].trim())}>Copiar borrador</button></>}
        <p className="muted-note">Nada se envía solo: WhatsApp se abre con el texto puesto{numero(act) ? '' : ', eliges tú el chat'} y tú decides si lo mandas.</p>
      </>}
    </Hoja>}
  </div>
}
