import { useEffect, useRef, useState } from 'react'
import type { TouchEvent } from 'react'
import { Icon } from '../icons'
import { fmtSize, urlDescarga } from '../lib'
import { Hoja, Ic } from './ui'
import { escribiendo, fecha, fuentesDe, num, useVideo } from './nube'
import type { Medio } from './nube'

type Props = {
  m: Medio; pos: number; total: number; hayAnt: boolean; haySig: boolean; siguiente: Medio | null
  enAlbum: boolean; zazu: string
  /** hay otra hoja encima (álbum, compartir…): ni atajos ni presentación */
  bloqueado: boolean
  onIr: (d: -1 | 1) => void
  /** presentación: pasa a la siguiente foto ('espera' si aún está llegando la página siguiente, 'fin' si no hay más) */
  onAvanzar: () => 'ok' | 'espera' | 'fin'
  onFav: () => void; onAlbum: () => void; onCompartir: () => void; onQuitarAlbum: () => void
  onPapelera: () => void; onPreguntar: () => void; onCarpetas: () => void; onClose: () => void
}

const DIAPO = 4000   // presentación: cuatro segundos por foto

/** El visor de una foto o vídeo: flechas, F, deslizar, presentación y todas las acciones. Va dentro de una Hoja (Esc y el Atrás del móvil la cierran). */
export function Visor(p: Props) {
  const { m } = p
  const h = useRef(p); h.current = p   // los atajos y los temporizadores usan siempre lo último
  const vid = useVideo(m.kind === 'video' ? m.path : null)
  const [pres, setPres] = useState(false)
  const [cargada, setCargada] = useState('')   // la foto que ya llegó (una por ruta: no hace falta reiniciarla)
  const [rota, setRota] = useState('')   // la foto que no se pudo enseñar ni en miniatura
  const [vez, setVez] = useState(0)
  const reintento = useRef(false), toque = useRef<{ x: number; y: number } | null>(null), pre = useRef<HTMLImageElement | null>(null)

  useEffect(() => {   // atajos: ← → para pasar, F para favorito (Esc ya lo trata la hoja)
    const k = (e: KeyboardEvent) => {
      const { bloqueado, onIr, onFav } = h.current
      if (bloqueado || e.ctrlKey || e.metaKey || e.altKey || escribiendo(e.target)) return
      const medio = e.target instanceof HTMLMediaElement   // en un vídeo, las flechas mueven el tiempo
      if (e.key === 'ArrowLeft' && !medio) onIr(-1)
      else if (e.key === 'ArrowRight' && !medio) onIr(1)
      else if ((e.key === 'f' || e.key === 'F') && !e.repeat) onFav()
    }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  }, [])

  const sig = p.siguiente
  useEffect(() => {   // la siguiente foto ya va bajando mientras se mira esta
    if (sig?.kind !== 'image') return
    const im = new Image(); im.src = fuentesDe(sig)[0]; pre.current = im
  }, [sig?.path, sig?.kind])

  const foto = m.kind === 'image'
  const fuentes = fuentesDe(m)
  useEffect(() => {   // presentación: solo fotos; un vídeo se salta
    if (!pres || p.bloqueado) return
    if (!foto || cargada === m.path) {
      const t = setTimeout(() => {
        const r = h.current.onAvanzar()
        reintento.current = r === 'espera'
        if (r === 'fin') setPres(false); else if (r === 'espera') setVez(v => v + 1)
      }, !foto ? 500 : reintento.current ? 1000 : DIAPO)
      return () => clearTimeout(t)
    }
  }, [pres, p.bloqueado, foto, cargada, m.path, vez]) // eslint-disable-line react-hooks/exhaustive-deps

  const abajo = (e: TouchEvent) => { toque.current = e.touches.length === 1 && !(e.target instanceof HTMLMediaElement) ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null }   // en un vídeo, deslizar es mover el tiempo
  const arriba = (e: TouchEvent) => {
    const a = toque.current; toque.current = null
    if (!a) return
    const dx = e.changedTouches[0].clientX - a.x, dy = e.changedTouches[0].clientY - a.y
    if (Math.abs(dx) > 60 && Math.abs(dx) > 1.5 * Math.abs(dy)) p.onIr(dx < 0 ? 1 : -1)
  }

  const sub = [fecha(m.mtime), m.size ? fmtSize(m.size) : '', p.pos >= 0 ? `${num(p.pos + 1)} de ${num(p.total)}` : ''].filter(Boolean).join(' · ')
  return <Hoja titulo={m.name} sub={sub} ancha clase="nube-hoja-visor" onClose={p.onClose}>
    <div className="nube-visor" onTouchStart={abajo} onTouchEnd={arriba}>
      {foto
        ? rota === m.path ? <p className="nube-prep" role="status">No se puede enseñar esta foto aquí.<br />Pulsa «Descargar» para abrirla con otra app.</p>
          : <>{cargada !== m.path && <span className="nube-cargando" role="status">Cargando…</span>}
            <img key={m.path} src={fuentes[0]} alt={m.name} decoding="async" onLoad={() => setCargada(m.path)}
              onError={e => { const t = e.currentTarget, k = +(t.dataset.k || 0) + 1; if (k < fuentes.length) { t.dataset.k = String(k); t.src = fuentes[k] } else { setCargada(m.path); setRota(m.path) } }} /></>   // si una no llega, la siguiente; si ninguna, un aviso
        : vid?.listo ? <video key={m.path} src={vid.src} controls autoPlay playsInline />
          : <p className="nube-prep" role="status">{vid?.error ? <>No se puede preparar este vídeo para verlo aquí.<br />Pulsa «Descargar» para abrirlo con otra app.</> : vid ? <>Preparando el vídeo para verlo aquí…<br />Solo tarda la primera vez.</> : 'Cargando…'}</p>}
      <button type="button" className="nube-flecha ant" disabled={!p.hayAnt} onClick={() => p.onIr(-1)} aria-label="Anterior" title="Anterior (←)"><Icon name="back" size={22} /></button>
      <button type="button" className="nube-flecha sig" disabled={!p.haySig} onClick={() => p.onIr(1)} aria-label="Siguiente" title="Siguiente (→)"><Icon name="chevron" size={22} /></button>
    </div>
    <div className="nube-vacc">
      <button type="button" className={`nube-vb${m.fav ? ' on' : ''}`} aria-pressed={m.fav} onClick={p.onFav} title="Favorita (tecla F)"><Ic n="heart" lleno={m.fav} /><span>Favorita</span></button>
      <button type="button" className="nube-vb" onClick={() => setPres(v => !v)}><Icon name={pres ? 'pause' : 'play'} /><span>{pres ? 'Pausar presentación' : 'Presentación'}</span></button>
      <button type="button" className="nube-vb" onClick={p.onAlbum}><Ic n="album" /><span>Añadir a álbum</span></button>
      <button type="button" className="nube-vb" onClick={p.onCompartir}><Ic n="share" /><span>Compartir</span></button>
      <a className="nube-vb" href={urlDescarga('compartido', m.path)} download={m.name}><Icon name="download" /><span>Descargar</span></a>
      <button type="button" className="nube-vb" onClick={p.onPreguntar}><Ic n="idea" /><span>Preguntar a {p.zazu}</span></button>
      <button type="button" className="nube-vb" onClick={p.onCarpetas}><Icon name="folder" /><span>Ver en carpetas</span></button>
      {p.enAlbum && <button type="button" className="nube-vb" onClick={p.onQuitarAlbum}><Ic n="album" /><span>Quitar de este álbum</span></button>}
      <button type="button" className="nube-vb peligro" onClick={p.onPapelera}><Ic n="trash" /><span>A la papelera</span></button>
    </div>
  </Hoja>
}
