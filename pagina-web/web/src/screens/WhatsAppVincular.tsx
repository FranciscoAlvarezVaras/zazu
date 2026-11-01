import { useEffect, useRef, useState } from 'react'
import { Icon } from '../icons'
import { EN_APP, post, useFetch } from '../lib'
import { abrirAjustes } from './PermisosDispositivo'
import { copiar } from '../chat/Acciones'

/** WhatsApp: estado compartido de /api/canales (invitadas), abrir WhatsApp, el número y las filas de «Tus permisos». */
export type CanalWa = { conectado: boolean; numero: string | null; emparejando: 'esperando' | 'conectado' | 'error' | null; qr: string | null
  codigo?: string | null; caduca_en?: number | null; telefono?: string | null; error?: string | null }
export type Canales = { whatsapp: CanalWa; telegram: { conectado: boolean; bot: string | null; codigo: string | null }; gateway: string }

/** Lo lanza quien cambia algo en /api/canales: la tarjeta «WhatsApp y Telegram» y la fila de «Tus permisos» se ponen de acuerdo. */
export const CANALES_CAMBIO = 'zazu:canales'
export const avisarCanales = () => window.dispatchEvent(new Event(CANALES_CAMBIO))

/** /api/canales que se vuelve a pedir cuando otra parte lo cambia y al volver a la app (por ejemplo, de WhatsApp). */
export function useCanales(every = 0, path: string | null = '/api/canales') {
  const c = useFetch<Canales>(path, every)
  const { reload } = c
  useEffect(() => {
    if (!path) return
    const otra = () => { if (!document.hidden) void reload() }
    window.addEventListener(CANALES_CAMBIO, otra)
    document.addEventListener('visibilitychange', otra)
    return () => { window.removeEventListener(CANALES_CAMBIO, otra); document.removeEventListener('visibilitychange', otra) }
  }, [path, reload])
  return c
}

/** Abrir WhatsApp en este móvil para vincularlo. App de Android 2.4+: con su puente. App vieja: wa.me (lo abre Android fuera).
 *  Chrome o la web instalada: whatsapp://. Si a los 2 s seguimos aquí, se le dice que lo abra ella. */
export function abrirWhatsApp(toast: (m: string) => void) {
  const movil = EN_APP || /Android|iPhone|iPad/.test(navigator.userAgent)
  if (!movil && !abrirAjustes('whatsapp')) { toast('Abre WhatsApp en tu móvil.'); return }
  let fuera = false
  const marca = () => { if (document.hidden) fuera = true }
  document.addEventListener('visibilitychange', marca)
  setTimeout(() => {
    document.removeEventListener('visibilitychange', marca)
    if (!fuera && !document.hidden) toast('No he podido abrir WhatsApp desde aquí. Ábrelo tú desde la pantalla de inicio del móvil.')
  }, 2000)
  if (abrirAjustes('whatsapp')) return
  location.href = EN_APP ? 'https://wa.me/' : 'whatsapp://send'   // la app vieja abre fuera los enlaces https (wa.me lo coge WhatsApp)
}

