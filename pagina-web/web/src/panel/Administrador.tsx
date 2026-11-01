/* Administrador › Registros (solo Fran): el visor de registros de la app, Zazu y los invitados, como el Explorador de registros de Google.
   Filtros arriba, gráfico por tiempo (pulsa una barra para ver ese rato), la lista en vivo (con pausa) o los errores agrupados, y el detalle
   de cada línea con lo que pasó justo antes y después. Los datos los junta visor.py en el servidor (ya tachados); aquí todo se pinta como TEXTO. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactElement } from 'react'
import { api, post } from '../lib'
import { useEscritorio } from '../tema'
import type { Ctx } from '../ctx'
import { Esqueleto, Fallo, Hoja, Icono } from './ui'
import './admin.css'

type Grav = 'info' | 'aviso' | 'error'
type Ent = { t: number; o: string; g: Grav; p: string | null; x: string; d?: string; f: string }
type Grupo = { f: string; n: number; primera: number; ultima: number; o: string; g: Grav; x: string; perfiles: string[] }
type Cubo = { t: number } & Record<Grav, number>
type Vista = { entradas: Ent[]; total: number; histograma: Cubo[]; cubo: number; cuentas: Record<Grav, number>; grupos: Grupo[]
  desde: number; hasta: number; ahora: number; activas: { gravedad: string; texto: string; desde: number }[] }

const RANGOS = [{ s: 3600, t: '1 hora' }, { s: 6 * 3600, t: '6 horas' }, { s: 86400, t: '24 horas' }, { s: 7 * 86400, t: '7 días' }, { s: 30 * 86400, t: '30 días' }]
const GRAVEDADES: { v: '' | Grav; t: string }[] = [{ v: '', t: 'Todo' }, { v: 'aviso', t: 'Avisos y errores' }, { v: 'error', t: 'Solo errores' }]
const ORIGENES: Record<string, string> = { app: 'La app', zazu: 'Zazu', invitados: 'Invitados', vigilante: 'Vigilante' }
const NOMBRE_G: Record<Grav, string> = { info: 'Info', aviso: 'Aviso', error: 'Error' }
type Marcador = { nivel: number; nombre: string; puntos: number; para_subir: number | null; entendidos: number; arreglados: number; gasto_mes: number; tope: number }
type DeFirma = { entendido?: boolean; arreglado?: boolean }
type Respuesta = Marcador & DeFirma & { ok: boolean; texto?: string; guardada?: boolean; coste?: number; motivo?: string }
type Examen = Marcador & DeFirma & { ok: boolean; preguntas?: string[]; motivo?: string }
type Nota = Marcador & DeFirma & { ok: boolean; aprobado?: boolean; notas?: { bien: boolean; comentario: string }[]; frase?: string; motivo?: string }
const MOTIVO: Record<string, string> = {
  tope: 'Este mes ya se gastó el tope de 15 $ en explicaciones. El mes que viene vuelve a funcionar.',
  sin_ia: 'Ahora mismo no hay forma de llamar a Claude desde el servidor.', ocupado: 'Claude está con otra explicación; prueba en unos segundos.',
  fallo: 'Claude no ha contestado (tardó mucho o falló). Prueba otra vez.', vacio: 'Escribe al menos una respuesta.',
  sin_explicacion: 'Primero pide la explicación.', sin_examen: 'Primero pide el examen.' }
const dolares = (n: number) => `${n.toFixed(2).replace('.', ',')} $`
const CADA = 3000   // ms entre vistazos en vivo
const TZ = 'Europe/Madrid'
const F_HORA = new Intl.DateTimeFormat('es', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
const F_CORTA = new Intl.DateTimeFormat('es', { timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
const F_LARGA = new Intl.DateTimeFormat('es', { timeZone: TZ, weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
const hora = (t: number, corto: boolean) => (corto ? F_HORA : F_CORTA).format(new Date(t * 1000))
const clave = (e: Ent) => `${e.t}|${e.f}|${e.p}|${e.x}`
/** Claves únicas para React: dos líneas iguales en el mismo segundo (pasa en Zazu) llevan #2, #3… Con claves repetidas React deja filas viejas. */
const claves = (es: Ent[]) => { const n = new Map<string, number>(); return es.map(e => { const k = clave(e), i = (n.get(k) || 0) + 1; n.set(k, i); return i > 1 ? `${k}#${i}` : k }) }
const F_EJE = new Intl.DateTimeFormat('es', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false })
const eje = (t: number, corto: boolean) => (corto ? F_EJE : F_CORTA).format(new Date(t * 1000))
const origenDe = (o: string, p: string | null) => (ORIGENES[o] || o) + (p && p !== 'zazu' ? ` · ${p}` : '')

