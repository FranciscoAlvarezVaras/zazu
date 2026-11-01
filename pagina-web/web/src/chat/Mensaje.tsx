import { useLayoutEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { Icon, LogoZazu } from '../icons'
import { abrirEnCarpetas, md, rutaApp, urlDescarga } from '../lib'
import { copiar } from './Acciones'
import Indicador from './Indicador'

type Adj = { name: string; imagen: boolean; root?: string; path?: string }
const FOTO = /\.(jpe?g|png|gif|webp|avif)$/i
/** Los adjuntos viajan como «[Imagen adjunta: /ruta]» para el asistente; en la burbuja se ven como miniatura o ficha. */
function separar(text: string): { texto: string; adj: Adj[] } {
  const adj: Adj[] = [], resto: string[] = []
  for (const ln of text.split('\n')) {
    let m: RegExpMatchArray | null
    // Línea con solo una ruta de imagen (la que Hermes usa para que Zazu la vea): no se enseña, la miniatura ya va en «[Imagen adjunta: …]»
    if (/^["']?[~/.][^\n"']*\.(?:jpe?g|png|gif|webp|avif|bmp|tiff?|heic)["']?$/i.test(ln.trim())) continue
    if ((m = ln.match(/^\[(Imagen adjunta|Archivo adjunto): (.+)\]$/))) { adj.push({ ...(rutaApp(m[2]) || {}), name: m[2].split('/').pop() || m[2], imagen: m[1] === 'Imagen adjunta' }); continue }
    if ((m = ln.match(/^\[Archivo guardado en mis carpetas › (.+)\]$/))) { const path = m[1].split(' › ').join('/'); adj.push({ root: 'compartido', path, name: path.split('/').pop() || path, imagen: FOTO.test(path) }); continue }
    resto.push(ln)
  }
  const texto = resto.join('\n').trim()
  return { texto: adj.length && texto === 'Te adjunto esto.' ? '' : texto, adj }
}

function Adjunto({ a }: { a: Adj }) {
  const [roto, setRoto] = useState(false)
  const foto = a.imagen && a.root && a.path !== undefined && !roto
  const dentro = foto ? <img src={urlDescarga(a.root!, a.path!, true)} alt={a.name} loading="lazy" onError={() => setRoto(true)} /> : <><Icon name="file" size={18} /><span className="cut">{a.name}</span></>
  return a.root && a.path !== undefined
    ? <button type="button" className={`bubble-adj ${foto ? 'foto' : ''}`} onClick={() => abrirEnCarpetas(a.root!, a.path!, false)} aria-label={`Abrir ${a.name} en Carpetas`}>{dentro}</button>
    : <span className="bubble-adj">{dentro}</span>
}

/** Lo que escribiste: burbuja a la derecha, con los adjuntos encima. */
export function MensajeTuyo({ text, time }: { text: string; time?: string }) {
  if (text.startsWith('[[organizar-agenda]]')) return <div className="msg msg-tuyo"><span className="visually-hidden">Tú{time ? `, a las ${time}` : ''}:</span>
    <div className="msg-burbuja">📅 Organizar mi agenda</div></div>
  const { texto, adj } = separar(text)
  return <div className="msg msg-tuyo">
    <span className="visually-hidden">Tú{time ? `, a las ${time}` : ''}:</span>
    {adj.length > 0 && <div className="bubble-adjuntos">{adj.map((a, i) => <Adjunto key={i} a={a} />)}</div>}
    {texto && (texto.length > 700 ? <details className="msg-burbuja largo"><summary>Mensaje largo ({texto.length} caracteres)</summary>{texto}</details> : <div className="msg-burbuja">{texto}</div>)}
  </div>
}

/** A cada bloque de código de una respuesta se le pone encima un botón «Copiar» (el HTML lo genera lib.md; aquí solo se envuelve). */
function ponerCopiar(raiz: HTMLElement | null) {
  raiz?.querySelectorAll('pre').forEach(pre => {
    if (pre.parentElement?.classList.contains('md-codigo')) return
    const caja = document.createElement('div'); caja.className = 'md-codigo'
    const b = document.createElement('button'); b.type = 'button'; b.className = 'md-copiar'; b.textContent = 'Copiar'; b.setAttribute('aria-label', 'Copiar el código')
    pre.replaceWith(caja); caja.append(b, pre)
  })
}
async function alCopiarCodigo(e: MouseEvent<HTMLElement>) {
  const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.md-copiar')
  if (!b) return
  const texto = b.parentElement?.querySelector('pre')?.textContent || ''
  try { await copiar(texto); b.textContent = 'Copiado' } catch { b.textContent = 'No se pudo' }
  setTimeout(() => { b.textContent = 'Copiar' }, 2000)
}

/** Respuesta del asistente: prosa sin burbuja, con letra de lectura (Markdown seguro de lib.md, con enlaces a Carpetas y fichas MEDIA:). */
export function RespuestaIA({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const html = useMemo(() => md(text), [text])
  useLayoutEffect(() => ponerCopiar(ref.current), [html])
  return <div ref={ref} className="msg msg-ia md" onClick={e => void alCopiarCodigo(e)} dangerouslySetInnerHTML={{ __html: html }} />
}

/** Al empezar cada respuesta: el logo y el nombre (Zazu, o el de la asistente de una invitada), y la hora. */
export function CabeceraTurno({ nombre, time, cara }: { nombre: string; time?: string; cara?: ReactNode }) {
  return <div className="turno">{cara ?? <LogoZazu tam={20} />}<span>{nombre}</span>{time && <small>{time}</small>}</div>
}

/** «Zazu está pensando…» (o el nombre de su asistente, para una invitada) mientras no hay nada en directo que enseñar. */
export function Pensando({ nombre }: { nombre: string }) {
  return <div className="msg msg-ia pensando" role="status" aria-label={`${nombre} está pensando`}><Indicador tam={20} /></div>
}
