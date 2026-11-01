import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Icon } from '../icons'
import { MAS } from '../data'
import type { Quick } from '../data'
import { api, fmtSize, irA, nombreAsistente, post, useAtrasCierra } from '../lib'
import { PERFIL_HERMES } from '../tipos'
import type { ChatApi } from '../tipos'

type Adj = { name: string; ruta: string | null; imagen: boolean; vista: string | null }

/** Dictado: se graba aquí y Whisper lo pasa a texto en el servidor de casa (POST /api/dictado). Sin micro o sin MediaRecorder no hay botón. */
import { microApagado } from './Permisos'
import { GuiaPermiso, mensajePedido, pedirMedio, usePermiso } from './PermisosDispositivo'
const PUEDE_DICTAR = typeof MediaRecorder !== 'undefined' && typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
const MAX_DICTADO_MS = 5 * 60 * 1000   // corta solo a los 5 min (el servidor admite 15 MB)
const LIMITE = 100 * 1024 * 1024   // Cloudflare corta las subidas de más de 100 MB desde fuera de casa
const stamp = () => new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')
/** Lo que pega el portapapeles suele llamarse «image.png»: se le pone un nombre que se entienda. */
const nombreDe = (f: File) => /^(image|imagen|blob)(\.\w+)?$/i.test(f.name) || f.name === '' ? `captura-${stamp()}.${(f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')}` : f.name

/** Icono de portapapeles (el de documento confundía con «adjuntar») */
type Nativo = { portapapeles?: () => string; imagenPegada?: () => string }
const nativo = () => (window as unknown as { ZazuNativo?: Nativo }).ZazuNativo
/** {tipo, imagen(base64)} de la app de Android → un archivo para adjuntar */
function aArchivo(d: { tipo?: string; imagen?: string }) {
  const bin = atob(d.imagen!), b = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i)
  return new File([b], '', { type: d.tipo })
}
const Pegar = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="8" y="2.5" width="8" height="4" rx="1.2" /><path d="M16 4.5h2a2 2 0 0 1 2 2V19a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6.5a2 2 0 0 1 2-2h2" /><path d="M9 12h6M9 16h4" /></svg>

/** Icono de «Parar» (la respuesta en marcha) */
const Cuadrado = () => <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2.5" fill="currentColor" /></svg>

/** Cuadro de escribir. Mientras hay respuesta en marcha, el botón de enviar es «Parar». El micro va siempre a su lado (sin texto o con él: lo dictado se añade).
 *  Fran (no `guest`) tiene además el menú «+» (recordatorio, nota, evento…). `centrado`: el inicio en escritorio, con el cuadro bajo el saludo. */
