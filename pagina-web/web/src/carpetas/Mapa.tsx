import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../icons'
import { Ic } from './ui'
import { mini, msg, num, plural } from './nube'
import { cajaDe, coordenadas, leerMapa, unir } from './mapa'
import type { Caja, Punto, RespMapa } from './mapa'
import MapaOSM from './MapaOSM'
import './mapa.css'

/* El mapa de Mi nube (solo Fran). Por privacidad no pide nada a internet mientras no se active: sin permiso enseña «Lugares», la lista de zonas con sus fotos
   (que también es la alternativa para lector de pantalla). Con el interruptor encendido añade el mapa de OpenStreetMap, que sí pide mosaicos a openstreetmap.org. */
const OSM = 'nube-mapa-osm'   // el permiso para pedir mosaicos a openstreetmap.org, recordado en este navegador
const ZOOM_LUGARES = 7        // celdas de unos 30 a 50 km: una ciudad con sus alrededores
const leerOSM = () => { try { return localStorage.getItem(OSM) === '1' } catch { return false } }
const guardarOSM = (si: boolean) => { try { if (si) localStorage.setItem(OSM, '1'); else localStorage.removeItem(OSM) } catch { /* sin almacenamiento: vale para esta visita */ } }

/** Los lugares (el mundo entero a zoom bajo) y cómo va el índice del GPS: mientras el servidor aún lee las fotos se vuelve a preguntar cada pocos segundos */
function useLugares() {
  const [d, setD] = useState<RespMapa | null>(null)
  const [error, setError] = useState('')
  const [intento, setIntento] = useState(0)
  const tuvo = useRef(false)
  useEffect(() => {
    let vivo = true, t = 0
    const ver = async () => {
      if (document.hidden && tuvo.current) { t = window.setTimeout(() => void ver(), 4000); return }   // con la pestaña oculta no se gasta red ni batería
      try {
        const x = await leerMapa(ZOOM_LUGARES)
        if (!vivo) return
        tuvo.current = true; setD(x); setError('')
        if (x.indexando) t = window.setTimeout(() => void ver(), 4000)
      } catch (e) {
        if (!vivo) return
        setError(msg(e))
        if (tuvo.current) t = window.setTimeout(() => void ver(), 8000)   // ya hay algo que enseñar: se sigue intentando sin molestar
      }
    }
    void ver()
    return () => { vivo = false; clearTimeout(t) }
  }, [intento])
  return { d, error, reintentar: () => { setError(''); setIntento(n => n + 1) } }
}

/** El encuadre de salida: lo que reúne a los lugares que juntan el 80 % de las fotos (a los más lejanos se llega con la diana, que lo encuadra todo) */
function principal(ls: Punto[]): Caja | null {
  const total = ls.reduce((a, p) => a + p.n, 0), cs: Caja[] = []
  let suma = 0
  for (const p of ls) { cs.push(cajaDe(p, ZOOM_LUGARES)); suma += p.n; if (suma >= total * 0.8) break }   // (ya vienen del que más tiene al que menos)
  return unir(cs)
}

/** Preparando el mapa… y cuántas fotos tienen ubicación */
function Estado({ d }: { d: RespMapa }) {
  const pct = Math.round(d.progreso * 100)
  return <div className="nube-mapa-estado">
    {d.indexando && <div className="nube-preparando"><strong>Preparando el mapa… {pct} %</strong>
      <span className="cp-progreso" role="progressbar" aria-label="Preparando el mapa" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><i style={{ width: `${pct}%` }} /></span>
      <small>Estoy leyendo dónde se hizo cada foto. Pasa la primera vez y puedes seguir usando tu nube mientras tanto.</small></div>}
    <p className="nube-ubic"><strong>{num(d.conGps)}</strong> {d.conGps === 1 ? 'foto' : 'fotos'} con ubicación · <strong>{num(d.sinGps)}</strong> sin ubicación</p>
  </div>
}

/** El permiso para el mapa de OpenStreetMap, dicho claro */
function Permiso({ osm, onCambiar }: { osm: boolean; onCambiar: (si: boolean) => void }) {
  return <div className="nube-osm">
    <div className="nube-osm-txt"><strong id="osm-t">Ver mapa con OpenStreetMap</strong>
      <small id="osm-d">{osm ? 'Pide los mosaicos de mapa a openstreetmap.org y le dice qué zona miras.'
        : 'Pide los mosaicos de mapa a openstreetmap.org y le dice qué zona miras. Apagado, no se pide nada a internet y ves tus lugares en lista. Tus fotos nunca salen de aquí.'}</small></div>
    <button type="button" role="switch" aria-checked={osm} aria-labelledby="osm-t" aria-describedby="osm-d" className="nube-interruptor" onClick={() => onCambiar(!osm)}><i aria-hidden="true" /></button>
  </div>
}

