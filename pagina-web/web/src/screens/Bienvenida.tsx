import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BrandMark, Icon } from '../icons'
import type { IconName } from '../icons'
import { EN_APP, IA_PROPIA, irA as irApp, leerParams, post, puede, useAtrasCierra, useFetch } from '../lib'
import type { Ctx } from '../ctx'
import type { Me } from './Invitada'
import { CanalesInvitada, CuentaIA, RutinasInvitada, SIN_GOOGLE } from './Invitada'
import { usePush } from './Ajustes'
import { FormPreferencias, type Prefs } from './Preferencias'
import { GuiaPermiso, abrirAjustes, appConAvisos, mensajePedido, nativo, pedirMedio, pedirNativo, pedirPosicion, useNativo, usePermiso, type Tipo } from './PermisosDispositivo'
import { TarjetaWhatsAppFran } from './WhatsAppVincular'
import CuentasScreen from './CuentasScreen'

type Z = { asistente: string; tono: string; largo: string; web: boolean; sobre_mi: string; prefs?: Prefs }
const TONOS: [string, string, string][] = [['cercano', 'Cercano', 'Cálido, como una amiga'], ['directo', 'Directo', 'Al grano, sin rodeos'], ['divertido', 'Divertido', 'Con un poco de humor'], ['formal', 'Formal', 'Educado, de usted']]
/** Pantallas de la guía. «ia» solo con IA_PROPIA; «cosas» solo si tiene Carpetas o Rutinas; la cámara solo en la app
 *  (en el navegador las fotos van con el selector del sistema y no piden permiso). Los permisos, uno a uno («p-…»). */
type Paso = 'hola' | 'asistente' | 'ia' | 'p-notificaciones' | 'p-ubicacion' | 'p-microfono' | 'p-camara' | 'datos' | 'conexiones' | 'hablar' | 'cosas' | 'menu' | 'listo'
type BIP = Event & { prompt: () => Promise<void> }
/** Dónde se quedó (para volver ahí al recargar o al volver de Google). Un día como mucho. */
const CLAVE = (u: string) => `hz-onb:${u}`
const leer = (u: string): string | null => { try { const v = JSON.parse(localStorage.getItem(CLAVE(u)) || 'null') as { p?: string; t?: number } | null; return v?.p && Date.now() - (v.t || 0) < 86400e3 ? v.p : null } catch { return null } }
const apuntar = (u: string, p: Paso) => { try { localStorage.setItem(CLAVE(u), JSON.stringify({ p, t: Date.now() })) } catch { /* sin almacenamiento */ } }
const olvidar = (u: string) => { try { localStorage.removeItem(CLAVE(u)); sessionStorage.removeItem('onb') } catch { /* sin almacenamiento */ } }
/** La URL con la que se abrió la app: App la limpia (?ok=google…) antes de que se sepa quién eres y salga la guía. */
const URL_INICIAL = typeof location !== 'undefined' ? location.search : ''
/** El estado del historial sin la marca de una hoja abierta (useAtrasCierra). */
const sinHoja = (s: unknown) => { const { hoja: _h, ...r } = (s && typeof s === 'object' ? s : {}) as Record<string, unknown>; return r }

/** Guía de bienvenida: la primera vez (al acabar se marca `onboarded`; también Fran si reinicia su perfil) o, con `repaso`, desde Tu espacio.
 *  El Atrás del móvil vuelve al paso anterior (cada paso deja una entrada en el historial, que se recoge al terminar). */
