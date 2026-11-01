import type { ReactNode } from 'react'

export type IconName = 'spark' | 'arrow' | 'arrowUp' | 'home' | 'chat' | 'check' | 'settings' | 'bell' | 'calendar' | 'plus' | 'mic' | 'paperclip' | 'sun' | 'pen' | 'lightbulb' | 'chevron' | 'close' | 'volume' | 'shield' | 'moon' | 'logout' | 'clock' | 'folder' | 'mail' | 'grid' | 'back' | 'download' | 'file' | 'play' | 'pause' | 'upload' | 'menu' | 'camera' | 'pin'

export function Icon({ name, size = 20, strokeWidth = 1.8 }: { name: IconName; size?: number; strokeWidth?: number }) {
  const paths: Record<IconName, ReactNode> = {
    spark: <><path d="M12 2.5c.6 5.5 2 7 7.5 9.5-5.5.6-7 2-7.5 9.5-.6-5.5-2-7-7.5-9.5 5.5-.6 7-2 7.5-9.5Z"/><path d="M19.5 2.5v4M17.5 4.5h4"/></>,
    arrow: <><path d="M4 12h15m-6-6 6 6-6 6"/></>,
    arrowUp: <><path d="M12 19V5m-6 6 6-6 6 6"/></>,
    home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z"/><path d="M9 21v-7h6v7"/></>,
    chat: <path d="M20 11.5a8.5 8.5 0 0 1-8.5 8.5 9 9 0 0 1-3.5-.7L3 21l1.7-5A8.5 8.5 0 1 1 20 11.5Z"/>,
    check: <path d="m5 12 4.5 4.5L19 7"/>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.56V21h-4v-.04A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H3v-4h.04A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88L4.2 7.06 7.06 4.2l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.56V3h4v.04A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.56 1H21v4h-.04A1.7 1.7 0 0 0 19.4 15Z"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 8-3 9h18c0-1-3-2-3-9ZM10 21h4"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    mic: <><rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 11a7 7 0 0 0 14 0m-7 7v4m-4 0h8"/></>,
    paperclip: <path d="m8 12.5 6.7-6.7a3 3 0 0 1 4.2 4.2l-8.5 8.5a5 5 0 0 1-7.1-7.1l8.5-8.5"/>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></>,
    pen: <><path d="m4 20 4.5-1 11-11a2.12 2.12 0 0 0-3-3l-11 11L4 20Z"/><path d="m14.5 7.5 3 3"/></>,
    lightbulb: <><path d="M9 18h6m-5 3h4M8.5 15.5a7 7 0 1 1 7 0c-.9.6-1 1.5-1 2.5h-5c0-1-.1-1.9-1-2.5Z"/></>,
    chevron: <path d="m9 18 6-6-6-6"/>,
    close: <path d="M5 5 19 19M19 5 5 19"/>,
    volume: <><path d="M4 9v6h4l5 4V5L8 9H4Zm12-1a6 6 0 0 1 0 8m2-11a10 10 0 0 1 0 14"/></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></>,
    moon: <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5 8.5 8.5 0 1 0 20.5 14.5Z"/>,
    logout: <><path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5m4-4 4-4-4-4m4 4H8"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    back: <path d="m15 18-6-6 6-6"/>,
    download: <><path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/></>,
    file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/></>,
    play: <path d="M7 4.5v15l12-7.5Z"/>,
    pause: <path d="M8 5v14M16 5v14"/>,
    upload: <><path d="M12 16V5m-5 5 5-5 5 5M5 20h14"/></>,
    menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
    camera: <><path d="M4 8a2 2 0 0 1 2-2h1.5l1.2-2h6.6l1.2 2H18a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z"/><circle cx="12" cy="13" r="3.5"/></>,
    pin: <><path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

/** El logo de HolaZazu en pequeño (barra de arriba, saludos): la cara del gato del logo nuevo, web/public/holazazu-cara.png. */
export function LogoZazu({ tam = 30, className = '' }: { tam?: number; className?: string }) {
  // logo de HolaZazu (2026-10-21): la cara del gato del logo completo (brand/holazazu-logo-2048.jpg)
  return <img className={className} src="/holazazu-cara.png" width={tam} height={tam} alt="Zazu" style={{ flex: 'none', display: 'block', borderRadius: Math.round(tam * 0.22), objectFit: 'cover' }} />
}

/** La marca de Zazu (pantalla de carga, bienvenida): el mismo logo de bits para todos. */
export function BrandMark({ small = false }: { small?: boolean }) {
  return <LogoZazu tam={small ? 32 : 40} className="brand-logo" />
}
