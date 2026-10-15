import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';

const shellURL = new URL('../web/app/shell.js', import.meta.url);
const source = await readFile(shellURL, 'utf8');
const html = await readFile(new URL('../web/app/index.html', import.meta.url), 'utf8');

function eventTarget(extra = {}) {
  const listeners = new Map();
  return Object.assign({
    addEventListener(type, callback) {
      const callbacks = listeners.get(type) || [];
      callbacks.push(callback);
      listeners.set(type, callbacks);
    },
    emit(type, event = {}) {
      for (const callback of listeners.get(type) || []) callback(event);
    }
  }, extra);
}

function harness({ wasm = true, lang = '', offline = false, serviceWorker } = {}) {
  const elements = new Map();
  for (const id of ['splash', 'splash-status', 'app-root', 'app-hint', 'resume-link', 'app-retry', 'splash-subtitle']) {
    const classes = new Set();
    elements.set('#' + id, eventTarget({
      id, textContent: '', hidden: id === 'app-retry', shadowRoot: null,
      classList: { add: value => classes.add(value), contains: value => classes.has(value) }
    }));
  }
  let now = 0;
  let nextTimer = 1;
  let reloads = 0;
  const timers = new Map();
  const scripts = [];
  const window = eventTarget();
  const navigator = { onLine: !offline };
  if (serviceWorker) navigator.serviceWorker = serviceWorker;
  const document = {
    documentElement: {},
    querySelector: selector => elements.get(selector),
    createElement: tagName => eventTarget({ tagName: tagName.toUpperCase() }),
    body: { appendChild: element => scripts.push(element) }
  };
  vm.runInNewContext(source, {
    document, window, navigator, URLSearchParams,
    location: { search: lang ? '?lang=' + encodeURIComponent(lang) : '', reload() { reloads += 1; } },
    WebAssembly: wasm ? { instantiate() {} } : undefined,
    setTimeout(callback, delay) {
      const id = nextTimer++;
      timers.set(id, { callback, at: now + delay });
      return id;
    },
    clearTimeout(id) { timers.delete(id); }
  }, { filename: 'shell.js' });

  function advance(ms) {
    const end = now + ms;
    while (timers.size) {
      const [id, timer] = [...timers].sort((a, b) => a[1].at - b[1].at)[0];
      if (timer.at > end) break;
      now = timer.at;
      timers.delete(id);
      timer.callback();
    }
    now = end;
  }
  function exposeCanvas() {
    const canvas = eventTarget();
    elements.get('#app-root').shadowRoot = { querySelector: selector => selector === 'canvas' ? canvas : null };
    advance(100);
    return canvas;
  }
  return {
    get: id => elements.get('#' + id), window, navigator, document, scripts,
    advance, exposeCanvas, reloads: () => reloads, pendingTimers: () => timers.size
  };
}

function assertFailed(app) {
  assert.equal(app.get('splash').hidden, false);
  assert.equal(app.get('splash').classList.contains('failed'), true);
  assert.equal(app.get('app-root').hidden, true);
  assert.equal(app.get('app-retry').hidden, false);
  assert.equal(app.get('resume-link').hidden, false);
}

test('the HTML exit exists before JavaScript, and the Wasm bundle is conditionally loaded', () => {
  assert.match(html, /<a id="resume-link" href="\/curriculo\/\?lang=pt-BR">/);
  assert.match(html, /<noscript>/);
  assert.doesNotMatch(html, /<script[^>]+src="resume-app\.js"/);
});

test('supported browsers load Kotlin while keeping the HTML résumé link usable', () => {
  const app = harness();
  assert.equal(app.scripts.length, 1);
  assert.equal(app.scripts[0].src, 'resume-app.js');
  assert.equal(app.get('resume-link').href, '/curriculo/?lang=pt-BR');
  assert.equal(app.get('splash').hidden, false);
  assert.equal(app.get('app-retry').hidden, true);
});

test('unsupported WebAssembly shows an alternative without downloading the app', () => {
  const app = harness({ wasm: false });
  assertFailed(app);
  assert.match(app.get('splash-status').textContent, /WebAssembly/);
  assert.equal(app.scripts.length, 0);
  assert.equal(app.pendingTimers(), 0);
});

test('early runtime failure remains readable and stops the loading timer', () => {
  const app = harness();
  app.window.emit('error', { target: app.window, filename: 'resume-app.js', message: 'getParameter' });
  assertFailed(app);
  assert.equal(app.pendingTimers(), 0);
  app.exposeCanvas();
  assertFailed(app);
});

test('a failed bundle download shows a retry and the persistent HTML link', () => {
  const app = harness();
  app.scripts[0].emit('error');
  assertFailed(app);
});

