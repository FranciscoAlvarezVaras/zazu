import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { EN_APP, useAtrasCierra } from '../lib'

/** Permisos del dispositivo (ubicación, micrófono, cámara, notificaciones): el estado de verdad, pedirlos y,
 *  si están bloqueados, la guía para desbloquearlos según dónde esté abierta la app.
 *  En la app de Android (2.4 o más) hay un puente, window.ZazuNativo, que da el estado real del sistema y abre sus ajustes.
 *  Sin puente, en un WebView `permissions.query` no dice la verdad (micro y cámara contestan siempre «prompt» o «denied»):
 *  ahí solo vale lo que pasó al pedirlo, que se recuerda en este dispositivo. */
export type Tipo = 'ubicacion' | 'microfono' | 'camara' | 'notificaciones'
export type E = 'granted' | 'denied' | 'prompt' | '?'
type Nativo = { version?: () => string; estado: () => string; pedir: (t: string) => void; abrirAjustes: (t: string) => void }
type EstadoNativo = Partial<Record<Tipo, E>> & { ubicacionSistema?: 'on' | 'off' }

export const nativo = (): Nativo | null => {
  const n = typeof window !== 'undefined' ? (window as unknown as { ZazuNativo?: Nativo }).ZazuNativo : undefined
  return n && typeof n.estado === 'function' && typeof n.pedir === 'function' ? n : null
}
export function leerNativo(): EstadoNativo | null {
  const n = nativo()
  if (!n) return null
  try { return JSON.parse(n.estado()) as EstadoNativo } catch { return null }
}
/** App 2.5 o más: recoge los avisos de Zazu (recordatorios, rutinas, permisos, alertas) y los enseña como notificación.
 *  Solo le llegan a Fran: el móvil de la app se registra con su sesión (las invitadas siguen con la web instalada). */
export function appConAvisos(): boolean {
  const [a, b] = (nativo()?.version?.() || '0').split('.').map(Number)
  return a > 2 || (a === 2 && b >= 5)
}
/** Abre los ajustes del sistema (solo en la app con puente). tipo: también 'whatsapp' (abre WhatsApp). */
export function abrirAjustes(t: Tipo | 'whatsapp'): boolean {
  const n = nativo()
  if (!n || typeof n.abrirAjustes !== 'function') return false
  try { n.abrirAjustes(t); return true } catch { return false }
}

export const NOMBRE: Record<Tipo, string> = { ubicacion: 'Ubicación', microfono: 'Micrófono', camara: 'Cámara', notificaciones: 'Notificaciones' }
export const EL: Record<Tipo, string> = { ubicacion: 'la ubicación', microfono: 'el micrófono', camara: 'la cámara', notificaciones: 'las notificaciones' }
const BLOQ: Record<Tipo, string> = { ubicacion: 'Ubicación bloqueada', microfono: 'Micrófono bloqueado', camara: 'Cámara bloqueada', notificaciones: 'Notificaciones bloqueadas' }
const LO: Record<Tipo, string> = { ubicacion: 'la', microfono: 'lo', camara: 'la', notificaciones: 'las' }
const QUERY: Record<Tipo, string> = { ubicacion: 'geolocation', microfono: 'microphone', camara: 'camera', notificaciones: 'notifications' }

/** «Ya funcionó en este dispositivo»: tras un getUserMedia o una posición que salieron bien (Chrome con «solo esta vez»
 *  y el WebView vuelven a decir «prompt» aunque funcione). */
const CLAVE = (t: Tipo) => `hz-ok-${t}`
/** «Falló al pedirlo»: en la app sin puente, que lo negó; en el navegador, que el sitio tiene permiso pero el navegador no tiene el del sistema. */
const NO = (t: Tipo) => `hz-no-${t}`
const leerSi = (k: string) => { try { return localStorage.getItem(k) === '1' } catch { return false } }
const recordado = (t: Tipo) => leerSi(CLAVE(t))
const negado = (t: Tipo) => leerSi(NO(t))
/** «El navegador ya no pregunta» (contestó «no» al instante): permissions.query sigue diciendo «prompt», pero para ella está bloqueado.
 *  Chrome lo silencia unos días; se olvida a la semana, al funcionar o si el navegador ya dice otra cosa. */
