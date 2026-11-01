/* Piezas comunes del panel: iconos del diseño de Fran, marca, avatar, avisos de error honestos, hoja (diálogo) y formatos. */
import { useEffect, useRef } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { useAtrasCierra } from '../lib'
import { LogoZazu } from '../icons'
import { useMenu } from './datos'

export type Ico = 'sun' | 'moon' | 'home' | 'board' | 'spark' | 'clock' | 'check' | 'arrow' | 'more' | 'plus' | 'search' | 'calendar'
  | 'close' | 'mic' | 'bell' | 'chevron' | 'down' | 'mail' | 'chat' | 'folder' | 'repeat' | 'list' | 'back' | 'link' | 'send' | 'gear' | 'pen' | 'pin' | 'user' | 'eye' | 'alert' | 'pause' | 'play' | 'shield' | 'clip' | 'cam' | 'wallet' | 'brief' | 'plane' | 'file'

const RUTAS: Record<Ico, ReactNode> = {
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" /></>,
  moon: <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z" />,
  home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-6h6v6" /></>,
  board: <><rect x="3" y="3" width="7" height="18" rx="1.5" /><rect x="14" y="3" width="7" height="10" rx="1.5" /><path d="M14 17h7M14 21h7" /></>,
  spark: <path d="m12 2 1.5 5.3L19 9l-5.5 1.7L12 16l-1.5-5.3L5 9l5.5-1.7L12 2ZM5 16l.8 2.2L8 19l-2.2.8L5 22l-.8-2.2L2 19l2.2-.8L5 16Z" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  arrow: <path d="M5 12h14M14 7l5 5-5 5" />,
  more: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  mic: <><rect x="9" y="2.5" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3.5" /></>,
  bell: <path d="M6 17h12l-1.5-2V11a4.5 4.5 0 0 0-9 0v4zM10 20h4" />,
  chevron: <path d="m9 6 6 6-6 6" />,
  cam: <><path d="M4 8a2 2 0 0 1 2-2h1.5l1.2-2h6.6l1.2 2H18a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z" /><circle cx="12" cy="13" r="3.5" /></>,
  clip: <path d="m21 11.5-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l9-9a3.7 3.7 0 0 1 5.2 5.2l-9 9a1.8 1.8 0 0 1-2.6-2.6l8.3-8.3" />,
  down: <path d="m6 9 6 6 6-6" />,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></>,
  chat: <path d="M20 11.5a8.5 8.5 0 0 1-8.5 8.5 9 9 0 0 1-3.5-.7L3 21l1.7-5A8.5 8.5 0 1 1 20 11.5Z" />,
  folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  repeat: <><path d="M17 3l3 3-3 3" /><path d="M4 11V9a3 3 0 0 1 3-3h13" /><path d="M7 21l-3-3 3-3" /><path d="M20 13v2a3 3 0 0 1-3 3H4" /></>,
  list: <><path d="M9 6h11M9 12h11M9 18h11" /><path d="m3.5 6 1 1 2-2M3.5 12l1 1 2-2M3.5 18l1 1 2-2" /></>,
  back: <path d="m15 18-6-6 6-6" />,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1" /></>,
  send: <path d="M5 12h14M13 6l6 6-6 6" />,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.56V21h-4v-.04A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H3v-4h.04A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88L4.2 7.06 7.06 4.2l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.56V3h4v.04A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.56 1H21v4h-.04A1.7 1.7 0 0 0 19.4 15Z" /></>,
  pen: <><path d="m4 20 4.5-1 11-11a2.12 2.12 0 0 0-3-3l-11 11L4 20Z" /><path d="m14.5 7.5 3 3" /></>,
  pin: <path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21Zm0-8.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  eye: <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  alert: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 10v5M12 17.8v.2" /></>,
  pause: <path d="M8 5v14M16 5v14" />,
  play: <path d="M7 4.5v15l12-7.5-12-7.5Z" />,
  shield: <path d="M12 3 4.5 6v5.5c0 4.5 3.2 8 7.5 9.5 4.3-1.5 7.5-5 7.5-9.5V6L12 3Z" />,
  wallet: <><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18M7 15h3" /></>,
  brief: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" /></>,
  plane: <path d="M21 3 10 14M21 3l-7 18-4-7-7-4 18-7Z" />,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" /><path d="M14 3v5h5" /></>,
}

export function Icono({ n, size = 18 }: { n: Ico; size?: number }) {
  return <svg aria-hidden="true" focusable="false" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{RUTAS[n]}</svg>
}

/** Logo y nombre del asistente (Zazu, o el que le puso la invitada al suyo). */
export function Marca({ onClick, nombre = 'Zazu' }: { onClick?: () => void; nombre?: string }) {
  const dentro = <><LogoZazu tam={34} /><span>{nombre}</span></>
  return onClick ? <button type="button" className="pz-marca" onClick={onClick} aria-label={`${nombre}: ir al inicio`}>{dentro}</button> : <div className="pz-marca">{dentro}</div>
}

/** El ☰ de la cabecera del chat en el móvil (allí no hay barra de arriba): abre el cajón con el menú. En el ordenador no sale. */
export function BotonMenu() {
  const abrir = useMenu()
  if (!abrir) return null
  return <button type="button" className="pz-top-btn pz-menu-btn" onClick={abrir} aria-label="Abrir el menú" aria-haspopup="dialog">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h10" /></svg></button>
}

export function Avatar({ nombre }: { nombre: string }) {
  const ini = (nombre.replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('') || 'F').toUpperCase()
  return <span className="pz-avatar" aria-hidden="true">{ini}</span>
}