/** Igual que en el servidor (wa_telefono): lo que escribe → cifras con prefijo, o qué está mal. */
export function normalTel(texto: string): { tel: string; mal?: string } {
  const t = texto.includes('+') ? texto.slice(texto.lastIndexOf('+')) : texto   // «+34 +58 414…»: vale el último prefijo
  let tel = t.replace(/\D/g, '')
  if (tel.startsWith('00')) tel = tel.slice(2)
  if (tel.length === 9 && '6789'.includes(tel[0])) tel = '34' + tel
  if (tel.startsWith('580')) tel = '58' + tel.slice(3)   // Venezuela: el 0 de «0414» no va con el +58
  if (!/^[1-9]\d{7,14}$/.test(tel)) return { tel, mal: 'Escribe tu número con el prefijo del país, p. ej. +34 600 111 222.' }
  if (tel.startsWith('34') && (tel.length !== 11 || !'6789'.includes(tel[2])))
    return { tel, mal: tel[2] === '0' || tel.length > 11 ? 'Ese número no es de España. Si es de otro país, borra el +34 y escribe su prefijo (p. ej. +58 414 123 4567).' : 'A ese número le faltan cifras: un móvil de España tiene 9.' }
  if (tel.startsWith('58') && tel.length !== 12) return { tel, mal: 'Revisa el número: un móvil de Venezuela es +58 y 10 cifras.' }
  return { tel }
}
export const telBonito = (tel: string) => tel.startsWith('34') && tel.length === 11 ? `+34 ${tel.slice(2, 5)} ${tel.slice(5, 8)} ${tel.slice(8)}`
  : tel.startsWith('58') && tel.length === 12 ? `+58 ${tel.slice(2, 5)} ${tel.slice(5, 8)} ${tel.slice(8)}` : `+${tel}`

const hace = (iso?: string | null) => {
  const t = iso ? Date.parse(iso) : NaN
  if (isNaN(t)) return null
  const m = Math.max(0, Math.round((Date.now() - t) / 60000))
  return { m, txt: m < 2 ? 'ahora mismo' : m < 60 ? `hace ${m} min` : m < 48 * 60 ? `hace ${Math.round(m / 60)} h` : `hace ${Math.round(m / 1440)} días` }
}

/** El WhatsApp de Fran es de solo lectura (wacli): estado en cristiano. estado: connected | fatal | disconnected | null (no se sabe). */
export function textoWaFran(estado: string | null | undefined, sync?: string | null, vivo?: boolean | null): { ok: boolean | undefined; texto: string } {
  const h = hace(sync)   // la última actividad: tras una noche sin mensajes puede ser de hace horas, y eso no es un fallo
  // el aviso sale solo si el repaso (wacli-sync) está parado de verdad, no por llevar horas sin mensajes
  if (estado === 'connected') return { ok: vivo !== false, texto: 'Conectado (solo lectura): Zazu lee tus chats y te propone cosas en la app.'
    + (vivo === false ? ' Ojo: el repaso de WhatsApp en el PC está parado, así que no llegan los mensajes nuevos. Toca «Ponerlo en marcha».' : h ? ` Última actividad: ${h.txt}.` : '') }
  if (estado === 'fatal') return { ok: false, texto: 'WhatsApp cerró la sesión de Zazu. Vuelve a vincularlo con un código de 8 letras, desde este mismo móvil.' }
  if (estado === 'disconnected') return { ok: false, texto: 'Sin vincular. Vincúlalo con un código de 8 letras, desde este mismo móvil.' }
  return { ok: undefined, texto: 'No pude comprobarlo ahora. Prueba otra vez en un rato.' }
}

/** Fila «Tu WhatsApp» de Fran en «Tus permisos»: cómo está y, al tocar «Vincular», la tarjeta para hacerlo ahí mismo.
 *  Lee /api/whatsapp-fran (al día tras vincular); mientras no llega, lo que le pasa «Tus permisos» de /api/cuentas. */