const SILENCIO = (t: Tipo) => `hz-silencio-${t}`
export const silenciado = (t: Tipo) => { try { return Date.now() - Number(localStorage.getItem(SILENCIO(t)) || 0) < 7 * 86400e3 } catch { return false } }
export const callar = (t: Tipo, si: boolean) => { try { if (si) localStorage.setItem(SILENCIO(t), String(Date.now())); else localStorage.removeItem(SILENCIO(t)) } catch { /* sin almacenamiento */ } }
/** El navegador del móvil o del PC no tiene el permiso del sistema (el sitio sí): los pasos son los del sistema. */
export const faltaSistema = (t: Tipo) => !EN_APP && negado(t)
const CAMBIO = 'hz-permiso'
/** si: funcionó. Si no, se olvida lo que funcionó y, con `no`, se recuerda que falló. */
export function recordar(t: Tipo, si: boolean, no = false) {
  if (si) callar(t, false)
  try {
    if (si) { localStorage.setItem(CLAVE(t), '1'); localStorage.removeItem(NO(t)) }
    else { localStorage.removeItem(CLAVE(t)); if (no) localStorage.setItem(NO(t), '1'); else localStorage.removeItem(NO(t)) }
  } catch { /* sin almacenamiento */ }
  dispatchEvent(new CustomEvent(CAMBIO, { detail: { tipo: t } }))
}

async function query(t: Tipo): Promise<E> {
  try { return (await navigator.permissions.query({ name: QUERY[t] as PermissionName })).state as E } catch { return '?' }
}

/** El estado de verdad, con lo mejor que haya: el puente de la app, permissions.query o lo recordado. */
export async function estadoPermiso(t: Tipo): Promise<E> {
  const nat = leerNativo()
  if (nat) return nat[t] || '?'
  if (EN_APP) return recordado(t) ? 'granted' : negado(t) ? 'denied' : '?'   // app sin puente: query miente; vale lo que pasó al pedirlo
  if (t === 'notificaciones' && 'Notification' in window) { const p = Notification.permission; return p === 'default' ? 'prompt' : p }
  const q = await query(t)
  if (q !== 'prompt' && silenciado(t)) callar(t, false)
  if (q === 'denied') { if (recordado(t) || negado(t)) recordar(t, false); return 'denied' }
  if (q === 'granted') return negado(t) ? 'denied' : 'granted'   // el sitio sí, pero el navegador no tiene el permiso del sistema
  return recordado(t) ? 'granted' : q === 'prompt' && silenciado(t) ? 'denied' : q
}

/** Estado de un permiso que se pone al día solo: al cambiarlo en el navegador, al volver de los ajustes y al pedirlo en otra pantalla. */
export function usePermiso(t: Tipo): [E, () => void, (e: E) => void] {
  const [e, setE] = useState<E>('?')
  const mirar = useCallback(() => { void estadoPermiso(t).then(setE) }, [t])
  useEffect(() => {
    mirar()
    let st: PermissionStatus | null = null
    if (!EN_APP && navigator.permissions) navigator.permissions.query({ name: QUERY[t] as PermissionName }).then(p => { st = p; p.onchange = mirar }, () => { })
    const vis = () => { if (!document.hidden) mirar() }
    const ev = (x: Event) => { const d = (x as CustomEvent).detail as { tipo?: string } | undefined; if (!d?.tipo || d.tipo === t) mirar() }
    document.addEventListener('visibilitychange', vis)
    addEventListener('zazu-permiso', ev); addEventListener('zazu-permisos', mirar); addEventListener(CAMBIO, ev); addEventListener('focus', vis)
    return () => {
      if (st) st.onchange = null
      document.removeEventListener('visibilitychange', vis)
      removeEventListener('zazu-permiso', ev); removeEventListener('zazu-permisos', mirar); removeEventListener(CAMBIO, ev); removeEventListener('focus', vis)
    }
  }, [mirar, t])
  return [e, mirar, setE]
}