export default function Bienvenida({ me, done, toast, repaso = false }: { me: Me; done: () => void; toast: (m: string) => void; repaso?: boolean }) {
  const zf = useFetch<Z>('/api/mi-zazu')
  const [z, setZ] = useState<Z | null>(null)
  const carpetas = puede(me, 'carpetas'), rutinas = puede(me, 'rutinas')
  const admin = me.role !== 'guest'   // Fran también pasa por la guía (sin «¿cómo se llama tu gato?»: pisaría las instrucciones de su Zazu)
  const pasos: Paso[] = ['hola', ...(admin ? [] : ['asistente' as const]), ...(IA_PROPIA && !admin ? ['ia' as const] : []),
    'p-notificaciones', 'p-ubicacion', 'p-microfono', ...(EN_APP ? ['p-camara' as const] : []),
    ...(me.demo ? [] : ['datos' as const, 'conexiones' as const]), 'hablar', ...(carpetas || rutinas ? ['cosas' as const] : []), 'menu', 'listo']
  const [paso, setPaso] = useState<Paso>(() => {
    if (repaso) return 'hola'
    const g = leer(me.user) as Paso | null
    if (g && pasos.includes(g)) return g
    const q = new URLSearchParams(URL_INICIAL)   // vuelve de Google (bien o mal): al paso de las conexiones
    return pasos.includes('conexiones') && (q.get('ok') === 'google' || /^(google|google_no|guardar|caducado|nivel)$/.test(q.get('e') || '')) ? 'conexiones' : 'hola'
  })
  const [busy, setBusy] = useState(false)
  const [instalar, setInstalar] = useState<BIP | null>(null)
  const [verCuentas, setVerCuentas] = useState(false)
  const [borrador, setBorrador] = useState<Partial<Prefs>>({})   // «Sobre ti» sin guardar: no se pierde al ir Atrás y volver
  const [geo] = usePermiso('ubicacion')
  const i = Math.max(0, pasos.indexOf(paso))
  // —— historial: cada paso hacia delante deja una entrada; el Atrás del móvil (o el botón) vuelve por ellas ——
  const pasoRef = useRef(paso); pasoRef.current = paso
  const pasosRef = useRef(pasos); pasosRef.current = pasos
  const empujados = useRef(0), saliendo = useRef(false)
  useEffect(() => {
    try { history.replaceState({ ...sinHoja(history.state), onb: pasoRef.current }, '', location.href) } catch { /* nada */ }
    const pop = () => {
      if (saliendo.current) return
      const p = (history.state as { onb?: Paso; hoja?: number } | null)
      if (p?.hoja) return   // se abrió o cerró una hoja («Cómo activarlo»): no es cambio de paso
      if (p?.onb && pasosRef.current.includes(p.onb) && p.onb !== pasoRef.current) { empujados.current = Math.max(0, empujados.current - 1); setPaso(p.onb) }
    }
    addEventListener('popstate', pop)
    return () => removeEventListener('popstate', pop)
  }, [])
  const irA = (nuevo: Paso, adelante: boolean) => {
    if (nuevo === paso) return
    if (!adelante && empujados.current > 0 && history.state?.onb === paso) { history.back(); return }   // el popstate pone el paso
    try {
      if (adelante) { history.pushState({ ...sinHoja(history.state), onb: nuevo }, '', location.href); empujados.current++ }
      else history.replaceState({ ...sinHoja(history.state), onb: nuevo }, '', location.href)
    } catch { /* nada */ }
    setPaso(nuevo)
  }
  const ir = (d: number) => irA(pasos[Math.max(0, Math.min(pasos.length - 1, i + d))], d > 0)
  /** Recoge las entradas del historial que dejó la guía (si no, el Atrás del móvil tendría que pasar por todas). */
  const recoger = () => new Promise<void>(ok => {
    const n = empujados.current
    empujados.current = 0
    if (!n) return ok()
    saliendo.current = true
    let hecho = false
    const fin = () => { if (hecho) return; hecho = true; removeEventListener('popstate', fin); saliendo.current = false; ok() }
    addEventListener('popstate', fin); setTimeout(fin, 700)
    history.go(-n)
  })
  useEffect(() => { if (zf.data && !z) setZ(zf.data) }, [zf.data, z])
  useEffect(() => { if (!repaso) apuntar(me.user, paso) }, [paso, repaso, me.user])
  useEffect(() => {   // al cambiar de paso: arriba del todo y el foco en el título (lectores de pantalla)
    scrollTo({ top: 0 }); document.querySelector('.onb-capa')?.scrollTo({ top: 0 })
    const h = document.querySelector<HTMLElement>('.onb-card h2'); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }) }
  }, [paso, verCuentas])
  useEffect(() => {
    const guardado = (window as unknown as { zazuInstalar?: BIP }).zazuInstalar; if (guardado) setInstalar(guardado)
    const f = (e: Event) => { e.preventDefault(); setInstalar(e as BIP) }; addEventListener('beforeinstallprompt', f); return () => removeEventListener('beforeinstallprompt', f)
  }, [])
  useAtrasCierra(verCuentas, () => setVerCuentas(false))

  const guardar = async () => {
    if (!z) return
    setBusy(true)
    try { await post('/api/mi-zazu', { action: 'save', ...z }); ir(1) } catch (e) { toast((e as Error).message) } finally { setBusy(false) }
  }
  const terminar = async () => {   // también «Saltar»
    try { localStorage.setItem('hz-menu-visto', '1') } catch { /* sin almacenamiento */ }   // «Tu menú» ya va en la guía: que no salga otra vez al terminar
    if (repaso) { await recoger(); return done() }
    setBusy(true)
    try {
      await post('/api/mi-zazu', { action: 'onboarded' }); olvidar(me.user); await recoger()
      if (leerParams().tab === 'cuentas') irApp({ tab: 'inicio' }, true)   // volvió de Google a «Tus cuentas»: quien acaba la guía empieza en Inicio
      done()
    } catch (e) { toast((e as Error).message); setBusy(false) }
  }
  const nombre = z?.asistente || me.asistente || 'Zazu'
  const sinIA = !IA_PROPIA && me.ia === false
  const ua = navigator.userAgent
  const ios = /iphone|ipad/i.test(ua) || (/Mac/.test(ua) && navigator.maxTouchPoints > 1)   // los iPad dicen ser Mac
  const safariMac = !ios && /Macintosh/.test(ua) && /Safari\//.test(ua) && !/Chrome|Chromium|CriOS|Edg|Firefox|FxiOS|OPR/.test(ua) && !navigator.maxTouchPoints   // Safari del Mac: no hay aviso de instalar, va por el menú
  const instalada = EN_APP || matchMedia('(display-mode: standalone)').matches
  const sinDatos = paso === 'asistente' && !z
  const siguiente = <button className="btn-primary" onClick={() => ir(1)}>Siguiente <Icon name="arrow" size={17} /></button>
  const atras = i > 0 ? <button className="text-link" onClick={() => ir(-1)}>Atrás</button> : null
  const tarjeta = (kicker: string, titulo: ReactNode, cuerpo: ReactNode, pie: ReactNode = siguiente) =>
    <section className="onb-card"><span className="section-kicker">{kicker}</span><h2>{titulo}</h2>{cuerpo}{pie}{atras}</section>
  // los puntos de arriba: los permisos cuentan como uno
  const grupo = (p: Paso) => p.startsWith('p-') ? 'permisos' : p
  const grupos = pasos.map(grupo).filter((g, n, a) => a.indexOf(g) === n)
  const gi = grupos.indexOf(grupo(paso))
  const permisos = pasos.filter(p => p.startsWith('p-'))
  const kickerPermiso = `TUS PERMISOS · ${permisos.indexOf(paso) + 1} DE ${permisos.length}`
  const prefs = { ...(z?.prefs || me.prefs), ...borrador } as Prefs

  // «Tus cuentas» de Fran, dentro de la guía (y «Volver a la guía»)
  if (verCuentas) {
    const ctx = { me, toast, guest: false, go: () => setVerCuentas(false), ask: () => { }, draft: '', setDraft: () => { }, abrirModelos: () => { }, abrirAsistentes: () => { } } as unknown as Ctx
    return <div className="onb">
      <div className="onb-top"><BrandMark small /><button className="text-link" onClick={() => setVerCuentas(false)}><Icon name="back" size={16} /> Volver a la guía</button></div>
      <div style={{ width: '100%', maxWidth: 480 }}><CuentasScreen {...ctx} soloGoogle /></div>
      <button className="btn-primary" style={{ marginTop: 16 }} onClick={() => setVerCuentas(false)}>Volver a la guía <Icon name="arrow" size={17} /></button>
    </div>
  }

  return <div className="onb">
    <div className="onb-top"><BrandMark small />
      <div className="onb-dots" role="img" aria-label={`Paso ${gi + 1} de ${grupos.length}`}>{grupos.map((g, n) => <span key={g} className={n <= gi ? 'on' : ''} style={{ width: Math.min(22, Math.floor(150 / grupos.length) - 6) }} />)}</div>
      {paso !== 'listo' ? <button className="text-link" disabled={busy} onClick={() => void terminar()}>Saltar</button> : <span style={{ width: 32 }} />}</div>

    {sinDatos && <section className="onb-card"><h2>Un momento…</h2>
      {zf.error ? <><p>No se pudo cargar tu asistente ({zf.error}).</p><button className="btn-primary" onClick={() => void zf.reload()}>Reintentar</button></> : <p>Cargando…</p>}
      <button className="text-link" onClick={() => irA('hola', false)}>Volver al inicio</button></section>}

    {paso === 'hola' && <section className="onb-card">
      <div className="onb-art"><BrandMark /></div>
      <h2>Hola, {me.name}<span className="greeting-dot">.</span></h2>
      <p>Soy {nombre}, tu asistente personal. Te ayudo a organizar el día, escribir mensajes, recordar cosas y buscar lo que necesites.</p>
      <p className="onb-note"><Icon name="shield" size={16} /> {admin ? 'Soy tu Zazu: vivo en tu servidor, en casa. Lo que hablemos es tuyo.' : 'Soy solo para ti. Lo que hablemos es privado: nadie más lo ve, tampoco Fran.'}</p>
      {sinIA && <p className="onb-note"><Icon name="clock" size={16} /> Tu {nombre} todavía no está activo. Fran lo activará pronto; mientras, te enseño cómo funciona.</p>}
      <p>Lo dejamos listo en unos pasos cortos: tus permisos, unos datos y tus cuentas.</p>
      <button className="btn-primary" onClick={() => ir(1)}>Empezar <Icon name="arrow" size={17} /></button>
    </section>}

    {paso === 'asistente' && z && tarjeta('TU ASISTENTE', '¿Cómo se llama tu gato?', <>
      <p>Tu asistente llevará su nombre. Si no tienes gato, pon el de otra mascota o el que más te guste.</p>
      <label className="onb-field">Nombre<input value={z.asistente} maxLength={24} onChange={e => setZ({ ...z, asistente: e.target.value })} onFocus={e => e.target.value === 'Zazu' && e.target.select()} placeholder="Zazu" /></label>
      <div className="onb-field">Su forma de hablar
        <div className="onb-options">{TONOS.map(([v, t, s]) => <button key={v} type="button" className={`onb-option ${z.tono === v ? 'on' : ''}`} aria-pressed={z.tono === v} onClick={() => setZ({ ...z, tono: v })}><strong>{t}</strong><small>{s}</small></button>)}</div></div>
      <label className="onb-field">Sobre ti (si quieres)<textarea rows={3} maxLength={800} value={z.sobre_mi} onChange={e => setZ({ ...z, sobre_mi: e.target.value })} placeholder="Ej.: trabajo de enfermera por turnos, tengo un perro que se llama Tula, me gusta que me expliquen las cosas fácil…" /></label>
      <small className="muted-note" style={{ margin: 0 }}>Lo tendrá siempre en cuenta. Puedes cambiarlo cuando quieras en Tu espacio.</small></>,
      <button className="btn-primary" disabled={busy || !z.asistente.trim()} onClick={() => void guardar()}>{busy ? 'Guardando…' : 'Siguiente'} <Icon name="arrow" size={17} /></button>)}

    {paso === 'ia' && tarjeta('TU IA', 'Conecta tu ChatGPT o tu Claude', <>
      <p>{nombre} piensa con tu propia cuenta de ChatGPT (Plus o superior) o de Claude (Pro o Max). Solo hay que abrir un enlace y copiar un código, sin claves. Sin esto, {nombre} no podrá responderte.</p>
      <CuentaIA toast={toast} nombre={nombre} onConnected={() => ir(1)} /></>,
      <button className="btn-secondary" onClick={() => ir(1)}>Lo haré luego</button>)}

    {paso === 'p-notificaciones' && <PasoNotificaciones key={paso} kicker={kickerPermiso} admin={admin} me={me} nombre={nombre} toast={toast} seguir={() => ir(1)} atras={atras} />}
    {(paso === 'p-ubicacion' || paso === 'p-microfono' || paso === 'p-camara') &&
      <PasoPermiso key={paso} tipo={paso.slice(2) as Tipo} kicker={kickerPermiso} nombre={nombre} toast={toast} seguir={() => ir(1)} atras={atras} />}

    {paso === 'datos' && tarjeta('SOBRE TI', <>Unos datos para que {nombre} te trate bien</>, <>
      <p>Así sé cómo llamarte, qué hora es donde estás y cómo darte el tiempo.</p>
      {zf.loading && !zf.data ? <p>Cargando…</p>
        : <FormPreferencias key={zf.data ? 'con' : 'sin'} nombre={me.name || 'Fran'} prefs={prefs} asistente={nombre} toast={toast} autoInicial={geo === 'granted'}
          guardado={() => { void zf.reload(); ir(1) }} alCambiar={setBorrador} boton="Guardar y seguir" />}
      <small className="muted-note" style={{ margin: 0 }}>Lo puedes cambiar cuando quieras en Tu espacio.</small></>, null)}

    {paso === 'conexiones' && tarjeta('TUS CUENTAS', 'Conecta lo que ya usas', <>
      <p>{admin ? `Con tu Google, ${nombre} ve tu agenda, tus tareas y tus correos. Con tu WhatsApp, lee tus chats para avisarte y resumírtelos. Las dos cosas son opcionales.`
        : me.nivel === 'invitada' ? `Con tu WhatsApp, le escribes a ${nombre} desde ahí, como a cualquier contacto. Es opcional.`
        : `Con tu Google, ${nombre} ve tu agenda y tus tareas. Con tu WhatsApp, le escribes desde ahí. Las dos cosas son opcionales.`}</p>
      <Conexiones me={me} admin={admin} nombre={nombre} toast={toast} alIrAGoogle={() => { if (!repaso) apuntar(me.user, 'conexiones') }} abrirCuentas={() => setVerCuentas(true)} /></>)}

    {paso === 'hablar' && tarjeta('CÓMO HABLARLE', 'Háblale como a una persona', <>
      <p>Escríbele en el cuadro de abajo o pulsa el <b>micrófono</b> y díctale. Con el <b>clip</b> le mandas fotos y archivos.</p>
      <span className="section-kicker">PRUEBA A PEDIRLE</span>
      <div className="onb-ej">
        <span>«Escríbeme un mensaje para felicitar a mi hermana»</span>
        <span>«¿Qué tiempo hará el sábado en Málaga?»</span>
        <span>«Explícame esta carta del banco» (con una foto)</span>
        <span>«Acuérdate de que no como gluten»</span>
      </div></>)}

    {paso === 'cosas' && tarjeta('TUS COSAS', carpetas && rutinas ? 'Carpetas y rutinas' : carpetas ? 'Tus carpetas' : 'Tus rutinas', <>
      <ul className="onb-list">
        {carpetas && <li><Icon name="folder" size={18} /><span><b>Carpetas</b>: guarda notas, enlaces y archivos. Hazlo tú o pídeselo: «guárdalo en mis carpetas».</span></li>}
        {rutinas && <li><Icon name="clock" size={18} /><span><b>Rutinas</b>: {nombre} te escribe solo a la hora que elijas, con lo que tú le pidas. Puedes inventarte las tuyas:</span></li>}
      </ul>
      {rutinas && <div className="onb-ej">
        <span>«Cada mañana a las 8: el tiempo de hoy y una frase bonita»</span>
        <span>«Los lunes a las 19:00: 3 ideas de cena fáciles para la semana»</span>
        <span>«Todos los días a las 22:00: pregúntame cómo me ha ido el día»</span>
        <span>«Los viernes: recuérdame regar las plantas»</span>
      </div>}
      {rutinas && !admin && <><small className="muted-note" style={{ margin: 0 }}>Si quieres, crea una ahora (también puedes hacerlo luego):</small><RutinasInvitada toast={toast} /></>}</>)}

    {paso === 'menu' && tarjeta('TU MENÚ', 'Qué hay en cada sitio', <>
      <small className="muted-note" style={{ margin: 0 }}>Ábrelo con el botón ☰ de arriba o con «Todo», abajo.</small>
      <GuiaMenu me={me} nombre={nombre} /></>)}

    {paso === 'listo' && tarjeta('TENLO A MANO', instalada ? <>¡Todo listo<span className="greeting-dot">!</span></> : <>Pon a {nombre} en tu pantalla de inicio</>, <>
      {instalada ? <p className="onb-note"><Icon name="check" size={16} /> Ya tienes {nombre} en tu pantalla de inicio{nombre !== (EN_APP ? 'HolaZazu' : 'Zazu') ? `: es el icono «${EN_APP ? 'HolaZazu' : 'Zazu'}»` : ''}.</p> : instalar ? <button className="btn-secondary" onClick={() => void instalar.prompt().then(() => setInstalar(null))}><Icon name="download" size={17} /> Añadir a pantalla de inicio</button>
        : safariMac ? <ol className="onb-list num"><li>En Safari, abre el menú <b>Archivo</b> (arriba, en la barra del Mac).</li><li>Elige <b>«Añadir al Dock»</b>.</li></ol>
        : ios ? <ol className="onb-list num"><li>Abre esta página en <b>Safari</b>.</li><li>Pulsa el botón <b>Compartir</b> (el cuadrado con la flecha hacia arriba).</li><li>Elige <b>«Añadir a pantalla de inicio»</b>.</li></ol>
          : <ol className="onb-list num"><li>Abre esta página en <b>Chrome</b>.</li><li>Pulsa los <b>tres puntos</b> arriba a la derecha.</li><li>Elige <b>«Añadir a pantalla de inicio»</b> o <b>«Instalar aplicación»</b>.</li></ol>}
      {!instalada && <p>Así entras con un toque, como cualquier app.{nombre !== 'Zazu' ? ' El icono se llamará «Zazu».' : ''}</p>}
      {admin ? <><span className="section-kicker">TÚ DECIDES</span>
        <ul className="onb-list">
          <li><Icon name="shield" size={18} /><span>En tu PC, lo importante (instalar, borrar, órdenes de administrador) te lo pregunta antes: <b>Permitir</b> o <b>Rechazar</b>.</span></li>
          <li><Icon name="settings" size={18} /><span>No cambia la app por su cuenta: los cambios los decides tú.</span></li>
          <li><Icon name="mail" size={18} /><span>No envía correos ni mensajes en tu nombre si no se lo pides.</span></li>
        </ul></>
        : <><span className="section-kicker">LO QUE {nombre.toUpperCase()} NO HACE</span>
        <ul className="onb-list">
          <li><Icon name="close" size={18} /><span>No toca ningún ordenador ni sus archivos.</span></li>
          <li><Icon name="settings" size={18} /><span>No cambia la app por su cuenta: eso solo lo decide Fran.</span></li>
          <li><Icon name="mail" size={18} /><span>No envía correos en tu nombre ni comparte lo que le cuentas.</span></li>
        </ul></>}
      <small className="muted-note" style={{ margin: 0 }}>Tus permisos y tus cuentas los cambias cuando quieras en <b>Tu espacio</b>.</small>
      {sinIA && <p className="onb-note"><Icon name="clock" size={16} /> Tu {nombre} todavía no está activo. Fran lo activará pronto.</p>}</>,
      <button className="btn-primary" disabled={busy} onClick={() => void terminar()}>{repaso ? 'Cerrar la guía' : `Empezar a usar ${nombre}`} <Icon name="arrow" size={17} /></button>)}
  </div>
}

