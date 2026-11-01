/* Hoja «Esto es lo que voy a apuntar»: la comparten la barra de órdenes de «Mi día» y el formulario «Añadir tarea» de Tareas.
   useOrden() lleva el estado (entendiendo → propuesta → apuntando) y <HojasOrden> pinta lo que toque. Nada se guarda hasta «Confirmar»;
   lo que no es una orden de organizador se abre en el chat con Zazu (o, desde Tareas, se puede guardar tal cual como tarea). */
import { useEffect, useRef, useState } from 'react'
import { confirmar, ErrorApi, proponer } from './api'
import type { Elemento, Propuesta, Respuesta, Resultado } from './api'
import { Hoja, Icono } from './ui'

export const TIPO: Record<string, string> = { nota: 'Nota', idea: 'Idea', tarea: 'Tarea', evento: 'Cita', aplicar: 'Candidatura', investigar: 'Por investigar', proyecto: 'Proyecto',
  completar: 'Marcar como hecha', reprogramar: 'Cambiar el día' }
const ESPERA_MAX_MS = 40000   // el servidor espera al modelo ≤ 30 s: pasado esto se corta y se dice

export type Fase = null | { k: 'pensando' } | { k: 'resp'; r: Respuesta } | { k: 'creando'; p: Propuesta; marcados: number[]; error?: string; fallos?: Resultado['fallos'] } | { k: 'fallo'; texto: string }

export function textoApuntado(r: Resultado): string {
  if (r.creados.length > 1) return `Apuntadas ${r.creados.length} cosas`
  const c = r.creados[0]
  if (!c) return 'Hecho'
  if (c.tipo === 'completar') return `Marcada como hecha: ${c.titulo}`
  if (c.tipo === 'reprogramar') return `Día cambiado: ${c.titulo}`
  return `Apuntado en ${c.donde}${c.id ? ` #${c.id}` : ''}: ${c.titulo}`
}

export function useOrden({ toast, alApuntar }: { toast: (m: string) => void; alApuntar: () => void }) {
  const [fase, setFase] = useState<Fase>(null)
  const ctl = useRef<AbortController | null>(null)
  const corte = useRef<number | undefined>(undefined)
  const ocupado = fase?.k === 'pensando' || (fase?.k === 'creando' && !fase.error)
  useEffect(() => () => { ctl.current?.abort(); window.clearTimeout(corte.current) }, [])

  async function enviar(texto: string) {
    const t = texto.trim()
    if (!t || ocupado) return
    const c = new AbortController(); ctl.current = c
    let tardo = false
    window.clearTimeout(corte.current)
    corte.current = window.setTimeout(() => { tardo = true; c.abort() }, ESPERA_MAX_MS)
    setFase({ k: 'pensando' })
    try {
      const r = await proponer(t, c.signal)
      if (!c.signal.aborted) setFase({ k: 'resp', r })
    } catch (e) {
      if (c.signal.aborted || (e instanceof ErrorApi && e.status === -1)) setFase(tardo ? { k: 'fallo', texto: 'Zazu tardó demasiado en entenderlo. Prueba otra vez o escríbelo más sencillo.' } : null)
      else setFase({ k: 'fallo', texto: (e as Error).message })
    } finally { window.clearTimeout(corte.current); if (ctl.current === c) ctl.current = null }
  }
  function cancelar() { ctl.current?.abort(); setFase(null) }
  /** `marcados` = posiciones de las cosas marcadas. */
  async function aceptar(p: Propuesta, marcados: number[]) {
    if (fase?.k === 'creando' && !fase.error) return
    setFase({ k: 'creando', p, marcados })
    try {
      const r = await confirmar(p.id, p.items.length > 1 || marcados.length !== 1 ? marcados : undefined)
      if (r.fallos.length) {
        toast(textoApuntado(r)); alApuntar()
        setFase({ k: 'creando', p, marcados: r.fallos.map(f => f.indice), error: 'No pude apuntar todo. Lo que falta se puede reintentar.', fallos: r.fallos })
        return
      }
      setFase(null)
      toast(textoApuntado(r)); alApuntar()
    } catch (e) {
      const caducada = e instanceof ErrorApi && e.status === 410
      setFase({ k: 'creando', p: caducada ? { ...p, confirmable: false, items: p.items.map(i => ({ ...i, confirmable: false })) } : p, marcados, error: (e as Error).message })
    }
  }
  return { fase, setFase, ocupado, enviar, cancelar, aceptar, cerrar: () => setFase(null) }
}
export type Orden = ReturnType<typeof useOrden>

