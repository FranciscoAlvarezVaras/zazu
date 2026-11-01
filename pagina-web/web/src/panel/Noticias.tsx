/* «Noticias»: los titulares del día que recoge zazu/scripts/noticias.py (07:00, 14:00, 21:00) desde fuentes públicas
   gratuitas. Cuatro apartados (Venezuela, España, IA, Mundo) con chips que se deslizan en horizontal para ver uno solo.
   Estilo Google Noticias/Discover: en cada apartado una DESTACADA con la foto grande y el titular en serif, y el resto
   en filas con miniatura cuadrada a la derecha. Móvil a una columna; en escritorio los apartados van en dos columnas.
   Las fotos las baja el recolector al servidor y aquí se piden a /api/noticias/img/<sha1>.webp (nada de terceros:
   la CSP solo deja imágenes propias). Hueco de tamaño fijo (aspect-ratio) para que nada salte al cargar; si una
   imagen falla, la noticia se queda sin ella. Cada noticia abre el artículo en el navegador.
   Las invitadas (2026-10-22) ven LAS SUYAS (/api/inv/noticias, noticias_invitadas.py): la primera vez eligen con casillas
   sus países y sus temas; luego sus apartados con el mismo estilo, un resumen corto y el botón «Elegir mis noticias».
   Contenido de terceros: aquí solo son enlaces y texto. */
import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { Ctx } from '../ctx'
import { post, useFetch } from '../lib'
import { Esqueleto, Fallo, Icono } from './ui'
import { relativa } from './relativa'
import './noticias-inv.css'

type Item = { titulo: string; fuente: string; url: string; fecha: string; img?: string; resumen?: string }
type Apartado = { clave: string; titulo: string; items: Item[] }
type Noticias = { ok: boolean; fecha?: string; hoy?: boolean; generado?: string; apartados: Apartado[]; fuentes_caidas: string[] }

type Opcion = { clave: string; nombre: string }
/** Lo de una invitada: lo que eligió (o lo que se le propone, si aún no eligió), el catálogo y sus apartados. */
type NoticiasInv = { ok: boolean; elegido: boolean; paises: string[]; temas: string[]; catalogo: { paises: Opcion[]; temas: Opcion[] };
  apartados: Apartado[]; fuentes_caidas: string[]; pendiente: boolean; generado?: string | null; hoy?: boolean }

const FILAS_RESUMEN = 4   // en «Todo», cuántas filas van bajo la destacada antes de «Ver más»
const CHIP_KEY = 'zazu:noticias:apartado'
const CHIP_KEY_INV = 'zazu:noticias-inv:apartado'
const IMG_FRAN = '/api/noticias/img/'
const IMG_INV = '/api/inv/noticias/img/'

/** «hoy a las 14:32» / «ayer a las 21:00» / la fecha, a partir de la marca `generado`. */
function actualizado(gen?: string, hoy?: boolean): string {
  if (!gen) return ''
  const d = new Date(gen)
  if (isNaN(d.getTime())) return ''
  const h = d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
  if (hoy) return `hoy a las ${h}`
  return `${d.toLocaleDateString('es', { day: 'numeric', month: 'long' })} a las ${h}`
}

/** La inicial del medio, como el «favicon» de Google Noticias. */
function inicial(fuente: string): string {
  const s = (fuente || '').trim()
  return s ? s[0].toUpperCase() : '•'
}

function leerChip(clave: string): string {
  try { return localStorage.getItem(clave) || '' } catch { return '' }
}
function guardarChip(clave: string, v: string) {
  try { localStorage.setItem(clave, v) } catch { /* sin almacenamiento: no pasa nada */ }
}

/** La miniatura (propia del servidor). El hueco tiene tamaño fijo; si la imagen falla, `onFallo` la quita. */
function Foto({ img, base, className, onFallo }: { img: string; base: string; className: string; onFallo: () => void }) {
  return <span className={className}>
    <img src={`${base}${img}.webp`} alt="" loading="lazy" decoding="async" onError={onFallo} />
  </span>
}