/** Cómo está un permiso, en una etiqueta. */
type Est = 'si' | 'no' | 'bloqueado' | 'apagada' | 'mirando' | 'noapp'
/** g: el micrófono (m), la ubicación o la cámara (f), las notificaciones (fp). */
type Genero = 'm' | 'f' | 'fp'
const ETIQ: Record<Est, [(g: Genero) => string, string, string]> = {
  si: [g => g === 'fp' ? 'Ya están activadas' : `Ya está activad${g === 'f' ? 'a' : 'o'}`, '#e7f0db', '#2d5133'], no: [() => 'Todavía sin activar', '#f0f1ec', '#4f5b52'],
  bloqueado: [g => g === 'fp' ? 'Están bloqueadas' : `Está bloquead${g === 'f' ? 'a' : 'o'}`, '#fbe9e5', '#6b2c22'],
  apagada: [() => 'Permitida, pero la ubicación del móvil está apagada', '#fff3d6', '#6a4a00'], mirando: [() => 'Comprobando…', '#f0f1ec', '#4f5b52'],
  noapp: [() => 'Todavía no llegan a esta app', '#f0f1ec', '#4f5b52'],
}
const GENERO: Record<Tipo, Genero> = { microfono: 'm', ubicacion: 'f', camara: 'f', notificaciones: 'fp' }
const Etiqueta = ({ e, g }: { e: Est; g: Genero }) => <span role="status" style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 6, borderRadius: 999, padding: '5px 12px', fontSize: 14, fontWeight: 600, background: ETIQ[e][1], color: ETIQ[e][2] }}>
  {e === 'si' && <Icon name="check" size={15} />}{ETIQ[e][0](g)}</span>

