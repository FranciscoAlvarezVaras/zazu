import { greeting, nombreAsistente } from '../lib'
import { PROFILE_HINTS, PROFILE_NAMES } from '../data'
import { esEstilo } from '../tipos'
import type { Me } from '../screens/Invitada'
import { useEffect, useRef } from 'react'

/** La miniatura del saludo: Zazu (el muñeco 3D) saluda con la pata UNA vez al montar la pantalla y se queda quieto en su póster,
 *  que es la misma pose del principio y del final del vídeo. Sin bucle; con «reducir movimiento», solo el póster.
 *  Mismo tamaño y esquinas que el logo que había (58 px, radio 22 %); el vídeo es de 160 px para verse nítido. */
function GatoSaluda({ tam = 58 }: { tam?: number }) {
  const ref = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    const v = ref.current
    if (!v || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    v.muted = true   // React no pone el atributo «muted» y sin él algunos navegadores no dejan arrancar solo
    v.play().catch(() => {})   // si no deja (ahorro de batería), se queda el póster
  }, [])
  return <video ref={ref} className="saludo-logo saludo-video" width={tam} height={tam} poster="/zazu-saludo-mini.webp" muted playsInline preload="metadata"
    disablePictureInPicture role="img" aria-label="Zazu" style={{ flex: 'none', display: 'block', borderRadius: Math.round(tam * 0.22), objectFit: 'cover' }}>
    <source src="/zazu-saludo-mini.webm" type="video/webm" />
    <source src="/zazu-saludo-mini.mp4" type="video/mp4" />
  </video>
}

/** Cabecera del inicio (la conversación vacía). Es el h1 de la pantalla: recibe el foco al llegar aquí. */
export default function Saludo({ me, guest, perfil = 'default' }: { me: Me; guest?: boolean; perfil?: string }) {
  const nombre = me.name?.split(' ')[0] || 'Fran'
  const asistente = nombreAsistente(guest, me.asistente)
  return <div className="saludo">
    <GatoSaluda />
    <h1>{greeting()}, {nombre}</h1>
    <p>{guest ? `Soy ${asistente}. ¿En qué te ayudo hoy?` : '¿En qué te ayudo hoy?'}</p>
    {!guest && esEstilo(perfil) && <small className="saludo-perfil"><b>{PROFILE_NAMES[perfil] || perfil}</b>{PROFILE_HINTS[perfil] ? ` · ${PROFILE_HINTS[perfil]}` : ''}</small>}
  </div>
}
