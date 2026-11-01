/* Los tableros como LISTAS por estado, con frases claras y botones en llano («Preparar la carta», «Ya la envié», «Recordarme en 3 días»…), y la ficha de una candidatura.
   Lo que cambia de estado usa la hoja «¿Qué ha pasado?» (endpoint de siempre: mover). Lo que no existe en el servidor (preparar la carta, recordar…) abre el chat con Zazu
   con la petición ya escrita. «Ver como columnas» enseña el tablero de siempre. */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { irA, useParams } from '../lib'
import type { Params } from '../lib'
import type { Ctx } from '../ctx'
import { useMedia } from '../tema'
import type { Columna, Tarjeta } from './api'
import type { DatosTableros } from './datos'
import { cap, fechaLarga as dia, inicial, tarjetaDe } from './formato'
import type { TableroKanban } from './formato'
import { useDatosPanel } from './datos'
import { DONDE, TERMINALES, useMover } from './Mover'
import type { AccionHoja } from './Mover'
import { diaCorto, enDias, Fallo, horaDe, Icono, plural } from './ui'

type Grupo = { id: string; titulo: string; color: string; estados: string[]; cerrado?: boolean }
const G_CAND: Grupo[] = [
  { id: 'ahora', titulo: 'Para hacer ahora', color: 'var(--pz-cat-1)', estados: ['por enviar'] },
  { id: 'espera', titulo: 'Esperando respuesta', color: 'var(--pz-cat-2)', estados: ['enviada'] },
  { id: 'prueba', titulo: 'Prueba o entrevista', color: 'var(--pz-cat-3)', estados: ['prueba', 'entrevista'] },
  { id: 'oferta', titulo: 'Con oferta', color: 'var(--pz-cat-4)', estados: ['oferta'] },
  { id: 'cerradas', titulo: 'Cerradas', color: 'var(--pz-cat-5)', estados: ['rechazada', 'descartada'], cerrado: true },
]
const G_PROY: Grupo[] = [
  { id: 'activos', titulo: 'Activos', color: 'var(--pz-cat-1)', estados: ['activo'] },
  { id: 'esperando', titulo: 'Esperando', color: 'var(--pz-cat-2)', estados: ['esperando'] },
  { id: 'pausa', titulo: 'En pausa', color: 'var(--pz-cat-5)', estados: ['en pausa'] },
  { id: 'nuevas', titulo: 'Ideas nuevas', color: 'var(--pz-cat-3)', estados: ['nueva'] },
  { id: 'hechos', titulo: 'Hechos', color: 'var(--pz-cat-4)', estados: ['hecho'], cerrado: true },
  { id: 'aparcadas', titulo: 'Aparcadas', color: 'var(--pz-cat-5)', estados: ['aparcada'], cerrado: true },
]
const CERRADA_TXT: Record<string, [string, string]> = { rechazada: ['rechazada', 'rechazadas'], descartada: ['descartada', 'descartadas'], hecho: ['hecho', 'hechos'], aparcada: ['aparcada', 'aparcadas'] }

type Cargado = { g: Grupo; tarjetas: Tarjeta[] }
function agrupar(b: TableroKanban): Cargado[] {
  const base = b.id === 'candidaturas' ? G_CAND : G_PROY
  const todas = b.columnas.flatMap(c => c.tarjetas)
  const usadas = new Set(base.flatMap(g => g.estados))
  const res: Cargado[] = base.map(g => ({ g, tarjetas: todas.filter(t => g.estados.includes(t.estado)) })).filter(x => x.tarjetas.length)
  const otras = todas.filter(t => !usadas.has(t.estado))
  if (otras.length) res.push({ g: { id: 'otras', titulo: 'Sin estado válido', color: 'var(--pz-cat-5)', estados: [] }, tarjetas: otras })
  return res
}