/** Una pantalla de permiso: para qué sirve, cómo está de verdad y el botón. Si está activado, «Siguiente»; si no, «Ahora no». */
function CajaPermiso({ kicker, icono, titulo, para, e, g, boton, extra, seguir, atras }:
  { kicker: string; icono: IconName; titulo: string; para: ReactNode; e: Est; g: Genero; boton?: ReactNode; extra?: ReactNode; seguir: () => void; atras: ReactNode }) {
  return <section className="onb-card">
    <span className="section-kicker">{kicker}</span>
    <div className="onb-art" style={{ width: 64, height: 64, borderRadius: 20 }}><Icon name={icono} size={30} /></div>
    <h2>{titulo}</h2>
    <p>{para}</p>
    <Etiqueta e={e} g={g} />
    {extra}
    {e === 'si' || e === 'noapp' ? <button className="btn-primary" onClick={seguir}>Siguiente <Icon name="arrow" size={17} /></button>
      : <>{boton}<button className="btn-secondary" onClick={seguir}>Ahora no</button></>}
    {atras}
  </section>
}

const TEXTOS: Record<'ubicacion' | 'microfono' | 'camara', { icono: IconName; titulo: string; para: (n: string) => string }> = {
  ubicacion: { icono: 'pin', titulo: 'Tu ubicación', para: n => `Para que ${n} sepa en qué ciudad estás: el tiempo de allí y tu hora bien puesta cuando viajas. Solo la ciudad, nunca tu calle.` },
  microfono: { icono: 'mic', titulo: 'Tu micrófono', para: n => `Para dictarle a ${n} en vez de escribir. Solo escucha mientras pulsas el micrófono.` },
  camara: { icono: 'camera', titulo: 'Tu cámara', para: n => `Para hacerle una foto a una carta, una receta o un cartel, y que ${n} te lo explique.` },
}

