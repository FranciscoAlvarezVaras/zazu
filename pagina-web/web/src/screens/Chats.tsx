/* Pestaña Chats: con quién hablas, como la lista de mensajes del móvil. Zazu arriba (fijado), «Zazu por WhatsApp» si hay
   conversaciones por ahí y cada asistente de un oficio, con lo último dicho. Tocar uno abre su chat seguido (?tab=chat&contacto=…).
   Una invitada ve solo su asistente. */
import { useEffect, useRef, useState } from 'react'
import { PROFILE_HINTS, PROFILE_NAMES } from '../data'
import { LogoZazu } from '../icons'
import { api, irA, relTime } from '../lib'
import type { Ctx } from '../ctx'
import { Icono } from '../panel/ui'
import { PERFIL_HERMES } from '../tipos'
import '../chats.css'

/** Un chat de la lista (lo da /api/chats). `id`: «tecnico» (Zazu), «whatsapp» o el perfil del asistente. */
export type Contacto = { id: string; profile: string; modo: 'hermes' | 'zazu'; fuente: string | null; sesion: string | null; last: number | null; preview: string; de: 'tu' | 'zazu' | null; busy: boolean; nuevos?: number }

const corto = (s: string) => s.replace(/^Zazu\s+/i, '').replace(/\s+ligera$/i, '')
/** Cómo se llama ese chat: Zazu, Zazu por WhatsApp, Viajes… (una invitada: su asistente). */
export const nombreContacto = (id: string, guest?: boolean, asistente?: string) =>
  id === 'whatsapp' ? `${guest ? asistente || 'Zazu' : 'Zazu'} por WhatsApp` : guest ? asistente || 'Zazu' : id === PERFIL_HERMES ? 'Zazu' : corto(PROFILE_NAMES[id] || id)
/** Una línea sobre qué hace. */
export const pistaContacto = (id: string, guest?: boolean, asistente?: string) =>
  id === 'whatsapp' ? 'Lo que habláis por WhatsApp: aquí solo se lee' : guest ? `Soy ${asistente || 'Zazu'}. ¿En qué te ayudo hoy?` : id === PERFIL_HERMES ? 'El de siempre: correo, agenda, archivos, web y permisos' : PROFILE_HINTS[id] || ''

/** La cara del chat: el logo para Zazu (y los asistentes de invitadas), verde para WhatsApp, la inicial para los demás. */
export function CaraContacto({ c, tam = 50 }: { c: Pick<Contacto, 'id' | 'profile' | 'modo'>; tam?: number }) {
  const estilo = { width: tam, height: tam }
  if (c.id === 'whatsapp') return <span className="chats-cara wa" style={estilo} aria-hidden="true"><Icono n="chat" size={Math.round(tam / 2)} /></span>
  if (c.modo === 'hermes' || /^zi/.test(c.profile)) return <span className="chats-cara zazu" style={estilo} aria-hidden="true"><LogoZazu tam={tam - 6} /></span>
  return <span className="chats-cara letra" style={estilo} aria-hidden="true">{corto(PROFILE_NAMES[c.id] || c.id)[0].toUpperCase()}</span>
}

export default function Chats(p: Ctx) {
  const [lista, setLista] = useState<Contacto[] | null>(null)
  const [filtro, setFiltro] = useState('')
  const [fallo, setFallo] = useState(false)
  const recargar = useRef<() => void>(() => {})
  useEffect(() => {
    let vivo = true
    const cargar = () => api<Contacto[]>('/api/chats').then(l => { if (vivo) { setLista(l); setFallo(false) } }).catch(() => { if (vivo) setFallo(true) })   // se reintenta cada 20 s
    recargar.current = cargar
    cargar()
    const t = setInterval(() => { if (!document.hidden) cargar() }, 20000)
    const vis = () => { if (!document.hidden) cargar() }
    document.addEventListener('visibilitychange', vis)
    return () => { vivo = false; clearInterval(t); document.removeEventListener('visibilitychange', vis) }
  }, [])
  const nombre = (c: Contacto) => nombreContacto(c.id, p.guest, p.me.asistente)
  const abrir = (c: Contacto) => irA({ tab: 'chat', contacto: c.id })
  const q = filtro.trim().toLowerCase()
  const visibles = (lista || []).filter(c => !q || nombre(c).toLowerCase().includes(q) || c.preview.toLowerCase().includes(q))
  const fijo = (c: Contacto) => c.id === PERFIL_HERMES || !!p.guest   // Zazu (y el asistente de una invitada) siempre como fila, aunque no haya nada aún
  // Zazu fijado arriba; el resto, el más reciente primero (como una lista de mensajes)
  const conMensajes = visibles.filter(c => c.sesion || c.last || fijo(c)).sort((a, b) => Number(fijo(b)) - Number(fijo(a)) || (b.last || 0) - (a.last || 0))
  const sinEmpezar = visibles.filter(c => !c.sesion && !c.last && !fijo(c))
  return <div className="chats">
    <h1 className="visually-hidden">Chats</h1>
    {(lista?.length || 0) > 3 && <label className="chats-buscar"><Icono n="search" size={18} />
      <input type="search" value={filtro} onChange={e => setFiltro(e.target.value)} placeholder="Buscar en los chats" aria-label="Buscar en los chats" /></label>}
    {lista === null && !fallo && <p className="chats-vacio">Cargando…</p>}
    {fallo && <p className="chats-vacio" role="alert">{lista === null ? 'No pude cargar tus chats.' : 'No pude actualizar la lista: puede estar desfasada.'} <button type="button" className="pz-enlace" onClick={() => recargar.current()}>Reintentar</button></p>}
    {lista !== null && !visibles.length && <p className="chats-vacio">{q ? 'Ningún chat se llama así.' : 'Aún no hay chats.'}</p>}
    <ul className="chats-lista">
      {conMensajes.map(c => <li key={c.id}><button type="button" className={`chats-fila ${c.nuevos ? 'con-nuevos' : ''}`} onClick={() => abrir(c)}>
        <CaraContacto c={c} />
        <span className="chats-txt">
          <span className="chats-nombre">{nombre(c)}{c.id === PERFIL_HERMES && !p.guest && <span className="chats-fijado" role="img" aria-label="fijado">★</span>}</span>
          <span className="chats-ultimo">{c.busy ? 'Respondiendo…' : `${c.de === 'tu' ? 'Tú: ' : ''}${c.preview || 'Sin mensajes'}`}</span>
        </span>
        <span className="chats-hora">{c.busy ? <span className="sd ok pulse" role="img" aria-label="respondiendo" /> : relTime(c.last)}
          {!!c.nuevos && <span className="chats-nuevos" aria-label={`${c.nuevos} sin leer`}>{c.nuevos}</span>}</span>
      </button></li>)}
    </ul>
    {sinEmpezar.length > 0 && <>
      <h2 className="chats-sub">Sin empezar</h2>
      <div className="chats-chips">{sinEmpezar.map(c => <button key={c.id} type="button" className="chats-chip" onClick={() => abrir(c)} title={pistaContacto(c.id, p.guest, p.me.asistente)}>{nombre(c)}</button>)}</div>
    </>}
  </div>
}
