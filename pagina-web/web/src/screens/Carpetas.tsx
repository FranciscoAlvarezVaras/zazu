import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Icon } from '../icons'
import { fmtSize, irA, leerParams, NAV, nombreAsistente, relTime, toneOf, urlApp, urlDescarga, urlZip, useFetch } from '../lib'
import type { Ctx } from '../ctx'
import { aMiWhatsApp, aPapelera, base, crearCarpeta, descartarCompartidos, etiqueta, itemDe, kindOf, LIMITE_SUBIDA, migas, mover, normalizar, padre, pendientesCompartidos, protegido, RAICES, raizValida, recogerCompartidos, restaurar, subir, unir, urlListado } from '../carpetas/api'
import type { Item, ListadoCrudo, Pendiente, Raiz } from '../carpetas/api'
import { BarraAviso, Ficha, Hoja, Ic, soltandoHoja, tomarHoja, trasHoja } from '../carpetas/ui'
import type { Aviso, Ico } from '../carpetas/ui'
import { ACC, meta, Vista } from '../carpetas/Vista'
import type { Accion } from '../carpetas/Vista'
import { CopiaZip, ElegirCarpeta, Renombrar } from '../carpetas/Hojas'
import Galeria from '../carpetas/Galeria'
import { Papelera } from '../carpetas/Papelera'
import '../carpetas/carpetas.css'

const enc = encodeURIComponent
const PAGINA = 120   // WhatsApp del móvil tiene cientos de archivos en una carpeta
type Orden = 'fecha' | 'nombre'
type Pos = { root: Raiz; ruta: string; archivo: string }
const leerOrden = (): Orden => { try { return localStorage.getItem('cp-orden') === 'nombre' ? 'nombre' : 'fecha' } catch { return 'fecha' } }
const limpia = (p?: string | null) => (p || '').replace(/^\/+|\/+$/g, '')

/** Dónde abrir según el enlace (?tab=carpetas&root=…&ruta=…&archivo=…); null si la URL es de otra pestaña */
function posDeUrl(guest: boolean): Pos | null {
  const p = leerParams() as { tab?: string; root?: string; ruta?: string; archivo?: string }
  if (p.tab && p.tab !== 'carpetas' && p.tab !== 'files') return null
  const archivo = limpia(p.archivo)
  return { root: guest ? 'compartido' : raizValida(p.root), ruta: p.ruta != null ? limpia(p.ruta) : padre(archivo), archivo }
}

const ICONO_CARPETA: Record<string, Ico> = { Recibidos: 'inbox', Importante: 'star', Enviados: 'send' }
const DESCR: Record<string, string> = { Recibidos: 'Llega solo de WhatsApp', Importante: 'Tus documentos clave', Guardado: '«Guárdalo» sin carpeta', Adjuntos: 'Lo del chat' }

const cuenta = (d: number, f: number) => [d ? `${d} ${d === 1 ? 'carpeta' : 'carpetas'}` : '', f ? `${f} ${f === 1 ? 'archivo' : 'archivos'}` : ''].filter(Boolean).join(' · ') || 'Vacía'

/** Una línea de ayuda por carpeta: cómo llegan las cosas aquí desde WhatsApp */
function pista(root: Raiz, ruta: string, guest: boolean, nombre?: string) {
  if (guest) return `Lo que guardas aquí o le pides a ${nombreAsistente(true, nombre)} que guarde. Tienes 2 GB.`
  if (root === 'notas') return 'Tus notas del Cerebro. Si quieres cambiar algo, pídeselo a Zazu.'
  if (root === 'whatsapp') return 'Los documentos de tus chats de WhatsApp, tal como están en el móvil.'
  const [a] = ruta.split('/')
  if (!ruta) return 'En el chat, dile a Zazu «guárdalo» o «enséñame el billete del tren».'
  if (a === 'Recibidos') return 'Aquí cae lo que subes sin carpeta. Toca «Guardar en…» para ordenarlo.'
  if (a === 'Importante') return `En el chat, dile a Zazu «guárdalo en ${ruta === 'Importante' ? 'Importante › Viajes' : migas(ruta)}».`
  if (a === 'Guardado') return 'Lo que le pides a Zazu que guarde sin decir dónde.'
  if (a === 'Adjuntos') return 'Lo que adjuntas en el chat. Aquí no se mueve ni se borra nada.'
  return `En el chat, dile a Zazu «guárdalo en ${migas(ruta)}».`
}

