// Service worker do app: permite abrir o currículo sem rede depois da primeira visita.
// Os .wasm têm hash no nome e nunca mudam: cache primeiro. O resto: rede primeiro, cache como reserva.
const CACHE='resume-app-v1';
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==location.origin||!url.pathname.startsWith('/app/')&&url.pathname!=='/assets/favicon.svg')return;
  const store=response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(url.pathname,copy));}return response;};
  if(url.pathname.endsWith('.wasm'))event.respondWith(caches.match(url.pathname).then(cached=>cached||fetch(request).then(store)));
  else event.respondWith(fetch(request).then(store).catch(()=>caches.match(url.pathname).then(cached=>cached||Response.error())));
});
self.addEventListener('message',event=>{
  const keep=event.data?.keep;if(!Array.isArray(keep)||!keep.length)return;
  event.waitUntil(caches.open(CACHE).then(cache=>cache.keys().then(keys=>Promise.all(keys.filter(key=>{const path=new URL(key.url).pathname;return path.endsWith('.wasm')&&!keep.includes(path);}).map(key=>cache.delete(key))))));
});
