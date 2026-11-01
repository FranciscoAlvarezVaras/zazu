import { useState } from 'react'
import { Hoja } from '../panel/ui'
import { Icono } from '../panel/ui'
import type { Session } from '../lib'
import type { ChatApi } from '../tipos'
import Sessions from '../screens/Sessions'

/** Hoja «Conversaciones»: todas las de Fran en una sola lista (las nuevas con Zazu y las antiguas), con buscador.
 *  Tocar una la abre (Sessions ya la ha abierto) y se avisa con `abrir` para poner su URL. */
export default function HojaHistorial({ chat, cerrar, abrir }: { chat: ChatApi; cerrar: () => void; abrir: (s: Session) => void }) {
  const [buscar, setBuscar] = useState('')
  return <Hoja titulo="Conversaciones" id="historial" cerrar={cerrar}>
    <div className="hist-buscar" role="search">
      <Icono n="search" size={17} />
      <label className="pz-oculto" htmlFor="hist-buscar">Buscar conversaciones</label>
      <input id="hist-buscar" data-foco type="search" value={buscar} onChange={e => setBuscar(e.target.value)} placeholder="Buscar conversaciones" autoComplete="off" enterKeyHint="search" />
    </div>
    <div className="hist-hoja"><Sessions chat={chat} onPick={s => { abrir(s); cerrar() }} limit={80} buscar={buscar} agrupar /></div>
  </Hoja>
}