test('a late exception after canvas detection restores the failure screen', () => {
  const app = harness();
  app.exposeCanvas();
  assert.equal(app.get('splash').hidden, true);
  assert.ok(app.pendingTimers() > 0, 'canvas creation must not cancel timeout guidance');
  app.advance(60000);
  app.window.emit('error', { target: app.window, filename: 'resume-app.js' });
  assertFailed(app);
});

test('unhandled promise rejections are caught both before and after canvas detection', () => {
  for (const withCanvas of [false, true]) {
    const app = harness();
    if (withCanvas) app.exposeCanvas();
    app.window.emit('unhandledrejection', { reason: new Error('WebGL failed') });
    assertFailed(app);
  }
});

test('lost graphics contexts retain a route out of the app', () => {
  for (const type of ['webglcontextlost', 'contextlost']) {
    const app = harness();
    app.exposeCanvas().emit(type);
    assertFailed(app);
  }
});

test('a startup timeout without a canvas fails with useful guidance', () => {
  const app = harness();
  app.advance(20000);
  assertFailed(app);
  assert.match(app.get('splash-status').textContent, /demorando/);
});

test('canvas presence does not certify success; the timeout hint never covers a healthy app', () => {
  const app = harness();
  app.exposeCanvas();
  app.advance(20000);
  assert.equal(app.get('splash').hidden, true);
  assert.equal(app.get('app-root').hidden, false);
  assert.match(app.get('app-hint').textContent, /vazio ou sem resposta/);
  assert.equal(app.get('resume-link').hidden, false);
});

test('offline mode attempts cached app assets and explains the HTML network limitation', () => {
  const app = harness({ offline: true });
  assert.equal(app.scripts.length, 1);
  assert.match(app.get('splash-status').textContent, /arquivos salvos/);
  assert.match(app.get('app-hint').textContent, /precisar de conexão/);
  app.exposeCanvas();
  app.advance(20000);
  assert.equal(app.get('splash').hidden, true);
  app.window.emit('unhandledrejection');
  assertFailed(app);
  assert.match(app.get('splash-status').textContent, /sem conexão/);
  app.navigator.onLine = true;
  app.window.emit('online');
  assert.match(app.get('splash-status').textContent, /não abriu corretamente/);
});

test('retry reloads the runtime without clearing offline data', () => {
  const app = harness();
  app.window.emit('unhandledrejection');
  app.get('app-retry').emit('click');
  assert.equal(app.reloads(), 1);
  assert.doesNotMatch(source, /caches\.delete|\.unregister\(/);
});

test('all four languages translate the exit, loading, failure and retry states', () => {
  const expected = {
    'pt-BR': ['Ler currículo em HTML', 'Carregando o app…', 'Tentar novamente'],
    'pt-PT': ['Ler currículo em HTML', 'A carregar a app…', 'Tentar novamente'],
    'en-US': ['Read the HTML résumé', 'Loading the app…', 'Try again'],
    'it-IT': ['Leggi il curriculum in HTML', 'Caricamento dell’app…', 'Riprova']
  };
  for (const [lang, [link, loading, retry]] of Object.entries(expected)) {
    const app = harness({ lang });
    assert.equal(app.document.documentElement.lang, lang);
    assert.equal(app.get('resume-link').href, '/curriculo/?lang=' + lang);
    assert.equal(app.get('resume-link').textContent, link);
    assert.equal(app.get('splash-status').textContent, loading);
    app.window.emit('unhandledrejection');
    assertFailed(app);
    assert.ok(app.get('splash-status').textContent.length > 20);
    assert.equal(app.get('app-retry').textContent, retry);
  }
});

test('invalid language values safely fall back to Portuguese', () => {
  for (const lang of ['unknown', '__proto__', 'constructor', '<script>']) {
    const app = harness({ lang });
    assert.equal(app.document.documentElement.lang, 'pt-BR');
    assert.equal(app.get('resume-link').href, '/curriculo/?lang=pt-BR');
  }
});

test('unrelated resource failures and service-worker denial do not block the app', () => {
  const app = harness({ serviceWorker: { register() { throw new Error('Access denied'); } } });
  app.window.emit('error', { target: { id: 'favicon' } });
  app.window.emit('error', { target: app.window, filename: 'https://example.test/assets/track.js' });
  app.exposeCanvas();
  assert.equal(app.get('splash').hidden, true);
  assert.equal(app.get('app-root').hidden, false);
});

test('published shell resources match the Kotlin build inputs byte for byte', async () => {
  for (const name of ['shell.js', 'shell.css', 'index.html']) {
    const published = await readFile(new URL('../web/app/' + name, import.meta.url), 'utf8');
    const buildInput = await readFile(new URL('../apps/resume-compose/shared/src/wasmJsMain/resources/' + name, import.meta.url), 'utf8');
    assert.equal(buildInput, published, name);
  }
});
