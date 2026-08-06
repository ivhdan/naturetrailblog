/* ------------------------------------------------------------------
   scheda.js — carica la scheda dell'escursione dentro il post.

   Nel post di Blogger si incolla soltanto:

     <div data-scheda="pian-fum"></div>
     <script src="https://ivhdan.github.io/naturetrailblog/scheda.js"></script>

   dove "pian-fum" è il nome del file in schede/, senza estensione.
   Da quel momento ogni modifica alla scheda nel repository si riflette
   sul post senza doverlo riaprire.
   ------------------------------------------------------------------ */
(function () {
  var BASE = 'https://ivhdan.github.io/naturetrailblog';

  function avviso(testo, url) {
    var p = document.createElement('p');
    p.style.cssText = 'font:12px ui-monospace,monospace;color:#16211d99;' +
                      'border:1px dashed #16211d29;padding:18px;text-align:center';
    p.textContent = testo + ' ';
    if (url) {
      var a = document.createElement('a');
      a.href = url;
      a.textContent = 'apri la scheda';
      a.style.color = '#1c6e8c';
      p.appendChild(a);
    }
    return p;
  }

  function carica(contenitore) {
    var nome = contenitore.getAttribute('data-scheda');
    if (!nome) return;
    var url = BASE + '/schede/' + nome + '.html';

    contenitore.appendChild(avviso('Caricamento della scheda…'));

    fetch(url, { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        contenitore.innerHTML = html;
      })
      .catch(function () {
        contenitore.innerHTML = '';
        contenitore.appendChild(avviso(
          'Scheda momentaneamente non raggiungibile.', url));
      });
  }

  function avvia() {
    var contenitori = document.querySelectorAll('[data-scheda]');
    for (var i = 0; i < contenitori.length; i++) carica(contenitori[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', avvia);
  } else {
    avvia();
  }
})();
