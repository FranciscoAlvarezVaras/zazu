/* La SIGUIENTE ACCIÓN de cada cosa, dicha en lenguaje normal («Preparar el pago», «Preparar la carta», «Buscar opciones»).
   Ninguna escribe nada por su cuenta: abren el chat con Zazu con la petición ya escrita para que Fran la mande (o la cambie). */
export type Accion = { texto: string; peticion: string }

/** «Ordenar todo con Zazu»: se manda ya, al chat de Zazu (con permisos dentro del chat). Zazu solo PROPONE; no toca nada hasta que Fran diga que sí. */
/** «Organizar mi agenda»: va al chat con esta marca delante; la app no enseña la orden, solo «📅 Organizar mi agenda» y la respuesta. */
export const MARCA_ORGANIZAR = '[[organizar-agenda]]'
export const organizarAgenda = (invitada: boolean) => `${MARCA_ORGANIZAR}\n` + (invitada
  ? 'Organiza mi agenda: mira mis citas y tareas de hoy y de los próximos 7 días (si tengo Google conectado), las tareas sin fecha o vencidas y mis recordatorios. Propón en una lista corta cómo repartirlo y qué mover o quitar, y espera mi OK antes de apuntar o cambiar nada.'
  : 'Organiza mi agenda: mira mis citas y tareas de hoy y de los próximos 7 días, las tareas sin fecha o vencidas, los papeles por archivar, las notas de la bandeja del Cerebro y las suscripciones que quiero cancelar. Propón en una lista corta qué cambiar y espera mi OK antes de tocar nada.')
export const ORDENA_TODO = 'Ordena todo: revisa mis tareas sin fecha o vencidas, los papeles por archivar, las notas de la bandeja del Cerebro y las suscripciones que quiero cancelar. Dime en una lista qué propones cambiar y espera mi OK antes de tocar nada.'

const REGLAS: { re: RegExp; texto: string; peticion: (t: string) => string }[] = [
  { re: /\b(pagar|pago|cuota|recibo|factura|abonar|transferencia|domiciliaci[oó]n)\b/i, texto: 'Preparar el pago',
    peticion: t => `Ayúdame a preparar esto: «${t}». Dime qué datos hacen falta y cómo se paga. No pagues nada tú.` },
  { re: /\b(aplicar|candidatura|carta|solicitud|postular|inscrib\w+|apuntarme)\b/i, texto: 'Preparar la carta',
    peticion: t => `Prepárame la carta de presentación para: «${t}». Usa mi CV y dime qué te falta.` },
  { re: /\b(alquilar|comprar|buscar|reservar|billete|tren|vuelo|hotel|encargar)\b/i, texto: 'Buscar opciones',
    peticion: t => `Búscame opciones para: «${t}». Dime precios y enlaces, y no compres nada.` },
  { re: /\b(llamar|escribir|mandar|enviar|contestar|responder|avisar)\b/i, texto: 'Preparar el mensaje',
    peticion: t => `Prepárame el mensaje para: «${t}». Déjamelo escrito y no lo envíes.` },
]

export function accionDeTarea(titulo: string): Accion {
  const t = titulo.trim()
  const r = REGLAS.find(x => x.re.test(t))
  return r ? { texto: r.texto, peticion: r.peticion(t) } : { texto: 'Pedir ayuda', peticion: `Ayúdame con esta tarea: «${t}». Dime los pasos y qué necesitas de mí.` }
}

/** «Planifícame el día» (Agenda › Semana): Zazu reparte las tareas pendientes en los huecos libres del calendario y espera el OK. */
export const PLANIFICA_DIA = 'Planifícame el día de hoy: mira mi agenda de hoy en las dos cuentas y mis tareas pendientes (las vencidas y las de hoy), y propón a qué hora hago cada una en los huecos libres, en una lista corta con horas. Espera mi OK antes de crear nada en el calendario.'
