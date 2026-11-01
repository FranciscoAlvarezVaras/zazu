import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, MouseEvent, PointerEvent, SyntheticEvent } from 'react'
import { Icon } from '../icons'
import { Ic } from './ui'
import { mini, msg, num, plural } from './nube'
import { acotar, ajustar, cabe, cajaDe, cajaVista, contarZona, corto, leerMapa, limitar, mx, my, T, textoCaja, ZMAX } from './mapa'
import type { Caja, Punto, Tam, Vista } from './mapa'

/* Un mapa de mosaicos mínimo, sin librerías: Mercator, arrastrar, pellizcar, rueda con Ctrl, teclado, y las celdas de /api/nube/mapa como burbujas.
   Solo existe si Fran lo activa (Mapa.tsx): al pintarlo, el navegador pide los mosaicos a openstreetmap.org y le dice qué zona se mira. */
const PLANTILLA = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const MAX_PUNTOS = 200   // burbujas pintadas como máximo: más haría ir a trompicones al móvil
const MAX_FOTOS = 40     // de ellas, las que llevan miniatura (cada una es una imagen que el servidor prepara)
const ZOOM_FOTOS = 9     // desde este zoom las burbujas grandes llevan la miniatura de su portada
const ABRIR_SI = 30      // un grupo de tantos o menos se abre directamente en vez de acercar
const reducido = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

let ultima: Vista | null = null   // por dónde se quedó el mapa: al volver de ver unas fotos, sigue donde estaba

type Tesela = { clave: string; src: string; x: number; y: number; t: number }
/** Los mosaicos del zoom Z que cubren la pantalla (y media tesela de más por cada lado, para que al arrastrar no se vea el hueco) */
function teselasDe(v: Vista, tam: Tam, Z: number): Tesela[] {
  const n = 2 ** Z, t = T * 2 ** (v.z - Z), cx = v.x * n, cy = v.y * n, mw = tam.w / 2 + T / 2, mh = tam.h / 2 + T / 2
  const out: Tesela[] = []
  for (let j = Math.max(0, Math.floor(cy - mh / t)); j <= Math.min(n - 1, Math.floor(cy + mh / t)); j++)
    for (let i = Math.floor(cx - mw / t); i <= Math.floor(cx + mw / t); i++)
      out.push({ clave: `${Z}/${i}/${j}`, src: PLANTILLA.replace('{z}', String(Z)).replace('{x}', String(((i % n) + n) % n)).replace('{y}', String(j)),
        x: Math.round(tam.w / 2 + (i - cx) * t), y: Math.round(tam.h / 2 + (j - cy) * t), t: Math.ceil(t) + 1 })   // +1: sin rayitas entre mosaicos
  return out
}

type Marca = { p: Punto; x: number; y: number; foto: boolean }
/** Una burbuja del mapa: el número de medios que agrupa (y, al acercar, la miniatura de su portada) */
const Burbuja = memo(function Burbuja({ p, x, y, foto, onTocar }: Marca & { onTocar: (p: Punto) => void }) {
  const d = foto ? 56 : p.n === 1 ? 30 : Math.round(38 + Math.min(18, Math.log10(p.n) * 7))
  return <button type="button" tabIndex={-1} className={`mp-punto${foto ? ' foto' : ''}${p.n === 1 ? ' uno' : ''}`} title={plural(p.n, 'foto', 'fotos')}
    style={{ width: d, height: d, transform: `translate3d(${(x - d / 2).toFixed(1)}px,${(y - d / 2).toFixed(1)}px,0)` }} onClick={() => onTocar(p)}>
    {foto ? <span className="mp-img"><img src={mini(p.path)} alt="" decoding="async" draggable={false} onError={e => { e.currentTarget.style.visibility = 'hidden' }} /></span> : p.n > 1 ? corto(p.n) : null}
    {foto && p.n > 1 && <span className="mp-n">{corto(p.n)}</span>}
  </button>
})