export default function Administrador({ toast }: Ctx) {
  const escritorio = useEscritorio()
  const [rango, setRango] = useState(2)
  const [ventana, setVentana] = useState<{ desde: number; hasta: number } | null>(null)   // un rato elegido en el gráfico
  const [grav, setGrav] = useState<'' | Grav>('')
  const [origen, setOrigen] = useState('')
  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [firma, setFirma] = useState('')
  const [vistaLista, setVistaLista] = useState<'lista' | 'grupos'>('lista')
  const [vivo, setVivo] = useState(true)
  const [datos, setDatos] = useState<Vista | null>(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(true)
  const [sel, setSel] = useState<Ent | null>(null)
  const [recien, setRecien] = useState<Set<string>>(new Set())
  const [marcador, setMarcador] = useState<Marcador | null>(null)
  useEffect(() => { api<Marcador>('/api/admin/aprendizaje').then(setMarcador).catch(() => { /* sin marcador no pasa nada */ }) }, [])
  const seq = useRef(0)
  const ref = useRef<Vista | null>(null)
  ref.current = datos
  useEffect(() => { const t = setTimeout(() => setQ(texto.trim()), 400); return () => clearTimeout(t) }, [texto])   // buscar sin pedir a cada letra

  const filtros = useMemo(() => {
    const u = new URLSearchParams()
    const ahora = Date.now() / 1000
    u.set('desde', String(Math.floor(ventana ? ventana.desde : ahora - RANGOS[rango].s)))
    if (ventana) u.set('hasta', String(Math.ceil(ventana.hasta)))
    if (grav) u.set('gravedad', grav)
    if (origen) u.set('origen', origen)
    if (q) u.set('q', q)
    if (firma) u.set('firma', firma)
    return u
  }, [rango, ventana, grav, origen, q, firma])

  const cargar = useCallback(async () => {
    const n = ++seq.current
    try {
      const d = await api<Vista>(`/api/admin/registros?${filtros}`)
      if (n === seq.current) { setDatos(d); setError('') }
    } catch (e) { if (n === seq.current) setError((e as Error).message) }
    finally { if (n === seq.current) setCargando(false) }
  }, [filtros])
  useEffect(() => { setCargando(true); void cargar() }, [cargar])

  // en vivo: cada 3 s lo que llegó después de la última; cada 30 s todo (gráfico y agrupados al día). Con un rato elegido no hay «en vivo».
  useEffect(() => {
    if (!vivo || ventana) return
    let vueltas = 0
    const t = setInterval(async () => {
      const d = ref.current
      if (document.hidden || !d) return
      if (++vueltas % 10 === 0) { void cargar(); return }
      const u = new URLSearchParams(filtros)
      u.set('despues', String(d.entradas[0]?.t ?? d.ahora))
      try {
        const r = await api<{ nuevas: Ent[] }>(`/api/admin/registros?${u}`)
        if (!r.nuevas.length || ref.current !== d) return
        const ya = new Set(d.entradas.map(clave))
        const nuevas = r.nuevas.filter(e => !ya.has(clave(e)))
        if (!nuevas.length) return
        const cuentas = { ...d.cuentas }
        nuevas.forEach(e => { cuentas[e.g]++ })
        setDatos({ ...d, entradas: [...nuevas, ...d.entradas].slice(0, 500), total: d.total + nuevas.length, cuentas })
        setRecien(new Set(nuevas.map(clave)))
      } catch { /* la próxima vuelta lo intenta otra vez */ }
    }, CADA)
    return () => clearInterval(t)
  }, [vivo, ventana, filtros, cargar])

  const quitar = () => { setTexto(''); setQ(''); setFirma(''); setVentana(null) }
  const hayFiltro = !!(q || firma || ventana)
  const corto = (ventana ? ventana.hasta - ventana.desde : RANGOS[rango].s) <= 86400
  const veces = (f: string) => datos?.grupos.find(g => g.f === f)?.n ?? datos?.entradas.filter(e => e.f === f).length ?? 0
  const detalle = sel && <Detalle key={clave(sel)} e={sel} veces={veces(sel.f)} toast={toast} marcador={setMarcador}
    verTodas={() => { setFirma(sel.f); setVistaLista('lista'); setSel(null) }} />

  return <div className="pz-page adm">
    <header className="pz-cab-pag adm-cab">
      <div>
        <p className="pz-eyebrow">ADMINISTRADOR</p>
        <h1>Registros</h1>
      </div>
      <button type="button" className={`pz-btn pz-btn-suave adm-vivo${vivo && !ventana ? ' on' : ''}`} onClick={() => setVivo(!vivo)} disabled={!!ventana}
        aria-pressed={vivo && !ventana} title={ventana ? 'Con un rato elegido en el gráfico no hay «en vivo»' : undefined}>
        {vivo && !ventana ? <><i className="adm-latido" aria-hidden="true" /> En vivo</> : <><Icono n="pause" size={16} /> En pausa</>}
      </button>
    </header>

    {marcador && <p className="adm-marcador" title="Cada error que entiendes suma 1 punto y cada uno que arreglas, 2. Con más nivel, Claude te habla más técnico.">
      <Icono n="spark" size={16} /> <b>Nivel {marcador.nivel} · {marcador.nombre}</b>
      <span>{marcador.puntos} {marcador.puntos === 1 ? 'punto' : 'puntos'}{marcador.para_subir !== null ? ` (te faltan ${marcador.para_subir} para subir)` : ''}</span>
      <span>{marcador.entendidos} entendidos · {marcador.arreglados} arreglados</span>
      <span className="adm-gasto">Explicaciones este mes: {dolares(marcador.gasto_mes)} de {dolares(marcador.tope)}</span>
    </p>}
    {datos && <Estado activas={datos.activas} />}

    <section className="adm-filtros" aria-label="Filtros">
      <div className="pz-chips" role="group" aria-label="Cuánto tiempo">
        {RANGOS.map((r, i) => <button key={r.s} type="button" aria-pressed={!ventana && rango === i} onClick={() => { setVentana(null); setRango(i) }}>{r.t}</button>)}
      </div>
      <div className="pz-chips" role="group" aria-label="Gravedad">
        {GRAVEDADES.map(g => <button key={g.v} type="button" aria-pressed={grav === g.v} onClick={() => setGrav(g.v)}>
          {g.v && <i className={`adm-punto g-${g.v}`} aria-hidden="true" />}{g.t}</button>)}
      </div>
      <div className="adm-fila-filtros">
        <label className="adm-campo"><span>De dónde</span>
          <select value={origen} onChange={e => setOrigen(e.target.value)}>
            <option value="">Todo</option>
            {Object.entries(ORIGENES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label className="adm-campo adm-buscar"><span>Buscar</span>
          <input type="search" value={texto} onChange={e => setTexto(e.target.value)} placeholder="Una palabra del error, una ruta…" enterKeyHint="search" /></label>
      </div>
      {hayFiltro && <div className="adm-activos">
        {ventana && <span className="adm-etq">{hora(ventana.desde, false)} – {hora(ventana.hasta, false)}</span>}
        {firma && <span className="adm-etq">Solo este error</span>}
        {q && <span className="adm-etq">«{q}»</span>}
        <button type="button" className="pz-btn pz-btn-texto" onClick={quitar}><Icono n="close" size={15} /> Quitar</button>
      </div>}
    </section>

    {error && <Fallo texto={`No he podido leer los registros: ${error}`} reintentar={() => void cargar()} ocupado={cargando} />}
    {!datos && !error && <Esqueleto filas={6} alto={40} />}
    {datos && <>
      <Grafico d={datos} corto={corto} elegir={c => { setVentana({ desde: c.t, hasta: c.t + datos.cubo }); setVivo(false) }} />

      <div className="pz-chips adm-pestanas" role="group" aria-label="Qué ver">
        <button type="button" aria-pressed={vistaLista === 'lista'} onClick={() => setVistaLista('lista')}>Registros <span className="adm-n">{datos.total}</span></button>
        <button type="button" aria-pressed={vistaLista === 'grupos'} onClick={() => setVistaLista('grupos')}>Errores agrupados <span className="adm-n">{datos.grupos.length}</span></button>
      </div>

      <div className={`adm-cuerpo${escritorio && sel ? ' con-detalle' : ''}`}>
        <div className="adm-lista-caja" aria-busy={cargando}>
          {vistaLista === 'lista'
            ? <Lista d={datos} corto={corto} sel={sel} recien={recien} elegir={setSel} />
            : <Grupos g={datos.grupos} corto={corto} elegir={g => { setFirma(g.f); setVistaLista('lista') }} />}
        </div>
        {escritorio && detalle && <aside className="adm-detalle" aria-label="Detalle">
          <button type="button" className="pz-btn pz-btn-texto adm-cerrar" onClick={() => setSel(null)} aria-label="Cerrar el detalle"><Icono n="close" size={18} /></button>
          {detalle}
        </aside>}
      </div>
    </>}
    {!escritorio && detalle && <Hoja titulo="Detalle del registro" cerrar={() => setSel(null)} id="adm">{detalle}</Hoja>}
  </div>
}

function Estado({ activas }: { activas: Vista['activas'] }) {
  if (!activas.length) return <p className="adm-estado ok"><Icono n="check" size={18} /> Ahora mismo todo funciona: la web, Zazu, el túnel y los servicios responden.</p>
  return <div className="adm-estado mal" role="status">
    <strong><Icono n="alert" size={18} /> Ahora mismo hay {activas.length === 1 ? 'algo que falla' : `${activas.length} cosas que fallan`}</strong>
    <ul>{activas.map((a, i) => <li key={i} className={`g-${a.gravedad === 'error' ? 'error' : 'aviso'}`}>{a.texto}</li>)}</ul>
  </div>
}

function Grafico({ d, corto, elegir }: { d: Vista; corto: boolean; elegir: (c: Cubo) => void }) {
  const h = d.histograma
  const tope = Math.max(1, ...h.map(c => c.info + c.aviso + c.error))
  const alto = 72, ancho = 10
  const resumen = `${d.total} registros: ${d.cuentas.error} errores, ${d.cuentas.aviso} avisos y ${d.cuentas.info} de información`
  return <section className="adm-grafico" aria-label="Registros por tiempo">
    <div className="adm-cuentas">
      <span><b>{d.total}</b> registros</span>
      <span className="g-aviso"><i className="adm-punto g-aviso" aria-hidden="true" /><b>{d.cuentas.aviso}</b> avisos</span>
      <span className="g-error"><i className="adm-punto g-error" aria-hidden="true" /><b>{d.cuentas.error}</b> errores</span>
    </div>
    <svg viewBox={`0 0 ${h.length * ancho} ${alto}`} preserveAspectRatio="none" role="group" aria-label={resumen}>
      {h.map((c, i) => {
        const total = c.info + c.aviso + c.error
        if (!total) return null
        let y = alto
        const capa = (n: number, g: Grav) => {
          if (!n) return null
          const hh = Math.max(1.5, n / tope * (alto - 4))
          y -= hh
          return <rect key={g} className={`b-${g}`} x={i * ancho + 1} y={y} width={ancho - 2} height={hh} rx="1.5" />
        }
        return <g key={c.t} className="adm-barra" tabIndex={0} role="button" onClick={() => elegir(c)}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); elegir(c) } }}
          aria-label={`${hora(c.t, corto)}: ${c.error} errores, ${c.aviso} avisos, ${c.info} info. Ver este rato`}>
          <title>{`${hora(c.t, corto)} · ${c.error} errores · ${c.aviso} avisos · ${c.info} info`}</title>
          <rect className="adm-barra-hueco" x={i * ancho} y={0} width={ancho} height={alto} />
          {capa(c.error, 'error')}{capa(c.aviso, 'aviso')}{capa(c.info, 'info')}
        </g>
      })}
    </svg>
    <div className="adm-eje"><span>{eje(d.desde, corto)}</span><span className="pz-nota">Pulsa una barra para ver solo ese rato</span><span>{d.hasta >= d.ahora - 60 ? 'ahora' : eje(d.hasta, corto)}</span></div>
  </section>
}

