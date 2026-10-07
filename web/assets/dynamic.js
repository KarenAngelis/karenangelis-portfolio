const paths={
  app:{title:'Uma ideia vira um aplicativo.',description:'Telas, navegação, estado e integração com serviços. Experimente o currículo em Kotlin conectado à API Go, e conheça o Luniay web/mobile.',tags:['Flutter / Dart','Kotlin','Go','APIs','UX'],url:'/demos/kotlin/',label:'Abrir app do currículo',groups:['mobile','backend','database','ux']},
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
  const example=document.querySelector('#scenario-example');example.href=scenario.url;example.textContent=scenario.label+' ↗';
  chooser.querySelectorAll('button').forEach(button=>{const selected=button.dataset.scenario===key;button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected));});
  const preview=document.querySelector('#scenario-preview');preview.classList.remove('changed');requestAnimationFrame(()=>preview.classList.add('changed'));
}
chooser.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>selectScenario(button.dataset.scenario)));
document.querySelector('#scenario-skills').addEventListener('click',()=>{
  window.dispatchEvent(new CustomEvent('portfolio-focus',{detail:{ids:paths[active].groups}}));
  document.querySelector('#habilidades').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
});
selectScenario(active);

const tasks=[{title:'Criar a interface',stage:0},{title:'Conectar a API',stage:1},{title:'Validar os testes',stage:0}];
const stages=['A fazer','Em andamento','Concluído'];
const board=document.querySelector('#demo-board');
function renderBoard(){
  board.replaceChildren();
  stages.forEach((label,index)=>{
    const column=document.createElement('section');column.className='board-column';column.setAttribute('aria-label',label);
    const heading=document.createElement('h4');heading.textContent=label+' · '+tasks.filter(t=>t.stage===index).length;column.append(heading);
    for(const task of tasks.filter(t=>t.stage===index)){
      const card=document.createElement('div');card.className='board-task';const title=document.createElement('span');title.textContent=task.title;card.append(title);
      if(index<2){const button=document.createElement('button');button.type='button';button.textContent='Avançar →';button.setAttribute('aria-label',`Mover ${task.title} para ${stages[index+1]}`);button.addEventListener('click',()=>{task.stage++;renderBoard();});card.append(button);}else{const done=document.createElement('small');done.textContent='✓ Concluído';card.append(done);}
      column.append(card);
    }
    board.append(column);
  });
  const count=tasks.filter(t=>t.stage===2).length;document.querySelector('#board-status').textContent=count===tasks.length?'Tudo concluído. Você acabou de usar uma interface com estado e feedback.':`${count} de ${tasks.length} tarefas concluídas. Avance uma tarefa para experimentar.`;
}
document.querySelector('#reset-board').addEventListener('click',()=>{tasks.forEach(t=>t.stage=0);renderBoard();});renderBoard();

const reduced=matchMedia('(prefers-reduced-motion: reduce)');
if(!reduced.matches&&'IntersectionObserver' in window){
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('in-view');observer.unobserve(entry.target);}}),{threshold:.07});
  document.querySelectorAll('.section-heading,.lab-card,.site-card,.about').forEach(node=>{node.classList.add('reveal');observer.observe(node);});
}
let framePending=false;
const progress=document.querySelector('#scroll-progress');
window.addEventListener('scroll',()=>{if(framePending)return;framePending=true;requestAnimationFrame(()=>{const range=document.documentElement.scrollHeight-innerHeight;progress.style.width=(range>0?Math.min(100,scrollY/range*100):0)+'%';framePending=false;});},{passive:true});