/** «Entendiendo…» con Cancelar: se ve mientras el modelo piensa (hasta ~30 s). */
export function Entendiendo({ o }: { o: Orden }) {
  if (o.fase?.k !== 'pensando') return null
  return <div className="pz-entendiendo" role="status" aria-live="polite">
    <span className="pz-girando" aria-hidden="true" /><span>Entendiendo lo que escribiste…</span>
    <button type="button" className="pz-btn pz-btn-texto" onClick={o.cancelar}>Cancelar</button>
  </div>
}

function Fila({ it, marcado, alternar, bloqueado, multi }: { it: Elemento; marcado: boolean; alternar: () => void; bloqueado: boolean; multi: boolean }) {
  const cuerpo = <>
    <span className="pz-etiqueta pz-etiqueta-sec">{TIPO[it.tipo] || 'Apunte'}</span>
    <span className={multi ? 'pz-fila-res' : 'pz-propuesta-res'}>{it.resumen}</span>
    <span className="pz-meta">{it.destinoTxt}</span>
    {it.relacionado && <span className="pz-relacionado">Relacionado con: {it.relacionado.etiqueta}</span>}
    {it.aviso && <span className={`pz-propuesta-aviso ${it.duplicado ? 'dup' : it.confirmable ? '' : 'mal'}`} role="note">{it.aviso}</span>}
    {!it.confirmable && !it.aviso && <span className="pz-propuesta-aviso mal" role="note">Falta algún dato para poder apuntarlo. Pulsa Editar.</span>}
  </>
  if (!multi) return <div className="pz-propuesta">{cuerpo}</div>
  return <li className="pz-fila-ord"><label className={`pz-fila-lab ${!it.confirmable ? 'apagada' : ''}`}>
    <input type="checkbox" checked={marcado && it.confirmable} disabled={!it.confirmable || bloqueado} onChange={alternar} />
    <span className="pz-fila-cuerpo">{cuerpo}</span></label></li>
}

function HojaPropuesta({ o, p, editar }: { o: Orden; p: Propuesta; editar: () => void }) {
  const creando = o.fase?.k === 'creando' ? o.fase : null
  const multi = p.items.length > 1
  // marcadas desde el principio: lo que se puede apuntar (y, si son varias, sin lo que parece repetido)
  const [marcadas, setMarcadas] = useState<number[]>(() => p.items.flatMap((i, n) => i.confirmable && (!multi || !i.duplicado) ? [n] : []))
  const [vistos, setVistos] = useState(creando?.marcados)
  if (creando && creando.marcados !== vistos) { setVistos(creando.marcados); if (creando.error) setMarcadas(creando.marcados) }   // tras un fallo parcial: solo lo que falló
  const quedan = creando?.fallos ? new Set(creando.fallos.map(f => f.indice)) : null
  const bloqueado = !!creando && !creando.error
  const sel = marcadas.filter(n => p.items[n]?.confirmable)
  const alternar = (n: number) => setMarcadas(m => m.includes(n) ? m.filter(x => x !== n) : [...m, n])
  const n = sel.length
  const etiqueta = creando?.error ? 'Reintentar' : creando ? 'Apuntando…' : multi ? (n === 1 ? 'Apuntar 1 cosa' : `Apuntar ${n} cosas`) : p.tipo === 'completar' ? 'Marcar como hecha' : p.tipo === 'reprogramar' ? 'Cambiar el día' : 'Confirmar'
  return <Hoja titulo={multi ? `Esto es lo que voy a apuntar (${p.items.length})` : p.tipo === 'completar' || p.tipo === 'reprogramar' ? 'Esto es lo que voy a cambiar' : 'Esto es lo que voy a apuntar'} id="prop" cerrar={() => { if (!bloqueado) o.cerrar() }}>
    {multi
      ? <ul className="pz-filas-ord">{p.items.map((it, i) => (!quedan || quedan.has(i)) && <Fila key={i} it={it} multi marcado={marcadas.includes(i)} alternar={() => alternar(i)} bloqueado={bloqueado} />)}</ul>
      : <Fila it={p.items[0]} multi={false} marcado alternar={() => {}} bloqueado={bloqueado} />}
    {p.avisoGeneral && <p className="pz-propuesta-aviso" role="note">{p.avisoGeneral}</p>}
    {creando?.error && <div className="pz-fallo" role="alert"><span>{creando.error}{creando.fallos?.map(f => ` ${f.error}`).join('')}</span></div>}
    <p className="pz-ia">{p.entendidoCon === 'haiku' ? 'Lo entendí con IA' : 'Lo entendí con reglas'}</p>
    <div className="pz-hoja-acc">
      <button type="button" className="pz-btn pz-btn-primario" data-foco disabled={bloqueado || (multi ? n === 0 : !p.confirmable)} onClick={() => void o.aceptar(p, multi ? sel : [0])}>
        <Icono n="check" size={17} /> {etiqueta}</button>
      <button type="button" className="pz-btn pz-btn-suave" onClick={editar} disabled={bloqueado}>Editar</button>
      <button type="button" className="pz-btn pz-btn-texto" onClick={o.cerrar} disabled={bloqueado}>Cancelar</button>
    </div>
    <p className="pz-nota">Hasta que confirmes, no se guarda nada.</p>
  </Hoja>
}

