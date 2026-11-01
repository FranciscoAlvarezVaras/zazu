import { useEffect, useRef, useState } from 'react'
import { Icon } from '../icons'
import { useAtrasCierra } from '../lib'
import { esEstilo } from '../tipos'
import type { ChatApi } from '../tipos'
import { PROFILE_NAMES } from '../data'
import { ChipModelo } from './Modelos'
import { ChipAsistente } from './Asistentes'
import { BotonMenu } from '../panel/ui'

/** Menú «⋯» de la conversación: Nueva conversación (lo de WhatsApp se quitó). Se cierra con Atrás, Esc o tocando fuera. */
export function MenuHilo({ nueva }: { nueva: () => void }) {
  const [abierto, setAbierto] = useState(false)
  const caja = useRef<HTMLDivElement>(null)
  const boton = useRef<HTMLButtonElement>(null)
  const cerrar = () => setAbierto(false)
  useAtrasCierra(abierto, cerrar)
  useEffect(() => {
    if (!abierto) return
    caja.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus()
    const fuera = (e: PointerEvent) => { if (!caja.current?.contains(e.target as Node)) cerrar() }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { cerrar(); boton.current?.focus() } }
    document.addEventListener('pointerdown', fuera); addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', fuera); removeEventListener('keydown', esc) }
  }, [abierto])
  return <div className="hilo-menu" ref={caja}>
    <button type="button" ref={boton} className="hilo-mas" onClick={() => setAbierto(!abierto)} aria-haspopup="menu" aria-expanded={abierto} aria-label="Más opciones de la conversación">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
    </button>
    <div className="hilo-panel" role="menu" aria-label="Opciones de la conversación" hidden={!abierto}>
      <button type="button" className="hilo-item" role="menuitem" onClick={() => { cerrar(); nueva() }}><Icon name="plus" size={15} /> Nueva conversación</button>
    </div>
  </div>
}

/** Barra de arriba del chat: cómo se llama la conversación, el modelo (solo en el chat de Fran), las conversaciones anteriores y «Nueva».
 *  Una invitada la tiene igual, con sus conversaciones. */
export default function BarraChat({ chat, titulo, nueva, historial, modelos, asistentes }: { chat: ChatApi; titulo: string
  nueva: () => void; historial: () => void; modelos: () => void; asistentes?: () => void }) {
  const estilo = esEstilo(chat.cur.profile) ? PROFILE_NAMES[chat.cur.profile] || chat.cur.profile : ''
  const conWhatsApp = !!chat.cur.id && !chat.soloLectura && chat.cur.profile === 'default'   // solo las antiguas de Zazu pasan a WhatsApp
  return <div className="chatbar">
    <BotonMenu />
    <div className="chatbar-tit"><strong title={titulo}>{titulo}</strong>{estilo && <small>{estilo}</small>}</div>
    <div className="chatbar-acc">
      {asistentes && <ChipAsistente chat={chat} onClick={asistentes} />}
      <ChipModelo chat={chat} onClick={modelos} />
      <button type="button" className="chatbar-btn" onClick={historial} aria-haspopup="dialog" aria-label="Conversaciones anteriores" title="Conversaciones anteriores"><Icon name="clock" size={20} /></button>
      <button type="button" className="chatbar-btn" onClick={nueva} aria-label="Nueva conversación" title="Nueva conversación"><Icon name="pen" size={20} /></button>
      {conWhatsApp && <MenuHilo nueva={nueva} />}
    </div>
  </div>
}
