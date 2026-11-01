import { Fragment, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Icon } from '../icons'
import { fmtSize, useFetch } from '../lib'
import { extension, migas, normalizar, renombrar, urlListado } from './api'
import type { Item, ListadoCrudo } from './api'
import { Hoja, Ic } from './ui'

const enAdjuntos = (d: string) => d === 'Adjuntos' || d.startsWith('Adjuntos/')
const porNombre = (a: Item, b: Item) => a.name.localeCompare(b.name, 'es', { numeric: true, sensitivity: 'base' })

/** «¿Dónde lo guardo?» / «Mover a…»: atajos (Importante › <Área>, Guardado) y cualquier otra carpeta de Mis carpetas */
export function ElegirCarpeta({ titulo, items, desde, dejar, onClose, onElegir }: { titulo: string; items: Item[]; desde: string; dejar?: string; onClose: () => void; onElegir: (destino: string) => void }) {
  const [ruta, setRutaYa] = useState('')
  const [elegida, setElegida] = useState(false)   // hasta que no elige una carpeta abajo, el botón grande no guarda (antes iba a parar a la raíz con un toque)
  const setRuta = (d: string) => { setRutaYa(d); setElegida(true) }
  const areas = useFetch<ListadoCrudo>(urlListado('compartido', 'Importante'))
  const lst = useFetch<ListadoCrudo>(urlListado('compartido', ruta))
  // ni dentro de sí misma ni en Adjuntos (es del chat)
  const valido = (d: string) => !enAdjuntos(d) && !items.some(it => it.dir && (d === it.path || d.startsWith(`${it.path}/`)))
  const puede = (d: string) => d !== desde && valido(d)
  const L = normalizar(lst.data, 'compartido')
  const dirs = L && L.path === ruta ? L.items.filter(i => i.dir && valido(i.path)).sort(porNombre) : []
  const rapidos = [...(normalizar(areas.data, 'compartido')?.items || []).filter(i => i.dir).sort(porNombre).map(i => i.path), 'Importante', 'Guardado'].filter(valido)
  const partes = ruta ? ruta.split('/') : []
  return <Hoja titulo={titulo} sub={items.length <= 3 ? items.map(i => i.name).join(' · ') : `${items.length} archivos`} onClose={onClose}>
    <span className="section-kicker">LO MÁS USADO</span>
    <div className="cp-rapidos">{rapidos.map(d => <button key={d} disabled={!puede(d)} onClick={() => onElegir(d)}>
      <Ic n={d === 'Guardado' ? 'folder' : 'star'} size={16} /> {migas(d)}</button>)}</div>
    <span className="section-kicker">OTRA CARPETA</span>
    <nav className="cp-migas" aria-label="Carpeta elegida"><button onClick={() => setRuta('')} aria-current={!ruta ? 'page' : undefined}>Mis carpetas</button>
      {partes.map((p, i) => <Fragment key={i}><Icon name="chevron" size={14} /><button onClick={() => setRuta(partes.slice(0, i + 1).join('/'))} aria-current={i === partes.length - 1 ? 'page' : undefined}>{p}</button></Fragment>)}</nav>
    <div className="cp-elegir-lista">{dirs.map(d => <button key={d.path} onClick={() => setRuta(d.path)}><Ic n="folder" size={18} /><span className="cut">{d.name}</span><Icon name="chevron" size={16} /></button>)}
      {!dirs.length && <p className="cp-vacio">{lst.loading ? 'Cargando…' : lst.error ? `No pude abrirla: ${lst.error}` : 'No hay más carpetas dentro.'}</p>}</div>
    <button className="btn-primary cp-ancho" disabled={!elegida || !puede(ruta)} onClick={() => onElegir(ruta)}>
      {!elegida ? 'Elige una carpeta' : ruta === desde ? 'Ya está en esta carpeta' : `Guardar en ${ruta ? migas(ruta) : 'Mis carpetas'}`}</button>
    {dejar && <button className="btn-secondary cp-ancho" onClick={onClose}>{dejar}</button>}
  </Hoja>
}

/** Cambiar el nombre: la extensión se mantiene aparte para no romper el archivo */
export function Renombrar({ it, onClose, onHecho }: { it: Item; onClose: () => void; onHecho: (nuevo: string) => void }) {
  const ext = it.dir ? '' : extension(it.name)
  const tallo = ext ? it.name.slice(0, -(ext.length + 1)) : it.name
  const [n, setN] = useState(tallo)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function ok(e: FormEvent) {
    e.preventDefault()
    const v = n.trim()
    if (!v || v === tallo) return
    if (v.includes('/')) return setErr('El nombre no puede llevar /')
    if (v.startsWith('.')) return setErr('El nombre no puede empezar por un punto')
    setBusy(true); setErr('')
    try { onHecho((await renombrar(it.path, ext ? `${v}.${ext}` : v)).path) }
    catch (e) { setErr((e as Error).message === 'ya existe' ? 'Ya hay algo con ese nombre aquí' : (e as Error).message) }
    finally { setBusy(false) }
  }
  return <Hoja titulo="Renombrar" sub={it.name} onClose={onClose}>
    <form onSubmit={e => void ok(e)}>
      <label className="cp-campo"><input autoFocus value={n} onChange={e => { setN(e.target.value); setErr('') }} aria-label="Nombre nuevo" maxLength={150} />{ext && <span>.{ext}</span>}</label>
      {err && <p className="cp-error" role="alert">{err}</p>}
      <div className="cp-botones"><button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" disabled={busy || !n.trim() || n.trim() === tallo}>{busy ? 'Guardando…' : 'Guardar'}</button></div>
    </form>
  </Hoja>
}

/** «Copia ZIP» de todo un espacio. Antes de empezar se avisa de que es muy grande: tarda y, por internet, es fácil que se corte. El enlace de descarga solo existe dentro del aviso (un doble clic no lanza dos copias).
 *  avisar={false}: una carpeta cualquiera, que es un enlace de descarga directo. */
export function CopiaZip({ href, avisar = true, bytes, className, title, children }: { href: string; avisar?: boolean; bytes?: number; className: string; title?: string; children: ReactNode }) {
  const [abierto, setAbierto] = useState(false)
  const pedida = useRef(false)   // la descarga ya salió: un segundo clic (doble clic) no lanza otra copia
  if (!avisar) return <a className={className} href={href} download title={title}>{children}</a>
  return <>
    <button type="button" className={className} title={title} onClick={() => { pedida.current = false; setAbierto(true) }}>{children}</button>
    {abierto && <Hoja titulo="Copia ZIP de todo" onClose={() => setAbierto(false)}>
      <p className="nube-publico"><Icon name="clock" size={18} /><span>Es todo en un solo ZIP{bytes ? ` (unos ${fmtSize(bytes)})` : ''}: una descarga muy grande. Puede tardar horas y, por internet (holazazu.app), es fácil que se corte antes de acabar. Desde el propio PC va mucho mejor.</span></p>
      <button type="button" className="btn-primary cp-ancho" autoFocus onClick={() => setAbierto(false)}>Cancelar</button>
      <a className="btn-secondary cp-ancho" href={href} download onClick={e => { if (pedida.current) return e.preventDefault(); pedida.current = true; setTimeout(() => setAbierto(false), 400) }}>Descargar igual</a>
    </Hoja>}
  </>
}
