/* Marco de Zazu («cara fácil»). «Una sola app»: Fran y las invitadas usan este mismo marco; el menú, las pestañas del móvil y «Más» salen de
   las capacidades de cada uno (/api/me → lib.puede), así que una invitada solo ve (y solo abre) sus secciones.
   2026-10-22, al estilo de las apps de chat («de lectura»):
   Ordenador (≥ 900 px): sin barra de arriba. Menú de la izquierda con la marca y la campana, «Nuevo chat», «Buscar», las secciones, «Más» plegado,
   las conversaciones recientes y, abajo, tú (ajustes). La pantalla en el centro y, en la Agenda muy ancha (≥ 1100 px), un panel con lo que viene.
   Móvil (< 900 px): barra de arriba fina (☰, logo y título, buscar, avisos), la pantalla en una columna y la barra de pestañas de abajo
   (Zazu, Agenda, Noticias, Empleo, Todo), más fina. El ☰ y «Todo» abren el mismo cajón (el menú de la izquierda). En el chat no hay barra
   de arriba: la cabecera del chat lleva su ☰ y el título de la conversación. */
import { useEffect, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import { EN_APP, avisarCambio, irA, puede } from '../lib'
import type { Tab } from '../lib'
import type { Ctx } from '../ctx'
import { ANCHO_PANEL, useEscritorio, useMedia } from '../tema'
import { cargarPanel, cargarTableros, useCarga } from './api'
import type { Panel, Tablero } from './api'
import BarraOrden from './BarraOrden'
import Buscador from './Buscador'
import { CtxMenu, CtxPanel, CtxPanelDerecho, CtxTableros } from './datos'
import type { DatosPanel } from './datos'
import { organizarAgenda } from './acciones'
import { PanelInicio } from './Derecha'
import { Hoja, Icono, Marca, useTrampaFoco } from './ui'
import type { Ico } from './ui'
import { GatoIcono } from './GatoIcono'
import type { Gato } from './GatoIcono'
import { useTemaPz } from './tema'
import { PALETAS, usePaleta } from './paleta'
import { LogoZazu } from '../icons'
import { PERFIL_HERMES } from '../tipos'
import { tituloSesion } from '../screens/Sessions'
import './panel.css'
import './legado.css'   // las pantallas de siempre, repintadas con las fichas (generado)
import './cara.css'
import './lectura.css'   // 2026-10-22: el chat «de lectura» y el menú lateral / cajón (va el último: manda sobre lo anterior)

/** Pantallas que se pintan con el marco nuevo (el resto —Agenda, Tareas, Correo, WhatsApp, Carpetas, Rutinas, Ajustes…— se enseña dentro de él con su propio contenido). */
export const PESTANAS_PANEL: Tab[] = ['inicio', 'semana', 'noticias', 'zazu', 'empleo', 'dinero']
/** Las que necesitan los tableros del Cerebro (suscripciones, candidaturas…). */
const CON_TABLEROS: Tab[] = ['inicio', 'empleo', 'dinero']

type Entrada = { id: string; icono: Ico; gato?: Gato; texto: string; ir: () => void; activo?: boolean; cuenta?: number; urgente?: boolean }

type Props = {
  tab: Tab; nombre: string; titulo: string; mainRef: RefObject<HTMLElement | null>
  ctx: Ctx
  /** Algo que revisar del servidor (Zazu sin responder, alertas de infraestructura). */
  aviso: boolean
  toastEl: ReactNode
  /** Hojas que van por encima de todo (p. ej. la de modelos del chat). */
  hojas?: ReactNode
  children: ReactNode
}

export default function PanelShell(p: Props) {
  const { ctx, tab } = p
  const pu = (t: string) => puede(ctx.me, t)
  const asistente = ctx.nombre || 'Zazu'
  const escritorio = useEscritorio()
  const ancho = useMedia(ANCHO_PANEL)
  const enPanel = PESTANAS_PANEL.includes(tab)
  const cada = enPanel ? 60000 : 0   // en las otras pantallas basta una lectura (para los contadores)
  const fresco = useRef(false)
  const panel = useCarga<Panel>(() => { const f = fresco.current; fresco.current = false; return cargarPanel(f) }, 'panel', cada)
  const tableros = useCarga<Tablero[]>(CON_TABLEROS.includes(tab) && pu('tableros') ? () => cargarTableros() : null, 'tableros', 60000)
  const datos: DatosPanel = {
    data: panel.data, error: panel.error, loading: panel.loading,
    recargar: panel.reload,
    refrescar: async () => { fresco.current = true; await panel.reload() },   // tras una acción: salta las cachés del servidor
  }
  const [cajon, setCajon] = useState(false)
  useEffect(() => { if (escritorio) setCajon(false) }, [escritorio])
  useEffect(() => setCajon(false), [tab])   // al cambiar de pantalla, el cajón nunca se queda abierto encima
  // ¿teclado abierto? La ventana se encoge: si mide menos del 75 % de lo más alto que ha medido en esta orientación, lo está
  // (se compara con la propia ventana y no con la pantalla, que en un iPhone apaisado sigue midiendo como en vertical)
  const [teclado, setTeclado] = useState(false)
  useEffect(() => {
    if (escritorio) { setTeclado(false); return }
    let mayor = 0, orientacion = ''
    const mirar = () => {
      const o = window.screen?.orientation?.type || String(window.orientation ?? '')
      if (o !== orientacion) { orientacion = o; mayor = 0 }
      const alto = window.visualViewport?.height ?? window.innerHeight
      if (alto > mayor) mayor = alto
      // la ventana encogida Y un campo de texto con el cursor: solo así es el teclado (en pantalla dividida o con la ventana más pequeña, no)
      const el = document.activeElement as HTMLElement | null
      const escribiendo = !!el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable)
      setTeclado(escribiendo && alto < mayor * 0.75)
    }
    mirar(); addEventListener('resize', mirar); addEventListener('orientationchange', mirar); window.visualViewport?.addEventListener('resize', mirar); document.addEventListener('focusin', mirar); document.addEventListener('focusout', mirar)
    return () => { removeEventListener('resize', mirar); removeEventListener('orientationchange', mirar); window.visualViewport?.removeEventListener('resize', mirar); document.removeEventListener('focusin', mirar); document.removeEventListener('focusout', mirar) }
  }, [escritorio])
  const [buscar, setBuscar] = useState(false)

  const nAvisos = (panel.data?.avisos.ok ? panel.data.avisos.items.length : 0) + (panel.data?.capturas.ok ? panel.data.capturas.items.length : 0)   // avisos + propuestas por contestar
  const abre = (t: Tab) => () => ctx.go(t)
  // 2026-10-22 (Fran): Nuevo chat · Organizar mi agenda · Chats · Agenda · Noticias · Correo · Rutinas · … · Dinero y Empleo al final.
  // Iconos de línea (los gatos dibujados no se entendían). «Hoy y agenda» (la pantalla vieja del calendario) ya no sale: era la Agenda repetida.
  const todas: Entrada[] = [
    { id: 'chats', icono: 'chat', texto: 'Chats', ir: abre('chats'), activo: tab === 'chats' },
    { id: 'inicio', icono: 'calendar', texto: 'Agenda', ir: abre('inicio'), activo: tab === 'inicio' },
    { id: 'noticias', icono: 'file', texto: 'Noticias', ir: abre('noticias'), activo: tab === 'noticias' },
    { id: 'correo', icono: 'mail', texto: 'Correo', ir: abre('correo'), activo: tab === 'correo' },
    { id: 'rutinas', icono: 'repeat', texto: 'Rutinas', ir: abre('rutinas'), activo: tab === 'rutinas' },
    { id: 'carpetas', icono: 'folder', texto: ctx.guest ? 'Carpetas' : 'Mi nube', ir: abre('carpetas'), activo: tab === 'carpetas' },
    { id: 'semana', icono: 'list', texto: 'Semana', ir: abre('semana'), activo: tab === 'semana' },
    { id: 'dinero', icono: 'wallet', texto: 'Dinero', ir: abre('dinero'), activo: tab === 'dinero' },
    { id: 'empleo', icono: 'brief', texto: 'Empleo', ir: abre('empleo'), activo: tab === 'empleo' },
    { id: 'admin', icono: 'shield', texto: 'Administrador', ir: abre('admin'), activo: tab === 'admin' },   // solo Fran: los registros
  ]
  const principales = todas.filter(e => pu(e.id))
  const enMas = tab !== 'chat' && !principales.some(e => e.activo)
  // el chat seguido con Zazu (una invitada, con su asistente): la pestaña «Zazu» del móvil
  // 2026-10-23 (Fran): ya no abre el hilo que junta todas las conversaciones (parecía que arrastraba el contexto). Abre la de ahora si
  // hablaste hace menos de 30 min; si no, una NUEVA en blanco (con «Últimas conversaciones» debajo para seguir alguna).
  const escribir = () => {
    const pf = ctx.guest ? ctx.me.profile || 'default' : PERFIL_HERMES
    const ult = ctx.chat.sessions.filter(s => (s.profile || 'default') === pf && s.source !== 'cron' && s.source !== 'whatsapp').sort((a, b) => b.last - a.last)[0]
    if (ult && Date.now() / 1000 - ult.last < 1800) { void ctx.chat.open(ult.id, ult.profile, ult.source); irA({ tab: 'chat', conv: ult.id, pf: pf === 'default' ? undefined : pf }) }
    else { ctx.chat.newChat(pf); irA({ tab: 'chat', nuevo: '1' }) }
  }
  // la barra de Zazu, solo en la Agenda: «mañana dentista a las 10», «apunta: …», «recuérdame…» (Fran: el intérprete de órdenes; una invitada: su chat)
  const entrada = useRef<HTMLInputElement>(null)
  const barra = tab === 'inicio' && <div className="pz-barra-zona"><BarraOrden variante="compacta" texto={ctx.draft} setTexto={ctx.setDraft} toast={ctx.toast} inputRef={entrada}
    alCrear={() => { void datos.refrescar(); avisarCambio() }} abrirChat={t => { ctx.setDraft(''); ctx.ask(t, { fill: true }) }} preguntar={t => ctx.ask(t)}
    soloChat={!pu('tableros')} nombre={asistente} /></div>
  // 2026-10-22: el chat va sin panel derecho (las conversaciones están en el menú de la izquierda, como en las apps de chat); la Agenda lo conserva
  const derecha = ancho && escritorio && tab === 'inicio'
  // en el móvil, dentro del chat no hay barra de arriba: la cabecera del chat lleva el ☰ y el título de la conversación
  const sinTop = !escritorio && tab === 'chat'
  const campana = pu('zazu') && <button type="button" className="pz-top-btn" onClick={() => ctx.go('zazu')} aria-label={nAvisos ? `Avisos de Zazu: ${nAvisos}` : p.aviso ? 'Avisos de Zazu (hay algo que revisar)' : 'Avisos de Zazu'}>
    <Icono n="bell" size={20} />{nAvisos > 0 ? <b className="pz-insignia">{nAvisos > 9 ? '9+' : nAvisos}</b> : p.aviso ? <i className="pz-punto" aria-hidden="true" /> : null}
  </button>
  const lateral = (enCajon: boolean) => <Lateral ctx={ctx} principales={principales} enMas={enMas} nombre={p.nombre} asistente={asistente} enCajon={enCajon}
    cabecera={enCajon ? <button type="button" className="pz-top-btn" onClick={() => setCajon(false)} aria-label="Cerrar el menú"><Icono n="close" size={20} /></button> : campana}
    buscar={() => { setCajon(false); setBuscar(true) }} />
  const enTabs = tab === 'inicio' || tab === 'noticias' || tab === 'empleo' || tab === 'chats' || tab === 'chat' || (!!ctx.guest && tab === 'ajustes')   // las invitadas tienen «Tu espacio» abajo

  return <CtxPanel.Provider value={datos}><CtxTableros.Provider value={tableros}><CtxPanelDerecho.Provider value={derecha}><CtxMenu.Provider value={escritorio ? null : () => setCajon(true)}>
    <div className="pz pz-app" data-pantalla={tab} data-teclado={teclado ? '1' : undefined}>
      {!escritorio && !sinTop && <header className="pz-top">
        <button type="button" className="pz-top-btn pz-menu-btn" onClick={() => setCajon(true)} aria-label="Abrir el menú" aria-haspopup="dialog" aria-expanded={cajon}><MenuIco /></button>
        <button type="button" className="pz-top-tit" onClick={() => ctx.go('inicio')} aria-label={`${p.titulo}. Ir a la Agenda`}><LogoZazu tam={26} /><span>{p.titulo}</span></button>
        <span className="pz-top-sep" />
        <button type="button" className="pz-top-btn" onClick={() => setBuscar(true)} aria-label="Buscar" aria-haspopup="dialog"><Icono n="search" size={20} /></button>
        {campana}
      </header>}
      <div className="pz-cuerpo">
        {escritorio && <aside className="pz-lado" aria-label="Menú">{lateral(false)}</aside>}
        <div className="pz-col">
          {enPanel
            ? <main className="pz-main" ref={p.mainRef} id="pz-main">{p.children}</main>
            : tab === 'chat'
              ? <div className="main pz-legado pz-chat"><main className="app-content es-chat" ref={p.mainRef} id="pz-main"><div className="content-wrap">{p.children}</div></main></div>
              : <div className="main pz-legado"><main className="app-content" ref={p.mainRef} id="pz-main"><div className="content-wrap">{p.children}</div></main></div>}
          {barra}
        </div>
        {derecha && <aside className="pz-der" aria-label="Lo que viene"><PanelInicio ctx={ctx} /></aside>}
      </div>
      {!escritorio && <nav className="pz-tabs" aria-label="Secciones">
        {/* Se queda (Fran la usa a diario), más fina: Zazu, Agenda, Noticias, Empleo y «Todo», que abre el mismo cajón que el ☰. */}
        <TabMovil icono="chat" texto={ctx.guest ? 'Chats' : asistente} activo={tab === 'chats' || tab === 'chat'} onClick={ctx.guest ? () => ctx.go('chats') : escribir} />
        <TabMovil icono="calendar" texto="Agenda" activo={tab === 'inicio'} onClick={() => ctx.go('inicio')} />
        {pu('noticias') && <TabMovil icono="file" texto="Noticias" activo={tab === 'noticias'} onClick={() => ctx.go('noticias')} />}
        {pu('empleo') && <TabMovil icono="brief" texto="Empleo" activo={tab === 'empleo'} onClick={() => ctx.go('empleo')} />}
        {ctx.guest && <TabMovil icono="user" texto="Tu espacio" activo={tab === 'ajustes'} onClick={() => ctx.go('ajustes')} />}
        <button type="button" onClick={() => setCajon(true)} aria-haspopup="dialog" aria-current={enTabs ? undefined : 'page'} className="pz-tab"><span className="pz-tab-ico"><Icono n="more" size={22} /></span><span>Todo</span></button>
      </nav>}
      {cajon && <Cajon cerrar={() => setCajon(false)}>{lateral(true)}</Cajon>}
      {buscar && <Hoja titulo="Buscar" id="buscar" cerrar={() => setBuscar(false)}><Buscador ctx={ctx} panel={panel.data} tableros={tableros.data} enHoja alElegir={() => setBuscar(false)} /></Hoja>}
      {p.toastEl}
      {p.hojas}
    </div>
  </CtxMenu.Provider></CtxPanelDerecho.Provider></CtxTableros.Provider></CtxPanel.Provider>
}

