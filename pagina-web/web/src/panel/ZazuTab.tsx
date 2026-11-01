/* Pestaña «Zazu»: bandeja de avisos, lo que Zazu apuntó de tus chats, sugerencia, estado de los vigías y atajos de ajustes. */
import { useState } from 'react'
import { irA, useParams } from '../lib'
import type { Ctx } from '../ctx'
import { cargarAvisos, useCarga } from './api'
import type { EstadoAvisos } from './api'
import { Capturas, ListaAvisos, Reglas } from './Avisos'
import Registro from './Registro'
import Aprendido from './Aprendido'
import { tardeLibre } from './Hoy'
import { useDatosPanel } from './datos'
import { useTemaPz } from './tema'
import { Esqueleto, Fallo, haceMin, Icono, plural } from './ui'
import type { Ico } from './ui'

const FILTROS: [EstadoAvisos, string][] = [['abierto', 'Abiertos'], ['luego', 'Pospuestos'], ['hecho', 'Hechos'], ['descartado', 'Descartados']]
const VACIO: Record<EstadoAvisos, string> = { abierto: 'Bandeja vacía: nada te espera.', luego: 'No hay avisos pospuestos.', hecho: 'Aún no has marcado nada como hecho.', descartado: 'No has descartado nada.' }

/** `?tab=zazu&vista=registro` (o `vista=flujos`): «Qué ha hecho Zazu». Sin `vista`, la pestaña de siempre. */
export default function ZazuTab(ctx: Ctx) {
  const { vista } = useParams()
  return vista === 'aprendizaje' ? <Aprendido {...ctx} /> : vista === 'registro' || vista === 'flujos' ? <Registro key={vista} {...ctx} /> : <ZazuInicio {...ctx} />
}

