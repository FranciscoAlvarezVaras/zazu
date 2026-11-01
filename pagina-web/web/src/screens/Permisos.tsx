import { useState, type ReactNode } from 'react'
import { Icon, type IconName } from '../icons'
import { EN_APP, irA, post, useFetch } from '../lib'
import { usePush } from './Ajustes'
import { enviarPosicion, type Prefs } from './Preferencias'
import { EL, GuiaPermiso, Nivel, abrirAjustes, appConAvisos, dondeTexto, faltaSistema, leerNativo, mensajePedido, nativo, pedirMedio, pedirNativo, pedirPosicion, probarMicro, useNativo, usePermiso, type Tipo } from './PermisosDispositivo'
import type { Me } from './Invitada'
import { abrirWhatsApp, avisarCanales, FilaWhatsAppFran, subWhatsApp, useCanales } from './WhatsAppVincular'
import { numeroWa, type EstadoAgendaChats } from './AgendaChats'

/** Micrófono apagado en este dispositivo (lo decide ella en «Tus permisos»): el botón de dictar no sale.
 *  Es lo único que dice el interruptor: el permiso del navegador se informa aparte. */
export const microApagado = () => { try { return localStorage.getItem('hz-sin-micro') === '1' } catch { return false } }

const MOVIL = /Android|iPhone|iPad/.test(typeof navigator !== 'undefined' ? navigator.userAgent : '')

function Fila({ icono, titulo, sub, on, cambiar, busy, fijo, extra }: { icono: IconName; titulo: string; sub: string; on: boolean; cambiar?: () => void; busy?: boolean; fijo?: boolean; extra?: ReactNode }) {
  return <div className="setting-row" style={{ alignItems: 'flex-start', paddingTop: 12, paddingBottom: 12 }}>
    <span className="setting-icon"><Icon name={icono} size={19} /></span>
    <span className="setting-copy"><strong>{titulo}</strong><small>{sub}</small>{extra}</span>
    <button type="button" role="switch" aria-checked={on} aria-label={titulo} className={`toggle ${on ? 'active' : ''}`} disabled={busy || fijo || !cambiar}
      onClick={cambiar} style={fijo ? { opacity: 0.6 } : undefined}><span /></button>
  </div>
}