/** Quién y qué: «Desarrollador/a web en Lumen Studio». */
const que = (x: Tarjeta) => `«${x.puesto && x.puesto !== x.titulo ? x.puesto : x.titulo}»${x.empresa ? ` en ${x.empresa}` : ''}`
const hace = (ms: number) => { const d = Math.floor((Date.now() - ms) / 864e5); return d <= 0 ? 'hoy' : d === 1 ? 'ayer' : `hace ${d} días` }
const novedad = (x: Tarjeta) => x.mtime ? `última novedad el ${dia(new Date(x.mtime).toISOString().slice(0, 10))} (${hace(x.mtime)})` : ''

/** Lo que dice la segunda línea de cada fila de candidatura, según el estado. */
function fraseCand(x: Tarjeta): string {
  const quien = x.empresa || x.ciudad || ''
  const pasos = x.pasos.total > 0 ? `${x.pasos.hechos} de ${x.pasos.total} pasos` : ''
  switch (x.estado) {
    case 'por enviar': return [quien, 'todavía no la has enviado'].filter(Boolean).join(' · ')
    case 'enviada': return [quien, `enviada · ${novedad(x)}`].filter(Boolean).join(' · ')
    case 'prueba': return [quien, 'prueba técnica', pasos].filter(Boolean).join(' · ')
    case 'entrevista': return [quien, x.plazo ? `entrevista el ${diaCorto(x.plazo)}` : 'entrevista'].filter(Boolean).join(' · ')
    case 'oferta': return [quien, 'te han hecho una oferta'].filter(Boolean).join(' · ')
    case 'rechazada': return [quien, 'te dijeron que no'].filter(Boolean).join(' · ')
    case 'descartada': return [quien, 'la descartaste'].filter(Boolean).join(' · ')
    default: return quien
  }
}
/** El plazo, dicho en una frase (en rojo vino si ya pasó). */
function plazoFrase(x: Tarjeta): { t: string; mal: boolean } | null {
  if (!x.plazo || x.estado === 'rechazada' || x.estado === 'descartada' || x.estado === 'hecho') return null
  if (x.estado === 'entrevista') return x.vencido ? { t: `Fue el ${diaCorto(x.plazo)}`, mal: true } : { t: `${diaCorto(x.plazo)} · ${enDias(x.dias)}`, mal: false }
  if (x.vencido) return { t: `Se pasó el plazo (${dia(x.plazo)})`, mal: true }
  if (x.dias === 0) return { t: 'El plazo es hoy', mal: false }
  return { t: `Plazo: ${diaCorto(x.plazo)} · ${enDias(x.dias)}`, mal: false }
}
function fraseProy(x: Tarjeta): string {
  const pasos = x.pasos.total > 0 ? `${x.pasos.hechos} de ${x.pasos.total} pasos` : ''
  return [x.siguiente ? `Siguiente: ${x.siguiente}` : '', pasos].filter(Boolean).join(' · ') || 'Sin siguiente paso apuntado'
}

