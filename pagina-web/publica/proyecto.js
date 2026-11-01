/* Botones «Copiar» de /proyecto: copian el texto del bloque indicado; si el navegador no deja, lo dejan seleccionado. */
(function () {
  function seleccionar(el, b) {
    var r = document.createRange(); r.selectNodeContents(el);
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    b.textContent = 'Seleccionado: cópialo con el menú del móvil';
  }
  document.querySelectorAll('[data-copiar]').forEach(function (b) {
    var original = b.textContent;
    b.addEventListener('click', function () {
      var el = document.getElementById(b.getAttribute('data-copiar'));
      if (!el) return;
      var texto = el.innerText.trim();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(texto).then(function () {
          b.textContent = 'Copiado \u2713';
          setTimeout(function () { b.textContent = original; }, 2000);
        }, function () { seleccionar(el, b); });
      } else {
        seleccionar(el, b);
      }
    });
  });
})();