/** Error honesto con botón para reintentar: jamás se sustituye por «0 cosas» ni «todo en orden». */
export function Fallo({ texto, reintentar, ocupado }: { texto: string; reintentar?: () => void; ocupado?: boolean }) {
  return <div className="pz-fallo" role="alert"><span>{texto}</span>{reintentar && <button type="button" className="pz-btn pz-btn-suave" onClick={reintentar} disabled={ocupado}>Reintentar</button>}</div>
}

export function Esqueleto({ filas = 3, alto = 56 }: { filas?: number; alto?: number }) {
  return <div className="pz-esq" aria-busy="true" aria-label="Cargando">{Array.from({ length: filas }, (_, i) => <span key={i} style={{ height: alto }} />)}</div>
}

/** Nota pequeña de «datos de hace un rato» cuando la fuente se atascó y se enseña el último dato bueno. */
export function Obsoleto({ actualizado }: { actualizado: string | null }) {
  const m = actualizado ? Math.max(1, Math.round((Date.now() - new Date(actualizado).getTime()) / 60000)) : null
  return <p className="pz-nota" role="status">Esta parte tardó en contestar: {m ? `dato de hace ${m} min` : 'dato anterior'}.</p>
}

/** La trampa de foco de los diálogos (Hoja y el Cajón del menú): Esc y el Atrás del móvil cierran, al abrir el foco va al primer
 *  selector de `primero` que exista (en ese orden), Tab da la vuelta dentro de la caja y al cerrar el foco vuelve a donde estaba.
 *  `soloVisibles`: salta lo que está oculto (el Cajón tiene secciones plegadas). Devuelve la ref de la caja y su onKeyDown. */
export function useTrampaFoco(cerrar: () => void, primero: string[], enfocables: string, soloVisibles = false) {
  const caja = useRef<HTMLDivElement>(null)
  const prev = useRef<Element | null>(typeof document !== 'undefined' ? document.activeElement : null)
  useAtrasCierra(true, cerrar)
  useEffect(() => {
    const previo = prev.current as HTMLElement | null
    for (const s of primero) { const el = caja.current?.querySelector<HTMLElement>(s); if (el) { el.focus({ preventScroll: true }); break } }
    return () => { if (previo && document.contains(previo)) previo.focus({ preventScroll: true }) }
  }, [])
  const teclas = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cerrar(); return }
    if (e.key !== 'Tab') return
    const f = [...(caja.current?.querySelectorAll<HTMLElement>(enfocables) || [])].filter(x => !soloVisibles || x.offsetParent !== null)
    if (!f.length) return
    const [a, z] = [f[0], f[f.length - 1]]
    if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus() }
    else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus() }
  }
  return { caja, teclas }
}

/** Diálogo: hoja desde abajo en el móvil, ventana centrada en el escritorio. Esc, velo y Atrás del móvil lo cierran; el foco vuelve a donde estaba. */
export function Hoja({ titulo, cerrar, children, id }: { titulo: string; cerrar: () => void; children: ReactNode; id?: string }) {
  const { caja, teclas } = useTrampaFoco(cerrar, ['[data-foco]', 'button, [href], input, select, textarea'],
    'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])')
  const t = `pz-hoja-t-${id || 'x'}`
  return <div className="pz-hoja-fondo" onMouseDown={e => { if (e.target === e.currentTarget) cerrar() }}>
    <div className="pz-hoja" role="dialog" aria-modal="true" aria-labelledby={t} ref={caja} onKeyDown={teclas}>
      <span className="pz-hoja-asa" aria-hidden="true" />
      <div className="pz-hoja-cab"><h2 id={t}>{titulo}</h2><button type="button" className="pz-icono" onClick={cerrar} aria-label="Cerrar"><Icono n="close" size={20} /></button></div>
      {children}
    </div>
  </div>
}

/* ---------- formatos ---------- */
const MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const DIA = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
export const plural = (n: number, uno: string, otros: string) => `${n} ${n === 1 ? uno : otros}`
const dia0 = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
/** «AAAA-MM-DD» (o ISO) → «vie 9 oct». */
export function diaCorto(v: string | null): string {
  if (!v) return ''
  const d = /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(v + 'T12:00') : new Date(v)
  return isNaN(d.getTime()) ? '' : `${DIA[d.getDay()]} ${d.getDate()} ${MES[d.getMonth()]}`
}
export const horaDe = (v: string | null) => { if (!v) return ''; const d = new Date(v); return isNaN(d.getTime()) ? '' : `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }
/** «hoy 18:20», «ayer», «5 oct». */
export function cuandoCorto(v: string | null): string {
  if (!v) return ''
  const d = new Date(v)
  if (isNaN(d.getTime())) return ''
  const dif = Math.round((dia0(new Date()) - dia0(d)) / 864e5)
  return dif === 0 ? `hoy ${horaDe(v)}` : dif === 1 ? `ayer ${horaDe(v)}` : `${d.getDate()} ${MES[d.getMonth()]}`
}
/** Días hasta un plazo → «hoy», «mañana», «en 4 d», «hace 2 d». */
export const enDias = (n: number | null) => n === null ? '' : n === 0 ? 'hoy' : n === 1 ? 'mañana' : n > 0 ? `en ${n} d` : n === -1 ? 'ayer' : `hace ${-n} d`
export function haceMin(m: number | null): string {
  if (m === null) return 'sin datos'
  if (m < 1) return 'ahora mismo'
  if (m < 60) return `hace ${m} min`
  return m < 1440 ? `hace ${Math.round(m / 60)} h` : `hace ${Math.round(m / 1440)} d`
}
