/* Ofertas de empleo: las que encuentra el buscador (empleo-buscador), en tarjetas con ficha al lado (escritorio) o a pantalla completa (móvil).
   Diseño: Figma «HolaZazu · Ofertas de empleo (estilo LinkedIn)». Guardar y «No me interesa» son los clics que enseñan al buscador lo que te gusta.
   Aquí no se envía nada: «Ver la oferta» abre su web y la candidatura la haces tú. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { irA, post, useFetch, useParams } from '../lib'
import type { Ctx } from '../ctx'
import { useMedia } from '../tema'
import { useDatosTableros } from './datos'
import { Esqueleto, Fallo, Icono } from './ui'
import './ofertas.css'

export type Oferta = { id: string; titulo: string; empresa: string; lugar: string; pais: string; remoto: boolean; fecha: string; pista: string; puntos: number; estado: string; fuente: string; visto: number; url: string }
type Cuentas = { activas: number; nuevas: number; guardadas: number; descartadas: number; candidaturas: number }
type Lista = { ok: boolean; total: number; items: Oferta[]; cuentas: Cuentas }
type Detalle = Oferta & { motivos: string[]; parrafos: string[]; etiquetas: string[]; salario: string }
type Marca = 'vista' | 'guardada' | 'descartada' | 'nueva' | 'quitar'

/** Lista y ficha lado a lado solo cuando cabe (con el menú lateral, desde 1100 px); por debajo, la ficha ocupa la pantalla como en el móvil. */
export const ANCHO_DOS = '(min-width: 1100px)'
export const useDosColumnas = () => useMedia(ANCHO_DOS)
const POR_PAGINA = 30
const GRUPOS: { id: string; texto: string; ver: string; pista?: string }[] = [
  { id: 'todas', texto: 'Todas', ver: 'activas' }, { id: 'datos', texto: 'Datos', ver: 'activas', pista: 'dev' }, { id: 'marketing', texto: 'Marketing', ver: 'activas', pista: 'marketing' },
  { id: 'guardadas', texto: 'Guardadas', ver: 'guardadas' }, { id: 'descartadas', texto: 'Descartadas', ver: 'descartadas' }]
const ID_OFERTA = /^[0-9a-f]{4,32}$/

/** «hoy», «ayer», «hace 3 días», «hace 2 semanas» según la fecha de la oferta (AAAA-MM-DD). */
export function haceDe(fecha: string, ahora = new Date()): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fecha)
  if (!m) return ''
  const d = Math.round((Date.UTC(ahora.getFullYear(), ahora.getMonth(), ahora.getDate()) - Date.UTC(+m[1], +m[2] - 1, +m[3])) / 864e5)
  if (d <= 0) return 'Hoy'
  if (d === 1) return 'Ayer'
  if (d < 14) return `Hace ${d} días`
  if (d < 60) return `Hace ${Math.round(d / 7)} semanas`
  return `Hace ${Math.round(d / 30)} meses`
}
/** «Encaja mucho / bien / algo / poco» según los puntos del buscador (0–100). */
export const encaja = (p: number) => p >= 70 ? 'mucho' : p >= 50 ? 'bien' : p >= 35 ? 'algo' : 'poco'
const tono = (s: string) => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 5; return h }
const inicialDe = (s: string) => (s.replace(/[^\p{L}\p{N}]/gu, '')[0] || '·').toUpperCase()
const lugarDe = (o: Pick<Oferta, 'lugar' | 'remoto'>) => [o.lugar, o.remoto && !/remot/i.test(o.lugar) ? 'Remoto' : ''].filter(Boolean).join(' · ')

function Logo({ empresa, grande }: { empresa: string; grande?: boolean }) {
  return <span className={`pz-of-logo${grande ? ' grande' : ''}`} data-tono={tono(empresa)} aria-hidden="true">{inicialDe(empresa)}</span>
}

