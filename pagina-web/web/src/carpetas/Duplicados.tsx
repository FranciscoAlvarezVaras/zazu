import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../icons'
import { fmtSize } from '../lib'
import { etiqueta, itemDe, kindOf, padre, protegido } from './api'
import { Ficha, Hoja, Ic } from './ui'
import type { Aviso } from './ui'
import { fecha, mini, msg, num, plural, restaurarTodos, tirarTodos, verDuplicados } from './nube'
import type { Copia, Duplicados, Medio, Tirada } from './nube'

let sucio = false   // se quitaron o devolvieron copias: el servidor guarda el último resultado una hora, así que se vuelve a calcular
type Viva = { clave: string; size: number; items: Copia[]; queda: string; quitables: Copia[] }
const esMedio = (nombre: string) => ['image', 'video'].includes(kindOf(nombre))

/** Lo que llegó del servidor, con la forma que espera la pantalla (un grupo raro no la rompe) */
function normal(x: Duplicados): Duplicados {
  const grupos = (Array.isArray(x.grupos) ? x.grupos : []).map(g => ({ size: Number(g?.size) || 0, items: (Array.isArray(g?.items) ? g.items : []).filter(i => i && typeof i.path === 'string').map(i => ({ path: i.path, name: i.name || i.path.split('/').pop() || i.path, mtime: Number(i.mtime) || 0 })) })).filter(g => g.items.length > 1)
  return { estado: x.estado === 'listo' || x.estado === 'error' ? x.estado : 'calculando', grupos, ahorro: Number(x.ahorro) || 0, vistos: Number(x.vistos) || 0, total: Number(x.total) || grupos.length }
}