/** Ubicación, micrófono o cámara: se pide de verdad (en la app, con el permiso del sistema) y, si está bloqueado, «Cómo activarlo». */
function PasoPermiso({ tipo, kicker, nombre, toast, seguir, atras }: { tipo: Tipo; kicker: string; nombre: string; toast: (m: string) => void; seguir: () => void; atras: ReactNode }) {
  const [e, , ponE] = usePermiso(tipo)
  const nat = useNativo()
  const [guia, setGuia] = useState(false)
  const [busy, setBusy] = useState(false)
  const t = TEXTOS[tipo as 'ubicacion' | 'microfono' | 'camara']
  const apagada = tipo === 'ubicacion' && e === 'granted' && nat?.ubicacionSistema === 'off'
  const est: Est = apagada ? 'apagada' : e === 'granted' ? 'si' : e === 'denied' ? 'bloqueado' : 'no'
  const activar = async () => {
    if (e === 'denied') { setGuia(true); return }
    if (apagada) { if (!abrirAjustes('ubicacion')) setGuia(true); return }
    setBusy(true)
    try {
      const r = tipo === 'ubicacion' ? await pedirPosicion() : await pedirMedio(tipo as 'microfono' | 'camara')
      r.stream?.getTracks().forEach(x => x.stop())
      if (r.pos || r.stream) {
        ponE('granted')
        if (tipo === 'microfono') { try { localStorage.removeItem('hz-sin-micro') } catch { /* sin almacenamiento */ } }
        toast(tipo === 'microfono' ? '¡Hecho! El micrófono ya está activado.' : tipo === 'camara' ? '¡Hecho! La cámara ya está activada.' : '¡Hecho! La ubicación ya está activada.')
        return
      }
      if (r.estado === 'denied') { ponE('denied'); setGuia(true) }
      else if (tipo === 'ubicacion' && r.error === 'posicion' && r.estado === 'granted') { ponE('granted'); if (nat?.ubicacionSistema === 'off') setGuia(true) }
      toast(mensajePedido(tipo, r))
    } finally { setBusy(false) }
  }
  return <>
    {guia && <GuiaPermiso tipo={tipo} toast={toast} cerrar={() => setGuia(false)} />}
    <CajaPermiso kicker={kicker} icono={t.icono} titulo={t.titulo} para={t.para(nombre)} e={est} g={GENERO[tipo]} seguir={seguir} atras={atras}
      extra={tipo === 'ubicacion' && est === 'si' ? <small className="muted-note" style={{ margin: 0 }}>En el paso de tus datos eliges si quieres que {nombre} cambie tu hora sola cuando viajes.</small> : null}
      boton={<button className="btn-primary" disabled={busy} onClick={() => void activar()}>
        {busy ? 'Esperando tu respuesta…' : est === 'bloqueado' ? (tipo === 'microfono' ? 'Cómo activarlo' : 'Cómo activarla') : apagada ? 'Encender la ubicación' : 'Activar'} {!busy && <Icon name="arrow" size={17} />}</button>} />
  </>
}

