/* La barra de Zazu («cara fácil»): la misma entrada de siempre, en dos tamaños. GRANDE (Inicio): campo grande, adjuntar, foto, indicador «modo rápido», dictar y enviar,
   con cuatro frases de ejemplo encima. COMPACTA (el resto de pantallas): una línea. Es el intérprete rápido de órdenes («Apunta, recuérdame, crea una cita…»):
   SIN escribir nada antes de confirmar; primero sale una propuesta (hoja) y solo el botón de confirmar la ejecuta. Lo que no es una orden se abre en el chat con Zazu.
   `soloChat` (una invitada): no hay intérprete de órdenes (es de Fran, con sus cuentas); lo que escribe va como mensaje nuevo a su chat. */
import { useRef, useState } from 'react'
import type { RefObject } from 'react'
import { api, fmtSize, irA, post } from '../lib'
import { Entendiendo, HojasOrden, useOrden } from './Propuesta'
import { organizarAgenda } from './acciones'
import { Hoja, Icono } from './ui'

type Subido = { name: string; ruta: string | null }
const LIMITE = 100 * 1024 * 1024   // Cloudflare corta las subidas de más de 100 MB desde fuera de casa
type SR = { lang: string; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: (() => void) | null; onend: (() => void) | null; start(): void; stop(): void }
const dictado = (): (new () => SR) | null => { const w = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR }; return w.SpeechRecognition || w.webkitSpeechRecognition || null }

/** Frases de ejemplo de la barra grande. `enviar`: es una pregunta, va directa al chat con Zazu; `empezar`: se deja la frase empezada en la barra para completarla. */
const EJEMPLOS: { texto: string; enviar?: string; empezar?: string }[] = [
  { texto: '¿Qué tengo mañana?', enviar: '¿Qué tengo mañana en mi agenda? Dime las horas exactas y qué tengo que llevar.' },
  { texto: 'Apunta una tarea', empezar: 'Apunta una tarea: ' },
  { texto: 'Resumen de gastos', enviar: 'Hazme un resumen de mis gastos de este mes y de las suscripciones que renuevan pronto.' },
  { texto: 'Organizar mi agenda', enviar: organizarAgenda(false) },
]
const EJEMPLOS_CHAT: typeof EJEMPLOS = [
  { texto: '¿Qué tengo mañana?', enviar: '¿Qué tengo mañana en mi agenda? Dime las horas exactas.' },
  { texto: 'Escribir un mensaje', empezar: 'Ayúdame a escribir un mensaje: ' },
  { texto: 'Idea para cenar', enviar: 'Dame una idea fácil para cenar hoy.' },
]

type Props = {
  texto: string; setTexto: (t: string) => void; toast: (m: string) => void
  inputRef: RefObject<HTMLInputElement | null>
  /** Se creó algo de verdad: refrescar el panel. */
  alCrear: () => void
  /** «Abrir en el chat» con el texto ya puesto. */
  abrirChat: (texto: string) => void
  /** Una pregunta que va directa al chat con Zazu (las frases de ejemplo). */
  preguntar: (texto: string) => void
  variante?: 'grande' | 'compacta'
  /** Sin intérprete de órdenes: lo escrito va al chat (las invitadas). */
  soloChat?: boolean
  /** El nombre del asistente (Zazu, o el de la invitada). */
  nombre?: string
}

