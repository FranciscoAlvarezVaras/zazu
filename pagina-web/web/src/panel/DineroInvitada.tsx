/* Dinero de una invitada (nivel Familia, con su Gmail): primero «¿Qué quieres ver?» (gastos del mes, suscripciones, presupuesto con su cifra
   y la moneda) y luego su resumen, con el mismo estilo que el Dinero de Fran. Lo calcula el servidor a partir de los recibos de SU Gmail
   (/api/inv/dinero); aquí solo se pinta, siempre como texto. Lo que se lee del correo nunca llega como HTML. */
import { useEffect, useState } from 'react'
import type { Ctx } from '../ctx'
import { post, useFetch } from '../lib'
import { cap, eur, inicial, mesDe, nombreCat } from './formato'
import { diaCorto, enDias, Esqueleto, Fallo, plural } from './ui'
import './dinero-invitada.css'

type Moneda = 'EUR' | 'USD' | 'GBP'
type Ver = { gastos: boolean; suscripciones: boolean; presupuesto: boolean }
type Eleccion = { elegido: boolean; ver: Ver; presupuesto: number | null; moneda: Moneda }
type Sub = { nombre: string; importe: number | null; moneda: string; periodo: string | null; mensual: number | null; proximo: string | null; dias: number | null; estado: string; categoria: string | null }
type Resumen = {
  mes: string; moneda: Moneda
  gastos?: { total: number; n: number; categorias: { categoria: string; importe: number; n: number }[]; otras_monedas: { moneda: string; importe: number }[]
    ultimos: { nombre: string; importe: number; moneda: string; fecha: string; categoria: string; reembolso: boolean }[] }
  suscripciones?: { items: Sub[]; activas: number; al_mes: number }
  presupuesto?: { tope: number; usado: number; pasado: boolean }
}
type Vista = { ok: boolean; gmail: boolean; mensaje?: string; eleccion: Eleccion; leyendo?: boolean; leido?: string | null; parcial?: boolean; error?: string | null; resumen?: Resumen | null }

const MONEDAS: { id: Moneda; texto: string }[] = [{ id: 'EUR', texto: 'Euros (€)' }, { id: 'USD', texto: 'Dólares (US$)' }, { id: 'GBP', texto: 'Libras (£)' }]
const PERIODO: Record<string, string> = { semanal: 'Semanal', mensual: 'Mensual', trimestral: 'Trimestral', anual: 'Anual' }
const OPCIONES: { id: keyof Ver; texto: string; ayuda: string }[] = [
  { id: 'gastos', texto: 'Gastos del mes', ayuda: 'Lo que llevas gastado, por categorías, y tus últimos pagos.' },
  { id: 'suscripciones', texto: 'Suscripciones', ayuda: 'Lo que te cobran cada mes o cada año, y cuándo es el próximo cobro.' },
  { id: 'presupuesto', texto: 'Presupuesto mensual', ayuda: 'Un tope al mes y cuánto llevas.' },
]

