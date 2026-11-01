import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { deHermes } from '../lib'
import type { Aprobacion, Decision } from '../tipos'
import { useAhora } from './api'

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const miles = (n: number) => n.toLocaleString('es-ES')

/** Lo que podría esconder algo en el comando: varias líneas en blanco seguidas, espacios largos (no la sangría normal)
 *  y caracteres invisibles o de control (incluidos los que cambian el orden del texto). */
const RAROS = /\n(?:[ \t]*\n){2,}|[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]{10,}|[\0-\x08\x0b-\x1f\x7f-\x9f\xad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb\u{e0000}-\u{e007f}]/gu

/** El comando entero, con lo raro convertido en marcas que se ven: «⏎×60» (líneas en blanco), «␠×4100» (espacios), «U+202E». */
export function comandoVisible(c: string): { partes: ReactNode[]; marcas: number } {
  const partes: ReactNode[] = []
  let i = 0, marcas = 0, m: RegExpExecArray | null
  const marca = (vista: string, dicho: string) => {
    marcas++
    partes.push(<span key={`t${partes.length}`} className="hz-tok" title={dicho}><span aria-hidden="true">{vista}</span><span className="visually-hidden">{` (${dicho}) `}</span></span>)
  }
  RAROS.lastIndex = 0
  while ((m = RAROS.exec(c))) {
    const t = m[0], n = [...t].length
    const tipo = t[0] === '\n' ? 'blancas' : n >= 10 ? 'espacios' : 'invisible'
    if (tipo === 'espacios' && (m.index === 0 || c[m.index - 1] === '\n') && n <= 32 && /^[ \t]+$/.test(t)) continue   // sangría normal de un script
    partes.push(c.slice(i, m.index))
    if (tipo === 'blancas') { const b = t.split('\n').length - 2; partes.push('\n'); marca(`⏎×${b}`, `${b} líneas en blanco`); partes.push('\n') }
    else if (tipo === 'espacios') marca(`␠×${n}`, `${n} espacios seguidos`)
    else { const cp = (t.codePointAt(0) || 0).toString(16).toUpperCase().padStart(4, '0'); marca(`U+${cp}`, `carácter invisible U+${cp}`) }
    i = m.index + t.length
  }
  partes.push(c.slice(i))
  return { partes, marcas }
}

/** Tarjeta «Zazu necesita tu permiso»: qué quiere hacer, el comando ENTERO y Aprobar / No
 *  (y «Sí, durante esta respuesta» si se ofrece). «Siempre» nunca se da desde la app.
 *  Nada queda escondido: sin alto máximo (los botones van siempre después del final), líneas en blanco y espacios largos
 *  se ven como marcas y se cuentan las líneas. Si el hub no pudo enseñarlo entero (`recorte`), lo dice y solo deja «No».
 *  Sin el código de este trabajo (otro navegador) los botones quedan desactivados. */
export default function TarjetaAprobacion({ a, puedeAprobar, onDecidir }: { a: Aprobacion; puedeAprobar: boolean; onDecidir(d: Decision): void }) {
  const ahora = useAhora()
  const [enviada, setEnviada] = useState<Decision | null>(null)
  useEffect(() => { setEnviada(null) }, [a.id])
  useEffect(() => { if (!enviada) return; const t = setTimeout(() => setEnviada(null), 8000); return () => clearTimeout(t) }, [enviada])   // si no llega respuesta, se puede volver a intentar
  const quedan = Math.max(0, Math.round(a.expira - ahora / 1000))
  const caducada = quedan <= 0
  const quieto = !puedeAprobar || caducada || !!enviada
  const cortado = (a.recorte || 0) > 0
  const decidir = (d: Decision) => { if (quieto || (cortado && d !== 'deny')) return; setEnviada(d); onDecidir(d) }
  const hasta = new Date(a.expira * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
  const tid = `hz-aprob-${a.id}`
  const { partes, marcas } = comandoVisible(a.comando)
  const lineas = a.lineas || a.comando.split('\n').length
  return <section className={`hz-aprob ${caducada ? 'caducada' : ''} ${quedan <= 30 ? 'urge' : ''}`} data-aprob={a.id} aria-labelledby={tid}>
    <div className="hz-aprob-top">
      <strong id={tid}>Zazu necesita tu permiso</strong>
      <span className="hz-aprob-reloj"><span aria-hidden="true">{caducada ? 'Caducó' : mmss(quedan)}</span><span className="visually-hidden">{caducada ? 'Caducó' : `Caduca a las ${hasta}`}</span></span>
    </div>
    <p className="hz-aprob-tit">{deHermes(a.titulo)}</p>
    {a.motivo && <p className="hz-aprob-motivo">Motivo: {deHermes(a.motivo)}</p>}
    <p className="hz-aprob-meta">{cortado ? 'Comando (no cabe entero)' : 'Comando completo'} · {miles(lineas)} {lineas === 1 ? 'línea' : 'líneas'}{marcas > 0 ? ' · ⏎ = líneas en blanco, ␠ = espacios' : ''}</p>
    <pre className="hz-aprob-cmd" tabIndex={0} aria-label={`${cortado ? 'Comando, sin el final' : 'Comando completo'}, ${lineas} ${lineas === 1 ? 'línea' : 'líneas'}`}>{partes}{cortado && <span className="hz-tok hz-tok-corte">{`… faltan ${miles(a.recorte || 0)} caracteres que no se pueden enseñar`}</span>}</pre>
    {cortado && <p className="hz-aprob-nota hz-aprob-aviso" role="note">Es demasiado largo para enseñártelo entero, así que no se puede aprobar: solo «No». Pídele a Zazu que lo divida en pasos más cortos.</p>}
    {a.inteligente && <p className="hz-aprob-nota">El revisor automático lo rechazó; decides tú.</p>}
    {!puedeAprobar && !caducada && <p className="hz-aprob-nota">Empezado en otro dispositivo. Aprueba desde el móvil o el ordenador donde lo pediste, o desde la notificación.</p>}
    {caducada ? <p className="hz-aprob-nota">Nadie respondió a tiempo: Zazu lo da por denegado.</p>
      : <div className="hz-aprob-botones">
        {(a.opciones.includes('once') || cortado) && <button type="button" className="hz-btn hz-btn-si" disabled={quieto || cortado} onClick={() => decidir('once')}>{enviada === 'once' ? 'Aprobando…' : 'Aprobar'}</button>}
        {a.opciones.includes('deny') && <button type="button" className="hz-btn hz-btn-no" disabled={quieto} onClick={() => decidir('deny')}>{enviada === 'deny' ? 'Denegando…' : 'No'}</button>}
        {a.opciones.includes('session') && !cortado && <button type="button" className="hz-btn hz-btn-sesion" disabled={quieto} onClick={() => decidir('session')}>{enviada === 'session' ? 'Aprobando…' : 'Sí, durante esta respuesta'}</button>}
      </div>}
  </section>
}
