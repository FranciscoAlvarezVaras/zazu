/* Empleo: dos pestañas. «Ofertas» (lo que encuentra el buscador, con guardar y «no me interesa») y «Candidaturas» (tus candidaturas como lista por estado,
   o la ficha de una, con `?tab=empleo&tarjeta=<ruta de la nota>`). Una oferta abierta es `?tab=empleo&tarjeta=<id>` (el id es hexadecimal; una nota lleva «/»). */
import type { Ctx } from '../ctx'
import { irA, useParams } from '../lib'
import { useDatosTableros } from './datos'
import { tableroKanban } from './formato'
import { Ficha, VistaKanban } from './Listas'
import Ofertas, { useDosColumnas } from './Ofertas'
import { Esqueleto, Fallo } from './ui'

const ID_OFERTA = /^[0-9a-f]{4,32}$/

function Candidaturas(ctx: Ctx) {
  const t = useDatosTableros()
  const { tarjeta } = useParams()
  const b = tableroKanban(t.data, 'candidaturas')
  if (!b) {
    const mal = t.data?.find(x => x.id === 'candidaturas')
    return <div className="pz-page"><header className="pz-cab-lista"><div><h1>Candidaturas</h1></div></header>
      {!t.data && t.loading ? <><p className="pz-nota" role="status">Cargando tus candidaturas…</p><Esqueleto filas={4} alto={72} /></> : <Fallo texto={`No pude leer tus candidaturas${mal && !mal.ok ? `: ${mal.error}` : t.error ? `: ${t.error}` : ''}.`} reintentar={() => void t.reload()} />}</div>
  }
  return tarjeta ? <Ficha b={b} t={t} ctx={ctx} ruta={tarjeta} /> : <VistaKanban b={b} t={t} ctx={ctx} base={{ tab: 'empleo', tablero: 'candidaturas' }} titulo="Candidaturas" />
}

export default function Empleo(ctx: Ctx) {
  const ancho = useDosColumnas()
  const { tarjeta, tablero, vista } = useParams()
  const esNota = !!tarjeta && !ID_OFERTA.test(tarjeta)
  const cand = tablero === 'candidaturas' || esNota || vista === 'columnas'
  const conPestanas = !tarjeta || ancho && !esNota          // una ficha abierta a pantalla completa lleva su propio «Volver»
  return <>
    {conPestanas && <div className="pz-page pz-of-pest-pag"><nav className="pz-of-pest" aria-label="Empleo">
      <button type="button" aria-current={cand ? undefined : 'page'} onClick={() => { irA({ tab: 'empleo' }); window.scrollTo({ top: 0 }) }}>Ofertas</button>
      <button type="button" aria-current={cand ? 'page' : undefined} onClick={() => { irA({ tab: 'empleo', tablero: 'candidaturas' }); window.scrollTo({ top: 0 }) }}>Candidaturas</button></nav></div>}
    {cand ? <Candidaturas {...ctx} /> : <div className="pz-page pz-of-pag"><Ofertas ctx={ctx} /></div>}
  </>
}
