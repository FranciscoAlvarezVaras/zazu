/* Avisos del vigía (Hecho · Luego · Descartar), sus propuestas (Sí · No · Sí, siempre · No, nunca) y las reglas que has dado. */
import { useState } from 'react'
import { accionAviso, cargarReglas, quitarRegla, responderPropuesta, useCarga } from './api'
import type { AccionAviso, Aviso, Captura, Regla, RespuestaPropuesta as Respuesta } from './api'
import { cuandoCorto, diaCorto, Hoja, Icono, plural } from './ui'

const FUENTE: Record<string, string> = { correo: 'Correo', wa: 'WhatsApp', agenda: 'Agenda', sistema: 'Sistema', agente: 'Asistente' }
export const nombreFuente = (f: string) => FUENTE[f] || 'Zazu'

type Luego = { horas?: number; cuando?: 'manana' | 'tarde' }
const LUEGOS: { t: string; v: Luego }[] = [{ t: 'En 3 horas', v: { horas: 3 } }, { t: 'Esta tarde (17:00)', v: { cuando: 'tarde' } }, { t: 'Mañana (08:00)', v: { cuando: 'manana' } }]
const OK: Record<AccionAviso, string> = { hecho: 'Aviso hecho', descartar: 'Aviso descartado', luego: 'Te lo recordaré más tarde' }

