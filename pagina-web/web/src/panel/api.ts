/* ===== Panel de Zazu · TODA la forma de la red está aquí (contrato: docs/contrato-panel.md, rama panel-be) =====
   Las pantallas solo ven los tipos «vista» de abajo; si el servidor cambia, se adapta esta capa y nada más.
   ?demo=1 (solo en la URL, al cargar) sirve datos de ejemplo de ./mock sin tocar la red (el módulo se carga aparte, bajo demanda). */
import { useCallback, useEffect, useRef, useState } from 'react'
import { aLogin, SIN_RED } from '../lib'

/** ?demo=1 se lee una sola vez, al cargar (la app limpia la URL después). Nunca se activa sin ese parámetro. */
export const DEMO = typeof location !== 'undefined' && new URLSearchParams(location.search).get('demo') === '1'
/** Solo en demo: ?demo=1&caso=error|parcial|vacio|lento para ver cada estado. */
export const CASO_DEMO = DEMO ? new URLSearchParams(location.search).get('caso') || '' : ''

/* ---------- transporte ---------- */
export class ErrorApi extends Error {
  constructor(msg: string, public status: number, public cuerpo: any) { super(msg) }
}
type Init = { metodo?: 'GET' | 'POST'; cuerpo?: unknown; signal?: AbortSignal }

async function http<T>(ruta: string, o: Init = {}): Promise<T> {
  if (DEMO) { const m = await import('./mock'); return m.demoHttp<T>(ruta, o) }
  let r: Response
  try {
    r = await fetch(ruta, o.metodo === 'POST'
      ? { method: 'POST', headers: { 'X-Hub': '1', 'Content-Type': 'application/json' }, body: JSON.stringify(o.cuerpo ?? {}), signal: o.signal }
      : { headers: { 'X-Hub': '1' }, signal: o.signal })
  } catch (e) { if ((e as Error)?.name === 'AbortError') throw new ErrorApi('cancelado', -1, null); throw new ErrorApi(SIN_RED, 0, null) }
  if (r.status === 401) { aLogin(); throw new ErrorApi('sesión caducada', 401, null) }
  let cuerpo: any = null
  try { cuerpo = await r.json() } catch { /* sin cuerpo JSON */ }
  if (!r.ok) throw new ErrorApi(typeof cuerpo?.error === 'string' ? cuerpo.error : r.status >= 500 ? 'algo falló; inténtalo otra vez' : `error ${r.status}`, r.status, cuerpo)
  return cuerpo as T
}

/* ---------- utilidades de lectura (el servidor es de fiar, pero un campo raro no tumba la pantalla) ---------- */
const str = (v: unknown, d = '') => typeof v === 'string' ? v : typeof v === 'number' ? String(v) : d
const num = (v: unknown): number | null => typeof v === 'number' && isFinite(v) ? v : null
const arr = (v: unknown): any[] => Array.isArray(v) ? v : []
const strs = (v: unknown) => arr(v).map(x => str(x)).filter(Boolean)
const obj = (v: unknown): any => v && typeof v === 'object' && !Array.isArray(v) ? v : {}

/* ---------- vista: Mi día ---------- */
export type Sec<T> = { ok: true; items: T[]; obsoleto: boolean; parcial: string[]; actualizado: string | null } | { ok: false; error: string }
export type Evento = { id: string; titulo: string; inicio: string; fin: string | null; todoDia: boolean; lugar: string; dia: 'hoy' | 'mañana'; llevar: string[]; tentativo: boolean; cuenta: string }
export type TareaHoy = { id: string; titulo: string; due: string; vencida: boolean; diasRetraso: number; cuenta: string; cuentaEmail: string }
export type Aviso = { id: number; codigo: string; fuente: string; tipo: string; prio: 1 | 2 | 3; titulo: string; detalle: string; borrador: string; enlace: string; chat: string; creado: string; estado: string }
/** Una propuesta del vigía (tarea o evento tentativo sacado de WhatsApp o de un correo). `preparada`: una regla «siempre» la dejó aceptada
 *  (en modo sombra solo significa que se ofrece lista para apuntar con un toque). `sospechosa`: el texto de origen traía frases que parecen órdenes. */
export type Riesgo = 'bajo' | 'medio' | 'alto'
export type Captura = { id: number; fuente: 'wa' | 'correo'; tipo: 'tarea' | 'evento'; titulo: string; detalle: string; due: string | null; hora: string | null; chat: string; accion: string; accionTxt: string; creado: string
  riesgo: Riesgo; sospechosa: boolean; preparada: boolean; regla: 'siempre' | 'nunca' | null; recordable: boolean }
export type Vigia = { id: string; nombre: string; ok: boolean; haceMin: number | null; modo: string | null }
export type Vigias = { pausa: boolean; entregaReal: boolean; items: Vigia[] }
export type Semana = { dias: { d: string; hechas: number; total: number }[]; pct: number }
export type Panel = {
  generado: string; fecha: string; nombre: string
  eventos: Sec<Evento>; tareas: Sec<TareaHoy>; avisos: Sec<Aviso>; capturas: Sec<Captura>
  vigias: { ok: true; v: Vigias } | { ok: false; error: string }
  tareasSinFecha: number | null
  /** El servidor aún no la manda (ver docs): sin ella no se enseña el anillo de la semana. */
  semana: Semana | null
  /** Secciones que esta persona tiene. Una invitada no tiene avisos, capturas ni vigías (son de Fran), ni agenda o tareas si su Google no les dio permiso:
   *  esas llegan vacías (sin error) y las pantallas no las pintan. */
  hay: { eventos: boolean; tareas: boolean; avisos: boolean; capturas: boolean; vigias: boolean }
}

