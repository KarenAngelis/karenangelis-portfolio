// HTML remains usable while the Kotlin/WebAssembly app starts or recovers from a failure.
(function () {
  'use strict';

  var copy = {
    'pt-BR': {
      subtitle: 'Meu currículo', loading: 'Carregando o app…',
      failure: 'O app não abriu corretamente neste navegador.',
      unsupported: 'Este navegador não oferece o suporte a WebAssembly necessário para abrir o app.',
      slow: 'O app está demorando para abrir. Você pode ler o currículo em HTML ou tentar novamente.',
      fallback: 'Ler currículo em HTML', retry: 'Tentar novamente',
      hint: 'Currículo em HTML disponível a qualquer momento.',
      check: 'App vazio ou sem resposta? Leia o currículo em HTML.',
      offline: 'Você está sem conexão. O app tentará usar os arquivos salvos.',
      offlineFailure: 'Você está sem conexão e o app não abriu. Reconecte para tentar novamente.',
      offlineHint: 'O currículo em HTML pode precisar de conexão.'
    },
    'pt-PT': {
      subtitle: 'O meu currículo', loading: 'A carregar a app…',
      failure: 'A app não abriu corretamente neste navegador.',
      unsupported: 'Este navegador não oferece o suporte a WebAssembly necessário para abrir a app.',
      slow: 'A app está a demorar a abrir. Pode ler o currículo em HTML ou tentar novamente.',
      fallback: 'Ler currículo em HTML', retry: 'Tentar novamente',
      hint: 'Currículo em HTML disponível a qualquer momento.',
      check: 'App vazia ou sem resposta? Leia o currículo em HTML.',
      offline: 'Está sem ligação à Internet. A app tentará usar os ficheiros guardados.',
      offlineFailure: 'Está sem ligação à Internet e a app não abriu. Volte a ligar-se para tentar novamente.',
      offlineHint: 'O currículo em HTML pode precisar de ligação à Internet.'
    },
    'en-US': {
      subtitle: 'My résumé', loading: 'Loading the app…',
      failure: 'The app could not run correctly in this browser.',
      unsupported: 'This browser does not support the WebAssembly features needed to open the app.',
      slow: 'The app is taking a while to open. You can read the HTML résumé or try again.',
      fallback: 'Read the HTML résumé', retry: 'Try again',
      hint: 'The HTML résumé is always available as an alternative.',
      check: 'Blank or unresponsive app? Read the HTML résumé.',
      offline: 'You are offline. The app will try to use saved files.',
      offlineFailure: 'You are offline and the app could not open. Reconnect to try again.',
      offlineHint: 'The HTML résumé may need an Internet connection.'
    },
    'it-IT': {
      subtitle: 'Il mio curriculum', loading: 'Caricamento dell’app…',
      failure: 'L’app non funziona correttamente in questo browser.',
      unsupported: 'Questo browser non supporta le funzionalità WebAssembly necessarie per aprire l’app.',
      slow: 'L’app sta impiegando più tempo del previsto. Puoi leggere il curriculum in HTML o riprovare.',
      fallback: 'Leggi il curriculum in HTML', retry: 'Riprova',
      hint: 'Il curriculum in HTML è sempre disponibile come alternativa.',
      check: 'App vuota o bloccata? Leggi il curriculum in HTML.',
      offline: 'Sei offline. L’app proverà a usare i file salvati.',
      offlineFailure: 'Sei offline e l’app non si è aperta. Riconnettiti per riprovare.',
      offlineHint: 'Il curriculum in HTML potrebbe richiedere una connessione Internet.'
    }
  };
  var requested;
  try { requested = new URLSearchParams(location.search).get('lang'); } catch (_) {}
  var language = Object.prototype.hasOwnProperty.call(copy, requested) ? requested : 'pt-BR';
  var text = copy[language];
  var splash = document.querySelector('#splash');
  var status = document.querySelector('#splash-status');
  var root = document.querySelector('#app-root');
  var hint = document.querySelector('#app-hint');
  var link = document.querySelector('#resume-link');
  var retry = document.querySelector('#app-retry');
  var state = 'loading';
  var delayed = false;
  var failureReason = 'failure';
  var poll;
  var deadline;

  document.documentElement.lang = language;
  document.querySelector('#splash-subtitle').textContent = text.subtitle;
  link.href = '/curriculo/?lang=' + language;
  link.textContent = text.fallback;
  retry.textContent = text.retry;

  function updateText() {
    var offline = navigator.onLine === false;
    hint.textContent = offline ? text.offlineHint : (delayed ? text.check : text.hint);
    status.textContent = state === 'failed'
      ? (offline && failureReason !== 'unsupported' ? text.offlineFailure : text[failureReason])
      : (offline ? text.offline : text.loading);
  }

  function fail(reason) {
    if (state === 'failed') return;
    state = 'failed';
    failureReason = reason || 'failure';
    clearTimeout(poll);
    clearTimeout(deadline);
    // Keep the shell in the DOM so a later runtime failure can restore it.
    splash.hidden = false;
    splash.classList.add('failed');
    root.hidden = true;
    retry.hidden = false;
    updateText();
  }

  function watch() {
    if (state !== 'loading') return;
    var canvas = root.shadowRoot && root.shadowRoot.querySelector('canvas');
    if (canvas) {
      // Canvas creation is NOT proof of a rendered frame. Only reveal the app;
      // keep the HTML escape route, error handlers and timeout guidance active.
      state = 'presenting';
      splash.hidden = true;
      canvas.addEventListener('webglcontextlost', function () { fail(); });
      canvas.addEventListener('contextlost', function () { fail(); });
      return;
    }
    poll = setTimeout(watch, 100);
  }

  window.addEventListener('error', function (event) {
    // Resource errors for analytics, icons, etc. do not mean the Kotlin app failed.
    if (event.target && event.target !== window) {
      if (event.target.id === 'resume-bundle') fail();
      return;
    }
    if (event.filename && /\/assets\/track\.js(?:[?#]|$)/.test(event.filename)) return;
    fail();
  }, true);
  window.addEventListener('unhandledrejection', function () { fail(); });
  window.addEventListener('offline', updateText);
  window.addEventListener('online', updateText);
  // A full reload resets the Wasm runtime without deleting the offline cache.
  retry.addEventListener('click', function () { location.reload(); });
  updateText();

  if (typeof WebAssembly !== 'object' || typeof WebAssembly.instantiate !== 'function') {
    fail('unsupported');
  } else {
    deadline = setTimeout(function () {
      if (state === 'failed') return;
      if (state === 'loading') { fail('slow'); return; }
      // There is no first-frame signal from this bundle. Do not cover a healthy
      // app or claim it rendered: provide a persistent, non-blocking escape hint.
      delayed = true;
      updateText();
    }, 20000);
    watch();
    var bundle = document.createElement('script');
    bundle.id = 'resume-bundle';
    bundle.src = 'resume-app.js';
    bundle.addEventListener('error', function () { fail(); });
    document.body.appendChild(bundle);
  }

  // Cache support is optional. Failure to register must not break the app.
  // Do not prune older Wasm files based only on canvas creation: a failed update
  // must not remove potentially useful cached assets.
  if ('serviceWorker' in navigator) {
    try { navigator.serviceWorker.register('sw.js').catch(function () {}); } catch (_) {}
  }
}());