export default function Composer({ chat, draft, setDraft, toast, onSent, canAttach = true, name, guest = false, soloLectura = false, centrado = false, placeholder, sinMas = false }: { chat: ChatApi; draft: string; setDraft: (s: string) => void; toast: (m: string) => void; onSent: () => void; canAttach?: boolean; name?: string; placeholder?: string; sinMas?: boolean; guest?: boolean; soloLectura?: boolean; centrado?: boolean }) {
  const area = useRef<HTMLTextAreaElement>(null)
  const file = useRef<HTMLInputElement>(null)
  const foto = useRef<HTMLInputElement>(null)
  const masRef = useRef<HTMLDivElement>(null)
  const rec = useRef<MediaRecorder | null>(null)
  const pulsado = useRef(0)   // cuándo se pulsó el micro (para distinguir «toca y habla» de «mantén y suelta»)
  const [listening, setListening] = useState(false)
  const [transcribiendo, setTranscribiendo] = useState(false)
  const [micEstado, , ponMic] = usePermiso('microfono')   // bloqueado: el botón enseña cómo desbloquearlo en vez de fallar
  const [guiaMic, setGuiaMic] = useState(false)
  const draftRef = useRef(draft)
  draftRef.current = draft
  useEffect(() => () => { const r = rec.current; if (r) { r.ondataavailable = null; r.onstop = null; if (r.state !== 'inactive') r.stop(); r.stream.getTracks().forEach(t => t.stop()) } }, [])   // al salir, soltar el micro
  const [adj, setAdj] = useState<Adj[]>([])
  const [subiendo, setSubiendo] = useState(0)
  const [arrastrando, setArrastrando] = useState(false)
  const [mas, setMas] = useState(false)
  const attachRef = useRef<(fs: File[]) => Promise<void>>(async () => { })
  const sendRef = useRef<() => void>(() => { })
  const shift = useRef(false)

  const grow = () => { const a = area.current; if (a) { a.style.height = 'auto'; a.style.height = `${Math.min(a.scrollHeight, 220)}px` } }
  const change = (v: string) => setDraft(v)
  useLayoutEffect(grow, [draft])   // también cuando el texto lo pone la app (compartir, un envío rechazado, una tarjeta)
  const alFinal = () => requestAnimationFrame(() => { const a = area.current; if (a) { a.focus(); a.setSelectionRange(a.value.length, a.value.length) } })

  async function attachMany(fs: File[]) {
    if (!canAttach || !fs.length) return
    const grandes = fs.filter(f => f.size > LIMITE)
    if (grandes.length && !confirm(`${grandes.map(f => `«${nombreDe(f)}» (${fmtSize(f.size)})`).join(', ')} ${grandes.length === 1 ? 'pesa' : 'pesan'} más de 100 MB. Desde fuera de casa suele fallar la subida. ¿Lo intento igualmente?`)) fs = fs.filter(f => f.size <= LIMITE)
    if (!fs.length) return
    try { await post('/api/mkdir', { path: '', name: 'Adjuntos' }) } catch { /* ya existe */ }
    for (const f of fs) {
      const nombre = nombreDe(f)
      setSubiendo(n => n + 1)
      try {
        const r = await api<{ name: string; ruta?: string | null }>(`/api/upload?path=Adjuntos&name=${encodeURIComponent(nombre)}`, { method: 'POST', body: f })
        const imagen = f.type.startsWith('image/')
        setAdj(a => [...a, { name: r.name, ruta: r.ruta || null, imagen, vista: imagen ? URL.createObjectURL(f) : null }])
      } catch (e) { toast(`No se pudo subir ${nombre}: ${(e as Error).message}`) } finally { setSubiendo(n => n - 1) }
    }
    area.current?.focus()
  }
  attachRef.current = attachMany

  /** Quitar un adjunto antes de enviarlo: ya estaba subido, así que va a la papelera (se puede recuperar 30 días). */
  const quitar = (i: number) => {
    const x = adj[i]
    if (!x) return
    if (x.vista) URL.revokeObjectURL(x.vista)
    setAdj(a => a.filter((_, j) => j !== i))
    if (!guest) post('/api/papelera', { path: `Adjuntos/${x.name}` }).catch(() => { /* si falla, solo se queda en Adjuntos */ })
  }

  // Pegar (Ctrl+V) y soltar archivos en cualquier parte de la pantalla del chat, no solo con el cuadro enfocado
  useEffect(() => {
    if (!canAttach || soloLectura) return
    const paste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return   // en el cuadro de texto ya lo maneja su propio onPaste
      const fs = Array.from(e.clipboardData?.files || [])
      if (fs.length && !e.clipboardData?.getData('text/plain')) { e.preventDefault(); void attachRef.current(fs) }
    }
    const over = (e: DragEvent) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); setArrastrando(true) } }
    const leave = (e: DragEvent) => { if (!e.relatedTarget) setArrastrando(false) }
    const drop = (e: DragEvent) => { if (e.dataTransfer?.files.length) { e.preventDefault(); setArrastrando(false); void attachRef.current(Array.from(e.dataTransfer.files)) } }
    addEventListener('paste', paste); addEventListener('dragover', over); addEventListener('dragleave', leave); addEventListener('drop', drop)
    return () => { removeEventListener('paste', paste); removeEventListener('dragover', over); removeEventListener('dragleave', leave); removeEventListener('drop', drop) }
  }, [canAttach, soloLectura])

  // App de Android: una captura elegida en el portapapeles del teclado llega aquí (la app la recoge del teclado)
  useEffect(() => {
    if (!canAttach || soloLectura) return
    const llega = () => {
      try {
        const d = JSON.parse(nativo()?.imagenPegada?.() || '{}') as { tipo?: string; imagen?: string; error?: string }
        if (d.imagen && d.tipo) void attachRef.current([aArchivo(d)])
        else if (d.error) toast(d.error)
      } catch { toast('No pude pegar la imagen. Usa el clip.') }
    }
    addEventListener('zazu-imagen-pegada', llega)
    return () => removeEventListener('zazu-imagen-pegada', llega)
  }, [canAttach, soloLectura])   // eslint-disable-line react-hooks/exhaustive-deps

  // Intro envía también en el móvil: Gboard manda el Intro mientras «compone» la palabra y keydown no sirve; beforeinput sí
  useEffect(() => {
    const a = area.current
    if (!a) return
    const f = (e: InputEvent) => { if ((e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') && !shift.current) { e.preventDefault(); sendRef.current() } }
    a.addEventListener('beforeinput', f)
    return () => a.removeEventListener('beforeinput', f)
  }, [])

  // menú «+»: se cierra al tocar fuera, con Esc o con el Atrás del móvil
  useAtrasCierra(mas, () => setMas(false))
  useEffect(() => {
    if (!mas) return
    const fuera = (e: PointerEvent) => { const t = e.target as Element; if (!masRef.current?.contains(t) && !t.closest?.('.mas-btn')) setMas(false) }   // el propio «+» ya lo cierra
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMas(false) }
    document.addEventListener('pointerdown', fuera); addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', fuera); removeEventListener('keydown', esc) }
  }, [mas])

  /** Acción del «+»: deja la frase empezada (lo ya escrito se queda detrás) y, si es «Guardar archivo», abre el selector.
   *  Necesitan herramientas: si estás en Charla, Escritor o Investigador (o en una conversación antigua), la frase va a una conversación nueva de Zazu con todas sus herramientas. */
  function elegir(q: Quick) {
    setMas(false)
    if (chat.cur.profile !== PERFIL_HERMES) { const enHilo = !!chat.cur.id; chat.newChat(PERFIL_HERMES); if (enHilo) irA({ tab: 'chat' }) }
    const t = draft.trim()
    if (!t.toLowerCase().startsWith(q.prompt.trim().toLowerCase())) change(q.archivo ? (t ? `${q.prompt}. ${t}` : q.prompt) : `${q.prompt}${t}`)
    if (q.archivo) file.current?.click(); else alFinal()
  }

  /** Botón «Pegar»: en el móvil, mantener pulsado en el cuadro solo pega texto; este botón lee también las imágenes del portapapeles. */
  async function pegar() {
    setMas(false)
    const pegarTexto = (t: string) => { change(`${draft}${draft && !draft.endsWith(' ') ? ' ' : ''}${t}`); area.current?.focus() }
    // App de Android (2.5.2 o más): su WebView no deja leer el portapapeles, así que lo lee la app
    const n = nativo()
    if (typeof n?.portapapeles === 'function') {
      try {
        const d = JSON.parse(n.portapapeles() || '{}') as { texto?: string; tipo?: string; imagen?: string; error?: string }
        if (d.imagen && d.tipo) await attachMany([aArchivo(d)])
        else if (d.texto) pegarTexto(d.texto)
        else toast(d.error || 'No hay nada que pegar en el portapapeles')
      } catch { toast('No pude leer el portapapeles. Mantén pulsado en el cuadro de texto y elige «Pegar», o usa el clip.') }
      return
    }
    try {
      const fs: File[] = []; let texto = ''
      for (const it of await navigator.clipboard.read()) {
        for (const t of it.types) {
          if (t.startsWith('image/')) { const b = await it.getType(t); fs.push(new File([b], '', { type: t })) }
          else if (t === 'text/plain' && !texto) texto = await (await it.getType(t)).text()
        }
      }
      if (fs.length) await attachMany(fs)
      else if (texto) { change(`${draft}${draft && !draft.endsWith(' ') ? ' ' : ''}${texto}`); area.current?.focus() }
      else toast('No hay nada que pegar en el portapapeles')
    } catch {
      try {
        const t = await navigator.clipboard.readText()
        if (t) { change(`${draft}${draft && !draft.endsWith(' ') ? ' ' : ''}${t}`); area.current?.focus() } else toast('No hay nada que pegar en el portapapeles')
      } catch { toast('El navegador no deja leer el portapapeles. Mantén pulsado en el cuadro de texto y elige «Pegar», o usa el clip.') }
    }
  }

  function send() {
    const text = draft.trim()
    if (soloLectura || (!text && !adj.length) || subiendo) return   // con una respuesta en marcha también se envía: el chat la para y sigue con el contexto
    if (chat.soloLectura) chat.newChat(guest ? chat.cur.profile : PERFIL_HERMES)   // con una conversación de WhatsApp abierta: empieza una nueva
    const refs = adj.map(a => guest ? `[Archivo guardado en mis carpetas › Adjuntos › ${a.name}]` : `[${a.imagen ? 'Imagen adjunta' : 'Archivo adjunto'}: ${a.ruta || `~/Compartido/Adjuntos/${a.name}`}]`)
    // Para que Zazu VEA una imagen, Hermes solo la adjunta al modelo (herramienta vision) si la ruta va SOLA, entre comillas,
    // al PRINCIPIO del mensaje; usa ~/Compartido (enlace sin espacios, se resuelve en casa). El texto y las fichas van detrás,
    // y Hermes la quita del mensaje guardado. Solo Fran (una invitada no ve el disco del servidor). La miniatura sigue en «[Imagen adjunta: …]».
    const foto = !guest && adj.find(a => a.imagen)
    const cabecera = foto ? [`"~/Compartido/Adjuntos/${foto.name}"`] : []
    const completo = [...cabecera, text || 'Te adjunto esto.', ...refs].join('\n')
    const guardado = adj
    setDraft(''); setAdj([]); onSent()
    chat.send(completo).catch(e => { setDraft(text); setAdj(guardado); toast(`No se pudo enviar: ${(e as Error).message}`) })   // devolver lo escrito y los adjuntos
  }

  sendRef.current = send

  async function dictate() {
    if (rec.current) { if (rec.current.state !== 'inactive') rec.current.stop(); return }   // segundo toque: parar y transcribir
    if (transcribiendo) return
    if (micEstado === 'denied') { setGuiaMic(true); return }
    // en la app, primero el permiso del sistema; si dice que no, se distingue «bloqueado» (guía con los pasos de aquí) de «cerraste la pregunta»
    const p = await pedirMedio('microfono')
    if (!p.stream) {
      toast(mensajePedido('microfono', p))
      if (p.estado === 'denied') { ponMic('denied'); setGuiaMic(true) }
      return
    }
    const stream = p.stream
    const r = new MediaRecorder(stream)
    const trozos: Blob[] = []
    const tope = setTimeout(() => { if (r.state !== 'inactive') r.stop() }, MAX_DICTADO_MS)
    r.ondataavailable = e => { if (e.data.size) trozos.push(e.data) }
    r.onstop = async () => {
      clearTimeout(tope); stream.getTracks().forEach(t => t.stop())
      rec.current = null; setListening(false)
      const audio = new Blob(trozos, { type: r.mimeType || 'audio/webm' })
      if (!audio.size) return
      setTranscribiendo(true)
      try {
        const { texto } = await api<{ texto: string }>('/api/dictado', { method: 'POST', headers: { 'Content-Type': audio.type }, body: audio })
        if (!texto) { toast('No he entendido nada; prueba a hablar más cerca del micrófono'); return }
        const d = draftRef.current
        change(`${d}${d && !/\s$/.test(d) ? ' ' : ''}${texto}`); alFinal()   // al cuadro, para revisarlo antes de enviar
      } catch (e) { toast(`No se pudo transcribir: ${(e as Error).message}`) } finally { setTranscribiendo(false) }
    }
    rec.current = r; setListening(true); r.start()
    void api('/api/dictado/calentar', { method: 'POST' }).catch(() => { })   // el servidor carga el modelo mientras hablas: al parar ya está listo
  }

  /** Micro: tocar y soltar enseguida empieza a grabar (otro toque para); mantener pulsado graba mientras dure y, al soltar, pasa a texto.
   *  El «click» del teclado (detail 0) sigue funcionando como siempre. */
  const micAbajo = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* sin captura, soltar fuera del botón no se vería */ }
    if (rec.current) { void dictate(); return }   // ya grabando: este toque la para
    pulsado.current = Date.now(); void dictate()
  }
  const micArriba = () => {
    const t = pulsado.current; pulsado.current = 0
    if (t && rec.current && rec.current.state !== 'inactive' && Date.now() - t > 450) rec.current.stop()
  }

  const vacio = !draft.trim() && !adj.length
  const quien = nombreAsistente(guest, name)   // Fran habla con Zazu; una invitada, con su asistente (por defecto Zazu)
  const conMas = canAttach && !guest && !sinMas   // en el chat con un asistente de un oficio no hay acciones rápidas (irían a Zazu)
  const parando = chat.vivo?.estado === 'parando'
  const aprob = chat.vivo?.aprobacion
  const fuera = useFueraDeVista(aprob?.id)
  const revisar = () => {
    const el = document.querySelector<HTMLElement>(`[data-aprob="${CSS.escape(aprob?.id || '')}"]`)
    el?.querySelector<HTMLElement>('pre')?.focus({ preventScroll: true })   // primero el comando entero; los botones van después con Tab
    el?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' })
  }
  return <div className={`composer-area ${arrastrando ? 'drag' : ''} ${soloLectura ? 'bloqueado' : ''} ${conMas ? 'con-mas' : ''} ${centrado ? 'centrado' : ''}`}>
    {aprob && fuera && <div className="hz-minibarra" role="status"><span className="hz-minibarra-punto" aria-hidden="true" /><span>Zazu necesita tu permiso</span>
      <button type="button" className="hz-chip" onClick={revisar}>Revisar</button></div>}
    {(adj.length > 0 || subiendo > 0) && <div className="adjuntos" aria-label="Archivos adjuntos">
      {adj.map((a, i) => <div className="adjunto" key={`${a.name}${i}`}>
        {a.vista ? <img src={a.vista} alt="" /> : <span className="adjunto-ic"><Icon name="file" size={20} /></span>}
        <span className="adjunto-nombre">{a.name}</span>
        <button type="button" onClick={() => quitar(i)} aria-label={`Quitar ${a.name}`}><Icon name="close" size={14} /></button></div>)}
      {subiendo > 0 && <div className="adjunto subiendo" role="status">Subiendo…</div>}
    </div>}
    {arrastrando && <div className="soltar" role="status">Suelta aquí para adjuntar</div>}
    {guiaMic && <GuiaPermiso tipo="microfono" toast={toast} cerrar={() => setGuiaMic(false)} />}
    {(listening || transcribiendo) && <div className="hz-minibarra" role="status"><span className="hz-minibarra-punto" aria-hidden="true" /><span>{listening ? 'Te escucho… suelta o toca el micro para terminar' : 'Pasando tu voz a texto…'}</span></div>}
    {conMas && <div className="mas-wrap" ref={masRef}>
      {mas && <div className="mas-menu" role="menu" aria-label="Más acciones">
        {MAS.map(q => <button key={q.title} type="button" role="menuitem" onClick={() => elegir(q)}>
          <span className={`mas-ic ${q.tone}`}><Icon name={q.icon} size={18} /></span><span className="mas-txt"><strong>{q.title}</strong><small>{q.subtitle}</small></span></button>)}
        <button type="button" role="menuitem" className="mas-pegar" onClick={() => { setMas(false); foto.current?.click() }}><span className="mas-ic butter"><Icon name="camera" size={18} /></span><span className="mas-txt"><strong>Hacer una foto</strong><small>Con la cámara, para enseñársela a Zazu</small></span></button>
        <button type="button" role="menuitem" className="mas-pegar" onClick={() => void pegar()}><span className="mas-ic butter"><Pegar /></span><span className="mas-txt"><strong>Pegar</strong><small>Texto o imagen del portapapeles</small></span></button>
      </div>}
    </div>}
    <form className="composer" onSubmit={e => { e.preventDefault(); send() }}>
      {/* 2026-10-22, como en las apps de chat: una caja redondeada y elevada; arriba el texto (crece al escribir) y abajo, en una fila,
          «+» (recordatorio, nota, foto…), el clip, y a la derecha el micro y el botón redondo de enviar (o «Parar» mientras responde) */}
      <div className="composer-campo">
        <textarea ref={area} rows={1} value={draft} onChange={e => change(e.target.value)} disabled={soloLectura}
          placeholder={soloLectura ? 'Sigue en WhatsApp' : placeholder || `Pregúntale a ${quien}…`} aria-label={`Escribe un mensaje a ${quien}`} enterKeyHint="send"
          onPaste={e => { const fs = Array.from(e.clipboardData.files || []); if (canAttach && fs.length && !e.clipboardData.getData('text/plain')) { e.preventDefault(); void attachMany(fs) } }}
          onKeyDown={e => { shift.current = e.shiftKey; if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} onKeyUp={e => { shift.current = e.shiftKey }} />
        <input ref={file} type="file" multiple className="visually-hidden" onChange={e => { void attachMany(Array.from(e.target.files || [])); e.target.value = '' }} aria-label="Seleccionar archivos" />
        {(conMas || (guest && canAttach)) && <input ref={foto} type="file" accept="image/*" capture="environment" className="visually-hidden" tabIndex={-1} aria-hidden="true" onChange={e => { void attachMany(Array.from(e.target.files || [])); e.target.value = '' }} />}
      </div>
      <div className="composer-pie">
        {conMas && <button type="button" className={`composer-tool mas-btn ${mas ? 'on' : ''}`} disabled={soloLectura} onClick={() => setMas(!mas)} aria-expanded={mas} aria-haspopup="menu" aria-label="Más: recordatorio, nota, evento, foto…" title="Más"><Icon name="plus" size={20} /></button>}
        {canAttach && <button type="button" className="composer-tool" disabled={soloLectura} onClick={() => file.current?.click()} aria-label="Adjuntar archivo o foto" title="Adjuntar"><Icon name="paperclip" size={19} /></button>}
        {guest && canAttach && <button type="button" className="composer-tool" disabled={soloLectura} onClick={() => foto.current?.click()} aria-label="Hacer una foto para preguntarle" title="Cámara"><Icon name="camera" size={19} /></button>}
        {canAttach && !conMas && <button type="button" className="composer-tool pegar-btn" disabled={soloLectura} onClick={() => void pegar()} aria-label="Pegar del portapapeles (texto o imagen)" title="Pegar"><Pegar /></button>}
        <span className="composer-hueco" />
        {PUEDE_DICTAR && !soloLectura && !microApagado() && <button type="button" className={`composer-tool micro ${listening ? 'live' : ''}`} onPointerDown={micAbajo} onPointerUp={micArriba} onPointerCancel={micArriba} onContextMenu={e => e.preventDefault()}
          onClick={e => { if (e.detail === 0) void dictate() }} disabled={transcribiendo} style={{ touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none' }}
          aria-label={transcribiendo ? 'Transcribiendo lo que has dicho…' : listening ? 'Parar y pasar a texto' : micEstado === 'denied' ? 'Micrófono bloqueado: ver cómo activarlo' : 'Dictar mensaje'} title={transcribiendo ? 'Transcribiendo…' : listening ? 'Parar' : micEstado === 'denied' ? 'Micrófono bloqueado' : 'Dictar: toca para grabar y toca otra vez para parar, o mantén pulsado y suelta'} aria-pressed={listening}><Icon name="mic" size={20} /></button>}
        {chat.pending && vacio
          ? <button type="button" className="send-button parar" disabled={parando} onClick={() => void chat.parar()} aria-label={parando ? 'Parando la respuesta' : 'Parar la respuesta'} title="Parar"><Cuadrado /></button>
          : <button type="submit" className="send-button" disabled={soloLectura || vacio || subiendo > 0 || listening || transcribiendo} aria-label="Enviar mensaje" title="Enviar"><Icon name="arrowUp" size={20} strokeWidth={2.2} /></button>}
      </div>
    </form></div>
}

/** ¿La tarjeta de permiso está fuera de la vista? (para avisar encima del cuadro de escribir) */
function useFueraDeVista(id?: string): boolean {
  const [fuera, setFuera] = useState(false)
  useEffect(() => {
    setFuera(false)
    if (!id || typeof IntersectionObserver === 'undefined') return
    let io: IntersectionObserver | null = null, el: Element | null = null
    const t = setInterval(() => {   // la tarjeta puede pintarse después, o desaparecer y volver (otra pantalla)
      if (el?.isConnected) return
      io?.disconnect(); io = null; setFuera(false)
      el = document.querySelector(`[data-aprob="${CSS.escape(id)}"]`)
      if (!el) return
      io = new IntersectionObserver(([e]) => setFuera(!e.isIntersecting), { threshold: 0.3 })
      io.observe(el)
    }, 700)
    return () => { clearInterval(t); io?.disconnect() }
  }, [id])
  return fuera
}