function Lista({ d, corto, sel, recien, elegir }: { d: Vista; corto: boolean; sel: Ent | null; recien: Set<string>; elegir: (e: Ent) => void }) {
  if (!d.entradas.length) return <p className="adm-vacio">No hay nada con estos filtros. Prueba con más tiempo o con «Todo».</p>
  const ks = claves(d.entradas)
  return <>
    <ol className="adm-lista">
      {d.entradas.map((e, i) => <li key={ks[i]}>
        <button type="button" className={`adm-fila g-${e.g}${recien.has(clave(e)) ? ' recien' : ''}`} aria-pressed={!!sel && clave(sel) === clave(e)} onClick={() => elegir(e)}>
          <span className="adm-hora">{hora(e.t, corto)}</span>
          <i className={`adm-punto g-${e.g}`} title={NOMBRE_G[e.g]} aria-label={NOMBRE_G[e.g]} />
          <span className="adm-origen">{origenDe(e.o, e.p)}</span>
          <span className="adm-texto">{e.x}</span>
          {e.d && <span className="adm-mas">detalle</span>}
        </button>
      </li>)}
    </ol>
    {d.total > d.entradas.length && <p className="pz-nota adm-pie">Se ven las {d.entradas.length} más nuevas de {d.total}. Para ver otras, acota con los filtros o pulsa una barra del gráfico.</p>}
  </>
}

