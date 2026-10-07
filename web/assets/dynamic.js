import './board.js';
const paths={
  app:{title:'Da ideia à experiência de usar.',description:'Navegação, busca, persistência e integração com o backend. Explore as habilidades que uso para construir aplicativos.',tags:['Kotlin','Flutter','Go','UX'],url:'#laboratorio',label:'Ir ao laboratório',groups:['mobile','backend','database','ux']},
  api:{title:'Uma pergunta vira dados na tela.',description:'A API FastAPI consulta o feed do Google Trends e devolve dados reais para você explorar por país.',tags:['Python','FastAPI','Contratos','Tratamento de erros'],url:'/demos/trends/',label:'Consultar tendências reais',groups:['backend','database','qa','delivery']},
  automation:{title:'Um processo vira um fluxo conectado.',description:'Atendimento, conectores, eventos e tarefas em segundo plano. Conheça o Clycka e as habilidades por trás de suas integrações.',tags:['Webhooks','Workers','OAuth / PKCE','Idempotência'],url:'https://clycka.com/',label:'Conhecer Clycka',groups:['integrations','security','backend','delivery']},
  data:{title:'Dados viram uma decisão melhor.',description:'Explore o projeto de demanda e estoque, com Python, organização de dados, métricas e relatórios.',tags:['pandas','NumPy','Validação temporal','Dashboards'],url:'https://github.com/KarenAngelis/Reinaldo',label:'Explorar projeto de dados',groups:['ai-data','database','business']},
  ux:{title:'Uma interface vira uma experiência.',description:'Jornada, navegação, feedback e clareza. Veja como frontend e UX se encontram no Luniay.',tags:['UX','UX Writing','Acessibilidade','Frontend'],url:'https://luniay.com.br/',label:'Explorar Luniay',groups:['frontend','ux','business']}
};
const chooser=document.querySelector('#scenario-chooser');
let active='app';
function selectScenario(key){
  active=key;const scenario=paths[key];
  document.querySelector('#scenario-title').textContent=scenario.title;
  document.querySelector('#scenario-description').textContent=scenario.description;
  const tags=document.querySelector('#scenario-tags');tags.replaceChildren();
  for(const text of scenario.tags){const tag=document.createElement('span');tag.textContent=text;tags.append(tag);}
  const example=document.querySelector('#scenario-example');example.href=scenario.url;example.textContent=scenario.label;
  if(scenario.url.startsWith('#')){example.removeAttribute('target');}else{example.target='_blank';example.rel='noopener noreferrer';}
  chooser.querySelectorAll('button').forEach(button=>{const selected=button.dataset.scenario===key;button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected));});
  const preview=document.querySelector('#scenario-preview');preview.classList.remove('changed');requestAnimationFrame(()=>preview.classList.add('changed'));
}
chooser.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>selectScenario(button.dataset.scenario)));
document.querySelector('#scenario-skills').addEventListener('click',()=>{
  window.dispatchEvent(new CustomEvent('portfolio-focus',{detail:{ids:paths[active].groups}}));
  document.querySelector('#habilidades').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
});
selectScenario(active);

const reduced=matchMedia('(prefers-reduced-motion: reduce)');
if(!reduced.matches&&'IntersectionObserver' in window){
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('in-view');observer.unobserve(entry.target);}}),{threshold:.07});
  document.querySelectorAll('.section-heading,.lab-card,.site-card,.about').forEach(node=>{node.classList.add('reveal');observer.observe(node);});
}
let framePending=false;
const progress=document.querySelector('#scroll-progress');
window.addEventListener('scroll',()=>{if(framePending)return;framePending=true;requestAnimationFrame(()=>{const range=document.documentElement.scrollHeight-innerHeight;progress.style.width=(range>0?Math.min(100,scrollY/range*100):0)+'%';framePending=false;});},{passive:true});
