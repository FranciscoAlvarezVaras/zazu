// Vincula el WhatsApp de una invitada con su NÚMERO (código de 8 letras), sin QR: así puede hacerlo desde el mismo móvil.
// Uso (lo lanza server.py): node wa_codigo.mjs --bridge <carpeta del puente de Hermes> --session <carpeta de sesión> --telefono 34600111222
// Escribe líneas JSON: {"event":"code","code":"ABCD1234","vale":150} (uno nuevo en cada reconexión) · {"event":"connected","user":{...}} · {"event":"error","error":"..."}
// La sesión queda en el mismo formato que usa el puente de Hermes (bridge.js), que la recoge después. No toca los archivos de Hermes.
import path from 'path';
import { pathToFileURL } from 'url';

const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : ''; };
const BRIDGE = arg('--bridge'), SESSION = arg('--session'), TEL = (arg('--telefono') || '').replace(/\D/g, '');
const out = (o) => process.stdout.write(JSON.stringify({ ts: Date.now(), ...o }) + '\n');
if (!BRIDGE || !SESSION || !/^\d{8,15}$/.test(TEL)) { out({ event: 'error', error: 'faltan datos o el número no vale' }); process.exit(2); }

const mod = (p) => import(pathToFileURL(path.join(BRIDGE, 'node_modules', p)).href);
const B = await mod('@whiskeysockets/baileys/lib/index.js');
const pino = (await mod('pino/pino.js')).default;
const { makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, Browsers } = B;

async function arrancar() {
  // Un código por conexión: WhatsApp cierra el emparejado a los ~160 s (408, «QR refs attempts ended») y, al reconectar,
  // hay que pedir otro; si no, la pantalla seguiría enseñando uno que ya no vale.
  let pedido = false;
  const { state, saveCreds } = await useMultiFileAuthState(SESSION);
  // requestPairingCode deja guardado creds.me: con él, Baileys intenta ENTRAR (login) en vez de registrarse, WhatsApp no
  // manda pair-device, no sale «qr» y nunca llega el código nuevo. Si el emparejado no se completó (sin creds.account,
  // que solo pone pair-success), se olvida para volver a registrarse. Tras el 515 de un emparejado bueno, account ya está.
  if (!state.creds.account) { delete state.creds.me; delete state.creds.pairingCode; }
  let version;
  try { version = (await fetchLatestBaileysVersion()).version; } catch { /* la de la librería */ }
  const sock = makeWASocket({
    ...(version ? { version } : {}), auth: state, logger: pino({ level: 'silent' }), printQRInTerminal: false,
    browser: Browsers ? Browsers.ubuntu('Chrome') : ['HolaZazu', 'Chrome', '120.0'], syncFullHistory: false, markOnlineOnConnect: false,
    getMessage: async () => ({ conversation: '' }),
  });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr && !pedido && !state.creds.registered) {   // WhatsApp ya escucha: se pide el código en vez de enseñar el QR
      pedido = true;
      try { out({ event: 'code', code: await sock.requestPairingCode(TEL), vale: 150 }); }
      catch (e) { out({ event: 'error', error: 'WhatsApp no dio el código: ' + (e?.message || e) }); process.exit(1); }
    }
    if (connection === 'open') {
      out({ event: 'connected', user: sock.user ? { id: sock.user.id || null, name: sock.user.name || sock.user.verifiedName || null } : null });
      setTimeout(() => process.exit(0), 2500);   // que se guarden las credenciales
    } else if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) { out({ event: 'error', error: 'logged_out' }); process.exit(1); }
      setTimeout(() => arrancar().catch((e) => { out({ event: 'error', error: String(e?.message || e) }); process.exit(1); }), code === 515 ? 1000 : 3000);
    }
  });
}
arrancar().catch((e) => { out({ event: 'error', error: String(e?.message || e) }); process.exit(1); });