/** El estado del puente de la app (null sin puente), al día: al pedir un permiso, al volver de Ajustes y al volver a la app. */
export function useNativo(): EstadoNativo | null {
  const [n, setN] = useState(leerNativo)
  useEffect(() => {
    if (!nativo()) return
    const mirar = () => setN(leerNativo())
    const vis = () => { if (!document.hidden) mirar() }
    addEventListener('zazu-permiso', mirar); addEventListener('zazu-permisos', mirar); addEventListener('focus', mirar)
    document.addEventListener('visibilitychange', vis)
    return () => { removeEventListener('zazu-permiso', mirar); removeEventListener('zazu-permisos', mirar); removeEventListener('focus', mirar); document.removeEventListener('visibilitychange', vis) }
  }, [])
  return n
}

/** En la app con puente: pide el permiso del sistema y espera la respuesta (evento zazu-permiso). */
export function pedirNativo(t: Tipo): Promise<E> {
  const n = nativo()
  if (!n) return Promise.resolve('?')
  if (leerNativo()?.[t] === 'granted') return Promise.resolve('granted')
  return new Promise(ok => {
    let hecho = false
    const fin = (e: E) => { if (hecho) return; hecho = true; removeEventListener('zazu-permiso', on); clearTimeout(tope); ok(e) }
    const on = (x: Event) => { const d = (x as CustomEvent).detail as { tipo?: string; estado?: E } | undefined; if (d?.tipo === t) fin(d.estado || '?') }
    addEventListener('zazu-permiso', on)
    const tope = setTimeout(() => fin(leerNativo()?.[t] || '?'), 90000)
    try { n.pedir(t) } catch { fin('?') }
  })
}

/** Lo que pasó al pedir: el estado y, si falló por otra cosa, por qué. `rapido`: el navegador dijo que no sin preguntar. */
export type Pedido = { estado: E; error?: 'nodispositivo' | 'ocupado' | 'posicion' | 'inseguro' | 'otro'; stream?: MediaStream; pos?: GeolocationPosition
  /** el sitio tiene permiso, pero el navegador no tiene el del sistema (Android: Chrome sin micrófono) */ sistema?: boolean
  /** el navegador contestó «no» al instante, sin que se viera la pregunta */ silenciado?: boolean }

/** Tras un «no» del navegador: ¿lo ha bloqueado o solo se cerró la pregunta? (Chrome da el mismo error en los dos casos.) */
async function trasNo(t: Tipo, ms: number): Promise<Pedido> {
  if (EN_APP && nativo()) { recordar(t, false); return { estado: 'denied' } }   // lo que funcionó antes ya no vale
  // app sin puente (2.3): si el diálogo de Android se vio y se cerró, volverá a preguntar; solo un «no» al instante es bloqueo
  if (EN_APP) { recordar(t, false, ms < 350); return { estado: ms < 350 ? 'denied' : 'prompt' } }
  const q = await query(t)
  if (q === 'denied') { recordar(t, false); return { estado: 'denied' } }
  if (q === 'granted') { recordar(t, false, true); return { estado: 'denied', sistema: true } }   // típico en Android: Chrome no tiene el micrófono del móvil
  recordar(t, false)
  // contestó «no» al instante sin que nadie viera la pregunta: el navegador ya no pregunta (la ha silenciado); se recuerda para que la fila diga lo mismo que la hoja
  if (ms < 350) { callar(t, true); dispatchEvent(new CustomEvent(CAMBIO, { detail: { tipo: t } })); return { estado: 'denied', silenciado: true } }
  return { estado: 'prompt' }
}

