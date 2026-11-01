/* Dinero = gastos del mes + suscripciones. Todo es de solo lectura: lo que el vigía de correo ve en tus cobros (el Hub no calcula nada y no inventa cifras).
   Arriba, cuatro cifras claras; debajo, los gastos por categoría y la tabla de suscripciones con sus filtros. */
import { useState } from 'react'
import { post } from '../lib'
import type { Ctx } from '../ctx'
import type { Cancelada, Consejo, GastosMes, Suscripcion } from './api'
import { useDatosTableros } from './datos'
import { cap, diaSemana, eur, inicial, mesDe, nombreCat, paraCancelar, tableroSus } from './formato'
import type { TableroSus } from './formato'
import { diaCorto, enDias, Esqueleto, Fallo, haceMin, plural } from './ui'
import DineroInvitada from './DineroInvitada'

const PERIODO: Record<string, string> = { semanal: 'Semanal', mensual: 'Mensual', trimestral: 'Trimestral', anual: 'Anual' }

/** Una invitada ve SU dinero (de los recibos de su Gmail); Fran, el suyo de siempre. */
export default function Dinero(ctx: Ctx) {
  return ctx.me.role === 'guest' ? <DineroInvitada {...ctx} /> : <DineroFran />
}

function DineroFran() {
  const t = useDatosTableros()
  const b = tableroSus(t.data)
  const fallo = t.data?.find(x => x.id === 'suscripciones')
  return <div className="pz-page pz-dinero">
    <header className="pz-cab-lista"><div><h1>Dinero</h1>{b && <p className="pz-resumen">{resumenDinero(b)}</p>}</div></header>
    {t.error && t.data && <Fallo texto={`No pude actualizar: ${t.error}. Lo que ves puede estar desfasado.`} reintentar={() => void t.reload()} />}
    {b ? <VistaDinero b={b} reintentar={() => void t.reload()} />
      : !t.data ? (t.loading ? <Esqueleto filas={4} alto={72} /> : <Fallo texto={`No pude leer tus gastos${t.error ? `: ${t.error}` : ''}.`} reintentar={() => void t.reload()} />)
        : <Fallo texto={`No pude leer tus gastos y suscripciones${fallo && !fallo.ok ? `: ${fallo.error}` : ''}.`} reintentar={() => void t.reload()} />}
  </div>
}

/** Una frase con lo que importa: «Este mes llevas 148,86 €. Tienes 6 suscripciones activas y 3 para cancelar.» Solo cuenta lo que se pudo leer. */
function resumenDinero(b: TableroSus): string {
  const g = b.gastos && b.gastos.ok ? b.gastos : null
  const vivas = b.items.filter(x => x.estado === 'activa' || x.estado === 'nueva').length
  const canc = b.items.filter(paraCancelar).length
  return [g ? `Este mes llevas ${eur(g.totalEur)}.` : '', vivas ? `Tienes ${plural(vivas, 'suscripción activa', 'suscripciones activas')}${canc ? ` y ${canc} para cancelar` : ''}.` : ''].filter(Boolean).join(' ')
}

export function VistaDinero({ b, reintentar }: { b: TableroSus; reintentar: () => void }) {
  const leyendo = b.lectura?.fase === 'inicial'
  return <div className="pz-dinero-cuerpo">
    {leyendo && <p className="pz-nota" role="status">Todavía estoy leyendo tu correo de los últimos meses{b.lectura?.pendientes ? ` (faltan ${plural(b.lectura.pendientes, 'correo', 'correos')} por mirar)` : ''}: las cifras pueden estar incompletas.</p>}
    <Cifras b={b} />
    <Consejos b={b} reintentar={reintentar} />
    <Gastos g={b.gastos} reintentar={reintentar} />
    <Tabla b={b} reintentar={reintentar} />
    <Canceladas b={b} reintentar={reintentar} />
  </div>
}

