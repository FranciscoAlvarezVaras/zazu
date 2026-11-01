import { useEffect, useRef, useState } from 'react'
import { Icon } from '../icons'
import { PROFILE_HINTS, PROFILE_NAMES } from '../data'
import { EN_APP, fmtSize, irA, post, useFetch, useParams } from '../lib'
import type { Status, Usage } from '../lib'
import type { Ctx } from '../ctx'
import { esEstilo, PERFIL_HERMES } from '../tipos'

/** Estados del servidor y de los canales, en cristiano. */
const GATEWAY: Record<string, string> = { running: 'Despierto', starting: 'Despertando…', draining: 'Terminando lo que tenía a medias', degraded: 'Funciona, pero con algún fallo', startup_failed: 'No pudo arrancar', stopped: 'Apagado' }
const CANAL: Record<string, string> = { connected: 'Conectado', connecting: 'Conectando…', retrying: 'Reconectando…', disconnected: 'Desconectado', fatal: 'Desconectado: hay que volver a vincularlo', disabled: 'Desactivado', paused: 'En pausa', failed: 'No consiguió conectar', pending: 'Pendiente' }
export const estadoCanal = (s?: string | null) => s ? CANAL[s] || 'No sé cómo está ahora' : 'Sin datos'
const ORIGEN: Record<string, string> = { '': 'App', hub: 'App', whatsapp: 'WhatsApp', telegram: 'Telegram', cli: 'Ordenador', cron: 'Rutina', api_server: 'App' }
/** /api/usage manda «perfil/origen» (default/whatsapp): «WhatsApp», o «App · Charla ligera» si es otro modo de Zazu. */
const origen = (src = '') => {
  const i = src.lastIndexOf('/'), perfil = i < 0 ? 'default' : src.slice(0, i), o = src.slice(i + 1)
  const txt = ORIGEN[o] || o[0].toUpperCase() + o.slice(1)
  return perfil && perfil !== 'default' && perfil !== PERFIL_HERMES ? `${txt} · ${PROFILE_NAMES[perfil] || perfil[0].toUpperCase() + perfil.slice(1)}` : txt
}

