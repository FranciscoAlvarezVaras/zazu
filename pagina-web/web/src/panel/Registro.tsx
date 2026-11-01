/* «Qué ha hecho Zazu»: lo que el vigía ha leído, propuesto o escrito (línea de tiempo por días) y los flujos con su interruptor de tres estados.
   Contrato: docs/contrato-registro.md. Todo texto del vigía se pinta como TEXTO (nada de HTML); solo un enlace http(s) validado llega a un href.
   Un fallo de lectura se dice con su Reintentar: nunca se pinta como «0 cosas» ni «0 flujos», y no se inventa ningún número. */
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { irA, useParams } from '../lib'
import { useEscritorio } from '../tema'
import type { Ctx } from '../ctx'
import { cambiarFlujo, cargarFlujos, cargarRegistro, claveReg, FUENTES_REG, TIPOS_REG, useCarga } from './api'
import type { Entrada, Flujo, Flujos, FuenteReg, General, Registro as Reg, ResumenDia, TipoReg } from './api'
import { cuandoCorto, diaCorto, Esqueleto, Fallo, Hoja, Icono, plural } from './ui'
import type { Ico } from './ui'

/* ---------- fechas (el vigía y el Hub trabajan en hora de Madrid, vaya donde vaya el móvil) ---------- */
const TZ = 'Europe/Madrid'
const FMT_DIA = new Intl.DateTimeFormat('sv-SE', { timeZone: TZ })
const FMT_HORA = new Intl.DateTimeFormat('es', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false })
const hoyMadrid = () => FMT_DIA.format(new Date())
const sumaDias = (dia: string, n: number) => { const d = new Date(dia + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10) }
const horaMadrid = (iso: string) => { const d = new Date(iso); return isNaN(d.getTime()) ? '' : FMT_HORA.format(d) }
const RETENCION = 30   // días que guarda el vigía
const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s
function etiquetaDia(dia: string, hoy: string): string {
  const largo = cap(new Date(dia + 'T12:00:00').toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' }))
  return dia === hoy ? `Hoy · ${largo}` : dia === sumaDias(hoy, -1) ? `Ayer · ${largo}` : largo
}

/* ---------- etiquetas en español ---------- */
const TIPO: Record<TipoReg, { label: string; ico: Ico }> = {
  leyo: { label: 'Leyó', ico: 'eye' }, propuso: { label: 'Propuso', ico: 'spark' }, escribio: { label: 'Escribió', ico: 'check' },
  descarto: { label: 'Descartó', ico: 'close' }, fallo: { label: 'Falló', ico: 'alert' }, aviso: { label: 'Avisó', ico: 'bell' },
}
const FUENTE: Record<FuenteReg, string> = { wa: 'WhatsApp', correo: 'Correo', agenda: 'Agenda', tareas: 'Tareas', sistema: 'Sistema' }
const ACCION: Record<string, string> = { tarea: 'Crea tareas', evento: 'Crea eventos', aviso: 'Te avisa' }
const nombreSeguro = (f: string | null, nombres: Record<string, string>) => f ? nombres[f] || f.replace(/-/g, ' ') : ''

/* ---------- el resumen del día en una frase ---------- */
function unir(p: string[]) { return p.length < 2 ? p.join('') : `${p.slice(0, -1).join(', ')} y ${p[p.length - 1]}` }
export function fraseDelDia(r: ResumenDia, dia: string, hoy: string): { frase: string; cifras: string[]; fuentesConFallo: FuenteReg[] } {
  const c = r.cuenta
  const cuando = dia === hoy ? 'Hoy' : dia === sumaDias(hoy, -1) ? 'Ayer' : `El ${diaCorto(dia)}`
  const vacio = TIPOS_REG.every(t => c[t] === 0)
  const leidas = FUENTES_REG.filter(f => (r.porFuente[f]?.leyo ?? 0) > 0).length
  const partes: string[] = []
  if (c.leyo > 0) partes.push(leidas ? `leí ${plural(leidas, 'fuente', 'fuentes')}` : 'leí tus fuentes')
  partes.push(c.propuso > 0 ? `propuse ${plural(c.propuso, 'cosa', 'cosas')}` : 'no propuse nada')
  partes.push(c.escribio > 0 ? `escribí ${plural(c.escribio, 'cosa', 'cosas')} en tu Google` : 'no escribí nada en tu Google')
  const cifras = [c.aviso > 0 && plural(c.aviso, 'aviso', 'avisos'), c.descarto > 0 && plural(c.descarto, 'descarte', 'descartes'), c.fallo > 0 && plural(c.fallo, 'fallo', 'fallos')].filter((x): x is string => !!x)
  return {
    frase: vacio ? (dia === hoy ? 'Hoy todavía no he hecho nada.' : `${cuando === 'Ayer' ? 'Ayer' : 'Ese día'} no hice nada.`) : `${cuando} ${unir(partes)}.`,
    cifras, fuentesConFallo: FUENTES_REG.filter(f => (r.porFuente[f]?.fallo ?? 0) > 0),
  }
}

/* ---------- la página ---------- */
type Seccion = 'actividad' | 'flujos'

export default function Registro({ toast }: Ctx) {
  const params = useParams()
  const hoy = hoyMadrid(), ayer = sumaDias(hoy, -1), minimo = sumaDias(hoy, -RETENCION)
  const [dia, setDia] = useState(hoy)
  const [otroAbierto, setOtroAbierto] = useState(false)
  const [fuente, setFuente] = useState<FuenteReg | ''>('')
  const [tipo, setTipo] = useState<TipoReg | ''>('')
  const [n, setN] = useState(100)
  const escritorio = useEscritorio()
  const [filtrosAbiertos, setFiltrosAbiertos] = useState(false)
  const [extra, setExtra] = useState(0)   // días anteriores que se han ido añadiendo debajo
  const [seccion, setSeccion] = useState<Seccion>(params.vista === 'flujos' ? 'flujos' : 'actividad')
  const titulo = useRef<HTMLHeadingElement>(null)
  useEffect(() => { document.getElementById('pz-main')?.scrollTo(0, 0); titulo.current?.focus({ preventScroll: true }) }, [])

  const filtro = { fuente, tipo, n }
  const clave = claveReg(dia, filtro)
  const carga = useCarga<Reg>(() => cargarRegistro(dia, filtro), `reg-${clave}`, dia === hoy ? 60000 : 0)
  const base = { ...carga, data: carga.data?.clave === clave ? carga.data : null }   // lo del día o filtro anterior no se enseña mientras llega lo nuevo
  const fl = useCarga<Flujos>(cargarFlujos, 'flujos', 60000)
  const [leido, setLeido] = useState<Date | null>(null)
  useEffect(() => { if (base.data?.ok) setLeido(new Date()) }, [base.data])
  const nombres: Record<string, string> = {}
  if (fl.data?.ok) for (const f of fl.data.flujos) nombres[f.id] = f.nombre

  const sel = dia === hoy ? 'hoy' : dia === ayer ? 'ayer' : 'otro'
  const elegirDia = (d: string) => { setDia(d); setExtra(0); setN(100) }
  const hayFiltro = !!(fuente || tipo)
  const resumen = base.data?.ok ? base.data.resumen : null
  const cuenta = (t: TipoReg) => resumen ? resumen.cuenta[t] : null
  const cuentaFuente = (f: FuenteReg) => resumen?.porFuente[f] ? TIPOS_REG.reduce((a, t) => a + (resumen.porFuente[f]?.[t] ?? 0), 0) : resumen ? 0 : null
  const siguiente = sumaDias(dia, -(extra + 1))
  const puedeAnterior = siguiente >= minimo

  return <div className="pz-page pz-reg" data-seccion={seccion}>
    <header className="pz-cab-pag">
      <div>
        <button type="button" className="pz-enlace pz-atras" onClick={() => irA({ tab: 'zazu' })}><Icono n="back" size={16} /> Zazu</button>
        <h1 ref={titulo} tabIndex={-1}>Qué ha hecho Zazu</h1>
      </div>
    </header>

    <div className="pz-chips pz-reg-tabs" role="group" aria-label="Qué quieres ver">
      <button type="button" aria-pressed={seccion === 'actividad'} onClick={() => setSeccion('actividad')}>Actividad</button>
      <button type="button" aria-pressed={seccion === 'flujos'} onClick={() => setSeccion('flujos')}>Flujos{fl.data?.ok && fl.data.flujos.length > 0 ? <span className="pz-reg-n">{fl.data.flujos.length}</span> : null}</button>
    </div>

    <div className="pz-grid pz-reg-grid">
      <div className="pz-col-dia pz-reg-act">
        <section className="pz-reg-resumen" aria-labelledby="pz-reg-res-t">
          <h2 id="pz-reg-res-t" className="pz-eyebrow">RESUMEN</h2>
          <ResumenDelDia base={base.data} cargando={!base.data && base.loading} dia={dia} hoy={hoy} leido={leido} actualizar={() => void base.reload()} />
        </section>

        <section aria-label="Elegir día y filtros" className="pz-reg-ctrl">
          <div className="pz-reg-grupo">
            <span className="pz-reg-grupo-t" id="pz-reg-g-dia">Día</span>
            <div className="pz-chips" role="group" aria-labelledby="pz-reg-g-dia">
              <button type="button" aria-pressed={sel === 'hoy' && !otroAbierto} onClick={() => { setOtroAbierto(false); elegirDia(hoy) }}>Hoy</button>
              <button type="button" aria-pressed={sel === 'ayer' && !otroAbierto} onClick={() => { setOtroAbierto(false); elegirDia(ayer) }}>Ayer</button>
              <button type="button" aria-pressed={sel === 'otro' || otroAbierto} onClick={() => setOtroAbierto(true)}>Otro día</button>
            </div>
            {(otroAbierto || sel === 'otro') && <label className="pz-reg-fecha"><span>Elige un día (guardo los últimos {RETENCION})</span>
              <input type="date" value={dia} min={minimo} max={hoy} onChange={e => { const v = e.target.value; if (/^\d{4}-\d{2}-\d{2}$/.test(v) && v >= minimo && v <= hoy) elegirDia(v) }} /></label>}
          </div>
          {!escritorio && <div className="pz-reg-filtrar">
            <button type="button" className="pz-btn pz-btn-suave" aria-expanded={filtrosAbiertos} aria-controls="pz-reg-filtros" onClick={() => setFiltrosAbiertos(!filtrosAbiertos)}>
              Filtrar{hayFiltro ? ` (${(fuente ? 1 : 0) + (tipo ? 1 : 0)})` : ''} <Icono n="down" size={16} /></button>
            {hayFiltro && <span className="pz-meta">{[fuente && FUENTE[fuente], tipo && TIPO[tipo].label].filter(Boolean).join(' · ')}</span>}
            {hayFiltro && <button type="button" className="pz-btn pz-btn-texto" onClick={() => { setFuente(''); setTipo(''); setExtra(0); setN(100) }}>Quitar</button>}
          </div>}
          {(escritorio || filtrosAbiertos) && <div id="pz-reg-filtros" className="pz-reg-filtros">
            <div className="pz-reg-grupo">
              <span className="pz-reg-grupo-t" id="pz-reg-g-fuente">De dónde</span>
              <div className="pz-chips" role="group" aria-labelledby="pz-reg-g-fuente">
                <button type="button" aria-pressed={!fuente} onClick={() => { setFuente(''); setExtra(0); setN(100) }}>Todas</button>
                {FUENTES_REG.map(f => <button key={f} type="button" aria-pressed={fuente === f} onClick={() => { setFuente(f); setExtra(0); setN(100) }}>{FUENTE[f]}{cuentaFuente(f) !== null && <span className="pz-reg-n">{cuentaFuente(f)}</span>}</button>)}
              </div>
            </div>
            <div className="pz-reg-grupo">
              <span className="pz-reg-grupo-t" id="pz-reg-g-tipo">Qué hice</span>
              <div className="pz-chips" role="group" aria-labelledby="pz-reg-g-tipo">
                <button type="button" aria-pressed={!tipo} onClick={() => { setTipo(''); setExtra(0); setN(100) }}>Todo</button>
                {TIPOS_REG.map(t => <button key={t} type="button" aria-pressed={tipo === t} onClick={() => { setTipo(t); setExtra(0); setN(100) }}>{TIPO[t].label}{cuenta(t) !== null && <span className="pz-reg-n">{cuenta(t)}</span>}</button>)}
              </div>
            </div>
          </div>}
          <p className="pz-nota pz-reg-leyenda"><b>Prueba</b>: lo apunto, pero no hago nada de verdad. <b>Hecho</b>: lo hice de verdad.</p>
        </section>

        <Grupo dia={dia} hoy={hoy} estado={base} nombres={nombres} hayFiltro={hayFiltro} quitarFiltros={() => { setFuente(''); setTipo('') }}
          masFilas={base.data?.ok && base.data.hayMas && n < 200 ? () => setN(200) : undefined} />
        {Array.from({ length: extra }, (_, i) => <Extra key={`${dia}${fuente}${tipo}${i}`} dia={sumaDias(dia, -(i + 1))} hoy={hoy} filtro={{ fuente, tipo }} nombres={nombres} hayFiltro={hayFiltro} quitarFiltros={() => { setFuente(''); setTipo('') }} />)}
        {puedeAnterior
          ? <button type="button" className="pz-btn pz-btn-suave pz-reg-anterior" onClick={() => setExtra(extra + 1)}>Ver el día anterior · {diaCorto(siguiente)}</button>
          : <p className="pz-nota">Solo guardo los últimos {RETENCION} días.</p>}
      </div>

      <aside className="pz-col-lado pz-reg-flujos" aria-labelledby="pz-reg-fl-t">
        <SeccionFlujos fl={fl} toast={toast} />
      </aside>
    </div>
  </div>
}

/* ---------- resumen ---------- */
function ResumenDelDia({ base, cargando, dia, hoy, leido, actualizar }: { base: Reg | null; cargando: boolean; dia: string; hoy: string; leido: Date | null; actualizar: () => void }) {
  if (cargando) return <Esqueleto filas={2} alto={34} />
  if (!base || !base.ok) return <p className="pz-reg-frase pz-reg-frase-duda">No he podido leer el registro, así que ahora mismo no sé qué ha pasado {dia === hoy ? 'hoy' : 'ese día'}.</p>
  if (!base.resumen) return <p className="pz-reg-frase pz-reg-frase-duda">No puedo resumir el día: el vigía no me ha dado las cuentas completas. Debajo tienes lo que sí he leído.</p>
  const { frase, cifras, fuentesConFallo } = fraseDelDia(base.resumen, dia, hoy)
  return <>
    <p className="pz-reg-frase">{frase}</p>
    {cifras.length > 0 && <ul className="pz-reg-cifras" aria-label="Además">{cifras.map(c => <li key={c}>{c}</li>)}</ul>}
    {base.resumen.cuenta.fallo > 0 && <p className="pz-propuesta-aviso mal" role="status">{fuentesConFallo.length
      ? `No pude leer bien: ${unir(fuentesConFallo.map(f => FUENTE[f]))}. Mira las filas marcadas «Falló».`
      : 'Hubo algún fallo. Mira las filas marcadas «Falló».'}</p>}
    <p className="pz-meta pz-reg-leido">{leido ? `Leído a las ${horaMadrid(leido.toISOString())}` : ''}<button type="button" className="pz-btn pz-btn-texto" onClick={actualizar}>Actualizar</button></p>
  </>
}

/* ---------- línea de tiempo ---------- */
type Estado = { data: Reg | null; error: string; loading: boolean; reload: () => Promise<void> }
function Extra({ dia, hoy, filtro, nombres, hayFiltro, quitarFiltros }: { dia: string; hoy: string; filtro: { fuente: FuenteReg | ''; tipo: TipoReg | '' }; nombres: Record<string, string>; hayFiltro: boolean; quitarFiltros: () => void }) {
  const c = useCarga<Reg>(() => cargarRegistro(dia, filtro), `reg-x-${dia}-${filtro.fuente}-${filtro.tipo}`)
  return <Grupo dia={dia} hoy={hoy} estado={c} nombres={nombres} hayFiltro={hayFiltro} quitarFiltros={quitarFiltros} />
}

function Grupo({ dia, hoy, estado, nombres, hayFiltro, quitarFiltros, masFilas }: { dia: string; hoy: string; estado: Estado; nombres: Record<string, string>; hayFiltro: boolean; quitarFiltros: () => void; masFilas?: () => void }) {
  const { data, error, loading, reload } = estado
  const id = `pz-reg-d-${dia}`
  let cuerpo: ReactNode
  if (!data) cuerpo = loading ? <Esqueleto filas={4} alto={64} /> : <Fallo texto={`No pude leer lo que hizo el vigía: ${error || 'sin respuesta'}.`} reintentar={() => void reload()} />
  else if (!data.ok) cuerpo = <Fallo texto={`No pude leer lo que hizo el vigía: ${data.error}.`} reintentar={() => void reload()} />
  else if (!data.items.length) {
    cuerpo = hayFiltro
      ? <div className="pz-vacio"><p>Con esos filtros no hay nada ese día.</p><button type="button" className="pz-btn pz-btn-suave" onClick={quitarFiltros}>Quitar filtros</button></div>
      : <p className="pz-vacio">{dia === hoy ? 'Hoy todavía no ha pasado nada. En cuanto el vigía haga algo, lo verás aquí.' : 'Ese día no hay nada apuntado.'}</p>
  } else cuerpo = <>
    <ol className="pz-reg-lista">{data.items.map(e => <Fila key={e.id} e={e} nombres={nombres} />)}</ol>
    {data.omitidos > 0 && <p className="pz-nota" role="status">{plural(data.omitidos, 'apunte no se ha podido mostrar', 'apuntes no se han podido mostrar')} (el vigía los mandó en un formato que no entiendo).</p>}
    {data.hayMas && (masFilas
      ? <button type="button" className="pz-btn pz-btn-suave" onClick={masFilas}>Puede haber más: ver hasta 200</button>
      : <p className="pz-nota">Se enseñan los {data.items.length} más recientes; puede haber más.</p>)}
  </>
  return <section className="pz-reg-dia" aria-labelledby={id}>
    <div className="pz-sec-cab"><h3 id={id}>{etiquetaDia(dia, hoy)}</h3>{data?.ok && data.items.length > 0 && <span>{plural(data.items.length, 'cosa', 'cosas')}</span>}</div>
    {cuerpo}
  </section>
}

function Fila({ e, nombres }: { e: Entrada; nombres: Record<string, string> }) {
  const T = TIPO[e.tipo]
  const flujo = nombreSeguro(e.flujo, nombres)
  const sello = e.modo === 'sombra' ? 'Prueba' : e.tipo === 'fallo' ? 'En real' : 'Hecho'
  return <li className={`pz-reg-fila t-${e.tipo}`}>
    <span className="pz-reg-ico" aria-hidden="true"><Icono n={T.ico} size={18} /></span>
    <div className="pz-reg-cuerpo">
      <p className="pz-reg-linea"><time dateTime={e.ts}>{horaMadrid(e.ts)}</time><span className={`pz-reg-sello ${e.modo}`}>{sello}</span></p>
      <p className="pz-reg-titulo"><span className="pz-oculto">{T.label}: </span><strong>{e.titulo}</strong></p>
      {e.detalle && <p className="pz-reg-detalle">{e.detalle}</p>}
      <p className="pz-meta pz-reg-pie">{FUENTE[e.fuente]} · {T.label}{flujo ? ` · Flujo «${flujo}»` : ''}{e.ref && !e.enlace ? <span className="pz-reg-ref"> · Ref. {e.ref}</span> : null}</p>
      {e.enlace && <a className="pz-enlace" href={e.enlace} target="_blank" rel="noopener noreferrer">Abrir enlace <Icono n="link" size={15} /></a>}
    </div>
  </li>
}

/* ---------- flujos ---------- */
type Destino = 'prueba' | 'activo' | 'pausado'
const estadoDe = (f: Flujo): Destino => f.pausado ? 'pausado' : f.modo === 'sombra' ? 'prueba' : 'activo'
const OPCIONES: { v: Destino; t: string; ico: Ico }[] = [{ v: 'prueba', t: 'En prueba', ico: 'eye' }, { v: 'activo', t: 'Activo', ico: 'check' }, { v: 'pausado', t: 'Pausado', ico: 'pause' }]
const FRASE_ESTADO: Record<Destino, string> = { prueba: 'En prueba', activo: 'Activo', pausado: 'Pausado' }

function estadoGeneral(g: General | null, f: Flujo): { texto: string; escribiria: boolean } {
  if (!g) return { texto: 'No he podido comprobar cómo está ahora mismo.', escribiria: false }
  if (g.pausa) return { texto: 'Ahora mismo el vigía entero está en pausa, así que no escribiría nada.', escribiria: false }
  if (!g.entregaReal) return { texto: 'Ahora mismo está apagado, así que aunque lo actives seguirá solo apuntando lo que haría.', escribiria: false }
  const m = f.fuente ? g.modo[f.fuente] : undefined
  if (f.fuente && m !== 'activo') return { texto: `Ahora mismo está encendido, pero ${m ? `la fuente «${FUENTE[f.fuente]}» sigue en prueba` : `no sé si la fuente «${FUENTE[f.fuente]}» está activa`}, así que de momento seguiría solo apuntando.`, escribiria: false }
  return { texto: 'Ahora mismo está encendido: este flujo empezaría a escribir de verdad.', escribiria: true }
}
const queEscribiria = (f: Flujo) => {
  const l = f.acciones.map(a => a === 'tarea' ? 'crear tareas en tu Google Tareas' : a === 'evento' ? 'crear eventos en tu Google Calendar' : a === 'aviso' ? 'mandarte avisos' : '').filter(Boolean)
  return l.length ? l : ['escribir en tu Google']
}

function SeccionFlujos({ fl, toast }: { fl: { data: Flujos | null; error: string; loading: boolean; reload: () => Promise<void>; setData: (d: Flujos | null) => void }; toast: (m: string) => void }) {
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [confirmar, setConfirmar] = useState<Flujo | null>(null)
  const { data } = fl

  const poner = (f: Flujo, g: General | null) => {
    const d = fl.data
    if (d?.ok) fl.setData({ ...d, flujos: d.flujos.map(x => x.id === f.id ? f : x), general: g ?? d.general })
  }
  const aplicar = async (f: Flujo, destino: Destino) => {
    setOcupado(f.id)
    try {
      let cur = f, gen: General | null = null
      const paso = async (c: Parameters<typeof cambiarFlujo>[1]) => { const r = await cambiarFlujo(f.id, c); cur = r.flujo; gen = r.general }
      if (destino === 'pausado') { if (!cur.pausado) await paso({ accion: 'pausa' }) }
      else {
        if (destino === 'prueba' && cur.modo !== 'sombra') await paso({ accion: 'modo', modo: 'sombra' })
        if (destino === 'activo' && cur.modo !== 'activo') await paso({ accion: 'modo', modo: 'activo', confirmo: true })
        if (cur.pausado) await paso({ accion: 'reanuda' })
      }
      poner(cur, gen)
      toast(destino === 'pausado' ? `«${cur.nombre}» en pausa` : destino === 'prueba' ? `«${cur.nombre}» vuelve a En prueba: solo apunta` : cur.efectivo === 'vivo' ? `«${cur.nombre}» está Activo y escribe de verdad` : `«${cur.nombre}» está Activo, pero de momento solo apunta`)
    } catch (e) {
      toast(`No se pudo cambiar: ${(e as Error).message}`)
      await fl.reload()   // por si un paso sí se hizo: se enseña lo que dice el vigía, no lo que esperábamos
    } finally { setOcupado(null) }
  }
  const elegir = (f: Flujo, v: Destino) => {
    if (estadoDe(f) === v || ocupado) return
    if (v === 'activo') setConfirmar(f)   // escribir de verdad en Google siempre se confirma
    else void aplicar(f, v)
  }

  let cuerpo: ReactNode
  if (!data) cuerpo = fl.loading ? <Esqueleto filas={3} alto={150} /> : <Fallo texto={`No pude leer los flujos: ${fl.error || 'sin respuesta'}.`} reintentar={() => void fl.reload()} />
  else if (!data.ok) cuerpo = <Fallo texto={`No pude leer los flujos: ${data.error}.`} reintentar={() => void fl.reload()} />
  else cuerpo = <>
    <BannerGeneral g={data.general} />
    {data.flujos.length
      ? <ul className="pz-fl-lista">{data.flujos.map(f => <TarjetaFlujo key={f.id} f={f} ocupado={ocupado === f.id} bloqueado={!!ocupado} elegir={v => elegir(f, v)} />)}</ul>
      : <p className="pz-vacio">El vigía no tiene ningún flujo configurado.</p>}
    {fl.error && <Fallo texto={`No pude actualizar: ${fl.error}.`} reintentar={() => void fl.reload()} />}
  </>

  return <>
    <div className="pz-sec-cab"><h2 id="pz-reg-fl-t" className="pz-reg-h2">Flujos</h2>{data?.ok && data.flujos.length > 0 && <span>{plural(data.flujos.length, 'flujo', 'flujos')}</span>}</div>
    <p className="pz-nota">Un flujo es una cosa concreta que el vigía sabe hacer. En prueba solo apunta; en Activo puede escribir en tu Google.</p>
    {cuerpo}
    {confirmar && <HojaActivar f={confirmar} general={data?.ok ? data.general : null} cerrar={() => setConfirmar(null)}
      confirmar={async () => { const f = confirmar; setConfirmar(null); await aplicar(f, 'activo') }} />}
  </>
}

function BannerGeneral({ g }: { g: General | null }) {
  if (!g) return <p className="pz-nota" role="status"><Icono n="shield" size={15} /> No he podido leer el interruptor general del vigía.</p>
  const estado = g.pausa ? 'en pausa' : g.entregaReal ? 'encendido' : 'apagado'
  return <p className={`pz-nota pz-fl-general ${g.pausa || !g.entregaReal ? 'apagado' : 'encendido'}`} role="status"><Icono n="shield" size={15} />
    <span>Interruptor general del vigía: <b>{estado}</b>.{g.pausa || !g.entregaReal ? ' Mientras no esté encendido, ningún flujo escribe en tu Google, aunque esté Activo.' : ''}</span></p>
}

function TarjetaFlujo({ f, ocupado, bloqueado, elegir }: { f: Flujo; ocupado: boolean; bloqueado: boolean; elegir: (v: Destino) => void }) {
  const actual = estadoDe(f)
  const nota = f.pausado ? 'En pausa: no hace nada hasta que lo reanudes.'
    : f.modo === 'sombra' ? 'En prueba: apunta lo que haría, sin tocar nada.'
      : f.efectivo === 'vivo' ? 'Activo: escribe de verdad en tu Google.'
        : f.efectivo === 'prueba' ? `Activo, pero ahora mismo solo apunta${f.motivo ? `: ${f.motivo}` : ''}.`
          : `Activo, pero no puedo saber si escribe de verdad${f.motivo ? `: ${f.motivo}` : ''}.`
  const aviso = !f.pausado && f.modo === 'activo' && f.efectivo !== 'vivo'
  const id = `pz-fl-${f.id}`
  return <li className="pz-fl" aria-busy={ocupado}>
    <h3 id={id}>{f.nombre}</h3>
    {f.descripcion && <p className="pz-fl-desc">{f.descripcion}</p>}
    <div className="pz-fl-chips">
      {f.fuente && <span className="pz-etiqueta">{FUENTE[f.fuente]}</span>}
      {f.acciones.map(a => <span key={a} className="pz-etiqueta pz-etiqueta-sec">{ACCION[a] || a}</span>)}
    </div>
    <p className="pz-meta">{f.ultimo ? `Último disparo: ${cuandoCorto(f.ultimo)}` : 'Todavía no ha disparado'}{f.disparos7d !== null ? ` · ${plural(f.disparos7d, 'disparo', 'disparos')} en 7 días` : ''}</p>
    <div className="pz-tres" role="group" aria-labelledby={id}>
      {OPCIONES.map(o => <button key={o.v} type="button" className={`pz-tres-${o.v}`} aria-pressed={actual === o.v} disabled={bloqueado && actual !== o.v} onClick={() => elegir(o.v)}>
        <Icono n={o.ico} size={18} />{o.t}</button>)}
    </div>
    <p className={`pz-fl-estado${aviso ? ' aviso' : ''}`} role="status">{ocupado ? 'Guardando…' : nota}</p>
  </li>
}

function HojaActivar({ f, general, cerrar, confirmar }: { f: Flujo; general: General | null; cerrar: () => void; confirmar: () => void | Promise<void> }) {
  const eg = estadoGeneral(general, f)
  const yaConfirmado = f.modo === 'activo'   // estaba en pausa con el modo Activo: solo se reanuda
  return <Hoja titulo={`¿Activar «${f.nombre}»?`} id="activar" cerrar={cerrar}>
    <p className="pz-hoja-texto">{yaConfirmado ? 'Lo reanudo y volverá a hacer esto:' : 'Hasta ahora solo apuntaba lo que haría. Si lo activas, podrá escribir de verdad en tu Google:'}</p>
    <ul className="pz-puntos">{queEscribiria(f).map(t => <li key={t}>{cap(t)}</li>)}</ul>
    <p className={`pz-propuesta-aviso${eg.escribiria ? ' mal' : ''}`}><b>Ojo:</b> además de esto, el interruptor general del vigía también tiene que estar encendido para que escriba. {eg.texto} Ese interruptor no se toca desde aquí.</p>
    <p className="pz-hoja-texto">Puedes volver a «{FRASE_ESTADO.prueba}» cuando quieras.</p>
    <div className="pz-hoja-acc">
      <button type="button" className="pz-btn pz-btn-suave" onClick={cerrar} data-foco>Mejor no</button>
      <button type="button" className="pz-btn pz-btn-primario" onClick={() => void confirmar()}>Sí, activar</button>
    </div>
  </Hoja>
}
