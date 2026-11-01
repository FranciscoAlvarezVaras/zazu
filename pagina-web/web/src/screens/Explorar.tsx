import { Icon } from '../icons'
import type { IconName } from '../icons'
import { irA } from '../lib'
import type { Tab } from '../lib'
import type { Ctx } from '../ctx'

const fila = (key: string, go: () => void, icon: IconName, tone: string, title: string, sub: string) =>
  <button className="explore-row" key={key} onClick={go}><span className={`explore-icon ${tone}`}><Icon name={icon} size={22} /></span><span><strong>{title}</strong><small>{sub}</small></span><Icon name="chevron" size={18} /></button>
const row = (go: (t: Tab) => void, t: Tab, icon: IconName, tone: string, title: string, sub: string) => fila(t, () => go(t), icon, tone, title, sub)

/** Todo lo de la app en una lista (se abre desde el menú ☰). Las invitadas no llegan aquí (App.GUEST_GO). */
export default function Explorar({ go }: Ctx) {
  return <div className="extra-screen screen-enter">
    <div className="screen-heading"><span className="section-kicker">TODO EN UN MISMO LUGAR</span><h2>Explorar<span className="greeting-dot">.</span></h2><p>Lo que necesitas, cuando lo necesitas.</p></div>
    <div className="explore-highlight"><span className="feature-label"><span className="feature-label-dot" /> TU ESPACIO</span><Icon name="spark" size={28} /><h3>Más espacio para<br />lo que importa.</h3><p>Organiza, entiende y avanza a tu manera.</p></div>
    <div className="explore-group"><span className="section-kicker">ORGANIZA TU MUNDO</span>
      {row(go, 'midia', 'sun', 'mint', 'Hoy', 'Tu resumen, agenda y tareas de hoy')}
      {row(go, 'calendario', 'calendar', 'butter', 'Calendario', 'Google Calendar: mes y nuevos eventos')}
      {fila('carpetas', () => irA({ tab: 'carpetas', root: 'compartido' }), 'folder', 'peach', 'Mis carpetas', 'Tus archivos, también lo que mandas por WhatsApp')}
      {fila('notas', () => irA({ tab: 'carpetas', root: 'notas' }), 'pen', 'lavender', 'Mis notas', 'Bandeja, diario e ideas de tu Cerebro (solo lectura)')}
      {fila('wa-movil', () => irA({ tab: 'carpetas', root: 'whatsapp' }), 'file', 'mint', 'WhatsApp del móvil', 'Fotos y documentos de tus chats (solo lectura)')}</div>
    <div className="explore-group"><span className="section-kicker">COMUNICACIONES</span>{row(go, 'correo', 'mail', 'lavender', 'Correos', 'Encuentra lo importante')}{row(go, 'whatsapp', 'chat', 'mint', 'WhatsApp', 'Conversaciones en claro')}</div>
    <div className="explore-group"><span className="section-kicker">ZAZU</span>{row(go, 'chat', 'spark', 'lavender', 'Chat con Zazu', 'Pídele lo que quieras: lo delicado te lo pregunta antes')}{row(go, 'rutinas', 'clock', 'butter', 'Rutinas', 'Lo que hace solo cada día')}{row(go, 'cuentas', 'shield', 'peach', 'Cuentas', 'Conectar Google y WhatsApp')}{row(go, 'ajustes', 'settings', 'lavender', 'Tu espacio', 'Estado, gasto y preferencias')}</div>
    <p className="demo-note"><Icon name="shield" size={15} /> Correos y WhatsApp aquí son de solo lectura. Zazu no escribe a nadie más sin preguntarte.</p>
  </div>
}
