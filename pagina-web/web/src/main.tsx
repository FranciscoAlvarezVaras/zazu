import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/dm-sans/400.css'
import '@fontsource/dm-sans/500.css'
import '@fontsource/dm-sans/600.css'
import '@fontsource/dm-sans/700.css'
import '@fontsource/plus-jakarta-sans/500.css'
import '@fontsource/plus-jakarta-sans/600.css'
import '@fontsource/plus-jakarta-sans/700.css'
import '@fontsource/plus-jakarta-sans/800.css'
import '@fontsource/instrument-serif/400.css'
import '@fontsource/instrument-serif/400-italic.css'
// 2026-10-22, chat «de lectura»: Inter para la interfaz y Source Serif 4 para leer las respuestas de Zazu (libres, OFL)
import '@fontsource-variable/inter/index.css'
import '@fontsource/source-serif-4/400.css'
import '@fontsource/source-serif-4/400-italic.css'
import '@fontsource/source-serif-4/600.css'
import './design.css'
import './theme.css'
import './tokens.css'   // fichas de color y tipografía (piel «Sereno»)
import './shell.css'    // cabecera, cajón y panel lateral
import App from './App'

// el aviso de «instalar app» puede llegar antes de que exista la pantalla de bienvenida: se guarda aquí
addEventListener('beforeinstallprompt', e => { e.preventDefault(); (window as unknown as { zazuInstalar?: Event }).zazuInstalar = e })

/** Si algo se rompe al pintar, un aviso con «Recargar» en vez de la pantalla en blanco. */
class Red extends React.Component<{ children: React.ReactNode }, { roto: boolean }> {
  state = { roto: false }
  static getDerivedStateFromError() { return { roto: true } }
  componentDidCatch(e: unknown) { console.error(e) }
  render() {
    return this.state.roto ? <div className="boot" role="alert"><p>Algo ha fallado al mostrar esta pantalla. Recarga para seguir.</p>
      <button className="btn-primary" onClick={() => location.reload()}>Recargar</button></div> : this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Red><App /></Red></React.StrictMode>)
if ('serviceWorker' in navigator && /ZazuApp/.test(navigator.userAgent)) {
  // dentro de la app no hay service worker: cada vez se baja la página del servidor, así que nunca hay una copia vieja. Si había uno de antes, se quita.
  navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => void r.unregister())).catch(() => { })
  if ('caches' in window) caches.keys().then(ks => ks.forEach(k => { if (k !== 'compartidos') void caches.delete(k) })).catch(() => { })
} else if ('serviceWorker' in navigator) {
  // versión nueva publicada: cuando el service worker nuevo toma el control, la app se recarga (en cuanto dejes de mirarla)
  // para no seguir con pantallas viejas. En la primera instalación no hay nada que recargar.
  let habia = !!navigator.serviceWorker.controller
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!habia) { habia = true; return }
    if (document.hidden) location.reload()
    else document.addEventListener('visibilitychange', () => { if (document.hidden) location.reload() }, { once: true })
  })
  // una app abierta de fondo no vuelve a pedir su service worker sola: se le pregunta si hay versión nueva cada vez que se vuelve a ella y cada media hora
  navigator.serviceWorker.register('/sw.js').then(reg => {
    const comprobar = () => { if (!document.hidden) reg.update().catch(() => { }) }
    document.addEventListener('visibilitychange', comprobar)
    setInterval(comprobar, 30 * 60 * 1000)
  }).catch(() => { })
}