export default function DineroInvitada({ go }: Ctx) {
  const [cada, setCada] = useState(0)
  const v = useFetch<Vista>('/api/inv/dinero', cada)
  const [editando, setEditando] = useState(false)
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const d = v.data
  useEffect(() => { setCada(d?.leyendo ? 3000 : 0) }, [d?.leyendo])   // mientras lee su correo, se vuelve a preguntar cada 3 s

  const actualizar = async () => {
    setOcupado(true); setAviso('')
    try { await post('/api/inv/dinero/actualizar', {}); await v.reload() }
    catch (e) { setAviso((e as Error).message) }
    finally { setOcupado(false) }
  }

  const cab = (texto?: string, acciones = false) => <header className="pz-cab-lista"><div><h1>Dinero</h1>{texto && <p className="pz-resumen">{texto}</p>}</div>
    {acciones && <div className="pz-cab-acc">
      <button type="button" className="pz-btn pz-btn-fila" onClick={() => void actualizar()} disabled={ocupado || !!d?.leyendo}>{d?.leyendo ? 'Leyendo…' : 'Actualizar'}</button>
      <button type="button" className="pz-btn pz-btn-texto" onClick={() => setEditando(true)}>Cambiar qué veo</button></div>}</header>

  if (!d) return <div className="pz-page pz-dinero">{cab()}
    {v.loading ? <Esqueleto filas={4} alto={72} /> : <Fallo texto={`No pude abrir tu Dinero${v.error ? `: ${v.error}` : ''}.`} reintentar={() => void v.reload()} />}</div>

  if (!d.gmail) return <div className="pz-page pz-dinero">{cab()}
    <section className="pz-calma pz-calma-espera dinv-sin-gmail"><div><strong>{d.mensaje || 'Conecta tu Gmail para ver tu dinero.'}</strong>
      <p>Cuando lo conectes, aquí verás tus gastos y suscripciones sacados de tus recibos.</p>
      <button type="button" className="pz-btn pz-btn-primario" onClick={() => go('ajustes')}>Ir a Tu espacio</button></div></section></div>

  if (!d.eleccion.elegido || editando) return <div className="pz-page pz-dinero">{cab()}
    <Elegir inicial={d.eleccion} primera={!d.eleccion.elegido} cancelar={d.eleccion.elegido ? () => setEditando(false) : undefined}
      listo={async () => { setEditando(false); await v.reload() }} /></div>

  const r = d.resumen
  return <div className="pz-page pz-dinero">
    {cab(r ? frase(r) : undefined, true)}
    {v.error && <Fallo texto={`No pude actualizar: ${v.error}. Lo que ves puede estar desfasado.`} reintentar={() => void v.reload()} />}
    {aviso && <p className="pz-nota" role="status">{aviso}</p>}
    {d.leyendo && <p className="pz-nota" role="status">{r ? 'Estoy mirando si hay recibos nuevos en tu Gmail…' : 'Estoy leyendo los recibos de tu Gmail de los últimos 3 meses. Tarda un minuto: puedes quedarte o volver luego.'}</p>}
    {!d.leyendo && d.parcial && r && <p className="pz-nota">Todavía me quedan correos por mirar: las cifras pueden estar incompletas. Sigo la próxima vez que entres.</p>}
    {d.error && !d.leyendo && <Fallo texto={d.error} reintentar={() => void actualizar()} ocupado={ocupado} />}
    {r ? <VistaResumen r={r} /> : d.leyendo ? <Esqueleto filas={3} alto={72} /> : null}
    <p className="pz-nota dinv-pie">Solo leo tus recibos del correo (nunca escribo ni borro nada) y no apunto la publicidad.{d.leido ? ` Última lectura: ${diaCorto(d.leido.slice(0, 10))}.` : ''}</p>
  </div>
}

function frase(r: Resumen): string {
  const g = r.gastos, s = r.suscripciones, p = r.presupuesto
  return [g ? `Este mes llevas ${eur(g.total, r.moneda)}.` : p ? `Este mes llevas ${eur(p.usado, r.moneda)} de ${eur(p.tope, r.moneda)}.` : '',
    s && s.activas ? `Tienes ${plural(s.activas, 'suscripción activa', 'suscripciones activas')}.` : ''].filter(Boolean).join(' ')
}

/* ---------- «¿Qué quieres ver?» ---------- */
function Elegir({ inicial: ini, primera, cancelar, listo }: { inicial: Eleccion; primera: boolean; cancelar?: () => void; listo: () => Promise<void> }) {
  const [ver, setVer] = useState<Ver>(ini.ver)
  const [moneda, setMoneda] = useState<Moneda>(ini.moneda)
  const [tope, setTope] = useState(ini.presupuesto ? String(ini.presupuesto).replace('.', ',') : '')
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const algo = ver.gastos || ver.suscripciones || ver.presupuesto
  const guardar = async () => {
    setError('')
    if (!algo) { setError('Elige al menos una cosa para ver.'); return }
    if (ver.presupuesto && !tope.trim()) { setError('Pon la cifra de tu presupuesto al mes, por ejemplo 400.'); return }
    setOcupado(true)
    try { await post('/api/inv/dinero/elegir', { ver, moneda, presupuesto: ver.presupuesto ? tope : null }); await listo() }
    catch (e) { setError((e as Error).message) }
    finally { setOcupado(false) }
  }
  return <section className="pz-tarjeta-g dinv-elegir" aria-labelledby="dinv-t">
    <div className="pz-tarjeta-cab"><h2 id="dinv-t">¿Qué quieres ver?</h2></div>
    <div className="dinv-cuerpo">
      <p className="dinv-intro">{primera ? 'Puedo mirar los recibos de tu Gmail de los últimos 3 meses y enseñarte lo que elijas. ' : ''}Solo leo los recibos: nunca escribo ni borro nada. Lo puedes cambiar cuando quieras.</p>
      <fieldset className="dinv-opciones"><legend className="dinv-oculto">Qué ver</legend>
        {OPCIONES.map(o => <label key={o.id} className={`dinv-opcion ${ver[o.id] ? 'on' : ''}`}>
          <input type="checkbox" checked={ver[o.id]} onChange={e => setVer({ ...ver, [o.id]: e.target.checked })} />
          <span><strong>{o.texto}</strong><small>{o.ayuda}</small></span></label>)}
      </fieldset>
      {ver.presupuesto && <label className="dinv-tope"><span>¿Cuánto quieres gastar como mucho al mes?</span>
        <span className="dinv-tope-campo"><input type="text" inputMode="decimal" autoComplete="off" placeholder="400" value={tope} maxLength={12}
          onChange={e => setTope(e.target.value.replace(/[^\d.,]/g, ''))} /><b>{moneda === 'EUR' ? '€' : moneda === 'USD' ? 'US$' : '£'}</b></span></label>}
      <div className="dinv-moneda"><span id="dinv-mon">¿En qué moneda?</span>
        <div className="pz-pestanas" role="group" aria-labelledby="dinv-mon">
          {MONEDAS.map(m => <button key={m.id} type="button" aria-pressed={moneda === m.id} onClick={() => setMoneda(m.id)}>{m.texto}</button>)}</div>
        <small className="pz-nota">Los pagos en otra moneda se enseñan aparte, sin convertir.</small></div>
      {error && <p className="pz-mal" role="alert">{error}</p>}
      <div className="dinv-botones">
        <button type="button" className="pz-btn pz-btn-primario pz-btn-grande" onClick={() => void guardar()} disabled={ocupado}>{ocupado ? 'Guardando…' : primera ? 'Empezar' : 'Guardar'}</button>
        {cancelar && <button type="button" className="pz-btn pz-btn-texto" onClick={cancelar} disabled={ocupado}>Cancelar</button>}
      </div>
    </div>
  </section>
}