function Medio({ it }: { it: Item }) {
  const cuando = relativa(it.fecha)
  return <span className="not-medio">
    <span className="not-medio-chip" aria-hidden="true">{inicial(it.fuente)}</span>
    <span className="not-medio-nombre">{it.fuente || 'Fuente'}</span>
    {cuando && <><span className="not-medio-punto" aria-hidden="true">·</span><span className="not-medio-hora">{cuando}</span></>}
  </span>
}

/** La destacada: foto grande arriba (16:9), el titular en serif y, si lo trae, el resumen. */
function Destacada({ it, base }: { it: Item; base: string }) {
  const [roto, setRoto] = useState(false)
  const conImg = !!it.img && !roto
  return <a href={it.url} target="_blank" rel="noopener noreferrer" className={'not-dest' + (conImg ? '' : ' sin-foto')}>
    {conImg && <Foto img={it.img!} base={base} className="not-dest-foto" onFallo={() => setRoto(true)} />}
    <span className="not-dest-txt">
      <Medio it={it} />
      <h3 className="not-dest-titulo">{it.titulo}</h3>
      {it.resumen && <span className="not-resumen">{it.resumen}</span>}
    </span>
  </a>
}

/** Una fila: medio y hora, titular (3 líneas como mucho), el resumen si lo trae y miniatura cuadrada a la derecha. */
function Fila({ it, base }: { it: Item; base: string }) {
  const [roto, setRoto] = useState(false)
  const conImg = !!it.img && !roto
  return <a href={it.url} target="_blank" rel="noopener noreferrer" className="not-fila">
    <span className="not-fila-txt">
      <Medio it={it} />
      <h3 className="not-fila-titulo">{it.titulo}</h3>
      {it.resumen && <span className="not-fila-resumen">{it.resumen}</span>}
    </span>
    {conImg && <Foto img={it.img!} base={base} className="not-fila-foto" onFallo={() => setRoto(true)} />}
  </a>
}

function Grupo({ a, resumen, verMas, base }: { a: Apartado; resumen: boolean; verMas: () => void; base: string }) {
  if (!a.items.length) return null
  // destaca la primera noticia que trae foto (si ninguna la trae, la primera)
  const iDest = Math.max(0, a.items.findIndex(it => !!it.img))
  const dest = a.items[iDest]
  const resto = a.items.filter((_, i) => i !== iDest)
  const filas = resumen ? resto.slice(0, FILAS_RESUMEN) : resto
  const quedan = resto.length - filas.length
  const id = `not-${a.clave}`
  return <section className={'not-grupo' + (resumen ? '' : ' solo')} aria-labelledby={id}>
    <h2 id={id} className="not-grupo-titulo">{a.titulo}</h2>
    <div className="not-grupo-cuerpo">
      <Destacada it={dest} base={base} />
      {filas.length > 0 && <div className="not-filas">
        {filas.map((it, i) => <Fila key={a.clave + i + it.url} it={it} base={base} />)}
        {quedan > 0 && <button type="button" className="not-mas" onClick={verMas}>
          Ver {quedan} más de {a.titulo} <Icono n="chevron" size={16} />
        </button>}
      </div>}
    </div>
  </section>
}

/** Chips de apartado (se deslizan; «Todo» o uno solo), el aviso de fuentes caídas y los apartados. Lo usan Fran y las invitadas. */
function Lista({ apartados, caidas, base, chipKey, arriba }: { apartados: Apartado[]; caidas: string[]; base: string; chipKey: string; arriba: RefObject<HTMLDivElement | null> }) {
  const [chip, setChipEstado] = useState(() => leerChip(chipKey))
  const conItems = apartados.filter(a => a.items.length)
  const elegido = conItems.find(a => a.clave === chip)
  const visibles = elegido ? [elegido] : conItems

  const setChip = (v: string) => {
    setChipEstado(v); guardarChip(chipKey, v)
    arriba.current?.scrollIntoView({ block: 'start' })   // el scroll va dentro del panel, no en window
  }

  return <>
    {conItems.length > 1 && <nav className="not-chips" aria-label="Apartados">
      {[{ clave: '', titulo: 'Todo' }, ...conItems].map(a =>
        <button key={a.clave || 'todo'} type="button" className="not-chip" aria-pressed={(elegido?.clave || '') === a.clave}
          onClick={() => setChip(a.clave)}>{a.titulo}</button>)}
    </nav>}
    {caidas.length > 0 && <p className="not-aviso" role="note">
      Alguna fuente no respondió esta vez ({caidas.join(', ')}); el resto está al día.
    </p>}
    {!conItems.length
      ? <p className="pz-vacio">No llegó ningún titular esta vez. Se vuelve a intentar en el próximo pase.</p>
      : <div className={'not-grupos' + (elegido ? ' solo' : '')}>
        {visibles.map(a => <Grupo key={a.clave} a={a} resumen={!elegido} verMas={() => setChip(a.clave)} base={base} />)}
      </div>}
  </>
}

