import { useEffect, useState } from 'react'

/** Color de la barra del navegador: el de la barra superior de Zazu (claro u oscuro, según el tema elegido) o, en la pantalla de una invitada, el fondo de su piel «Sereno».
 *  (Ya no hay piel oscura de Hermes: todo lo que se ve es Zazu.) */
export function aplicarPiel(panel = false) {
  const raiz = document.documentElement
  if (raiz.dataset.modo) delete raiz.dataset.modo   // restos de la versión anterior
  const fondo = getComputedStyle(raiz).getPropertyValue(panel ? '--pz-barra' : '--ground').trim()   // Fran: el color de la barra de arriba (azul petróleo; en oscuro, el suyo)
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (fondo && meta && meta.content !== fondo) meta.content = fondo
}

export function usePiel(panel = false, tema = '') {
  useEffect(() => aplicarPiel(panel), [panel, tema])
}

/** Pantalla ancha (≥ 900 px): menú lateral fijo en vez de pestañas de abajo. */
export const ANCHO_ESCRITORIO = '(min-width: 900px)'
/** Panel derecho fijo (Agenda, Renuevan, Gasto…): solo en pantallas muy anchas; en medio, esas cosas van debajo. */
export const ANCHO_PANEL = '(min-width: 1100px)'
export function useMedia(q: string): boolean {
  const [si, setSi] = useState(() => typeof matchMedia === 'function' && matchMedia(q).matches)
  useEffect(() => {
    const m = matchMedia(q)
    const f = () => setSi(m.matches)
    f()
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [q])
  return si
}
export const useEscritorio = () => useMedia(ANCHO_ESCRITORIO)