/** Notificaciones: en la app con puente, las del sistema; en el navegador, Web Push (con su notificación de prueba). */
function PasoNotificaciones({ kicker, admin, me, nombre, toast, seguir, atras }: { kicker: string; admin: boolean; me: Me; nombre: string; toast: (m: string) => void; seguir: () => void; atras: ReactNode }) {
  const push = usePush(toast, admin)
  const [nApp, , ponNApp] = usePermiso('notificaciones')
  const [guia, setGuia] = useState(false)
  const [busy, setBusy] = useState(false)
  const conPuente = EN_APP && !!nativo()
  // a una invitada en la app no le llega ningún aviso nativo (el token del móvil es solo de Fran) ni hay Web Push en el WebView: no se le promete nada
  const sinAvisos = EN_APP && !admin
  const familia = !admin && me.nivel === 'familia'
  const iphone = /iPhone|iPad/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  const est: Est = sinAvisos ? 'noapp' : conPuente ? (nApp === 'granted' ? 'si' : nApp === 'denied' ? 'bloqueado' : 'no')
    : EN_APP ? 'no'
    : push.estado === 'si' ? 'si' : push.estado === 'bloqueado' ? 'bloqueado' : push.estado === '?' ? 'mirando' : 'no'
  const activar = async () => {
    if (conPuente) {
      if (nApp === 'denied') { setGuia(true); return }
      setBusy(true)
      try { const r = await pedirNativo('notificaciones'); ponNApp(r); if (r === 'granted') toast('¡Hecho! Ya te puedo avisar.'); else if (r === 'denied') setGuia(true); else toast('Has dicho que no. Si las quieres, toca otra vez y pulsa «Permitir».') } finally { setBusy(false) }
      return
    }
    if (EN_APP || push.estado === 'bloqueado' || (push.estado === 'nosoporta' && iphone)) { setGuia(true); return }
    if (push.estado === 'nosoporta') { toast('Este navegador no puede mandar avisos. Prueba con Chrome.'); return }
    if (push.estado === 'error') { toast(`Aquí no se pueden activar: ${push.fallo}`); return }
    if (push.estado === '?') { toast('Un segundo, que lo estoy comprobando.'); return }
    const r = await push.activar()
    if (r === 'bloqueado') setGuia(true)
  }
  const para = admin ? `Para que ${nombre} te avise en el móvil: lo que tenga que preguntarte y, si algo falla en casa, enseguida.`
    : sinAvisos ? `En esta app, ${nombre} todavía no te puede mandar avisos al móvil. Tus recordatorios y tus rutinas te llegan por WhatsApp${me.demo ? '' : ' (lo vinculas en el paso de tus cuentas, dentro de nada)'}. Si prefieres avisos en el móvil, abre holazazu.app en Chrome y actívalos allí.`
    : `Para que ${nombre} te avise en el móvil: ${familia ? 'tus recordatorios, tus rutinas y cuando necesite tu permiso' : 'tus recordatorios y tus rutinas'}. Aunque tengas la app cerrada.`
  const nota = sinAvisos ? '' : !conPuente && !EN_APP && push.estado === 'nosoporta'
    ? (iphone ? 'En el iPhone, los avisos solo llegan con Zazu en la pantalla de inicio. Toca «Cómo activarlas» y te lo enseño.' : 'Este navegador no puede mandar avisos. No pasa nada: sigue, y actívalos luego desde Chrome.')
    : EN_APP && !conPuente ? 'En esta app se activan en los ajustes del móvil. Toca «Cómo activarlas» y te enseño dónde.'
    : push.estado === 'error' && !EN_APP ? `Aquí no se pueden activar ahora (${push.fallo}).` : ''
  return <>
    {guia && <GuiaPermiso tipo="notificaciones" toast={toast} cerrar={() => setGuia(false)} alPermitir={EN_APP ? undefined : () => { void push.activar() }} />}
    <CajaPermiso kicker={kicker} icono="bell" titulo="¿Te aviso en el móvil?" para={para} e={est} g="fp" seguir={seguir} atras={atras}
      extra={<>{nota && <small className="muted-note" style={{ margin: 0 }}>{nota}</small>}
        {familia && <div className="onb-note"><Icon name="shield" size={16} /><span>Cuando {nombre} quiera apuntarte una cita o una tarea, {sinAvisos ? 'te lo preguntará aquí, en la app, al abrirla,' : 'te llegará un aviso'} para <b>Permitir</b> o <b>Rechazar</b>. Sin tu permiso, no se apunta nada.</span></div>}</>}
      boton={<button className="btn-primary" disabled={busy || push.busy} onClick={() => void activar()}>
        {busy || push.busy ? 'Esperando tu respuesta…' : est === 'bloqueado' || (EN_APP && !conPuente) || (push.estado === 'nosoporta' && iphone) ? 'Cómo activarlas' : 'Activar'} {!(busy || push.busy) && <Icon name="arrow" size={17} />}</button>} />
  </>
}