/** Botón pequeño debajo del texto de una fila (cómo activarlo, abrir ajustes, probar…). */
const Mini = ({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) =>
  <button type="button" className="text-link" disabled={disabled} onClick={onClick} style={{ display: 'inline-block', marginTop: 6, marginRight: 14, fontSize: 13, minHeight: 32, textAlign: 'left' }}>{children}</button>

/** «Tus permisos»: todo lo que la app pide al móvil o al PC, con un interruptor para cada cosa. Ella decide.
 *  Cada interruptor dice lo que hay de verdad; tocarlo lo pide, y si está bloqueado enseña cómo desbloquearlo aquí. */
export function PanelPermisos({ prefs, nivel, asistente, toast, cambio, irWhatsApp, admin = false, irCuentas }:
  { prefs?: Prefs; nivel?: string; asistente: string; toast: (m: string) => void; cambio: () => void; irWhatsApp: () => void; admin?: boolean; irCuentas?: () => void }) {
  const push = usePush(toast, admin)
  const [geo, , ponGeo] = usePermiso('ubicacion')
  const [mic, , ponMic] = usePermiso('microfono')
  const [cam, , ponCam] = usePermiso('camara')
  const [notiApp, , ponNotiApp] = usePermiso('notificaciones')   // solo cuenta en la app (sus avisos nativos)
  const nat = useNativo()   // al día: al volver de encender la ubicación del móvil, la fila cambia sola
  const conPuente = EN_APP && !!nativo()
  const sinPuente = EN_APP && !conPuente   // app 2.3 o anterior: no sabemos el estado hasta probarlo
  const fran = useFetch<{ google: { email: string; error?: boolean }[]; whatsapp?: string | null; whatsapp_sync?: string | null; whatsapp_vivo?: boolean | null }>(admin ? '/api/cuentas' : null)
  const [guia, setGuia] = useState<{ tipo: Tipo; quitar?: boolean } | null>(null)
  const [sinMicro, setSinMicro] = useState(microApagado())
  const [sonido, setSonido] = useState(0)
  const [oido, setOido] = useState<number | null>(null)
  const g = useFetch<{ google: { email: string; error: boolean }[] }>(nivel === 'invitada' || admin ? null : '/api/cuentas')
  const c = useCanales(0, admin ? null : '/api/canales')
  const ag = useFetch<EstadoAgendaChats>(admin ? null : '/api/inv/whatsapp')   // sus WhatsApp para la agenda (puede tener varios)
  const agOn = (ag.data?.cuentas || []).filter(x => x.estado === 'conectado')   // el mismo estado que la tarjeta «WhatsApp y Telegram»
  const [busy, setBusy] = useState('')
  const hacer = async (k: string, f: () => Promise<unknown>) => { setBusy(k); try { await f() } catch (e) { toast(`No se pudo: ${(e as Error).message}`) } finally { setBusy('') } }
  const bloqueada = (femenino = false, t?: Tipo) => t && faltaSistema(t)
    ? `Zazu tiene permiso, pero el navegador no tiene el del ${MOVIL ? 'móvil' : 'ordenador'} para usar ${EL[t]}. Toca «Cómo activarl${femenino ? 'a' : 'o'}».`
    : `Bloquead${femenino ? 'a' : 'o'} ${dondeTexto()}. Toca «Cómo activarl${femenino ? 'a' : 'o'}».`

  // —— Ubicación ——
  const sistemaOff = nat?.ubicacionSistema === 'off'
  const seguir = !!prefs?.auto
  const ubicOn = admin ? geo === 'granted' : seguir && geo === 'granted' && !!(prefs?.ciudad || prefs?.t_ubic)
  const ubicacion = () => {
    if (geo === 'denied') { setGuia({ tipo: 'ubicacion' }); return }
    // permiso dado pero la ubicación del móvil apagada: el interruptor sale apagado, así que tocarlo la enciende (nunca borra su ciudad)
    if (sistemaOff && geo === 'granted') { if (!abrirAjustes('ubicacion')) setGuia({ tipo: 'ubicacion' }); return }
    if (admin && geo === 'granted' && !sistemaOff) { setGuia({ tipo: 'ubicacion', quitar: true }); return }   // Fran: solo el permiso de este dispositivo
    if (!admin && ubicOn) {
      void hacer('ubic', async () => { await post('/api/mi-zazu', { action: 'preferencias', ...prefs, auto: false }); toast(`${asistente} ya no sigue tu ubicación (se ha borrado tu ciudad)`); cambio() })
      return
    }
    darUbic()
  }
  const darUbic = () => {
    void hacer('ubic', async () => {
      const p = await pedirPosicion()   // primero el permiso y la posición; solo si salen bien se guarda «seguir mi ubicación»
      if (!p.pos) {
        if (p.estado === 'denied') ponGeo('denied')
        toast(mensajePedido('ubicacion', p))
        if (p.estado === 'denied' || (p.error === 'posicion' && leerNativo()?.ubicacionSistema === 'off')) setGuia({ tipo: 'ubicacion' })
        return
      }
      ponGeo('granted')
      if (admin) { toast('Ubicación permitida en este dispositivo'); return }
      if (!seguir) await post('/api/mi-zazu', { action: 'preferencias', ...prefs, auto: true })
      const r = await enviarPosicion(p.pos)
      toast(r?.ciudad ? `${asistente} ya sabe que estás en ${r.ciudad}` : `Activada: ${asistente} ya sabe tu hora`)
      cambio()
    })
  }
  const ubicSub = sistemaOff && geo === 'granted' ? 'Permitida, pero la ubicación del móvil está apagada. Toca «Encenderla».'
    : geo === 'denied' ? bloqueada(true, 'ubicacion') + (!admin && seguir ? ' Mientras, tu hora la pones tú.' : '')
    : admin ? (geo === 'granted' ? 'Permitida en este dispositivo.' : sinPuente ? 'Toca para comprobarla o pedirla.' : 'Sin permiso en este dispositivo. Toca para darlo.')
    : ubicOn ? `Activada: ${asistente} sabe tu ciudad${prefs?.ciudad ? ` (${prefs.ciudad})` : ''} y cambia tu hora sola cuando viajas.`
    : seguir ? 'Pendiente: falta el permiso del móvil. Toca y pulsa «Permitir».'
    : `Apagada: ${asistente} no sabe dónde estás. Tu hora la pones tú.`

  // —— Notificaciones ——
  const pushOn = conPuente ? notiApp === 'granted' : push.estado === 'si'
  const notificaciones = () => {
    if (conPuente) {   // en la app no hay Web Push: sus avisos nativos y el acceso directo a sus ajustes
      if (notiApp === 'granted') { if (!abrirAjustes('notificaciones')) setGuia({ tipo: 'notificaciones', quitar: true }); else toast('Para quitarlas, apágalas en los ajustes que se acaban de abrir.'); return }
      if (notiApp === 'denied') { setGuia({ tipo: 'notificaciones' }); return }
      void hacer('noti', async () => { const e = await pedirNativo('notificaciones'); ponNotiApp(e); if (e === 'granted') toast('Notificaciones de la app activadas'); else if (e === 'denied') setGuia({ tipo: 'notificaciones' }); else toast('Has dicho que no. Si las quieres, toca otra vez y pulsa «Permitir».') })
      return
    }
    if (EN_APP) { setGuia({ tipo: 'notificaciones' }); return }
    if (push.estado === 'si') { void push.desactivar(); return }
    if (push.estado === 'bloqueado') { setGuia({ tipo: 'notificaciones' }); return }
    if (push.estado === 'nosoporta') { if (/iPhone|iPad/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) setGuia({ tipo: 'notificaciones' }); else toast('Este navegador no admite notificaciones. Prueba con Chrome.'); return }
    if (push.estado === 'error') { toast(`No se pueden activar aquí: ${push.fallo}`); return }
    if (push.estado === '?') { toast('Un segundo, que lo estoy comprobando.'); return }
    void push.activar().then(r => { if (r === 'bloqueado') setGuia({ tipo: 'notificaciones' }) })
  }
  const appSinPush = admin && appConAvisos() ? (notiApp === 'granted' ? 'Y también los recordatorios, las rutinas y las alertas del servidor (pueden tardar hasta 15 minutos).' : 'Actívalos y te llegarán aquí los recordatorios, las rutinas y las alertas del servidor.')
    : admin ? 'Las alertas del servidor todavía no llegan a esta app: actívalas en holazazu.app desde Chrome.'
    : c.data?.whatsapp?.conectado ? 'Los recordatorios y las rutinas todavía no llegan a esta app: te llegan por WhatsApp, o abre holazazu.app en Chrome y actívalas allí.'
    : 'Los recordatorios y las rutinas todavía no llegan a esta app. Para recibirlos, vincula tu WhatsApp (más abajo) o abre holazazu.app en Chrome y activa allí las notificaciones.'
  // en la app, «activadas» es solo para sus avisos nativos (Permitir o Rechazar): los recordatorios van por otro camino que aún no llega
  // a una invitada en la app no le llega ningún aviso nativo (el token del móvil es solo de Fran): no se le promete nada
  const notiSub = conPuente ? (notiApp === 'granted' ? (admin ? `Avisos de la app activados: te llegan los de Permitir o Rechazar. ${appSinPush}` : `Permitidas en el móvil. ${appSinPush}`) : notiApp === 'denied' ? `Apagados en los ajustes del móvil. Toca «Abrir ajustes». ${appSinPush}` : `Apagados. Toca para activarlos. ${appSinPush}`)
    : EN_APP ? `En esta app se activan en los ajustes del móvil: Ajustes › Aplicaciones › HolaZazu › Notificaciones. ${appSinPush}`
    : pushOn ? `Activadas: te llegan ${admin ? 'las alertas del servidor (si algo falla) y los permisos para Permitir o Rechazar' : nivel === 'invitada' ? 'tus recordatorios y tus rutinas' : 'tus recordatorios, tus rutinas y los permisos para Permitir o Rechazar'}.${push.info.data ? ` (${push.info.data.n} dispositivo${push.info.data.n === 1 ? '' : 's'})` : ''}`
    : push.estado === 'bloqueado' ? `Bloqueadas ${dondeTexto()}. Toca «Cómo activarlas».`
    : push.estado === 'nosoporta' ? (/iPhone|iPad/.test(navigator.userAgent) ? 'En el iPhone solo van con Zazu en la pantalla de inicio. Toca para ver cómo.' : 'Este navegador no las admite. En el móvil, usa Chrome o la web instalada.')
    : push.estado === 'error' ? `No se pueden activar aquí: ${push.fallo}.`
    : admin ? 'Apagadas: no te llegarán las alertas del servidor ni los permisos a este dispositivo. Toca para activarlas.'
    : 'Apagadas: no te llegarán recordatorios ni avisos al móvil. Toca para activarlas.'

  // —— Micrófono: el interruptor = «quiero el botón de dictar»; el permiso, en el texto ——
  const micOn = !sinMicro && mic !== 'denied'
  const probar = () => hacer('mic', async () => {
    setOido(null)
    const r = await pedirMedio('microfono')
    if (!r.stream) {
      if (r.estado === 'denied') { ponMic('denied'); setGuia({ tipo: 'microfono' }) }
      toast(mensajePedido('microfono', r)); return
    }
    ponMic('granted')
    const max = await probarMicro(r.stream, setSonido)
    setOido(max)
    toast(max < 0 ? 'Micrófono listo para dictar' : max < 0.04 ? 'El micrófono va, pero no te he oído. Habla un poco más cerca y vuelve a probar.' : 'Micrófono listo: te oigo bien')
  })
  const microfono = () => {
    if (mic === 'denied') { setGuia({ tipo: 'microfono' }); return }
    if (micOn) { try { localStorage.setItem('hz-sin-micro', '1') } catch { /* sin almacenamiento */ } setSinMicro(true); setOido(null); toast('Micrófono apagado: el botón de dictar ya no sale'); return }
    try { localStorage.removeItem('hz-sin-micro') } catch { /* sin almacenamiento */ }
    setSinMicro(false)
    void probar()   // al encenderlo, se pide el permiso y se prueba 1 segundo
  }
  const micSub = sinMicro ? 'Apagado: el botón de dictar no sale.'
    : mic === 'denied' ? bloqueada(false, 'microfono')
    : mic === 'granted' ? 'Activado: puedes dictarle en vez de escribir. Solo escucha mientras pulsas el micrófono.'
    : 'Activado. La primera vez que dictes, el móvil te pedirá permiso: pulsa «Permitir».'

  // —— Cámara (fotos para Zazu) ——
  const camara = () => {
    if (cam === 'denied') { setGuia({ tipo: 'camara' }); return }
    if (cam === 'granted') { setGuia({ tipo: 'camara', quitar: true }); return }
    void hacer('cam', async () => {
      const r = await pedirMedio('camara')
      if (r.stream) { r.stream.getTracks().forEach(t => t.stop()); ponCam('granted'); toast(`Cámara permitida: ya puedes hacerle fotos a ${asistente} desde el chat`); return }
      if (r.estado === 'denied') { ponCam('denied'); setGuia({ tipo: 'camara' }) }
      toast(mensajePedido('camara', r))
    })
  }
  const camSub = cam === 'granted' ? `Permitida: puedes hacerle fotos a ${asistente} desde el chat.` : cam === 'denied' ? bloqueada(true, 'camara')
    : `Para hacerle fotos a ${asistente} desde el chat. Toca para dar permiso.`

  const googleOn = !!g.data?.google.some(x => !x.error)
  const google = () => {
    if (!googleOn) { location.href = '/oauth/google/start?mode=connect'; return }
    if (!confirm(`¿Desconectar tu Google? ${asistente} dejará de ver tu agenda, tus tareas y tu correo.`)) return
    void hacer('google', async () => { for (const x of g.data!.google) await post('/api/mi-zazu', { action: 'desconectar_google', email: x.email }); await g.reload(); toast('Google desconectado') })
  }
  const waOn = !!c.data?.whatsapp.conectado
  const whatsapp = () => {
    if (!waOn) { irWhatsApp(); return }
    if (!confirm('¿Desconectar WhatsApp? Después, en tu móvil, quita «HolaZazu» de Dispositivos vinculados.')) return
    void hacer('wa', async () => { await post('/api/canales', { action: 'whatsapp_off' }); avisarCanales(); toast('WhatsApp desconectado') })
  }
  const abrirWa = MOVIL || conPuente ? <Mini onClick={() => abrirWhatsApp(toast)}>Abrir WhatsApp</Mini> : null

  return <div className="settings-list" id="permisos">
    {guia && <GuiaPermiso tipo={guia.tipo} quitar={guia.quitar} toast={toast} cerrar={() => setGuia(null)}
      alPermitir={guia.quitar ? undefined   // desbloqueado en los ajustes: se termina de activar aquí mismo, sin otro toque
        : guia.tipo === 'notificaciones' && !EN_APP ? () => { void push.activar() }
        : guia.tipo === 'ubicacion' && !admin && !ubicOn ? darUbic : undefined} />}
    <Fila icono="pin" titulo="Ubicación" busy={busy === 'ubic'} on={ubicOn && !sistemaOff} cambiar={ubicacion} sub={ubicSub}
      extra={geo === 'denied' ? <Mini onClick={() => setGuia({ tipo: 'ubicacion' })}>Cómo activarla</Mini>
        : sistemaOff ? <Mini onClick={() => { if (!abrirAjustes('ubicacion')) setGuia({ tipo: 'ubicacion' }) }}>Encenderla</Mini> : null} />
    <Fila icono="bell" titulo={conPuente ? 'Avisos de la app' : 'Notificaciones en este dispositivo'} busy={push.busy || busy === 'noti' || (!EN_APP && push.estado === 'no' && push.info.loading)} on={pushOn} cambiar={notificaciones} sub={notiSub}
      extra={<>{conPuente && <Mini onClick={() => { if (!abrirAjustes('notificaciones')) toast('No pude abrir los ajustes') }}>Abrir ajustes de notificaciones</Mini>}
        {!EN_APP && pushOn && <Mini disabled={push.busy} onClick={() => void push.probar()}>Probar</Mini>}
        {(push.estado === 'bloqueado' || (EN_APP && !conPuente)) && <Mini onClick={() => setGuia({ tipo: 'notificaciones' })}>Cómo activarlas</Mini>}</>} />
    <Fila icono="mic" titulo="Micrófono (dictar)" busy={busy === 'mic'} on={micOn} cambiar={microfono} sub={micSub}
      extra={mic === 'denied' ? <Mini onClick={() => setGuia({ tipo: 'microfono' })}>Cómo activarlo</Mini>
        : micOn ? <>{busy === 'mic' ? <><small>Habla ahora…</small><Nivel n={sonido} /></>
          : <Mini onClick={() => void probar()}>Probar el micrófono (1 segundo)</Mini>}
          {oido !== null && busy !== 'mic' && <small>{oido < 0 ? 'Funciona.' : oido < 0.04 ? 'Funciona, pero no te he oído: acércate más.' : 'Te oigo bien ✓'}</small>}</> : null} />
    {/* solo en la app: en el navegador las fotos van con el selector del sistema y no necesitan este permiso */}
    {EN_APP && <Fila icono="camera" titulo="Cámara (fotos)" busy={busy === 'cam'} on={cam === 'granted'} cambiar={camara} sub={camSub}
      extra={cam === 'denied' ? <Mini onClick={() => setGuia({ tipo: 'camara' })}>Cómo activarla</Mini> : null} />}
    {admin ? null : nivel === 'invitada'
      ? <Fila icono="calendar" titulo="Google (agenda, tareas y correo)" on={false} fijo sub="Tu acceso no incluye Google. Si lo necesitas, díselo a Fran." />
      : <Fila icono="calendar" titulo="Google (agenda, tareas y correo)" busy={busy === 'google' || g.loading} on={googleOn} cambiar={google}
        sub={googleOn ? `Conectado: ${asistente} ve tu agenda, tus tareas y tus correos (sin enviar nunca nada).` : 'Desconectado. Actívalo para conectar tu Gmail en un minuto.'} />}
    {!admin && <Fila icono="chat" titulo={`WhatsApp para hablar con ${asistente}`} busy={busy === 'wa' || (c.loading && !c.data)} on={waOn} cambiar={whatsapp}
      sub={subWhatsApp(c, asistente)} extra={waOn ? abrirWa : null} />}
    {!admin && ag.data && <Fila icono="calendar" titulo="WhatsApp para tu agenda" on={agOn.length > 0} cambiar={() => irA({ tab: 'ajustes', vista: 'agenda-chats' })}
      sub={agOn.length ? `${agOn.length === 1 ? 'Conectado' : `${agOn.length} conectados`} ✓: ${agOn.map(x => numeroWa(x.numero)).join(', ')}. Toca para añadir otro o quitarlo.`
        : ag.data.cuentas?.some(x => x.estado === 'esperando') ? 'Esperando el código de WhatsApp… Toca para verlo.'
        : `Sin conectar. ${asistente} puede leer tus chats y proponerte citas. Puedes conectar más de un WhatsApp.`} />}
    {admin && <Fila icono="calendar" titulo="Tu Google (agenda, tareas y correo)" on={!!fran.data?.google.some(x => !x.error)} cambiar={irCuentas}
      sub={fran.loading ? 'Comprobando…' : fran.data?.google.length ? `${fran.data.google.filter(x => !x.error).length} de ${fran.data.google.length} cuentas conectadas. Toca para verlas o añadir otra.` : 'Sin conectar. Toca para conectar tu Gmail.'} />}
    {admin && <FilaWhatsAppFran estado={fran.error ? null : fran.data?.whatsapp} sync={fran.data?.whatsapp_sync} vivo={fran.data?.whatsapp_vivo} cargando={fran.loading && !fran.data} irCuentas={irCuentas} toast={toast} />}
    {nivel !== 'invitada' && !admin && <Fila icono="shield" titulo="Pedirme permiso antes de apuntar nada" on fijo
      sub={`Siempre activado: ${asistente} nunca apunta citas ni tareas en tu Google sin tu «Permitir».`} />}
  </div>
}

const SECCION: Record<string, [IconName, string, string]> = {
  noticias: ['file', 'Noticias', 'Las de los temas y países que elijas'], correo: ['mail', 'Correo', 'Tus últimos correos (solo leer)'],
  rutinas: ['clock', 'Rutinas', 'Mensajes automáticos a tu hora'], carpetas: ['folder', 'Carpetas', 'Tus notas, fotos y archivos'],
  tareas: ['check', 'Tareas', 'Tu lista de tareas de Google'], dinero: ['shield', 'Dinero', 'Tus gastos y suscripciones'],
}
const PORTADA: Record<string, string> = { chat: 'El chat', inicio: 'La agenda', noticias: 'Noticias', carpetas: 'Carpetas', rutinas: 'Rutinas', dinero: 'Dinero', correo: 'Correo', tareas: 'Tareas' }

/** «Tu menú»: qué secciones quiere ver y cuál abre primero. Chat, Agenda y Tu espacio se quedan siempre. */
export function TuMenu({ me, toast, cambio }: { me: Me; toast: (m: string) => void; cambio: () => void }) {
  const posibles = me.menu_posible || []
  const [ocultas, setOcultas] = useState<string[]>(me.ocultas || [])
  const [portada, setPortada] = useState(me.portada || 'inicio')
  const [busy, setBusy] = useState(false)
  const guardar = async (o: string[], p = portada) => {
    setBusy(true)
    try { await post('/api/mi-zazu', { action: 'menu', ocultas: o, portada: p }); setOcultas(o); setPortada(p); cambio() }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  const visibles = ['chat', 'inicio', ...posibles.filter(t => !ocultas.includes(t))]
  return <div className="settings-list">
    {posibles.map(t => { const [ico, tit, sub] = SECCION[t] || ['spark', t, '']; const on = !ocultas.includes(t)
      return <Fila key={t} icono={ico} titulo={tit} sub={on ? sub : 'Oculta en tu menú'} on={on} busy={busy}
        cambiar={() => void guardar(on ? [...ocultas, t] : ocultas.filter(x => x !== t), !on || portada !== t ? portada : 'inicio').then(() => toast(on ? `${tit} ya no sale en tu menú` : `${tit} vuelve a tu menú`))} /> })}
    {!posibles.includes('noticias') && <Fila icono="file" titulo="Noticias" sub="Muy pronto: las de los temas y países que tú elijas." on={false} fijo />}
    {!posibles.includes('dinero') && me.nivel !== 'invitada' && <Fila icono="shield" titulo="Dinero" sub="Muy pronto: tus gastos y suscripciones, sacados de tus recibos de Gmail." on={false} fijo />}
    <div className="setting-row" style={{ alignItems: 'flex-start', paddingTop: 12, paddingBottom: 12 }}>
      <span className="setting-icon"><Icon name="spark" size={19} /></span>
      <span className="setting-copy"><strong>Lo que más usas: ábrelo primero</strong><small>Al abrir la app, ir directamente a…</small>
        <select className="campo" style={{ marginTop: 6 }} value={visibles.includes(portada) ? portada : 'inicio'} disabled={busy} onChange={e => void guardar(ocultas, e.target.value).then(() => toast('Guardado'))}>
          {visibles.map(t => <option key={t} value={t}>{PORTADA[t] || t}</option>)}</select></span>
    </div>
  </div>
}