/* ---------- las cuatro cifras ---------- */
function Cifras({ b }: { b: TableroSus }) {
  const g = b.gastos && b.gastos.ok ? b.gastos : null
  const eu = b.totales.find(t => t.moneda === 'EUR')
  const otras = b.totales.filter(t => t.moneda !== 'EUR')
  const canc = b.items.filter(paraCancelar)
  const prox = b.items.filter(s => s.dias !== null && s.dias >= 0 && (s.estado === 'activa' || s.estado === 'nueva')).sort((x, y) => (x.dias ?? 0) - (y.dias ?? 0))[0]
  const dif = g && g.anterior.aEstaAltura ? (g.totalEur - g.anterior.aEstaAltura) * 100 / g.anterior.aEstaAltura : null
  return <div className="pz-cifras">
    {g && <div className="pz-cifra-card"><span>Gasto de {mesDe(g.mes)}</span><b>{eur(g.totalEur)}</b>
      <small>{[dif !== null && g.anterior.aEstaAltura !== null ? (Math.abs(dif) < 1 ? 'Casi igual que el mes pasado a estas alturas' : `${Math.round(Math.abs(dif))} % ${dif > 0 ? 'más' : 'menos'} que el mes pasado a estas alturas`) : (g.sinConvertir.length ? '' : 'Lo que llevas gastado este mes'),
        g.sinConvertir.length ? `Sin contar ${g.sinConvertir.map(x => eur(x.importe, x.moneda)).join(' y ')} (otra moneda, sin convertir)` : ''].filter(Boolean).join(' · ')}</small></div>}
    {eu && <div className="pz-cifra-card"><span>Suscripciones al mes</span><b>{eur(eu.mensual)}</b>
      <small>{otras.length ? `+ ${otras.map(t => eur(t.mensual, t.moneda)).join(' y ')} sin convertir · ` : ''}≈ {eur(eu.anual)} al año (solo euros)</small></div>}
    <div className="pz-cifra-card"><span>Para cancelar</span><b className={canc.length ? 'mal' : ''}>{canc.length}</b><small>{canc.length ? canc.map(s => s.nombre).join(', ') : 'Ninguna en tu lista de cancelar'}</small></div>
    <div className="pz-cifra-card"><span>Próximo cobro</span><b>{prox ? (prox.dias === 0 ? 'hoy' : prox.dias === 1 ? 'mañana' : diaSemana(prox.proximaFecha)) : '—'}</b>
      <small>{prox ? `${prox.nombre}${prox.importe !== null ? ` · ${eur(prox.importe, prox.moneda || 'EUR')}` : ''}` : 'No veo cobros próximos'}</small></div>
  </div>
}