export function FilaWhatsAppFran({ estado, sync, vivo, cargando, irCuentas, toast }: { estado?: string | null; sync?: string | null; vivo?: boolean | null; cargando: boolean; irCuentas?: () => void; toast?: (m: string) => void }) {
  const f = useWhatsAppFran(!!toast)
  const [abierta, setAbierta] = useState(false)
  const d = f.data
  const t = d ? textoWaFran(d.estado, d.sync, d.vivo) : textoWaFran(estado, sync, vivo)
  const vinculando = !!d?.emparejando && d.emparejando !== 'conectado'
  const [arrancando, setArrancando] = useState(false)
  const parado = !vinculando && (d ? d.vivo === false || !!d.parado : vivo === false)
  return <><div className="setting-row informational" style={{ alignItems: 'flex-start', paddingTop: 12, paddingBottom: 12 }}>
    <span className="setting-icon"><Icon name="chat" size={19} /></span>
    <span className="setting-copy"><strong>Tu WhatsApp</strong>
      <small className={(cargando && !d) || t.ok === undefined ? '' : t.ok ? 'ok' : 'bad'}>{cargando && !d ? 'Comprobando…' : vinculando ? (d!.codigo ? `Vinculando: tu código es ${d!.codigo}.` : 'Vinculando…') : t.texto}</small>
      {toast && parado && !abierta && <button type="button" className="text-link" style={{ marginTop: 6, marginRight: 14 }} disabled={arrancando}
        onClick={() => { setArrancando(true); void ponerEnMarcha(toast).finally(() => { setArrancando(false); void f.reload() }) }}>{arrancando ? 'Arrancando…' : 'Ponerlo en marcha'}</button>}
      {toast && !abierta && <button type="button" className="text-link" style={{ marginTop: 6, marginRight: 14 }} onClick={() => setAbierta(true)}>
        {vinculando ? 'Ver el código' : d?.conectado ? 'Vincular otro número o desconectar' : 'Vincular mi WhatsApp'}</button>}
      {irCuentas && <button type="button" className="text-link" style={{ marginTop: 6 }} onClick={irCuentas}>Ver en Tus cuentas</button>}</span>
  </div>
  {toast && abierta && <TarjetaWhatsAppFran toast={toast} f={f} />}</>
}

/** «Ponerlo en marcha»: vuelve a arrancar el repaso de WhatsApp en el PC (wacli-sync). */
const ponerEnMarcha = (toast: (m: string) => void) => post('/api/whatsapp-fran', { accion: 'arrancar' })
  .then(() => toast('Listo: WhatsApp vuelve a estar en marcha. Los mensajes nuevos llegan en un minuto.'), e => toast((e as Error).message))

/** /api/whatsapp-fran: su WhatsApp (wacli-sync) y si se está vinculando. Solo Fran. */
export type WaFran = { estado: string | null; sync: string | null; vivo: boolean | null; conectado: boolean
  emparejando: 'esperando' | 'conectado' | 'error' | null; codigo: string | null; caduca_en: number | null; telefono: string | null
  guardando: boolean; error: string | null; parado?: boolean; numero: string | null; desde: string | null; respaldo: string | null; desconectado: string | null }

export function useWhatsAppFran(activo = true) {
  const [cada, setCada] = useState(0)
  const f = useFetch<WaFran>(activo ? '/api/whatsapp-fran' : null, cada)
  const esperando = f.data?.emparejando === 'esperando'
  useEffect(() => { setCada(esperando ? 2000 : 0) }, [esperando])   // mientras se vincula, cada 2 s; si no, nada
  const { reload } = f
  useEffect(() => {   // al volver de WhatsApp, al momento
    if (!activo) return
    const otra = () => { if (!document.hidden) void reload() }
    document.addEventListener('visibilitychange', otra)
    return () => document.removeEventListener('visibilitychange', otra)
  }, [activo, reload])
  return f
}

/** Los pasos en WhatsApp para poner el código (Fran y las invitadas). */
function PasosCodigo() {
  return <ol className="onb-list num">
    <li>En WhatsApp, toca <b>⋮</b> (arriba a la derecha; en iPhone, <b>Ajustes</b> abajo) › <b>Dispositivos vinculados</b>.</li>
    <li>Toca <b>Vincular un dispositivo</b>. Si te pide la huella o el PIN, ponlo.</li>
    <li>Abajo del todo, toca <b>Vincular con el número de teléfono</b> (no hace falta escanear nada).</li>
    <li>Escribe el código de 8 letras. En unos segundos verás aquí «¡WhatsApp conectado!».</li></ol>
}

/** «2026-10-23» → «23 de octubre» (con el año si no es este). */
const fechaBonita = (iso: string) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const d = new Date(+m[1], +m[2] - 1, +m[3])
  return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'long', ...(d.getFullYear() !== new Date().getFullYear() ? { year: 'numeric' } : {}) })
}

