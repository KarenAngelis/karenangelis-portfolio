// Contagem de visitas e cliques, sem cookies e sem dados pessoais. Só nomes fixos são enviados; nada do que a pessoa digita.
const local=['localhost','127.0.0.1'].includes(location.hostname),api=(local?'http://127.0.0.1:8001':'')+'/api/stats/event';
// Respeita quem pediu para não ser rastreado.
const optedOut=navigator.doNotTrack==='1'||navigator.globalPrivacyControl===true;
// O idioma escolhido fica na URL ou no navegador; o atributo lang da página só muda depois que as traduções carregam.
function language(){let saved;try{saved=localStorage.getItem('portfolio-language');}catch{}const selected=new URLSearchParams(location.search).get('lang')||saved;return ['pt-BR','pt-PT','en-US','it-IT'].includes(selected)?selected:'pt-BR';}
function send(type,name=''){
  if(optedOut)return;
  let referrer='';try{const host=new URL(document.referrer).hostname;if(host!==location.hostname)referrer=host;}catch{}
  const body=JSON.stringify({type,name,path:location.pathname,referrer,lang:language(),device:matchMedia('(max-width: 700px)').matches?'mobile':'desktop'});
  // text/plain evita a pré-verificação de CORS no ambiente local; keepalive deixa o envio terminar mesmo saindo da página.
  fetch(api,{method:'POST',body,keepalive:true,headers:{'Content-Type':'text/plain'}}).catch(()=>{});
}
const slug=value=>String(value).toLowerCase().normalize('NFD').replace(/[^a-z0-9./-]+/g,'-').replace(/^-+|-+$/g,'').slice(0,40);
const terminalCommands=['help','whoami','skills','projects','curl','ls','cat','tests','stack','open','lang','contact','history','clear','sudo'];
const fixedButtons={connect:'curriculo:consultar-api',load:'noticias:buscar','refresh-profile':'curriculo:atualizar','reset-board':'quadro:limpar','reset-catalog':'habilidades:limpar-filtro','scenario-skills':'habilidades:cenario','technology-motion':'habilidades:movimento'};
// Traduz o elemento clicado em um nome estável, a partir de atributos do próprio HTML.
function describe(element){
  const data=element.dataset;
  if(data.track)return data.track;
  if(data.code)return 'codigo:'+slug(data.code);
  if(data.command)return 'terminal:'+slug(data.command.split(' ')[0]);
  if(data.preset)return 'console:quebrar:'+slug(data.preset);
  if(data.endpoint)return 'console:rota:'+slug(data.endpoint);
  if(data.node)return 'arquitetura:'+slug(data.node);
  if(data.scenario)return 'caminho:'+slug(data.scenario);
  if(data.filter)return 'projetos:filtro:'+slug(data.filter);
  if(data.try)return 'quadro:'+slug(data.try);
  if(data.locale)return 'idioma:'+slug(data.locale);
  if(data.tab)return 'curriculo:aba:'+slug(data.tab);
  if(data.topic)return 'noticias:tema:'+slug(data.topic);
  if(element.tagName==='BUTTON'){
    if(fixedButtons[element.id])return fixedButtons[element.id];
    if(element.matches('.company-next'))return 'empresas:proximas';
    if(element.matches('.company-previous'))return 'empresas:anteriores';
    if(element.matches('.technology'))return 'habilidade:'+slug(element.getAttribute('aria-label')?.split(' — ')[0]||'outro');
  }
  if(element.matches('.lab-card'))return 'testar:'+(element.matches('.app-card')?'app':'noticias');
  if(element.tagName==='A'){
    const url=new URL(element.href,location.href);
    if(url.hostname==='wa.me')return 'contato:whatsapp';
    if(url.hostname.endsWith('linkedin.com'))return 'contato:linkedin';
    if(url.origin!==location.origin)return 'link:'+slug(url.hostname+(url.hostname==='github.com'?url.pathname.split('/').slice(0,3).join('/'):''));
    if(url.pathname!==location.pathname)return 'pagina:'+slug(url.pathname);
    if(url.hash)return 'secao:'+slug(url.hash.slice(1));
  }
  return '';
}
document.addEventListener('click',event=>{
  const element=event.target.closest('[data-track],[data-code],[data-command],[data-preset],[data-endpoint],[data-node],[data-scenario],[data-filter],[data-try],[data-locale],[data-tab],[data-topic],button,a[href]');
  const name=element&&describe(element);if(name)send('click',name);
},true);
document.addEventListener('submit',event=>{
  if(event.target.id==='console-form')send('click','console:enviar');
  if(event.target.id==='terminal-form'){const command=event.target.querySelector('input').value.trim().split(/\s+/)[0].toLowerCase();if(command)send('click','terminal:'+(terminalCommands.includes(command)?command:'outro'));}
},true);
send('view');
