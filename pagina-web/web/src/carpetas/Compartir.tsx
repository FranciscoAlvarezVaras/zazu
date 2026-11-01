import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Icon } from '../icons'
import { base, kindOf } from './api'
import { Hoja, Ic } from './ui'
import type { Aviso } from './ui'
import { copiar, crearEnlace, enCuanto, fechaHora, mini, msg, plural, revocarEnlace, urlEnlace, verEnlaces } from './nube'
import type { Enlace, Medio } from './nube'

const DURACIONES: [number, string][] = [[1, '1 hora'], [24, '1 día'], [168, '7 días'], [720, '30 días']]
const alSeleccionar = (e: { currentTarget: HTMLInputElement }) => e.currentTarget.select()
const detalle = (e: Pick<Enlace, 'caduca' | 'visitas' | 'clave'>) => [`Caduca el ${fechaHora(e.caduca)} (${enCuanto(e.caduca)})`, plural(e.visitas || 0, 'visita', 'visitas'), e.clave ? 'con clave' : ''].filter(Boolean).join(' · ')

/** Una fila de enlace activo: Copiar y Dejar de compartir */
function FilaEnlace({ e, titulo, copiado, ocupado, onCopiar, onDejar }: { e: Enlace; titulo?: string; copiado: boolean; ocupado: boolean; onCopiar: () => void; onDejar: () => void }) {
  const media = ['image', 'video'].includes(kindOf(base(e.path)))
  return <div className="nube-enlace">
    {titulo !== undefined && <span className="nube-portada">{media ? <img src={mini(e.path)} alt="" loading="lazy" decoding="async" onError={ev => { ev.currentTarget.style.visibility = 'hidden' }} /> : <Ic n="link" size={22} />}</span>}
    <span className="nube-enlace-txt">{titulo !== undefined && <strong>{titulo}</strong>}<small>{detalle(e)}</small></span>
    <button type="button" className="btn-secondary" onClick={onCopiar}><Ic n="copy" size={16} /> {copiado ? '¡Copiado!' : 'Copiar'}</button>
    <button type="button" className="btn-secondary nube-dejar" disabled={ocupado} onClick={onDejar}>{ocupado ? 'Quitando…' : 'Dejar de compartir'}</button>
  </div>
}

/** Los enlaces activos (de un archivo, o todos) con el estado de copiar y revocar, que comparten las dos hojas */
function useEnlaces(path: string | undefined, avisar: (a: Aviso) => void) {
  const [lista, setLista] = useState<Enlace[] | null>(null)
  const [err, setErr] = useState('')
  const [ocupado, setOcupado] = useState('')
  const [copiado, setCopiado] = useState('')
  const cargar = useCallback(async () => {
    try { const d = await verEnlaces(path); setLista((Array.isArray(d.items) ? d.items : []).filter(e => e && typeof e.token === 'string').sort((a, b) => a.caduca - b.caduca)); setErr('') }
    catch (e) { setErr(msg(e)) }
  }, [path])
  useEffect(() => { void cargar() }, [cargar])
  async function copiarUrl(token: string, url: string) {
    if (await copiar(url)) { setCopiado(token); setTimeout(() => setCopiado(c => c === token ? '' : c), 2000) }
    else avisar({ texto: 'No pude copiarlo. Toca el enlace para seleccionarlo y cópialo a mano.' })
  }
  async function dejar(e: Enlace) {
    setOcupado(e.token)
    try { await revocarEnlace(e.token); setLista(l => l && l.filter(x => x.token !== e.token)); avisar({ texto: 'Dejaste de compartirlo: ese enlace ya no abre nada.' }) }
    catch (x) { avisar({ texto: `No se pudo quitar el enlace: ${msg(x)}` }) }
    finally { setOcupado('') }
  }
  return { lista, err, ocupado, copiado, cargar, copiarUrl, dejar }
}