const copiarCodigo = (c: string) => copiar(c.replace('-', '')).then(() => true, () => false)

/** El código de 8 letras con su cuenta atrás (cuando caduca, WhatsApp da otro solo y sale aquí). */
function CodigoConCuenta({ codigo, caduca_en, telefono, toast }: { codigo: string; caduca_en: number | null | undefined; telefono: string; toast: (m: string) => void }) {
  const [fin, setFin] = useState(() => caduca_en != null ? Date.now() + caduca_en * 1000 : 0)
  const [, tic] = useState(0)
  useEffect(() => { setFin(caduca_en != null ? Date.now() + caduca_en * 1000 : 0) }, [codigo, caduca_en])
  useEffect(() => { if (!fin) return; const t = setInterval(() => tic(n => n + 1), 1000); return () => clearInterval(t) }, [fin])
  const quedan = fin ? Math.max(0, Math.round((fin - Date.now()) / 1000)) : 0
  const copiarYAbrir = async () => { toast((await copiarCodigo(codigo)) ? 'Código copiado' : `Apunta el código: ${codigo}`); abrirWhatsApp(toast) }
  return <>
    <small>Tu código para <b>{telBonito(telefono)}</b>:</small>
    <button type="button" className="chatgpt-code" onClick={() => void copiarCodigo(codigo).then(ok => toast(ok ? 'Código copiado' : `Apunta el código: ${codigo}`))} aria-label={`Código ${codigo}. Toca para copiar`}
      style={quedan ? undefined : { opacity: 0.45 }}>{codigo}<small>{quedan ? `vale ${mmss(quedan)} · toca para copiar` : 'ya no vale: WhatsApp está preparando otro…'}</small></button>
    <button className="btn-primary" type="button" onClick={() => void copiarYAbrir()}>Copiar y abrir WhatsApp <Icon name="arrow" size={17} /></button>
    <PasosCodigo />
    <p className="onb-note"><Icon name="lightbulb" size={16} /> Si el código caduca, aquí sale uno nuevo solo: escribe siempre el último.</p></>
}

/** Tarjeta «Tu WhatsApp» de Fran: vincular con código (en una carpeta nueva: el de ahora sigue hasta que el nuevo conecta) y desconectar.
 *  Lo de antes se guarda siempre en Respaldos. */
