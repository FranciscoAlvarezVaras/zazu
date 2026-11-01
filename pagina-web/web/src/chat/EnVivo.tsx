import { deHermes, md } from '../lib'
import type { Decision, Vivo } from '../tipos'
import TarjetaAprobacion from './Aprobacion'
import Indicador from './Indicador'
import { useAhora } from './api'

const FIN = new Set(['terminado', 'fallo', 'parado', 'sin_respuesta'])
const DECIDIDO: Record<string, string> = { once: 'Aprobado · continúa…', session: 'Aprobado durante esta respuesta · continúa…', deny: 'Denegado', caducado: 'Caducó: nadie respondió a tiempo' }
const NOTA_FIN: Record<string, string> = { parado: 'Respuesta parada.', fallo: 'No se pudo responder', sin_respuesta: 'Este mensaje se quedó sin respuesta.' }

/** Lo que pasa ahora mismo en la respuesta en marcha: la tarjeta de permiso, «Pensando» mientras hay un paso en curso
 *  y el texto que se va escribiendo. Los pasos ya hechos salen de lo guardado (<Pasos>), no de aquí.
 *  Si la respuesta se paró, falló o no llegó, queda una nota con «Reintentar» (aunque no haya texto). */
export default function EnVivo({ vivo, onDecidir, onReintentar }: { vivo: Vivo; onDecidir(d: Decision): void; onReintentar?: () => void }) {
  const fin = FIN.has(vivo.estado)
  const paso = fin ? undefined : [...vivo.pasos].reverse().find(p => p.estado === 'en_curso')
  const a = fin ? null : vivo.aprobacion
  const u = !a && !fin ? vivo.ultima : null
  const ahora = useAhora(1000, !!paso || !!u)
  const decidido = u && ahora / 1000 - u.cuando < 60 ? u : null   // el resultado del permiso se ve un minuto
  const anuncio = a ? 'Zazu necesita tu permiso' : vivo.estado === 'parando' ? 'Parando…' : fin ? '' : 'Pensando'   // sin nombre: la asistente de una invitada se llama distinto
  const nota = NOTA_FIN[vivo.estado]
  return <div className="hz-vivo" aria-busy={!fin}>
    <span className="visually-hidden" role="status" aria-live="polite">{anuncio}</span>
    {a && <TarjetaAprobacion a={a} puedeAprobar={vivo.puedeAprobar} onDecidir={onDecidir} />}
    {decidido && <p className={`hz-decidido ${decidido.decision}`}>{DECIDIDO[decidido.decision]}</p>}
    {vivo.texto && <div className="hz-vivo-texto md" dangerouslySetInnerHTML={{ __html: md(vivo.texto) }} />}
    {nota && <div className={`hz-vivo-fin ${vivo.estado}`} role="note">
      <p className="hz-vivo-nota">{vivo.estado === 'fallo' ? `${nota}${vivo.error && !/^no se pudo responder\.?$/i.test(vivo.error) ? `: ${deHermes(vivo.error)}` : '.'}` : nota}</p>
      {onReintentar && <button type="button" className="hz-chip" onClick={onReintentar}>Reintentar</button>}
    </div>}
    {!fin && !a && (!vivo.texto || paso) && <p className="hz-pensando"><Indicador parando={vivo.estado === 'parando'} /></p>}
  </div>
}
