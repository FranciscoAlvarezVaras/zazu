import { useEffect, useRef, useState } from 'react'
import { PreguntaPreferencias, SeguirUbicacion } from './screens/Preferencias'
import { MenuUnaVez } from './screens/Bienvenida'
import PermisosInvitada from './chat/PermisosInvitada'
import type { ReactElement } from 'react'
import { BrandMark } from './icons'
import { useChat } from './chat'
import { AGENTE, deHermes, irA, leerParams, NAV, perfilDeUrl, puede, urlApp, useFetch, useParams } from './lib'
import type { Params, Status, Tab } from './lib'
import type { Ask, Ctx } from './ctx'
import { esEstilo, PERFIL_HERMES } from './tipos'
import { usePiel } from './tema'
import PanelShell from './panel/Shell'
import AvisoVersion from './panel/AvisoVersion'
import Agenda from './panel/Agenda'
import Empleo from './panel/Empleo'
import Dinero from './panel/Dinero'
import ZazuTab from './panel/ZazuTab'
import { useTemaPz } from './panel/tema'
import { HojaModelos } from './chat/Modelos'
import { HojaAsistentes } from './chat/Asistentes'
import Conversacion from './screens/Conversacion'
import Chats from './screens/Chats'
import Tareas from './screens/Tareas'
import Semana from './panel/Semana'
import Noticias from './panel/Noticias'
import MiDia from './screens/MiDia'
import Correo from './screens/Correo'
import WhatsApp from './screens/WhatsApp'
import Carpetas from './screens/Carpetas'
import Rutinas from './screens/Rutinas'
import Explorar from './screens/Explorar'
import Ajustes from './screens/Ajustes'
import Administrador from './panel/Administrador'
import Calendario from './screens/Calendario'
import CuentasScreen from './screens/CuentasScreen'
import { EspacioInvitada, PantallaRutinas } from './screens/Invitada'
import Bienvenida from './screens/Bienvenida'
import type { Me } from './screens/Invitada'

const TITLES: Record<Tab, string> = { inicio: 'Agenda', semana: 'Semana', noticias: 'Noticias', empleo: 'Empleo', dinero: 'Dinero', zazu: AGENTE, chat: 'Conversación', chats: 'Chats', tareas: 'Tareas', midia: 'Hoy', calendario: 'Calendario', cuentas: 'Cuentas', correo: 'Correos', whatsapp: 'WhatsApp', carpetas: 'Carpetas', rutinas: 'Rutinas', ajustes: 'Tu espacio', explorar: 'Explorar', admin: 'Administrador' }
/** Enlaces guardados de antes: ?tab=hermes (el modo Hermes) es ahora el chat con Zazu. ?tab=zazu es la pestaña de avisos de Zazu, y también vale ?tab=byte.
 *  La pantalla «Tableros» se retiró (2026-10): Empleo y Dinero son sus caras; ?tab=tableros vuelve a la Agenda. */
const ALIAS: Record<string, Tab> = { hoy: 'inicio', midia: 'inicio', asist: 'explorar', files: 'carpetas', stat: 'ajustes', hermes: 'chat', byte: 'zazu', tableros: 'inicio' }
const tabDe = (t = ''): Tab => ALIAS[t] || (t in TITLES ? (t as Tab) : 'inicio')
/** Errores y avisos importantes se quedan más tiempo en pantalla. */
const LARGO = /no se pudo|no pude|no se puede|error|fall[oóa]|caduc|no hay|no está|no deja|inténtalo|sin conexión/i
/** Conversación que pide la URL (`conv` + `pf`) como una sola clave: '' si no hay. */
const convDe = (p: Params = leerParams()) => p.conv ? JSON.stringify([p.pf || 'default', p.conv]) : ''
/** En la URL, el perfil «default» no se escribe. */
const pfUrl = (perfil: string) => perfil === 'default' ? undefined : perfil

// enlace directo que se abrió sin sesión: al volver del login se recupera (lo guarda lib.aLogin)
try {
  const v = JSON.parse(localStorage.getItem('zazu:volver') || 'null') as { u?: string; t?: number } | null
  localStorage.removeItem('zazu:volver')
  if (v?.u?.startsWith('/?') && Date.now() - (v.t || 0) < 3600e3 && !location.search) history.replaceState(null, '', v.u)
} catch { /* sin almacenamiento */ }

