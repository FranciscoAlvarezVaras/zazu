import type { Tab } from './lib'
import type { ChatApi } from './tipos'
import type { Me } from './screens/Invitada'

export type Ask = (prompt: string, o?: { profile?: string; fill?: boolean; ctx?: string; nueva?: boolean }) => void
/** Lo que reciben todas las pantallas. */
export type Ctx = { nombre?: string; guest?: boolean; me: Me; go: (t: Tab) => void; ask: Ask; toast: (m: string) => void;
  chat: ChatApi; draft: string; setDraft: (s: string) => void; abrirModelos: () => void; abrirAsistentes: () => void }