/** ¿Pide la URL la Galería (fotos y vídeos en cuadrícula, o su mapa)? Solo Fran: ?tab=carpetas&vista=galeria (o vista=mapa) */
const enGaleria = (guest?: boolean) => !guest && ['galeria', 'mapa'].includes(leerParams().vista || '')

export default function Carpetas({ guest, nombre, ask }: Ctx) {
  const [galeria, setGaleria] = useState(() => enGaleria(guest))
  const inv = !!guest
  const [pos, setPos] = useState<Pos>(() => posDeUrl(inv) || { root: 'compartido', ruta: '', archivo: '' })
  const posRef = useRef(pos)
  const fijar = (p: Pos) => { posRef.current = p; setPos(p) }   // síncrono: el aviso NAV de nuestro propio irA() llega antes de pintar
  const { root, ruta, archivo } = pos
  const [llegada] = useState(() => new URLSearchParams(location.search).get('recibido'))   // vuelta del «Compartir › Zazu» ('1' o 'demasiado')
  const [q, setQ] = useState('')
  const [qd, setQd] = useState('')
  const [orden, setOrden] = useState<Orden>(leerOrden)
  const [papelera, setPapelera] = useState(false)
  const [menu, setMenu] = useState<Item | null>(null)
  const [elegir, setElegir] = useState<{ items: Item[]; titulo: string; dejar?: string } | null>(null)
  const [renom, setRenom] = useState<Item | null>(null)
  const [nueva, setNueva] = useState<string | null>(null)   // nombre de la carpeta nueva; null = formulario cerrado
  const [subida, setSubida] = useState<{ n: number; total: number; nombre: string; pct: number } | null>(null)
  const [grandes, setGrandes] = useState<File[] | null>(null)
  const [listo, setListo] = useState<File | null>(null)   // compartir tras una descarga larga necesita otro toque
  const [pend, setPend] = useState<Pendiente[] | null>(null)   // lo compartido con Zazu que espera a que Fran diga «Guardar»
  const [recien, setRecien] = useState<Item | null>(null)   // el archivo abierto que se acaba de renombrar (hasta que llega el listado nuevo)
  const [aviso, setAviso] = useState<Aviso | null>(null)
  const [cuantos, setCuantos] = useState(PAGINA)
  const input = useRef<HTMLInputElement>(null)
  const vistaPush = useRef(false)
  const enviando = useRef(new Set<string>())
  const avisar = (a: Aviso) => setAviso(a)

  const escribe = !inv && root === 'compartido'   // mover, renombrar y papelera: solo Fran (las invitadas suben y crean carpetas)
  const lst = useFetch<ListadoCrudo>(papelera ? null : urlListado(root, ruta))
  const L = normalizar(lst.data, root)
  const fresco = !!L && L.path === ruta && (inv || L.root === root)   // useFetch deja el listado anterior mientras carga el nuevo
  const items = fresco ? L.items : []
  const soloLeer = root !== 'compartido' || !!(fresco && L.readonly)
  const buscando = !inv && qd.length >= 2 && !papelera
  const bus = useFetch<{ items: Item[] }>(buscando ? `/api/buscar?q=${enc(qd)}&root=${root}` : null)
  const verRecientes = !inv && root === 'compartido' && !ruta && !buscando && !papelera
  const rec = useFetch<{ items: Item[] }>(verRecientes ? '/api/recientes?n=12' : null)
  const recargar = useRef(() => { })   // siempre la versión actual (los avisos con Deshacer llegan más tarde)
  recargar.current = () => { void lst.reload(); void rec.reload(); void bus.reload() }

  useEffect(() => { const t = setTimeout(() => setQd(q.trim()), 300); return () => clearTimeout(t) }, [q])

  /* ---------- navegación (Atrás del móvil y enlaces directos) ---------- */
  const cerrarHojas = () => { setMenu(null); setElegir(null); setRenom(null); setGrandes(null); setListo(null) }
  function ir(nr: Raiz, nruta: string, reemplazar = false) {
    reemplazar = tomarHoja() || reemplazar   // desde una hoja (⋯ → Abrir): su entrada del historial pasa a ser la carpeta
    cerrarHojas(); setRecien(null)
    fijar({ root: nr, ruta: nruta, archivo: '' }); setQ(''); setQd(''); setPapelera(false); setCuantos(PAGINA); setNueva(null)
    vistaPush.current = false
    irA({ tab: 'carpetas', root: nr, ruta: nruta }, reemplazar)
    document.querySelector('.app-content')?.scrollTo({ top: 0 })
  }
  function ver(it: Item) {
    if (it.dir) return ir(root, it.path)
    fijar({ ...posRef.current, archivo: it.path }); vistaPush.current = true
    irA({ tab: 'carpetas', root, ruta, archivo: it.path }, tomarHoja())
  }
  function cerrarVista() {
    // si la abrimos nosotros, Atrás deja el historial como estaba; si llegó por enlace, se quita de la URL
    if (vistaPush.current && new URLSearchParams(location.search).get('archivo') === archivo) history.back()
    else irA({ tab: 'carpetas', root, ruta }, true)
    vistaPush.current = false; fijar({ ...posRef.current, archivo: '' })
  }
  function abrirPapelera() {   // misma URL, pero con su propia entrada: el Atrás del móvil la cierra
    history.pushState(history.state, '', location.href); setPapelera(true)
    document.querySelector('.app-content')?.scrollTo({ top: 0 })
  }
  useEffect(() => {   // Atrás/Adelante, o un enlace a otra carpeta (también tocar «Carpetas» abajo: vuelve al principio)
    const f = () => {
      setGaleria(enGaleria(inv))   // Atrás o Adelante entre la Galería y las carpetas
      const p = posDeUrl(inv), c = posRef.current
      if (!p) return
      if (soltandoHoja()) {   // se quitó la entrada de una hoja (no es navegar); si mientras tanto cambió el archivo abierto (Renombrar), se corrige la URL
        if (!enGaleria(inv) && urlApp({ tab: 'carpetas', ...c }) !== location.pathname + location.search) irA({ tab: 'carpetas', ...c }, true)   // (en la Galería la URL es otra y no se toca)
        return
      }
      // nuestra propia navegación: sin cambios (una vista previa abierta desde Recientes o la búsqueda no lleva ruta en la URL)
      const misma = p.root === c.root && (p.ruta === c.ruta || (!!p.archivo && !leerParams().ruta))
      if (misma && p.archivo === c.archivo) return setPapelera(false)   // Atrás desde la papelera, o «Carpetas» abajo
      fijar(p); cerrarHojas(); setPapelera(false)
      if (!misma) { setQ(''); setQd('') }   // abrir o cerrar una vista previa (Atrás) no borra la búsqueda
      if (!p.archivo) vistaPush.current = false
    }
    addEventListener(NAV, f)
    return () => removeEventListener(NAV, f)
  }, [inv]) // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------- Compartir › Zazu (archivos que dejó el service worker) ---------- */
  // Nada se sube sin que Fran lo confirme: cualquier web podría mandar archivos a /compartir y dejarlos esperando.
  useEffect(() => {
    if (llegada) irA({ tab: 'carpetas', ...posRef.current }, true)   // fuera ?recibido: Atrás o recargar no vuelven a avisar
    let vivo = true
    void pendientesCompartidos().catch(() => [] as Pendiente[]).then(ps => {
      if (!vivo) return
      if (llegada === 'demasiado') avisar({ texto: 'Era demasiado de una vez: comparte como mucho 10 archivos y 200 MB en total.' })
      if (ps.length) setPend(ps)
      else if (llegada === '1') avisar({ texto: 'No encontré lo que compartiste. Prueba a compartirlo otra vez.' })
    })
    return () => { vivo = false }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  function descartar(ps: Pendiente[]) {
    setPend(null)
    void descartarCompartidos(ps).then(() => avisar({ texto: 'Descartado: no se ha guardado nada.' }), () => avisar({ texto: 'No pude descartarlo. Inténtalo otra vez.' }))
  }
  function guardarCompartidos(ps: Pendiente[]) {
    setPend(null)
    trasHoja(() => void recoger(ps))   // primero se quita la entrada de la hoja; luego se navega a Recibidos
  }
  async function recoger(ps: Pendiente[]) {
    const destino = inv ? '' : 'Recibidos'
    const subidos: Item[] = []
    const total = await recogerCompartidos(destino, ps, {
      antes: async () => { if (!inv) await crearCarpeta('', 'Recibidos').catch(() => { }); ir('compartido', destino, true); avisar({ texto: 'Guardando lo que has compartido…' }) },   // si ya existe, el servidor dice 409 y seguimos
      alSubir: (n, size) => subidos.push({ ...itemDe(unir(destino, n)), size, mtime: Date.now() / 1000 }),
      alFallar: (n, e) => avisar({ texto: `No pude guardar «${n}»: ${e.message}` }),
    })
    if (!total) return avisar({ texto: 'Ya no estaba. Prueba a compartirlo otra vez.' })
    if (total < 0) return
    recargar.current()
    if (!subidos.length) return
    if (inv) avisar({ texto: subidos.length === 1 ? `«${subidos[0].name}» guardado` : `${subidos.length} archivos guardados` })
    else { setAviso(null); setElegir({ items: subidos, titulo: '¿Dónde lo guardo?', dejar: 'Déjalo en Recibidos' }) }
  }

  /* ---------- acciones ---------- */
  function accionesDe(it: Item): Accion[] {
    const a: Accion[] = [it.dir ? 'abrir' : 'ver']
    if (!it.dir) a.push('compartir', 'descargar')
    if (!inv) a.push('preguntar')
    if (escribe && !protegido(it.path)) a.push('mover', 'renombrar', 'papelera')
    return a
  }
  function hacer(a: Accion, it: Item) {
    setMenu(null)
    if (a === 'ver' || a === 'abrir') return ver(it)
    if (a === 'whatsapp') return void mandar(it)
    if (a === 'compartir') return void compartir(it)
    if (a === 'descargar') return descargar(it)
    if (a === 'preguntar') return trasHoja(() => ask(`Sobre «${etiqueta(root, it.path)}»: `, { fill: true }))   // desde ⋯: sin dejar la entrada de la hoja en el historial
    if (a === 'mover') return setElegir({ items: [it], titulo: 'Mover a…' })
    if (a === 'renombrar') return setRenom(it)
    if (a === 'papelera') return void tirar(it)
  }
  async function mandar(it: Item) {
    if (enviando.current.has(it.path)) return
    enviando.current.add(it.path); avisar({ texto: 'Mandándolo a tu WhatsApp…' })
    try { await aMiWhatsApp(it.path, root); avisar({ texto: `Hecho: «${it.name}» va de camino a tu WhatsApp.` }) }
    catch (e) { avisar({ texto: `No se pudo mandar: ${(e as Error).message}` }) }
    finally { enviando.current.delete(it.path) }
  }
  function descargar(it: Item) {
    const a = document.createElement('a'); a.href = urlDescarga(root, it.path); a.download = it.name
    document.body.appendChild(a); a.click(); a.remove()
  }
  async function compartir(it: Item) {
    if (!navigator.canShare || it.size > 60 * 1048576) return descargar(it)
    avisar({ texto: 'Preparándolo…' })
    let f: File
    try {
      const res = await fetch(urlDescarga(root, it.path))
      if (!res.ok) throw new Error(String(res.status))
      const b = await res.blob()
      f = new File([b], it.name, { type: b.type })
    } catch { return avisar({ texto: 'No pude prepararlo. Inténtalo otra vez.' }) }
    if (!navigator.canShare({ files: [f] })) { avisar({ texto: 'Este tipo de archivo no se puede compartir directamente: te lo descargo.' }); return descargar(it) }
    setAviso(null)
    try { await navigator.share({ files: [f], title: it.name }) }
    catch (e) { if ((e as Error).name === 'NotAllowedError') setListo(f) }   // tardó demasiado: el móvil pide otro toque
  }
  async function tirar(it: Item) {
    try {
      const { id } = await aPapelera(it.path)
      if (archivo === it.path) cerrarVista()
      recargar.current()
      avisar({ texto: `«${it.name}» está en la papelera.`, accion: { label: 'Deshacer', fn: () => void restaurar(id).then(() => { recargar.current(); avisar({ texto: `«${it.name}» ha vuelto a su sitio.` }) }).catch(e => avisar({ texto: `No se pudo recuperar: ${(e as Error).message}` })) } })
    } catch (e) { avisar({ texto: `No se pudo: ${(e as Error).message}` }) }
  }
  async function moverA(lista: Item[], destino: string) {
    setElegir(null)
    let ok = 0
    for (const it of lista) { try { await mover(it.path, destino); ok++ } catch (e) { avisar({ texto: `No pude mover «${it.name}»: ${(e as Error).message}` }) } }
    if (archivo && lista.some(i => i.path === archivo)) cerrarVista()
    recargar.current()
    if (ok) avisar({ texto: ok === 1 ? `«${lista[0].name}» ya está en ${etiqueta('compartido', destino)}` : `${ok} archivos ya están en ${etiqueta('compartido', destino)}`, accion: { label: 'Abrir', fn: () => ir('compartido', destino) } })
  }
  async function crear(e: FormEvent) {
    e.preventDefault()
    const n = (nueva || '').trim()
    if (!n) return
    if (n.includes('/')) return avisar({ texto: 'El nombre no puede llevar /' })
    try { await crearCarpeta(ruta, n); setNueva(null); recargar.current(); avisar({ texto: `Carpeta «${n}» creada`, accion: { label: 'Abrir', fn: () => ir(root, unir(ruta, n)) } }) }
    catch (e) { const m = (e as Error).message; avisar({ texto: `No se pudo crear: ${m === 'ya existe' ? 'ya hay una carpeta con ese nombre' : m}` }) }
  }
  function elegirArchivos(fl: FileList | null) {
    const fs = Array.from(fl || [])
    if (!fs.length) return
    if (fs.some(f => f.size > LIMITE_SUBIDA)) setGrandes(fs)
    else void subirTodos(fs)
  }
  async function subirTodos(fs: File[]) {
    setGrandes(null)
    const destino = ruta
    let ok = 0
    for (const [i, f] of fs.entries()) {
      setSubida({ n: i + 1, total: fs.length, nombre: f.name, pct: 0 })
      try { await subir(destino, f, f.name, pct => setSubida(s => s && { ...s, pct })); ok++ }
      catch (e) { avisar({ texto: `No se pudo subir «${f.name}»: ${(e as Error).message}` }) }
    }
    setSubida(null); recargar.current()
    if (ok === fs.length) avisar({ texto: ok === 1 ? `«${fs[0].name}» subido` : `${ok} archivos subidos` })
    else if (ok) avisar({ texto: `Subidos ${ok} de ${fs.length}` })
  }
  const cambiarOrden = (o: Orden) => { setOrden(o); try { localStorage.setItem('cp-orden', o) } catch { /* sin almacenamiento */ } }

  /* ---------- datos para pintar ---------- */
  const porNombre = (x: Item, y: Item) => x.name.localeCompare(y.name, 'es', { numeric: true, sensitivity: 'base' })
  // las carpetas, por nombre (la entrada, Recibidos, la primera); el orden por fecha es para los archivos
  const dirs = items.filter(i => i.dir).sort((x, y) => (escribe && !ruta ? +(y.name === 'Recibidos') - +(x.name === 'Recibidos') : 0) || porNombre(x, y))
  const files = items.filter(i => !i.dir).sort(orden === 'fecha' ? (x, y) => y.mtime - x.mtime : porNombre)
  const enRecibidos = escribe && (ruta === 'Recibidos' || ruta.startsWith('Recibidos/'))
  const recItems = (rec.data?.items || []).map(i => ({ ...i, kind: i.kind || kindOf(i.name, i.dir) }))
  const busItems = (bus.data?.items || []).map(i => ({ ...i, kind: i.kind || kindOf(i.name, i.dir) }))
  const roto = !!lst.error && !fresco   // la carpeta no se pudo abrir (enlace a una que ya no existe)
  const hallado = archivo ? [...items, ...recItems, ...busItems, ...(recien ? [recien] : [])].find(i => i.path === archivo) : undefined
  // enlace viejo (del chat) a un archivo de esta carpeta: si ya cargó y no está, se movió, se renombró o está en la papelera
  const enSuCarpeta = !!archivo && !hallado && padre(archivo) === ruta
  const perdido = enSuCarpeta && (fresco || lst.error === 'no existe')
  const vista = archivo && !perdido && !(enSuCarpeta && !fresco && !lst.error) ? hallado || itemDe(archivo) : null
  const raizLabel = inv ? 'Mis carpetas' : RAICES.find(x => x.id === root)!.label
  const partes = ruta ? ruta.split('/') : []
  const texto = pista(root, ruta, inv, nombre)

  const fila = (it: Item, extra?: ReactNode, donde?: string) => <div className="cp-fila" key={it.path}>
    <button className="cp-fila-main" onClick={() => ver(it)}><Ficha it={it} root={root} />
      <span className="cp-fila-txt"><strong>{it.name}</strong>
        <small>{it.origen === 'whatsapp' && <span className="cp-tag">por WhatsApp</span>}{meta(it)}{donde !== undefined && ` · en ${donde ? migas(donde) : raizLabel}`}</small></span></button>
    {accionesDe(it).length > 1 && <button className="cp-mas" onClick={() => setMenu(it)} aria-label={`Más opciones: ${it.name}`}><Ic n="more" /></button>}
    {extra && <div className="cp-fila-extra">{extra}</div>}
  </div>

  return <div className="extra-screen screen-enter cp">
    <div className="screen-heading"><span className="section-kicker">{inv ? 'SOLO TUYAS' : 'TUS ARCHIVOS'}</span><h2>{inv ? 'Mis carpetas' : 'Mi nube'}<span className="greeting-dot">.</span></h2>
      <p>{inv ? texto : 'Tus carpetas, fotos y vídeos, guardados en este PC y en tu móvil.'}</p></div>

    {!inv && !papelera && !ruta && <div className="cp-raices" role="group" aria-label="Qué quieres ver">{RAICES.map(x => <button key={x.id} aria-pressed={!galeria && root === x.id} className={!galeria && root === x.id ? 'on' : ''} onClick={() => { setGaleria(false); ir(x.id, '') }}>
      <Ic n={x.id === 'compartido' ? 'folder' : x.id === 'notas' ? 'brain' : 'phone'} size={16} /> {x.label}</button>)}
      <button aria-pressed={galeria} className={galeria ? 'on' : ''} onClick={() => { if (galeria) return; setGaleria(true); irA({ tab: 'carpetas', vista: 'galeria' }) }}><Ic n="image" size={16} /> Galería</button></div>}
    {!inv && !papelera && !galeria && root !== 'compartido' && <p className="cp-solo"><Ic n="lock" size={15} /> Solo para mirar: desde aquí no se cambia nada.</p>}

    {!inv && !papelera && !galeria && <div className="cp-buscar"><Ic n="search" size={18} />
      <input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder={`Buscar en ${raizLabel}`} aria-label="Buscar por nombre" enterKeyHint="search" />
      {q && <button onClick={() => setQ('')} aria-label="Borrar la búsqueda"><Icon name="close" size={16} /></button>}</div>}

    {galeria && !inv && !papelera ? <Galeria ask={ask} alCarpetas={(r, a) => { const rep = tomarHoja(); setGaleria(false); irA({ tab: 'carpetas', root: 'compartido', ruta: r, archivo: a }, rep) }} />
      : papelera ? <Papelera avisar={avisar} volver={() => history.back()} abrir={d => ir('compartido', d)} />
      : buscando ? <section className="cp-seccion" aria-live="polite">
        <div className="cp-cab-lista"><h3>{bus.loading && !bus.data ? 'Buscando…' : `${busItems.length === 50 ? 'Más de 50' : busItems.length} ${busItems.length === 1 ? 'resultado' : 'resultados'}`}</h3></div>
        {bus.error ? <p className="cp-vacio" role="alert">No pude buscar: {bus.error}</p>
          : !busItems.length && !bus.loading ? <p className="cp-vacio">No encontré nada con «{qd}». Prueba con otra palabra.</p>
          : <div className="cp-lista">{busItems.map(it => fila(it, undefined, it.folder ?? padre(it.path)))}</div>}
      </section>
      : <>
        {verRecientes && recItems.length > 0 && <section className="cp-seccion">
          <div className="cp-cab-lista"><div><h3>Recientes</h3></div></div>
          <div className="cp-tira">{recItems.map(it => <button key={it.path} className="cp-reciente" onClick={() => ver(it)}>
            <Ficha it={it} root="compartido" big /><strong>{it.name}</strong>
            <small>{it.origen === 'whatsapp' && <span className="cp-tag">por WhatsApp</span>}{relTime(it.mtime)}</small></button>)}</div>
        </section>}

        {ruta && <nav className="cp-migas" aria-label="Dónde estás"><button onClick={() => ir(root, '')}>{raizLabel}</button>
          {partes.map((p, i) => <Fragment key={i}><Icon name="chevron" size={14} /><button onClick={() => ir(root, partes.slice(0, i + 1).join('/'))} aria-current={i === partes.length - 1 ? 'page' : undefined}>{p}</button></Fragment>)}</nav>}

        <div className={`cp-barra ${ruta ? '' : 'raiz'}`}>
          <div className="cp-barra-top"><span className="cp-barra-ico"><Ic n={ICONO_CARPETA[base(ruta)] || 'folder'} size={22} /></span>
            <div className="cp-barra-txt"><strong>{ruta ? base(ruta) : raizLabel}</strong><small>{fresco ? cuenta(dirs.length, files.length) : roto ? 'No disponible' : 'Cargando…'}</small></div></div>
          {!roto && <div className="cp-barra-botones">
            {!soloLeer && <><button className="cp-subir" onClick={() => input.current?.click()}><Icon name="upload" size={18} /> Subir archivos</button>
            <button className="cp-boton" onClick={() => setNueva('')}><Icon name="plus" size={18} /> Nueva carpeta</button>
            <input ref={input} type="file" multiple className="visually-hidden" tabIndex={-1} aria-hidden="true" onChange={e => { elegirArchivos(e.target.files); e.target.value = '' }} /></>}
            {!inv && <CopiaZip href={urlZip(root, ruta)} avisar={root === 'compartido' && !ruta} className="cp-boton"><Icon name="download" size={18} /> Copia de seguridad (ZIP)</CopiaZip>}</div>}
        </div>
        {!inv && texto && !roto && <p className="cp-pista"><Ic n="idea" size={17} /> {texto}</p>}

        {nueva !== null && <form className="mini-form folder-create cp-nueva" onSubmit={e => void crear(e)}>
          <input autoFocus value={nueva} onChange={e => setNueva(e.target.value)} placeholder="Nombre de la carpeta" aria-label="Nombre de la carpeta nueva" maxLength={80} />
          <button type="button" className="mini-cancel" onClick={() => setNueva(null)} aria-label="Cancelar"><Icon name="close" size={17} /></button>
          <button type="submit" disabled={!nueva.trim()} aria-label="Crear carpeta"><Icon name="check" size={19} /></button></form>}
        {subida && <div className="cp-subida" role="status">Subiendo {subida.total > 1 ? `${subida.n} de ${subida.total}: ` : ''}«{subida.nombre}» · {subida.pct} %
          <span className="cp-progreso"><i style={{ width: `${subida.pct}%` }} /></span></div>}

        {lst.error && !fresco && <p className="cp-vacio" role="alert">No pude abrir esta carpeta: {lst.error}.{' '}
          <button className="text-link cp-en-linea" onClick={() => void lst.reload()}>Reintentar</button>{ruta && <> · <button className="text-link cp-en-linea" onClick={() => ir(root, '')}>Ir al principio</button></>}</p>}
        {!fresco && !lst.error && <p className="cp-vacio">Cargando…</p>}
        {fresco && !items.length && <p className="cp-vacio">{soloLeer ? 'Esta carpeta está vacía.' : 'Esta carpeta está vacía. Toca «Subir archivos» para añadir algo.'}</p>}

        {dirs.length > 0 && <div className="cp-carpetas">{dirs.map(d => <div className={`cp-carpeta ${toneOf(d.name)}`} key={d.path}>
          <button className="cp-carpeta-main" onClick={() => ir(root, d.path)}><Ic n={ICONO_CARPETA[d.name] || 'folder'} size={22} /><strong>{d.name}</strong>
            <small>{(escribe && !ruta && DESCR[d.name]) || (d.n === undefined ? relTime(d.mtime) : !d.n ? 'Vacía' : `${d.n} ${d.n === 1 ? 'elemento' : 'elementos'}`)}</small></button>
          {accionesDe(d).length > 1 && <button className="cp-mas" onClick={() => setMenu(d)} aria-label={`Más opciones: ${d.name}`}><Ic n="more" /></button>}
        </div>)}</div>}

        {files.length > 0 && <section className="cp-seccion">
          <div className="cp-cab-lista"><h3>Archivos</h3>
            <div className="cp-orden" role="group" aria-label="Ordenar">
              <button aria-pressed={orden === 'fecha'} onClick={() => cambiarOrden('fecha')}>Más nuevos</button>
              <button aria-pressed={orden === 'nombre'} onClick={() => cambiarOrden('nombre')}>A–Z</button></div></div>
          <div className="cp-lista">{files.slice(0, cuantos).map(it => fila(it, enRecibidos ? <button className="cp-guardar" onClick={() => setElegir({ items: [it], titulo: '¿Dónde lo guardo?' })}><Ic n="move" size={16} /> Guardar en…</button> : undefined))}</div>
          {files.length > cuantos && <button className="btn-secondary cp-ancho" onClick={() => setCuantos(c => c + PAGINA)}>Ver más ({files.length - cuantos})</button>}
        </section>}

        {escribe && !ruta && <button className="cp-ir-papelera" onClick={abrirPapelera}>
          <Ic n="trash" size={20} /><span><strong>Papelera</strong><small>Lo que quitas se guarda aquí 30 días</small></span><Icon name="chevron" size={18} /></button>}
      </>}

    {menu && <Hoja titulo={menu.name} sub={menu.dir ? 'Carpeta' : meta(menu)} onClose={() => setMenu(null)}>
      <div className="cp-menu">{accionesDe(menu).map(a => <button key={a} className={a === 'papelera' ? 'peligro' : ''} onClick={() => hacer(a, menu)}><Ic n={ACC[a].ico} /> {ACC[a].label}</button>)}</div>
      {escribe && protegido(menu.path) && <p className="cp-nota"><Ic n="lock" size={15} /> {menu.path.startsWith('Adjuntos') ? 'Adjuntos es del chat: aquí no se mueve ni se borra nada.' : 'Zazu usa esta carpeta: no se mueve ni se borra.'}</p>}
    </Hoja>}
    {vista && <Vista it={vista} root={root} nube={!inv && root === 'compartido'} donde={etiqueta(root, padre(vista.path))} acciones={accionesDe(vista).filter(a => a !== 'ver')} hacer={hacer} onClose={cerrarVista} />}
    {perdido && <Hoja titulo={base(archivo)} sub={`En ${etiqueta(root, ruta)}`} onClose={cerrarVista} atras={false}>
      <p className="cp-nota">Este archivo ya no está aquí. Puede que se moviera, le cambiaran el nombre o esté en la papelera.</p>
      {!inv && <button className="btn-primary cp-ancho" onClick={() => {
        const n = base(archivo).replace(/\.[^.]+$/, ''); cerrarVista(); setQ(n); document.querySelector('.app-content')?.scrollTo({ top: 0 })
      }}><Ic n="search" size={18} /> Buscarlo por su nombre</button>}
    </Hoja>}
    {elegir && <ElegirCarpeta titulo={elegir.titulo} items={elegir.items} desde={padre(elegir.items[0].path)} dejar={elegir.dejar} onClose={() => setElegir(null)} onElegir={d => void moverA(elegir.items, d)} />}
    {renom && <Renombrar it={renom} onClose={() => setRenom(null)} onHecho={p => {
      const viejo = renom.path; setRenom(null); recargar.current(); avisar({ texto: `Ahora se llama «${base(p)}»` })
      if (archivo === viejo) {   // la vista previa sigue abierta con el nombre nuevo; la URL se corrige cuando se quita la entrada de la hoja
        setRecien({ ...renom, name: base(p), path: p }); fijar({ ...posRef.current, archivo: p })
        trasHoja(() => { const c = posRef.current; if (c.archivo === p) irA({ tab: 'carpetas', ...c }, true) })
      }
    }} />}
    {grandes && <Hoja titulo="Pesa mucho" onClose={() => setGrandes(null)}>
      <ul className="cp-grandes">{grandes.filter(f => f.size > LIMITE_SUBIDA).map(f => <li key={f.name}><strong>{f.name}</strong> · {fmtSize(f.size)}</li>)}</ul>
      <p className="cp-nota">Por internet, lo que pasa de 100 MB suele fallar a mitad. ¿Lo intento igual?</p>
      <button className="btn-primary cp-ancho" onClick={() => void subirTodos(grandes)}>Intentarlo igual</button>
      {grandes.some(f => f.size <= LIMITE_SUBIDA) && <button className="btn-secondary cp-ancho" onClick={() => void subirTodos(grandes.filter(f => f.size <= LIMITE_SUBIDA))}>Subir solo los pequeños</button>}
      <button className="btn-secondary cp-ancho" onClick={() => setGrandes(null)}>Cancelar</button>
    </Hoja>}
    {listo && <Hoja titulo="Ya está listo" sub={listo.name} onClose={() => setListo(null)}>
      <button className="btn-primary cp-ancho" onClick={() => { const f = listo; setListo(null); navigator.share({ files: [f], title: f.name }).catch(() => { }) }}><Ic n="share" size={18} /> Compartir ahora</button>
    </Hoja>}
    {pend && <Hoja titulo={pend.length === 1 ? '¿Guardo lo que has compartido?' : `¿Guardo estos ${pend.length} archivos?`} sub="Con «Compartir › Zazu»" onClose={() => descartar(pend)}>
      <ul className="cp-grandes">{pend.map(p => <li key={p.key}><strong>{p.nombre}</strong> · {fmtSize(p.size)}</li>)}</ul>
      <p className="cp-nota">{llegada ? '' : 'Esto llegó con «Compartir › Zazu» y aún no lo has guardado. '}Si no lo has compartido tú, descártalo y no se guardará nada.</p>
      <button className="btn-primary cp-ancho" onClick={() => guardarCompartidos(pend)}><Ic n="inbox" size={18} /> {inv ? 'Guardar en Mis carpetas' : 'Guardar en Recibidos'}</button>
      <button className="btn-secondary cp-ancho" onClick={() => descartar(pend)}>Descartar</button>
    </Hoja>}
    <BarraAviso aviso={aviso} cerrar={() => setAviso(null)} />
  </div>
}