function initialTab(): Tab {
  const q = new URLSearchParams(location.search)
  // ?nuevo=1 (y ?perfil=): conversación nueva, en el chat
  if (q.has('nuevo')) return 'chat'
  // lo compartido desde el móvil (Compartir › Zazu) se abre en el chat, con el texto empezado en el cuadro de escribir
  if (['title', 'text', 'url'].some(k => q.has(k))) return 'chat'
  return tabDe(q.get('tab') || '')   // ?tab=chat y ?tab=hermes sin conversación: el chat nuevo
}
/** Borrador del chat por conversación: iOS recarga la app en segundo plano y lo que tenías a medias se perdía. */
const claveBorrador = (c: { id: string | null; profile: string }) => `zazu:borrador:${c.id ? `${c.profile}/${c.id}` : 'nueva'}`
const leerBorrador = (k: string) => { try { return localStorage.getItem(k) || '' } catch { return '' } }
const guardarBorrador = (k: string, t: string) => { try { if (t.trim()) localStorage.setItem(k, t); else localStorage.removeItem(k) } catch { /* sin almacenamiento */ } }

export default function App() {
  const chat = useChat()
  const [tab, setTab] = useState<Tab>(initialTab)
  const [conv, setConv] = useState(() => convDe())
  const [drafts, setDrafts] = useState({ barra: '', chat: '' })   // lo de la barra de Mi día no se cuela en el cuadro del chat (ni al revés)
  const [aviso, setAviso] = useState<{ m: string; n: number } | null>(null)
  const [verModelos, setVerModelos] = useState(false)
  const [verAsistentes, setVerAsistentes] = useState(false)
  const setMsg = (m: string) => setAviso(a => ({ m, n: (a?.n || 0) + 1 }))
  const compartido = useRef('')
  // lo compartido desde el móvil llega con el texto empezado: ese chat se abre sin preguntar «¿seguimos o empiezas una nueva?»
  const sinPregunta = useRef(['title', 'text', 'url'].some(k => new URLSearchParams(location.search).has(k)))
  const main = useRef<HTMLElement>(null)
  const tabRef = useRef(tab)
  const meF = useFetch<Me>('/api/me')
  const me = meF.data
  const guest = me?.role === 'guest'
  const msg = aviso ? (guest ? aviso.m : deHermes(aviso.m)) : ''   // a Fran, lo que llegue del servidor nombrando a «Hermes» se le muestra como Zazu
  const base = guest ? me?.profile || 'default' : 'default'   // perfil de una conversación nueva de una invitada
  const sistema = !!me && puede(me, 'sistema')   // estado del servidor y alertas: solo quien lo administra
  const [temaPz] = useTemaPz()
  const status = useFetch<Status>(sistema ? '/api/status' : null, 30000)
  const up = status.data ? status.data.gateway === 'running' : null
  const alertas = useFetch<{ activas: unknown[]; ultima: number | null }>(sistema ? '/api/alertas' : null, 60000)
  const hayAlertas = !!alertas.data && (alertas.data.activas.length > 0 || !alertas.data.ultima || Date.now() / 1000 - alertas.data.ultima > 15 * 60)

  // «una sola app»: todos dentro del marco de Zazu (Inicio, Chat, menú…); cada uno ve las secciones de sus capacidades
  usePiel(true, temaPz)
  // dos cuadros de escribir: el de la barra de Zazu (Inicio y demás pantallas) y el del chat
  const clave = (t: Tab) => t === 'chat' ? 'chat' as const : 'barra' as const
  const draft = drafts[clave(tab)]
  const setDraftDe = (k: 'barra' | 'chat', t: string) => setDrafts(d => d[k] === t ? d : { ...d, [k]: t })
  const setDraft = (t: string) => setDraftDe(clave(tab), t)

  // al cambiar de conversación, el cuadro del chat enseña lo que tenías a medias en ella
  const kBorrador = claveBorrador(chat.cur)
  const kAntes = useRef<string | null>(null)
  const montado = useRef(false)
  useEffect(() => {
    const k1 = kAntes.current
    if (k1 === kBorrador) return
    if (k1 === null && !chat.cur.id && convDe()) return   // recarga con una conversación en la URL: se espera a que se abra
    kAntes.current = kBorrador
    const t = drafts.chat
    if (k1 === null || !t) { if (!t) setDraftDe('chat', leerBorrador(kBorrador)); return }
    if (k1 === claveBorrador({ id: null, profile: '' })) { guardarBorrador(kBorrador, t); guardarBorrador(k1, ''); return }   // lo de una conversación nueva sigue en ella cuando ya tiene número
    if (t === leerBorrador(k1)) setDraftDe('chat', leerBorrador(kBorrador))   // era el borrador de la otra: se queda guardado allí
  }, [kBorrador]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!montado.current) { montado.current = true; return }
    if (kAntes.current === kBorrador) guardarBorrador(kBorrador, drafts.chat)   // al enviar se vacía, y se borra
  }, [drafts.chat]) // eslint-disable-line react-hooks/exhaustive-deps

  const toast = (m: string) => setMsg(m)
  // vuelta desde la caché del navegador (Atrás tras ir a Google y terminar la guía): /api/me puede haber cambiado (onboarded)
  const recargarMe = useRef(meF.reload); recargarMe.current = meF.reload
  useEffect(() => {
    const f = (e: PageTransitionEvent) => { if (e.persisted) void recargarMe.current() }
    addEventListener('pageshow', f); return () => removeEventListener('pageshow', f)
  }, [])
  useEffect(() => { if (!aviso) return; const t = setTimeout(() => setAviso(null), LARGO.test(aviso.m) ? 8000 : 3500); return () => clearTimeout(t) }, [aviso])
  useEffect(() => { if (chat.error) { setMsg(chat.error); chat.clearError() } }, [chat.error]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (chat.info) { setMsg(chat.info); chat.clearInfo() } }, [chat.info]) // eslint-disable-line react-hooks/exhaustive-deps

  // entrada por enlace: ?nuevo=1 &perfil=charla &title/text/url (compartir desde el móvil); ?tab=chat&perfil=charla: el chat en ese estilo al recargar
  useEffect(() => {
    const q = new URLSearchParams(location.search)
    const share = ['title', 'text', 'url'].map(k => q.get(k)).filter(Boolean).join('\n')
    const perfilNuevo = q.get('perfil') || 'default'
    // el chat de Fran (con todas las herramientas) lo abre el efecto del chat cuando ya se sabe quién eres; aquí, solo un estilo pedido (Charla…)
    if ((q.has('nuevo') || q.has('perfil')) && tabRef.current === 'chat' && esEstilo(perfilNuevo)) chat.newChat(perfilNuevo)
    compartido.current = share   // el texto compartido va al cuadro del chat cuando se sabe quién eres
    const avisos = { 'ok=google': 'Cuenta de Google conectada', 'e=google': 'Google no completó el permiso. Inténtalo otra vez.', 'e=guardar': 'Google dio permiso, pero algo falló al guardarlo. Inténtalo otra vez.', 'e=google_no': 'Google no dio permiso: o se canceló, o esa cuenta no deja conectar apps (pasa en cuentas de empresa o colegio).', 'e=nivel': 'Tu acceso no incluye Google. Si lo necesitas, díselo a Fran.', 'e=caducado': 'La conexión con Google caducó o ya se había usado. Vuelve a tocar el botón de conectar tu Google y termínalo de seguido, sin cerrar la pantalla de Google.' } as Record<string, string>
    for (const [k, m] of Object.entries(avisos)) { const [n, v] = k.split('='); if (q.get(n) === v) setMsg(m) }   // exacto: e=google no debe coincidir con e=google_no
    // se limpia la URL, pero se conservan pestaña, carpeta, archivo y conversación; el #fragmento (p. ej. #aprobar=) se deja para quien lo lea
    const url = urlApp({ ...leerParams(), tab: tabRef.current, perfil: tabRef.current === 'chat' && !leerParams().conv ? perfilDeUrl() || undefined : undefined })
    if (url !== location.pathname + location.search) history.replaceState(history.state, '', url + location.hash)   // sin perder la marca de la guía (el Atrás del móvil la usa)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Atrás/Adelante y enlaces internos: la pestaña y la conversación salen de la URL
  useEffect(() => {
    const f = () => {
      const p = leerParams()
      setConv(convDe(p))
      const t = tabDe(p.tab)
      if (t === tabRef.current) return
      tabRef.current = t; setTab(t); main.current?.scrollTo({ top: 0 })
      requestAnimationFrame(() => { const h = main.current?.querySelector<HTMLElement>('h1, h2'); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }) } })   // lectores de pantalla: anunciar la pantalla nueva
    }
    addEventListener(NAV, f)
    // enlaces de las respuestas (Carpetas › …, rutas, MEDIA:, conversaciones) se abren dentro de la app
    const clic = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest?.('a[data-nav]') as HTMLAnchorElement | null
      if (!a) return
      const u = new URL(a.href, location.href)
      if (u.origin !== location.origin) return
      e.preventDefault()
      const g = (k: string) => u.searchParams.get(k) || undefined
      irA({ tab: g('tab') || 'inicio', root: g('root'), ruta: g('ruta'), archivo: g('archivo'), recibido: g('recibido'), conv: g('conv'), pf: g('pf'), perfil: g('perfil'), contacto: g('contacto'), tablero: g('tablero'), vista: g('vista'), tarjeta: g('tarjeta') })
    }
    document.addEventListener('click', clic)
    return () => { removeEventListener(NAV, f); document.removeEventListener('click', clic) }
  }, [])

  // lo compartido desde el móvil (?title=&text=&url=) va al cuadro de escribir del chat en cuanto se sabe quién eres
  useEffect(() => {
    if (!me || !compartido.current) return
    setDraftDe('chat', compartido.current); compartido.current = ''
  }, [!!me]) // eslint-disable-line react-hooks/exhaustive-deps

  // el chat sin conversación pedida en la URL es una conversación nueva. Fran: con Zazu (por dentro, el perfil «tecnico», con tarjetas
  // de permiso; ?perfil=charla la abre en ese estilo). Una invitada: con su asistente (su perfil). Una conversación ya abierta no se toca.
  useEffect(() => {
    if (!me || tab !== 'chat' || conv || leerParams().contacto) return
    const quiere = guest ? base : perfilDeUrl() || PERFIL_HERMES
    // el chat «a secas» (enlace antiguo, ?perfil=charla…) es el chat seguido con ese contacto: Zazu, o el asistente pedido
    // ?nuevo=1 («Nuevo chat» del menú, el atajo «Nueva conversación»): una conversación en blanco de verdad, con el saludo, sin ir al hilo seguido
    if (quiere !== 'default' && chat.cur.id === null && !chat.pending && !leerParams().nuevo) { irA({ tab: 'chat', contacto: quiere }, true); return }
    if (chat.cur.id === null && chat.cur.profile !== quiere) chat.newChat(quiere)
  }, [tab, conv, guest, !!me, chat.cur.id, chat.cur.profile]) // eslint-disable-line react-hooks/exhaustive-deps

  // ?tab=chat&contacto=viajes: el chat seguido con ese contacto (su última conversación, con las anteriores encima).
  // Entrar así (pestaña, lista de chats, abrir la app) pregunta antes si la última lleva más de 30 min parada; un enlace con conv no pregunta.
  const params = useParams()
  useEffect(() => {
    if (!me || tab !== 'chat' || !params.contacto) return
    const preguntar = !sinPregunta.current && !location.hash.startsWith('#aprobar=')
    sinPregunta.current = false
    chat.abrirContacto(params.contacto, { preguntar }).catch(e => toast(`No se pudo abrir el chat: ${(e as Error).message}`))
  }, [tab, !!me, params.contacto]) // eslint-disable-line react-hooks/exhaustive-deps

  // URL → conversación: ?tab=chat&conv=…&pf=… (recarga, Atrás/Adelante, enlaces, notificaciones)
  useEffect(() => {
    if (tab !== 'chat' || !conv) return
    const [pf, id] = JSON.parse(conv) as [string, string]
    if (chat.cur.id === id && chat.cur.profile === pf) return
    void chat.open(id, pf)   // si falla, lo avisa el propio chat (y vuelve a lo de antes)
  }, [tab, conv]) // eslint-disable-line react-hooks/exhaustive-deps

  // conversación → URL: en cuanto una conversación nueva tiene id, o se abre otra, la URL la nombra
  useEffect(() => {
    const c = chat.cur
    if (!c.id || chat.contacto) return   // en un chat seguido la URL nombra al contacto, no la conversación
    const p = leerParams()
    if (p.conv === c.id && (p.pf || 'default') === c.profile) return
    const destino = { tab: 'chat', conv: c.id, pf: pfUrl(c.profile) }
    if (tabRef.current === 'chat') irA(destino, true)   // misma entrada del historial
  }, [chat.cur.id, chat.cur.profile]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { document.title = guest ? me?.asistente || 'Zazu' : AGENTE }, [guest, me?.asistente])
  // una sección que esta persona no tiene (enlace guardado, URL escrita a mano) no se abre: va a Inicio
  useEffect(() => { if (me && !puede(me, tab)) irA({ tab: 'inicio' }, true) }, [me, tab])

  // su sección favorita (Tu espacio › Tu menú): al abrir la app sin enlace concreto, va ahí primero (una vez por visita)
  useEffect(() => {
    if (!me || me.role !== 'guest' || !me.portada || me.portada === 'inicio' || location.search.includes('tab=') || location.search.includes('nuevo')) return
    try { if (sessionStorage.getItem('hz-portada')) return; sessionStorage.setItem('hz-portada', '1') } catch { /* sin almacenamiento */ }
    if (puede(me, me.portada)) go(me.portada as Tab)
  }, [!!me]) // eslint-disable-line react-hooks/exhaustive-deps
  const go = (t: Tab) => {
    const d: Tab = !me || !puede(me, t) ? 'inicio' : t === 'midia' ? 'inicio' : t   // «Hoy» de antes es Mi día
    // a la conversación: el chat seguido o la que está abierta (sin conv la URL la perdería y Atrás no volvería a ella)
    if (d === 'chat' && chat.contacto) irA({ tab: 'chat', contacto: chat.contacto })
    else if (d === 'chat' && chat.cur.id) irA({ tab: 'chat', conv: chat.cur.id, pf: pfUrl(chat.cur.profile) })
    else irA({ tab: d })   // deja rastro: el Atrás del móvil vuelve aquí
  }
  /** Una petición desde cualquier pantalla va al chat seguido con Zazu (Fran: el perfil «tecnico», con tarjetas de permiso; una invitada: su asistente). */
  const ask: Ask = (prompt, o) => {
    const perfil = o?.profile || (guest ? base : PERFIL_HERMES)
    const contacto = perfil === 'default' ? null : perfil
    const fallo = (e: unknown) => toast(`No se pudo enviar: ${(e as Error).message}`)
    if (o?.fill) {   // frase empezada: en el cuadro del chat, para completarla
      // abrirlo aquí (y no solo con la URL) evita la pregunta «¿seguimos o empiezas una nueva?»: vas a completar la frase
      if (contacto) { irA({ tab: 'chat', contacto }); chat.abrirContacto(contacto).catch(fallo) } else { chat.newChat(perfil); irA({ tab: 'chat' }) }
      setDraftDe('chat', prompt); return
    }
    if (o?.nueva) { chat.newChat(perfil); irA({ tab: 'chat', nuevo: '1' }); chat.send(prompt, o?.ctx).catch(fallo); return }   // en una conversación aparte
    if (contacto) { irA({ tab: 'chat', contacto }); chat.abrirContacto(contacto).then(() => chat.send(prompt, o?.ctx)).catch(fallo) }
    else { chat.newChat(perfil); irA({ tab: 'chat' }); chat.send(prompt, o?.ctx).catch(fallo) }
  }
  const abrirModelos = () => { if (!guest) setVerModelos(true) }
  const abrirAsistentes = () => { if (!guest) setVerAsistentes(true) }

  const toastEl = <div className="toast-live" role="status" aria-live="polite">{msg && <div className={`toast ${LARGO.test(msg) ? 'toast-error' : ''}`} onClick={() => setAviso(null)}>{msg}</div>}</div>
  if (!me) return <div className="boot">{meF.error ? <><p>No se pudo cargar. Revisa tu conexión.</p><button className="btn-primary" onClick={() => void meF.reload()}>Reintentar</button></> : <BrandMark />}</div>
  // en su capa con scroll propio: en el móvil html y body están fijos (theme.css) y la guía, más alta que la pantalla, no se movería
  if (!me.demo && !me.onboarded) return <><div className="onb-capa"><Bienvenida me={me} toast={toast} done={() => void meF.reload()} /></div>{toastEl}</>   // también Fran, si reinicia su perfil

  const ctx: Ctx = { go, ask, toast, chat, draft, setDraft, nombre: guest ? me.asistente : undefined, guest, me, abrirModelos, abrirAsistentes }
  const screens: Record<Tab, ReactElement> = {
    inicio: <Agenda {...ctx} />, semana: <Semana {...ctx} />, noticias: <Noticias {...ctx} />, empleo: <Empleo {...ctx} />, dinero: <Dinero {...ctx} />, zazu: <ZazuTab {...ctx} />, chat: <Conversacion {...ctx} tab="chat" />, chats: <Chats {...ctx} />, tareas: <Tareas {...ctx} />, midia: <MiDia {...ctx} />, correo: <Correo {...ctx} />,
    whatsapp: <WhatsApp {...ctx} />, carpetas: <Carpetas {...ctx} />, explorar: <Explorar {...ctx} />, calendario: <Calendario {...ctx} />, cuentas: <CuentasScreen {...ctx} />,
    // lo de una invitada: sus rutinas (texto, sin scripts) y sus ajustes (su IA, sus canales, su Zazu y cerrar sesión), dentro del mismo marco
    rutinas: guest ? <PantallaRutinas {...ctx} /> : <Rutinas {...ctx} />,
    ajustes: guest ? <EspacioInvitada {...ctx} onSaved={() => void meF.reload()} /> : <Ajustes {...ctx} />,
    admin: <Administrador {...ctx} />,   // solo Fran (capacidad «admin»): los registros de la app, Zazu y los invitados
  }
  const visible: Tab = puede(me, tab) ? tab : 'inicio'

  return <><AvisoVersion /><PanelShell tab={visible} nombre={me.name || me.user || 'Fran'} titulo={visible === 'zazu' ? 'Avisos' : visible === 'carpetas' && !guest ? 'Mi nube' : TITLES[visible]} mainRef={main} ctx={ctx}
    aviso={hayAlertas || up === false} toastEl={toastEl}
    hojas={<><HojaModelos abierto={verModelos} cerrar={() => setVerModelos(false)} chat={chat} /><HojaAsistentes abierto={verAsistentes} cerrar={() => setVerAsistentes(false)} chat={chat} /></>}>{screens[visible]}</PanelShell>
    {guest && me.nivel !== 'invitada' && <PermisosInvitada nombre={me.asistente || 'Zazu'} toast={toast} />}
    {!me.demo && !me.prefs?.preguntado && <PreguntaPreferencias nombre={me.name || 'Fran'} asistente={me.asistente || 'Zazu'} toast={toast} done={() => void meF.reload()} />}
    {!me.demo && me.prefs?.preguntado && <MenuUnaVez me={me} />}
    {guest && !me.demo && me.prefs?.auto && <SeguirUbicacion prefs={me.prefs} asistente={me.asistente || 'Zazu'} toast={toast} cambio={() => void meF.reload()} />}
    {me.demo && <div role="note" style={{ position: 'fixed', left: 0, right: 0, top: 0, zIndex: 70, background: '#1f3b2d', color: '#fff', fontSize: 14, padding: '8px 16px', textAlign: 'center' }}>
      Estás viendo una <strong>demo con datos inventados</strong>: aquí solo se mira. <a href="/#lista-espera" style={{ color: '#ffd98a', fontWeight: 600 }}>Pide tu invitación</a></div>}</>
}
