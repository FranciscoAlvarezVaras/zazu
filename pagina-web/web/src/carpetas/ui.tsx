import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Icon } from '../icons'
import { urlDescarga } from '../lib'
import { extension, KIND_LABEL } from './api'
import type { Item, Kind, Raiz } from './api'

/* Iconos propios de Carpetas (mismo trazo que icons.tsx) */
export type Ico = Kind | 'search' | 'more' | 'trash' | 'share' | 'send' | 'move' | 'restore' | 'eye' | 'lock' | 'inbox' | 'star' | 'brain' | 'phone' | 'down' | 'chat' | 'idea' | 'heart' | 'album' | 'copy' | 'link' | 'minus' | 'target'
const P: Record<Ico, ReactNode> = {
  folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  pdf: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-9 9" /></>,
  video: <><rect x="3" y="6" width="13" height="12" rx="2" /><path d="m16 10 5-3v10l-5-3" /></>,
  audio: <><path d="M9 18V5l11-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></>,
  doc: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" /><path d="M14 3v5h5M9 12h6M9 15h6M9 18h3" /></>,
  sheet: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M3 15h18M9 3v18" /></>,
  text: <path d="M4 6h16M4 10h16M4 14h10M4 18h7" />,
  note: <><path d="m4 20 4.5-1 11-11a2.12 2.12 0 0 0-3-3l-11 11L4 20Z" /><path d="m14.5 7.5 3 3" /></>,
  other: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" /><path d="M14 3v5h5" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  more: <><circle cx="5" cy="12" r="1.4" fill="currentColor" /><circle cx="12" cy="12" r="1.4" fill="currentColor" /><circle cx="19" cy="12" r="1.4" fill="currentColor" /></>,
  trash: <path d="M4 7h16M10 11v6m4-6v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V4h6v3" />,
  share: <><circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="m8.2 10.8 7.6-4.6m-7.6 7 7.6 4.6" /></>,
  send: <path d="M21 3 10 14M21 3l-7 18-4-7-7-4 18-7Z" />,
  move: <><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /><path d="M8.5 14H15m-2.5-2.5L15 14l-2.5 2.5" /></>,
  restore: <><path d="M4 10h11a5 5 0 0 1 0 10h-3" /><path d="m8 6-4 4 4 4" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  lock: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  inbox: <><path d="M3 13h5l1 3h6l1-3h5" /><path d="M5.5 5h13L21 13v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6Z" /></>,
  star: <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z" />,
  brain: <><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V5a2 2 0 0 0-3-1Z" /><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1" /></>,
  phone: <><rect x="6" y="2" width="12" height="20" rx="2.5" /><path d="M11 18h2" /></>,
  down: <path d="M12 4v11m-5-5 5 5 5-5M5 20h14" />,
  chat: <path d="M20 11.5a8.5 8.5 0 0 1-8.5 8.5 9 9 0 0 1-3.5-.7L3 21l1.7-5A8.5 8.5 0 1 1 20 11.5Z" />,
  idea: <path d="M9 18h6m-5 3h4M8.5 15.5a7 7 0 1 1 7 0c-.9.6-1 1.5-1 2.5h-5c0-1-.1-1.9-1-2.5Z" />,
  heart: <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78Z" />,
  album: <><rect x="3" y="7" width="14" height="14" rx="2" /><path d="M7 7V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2M3 17l4-4 4 4 2-2 4 4" /></>,
  copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h8" /></>,
  link: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
  minus: <path d="M5 12h14" />,
  target: <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="1.6" fill="currentColor" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3" /></>,
}
/** `lleno`: el dibujo va relleno (el corazón de un favorito) */
export function Ic({ n, size = 20, lleno = false }: { n: Ico; size?: number; lleno?: boolean }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill={lleno ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{P[n]}</svg>
}

/** Icono por tipo, o miniatura si es una foto */
export function Ficha({ it, root, big = false, foto = true }: { it: Pick<Item, 'name' | 'path' | 'kind' | 'inline'>; root: Raiz; big?: boolean; foto?: boolean }) {
  const [fallo, setFallo] = useState(false)
  const ext = extension(it.name)
  if (it.kind === 'image' && foto && it.inline !== false && !fallo)   // HEIC y similares: icono, sin descargarlas enteras
    return <span className={`cp-ficha image ${big ? 'big' : ''}`}>
    <img src={urlDescarga(root, it.path, true)} alt="" loading="lazy" decoding="async" onError={() => setFallo(true)} /></span>
  return <span className={`cp-ficha ${it.kind} ${big ? 'big' : ''}`} title={KIND_LABEL[it.kind]}><Ic n={it.kind} size={big ? 34 : 20} />
    {it.kind !== 'folder' && ext && ext.length <= 4 && <em>{ext}</em>}</span>
}

/* Hojas abiertas (Esc cierra solo la de arriba) y el Atrás del móvil: mientras haya alguna con `atras`, hay UNA entrada
   nuestra en el historial (misma URL, state.cpHoja; lib usa .hoja para las suyas). Atrás la quita y cierra la hoja de arriba; si se cierra con X, Cancelar,
   tocando fuera o desde el código, la quitamos nosotros con history.back(). De una hoja a otra (⋯ → Renombrar) se reutiliza. */
type Abierta = { cerrar: () => void; atras: boolean; el: () => HTMLElement | null }
const pila: Abierta[] = []
let entrada = false                     // nuestra entrada está encima en el historial
let soltando = false                    // el history.back() que la quita está en camino
let luego: (() => void)[] = []          // lo que espera a que se haya quitado
let volverA: HTMLElement | null = null  // dónde estaba el foco antes de abrir la primera hoja
let repaso = 0
let marca = 0                           // distingue nuestra entrada de una que quedó de antes (recargar con una hoja abierta)
const encima = () => entrada && history.state?.cpHoja === marca
function poner() { marca = Math.random(); history.pushState({ ...history.state, cpHoja: marca }, '', location.href); entrada = true }
function soltado() { soltando = false; const fs = luego; luego = []; fs.forEach(f => f()) }
let aviso = 0
function soltar() {
  if (!encima()) { entrada = false; return }
  entrada = false; soltando = true; history.back()
  clearTimeout(aviso); aviso = window.setTimeout(() => { if (soltando) soltado() }, 700)   // por si el navegador no avisa
}
/** Tras cerrar una hoja puede abrirse otra en el mismo momento (⋯ → Renombrar): se espera un tick antes de soltar la entrada y devolver el foco */
function repasar() {
  clearTimeout(repaso)
  repaso = window.setTimeout(() => {
    if (!pila.some(h => h.atras)) soltar()
    const arriba = pila[pila.length - 1]
    if (arriba) { const el = arriba.el(); if (el && !el.contains(document.activeElement)) el.focus({ preventScroll: true }); return }
    document.body.classList.remove('cp-sin-scroll')
    if (volverA?.isConnected) volverA.focus({ preventScroll: true })
    volverA = null
  }, 0)
}
if (typeof window !== 'undefined') addEventListener('popstate', () => {
  if (soltando) {   // la quitamos nosotros; lo que esperaba va después de los avisos de navegación (NAV)
    clearTimeout(aviso); setTimeout(soltado, 0)
    return
  }
  if (!entrada || history.state?.cpHoja === marca) return
  entrada = false   // el Atrás del móvil se llevó nuestra entrada: se cierra la hoja de arriba
  const con = pila.filter(h => h.atras)
  con[con.length - 1]?.cerrar()
  if (con.length > 1) poner()
})

/** ¿Es este Atrás el que quita la entrada de una hoja? (la URL vuelve a la de antes de abrirla; no es navegar) */
export const soltandoHoja = () => soltando
/** Navegar desde una hoja abierta (⋯ → Ver/Abrir): true si su entrada está encima y hay que sustituirla (replaceState) en vez de apilar otra */
export function tomarHoja() {
  if (soltando || !encima()) return false
  entrada = false
  return true
}
/** Hace fn cuando la entrada de la hoja ya no está (p. ej. antes de ir a otra pantalla); si no hay, enseguida */
export function trasHoja(fn: () => void) {
  if (encima()) { soltar(); luego.push(fn) }
  else if (soltando) luego.push(fn)
  else fn()
}

/** Con una hoja abierta, Tab no se sale de ella (aria-modal no basta para el teclado). Los botones del aviso de abajo (Deshacer…) también cuentan. */
function atrapar(e: KeyboardEvent, hoja: HTMLElement | null) {
  if (!hoja) return
  const fs = [...hoja.querySelectorAll<HTMLElement>('a[href],button,input,select,textarea,[tabindex]'), ...document.querySelectorAll<HTMLElement>('.cp-aviso-live button')]
    .filter(x => x.tabIndex >= 0 && !(x as HTMLButtonElement).disabled && (x.offsetWidth > 0 || x.offsetHeight > 0))
  const a = document.activeElement
  if (!fs.length) { e.preventDefault(); hoja.focus(); return }
  const dentro = hoja.contains(a) || fs.includes(a as HTMLElement)
  if (!dentro || (e.shiftKey && (a === fs[0] || a === hoja))) { e.preventDefault(); fs[e.shiftKey ? fs.length - 1 : 0].focus() }
  else if (!e.shiftKey && a === fs[fs.length - 1]) { e.preventDefault(); fs[0].focus() }
}

/** Hoja que sube desde abajo (centrada en escritorio). Esc, tocar fuera o el Atrás del móvil la cierran.
 *  atras={false}: la hoja ya tiene su propia entrada en la URL (la vista previa, ?archivo=). */
export function Hoja({ titulo, sub, onClose, children, ancha = false, atras = true, clase = '' }: { titulo: string; sub?: ReactNode; onClose: () => void; children: ReactNode; ancha?: boolean; atras?: boolean; clase?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const cerrar = useRef(onClose); cerrar.current = onClose
  useState(() => { if (!pila.length && !volverA) volverA = document.activeElement as HTMLElement | null })   // al pintar, antes de que un autoFocus se lleve el foco
  useEffect(() => {
    if (!ref.current?.contains(document.activeElement)) ref.current?.focus({ preventScroll: true })   // si un campo ya tiene autoFocus, se queda con él
    const yo: Abierta = { cerrar: () => cerrar.current(), atras, el: () => ref.current }
    const k = (e: KeyboardEvent) => { if (pila[pila.length - 1] !== yo) return; if (e.key === 'Escape') yo.cerrar(); else if (e.key === 'Tab') atrapar(e, ref.current) }
    pila.push(yo); addEventListener('keydown', k); document.body.classList.add('cp-sin-scroll')
    if (atras && !entrada && !soltando) poner()
    else if (atras && soltando) luego.push(() => { if (pila.includes(yo) && !entrada) poner() })
    return () => { removeEventListener('keydown', k); pila.splice(pila.indexOf(yo), 1); repasar() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  // tocar fuera cierra; los enlaces de dentro (data-nav: notas que enlazan a otros archivos) siguen hasta App, que los abre sin recargar
  return createPortal(<div className="cp-velo" onClick={e => { if (e.target === e.currentTarget) cerrar.current() }}>
    <div className={`cp-hoja ${ancha ? 'ancha' : ''} ${clase}`} role="dialog" aria-modal="true" aria-label={titulo} tabIndex={-1} ref={ref}
      onClick={e => { if (!(e.target as Element).closest?.('a[data-nav]')) e.stopPropagation() }}>
      <div className="cp-hoja-top"><div className="cp-hoja-tit"><strong>{titulo}</strong>{sub && <small>{sub}</small>}</div>
        <button className="cp-x" onClick={() => cerrar.current()} aria-label="Cerrar"><Icon name="close" size={18} /></button></div>
      <div className="cp-hoja-body">{children}</div>
    </div></div>, document.body)
}

export type Aviso = { texto: string; accion?: { label: string; fn: () => void } }
/** Aviso propio de Carpetas: va por encima de las hojas y puede llevar un botón (Deshacer, Abrir…) */
export function BarraAviso({ aviso, cerrar }: { aviso: Aviso | null; cerrar: () => void }) {
  useEffect(() => { if (!aviso) return; const t = setTimeout(cerrar, aviso.accion ? 8000 : 4500); return () => clearTimeout(t) }, [aviso]) // eslint-disable-line react-hooks/exhaustive-deps
  return createPortal(<div className="cp-aviso-live" role="status" aria-live="polite">{aviso && <div className="cp-aviso">
    <span>{aviso.texto}</span>{aviso.accion && <button onClick={() => { aviso.accion!.fn(); cerrar() }}>{aviso.accion.label}</button>}</div>}</div>, document.body)
}
