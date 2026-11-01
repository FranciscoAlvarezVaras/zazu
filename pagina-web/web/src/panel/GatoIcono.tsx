/* Iconos de gato de Zazu (los dibujó Fran, uno por sección). Son PNG recortados en dos temas:
   /gatos/claro/<n>.png (fondo blanco) y /gatos/oscuro/<n>.png (fondo negro). El tema sale del mismo estado que el resto del panel
   (useTemaPz → <html data-pz-tema>), así cambian al instante al tocar Claro/Oscuro. Si la imagen no carga, se oculta y queda el hueco (no rompe). */
import { useTemaPz } from './tema'

export type Gato = 'agenda' | 'semana' | 'empleo' | 'finanzas' | 'transacciones' | 'ajustes' | 'viajes' | 'soporte' | 'educacion' | 'todo' | 'cara'

export function GatoIcono({ n, size = 22 }: { n: Gato; size?: number }) {
  const [tema] = useTemaPz()
  return <img className="pz-gato" src={`/gatos/${tema}/${n}.png`} width={size} height={size} alt="" aria-hidden="true"
    onError={e => { e.currentTarget.style.visibility = 'hidden' }} />
}