const k = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(0)} k` : String(n)

/** `serviceWorker.ready` no termina nunca si el registro falló (main.tsx se lo calla): a los 8 s, error a la vista. */
const swListo = () => Promise.race([navigator.serviceWorker.ready, new Promise<never>((_, ko) => setTimeout(() => ko(new Error('el servicio de la app no arrancó; recarga la página')), 8000))])

const b64 = (s: string) => { const p = (s + '='.repeat((4 - s.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/'); return Uint8Array.from(atob(p), c => c.charCodeAt(0)) }

/** Notificaciones de la app en este dispositivo (Web Push). Fran: alertas del servidor y permisos; una invitada, lo suyo. */
/** Avisos push de este dispositivo: estado, activar y quitar (lo usan AlertasPush y el panel de permisos). */
import { FormPreferencias, type Prefs } from './Preferencias'
import Bienvenida from './Bienvenida'
import { GatoIcono } from '../panel/GatoIcono'
import { PanelPermisos } from './Permisos'
import { AgendaChatsFran } from './AgendaChats'
import { GuiaPermiso, abrirAjustes, appConAvisos, callar, dondeTexto, nativo, silenciado } from './PermisosDispositivo'
const PUSH = 'hz-push'   // «cambió la suscripción en este dispositivo»: los dos controles (interruptor y tarjeta) se ponen al día
export type EstadoPush = '?' | 'si' | 'no' | 'bloqueado' | 'nosoporta' | 'error'
export function usePush(toast: (m: string) => void, admin = false) {
  const info = useFetch<{ clave: string | null; n: number }>('/api/push')
  const [estado, setEstado] = useState<EstadoPush>('?')
  const [fallo, setFallo] = useState('')
  const [busy, setBusy] = useState(false)
  const recargar = useRef(info.reload); recargar.current = info.reload
  useEffect(() => {
    let vivo = true
    const mirar = async () => {
      if (EN_APP || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return setEstado('nosoporta')
      if (Notification.permission === 'denied') return setEstado('bloqueado')
      // Chrome ya no pregunta (contestó «no» al instante): para ella está bloqueado, igual que dice la hoja
      if (Notification.permission === 'default' && silenciado('notificaciones')) return setEstado('bloqueado')
      if (Notification.permission === 'granted') callar('notificaciones', false)
      try { const reg = await swListo(); const sub = await reg.pushManager.getSubscription(); if (vivo) setEstado(sub && Notification.permission === 'granted' ? 'si' : 'no') }
      catch (e) { if (vivo) { setFallo((e as Error).message); setEstado('error') } }
    }
    void mirar()
    // al desbloquearlas en los ajustes y volver, sin recargar la página
    let st: PermissionStatus | null = null
    navigator.permissions?.query({ name: 'notifications' as PermissionName }).then(p => { st = p; p.onchange = () => void mirar() }, () => { })
    const vis = () => { if (!document.hidden) void mirar() }
    const otro = () => { void mirar(); void recargar.current() }
    document.addEventListener('visibilitychange', vis); addEventListener(PUSH, otro)
    return () => { vivo = false; if (st) st.onchange = null; document.removeEventListener('visibilitychange', vis); removeEventListener(PUSH, otro) }
  }, [])
  /** Devuelve 'bloqueado' si hay que enseñar cómo desbloquearlas. Cada salida avisa: nunca un toque sin respuesta. */
  const activar = async (): Promise<EstadoPush | undefined> => {
    if (!info.data) {
      if (info.loading) toast('Un segundo, que estoy preparando las notificaciones. Prueba otra vez.')
      else { toast(`No pude preguntar al servidor por las notificaciones${info.error ? `: ${info.error}` : ''}. Prueba otra vez.`); void info.reload() }
      return
    }
    if (!info.data.clave) { toast(admin ? 'Falta preparar las notificaciones en el servidor (la clave VAPID). Pídeselo a Claude.' : 'Las notificaciones no están preparadas en el servidor. Díselo a Fran.'); return }
    setBusy(true)
    try {
      const t0 = performance.now()
      const perm = await Notification.requestPermission()
      if (perm === 'denied') { setEstado('bloqueado'); toast('Notificaciones bloqueadas. Te enseño cómo activarlas.'); return 'bloqueado' }
      if (perm !== 'granted') {   // cerró la pregunta sin elegir, o el navegador la silenció (contesta al instante)
        if (performance.now() - t0 < 350) { callar('notificaciones', true); setEstado('bloqueado'); toast('El navegador no me deja preguntar. Te enseño cómo activarlas.'); return 'bloqueado' }
        toast('No has elegido nada. Toca otra vez y pulsa «Permitir».'); return
      }
      callar('notificaciones', false)
      const reg = await swListo()
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(info.data.clave) })
      const ua = navigator.userAgent
      await post('/api/push', { action: 'suscribir', sub: sub.toJSON(), equipo: /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iPhone' : 'Ordenador' })
      setEstado('si'); dispatchEvent(new Event(PUSH))
      await post('/api/push', { action: 'prueba' }); toast('Listo: te acabo de mandar una notificación de prueba')
      return 'si'
    } catch (e) { toast(`No se pudo activar: ${(e as Error).message}`) } finally { setBusy(false) }
  }
  const desactivar = async () => {
    setBusy(true)
    try {
      const sub = await (await swListo()).pushManager.getSubscription()
      if (sub) { await post('/api/push', { action: 'quitar', endpoint: sub.endpoint }); await sub.unsubscribe() }
      setEstado('no'); dispatchEvent(new Event(PUSH)); toast('Este dispositivo ya no recibirá notificaciones')
    } catch (e) { toast((e as Error).message) } finally { setBusy(false) }
  }
  const probar = () => post('/api/push', { action: 'prueba' }).then(() => toast('Enviada una notificación de prueba'), e => toast((e as Error).message))
  return { info, estado, fallo, busy, activar, desactivar, probar }
}

export function AlertasPush({ toast, guest }: { toast: (m: string) => void; guest?: boolean }) {
  const { info, estado, fallo, busy, activar, desactivar, probar } = usePush(toast, !guest)
  const [guia, setGuia] = useState(false)
  const conPuente = EN_APP && !!nativo()
  return <div className="acc-card">
    {guia && <GuiaPermiso tipo="notificaciones" toast={toast} cerrar={() => setGuia(false)} />}
    <div className="acc-top"><span className="setting-icon"><Icon name="bell" size={19} /></span><div><strong>{guest ? 'Notificaciones en este dispositivo' : 'Alertas en este dispositivo'}</strong>
      <small>{estado === 'si' ? guest ? 'Activadas.' : 'Activadas: si algo falla te llega una notificación de Zazu aquí.' : estado === 'bloqueado' ? `Bloqueadas ${dondeTexto()}. Toca «Cómo activarlas».` : estado === 'nosoporta' ? (/iPhone|iPad/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) ? 'En el iPhone, las notificaciones solo funcionan con Zazu en la pantalla de inicio: Compartir › Añadir a pantalla de inicio, y ábrela desde ese icono.' : EN_APP && !guest && appConAvisos() ? 'En esta app, los recordatorios, las rutinas, los permisos de Zazu y las alertas del servidor llegan como notificación de la app (pueden tardar hasta 15 minutos). Si no te llegan, activa sus notificaciones.' : EN_APP ? 'En esta app, los recordatorios y las rutinas todavía no llegan como notificación: te llegan por WhatsApp o activándolas en holazazu.app desde Chrome.' + (guest ? '' : ' Los avisos para Permitir o Rechazar sí los da la app.') : 'Este navegador no admite notificaciones. En el móvil, abre la app Zazu instalada.') : estado === 'error' ? `No se pueden activar aquí: ${fallo}.` : 'Recibe aquí una notificación si algo falla en el servidor.'}{info.data ? ` · ${info.data.n} dispositivo${info.data.n === 1 ? '' : 's'} con alertas` : ''}</small></div></div>
    {estado === 'no' && info.error && !info.data && <p className="muted-note">No se pudo preguntar al servidor por las alertas: {info.error}. <button className="text-link" onClick={() => void info.reload()}>Reintentar</button></p>}
    {estado === 'no' && <button className="btn-primary" disabled={busy || info.loading} onClick={() => void activar().then(r => { if (r === 'bloqueado') setGuia(true) })}>{busy ? 'Activando…' : info.loading ? 'Cargando…' : 'Activar alertas aquí'}</button>}
    {estado === 'bloqueado' && <button className="btn-primary" onClick={() => setGuia(true)}>Cómo activarlas</button>}
    {estado === 'nosoporta' && conPuente && <button className="btn-secondary" onClick={() => { if (!abrirAjustes('notificaciones')) toast('No pude abrir los ajustes') }}>Abrir ajustes de notificaciones</button>}
    {estado === 'si' && <div className="actions"><button className="btn-secondary" disabled={busy} onClick={() => void probar()}>Probar</button>
      <button className="text-link" disabled={busy} onClick={() => void desactivar()}>Desactivar</button></div>}
  </div>
}

export default function Ajustes({ chat, go, toast, me }: Ctx) {
  const vista = useParams().vista
  const [repaso, setRepaso] = useState(vista === 'guia')   // «Ver la guía otra vez» (aquí o desde el menú): sin tocar `onboarded`
  useEffect(() => { if (vista === 'guia') setRepaso(true) }, [vista])
  const st = useFetch<Status>('/api/status', 30000)
  const us = useFetch<Usage>('/api/usage')
  const s = st.data
  const total = (us.data?.days || []).reduce((a, d) => a + d.usd, 0)
  const wa = s ? s.platforms.whatsapp ?? Object.values(s.platforms)[0] : undefined
  const estilos = chat.profiles.filter(esEstilo)   // Asistentes: Charla, Escritor, Investigador, Viajes… (los perfiles de siempre, sin el motor ni las invitadas)
  const info = (icon: 'shield' | 'spark' | 'clock' | 'bell', a: string, b: string, ok?: boolean) =>
    <div className="setting-row informational" key={a}><span className="setting-icon"><Icon name={icon} size={19} /></span><span className="setting-copy"><strong>{a}</strong><small className={ok === undefined ? '' : ok ? 'ok' : 'bad'}>{b}</small></span></div>
  if (repaso) return <div className="onb-capa"><Bienvenida me={me} toast={toast} repaso done={() => { setRepaso(false); if (vista === 'guia') irA({ tab: 'ajustes' }, true) }} /></div>
  return <div className="settings-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">HECHO A TU MEDIDA</span><h2>Tu espacio<span className="greeting-dot">.</span></h2><p>Estado, gasto y preferencias.</p></div>
    <div className="profile-card fran-card"><GatoIcono n="cara" size={46} /><div><strong>{me.name || 'Fran'}</strong><small>Tu espacio: tus permisos, tus cuentas y cómo te trata Zazu</small></div></div>
    <button className="text-link" style={{ display: 'block', margin: '0 auto 10px' }} onClick={() => setRepaso(true)}><Icon name="lightbulb" size={15} /> Ver la guía otra vez (permisos, cuentas y menú)</button>
    <div className="settings-group"><span className="section-kicker">TÚ, TU PAÍS Y TU HORA</span><div className="acc-card">
      <FormPreferencias nombre={me.name || 'Fran'} prefs={(me as { prefs?: Prefs }).prefs} asistente="Zazu" toast={toast} guardado={() => {}} /></div></div>
    <div className="settings-group"><span className="section-kicker">TUS PERMISOS Y CUENTAS</span>
      <PanelPermisos admin asistente="Zazu" toast={toast} cambio={() => {}} irWhatsApp={() => go('cuentas')} irCuentas={() => go('cuentas')} /></div>
    {me.role === 'admin' && <AgendaChatsFran toast={toast} />}
    {!EN_APP && /Android/.test(navigator.userAgent) && <div className="settings-group"><span className="section-kicker">APP DE ANDROID</span><div className="acc-card">
      <div className="acc-top"><span className="setting-icon"><Icon name="spark" size={19} /></span><div><strong>Zazu como app</strong><small>Se instala una vez y siempre abre la versión de hoy, sin copias viejas. Al descargarla, el móvil te pedirá permitir instalar desde Chrome.</small></div></div>
      <a className="btn-secondary" href="/zazu.apk" download>Descargar la app de Android</a></div></div>}
    <div className="settings-group"><span className="section-kicker">ESTADO</span><div className="settings-list">
      {info('spark', 'Zazu', s ? GATEWAY[s.gateway] || 'No sé cómo está ahora' : st.error ? 'No pude comprobarlo ahora' : 'Comprobando…', s ? s.gateway === 'running' : st.error ? false : undefined)}
      {info('bell', 'WhatsApp', s ? estadoCanal(wa) : st.error ? 'No pude comprobarlo ahora' : '…', s ? wa === 'connected' : undefined)}
      {info('clock', 'Versión y espacio', s ? `Zazu ${s.version || '—'} · app ${__HUB_V__} · ${fmtSize(s.disk_free).replace('.', ',')} libres en el PC` : '…')}
    </div>{st.error && <div className="fallo" role="alert"><span>No pude comprobar el estado.</span><button type="button" className="reintentar" onClick={() => void st.reload()}>Reintentar</button></div>}</div>
    <div className="settings-group"><span className="section-kicker">GASTO · 7 DÍAS</span><div className="settings-list">
      {info('shield', `${total.toFixed(2).replace('.', ',')} USD estimados`, us.data ? `${us.data.days.reduce((a, d) => a + d.calls, 0)} llamadas` : us.error ? 'No pude calcularlo ahora' : 'Calculando…')}
      {(us.data?.top || []).slice(0, 3).map(t => info('spark', t.title || 'Conversación sin título', `${origen(t.source)} · ${t.calls} llamadas · ${k(t.avg_ctx)} de contexto · ${String(t.usd).replace('.', ',')} USD`))}
    </div><p className="muted-note">Si una conversación pasa de ~80 k de contexto, empieza otra al cambiar de tema.</p></div>
    <button className="inline-link-card" onClick={() => { go('cuentas'); setTimeout(() => document.getElementById('personas')?.scrollIntoView({ behavior: 'smooth' }), 400) }}><span className="inline-link-icon"><Icon name="plus" size={19} /></span><span><strong>Personas y accesos</strong><small>Dar acceso, nivel, crédito y lista de espera</small></span><Icon name="arrow" size={17} /></button>
    <button className="inline-link-card" onClick={() => go('cuentas')}><span className="inline-link-icon"><Icon name="shield" size={19} /></span><span><strong>Cuentas conectadas</strong><small>Google y WhatsApp</small></span><Icon name="arrow" size={17} /></button>
    {estilos.length > 0 && <div className="settings-group"><span className="section-kicker">ASISTENTES</span><div className="settings-list">
      {estilos.map(p => <button type="button" className="setting-row estilo-fila" key={p} onClick={() => { chat.newChat(p); irA({ tab: 'chat', perfil: p }) }}>
        <span className="setting-icon"><Icon name="spark" size={19} /></span>
        <span className="setting-copy"><strong>{PROFILE_NAMES[p] || p[0].toUpperCase() + p.slice(1)}</strong><small>{PROFILE_HINTS[p] || 'Para una conversación más ligera o especializada'}</small></span>
        <Icon name="chevron" size={16} /></button>)}
    </div><p className="muted-note">Cada uno abre una conversación nueva con un asistente de un solo oficio. El chat de siempre ya lo tiene todo; estos gastan menos o saben hacer una cosa muy bien. Los permisos solo se piden en el chat normal.</p></div>}
    <button className="btn-secondary" style={{ marginTop: 8 }} onClick={() => { void fetch('/api/logout', { method: 'POST', headers: { 'X-Hub': '1' } }).then(() => location.replace('/login')) }}>Cerrar sesión</button>
    <div className="settings-signature">Un poco de calma en cada día. <Icon name="spark" size={15} /></div>
  </div>
}