/** «Compartir» de un archivo: un enlace con caducidad (y clave si quieres) que cualquiera puede abrir sin entrar en Zazu */
export function CompartirHoja({ m, avisar, onClose }: { m: Medio; avisar: (a: Aviso) => void; onClose: () => void }) {
  const [horas, setHoras] = useState(24)
  const [clave, setClave] = useState('')
  const [sinGps, setSinGps] = useState(true)   // las fotos y vídeos del móvil llevan dentro el lugar donde se hicieron: por defecto, el enlace va sin eso
  const [creando, setCreando] = useState(false)
  const [err, setErr] = useState('')
  const [nuevo, setNuevo] = useState<{ token: string; url: string; caduca: number; clave: boolean; gps: boolean; sinGps: boolean } | null>(null)
  const E = useEnlaces(m.path, avisar)
  const listo = useRef<HTMLDivElement>(null)
  useEffect(() => { if (nuevo) listo.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [nuevo])   // el enlace recién creado queda a la vista
  async function crear(ev: FormEvent) {
    ev.preventDefault()
    if (creando) return
    setCreando(true); setErr('')
    try {
      const d = await crearEnlace(m.path, horas, clave.trim(), sinGps)
      if (!d || typeof d.token !== 'string' || !d.token) throw new Error('el servidor no devolvió el enlace')
      setNuevo({ token: d.token, url: d.url || urlEnlace({ token: d.token }), caduca: Number(d.caduca) || 0, clave: !!clave.trim(), gps: !!d.gps, sinGps: !!d.sin_gps })
      void E.cargar()
    } catch (x) { setErr(msg(x)) } finally { setCreando(false) }
  }
  const otros = (E.lista || []).filter(e => e.token !== nuevo?.token)
  return <Hoja titulo="Compartir" sub={m.name} onClose={onClose}>
    <p className="nube-publico"><Ic n="eye" size={18} /><span>Cualquiera con el enlace podrá ver este archivo hasta que caduque.</span></p>
    <form onSubmit={ev => void crear(ev)}>
      <fieldset className="nube-duracion"><legend>¿Cuánto tiempo?</legend>
        <div>{DURACIONES.map(([h, t]) => <label key={h} className="nube-opc"><input type="radio" name="nube-duracion" checked={horas === h} onChange={() => setHoras(h)} /><span>{t}</span></label>)}</div></fieldset>
      <label className="nube-casilla"><input type="checkbox" checked={sinGps} onChange={ev => setSinGps(ev.target.checked)} />
        <span><strong>Quitar la ubicación</strong><small>Las fotos y vídeos del móvil guardan dónde se hicieron. Así, quien abra el enlace no lo verá.</small></span></label>
      <label className="nube-clave"><span>Clave (si quieres)</span>
        <input type="text" value={clave} onChange={ev => setClave(ev.target.value)} minLength={6} maxLength={64} autoComplete="off" autoCapitalize="off" spellCheck={false} placeholder="Quien abra el enlace tendrá que escribirla" /></label>
      {err && <p className="cp-error" role="alert">{err}</p>}
      <button className="btn-primary cp-ancho" disabled={creando}><Ic n="link" size={18} /> {creando ? 'Creando…' : nuevo ? 'Crear otro enlace' : 'Crear enlace'}</button>
    </form>
    {nuevo && <div className="nube-nuevo-enlace" role="status" ref={listo}>
      <strong>Enlace listo</strong>
      <div className="nube-url"><input readOnly value={nuevo.url} onFocus={alSeleccionar} aria-label="Enlace para compartir" />
        <button type="button" className="btn-primary" onClick={() => void E.copiarUrl(nuevo.token, nuevo.url)}><Ic n="copy" size={16} /> {E.copiado === nuevo.token ? '¡Copiado!' : 'Copiar'}</button></div>
      {'share' in navigator && <button type="button" className="btn-secondary" onClick={() => void navigator.share({ title: m.name, url: nuevo.url }).catch(() => { /* lo cerró */ })}><Ic n="share" size={16} /> Enviar con otra app…</button>}
      <small>Caduca el {fechaHora(nuevo.caduca)} ({enCuanto(nuevo.caduca)}){nuevo.clave ? ' · con clave' : ''}</small>
      {nuevo.gps && (nuevo.sinGps ? <small>Este enlace va sin la ubicación del archivo.</small>
        : <p className="nube-publico"><Icon name="pin" size={18} /><span>Ojo: este archivo lleva la ubicación y quien abra el enlace podrá verla.</span></p>)}
    </div>}
    {E.err && !E.lista && <p className="cp-vacio" role="alert">No pude ver los enlaces que ya tenías: {E.err}. <button type="button" className="text-link cp-en-linea" onClick={() => void E.cargar()}>Reintentar</button></p>}
    {otros.length > 0 && <section className="nube-activos"><span className="section-kicker">{nuevo ? 'OTROS ENLACES ACTIVOS DE ESTE ARCHIVO' : 'ENLACES ACTIVOS DE ESTE ARCHIVO'}</span>
      {otros.map(e => <FilaEnlace key={e.token} e={e} copiado={E.copiado === e.token} ocupado={E.ocupado === e.token} onCopiar={() => void E.copiarUrl(e.token, urlEnlace(e))} onDejar={() => void E.dejar(e)} />)}</section>}
  </Hoja>
}

/** «Mis enlaces»: todo lo que está compartido ahora mismo, para quitarlo desde un solo sitio */
export function MisEnlaces({ avisar, onClose }: { avisar: (a: Aviso) => void; onClose: () => void }) {
  const E = useEnlaces(undefined, avisar)
  return <Hoja titulo="Mis enlaces" sub={E.lista ? plural(E.lista.length, 'enlace activo', 'enlaces activos') : 'Lo que tienes compartido'} ancha onClose={onClose}>
    {E.err && !E.lista && <p className="cp-vacio" role="alert">No pude ver tus enlaces: {E.err}. <button type="button" className="text-link cp-en-linea" onClick={() => void E.cargar()}>Reintentar</button></p>}
    {!E.err && !E.lista && <p className="cp-vacio">Cargando…</p>}
    {E.lista && !E.lista.length && <p className="cp-vacio">No tienes ningún enlace activo.<br />Para compartir algo, ábrelo en la galería y toca «Compartir».</p>}
    {E.lista && E.lista.length > 0 && <>
      <p className="nube-publico"><Icon name="clock" size={18} /><span>Cada enlace deja de abrirse solo cuando caduca. Aquí puedes quitarlo antes.</span></p>
      <div className="nube-activos">{E.lista.map(e => <FilaEnlace key={e.token} e={e} titulo={base(e.path)} copiado={E.copiado === e.token} ocupado={E.ocupado === e.token} onCopiar={() => void E.copiarUrl(e.token, urlEnlace(e))} onDejar={() => void E.dejar(e)} />)}</div></>}
  </Hoja>
}
