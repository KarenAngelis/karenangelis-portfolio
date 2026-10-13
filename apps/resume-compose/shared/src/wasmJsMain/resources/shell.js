// Casca do app: idioma, tela de abertura enquanto o WebAssembly carrega e uso offline depois de instalado.
const copy={
  'pt-BR':['Meu currículo','Carregando o app…','O app não abriu neste navegador.','Abrir a versão web'],
  'pt-PT':['O meu currículo','A carregar a app…','A app não abriu neste navegador.','Abrir a versão web'],
  'en-US':['My résumé','Loading the app…','The app could not start in this browser.','Open the web version'],
  'it-IT':['Il mio curriculum','Caricamento dell’app…','L’app non si è aperta in questo browser.','Apri la versione web']
};
const requested=new URLSearchParams(location.search).get('lang'),language=copy[requested]?requested:'pt-BR';
document.documentElement.lang=language;
const [subtitle,loading,failure,fallback]=copy[language];
const splash=document.querySelector('#splash'),status=document.querySelector('#splash-status'),root=document.querySelector('#app-root');
document.querySelector('#splash-subtitle').textContent=subtitle;status.textContent=loading;
let settled=false;
function fail(){
  if(settled)return;settled=true;splash.classList.add('failed');status.textContent=failure;
  const link=document.createElement('a');link.href='/demos/curriculo/?lang='+language;link.textContent=fallback;splash.append(link);
}
// Com o app na tela, avisa quais .wasm esta versão usa, para o service worker apagar os de versões antigas.
function prune(){
  const keep=performance.getEntriesByType('resource').map(entry=>new URL(entry.name).pathname).filter(path=>path.endsWith('.wasm'));
  navigator.serviceWorker?.ready.then(registration=>registration.active.postMessage({keep})).catch(()=>{});
}
// O Compose desenha em um canvas dentro do shadow DOM de #app-root; quando ele existe, o app está na tela.
function watch(){
  if(settled)return;
  if(root.shadowRoot?.querySelector('canvas')){settled=true;prune();setTimeout(()=>{splash.classList.add('done');setTimeout(()=>splash.remove(),400);},350);return;}
  requestAnimationFrame(watch);
}
if(typeof WebAssembly==='object'){watch();setTimeout(fail,45000);}else fail();
if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