function Grupos({ g, corto, elegir }: { g: Grupo[]; corto: boolean; elegir: (g: Grupo) => void }) {
  if (!g.length) return <p className="adm-vacio">Ningún aviso ni error en este rato.</p>
  return <>
    <p className="pz-nota">Los avisos y errores iguales salen juntos, como en el Error Reporting de Google: primero los errores, y arriba el que más se repite. Pulsa uno para ver todas sus veces.</p>
    <ol className="adm-lista adm-grupos">
      {g.map(x => <li key={x.f}>
        <button type="button" className={`adm-fila g-${x.g}`} onClick={() => elegir(x)}>
          <span className="adm-veces"><b>{x.n}</b> {x.n === 1 ? 'vez' : 'veces'}</span>
          <i className={`adm-punto g-${x.g}`} aria-label={NOMBRE_G[x.g]} />
          <span className="adm-origen">{ORIGENES[x.o] || x.o}{x.perfiles.length ? ` · ${x.perfiles.join(', ')}` : ''}</span>
          <span className="adm-texto">{x.x}</span>
          <span className="adm-cuando">{x.n > 1 ? `${hora(x.primera, corto)} → ${hora(x.ultima, corto)}` : hora(x.ultima, corto)}</span>
        </button>
      </li>)}
    </ol>
  </>
}

