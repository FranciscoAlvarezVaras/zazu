import { useEffect, useRef, useState } from 'react'
import { Icon } from '../icons'
import { post, useFetch } from '../lib'

/** «Seguir en WhatsApp»: el traspaso (/handoff) de la conversación. Tu WhatsApp pasa a ESTA conversación y Zazu te resume por dónde ibais.
 *  Va en el menú «⋯» de la conversación (screens/Conversacion.tsx); debe seguir montado mientras se espera el resultado. */
export function SeguirWhatsApp({ session, profile, busy, nombre, toast, className = 'text-link', role, onElegido }: { session: string; profile: string; busy: boolean; nombre: string; toast: (m: string) => void
  className?: string; role?: string; onElegido?: () => void }) {
  const [poll, setPoll] = useState(false)
  const h = useFetch<{ disponible: boolean; estado: string | null; error: string | null }>(`/api/handoff?session=${encodeURIComponent(session)}&profile=${encodeURIComponent(profile)}`, poll ? 2000 : 0)
  const antes = useRef<string | null>(null)
  useEffect(() => {
    const e = h.data?.estado ?? null
    if (poll && antes.current !== e) {
      if (e === 'completed') { setPoll(false); toast(`Listo: ${nombre} te ha escrito por WhatsApp. Sigue allí.`) }
      if (e === 'failed') { setPoll(false); toast(`No se pudo pasar a WhatsApp${h.data?.error ? `: ${h.data.error.slice(0, 120)}` : ''}`) }
    }
    antes.current = e
  }, [h.data?.estado]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!h.data?.disponible) return null
  const enCurso = poll || h.data.estado === 'pending' || h.data.estado === 'running'
  const pasar = async () => {
    onElegido?.()
    if (!confirm(`Tu chat de WhatsApp con ${nombre} pasará a esta conversación y te escribirá allí un resumen. ¿Seguimos?`)) return
    try { await post('/api/handoff', { session, profile }); setPoll(true); toast('Pasando a WhatsApp…') } catch (e) { toast((e as Error).message) }
  }
  return <button type="button" className={className} role={role} disabled={busy || enCurso} onClick={() => void pasar()}><Icon name="volume" size={15} /> {enCurso ? 'Pasando a WhatsApp…' : 'Seguir en WhatsApp'}</button>
}
