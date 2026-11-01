/* Contratos del chat de Zazu (Fase 0, congelados): los cambios pasan por quien integra.
   Por dentro, el chat de Fran usa el motor «Hermes» (perfil «tecnico», por el gateway, con tarjetas de permiso); en pantalla todo es Zazu. */
import type { Session } from './lib'

/** Ruta interna de una conversación (no se ve en pantalla): «hermes» = el motor con permisos (perfil «tecnico»), «zazu» = los perfiles de siempre
 *  (Charla, Escritor… y las conversaciones antiguas, de un solo disparo y sin tarjetas de permiso). El de una conversación es fijo. */
export type Modo = 'zazu' | 'hermes'
export const PERFIL_HERMES = 'tecnico'
export const modoDe = (profile?: string): Modo => profile === PERFIL_HERMES ? 'hermes' : 'zazu'
/** Estilos de Zazu (Charla, Escritor, Investigador…): los perfiles de siempre, menos el motor y los de invitadas (zi…). */
export const esEstilo = (profile?: string) => !!profile && profile !== 'default' && profile !== PERFIL_HERMES && !/^zi/.test(profile)
/** Respuestas que da la app a un permiso. «always» nunca: escribiría la lista global (también para WhatsApp). */
export type Decision = 'once' | 'session' | 'deny'
/** Paso guardado en el historial: llamada a una herramienta y, si llegó, su resultado (emparejados por call_id o por nombre). */
export type Paso = { id?: string; herramienta: string; args: string; cortado?: number; resultado?: string; error?: boolean }
/** Paso en directo de /api/job (el que está en marcha o los últimos 50). */
export type PasoVivo = { n: number; herramienta: string; resumen: string; estado: 'en_curso' | 'ok' | 'error'; ms?: number; desde: number }
/** `comando` llega entero; `lineas` son las del comando completo y `recorte` los caracteres que no se pudieron enseñar
 *  (si hay recorte, el hub solo deja denegar y la tarjeta lo dice). */
export type Aprobacion = { id: string; titulo: string; comando: string; motivo?: string; opciones: Decision[]; expira: number; inteligente: boolean; lineas?: number; recorte?: number }
/** Estado en directo de la respuesta en marcha. `puedeAprobar`: este navegador tiene el código del trabajo.
 *  `estado` «sin_respuesta»: al abrir la conversación, tu último mensaje no tiene respuesta y no hay nada en marcha. */
export type Vivo = { job: string; modo: Modo; estado: string; texto: string; pasos: PasoVivo[]; aprobacion: Aprobacion | null;
  ultima: { id: string; decision: Decision | 'caducado'; cuando: number } | null; puedeAprobar: boolean; error?: string | null }
export type Modelo = { id: string; nombre: string; detalle: string; proveedor: string; proveedor_nombre: string; pago: 'suscripcion' | 'uso'; nota: string; disponible: boolean }
export type Modelos = { activo: boolean; perfil: string; defecto: string; modelos: Modelo[] }
/** `ts`: segundos, para intercalar lo que escribió el asistente por su cuenta; `rutina`: eso mismo (una rutina o un aviso suyo, no una respuesta). */
export type Item = { kind: 'msg'; id: number; role: 'user' | 'assistant'; text: string; time: string; dia?: string; ts?: number; rutina?: string } | { kind: 'work'; id: number; pasos: Paso[] }
/** Lo que un asistente te escribió por su cuenta (/api/hilo → rutinas). */
export type Rutina = { id: string; ts: number; texto: string; nombre?: string }
export type Cur = { id: string | null; profile: string; source?: string; modo: Modo }
/** Al volver a un chat tras un rato sin actividad: la conversación que se iba a reabrir (`desde`: su última actividad, en segundos;
 *  `titulo`: su primer mensaje, por si la lista de conversaciones aún no ha llegado). */
export type PreguntaChat = { contacto: string; sesion: string; profile: string; desde: number; titulo: string }
export interface ChatApi {
  sessions: Session[]; cur: Cur; modo: Modo; soloLectura: boolean; items: Item[]; pending: boolean; profiles: string[]; vivo: Vivo | null
  modelo: string | null; setModelo(id: string | null): void; error: string; clearError(): void; info: string; clearInfo(): void
  open(id: string, profile?: string, source?: string): Promise<void>; newChat(profile?: string): void
  send(text: string, ctx?: string): Promise<void>; aprobar(d: Decision): Promise<void>; parar(): Promise<void>; reload(): Promise<void>
  /** Vuelve a mandar tu último mensaje de la conversación (tras una respuesta parada, fallida o que no llegó). */
  reintentar(): Promise<void>
  /** Chat seguido abierto («tecnico» = Zazu, «whatsapp», o un asistente: viajes, empleo…); null si es una conversación suelta. */
  contacto: string | null
  /** Lo dicho en las conversaciones anteriores de ese chat (se ve encima de la actual, en el mismo hilo). */
  anteriores: Item[]
  /** Lo que ese asistente te escribió por su cuenta (rutinas y avisos), para intercalar en el hilo por fecha. */
  rutinas: Rutina[]
  /** Abre el chat seguido con ese contacto: su última conversación si es reciente (o de WhatsApp, solo lectura); si no, una nueva con las anteriores encima. */
  abrirContacto(id: string, o?: { preguntar?: boolean }): Promise<void>
  /** «¿Seguimos con la anterior o empiezas una nueva?»: la abrió abrirContacto({ preguntar }) y llevaba más de 30 min parada. */
  pregunta: PreguntaChat | null
  cerrarPregunta(): void
}
