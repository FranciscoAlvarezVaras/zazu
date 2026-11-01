import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Icon } from '../icons'
import { AGENTE, etiquetaRuta, fmtSize, irA, urlZip, useFetch, useParams } from '../lib'
import type { Ask } from '../ctx'
import { base, crearCarpeta, LIMITE_SUBIDA, padre, subir } from './api'
import { BarraAviso, Hoja, Ic, trasHoja } from './ui'
import type { Aviso } from './ui'
import { Cuadricula, agrupar } from './Cuadricula'
import type { Grupo } from './Cuadricula'
import { BorrarAlbum, ElegirAlbum, FranjaAlbumes, NombreAlbum } from './Albumes'
import { CompartirHoja, MisEnlaces } from './Compartir'
import { DuplicadosHoja } from './Duplicados'
import { Espacio } from './Espacio'
import { CopiaZip } from './Hojas'
import { Visor } from './Visor'
import Mapa from './Mapa'
import { centroDe } from './mapa'
import type { Caja } from './mapa'
import { useLista } from './lista'
import { accionAlbum, albumLote, consulta, crearAlbumCon, escribiendo, medioSubido, msg, num, ORDENES, plural, ponerFav, restaurarTodos, tirarTodos, urlZipAlbum, urlZipFav } from './nube'
import type { Album, Filtros, Medio, Orden, Resumen, Tirada } from './nube'
import './galeria.css'

type Tipo = '' | 'image' | 'video'
const TIPOS: [Tipo, string][] = [['', 'Todo'], ['image', 'Fotos'], ['video', 'Vídeos']]
const ORIGENES: [string, string][] = [['', 'Todo'], ['DCIM', 'Cámara'], ['WhatsApp', 'WhatsApp']]
const SUBIDAS = 'Subidas'   // lo que se sube desde aquí va a esta carpeta de Compartido
type Lugar = { caja: Caja; n: number }   // una zona del mapa: se ven solo sus fotos
type HojaT = null | { k: 'album'; paths: string[] } | { k: 'nuevo' } | { k: 'renombrar'; a: Album } | { k: 'borrar'; a: Album }
  | { k: 'compartir'; m: Medio } | { k: 'dup' } | { k: 'enlaces' } | { k: 'grandes'; fs: File[] }
const leerOrden = (): Orden => { try { const o = localStorage.getItem('nube-orden'); return o === 'antiguas' || o === 'tamano' ? o : 'nuevas' } catch { return 'nuevas' } }
const hayArchivos = (e: DragEvent) => Array.from(e.dataTransfer?.types || []).includes('Files')
/** ¿Una foto recién subida entra en lo que se está viendo? (los filtros de ahora) */
const encaja = (m: Medio, f: Filtros) => !f.dia && !f.album && !f.fav && !f.caja && (!f.tipo || m.kind === f.tipo) && (!f.en || m.path.toLowerCase().includes(f.en.toLowerCase())) && (!f.q || m.name.toLowerCase().includes(f.q.toLowerCase()))