/** Pide micrófono o cámara de verdad (getUserMedia). Si va bien, devuelve el stream: hay que pararlo. */
export async function pedirMedio(t: 'microfono' | 'camara'): Promise<Pedido> {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) return { estado: '?', error: 'inseguro' }
  if (nativo()) { const n = await pedirNativo(t); if (n !== 'granted') return { estado: n === '?' ? 'prompt' : n } }
  const t0 = performance.now()
  try {
    const stream = await navigator.mediaDevices.getUserMedia(t === 'microfono' ? { audio: true } : { video: true })
    recordar(t, true)
    return { estado: 'granted', stream }
  } catch (e) {
    const n = (e as Error)?.name
    if (n === 'NotAllowedError' || n === 'SecurityError') return await trasNo(t, performance.now() - t0)
    if (n === 'NotFoundError' || n === 'OverconstrainedError') return { estado: '?', error: 'nodispositivo' }
    if (n === 'NotReadableError' || n === 'AbortError') return { estado: '?', error: 'ocupado' }
    return { estado: '?', error: 'otro' }
  }
}

/** Pide la posición (con el permiso del sistema antes, en la app). */
export async function pedirPosicion(): Promise<Pedido> {
  if (!('geolocation' in navigator)) return { estado: '?', error: 'inseguro' }
  if (nativo()) {
    const n = await pedirNativo('ubicacion')
    if (n !== 'granted') return { estado: n === '?' ? 'prompt' : n }
    if (leerNativo()?.ubicacionSistema === 'off') return { estado: 'granted', error: 'posicion' }
  }
  const t0 = performance.now()
  const r = await new Promise<GeolocationPosition | GeolocationPositionError>(ok => navigator.geolocation.getCurrentPosition(ok, ok, { maximumAge: 3600_000, timeout: 15000 }))
  if ('coords' in r) { recordar('ubicacion', true); return { estado: 'granted', pos: r } }
  if (r.code === 1) return await trasNo('ubicacion', performance.now() - t0)
  return { estado: recordado('ubicacion') ? 'granted' : '?', error: 'posicion' }
}

/** Una frase para lo que pasó al pedirlo. */
export function mensajePedido(t: Tipo, p: Pedido): string {
  if (p.error === 'nodispositivo') return t === 'camara' ? 'No encuentro ninguna cámara en este dispositivo.' : 'No encuentro ningún micrófono en este dispositivo.'
  if (p.error === 'ocupado') return `Otra app está usando ${EL[t]}. Ciérrala y prueba otra vez.`
  if (p.error === 'inseguro') return `Aquí no se puede usar ${EL[t]}: abre holazazu.app con https.`
  if (p.error === 'posicion') return leerNativo()?.ubicacionSistema === 'off' ? 'La ubicación del móvil está apagada: enciéndela y vuelve a probar.' : 'No pude saber dónde estás ahora. Mira que la ubicación del móvil esté encendida y prueba otra vez.'
  if (p.sistema) return `${QUIEN[donde()]} no tiene permiso para usar ${EL[t]}. Te enseño cómo dárselo.`
  if (p.silenciado) return `El navegador no me ha dejado preguntar por ${EL[t]} (lo hace si se ha cerrado la pregunta varias veces). Te enseño cómo permitirlo.`
  if (p.estado === 'denied') return `${BLOQ[t]} ${LUGAR[donde()]}. Te enseño cómo activar ${EL[t]}.`
  if (p.estado === 'prompt') return nativo() || EN_APP ? `Has dicho que no. Si quieres usar${LO[t]}, toca otra vez y pulsa «Permitir».`
    : 'No has elegido nada. Toca otra vez y, cuando el móvil pregunte, pulsa «Permitir».'
  return `No pude usar ${EL[t]}. Prueba otra vez.`
}