/* ---------- su resumen ---------- */
function VistaResumen({ r }: { r: Resumen }) {
  const g = r.gastos, s = r.suscripciones, p = r.presupuesto
  const vivas = s ? s.items.filter(x => x.estado === 'activa' || x.estado === 'nueva') : []
  const prox = vivas.filter(x => x.dias !== null && x.dias >= 0).sort((a, b) => (a.dias ?? 0) - (b.dias ?? 0))[0]
  return <div className="pz-dinero-cuerpo">
    <div className="pz-cifras">
      {g && <div className="pz-cifra-card"><span>Gasto de {mesDe(r.mes)}</span><b>{eur(g.total, r.moneda)}</b>
        <small>{[g.n ? plural(g.n, 'pago', 'pagos') : 'Sin pagos este mes', g.otras_monedas.length ? `sin contar ${g.otras_monedas.map(x => eur(x.importe, x.moneda)).join(' y ')} en otra moneda` : ''].filter(Boolean).join(' · ')}</small></div>}
      {p && <div className="pz-cifra-card"><span>Presupuesto del mes</span><b className={p.pasado ? 'mal' : ''}>{eur(p.usado, r.moneda)}</b>
        <small>{p.pasado ? `Te has pasado: el tope es ${eur(p.tope, r.moneda)}` : `de ${eur(p.tope, r.moneda)} · te quedan ${eur(p.tope - p.usado, r.moneda)}`}</small></div>}
      {s && <div className="pz-cifra-card"><span>Suscripciones al mes</span><b>{eur(s.al_mes, r.moneda)}</b><small>{s.activas ? plural(s.activas, 'activa', 'activas') : 'Ninguna activa'}</small></div>}
      {s && <div className="pz-cifra-card"><span>Próximo cobro</span><b>{prox ? cap(enDias(prox.dias)) : '—'}</b>
        <small>{prox ? `${prox.nombre}${prox.importe !== null ? ` · ${eur(prox.importe, prox.moneda)}` : ''}` : 'No veo cobros próximos'}</small></div>}
    </div>
    {p && <div className="pz-tope">
      <div role="progressbar" aria-label="Presupuesto del mes" aria-valuemin={0} aria-valuemax={p.tope} aria-valuenow={Math.min(Math.max(p.usado, 0), p.tope)} className={`pz-tope-barra ${p.pasado ? 'pasado' : ''}`}>
        <i style={{ width: `${Math.min(100, Math.max(0, Math.round(p.usado * 100 / p.tope)))}%` }} /></div>
      <span className={p.pasado ? 'pz-mal' : ''}>{p.pasado ? 'Te has pasado del presupuesto: ' : 'Presupuesto: '}{eur(p.usado, r.moneda)} de {eur(p.tope, r.moneda)}</span>
    </div>}
    {g && <Categorias g={g} r={r} />}
    {g && <Ultimos g={g} />}
    {s && <Suscripciones s={s} />}
  </div>
}

