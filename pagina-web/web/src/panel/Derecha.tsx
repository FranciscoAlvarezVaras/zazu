/* Panel de la derecha (pantallas anchas): en Inicio, lo que viene (agenda, renovaciones, gasto); en Hablar con Zazu, las conversaciones
   recientes, el estilo de Zazu y lo que tiene a mano. Todo sale de datos reales; si una fuente falla se dice, nunca «0».
   Solo las secciones que esta persona tiene: una invitada ve su agenda y sus conversaciones, nada de las cosas de Fran. */
import { ParaHacer } from './Semana'
import { irA, puede, relTime } from '../lib'
import type { Ctx } from '../ctx'
import { esEstilo, PERFIL_HERMES } from '../tipos'
import { PROFILE_NAMES } from '../data'
import { tituloSesion } from '../screens/Sessions'
import { useDatosPanel, useDatosTableros } from './datos'
import { cap, diaSemana, eur, mesDe, paraCancelar, tableroSus } from './formato'
import { nombreFuente } from './Avisos'
import { cuandoCorto, Esqueleto, Fallo, horaDe, Icono } from './ui'

/** «Agenda de hoy», «Renuevan esta semana» y «Gasto de octubre». */
export function PanelInicio({ ctx }: { ctx: Ctx }) {
  const { data, loading, error, refrescar } = useDatosPanel()
  const tab = useDatosTableros()
  const sus = tableroSus(tab.data)
  const susFalla = !!tab.data && !sus && tab.data.some(b => b.id === 'suscripciones' && !b.ok)

  const hoy = data?.eventos.ok ? data.eventos.items.filter(e => e.dia === 'hoy').sort((a, b) => (a.todoDia === b.todoDia ? a.inicio.localeCompare(b.inicio) : a.todoDia ? -1 : 1)) : []
  const manana = data?.eventos.ok ? data.eventos.items.filter(e => e.dia === 'mañana').sort((a, b) => a.inicio.localeCompare(b.inicio)) : []
  const filasAg = [...hoy.map(e => ({ e, cuando: e.todoDia ? 'Todo el día' : horaDe(e.inicio) })), ...manana.map(e => ({ e, cuando: 'Mañana' }))].slice(0, 5)

  const renuevan = (sus?.items || []).filter(s => s.dias !== null && s.dias >= 0 && s.dias <= 7 && (s.estado === 'activa' || s.estado === 'nueva')).sort((a, b) => (a.dias ?? 0) - (b.dias ?? 0)).slice(0, 4)
  const g = sus?.gastos && sus.gastos.ok ? sus.gastos : null
  const top = g ? g.porComercio.slice(0, 2).map(c => `${cap(c.nombre)} ${eur(c.importe, c.moneda)}`).join(' · ') : ''

  return <>
    <ParaHacer ctx={ctx} />
    {(!data || data.hay.eventos) && <section aria-labelledby="pz-d-ag">
      <div className="pz-der-cab"><h2 id="pz-d-ag">Agenda de hoy</h2><button type="button" className="pz-enlace" onClick={() => ctx.go('calendario')}>Ver agenda</button></div>
      {!data ? (loading ? <Esqueleto filas={3} alto={44} /> : <Fallo texto={`No pude leer la agenda${error ? `: ${error}` : ''}.`} reintentar={() => void refrescar()} />)
        : !data.eventos.ok ? <Fallo texto={`No pude leer la agenda: ${data.eventos.error}.`} reintentar={() => void refrescar()} />
          : filasAg.length ? <ul className="pz-der-lista">{filasAg.map(({ e, cuando }) => <li key={e.id + cuando} className="pz-ev">
            <span className={`pz-hm ${cuando === 'Mañana' ? 'man' : ''}`}>{cuando}</span>
            <div><strong>{e.tentativo ? '¿? ' : ''}{e.titulo}</strong>
              <small>{[cuando === 'Mañana' && !e.todoDia ? horaDe(e.inicio) : '', e.tentativo ? 'Evento tentativo de Zazu' : '', e.lugar, e.llevar.length ? `Lleva ${e.llevar.join(', ')}` : ''].filter(Boolean).join(' · ') || e.cuenta}</small></div></li>)}</ul>
            : <p className="pz-vacio">Nada en tu agenda hoy ni mañana.</p>}
    </section>}

    {(sus || susFalla || tab.loading) && <section aria-labelledby="pz-d-re">
      <div className="pz-der-cab"><h2 id="pz-d-re">Renuevan esta semana</h2><button type="button" className="pz-enlace" onClick={() => ctx.go('dinero')}>Dinero</button></div>
      {!sus ? (susFalla ? <Fallo texto="No pude leer las suscripciones." reintentar={() => void tab.reload()} /> : <Esqueleto filas={2} alto={40} />)
        : renuevan.length ? <ul className="pz-der-lista">{renuevan.map(s => <li key={s.nombre + s.moneda} className="pz-ren">
          <strong>{s.nombre}</strong>
          <span>{paraCancelar(s) && <span className="pz-tag pz-tag-vino">Para cancelar</span>}
            <small>{s.importe !== null ? eur(s.importe, s.moneda || 'EUR') : ''}{!paraCancelar(s) && s.importe !== null ? ' · ' : ''}{!paraCancelar(s) ? (s.dias === 0 ? 'hoy' : s.dias === 1 ? 'mañana' : diaSemana(s.proximaFecha)) : ''}</small></span></li>)}</ul>
          : <p className="pz-vacio">No renueva nada en los próximos 7 días.</p>}
    </section>}

    {g && <section aria-labelledby="pz-d-ga">
      <div className="pz-der-cab"><h2 id="pz-d-ga">Gasto de {mesDe(g.mes)}</h2><button type="button" className="pz-enlace" onClick={() => ctx.go('dinero')}>Detalle</button></div>
      <p className="pz-der-cifra">{eur(g.totalEur)}</p>
      {top && <p className="pz-der-sub">{top}</p>}
      {g.sinConvertir.length > 0 && <p className="pz-der-sub">Sin contar {g.sinConvertir.map(x => eur(x.importe, x.moneda)).join(' y ')} (otra moneda)</p>}
    </section>}

    {data?.avisos.ok && data.avisos.items.length > 0 && <section aria-labelledby="pz-d-av">
      <div className="pz-der-cab"><h2 id="pz-d-av">Avisos de Zazu</h2><button type="button" className="pz-enlace" onClick={() => ctx.go('zazu')}>{data.avisos.items.length > 3 ? `Ver los ${data.avisos.items.length}` : 'Abrir'}</button></div>
      <ul className="pz-der-lista">{data.avisos.items.slice(0, 3).map(a => <li key={a.id} className="pz-aviso-der"><button type="button" onClick={() => ctx.go('zazu')}>
        <strong>{a.titulo}</strong><small>{nombreFuente(a.fuente)}{a.chat ? ` · ${a.chat}` : ''} · {cuandoCorto(a.creado)}</small></button></li>)}</ul>
    </section>}
  </>
}