const MenuIco = () => <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h10" /></svg>

/** El menú de la izquierda (ordenador) y el cajón del móvil, iguales: la marca, «Nuevo chat», buscar, las secciones, «Más» plegado,
 *  las conversaciones recientes y, abajo, tú (a «Tu espacio» y ajustes). Como en las apps de chat: lo de conversar arriba y a mano, lo demás sin estorbar. */
function Lateral({ ctx, principales, enMas, nombre, asistente, enCajon, cabecera, buscar }: { ctx: Ctx; principales: Entrada[]; enMas: boolean; nombre: string; asistente: string
  enCajon: boolean; cabecera: ReactNode; buscar: () => void }) {
  const { chat } = ctx
  // «Nuevo chat»: una conversación en blanco (con el saludo y las sugerencias), con todas las herramientas de Zazu (una invitada, con su asistente)
  const nuevo = () => { const pf = ctx.guest ? ctx.me.profile || 'default' : PERFIL_HERMES; chat.newChat(pf); irA({ tab: 'chat', nuevo: '1' }) }
  const recientes = chat.sessions.filter(s => s.source !== 'cron').slice(0, enCajon ? 12 : 20)
  const id = `pz-rec-${enCajon ? 'c' : 'l'}`
  return <div className={`pz-lateral ${enCajon ? 'en-cajon' : ''}`}>
    <div className="pz-lado-cab"><Marca onClick={() => ctx.go('inicio')} nombre={asistente} />{cabecera}</div>
    {/* Tu espacio, arriba del todo y a la vista (Fran, 2026-10-22): permisos, tu menú, tu cuenta */}
    <button type="button" className="pz-yo-arriba" onClick={() => ctx.go('ajustes')} aria-current={ctx.me && location.search.includes('tab=ajustes') ? 'page' : undefined}>
      <GatoIcono n="cara" size={34} /><span><strong>Tu espacio</strong><small>{nombre} · {ctx.guest ? 'permisos, menú y cuentas' : 'ajustes, permisos y cuentas'}</small></span><Icono n="chevron" size={18} /></button>
    <div className="pz-lado-acc">
      <button type="button" className="pz-nv pz-nuevo" onClick={nuevo}><span className="pz-nuevo-ico"><Icono n="plus" size={18} /></span><span>Nuevo chat</span></button>
      <button type="button" className="pz-nv" onClick={() => ctx.ask(organizarAgenda(!!ctx.guest), { nueva: true })}><Icono n="spark" size={20} /><span>Organizar mi agenda</span></button>
      {!enCajon && <button type="button" className="pz-nv" onClick={buscar} aria-haspopup="dialog"><Icono n="search" size={20} /><span>Buscar</span></button>}
    </div>
    <nav className="pz-lado-nav" aria-label="Secciones">
      {principales.map(e => <Enlace key={e.id} e={e} />)}
      <details className="pz-lado-mas" open={enMas || undefined}>
        <summary className="pz-nv"><Icono n="more" size={20} /><span>Más</span><Icono n="down" size={16} /></summary>
        <ItemsMas ctx={ctx} />
      </details>
    </nav>
    {recientes.length > 0 && <section className="pz-recientes" aria-labelledby={id}>
      <h2 className="pz-lado-etq" id={id}>Recientes</h2>
      <ul>{recientes.map(s => {
        const aqui = chat.cur.id === s.id && chat.cur.profile === (s.profile || 'default')
        return <li key={`${s.profile}/${s.id}`}><button type="button" className="pz-reciente" aria-current={aqui ? 'true' : undefined} title={tituloSesion(s)}
          onClick={() => { void chat.open(s.id, s.profile, s.source); irA({ tab: 'chat', conv: s.id, pf: s.profile === 'default' ? undefined : s.profile }) }}>
          <span>{tituloSesion(s)}</span>{s.busy && <i className="pz-reciente-vivo" role="img" aria-label="respondiendo" />}</button></li>
      })}</ul>
    </section>}
    <span className="pz-lado-resto" />
  </div>
}

