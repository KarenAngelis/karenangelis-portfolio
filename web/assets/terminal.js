// Terminal do topo: comandos de verdade sobre os dados do portfólio e as APIs publicadas.
import {sources,openCode} from './code-viewer.js';
import {findEndpoint,request} from './api.js';
import {setLocale} from './i18n.js';
const terminal=document.querySelector('#terminal'),log=document.querySelector('#terminal-log'),form=document.querySelector('#terminal-form'),input=document.querySelector('#terminal-input');
const history=[];let cursor=0,profileCache;
const profile=()=>profileCache??=fetch('/data/profile.json').then(response=>{if(!response.ok)throw new Error();return response.json();});
// text() passa pelo catálogo de idiomas da página; raw() fica como foi escrito (comandos, nomes, JSON).
function text(value,className=''){const span=document.createElement('span');span.textContent=value;if(className)span.className=className;return span;}
function raw(value,className=''){const span=text(value,className);span.dataset.noTranslate='';return span;}
function link(label,url){const anchor=document.createElement('a');anchor.textContent=label;anchor.href=url;if(!url.startsWith('#')){anchor.target='_blank';anchor.rel='noopener noreferrer';}return anchor;}
function print(...parts){
  const line=document.createElement('div');line.className='term-line';line.append(...parts.flatMap(part=>[part,' ']));log.append(line);
  while(log.children.length>160)log.firstElementChild.remove();
  log.scrollTop=log.scrollHeight;
}
const places={
  app:['Currículo em app','/app/?version=kotlin'],news:['Busca de notícias','/demos/trends/'],console:['Console de API','#console'],arquitetura:['Como este site foi feito','#arquitetura'],
  github:['GitHub','https://github.com/KarenAngelis'],linkedin:['LinkedIn','https://www.linkedin.com/in/karen-angelis/'],whatsapp:['WhatsApp','https://wa.me/5547997336808']
};
const locales=['pt-BR','pt-PT','en-US','it-IT'];
const commands={
  help:{about:'lista os comandos',run(){for(const [name,command] of Object.entries(commands))if(command.about)print(raw((command.usage||name).padEnd(18),'term-key'),text(command.about));}},
  whoami:{about:'quem está por trás do código',async run(){const data=await profile();print(raw(data.fullName,'term-key'));print(text(data.role));print(text(data.summary,'term-muted'));}},
  skills:{usage:'skills [term]',about:'áreas e competências',async run(args){
    const data=await profile(),needle=args.join(' ').toLowerCase();
    if(!needle){for(const group of data.skillGroups)print(raw(String(group.items.length).padStart(2),'term-key'),text(group.title));print(text('Filtre por termo. Exemplo:','term-muted'),raw('skills fastapi','term-key'));return;}
    const found=data.skillGroups.map(group=>({group,items:group.title.toLowerCase().includes(needle)||group.id===needle?group.items:group.items.filter(item=>item.toLowerCase().includes(needle))})).filter(entry=>entry.items.length);
    if(!found.length){print(text('Nenhuma competência com esse termo.'));return;}
    for(const {group,items} of found){print(text(group.title,'term-key'));print(text(items.join(' · ')));}
    print(link('Abrir o repertório completo','#habilidades'));
  }},
  projects:{about:'projetos e onde ver cada um',async run(){const data=await profile();data.projects.forEach((project,index)=>print(raw(String(index+1).padStart(2,'0'),'term-muted'),link(project.name,project.url),text(project.description,'term-muted')));}},
  curl:{usage:'curl <path>',about:'requisição real às minhas APIs',async run(args){
    const verb=args.includes('-X')&&String(args[args.indexOf('-X')+1]).toUpperCase()==='POST'?'POST':'GET',target=args.filter((arg,index)=>!arg.startsWith('-')&&args[index-1]!=='-X')[0]||'';
    let url;try{url=new URL(target.replace(/^['"]|['"]$/g,''),location.origin);}catch{}
    const key=url&&findEndpoint(url.pathname);
    if(!key){print(text('Rota fora deste portfólio. Rotas disponíveis:'));print(raw('/api/profile   /api/news?q=go&limit=3   /openapi.json','term-key'));return;}
    const result=await request(key,Object.fromEntries(url.searchParams),verb);
    print(raw(`HTTP ${result.status} · ${result.ms} ms · ${result.bytes} B · ${result.service}`,result.status<300?'term-ok':'term-warn'));
    const lines=(result.json===undefined?result.text:JSON.stringify(result.json,null,2)).split('\n');
    print(raw(lines.slice(0,12).join('\n'),'term-pre'));
    if(lines.length>12)print(text('Resposta cortada aqui.','term-muted'),link('Ver completa no console de API','#console'));
  }},
  ls:{about:'código-fonte disponível nesta página',async run(){const data=await sources();for(const [id,bundle] of Object.entries(data.bundles))print(raw(id.padEnd(12),'term-key'),raw(bundle.files.map(file=>file.name).join('  '),'term-muted'));print(text('Abra um arquivo. Exemplo:','term-muted'),raw('cat main.go','term-key'));}},
  cat:{usage:'cat <file>',about:'abre um arquivo no visualizador de código',async run(args){
    const data=await sources(),name=args[0]||'';
    const id=data.bundles[name]?name:Object.keys(data.bundles).find(key=>data.bundles[key].files.some(file=>file.name===name||file.path===name));
    if(!id){print(text('Arquivo não encontrado. Use ls para ver a lista.'));return;}
    await openCode(id,data.bundles[name]?0:name.split('/').pop());print(text('Aberto no visualizador de código.','term-ok'));
  }},
  tests:{about:'testes automatizados deste repositório',async run(){const {facts}=await sources();print(raw(String(facts.pythonTests).padStart(2),'term-key'),text('testes da API FastAPI'));print(raw(String(facts.goTests).padStart(2),'term-key'),text('teste de contrato da API Go'));print(text('Rodam no GitHub Actions a cada push.','term-muted'));}},
  stack:{about:'como este site foi feito',run(){
    print(raw('site     ','term-key'),text('HTML, CSS e módulos ES, sem framework'));print(raw('app      ','term-key'),text('Kotlin e Compose Multiplatform em WebAssembly'));
    print(raw('apis     ','term-key'),text('FastAPI para notícias e Go para o currículo'));print(raw('entrega  ','term-key'),text('Caddy, Docker Compose e GitHub Actions em uma VPS'));
    print(link('Ver a arquitetura e as decisões','#arquitetura'));
  }},
  open:{usage:'open <target>',about:'abre uma demonstração ou um contato',run(args){
    const place=places[args[0]];
    if(!place){for(const [name,[label]] of Object.entries(places))print(raw(name.padEnd(12),'term-key'),text(label));return;}
    if(place[1].startsWith('#'))document.querySelector(place[1]).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});else window.open(place[1],'_blank','noopener');
    print(text('Abrindo:','term-muted'),text(place[0]));
  }},
  lang:{usage:'lang <locale>',about:'troca o idioma da página',async run(args){if(!locales.includes(args[0])){print(raw(locales.join('   '),'term-key'));return;}await setLocale(args[0]);print(text('Idioma alterado.','term-ok'));}},
  contact:{about:'como falar comigo',run(){print(link('WhatsApp','https://wa.me/5547997336808'),link('LinkedIn','https://www.linkedin.com/in/karen-angelis/'),link('GitHub','https://github.com/KarenAngelis'));}},
  history:{about:'comandos já digitados',run(){history.forEach((entry,index)=>print(raw(String(index+1).padStart(2),'term-muted'),raw(entry)));}},
  clear:{about:'limpa a tela',run(){log.replaceChildren();}},
  sudo:{run(){print(text('Aqui não precisa de sudo: é só chamar.'),link('WhatsApp','https://wa.me/5547997336808'));}}
};
async function execute(entry){
  const [name,...args]=entry.trim().split(/\s+/);if(!name)return;
  terminal.classList.add('is-live');history.push(entry.trim());cursor=history.length;
  print(raw('karen@lab:~$','term-prompt'),raw(entry.trim()));
  const command=commands[name.toLowerCase()];
  if(!command){print(text('Comando não encontrado.'),text('Digite help para ver a lista.','term-muted'));return;}
  input.disabled=true;
  try{await command.run(args);}catch{print(text('Não foi possível concluir agora. Tente novamente.','term-warn'));}
  finally{input.disabled=false;}
}
form.addEventListener('submit',async event=>{event.preventDefault();const entry=input.value;input.value='';await execute(entry);input.focus({preventScroll:true});});
input.addEventListener('keydown',event=>{
  if(event.key==='ArrowUp'||event.key==='ArrowDown'){if(!history.length)return;event.preventDefault();cursor=Math.max(0,Math.min(history.length,cursor+(event.key==='ArrowUp'?-1:1)));input.value=history[cursor]||'';}
  else if(event.key==='Tab'&&input.value.trim()&&!input.value.includes(' ')){const options=Object.keys(commands).filter(name=>name.startsWith(input.value.trim().toLowerCase()));if(options.length===1&&options[0]!==input.value){event.preventDefault();input.value=options[0]+' ';}}
  else if(event.key==='l'&&event.ctrlKey){event.preventDefault();log.replaceChildren();}
});
terminal.querySelectorAll('[data-command]').forEach(chip=>chip.addEventListener('click',()=>execute(chip.dataset.command)));
terminal.addEventListener('focusin',()=>terminal.classList.add('is-live'));