function Detalle({ e, veces, verTodas, toast, marcador }: { e: Ent; veces: number; verTodas: () => void; toast: (m: string) => void; marcador: (m: Marcador) => void }) {
  const [cerca, setCerca] = useState<Ent[] | null>(null)
  useEffect(() => {
    let vivo = true
    setCerca(null)
    api<{ entradas: Ent[] }>(`/api/admin/registros/cerca?t=${e.t}&origen=${e.o}${e.p ? `&perfil=${encodeURIComponent(e.p)}` : ''}`).then(r => { if (vivo) setCerca(r.entradas) }).catch(() => { if (vivo) setCerca([]) })
    return () => { vivo = false }
  }, [e])
  const lineas = e.d ? e.d.split('\n') : []
  const antes = (cerca || []).filter(x => x.t <= e.t && clave(x) !== clave(e)).slice(-6)
  const despues = (cerca || []).filter(x => x.t > e.t).slice(0, 6)
  const ks = claves([...antes, e, ...despues])
  const fila = (x: Ent, i: number, yo = false) => <li key={ks[i] + (yo ? '-yo' : '')} className={`g-${x.g}${yo ? ' yo' : ''}`}>
    <span className="adm-hora">{F_HORA.format(new Date(x.t * 1000))}</span><span>{x.x}</span></li>
  return <div className="adm-det">
    <p className={`adm-det-g g-${e.g}`}><i className={`adm-punto g-${e.g}`} aria-hidden="true" /> {NOMBRE_G[e.g]} · {origenDe(e.o, e.p)}</p>
    <p className="adm-det-cuando">{F_LARGA.format(new Date(e.t * 1000))}</p>
    <h3>Qué dice</h3>
    <p className="adm-det-msg">{e.x}</p>
    {lineas.length > 0 && <>
      <h3>Detalle completo</h3>
      <pre className="adm-det-pre">{lineas.map((l, i) => <span key={i} className={l.trim().startsWith('File "') || i === lineas.length - 1 ? 'importa' : undefined}>{l + '\n'}</span>)}</pre>
      <p className="pz-nota">Lo resaltado es lo que importa: las líneas «File …» dicen <b>dónde</b> (el archivo y la función) y la última dice <b>qué</b> falló. Lo demás es el camino que siguió el programa hasta allí.</p>
    </>}
    {veces > 1 && <div className="adm-det-acc"><button type="button" className="pz-btn pz-btn-suave" onClick={verTodas}>Ver las {veces} veces</button></div>}
    <Profesor e={e} toast={toast} marcador={marcador} />
    <h3>Justo antes y después <span className="pz-meta">(2 minutos, mismo origen)</span></h3>
    {cerca === null ? <Esqueleto filas={3} alto={22} /> : antes.length + despues.length === 0 ? <p className="pz-nota">No pasó nada más en esos minutos.</p>
      : <ol className="adm-cerca">{antes.map((x, i) => fila(x, i))}{fila(e, antes.length, true)}{despues.map((x, i) => fila(x, antes.length + 1 + i))}</ol>}
  </div>
}