type Props = {
  o: Orden; texto: string
  /** Vuelve al campo de texto para corregir la orden. */
  editar: () => void
  /** Tras apuntar o descartar: vaciar el texto. */
  limpiar: () => void
  abrirChat: (texto: string) => void
  /** Solo en Tareas: guarda el texto tal cual como tarea (lo que se hacía antes). */
  guardarTalCual?: (texto: string) => Promise<void>
}

export function HojasOrden({ o, texto, editar, limpiar, abrirChat, guardarTalCual }: Props) {
  const fase = o.fase
  const [guardando, setGuardando] = useState(false)
  const resp = fase?.k === 'resp' ? fase.r : null
  const prop = resp?.k === 'propuesta' ? resp.p : fase?.k === 'creando' ? fase.p : null
  // al apuntar del todo la hoja desaparece (fase → null): el texto de la barra se vacía aquí, al ver que se cerró tras un «creando» sin error
  const antes = useRef<Fase>(null)
  useEffect(() => { if (antes.current?.k === 'creando' && !antes.current.error && fase === null) limpiar(); antes.current = fase }, [fase]) // eslint-disable-line react-hooks/exhaustive-deps
  async function talCual() {
    if (!guardarTalCual) return
    setGuardando(true)
    try { await guardarTalCual(texto); o.cerrar(); limpiar() } catch { /* el aviso lo da quien llama */ } finally { setGuardando(false) }
  }
  return <>
    {fase?.k === 'pensando' && <p className="pz-oculto" role="status">Entendiendo lo que escribiste…</p>}
    {prop && <HojaPropuesta key={prop.id} o={o} p={prop} editar={editar} />}
    {resp?.k === 'chat' && <Hoja titulo={guardarTalCual ? 'No lo he entendido como una tarea' : resp.mensaje} id="chat" cerrar={o.cerrar}>
      <p className="pz-hoja-texto">{guardarTalCual
        ? 'Parece algo para hablarlo en el chat (una pregunta, código, el servidor…). Puedes guardarlo tal cual como tarea o abrirlo en el chat.'
        : 'Aquí Zazu solo organiza tu día: apunta, recuerda y crea citas. Para preguntas, código, el servidor o el móvil, lo hablamos en el chat.'}</p>
      <p className="pz-cita">{resp.texto}</p>
      <div className="pz-hoja-acc">
        {guardarTalCual && <button type="button" className="pz-btn pz-btn-primario" data-foco disabled={guardando} onClick={() => void talCual()}>{guardando ? 'Guardando…' : 'Guardar tal cual como tarea'}</button>}
        <button type="button" className="pz-btn pz-btn-chat" data-foco={guardarTalCual ? undefined : true} onClick={() => { o.cerrar(); abrirChat(resp.texto) }}>Abrir en el chat <span className="pz-chat-flecha"><Icono n="arrow" size={15} /></span></button>
        <button type="button" className="pz-btn pz-btn-texto" onClick={editar}>Cambiar el texto</button>
      </div>
    </Hoja>}
    {resp?.k === 'privado' && <Hoja titulo="No lo apunto" id="privado" cerrar={() => { o.cerrar(); limpiar() }}>
      <p className="pz-hoja-texto">{resp.mensaje}</p>
      <div className="pz-hoja-acc"><button type="button" className="pz-btn pz-btn-primario" data-foco onClick={() => { o.cerrar(); limpiar() }}>Entendido</button></div>
    </Hoja>}
    {fase?.k === 'fallo' && <Hoja titulo="No pude preparar la propuesta" id="fallo" cerrar={o.cerrar}>
      <div className="pz-fallo" role="alert"><span>{fase.texto}</span></div>
      <p className="pz-nota">Tu texto sigue ahí: no se ha guardado nada.</p>
      <div className="pz-hoja-acc">
        <button type="button" className="pz-btn pz-btn-primario" data-foco onClick={() => { o.cerrar(); void o.enviar(texto) }}>Reintentar</button>
        {guardarTalCual && <button type="button" className="pz-btn pz-btn-suave" disabled={guardando} onClick={() => void talCual()}>Guardar tal cual como tarea</button>}
        <button type="button" className="pz-btn pz-btn-texto" onClick={o.cerrar}>Cerrar</button>
      </div>
    </Hoja>}
  </>
}