function Tarjeta({ o, activa, onAbrir, onMarcar }: { o: Oferta; activa: boolean; onAbrir: () => void; onMarcar: (m: Marca) => void }) {
  const guardada = o.estado === 'guardada', nueva = o.estado === 'nueva'
  return <li className={`pz-of-tarjeta${activa ? ' activa' : ''}`}>
    <div className="pz-of-cab">
      <button type="button" className="pz-of-abrir" onClick={onAbrir} aria-current={activa ? 'true' : undefined}>
        <Logo empresa={o.empresa} />
        <span className="pz-of-texto">
          <span className="pz-of-titulo">{o.titulo}</span>
          <span className="pz-of-empresa">{o.empresa}</span>
          <span className="pz-of-lugar">{lugarDe(o)}</span>
        </span>
      </button>
      <button type="button" className="pz-of-icono" onClick={() => onMarcar(o.estado === 'descartada' ? 'quitar' : 'descartada')} aria-label={o.estado === 'descartada' ? `Recuperar «${o.titulo}»` : `No me interesa «${o.titulo}»`}>
        <Icono n={o.estado === 'descartada' ? 'repeat' : 'close'} size={20} /></button>
      <button type="button" className="pz-of-icono" onClick={() => onMarcar(guardada ? 'quitar' : 'guardada')} aria-pressed={guardada} aria-label={guardada ? `Quitar de guardadas «${o.titulo}»` : `Guardar «${o.titulo}»`}>
        <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill={guardada ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"><path d="M6 4h12v17l-6-4-6 4V4Z" /></svg></button>
    </div>
    <div className="pz-of-pie">
      <span className={`pz-of-etq encaje-${encaja(o.puntos)}`} title="Puntos del buscador según tu perfil (de 0 a 100)">Encaje {o.puntos}</span>
      {nueva && <span className="pz-of-etq nueva">Nueva</span>}
      {o.estado === 'candidatura' && <span className="pz-of-etq nueva">En candidaturas</span>}
      <span className="pz-of-meta">{[haceDe(o.fecha), o.fuente].filter(Boolean).join(' · ')}</span>
    </div>
  </li>
}

function Ficha({ id, rev, atras, onMarcar, onCandidatura, ocupado }: { id: string; rev: number; atras?: () => void; onMarcar: (id: string, m: Marca) => void; onCandidatura: (id: string) => void; ocupado: boolean }) {
  const d = useFetch<{ ok: boolean } & Detalle>(`/api/ofertas/${id}?r=${rev}`)   // `r` solo cambia la dirección: así se vuelve a pedir tras marcar
  const o = d.data
  if (!o) return <section className="pz-of-ficha" aria-label="Oferta">
    {atras && <button type="button" className="pz-btn pz-btn-texto pz-of-atras" onClick={atras}><Icono n="back" size={18} /> Volver</button>}
    {d.error ? <Fallo texto={`No pude abrir esta oferta: ${d.error}.`} reintentar={() => void d.reload()} /> : <Esqueleto filas={3} alto={90} />}</section>
  const guardada = o.estado === 'guardada', enCand = o.estado === 'candidatura'
  return <section className="pz-of-ficha" aria-label={`Oferta: ${o.titulo}`}>
    {atras && <button type="button" className="pz-btn pz-btn-texto pz-of-atras" onClick={atras}><Icono n="back" size={18} /> Volver a las ofertas</button>}
    <div className="pz-of-hero">
      <div className="pz-of-hero-cab"><Logo empresa={o.empresa} grande /><div><h2>{o.titulo}</h2><p>{[o.empresa, lugarDe(o)].filter(Boolean).join(' · ')}</p></div></div>
      <div className="pz-of-etqs">
        <span className={`pz-of-etq encaje-${encaja(o.puntos)}`}>Encaje {o.puntos} de 100 · {encaja(o.puntos)}</span>
        {o.estado === 'nueva' && <span className="pz-of-etq nueva">Nueva</span>}
        {o.remoto && <span className="pz-of-etq">Remoto</span>}
        {o.salario && <span className="pz-of-etq">{o.salario}</span>}
        {haceDe(o.fecha) && <span className="pz-of-etq">{haceDe(o.fecha)} · {o.fuente}</span>}
      </div>
      <div className="pz-of-acciones">
        {o.url ? <a className="pz-btn pz-btn-primario" href={o.url} target="_blank" rel="noopener noreferrer">Ver la oferta <Icono n="link" size={18} /></a>
          : <span className="pz-nota">Esta oferta no trae enlace.</span>}
        <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado || enCand} aria-pressed={guardada} onClick={() => onMarcar(o.id, guardada ? 'quitar' : 'guardada')}>{guardada ? 'Guardada ✓' : 'Guardar'}</button>
        <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado || enCand} onClick={() => onMarcar(o.id, o.estado === 'descartada' ? 'quitar' : 'descartada')}>{o.estado === 'descartada' ? 'Recuperar' : 'No me interesa'}</button>
      </div>
    </div>
    {o.motivos.length > 0 && <div className="pz-of-bloque"><h3>Por qué encaja</h3>
      <ul className="pz-of-motivos">{o.motivos.map((m, i) => { const x = /^([+-]\d+)\s*(.*)$/.exec(m); return <li key={i}>{x ? <><b className={x[1].startsWith('-') ? 'resta' : 'suma'}>{x[1]}</b><span>{x[2]}</span></> : <span>{m}</span>}</li> })}</ul>
      <p className="pz-nota">Los puntos salen de lo que buscas en tu perfil.</p></div>}
    <div className="pz-of-bloque"><h3>Sobre la oferta</h3>
      {o.parrafos.length ? o.parrafos.map((p, i) => <p key={i} className="pz-of-parrafo">{p}</p>) : <p className="pz-nota">Esta oferta no trae texto. Ábrela para leerla entera.</p>}
      {o.etiquetas.length > 0 && <div className="pz-of-etqs">{o.etiquetas.map(x => <span key={x} className="pz-of-etq">{x}</span>)}</div>}</div>
    <div className="pz-of-bloque"><h3>¿Te has presentado?</h3>
      <p className="pz-of-parrafo">Zazu no envía nada por ti: la candidatura la haces tú en la web de la oferta. Después la pasas aquí para seguirla.</p>
      {enCand ? <button type="button" className="pz-btn pz-btn-suave" onClick={() => { irA({ tab: 'empleo', tablero: 'candidaturas' }); window.scrollTo({ top: 0 }) }}>Ver en Candidaturas</button>
        : <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado} onClick={() => onCandidatura(o.id)}><Icono n="brief" size={18} /> Pasar a candidaturas</button>}
    </div>
  </section>
}