/* ---------- gastos por categoría ---------- */
function Gastos({ g, reintentar }: { g: GastosMes | null; reintentar: () => void }) {
  if (!g) return null
  if (!g.ok) return <section aria-labelledby="pz-g-t"><div className="pz-tarjeta-cab"><h2 id="pz-g-t">Gastos del mes</h2></div><Fallo texto={`No pude leer los gastos del mes: ${g.error}.`} reintentar={reintentar} /></section>
  const p = g.presupuesto
  const mayor = Math.max(1, ...g.porCategoria.map(c => c.importeEur ?? 0))
  const uso = p.topeActivo && p.tope ? (p.usado ?? g.totalEur) : null
  const pasado = uso !== null && p.tope !== null && uso > p.tope
  return <section className="pz-tarjeta-g pz-gastos" aria-labelledby="pz-g-t">
    <div className="pz-tarjeta-cab"><h2 id="pz-g-t">Gastos de {mesDe(g.mes)} por categoría</h2></div>
    {g.anterior.totalEur !== null && <p className="pz-gastos-cmp">{cap(mesDe(g.anterior.mes))} entero: <b>{eur(g.anterior.totalEur)}</b>.</p>}
    {uso !== null && p.tope !== null && <div className="pz-tope">
      <div role="progressbar" aria-label="Tope mensual" aria-valuemin={0} aria-valuemax={p.tope} aria-valuenow={Math.min(uso, p.tope)} className={`pz-tope-barra ${pasado ? 'pasado' : ''}`}>
        <i style={{ width: `${Math.min(100, Math.round(uso * 100 / p.tope))}%` }} /></div>
      <span className={pasado ? 'pz-mal' : ''}>{pasado ? 'Te has pasado del tope: ' : 'Tope del mes: '}{eur(uso)} de {eur(p.tope)}</span>
    </div>}
    {g.porCategoria.length > 0
      ? <ul className="pz-cats" aria-label="Gasto por categoría">{g.porCategoria.map((c, i) => <li key={i}>
        <span className="pz-cat-nom">{nombreCat(c.nombre)}{c.moneda !== 'EUR' ? ` (${c.moneda})` : ''}</span><span className="pz-cat-imp">{eur(c.importe, c.moneda)}</span>
        {c.importeEur !== null && <span className="pz-cat-barra" aria-hidden="true"><i style={{ width: `${Math.max(2, Math.round(c.importeEur * 100 / mayor))}%` }} /></span>}</li>)}</ul>
      : <p className="pz-vacio">Todavía no hay gastos apuntados este mes.</p>}
    {((g.sinClasificar ?? 0) > 0 || (g.dudosos ?? 0) > 0) && <p className="pz-nota">
      {g.sinClasificar ? plural(g.sinClasificar, 'gasto sin clasificar', 'gastos sin clasificar') : ''}{g.sinClasificar && g.dudosos ? ' · ' : ''}
      {g.dudosos ? `${plural(g.dudosos, 'dudoso', 'dudosos')} (no suman hasta que se aclaren)` : ''}.</p>}
  </section>
}

/* ---------- tabla de suscripciones ---------- */
type Filtro = 'todas' | 'cancelar' | 'semana' | 'posibles'
const FILTROS: { id: Filtro; texto: string }[] = [{ id: 'todas', texto: 'Todas' }, { id: 'cancelar', texto: 'Para cancelar' }, { id: 'semana', texto: 'Renuevan en 7 días' }, { id: 'posibles', texto: 'Posibles canceladas' }]
const pasa = (f: Filtro, s: Suscripcion) => f === 'todas' ? true : f === 'cancelar' ? paraCancelar(s) : f === 'posibles' ? s.estado === 'posible_cancelada'
  : s.dias !== null && s.dias >= 0 && s.dias <= 7 && (s.estado === 'activa' || s.estado === 'nueva')

function Tabla({ b, reintentar }: { b: TableroSus; reintentar: () => void }) {
  const [f, setF] = useState<Filtro>('todas')
  if (!b.items.length) return <section className="pz-calma pz-calma-espera"><div><strong>{cap(b.nota || 'Pendiente del vigilante de correo')}</strong>
    <p>Una suscripción aparece cuando el vigilante ve al menos dos cobros parecidos del mismo sitio, a un mes, un año o una semana de distancia.</p></div></section>
  const cuenta = (x: Filtro) => b.items.filter(s => pasa(x, s)).length
  const lista = b.items.filter(s => pasa(f, s)).sort((x, y) => (paraCancelar(y) ? 1 : 0) - (paraCancelar(x) ? 1 : 0) || (x.dias ?? 999) - (y.dias ?? 999))
  const vivas = b.items.filter(x => x.estado === 'activa' || x.estado === 'nueva').length
  return <section aria-labelledby="pz-s-t">
    <div className="pz-tarjeta-cab"><h2 id="pz-s-t">Suscripciones <small>· {plural(vivas, 'activa', 'activas')}</small></h2>
      {b.lectura?.ultimaLectura && <small className="pz-meta">Leído del correo {haceMin(Math.max(0, Math.round((Date.now() - new Date(b.lectura.ultimaLectura).getTime()) / 60000)))}</small>}</div>
    <div className="pz-pestanas" role="group" aria-label="Qué suscripciones ver">
      {FILTROS.map(x => <button key={x.id} type="button" aria-pressed={f === x.id} onClick={() => setF(x.id)}>{x.texto}{x.id !== 'todas' && cuenta(x.id) > 0 && <span className={`pz-tag ${x.id === 'cancelar' ? 'pz-tag-vino' : 'pz-tag-gris'}`}>{cuenta(x.id)}</span>}</button>)}
    </div>
    {lista.length ? <div className="pz-tabla-caja"><table className="pz-tabla">
      <thead><tr><th scope="col">Suscripción</th><th scope="col">Importe</th><th scope="col">Periodo</th><th scope="col">Próximo cobro</th><th scope="col">Estado</th><th scope="col">Cuenta</th><th scope="col">¿Qué hago?</th></tr></thead>
      <tbody>{lista.map((s, i) => <Fila key={`${s.nombre}-${s.moneda}-${i}`} s={s} reintentar={reintentar} />)}</tbody>
    </table></div> : <p className="pz-vacio">No hay ninguna en esta vista.</p>}
  </section>
}

