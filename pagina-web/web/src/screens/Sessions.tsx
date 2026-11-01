import { useState } from 'react'
import { Icon } from '../icons'
import { relTime, vistaPrevia } from '../lib'
import type { Session } from '../lib'
import { esEstilo } from '../tipos'
import type { ChatApi } from '../tipos'

/** De dónde viene la conversación, en palabras de Fran */
export const origenDe = (src = '') => ({ hub: 'App', '': 'App', api_server: 'App', whatsapp: 'WhatsApp', cron: 'Automática' } as Record<string, string>)[src] || 'Ordenador'
/** Título de una conversación (lista del cajón y cabecera). */
/** Un título que empieza con «[DATOS recogidos…» es el bloque de datos de una acción rápida, no algo que escribiera Fran: no vale. */
export const tituloSesion = (s: Session) => /organizar-agenda/.test(`${s.title || ''} ${s.preview || ''}`.slice(0, 80)) ? '📅 Organizar mi agenda' : (s.title && !s.title.startsWith('[DATOS recogidos') ? s.title : '') || s.display_name || vistaPrevia(s.preview || '').slice(0, 48) || 'Sin título'
/** Nombre del estilo en la etiqueta: «Charla», no «charla». */
const nombrePerfil = (p: string) => p[0].toUpperCase() + p.slice(1)
const sinTildes = (t: string) => t.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
const DIA = 86400
/** Grupo por la última actividad (`last`, en segundos). */
const GRUPOS = ['Hoy', 'Ayer', 'Últimos 7 días', 'Antes']
const grupoDe = (last: number, hoy0: number) => GRUPOS[last >= hoy0 ? 0 : last >= hoy0 - DIA ? 1 : last >= hoy0 - 6 * DIA ? 2 : 3]

/** Historial de conversaciones: recientes (agrupadas por día si `agrupar`) y las rutinas automáticas en un grupo plegable.
 *  `buscar` lo pone quien la usa (el cajón de una invitada o la hoja «Conversaciones» de Fran). Al tocar una, se abre y se avisa con `onPick`. */
export default function Sessions({ chat, onPick, limit = 40, buscar = '', agrupar = false }: { chat: ChatApi; onPick: (s: Session) => void; limit?: number; buscar?: string; agrupar?: boolean }) {
  const [auto, setAuto] = useState(false)
  const q = sinTildes(buscar.trim())
  const vale = (s: Session) => !q || sinTildes(`${s.title || ''} ${s.display_name || ''} ${s.preview || ''}`).includes(q)
  const lista = chat.sessions.filter(vale)
  const rec = lista.filter(s => s.source !== 'cron').slice(0, limit)
  const aut = lista.filter(s => s.source === 'cron').slice(0, 12)
  const verAut = auto || !!q   // al buscar, lo que coincide también se ve

  const fila = (s: Session) => {
    const on = chat.cur.id === s.id && chat.cur.profile === s.profile
    const o = origenDe(s.source)
    return <li key={`${s.profile}/${s.id}`}>
      <button type="button" className={`hist ${on ? 'on' : ''}`} aria-current={on ? 'true' : undefined} onClick={() => { void chat.open(s.id, s.profile, s.source); onPick(s) }}>
        <span className="hist-top">
          <strong>{tituloSesion(s)}</strong>
          {s.busy && <span className="hist-ocupada" role="img" aria-label="respondiendo" />}
          <span className="hist-hora">{relTime(s.last * 1000)}</span>
        </span>
        <span className="hist-sub">
          {o !== 'App' && <span className={`hist-tag origen-${o === 'WhatsApp' ? 'wa' : o === 'Ordenador' ? 'pc' : 'auto'}`}>{o}</span>}
          {esEstilo(s.profile) && <span className="hist-tag">{nombrePerfil(s.profile)}</span>}
          <small>{vistaPrevia(s.preview || '') || ' '}</small>
        </span>
      </button>
    </li>
  }

  let grupos: [string, Session[]][] = [['', rec]]
  if (agrupar) {
    const d = new Date(); d.setHours(0, 0, 0, 0)
    const hoy0 = d.getTime() / 1000
    grupos = GRUPOS.map(g => [g, []] as [string, Session[]])
    for (const s of rec) grupos[GRUPOS.indexOf(grupoDe(s.last || 0, hoy0))][1].push(s)
  }

  return <div className="hist-lista">
    {grupos.map(([g, ss]) => ss.length > 0 && <section key={g || 'todas'} aria-label={g || 'Conversaciones'}>
      {g && <h3 className="hist-grupo">{g}</h3>}
      <ul>{ss.map(fila)}</ul>
    </section>)}
    {!rec.length && !aut.length && <p className="hist-vacio">{q ? `Nada coincide con «${buscar.trim()}».` : 'Aún no hay conversaciones.'}</p>}
    {aut.length > 0 && <section aria-label="Automáticas">
      <button type="button" className="hist-grupo hist-plegable" onClick={() => setAuto(!auto)} aria-expanded={verAut}><Icon name="chevron" size={14} /> Automáticas · {aut.length}</button>
      {verAut && <ul>{aut.map(fila)}</ul>}
    </section>}
  </div>
}
