/* «Qué ha aprendido Zazu»: el mapa de lecciones (reglas, datos tuyos, habilidades posibles) con su evidencia, y aprobar o retirar cada una.
   Idea: el «IDE de la lógica» de David Ragel Díaz-Jara (un texto convertido en un grafo que se puede mirar y corregir), aquí aplicado a lo que Zazu aprende.
   Aprobar una lección NO cambia lo que hace Zazu: la guarda como válida. Aplicarla es un paso aparte que decides tú (se dice en la pantalla). */
import { useState } from 'react'
import { irA, post, useFetch } from '../lib'
import type { Ctx } from '../ctx'
import { Esqueleto, Fallo, Hoja, Icono, plural } from './ui'
import './aprendido.css'

type Estado = 'propuesta' | 'aprobada' | 'rechazada'
type Tipo = 'regla' | 'dato' | 'habilidad'
type Evidencia = { fecha: string; perfil: string; tipo: string; texto: string }
export type Leccion = { id: number; texto: string; corto: string; tipo: Tipo; estado: Estado; origen: string; fecha: string; decidida: string; pruebas: number; asistentes: string[]; evidencia: Evidencia[] }
type Datos = { ok: boolean; resumen: { total: number; estado: Record<string, number> }; lecciones: Leccion[] }

const RAMAS: { id: Tipo; titulo: string; sub: string }[] = [
  { id: 'regla', titulo: 'Cómo debe actuar', sub: 'reglas que sacó de tus correcciones' },
  { id: 'dato', titulo: 'Lo que sabe de ti', sub: 'datos que dijiste y son duraderos' },
  { id: 'habilidad', titulo: 'Lo que podría saber hacer', sub: 'cosas que pides una y otra vez' }]
const ORIGEN: Record<string, string> = { claude: 'Propuesta en una sesión de trabajo', 'reflexion-nocturna': 'Reflexión de la noche sobre tus correcciones',
  'hechos-conversacion': 'Dato sacado de tus conversaciones', habilidades: 'Algo que pides una y otra vez' }
const ESTADO: Record<Estado, string> = { propuesta: 'Por decidir', aprobada: 'Aprobada', rechazada: 'Rechazada' }
const ASISTENTE = (p: string) => p === 'default' ? 'Zazu' : p === 'tecnico' ? 'Zazu técnico' : p
type Filtro = 'todas' | Estado
const FILTROS: [Filtro, string][] = [['todas', 'Todas'], ['propuesta', 'Por decidir'], ['aprobada', 'Aprobadas'], ['rechazada', 'Rechazadas']]
const diaLargo = (f: string) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(f); return m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('es-ES', { day: 'numeric', month: 'long' }) : f }

function Detalle({ l, cerrar, decidir, ocupado }: { l: Leccion; cerrar: () => void; decidir: (id: number, a: 'aprobar' | 'rechazar' | 'reabrir') => void; ocupado: boolean }) {
  return <Hoja titulo={RAMAS.find(r => r.id === l.tipo)?.titulo || 'Lección'} cerrar={cerrar}>
    <div className="pz-ap-det">
      <p className={`pz-ap-estado ${l.estado}`}>{ESTADO[l.estado]}{l.decidida ? ` · ${diaLargo(l.decidida)}` : ''}</p>
      <p className="pz-ap-texto">{l.texto}</p>
      <p className="pz-nota">{ORIGEN[l.origen] || l.origen} · {diaLargo(l.fecha)}{l.asistentes.length ? ` · ${l.asistentes.map(ASISTENTE).join(', ')}` : ''}</p>
      <h3>Por qué</h3>
      {l.evidencia.length ? <ul className="pz-ap-ev">{l.evidencia.map((e, i) => <li key={i}><span className="pz-ap-ev-meta">{diaLargo(e.fecha)} · {ASISTENTE(e.perfil) || 'Zazu'}{e.tipo === 'correccion' ? ' · te quejaste' : ''}</span><span>«{e.texto}»</span></li>)}</ul>
        : <p className="pz-nota">No guardó mensajes concretos como prueba.</p>}
      {l.pruebas > l.evidencia.length && <p className="pz-nota">Y {plural(l.pruebas - l.evidencia.length, 'prueba más', 'pruebas más')}.</p>}
      <div className="pz-ap-acc">
        {l.estado === 'propuesta' && <><button type="button" className="pz-btn pz-btn-primario" disabled={ocupado} onClick={() => decidir(l.id, 'aprobar')}><Icono n="check" size={16} /> Aprobar</button>
          <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado} onClick={() => decidir(l.id, 'rechazar')}>Rechazar</button></>}
        {l.estado === 'aprobada' && <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado} onClick={() => decidir(l.id, 'rechazar')}>Ya no vale</button>}
        {l.estado === 'rechazada' && <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado} onClick={() => decidir(l.id, 'reabrir')}>Volver a pensarla</button>}
      </div>
    </div>
  </Hoja>
}