export function TarjetaWhatsAppFran({ toast, f: dado }: { toast: (m: string) => void; f?: ReturnType<typeof useWhatsAppFran> }) {
  const propio = useWhatsAppFran(!dado)
  const f = dado || propio
  const d = f.data
  const [tel, setTel] = useState('+34 ')
  const [otro, setOtro] = useState(false)   // ya conectado: enseñar el formulario para vincular otra vez
  const [busy, setBusy] = useState('')
  const hecho = useRef(d?.emparejando)
  useEffect(() => {   // al terminar bien, un aviso (una vez)
    if (hecho.current === 'esperando' && d?.emparejando === 'conectado') { toast('¡WhatsApp conectado!'); setOtro(false) }
    hecho.current = d?.emparejando
  }, [d?.emparejando, toast])
  useEffect(() => { if (d?.emparejando === 'error' && d.telefono) setTel(telBonito(d.telefono)) }, [d?.emparejando, d?.telefono])
  const act = async (k: string, body: object, ok?: string) => {
    setBusy(k)
    try { await post('/api/whatsapp-fran', body); if (ok) toast(ok); return true }
    catch (e) { toast((e as Error).message); return false }
    finally { setBusy(''); void f.reload() }
  }
  const n = normalTel(tel), cifras = tel.replace(/\D/g, '').length
  const pedir = (telefono: string, nuevo = false) => act('codigo', { accion: 'vincular', telefono, nuevo })
  const desconectar = () => { if (confirm('¿Desconectar tu WhatsApp? Zazu dejará de leer tus chats. Guardo una copia en Respaldos y, para volver, lo vinculas con un código.')) void act('off', { accion: 'desconectar' }, 'WhatsApp desconectado') }

  let cuerpo
  if (!d) cuerpo = f.error ? <div className="fallo" role="alert"><span>No pude comprobar tu WhatsApp.</span><button type="button" className="reintentar" onClick={() => void f.reload()}>Reintentar</button></div>
    : <p className="onb-note"><Icon name="clock" size={16} /> Comprobando…</p>
  else if (d.emparejando === 'esperando' && d.guardando) cuerpo = <p className="onb-note" role="status"><Icon name="clock" size={16} /> ¡Conectado! Guardando tu WhatsApp en el PC… Tarda menos de un minuto. Esta pantalla se actualiza sola.</p>
  else if (d.emparejando === 'esperando' && d.codigo) cuerpo = <div className="chatgpt-login">
    <CodigoConCuenta codigo={d.codigo} caduca_en={d.caduca_en} telefono={d.telefono || ''} toast={toast} />
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <button className="btn-secondary" disabled={!!busy} onClick={() => void pedir(d.telefono!, true)}>{busy === 'codigo' ? 'Pidiendo…' : 'Pedir otro código'}</button>
      <button className="btn-secondary" disabled={!!busy} onClick={() => { setTel(telBonito(d.telefono || '')); setOtro(false); void act('cancelar', { accion: 'cancelar' }) }}>Cancelar</button></div></div>
  else if (d.emparejando === 'esperando') cuerpo = <div className="chatgpt-login">
    <p className="onb-note"><Icon name="clock" size={16} /> Pidiendo tu código a WhatsApp{d.telefono ? ` para ${telBonito(d.telefono)}` : ''}…</p>
    <button className="text-link" disabled={!!busy} onClick={() => { setOtro(false); void act('cancelar', { accion: 'cancelar' }) }}>Cancelar</button></div>
  else if ((d.conectado || d.emparejando === 'conectado') && !otro) {   // recién vinculado aunque `wacli doctor` aún no conteste: ya está
    const parado = d.vivo === false || !!d.parado
    const t = d.parado ? { texto: `Vinculado${d.numero ? ` (…${d.numero})` : ''}, pero el repaso de WhatsApp en el PC no ha arrancado: todavía no llegan tus mensajes. Toca «Ponerlo en marcha».` }
      : d.conectado ? textoWaFran(d.estado, d.sync, d.vivo) : { texto: `Vinculado${d.numero ? ` (…${d.numero})` : ''}. Zazu empieza a leer tus chats en un momento.` }
    cuerpo = <>
      <p className="onb-note"><Icon name={parado ? 'close' : 'check'} size={16} /><span>{t.texto}</span></p>
      {parado && <button className="btn-primary" disabled={!!busy} onClick={() => { setBusy('marcha'); void ponerEnMarcha(toast).finally(() => { setBusy(''); void f.reload() }) }}>
        {busy === 'marcha' ? 'Arrancando…' : 'Ponerlo en marcha'} <Icon name="arrow" size={17} /></button>}
      {d.emparejando === 'conectado' && d.respaldo && <small className="muted-note" style={{ margin: 0 }}>Tu WhatsApp de antes está guardado en Respaldos ({d.respaldo}). Si en <b>Dispositivos vinculados</b> ves dos «Chrome (Linux)», puedes quitar el más antiguo.</small>}
      <button className="btn-secondary" disabled={!!busy} onClick={() => setOtro(true)}>Vincular otra vez u otro número</button>
      <button className="text-link" disabled={!!busy} onClick={desconectar}>{busy === 'off' ? 'Desconectando…' : 'Desconectar mi WhatsApp'}</button></>
  } else cuerpo = <form className="chatgpt-login" onSubmit={e => { e.preventDefault(); if (!n.mal) void pedir(n.tel) }}>
    {d.emparejando === 'error' && <div className="fallo" role="alert"><span>{d.error || 'No se completó la vinculación. Pide un código nuevo.'}</span></div>}
    {d.desconectado && !d.conectado && d.emparejando !== 'error' && <small className="muted-note" style={{ margin: 0 }}>Desconectado el {fechaBonita(d.desconectado)}. Lo de antes está guardado en Respaldos{d.respaldo ? ` (${d.respaldo})` : ''}.</small>}
    <p>Escribe tu número de WhatsApp y te doy un <b>código de 8 letras</b> para vincularlo desde este mismo móvil. Sin escanear nada.</p>
    {d.conectado && <p className="onb-note"><Icon name="shield" size={16} /><span>Tu WhatsApp de ahora sigue funcionando mientras tanto. Solo si el nuevo conecta se cambia, y el de antes se guarda en Respaldos.</span></p>}
    <input className="campo" type="tel" inputMode="tel" autoComplete="tel" value={tel} onChange={e => setTel(e.target.value)} aria-label="Tu número de WhatsApp" placeholder="+34 600 111 222" />
    {cifras >= 9 && <small className={n.mal ? 'bad' : ''} role="status">{n.mal || <>¿Es este tu número de WhatsApp? <b>{telBonito(n.tel)}</b></>}</small>}
    <button className="btn-primary" disabled={!!busy || cifras < 9 || !!n.mal}>
      {busy === 'codigo' ? 'Pidiendo el código a WhatsApp…' : d.emparejando === 'error' ? 'Conseguir un código nuevo' : 'Conseguir mi código'} <Icon name="arrow" size={17} /></button>
    {d.conectado && <button type="button" className="text-link" onClick={() => setOtro(false)}>No, dejarlo como está</button>}</form>

  return <div className="acc-card" id="whatsapp-fran">
    <div className="acc-top"><span className="setting-icon"><Icon name="chat" size={19} /></span><div><strong>Tu WhatsApp</strong>
      <small>{d?.conectado || d?.emparejando === 'conectado' ? `Conectado${d.numero ? ` (…${d.numero})` : ''}.` : 'Para que Zazu lea tus chats y te proponga citas y tareas.'}</small></div></div>
    {cuerpo}
  </div>
}