type Acciones = { principal?: AccionHoja; estado: { texto: string; destacar?: string } }
/** El botón de la siguiente acción y el que cambia de estado, según dónde esté la tarjeta. */
function accionesDe(x: Tarjeta, tablero: string, ctx: Ctx): Acciones {
  const pedir = (texto: string) => () => ctx.ask(texto, { fill: true })   // el chat se abre con la petición escrita; la mandas tú
  if (tablero !== 'candidaturas') return { principal: { texto: 'Pedir ayuda a Zazu', run: pedir(`Ayúdame con el proyecto «${x.titulo}»${x.siguiente ? `. Lo siguiente es: ${x.siguiente}` : ''}. Dime los pasos y qué necesitas de mí.`) },
    estado: { texto: TERMINALES.includes(x.estado) ? 'Reabrir' : '¿Qué ha pasado?' } }
  switch (x.estado) {
    case 'por enviar': return { principal: { texto: 'Preparar la carta', primaria: true, run: pedir(`Prepárame la carta de presentación para ${que(x)}. Usa mi CV y dime qué te falta.`) }, estado: { texto: 'Ya la envié', destacar: 'enviada' } }
    case 'enviada': return { principal: { texto: 'Recordarme en 3 días', run: pedir(`Recuérdame dentro de 3 días preguntar cómo va mi candidatura a ${que(x)}.`) }, estado: { texto: 'Me han respondido' } }
    case 'prueba': return { principal: { texto: 'Seguir con la prueba', primaria: true, run: pedir(`Ayúdame a seguir con la prueba técnica de ${que(x)}. Dime por dónde voy y qué me falta.`) }, estado: { texto: '¿Qué ha pasado?' } }
    case 'entrevista': return { principal: { texto: 'Preparar la entrevista', primaria: true, run: pedir(`Ayúdame a preparar la entrevista de ${que(x)}: repasa la oferta y dime qué preguntas pueden salir.`) }, estado: { texto: '¿Qué ha pasado?' } }
    case 'oferta': return { principal: { texto: 'Pedir consejo', run: pedir(`Me han hecho una oferta de ${que(x)}. Ayúdame a pensar qué mirar antes de contestar.`) }, estado: { texto: '¿Qué ha pasado?' } }
    default: return { estado: { texto: 'Reabrir' } }
  }
}

/** Cuántas piden que hagas algo hoy (por enviar o prueba con el plazo vencido o de hoy, y la entrevista de hoy). */
export const piden = (b: TableroKanban) => b.columnas.flatMap(c => c.tarjetas).filter(x => ((x.estado === 'por enviar' || x.estado === 'prueba') && (x.vencido || x.dias === 0)) || (x.estado === 'entrevista' && x.dias === 0)).length

function resumenLista(b: TableroKanban): string {
  const todas = b.columnas.flatMap(c => c.tarjetas)
  const abiertas = todas.filter(x => !TERMINALES.includes(x.estado)).length
  if (b.id === 'candidaturas') {
    const n = piden(b)
    return `${abiertas ? `Tienes ${plural(abiertas, 'candidatura abierta', 'candidaturas abiertas')}.` : 'No tienes candidaturas abiertas.'}${n ? ` ${n === 1 ? '1 pide que hagas algo hoy.' : `${n} piden que hagas algo hoy.`}` : abiertas ? ' Nada urgente para hoy.' : ''}`
  }
  const venc = todas.filter(x => x.vencido && !TERMINALES.includes(x.estado)).length
  return `${abiertas ? `Tienes ${plural(abiertas, 'cosa abierta', 'cosas abiertas')}.` : 'No tienes nada abierto.'}${venc ? ` ${plural(venc, 'se ha pasado de plazo', 'se han pasado de plazo')}.` : ''}`
}