/** Buscar copias repetidas (en segundo plano en el servidor), ver cuál se queda y mandar el resto a la papelera, con Deshacer */
export function DuplicadosHoja({ avisar, onClose, alQuitar, alVolver }: { avisar: (a: Aviso) => void; onClose: () => void; alQuitar: (paths: string[]) => void; alVolver: (ms: Medio[]) => void }) {
  const [d, setD] = useState<Duplicados | null>(null)
  const [err, setErr] = useState('')
  const [busca, setBusca] = useState({ n: 0, rehacer: false })   // otra búsqueda: reintentar tras un fallo, o «Volver a buscar» (rehacer)
  const [hechas, setHechas] = useState<Set<string>>(new Set())   // las que ya están en la papelera
  const [conserva, setConserva] = useState<Map<string, string>>(new Map())   // la copia que Fran quiere que se quede, por cualquier ruta del grupo
  const [trabajo, setTrabajo] = useState<{ hecho: number; total: number } | null>(null)
  const [confirmar, setConfirmar] = useState(false)
  const parar = useRef(false)

  useEffect(() => {
    let vivo = true, t = 0
    const ver = async (rehacer: boolean) => {
      try {
        const x = await verDuplicados(rehacer)
        if (!vivo) return
        const n = normal(x)
        setD(n); setErr('')
        if (n.estado === 'calculando') t = window.setTimeout(() => void ver(false), 2500)   // se mira cada poco hasta que acabe
      } catch (e) { if (vivo) setErr(msg(e)) }
    }
    void ver(busca.rehacer || sucio); sucio = false
    return () => { vivo = false; clearTimeout(t) }
  }, [busca])

  const vivas = useMemo<Viva[]>(() => (d?.grupos || []).map(g => {
    const items = g.items.filter(i => !hechas.has(i.path))
    const elegida = items.map(i => conserva.get(i.path)).find(p => p && items.some(i => i.path === p))
    const queda = elegida || items[0]?.path || ''
    return { clave: g.items[0].path, size: g.size, items, queda, quitables: items.filter(i => i.path !== queda && !protegido(i.path)) }   // lo de Adjuntos lo usan el chat y las notas
  }).filter(g => g.items.length > 1), [d, hechas, conserva])
  const copias = vivas.reduce((a, g) => a + g.quitables.length, 0)
  const bytes = vivas.reduce((a, g) => a + g.size * g.quitables.length, 0)

  function conservar(g: Viva, ruta: string) {
    setConserva(c => { const n = new Map(c); g.items.forEach(i => n.set(i.path, ruta)); return n })
  }
  async function quitar(gs: Viva[]) {
    const lista = gs.flatMap(g => g.quitables.map(c => ({ ...c, size: g.size })))
    if (!lista.length) return
    parar.current = false; setConfirmar(false); setTrabajo({ hecho: 0, total: lista.length })
    const { hechos, fallos } = await tirarTodos(lista.map(c => c.path), hecho => setTrabajo({ hecho, total: lista.length }), parar)
    setTrabajo(null)
    if (hechos.length) {
      sucio = true
      setHechas(s => new Set([...s, ...hechos.map(h => h.path)]))
      alQuitar(hechos.map(h => h.path))
    }
    const resto = fallos.length ? ` · ${plural(fallos.length, 'no se pudo quitar', 'no se pudieron quitar')} (${fallos[0].error})` : ''
    if (!hechos.length) return avisar({ texto: `No se pudo quitar nada: ${fallos[0]?.error || 'se paró antes de empezar'}.` })
    avisar({ texto: `${plural(hechos.length, 'copia está', 'copias están')} en la papelera${resto}.`, accion: { label: 'Deshacer', fn: () => void deshacer(hechos, lista) } })
  }
  async function deshacer(hechos: Tirada[], lista: (Copia & { size: number })[]) {
    const { vueltos, fallos } = await restaurarTodos(hechos)
    sucio = true
    const vuelven = new Set(vueltos.map(v => v.path))
    setHechas(s => new Set([...s].filter(p => !vuelven.has(p))))
    alVolver(lista.filter(c => vuelven.has(c.path) && esMedio(c.name)).map(c => {
      const nuevo = vueltos.find(v => v.path === c.path)!.nuevo
      return { path: nuevo, name: nuevo.split('/').pop() || c.name, size: c.size, mtime: c.mtime, kind: kindOf(c.name) === 'video' ? 'video' : 'image', fav: false }
    }))
    avisar({ texto: fallos ? `Volvieron ${plural(vueltos.length, 'copia', 'copias')}; ${plural(fallos, 'no se pudo recuperar', 'no se pudieron recuperar')}.` : `${plural(vueltos.length, 'copia ha vuelto', 'copias han vuelto')} a su sitio.` })
  }

  const calculando = !err && (!d || d.estado === 'calculando')
  const total = d?.grupos.length || 0
  return <Hoja titulo="Duplicados" sub="Fotos y archivos repetidos" ancha onClose={onClose}>
    {err && <p className="cp-vacio" role="alert">No pude buscar duplicados: {err}. <button type="button" className="text-link cp-en-linea" onClick={() => { setErr(''); setBusca(b => ({ n: b.n + 1, rehacer: false })) }}>Reintentar</button></p>}
    {calculando && <div className="nube-calculando" role="status"><span className="nube-giro" aria-hidden="true" />
      <div><strong>Calculando…</strong><p>Comparo tus archivos uno a uno. Con tantas fotos puede tardar unos minutos: puedes cerrar esto y volver luego, seguirá en marcha.</p></div></div>}
    {d?.estado === 'error' && <p className="cp-vacio" role="alert">No pude terminar la búsqueda. <button type="button" className="text-link cp-en-linea" onClick={() => { setD(null); setBusca(b => ({ n: b.n + 1, rehacer: true })) }}>Probar otra vez</button></p>}
    {d?.estado === 'listo' && !vivas.length && <div className="nube-sin-dup" role="status"><Icon name="check" size={30} />
      <strong>{total ? 'Ya no queda ninguna copia por quitar' : 'No tienes archivos repetidos'}</strong>
      <p>{total ? 'Lo que no se puede quitar (Adjuntos es del chat) se queda como está.' : `He revisado ${num(d.vistos)} archivos y no hay dos iguales.`}</p></div>}
    {d?.estado === 'listo' && vivas.length > 0 && <>
      <div className="nube-dup-resumen"><div><strong>{plural(copias, 'copia', 'copias')} · {fmtSize(bytes)} recuperables</strong>
        <small>De cada grupo se queda una; el resto va a la papelera y se puede recuperar durante 30 días.</small></div>
        {copias > 0 && !trabajo && !confirmar && <button type="button" className="btn-primary nube-peligro" onClick={() => setConfirmar(true)}><Ic n="trash" size={18} /> Quitar todas las copias</button>}</div>
      {confirmar && <div className="nube-confirma" role="group" aria-label="Confirmar">
        <p><strong>¿Mandar {plural(copias, 'copia', 'copias')} a la papelera?</strong> Son {fmtSize(bytes)}. En cada grupo se queda la que pone «Se queda».</p>
        <div className="cp-botones"><button type="button" className="btn-secondary" autoFocus onClick={() => setConfirmar(false)}>No, cancelar</button>
          <button type="button" className="btn-primary nube-peligro" onClick={() => void quitar(vivas)}>Sí, quitar todas</button></div></div>}
      {trabajo && <div className="cp-subida" role="status">Quitando {num(trabajo.hecho)} de {num(trabajo.total)}…
        <span className="cp-progreso"><i style={{ width: `${Math.round(trabajo.hecho / trabajo.total * 100)}%` }} /></span>
        <button type="button" className="btn-secondary nube-parar" onClick={() => { parar.current = true }}>Parar</button></div>}
      {(d.total ?? total) > total && <p className="cp-nota"><Ic n="idea" size={15} /> Aquí salen los {num(total)} grupos que más espacio ahorran, de {num(d.total ?? total)} que hay (en total, {fmtSize(d.ahorro)} por recuperar). Cuando termines, vuelve a buscar para ver más.</p>}
      <div className="nube-dups">{vivas.map(g => <article className="nube-dup" key={g.clave}>
        <div className="nube-dup-fotos" role="group" aria-label="Copias iguales: toca la que quieras conservar">{g.items.map(i => <button type="button" key={i.path} className={`nube-dup-it${g.queda === i.path ? ' queda' : ''}`}
          aria-pressed={g.queda === i.path} disabled={!!trabajo} onClick={() => conservar(g, i.path)}>
          <span className="nube-dup-mini">{esMedio(i.name) ? <img src={mini(i.path)} alt="" loading="lazy" decoding="async" onError={e => { e.currentTarget.style.visibility = 'hidden' }} /> : <Ficha it={itemDe(i.path)} root="compartido" foto={false} />}
            {g.queda === i.path && <em>Se queda</em>}</span>
          <small><strong>{i.name}</strong>{etiqueta('compartido', padre(i.path))}{i.mtime ? ` · ${fecha(i.mtime)}` : ''}</small></button>)}</div>
        <div className="nube-dup-pie"><span>{plural(g.items.length, 'copia igual', 'copias iguales')} · {fmtSize(g.size)} cada una{g.items.length - 1 > g.quitables.length ? ' · algunas están en Adjuntos y no se tocan' : ''}</span>
          <button type="button" className="btn-secondary" disabled={!g.quitables.length || !!trabajo} onClick={() => void quitar([g])}><Ic n="trash" size={16} /> Quitar {plural(g.quitables.length, 'copia', 'copias')}</button></div>
      </article>)}</div></>}
    {d && d.estado !== 'calculando' && !trabajo && <button type="button" className="btn-secondary cp-ancho" onClick={() => { setD(null); setHechas(new Set()); setConserva(new Map()); setConfirmar(false); setBusca(b => ({ n: b.n + 1, rehacer: true })) }}>Volver a buscar</button>}
  </Hoja>
}