/** «Explícamelo»: Claude explica el registro como un profesor (pista primero; la solución, si la pides), responde dudas y apunta lo aprendido. */
function Profesor({ e, toast, marcador }: { e: Ent; toast: (m: string) => void; marcador: (m: Marcador) => void }) {
  const [partes, setPartes] = useState<{ tipo: 'explicar' | 'solucion' | 'pregunta'; q?: string; texto: string; nota: string }[]>([])
  const [pensando, setPensando] = useState('')
  const [fallo, setFallo] = useState('')
  const [pregunta, setPregunta] = useState('')
  const [hecho, setHecho] = useState<DeFirma>({})
  const [examen, setExamen] = useState<string[] | null>(null)
  const [respuestas, setRespuestas] = useState<string[]>(['', ''])
  const [nota, setNota] = useState<Nota | null>(null)
  const pedirExamen = async (otro = false) => {
    setFallo(''); setNota(null); setPensando('Claude está preparando 2 preguntas…')
    try {
      const r = await post<Examen>('/api/admin/examen', { t: e.t, f: e.f, otro })
      marcador(r)
      if (!r.ok || !r.preguntas) { setFallo(MOTIVO[r.motivo || 'fallo'] || MOTIVO.fallo); return }
      setExamen(r.preguntas); setRespuestas(r.preguntas.map(() => ''))
    } catch (err) { setFallo(`No se pudo: ${(err as Error).message}`) }
    finally { setPensando('') }
  }
  const entregar = async () => {
    setFallo(''); setPensando('Claude está corrigiendo tus respuestas…')
    try {
      const r = await post<Nota>('/api/admin/examen/corregir', { t: e.t, f: e.f, respuestas })
      marcador(r)
      if (!r.ok) { setFallo(MOTIVO[r.motivo || 'fallo'] || MOTIVO.fallo); return }
      setNota(r); setHecho({ entendido: r.entendido, arreglado: r.arreglado })
      if (r.aprobado) toast(`¡Aprobado! Apuntado en APRENDIZAJE.md · +1 punto · nivel ${r.nivel}: ${r.nombre}`)
    } catch (err) { setFallo(`No se pudo: ${(err as Error).message}`) }
    finally { setPensando('') }
  }
  const pedir = async (modo: 'explicar' | 'solucion' | 'pregunta', extra: { pregunta?: string; otra_vez?: boolean } = {}) => {
    setFallo('')
    setPensando(modo === 'pregunta' ? 'Claude está pensando la respuesta…' : modo === 'solucion' ? 'Claude está preparando la solución paso a paso…' : 'Claude está leyendo el error y el código… (tarda unos 20-30 segundos)')
    try {
      const historial = partes.map(p => ({ q: p.q || (p.tipo === 'solucion' ? 'Dame la solución' : 'Explícamelo'), a: p.texto }))
      const r = await post<Respuesta>('/api/admin/explicar', { t: e.t, f: e.f, modo, historial, ...extra })
      marcador(r)
      if (!r.ok || !r.texto) { setFallo(MOTIVO[r.motivo || 'fallo'] || MOTIVO.fallo); return }
      setHecho({ entendido: r.entendido, arreglado: r.arreglado })
      const nota = r.guardada ? 'Guardada de otra vez: no ha costado nada' : `Ha costado ${dolares(r.coste || 0)}`
      setPartes(ps => [...(extra.otra_vez ? ps.filter(p => p.tipo !== modo) : ps), { tipo: modo, q: extra.pregunta, texto: r.texto!, nota }])
      if (modo === 'pregunta') setPregunta('')
    } catch (err) { setFallo(`No se pudo: ${(err as Error).message}`) }
    finally { setPensando('') }
  }
  const arreglado = async () => {
    try {
      const r = await post<Marcador & { nuevo: boolean; falta_examen?: boolean }>('/api/admin/aprender', { t: e.t, f: e.f, que: 'arreglado' })
      marcador(r)
      if (r.falta_examen) { toast('Primero aprueba el mini examen: no se arregla lo que no se entiende.'); return }
      setHecho(h => ({ ...h, arreglado: true }))
      toast(r.nuevo ? `Apuntado en APRENDIZAJE.md · +2 puntos · nivel ${r.nivel}: ${r.nombre}` : 'Ya lo tenías apuntado.')
    } catch (err) { toast(`No se pudo apuntar: ${(err as Error).message}`) }
  }
  const tiene = (t: string) => partes.some(p => p.tipo === t)
  return <section className="adm-profe" aria-label="Explicación de Claude" aria-busy={!!pensando}>
    {!tiene('explicar') && !pensando && <button type="button" className="pz-btn pz-btn-primario" onClick={() => void pedir('explicar')}><Icono n="spark" size={17} /> Explícamelo</button>}
    {partes.map((p, i) => <div key={i} className={`adm-profe-parte t-${p.tipo}`}>
      {p.tipo === 'pregunta' && <p className="adm-profe-q">Tú: {p.q}</p>}
      {p.tipo === 'solucion' && <h3>La solución</h3>}
      <Md texto={p.texto} />
      <p className="pz-nota adm-profe-nota">{p.nota}{p.tipo !== 'pregunta' && <> · <button type="button" className="pz-enlace" disabled={!!pensando} onClick={() => void pedir(p.tipo, { otra_vez: true })}>explicar otra vez</button></>}</p>
    </div>)}
    {pensando && <p className="adm-profe-pensando" role="status"><i className="adm-latido" aria-hidden="true" /> {pensando}</p>}
    {fallo && <Fallo texto={fallo} />}
    {tiene('explicar') && <>
      <div className="adm-det-acc">
        {!tiene('solucion') && <button type="button" className="pz-btn pz-btn-suave" disabled={!!pensando} onClick={() => void pedir('solucion')}>Enséñame la solución</button>}
        {!examen && !hecho.entendido && <button type="button" className="pz-btn pz-btn-primario" disabled={!!pensando} onClick={() => void pedirExamen()}>Hacer el mini examen</button>}
        {hecho.entendido && <span className="adm-etq"><Icono n="check" size={14} /> Entendido (examen aprobado)</span>}
        <button type="button" className="pz-btn pz-btn-suave" disabled={!hecho.entendido || hecho.arreglado} onClick={() => void arreglado()}
          title={hecho.entendido ? undefined : 'Se desbloquea al aprobar el mini examen'}><Icono n="check" size={16} /> {hecho.arreglado ? 'Arreglado' : 'Lo he arreglado'}</button>
      </div>
      {examen && !hecho.entendido && <form className="adm-examen" onSubmit={ev => { ev.preventDefault(); if (!pensando) void entregar() }}>
        <h3>Mini examen</h3>
        <p className="pz-nota">Contesta con tus palabras, en una o dos frases. Si aciertas las dos, cuenta como entendido.</p>
        {examen.map((p, i) => <label key={i} className="adm-campo"><span>{i + 1}. {p}</span>
          <textarea rows={2} value={respuestas[i] || ''} maxLength={1200} onChange={ev => setRespuestas(rs => rs.map((x, j) => j === i ? ev.target.value : x))} />
          {nota?.notas?.[i] && <small className={nota.notas[i].bien ? 'adm-bien' : 'adm-mal'}>{nota.notas[i].bien ? '✓ ' : '✗ '}{nota.notas[i].comentario}</small>}
        </label>)}
        {nota && !nota.aprobado && <p className="pz-nota">{nota.frase || 'Casi. Repasa la explicación y vuelve a intentarlo.'}</p>}
        <div className="adm-det-acc">
          <button type="submit" className="pz-btn pz-btn-primario" disabled={!!pensando || !respuestas.some(r => r.trim())}>{nota ? 'Corregir otra vez' : 'Corregir'}</button>
          {nota && !nota.aprobado && <button type="button" className="pz-btn pz-btn-texto" disabled={!!pensando} onClick={() => void pedirExamen(true)}>Otras preguntas</button>}
        </div>
      </form>}
      {nota?.aprobado && <p className="adm-estado ok"><Icono n="check" size={18} /> {nota.frase || '¡Aprobado! Lo has entendido.'}</p>}
      <form className="adm-profe-preg" onSubmit={ev => { ev.preventDefault(); if (pregunta.trim() && !pensando) void pedir('pregunta', { pregunta: pregunta.trim() }) }}>
        <label className="adm-campo"><span>Pregúntale algo sobre este error</span>
          <input value={pregunta} onChange={ev => setPregunta(ev.target.value)} maxLength={800} placeholder="¿Y eso por qué pasa? ¿Qué es una ruta?" enterKeyHint="send" /></label>
        <button type="submit" className="pz-btn pz-btn-primario" disabled={!pregunta.trim() || !!pensando}>Preguntar</button>
      </form>
    </>}
  </section>
}