function ZazuInicio(ctx: Ctx) {
  const { data, error, loading, refrescar, recargar } = useDatosPanel()
  const { toast, go } = ctx
  const [estado, setEstado] = useState<EstadoAvisos>('abierto')
  const [tema, setTema] = useTemaPz()
  const lista = useCarga(() => cargarAvisos(estado), 'avisos-' + estado, 60000)
  const alCambiar = async () => { await Promise.all([refrescar(), lista.reload()]) }
  const libre = data ? tardeLibre(data) : null
  const hechasTitulo = data?.tareas.ok ? data.tareas.items[0]?.titulo : undefined
  const preparar = (t: string) => { ctx.setDraft(t); go('inicio') }   // «Sí»: la frase queda en la barra de Zazu; la apuntas tú
  const visibles = data?.capturas.ok ? data.capturas.items : []

  return <div className="pz-page pz-zazu">
    <header className="pz-cab-pag"><div><p className="pz-eyebrow">TU ORGANIZADOR</p><h1>Zazu</h1></div>
      <button type="button" className="pz-btn pz-btn-suave" onClick={() => irA({ tab: 'zazu', vista: 'registro' })}><Icono n="eye" size={16} /> Qué ha hecho Zazu</button>
      <button type="button" className="pz-btn pz-btn-suave" onClick={() => irA({ tab: 'zazu', vista: 'aprendizaje' })}><Icono n="spark" size={16} /> Qué ha aprendido</button></header>
    <div className="pz-grid">
      <div className="pz-col-dia">
        <section aria-labelledby="pz-z-av">
          <div className="pz-sec-cab"><h3 id="pz-z-av">Avisos</h3>{lista.data?.ok && <span>{plural(lista.data.items.length, 'aviso', 'avisos')}</span>}</div>
          <div className="pz-chips" role="group" aria-label="Qué avisos ver">{FILTROS.map(([e, t]) => <button key={e} type="button" aria-pressed={estado === e} onClick={() => setEstado(e)}>{t}</button>)}</div>
          {lista.loading && !lista.data ? <Esqueleto filas={3} alto={78} />
            : lista.error && !lista.data ? <Fallo texto={`No pude leer los avisos: ${lista.error}.`} reintentar={() => void lista.reload()} />
              : lista.data && !lista.data.ok ? <Fallo texto={`No pude leer los avisos: ${lista.data.error}.`} reintentar={() => void lista.reload()} />
                : lista.data?.ok && (lista.data.items.length
                  ? <ListaAvisos items={lista.data.items} toast={toast} alCambiar={alCambiar} />
                  : <p className="pz-vacio">{VACIO[estado]}</p>)}
          {lista.error && lista.data && <Fallo texto={`No pude actualizar: ${lista.error}.`} reintentar={() => void lista.reload()} />}
        </section>

        <section aria-labelledby="pz-z-cap">
          <div className="pz-sec-cab"><h3 id="pz-z-cap">Zazu propone apuntar</h3>{data?.capturas.ok && visibles.length > 0 && <span>{plural(visibles.length, 'cosa', 'cosas')}</span>}</div>
          {!data ? (loading ? <Esqueleto filas={2} alto={72} /> : <Fallo texto={`No pude leerlo${error ? `: ${error}` : ''}.`} reintentar={() => void recargar()} />)
            : !data.capturas.ok ? <Fallo texto={`No pude ver lo que Zazu apuntó de tus chats: ${data.capturas.error}.`} reintentar={() => void refrescar()} />
              : <Capturas items={data.capturas.items} toast={toast} alCambiar={alCambiar} preparar={preparar} vacio="No hay nada pendiente de tus chats ni de tu correo." />}
        </section>

        <Reglas toast={toast} />
      </div>

      <aside className="pz-col-lado">
        {libre && <section className="pz-sugerencia" aria-labelledby="pz-z-sug">
          <span className="pz-asistente"><Icono n="spark" size={18} /></span>
          <p className="pz-eyebrow">SUGERENCIA DE ZAZU</p>
          <h3 id="pz-z-sug">Tu tarde está libre.</h3>
          <p>{hechasTitulo ? `¿Reservamos 30 minutos para «${hechasTitulo}»?` : '¿Reservamos 30 minutos para avanzar con tus cosas?'}</p>
          <button type="button" onClick={() => { ctx.setDraft(`Evento: Tiempo para ${hechasTitulo || 'mis cosas'} hoy a las ${libre.hora}`); go('inicio') }}>Planificar tiempo <Icono n="arrow" size={16} /></button>
          <small>Te enseño la propuesta antes de apuntar nada.</small>
        </section>}

        <section aria-labelledby="pz-z-vig">
          <div className="pz-sec-cab"><h3 id="pz-z-vig">Vigías</h3></div>
          {!data ? (loading ? <Esqueleto filas={3} alto={44} /> : null)
            : !data.vigias.ok ? <Fallo texto={`${data.vigias.error}.`} reintentar={() => void refrescar()} />
              : <ul className="pz-vigias">{data.vigias.v.items.map(v => <li key={v.id}>
                <i className={`pz-semaforo ${v.ok ? 'ok' : 'mal'}`} aria-hidden="true" />
                <span><strong>{v.nombre}</strong><small>{v.ok ? 'Al día' : 'Sin señal reciente'} · {haceMin(v.haceMin)}{v.modo === 'sombra' ? ' · modo sombra' : ''}</small></span>
                <span className="pz-oculto">{v.ok ? 'correcto' : 'con problemas'}</span></li>)}
                {data.vigias.v.pausa && <li><i className="pz-semaforo mal" aria-hidden="true" /><span><strong>En pausa</strong><small>Los vigías no están avisando.</small></span></li>}
              </ul>}
          {data?.vigias.ok && !data.vigias.v.entregaReal && <p className="pz-nota">Modo sombra: los vigías miran y apuntan aquí, pero no te escriben por WhatsApp.</p>}
          <ul className="pz-atajos"><Atajo icono="eye" t="Qué ha hecho Zazu" s="Lo que ha leído, propuesto y hecho, y sus flujos" onClick={() => irA({ tab: 'zazu', vista: 'registro' })} /></ul>
        </section>

        <section aria-labelledby="pz-z-aj">
          <div className="pz-sec-cab"><h3 id="pz-z-aj">Ajustes</h3></div>
          <ul className="pz-atajos">
            <Atajo icono="bell" t="Silencio y avisos" s={`${data?.vigias.ok ? `${data.vigias.v.pausa ? 'Vigías en pausa' : data.vigias.v.entregaReal ? 'Te avisan por WhatsApp' : 'Solo se guardan aquí (modo sombra)'} · ` : ''}Pausa o activa cada flujo`} onClick={() => irA({ tab: 'zazu', vista: 'flujos' })} />
            <Atajo icono="bell" t="Notificaciones en este dispositivo" s="Activar o quitar las alertas del móvil" onClick={() => go('ajustes')} />
            <Atajo icono="link" t="Cuentas conectadas" s="Google y WhatsApp" onClick={() => go('cuentas')} />
            <Atajo icono="repeat" t="Rutinas" s="Resumen de la mañana y demás" onClick={() => go('rutinas')} />
          </ul>
          <div className="pz-tema pz-tema-ancho" role="group" aria-label="Tema de color">
            <button type="button" aria-pressed={tema === 'claro'} onClick={() => setTema('claro')}><Icono n="sun" size={16} /> Claro</button>
            <button type="button" aria-pressed={tema === 'oscuro'} onClick={() => setTema('oscuro')}><Icono n="moon" size={16} /> Oscuro</button>
          </div>
        </section>
      </aside>
    </div>
  </div>
}

function Atajo({ icono, t, s, onClick }: { icono: Ico; t: string; s: string; onClick: () => void }) {
  return <li><button type="button" className="pz-atajo" onClick={onClick}><span className="pz-atajo-ico"><Icono n={icono} size={18} /></span><span><strong>{t}</strong><small>{s}</small></span><Icono n="chevron" size={16} /></button></li>
}
