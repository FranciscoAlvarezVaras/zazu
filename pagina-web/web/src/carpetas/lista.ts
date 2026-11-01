import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib'
import { medioDe, msg } from './nube'
import type { Medio, Orden } from './nube'
import { colocar, enFavoritos, siguienteDesde } from './posicion'

export const PAGINA = 90   // de 90 en 90: son ~33.000 elementos

/** La lista paginada de fotos y vídeos que enseña la cuadrícula. Los cambios (favorito, quitar, volver tras Deshacer, subir) se hacen aquí mismo,
 *  sin volver a pedir nada: así no se pierde el sitio de la pantalla ni se espera al índice del servidor, que se renueva cada minuto. */
export function useLista(consulta: string, orden: Orden) {
  const [items, setItems] = useState<Medio[]>([])
  const [total, setTotal] = useState(0)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const seq = useRef(0), vuelo = useRef('')   // vuelo: la petición que va en camino (la misma no se repite)
  const q = useRef(consulta); q.current = consulta
  const o = useRef(orden); o.current = orden
  const ref = useRef(items); ref.current = items   // siempre la última, también dentro de funciones que llegan tarde
  const tot = useRef(total); tot.current = total   // para saber si aún falta algo por cargar
  const salieron = useRef(new Set<string>())   // las que han salido de lo cargado (papelera, álbum…): si vuelven, vuelven a su sitio aunque sea el último

  /** `desde`: por omisión, donde acaba lo ya cargado según el servidor (items.length no vale: lo subido a mano o lo desmarcado en Favoritos descolocan la cuenta) */
  const pedir = useCallback(async (desde?: number) => {
    if (desde === undefined) desde = siguienteDesde(ref.current, enFavoritos(q.current))
    const clave = `${q.current}|${desde}`
    if (vuelo.current === clave) return
    vuelo.current = clave
    const n = ++seq.current   // solo cuenta la respuesta más reciente
    setCargando(true)
    try {
      const d = await api<{ items?: unknown; total?: unknown }>(`/api/nube/medios?${[q.current, `desde=${desde}`, `n=${PAGINA}`].filter(Boolean).join('&')}`)
      if (n !== seq.current) return
      const nuevos = (Array.isArray(d.items) ? d.items : []).map(medioDe).filter((m): m is Medio => !!m)
      if (!desde) { ref.current = nuevos; setItems(nuevos); setTotal(typeof d.total === 'number' ? d.total : nuevos.length) }
      else {
        const vistos = new Set(ref.current.map(m => m.path))   // si el índice cambió entre páginas, no se repite nada
        const mas = nuevos.filter(m => !vistos.has(m.path))
        const todo = [...ref.current, ...mas]
        ref.current = todo; setItems(todo)
        setTotal(mas.length && typeof d.total === 'number' ? d.total : todo.length)   // una página sin nada nuevo: se acabó (así no se pide sin fin)
      }
      setError('')
    } catch (e) { if (n === seq.current) setError(msg(e)) } finally { if (vuelo.current === clave) vuelo.current = ''; if (n === seq.current) setCargando(false) }
  }, [])
  useEffect(() => { ref.current = []; salieron.current.clear(); setItems([]); setTotal(0); setError(''); void pedir(0) }, [consulta, pedir])

  /** Fuera de la lista (a la papelera, quitada del álbum…) */
  const quitar = useCallback((paths: Iterable<string>) => {
    const s = new Set(paths), fuera = ref.current.filter(m => s.has(m.path))
    if (!fuera.length) return fuera
    const resto = ref.current.filter(m => !s.has(m.path))
    fuera.forEach(m => salieron.current.add(m.path))
    const contaban = enFavoritos(q.current) ? fuera.filter(m => m.fav).length : fuera.length   // en Favoritos, lo desmarcado ya no contaba: poner() lo restó
    ref.current = resto; setItems(resto); setTotal(t => Math.max(0, t - contaban))
    return fuera   // tal como estaban al salir (con su corazón): Duplicados lo necesita para el Deshacer
  }, [])
  /** De vuelta en su sitio según el orden de ahora (Deshacer) o recién subidas */
  const insertar = useCallback((ms: Medio[]) => {
    const { lista, puestos } = colocar(ref.current, ms, o.current, ref.current.length < tot.current, p => salieron.current.has(p))
    if (!puestos.length) return
    ref.current = lista; setItems(lista); setTotal(x => x + puestos.length)
  }, [])
  /** Favorito sí/no por ruta (se pinta al momento; si el servidor falla, se vuelve a llamar con los valores de antes) */
  const poner = useCallback((cambios: Map<string, boolean>) => {
    let dif = 0
    const a = ref.current.map(m => { if (!cambios.has(m.path) || m.fav === cambios.get(m.path)) return m; dif += cambios.get(m.path) ? 1 : -1; return { ...m, fav: !!cambios.get(m.path) } })
    ref.current = a; setItems(a)
    if (dif && enFavoritos(q.current)) setTotal(t => Math.max(0, t + dif))   // en Favoritos el servidor ya no lista lo desmarcado (ni deja de listar lo que se vuelve a marcar)
  }, [])

  return { items, total, cargando, error, pedir, quitar, insertar, poner, ref }
}