/* ---------- la vista: lista por estados o columnas ---------- */
export function VistaKanban({ b, t, ctx, base, titulo }: { b: TableroKanban; t: DatosTableros; ctx: Ctx; base: Params; titulo: string }) {
  const { vista } = useParams()
  const columnas = vista === 'columnas'
  const movil = useMedia('(max-width: 899px)')
  const [filtro, setFiltro] = useState('')
  const mover = useMover(t.data || [], t, ctx)
  const grupos = agrupar(b)
  const abiertos = grupos.filter(x => !x.g.cerrado), cerrados = grupos.filter(x => x.g.cerrado)
  const visibles = filtro ? abiertos.filter(x => x.g.id === filtro) : abiertos
  const total = abiertos.reduce((a, x) => a + x.tarjetas.length, 0)
  const esEmpleo = b.id === 'candidaturas'
  const abrirFicha = (x: Tarjeta) => irA({ tab: 'empleo', tarjeta: x.ruta })
  const abrir = (x: Tarjeta, estado?: string) => { const a = accionesDe(x, b.id, ctx); mover.abrir({ tablero: b.id, t: x, acciones: a.principal ? [a.principal] : undefined, destacar: estado, verFicha: esEmpleo ? () => abrirFicha(x) : undefined }) }
  const nuevo = () => { ctx.setDraft(esEmpleo ? 'Aplicar a ' : b.id === 'proyectos' ? 'Proyecto: ' : 'Idea: '); requestAnimationFrame(() => { const e = document.getElementById('pz-orden') as HTMLInputElement | null; e?.focus(); e?.setSelectionRange(e.value.length, e.value.length) }) }
  const verColumnas = () => irA({ ...base, vista: columnas ? undefined : 'columnas' }, true)

  const fila = (x: Tarjeta) => {
    const a = accionesDe(x, b.id, ctx)
    const p = esEmpleo ? plazoFrase(x) : x.plazo && !TERMINALES.includes(x.estado) ? { t: x.vencido ? `Se pasó el plazo (${dia(x.plazo)})` : `Plazo: ${diaCorto(x.plazo)} · ${enDias(x.dias)}`, mal: x.vencido } : null
    const nombre = esEmpleo && x.puesto && x.puesto !== x.titulo ? x.puesto : x.titulo
    const sub = esEmpleo ? fraseCand(x) : fraseProy(x)
    const logo = inicial(esEmpleo ? x.empresa || x.titulo : x.titulo)
    const contenido = <>
      <span className={`pz-logo ${p?.mal ? 'mal' : ''}`} aria-hidden="true">{logo}</span>
      <span className="pz-lf-txt"><strong>{nombre}</strong><span>{sub}</span>{x.aviso && <span className="pz-mal">⚠ {x.aviso}</span>}{p && <span className={p.mal ? 'pz-mal pz-lf-plazo' : 'pz-lf-plazo'}>{p.t}</span>}</span>
    </>
    return <li key={x.ruta} className="pz-lf">
      {movil
        ? <button type="button" className="pz-lf-main" onClick={() => abrir(x)} aria-label={`${nombre}. Toca para ver qué puedes hacer`}>{contenido}<Icono n="chevron" size={18} /></button>
        : <>
          {esEmpleo ? <button type="button" className="pz-lf-main" onClick={() => abrirFicha(x)} aria-label={`Abrir la ficha de ${nombre}`}>{contenido}</button> : <div className="pz-lf-main">{contenido}</div>}
          <div className="pz-lf-acc">
            {a.principal && <button type="button" className={`pz-btn pz-btn-fila ${a.principal.primaria ? 'urgente' : ''}`} onClick={a.principal.run}>{a.principal.texto}</button>}
            <button type="button" className="pz-btn pz-btn-fila" onClick={() => abrir(x, a.estado.destacar)}>{a.estado.texto}</button>
          </div>
        </>}
    </li>
  }

  return <div className="pz-page pz-listas">
    <header className="pz-cab-lista">
      <div><h1>{titulo}</h1><p className="pz-resumen">{resumenLista(b)}</p></div>
      <div className="pz-cab-acc">
        <button type="button" className="pz-enlace" onClick={verColumnas}>{columnas ? 'Ver como lista' : 'Ver como columnas'}</button>
        {b.id !== 'programacion' && <button type="button" className="pz-btn pz-btn-primario pz-btn-grande" onClick={nuevo}>+ {esEmpleo ? 'Nueva candidatura' : 'Nuevo proyecto'}</button>}
      </div>
    </header>
    {t.error && <Fallo texto={`No pude actualizar: ${t.error}. Lo que ves puede estar desfasado.`} reintentar={() => void t.reload()} />}
    {columnas
      ? <Columnas cols={b.columnas} onMover={x => abrir(x)} />
      : !grupos.length ? <p className="pz-vacio">Todavía no hay nada en este tablero.</p>
        : <>
          {abiertos.length > 1 && <div className="pz-pastillas" role="group" aria-label="Filtrar por estado">
            <button type="button" aria-pressed={!filtro} onClick={() => setFiltro('')}>Todas · {total}</button>
            {abiertos.map(x => <button key={x.g.id} type="button" aria-pressed={filtro === x.g.id} onClick={() => setFiltro(x.g.id)}>{x.g.titulo} · {x.tarjetas.length}</button>)}
          </div>}
          {visibles.map(x => <section key={x.g.id} className="pz-lista-card" aria-labelledby={`pz-g-${x.g.id}`}>
            <div className="pz-lc-cab"><i style={{ background: x.g.color }} aria-hidden="true" /><h2 id={`pz-g-${x.g.id}`}>{x.g.titulo}</h2>
              <span className={`pz-tag ${x.g.id === 'ahora' || x.g.id === 'activos' ? 'pz-tag-vino' : 'pz-tag-gris'}`}>{x.tarjetas.length}</span></div>
            <ul>{x.tarjetas.map(fila)}</ul>
          </section>)}
          {!visibles.length && <p className="pz-vacio">Nada abierto ahora mismo.</p>}
          {cerrados.length > 0 && <details className="pz-cerradas">
            <summary>Cerradas: {cerrados.flatMap(x => x.tarjetas).length === 0 ? 'ninguna' : cuentaCerradas(cerrados)} · <span className="pz-enlace-txt">verlas</span></summary>
            <section className="pz-lista-card"><ul>{cerrados.flatMap(x => x.tarjetas).map(fila)}</ul></section>
          </details>}
        </>}
    {mover.hoja}
  </div>
}