/** Galería de Carpetas («Mi nube»): todo Compartido (la copia del móvil incluida) en cuadrícula, con favoritos, álbumes, selección, duplicados, enlaces para compartir, subida y Zazu. Solo para Fran. */
export default function Galeria({ ask, alCarpetas }: { ask: Ask; alCarpetas: (ruta: string, archivo?: string) => void }) {
  const [tipo, setTipo] = useState<Tipo>('')
  const [en, setEn] = useState('')
  const [q, setQ] = useState('')
  const [busca, setBusca] = useState('')
  const [dia, setDia] = useState(false)   // «un día como hoy»: lo de este día en años anteriores
  const [fav, setFav] = useState(false)
  const [lugar, setLugar] = useState<Lugar | null>(null)   // viene del mapa: solo las fotos con GPS dentro de ese recuadro
  const mapa = useParams().vista === 'mapa'   // Fotos | Mapa: vive en la URL (?tab=carpetas&vista=mapa), así Atrás, Adelante y recargar funcionan
  const [album, setAlbum] = useState('')   // fav y álbum no van juntos: es una cosa o la otra
  const [orden, setOrden] = useState<Orden>(leerOrden)
  const [abierto, setAbierto] = useState<string | null>(null)   // la ruta de la foto del visor
  const [selec, setSelec] = useState(false)
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [hoja, setHoja] = useState<HojaT>(null)
  const [aviso, setAviso] = useState<Aviso | null>(null)
  const [subida, setSubida] = useState<{ n: number; total: number; nombre: string; pct: number } | null>(null)
  const [trabajo, setTrabajo] = useState<{ texto: string; hecho: number; total: number } | null>(null)
  const [suelta, setSuelta] = useState(false)   // arrastrando archivos encima (escritorio)
  const zazu = AGENTE

  const caja = lugar?.caja ?? null
  const filtros: Filtros = { tipo, en, q: busca, dia, fav, album, orden, caja }
  const cons = useMemo(() => consulta({ tipo, en, q: busca, dia, fav, album, orden, caja }), [tipo, en, busca, dia, fav, album, orden, caja])
  const lista = useLista(cons, orden)
  const { items, total, cargando, error } = lista
  const resumen = useFetch<Resumen>('/api/nube')
  const albumes = useFetch<{ items: Album[] }>('/api/nube/albumes')
  const r = resumen.data && typeof resumen.data.bytes === 'number' ? resumen.data : null
  const misAlbumes = albumes.data && Array.isArray(albumes.data.items) ? albumes.data.items : null
  const albumActual = misAlbumes?.find(a => a.id === album)

  // lo último de cada cosa, para las funciones que llegan tarde (avisos con Deshacer, temporizadores)
  const abiertoRef = useRef(abierto); abiertoRef.current = abierto
  const hojaRef = useRef(hoja); hojaRef.current = hoja
  const selecRef = useRef(selec); selecRef.current = selec
  const favRef = useRef(fav); favRef.current = fav
  const consRef = useRef(cons); consRef.current = cons
  const filtrosRef = useRef(filtros); filtrosRef.current = filtros
  const ancla = useRef(-1)   // la última marcada (Mayús + clic marca el tramo)
  const subiendo = useRef(false), carpetaLista = useRef(false)
  const hondo = useRef(0)   // cuántos «dragenter» sin su «dragleave»
  const entrada = useRef<HTMLInputElement>(null)
  const cabecera = useRef<HTMLDivElement>(null)
  const mas = useRef<HTMLButtonElement>(null)
  const reloj = useRef(0)
  const tirando = useRef(0)   // hasta cuándo no se atiende otro «A la papelera»: un doble toque no debe tirar también la foto de al lado, que el visor ya enseña
  const corazones = useRef(new Map<string, boolean>())   // el corazón de las copias que quitó Duplicados, para devolverlo con su Deshacer

  useEffect(() => { const t = setTimeout(() => setBusca(q.trim()), 350); return () => clearTimeout(t) }, [q])   // no pedir en cada tecla
  useEffect(() => () => clearTimeout(reloj.current), [])
  const avisar = useCallback((a: Aviso) => setAviso(a), [])
  /** Los números de arriba (espacio, favoritos, álbumes) se vuelven a pedir un momento después del último cambio */
  const { reload: recargarResumen } = resumen, { reload: recargarAlbumes } = albumes
  const refrescar = useCallback((conAlbumes = false) => {
    clearTimeout(reloj.current)
    reloj.current = window.setTimeout(() => { void recargarResumen(); if (conAlbumes) void recargarAlbumes() }, 600)
  }, [recargarResumen, recargarAlbumes])
  const cambiarOrden = (o: Orden) => { setOrden(o); try { localStorage.setItem('nube-orden', o) } catch { /* sin almacenamiento */ } }

  /* ---------- selección ---------- */
  const alternar = useCallback((i: number, rango: boolean) => {
    const L = lista.ref.current, desde = ancla.current   // la ancla de ANTES: el cambio de estado se aplica más tarde
    ancla.current = i
    setSel(s => {
      const n = new Set(s), p = L[i]?.path
      if (!p) return s
      if (rango && desde >= 0 && L[desde]) { const [a, b] = desde < i ? [desde, i] : [i, desde]; for (let k = a; k <= b; k++) n.add(L[k].path) }
      else if (n.has(p)) n.delete(p); else n.add(p)
      return n
    })
  }, [lista.ref])
  const cancelarSel = useCallback(() => { setSelec(false); setSel(new Set()); ancla.current = -1 }, [])
  const abrir = useCallback((i: number, mayus: boolean) => {
    if (selecRef.current) return alternar(i, mayus)
    const m = lista.ref.current[i]
    if (m) setAbierto(m.path)
  }, [alternar, lista.ref])
  const largo = useCallback((i: number) => { setSelec(true); alternar(i, false) }, [alternar])
  const marcarMes = useCallback((g: Grupo) => setSel(s => {
    const n = new Set(s), todas = g.ms.every(({ m }) => n.has(m.path))
    g.ms.forEach(({ m }) => { if (todas) n.delete(m.path); else n.add(m.path) })
    return n
  }), [])
  useEffect(() => {   // Esc sale de la selección (si no hay hoja encima)
    if (!selec) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape' && !abiertoRef.current && !hojaRef.current && !escribiendo(e.target)) cancelarSel() }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  }, [selec, cancelarSel])
  useEffect(() => {   // la barra de selección ocupa el sitio de los avisos: que se pongan encima
    document.body.classList.toggle('nube-selec', selec)
    return () => document.body.classList.remove('nube-selec')
  }, [selec])
  const conHoja = !!abierto || !!hoja
  useEffect(() => {   // con el visor o una hoja abierta, en el móvil los avisos van arriba: abajo taparían sus botones
    document.body.classList.toggle('nube-hojas', conHoja)
    return () => document.body.classList.remove('nube-hojas')
  }, [conHoja])

  /* ---------- favoritos ---------- */
  const { poner, quitar, insertar } = lista
  const cambiarFav = useCallback(async (paths: string[], on: boolean, soltar = true) => {
    const s = new Set(paths), afectados = lista.ref.current.filter(m => s.has(m.path))
    if (!afectados.length) return
    const sacar = favRef.current && !on && soltar   // en Favoritos, lo que deja de serlo sale de la lista
    poner(new Map(afectados.map(m => [m.path, on] as [string, boolean])))   // se pinta al momento
    if (sacar) quitar(afectados.map(m => m.path))
    try { await ponerFav(afectados.map(m => m.path), on); refrescar() }
    catch (e) {   // no se pudo: todo vuelve a como estaba
      if (sacar) insertar(afectados); else poner(new Map(afectados.map(m => [m.path, m.fav] as [string, boolean])))
      avisar({ texto: `No se pudo cambiar el favorito: ${msg(e)}` })
    }
  }, [lista.ref, poner, quitar, insertar, refrescar, avisar])
  const alFav = useCallback((i: number) => { const m = lista.ref.current[i]; if (m) void cambiarFav([m.path], !m.fav) }, [cambiarFav, lista.ref])

  /* ---------- papelera (con Deshacer) ---------- */
  async function tirar(ms: Medio[], antesDeQuitar?: () => void): Promise<string[]> {
    if (!ms.length || trabajo || Date.now() < tirando.current) return []
    tirando.current = Date.now() + 20000   // en marcha (si la red se cuelga, se suelta sola)
    try { return await tirarYa(ms, antesDeQuitar) } finally { tirando.current = Date.now() + 800 }
  }
  async function tirarYa(ms: Medio[], antesDeQuitar?: () => void): Promise<string[]> {
    const vista = consRef.current, varios = ms.length > 1
    const mostrar = (hecho: number) => { if (varios) setTrabajo({ texto: 'Mandando a la papelera', hecho, total: ms.length }) }
    mostrar(0)
    const { hechos, fallos } = await tirarTodos(ms.map(m => m.path), mostrar)
    setTrabajo(null)
    const idos = new Set(hechos.map(h => h.path))
    if (!idos.size) { avisar({ texto: `No se pudo mandar a la papelera: ${fallos[0]?.error || 'algo falló'}.` }); return [] }
    antesDeQuitar?.(); quitar(idos); refrescar(true)
    const resto = fallos.length ? ` ${plural(fallos.length, 'no se pudo mover', 'no se pudieron mover')} (${fallos[0].error}).` : ''
    avisar({ texto: `${idos.size === 1 ? `«${ms.find(m => idos.has(m.path))!.name}» está` : `${plural(idos.size, 'elemento está', 'elementos están')}`} en la papelera.${resto}`, accion: { label: 'Deshacer', fn: () => void deshacerTirar(hechos, ms, vista) } })
    return [...idos]
  }
  async function deshacerTirar(hechos: Tirada[], ms: Medio[], vista: string) {
    const { vueltos, fallos } = await restaurarTodos(hechos)
    const por = new Map(ms.map(m => [m.path, m] as [string, Medio]))
    if (consRef.current === vista) insertar(vueltos.map(v => { const m = por.get(v.path)!; return v.nuevo === m.path ? m : { ...m, path: v.nuevo, name: base(v.nuevo) } }))   // si ya se está mirando otra cosa, aparecerán al volver
    refrescar(true)
    avisar({ texto: fallos ? `Volvieron ${plural(vueltos.length, 'elemento', 'elementos')}; ${plural(fallos, 'no se pudo recuperar', 'no se pudieron recuperar')}.` : vueltos.length === 1 ? `«${por.get(vueltos[0].path)!.name}» ha vuelto a su sitio.` : `${plural(vueltos.length, 'elemento ha vuelto', 'elementos han vuelto')} a su sitio.` })
  }

  /* ---------- álbumes ---------- */
  const verAlbum = useCallback((id: string) => { setAlbum(id); setFav(false); cancelarSel(); setHoja(null) }, [cancelarSel])
  const verFavoritos = () => { setFav(f => !f); setAlbum(''); cancelarSel() }
  const verVista = (aMapa: boolean) => { if (aMapa !== mapa) { cancelarSel(); irA({ tab: 'carpetas', vista: aMapa ? 'mapa' : 'galeria' }) } }
  /** Desde el mapa: las fotos de una zona, en la cuadrícula de siempre y sin otros filtros que las escondan */
  const verZona = useCallback((c: Caja, n: number) => {
    setLugar({ caja: c, n }); setTipo(''); setEn(''); setQ(''); setBusca(''); setDia(false); setFav(false); setAlbum(''); cancelarSel()
    irA({ tab: 'carpetas', vista: 'galeria' })
    document.querySelector('.app-content')?.scrollTo({ top: 0 })
  }, [cancelarSel])
  async function añadirA(a: Album, paths: string[]) {
    await albumLote('añadir', a.id, paths)
    setHoja(null); cancelarSel(); refrescar(true)
    avisar({ texto: `${plural(paths.length, 'elemento añadido', 'elementos añadidos')} a «${a.nombre}».`, accion: { label: 'Ver álbum', fn: () => verAlbum(a.id) } })
  }
  async function crearAlbum(nombre: string, paths: string[]) {
    try {
      const id = await crearAlbumCon(nombre, paths)
      setHoja(null); cancelarSel()
      avisar({ texto: paths.length ? `Álbum «${nombre}» creado con ${plural(paths.length, 'elemento', 'elementos')}.` : `Álbum «${nombre}» creado.`, accion: { label: 'Abrir', fn: () => verAlbum(id) } })
    } finally { refrescar(true) }
  }
  async function renombrarAlbum(a: Album, nombre: string) {
    await accionAlbum({ accion: 'renombrar', id: a.id, nombre })
    setHoja(null); refrescar(true); avisar({ texto: `Ahora se llama «${nombre}».` })
  }
  async function borrarAlbum(a: Album) {
    await accionAlbum({ accion: 'borrar', id: a.id })
    setHoja(null); setAlbum(''); refrescar(true)
    avisar({ texto: `Álbum «${a.nombre}» borrado. Sus fotos y vídeos siguen en su sitio.` })
  }
  async function quitarDeAlbum(ms: Medio[], antesDeQuitar?: () => void) {
    if (!album || !ms.length) return
    const id = album, vista = consRef.current
    try {
      await albumLote('quitar', id, ms.map(m => m.path))
      antesDeQuitar?.(); quitar(ms.map(m => m.path)); refrescar(true)
      avisar({ texto: ms.length === 1 ? `«${ms[0].name}» ya no está en este álbum.` : `${plural(ms.length, 'elemento', 'elementos')} fuera de este álbum.`, accion: { label: 'Deshacer', fn: () => void volverAlAlbum(id, ms, vista) } })
    } catch (e) { avisar({ texto: `No se pudo quitar del álbum: ${msg(e)}` }) }
  }
  async function volverAlAlbum(id: string, ms: Medio[], vista: string) {
    try { await albumLote('añadir', id, ms.map(m => m.path)); if (consRef.current === vista) insertar(ms); refrescar(true) }
    catch (e) { avisar({ texto: `No se pudo volver a ponerlo: ${msg(e)}` }) }
  }

  /* ---------- visor ---------- */
  const i = abierto ? items.findIndex(x => x.path === abierto) : -1
  const m = i >= 0 ? items[i] : null
  useEffect(() => { if (abierto && i < 0 && !cargando) setAbierto(null) }, [abierto, i, cargando])   // la foto ya no está en la lista
  useEffect(() => {   // cerca del final de lo cargado se pide la página siguiente: así se puede seguir pasando (y la presentación no se corta)
    if (i >= 0 && i >= items.length - 6 && items.length < total && !cargando && !error) void lista.pedir()
  }, [i, items.length, total, cargando, error]) // eslint-disable-line react-hooks/exhaustive-deps
  const cerrarVisor = useCallback(() => {
    setAbierto(null)
    if (favRef.current) quitar(lista.ref.current.filter(x => !x.fav).map(x => x.path))   // en Favoritos, lo que se desmarcó mirándolo sale al cerrar
  }, [quitar, lista.ref])
  const ir = (d: -1 | 1) => { const n = items[i + d]; if (n) setAbierto(n.path) }
  const avanzar = (): 'ok' | 'espera' | 'fin' => {
    for (let k = i + 1; k < items.length; k++) if (items[k].kind === 'image') { setAbierto(items[k].path); return 'ok' }
    if (items.length < total) { if (!cargando && !error) void lista.pedir(); return 'espera' }
    avisar({ texto: 'Fin de la presentación.' }); return 'fin'
  }
  /** Tras quitar la foto abierta, el visor sigue con la de al lado (o se cierra si era la única) */
  const alLado = (p: string) => { const v = items[i + 1] ?? items[i - 1] ?? null; return () => { if (abiertoRef.current === p) setAbierto(v?.path ?? null) } }

  /* ---------- subir (botón o arrastrar) ---------- */
  function recibir(fl: FileList | File[] | null) {
    const fs = Array.from(fl || [])
    if (!fs.length) return
    if (subiendo.current) return avisar({ texto: 'Espera a que termine la subida de ahora.' })
    if (fs.some(f => f.size > LIMITE_SUBIDA)) setHoja({ k: 'grandes', fs }); else void subirTodos(fs)
  }
  async function subirTodos(fs: File[]) {
    setHoja(null)
    if (subiendo.current) return
    subiendo.current = true
    if (!carpetaLista.current) { await crearCarpeta('', SUBIDAS).catch(() => { /* ya existe */ }); carpetaLista.current = true }
    const nombres: string[] = [], medios: Medio[] = [], fallos: string[] = []
    for (const [k, f] of fs.entries()) {
      setSubida({ n: k + 1, total: fs.length, nombre: f.name, pct: 0 })
      try {
        const d = await subir(SUBIDAS, f, f.name, pct => setSubida(s => s && { ...s, pct })), x = medioSubido(`${SUBIDAS}/${d.name}`, f.size)
        nombres.push(d.name); if (x) medios.push(x)
      }
      catch (e) { fallos.push(`«${f.name}»: ${msg(e)}`) }
    }
    subiendo.current = false; setSubida(null)
    const nuevas = medios.filter(x => encaja(x, filtrosRef.current))
    if (nuevas.length) insertar(nuevas)   // el servidor las verá en su índice en menos de un minuto; mientras tanto se enseñan ya
    if (nombres.length) refrescar()
    const dentro = `a «${SUBIDAS}»`
    avisar({ texto: !fallos.length ? (nombres.length === 1 ? `«${nombres[0]}» subido ${dentro}.` : `${plural(nombres.length, 'archivo subido', 'archivos subidos')} ${dentro}.`) : `${nombres.length ? `Subidos ${nombres.length} de ${fs.length}. ` : ''}No se pudo subir ${fallos[0]}${fallos.length > 1 ? ` (y ${fallos.length - 1} más)` : ''}.` })
  }
  const enArrastre = {
    onDragEnter: (e: DragEvent) => { if (hayArchivos(e)) { hondo.current++; setSuelta(true) } },
    onDragOver: (e: DragEvent) => { if (hayArchivos(e)) e.preventDefault() },
    onDragLeave: (e: DragEvent) => { if (hayArchivos(e) && --hondo.current <= 0) { hondo.current = 0; setSuelta(false) } },
    onDrop: (e: DragEvent) => { if (!hayArchivos(e)) return; e.preventDefault(); hondo.current = 0; setSuelta(false); recibir(e.dataTransfer.files) },
  }

  /* ---------- lo que se pinta ---------- */
  const grupos = useMemo(() => agrupar(items, orden), [items, orden])   // una vez por cambio de lista, no en cada pintado
  const porRuta = useMemo(() => new Map(items.map(x => [x.path, x] as [string, Medio])), [items])
  const todasFav = sel.size > 0 && [...sel].every(p => porRuta.get(p)?.fav)
  const preguntar = (x: Medio) => { cerrarVisor(); trasHoja(() => ask(`Sobre «${etiquetaRuta('compartido', x.path)}»: `, { fill: true })) }
  const vacio = busca ? `Nada llamado «${busca}».` : lugar ? 'No hay fotos con ubicación en esta zona.' : fav ? 'Aún no tienes favoritos. Toca el corazón de una foto para guardarla aquí.' : album ? 'Este álbum está vacío. Abre una foto y toca «A un álbum».'
    : dia ? 'Hoy no hay recuerdos de otros años.' : 'No hay nada de este tipo todavía.'
  const pedirMas = () => void lista.pedir()
  useEffect(() => {   // al llegar abajo se piden las 90 siguientes (el botón sigue ahí por si el navegador no sabe)
    const el = mas.current
    if (!el || cargando || error || items.length >= total || typeof IntersectionObserver === 'undefined') return
    const o = new IntersectionObserver(es => { if (es.some(x => x.isIntersecting)) void lista.pedir() }, { rootMargin: '900px 0px' })
    o.observe(el); return () => o.disconnect()
  }, [cargando, error, items.length, total]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (album || fav) cabecera.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [album, fav])

  return <div className="nube" {...enArrastre}>
    <div className="nube-hero">
      <div><h3>Tus fotos y vídeos</h3><p>{r ? `${plural(r.fotos, 'foto', 'fotos')} · ${plural(r.videos, 'vídeo', 'vídeos')}` : 'En este PC.'}</p></div>
      <div className="nube-hero-acc">
        <button type="button" className="btn-primary" disabled={!!subida} onClick={() => entrada.current?.click()}><Icon name="upload" size={18} /> Subir</button>
        {!mapa && <button type="button" className="btn-secondary" aria-pressed={selec} onClick={() => selec ? cancelarSel() : setSelec(true)}><Icon name="check" size={18} /> {selec ? 'Listo' : 'Seleccionar'}</button>}
        <CopiaZip href={urlZip('compartido', '')} avisar={!r || r.bytes > 2 * 1024 ** 3} bytes={r?.bytes} className="btn-secondary" title="Copia de seguridad de toda la nube"><Icon name="download" size={18} /> Copia ZIP</CopiaZip>
        <input ref={entrada} type="file" multiple accept="image/*,video/*" className="visually-hidden" tabIndex={-1} aria-hidden="true" onChange={e => { recibir(e.target.files); e.target.value = '' }} />
      </div></div>
    {subida && <div className="cp-subida" role="status">Subiendo {subida.total > 1 ? `${subida.n} de ${subida.total}: ` : ''}«{subida.nombre}» · {subida.pct} %
      <span className="cp-progreso"><i style={{ width: `${subida.pct}%` }} /></span></div>}
    <div className="nube-vistas" role="group" aria-label="Cómo ver tus fotos">
      <button type="button" aria-pressed={!mapa} onClick={() => verVista(false)}><Ic n="image" size={18} /> Fotos</button>
      <button type="button" aria-pressed={mapa} onClick={() => verVista(true)}><Icon name="pin" size={18} /> Mapa</button></div>
    {mapa ? <Mapa onVer={verZona} onFotos={() => verVista(false)} /> : <>
    {lugar && <div className="nube-coleccion nube-zona">
      <button type="button" className="nube-volver" onClick={() => verVista(true)}><Icon name="back" size={16} /> Volver al mapa</button>
      <div className="nube-coleccion-tit"><strong>Fotos de esta zona</strong>{(!cargando || items.length > 0) && <small>{plural(total, 'elemento', 'elementos')} · cerca de {centroDe(lugar.caja)}</small>}</div>
      <div className="nube-coleccion-acc uno"><button type="button" className="nube-vb" onClick={() => setLugar(null)}><Icon name="close" size={18} /><span>Ver todas las fotos, sin zona</span></button></div></div>}
    {!lugar && <>
    <Espacio r={r} error={resumen.error && msg(new Error(resumen.error))} onReintentar={() => void resumen.reload()} onDuplicados={() => setHoja({ k: 'dup' })} onEnlaces={() => setHoja({ k: 'enlaces' })} />
    <div className="nube-zazu"><Ic n="idea" size={18} /><span>Pídele a {zazu} lo que quieras de tu nube</span>
      <button type="button" onClick={() => ask('En mi nube (Carpetas › Movil-S25): busca ', { fill: true })}>Buscar</button>
      <button type="button" onClick={() => ask('Ordena y resúmeme lo que hay en mi nube (Carpetas › Movil-S25): ', { fill: true })}>Resumir</button></div></>}
    <label className="cp-buscar"><Ic n="search" size={18} /><input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar por nombre…" aria-label="Buscar en mi nube" />
      {q && <button type="button" onClick={() => setQ('')} aria-label="Borrar búsqueda"><Icon name="close" size={16} /></button>}</label>
    <div className="nube-filtros">
      <div className="cp-raices" role="group" aria-label="Qué enseñar">{TIPOS.map(([t, l]) =>
        <button type="button" key={t} aria-pressed={tipo === t} className={tipo === t ? 'on' : ''} onClick={() => setTipo(t)}>{l}</button>)}</div>
      <div className="nube-chips">
        <button type="button" aria-pressed={fav} className={fav ? 'on' : ''} onClick={verFavoritos}><Ic n="heart" size={14} lleno={fav} /> Favoritos{r?.favoritos ? ` · ${num(r.favoritos)}` : ''}</button>
        {ORIGENES.map(([v, l]) => <button type="button" key={v} aria-pressed={en === v} aria-label={v ? undefined : 'Todo, de cualquier carpeta'} className={en === v ? 'on' : ''} onClick={() => setEn(v)}>{l}</button>)}
        <button type="button" aria-pressed={dia} className={dia ? 'on' : ''} onClick={() => setDia(d => !d)}>Un día como hoy</button>
        <button type="button" onClick={() => alCarpetas('')}><Icon name="folder" size={14} /> Ver carpetas</button>
        <label className="nube-orden"><span className="visually-hidden">Ordenar por</span>
          <select value={orden} onChange={e => cambiarOrden(e.target.value as Orden)}>{ORDENES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label></div></div>

    <FranjaAlbumes lista={misAlbumes} error={albumes.error && msg(new Error(albumes.error))} actual={album} onElegir={id => id === album ? setAlbum('') : verAlbum(id)} onNuevo={() => setHoja({ k: 'nuevo' })} onReintentar={() => void albumes.reload()} />
    {(album || fav) && <div className="nube-coleccion" ref={cabecera}>
      <button type="button" className="nube-volver" onClick={() => { setAlbum(''); setFav(false) }}><Icon name="back" size={16} /> Todas las fotos</button>
      <div className="nube-coleccion-tit"><strong>{album ? albumActual?.nombre ?? 'Álbum' : 'Tus favoritos'}</strong>{(!cargando || items.length > 0) && <small>{plural(total, 'elemento', 'elementos')}</small>}</div>
      <div className={`nube-coleccion-acc${fav ? ' uno' : ''}`}>
        {album && albumActual && <>
          <button type="button" className="nube-vb" onClick={() => setHoja({ k: 'renombrar', a: albumActual })}><Icon name="pen" /><span>Renombrar</span></button>
          <a className="nube-vb" href={urlZipAlbum(album)} download><Icon name="download" /><span>Copia ZIP del álbum</span></a>
          <button type="button" className="nube-vb nube-borrar" onClick={() => setHoja({ k: 'borrar', a: albumActual })}><Ic n="trash" /><span>Borrar álbum</span></button></>}
        {fav && <a className="nube-vb" href={urlZipFav} download><Icon name="download" /><span>Copia ZIP de favoritos</span></a>}</div></div>}

    <p className="visually-hidden" role="status">{!cargando || items.length ? plural(total, 'resultado', 'resultados') : 'Cargando…'}</p>
    <Cuadricula grupos={grupos} sel={sel} selec={selec} peso={orden === 'tamano'} onAbrir={abrir} onFav={alFav} onLargo={largo} onMes={marcarMes} />
    {cargando && !items.length && <div className="nube-grid" aria-hidden="true">{Array.from({ length: 18 }, (_, k) => <span key={k} className="nube-celda nube-esqueleto" />)}</div>}
    {error && <p className="cp-vacio" role="alert">No se pudo cargar{items.length ? ' lo siguiente' : ''}: {error}. <button type="button" className="text-link cp-en-linea" onClick={pedirMas}>Reintentar</button></p>}
    {!cargando && !error && !items.length && <p className="cp-vacio">{vacio}</p>}
    {items.length < total && !error && <button type="button" ref={mas} className="btn-secondary cp-ancho nube-mas" disabled={cargando} onClick={pedirMas}>
      {cargando ? 'Cargando…' : `Ver más (${num(total - items.length)})`}</button>}
    </>}

    {selec && <div className="nube-selbar" role="toolbar" aria-label="Qué hacer con lo marcado">
      <div className="nube-selcuenta" aria-live="polite"><strong>{num(sel.size)}</strong><span>{sel.size === 1 ? 'marcada' : 'marcadas'}</span></div>
      {trabajo ? <div className="nube-selprog" role="status">{trabajo.texto}: {num(trabajo.hecho)} de {num(trabajo.total)}
        <span className="cp-progreso"><i style={{ width: `${Math.round(trabajo.hecho / trabajo.total * 100)}%` }} /></span></div>
        : <>
          <button type="button" disabled={!sel.size} onClick={() => { void cambiarFav([...sel], !todasFav); cancelarSel() }}><Ic n="heart" lleno={todasFav} /><span>{todasFav ? 'Quitar favorito' : 'Favorito'}</span></button>
          <button type="button" disabled={!sel.size} onClick={() => setHoja({ k: 'album', paths: [...sel] })}><Ic n="album" /><span>Álbum</span></button>
          {album && <button type="button" disabled={!sel.size} onClick={() => void quitarDeAlbum(items.filter(x => sel.has(x.path))).then(cancelarSel)}><Ic n="album" /><span>Quitar del álbum</span></button>}
          <button type="button" className="peligro" disabled={!sel.size} onClick={() => void tirar(items.filter(x => sel.has(x.path))).then(cancelarSel)}><Ic n="trash" /><span>A la papelera</span></button>
          <button type="button" onClick={cancelarSel}><Icon name="close" /><span>Cancelar</span></button></>}
    </div>}
    {suelta && <div className="nube-suelta" aria-hidden="true"><Icon name="upload" size={34} /><strong>Suelta aquí para subir</strong><span>Se guardan en la carpeta «{SUBIDAS}»</span></div>}

    {m && <Visor m={m} pos={i} total={total} hayAnt={i > 0} haySig={i < items.length - 1} siguiente={items[i + 1] ?? null} enAlbum={!!album} zazu={zazu} bloqueado={!!hoja}
      onIr={ir} onAvanzar={avanzar} onFav={() => void cambiarFav([m.path], !m.fav, false)}
      onAlbum={() => setHoja({ k: 'album', paths: [m.path] })} onCompartir={() => setHoja({ k: 'compartir', m })}
      onQuitarAlbum={() => void quitarDeAlbum([m], alLado(m.path))} onPapelera={() => void tirar([m], alLado(m.path))}
      onPreguntar={() => preguntar(m)} onCarpetas={() => alCarpetas(padre(m.path), m.path)} onClose={cerrarVisor} />}

    {hoja?.k === 'album' && <ElegirAlbum albumes={misAlbumes || []} n={hoja.paths.length} excepto={album} onClose={() => setHoja(null)} onElegir={a => añadirA(a, hoja.paths)} onNuevo={nombre => crearAlbum(nombre, hoja.paths)} />}
    {hoja?.k === 'nuevo' && <NombreAlbum titulo="Nuevo álbum" boton="Crear álbum" onClose={() => setHoja(null)} onGuardar={nombre => crearAlbum(nombre, [])} />}
    {hoja?.k === 'renombrar' && <NombreAlbum titulo="Cambiar el nombre" inicial={hoja.a.nombre} boton="Guardar" onClose={() => setHoja(null)} onGuardar={nombre => renombrarAlbum(hoja.a, nombre)} />}
    {hoja?.k === 'borrar' && <BorrarAlbum a={hoja.a} onClose={() => setHoja(null)} onBorrar={() => borrarAlbum(hoja.a)} />}
    {hoja?.k === 'compartir' && <CompartirHoja m={hoja.m} avisar={avisar} onClose={() => setHoja(null)} />}
    {hoja?.k === 'enlaces' && <MisEnlaces avisar={avisar} onClose={() => setHoja(null)} />}
    {hoja?.k === 'dup' && <DuplicadosHoja avisar={avisar} onClose={() => setHoja(null)} alQuitar={ps => { for (const x of quitar(ps)) corazones.current.set(x.path, x.fav) }}
      alVolver={ms => { if (ms.length) insertar(ms.filter(x => encaja(x, filtrosRef.current)).map(x => ({ ...x, fav: !!corazones.current.get(x.path) }))) }} />}
    {hoja?.k === 'grandes' && <Hoja titulo="Pesa mucho" onClose={() => setHoja(null)}>
      <ul className="cp-grandes">{hoja.fs.filter(f => f.size > LIMITE_SUBIDA).map((f, k) => <li key={k}><strong>{f.name}</strong> · {fmtSize(f.size)}</li>)}</ul>
      <p className="cp-nota">Por internet, lo que pasa de 100 MB suele fallar a mitad. ¿Lo intento igual?</p>
      <button type="button" className="btn-primary cp-ancho" onClick={() => void subirTodos(hoja.fs)}>Intentarlo igual</button>
      {hoja.fs.some(f => f.size <= LIMITE_SUBIDA) && <button type="button" className="btn-secondary cp-ancho" onClick={() => void subirTodos(hoja.fs.filter(f => f.size <= LIMITE_SUBIDA))}>Subir solo los pequeños</button>}
      <button type="button" className="btn-secondary cp-ancho" onClick={() => setHoja(null)}>Cancelar</button>
    </Hoja>}
    <BarraAviso aviso={aviso} cerrar={() => setAviso(null)} />
  </div>
}