const FRASES = ['Recuérdame llamar al taller el jueves', 'Apunta en mis notas: ', '¿Cuánto he gastado este mes?', 'Enséñame el billete del tren']
const FRASES_INVITADA = ['¿Qué tengo mañana?', 'Ayúdame a escribir un mensaje: ', 'Dame una idea para cenar hoy', 'Explícame esto con palabras sencillas: ']
const ESTILOS: { perfil: string; texto: string }[] = [{ perfil: PERFIL_HERMES, texto: 'Rápido' }, { perfil: 'charla', texto: 'Charla' }, { perfil: 'escritor', texto: 'Escritor' }, { perfil: 'investigador', texto: 'Investigador' }]

/** «+ Nueva conversación», «Recientes», «Estilo de Zazu» y «Zazu tiene a mano». */
export function PanelChat({ ctx }: { ctx: Ctx }) {
  const { chat, guest, me } = ctx
  const recientes = chat.sessions.filter(s => s.source !== 'cron').slice(0, 8)
  const perfil = chat.cur.profile
  const nueva = (p: string) => { chat.newChat(p); irA({ tab: 'chat', perfil: esEstilo(p) ? p : undefined }) }
  const activo = (p: string) => perfil === p
  // una invitada: su asistente (su perfil), sin los estilos de Fran ni sus herramientas
  const asistente = ctx.nombre || 'Zazu'
  const frases = guest ? FRASES_INVITADA : FRASES
  const amano = guest ? [puede(me, 'calendario') && 'Tu agenda', puede(me, 'tareas') && 'Tus tareas', puede(me, 'correo') && 'Tu correo (solo leerlo)', 'Tus carpetas'].filter(Boolean) as string[] : null
  return <>
    <button type="button" className="pz-btn pz-btn-primario pz-btn-grande" onClick={() => nueva(guest ? me.profile || 'default' : esEstilo(perfil) ? perfil : PERFIL_HERMES)}><Icono n="plus" size={18} /> Nueva conversación</button>
    <section aria-labelledby="pz-c-re">
      <h2 className="pz-der-etq" id="pz-c-re">RECIENTES</h2>
      {recientes.length ? <ul className="pz-hist">{recientes.map(s => {
        const aqui = chat.cur.id === s.id && perfil === (s.profile || 'default')
        return <li key={`${s.profile}/${s.id}`}><button type="button" className={aqui ? 'on' : ''} aria-current={aqui ? 'true' : undefined}
          onClick={() => { void chat.open(s.id, s.profile, s.source); irA({ tab: 'chat', conv: s.id, pf: s.profile === 'default' ? undefined : s.profile }) }}>
          <span>{tituloSesion(s)}</span><small>{relTime(s.last * 1000)}</small></button></li>
      })}</ul> : <p className="pz-vacio">Todavía no hay conversaciones.</p>}
    </section>
    {!guest && <section aria-labelledby="pz-c-es">
      <h2 className="pz-der-etq" id="pz-c-es">ESTILO DE ZAZU</h2>
      <div className="pz-estilos" role="group" aria-labelledby="pz-c-es" aria-describedby="pz-c-es-n">
        {ESTILOS.map(e => <button key={e.perfil} type="button" aria-pressed={activo(e.perfil)} title={PROFILE_NAMES[e.perfil]} onClick={() => { if (!activo(e.perfil) || chat.cur.id) nueva(e.perfil) }}>{e.texto}</button>)}
      </div>
      <p className="pz-nota" id="pz-c-es-n">Cambiar de estilo empieza una conversación nueva.</p>
    </section>}
    <section aria-labelledby="pz-c-pr">
      <h2 className="pz-der-etq" id="pz-c-pr">PRUEBA A DECIRLE</h2>
      <ul className="pz-frases">{frases.map(f => <li key={f}><button type="button" onClick={() => { ctx.setDraft(f); requestAnimationFrame(() => { const a = document.querySelector<HTMLTextAreaElement>('.conv .composer textarea'); if (a) { a.focus(); a.setSelectionRange(f.length, f.length) } }) }}>{f}</button></li>)}</ul>
    </section>
    <section aria-labelledby="pz-c-ma">
      <h2 className="pz-der-etq" id="pz-c-ma">{asistente.toUpperCase()} TIENE A MANO</h2>
      <ul className="pz-amano">
        {amano ? amano.map(x => <li key={x}>{x}</li>)
          : <><li>Tu agenda y tus tareas</li><li>Tus gastos y suscripciones</li><li>Tus papeles y el Cerebro</li><li>Tu móvil y el servidor <span>(con tu permiso)</span></li></>}
      </ul>
    </section>
  </>
}