export default function Aprendido({ toast }: Ctx) {
  const d = useFetch<Datos>('/api/aprendido')
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const [abierta, setAbierta] = useState<number | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const todas = d.data?.lecciones ?? []
  const n = d.data?.resumen.estado ?? {}
  const visibles = todas.filter(l => filtro === 'todas' || l.estado === filtro)
  const sel = todas.find(l => l.id === abierta) || null

  const decidir = async (id: number, accion: 'aprobar' | 'rechazar' | 'reabrir') => {
    setOcupado(true)
    try { await post('/api/aprendido/decidir', { id, accion }); toast(accion === 'aprobar' ? 'Aprobada' : accion === 'rechazar' ? 'Rechazada' : 'Vuelve a estar por decidir'); setAbierta(null); await d.reload() }
    catch (e) { toast(`No pude guardar tu decisión: ${(e as Error).message}`) }
    finally { setOcupado(false) }
  }

  return <div className="pz-page pz-ap">
    <header className="pz-cab-pag"><div><p className="pz-eyebrow">LO QUE APRENDE ZAZU</p><h1>Qué ha aprendido</h1></div>
      <button type="button" className="pz-btn pz-btn-suave" onClick={() => irA({ tab: 'zazu' })}>Volver a Zazu</button></header>
    <p className="pz-nota pz-ap-aviso" role="note"><b>Aprobar no cambia todavía lo que hace Zazu.</b> Una lección aprobada queda guardada como válida; aplicarla a su memoria o a una habilidad es el paso siguiente, y lo decides tú.</p>
    {!d.data && d.loading && <Esqueleto filas={4} alto={72} />}
    {!d.data && !d.loading && d.error && <Fallo texto={`No pude leer las lecciones: ${d.error}.`} reintentar={() => void d.reload()} />}
    {d.data && <>
      <div className="pz-chips" role="group" aria-label="Filtrar lecciones">
        {FILTROS.map(([id, t]) => <button key={id} type="button" aria-pressed={filtro === id} onClick={() => setFiltro(id)}>{t}{id !== 'todas' && n[id] ? ` · ${n[id]}` : ''}{id === 'todas' ? ` · ${d.data!.resumen.total}` : ''}</button>)}
      </div>
      {!todas.length && <p className="pz-vacio">Zazu todavía no ha propuesto ninguna lección. Cada noche mira tus correcciones y propone las que ve claras.</p>}
      {todas.length > 0 && <div className="pz-ap-mapa">
        <div className="pz-ap-raiz"><span className="pz-ap-raiz-pun" aria-hidden="true" />Zazu<small>{plural(d.data.resumen.total, 'lección', 'lecciones')}</small></div>
        <div className="pz-ap-ramas">
          {RAMAS.map(r => { const hojas = visibles.filter(l => l.tipo === r.id); const total = todas.filter(l => l.tipo === r.id).length
            return <section key={r.id} className="pz-ap-rama" aria-label={r.titulo}>
              <header className="pz-ap-rama-cab"><b>{r.titulo}</b><span>{total}</span><small>{r.sub}</small></header>
              {hojas.length ? <ul className="pz-ap-hojas">{hojas.map(l => <li key={l.id}>
                <button type="button" className={`pz-ap-hoja ${l.estado}`} onClick={() => setAbierta(l.id)} aria-label={`${ESTADO[l.estado]}: ${l.corto}`}>
                  <span className="pz-ap-txt">{l.corto}</span>
                  <span className="pz-ap-meta">{ESTADO[l.estado]}{l.pruebas ? ` · ${plural(l.pruebas, 'prueba', 'pruebas')}` : ''}</span></button></li>)}</ul>
                : <p className="pz-nota pz-ap-vacia">{total ? 'Ninguna con este filtro.' : 'Aún nada aquí.'}</p>}
            </section> })}
        </div>
      </div>}
    </>}
    {sel && <Detalle l={sel} cerrar={() => setAbierta(null)} decidir={(i, a) => void decidir(i, a)} ocupado={ocupado} />}
  </div>
}
