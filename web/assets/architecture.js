// Arquitetura clicável e sinais de engenharia: decisões do projeto e números tirados do próprio repositório.
import {sources} from './code-viewer.js';
const nodes={
  site:{label:'NAVEGADOR',title:'Site estático, sem framework',what:'HTML, CSS e módulos ES nativos. Não há bundler nem etapa de build para a página.',why:'A página é conteúdo com pontos de interação. Um framework custaria mais para carregar do que entregaria aqui.',cost:'O DOM é atualizado à mão e a troca de idioma usa um catálogo próprio. Em uma aplicação com muito estado eu usaria React ou Next.js.',code:'i18n'},
  proxy:{label:'BORDA',title:'Caddy na borda',what:'O Caddy emite o certificado, serve os arquivos e encaminha /api/news para o FastAPI e /api/profile para o Go.',why:'Uma única origem para site e APIs: sem CORS em produção e com os mesmos cabeçalhos de segurança em tudo.',cost:'Tudo roda em uma VPS. É simples e barato de operar, mas não tem redundância.',code:'infra',file:'Caddyfile'},
  app:{label:'/app',title:'Um app, duas plataformas',what:'Telas, navegação, busca e cliente da API escritos uma vez em Compose Multiplatform e compilados para Android e WebAssembly.',why:'Mostrar o mesmo código rodando no celular e no navegador, sem recriar as telas em HTML.',cost:'O WebAssembly pesa: por isso o app abre em outra aba e só é baixado quando alguém pede. Ele traz o currículo embutido e continua funcionando sem rede.',code:'resume-app'},
  news:{label:'/api/news',title:'FastAPI para notícias',what:'Consulta o RSS do Google Notícias e devolve JSON. Parâmetros fora do contrato recebem 422, e falha da fonte vira 502 com explicação.',why:'O contrato fica no próprio código: a validação e a documentação em /docs saem dos tipos.',cost:'O cache de 5 minutos fica na memória do processo. Com mais de uma instância eu trocaria por Redis.',code:'trends-api'},
  resume:{label:'/api/profile',title:'Go só com a biblioteca padrão',what:'Lê o currículo ao iniciar e responde GET /api/profile, com lista de origens permitidas e tempos limite. A imagem final parte de scratch e roda sem privilégios.',why:'Go entrou como laboratório deste portfólio: um serviço pequeno é o lugar certo para aprender a linguagem com teste e deploy de verdade.',cost:'Mudar o currículo exige novo deploy. Em troca, não há banco de dados nem estado para manter.',code:'resume-api'},
  data:{label:'DADOS',title:'Uma fonte para três consumidores',what:'O mesmo profile.json alimenta o site, a API Go e o app Kotlin.',why:'O currículo é corrigido em um lugar e aparece igual em todos.',cost:'Mudar o formato afeta três leitores. O teste de contrato da API e a validação feita pelo app seguram essa mudança.',code:'resume-app',file:'Profile.kt'},
  ci:{label:'ENTREGA',title:'Verificação a cada push',what:'O GitHub Actions confere o site, roda os testes do FastAPI e do Go e compila o Kotlin. Outro fluxo gera o APK e testa em um emulador.',why:'Cada serviço é pequeno, mas todos leem os mesmos dados. A verificação automática avisa quando um quebra o outro.',cost:'A publicação na VPS ainda é acionada manualmente, com Docker Compose.',code:'infra',file:'check.yml'}
};
const map=document.querySelector('#arch-map'),title=document.querySelector('#arch-title'),label=document.querySelector('#arch-label'),code=document.querySelector('#arch-code');
function select(key){
  const item=nodes[key];
  map.querySelectorAll('[data-node]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.node===key)));
  label.textContent=item.label;title.textContent=item.title;
  for(const field of ['what','why','cost'])document.querySelector('#arch-'+field).textContent=item[field];
  code.dataset.code=item.code;if(item.file)code.dataset.file=item.file;else delete code.dataset.file;
  const detail=document.querySelector('#arch-detail');detail.classList.remove('changed');requestAnimationFrame(()=>detail.classList.add('changed'));
}
// Em telas estreitas o detalhe fica abaixo do mapa: leva a pessoa até ele depois do clique.
map.querySelectorAll('[data-node]').forEach(button=>button.addEventListener('click',()=>{
  select(button.dataset.node);const detail=document.querySelector('#arch-detail');
  if(detail.getBoundingClientRect().top>innerHeight*.7)detail.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
}));
select('site');

const set=(id,value)=>{document.querySelector(id).textContent=value;};
sources().then(({facts})=>{
  set('#signal-tests',facts.pythonTests+facts.goTests);set('#signal-dependencies',facts.npmDependencies);set('#signal-locales',facts.locales);
  set('#signal-wasm',(facts.wasmBytes/1048576).toFixed(1).replace('.',','));
}).catch(()=>{});
// Medido no navegador de quem está lendo, depois que a página termina de carregar.
function measure(){
  const [navigation]=performance.getEntriesByType('navigation');if(!navigation)return;
  const resources=performance.getEntriesByType('resource').filter(entry=>new URL(entry.name).origin===location.origin);
  const bytes=[navigation,...resources].reduce((total,entry)=>total+(entry.transferSize||entry.encodedBodySize||0),0);
  set('#signal-interactive',Math.round(navigation.domInteractive));set('#signal-requests',resources.length+1);set('#signal-weight',Math.round(bytes/1024));
}
if(document.readyState==='complete')setTimeout(measure,0);else window.addEventListener('load',()=>setTimeout(measure,0));
