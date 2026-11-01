import { useEffect, useState } from 'react'
import { fmtSize, md, relTime, urlDescarga } from '../lib'
import { KIND_LABEL } from './api'
import type { Item, Raiz } from './api'
import { Ficha, Hoja, Ic } from './ui'
import type { Ico } from './ui'
import { useVideo } from './nube'

export type Accion = 'ver' | 'abrir' | 'whatsapp' | 'compartir' | 'descargar' | 'preguntar' | 'mover' | 'renombrar' | 'papelera'
export const ACC: Record<Accion, { label: string; ico: Ico }> = {
  ver: { label: 'Ver', ico: 'eye' }, abrir: { label: 'Abrir', ico: 'folder' }, whatsapp: { label: 'Mandar a mi WhatsApp', ico: 'send' },
  compartir: { label: 'Compartir', ico: 'share' }, descargar: { label: 'Descargar', ico: 'down' }, preguntar: { label: 'Preguntar a Zazu', ico: 'chat' },
  mover: { label: 'Mover a…', ico: 'move' }, renombrar: { label: 'Renombrar', ico: 'note' }, papelera: { label: 'A la papelera', ico: 'trash' },
}
export const meta = (it: Item) => [it.dir ? 'Carpeta' : KIND_LABEL[it.kind], !it.dir && it.size ? fmtSize(it.size) : '', relTime(it.mtime || null)].filter(Boolean).join(' · ')
const MAX_TEXTO = 1024 * 1024

/** Vista previa: fotos, PDF, vídeo, audio y notas/textos; lo demás, descargar o compartir.
 *  `nube`: es Mis carpetas de Fran; sus vídeos de cámara (HEVC) pasan por el mismo servidor de conversión que la Galería. */
export function Vista({ it, root, donde, acciones, hacer, onClose, nube = false }: { it: Item; root: Raiz; donde: string; acciones: Accion[]; hacer: (a: Accion, it: Item) => void; onClose: () => void; nube?: boolean }) {
  const url = urlDescarga(root, it.path, true)
  const vid = useVideo(nube && root === 'compartido' && it.kind === 'video' ? it.path : null)
  const leer = (it.kind === 'note' || it.kind === 'text') && it.size < MAX_TEXTO
  const [texto, setTexto] = useState<string | null>(null)
  useEffect(() => {
    if (!leer) return
    let vivo = true; setTexto(null)
    fetch(url).then(r => r.ok ? r.text() : Promise.reject()).then(t => { if (vivo) setTexto(t) }).catch(() => { if (vivo) setTexto('') })
    return () => { vivo = false }
  }, [url, leer])
  const otro = <div className="cp-vista-otro"><Ficha it={it} root={root} big /><p>Este archivo no se puede ver aquí. Descárgalo o compártelo para abrirlo con otra app.</p></div>
  const cuerpo = it.inline === false && it.kind !== 'note' && it.kind !== 'text' ? otro   // el navegador no sabe enseñarlo (HEIC, opus…)
    : it.kind === 'image' ? <img src={url} alt={it.name} />
    // el servidor no deja meter sus archivos en marcos (X-Frame-Options: DENY): el PDF se abre en su propio visor
    : it.kind === 'pdf' ? <a className="cp-vista-otro" href={url} target="_blank" rel="noopener noreferrer"><Ficha it={it} root={root} big /><strong>Abrir el PDF</strong><span>Se abre en el visor del móvil o en otra pestaña</span></a>
    : it.kind === 'video' ? (nube && root === 'compartido' ? (vid?.listo ? <video src={vid.src} controls playsInline preload="metadata" /> : <p className="nube-prep" role="status">{vid?.error ? 'No se puede preparar este vídeo. Descárgalo para abrirlo con otra app.' : vid ? 'Preparando el vídeo…' : 'Cargando…'}</p>) : <video src={url} controls playsInline preload="metadata" />)
    : it.kind === 'audio' ? <audio src={url} controls preload="metadata" />
    : leer ? texto === null ? <p className="cp-vacio">Cargando…</p>
      : !texto ? <p className="cp-vacio">No pude leerlo. Prueba a descargarlo.</p>
      : it.kind === 'note' ? <div className="cp-vista-texto md" dangerouslySetInnerHTML={{ __html: md(texto.replace(/^---\n[\s\S]*?\n---\n/, '')) }} />
      : <pre className="cp-vista-texto">{texto}</pre>
    : otro
  return <Hoja titulo={it.name} sub={<>{meta(it)}{donde && <><br />En {donde}</>}</>} onClose={onClose} ancha atras={false}>
    <div className={`cp-vista ${it.kind}`}>{cuerpo}</div>
    {!!acciones.length && <div className="cp-acciones">{acciones.map(a => <button key={a} className={a === 'whatsapp' ? 'principal' : a === 'papelera' ? 'peligro' : ''} onClick={() => hacer(a, it)}>
      <Ic n={ACC[a].ico} size={18} /> {ACC[a].label}</button>)}</div>}
  </Hoja>
}
