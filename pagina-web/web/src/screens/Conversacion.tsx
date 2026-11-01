import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { Ctx } from '../ctx'
import { Icon } from '../icons'
import { hm, IA_PROPIA, irA, isoDay, nombreAsistente } from '../lib'
import type { Session } from '../lib'
import { esEstilo, PERFIL_HERMES } from '../tipos'
import type { ChatApi, Decision, Item, Rutina } from '../tipos'
import Composer from './Composer'
import EnVivo from '../chat/EnVivo'
import Saludo from '../chat/Saludo'
import { FilaAsistentes } from '../chat/Asistentes'
import Sugerencias from '../chat/Sugerencias'
import AvisosHoy from '../chat/AvisosHoy'
import Acciones from '../chat/Acciones'
import Rapidas, { extraerRapidas } from '../chat/Rapidas'
import BarraChat, { MenuHilo } from '../chat/BarraChat'
import HojaHistorial from '../chat/Historial'
import { ChipModelo } from '../chat/Modelos'
import { CaraContacto, nombreContacto, pistaContacto } from './Chats'
import { BotonMenu, Hoja, Icono } from '../panel/ui'
import { useMenu } from '../panel/datos'
import type { Me } from './Invitada'
import { tituloSesion } from './Sessions'
import { CabeceraTurno, MensajeTuyo, Pensando, RespuestaIA } from '../chat/Mensaje'
import '../conversacion.css'

type Fila = { it: Item; cabecera: boolean; hora?: string; acciones: boolean }
/** Cada respuesta empieza con su cabecera (logo y nombre de Zazu, o de la asistente de una invitada); las acciones van bajo su último mensaje,
 *  y en la última respuesta solo cuando ya ha terminado. */
function filas(items: Item[], pending: boolean): Fila[] {
  let enTurno = false
  return items.map((it, i) => {
    const deIA = it.kind === 'work' || it.role === 'assistant'
    let cabecera = false, hora: string | undefined
    if (deIA && !enTurno) {
      cabecera = true
      for (const x of items.slice(i)) { if (x.kind !== 'msg') continue; if (x.role === 'user') break; hora = x.time; break }
    }
    enTurno = deIA
    let acciones = false
    if (it.kind === 'msg' && it.role === 'assistant') {
      const sig = items.slice(i + 1).find(x => x.kind === 'msg')
      acciones = sig ? sig.role === 'user' : !pending
    }
    return { it, cabecera, hora, acciones }
  })
}

const sinPrisa = () => matchMedia('(prefers-reduced-motion: reduce)').matches

