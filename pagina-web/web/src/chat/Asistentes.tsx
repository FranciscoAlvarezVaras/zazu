import { Hoja } from '../panel/ui'
import { PROFILE_HINTS, PROFILE_NAMES } from '../data'
import { irA } from '../lib'
import { esEstilo, PERFIL_HERMES } from '../tipos'
import type { ChatApi } from '../tipos'

/** Los asistentes de Fran: Zazu (el chat normal, con todas las herramientas y permisos) y los de un solo oficio
 *  (Viajes, Escritor, Investigador, Charla…: los perfiles «estilo», sin tarjetas de permiso). */
export type Asistente = { id: string; nombre: string; corto: string; pista: string; principal: boolean }
const cap = (s: string) => s[0].toUpperCase() + s.slice(1)
export function asistentesDe(chat: ChatApi): Asistente[] {
  const zazu: Asistente = { id: PERFIL_HERMES, nombre: 'Zazu', corto: 'Zazu', pista: 'El de siempre: correo, agenda, archivos, web y permisos.', principal: true }
  const otros = chat.profiles.filter(esEstilo).map(p => {
    const nombre = PROFILE_NAMES[p] || cap(p)
    return { id: p, nombre, corto: nombre.replace(/^Zazu\s+/i, '').replace(/\s+ligera$/i, ''), pista: PROFILE_HINTS[p] || 'Para una conversación más ligera o especializada', principal: false }
  })
  return [zazu, ...otros]
}
/** Empieza una conversación nueva con ese asistente (Fran). Sin go(): la URL ya lleva al chat. */
export function empezarCon(chat: ChatApi, id: string) {
  chat.newChat(id)
  irA({ tab: 'chat', perfil: esEstilo(id) ? id : undefined })
}
export const asistenteActual = (chat: ChatApi) => asistentesDe(chat).find(a => a.id === chat.cur.profile)

/** Fila de chips bajo el saludo del chat: toca uno y empiezas con él. El de la conversación actual va marcado. */
export function FilaAsistentes({ chat }: { chat: ChatApi }) {
  const lista = asistentesDe(chat)
  if (lista.length < 2) return null
  return <div className="asistentes" role="group" aria-label="Con quién hablas">
    {lista.map(a => <button key={a.id} type="button" className="asistente-chip" aria-pressed={a.id === chat.cur.profile} title={a.pista}
      onClick={() => { if (a.id !== chat.cur.profile || chat.cur.id) empezarCon(chat, a.id) }}>{a.corto}</button>)}
  </div>
}

/** Chip de la barra del chat con el asistente de esta conversación; al pulsarlo abre la hoja para cambiar (empieza otra conversación). */
export function ChipAsistente({ chat, onClick }: { chat: ChatApi; onClick(): void }) {
  const a = asistenteActual(chat)
  if (!a || chat.cur.profile === 'default') return null   // las conversaciones antiguas no cambian de asistente
  // con Zazu ya está el título (y el chip del modelo): un botón pequeño, para que desde cualquier conversación se llegue a los demás
  if (a.principal) return <button type="button" className="chatbar-btn chatbar-asistentes" onClick={onClick} aria-haspopup="dialog" aria-label="Asistentes: Viajes, Empleo, Compras…" title="Asistentes"><span aria-hidden="true">✦</span></button>
  return <button type="button" className="hz-chip hz-chip-asistente oficio" onClick={onClick} aria-haspopup="dialog" title="Cambiar de asistente">
    <span aria-hidden="true">✦</span> {a.corto}
  </button>
}

/** Hoja «Asistente»: la lista con su explicación. Elegir empieza una conversación nueva con él y cierra la hoja. */
export function HojaAsistentes({ abierto, cerrar, chat }: { abierto: boolean; cerrar(): void; chat: ChatApi }) {
  if (!abierto) return null
  const lista = asistentesDe(chat)
  return <Hoja titulo="¿Con quién hablas?" id="asistentes" cerrar={cerrar}>
    <div className="hz-modelos">
      <div className="hz-modelos-lista" role="radiogroup" aria-label="Asistente">
        {lista.map(a => {
          const on = a.id === chat.cur.profile
          return <button key={a.id} type="button" role="radio" aria-checked={on} className="hz-modelo" {...(on ? { 'data-foco': true } : {})}
            onClick={() => { cerrar(); if (!on || chat.cur.id) empezarCon(chat, a.id) }}>
            <span className="hz-modelo-radio" aria-hidden="true" />
            <span className="hz-modelo-txt"><strong>{a.nombre}</strong><small>{a.pista}</small></span>
          </button>
        })}
      </div>
      <p className="hz-modelos-pie">Cada asistente empieza una conversación nueva. Los permisos solo se piden en el chat con Zazu.</p>
    </div>
  </Hoja>
}
