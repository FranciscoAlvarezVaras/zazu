import type { Paso } from '../tipos'
import { argsBonitos, primeraLinea, resumenArgs } from './api'

/** Nombre que se ve (en mono) para cada herramienta; lo usa también la respuesta en directo. */
export const HERRAMIENTA: Record<string, string> = {
  terminal: 'terminal', process: 'procesos', process_manage: 'procesos', execute_code: 'código',
  read_file: 'leer archivo', write_file: 'escribir archivo', patch: 'editar archivo', search_files: 'buscar archivos',
  web_search: 'buscar en la web', web_extract: 'leer web', browser_navigate: 'navegador', browser_exec: 'navegador',
  vision_analyze: 'mirar imagen', skill_view: 'ver skill', skills_list: 'skills', skill_manage: 'skills',
  session_search: 'buscar conversaciones', todo: 'lista de pasos', memory: 'memoria', cronjob: 'rutinas', cronjob_manage: 'rutinas',
  text_to_speech: 'voz', send_message: 'enviar mensaje', clarify: 'pregunta', delegate_task: 'subagente', tool_search: 'buscar herramientas',
}
export const etiqueta = (h: string) => HERRAMIENTA[h] || (h.startsWith('browser_') ? 'navegador' : h.replace(/^mcp_/, '').replace(/_/g, ' '))

/** Las conversaciones de un solo disparo (las antiguas de Zazu y las de invitadas) bloquean lo delicado: el resultado lo dice así. */
const SOLO_CONSULTA = 'single-query mode (-q)'
const AVISO_PERMISO_FRAN = 'Esto necesitaba tu permiso y esta conversación antigua no puede pedirlo. Empieza una conversación nueva y Zazu te lo preguntará aquí.'
const AVISO_PERMISO_INVITADA = 'Esto necesita un permiso que desde aquí no se puede dar.'

/** Pasos técnicos de una respuesta (herramientas que se usaron), plegados bajo «Detalles · N pasos».
 *  Invitadas: la lista de siempre. Fran: al abrirlos, cada paso con su herramienta, sus argumentos y la primera línea del resultado. */
export default function Pasos({ pasos, guest = false }: { pasos: Paso[]; guest?: boolean }) {
  const n = Math.max(1, pasos.length)
  const permiso = pasos.some(p => p.resultado?.includes(SOLO_CONSULTA))
  return <>
    <details className="work"><summary>Detalles <small>· {n} {n === 1 ? 'paso' : 'pasos'}</small></summary>
      {guest
        ? <div className="steps">{pasos.map((p, i) => <details className="tool" key={p.id || i}><summary>{p.herramienta}</summary>
          {p.args && <pre>{p.args}</pre>}{p.resultado !== undefined && <pre>{p.resultado}</pre>}</details>)}</div>
        : <ol className="hz-pasos-lista">{pasos.map((p, i) => <PasoFila key={p.id || i} p={p} />)}</ol>}
    </details>
    {permiso && <p className="hz-aviso-permiso" role="note">{guest ? AVISO_PERMISO_INVITADA : AVISO_PERMISO_FRAN}</p>}
  </>
}

function PasoFila({ p }: { p: Paso }) {
  const args0 = resumenArgs(p.args)
  const args = p.cortado && args0 && !args0.endsWith('…') ? `${args0} …` : args0   // argumentos recortados al guardar: que se note
  const res = p.resultado === undefined ? '' : primeraLinea(p.resultado) || '(sin salida)'
  const detalle = (p.args && argsBonitos(p.args) !== args) || (p.resultado || '').split('\n').filter(Boolean).length > 1 || (p.resultado || '').length > 160
  const cuerpo = <>
    <span className="hz-paso-et">{etiqueta(p.herramienta)}{p.error && <span className="hz-paso-err"> · error</span>}</span>
    {args && <span className="hz-paso-args">{args}</span>}
    {p.resultado === undefined ? <span className="hz-paso-res espera">esperando resultado…</span> : <span className="hz-paso-res">{res}</span>}
  </>
  return <li className={`hz-paso ${p.error ? 'error' : ''}`}>
    {detalle ? <details><summary>{cuerpo}</summary>
      {p.args && <pre className="hz-pre" aria-label="Argumentos">{argsBonitos(p.args)}{p.cortado ? <span className="hz-tok hz-tok-corte">{`… faltan ${p.cortado.toLocaleString('es-ES')} caracteres`}</span> : null}</pre>}
      {p.resultado !== undefined && <pre className="hz-pre" aria-label="Resultado">{p.resultado || '(sin salida)'}</pre>}
    </details> : <div className="hz-paso-fila">{cuerpo}</div>}
  </li>
}