function Fila({ s, reintentar }: { s: Suscripcion; reintentar: () => void }) {
  const canc = paraCancelar(s)
  const cobro = s.estado === 'posible_cancelada' ? (s.ultimoCobro ? `Último: ${diaCorto(s.ultimoCobro)}` : 'Sin cobros recientes') : s.proximaFecha ? `${diaCorto(s.proximaFecha)}` : 'Sin próximo cobro'
  const cuando = s.estado !== 'posible_cancelada' && s.proximaFecha ? enDias(s.dias) + (s.proximoFuente === 'agenda' ? ' · según tu agenda' : s.proximoFuente === 'estimado' ? ' · estimado' : '') : ''
  return <tr className={canc ? 'cancelar' : ''}>
    <th scope="row" data-et="Suscripción"><div className="pz-tb-celda"><span className="pz-logo" aria-hidden="true">{inicial(s.nombre)}</span><span className="pz-tb-nom"><strong>{s.nombre}</strong><small>{s.categoria ? nombreCat(s.categoria) : s.estado === 'solo_agenda' ? 'Solo en tu agenda' : 'Sin categoría'}</small></span></div></th>
    <td data-et="Importe"><b>{s.importe !== null ? eur(s.importe, s.moneda || 'EUR') : 'Sin confirmar'}</b>{s.periodo === 'anual' && s.mensual !== null && <small>≈ {eur(s.mensual, s.moneda || 'EUR')} al mes</small>}</td>
    <td data-et="Periodo">{s.periodo ? PERIODO[s.periodo] : '—'}</td>
    <td data-et="Próximo cobro"><span className={canc && s.dias !== null && s.dias <= 1 ? 'pz-mal' : ''}>{cobro}</span>{cuando && <small>{cuando}</small>}</td>
    <td data-et="Estado"><span className="pz-etqs">
      {canc ? <span className="pz-tag pz-tag-vino">Para cancelar</span>
        : s.estado === 'activa' ? <span className="pz-tag pz-tag-verde">Activa</span>
          : s.estado === 'nueva' ? <span className="pz-tag pz-tag-gris">Nueva</span>
            : s.estado === 'solo_agenda' ? <span className="pz-tag pz-tag-gris">Solo agenda</span>
              : s.cancelar ? <span className="pz-tag pz-tag-gris">Ya no cobran</span> : <span className="pz-tag pz-tag-gris">¿Cancelada?</span>}
      {s.subidaPct !== null && s.subidaPct > 0 && <span className="pz-tag pz-tag-gris">Sube {Math.round(s.subidaPct)} %</span>}</span></td>
    <td data-et="Cuenta">{s.cuenta || '—'}</td>
    <td data-et="¿Qué hago?"><Botones comercio={s.comercio} acciones={canc ? ['cancelada', 'sigue'] : ['cancelada', 'quiero-cancelar', 'sigue']} reintentar={reintentar} /></td>
  </tr>
}