/** Fran: sus noticias de siempre, recogidas por zazu/scripts/noticias.py. */
function NoticiasFran() {
  const r = useFetch<Noticias>('/api/noticias', 300000)
  const d = r.data
  const arriba = useRef<HTMLDivElement>(null)
  const cuando = actualizado(d?.generado, d?.hoy)

  return <div className="pz-page not-page" ref={arriba}>
    <header className="pz-cab-lista not-cab">
      <div>
        <h1>Noticias</h1>
        {cuando && <p className="not-cuando">Actualizado {cuando}</p>}
      </div>
      <button type="button" className="not-actualizar" onClick={() => r.reload()} disabled={r.loading} aria-label="Actualizar las noticias">
        <Icono n="repeat" size={16} /> <span className="not-actualizar-txt">Actualizar</span>
      </button>
    </header>

    {!d && r.loading && <><p className="pz-nota" role="status">Buscando los titulares del día…</p><Esqueleto filas={4} alto={96} /></>}
    {!d && r.error && <Fallo texto={`No pude leer las noticias: ${r.error}.`} reintentar={() => void r.reload()} />}

    {d && !d.ok && <p className="pz-vacio">Aún no hay noticias recogidas. Zazu las prepara a las 07:00, 14:00 y 21:00.</p>}

    {d && d.ok && <Lista apartados={d.apartados} caidas={d.fuentes_caidas} base={IMG_FRAN} chipKey={CHIP_KEY} arriba={arriba} />}
  </div>
}

/** Casillas de una lista (países o temas). */
function Casillas({ titulo, ops, marcadas, cambiar }: { titulo: string; ops: Opcion[]; marcadas: string[]; cambiar: (v: string[]) => void }) {
  return <fieldset className="ninv-grupo">
    <legend className="ninv-leyenda">{titulo}</legend>
    <div className="ninv-ops">
      {ops.map(o => {
        const on = marcadas.includes(o.clave)
        return <label key={o.clave} className={'ninv-op' + (on ? ' on' : '')}>
          <input type="checkbox" checked={on} onChange={() => cambiar(on ? marcadas.filter(x => x !== o.clave) : [...marcadas, o.clave])} />
          <span>{o.nombre}</span>
        </label>
      })}
    </div>
  </fieldset>
}

/** «¿Qué noticias quieres?»: países y temas con casillas. Viene marcado su país (de Tu espacio) y «Mundo», o lo que ya eligió. */
function Selector({ d, listo, cancelar }: { d: NoticiasInv; listo: () => Promise<void>; cancelar?: () => void }) {
  const [paises, setPaises] = useState(d.paises)
  const [temas, setTemas] = useState(d.temas)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const vacio = !paises.length && !temas.length

  const guardar = async () => {
    setEnviando(true); setError('')
    try { await post('/api/inv/noticias/elegir', { paises, temas }); await listo() }
    catch (e) { setError((e as Error).message) }
    finally { setEnviando(false) }
  }

  return <form className="ninv-form" onSubmit={e => { e.preventDefault(); if (!vacio && !enviando) void guardar() }}>
    <p className="ninv-intro">Dime qué te interesa y te junto los titulares de periódicos conocidos. Puedes cambiarlo cuando quieras.</p>
    <Casillas titulo="¿De qué país o países?" ops={d.catalogo.paises} marcadas={paises} cambiar={setPaises} />
    <Casillas titulo="¿Qué temas te interesan?" ops={d.catalogo.temas} marcadas={temas} cambiar={setTemas} />
    {error && <p className="ninv-error" role="alert">No pude guardarlo: {error}.</p>}
    <div className="ninv-acciones">
      <button type="submit" className="pz-btn pz-btn-primario" disabled={vacio || enviando}>
        {enviando ? 'Preparando tus noticias…' : 'Ver mis noticias'}
      </button>
      {cancelar && <button type="button" className="pz-btn pz-btn-texto" onClick={cancelar} disabled={enviando}>Cancelar</button>}
      {vacio && <span className="ninv-nota">Marca al menos un país o un tema.</span>}
    </div>
  </form>
}