/** «1 rechazada · 2 descartadas». */
function cuentaCerradas(cs: Cargado[]) {
  const por: Record<string, number> = {}
  for (const x of cs) for (const k of x.tarjetas) por[k.estado] = (por[k.estado] || 0) + 1
  return Object.entries(por).map(([e, n]) => { const [uno, otros] = CERRADA_TXT[e] || [e, e]; return `${n} ${n === 1 ? uno : otros}` }).join(' · ')
}

/* ---------- columnas (el tablero de siempre) ---------- */
function plazoChip(x: Tarjeta) {
  if (!x.plazo) return null
  const cls = x.vencido ? 'mal' : x.dias !== null && x.dias <= 3 ? 'pronto' : ''
  return <span className={`pz-plazo ${cls}`}>{x.vencido ? 'Vencido' : 'Plazo'} {diaCorto(x.plazo)} · {enDias(x.dias)}</span>
}
export function Columnas({ cols, onMover }: { cols: Columna[]; onMover: (x: Tarjeta) => void }) {
  return <div className="pz-columnas" tabIndex={0} role="group" aria-label="Columnas del tablero (desplázate hacia los lados)">
    {cols.map(c => <section key={c.id} className={`pz-columna ${TERMINALES.includes(c.id) ? 'fin' : ''}`} aria-label={`${c.titulo}: ${plural(c.tarjetas.length, 'tarjeta', 'tarjetas')}`}>
      <div className="pz-columna-cab"><span>{(DONDE[c.id] ?? c.titulo).toUpperCase()}</span><b>{c.tarjetas.length}</b></div>
      {c.tarjetas.map(x => <article key={x.ruta} className="pz-tarjeta">
        <strong>{x.titulo}</strong>
        {(x.puesto || x.empresa || x.ciudad) && <p>{[x.puesto, x.empresa, x.ciudad].filter(Boolean).join(' · ')}</p>}
        {x.siguiente && <p>{x.siguiente}</p>}
        {x.aviso && <p className="pz-mal" role="note">⚠ {x.aviso}</p>}
        <div className="pz-tarjeta-pie">
          <span className="pz-tarjeta-meta">{plazoChip(x)}{x.pasos.total > 0 && <span>{x.pasos.hechos}/{x.pasos.total} pasos</span>}</span>
          <button type="button" className="pz-btn pz-btn-suave" onClick={() => onMover(x)} aria-label={`Mover «${x.titulo}» a otra columna`}>Mover</button>
        </div>
      </article>)}
      {!c.tarjetas.length && <p className="pz-vacio pz-vacio-col">Vacía</p>}
    </section>)}
  </div>
}