type CuentasG = { google: { email: string; error?: boolean; services?: string[] }[]; google_web?: boolean; whatsapp?: string | null; whatsapp_sync?: string | null; whatsapp_vivo?: boolean | null }

/** Google y WhatsApp: si ya están conectados lo dice; si no, el botón. Fran: su WhatsApp se ve (y se vincula) en «Tus cuentas». */
function Conexiones({ me, admin, nombre, toast, alIrAGoogle, abrirCuentas }: { me: Me; admin: boolean; nombre: string; toast: (m: string) => void; alIrAGoogle: () => void; abrirCuentas: () => void }) {
  const sinGoogle = !admin && me.nivel === 'invitada'
  const g = useFetch<CuentasG>(sinGoogle ? null : '/api/cuentas')
  const todas = g.data?.google || []
  const bien = todas.filter(x => !x.error), mal = todas.filter(x => x.error)
  const conectar = admin && g.data && !g.data.google_web
    ? <button className={bien.length && !mal.length ? 'btn-secondary' : 'btn-primary'} onClick={abrirCuentas}>{bien.length ? 'Conectar otra cuenta' : 'Conectar mi Google'} <Icon name="arrow" size={17} /></button>
    : <a className={bien.length && !mal.length ? 'btn-secondary' : 'btn-primary'} href="/oauth/google/start?mode=connect" onClick={alIrAGoogle}>{bien.length ? 'Conectar otra cuenta' : mal.length ? 'Volver a conectar mi Google' : 'Conectar mi Google'} <Icon name="arrow" size={17} /></a>
  return <>
    <span className="section-kicker">TU GOOGLE</span>
    {sinGoogle ? <small className="muted-note" style={{ margin: 0 }}>{SIN_GOOGLE}</small>
      : g.loading && !g.data ? <p className="onb-note"><Icon name="clock" size={16} /> Comprobando…</p>
      : g.error && !g.data ? <p className="onb-note"><Icon name="close" size={16} /><span>No pude comprobarlo. <button className="text-link" style={{ padding: 0, minHeight: 0 }} onClick={() => void g.reload()}>Reintentar</button></span></p>
      : <>
        {bien.length > 0 && <p className="onb-note"><Icon name="check" size={16} /><span><b>Conectado</b>: <span style={{ overflowWrap: 'anywhere' }}>{bien.map(x => x.email).join(', ')}</span>. {nombre} ya ve tu agenda, tus tareas y tus correos.</span></p>}
        {mal.length > 0 && <p className="onb-note"><Icon name="close" size={16} /><span>{mal.map(x => x.email).join(', ')}: hay que volver a conectarla.</span></p>}
        {!bien.length && <>
          <ul className="onb-list">
            <li><Icon name="calendar" size={18} /> Tu calendario, y podrás apuntar citas</li>
            <li><Icon name="check" size={18} /> Tus tareas de Google</li>
            <li><Icon name="mail" size={18} /> {admin ? 'Tus correos: los lee y te deja borradores; no envía nada solo' : 'Tus correos (solo para leer: nunca envía nada)'}</li>
          </ul>
          <div className="onb-note"><Icon name="lightbulb" size={16} /><span>Google dirá <b>«Google no ha verificado esta aplicación»</b>. Es normal: {admin ? 'la app es tuya y no está publicada' : 'la app es de Fran'}. Pulsa <b>Configuración avanzada</b>, luego <b>Ir a holazazu.app</b>, y marca todas las casillas.</span></div>
        </>}
        {(!bien.length || mal.length > 0 || admin) && conectar}
        {EN_APP && !appConAvisos() && !bien.length && <small className="muted-note" style={{ margin: 0 }}>Si la app te dice que esto se hace desde Chrome: abre holazazu.app en Chrome y conéctalo allí. Después aquí saldrá conectado.</small>}
      </>}
    <span className="section-kicker">TU WHATSAPP</span>
    {admin ? <TarjetaWhatsAppFran toast={toast} />
      : <><small className="muted-note" style={{ margin: 0 }}>Se vincula con un código, en un minuto.</small>
        <CanalesInvitada toast={toast} nombre={nombre} soloWhatsApp /></>}
  </>
}

