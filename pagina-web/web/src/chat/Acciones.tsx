import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { post, vistaPrevia } from '../lib'

const svg = (d: ReactNode) => <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
const COPIAR = svg(<><rect x="8.5" y="8.5" width="11" height="11" rx="2.2" /><path d="M15.5 8.5V6.2a1.7 1.7 0 0 0-1.7-1.7H6.2a1.7 1.7 0 0 0-1.7 1.7v7.6a1.7 1.7 0 0 0 1.7 1.7h2.3" /></>)
const HECHO = svg(<path d="m5 12 4.5 4.5L19 7" />)
const REPETIR = svg(<><path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5" /><path d="M20 4v4.5h-4.5" /><path d="M20 12a8 8 0 0 1-13.7 5.6L4 15.5" /><path d="M4 20v-4.5h4.5" /></>)
const CEREBRO = svg(<><path d="M6 3.5h12a1 1 0 0 1 1 1v16l-7-4.2-7 4.2v-16a1 1 0 0 1 1-1Z" /><path d="M12 7.5v6M9 10.5h6" /></>)

/** Copiar al portapapeles (y, si el navegador no deja, a la antigua). También lo usan los bloques de código de las respuestas. */
export async function copiar(t: string) {
  try { await navigator.clipboard.writeText(t); return }
  catch { /* sin permiso o sin https: a la antigua */ }
  const a = document.createElement('textarea')
  a.value = t; a.setAttribute('readonly', ''); a.style.position = 'fixed'; a.style.opacity = '0'
  document.body.appendChild(a); a.select()
  const ok = document.execCommand('copy')
  a.remove()
  if (!ok) throw new Error('no se pudo')
}

/** Debajo de cada respuesta terminada: Copiar, Guardar en el Cerebro (invitadas: solo Copiar) y, en la última, Repetir (vuelve a mandar tu último mensaje). */
export default function Acciones({ texto, guest, toast, repetir }: { texto: string; guest?: boolean; toast: (m: string) => void; repetir?: () => void }) {
  const [copiado, setCopiado] = useState(false)
  const [haciendo, setHaciendo] = useState<'' | 'nota'>('')
  useEffect(() => { if (!copiado) return; const t = setTimeout(() => setCopiado(false), 2000); return () => clearTimeout(t) }, [copiado])
  const limpio = () => vistaPrevia(texto).trim()   // «MEDIA:/ruta/billete.pdf» → «📎 billete.pdf»

  const alPortapapeles = async () => {
    try { await copiar(limpio()); setCopiado(true) } catch { toast('El navegador no deja copiar aquí. Mantén pulsado el texto y elige «Copiar».') }
  }
  const alCerebro = async () => {
    setHaciendo('nota')
    try { const r = await post<{ ok?: boolean; mensaje?: string }>('/api/nota', { texto: texto.trim().slice(0, 20000) }); toast(r.mensaje || 'Guardado en tu Cerebro') }
    catch (e) { toast(`No se pudo guardar en el Cerebro: ${(e as Error).message}`) }
    finally { setHaciendo('') }
  }

  return <div className="acciones" role="group" aria-label="Acciones de la respuesta">
    <button type="button" onClick={() => void alPortapapeles()} aria-label={copiado ? 'Copiado' : 'Copiar la respuesta'} title="Copiar">{copiado ? HECHO : COPIAR}<span className="acc-txt">{copiado ? 'Copiado' : 'Copiar'}</span></button>
    {!guest && <>
      <button type="button" onClick={() => void alCerebro()} disabled={!!haciendo} aria-busy={haciendo === 'nota'} aria-label="Guardar la respuesta en el Cerebro" title="Guardar en el Cerebro">{CEREBRO}<span className="acc-txt">{haciendo === 'nota' ? 'Guardando…' : 'Guardar en el Cerebro'}</span></button>
    </>}
    {repetir && <button type="button" onClick={repetir} aria-label="Repetir: volver a pedir la respuesta" title="Repetir">{REPETIR}<span className="acc-txt">Repetir</span></button>}
    <span className="visually-hidden" role="status" aria-live="polite">{copiado ? 'Copiado' : ''}</span>
  </div>
}