/* ---------- ficha de una candidatura ---------- */
const ETAPAS: [string, string][] = [['por enviar', 'Por enviar'], ['enviada', 'Enviada'], ['prueba', 'Prueba técnica'], ['entrevista', 'Entrevista'], ['oferta', 'Oferta']]

const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '')

export function Ficha({ b, t, ctx, ruta }: { b: TableroKanban; t: DatosTableros; ctx: Ctx; ruta: string }) {
  const x = tarjetaDe(b, ruta)
  const mover = useMover(t.data || [], t, ctx)
  const { data: panel } = useDatosPanel()
  const volver = () => irA({ tab: 'empleo', tablero: 'candidaturas' })
  if (!x) return <div className="pz-page"><nav className="pz-migas"><button type="button" className="pz-enlace" onClick={volver}><Icono n="back" size={16} /> Candidaturas</button></nav>
    <Fallo texto="Esa candidatura ya no está en la lista (puede que se haya movido o borrado en Obsidian)." reintentar={volver} /></div>
  const a = accionesDe(x, 'candidaturas', ctx)
  const nombre = x.puesto && x.puesto !== x.titulo ? x.puesto : x.titulo
  const p = plazoFrase(x)
  const i = ETAPAS.findIndex(([e]) => e === x.estado)
  const cerrada = x.estado === 'rechazada' || x.estado === 'descartada'
  const abrir = (estado?: string) => mover.abrir({ tablero: 'candidaturas', t: x, destacar: estado })
  // lo de hoy y mañana que habla de esta empresa (tareas y citas ya leídas: nada inventado)
  const clave = x.empresa && norm(x.empresa).length >= 3 ? norm(x.empresa) : ''
  const rel = !clave || !panel ? [] : [
    ...(panel.tareas.ok ? panel.tareas.items.filter(k => norm(k.titulo).includes(clave)).map(k => ({ id: 't' + k.id, tipo: 'Tarea', titulo: k.titulo, cuando: k.vencida ? 'Vencida' : 'Para hoy', mal: k.vencida, ir: () => ctx.go('tareas') })) : []),
    ...(panel.eventos.ok ? panel.eventos.items.filter(k => norm(k.titulo).includes(clave)).map(k => ({ id: 'e' + k.id, tipo: 'Cita', titulo: k.titulo, cuando: `${k.dia === 'hoy' ? 'Hoy' : 'Mañana'}${k.todoDia ? '' : ` · ${horaDe(k.inicio)}`}`, mal: false, ir: () => ctx.go('calendario') })) : [])]
  const filas: [string, ReactNode][] = [
    ['Puesto', nombre], ['Empresa', x.empresa], ['Ciudad', x.ciudad], ['Estado', DONDE[x.estado] ? cap(x.estado) : x.estado || 'Sin estado'],
    ['Plazo', x.plazo ? <span className={x.vencido ? 'pz-mal' : ''}>{diaCorto(x.plazo)} · {enDias(x.dias)}</span> : null],
    ['Enlace de la oferta', x.enlace ? <a href={x.enlace} target="_blank" rel="noopener noreferrer">{x.enlace.replace(/^https?:\/\//, '').slice(0, 40)}… <Icono n="link" size={14} /></a> : null],
    ['Etiquetas', x.tags.length ? <span className="pz-etqs">{x.tags.map(e => <span key={e} className="pz-tag pz-tag-gris">{e}</span>)}</span> : null],
    ['Siguiente paso', x.siguiente], ['Pasos de la nota', x.pasos.total ? `${x.pasos.hechos} de ${x.pasos.total}` : null],
    ['Nota de Obsidian', x.obsidian ? <a href={x.obsidian}>Abrir en el Cerebro</a> : null],
  ]
  return <div className="pz-page pz-ficha">
    <nav className="pz-migas"><button type="button" className="pz-enlace" onClick={volver}><Icono n="back" size={16} /> Candidaturas</button></nav>
    <section className="pz-ficha-cab">
      <div className="pz-ficha-tit"><span className="pz-logo grande" aria-hidden="true">{inicial(x.empresa || x.titulo)}</span>
        <div><h1>{nombre}</h1><p>{[x.empresa, x.ciudad].filter(Boolean).join(' · ') || 'Candidatura'}</p></div></div>
      <ol className="pz-etapas" aria-label="Etapas de la candidatura">
        {ETAPAS.map(([e, tt], k) => <li key={e} className={k === i ? 'on' : k < i ? 'pasada' : ''} aria-current={k === i ? 'step' : undefined}>{tt}</li>)}
      </ol>
      {cerrada && <p className="pz-etapa-cerrada" role="status">{x.estado === 'rechazada' ? 'Te dijeron que no.' : 'La descartaste.'} Si cambia algo, pulsa «Reabrir».</p>}
    </section>
    <div className="pz-ficha-grid">
      <div className="pz-ficha-izq">
      <section className="pz-tarjeta-g" aria-labelledby="pz-f-toca">
        <div className="pz-tarjeta-cab"><h2 id="pz-f-toca">Qué toca ahora</h2></div>
        <div className="pz-ficha-toca">
          <p className="pz-ficha-sig">{x.siguiente || (cerrada ? 'Nada pendiente.' : 'Todavía no hay un siguiente paso apuntado en la nota.')}</p>
          {p && <p className={p.mal ? 'pz-mal pz-lf-plazo' : 'pz-lf-plazo'}>{p.t}</p>}
          {x.aviso && <p className="pz-mal">⚠ {x.aviso}</p>}
          <p className="pz-ficha-nota">{fraseCand(x)}</p>
          <div className="pz-hoja-acc">
            {a.principal && <button type="button" className={`pz-btn ${a.principal.primaria ? 'pz-btn-primario' : 'pz-btn-suave'} pz-btn-grande`} onClick={a.principal.run}>{a.principal.texto}</button>}
            <button type="button" className="pz-btn pz-btn-suave pz-btn-grande" onClick={() => abrir(a.estado.destacar)}>{a.estado.texto}</button>
            {x.enlace && <a className="pz-btn pz-btn-suave pz-btn-grande" href={x.enlace} target="_blank" rel="noopener noreferrer">Abrir la oferta <Icono n="link" size={15} /></a>}
          </div>
        </div>
      </section>
      {x.empresa && <section className="pz-tarjeta-g pz-ficha-rel" aria-labelledby="pz-f-rel">
        <div className="pz-tarjeta-cab"><h2 id="pz-f-rel">Tareas y citas de {x.empresa}</h2></div>
        {rel.length ? <ul className="pz-imp">{rel.map(r => <li key={r.id} className="pz-imp-fila"><span className="pz-imp-ico" aria-hidden="true"><Icono n={r.tipo === 'Cita' ? 'calendar' : 'check'} size={18} /></span>
          <div className="pz-imp-txt"><strong>{r.titulo}</strong><span className={r.mal ? 'pz-mal' : ''}>{r.tipo} · {r.cuando}</span></div>
          <button type="button" className="pz-btn pz-btn-fila" onClick={r.ir}>{r.tipo === 'Cita' ? 'Ver agenda' : 'Ver tareas'}</button></li>)}</ul>
          : <p className="pz-vacio pz-vacio-pad">{panel ? `Hoy y mañana no hay ninguna tarea ni cita que nombre a ${x.empresa}.` : 'Mirando tu día…'}</p>}
      </section>}
      </div>
      <aside className="pz-tarjeta-g pz-ficha-sobre" aria-labelledby="pz-f-sobre">
        <div className="pz-tarjeta-cab"><h2 id="pz-f-sobre">Sobre esta candidatura</h2></div>
        <dl className="pz-sg">{filas.filter(([, v]) => v).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      </aside>
    </div>
    {mover.hoja}
  </div>
}