/** Dónde está abierta Zazu: cada sitio tiene sus ajustes. */
export type Donde = 'app' | 'android-pwa' | 'android' | 'iphone-pwa' | 'iphone' | 'firefox' | 'edge' | 'safari-mac' | 'pc'
export function donde(): Donde {
  const ua = navigator.userAgent
  if (EN_APP) return 'app'
  const pwa = matchMedia('(display-mode: standalone)').matches || (navigator as unknown as { standalone?: boolean }).standalone === true
  if (/iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) return pwa ? 'iphone-pwa' : 'iphone'
  if (/Android/.test(ua)) return pwa ? 'android-pwa' : 'android'
  if (/Firefox\//.test(ua)) return 'firefox'
  if (/Edg\//.test(ua)) return 'edge'
  if (/Safari\//.test(ua) && !/Chrome|Chromium/.test(ua)) return 'safari-mac'
  return 'pc'
}
const LUGAR: Record<Donde, string> = { app: 'en la app HolaZazu', 'android-pwa': 'en Zazu instalada', android: 'en Chrome', 'iphone-pwa': 'en Zazu instalada', iphone: 'en Safari', firefox: 'en Firefox', edge: 'en Edge', 'safari-mac': 'en Safari', pc: 'en el navegador' }
export const dondeTexto = () => LUGAR[donde()]
/** Quién no tiene el permiso del sistema cuando el sitio sí lo tiene. */
const QUIEN: Record<Donde, string> = { app: 'La app HolaZazu', 'android-pwa': 'Chrome', android: 'Chrome', 'iphone-pwa': 'Safari', iphone: 'Safari', firefox: 'Firefox', edge: 'Edge', 'safari-mac': 'Safari', pc: 'El navegador' }
/** En Android, «Permitir» a secas ya no existe para ubicación, micrófono y cámara (Android 11 o más). */
const SOLO_USO = '«Permitir solo mientras se usa la aplicación» (o «Permitir»)'

/** Los pasos exactos para desbloquearlo aquí. */
export function pasos(t: Tipo, d: Donde = donde(), nat: EstadoNativo | null = leerNativo()): string[] {
  const N = NOMBRE[t]
  const permitir = `«${N}» › «Permitir»`
  if (d === 'app') {   // en Android la app se llama «HolaZazu» (así sale en Ajustes › Aplicaciones)
    if (nat) {
      if (t === 'notificaciones') return ['Pulsa «Abrir ajustes» aquí abajo.', 'Activa «Mostrar notificaciones» (o «Todas las notificaciones de HolaZazu»).', 'Vuelve a la app: se comprueba solo.']
      if (t === 'ubicacion' && nat.ubicacionSistema === 'off') return ['La ubicación del móvil está apagada.', 'Pulsa «Abrir ajustes» y enciende «Usar ubicación».', 'Vuelve a la app: se comprueba solo.']
      return ['Pulsa «Abrir ajustes» aquí abajo.', `Entra en «Permisos» › «${N}».`, `Elige ${SOLO_USO}.`, 'Vuelve a la app: se comprueba solo.']
    }
    return ['Abre los Ajustes del móvil › «Aplicaciones» › «HolaZazu».', t === 'notificaciones' ? 'Entra en «Notificaciones» y actívalas.' : `Entra en «Permisos» › «${N}» y elige ${SOLO_USO}.`,
      ...(t === 'ubicacion' ? ['Mira también que la ubicación del móvil esté encendida (el icono de ubicación en los ajustes rápidos).'] : []), 'Vuelve a la app y toca «Ya lo he cambiado».']
  }
  // Android: el sitio puede tener permiso y Chrome no tener el del móvil (o al revés); son dos sitios distintos
  const chrome = `Ajustes del móvil › «Aplicaciones» › «Chrome» › «Permisos» › «${N}» › ${SOLO_USO}`
  if ((d === 'android' || d === 'android-pwa') && t !== 'notificaciones' && faltaSistema(t)) return [   // la cabecera de la guía ya dice qué pasa
    `Abre los ${chrome}.`,
    ...(t === 'ubicacion' ? ['Mira también que la ubicación del móvil esté encendida (el icono de ubicación en los ajustes rápidos).'] : []),
    'Vuelve a Zazu y toca «Ya lo he cambiado».']
  const otroAndroid = t === 'notificaciones' ? (d === 'android' ? ['Si ya pone «Permitir» y siguen sin llegar: Ajustes del móvil › «Aplicaciones» › «Chrome» › «Notificaciones», y actívalas.'] : [])
    : [`Si ya pone «Permitir» y sigue sin ir: ${chrome}.`]
  if (d === 'android-pwa') return ['Mantén pulsado el icono de Zazu en la pantalla de inicio.', 'Toca «Información de la app» (la ⓘ).',
    t === 'notificaciones' ? 'Entra en «Notificaciones» y actívalas.' : `Entra en «Permisos» (o «Configuración del sitio») › ${permitir}.`,
    'Vuelve a Zazu y toca «Ya lo he cambiado».',
    `Si ahí no sale: abre Chrome › ⋮ › «Configuración» › «Configuración de sitios» › «${N}» › holazazu.app › «Permitir».`, ...otroAndroid]
  if (d === 'android') return ['Arriba, en la barra de direcciones, toca el icono que hay a la izquierda de holazazu.app (un candado o dos rayitas).',
    `Toca «Permisos» (o «Configuración del sitio») › ${permitir}.`, 'Recarga la página y vuelve a probar.',
    `Si no sale: ⋮ › «Configuración» › «Configuración de sitios» › «${N}» › holazazu.app › «Permitir».`, ...otroAndroid]
  if (d === 'iphone') {
    if (t === 'notificaciones') return ['En el iPhone, las notificaciones solo van con Zazu en la pantalla de inicio.', 'Toca Compartir (el cuadrado con la flecha) › «Añadir a pantalla de inicio».', 'Abre Zazu desde ese icono y activa aquí las notificaciones.']
    return [...(t === 'ubicacion' ? ['Ajustes del iPhone › «Privacidad y seguridad» › «Localización»: que esté activada y «Sitios web de Safari» en «Al usar la app».'] : []),
      'En Safari, toca «aA» (o ⋯) a la izquierda de la dirección › «Configuración del sitio web».', `«${N}» › «Permitir».`,
      ...(t !== 'ubicacion' ? [`Si no sale ahí: Ajustes del iPhone › «Apps» › «Safari» › «${N}» › «Permitir».`] : []), 'Recarga la página y vuelve a probar.']
  }
  if (d === 'iphone-pwa') {
    if (t === 'notificaciones') return ['Ajustes del iPhone › «Notificaciones» › «Zazu».', 'Activa «Permitir notificaciones».', 'Vuelve a Zazu y toca «Ya lo he cambiado».']
    if (t === 'ubicacion') return ['Ajustes del iPhone › «Privacidad y seguridad» › «Localización».', 'Que esté activada y «Sitios web de Safari» en «Al usar la app».', 'Vuelve a Zazu, toca «Ya lo he cambiado» y vuelve a probar.']
    return [`Ajustes del iPhone › «Apps» › «Safari» › «${N}» › «Preguntar» o «Permitir».`, 'Cierra Zazu del todo (desliza hacia arriba) y vuelve a abrirla.', 'Vuelve a probar y pulsa «Permitir».']
  }
  const sistema = t === 'microfono' || t === 'camara' ? [`Si sigue sin ir: en Windows, Configuración › Privacidad › «${N}»; en Mac, Ajustes del Sistema › Privacidad y seguridad › «${N}», y deja usarlo al navegador.`] : []
  if (d === 'firefox') return ['Haz clic en el icono de permisos, a la izquierda de la dirección (sale tachado).', 'Quita el «Bloqueado» con la ✕.', 'Recarga la página, vuelve a probar y pulsa «Permitir».', ...sistema]
  if (d === 'safari-mac') return ['Menú Safari › «Ajustes» › «Sitios web».', `A la izquierda, «${N}»; junto a holazazu.app, elige «Permitir».`, 'Recarga la página.', ...sistema]
  return ['Haz clic en el icono que hay a la izquierda de la dirección (holazazu.app), arriba.',
    `En «${d === 'edge' ? 'Permisos para este sitio' : 'Configuración del sitio'}», pon «${N}» en «Permitir».`, 'Recarga la página (F5).', ...sistema]
}

/** Hoja «Cómo activarlo»: los pasos de aquí, «Abrir ajustes» (en la app) y «Ya lo he cambiado, comprobar». */
export function GuiaPermiso({ tipo, cerrar, toast, quitar = false, alPermitir }: { tipo: Tipo; cerrar: () => void; toast: (m: string) => void; quitar?: boolean
  /** ya permitido: lo que falta para que funcione de verdad (en el navegador, suscribirse a los avisos; la ubicación de una invitada, guardarla) */ alPermitir?: () => void }) {
  useAtrasCierra(true, cerrar)
  const [comprobando, setComprobando] = useState(false)
  const nat = useNativo()
  const d = donde()
  const yaProbado = useRef(false)   // al volver solo, se prueba de verdad una vez (así un diálogo que se cierra no vuelve a salir en bucle)
  const comprobar = async (callado = false) => {
    setComprobando(true)
    let e: E
    try {
      e = await estadoPermiso(tipo)
      const n = nativo()
      const probar = !quitar && tipo !== 'notificaciones' && e !== 'granted' && (!callado || !yaProbado.current)
      if (n && probar) { yaProbado.current = true; e = await pedirNativo(tipo) }   // «bloqueado» puede ser un recuerdo viejo: el sistema contesta al momento si sigue así
      else if (!n && !quitar && tipo !== 'notificaciones' && (EN_APP || e !== 'denied' || faltaSistema(tipo) || silenciado(tipo)) && (!callado || !yaProbado.current)) {
        // sin puente (o en el navegador, si el sitio ya lo tiene) no hay otra forma de saberlo que probarlo
        yaProbado.current = true
        if (tipo === 'ubicacion') { const r = await pedirPosicion(); e = r.pos ? 'granted' : r.estado }
        else { const r = await pedirMedio(tipo); r.stream?.getTracks().forEach(x => x.stop()); e = r.estado }
      } else if (!n && EN_APP && tipo === 'notificaciones' && !quitar) {
        if (!callado) { toast('Desde aquí no puedo comprobarlo. Si ya las activaste en los ajustes del móvil, ya está.'); cerrar() }
        return
      }
    } finally { setComprobando(false) }
    dispatchEvent(new CustomEvent(CAMBIO, { detail: { tipo } }))
    if (quitar) { if (callado) return; toast(e === 'granted' ? `${NOMBRE[tipo]}: sigue permitido` : 'Hecho: ya no está permitido'); if (e !== 'granted') cerrar(); return }
    if (e === 'granted' && !(tipo === 'ubicacion' && leerNativo()?.ubicacionSistema === 'off')) {
      if (alPermitir) { cerrar(); alPermitir() } else { toast('¡Listo! Ya está permitido.'); cerrar() }   // alPermitir da su propio aviso
      return
    }
    if (e === 'granted') { if (!callado) toast('El permiso está, pero la ubicación del móvil sigue apagada. Enciéndela y vuelve.'); return }
    if (!callado) toast(e === 'denied' ? (d === 'app' ? 'Todavía sale bloqueado. Sigue los pasos y vuelve.' : 'Todavía sale bloqueado. Si ya lo cambiaste, recarga la página.') : 'Ya no está bloqueado: vuelve a probar y pulsa «Permitir».')
    else if (e !== 'denied') cerrar()
  }
  const fin = useRef(comprobar); fin.current = comprobar
  useEffect(() => {   // al volver de los ajustes, se comprueba solo
    const vis = () => { if (!document.hidden) void fin.current(true) }
    document.addEventListener('visibilitychange', vis)
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') cerrar() }
    addEventListener('keydown', esc)
    return () => { document.removeEventListener('visibilitychange', vis); removeEventListener('keydown', esc) }
  }, [cerrar])
  const lista = quitar ? pasos(tipo, d, nat).filter(p => !/^(Si sigue sin ir|Si ya pone|Mira también)/.test(p)).map(p => p.replace(/ \(o «Permitir»\)/g, '').replace(/«Preguntar» o «Permitir»/, '«No permitir»').replace(/«Permitir[^»]*»/g, '«No permitir»').replace(/actívalas/g, 'apágalas').replace(/Activa «/, 'Apaga «'))
    : pasos(tipo, d, nat)
  const apagada = tipo === 'ubicacion' && nat?.ubicacionSistema === 'off' && nat.ubicacion === 'granted'
  // en document.body: dentro de una pantalla con transform (la animación de entrada), position:fixed se pinta fuera de la vista
  return createPortal(<div role="dialog" aria-modal="true" aria-label={`Cómo ${quitar ? 'quitar' : 'activar'} ${EL[tipo]}`} onClick={cerrar}
    style={{ position: 'fixed', inset: 0, zIndex: 110, background: 'var(--scrim, rgba(0,0,0,.45))', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 16 }}>
    <div className="acc-card" style={{ width: '100%', maxWidth: 480, maxHeight: '90dvh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
      <strong style={{ fontSize: 18 }}>Cómo {quitar ? 'quitar' : 'activar'} {EL[tipo]}</strong>
      <small>{quitar ? 'Desde aquí no se puede quitar: se hace en los ajustes.' : apagada ? 'La ubicación del móvil está apagada. Se enciende en un toque:'
        : faltaSistema(tipo) ? `${QUIEN[d]} no tiene permiso del ${/^(android|iphone)/.test(d) ? 'móvil' : 'ordenador'} para usar ${EL[tipo]}. Se da en sus ajustes:`
        : d === 'app' && !nat ? 'Se cambia en los ajustes del móvil. Son unos pocos toques:' : `${BLOQ[tipo]} ${LUGAR[d]}. Desde aquí no se puede cambiar, pero son unos pocos toques:`}</small>
      <ol className="onb-list num" style={{ marginTop: 8 }}>{lista.map(p => <li key={p}>{p}</li>)}</ol>
      <div className="actions" style={{ flexWrap: 'wrap' }}>
        {d === 'app' && nat && <button className="btn-primary" onClick={() => { if (!abrirAjustes(tipo)) toast('No pude abrir los ajustes. Ve a Ajustes del móvil › Aplicaciones › HolaZazu.') }}>Abrir ajustes</button>}
        <button className={d === 'app' && nat ? 'btn-secondary' : 'btn-primary'} disabled={comprobando} onClick={() => void comprobar()}>{comprobando ? 'Comprobando…' : 'Ya lo he cambiado, comprobar'}</button>
        {d !== 'app' && !quitar && <button className="btn-secondary" onClick={() => location.reload()}>Recargar la página</button>}
        <button className="text-link" onClick={cerrar}>Cerrar</button>
      </div>
    </div></div>, document.body)
}

/** Prueba de 1 s del micrófono con la barra de nivel: dice si se oye algo. */
export async function probarMicro(stream: MediaStream, alNivel: (n: number) => void, ms = 1000): Promise<number> {
  const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  let max = 0
  if (!AC) { await new Promise(r => setTimeout(r, ms)); stream.getTracks().forEach(t => t.stop()); return -1 }
  const ctx = new AC()
  try {
    if (ctx.state === 'suspended') await ctx.resume().catch(() => { })
    const an = ctx.createAnalyser(); an.fftSize = 1024
    ctx.createMediaStreamSource(stream).connect(an)
    const buf = new Uint8Array(an.fftSize)
    const t0 = performance.now()
    await new Promise<void>(ok => {
      const paso = () => {
        an.getByteTimeDomainData(buf)
        let s = 0
        for (const v of buf) { const x = (v - 128) / 128; s += x * x }
        const n = Math.min(1, Math.sqrt(s / buf.length) * 4)
        max = Math.max(max, n); alNivel(n)
        if (performance.now() - t0 < ms) requestAnimationFrame(paso); else ok()
      }
      requestAnimationFrame(paso)
    })
  } finally { stream.getTracks().forEach(t => t.stop()); void ctx.close().catch(() => { }); alNivel(0) }
  return max
}

/** La barra de nivel de sonido. */
export const Nivel = ({ n }: { n: number }) => <span role="meter" aria-label="Nivel del micrófono" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(n * 100)}
  style={{ display: 'block', height: 8, borderRadius: 8, background: 'var(--surface-3, #e8e4d8)', overflow: 'hidden', marginTop: 8, maxWidth: 220 }}>
  <span style={{ display: 'block', height: '100%', width: `${Math.round(n * 100)}%`, background: 'var(--accent, #55702a)', transition: 'width 60ms linear' }} /></span>

