/* Respuestas rápidas bajo la última respuesta: las que propone el asistente al final de su texto, en su propia línea
   («[[Sí | No | Luego]]», se la quitamos al pintar), o, si termina preguntando algo de sí o no, «Sí» y «No».
   Tocar una la manda como mensaje, sin escribir. */

const RAPIDAS = /\n?[ \t]*\[\[([^\]\n]{1,200})\]\][ \t]*$/
const PREGUNTA_SI_NO = /\b(quieres|apunto|lo hago|creo|borro|quito|mando|sigo|te parece|vale|ok|confirmo|te lo|lo dejo|lo pongo|lo cambio|empezamos|hacemos|lo guardo|lo apunto|lo envío|lo mando)\b/i

/** El texto sin la línea de opciones, y las opciones (máximo 4, cortas). */
export function extraerRapidas(text: string): { texto: string; opciones: string[] } {
  const m = RAPIDAS.exec(text)
  if (m) {
    const opciones = m[1].split('|').map(s => s.trim()).filter(s => s && s.length <= 40).slice(0, 4)
    if (opciones.length) return { texto: text.replace(RAPIDAS, '').trimEnd(), opciones }
  }
  const t = text.trimEnd()
  if (/\?[»")*_]*$/.test(t) && PREGUNTA_SI_NO.test(t.slice(-240))) return { texto: text, opciones: ['Sí', 'No'] }
  return { texto: text, opciones: [] }
}

export default function Rapidas({ opciones, onElegir }: { opciones: string[]; onElegir(o: string): void }) {
  if (!opciones.length) return null
  return <div className="rapidas" role="group" aria-label="Respuestas rápidas">
    {opciones.map(o => <button key={o} type="button" className="rapida" onClick={() => onElegir(o)}>{o}</button>)}
  </div>
}