/** Texto de la fila «WhatsApp» de una invitada en «Tus permisos»: dice lo mismo que la tarjeta de «WhatsApp y Telegram». */
export function subWhatsApp(c: { data: Canales | null; error: string }, asistente: string) {
  const w = c.data?.whatsapp
  if (!w) return c.error ? 'No pude comprobarlo ahora. Toca para ver tu WhatsApp.' : 'Comprobando…'
  if (w.conectado) return c.data!.gateway !== 'active' ? `Conectado (…${w.numero}). ${asistente} estará listo en un minuto.`
    : `Conectado (…${w.numero}): escríbele a ${asistente} en tu chat contigo de WhatsApp.`
  if (w.emparejando === 'esperando') return w.codigo ? `Vinculando: tu código es ${w.codigo}. Toca para verlo.` : 'Vinculando… Toca para verlo.'
  if (w.emparejando === 'error') return `No se pudo vincular. ${w.error || ''} Toca para probar otra vez.`
  return 'Desconectado. Toca para vincularlo: te damos un código de 8 letras y lo pones en WhatsApp.'
}

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

/** Tarjeta «WhatsApp» de una invitada: conectado · pidiendo el código · código con cuenta atrás · caducado (llega otro solo) · error con el motivo. */
export function TarjetaWhatsApp({ d, act, busy, toast, nombre }: { d: Canales; act: (body: object, ok?: string) => Promise<boolean>; busy: string; toast: (m: string) => void; nombre: string }) {
  const wa = d.whatsapp
  const [tel, setTel] = useState('+34 ')
  const [verQr, setVerQr] = useState(!matchMedia('(pointer: coarse)').matches)   // en el móvil, el código; en el PC, el QR
  const [fin, setFin] = useState(() => wa.codigo && wa.caduca_en != null ? Date.now() + wa.caduca_en * 1000 : 0)
  const [, tic] = useState(0)
  useEffect(() => { setFin(wa.codigo && wa.caduca_en != null ? Date.now() + wa.caduca_en * 1000 : 0) }, [wa.codigo, wa.caduca_en])
  useEffect(() => { if (!fin) return; const t = setInterval(() => tic(n => n + 1), 1000); return () => clearInterval(t) }, [fin])
  useEffect(() => { if (wa.emparejando === 'error' && wa.telefono) setTel(telBonito(wa.telefono)) }, [wa.emparejando, wa.telefono])   // si falló, su número sigue escrito
  const quedan = fin ? Math.max(0, Math.round((fin - Date.now()) / 1000)) : 0
  const n = normalTel(tel), cifras = tel.replace(/\D/g, '').length
  const copiarYAbrir = async () => { if (!(await copiarCodigo(wa.codigo!))) toast(`Apunta el código: ${wa.codigo}`); else toast('Código copiado'); abrirWhatsApp(toast) }
  const pedir = (telefono: string, nuevo = false) => act({ action: 'whatsapp_codigo', telefono, nuevo })
  const cambiarNumero = async () => { if (wa.telefono) setTel(telBonito(wa.telefono)); await act({ action: 'whatsapp_cancelar' }) }
  const enCodigo = wa.emparejando === 'esperando' && !!wa.telefono
  // la tarjeta se sondea sola; la fila de «Tus permisos» no: cuando cambia lo que se ve, se le avisa (al montarse, no)
  const firma = `${wa.conectado}|${wa.emparejando}|${wa.codigo}|${wa.error}|${d.gateway}`
  const vista = useRef(firma)
  useEffect(() => { if (vista.current !== firma) { vista.current = firma; avisarCanales() } }, [firma])

  let cuerpo
  if (wa.conectado) cuerpo = <>
    {d.gateway !== 'active' && <p className="onb-note"><Icon name="clock" size={16} /> Conectado. Tu {nombre} estará listo en un minuto… Esta pantalla se actualiza sola.</p>}
    <button className="btn-primary" type="button" onClick={() => abrirWhatsApp(toast)}>Abrir WhatsApp <Icon name="arrow" size={17} /></button>
    <button className="btn-secondary" disabled={!!busy} onClick={() => { if (confirm('¿Desconectar WhatsApp? Después, en tu móvil, quita «HolaZazu» de Dispositivos vinculados.')) void act({ action: 'whatsapp_off' }, 'WhatsApp desconectado') }}>Desconectar WhatsApp</button></>
  else if (enCodigo && wa.codigo) cuerpo = <div className="chatgpt-login">
    <small>Tu código para <b>{telBonito(wa.telefono!)}</b>:</small>
    <button type="button" className="chatgpt-code" onClick={() => void copiarCodigo(wa.codigo!).then(ok => toast(ok ? 'Código copiado' : `Apunta el código: ${wa.codigo}`))} aria-label={`Código ${wa.codigo}. Toca para copiar`}
      style={quedan ? undefined : { opacity: 0.45 }}>{wa.codigo}<small>{quedan ? `vale ${mmss(quedan)} · toca para copiar` : 'ya no vale: WhatsApp está preparando otro…'}</small></button>
    <button className="btn-primary" type="button" onClick={() => void copiarYAbrir()}>Copiar y abrir WhatsApp <Icon name="arrow" size={17} /></button>
    <PasosCodigo />
    <p className="onb-note"><Icon name="lightbulb" size={16} /> Si el código caduca, aquí sale uno nuevo solo: escribe siempre el último.</p>
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <button className="btn-secondary" disabled={!!busy} onClick={() => void pedir(wa.telefono!, true)}>{busy === 'whatsapp_codigo' ? 'Pidiendo…' : 'Pedir otro código'}</button>
      <button className="btn-secondary" disabled={!!busy} onClick={() => void cambiarNumero()}>Cambiar de número</button></div></div>
  else if (enCodigo) cuerpo = <div className="chatgpt-login">
    <p className="onb-note"><Icon name="clock" size={16} /> Pidiendo tu código a WhatsApp para {telBonito(wa.telefono!)}…</p>
    <button className="text-link" disabled={!!busy} onClick={() => void act({ action: 'whatsapp_cancelar' })}>Cancelar</button></div>
  else if (wa.emparejando === 'esperando') cuerpo = wa.qr ? <div className="chatgpt-login">
    <ol className="onb-list num"><li>Abre WhatsApp en tu móvil.</li><li>Toca <b>⋮</b> (en iPhone, <b>Ajustes</b>) › <b>Dispositivos vinculados</b> › <b>Vincular un dispositivo</b>.</li><li>Escanea este código:</li></ol>
    <img className="wa-qr" src={`data:image/svg+xml;utf8,${encodeURIComponent(wa.qr)}`} alt="Código QR para vincular WhatsApp" />
    <p className="onb-note"><Icon name="lightbulb" size={16} /> Si estás viendo esto en el mismo móvil, ábrelo en un ordenador o tablet para escanearlo. El código cambia cada 20 segundos.</p>
    <button className="text-link" disabled={!!busy} onClick={() => void act({ action: 'whatsapp_cancelar' })}>Cancelar</button></div>
    : <button className="btn-primary" disabled>Preparando el código…</button>
  else if (!verQr) cuerpo = <form className="chatgpt-login" onSubmit={e => { e.preventDefault(); if (!n.mal) void pedir(tel) }}>
    <p>Escribe tu número de WhatsApp y te damos un <b>código de 8 letras</b> para vincularlo desde este mismo móvil. Sin escanear nada.</p>
    <input className="campo" type="tel" inputMode="tel" autoComplete="tel" value={tel} onChange={e => setTel(e.target.value)} aria-label="Tu número de WhatsApp" placeholder="+34 600 111 222" />
    {cifras >= 9 && <small className={n.mal ? 'bad' : ''} role="status">{n.mal || <>¿Es este tu número de WhatsApp? <b>{telBonito(n.tel)}</b></>}</small>}
    <button className="btn-primary" disabled={!!busy || cifras < 9 || !!n.mal}>
      {busy === 'whatsapp_codigo' ? 'Pidiendo el código a WhatsApp…' : wa.emparejando === 'error' ? 'Conseguir un código nuevo' : 'Conseguir mi código'} <Icon name="arrow" size={17} /></button>
    <button type="button" className="text-link" onClick={() => setVerQr(true)}>Prefiero escanear un QR desde otra pantalla</button></form>
  else cuerpo = <>
    <button className="btn-primary" disabled={!!busy} onClick={() => void act({ action: 'whatsapp' })}>{busy === 'whatsapp' ? 'Preparando el código…' : 'Conectar WhatsApp con un QR'} <Icon name="arrow" size={17} /></button>
    <button type="button" className="text-link" onClick={() => setVerQr(false)}>Prefiero un código con mi número (desde este móvil)</button></>

  return <div className="acc-card">
    <div className="acc-top"><span className="setting-icon"><Icon name="chat" size={19} /></span><div><strong>WhatsApp</strong>
      <small>{wa.conectado ? `Conectado (…${wa.numero}). Escríbele en tu chat contigo (el que se llama como tú, «Tú» o «Mensaje para ti»).` : `Habla con ${nombre} desde tu propio WhatsApp.`}</small></div></div>
    {wa.emparejando === 'error' && !wa.conectado && <div className="fallo" role="alert"><span>{wa.error || 'No se completó la vinculación. Pide un código nuevo.'}</span></div>}
    {cuerpo}
  </div>
}