/** La portada de un lugar: su foto más nueva (o el dibujo de un pin si su miniatura no llega) */
function Cubierta({ path, video }: { path: string; video: boolean }) {
  const [fallo, setFallo] = useState(false)
  return <span className="nube-lugar-img">{fallo ? <Icon name="pin" size={28} /> : <img src={mini(path)} alt="" loading="lazy" decoding="async" onError={() => setFallo(true)} />}
    {video && !fallo && <span className="nube-play" aria-hidden="true"><Ic n="video" size={14} /></span>}</span>
}

/** Los lugares con sus fotos: del que más tiene al que menos. Pulsar uno abre sus fotos. */
function Lugares({ lugares, onVer }: { lugares: RespMapa['puntos']; onVer: (c: Caja, n: number) => void }) {
  const [ver, setVer] = useState(8)
  if (!lugares.length) return null
  return <section className="nube-lugares" aria-labelledby="lugares-t">
    <div className="nube-cab"><h3 id="lugares-t">Lugares</h3><small className="nube-sub">{lugares.length < 500 ? plural(lugares.length, 'zona', 'zonas') : `Las ${num(lugares.length)} con más fotos`}</small></div>
    <ul className="nube-lugares-lista" role="list">{lugares.slice(0, ver).map(p => <li key={p.path}>
      <button type="button" className="nube-lugar" onClick={() => onVer(cajaDe(p, ZOOM_LUGARES), p.n)} aria-label={`${plural(p.n, 'foto', 'fotos')} en la zona ${coordenadas(p.lat, p.lon)}. Ver las fotos`}>
        <Cubierta path={p.path} video={p.kind === 'video'} /><strong>{plural(p.n, 'foto', 'fotos')}</strong><small>{coordenadas(p.lat, p.lon)}</small></button></li>)}</ul>
    {lugares.length > ver && <button type="button" className="btn-secondary cp-ancho" onClick={() => setVer(n => n + 16)}>Ver más lugares ({num(lugares.length - ver)})</button>}
  </section>
}

/** Ninguna foto trae ubicación: se dice por qué y qué hacer */
function SinUbicacion({ onFotos }: { onFotos: () => void }) {
  return <div className="nube-sin-dup" role="status"><Icon name="pin" size={30} />
    <strong>Ninguna foto tiene ubicación</strong>
    <p>Las fotos que haces con la cámara del móvil guardan dónde las hiciste si tiene la ubicación activada. Las que llegan por WhatsApp la pierden.</p>
    <p>Para que las próximas la guarden, activa las «etiquetas de ubicación» en los ajustes de la cámara del móvil.</p>
    <button type="button" className="btn-secondary" onClick={onFotos}>Ver todas las fotos</button></div>
}

/** `onVer`: abre las fotos de una zona (la Galería las enseña filtradas por ese recuadro); `onFotos`: vuelve a la cuadrícula de siempre */
export default function Mapa({ onVer, onFotos }: { onVer: (c: Caja, n: number) => void; onFotos: () => void }) {
  const [osm, setOsm] = useState(leerOSM)
  const { d, error, reintentar } = useLugares()
  const lugares = useMemo(() => d ? [...d.puntos].sort((a, b) => b.n - a.n || (a.path < b.path ? -1 : 1)) : [], [d])
  const todo = useMemo(() => unir(lugares.map(p => cajaDe(p, ZOOM_LUGARES))), [lugares])
  const inicio = useMemo(() => principal(lugares), [lugares])
  const cambiar = (si: boolean) => { setOsm(si); guardarOSM(si) }

  if (!d) return error ? <p className="cp-vacio" role="alert">No pude cargar el mapa: {error === 'no existe' ? 'este servidor aún no lo tiene' : error}. <button type="button" className="text-link cp-en-linea" onClick={reintentar}>Reintentar</button></p>
    : <p className="cp-vacio" role="status">Cargando el mapa…</p>
  return <section className="nube-mapa" aria-label="Mapa de tus fotos">
    <Estado d={d} />
    {error && <p className="cp-vacio" role="alert">No pude actualizar el mapa: {error}.</p>}
    {!d.indexando && d.conGps === 0 ? <SinUbicacion onFotos={onFotos} />
      : <>
        <Permiso osm={osm} onCambiar={cambiar} />
        {osm && lugares.length > 0 && <MapaOSM inicio={inicio} todo={todo} onVer={onVer} />}
        <Lugares lugares={lugares} onVer={onVer} />
      </>}
  </section>
}
