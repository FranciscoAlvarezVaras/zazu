/* Datos compartidos del marco de Zazu: el panel del día (agenda, tareas, avisos, capturas), y los tableros del Cerebro.
   Los carga el marco una sola vez y los leen Inicio, el panel derecho, Empleo, Dinero, el buscador y los contadores del menú. */
import { createContext, useContext } from 'react'
import type { Panel, Tablero } from './api'
import { useCarga } from './api'

export type DatosPanel = { data: Panel | null; error: string; loading: boolean; recargar: () => Promise<void>; refrescar: () => Promise<void> }
export type DatosTableros = ReturnType<typeof useCarga<Tablero[]>>

export const CtxPanel = createContext<DatosPanel | null>(null)
export const CtxTableros = createContext<DatosTableros | null>(null)

const quiere = <T,>(c: T | null): T => { if (!c) throw new Error('falta PanelShell'); return c }
export const useDatosPanel = () => quiere(useContext(CtxPanel))
export const useDatosTableros = () => quiere(useContext(CtxTableros))
/** Hay un panel derecho fijo al lado (solo en pantallas muy anchas): si no, Inicio enseña esas cosas debajo. */
export const CtxPanelDerecho = createContext(false)
export const usePanelDerecho = () => useContext(CtxPanelDerecho)
/** Abrir el menú lateral (el cajón del móvil). Lo da el marco; la cabecera del chat del móvil lo usa para su botón ☰ (allí no hay barra de arriba). */
export const CtxMenu = createContext<(() => void) | null>(null)
export const useMenu = () => useContext(CtxMenu)
