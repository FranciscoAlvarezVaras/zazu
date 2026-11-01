import { useState } from 'react'
import type { FormEvent } from 'react'
import { Icon } from '../icons'
import { Hoja, Ic } from './ui'
import { mini, msg, plural } from './nube'
import type { Album } from './nube'

/** La portada de un álbum: su foto más nueva, o el dibujo de un álbum si aún no tiene nada (o su miniatura no llega) */
function Portada({ ruta }: { ruta: string | null }) {
  const [fallo, setFallo] = useState(false)
  return <span className="nube-portada">{ruta && !fallo ? <img src={mini(ruta)} alt="" loading="lazy" decoding="async" onError={() => setFallo(true)} /> : <Ic n="album" size={26} />}</span>
}

/** La franja de álbumes, con «Nuevo álbum» siempre la primera */
export function FranjaAlbumes({ lista, error, actual, onElegir, onNuevo, onReintentar }: { lista: Album[] | null; error: string; actual: string; onElegir: (id: string) => void; onNuevo: () => void; onReintentar: () => void }) {
  const vacia = !!lista && !lista.length   // aún sin álbumes: basta un botón, no una fila de portadas (así las fotos salen antes en el móvil)
  return <section className="nube-albumes" aria-label="Álbumes">
    <div className="nube-cab"><h3>Álbumes</h3>{vacia && <button type="button" className="btn-secondary nube-album-nuevo" onClick={onNuevo}><Icon name="plus" size={16} /> Nuevo álbum</button>}</div>
    {error && !lista ? <p className="cp-vacio" role="alert">No pude cargar los álbumes: {error}. <button type="button" className="text-link cp-en-linea" onClick={onReintentar}>Reintentar</button></p>
      : !vacia && <div className="nube-franja">
        <button type="button" className="nube-album nuevo" onClick={onNuevo}><span className="nube-portada"><Icon name="plus" size={26} /></span><strong>Nuevo álbum</strong><small>Por viaje o evento</small></button>
        {(lista || []).map(a => <button type="button" key={a.id} className={`nube-album${actual === a.id ? ' on' : ''}`} aria-pressed={actual === a.id} onClick={() => onElegir(a.id)}>
          <Portada ruta={a.portada} /><strong>{a.nombre}</strong><small>{plural(a.n, 'elemento', 'elementos')}</small></button>)}
      </div>}
  </section>
}

/** «Añadir a un álbum»: los que hay, o uno nuevo con su nombre (que se crea y se añade de una vez) */
export function ElegirAlbum({ albumes, n, excepto, onElegir, onNuevo, onClose }: { albumes: Album[]; n: number; excepto?: string; onElegir: (a: Album) => Promise<void>; onNuevo: (nombre: string) => Promise<void>; onClose: () => void }) {
  const [nombre, setNombre] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const hay = albumes.filter(a => a.id !== excepto)
  async function hacer(clave: string, f: () => Promise<void>) {
    setBusy(clave); setErr('')
    try { await f() } catch (e) { setErr(msg(e)) } finally { setBusy('') }
  }
  return <Hoja titulo="Añadir a un álbum" sub={plural(n, 'elemento', 'elementos')} onClose={onClose}>
    <form className="nube-nuevo" onSubmit={(e: FormEvent) => { e.preventDefault(); if (nombre.trim()) void hacer('nuevo', () => onNuevo(nombre.trim())) }}>
      <label className="cp-campo"><Ic n="album" size={18} />
        <input autoFocus={!hay.length} value={nombre} onChange={e => { setNombre(e.target.value); setErr('') }} placeholder="Nuevo álbum: ponle nombre" aria-label="Nombre del álbum nuevo" maxLength={60} /></label>
      <button className="btn-primary" disabled={!!busy || !nombre.trim()}>{busy === 'nuevo' ? 'Creando…' : 'Crear y añadir'}</button>
    </form>
    {err && <p className="cp-error" role="alert">{err}</p>}
    {!!hay.length && <><span className="section-kicker">O ELIGE UNO</span>
      <div className="nube-elegir">{hay.map(a => <button type="button" key={a.id} disabled={!!busy} onClick={() => void hacer(a.id, () => onElegir(a))}>
        <Portada ruta={a.portada} /><span><strong>{a.nombre}</strong><small>{busy === a.id ? 'Añadiendo…' : plural(a.n, 'elemento', 'elementos')}</small></span></button>)}</div></>}
  </Hoja>
}

/** Crear un álbum o cambiarle el nombre (el servidor avisa si ya hay otro con ese nombre) */
export function NombreAlbum({ titulo, inicial = '', boton, onGuardar, onClose }: { titulo: string; inicial?: string; boton: string; onGuardar: (nombre: string) => Promise<void>; onClose: () => void }) {
  const [n, setN] = useState(inicial)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function ok(e: FormEvent) {
    e.preventDefault()
    const v = n.trim()
    if (!v || v === inicial) return
    setBusy(true); setErr('')
    try { await onGuardar(v) } catch (x) { setErr(msg(x)) } finally { setBusy(false) }
  }
  return <Hoja titulo={titulo} onClose={onClose}>
    <form onSubmit={e => void ok(e)}>
      <label className="cp-campo"><input autoFocus value={n} onChange={e => { setN(e.target.value); setErr('') }} placeholder="Por ejemplo: Viaje a Valencia" aria-label="Nombre del álbum" maxLength={60} /></label>
      {err && <p className="cp-error" role="alert">{err}</p>}
      <div className="cp-botones"><button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" disabled={busy || !n.trim() || n.trim() === inicial}>{busy ? 'Guardando…' : boton}</button></div>
    </form>
  </Hoja>
}

/** Borrar un álbum no borra ningún archivo: se dice claro antes */
export function BorrarAlbum({ a, onBorrar, onClose }: { a: Album; onBorrar: () => Promise<void>; onClose: () => void }) {
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function ok() {
    setBusy(true); setErr('')
    try { await onBorrar() } catch (x) { setErr(msg(x)) } finally { setBusy(false) }
  }
  return <Hoja titulo="¿Borrar este álbum?" sub={a.nombre} onClose={onClose}>
    <p className="cp-nota"><Ic n="lock" size={15} /> Solo se borra el álbum. Sus fotos y vídeos no se tocan: siguen en su carpeta.</p>
    {err && <p className="cp-error" role="alert">{err}</p>}
    <div className="cp-botones"><button type="button" className="btn-secondary" onClick={onClose} autoFocus>Cancelar</button>
      <button type="button" className="btn-primary nube-peligro" disabled={busy} onClick={() => void ok()}>{busy ? 'Borrando…' : 'Borrar álbum'}</button></div>
  </Hoja>
}
