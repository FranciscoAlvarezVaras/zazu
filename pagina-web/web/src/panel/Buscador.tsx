/* Buscador general de la barra de arriba: pantallas, tareas de hoy, candidaturas y demás tarjetas, suscripciones y personas.
   Solo busca en lo que ya está cargado (no pide nada nuevo al servidor). Lo que no encuentra se le pregunta a Zazu en el chat. */
import { useId, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { irA, puede } from '../lib'
import type { Tab } from '../lib'
import type { Ctx } from '../ctx'
import type { Panel, Tablero } from './api'
import { Icono } from './ui'
import type { Ico } from './ui'

type Res = { clave: string; icono: Ico; titulo: string; sub: string; ir: () => void }
const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '')
const TAB = (tab: Tab) => () => irA({ tab })
/** `c`: la capacidad que hace falta para verla (lib.puede). */
const PANTALLAS: { t: string; icono: Ico; ir: () => void; k?: string; c: string }[] = [
  { t: 'Agenda', icono: 'calendar', ir: TAB('inicio'), c: 'inicio', k: 'inicio hoy calendario citas' }, { t: 'Hablar con Zazu', icono: 'chat', ir: TAB('chat'), c: 'chat', k: 'chat conversacion' },
  { t: 'Dinero', icono: 'wallet', ir: TAB('dinero'), c: 'dinero', k: 'gastos suscripciones' },
  { t: 'Empleo', icono: 'brief', ir: TAB('empleo'), c: 'empleo', k: 'candidaturas trabajo' }, { t: 'Correo', icono: 'mail', ir: TAB('correo'), c: 'correo' }, { t: 'WhatsApp', icono: 'chat', ir: TAB('whatsapp'), c: 'whatsapp' },
  { t: 'Mi nube', icono: 'folder', ir: TAB('carpetas'), c: 'carpetas', k: 'archivos carpetas fotos videos galeria' }, { t: 'Rutinas', icono: 'repeat', ir: TAB('rutinas'), c: 'rutinas' }, { t: 'Ajustes', icono: 'gear', ir: TAB('ajustes'), c: 'ajustes' },
  { t: 'Avisos de Zazu', icono: 'bell', ir: TAB('zazu'), c: 'zazu' }, { t: 'Qué ha hecho Zazu', icono: 'eye', ir: () => irA({ tab: 'zazu', vista: 'registro' }), c: 'registro' },
]

export function buscarTodo(q: string, panel: Panel | null, tableros: Tablero[] | null, tiene: (c: string) => boolean = () => true): Res[] {
  const n = norm(q.trim())
  if (!n) return []
  const ok = (...t: (string | null | undefined)[]) => norm(t.filter(Boolean).join(' ')).includes(n)
  const out: Res[] = []
  for (const p of PANTALLAS) if (tiene(p.c) && ok(p.t, p.k)) out.push({ clave: 'p' + p.t, icono: p.icono, titulo: p.t, sub: 'Pantalla', ir: p.ir })
  if (panel?.tareas.ok && tiene('tareas')) for (const t of panel.tareas.items) if (ok(t.titulo)) out.push({ clave: 't' + t.id, icono: 'check', titulo: t.titulo, sub: t.vencida ? 'Tarea vencida' : 'Tarea de hoy', ir: TAB('tareas') })
  for (const b of tableros || []) {
    if (!b.ok) continue
    if (b.clase === 'kanban' && b.id === 'candidaturas') for (const c of b.columnas) for (const x of c.tarjetas) {
      if (ok(x.titulo, x.empresa, x.puesto, x.ciudad, x.siguiente, ...x.tags)) out.push({ clave: 'k' + x.ruta, icono: 'brief', titulo: x.titulo,
        sub: `${b.titulo}${x.empresa ? ` · ${x.empresa}` : ''}`, ir: () => irA({ tab: 'empleo', tarjeta: x.ruta }) })
    }
    else if (b.clase === 'suscripciones') for (const s of b.items) { if (ok(s.nombre, s.categoria)) out.push({ clave: 's' + s.nombre, icono: 'wallet', titulo: s.nombre, sub: 'Suscripción', ir: TAB('dinero') }) }
  }
  return out.slice(0, 8)
}

/** Campo de búsqueda con lista de resultados. `enHoja`: en el móvil va dentro de una hoja y la lista ocupa su sitio. */
export default function Buscador({ ctx, panel, tableros, alElegir, enHoja }: { ctx: Ctx; panel: Panel | null; tableros: Tablero[] | null; alElegir?: () => void; enHoja?: boolean }) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const [abierto, setAbierto] = useState(false)
  const id = useId()
  const campo = useRef<HTMLInputElement>(null)
  const res = useMemo(() => buscarTodo(q, panel, tableros, c => puede(ctx.me, c)), [q, panel, tableros, ctx.me])
  const total = res.length + (q.trim() ? 1 : 0)   // la última fila es «Preguntarle a Zazu»
  const ver = (abierto || !!enHoja) && !!q.trim()
  const elegir = (i: number) => {
    const t = q.trim()
    if (i < res.length) res[i].ir(); else if (t) ctx.ask(t, { fill: true })
    setQ(''); setAbierto(false); alElegir?.()
  }
  const teclas = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setAbierto(true); setSel(s => Math.min(s + 1, total - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
    else if (e.key === 'Enter' && q.trim()) { e.preventDefault(); elegir(Math.min(sel, total - 1)) }
    else if (e.key === 'Escape') { if (q) { e.stopPropagation(); setQ('') } setAbierto(false) }
  }
  return <div className={`pz-buscador ${enHoja ? 'en-hoja' : ''}`} role="search" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setAbierto(false) }}>
    <label className="pz-oculto" htmlFor={id + 'q'}>Buscar en Zazu</label>
    <span className="pz-buscador-campo">
      <Icono n="search" size={18} />
      <input id={id + 'q'} ref={campo} type="search" value={q} placeholder="Buscar" autoComplete="off" enterKeyHint="search" role="combobox" aria-expanded={ver} aria-controls={id + 'l'} aria-autocomplete="list"
        aria-activedescendant={ver ? `${id}o${sel}` : undefined} data-foco
        onChange={e => { setQ(e.target.value); setSel(0); setAbierto(true) }} onFocus={() => setAbierto(true)} onKeyDown={teclas} />
    </span>
    {ver && <ul className="pz-buscador-lista" id={id + 'l'} role="listbox" aria-label="Resultados">
      {res.map((r, i) => <li key={r.clave} id={`${id}o${i}`} role="option" aria-selected={i === sel}>
        <button type="button" tabIndex={-1} onMouseDown={e => e.preventDefault()} onClick={() => elegir(i)}><Icono n={r.icono} size={18} /><span><strong>{r.titulo}</strong><small>{r.sub}</small></span></button></li>)}
      <li id={`${id}o${res.length}`} role="option" aria-selected={sel === res.length}>
        <button type="button" tabIndex={-1} onMouseDown={e => e.preventDefault()} onClick={() => elegir(res.length)}><Icono n="spark" size={18} /><span><strong>Preguntarle a {ctx.nombre || 'Zazu'}</strong><small>«{q.trim()}»: lo escribo en el chat</small></span></button></li>
    </ul>}
  </div>
}