/** El menú, sección a sección (lo que tiene esta persona). Lo usan la guía y el aviso de una vez. */
export function GuiaMenu({ me, nombre }: { me: Me; nombre: string }) {
  const carpetas = puede(me, 'carpetas'), rutinas = puede(me, 'rutinas')
  const admin = me.role !== 'guest', sinGoogle = !admin && me.nivel === 'invitada'   // su acceso no incluye Google: no se le promete
  const espacio = admin ? 'tus permisos, tu Google, tu WhatsApp, tu país y tu hora'
    : `tus permisos, ${sinGoogle ? '' : 'tu Google, '}tu WhatsApp, tu país, tu hora y cómo es ${nombre}`
  return <>
      <ul className="onb-list">
        <li><Icon name="plus" size={18} /><span><b>Nuevo chat</b>: empieza una conversación en blanco con {nombre}.</span></li>
        <li><Icon name="spark" size={18} /><span><b>Organizar mi agenda</b>: {nombre} mira lo que tienes y te propone cómo repartirlo. No cambia nada sin tu OK.</span></li>
        <li><Icon name="chat" size={18} /><span><b>Chats</b>: tus conversaciones de antes.</span></li>
        <li><Icon name="calendar" size={18} /><span><b>Agenda</b>: tu día y tu semana{puede(me, 'calendario') || sinGoogle ? '' : ' (con tu Google conectado: tus citas y tareas)'}.</span></li>
        {puede(me, 'noticias') && <li><Icon name="file" size={18} /><span><b>Noticias</b>: las de los temas y países que elijas.</span></li>}
        {puede(me, 'correo') && <li><Icon name="mail" size={18} /><span><b>Correo</b>: {admin ? `tus últimos correos, para verlos de un vistazo. Si quieres un borrador, pídeselo a ${nombre} en el chat.` : 'tus últimos correos (solo leer).'}</span></li>}
        {rutinas && <li><Icon name="clock" size={18} /><span><b>Rutinas</b>: los mensajes que {nombre} te manda solo, a tu hora.</span></li>}
        {carpetas && <li><Icon name="folder" size={18} /><span><b>Carpetas</b>: lo que guardas: notas, fotos y archivos.</span></li>}
        {puede(me, 'dinero') && <li><Icon name="shield" size={18} /><span><b>Dinero</b>: tus gastos y suscripciones, sacados de tus recibos.</span></li>}
        {puede(me, 'semana') && <li><Icon name="calendar" size={18} /><span><b>Semana</b>: tu semana de un vistazo.</span></li>}
        {puede(me, 'empleo') && <li><Icon name="file" size={18} /><span><b>Empleo</b>: tus candidaturas y las ofertas de trabajo.</span></li>}
        {me.role !== 'guest' && <li><Icon name="grid" size={18} /><span><b>Más</b>: el Panel de Hermes y los Ajustes.</span></li>}
        <li><Icon name="settings" size={18} /><span><b>Tu espacio</b> (arriba del todo en el menú, con tu nombre): {espacio}. <b>Míralo: ahí lo decides todo tú.</b></span></li>
      </ul>
  </>
}

/** A quien ya hizo la guía antes de que existiera esta pantalla: «Tu menú» una vez (por cuenta, con menu_visto; y por dispositivo). */
export function MenuUnaVez({ me }: { me: Me }) {
  const [ver, setVer] = useState(() => { try { return localStorage.getItem('hz-menu-visto') !== '1' } catch { return false } })
  if (!ver || me.menu_visto) return null   // menu_visto: ya hizo la guía (que lo enseña) o lo cerró en otro aparato
  const cerrar = () => {
    try { localStorage.setItem('hz-menu-visto', '1') } catch { /* sin almacenamiento */ }
    setVer(false)
    void post('/api/mi-zazu', { action: 'onboarded' }).catch(() => { })   // ya estaba hecha: solo apunta menu_visto para los demás aparatos
  }
  return <div role="dialog" aria-modal="true" aria-label="Tu menú" style={{ position: 'fixed', inset: 0, zIndex: 79, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 16 }}>
    <div className="acc-card" style={{ width: '100%', maxWidth: 480, maxHeight: '90dvh', overflowY: 'auto' }}>
      <span className="section-kicker">NOVEDAD</span><strong style={{ fontSize: 18 }}>Tu menú, sección a sección</strong>
      <small>Ábrelo con el botón ☰ de arriba o con «Todo», abajo.</small>
      <GuiaMenu me={me} nombre={me.asistente || 'Zazu'} />
      <div className="actions"><button className="btn-primary" onClick={cerrar}>Entendido</button></div>
    </div></div>
}