/** Una invitada: la primera vez, el selector; después, sus noticias. Mientras llegan fuentes o fotos, vuelve a preguntar unas veces. */
function NoticiasInvitada() {
  const r = useFetch<NoticiasInv>('/api/inv/noticias', 600000)
  const d = r.data
  const [editando, setEditando] = useState(false)
  const arriba = useRef<HTMLDivElement>(null)
  const intentos = useRef(0)
  const { reload } = r
  useEffect(() => {
    if (!d?.pendiente || intentos.current >= 4) return
    const t = setTimeout(() => { intentos.current++; void reload() }, 5000)
    return () => clearTimeout(t)
  }, [d, reload])

  const preguntar = !!d && (!d.elegido || editando)
  const cuando = d && !preguntar ? actualizado(d.generado || undefined, d.hoy) : ''
  const hay = !!d && d.apartados.some(a => a.items.length)

  return <div className="pz-page not-page" ref={arriba}>
    <header className="pz-cab-lista not-cab">
      <div>
        <h1>{preguntar ? '¿Qué noticias quieres?' : 'Noticias'}</h1>
        {cuando && <p className="not-cuando">Actualizado {cuando}</p>}
      </div>
      {d && !preguntar && <div className="ninv-botones">
        <button type="button" className="not-actualizar" onClick={() => setEditando(true)}>
          <Icono n="pen" size={16} /> Elegir mis noticias
        </button>
        <button type="button" className="not-actualizar" onClick={() => { intentos.current = 0; void reload() }} disabled={r.loading} aria-label="Actualizar las noticias">
          <Icono n="repeat" size={16} /> <span className="not-actualizar-txt">Actualizar</span>
        </button>
      </div>}
    </header>

    {!d && r.loading && <><p className="pz-nota" role="status">Un momento…</p><Esqueleto filas={4} alto={96} /></>}
    {!d && r.error && <Fallo texto={`No pude leer tus noticias: ${r.error}.`} reintentar={() => void reload()} />}

    {d && preguntar && <Selector key={d.paises.join() + '|' + d.temas.join()} d={d}
      listo={async () => { intentos.current = 0; await reload(); setEditando(false) }}
      cancelar={d.elegido ? () => setEditando(false) : undefined} />}

    {d && !preguntar && (!hay && d.pendiente
      ? <><p className="pz-nota" role="status">Buscando tus titulares…</p><Esqueleto filas={4} alto={96} /></>
      : <Lista apartados={d.apartados} caidas={d.fuentes_caidas} base={IMG_INV} chipKey={CHIP_KEY_INV} arriba={arriba} />)}
  </div>
}

export default function Noticias(ctx: Ctx) {
  const [probar, setProbar] = useState(false)   // Fran: ver y probar lo que ven las invitadas (se guarda en su cuenta, no cambia sus noticias)
  if (ctx.me?.role === 'guest') return <NoticiasInvitada />
  return <>
    <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '8px 16px 0' }}>
      <button type="button" className="pz-btn" onClick={() => setProbar(!probar)}>{probar ? 'Volver a mis noticias' : 'Probar las noticias de los invitados'}</button></div>
    {probar ? <NoticiasInvitada /> : <NoticiasFran />}</>
}
