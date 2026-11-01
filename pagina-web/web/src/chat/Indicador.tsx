/* «Zazu está trabajando»: un engranaje que gira y una palabra que cambia cada pocos segundos (en vez del logo repetido).
   Las palabras son nuestras: se cambian aquí. Con «reducir movimiento» el engranaje queda quieto y la palabra sigue cambiando. */
import { useEffect, useState } from 'react'

const PALABRAS = ['Pensando', 'Revisando', 'Analizando', 'Comparando', 'Ordenando ideas', 'Buscando datos', 'Preparando la respuesta', 'Casi listo']

export function Engranaje({ tam = 18 }: { tam?: number }) {
  return <svg className="zz-engranaje" width={tam} height={tam} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="3.2" />
    <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" />
    <circle cx="12" cy="12" r="6.6" />
  </svg>
}

export default function Indicador({ parando = false, tam = 18 }: { parando?: boolean; tam?: number }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (parando) return
    const t = setInterval(() => setI(n => (n + 1) % PALABRAS.length), 3500)
    return () => clearInterval(t)
  }, [parando])
  return <>
    <span aria-hidden="true" className="pensando-gato"><Engranaje tam={tam} /></span>
    <span className="pensando-txt">{parando ? 'Parando' : PALABRAS[i]}</span>
  </>
}
