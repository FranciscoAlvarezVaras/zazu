// Service worker mínimo: instalable + la carcasa abre sin red. Las llamadas /api/ nunca se cachean.
const V='hub-v72', SHELL=['/','/manifest.json','/icon-192.png'], COMPARTIDOS='compartidos';
const MAX_ARCH=10, MAX_BYTES=200*1024*1024;   // lo que se guarda de un «Compartir» (y de lo pendiente sumado)
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
// al actualizar se borran las cachés viejas, pero nunca lo compartido que aún no se ha subido
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V&&x!==COMPARTIDOS).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method==='POST'&&u.origin===location.origin&&u.pathname==='/compartir'){
    // Android comparte sin referrer: un formulario de otra web que apunta aquí no se guarda
    const rf=e.request.referrer;
    if(/^https?:/.test(rf)&&new URL(rf).origin!==location.origin)return e.respondWith(Response.redirect(location.origin+'/',303));
    return e.respondWith(compartir(e.request));
  }
  // los vídeos van directos al servidor: llegan por tramos (206) y la caché no guarda respuestas parciales
  if(e.request.method!=='GET'||u.origin!==location.origin||u.pathname.startsWith('/api/')||u.pathname.startsWith('/c/')||u.pathname==='/zazu.apk'||/\.(webm|mp4)$/.test(u.pathname))return;
  // sin red, una página (/?tab=…&conv=…) que no esté guardada tal cual abre la carcasa guardada de '/'
  // solo se guarda lo que salió bien; si el servidor de casa está caído (502/530 de Cloudflare), se abre la carcasa guardada en vez de la página de error
  e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(V).then(c=>c.put(e.request,cp));return r}
    if(e.request.mode==='navigate'&&r.status>=500)return caches.match(e.request).then(h=>h||caches.match('/')).then(h=>h||r);return r}).catch(()=>caches.match(e.request).then(r=>r||(e.request.mode==='navigate'?caches.match('/'):r))));
});

// Compartir › Zazu desde otra app (manifest share_target, POST multipart). Android no manda la cabecera X-Hub,
// así que los archivos se guardan aquí (caché "compartidos", claves /compartido/<n>, nombre en X-Nombre, tamaño en X-Tam)
// y Carpetas los enseña y solo los sube si Fran toca «Guardar» (el referrer se puede ocultar: la confirmación es lo que protege).
// Si solo llega texto o un enlace, se abre el chat como siempre.
async function compartir(req){
  const ir=p=>Response.redirect(new URL(p,location.origin).href,303);
  if((+req.headers.get('content-length')||0)>MAX_BYTES+1048576)return ir('/?tab=carpetas&recibido=demasiado');
  let f;try{f=await req.formData()}catch(_){return ir('/?tab=carpetas')}
  const arch=f.getAll('archivos').filter(x=>x&&typeof x==='object'&&x.size>0);
  if(!arch.length){
    const q=new URLSearchParams();for(const k of ['title','text','url']){const v=f.get(k);if(typeof v==='string'&&v.trim())q.set(k,v)}
    return ir(q.toString()?'/?'+q:'/');
  }
  const tam=arch.reduce((s,x)=>s+x.size,0);
  if(arch.length>MAX_ARCH||tam>MAX_BYTES)return ir('/?tab=carpetas&recibido=demasiado');
  const c=await caches.open(COMPARTIDOS);
  // numerar después de lo que haya pendiente: un segundo envío no pisa al primero
  const viejas=await c.keys();let n=0,peso=0;
  for(const r of viejas){const x=parseInt(new URL(r.url).pathname.split('/').pop(),10);if(!isNaN(x))n=Math.max(n,x+1);const m=await c.match(r);peso+=Number(m&&m.headers.get('X-Tam'))||0}
  // lo pendiente sin confirmar más lo nuevo tampoco pasa del límite: si no cabe, se queda solo lo nuevo
  if(viejas.length+arch.length>MAX_ARCH||peso+tam>MAX_BYTES)for(const r of viejas)await c.delete(r);
  for(const x of arch)await c.put('/compartido/'+(n++),new Response(x,{headers:{'Content-Type':x.type||'application/octet-stream','X-Nombre':encodeURIComponent(x.name||'archivo'),'X-Tam':String(x.size)}}));
  return ir('/?tab=carpetas&recibido=1');
}

// Alertas push (el vigilante del servidor): notificación con el logo de Zazu; al tocarla, abre el Inicio.
self.addEventListener('push',e=>{
  let d={};try{d=e.data?e.data.json():{}}catch(_){d={body:e.data&&e.data.text()}}
  const ap=/^[0-9a-f]{12}$/.test(d.aprob||'')?d.aprob:null;   // permiso de su Zazu: Permitir / Rechazar desde el propio aviso
  e.waitUntil(self.registration.showNotification(d.title||'Zazu',{body:d.body||'',icon:'/icon-192.png',badge:'/badge-96.png',tag:d.tag||'zazu',renotify:true,
    data:{url:d.url||'/',aprob:ap},...(ap?{requireInteraction:true,actions:[{action:'si',title:'Permitir'},{action:'no',title:'Rechazar'}]}:{})}));
});
self.addEventListener('notificationclick',e=>{
  e.notification.close();
  const ap=e.notification.data&&e.notification.data.aprob;
  if(ap&&(e.action==='si'||e.action==='no')){
    e.waitUntil(fetch('/api/aprobaciones',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Hub':'1'},body:JSON.stringify({id:ap,decision:e.action})})
      .then(r=>self.registration.showNotification(r.ok?(e.action==='si'?'Permitido':'Rechazado'):'No se pudo responder',
        {body:r.ok?'':'Ya no estaba pendiente o tu sesión caducó. Abre la app.',icon:'/icon-192.png',badge:'/badge-96.png',tag:'aprob-hecho'}))
      .catch(()=>clients.openWindow(e.notification.data.url||'/')));
    return;
  }
  const url=(e.notification.data&&e.notification.data.url)||'/';
  e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(ws=>{
    for(const w of ws){if(new URL(w.url).origin===location.origin){w.navigate(url);return w.focus()}}
    return clients.openWindow(url);
  }));
});