/** Cajón del móvil: entra desde la izquierda. Como una hoja: Esc, tocar el velo y el Atrás del móvil lo cierran, el foco se queda dentro
 *  y vuelve al botón al cerrar. Elegir algo (sección, conversación, «Nuevo chat», ajustes) también lo cierra. */
function Cajon({ cerrar, children }: { cerrar: () => void; children: ReactNode }) {
  const { caja, teclas } = useTrampaFoco(cerrar, ['.pz-nuevo'], 'button:not([disabled]), summary, [href], input:not([disabled])', true)
  return <div className="pz-cajon-fondo" onMouseDown={e => { if (e.target === e.currentTarget) cerrar() }}>
    <div className="pz-cajon" role="dialog" aria-modal="true" aria-label="Menú" ref={caja} onKeyDown={teclas}
      onClick={e => { if ((e.target as HTMLElement).closest('.pz-nv:not(summary), .pz-mas-it, .pz-reciente, .pz-lado-yo, .pz-yo-arriba, .pz-marca')) cerrar() }}>{children}</div>
  </div>
}

function Enlace({ e }: { e: Entrada }) {
  return <button type="button" className="pz-nv" onClick={e.ir} aria-current={e.activo ? 'page' : undefined}>
    <Icono n={e.icono} size={22} /><span>{e.texto}</span>
    {!!e.cuenta && <span className={`pz-tag ${e.urgente ? 'pz-tag-vino' : 'pz-tag-gris'}`} aria-label={`${e.cuenta} ${e.urgente ? 'vencidas' : 'por revisar'}`}>{e.cuenta}</span>}
  </button>
}

