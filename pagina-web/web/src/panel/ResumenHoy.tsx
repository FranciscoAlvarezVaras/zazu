/* Tarjeta «Hoy» (solo Fran, encima del día de hoy en la Agenda): el resumen que Zazu deja hecho a las 06:45
   (zazu/scripts/resumen-hoy.py), con ▶ Escuchar, y «¿Lo recuerdo?» con las lecciones que el aprendizaje propone (Sí / No). */
import { useRef, useState } from 'react'
import { irA, post, useFetch } from '../lib'

type Resumen = { ok: boolean; hoy?: boolean; texto: string | null; audio: boolean }
type Leccion = { id: number; texto: string }
type ItemIA = { titulo: string; url: string }
type Noticias = { ok: boolean; apartados: { clave: string; items: ItemIA[] }[] }

export default function ResumenHoy({ toast }: { toast: (m: string) => void }) {
  const r = useFetch<Resumen>('/api/resumen-hoy')
  const l = useFetch<{ items: Leccion[] }>('/api/lecciones')
  const n = useFetch<Noticias>('/api/noticias')
  const [abierto, setAbierto] = useState(false)
  const [sonando, setSonando] = useState(false)
  const [hechas, setHechas] = useState<number[]>([])
  const [ocupada, setOcupada] = useState(0)
  const audio = useRef<HTMLAudioElement>(null)
  const texto = r.data?.ok && r.data.hoy ? (r.data.texto || '') : ''   // el de otro día no se enseña
  const lecciones = (l.data?.items || []).filter(x => !hechas.includes(x.id))
  const ia = (n.data?.ok ? n.data.apartados.find(a => a.clave === 'ia')?.items : [])?.slice(0, 2) || []
  if (!texto && !lecciones.length) return null   // la línea de IA solo acompaña a la tarjeta; nunca la crea sola
  const largo = texto.length > 280

  function escuchar() {
    const a = audio.current; if (!a) return
    if (a.paused) a.play().then(() => setSonando(true)).catch(() => toast('No pude reproducir el audio'))
    else { a.pause(); setSonando(false) }
  }
  async function decidir(x: Leccion, si: boolean) {
    setOcupada(x.id)
    try { await post(`/api/lecciones/${x.id}/${si ? 'si' : 'no'}`, {}); setHechas(h => [...h, x.id]); toast(si ? 'Lo recordaré' : 'Descartada') }
    catch (e) { toast(`No se pudo guardar: ${(e as Error).message}`) } finally { setOcupada(0) }
  }

  return <section className="hz" aria-label="Resumen de hoy">
    {texto && <>
      <div className="hz-cab">
        <h2>Hoy</h2>
        {r.data?.audio && <>
          <button type="button" className="hz-oir" onClick={escuchar} aria-pressed={sonando}>{sonando ? '❚❚ Pausa' : '▶ Escuchar'}</button>
          <audio ref={audio} src="/api/resumen-hoy/audio" preload="none" onEnded={() => setSonando(false)} onPause={() => setSonando(false)} />
        </>}
      </div>
      <p className={`hz-texto ${largo && !abierto ? 'plegado' : ''}`}>{texto}</p>
      {largo && <button type="button" className="pz-enlace hz-mas" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>{abierto ? 'Ver menos' : 'Ver todo'}</button>}
    </>}
    {lecciones.length > 0 && <div className="hz-lec">
      <h3>¿Lo recuerdo?</h3>
      {lecciones.map(x => <div key={x.id} className="hz-lec-fila">
        <p>{x.texto}</p>
        <div className="hz-lec-acc">
          <button type="button" className="pz-btn pz-btn-primario" disabled={ocupada === x.id} onClick={() => void decidir(x, true)}>Sí, recuérdalo</button>
          <button type="button" className="pz-btn-fila" disabled={ocupada === x.id} onClick={() => void decidir(x, false)}>No</button>
        </div>
      </div>)}
    </div>}
    {ia.length > 0 && <div className="hz-ia">
      <h3>IA hoy</h3>
      <ul>{ia.map((x, i) => <li key={i}><a href={x.url} target="_blank" rel="noopener noreferrer">{x.titulo}</a></li>)}</ul>
      <button type="button" className="pz-enlace" onClick={() => irA({ tab: 'noticias' })}>Ver más noticias</button>
    </div>}
  </section>
}