/** El mapa y, debajo, cuántas fotos hay en lo que se ve con el botón para abrirlas. `inicio`: el encuadre de salida (donde están casi todas las fotos); `todo`: la caja que reúne todos los lugares. */
export default function MapaOSM({ inicio, todo, onVer }: { inicio: Caja | null; todo: Caja | null; onVer: (c: Caja, n: number) => void }) {
  const lienzo = useRef<HTMLDivElement>(null)
  const [tam, setTam] = useState<Tam | null>(null)
  const [vista, setVista] = useState<Vista | null>(null)
  const [puntos, setPuntos] = useState<Punto[]>([])
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const [intento, setIntento] = useState(0)
  const [mueve, setMueve] = useState(false)
  const [listo, setListo] = useState(false)   // ya llegó la primera respuesta del servidor
  const [sinMapa, setSinMapa] = useState(false)   // los mosaicos no llegan (sin red, o el navegador los bloquea)
  const [bloqueado, setBloqueado] = useState(false)   // la política de seguridad de la web no deja pedir mosaicos a openstreetmap.org
  const [antes, setAntes] = useState<number | null>(null)   // el zoom anterior, mientras llegan los mosaicos del nuevo
  const [zona, setZona] = useState<{ clave: string; n: number } | null>(null)   // cuántas fotos hay en lo que se ve (exacto, lo cuenta el servidor)
  const v = useRef<Vista | null>(null), t = useRef<Tam | null>(null), raf = useRef(0), anim = useRef(0)   // lo último, para los manejadores
  const dedos = useRef(new Map<number, { x: number; y: number }>()), base = useRef<{ v: Vista; ps: Map<number, { x: number; y: number }> } | null>(null), cogidos = useRef(new Set<number>())
  const arrastro = useRef(false), cuenta = useRef({ ok: 0, mal: 0 })
  const cubierto = useRef<{ z: number; caja: Caja } | null>(null), ctl = useRef<AbortController | null>(null)
  const alVer = useRef(onVer); alVer.current = onVer
  const todoRef = useRef(todo); todoRef.current = todo
  const inicioRef = useRef(inicio); inicioRef.current = inicio

  /** Cambia lo que se ve: se anota ya y se pinta en el siguiente cuadro (un gesto manda muchos eventos por cuadro) */
  const poner = useCallback((n: Vista, ya = false) => {
    const l = limitar(n, t.current!)
    v.current = ultima = l
    if (ya) { cancelAnimationFrame(raf.current); raf.current = 0; setVista(l) }
    else if (!raf.current) raf.current = requestAnimationFrame(() => { raf.current = 0; setVista(v.current) })
  }, [])
  /** Va a otra vista con un deslizamiento corto (sin él, si el usuario lo prefiere así) */
  const volar = useCallback((a: Vista) => {
    cancelAnimationFrame(anim.current)
    const d = v.current!
    if (reducido()) return poner(a)
    const ini = performance.now(), dx = a.x - d.x, ex = dx - Math.round(dx)   // por el camino corto, también al cruzar los 180°
    const paso = (ahora: number) => {
      const k = Math.min(1, (ahora - ini) / 320), e = 1 - (1 - k) ** 3
      poner({ x: d.x + ex * e, y: d.y + (a.y - d.y) * e, z: d.z + (a.z - d.z) * e })
      if (k < 1) anim.current = requestAnimationFrame(paso)
    }
    anim.current = requestAnimationFrame(paso)
  }, [poner])
  /** Un nivel más cerca o más lejos, manteniendo quieto el punto (px, py) de la pantalla (el centro, si no se da) */
  const acercar = useCallback((dz: number, px?: number, py?: number) => {
    const V = v.current!, G = t.current!, x = px ?? G.w / 2, y = py ?? G.h / 2
    const z = limitar({ ...V, z: dz > 0 ? Math.floor(V.z) + dz : Math.ceil(V.z) + dz }, G).z, S0 = T * 2 ** V.z, S1 = T * 2 ** z
    volar({ x: V.x + (x - G.w / 2) / S0 - (x - G.w / 2) / S1, y: V.y + (y - G.h / 2) / S0 - (y - G.h / 2) / S1, z })
  }, [volar])
  const tocar = useCallback((p: Punto) => {   // una burbuja: si agrupa poco, o ya no hay más que separar, se abren sus fotos; si no, se acerca
    if (arrastro.current || !v.current || !t.current) return
    const c = cajaDe(p, Math.round(v.current.z))
    if (p.n <= ABRIR_SI || v.current.z >= 15.5) return alVer.current(c, p.n)
    const f = ajustar(c, t.current, 70, ZMAX)
    if (f.z >= 15) return alVer.current(c, p.n)   // todo está en un sitio más pequeño que la pantalla: acercar no separa nada
    volar({ ...f, z: Math.max(f.z, v.current.z + 1.5) })
  }, [volar])

  /* ---------- tamaño y primera vista ---------- */
  useLayoutEffect(() => {
    const el = lienzo.current!
    const medir = () => { const r = el.getBoundingClientRect(); if (r.width > 0 && r.height > 0) setTam(a => a && Math.abs(a.w - r.width) < 1 && Math.abs(a.h - r.height) < 1 ? a : { w: r.width, h: r.height }) }
    medir()
    const o = typeof ResizeObserver === 'function' ? new ResizeObserver(medir) : null
    o?.observe(el); addEventListener('resize', medir)
    return () => { o?.disconnect(); removeEventListener('resize', medir) }
  }, [])
  useLayoutEffect(() => {
    if (!tam) return
    t.current = tam
    const c = inicioRef.current ?? todoRef.current, ini = v.current ?? ultima ?? (c ? ajustar(c, tam) : { x: 0.5, y: 0.4, z: 2 })
    poner(ini, true)
  }, [tam, poner])
  useEffect(() => () => { cancelAnimationFrame(raf.current); cancelAnimationFrame(anim.current); ctl.current?.abort() }, [])

  /* ---------- las burbujas de lo que se ve (con un poco de margen alrededor) ---------- */
  const zi = vista ? acotar(Math.round(vista.z), 0, ZMAX) : 0
  useEffect(() => {
    if (!vista || !tam) return
    const c = cajaVista(vista, tam, 0), cub = cubierto.current
    if (cub && cub.z === zi && cabe(c, cub.caja)) return   // lo que ya se pidió llega: no hace falta volver a preguntar
    const id = setTimeout(async () => {
      ctl.current?.abort()
      const a = ctl.current = new AbortController(), grande = cajaVista(vista, tam, 0.5)
      setCargando(true)
      try {
        const d = await leerMapa(zi, grande, a.signal)
        if (a.signal.aborted) return
        cubierto.current = { z: zi, caja: grande }; setPuntos(d.puntos); setError(''); setListo(true)
      } catch (e) { if (!a.signal.aborted && (e as Error).name !== 'AbortError') setError(msg(e)) }
      finally { if (ctl.current === a) setCargando(false) }
    }, 220)   // sin pedir mientras se arrastra
    return () => clearTimeout(id)
  }, [vista?.x, vista?.y, zi, tam?.w, tam?.h, intento]) // eslint-disable-line react-hooks/exhaustive-deps

  const claveVista = vista && tam ? textoCaja(cajaVista(vista, tam, 0)) : ''
  useEffect(() => {
    if (!claveVista) return
    const a = new AbortController()
    const id = setTimeout(async () => {
      try { const n = await contarZona(claveVista.split(',').map(Number) as Caja, a.signal); if (!a.signal.aborted) setZona({ clave: claveVista, n }) }
      catch { /* sin el número exacto se queda el aproximado */ }
    }, 220)
    return () => { clearTimeout(id); a.abort() }
  }, [claveVista])

  const { marcas, aprox } = useMemo(() => {
    if (!vista || !tam) return { marcas: [] as Marca[], aprox: 0 }
    const S = T * 2 ** vista.z, vis: Marca[] = []
    let dentro = 0
    for (const p of puntos) {
      let dx = mx(p.lon) - vista.x; dx -= Math.round(dx)   // la copia del mundo más cercana al centro
      const x = tam.w / 2 + dx * S, y = tam.h / 2 + (my(p.lat) - vista.y) * S
      if (x >= 0 && x <= tam.w && y >= 0 && y <= tam.h) dentro += p.n
      if (x > -50 && x < tam.w + 50 && y > -50 && y < tam.h + 50) vis.push({ p, x, y, foto: false })
    }
    vis.sort((a, b) => b.p.n - a.p.n)
    const top = vis.slice(0, MAX_PUNTOS)
    if (vista.z >= ZOOM_FOTOS) top.slice(0, MAX_FOTOS).forEach(m => { m.foto = true })
    return { marcas: top.reverse(), aprox: dentro }   // las grandes se pintan al final, encima de las pequeñas
  }, [puntos, vista, tam])

  /* ---------- mosaicos ---------- */
  const Z = vista ? acotar(Math.floor(vista.z), 0, ZMAX) : 0
  const Zprev = useRef(Z)
  useEffect(() => {   // al cambiar de zoom, los mosaicos del anterior (ya en caché) se quedan debajo hasta que llegan los nuevos
    if (Zprev.current === Z) return
    const cerca = Math.abs(Zprev.current - Z) <= 2
    setAntes(cerca ? Zprev.current : null); Zprev.current = Z
    if (!cerca) return
    const id = setTimeout(() => setAntes(null), 700)
    return () => clearTimeout(id)
  }, [Z])
  const teselas = useMemo(() => vista && tam ? [...(antes != null ? teselasDe(vista, tam, antes) : []), ...teselasDe(vista, tam, Z)] : [], [vista, tam, antes, Z])
  const cargo = useCallback(() => { cuenta.current.ok++; setSinMapa(false) }, [])
  const fallo = useCallback((e: SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.visibility = 'hidden'; if (++cuenta.current.mal >= 3 && !cuenta.current.ok) setSinMapa(true) }, [])   // (sin el dibujito de «imagen rota»)

  useEffect(() => {   // si la web no deja pedir mosaicos a OSM (su CSP), se dice claro en vez de enseñar un mapa vacío
    const f = (e: SecurityPolicyViolationEvent) => { if (/openstreetmap\.org/.test(e.blockedURI)) setBloqueado(true) }
    document.addEventListener('securitypolicyviolation', f)
    return () => document.removeEventListener('securitypolicyviolation', f)
  }, [])

  /* ---------- gestos ---------- */
  const donde = (e: { clientX: number; clientY: number }) => { const r = lienzo.current!.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top } }
  const abajo = (e: PointerEvent) => {
    if ((e.pointerType === 'mouse' && e.button !== 0) || (e.target as Element).closest('.mp-controles,.mp-atrib,.mp-aviso') || !v.current) return
    cancelAnimationFrame(anim.current); arrastro.current = false
    dedos.current.set(e.pointerId, donde(e))
    base.current = { v: v.current, ps: new Map(dedos.current) }
  }
  const mover = (e: PointerEvent) => {
    const b = base.current, G = t.current
    if (!b || !G || !dedos.current.has(e.pointerId)) return
    dedos.current.set(e.pointerId, donde(e))
    const ids = [...b.ps.keys()].filter(id => dedos.current.has(id)), S0 = T * 2 ** b.v.z
    if (!ids.length) return
    if (!arrastro.current) {   // hasta que el dedo o el ratón se mueve de verdad es un toque, y un toque llega a la burbuja de debajo
      const p0 = b.ps.get(ids[0])!, p1 = dedos.current.get(ids[0])!
      if (ids.length < 2 && Math.hypot(p1.x - p0.x, p1.y - p0.y) < 6) return
      arrastro.current = true; setMueve(true)
    }
    if (!cogidos.current.has(e.pointerId)) { try { lienzo.current!.setPointerCapture(e.pointerId); cogidos.current.add(e.pointerId) } catch { /* ya no está */ } }
    if (ids.length >= 2) {   // pellizco: el punto del mapa que había entre los dedos sigue entre ellos
      const [a0, b0, a1, b1] = [b.ps.get(ids[0])!, b.ps.get(ids[1])!, dedos.current.get(ids[0])!, dedos.current.get(ids[1])!]
      const z = limitar({ ...b.v, z: b.v.z + Math.log2(Math.max(Math.hypot(a1.x - b1.x, a1.y - b1.y), 1) / (Math.hypot(a0.x - b0.x, a0.y - b0.y) || 1)) }, G).z, S1 = T * 2 ** z
      const [m0x, m0y, m1x, m1y] = [(a0.x + b0.x) / 2, (a0.y + b0.y) / 2, (a1.x + b1.x) / 2, (a1.y + b1.y) / 2]
      poner({ x: b.v.x + (m0x - G.w / 2) / S0 - (m1x - G.w / 2) / S1, y: b.v.y + (m0y - G.h / 2) / S0 - (m1y - G.h / 2) / S1, z })
    } else {
      const p0 = b.ps.get(ids[0])!, p1 = dedos.current.get(ids[0])!
      poner({ x: b.v.x - (p1.x - p0.x) / S0, y: b.v.y - (p1.y - p0.y) / S0, z: b.v.z })
    }
  }
  const soltar = (e: PointerEvent) => {
    if (!dedos.current.delete(e.pointerId)) return
    cogidos.current.delete(e.pointerId)
    if (dedos.current.size) base.current = { v: v.current!, ps: new Map(dedos.current) }   // queda un dedo: sigue desde donde está
    else { base.current = null; setMueve(false) }
  }
  const doble = (e: MouseEvent) => { if (!(e.target as Element).closest('.mp-controles,.mp-atrib,.mp-aviso,.mp-punto')) { const p = donde(e); acercar(1, p.x, p.y) } }
  const tecla = (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey || e.altKey || !v.current || !t.current) return
    const V = v.current, G = t.current, S = T * 2 ** V.z, paso = (dx: number, dy: number) => { e.preventDefault(); volar({ ...V, x: V.x + dx * G.w / 4 / S, y: V.y + dy * G.h / 4 / S }) }
    if (e.key === 'ArrowLeft') paso(-1, 0); else if (e.key === 'ArrowRight') paso(1, 0); else if (e.key === 'ArrowUp') paso(0, -1); else if (e.key === 'ArrowDown') paso(0, 1)
    else if (e.key === '+' || e.key === '=') { e.preventDefault(); acercar(1) } else if (e.key === '-' || e.key === '_') { e.preventDefault(); acercar(-1) }
  }
  useEffect(() => {   // la rueda acerca hacia el cursor (también con Ctrl y con el pellizco de un panel táctil). Hasta que se pulsa el mapa, sin Ctrl la rueda sigue moviendo la página: no se la lleva el mapa al pasar por encima.
    const el = lienzo.current!
    const f = (e: WheelEvent) => {
      if ((!e.ctrlKey && !e.metaKey && !el.contains(document.activeElement)) || !v.current || !t.current) return
      e.preventDefault(); cancelAnimationFrame(anim.current)
      const V = v.current, G = t.current, r = el.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top
      const px = acotar(e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY, -150, 150)
      const z = limitar({ ...V, z: V.z - px * 0.006 }, G).z, S0 = T * 2 ** V.z, S1 = T * 2 ** z
      poner({ x: V.x + (x - G.w / 2) / S0 - (x - G.w / 2) / S1, y: V.y + (y - G.h / 2) / S0 - (y - G.h / 2) / S1, z })
    }
    el.addEventListener('wheel', f, { passive: false })
    return () => el.removeEventListener('wheel', f)
  }, [poner])

  const cajaZona = vista && tam ? cajaVista(vista, tam, 0) : null
  const enZona = zona ? zona.n : aprox, vigente = !zona || zona.clave === claveVista   // (mientras se mueve, el número de antes, apagado)
  return <div className="mp">
    <div ref={lienzo} className={`mp-lienzo${mueve ? ' mueve' : ''}`} tabIndex={0} role="group" onKeyDown={tecla} onDoubleClick={doble}
      aria-label="Mapa de tus fotos. Con el teclado: las flechas lo mueven y más y menos acercan o alejan. La lista «Lugares» dice lo mismo en texto."
      onPointerDown={abajo} onPointerMove={mover} onPointerUp={soltar} onPointerCancel={soltar}>
      {vista && tam && <>
        <div className="mp-teselas" aria-hidden="true">{teselas.map(s =>
          <img key={s.clave} src={s.src} alt="" draggable={false} decoding="async" referrerPolicy="origin" onLoad={cargo} onError={fallo}
            style={{ width: s.t, height: s.t, transform: `translate3d(${s.x}px,${s.y}px,0)` }} />)}</div>
        <div className="mp-puntos" aria-hidden="true">{marcas.map(m => <Burbuja key={m.p.path} p={m.p} x={m.x} y={m.y} foto={m.foto} onTocar={tocar} />)}</div></>}
      <div className="mp-controles" role="group" aria-label="Controles del mapa">
        <button type="button" onClick={() => acercar(1)} disabled={!vista || vista.z >= ZMAX} aria-label="Acercar" title="Acercar (+)"><Icon name="plus" size={20} /></button>
        <button type="button" onClick={() => acercar(-1)} disabled={!vista} aria-label="Alejar" title="Alejar (−)"><Ic n="minus" size={20} /></button>
        <button type="button" onClick={() => tam && volar(todoRef.current ? ajustar(todoRef.current, tam) : { x: 0.5, y: 0.4, z: 2 })} disabled={!vista} aria-label="Ver todos los lugares" title="Ver todos los lugares"><Ic n="target" size={20} /></button>
      </div>
      <a className="mp-atrib" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>
      {cargando && <span className="mp-cargando" role="status">Cargando…</span>}
      {error && <p className="mp-aviso" role="alert">No pude traer los lugares: {error}. <button type="button" className="text-link cp-en-linea" onClick={() => { cubierto.current = null; setIntento(n => n + 1) }}>Reintentar</button></p>}
      {(sinMapa || bloqueado) && !error && <p className="mp-aviso" role="status">{bloqueado ? 'Esta versión de Zazu no deja cargar el mapa de openstreetmap.org.' : 'No llegan los mosaicos del mapa. Revisa tu conexión.'} Mientras tanto, usa la lista de lugares.</p>}
    </div>
    <div className="mp-barra">
      <p className={vigente ? '' : 'viejo'}><span>{!listo ? 'Buscando las fotos de esta zona…' : enZona ? <><strong>{num(enZona)}</strong> {enZona === 1 ? 'foto' : 'fotos'} en esta zona</> : 'No hay fotos en esta zona'}</span>
        <small>{enZona ? 'Pulsa una burbuja para acercar o abrir esas fotos.' : listo ? 'Mueve el mapa o pulsa la diana para ver todos los lugares.' : ' '}</small>
        <small className="mp-ayuda">Arrastra para mover. Pulsa el mapa y usa la rueda (o Ctrl + rueda) para acercar.</small></p>
      <button type="button" className="btn-primary" disabled={!enZona || !cajaZona} onClick={() => cajaZona && onVer(cajaZona, enZona)}>Ver {enZona === 1 ? 'esta foto' : 'estas fotos'}</button>
    </div>
  </div>
}
