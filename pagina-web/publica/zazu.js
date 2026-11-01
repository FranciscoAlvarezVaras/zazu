// Páginas públicas de holazazu.app. Todo funciona sin JS; esto solo lo mejora:
// menú del teléfono (C12), pestañas de /descargar (C11), saludo de Zazu, demo de chat (C1) y lista de espera (C6).
var REDUCIR = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

// C12: el menú del teléfono es un <details>; se cierra con Esc (y el foco vuelve a «Menú»), al tocar fuera o al elegir un enlace.
(function () {
  var m = document.querySelector('.menu-movil');
  if (!m) return;
  var s = m.querySelector('summary');
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && m.open) { m.open = false; s.focus(); }
  });
  document.addEventListener('click', function (e) {
    if (m.open && !m.contains(e.target)) m.open = false;
  });
  m.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('nav a')) m.open = false;   // /#lista-espera en la misma página: que no quede abierto
  });
})();

// C11: en /descargar el selector Android / Apple funciona solo con CSS (:target); esto marca la pestaña actual para los lectores
// de pantalla y, si entras desde un iPhone, iPad o Mac sin elegir nada, te abre la de Apple (en los demás casos, Android).
(function () {
  var sel = document.querySelector('.selector');
  if (!sel) return;
  var enlaces = sel.querySelectorAll('a');
  function marcar() {
    var apple = location.hash === '#apple';
    for (var i = 0; i < enlaces.length; i++) {
      var es = (enlaces[i].getAttribute('href') === '#apple') === apple;
      if (es) enlaces[i].setAttribute('aria-current', 'true'); else enlaces[i].removeAttribute('aria-current');
    }
  }
  if (!location.hash && /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent)) {
    location.replace('#apple');
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', marcar);
  marcar();
})();

// Portada: Zazu saluda UNA vez al cargar y se queda quieto (el vídeo empieza y acaba en la pose del póster, sin bucle).
// Si pasas el ratón por encima, lo tocas o lo enfocas con el teclado, vuelve a saludar una vez. Con «reducir movimiento», solo el póster.
(function () {
  var v = document.getElementById('zazu-saludo');
  if (!v || !v.play || REDUCIR) return;
  var escena = v.parentNode;
  function saludar() {
    if (!v.paused && !v.ended) return;
    if (v.preload !== 'auto') v.preload = 'auto';
    if (v.ended || v.currentTime > 0) v.currentTime = 0;
    var p = v.play();
    if (p && p.catch) p.catch(function () {});   // reproducción bloqueada (ahorro de batería): se queda el póster
  }
  escena.tabIndex = 0;
  escena.addEventListener('mouseenter', saludar);
  escena.addEventListener('click', saludar);
  escena.addEventListener('focus', saludar);
  saludar();
})();