function TabMovil({ icono, texto, activo, onClick }: { icono: Ico; texto: string; activo: boolean; onClick: () => void }) {
  return <button type="button" className="pz-tab" onClick={onClick} aria-current={activo ? 'page' : undefined}><span className="pz-tab-ico"><Icono n={icono} size={24} /></span><span>{texto}</span></button>
}

/** El panel de Hermes (dashboard) por internet: el servidor da un pase de un solo uso para hermes.holazazu.app (solo Fran). */
async function abrirPanelHermes() {
  try { const r = await fetch('/api/panel-hermes', { credentials: 'same-origin' }); const d = await r.json(); if (d.url) location.href = d.url } catch { /* sin red: no pasa nada */ }
}

/** Lo que cuelga de «Más»: el resto de pantallas, las listas extra, el registro, los ajustes y el tema. Lo comparten el menú del ordenador y la hoja del móvil. */
function ItemsMas({ ctx }: { ctx: Ctx }) {
  const [tema, setTema] = useTemaPz()
  const [paleta, setPaleta] = usePaleta()
  const g = (t: Tab) => () => ctx.go(t)
  type It = Omit<Entrada, 'id'> & { cap: string }
  // las secciones principales ya están en el menú y en el cajón; aquí, lo demás. Una invitada ve aquí sus tareas (Fran las tiene en la Agenda).
  const cada: It[] = ctx.guest ? [{ cap: 'tareas', icono: 'list', texto: 'Tareas', ir: g('tareas') }] : []
  const todos: { t: string; l: It[] }[] = [
    // también Fran: si se saltó un paso (Google, WhatsApp, permisos), la repite sin reiniciar nada
    { t: 'Tu espacio', l: [
      { cap: 'ajustes', icono: 'spark' as Ico, texto: ctx.guest ? 'Ver la guía otra vez (cómo te llamo, permisos, menú)' : 'Ver la guía otra vez (permisos, cuentas, menú)', ir: () => irA({ tab: 'ajustes', vista: 'guia' }) },
      { cap: 'ajustes', icono: 'shield' as Ico, texto: 'Tus permisos (ubicación, avisos, micrófono…)', ir: () => { ctx.go('ajustes'); setTimeout(() => document.getElementById('permisos')?.scrollIntoView({ behavior: 'smooth' }), 400) } }] },
    { t: ctx.nombre || 'Zazu', l: [{ cap: 'registro', icono: 'eye', gato: 'cara', texto: 'Qué ha hecho Zazu', ir: () => irA({ tab: 'zazu', vista: 'registro' }) }, ...(ctx.guest ? [] : [{ cap: 'sistema', icono: 'shield' as Ico, gato: 'ajustes' as Gato, texto: 'Panel de Hermes', ir: () => { void abrirPanelHermes() } }]), ...(EN_APP || ctx.guest ? [] : [{ cap: 'ajustes', icono: 'down' as Ico, texto: 'Bajar la app Android', ir: () => { location.href = '/zazu.apk' } }]), ...(ctx.guest ? [] : [{ cap: 'ajustes', icono: 'gear' as Ico, gato: 'ajustes' as Gato, texto: 'Ajustes', ir: g('ajustes') }])] },
    ...(cada.length ? [{ t: 'Cada día', l: cada }] : []),
    { t: 'Tus cosas', l: [{ cap: 'whatsapp', icono: 'chat', texto: 'WhatsApp', ir: g('whatsapp') }] },
  ]
  const grupos = todos.map(gr => ({ ...gr, l: gr.l.filter(e => puede(ctx.me, e.cap)) })).filter(gr => gr.l.length)
  return <div className="pz-mas">
    {grupos.map(gr => <section key={gr.t} aria-label={gr.t}>
      <h3 className="pz-mas-t">{gr.t}</h3>
      {gr.l.map(e => <button key={e.texto} type="button" className="pz-mas-it" onClick={e.ir}><Icono n={e.icono} size={20} /><span>{e.texto}</span></button>)}
    </section>)}
    <div className="pz-tema" role="group" aria-label="Tema de color">
      <button type="button" aria-pressed={tema === 'claro'} onClick={() => setTema('claro')}><Icono n="sun" size={16} /> Claro</button>
      <button type="button" aria-pressed={tema === 'oscuro'} onClick={() => setTema('oscuro')}><Icono n="moon" size={16} /> Oscuro</button>
    </div>
    <div className="pz-paletas" role="group" aria-label="Color de acento">
      {PALETAS.map(p => <button key={p.id} type="button" className="pz-paleta" aria-pressed={paleta === p.id} aria-label={p.nombre} title={p.nombre} onClick={() => setPaleta(p.id)} style={{ background: `hsl(${p.h} ${p.s}% 45%)` }} />)}
      <label className="pz-paleta pz-paleta-propia" title="Tu color" aria-label="Elegir tu propio color" data-on={paleta.startsWith('#') ? 'si' : 'no'}>
        <input type="color" value={paleta.startsWith('#') ? paleta : '#3b82c4'} onChange={e => setPaleta(e.target.value)} />
      </label>
    </div>
  </div>
}
