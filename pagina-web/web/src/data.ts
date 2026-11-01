import type { IconName } from './icons'

export type Quick = { icon: IconName; title: string; subtitle: string; prompt: string; tone: 'peach' | 'lavender' | 'mint' | 'butter'; fill?: boolean; ctx?: string; archivo?: boolean }

/** Acciones rápidas: el prompt se envía tal cual a Zazu (correo solo lectura, nada se envía solo). */
export const QUICK: Quick[] = [
  { icon: 'sun', title: 'Resumen del día', subtitle: 'Urgente, hoy y lo que puede esperar', tone: 'peach',
    prompt: 'Hazme el resumen del día en el orden urgente, hoy, puede esperar: agenda de hoy, tareas pendientes y correos importantes de las dos cuentas (solo lectura). Máximo cinco puntos.', ctx: 'manana' },
  { icon: 'mail', title: 'Correos importantes', subtitle: 'Las dos cuentas, solo lectura', tone: 'lavender',
    prompt: 'Revisa mis correos recientes de las dos cuentas (solo lectura) y dime cuáles son importantes o esperan respuesta. Si hace falta, déjame borradores, sin enviar nada.', ctx: 'correo' },
  { icon: 'calendar', title: 'Agenda', subtitle: 'Hoy y mañana', tone: 'mint',
    prompt: 'Dime mi agenda de hoy y de mañana, con horas exactas, y avísame si hay solapes.', ctx: 'agenda' },
  { icon: 'clock', title: 'Recordatorio', subtitle: 'Te lo apunto con fecha', tone: 'butter', fill: true, prompt: 'Recuérdame ' },
  { icon: 'pen', title: 'Nota rápida', subtitle: 'Apuntar algo al instante', tone: 'lavender', fill: true, prompt: 'Apunta en mis notas: ' },
  { icon: 'lightbulb', title: 'Investigar', subtitle: 'Búsqueda con fuentes', tone: 'mint', fill: true, prompt: 'Investiga y dame un resumen con fuentes sobre: ' },
]

/** Botón «+» del cuadro de escribir: dejan la frase empezada para que la completes. «Guardar archivo» abre además el selector. */
export const MAS: Quick[] = [
  QUICK[3], QUICK[4],
  { icon: 'calendar', title: 'Evento', subtitle: 'Lo añado a tu calendario', tone: 'mint', fill: true, prompt: 'Añade a mi calendario: ' },
  { icon: 'folder', title: 'Guardar archivo', subtitle: 'Lo dejo en tus carpetas', tone: 'peach', fill: true, archivo: true, prompt: 'Guárdalo en mis carpetas' },
  QUICK[5],
]

/** Inicio del chat de Fran: seis sugerencias en 2×3. «fill» deja la frase empezada en el cuadro de escribir. */
export type Sugerencia = { titulo: string; detalle: string; prompt: string; fill?: boolean; ctx?: string }
export const SUGERENCIAS: Sugerencia[] = [
  { titulo: '¿Qué tengo hoy?', detalle: 'Agenda, tareas y correo', prompt: QUICK[0].prompt, ctx: QUICK[0].ctx },   // el detalle se cambia por lo que hay hoy
  { titulo: 'Apunta en mi agenda', detalle: 'Una cita o un recordatorio', prompt: 'Apunta en mi agenda: ', fill: true },
  { titulo: 'Ofertas de empleo', detalle: 'Las mejores nuevas',
    prompt: '¿Qué ofertas de empleo nuevas hay? Mira las del buscador de empleo (la tabla de Empleo) y dime las 5 más interesantes para mí, con enlace.' },
  { titulo: 'Pregúntame lo que quieras', detalle: 'IA, ideas, dudas', prompt: '', fill: true },
]
/** Inicio de una invitada: ideas que valen sin saber nada de ella. «google»: solo si tiene ese servicio conectado. */
export const SUGERENCIAS_INVITADA: (Sugerencia & { google?: string })[] = [
  { titulo: 'Organiza mi día', detalle: 'Un plan claro', prompt: 'Ayúdame a organizar mi día. Pregúntame lo que necesites saber.' },
  { titulo: 'Escribe por mí', detalle: 'Encuentra las palabras', prompt: 'Ayúdame a escribir un mensaje: ', fill: true },
  { titulo: 'Dame ideas', detalle: 'Inspírame un poco', prompt: 'Dame algunas ideas para hoy.' },
  { titulo: '¿Qué tengo mañana?', detalle: 'Tu agenda de mañana', prompt: '¿Qué tengo mañana en mi agenda?', google: 'calendar' },
]
export const PROFILE_NAMES: Record<string, string> = { default: 'Chat de antes', tecnico: 'Zazu', charla: 'Charla ligera', escritor: 'Escritor', investigador: 'Investigador', viajes: 'Zazu Viajes', empleo: 'Zazu Empleo', teorico: 'Profe del teórico', comidas: 'Comidas y compra', dinero: 'Zazu Dinero', papeles: 'Zazu Papeles', compras: 'Zazu Compras', salud: 'Zazu Salud', profe: 'Profe de Spirit', analista: 'Zazu Analista' }
export const PROFILE_HINTS: Record<string, string> = {
  default: 'Correo, agenda, archivos, web y comandos.',
  charla: 'Sin herramientas: gasta ~65 % menos.',
  escritor: 'Redacta y corrige con tu tono.',
  investigador: 'Web y papers con fuentes citadas.',
  viajes: 'Busca, compara y arma itinerarios. No reserva ni paga.',
  empleo: 'Adapta CV y carta a una oferta y ensaya la entrevista. Tú envías.',
  teorico: '10 preguntas tipo test de la DGT al día y lleva tu racha.',
  comidas: 'Menú de la semana y lista de la compra. No compra.',
  dinero: 'Revisa gastos y suscripciones; redacta bajas. Nunca paga ni cancela.',
  papeles: 'Qué caduca y qué trámite toca. No rellena formularios.',
  compras: 'Compara precios y opiniones, y te dice si una web es de fiar. No compra.',
  salud: 'Citas, medicación y qué contarle al médico. No decide nada médico.',
  profe: 'Te explica tu propio código, paso a paso. Solo lee.',
  analista: 'Qué hace de verdad una web, una app o un archivo (REA). Solo lee.',
}
export const MAIL_ADDR: Record<string, string> = { varas: 'cuenta.principal@example.com', alvarez: 'cuenta.secundaria@example.com' }