/* ---------- decisiones de Fran: se anotan en el vigía y todo se recalcula ---------- */
const TEXTO_ACC: Record<string, string> = { cancelada: 'Ya la cancelé', 'quiero-cancelar': 'Quiero cancelarla', sigue: 'Sigue activa', deshacer: 'Deshacer' }

/** Cada pregunta se contesta con palabras que encajan con ella (no un «Sigue» genérico). */
function rotulos(texto: string): Record<string, string> {
  if (/ha subido/i.test(texto)) return { sigue: 'Sí, me compensa', 'quiero-cancelar': 'No, quiero cancelarla', cancelada: 'Ya la cancelé' }
  if (/sin cobrar|¿La cancelaste/i.test(texto)) return { cancelada: 'Sí, la cancelé', sigue: 'No, sigue activa' }
  if (/lista para cancelar/i.test(texto)) return { cancelada: 'Ya la cancelé' }
  return { sigue: 'Sí, la mantengo', 'quiero-cancelar': 'Quiero cancelarla', cancelada: 'Ya la cancelé' }
}

function Botones({ comercio, acciones, reintentar, rot }: { comercio: string; acciones: string[]; reintentar: () => void; rot?: Record<string, string> }) {
  const [ocupado, setOcupado] = useState('')
  const [fallo, setFallo] = useState('')
  const ir = async (accion: string) => {
    setOcupado(accion); setFallo('')
    try { await post('/api/gastos/decidir', { accion, comercio }); reintentar() } catch (e) { setFallo(e instanceof Error ? e.message : 'No se pudo anotar') } finally { setOcupado('') }
  }
  return <span className="pz-etqs">
    {acciones.map(a => <button key={a} type="button" className="pz-enlace" disabled={!!ocupado} onClick={() => void ir(a)}>{ocupado === a ? 'Anotando…' : (rot?.[a] ?? TEXTO_ACC[a])}</button>)}
    {fallo && <small className="pz-mal" role="alert">{fallo}</small>}
  </span>
}

/* ---------- lo que la app piensa: preguntas con botones ---------- */
function Consejos({ b, reintentar }: { b: TableroSus; reintentar: () => void }) {
  if (!b.consejos.length) return null
  return <section aria-labelledby="pz-c-t">
    <div className="pz-tarjeta-cab"><h2 id="pz-c-t">Para decidir</h2></div>
    <ul className="pz-cats pz-consejos">{b.consejos.map((c: Consejo, i) => <li key={`${c.comercio}-${i}`}>
      <span className="pz-cat-nom">{c.texto}{c.ia ? ' · IA' : ''}</span>
      <Botones comercio={c.comercio} acciones={c.acciones} reintentar={reintentar} rot={rotulos(c.texto)} /></li>)}</ul>
  </section>
}

/* ---------- canceladas: fuera de las cuentas, con deshacer ---------- */
function Canceladas({ b, reintentar }: { b: TableroSus; reintentar: () => void }) {
  if (!b.canceladas.length && !b.ocultas) return null
  return <section aria-labelledby="pz-x-t">
    <div className="pz-tarjeta-cab"><h2 id="pz-x-t">Canceladas · {b.canceladas.length}</h2></div>
    {b.canceladas.length > 0 && <ul className="pz-cats">{b.canceladas.map((c: Cancelada) => <li key={c.comercio}>
      <span className="pz-cat-nom">{cap(c.comercio)}{c.desde ? ` · desde el ${diaCorto(c.desde)}` : ''}</span>
      <Botones comercio={c.comercio} acciones={['deshacer']} reintentar={reintentar} /></li>)}</ul>}
    <p className="pz-nota">Si alguna vuelve a cobrarte, te aviso.{b.ocultas ? ` Hay ${plural(b.ocultas, 'suscripción que solo sale', 'suscripciones que solo salen')} en tu agenda sin cobros reales: no las cuento hasta que haya un cobro.` : ''}</p>
  </section>
}