export default function Ofertas({ ctx }: { ctx: Ctx }) {
  const ancho = useDosColumnas()
  const tableros = useDatosTableros()
  const { tarjeta } = useParams()
  const abierta = tarjeta && ID_OFERTA.test(tarjeta) ? tarjeta : ''
  const [grupo, setGrupo] = useState('todas')
  const [remoto, setRemoto] = useState(false)
  const [espana, setEspana] = useState(false)
  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [n, setN] = useState(POR_PAGINA)
  const [ocupado, setOcupado] = useState(false)
  const [rev, setRev] = useState(0)
  const [deshacer, setDeshacer] = useState<{ id: string; marca: Marca; texto: string } | null>(null)
  const temporizador = useRef<number | undefined>(undefined)
  const g = GRUPOS.find(x => x.id === grupo) || GRUPOS[0]
  useEffect(() => { const t = window.setTimeout(() => { setQ(texto.trim()); setN(POR_PAGINA) }, 300); return () => window.clearTimeout(t) }, [texto])
  const params = new URLSearchParams({ ver: g.ver, n: String(n) })
  if (g.pista) params.set('pista', g.pista)
  if (remoto) params.set('remoto', '1')
  if (espana) params.set('espana', '1')
  if (q) params.set('q', q)
  const lista = useFetch<Lista>(`/api/ofertas?${params}`)
  const d = lista.data
  const items = d?.items ?? []
  const seleccion = abierta || (ancho ? items[0]?.id || '' : '')

  const marcar = useCallback(async (id: string, marca: Marca, callada = false) => {
    if (marca === 'vista') { const o = items.find(x => x.id === id); if (!o || o.estado !== 'nueva') return }
    setOcupado(true)
    try {
      await post('/api/ofertas/marcar', { id, estado: marca })
      if (!callada) {
        const o = items.find(x => x.id === id)
        const t = marca === 'guardada' ? 'Guardada' : marca === 'descartada' ? 'Descartada: no te la volveré a enseñar' : marca === 'quitar' ? 'Marca quitada' : ''
        window.clearTimeout(temporizador.current)
        if (t) { setDeshacer({ id, marca: marca === 'guardada' || marca === 'descartada' ? 'quitar' : 'nueva', texto: `${t}${o ? ` · ${o.titulo}` : ''}` }); temporizador.current = window.setTimeout(() => setDeshacer(null), 7000) }
        if (marca === 'descartada' && !ancho && abierta) irA({ tab: 'empleo' }, true)
      }
      setRev(v => v + 1)
      await lista.reload()
    } catch (e) { ctx.toast(`No pude guardar tu marca: ${(e as Error).message}`) }
    finally { setOcupado(false) }
  }, [items, lista, ctx, ancho, abierta])

  const abrir = (id: string) => { irA({ tab: 'empleo', tarjeta: id }); void marcar(id, 'vista', true) }

  const candidatura = async (id: string) => {
    setOcupado(true)
    try { await post('/api/ofertas/candidatura', { id }); ctx.toast('Apuntada en tus candidaturas, por enviar'); setRev(v => v + 1); void tableros.reload(); await lista.reload() }
    catch (e) { ctx.toast(`No pude apuntarla: ${(e as Error).message}`) }
    finally { setOcupado(false) }
  }
  useEffect(() => () => window.clearTimeout(temporizador.current), [])

  const cabecera = <>
    <div className="pz-of-busca"><Icono n="search" size={18} /><input type="search" value={texto} onChange={e => setTexto(e.target.value)} placeholder="Puesto, empresa o lugar" aria-label="Buscar ofertas" maxLength={60} /></div>
    <div className="pz-chips" role="group" aria-label="Filtrar ofertas">
      {GRUPOS.map(x => <button key={x.id} type="button" aria-pressed={grupo === x.id} onClick={() => { setGrupo(x.id); setN(POR_PAGINA) }}>{x.texto}{d && x.id === 'guardadas' && d.cuentas.guardadas > 0 ? ` · ${d.cuentas.guardadas}` : ''}</button>)}
      <button type="button" aria-pressed={remoto} onClick={() => { setRemoto(v => !v); setN(POR_PAGINA) }}>Remoto</button>
      <button type="button" aria-pressed={espana} onClick={() => { setEspana(v => !v); setN(POR_PAGINA) }}>España</button>
    </div>
  </>
  const resumen = d ? (d.total ? `${d.total} ${d.total === 1 ? 'oferta' : 'ofertas'}${d.cuentas.nuevas ? ` · ${d.cuentas.nuevas} ${d.cuentas.nuevas === 1 ? 'nueva' : 'nuevas'}` : ''} · las que más encajan primero` : '') : ''
  const vacio = d && !items.length ? (q || remoto || espana || g.pista || grupo !== 'todas' ? 'Ninguna oferta coincide con eso. Prueba a quitar un filtro.' : 'Todavía no hay ofertas. El buscador las revisa cada mañana a las 08:15.') : ''

  const columnaLista = <div className="pz-of-lista">
    {cabecera}
    {resumen && <p className="pz-nota" role="status">{resumen}</p>}
    {!d && lista.loading && <Esqueleto filas={4} alto={110} />}
    {!d && !lista.loading && lista.error && <Fallo texto={`No pude leer las ofertas: ${lista.error}.`} reintentar={() => void lista.reload()} />}
    {vacio && <p className="pz-vacio">{vacio}</p>}
    {items.length > 0 && <ul className="pz-of-tarjetas">{items.map(o => <Tarjeta key={o.id} o={o} activa={ancho && seleccion === o.id} onAbrir={() => abrir(o.id)} onMarcar={m => void marcar(o.id, m)} />)}</ul>}
    {d && d.total > items.length && <button type="button" className="pz-btn pz-btn-suave" onClick={() => setN(v => v + POR_PAGINA)}>Ver más ofertas ({d.total - items.length})</button>}
  </div>

  const aviso = deshacer && <div className="pz-of-deshacer" role="status"><span>{deshacer.texto}</span>
    <button type="button" className="pz-btn pz-btn-texto" onClick={() => { const x = deshacer; setDeshacer(null); void marcar(x.id, x.marca, true) }}>Deshacer</button></div>

  if (!ancho && abierta) return <div className="pz-of-movil">
    <Ficha id={abierta} atras={() => irA({ tab: 'empleo' })} onMarcar={(id, m) => void marcar(id, m)} onCandidatura={id => void candidatura(id)} rev={rev} ocupado={ocupado} />{aviso}</div>
  return <div className={`pz-of-pagina${ancho ? ' dos' : ''}`}>
    {columnaLista}
    {ancho && (seleccion ? <Ficha key={seleccion} id={seleccion} onMarcar={(id, m) => void marcar(id, m)} onCandidatura={id => void candidatura(id)} rev={rev} ocupado={ocupado} />
      : <section className="pz-of-ficha vacia"><p className="pz-nota">Elige una oferta de la lista para verla entera.</p></section>)}
    {aviso}
  </div>
}