/** Hace la acción en el servidor y avisa. Devuelve true si salió bien. */
export function useAccionAviso(toast: (m: string) => void, alCambiar: () => Promise<void> | void) {
  const [ocupado, setOcupado] = useState<number | null>(null)
  const [luego, setLuego] = useState<Aviso | null>(null)
  const hacer = async (a: Aviso, que: AccionAviso, l?: Luego) => {
    setOcupado(a.id)
    try { await accionAviso(a.id, que, l); toast(OK[que]); await alCambiar(); return true }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`); return false }
    finally { setOcupado(null) }
  }
  const hoja = luego && <Hoja titulo="Avisarme más tarde" id="luego" cerrar={() => setLuego(null)}>
    <p className="pz-hoja-sub">{luego.titulo}</p>
    <div className="pz-opciones">{LUEGOS.map(o => <button key={o.t} type="button" className="pz-opcion" onClick={async () => { const a = luego; setLuego(null); await hacer(a, 'luego', o.v) }}><Icono n="clock" size={18} /> {o.t}</button>)}</div>
  </Hoja>
  return { ocupado, hacer, pedirLuego: setLuego, hoja }
}

const PRIO = ['', 'Ya', 'Hoy', 'Puede esperar']

export function ListaAvisos({ items, toast, alCambiar, limite }: { items: Aviso[]; toast: (m: string) => void; alCambiar: () => Promise<void> | void; limite?: number }) {
  const { ocupado, hacer, pedirLuego, hoja } = useAccionAviso(toast, alCambiar)
  const ver = limite ? items.slice(0, limite) : items
  return <>
    <ul className="pz-avisos">{ver.map(a => <li key={a.id} className={`pz-aviso p${a.prio}`}>
      <span className="pz-aviso-marca" aria-hidden="true" />
      <div className="pz-aviso-cuerpo">
        <div className="pz-aviso-top"><span className="pz-etiqueta">{nombreFuente(a.fuente)}{a.chat ? ` · ${a.chat}` : ''}</span><span className="pz-meta">{PRIO[a.prio]} · {cuandoCorto(a.creado)}</span></div>
        <strong>{a.titulo}</strong>
        {a.detalle && <p>{a.detalle}</p>}
        {a.borrador && <p className="pz-borrador"><span>Borrador:</span> {a.borrador}</p>}
        <div className="pz-aviso-acc">
          <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado === a.id} onClick={() => void hacer(a, 'hecho')}><Icono n="check" size={16} /> Hecho</button>
          <button type="button" className="pz-btn pz-btn-suave" disabled={ocupado === a.id} onClick={() => pedirLuego(a)}><Icono n="clock" size={16} /> Luego</button>
          <button type="button" className="pz-btn pz-btn-texto" disabled={ocupado === a.id} onClick={() => void hacer(a, 'descartar')}>Descartar</button>
          {a.enlace && <a className="pz-btn pz-btn-texto" href={a.enlace} target="_blank" rel="noopener noreferrer">Abrir <Icono n="link" size={15} /></a>}
        </div>
      </div>
    </li>)}</ul>
    {hoja}
  </>
}

/* ---------- Propuestas del vigía: «Zazu ha apuntado de tus chats» ----------
   Cada respuesta va al vigía (no se guarda en este dispositivo): Sí · No · y, si el riesgo es bajo o medio, Sí, siempre · No, nunca.
   Lo contestado desaparece solo. En modo sombra nada se escribe en Google: «Sí» deja la frase lista en la barra de Zazu para apuntarla tú.
   Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: tools/proactive_tools.py (sí / no / «always» solo en riesgo
   bajo o medio). Cambios: botones en vez de respuestas por texto, «Sí, siempre» oculto en lo sospechoso y aviso visible del escudo. */
const CREADAS = ['creado', 'evento_creado', 'duplicado']
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const OK_RESP: Record<Respuesta, string> = { si: 'Aceptada', no: 'Descartada', siempre: 'Aceptada. Las parecidas te las dejaré preparadas', nunca: 'Descartada. No te enseñaré más como esta' }

/** La frase para la barra de Zazu: «Tarea: … el 17 de octubre» o «Evento: … el 17 de octubre a las 10:00». */
export function fraseDe(c: Captura): string {
  const m = c.due && /^(\d{4})-(\d{2})-(\d{2})$/.exec(c.due)
  const dia = m ? ` el ${Number(m[3])} de ${MESES[Number(m[2]) - 1]}` : ''
  return c.tipo === 'evento' ? `Evento: ${c.titulo}${dia}${c.hora ? ` a las ${c.hora}` : ''}` : `Tarea: ${c.titulo}${dia}`
}

export function Capturas({ items, toast, alCambiar, preparar, vacio }: { items: Captura[]; toast: (m: string) => void; alCambiar: () => Promise<void> | void; preparar?: (texto: string) => void; vacio?: string }) {
  const [ocupado, setOcupado] = useState<number | null>(null)
  const [hechas, setHechas] = useState<number[]>([])   // se ocultan al momento, sin esperar a recargar
  const ver = items.filter(c => !hechas.includes(c.id))
  const responder = async (c: Captura, r: Respuesta) => {
    setOcupado(c.id)
    try {
      await responderPropuesta(c.id, r)
      setHechas(h => [...h, c.id])
      const sinCrear = !CREADAS.includes(c.accion)
      if ((r === 'si' || r === 'siempre') && sinCrear && preparar) { toast(`${OK_RESP[r]}. Te la dejo escrita en la barra de Zazu`); preparar(fraseDe(c)) }
      else toast(OK_RESP[r])
      await alCambiar()
    } catch (e) { toast(`No se pudo: ${(e as Error).message}`) }
    finally { setOcupado(null) }
  }
  if (!ver.length) return vacio ? <p className="pz-vacio">{vacio}</p> : null
  return <ul className="pz-capturas">{ver.map(c => {
    const creada = CREADAS.includes(c.accion)
    const ocu = ocupado === c.id
    const b = (r: Respuesta, t: string, clase = 'pz-btn-suave', ico?: 'check' | 'close') =>
      <button type="button" className={`pz-btn ${clase}`} disabled={ocu} onClick={() => void responder(c, r)}>{ico && <Icono n={ico} size={16} />} {t}</button>
    return <li key={c.id} className={`pz-captura${c.sospechosa ? ' pz-captura-ojo' : ''}`}>
      <span className="pz-captura-ico" aria-hidden="true"><Icono n={c.sospechosa ? 'alert' : c.tipo === 'evento' ? 'calendar' : 'check'} size={18} /></span>
      <div className="pz-captura-cuerpo">
        <strong>{c.titulo}</strong>
        <p className="pz-meta">{c.tipo === 'evento' ? 'Cita' : 'Tarea'}{c.due ? ` · ${diaCorto(c.due)}${c.hora ? ` ${c.hora}` : ''}` : ''}{c.chat ? ` · de «${c.chat}»` : ''} · {c.fuente === 'correo' ? 'correo' : 'WhatsApp'} · {cuandoCorto(c.creado)}</p>
        {c.sospechosa && <p className="pz-estado pz-mal" role="note"><Icono n="alert" size={14} /> Ojo: el mensaje traía frases que parecen órdenes. Revísalo bien antes de decir que sí.</p>}
        {creada ? <p className="pz-estado ok">{c.accionTxt || 'Creada'}</p>
          : c.preparada ? <p className="pz-estado">Preparada por tu regla «siempre»: un toque y la apuntas</p>
            : c.riesgo === 'alto' ? <p className="pz-estado">Toca dinero o papeles: te lo pregunto siempre</p>
              : c.regla === 'siempre' ? <p className="pz-estado">Sueles decir que sí a estas</p> : null}
        <div className="pz-aviso-acc">
          {creada ? <>{b('si', 'Está bien', 'pz-btn-suave', 'check')}{b('no', 'Descartar', 'pz-btn-texto')}</>
            : c.preparada ? <>{b('si', 'Apuntar', 'pz-btn-primario', 'check')}{b('no', 'No', 'pz-btn-texto')}</>
              : <>{b('si', 'Sí', 'pz-btn-suave', 'check')}{b('no', 'No', 'pz-btn-suave', 'close')}
                {c.recordable && !c.sospechosa && b('siempre', 'Sí, siempre', 'pz-btn-texto')}
                {c.recordable && b('nunca', 'No, nunca', 'pz-btn-texto')}</>}
        </div>
      </div>
    </li>
  })}</ul>
}

/** Las reglas «siempre / nunca» que has dado, para verlas y quitarlas. No se pinta nada si no hay ninguna. */
export function Reglas({ toast }: { toast: (m: string) => void }) {
  const lista = useCarga(cargarReglas, 'reglas', 60000)
  const [ocupado, setOcupado] = useState('')
  const quitar = async (r: Regla) => {
    setOcupado(r.clave)
    try { await quitarRegla(r.clave); toast('Regla quitada: te lo volveré a preguntar'); await lista.reload() }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`) }
    finally { setOcupado('') }
  }
  const d = lista.data
  if (!d) return null
  if (!d.ok) return <p className="pz-nota">No pude leer tus reglas: {d.error}.</p>
  if (!d.items.length) return null
  return <section aria-labelledby="pz-z-reg">
    <div className="pz-sec-cab"><h3 id="pz-z-reg">Lo que ya sé</h3><span>{plural(d.items.length, 'regla', 'reglas')}</span></div>
    <ul className="pz-reglas">{d.items.map(r => <li key={r.clave}>
      <span className={`pz-etiqueta ${r.decision === 'nunca' ? 'pz-etiqueta-mal' : ''}`}>{r.decision === 'siempre' ? 'Siempre sí' : 'Nunca'}</span>
      <span className="pz-reglas-txt"><strong>{r.texto}</strong>{r.ejemplo && <small>Como «{r.ejemplo}»</small>}</span>
      <button type="button" className="pz-btn pz-btn-texto" disabled={ocupado === r.clave} onClick={() => void quitar(r)}>Quitar</button>
    </li>)}</ul>
  </section>
}

export const cuentaCapturas = (n: number) => plural(n, 'cosa', 'cosas')
