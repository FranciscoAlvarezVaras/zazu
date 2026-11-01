import { useEffect, useState } from 'react'
import { api, post } from '../lib'

type Permiso = { id: string; que: string; creada: number }

/** Solo invitadas de nivel Familia: lo que su Zazu espera que permita (también le llega como aviso al móvil).
 *  Mira cada 3 s mientras la app está a la vista; sin su «Permitir», no se hace nada. */
export default function PermisosInvitada({ nombre, toast }: { nombre: string; toast: (m: string) => void }) {
  const [lista, setLista] = useState<Permiso[]>([])
  const [busy, setBusy] = useState('')
  useEffect(() => {
    let vivo = true
    const mirar = () => { if (document.visibilityState === 'visible') api<{ pendientes: Permiso[] }>('/api/aprobaciones').then(d => { if (vivo) setLista(d.pendientes) }).catch(() => {}) }
    mirar()
    const t = setInterval(mirar, 3000)
    document.addEventListener('visibilitychange', mirar)
    return () => { vivo = false; clearInterval(t); document.removeEventListener('visibilitychange', mirar) }
  }, [])
  async function responder(p: Permiso, decision: 'si' | 'no') {
    setBusy(p.id)
    try { await post('/api/aprobaciones', { id: p.id, decision }); toast(decision === 'si' ? 'Permitido' : 'Rechazado') }
    catch (e) { toast(`No se pudo: ${(e as Error).message}`) }
    finally { setBusy(''); setLista(l => l.filter(x => x.id !== p.id)) }
  }
  // desde otra pestaña del navegador no se ve la tarjeta: el título avisa (y vuelve al suyo al responder)
  useEffect(() => {
    if (!lista.length) return
    const antes = document.title
    let on = false
    const t = setInterval(() => { on = !on; document.title = on ? `🔔 ${nombre} necesita tu permiso` : antes }, 1200)
    return () => { clearInterval(t); document.title = antes }
  }, [lista.length, nombre])
  if (!lista.length) return null
  return <div className="hz-aprob" role="alertdialog" aria-label="Permisos pendientes" style={{ position: 'fixed', left: 16, right: 16, bottom: 88, zIndex: 60, maxWidth: 520, margin: '0 auto' }}>
    {lista.map(p => <div className="acc-card" key={p.id} style={{ boxShadow: '0 8px 30px rgba(0,0,0,.25)' }}>
      <strong>{nombre} necesita tu permiso</strong>
      <p style={{ margin: '6px 0 10px' }}>{p.que}</p>
      <div className="actions">
        <button className="btn-secondary" disabled={busy === p.id} onClick={() => void responder(p, 'no')}>Rechazar</button>
        <button className="btn-primary" disabled={busy === p.id} onClick={() => void responder(p, 'si')}>Permitir</button>
      </div></div>)}
  </div>
}
