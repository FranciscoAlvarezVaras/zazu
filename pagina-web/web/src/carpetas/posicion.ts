import type { Medio, Orden } from './nube'

/* Dónde va cada foto en la lista paginada de la Galería. Sin React ni navegador: lo prueba posicion.test.ts (node --test web/src/carpetas/posicion.test.ts). */
/** El mismo orden que el servidor (server.py, _mas_nuevo): por fecha y, el mismo día, por ruta (todas las fotos de un día comparten fecha: la del nombre). Por peso, y a igualdad, como «nuevas». */
const nuevas = (a: Medio, b: Medio) => b.mtime - a.mtime || (a.path < b.path ? 1 : a.path > b.path ? -1 : 0)
export const porOrden = (o: Orden) => o === 'antiguas' ? (a: Medio, b: Medio) => nuevas(b, a) : o === 'tamano' ? (a: Medio, b: Medio) => b.size - a.size || nuevas(a, b) : nuevas
export const enFavoritos = (consulta: string) => /(^|&)fav=1(&|$)/.test(consulta)

/** Mete `ms` en su sitio según el orden. Si aún faltan por cargar, una que no estaba y iría después de la última que hay no se mete (saldría en medio de otras y descolocaría las páginas): la traerá la paginación, en su sitio.
 *  `estuvo`: las que ya estaban en la lista y salieron (papelera, álbum…); esas vuelven siempre, aunque sean las últimas. */
export function colocar(actual: Medio[], ms: Medio[], orden: Orden, faltan: boolean, estuvo: (path: string) => boolean = () => false) {
  const lista = [...actual], puestos: Medio[] = [], va = porOrden(orden)
  for (const m of ms) {
    if (lista.some(x => x.path === m.path)) continue
    const j = lista.findIndex(x => va(m, x) < 0)
    if (j < 0 && faltan && !estuvo(m.path)) continue
    lista.splice(j < 0 ? lista.length : j, 0, m); puestos.push(m)
  }
  return { lista, puestos }
}

/** Desde dónde se pide la página siguiente: cuántas de las ya cargadas sigue listando el servidor. En Favoritos, lo desmarcado desde el visor aún se ve en pantalla pero el servidor ya no lo lista. */
export const siguienteDesde = (cargadas: Medio[], favoritos: boolean) => cargadas.length - (favoritos ? cargadas.filter(m => !m.fav).length : 0)