/** Markdown sencillo de Claude pintado como TEXTO (nunca HTML): ###, listas, bloques ``` y `código` / **negrita** en línea. */
function Md({ texto }: { texto: string }) {
  const enLinea = (t: string) => t.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((x, i) =>
    x.startsWith('`') && x.endsWith('`') && x.length > 1 ? <code key={i}>{x.slice(1, -1)}</code>
      : x.startsWith('**') && x.endsWith('**') && x.length > 3 ? <strong key={i}>{x.slice(2, -2)}</strong> : x)
  const bloques: ReactElement[] = []
  const lineas = texto.split('\n')
  for (let i = 0; i < lineas.length; i++) {
    const l = lineas[i]
    if (l.startsWith('```')) {
      const cod: string[] = []
      while (++i < lineas.length && !lineas[i].startsWith('```')) cod.push(lineas[i])
      bloques.push(<pre key={i} className="adm-det-pre adm-md-pre">{cod.join('\n')}</pre>)
    } else if (/^#{1,4}\s/.test(l)) bloques.push(<h4 key={i}>{enLinea(l.replace(/^#+\s*/, ''))}</h4>)
    else if (/^\s*([-*]|\d+\.)\s/.test(l)) {
      const items: string[] = [], numerada = /^\s*\d+\./.test(l)
      for (; i < lineas.length && /^\s*([-*]|\d+\.)\s/.test(lineas[i]); i++) items.push(lineas[i].replace(/^\s*([-*]|\d+\.)\s/, ''))
      i--
      const Lista = numerada ? 'ol' : 'ul'
      bloques.push(<Lista key={i}>{items.map((x, j) => <li key={j}>{enLinea(x)}</li>)}</Lista>)
    } else if (l.trim()) bloques.push(<p key={i}>{enLinea(l)}</p>)
  }
  return <div className="adm-md">{bloques}</div>
}