/** Lo que elegiste en la pregunta «¿seguimos o empiezas una nueva?», por conversación y solo en esta visita (sessionStorage). */
type Eleccion = 'seguir' | 'nueva'
const K_ELECCION = 'zazu:chat-eleccion'
const elecciones = (): Record<string, Eleccion> => { try { return JSON.parse(sessionStorage.getItem(K_ELECCION) || '{}') || {} } catch { return {} } }
const recordar = (sesion: string, e: Eleccion) => { try { sessionStorage.setItem(K_ELECCION, JSON.stringify({ ...elecciones(), [sesion]: e })) } catch { /* sin almacenamiento: se vuelve a preguntar */ } }
/** «hace 40 min», «hace 3 h», «ayer», «hace 5 días». */
function haceCuanto(desde: number): string {
  const s = Math.max(0, Date.now() / 1000 - desde)
  if (s < 3600) return `hace ${Math.max(1, Math.round(s / 60))} min`
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`
  const d = Math.round(s / 86400)
  return d <= 1 ? 'ayer' : `hace ${d} días`
}
/** A partir de cuántos mensajes (tuyos y suyos) una conversación es «larga». */
const LARGA = 40

/** El chat, con su barra de arriba. Fran: la conversación con Zazu (por dentro, el perfil «tecnico», con tarjetas de permiso).
 *  Invitada: su conversación con su asistente (su perfil). Sin conversación abierta se ve el saludo (la conversación vacía).
 *  El cuadro de escribir va fuera de la zona que se desplaza (con el teclado abierto se queda encima, interactive-widget=resizes-content);
 *  en escritorio, en el inicio, se centra bajo el saludo. */
export default function Conversacion(p: Ctx & { tab: 'inicio' | 'chat' }) {
  const { chat, guest, me, toast, go, draft, setDraft, tab } = p
  const nombre = nombreAsistente(guest, p.nombre)   // Fran: Zazu. Una invitada: el nombre de su asistente (por defecto Zazu)
  const perfil = chat.cur.profile
  const raiz = useRef<HTMLDivElement>(null)
  const [historial, setHistorial] = useState(false)

  const contacto = chat.contacto   // chat seguido (Zazu, WhatsApp o un asistente): cabecera propia, hilo con lo anterior encima
  const quien = contacto && !guest && contacto !== PERFIL_HERMES && contacto !== 'whatsapp' ? nombreContacto(contacto) : nombre   // las respuestas de Viajes van firmadas «Viajes»
  const vacio = tab !== 'chat' || (chat.cur.id === null && !chat.items.length && !chat.anteriores.length && !chat.rutinas.length && !chat.pending)

  /** Tarjetas y atajos: «enviar» manda ya (y pasa a la conversación); «rellenar» deja la frase empezada en el cuadro.
   *  Las de Fran van siempre a Zazu con todas sus herramientas y permisos, aunque estés en un estilo (Charla, Escritor…). */
  const enviar = (prompt: string, ctx?: string) => p.ask(prompt, { profile: guest ? perfil : undefined, ctx: guest ? undefined : ctx })
  const rellenar = (prompt: string) => {
    if (!guest && !chat.cur.id && chat.cur.profile !== PERFIL_HERMES) chat.newChat(PERFIL_HERMES)   // la frase empezada se enviará con todas las herramientas y permisos
    const t = draft.trim()
    setDraft(!t || t.toLowerCase().startsWith(prompt.trim().toLowerCase()) ? t || prompt : `${prompt}${t}`)
    requestAnimationFrame(() => { const a = raiz.current?.querySelector<HTMLTextAreaElement>('.composer textarea'); if (a) { a.focus(); a.setSelectionRange(a.value.length, a.value.length) } })
  }
  const abrir = (s: Session) => { void chat.open(s.id, s.profile, s.source); irA({ tab: 'chat', conv: s.id, pf: s.profile }) }
  const abrirDeLista = (s: Session) => irA({ tab: 'chat', conv: s.id, pf: s.profile === 'default' ? undefined : s.profile })   // Sessions ya la ha abierto
  /** Nueva conversación: la de siempre para una invitada (su perfil); Fran sigue en su estilo (Charla…) o, si no, en el chat normal. */
  const nueva = () => {
    const nuevo = guest ? me.profile || 'default' : esEstilo(chat.cur.profile) ? chat.cur.profile : PERFIL_HERMES
    chat.newChat(nuevo)
    // sin go(): aún vería la conversación de ahora; nuevo=1: en blanco de verdad (sin él, el chat vuelve al hilo seguido y reabre la última)
    irA({ tab: 'chat', perfil: !guest && esEstilo(nuevo) ? nuevo : undefined, nuevo: '1' })
  }

  // al volver a un chat tras más de 30 min sin actividad: «¿seguimos con la anterior o empiezas una nueva?», como «¿Restaurar páginas?» de Chrome
  const preg = tab === 'chat' ? chat.pregunta : null
  const recordada = preg ? elecciones()[preg.sesion] : undefined
  const ocupada = chat.pending || !!chat.vivo?.aprobacion   // con una respuesta en marcha o un permiso esperando, se enseña la conversación
  useEffect(() => {
    if (!preg) return
    if (ocupada || recordada === 'seguir') chat.cerrarPregunta()
    else if (recordada === 'nueva') nueva()
  }, [preg?.sesion, recordada, ocupada]) // eslint-disable-line react-hooks/exhaustive-deps
  const preguntando = !!preg && !ocupada
  const elegir = (e: Eleccion) => { if (!preg) return; recordar(preg.sesion, e); if (e === 'nueva') nueva(); else chat.cerrarPregunta() }
  const sesPreg = preg && chat.sessions.find(s => s.id === preg.sesion && (s.profile || 'default') === preg.profile)
  const tituloPreg = sesPreg ? tituloSesion(sesPreg) : preg?.titulo || 'tu última conversación'

  // conversación muy larga: aviso discreto encima del cuadro de escribir (se puede cerrar; vuelve en otra conversación)
  const [sinAvisoLarga, setSinAvisoLarga] = useState('')
  const nMensajes = chat.items.filter(i => i.kind === 'msg').length
  const kConv = `${chat.cur.profile}/${chat.cur.id}`
  const larga = tab === 'chat' && !!chat.cur.id && !chat.soloLectura && !preguntando && nMensajes > LARGA && sinAvisoLarga !== kConv

  // Inicio e hilo comparten la misma estructura: el cuadro de escribir no se vuelve a montar al pasar de uno a otro
  // (no pierde el foco ni lo que tenga a medias al enviar desde el inicio).
  const scroller = useRef<HTMLDivElement>(null)
  const abajo = useRef(true)   // estabas al final del hilo: lo nuevo te arrastra; si subiste a leer, no
  const alDesplazar = () => { const el = scroller.current; if (el && !vacio) abajo.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140 }
  useLayoutEffect(() => { if (vacio) scroller.current?.scrollTo({ top: 0 }) }, [vacio])   // el inicio empieza arriba (el hilo se coloca solo al final)
  // el teclado del móvil encoge la pantalla: el saludo vuelve a empezar arriba (si no, el logo queda asomando cortado bajo la barra)
  // (y en una conversación, si estabas al final, el final sigue a la vista: lo último no queda tapado por el cuadro de escribir)
  useEffect(() => {
    const el = scroller.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let alto = el.clientHeight
    const ro = new ResizeObserver(() => {
      const nuevo = el.clientHeight
      // como WhatsApp: lo que se veía justo encima del cuadro de escribir sigue viéndose (el hilo sube lo mismo que se encogió)
      if (nuevo < alto) { if (vacio) el.scrollTo({ top: 0 }); else el.scrollTop += alto - nuevo }
      alto = nuevo
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [vacio])

  const ses = chat.cur.id ? chat.sessions.find(s => s.id === chat.cur.id && (s.profile || 'default') === chat.cur.profile) : undefined
  const titulo = vacio ? `Chat con ${nombre}` : ses ? tituloSesion(ses) : 'Conversación'
  const antigua = !guest && !vacio && !!chat.cur.id && chat.cur.profile === 'default' && !chat.soloLectura   // una de las de antes: sin tarjetas de permiso

  // .conv-fran: el chat pintado con las fichas del marco de Zazu (desde «una sola app», para todos)
  return <div className={`conv ${vacio ? 'conv-inicio' : 'conv-hilo'} conv-fran`} ref={raiz}>
    {contacto
      ? <CabeceraContacto chat={chat} id={contacto} guest={!!guest} me={me} abrirModelos={p.abrirModelos} historial={() => setHistorial(true)} />
      : <BarraChat chat={chat} titulo={titulo} nueva={nueva} historial={() => setHistorial(true)} modelos={p.abrirModelos} asistentes={p.abrirAsistentes} />}
    <div className="conv-scroll" ref={scroller} onScroll={alDesplazar}>
      {vacio ? <div className="conv-col">
        {!guest && (!contacto || contacto === PERFIL_HERMES) && <AvisosHoy nombre={nombre} />}
        {guest && me.ia === false && (IA_PROPIA ? <button type="button" className="aviso-ia" onClick={() => go('ajustes')}>
          <strong><Icon name="lightbulb" size={17} /> Conecta tu IA para empezar</strong>
          <span>{nombre} funciona con tu propio ChatGPT o Claude. Tócame y conéctalo en un minuto.</span></button>
          : <div className="aviso-ia" role="status" style={{ cursor: 'default' }}>
            <strong><Icon name="clock" size={17} /> Tu {nombre} todavía no está activo</strong>
            <span>Fran lo activará pronto. Cuando esté listo, podrás hablarle aquí.</span></div>)}
        {/* el chat con Zazu (también el seguido) empieza con el saludo grande; los asistentes de un oficio y WhatsApp, con su presentación */}
        {contacto && contacto !== PERFIL_HERMES
          ? <PresentacionContacto id={contacto} profile={perfil} modo={chat.modo} guest={!!guest} me={me} />
          : <><Saludo me={me} guest={guest} perfil={perfil} />{!guest && !contacto && <FilaAsistentes chat={chat} />}</>}
        {(!contacto || contacto === PERFIL_HERMES || guest) && <Sugerencias guest={guest} me={me} sessions={chat.sessions} enviar={enviar} rellenar={rellenar} abrir={abrir} />}
      </div>
        : preg && preguntando ? <div className="conv-col">{!recordada && <div className="acc-card conv-pregunta" role="region" aria-labelledby="conv-pregunta-t">
          <p id="conv-pregunta-t">¿Seguimos con «<strong>{tituloPreg}</strong>» ({haceCuanto(preg.desde)}) o empiezas una nueva?</p>
          <div className="conv-pregunta-bot">
            <button type="button" className="btn-primary" onClick={() => elegir('nueva')} autoFocus><Icon name="plus" size={17} /> Nueva conversación</button>
            <button type="button" className="btn-secondary" onClick={() => elegir('seguir')}>Seguir con la anterior</button>
          </div>
        </div>}</div>
        : <Hilo {...p} nombre={quien} scroller={scroller} abajo={abajo} nueva={nueva} antigua={antigua} />}
    </div>
    {larga && <div className="conv-larga" role="note">
      <span>Esta conversación ya es larga. Empieza una nueva para que {quien} vaya más rápido y gaste menos.</span>
      <button type="button" className="btn-secondary" onClick={nueva}>Nueva conversación</button>
      <button type="button" className="conv-larga-x" onClick={() => setSinAvisoLarga(kConv)} aria-label="Cerrar el aviso">×</button>
    </div>}
    {!preguntando && <div className="conv-composer"><Composer chat={chat} draft={draft} setDraft={setDraft} toast={toast} onSent={() => { if (tab !== 'chat') go('chat') }} canAttach guest={!!guest}
      name={guest ? me.asistente : undefined} soloLectura={!vacio && chat.soloLectura} centrado={vacio}
      placeholder={contacto && !guest ? `Escribe a ${nombreCorto(nombreContacto(contacto))}…` : undefined} sinMas={!!contacto && contacto !== PERFIL_HERMES} /></div>}
    {historial && <HojaHistorial chat={chat} cerrar={() => setHistorial(false)} abrir={abrirDeLista} />}
  </div>
}

/** La conversación abierta: tus mensajes en burbuja a la derecha, las respuestas como prosa, pasos y lo que pasa en directo. */
function Hilo({ chat, guest, toast, nombre, scroller, abajo, nueva, antigua }: Ctx & { nombre: string; scroller: RefObject<HTMLDivElement | null>; abajo: RefObject<boolean>; nueva: () => void; antigua: boolean }) {
  const antes = useRef(0)
  const ses = chat.sessions.find(s => s.id === chat.cur.id && (s.profile || 'default') === chat.cur.profile)
  const vivo = chat.vivo
  const enDirecto = !!vivo && (!!vivo.texto || !!vivo.aprobacion || vivo.pasos.some(x => x.estado === 'en_curso'))
  // en un chat seguido, lo de las conversaciones anteriores va encima, y lo que el asistente te escribió por su cuenta, por fecha
  const lista = filas(conRutinas([...chat.anteriores, ...chat.items], chat.rutinas), chat.pending)

  const bajar = (suave: boolean) => { const el = scroller.current; if (el) el.scrollTo({ top: el.scrollHeight, behavior: suave && !sinPrisa() ? 'smooth' : 'auto' }) }
  useLayoutEffect(() => { abajo.current = true; antes.current = 0; bajar(false) }, [chat.cur.id, chat.cur.profile, chat.anteriores.length, chat.rutinas.length])
  useEffect(() => {
    const n = chat.items.length, primera = antes.current === 0 && n > 0
    antes.current = n
    if (primera) bajar(false); else if (abajo.current) bajar(true)
  }, [chat.items.length, vivo?.texto.length, vivo?.aprobacion?.id, vivo?.pasos.length, enDirecto]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (chat.pending) { abajo.current = true; bajar(true) } }, [chat.pending])   // acabas de enviar: al final
  let diaPrevio = ''
  const ultimoMsg = lista.map(f => f.it).reduce((u, it, i) => it.kind === 'msg' ? i : u, -1)   // solo la última respuesta ofrece respuestas rápidas
  const rapida = (o: string) => { chat.send(o).catch(e => toast(`No se pudo enviar: ${(e as Error).message}`)) }
  // en el móvil, las acciones de una respuesta (copiar, mandar, guardar) salen al mantenerla pulsada; en el ordenador, siempre
  const [conAcciones, setConAcciones] = useState<number | null>(null)
  const mantener = (id: number) => (e: { preventDefault(): void }) => { e.preventDefault(); setConAcciones(x => x === id ? null : id) }
  // y con un toque en la respuesta (no en un enlace, un botón o el código, ni si estás seleccionando texto)
  const tocar = (id: number) => (e: { target: EventTarget }) => {
    if (!matchMedia('(pointer: coarse)').matches || (e.target as HTMLElement).closest('a, button, summary, input, textarea, .md-codigo, .rapidas') || getSelection()?.toString()) return
    setConAcciones(x => x === id ? null : id)
  }
  const decidir = (d: Decision) => { chat.aprobar(d).catch(e => toast(`No se pudo responder al permiso: ${(e as Error).message}`)) }
  const reintentar = chat.soloLectura ? undefined : () => { if (!chat.pending) chat.reintentar().catch(e => toast(`No se pudo enviar: ${(e as Error).message}`)) }

  return <div className="conv-col">
    {guest
      ? <div className="hilo-barra">
        <h1 className="visually-hidden">{ses ? tituloSesion(ses) : `Conversación con ${nombre}`}</h1>
        <MenuHilo nueva={nueva} />
      </div>
      : <h1 className="visually-hidden">{ses ? tituloSesion(ses) : `Conversación con ${nombre}`}</h1>}
    {chat.soloLectura && <div className="wa-banner" role="note"><span className="wa-banner-ic"><Icon name="chat" size={18} /></span>
      <div><strong>Solo lectura</strong><small>Es lo que habláis por WhatsApp: para seguir, escríbele allí.</small></div></div>}
    {antigua && <div className="wa-banner" role="note"><span className="wa-banner-ic"><Icon name="clock" size={18} /></span>
      <div><strong>Es una conversación de antes</strong><small>Aquí {nombre} no puede pedirte permisos para lo delicado. Si lo necesitas, empieza una nueva.</small></div>
      <button type="button" className="btn-secondary" onClick={nueva}>Nueva</button></div>}
    <div className="hilo">
      {lista.map(({ it, cabecera, hora, acciones }, idx) => {
        const cab = cabecera && <CabeceraTurno nombre={nombre} time={hora} cara={chat.contacto ? <CaraContacto c={{ id: chat.contacto, profile: chat.cur.profile, modo: chat.modo }} tam={20} /> : undefined} />
        // separador de día (solo en el chat seguido, donde se juntan varias conversaciones)
        const dia = chat.contacto && it.kind === 'msg' && it.dia && it.dia !== diaPrevio ? <div className="hilo-dia">{etiquetaDia(it.dia)}</div> : null
        if (it.kind === 'msg' && it.dia) diaPrevio = it.dia
        if (it.kind === 'work') return dia || cab ? <Fragment key={`w${it.id}`}>{dia}{cab && <div className="turno-pasos">{cab}</div>}</Fragment> : null   // 2026-10-21: no se enseña la «cocina» (herramientas); solo «Pensando…» y la respuesta
        if (it.role === 'user') return <Fragment key={`m${it.id}`}>{dia}<MensajeTuyo text={it.text} time={it.time} /></Fragment>
        const r = extraerRapidas(it.text)
        const rapidas = idx === ultimoMsg && !chat.pending && !chat.soloLectura ? <Rapidas opciones={r.opciones} onElegir={rapida} /> : null
        if (it.rutina) return <Fragment key={`r${it.id}`}>{dia}<div className="turno-ia turno-rutina">{cab}<span className="hilo-etq">{it.rutina}</span><RespuestaIA text={r.texto} />{rapidas}{acciones && <Acciones texto={r.texto} guest={guest} toast={toast} />}</div></Fragment>
        const ultima = idx === ultimoMsg && !chat.pending
        return <Fragment key={`m${it.id}`}>{dia}<div className={`turno-ia ${conAcciones === it.id ? 'con-acciones' : ''} ${ultima ? 'ultima' : ''}`} onContextMenu={mantener(it.id)} onClick={tocar(it.id)}>{cab}<RespuestaIA text={r.texto} />{rapidas}{acciones && <Acciones texto={r.texto} guest={guest} toast={toast} repetir={ultima ? reintentar : undefined} />}</div></Fragment>
      })}
      {vivo && <EnVivo vivo={vivo} onDecidir={decidir} onReintentar={reintentar} />}
      {chat.pending && !vivo && <Pensando nombre={nombre} />}
    </div>
  </div>
}

/** Intercala por fecha lo que el asistente te escribió por su cuenta (sus rutinas y avisos) entre los mensajes del hilo. */
function conRutinas(items: Item[], rutinas: Rutina[]): Item[] {
  if (!rutinas.length) return items
  const extra = rutinas.map((r, i): Item => ({ kind: 'msg', id: -1_000_000 - i, role: 'assistant', text: r.texto, time: hm(r.ts), dia: isoDay(new Date(r.ts * 1000)), ts: r.ts, rutina: r.nombre || 'Rutina' }))
  const out: Item[] = []
  let j = 0
  for (const it of items) {
    const ts = it.kind === 'msg' ? it.ts : undefined
    while (j < extra.length && ts !== undefined && ((extra[j] as { ts?: number }).ts ?? 0) <= ts) out.push(extra[j++])
    out.push(it)
  }
  return out.concat(extra.slice(j))
}

/** «Hoy», «Ayer» o «lunes 12 de octubre» para los separadores del hilo. */
/** «Profe del teórico» no cabe en el hueco de escribir: con nombres largos, solo la primera palabra. */
const nombreCorto = (n: string) => n.length <= 14 ? n : n.split(' ')[0]

function etiquetaDia(iso: string): string {
  const hoy = new Date(), d = new Date(`${iso}T12:00:00`)
  const dias = Math.round((new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate()).getTime() - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 864e5)
  if (dias === 0) return 'Hoy'
  if (dias === 1) return 'Ayer'
  const t = d.toLocaleDateString('es', dias < 7 ? { weekday: 'long' } : { weekday: 'long', day: 'numeric', month: 'long' })
  return t[0].toUpperCase() + t.slice(1)
}

const InfoIcon = () => <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>

/** Cabecera del chat seguido: atrás (a Chats), la cara y el nombre del contacto, su pista y (i) con lo demás
 *  (modelo para Zazu, conversaciones anteriores, empezar de cero). Sin chips ni lápiz: un chat es solo mensajes. */
function CabeceraContacto({ chat, id, guest, me, abrirModelos, historial }: { chat: ChatApi; id: string; guest: boolean; me: Me; abrirModelos: () => void; historial: () => void }) {
  const [info, setInfo] = useState(false)
  const abrirMenu = useMenu()
  const nombre = nombreContacto(id, guest, me.asistente), pista = pistaContacto(id, guest, me.asistente)
  const c = { id, profile: chat.cur.profile, modo: chat.modo }
  const deCero = () => { setInfo(false); const p = chat.cur.profile; chat.newChat(p); irA({ tab: 'chat', perfil: !guest && esEstilo(p) ? p : undefined, nuevo: '1' }) }   // nuevo=1: sin él se reabriría la última
  return <div className={`cc-cab ${id === 'whatsapp' ? 'wa' : ''}`}>
    {/* en el móvil, el ☰ abre el menú (los chats, las secciones y las conversaciones recientes); en el ordenador, la flecha vuelve a Chats */}
    {abrirMenu ? <BotonMenu /> : <button type="button" className="cc-atras" onClick={() => irA({ tab: 'chats' })} aria-label="Volver a los chats"><Icono n="back" size={22} /></button>}
    <CaraContacto c={c} tam={40} />
    <span className="cc-txt"><span className="cc-nombre">{nombre}</span><span className="cc-pista">{chat.pending ? 'Respondiendo…' : pista}</span></span>
    {id !== 'whatsapp' && <button type="button" className="cc-info" onClick={deCero} aria-label="Nueva conversación" title="Nueva conversación"><Icono n="pen" size={21} /></button>}
    <button type="button" className="cc-info" onClick={() => setInfo(true)} aria-haspopup="dialog" aria-label={`Sobre ${nombre}`}><InfoIcon /></button>
    {info && <Hoja titulo={nombre} id="contacto" cerrar={() => setInfo(false)}><div className="cc-hoja">
      <div className="cc-hoja-cab"><CaraContacto c={c} tam={44} /><strong>{nombre}</strong></div>
      <p>{pista}</p>
      <p className="cc-hoja-pista">Mantén pulsada una respuesta para copiarla, mandarla a WhatsApp o guardarla.</p>
      {chat.modo === 'hermes' && <div className="cc-hoja-fila"><span>Modelo de esta conversación</span><ChipModelo chat={chat} onClick={() => { setInfo(false); abrirModelos() }} /></div>}
      {id !== 'whatsapp' && <button type="button" className="btn-secondary" onClick={() => { setInfo(false); historial() }}>Conversaciones anteriores</button>}
      {id !== 'whatsapp' && <button type="button" className="btn-secondary" onClick={deCero}>Empezar de cero</button>}
    </div></Hoja>}
  </div>
}

/** El chat seguido aún vacío: quién es y qué hace. */
function PresentacionContacto({ id, profile, modo, guest, me }: { id: string; profile: string; modo: 'hermes' | 'zazu'; guest: boolean; me: Me }) {
  return <div className="cc-presenta">
    <CaraContacto c={{ id, profile, modo }} tam={72} />
    <strong>{nombreContacto(id, guest, me.asistente)}</strong>
    <p>{pistaContacto(id, guest, me.asistente)}</p>
  </div>
}