// C1: demo de chat. El HTML ya trae todas las burbujas (sin JS se leen una debajo de otra). Con JS:
// - .demo-chat con pestañas: clic o flechas ← → (Inicio/Fin); al abrir una, las burbujas entran en orden. Nunca avanza sola.
// - .demo-mini (héroe, sin pestañas): pasa una sola vez del primer panel al siguiente y se queda en el último.
// «Pausar ejemplo» congela la secuencia y pasa a «Seguir» (cambia el texto, no aria-pressed: un nombre que cambia y además «pulsado» se lee al revés). Con «reducir movimiento», todo se ve terminado y la mini no cambia.
(function () {
  var demos = document.querySelectorAll('.demo-chat');
  for (var i = 0; i < demos.length; i++) montar(demos[i]);

  function montar(demo) {
    var tabs = [].slice.call(demo.querySelectorAll('[role=tab]'));
    var paneles = [].slice.call(demo.querySelectorAll('.demo-panel'));
    var lista = demo.querySelector('[role=tablist]');
    var pausa = demo.querySelector('.demo-pausa');
    var mini = demo.classList.contains('demo-mini');
    var cola = [], reloj = null, parado = false, actual = 0, visto = false, tocado = false;
    if (!paneles.length) return;
    demo.classList.add('activa');
    if (lista) lista.hidden = false;
    if (pausa && !REDUCIR) pausa.hidden = false;

    function paso() {
      reloj = null;
      if (parado) return;
      var li = cola.shift();
      if (li) {
        li.classList.add('ver');
        reloj = setTimeout(paso, li.classList.contains('estado') ? 700 : 550);
      } else if (mini && actual < paneles.length - 1) {
        reloj = setTimeout(function () { reloj = null; if (!parado) mostrar(actual + 1); }, 3500);
      }
    }
    function reproducir(p) {
      clearTimeout(reloj);
      var items = p.querySelectorAll('.chat>li');
      cola = [];
      for (var j = 0; j < items.length; j++) {
        if (REDUCIR) items[j].classList.add('ver');
        else { items[j].classList.remove('ver'); cola.push(items[j]); }
      }
      if (!REDUCIR) reloj = setTimeout(paso, 150);
    }
    function mostrar(n, foco) {
      actual = n;
      for (var j = 0; j < paneles.length; j++) paneles[j].hidden = j !== n;
      for (j = 0; j < tabs.length; j++) {
        tabs[j].setAttribute('aria-selected', j === n ? 'true' : 'false');
        tabs[j].tabIndex = j === n ? 0 : -1;
      }
      if (foco) tabs[n].focus();
      if (tocado) paneles[n].setAttribute('aria-live', 'polite');   // solo tras tocar una pestaña: al cargar no se anuncia nada
      if (visto) reproducir(paneles[n]);
    }

    var inicial = 0;
    for (var j = 0; j < tabs.length; j++) if (tabs[j].getAttribute('aria-selected') === 'true') inicial = j;
    mostrar(inicial);
    // la primera secuencia arranca cuando la demo se ve en pantalla (si no, se vería ya terminada al llegar)
    function empezar() { if (!visto) { visto = true; reproducir(paneles[actual]); } }
    if (window.IntersectionObserver && !REDUCIR) {
      var io = new IntersectionObserver(function (es) {
        if (es[0].isIntersecting) { io.disconnect(); empezar(); }
      }, { threshold: 0.35 });
      io.observe(demo);
    } else empezar();

    tabs.forEach(function (t, n) {
      t.addEventListener('click', function () { tocado = true; visto = true; mostrar(n); });
    });
    if (lista) lista.addEventListener('keydown', function (e) {
      var n = { ArrowRight: actual + 1, ArrowLeft: actual - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (n === undefined) return;
      e.preventDefault();
      tocado = true; visto = true;
      mostrar((n + tabs.length) % tabs.length, true);
    });
    if (pausa) pausa.addEventListener('click', function () {
      parado = !parado;
      pausa.textContent = parado ? 'Seguir' : 'Pausar ejemplo';
      if (parado) { clearTimeout(reloj); reloj = null; } else if (visto) paso();
    });
  }
})();

// C6: lista de espera con un solo campo. Valida al salir del campo (si ya escribiste algo) y al enviar, no mientras escribes;
// el error se quita en cuanto el email es válido. Con fetch, el éxito sustituye al formulario y recibe el foco.
// Sin JS (o sin fetch) es un POST normal: el servidor vuelve a /#gracias o, si algo falla, a /?e=<código>#lista-espera con el aviso ya escrito.
(function () {
  var f = document.getElementById('form-espera');
  if (!f) return;
  var email = f.elements.email, err = document.getElementById('err-email'), estado = document.getElementById('estado-espera');
  var cuerpo = f.closest ? f.closest('.espera-cuerpo') : null;
  var boton = f.querySelector('button[type=submit]'), textoBoton = boton.textContent, escrito = false;
  var MAL_ESCRITO = 'Falta algo en el email. Ejemplo: nombre@gmail.com';
  var SIN_RED = 'No ha llegado. ¿Lo intentas otra vez en un momento?';
  function avisar(t) {
    err.textContent = t;
    if (t) email.setAttribute('aria-invalid', 'true'); else email.removeAttribute('aria-invalid');
  }
  function revisar() {
    var v = email.value.trim();
    if (!v) return 'Escribe tu email para poder avisarte.';
    return /^[^\s@]+@[^\s@]+\.[^\s@.]{2,}$/.test(v) ? '' : MAL_ESCRITO;
  }
  if (err.textContent.trim()) email.setAttribute('aria-invalid', 'true');   // el aviso que trae el servidor (?e=)
  email.addEventListener('input', function () {
    escrito = true;
    if (err.textContent && !revisar()) avisar('');
  });
  email.addEventListener('blur', function () { if (escrito) avisar(revisar()); });
  if (!window.fetch) return;
  f.addEventListener('submit', function (e) {
    e.preventDefault();
    var mal = revisar();
    if (mal) { avisar(mal); email.focus(); return; }
    avisar('');
    var correo = email.value.trim();
    boton.disabled = true;
    boton.textContent = 'Apuntando…';
    fetch('/api/lista-espera', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: correo, web: f.elements.web ? f.elements.web.value : '' })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { st: r.status, ok: r.ok, d: d }; });
    }).then(function (x) {
      if (x.ok) return hecho(correo);
      if (x.st === 429) return avisar(x.d.error || SIN_RED);
      if (x.st === 400) { avisar(MAL_ESCRITO); return email.focus(); }
      avisar(SIN_RED);
    }).catch(function () {
      avisar(SIN_RED);
    }).then(function () {
      boton.disabled = false;
      boton.textContent = textoBoton;
    });
  });
  function hecho(correo) {
    var p = document.createElement('p'), b = document.createElement('b'), a = document.createElement('a');
    p.className = 'ok';
    b.textContent = correo;
    a.href = '/funciones';
    a.textContent = 'Mientras, mira lo que ya sabe hacer →';
    p.appendChild(document.createTextNode('¡Apuntado! Te escribiremos a '));
    p.appendChild(b);
    p.appendChild(document.createTextNode(' cuando haya sitio. '));
    estado.textContent = '';
    estado.appendChild(p);
    estado.appendChild(a);
    if (cuerpo) cuerpo.hidden = true; else f.hidden = true;
    estado.tabIndex = -1;
    estado.focus();
  }
})();