function Categorias({ g, r }: { g: NonNullable<Resumen['gastos']>; r: Resumen }) {
  const mayor = Math.max(1, ...g.categorias.map(c => c.importe))
  return <section className="pz-tarjeta-g pz-gastos" aria-labelledby="dinv-c-t">
    <div className="pz-tarjeta-cab"><h2 id="dinv-c-t">Gastos de {mesDe(r.mes)} por categoría</h2></div>
    {g.categorias.length ? <ul className="pz-cats" aria-label="Gasto por categoría">{g.categorias.map(c => <li key={c.categoria}>
      <span className="pz-cat-nom">{nombreCat(c.categoria)}</span><span className="pz-cat-imp">{eur(c.importe, r.moneda)}</span>
      <span className="pz-cat-barra" aria-hidden="true"><i style={{ width: `${Math.max(2, Math.round(Math.max(c.importe, 0) * 100 / mayor))}%` }} /></span></li>)}</ul>
      : <p className="pz-vacio">Todavía no veo gastos este mes.</p>}
  </section>
}

function Ultimos({ g }: { g: NonNullable<Resumen['gastos']> }) {
  return <section aria-labelledby="dinv-u-t">
    <div className="pz-tarjeta-cab"><h2 id="dinv-u-t">Últimos pagos</h2></div>
    {g.ultimos.length ? <div className="pz-tabla-caja"><table className="pz-tabla">
      <thead><tr><th scope="col">Comercio</th><th scope="col">Importe</th><th scope="col">Fecha</th><th scope="col">Categoría</th></tr></thead>
      <tbody>{g.ultimos.map((x, i) => <tr key={i}>
        <th scope="row" data-et="Comercio"><div className="pz-tb-celda"><span className="pz-logo" aria-hidden="true">{inicial(x.nombre)}</span><span className="pz-tb-nom"><strong>{x.nombre}</strong></span></div></th>
        <td data-et="Importe"><b>{x.reembolso ? '+' : ''}{eur(x.importe, x.moneda)}</b>{x.reembolso && <small>Te lo devolvieron</small>}</td>
        <td data-et="Fecha">{diaCorto(x.fecha)}</td>
        <td data-et="Categoría">{nombreCat(x.categoria)}</td></tr>)}</tbody>
    </table></div> : <p className="pz-vacio">No he encontrado recibos en tus últimos 3 meses.</p>}
  </section>
}

function Suscripciones({ s }: { s: NonNullable<Resumen['suscripciones']> }) {
  if (!s.items.length) return <section className="pz-calma pz-calma-espera"><div><strong>No he visto suscripciones en tu correo</strong>
    <p>Una suscripción aparece cuando veo al menos dos cobros parecidos del mismo sitio, a un mes, un año o una semana de distancia.</p></div></section>
  return <section aria-labelledby="dinv-s-t">
    <div className="pz-tarjeta-cab"><h2 id="dinv-s-t">Suscripciones <small>· {plural(s.activas, 'activa', 'activas')}</small></h2></div>
    <div className="pz-tabla-caja"><table className="pz-tabla">
      <thead><tr><th scope="col">Suscripción</th><th scope="col">Importe</th><th scope="col">Periodo</th><th scope="col">Próximo cobro</th><th scope="col">Estado</th></tr></thead>
      <tbody>{s.items.map((x, i) => <tr key={`${x.nombre}-${x.moneda}-${i}`}>
        <th scope="row" data-et="Suscripción"><div className="pz-tb-celda"><span className="pz-logo" aria-hidden="true">{inicial(x.nombre)}</span><span className="pz-tb-nom"><strong>{x.nombre}</strong><small>{x.categoria ? nombreCat(x.categoria) : 'Sin categoría'}</small></span></div></th>
        <td data-et="Importe"><b>{x.importe !== null ? eur(x.importe, x.moneda) : 'Sin confirmar'}</b>{x.periodo === 'anual' && x.mensual !== null && <small>≈ {eur(x.mensual, x.moneda)} al mes</small>}</td>
        <td data-et="Periodo">{x.periodo ? PERIODO[x.periodo] : '—'}</td>
        <td data-et="Próximo cobro">{x.estado === 'posible_cancelada' ? 'Sin cobros recientes' : x.proximo ? diaCorto(x.proximo) : '—'}{x.estado !== 'posible_cancelada' && x.proximo && <small>{enDias(x.dias)} · estimado</small>}</td>
        <td data-et="Estado">{x.estado === 'activa' ? <span className="pz-tag pz-tag-verde">Activa</span> : x.estado === 'nueva' ? <span className="pz-tag pz-tag-gris">Nueva</span> : <span className="pz-tag pz-tag-gris">¿Cancelada?</span>}</td>
      </tr>)}</tbody>
    </table></div>
  </section>
}