const NOMBRE_VIGIA: Record<string, string> = { wa: 'WhatsApp', correo: 'Correo', agenda: 'Agenda', entrega: 'Entrega de avisos', ciclo: 'Ciclo del vigía', wacli: 'Sincronizador de WhatsApp', bandeja: 'Bandeja de Tareas' }

function sec<W, T>(w: any, f: (x: W) => T): Sec<T> {
  if (!w || typeof w !== 'object') return { ok: false, error: 'No contestó' }
  if (w.ok === false) return { ok: false, error: str(w.error) || 'No pude leerlo' }
  return { ok: true, items: arr(w.items).map(f as (x: any) => T), obsoleto: !!w.obsoleto, parcial: strs(w.parcial), actualizado: str(w.actualizado) || null }
}
const prio = (v: unknown): 1 | 2 | 3 => v === 1 ? 1 : v === 3 ? 3 : 2
const aviso = (x: any): Aviso => ({ id: num(x.id) ?? 0, codigo: str(x.codigo), fuente: str(x.fuente), tipo: str(x.tipo), prio: prio(x.prio), titulo: str(x.titulo), detalle: str(x.detalle),
  borrador: str(x.borrador), enlace: /^https?:\/\//i.test(str(x.enlace)) ? str(x.enlace) : '', chat: str(x.chat), creado: str(x.creado), estado: str(x.estado) })

function vigias(w: any): Panel['vigias'] {
  if (!w || w.ok === false) return { ok: false, error: str(w?.error) || 'No pude leer los vigías' }
  const items: Vigia[] = []
  for (const [k, v] of Object.entries<any>(obj(w.fuentes))) if (k !== 'ciclo' && k !== 'entrega') items.push({ id: k, nombre: NOMBRE_VIGIA[k] || k, ok: !!v?.ok, haceMin: num(v?.hace_min), modo: str(v?.modo) || null })
  if (w.wacli) items.push({ id: 'wacli', nombre: NOMBRE_VIGIA.wacli, ok: !!w.wacli.ok, haceMin: num(w.wacli.hace_min), modo: null })
  if (w.bandeja) items.push({ id: 'bandeja', nombre: NOMBRE_VIGIA.bandeja, ok: !!w.bandeja.ok, haceMin: num(w.bandeja.hace_min), modo: str(w.bandeja.modo) || null })
  return { ok: true, v: { pausa: !!w.pausa, entregaReal: !!w.entrega_real, items } }
}

function semana(w: any): Semana | null {
  const dias = arr(w?.dias).map(d => ({ d: str(d.d), hechas: num(d.hechas) ?? 0, total: num(d.total) ?? 0 }))
  if (!dias.length) return null
  const h = dias.reduce((a, d) => a + d.hechas, 0), t = dias.reduce((a, d) => a + d.total, 0)
  return { dias, pct: t ? Math.round(h / t * 100) : 0 }
}

/** Sección que esta persona no tiene: vacía y sin error (Panel.hay dice que no está). */
const vacia = <T,>(): Sec<T> => ({ ok: true, items: [], obsoleto: false, parcial: [], actualizado: null })

export function leerPanel(w: any): Panel {
  const u = obj(w?.urgentes)
  if (!w || typeof w !== 'object' || !w.urgentes) throw new ErrorApi('Respuesta inesperada del servidor', 200, w)
  const hay = { eventos: 'eventos' in u, tareas: 'tareas' in u, avisos: 'avisos' in u, capturas: 'recientes' in w, vigias: 'vigias' in w }
  const p = leerSecciones(w, u)
  return { ...p, hay, eventos: hay.eventos ? p.eventos : vacia(), tareas: hay.tareas ? p.tareas : vacia(), avisos: hay.avisos ? p.avisos : vacia(),
    capturas: hay.capturas ? p.capturas : vacia(), vigias: hay.vigias ? p.vigias : { ok: true, v: { pausa: false, entregaReal: true, items: [] } } }
}

function leerSecciones(w: any, u: any): Omit<Panel, 'hay'> {
  return {
    generado: str(w.generado), fecha: str(w.fecha), nombre: str(w.saludo?.nombre),
    eventos: sec(u.eventos, (x: any): Evento => ({ id: str(x.id), titulo: str(x.titulo), inicio: str(x.inicio), fin: str(x.fin) || null, todoDia: !!x.todo_dia, lugar: str(x.lugar),
      dia: x.dia === 'mañana' ? 'mañana' : 'hoy', llevar: strs(x.llevar), tentativo: !!x.tentativo, cuenta: str(x.cuenta) })),
    tareas: sec(u.tareas, (x: any): TareaHoy => ({ id: str(x.id), titulo: str(x.titulo), due: str(x.due), vencida: x.estado === 'vencida', diasRetraso: num(x.dias_retraso) ?? 0, cuenta: str(x.cuenta), cuentaEmail: str(x.email) })),
    avisos: sec(u.avisos, aviso),
    capturas: sec(w.recientes, (x: any): Captura => {
      const riesgo: Riesgo = x.riesgo === 'alto' ? 'alto' : x.riesgo === 'medio' ? 'medio' : 'bajo'
      return { id: num(x.id) ?? 0, fuente: x.fuente === 'correo' ? 'correo' : 'wa', tipo: x.tipo === 'evento' ? 'evento' : 'tarea', titulo: str(x.titulo), detalle: str(x.detalle),
        due: str(x.due) || null, hora: str(x.hora) || null, chat: str(x.chat), accion: str(x.accion), accionTxt: str(x.accion_txt), creado: str(x.creado),
        riesgo, sospechosa: x.sospechoso === true, preparada: x.preparada === true && x.sospechoso !== true, regla: x.regla === 'siempre' || x.regla === 'nunca' ? x.regla : null,
        recordable: riesgo !== 'alto' && x.recordable !== false }
    }),
    vigias: vigias(w.vigias),
    tareasSinFecha: num(w.urgentes?.tareas?.sin_fecha),
    semana: semana(w.semana),
  }
}

export const cargarPanel = async (fresco = false) => leerPanel(await http(fresco ? '/api/panel?fresco=1' : '/api/panel'))

/** Marcar una tarea hecha / pendiente otra vez (endpoint que ya existía: Google Tasks). */
export const tareaHecha = (t: TareaHoy, hecha: boolean) => http('/api/tareas', { metodo: 'POST', cuerpo: { action: hecha ? 'done' : 'undo', id: t.id, account: t.cuentaEmail } })

/* ---------- vista: avisos ---------- */
export type EstadoAvisos = 'abierto' | 'luego' | 'hecho' | 'descartado'
export type ListaAvisos = { ok: true; items: Aviso[] } | { ok: false; error: string }
export async function cargarAvisos(estado: EstadoAvisos): Promise<ListaAvisos> {
  const w = await http<any>(`/api/avisos?estado=${estado}&n=100`)
  return w?.ok === false ? { ok: false, error: str(w.error) || 'No pude leer los avisos' } : { ok: true, items: arr(w?.items).map(aviso) }
}
export type AccionAviso = 'hecho' | 'descartar' | 'luego'
/** `luego`: horas (0,1–168) o 'manana' / 'tarde'. */
export const accionAviso = (id: number, a: AccionAviso, luego?: { horas?: number; cuando?: 'manana' | 'tarde' }) =>
  http(`/api/avisos/${id}/${a}`, { metodo: 'POST', cuerpo: a === 'luego' ? luego ?? {} : {} })

/* ---------- propuestas del vigía y reglas «siempre / nunca» ---------- */
export type RespuestaPropuesta = 'si' | 'no' | 'siempre' | 'nunca'
/** Sí / No / Sí, siempre / No, nunca. Va al vigía (zv); en modo sombra nada de esto escribe en Google. */
export const responderPropuesta = (id: number, r: RespuestaPropuesta) => http<any>(`/api/propuestas/${id}/${r}`, { metodo: 'POST', cuerpo: {} })
export type Regla = { clave: string; decision: 'siempre' | 'nunca'; texto: string; ejemplo: string; vecesSi: number; vecesNo: number; aplicada: number }
export type ListaReglas = { ok: true; items: Regla[] } | { ok: false; error: string }
export async function cargarReglas(): Promise<ListaReglas> {
  const w = await http<any>('/api/permisos')
  if (w?.ok === false) return { ok: false, error: str(w.error) || 'No pude leer las reglas' }
  return { ok: true, items: arr(w?.items).map((x: any): Regla => ({ clave: str(x.clave), decision: x.decision === 'nunca' ? 'nunca' : 'siempre', texto: str(x.texto), ejemplo: str(x.ejemplo),
    vecesSi: num(x.veces_si) ?? 0, vecesNo: num(x.veces_no) ?? 0, aplicada: num(x.aplicada) ?? 0 })) }
}
export const quitarRegla = (clave: string) => http<any>('/api/permisos/quitar', { metodo: 'POST', cuerpo: { clave } })

/* ---------- vista: barra de órdenes (sin charla libre) ---------- */
/** Una cosa que Zazu propone apuntar. `tipo` además de nota|idea|tarea|evento|aplicar|investigar|proyecto: completar|reprogramar (sobre una tarea que ya existe). */
export type Relacionado = { tipo: 'evento' | 'tarea'; titulo: string; etiqueta: string }
export type Elemento = { tipo: string; titulo: string; resumen: string; destino: string; destinoTxt: string; fecha: string | null; hora: string | null; aviso: string | null
  confirmable: boolean; falta: string[]; relacionado: Relacionado | null; duplicado: boolean }
export type Propuesta = Elemento & { id: string; items: Elemento[]; entendidoCon: 'haiku' | 'reglas'; avisoGeneral: string | null }
export type Respuesta = { k: 'propuesta'; p: Propuesta } | { k: 'chat'; mensaje: string; texto: string } | { k: 'privado'; mensaje: string }
export type Creado = { tipo: string; donde: string; titulo: string; id: string | null }
export type Resultado = { creados: Creado[]; fallos: { indice: number; error: string }[] }
function elemento(w: any): Elemento {
  const r = w?.relacionado
  return { tipo: str(w?.tipo), titulo: str(w?.titulo), resumen: str(w?.resumen), destino: str(w?.destino), destinoTxt: str(w?.destino_txt) || (str(w?.destino) ? `Irá a: ${str(w.destino)}` : ''),
    fecha: str(w?.fecha) || null, hora: str(w?.hora) || null, aviso: str(w?.aviso) || null, confirmable: w?.confirmable !== false, falta: strs(w?.falta),
    relacionado: r && typeof r === 'object' && str(r.etiqueta) ? { tipo: r.tipo === 'tarea' ? 'tarea' : 'evento', titulo: str(r.titulo), etiqueta: str(r.etiqueta) } : null, duplicado: w?.duplicado === true }
}
export async function proponer(texto: string, signal?: AbortSignal): Promise<Respuesta> {
  const w = await http<any>('/api/captura', { metodo: 'POST', cuerpo: { texto }, signal })
  if (w?.tipo === 'fuera_de_ambito') return { k: 'chat', mensaje: str(w.mensaje) || 'Eso mejor lo hablamos en el chat', texto: str(w.texto) || texto }
  if (w?.tipo === 'privado') return { k: 'privado', mensaje: str(w.mensaje) }
  if (!w?.id && w?.confirmable !== false) throw new ErrorApi('Respuesta inesperada del servidor', 200, w)
  const items = arr(w.items).map(elemento)
  const e = elemento(w)
  return { k: 'propuesta', p: { ...e, id: str(w.id), items: items.length ? items : [e], entendidoCon: w.entendido_con === 'haiku' ? 'haiku' : 'reglas', avisoGeneral: str(w.aviso_general) || null } }
}
const creado = (c: any): Creado => ({ tipo: str(c?.tipo), donde: str(c?.donde), titulo: str(c?.titulo), id: str(c?.id) || null })
const resultado = (w: any): Resultado => ({ creados: arr(w?.creados).length ? arr(w.creados).map(creado) : w?.creado ? [creado(w.creado)] : [],
  fallos: arr(w?.fallos).map(f => ({ indice: Number(f?.indice) || 0, error: str(f?.error) })) })
/** Escribe de verdad. Solo se llama desde el botón «Confirmar»; `marcados` = posiciones de las cosas marcadas (sin él: todas las que se pueden).
 *  409 «Ya lo hice»: devuelve lo que ya se hizo. */
export async function confirmar(id: string, marcados?: number[]): Promise<Resultado> {
  try { return resultado(await http<any>('/api/captura/confirmar', { metodo: 'POST', cuerpo: marcados ? { id, marcados } : { id } })) }
  catch (e) { if (e instanceof ErrorApi && e.status === 409 && e.cuerpo?.creado) return resultado(e.cuerpo); throw e }
}

/* ---------- vista: tableros ---------- */
export type Tarjeta = { ruta: string; titulo: string; estado: string; siguiente: string | null; plazo: string | null; dias: number | null; vencido: boolean; empresa: string | null; puesto: string | null
  ciudad: string | null; enlace: string | null; tags: string[]; pasos: { hechos: number; total: number }; aviso: string | null; mtime: number; moverA: string[]; obsidian: string | null }
export type Columna = { id: string; titulo: string; tarjetas: Tarjeta[] }
export type Evento2 = { id: string; titulo: string; inicio: string; cuenta: string; lugar: string; todoDia: boolean }
export type Persona = { ruta: string; titulo: string; tipo: string; relacion: string | null; proximoCumple: string | null; diasCumple: number | null; edad: number | null; vip: boolean | null; pendientes: { tareas: string[]; avisos: string[]; total: number } | null; obsidian: string | null; aviso: string | null }
export type Viaje = { tipo: string; fecha: string | null; dias: number | null; titulo: string; estado: string | null; siguiente: string | null; checklist: string[]; obsidian: string | null; enlace: string | null }
export type FechaClave = { fecha: string; dias: number; tipo: string; titulo: string; vencido: boolean; obsidian: string | null }
export type EstadoSus = 'activa' | 'nueva' | 'posible_cancelada' | 'solo_agenda'
export type Periodo = 'semanal' | 'mensual' | 'trimestral' | 'anual'
export type Suscripcion = { nombre: string; importe: number | null; moneda: string | null; periodo: Periodo | null; mensual: number | null; anual: number | null
  proximaFecha: string | null; dias: number | null; ultimoCobro: string | null; estado: EstadoSus; cancelar: boolean; cargos: number; base: string
  categoria: string | null; cuenta: string | null; subidaPct: number | null; proximoFuente: string | null; comercio: string }
export type Consejo = { comercio: string; texto: string; acciones: string[]; ia: boolean }
export type Cancelada = { comercio: string; desde: string | null }
export type TotalSus = { moneda: string; mensual: number; anual: number; n: number }
export type LecturaVigia = { fase: 'inicial' | 'al_dia' | null; pendientes: number | null; ultimaLectura: string | null; desde: string | null }
export type FilaGasto = { nombre: string; importe: number; moneda: string; importeEur: number | null; n: number }
export type GastosMes =
  | { ok: false; error: string }
  | { ok: true; mes: string; totalEur: number; sinConvertir: { moneda: string; importe: number }[]; porCategoria: FilaGasto[]; porComercio: FilaGasto[]
      anterior: { mes: string | null; totalEur: number | null; aEstaAltura: number | null }; sinClasificar: number | null; dudosos: number | null
      presupuesto: { topeActivo: boolean; tope: number | null; usado: number | null } }
export type PasoCarnet = { linea: number; texto: string; hecho: boolean }
type Base = { id: string; titulo: string }
export type Tablero = Base & (
  | { ok: false; error: string }
  | { ok: true; clase: 'kanban'; columnas: Columna[]; total: number }
  | { ok: true; clase: 'carnet'; nota: Tarjeta; pasos: PasoCarnet[]; llevar: string[]; estudio: string[]; eventos: Sec<Evento2>; total: number }
  | { ok: true; clase: 'personas'; items: Persona[]; avisos: string[]; total: number }
  | { ok: true; clase: 'viajes'; items: Viaje[]; pasados: number; nota: string | null; total: number }
  | { ok: true; clase: 'fechas'; grupos: { id: string; titulo: string; items: FechaClave[] }[]; avisos: string[]; total: number }
  | { ok: true; clase: 'suscripciones'; items: Suscripcion[]; nota: string | null; total: number; totales: TotalSus[]; lectura: LecturaVigia | null; gastos: GastosMes | null; canceladas: Cancelada[]; ocultas: number; consejos: Consejo[] })

/** Los que se pueden mover de estado (los demás son de solo lectura). */
export const EDITABLES = ['candidaturas', 'proyectos', 'programacion', 'carnet']
/** Cómo se pintan en la lista y en la barra lateral (el servidor manda el contenido; esto es solo apariencia). */
export const TABLEROS_UI: { id: string; titulo: string; letra: string; tono: 'primary' | 'secondary' | 'neutral'; lectura?: boolean }[] = [
  { id: 'candidaturas', titulo: 'Candidaturas', letra: 'C', tono: 'primary' },
  { id: 'proyectos', titulo: 'Proyectos', letra: 'P', tono: 'secondary' },
  { id: 'programacion', titulo: 'Programación', letra: '</>', tono: 'neutral' },
  { id: 'carnet', titulo: 'Carnet', letra: 'C', tono: 'secondary' },
  { id: 'personas', titulo: 'Personas', letra: 'P', tono: 'primary', lectura: true },
  { id: 'viajes', titulo: 'Viajes', letra: 'V', tono: 'neutral', lectura: true },
  { id: 'fechas', titulo: 'Fechas clave', letra: 'F', tono: 'secondary', lectura: true },
  { id: 'suscripciones', titulo: 'Suscripciones', letra: 'S', tono: 'neutral', lectura: true },
]

export const tarjeta = (x: any): Tarjeta => ({ ruta: str(x.ruta), titulo: str(x.titulo), estado: str(x.estado), siguiente: str(x.siguiente) || null, plazo: str(x.plazo) || null, dias: num(x.dias),
  vencido: !!x.vencido, empresa: str(x.empresa) || null, puesto: str(x.puesto) || null, ciudad: str(x.ciudad) || null, enlace: /^https?:\/\//i.test(str(x.enlace)) ? str(x.enlace) : null,
  tags: strs(x.tags), pasos: { hechos: num(x.pasos?.hechos) ?? 0, total: num(x.pasos?.total) ?? 0 }, aviso: str(x.aviso) || null, mtime: num(x.mtime) ?? 0, moverA: strs(x.mover_a),
  obsidian: str(x.obsidian).startsWith('obsidian://') ? str(x.obsidian) : null })

const ESTADOS_SUS: EstadoSus[] = ['activa', 'nueva', 'posible_cancelada', 'solo_agenda']
const PERIODOS: Periodo[] = ['semanal', 'mensual', 'trimestral', 'anual']
/** Una suscripción del servidor → vista. Sin nombre o con un estado que no conocemos no se enseña (nada inventado). */
function suscripcion(s: any): Suscripcion | null {
  if (!ESTADOS_SUS.includes(s?.estado) || !str(s?.nombre)) return null
  return { nombre: str(s.nombre), importe: num(s.importe), moneda: str(s.moneda) || null, periodo: PERIODOS.includes(s.periodo) ? s.periodo : null, mensual: num(s.mensual), anual: num(s.anual),
    proximaFecha: str(s.proxima_fecha) || null, dias: num(s.dias), ultimoCobro: str(s.ultimo_cobro) || null, estado: s.estado, cancelar: s.cancelar === true, cargos: num(s.cargos) ?? 0,
    base: str(s.base), categoria: str(s.categoria) || null, cuenta: str(s.cuenta) || null, subidaPct: num(s.subida_pct), proximoFuente: str(s.proximo_fuente) || null, comercio: str(s.comercio) || str(s.nombre).toLowerCase() }
}
const lectura = (e: any): LecturaVigia => ({ fase: e.fase === 'inicial' || e.fase === 'al_dia' ? e.fase : null, pendientes: num(e.pendientes), ultimaLectura: str(e.ultima_lectura) || null, desde: str(e.desde) || null })
const filaGasto = (campo: string) => (x: any): FilaGasto | null => {
  const imp = num(x?.importe)
  return str(x?.[campo]) && imp !== null && str(x?.moneda) ? { nombre: str(x[campo]), importe: imp, moneda: str(x.moneda), importeEur: num(x.importe_eur), n: num(x.n) ?? 0 } : null
}
function gastosMes(g: any): GastosMes {
  if (g.ok !== true) return { ok: false, error: str(g.error) || 'No pude leer los gastos del mes' }
  const total = num(g.total_eur)
  if (total === null || !/^\d{4}-\d{2}$/.test(str(g.mes))) return { ok: false, error: 'No pude leer los gastos del mes' }      // sin total no hay «0 €»
  const a = obj(g.anterior), p = obj(g.presupuesto)
  return { ok: true, mes: str(g.mes), totalEur: total, sinConvertir: Object.entries(obj(g.sin_convertir)).flatMap(([moneda, v]) => num(v) !== null ? [{ moneda, importe: num(v)! }] : []),
    porCategoria: arr(g.por_categoria).map(filaGasto('categoria')).filter((x): x is FilaGasto => x !== null), porComercio: arr(g.por_comercio).map(filaGasto('comercio')).filter((x): x is FilaGasto => x !== null),
    anterior: { mes: str(a.mes) || null, totalEur: num(a.total_eur), aEstaAltura: num(a.total_eur_a_esta_altura) }, sinClasificar: num(g.sin_clasificar), dudosos: num(g.dudosos),
    presupuesto: { topeActivo: p.tope_activo === true, tope: num(p.tope), usado: num(p.usado) } }
}

function tablero(w: any): Tablero {
  const b = { id: str(w?.id), titulo: str(w?.titulo) }
  if (w?.ok === false) return { ...b, ok: false, error: str(w.error) || 'No pude leer este tablero' }
  const total = num(w?.total) ?? 0
  if (w?.tipo === 'kanban') return { ...b, ok: true, clase: 'kanban', total, columnas: arr(w.columnas).map(c => ({ id: str(c.id), titulo: str(c.titulo), tarjetas: arr(c.tarjetas).map(tarjeta) })) }
  switch (b.id) {
    case 'carnet': return { ...b, ok: true, clase: 'carnet', total, nota: tarjeta(obj(w.nota)), pasos: arr(w.pasos).map(p => ({ linea: num(p.linea) ?? 0, texto: str(p.texto), hecho: !!p.hecho })),
      llevar: strs(w.llevar), estudio: strs(w.estudio),
      eventos: sec(w.eventos, (e: any): Evento2 => ({ id: str(e.id), titulo: str(e.titulo), inicio: str(e.inicio), cuenta: str(e.cuenta), lugar: str(e.lugar), todoDia: !!e.todo_dia })) }
    case 'personas': return { ...b, ok: true, clase: 'personas', total, avisos: strs(w.avisos), items: arr(w.items).map((p): Persona => ({ ruta: str(p.ruta), titulo: str(p.titulo), tipo: str(p.tipo), relacion: str(p.relacion) || null,
      proximoCumple: str(p.proximo_cumple) || null, diasCumple: num(p.dias_cumple), edad: num(p.edad), vip: p.vip === true ? true : p.vip === false ? false : null,
      pendientes: p.pendientes ? { tareas: strs(p.pendientes.tareas), avisos: strs(p.pendientes.avisos), total: num(p.pendientes.total) ?? 0 } : null,
      obsidian: str(p.obsidian).startsWith('obsidian://') ? str(p.obsidian) : null, aviso: str(p.aviso) || null })) }
    case 'viajes': return { ...b, ok: true, clase: 'viajes', total, pasados: num(w.pasados) ?? 0, nota: str(w.nota) || null, items: arr(w.items).map((v): Viaje => ({ tipo: str(v.tipo), fecha: str(v.fecha) || null, dias: num(v.dias),
      titulo: str(v.titulo), estado: str(v.estado) || null, siguiente: str(v.siguiente) || null, checklist: strs(v.checklist), obsidian: str(v.obsidian).startsWith('obsidian://') ? str(v.obsidian) : null,
      enlace: str(v.enlace).startsWith('/?') ? str(v.enlace) : null })) }
    case 'fechas': return { ...b, ok: true, clase: 'fechas', total, avisos: strs(w.avisos), grupos: arr(w.grupos).map(g => ({ id: str(g.id), titulo: str(g.titulo), items: arr(g.items).map((f): FechaClave => ({ fecha: str(f.fecha),
      dias: num(f.dias) ?? 0, tipo: str(f.tipo), titulo: str(f.titulo), vencido: !!f.vencido, obsidian: str(f.obsidian).startsWith('obsidian://') ? str(f.obsidian) : null })) })) }
    case 'suscripciones': return { ...b, ok: true, clase: 'suscripciones', total, nota: str(w.nota) || null, items: arr(w.items).map(suscripcion).filter((x): x is Suscripcion => x !== null),
      totales: Object.entries(obj(w.totales)).map(([moneda, t]: [string, any]) => ({ moneda, mensual: num(t?.mensual) ?? 0, anual: num(t?.anual) ?? 0, n: num(t?.n) ?? 0 })),
      lectura: w.estado && typeof w.estado === 'object' ? lectura(w.estado) : null, gastos: w.gastos && typeof w.gastos === 'object' ? gastosMes(w.gastos) : null,
      canceladas: arr(w.canceladas).map((c): Cancelada => ({ comercio: str(c.comercio), desde: str(c.desde) || null })).filter(c => c.comercio),
      ocultas: num(w.ocultas) ?? 0,
      consejos: arr(w.consejos).map((c): Consejo => ({ comercio: str(c.comercio), texto: str(c.texto), acciones: strs(c.acciones), ia: c.ia === true })).filter(c => c.comercio && c.texto) }
  }
  return { ...b, ok: false, error: 'Tablero desconocido' }
}
export async function cargarTableros(fresco = false): Promise<Tablero[]> {
  const w = await http<any>(fresco ? '/api/tableros?fresco=1' : '/api/tableros')
  if (!Array.isArray(w?.tableros)) throw new ErrorApi('Respuesta inesperada del servidor', 200, w)
  return w.tableros.map(tablero)
}

export type ResultadoMover = { ok: true; tarjeta: Tarjeta | null } | { ok: false; conflicto: boolean; error: string; tarjeta: Tarjeta | null }
/** Mueve una tarjeta de estado. 409: la nota cambió (Obsidian/sincronización): devuelve su estado actual. */
export async function moverTarjeta(t: Tarjeta, estado: string): Promise<ResultadoMover> {
  try {
    const w = await http<any>('/api/tableros/mover', { metodo: 'POST', cuerpo: { path: t.ruta, estado, mtime: t.mtime } })
    return { ok: true, tarjeta: w?.tarjeta ? tarjeta(w.tarjeta) : null }
  } catch (e) {
    if (e instanceof ErrorApi && e.status !== 0) return { ok: false, conflicto: e.status === 409, error: e.message, tarjeta: e.cuerpo?.tarjeta ? tarjeta(e.cuerpo.tarjeta) : null }
    throw e
  }
}
export async function marcarPaso(nota: Tarjeta, p: PasoCarnet, hecho: boolean): Promise<ResultadoMover> {
  try {
    const w = await http<any>('/api/tableros/paso', { metodo: 'POST', cuerpo: { path: nota.ruta, linea: p.linea, texto: p.texto, hecho, mtime: nota.mtime } })
    return { ok: true, tarjeta: w?.tarjeta ? tarjeta(w.tarjeta) : null }
  } catch (e) {
    if (e instanceof ErrorApi && e.status !== 0) return { ok: false, conflicto: e.status === 409, error: e.message, tarjeta: e.cuerpo?.tarjeta ? tarjeta(e.cuerpo.tarjeta) : null }
    throw e
  }
}

/* ---------- carga con estado (sustituye a lib.useFetch: aquí la fuente puede ser el modo demo) ---------- */
export function useCarga<T>(cargar: (() => Promise<T>) | null, clave: string, cada = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(!!cargar)
  const seq = useRef(0)   // solo cuenta la respuesta más reciente
  const fn = useRef(cargar)
  fn.current = cargar
  const reload = useCallback(async () => {
    const f = fn.current
    if (!f) return
    const n = ++seq.current
    try { const d = await f(); if (n === seq.current) { setData(d); setError('') } }
    catch (e) { if (n === seq.current) setError((e as Error).message) }
    finally { if (n === seq.current) setLoading(false) }
  }, [])
  useEffect(() => {
    if (!cargar) { setLoading(false); return }
    setLoading(true)
    void reload()
    const t = cada ? setInterval(() => { if (!document.hidden) void reload() }, cada) : undefined
    const vis = () => { if (cada && !document.hidden) void reload() }   // al volver a la pestaña, al día
    document.addEventListener('visibilitychange', vis)
    return () => { seq.current++; if (t) clearInterval(t); document.removeEventListener('visibilitychange', vis) }
  }, [clave, cada, !!cargar]) // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, reload, setData }
}

/* ---------- vista: «Qué ha hecho Zazu» (registro del vigía y flujos; contrato: docs/contrato-registro.md) ---------- */
export const FUENTES_REG = ['wa', 'correo', 'agenda', 'tareas', 'sistema'] as const
export const TIPOS_REG = ['leyo', 'propuso', 'escribio', 'descarto', 'fallo', 'aviso'] as const
export type FuenteReg = typeof FUENTES_REG[number]
export type TipoReg = typeof TIPOS_REG[number]
const esFuente = (v: unknown): v is FuenteReg => (FUENTES_REG as readonly unknown[]).includes(v)
const esTipo = (v: unknown): v is TipoReg => (TIPOS_REG as readonly unknown[]).includes(v)
const FLUJO_ID = /^[a-z0-9-]{1,40}$/

export type Entrada = { id: number; ts: string; actor: string | null; fuente: FuenteReg; tipo: TipoReg; modo: 'sombra' | 'vivo'; titulo: string; detalle: string; flujo: string | null; ref: string; enlace: string }
export type ResumenDia = { dia: string; cuenta: Record<TipoReg, number>; porFuente: Partial<Record<FuenteReg, Partial<Record<TipoReg, number>>>> }
export type Registro = { ok: true; clave: string; dia: string; items: Entrada[]; resumen: ResumenDia | null; omitidos: number; hayMas: boolean; pedido: number } | { ok: false; clave: string; error: string; dia: string }
export type FiltroReg = { fuente?: FuenteReg | ''; tipo?: TipoReg | ''; n?: number }

/** Solo http(s) llega a un href: cualquier otra cosa (javascript:, data:, obsidian:…) se queda en texto. */
export const enlaceSeguro = (v: unknown) => { const s = str(v).trim(); return /^https?:\/\/[^\s<>"']{1,290}$/i.test(s) ? s : '' }

function entrada(x: any): Entrada | null {
  if (!x || typeof x !== 'object' || !esFuente(x.fuente) || !esTipo(x.tipo) || (x.modo !== 'sombra' && x.modo !== 'vivo') || typeof x.id !== 'number') return null
  const ts = str(x.ts)
  if (isNaN(new Date(ts).getTime()) || !str(x.titulo)) return null
  return { id: x.id, ts, actor: str(x.actor) || null, fuente: x.fuente, tipo: x.tipo, modo: x.modo, titulo: str(x.titulo), detalle: str(x.detalle), flujo: FLUJO_ID.test(str(x.flujo)) ? str(x.flujo) : null, ref: str(x.ref), enlace: enlaceSeguro(x.enlace) }
}
function resumenDia(w: any, dia: string): ResumenDia | null {
  if (!w || typeof w !== 'object') return null
  const cuenta = {} as Record<TipoReg, number>
  for (const t of TIPOS_REG) { const n = num(w[t]); if (n === null || n < 0) return null; cuenta[t] = n }   // un número que falta: no se inventa ninguno
  const porFuente: ResumenDia['porFuente'] = {}
  for (const f of FUENTES_REG) { const d = obj(obj(w.por_fuente)[f]); const o: Partial<Record<TipoReg, number>> = {}; for (const t of TIPOS_REG) { const n = num(d[t]); if (n !== null) o[t] = n } if (Object.keys(o).length) porFuente[f] = o }
  return { dia, cuenta, porFuente }
}
/** Identifica una petición: una respuesta de otro día o de otro filtro (que llega tarde) nunca se pinta como si fuera esta. */
export const claveReg = (dia: string, f: FiltroReg = {}) => `${dia}|${f.fuente || ''}|${f.tipo || ''}|${f.n || 100}`
export async function cargarRegistro(dia: string, f: FiltroReg = {}): Promise<Registro> {
  const clave = claveReg(dia, f)
  const q = new URLSearchParams({ dia, n: String(f.n || 100) })
  if (f.fuente) q.set('fuente', f.fuente)
  if (f.tipo) q.set('tipo', f.tipo)
  const w = await http<any>(`/api/registro?${q}`)
  if (!w || typeof w !== 'object') throw new ErrorApi('Respuesta inesperada del servidor', 200, w)
  if (w.ok !== true || !Array.isArray(w.items)) return { ok: false, clave, dia, error: str(w.error) || 'No pude leer el registro del vigía' }
  const items = arr(w.items).map(entrada).filter((x): x is Entrada => !!x)
  return { ok: true, clave, dia, items, resumen: resumenDia(w.resumen, dia), omitidos: (num(w.omitidos) ?? 0) + (arr(w.items).length - items.length), hayMas: !!w.hay_mas, pedido: num(w.n_pedido) ?? (f.n || 100) }
}

export type Efectivo = 'prueba' | 'vivo' | 'pausado' | 'desconocido'
export type Flujo = { id: string; nombre: string; descripcion: string; fuente: FuenteReg | null; acciones: string[]; modo: 'sombra' | 'activo'; pausado: boolean; ultimo: string | null; disparos7d: number | null; efectivo: Efectivo; motivo: string }
export type General = { pausa: boolean; entregaReal: boolean; modo: Partial<Record<FuenteReg, 'sombra' | 'activo'>> }
export type Flujos = { ok: true; flujos: Flujo[]; general: General | null } | { ok: false; error: string }

function flujo(x: any): Flujo | null {
  if (!x || typeof x !== 'object' || !FLUJO_ID.test(str(x.id)) || (x.modo !== 'sombra' && x.modo !== 'activo')) return null
  const ef = ['prueba', 'vivo', 'pausado', 'desconocido'].includes(x.efectivo) ? x.efectivo as Efectivo : 'desconocido'
  const ts = str(x.ultimo)
  return { id: x.id, nombre: str(x.nombre) || x.id, descripcion: str(x.descripcion), fuente: esFuente(x.fuente) ? x.fuente : null, acciones: strs(x.acciones).slice(0, 8), modo: x.modo, pausado: x.pausado === true,
    ultimo: ts && !isNaN(new Date(ts).getTime()) ? ts : null, disparos7d: num(x.disparos_7d), efectivo: ef, motivo: str(x.motivo) }
}
function general(w: any): General | null {
  if (!w || typeof w !== 'object') return null
  const modo: General['modo'] = {}
  for (const f of FUENTES_REG) { const m = obj(w.modo)[f]; if (m === 'sombra' || m === 'activo') modo[f] = m }
  return { pausa: !!w.pausa, entregaReal: !!w.entrega_real, modo }
}
export async function cargarFlujos(): Promise<Flujos> {
  const w = await http<any>('/api/flujos')
  if (!w || typeof w !== 'object') throw new ErrorApi('Respuesta inesperada del servidor', 200, w)
  if (w.ok !== true || !Array.isArray(w.flujos)) return { ok: false, error: str(w.error) || 'No pude leer los flujos' }   // fallo ≠ «0 flujos»
  return { ok: true, flujos: arr(w.flujos).map(flujo).filter((f): f is Flujo => !!f), general: general(w.general) }
}
export type CambioFlujo = { accion: 'pausa' } | { accion: 'reanuda' } | { accion: 'modo'; modo: 'sombra' } | { accion: 'modo'; modo: 'activo'; confirmo: true }
/** Devuelve el flujo ya cambiado, tal como lo ha vuelto a leer el servidor del vigía (nunca se da por hecho sin esa lectura). */
export async function cambiarFlujo(id: string, c: CambioFlujo): Promise<{ flujo: Flujo; general: General | null }> {
  const w = await http<any>(`/api/flujos/${encodeURIComponent(id)}`, { metodo: 'POST', cuerpo: c })
  const f = flujo(w?.flujo)
  if (!f) throw new ErrorApi('Respuesta inesperada del servidor', 200, w)
  return { flujo: f, general: general(w.general) }
}