export default function BarraOrden({ texto, setTexto, toast, inputRef, alCrear, abrirChat, preguntar, variante = 'compacta', soloChat = false, nombre = 'Zazu' }: Props) {
  const o = useOrden({ toast, alApuntar: alCrear })
  const [escuchando, setEscuchando] = useState(false)
  const rec = useRef<SR | null>(null)
  const fichero = useRef<HTMLInputElement>(null)
  const camara = useRef<HTMLInputElement>(null)
  const [menu, setMenu] = useState(false)
  const [subiendo, setSubiendo] = useState(0)
  const [subidos, setSubidos] = useState<Subido[] | null>(null)
  const puedeDictar = typeof window !== 'undefined' && !!dictado()
  const grande = variante === 'grande'

  const enviar = () => {
    if (!soloChat) { void o.enviar(texto); return }
    const t = texto.trim()
    if (t) { setTexto(''); preguntar(t) }   // un mensaje nuevo en su chat
  }
  const ejemplos = soloChat ? EJEMPLOS_CHAT : EJEMPLOS
  async function subir(lista: FileList | null) {
    const fs = Array.from(lista || [])
    if (fichero.current) fichero.current.value = ''
    if (camara.current) camara.current.value = ''
    if (!fs.length) return
    const grandes = fs.filter(f => f.size > LIMITE)
    const ok = grandes.length && !confirm(`${grandes.map(f => `«${f.name}» (${fmtSize(f.size)})`).join(', ')} pesa más de 100 MB. Desde fuera de casa suele fallar la subida. ¿Lo intento igualmente?`) ? fs.filter(f => f.size <= LIMITE) : fs
    if (!ok.length) return
    try { await post('/api/mkdir', { path: '', name: 'Adjuntos' }) } catch { /* ya existe */ }
    const hechos: Subido[] = []
    for (const f of ok) {
      setSubiendo(n => n + 1)
      try {
        const r = await api<{ name: string; ruta?: string | null }>(`/api/upload?path=Adjuntos&name=${encodeURIComponent(f.name || 'archivo')}`, { method: 'POST', body: f })
        hechos.push({ name: r.name, ruta: r.ruta || null })
      } catch (e) { toast(`No se pudo subir ${f.name}: ${(e as Error).message}`) } finally { setSubiendo(n => n - 1) }
    }
    if (hechos.length) setSubidos(hechos)
  }
  const editar = () => { o.cerrar(); requestAnimationFrame(() => inputRef.current?.focus()) }

  function dictar() {
    if (rec.current) { rec.current.stop(); return }
    const C = dictado()
    if (!C) return
    const r = new C(); r.lang = 'es-ES'
    r.onresult = e => { const t = e.results[0][0].transcript; setTexto(`${texto}${texto && !texto.endsWith(' ') ? ' ' : ''}${t}`); inputRef.current?.focus() }
    r.onerror = () => toast('No pude oírte: revisa el permiso del micrófono')
    r.onend = () => { rec.current = null; setEscuchando(false) }
    rec.current = r; setEscuchando(true); r.start()
  }

  const campo = <>
    <label className="pz-oculto" htmlFor="pz-orden">{grande || soloChat ? `Escríbele a ${nombre}` : 'Dile a Zazu qué apuntar'}</label>
    <input id="pz-orden" ref={inputRef} value={texto} onChange={e => setTexto(e.target.value)} maxLength={500} autoComplete="off" enterKeyHint="send" disabled={o.fase?.k === 'pensando'}
      placeholder={soloChat ? `Escríbele a ${nombre}…` : grande ? 'Pregúntale a Zazu o dile qué apuntar…' : 'Apunta, recuérdame, pregunta…'} />
    <input ref={fichero} type="file" multiple className="pz-oculto" tabIndex={-1} aria-hidden="true" onChange={e => void subir(e.target.files)} />
    <input ref={camara} type="file" accept="image/*" capture="environment" className="pz-oculto" tabIndex={-1} aria-hidden="true" onChange={e => void subir(e.target.files)} />
  </>
  const dictarBtn = puedeDictar && <button type="button" className={`pz-barra-btn ${escuchando ? 'vivo' : ''}`} onClick={dictar} aria-label="Dictar" aria-pressed={escuchando}><Icono n="mic" size={22} /></button>
  const probar = (x: typeof EJEMPLOS[number]) => {
    if (x.enviar) { preguntar(x.enviar); return }
    setTexto(x.empezar || x.texto); requestAnimationFrame(() => { const e = inputRef.current; if (e) { e.focus(); e.setSelectionRange(e.value.length, e.value.length) } })
  }

  return <>
    <Entendiendo o={o} />
    {grande && <div className="pz-ejemplos" role="group" aria-label="Frases de ejemplo">{ejemplos.map(x => <button key={x.texto} type="button" onClick={() => probar(x)}>{x.texto}</button>)}</div>}
    {grande
      ? <form className="pz-barra pz-barra-grande" onSubmit={e => { e.preventDefault(); enviar() }} role="search" aria-label={`Escríbele a ${nombre}`}>
        {campo}
        <div className="pz-barra-pie">
          <button type="button" className="pz-barra-herr" disabled={subiendo > 0} onClick={() => fichero.current?.click()} aria-label="Adjuntar fotos o archivos" title="Adjuntar"><Icono n="plus" size={22} /></button>
          <button type="button" className="pz-barra-herr" disabled={subiendo > 0} onClick={() => camara.current?.click()} aria-label="Hacer una foto" title="Hacer una foto"><Icono n="cam" size={22} /></button>
          <span className="pz-barra-modo"><i aria-hidden="true" />{soloChat ? `${nombre} · a tu chat` : 'Zazu · modo rápido'}</span>
          <span className="pz-barra-sep" />
          {dictarBtn}
          <button type="submit" className="pz-barra-add" disabled={o.ocupado || !texto.trim()} aria-label={`Enviar a ${nombre}`}><Icono n="arrow" size={22} /></button>
        </div>
      </form>
      : <form className="pz-barra pz-barra-compacta" onSubmit={e => { e.preventDefault(); enviar() }} role="search" aria-label={soloChat ? `Escríbele a ${nombre}` : 'Órdenes para Zazu'}>
        {campo}
        {dictarBtn}
        {texto.trim()
          ? <button type="submit" className="pz-barra-add" disabled={o.ocupado} aria-label={soloChat ? `Enviar a ${nombre}` : 'Preparar la propuesta'}><Icono n="arrow" size={22} /></button>
          : <button type="button" className="pz-barra-add" disabled={subiendo > 0} onClick={() => setMenu(true)} aria-label={subiendo > 0 ? 'Subiendo archivos…' : 'Añadir: adjuntar, foto o escribir'} aria-haspopup="dialog"><Icono n="plus" size={22} /></button>}
      </form>}

    {menu && <Hoja titulo="¿Qué quieres añadir?" id="menu-mas" cerrar={() => setMenu(false)}>
      <div className="pz-opciones">
        <button type="button" className="pz-opcion" data-foco onClick={() => { fichero.current?.click(); setMenu(false) }}><span className="pz-op-ico"><Icono n="clip" size={18} /> Adjuntar fotos o archivos<small className="pz-opcion-est">Se guardan en Carpetas › Adjuntos</small></span></button>
        <button type="button" className="pz-opcion" onClick={() => { camara.current?.click(); setMenu(false) }}><span className="pz-op-ico"><Icono n="cam" size={18} /> Hacer una foto<small className="pz-opcion-est">Con la cámara del móvil</small></span></button>
        {puedeDictar && <button type="button" className="pz-opcion" onClick={() => { setMenu(false); dictar() }}><span className="pz-op-ico"><Icono n="mic" size={18} /> {soloChat ? 'Dictar un mensaje' : 'Dictar una orden'}<small className="pz-opcion-est">Hablas y {nombre} lo escribe</small></span></button>}
        <button type="button" className="pz-opcion" onClick={() => { setMenu(false); requestAnimationFrame(() => inputRef.current?.focus()) }}><span className="pz-op-ico"><Icono n="check" size={18} /> {soloChat ? 'Escribir un mensaje' : 'Escribir una orden'}<small className="pz-opcion-est">{soloChat ? `Va a tu chat con ${nombre}` : 'Apunta, recuérdame, crea una cita…'}</small></span></button>
      </div>
      <div className="pz-hoja-acc"><button type="button" className="pz-btn pz-btn-texto" onClick={() => setMenu(false)}>Cancelar</button></div>
    </Hoja>}

    {subiendo > 0 && <p className="pz-oculto" role="status">Subiendo {subiendo} archivo(s)…</p>}
    {subidos && <Hoja titulo={subidos.length === 1 ? 'Archivo guardado' : `${subidos.length} archivos guardados`} id="subido" cerrar={() => setSubidos(null)}>
      <p className="pz-hoja-texto">Lo he guardado en tus carpetas, en «Adjuntos». Si quieres que {nombre} lo lea o lo trabaje, díselo en el chat.</p>
      <ul className="pz-lista-archivos">{subidos.map(x => <li key={x.name}>{x.name}</li>)}</ul>
      <div className="pz-hoja-acc">
        <button type="button" className="pz-btn pz-btn-chat" data-foco onClick={() => { const n = subidos.map(x => `«${x.name}»`).join(', '); setSubidos(null); abrirChat(`Mira ${subidos.length === 1 ? 'el archivo' : 'los archivos'} ${n} que acabo de subir a Carpetas › Adjuntos y dime qué es.`) }}>Pedirle a {nombre} que lo mire <span className="pz-chat-flecha"><Icono n="arrow" size={15} /></span></button>
        <button type="button" className="pz-btn pz-btn-suave" onClick={() => { setSubidos(null); irA({ tab: 'carpetas', ruta: 'Adjuntos' }) }}>Ver en Carpetas</button>
        <button type="button" className="pz-btn pz-btn-texto" onClick={() => setSubidos(null)}>Listo</button>
      </div>
    </Hoja>}

    <HojasOrden o={o} texto={texto} editar={editar} limpiar={() => setTexto('')} abrirChat={abrirChat} />
  </>
}

