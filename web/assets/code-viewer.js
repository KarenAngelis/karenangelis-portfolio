// Visualizador de código: mostra os arquivos reais do projeto, empacotados por scripts/sources.mjs.
let cache;
export function sources(){return cache??=fetch('/data/sources.json').then(response=>{if(!response.ok)throw new Error('Código indisponível');return response.json();});}

const slash=/\/\/.*|\/\*[\s\S]*?\*\//.source,hash=/#.*/.source;
const quoted=/"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/.source;
const grammars={
  javascript:{comment:slash,string:/`(?:\\.|[^`\\])*`/.source+'|'+quoted+'|'+/(?<=[=(,:;!&|?{}\[]\s*)\/(?![/*])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n])+\/[dgimsuvy]*/.source,words:'async await break case catch class const continue default delete do else export extends finally for from function if import in instanceof let new of return switch throw try typeof var void while yield true false null undefined this'},
  kotlin:{comment:slash,string:/"""[\s\S]*?"""/.source+'|'+quoted,words:'actual as break by catch class companion const continue data do else enum expect false finally for fun if import in interface internal is null object override package private protected public return sealed suspend this throw true try val var when while'},
  go:{comment:slash,string:/`[^`]*`/.source+'|'+quoted,words:'break case chan const continue default defer else for func go if import interface map package range return select struct switch type var true false nil'},
  python:{comment:hash,string:/"""[\s\S]*?"""/.source+'|'+quoted,words:'and as assert async await break class continue def del elif else except finally for from global if import in is lambda not or pass raise return try while with yield True False None'},
  yaml:{comment:hash,string:quoted,words:'true false null'},
  docker:{comment:hash,string:quoted,words:'FROM RUN COPY WORKDIR ENV USER ENTRYPOINT CMD AS'},
  json:{comment:'(?!)',string:quoted,words:'true false null'},
  text:{comment:hash,string:'(?!)',words:''}
};
// Divide o código em trechos [classe, texto]; o que não é reconhecido fica sem classe.
function tokenize(code,language){
  const grammar=grammars[language]||grammars.text,words=new Set(grammar.words.split(' '));
  const pattern=new RegExp(`(${grammar.comment})|(${grammar.string})|(@[\\w.]+)|(\\b\\d[\\d_.]*\\b)|([A-Za-z_$][\\w$]*)`,'g');
  const tokens=[];let last=0,match;
  while((match=pattern.exec(code))){
    if(match.index>last)tokens.push(['',code.slice(last,match.index)]);
    const [text,comment,string,annotation,number,word]=match;last=match.index+text.length;
    let type='';
    if(comment!==undefined)type='comment';
    else if(string!==undefined)type=language==='json'&&/^\s*:/.test(code.slice(last))?'property':'string';
    else if(annotation!==undefined)type='annotation';
    else if(number!==undefined)type='number';
    else if(words.has(word))type='keyword';
    else if(code[last]==='(')type='call';
    tokens.push([type,text]);
  }
  if(last<code.length)tokens.push(['',code.slice(last)]);
  return tokens;
}
export function highlight(code,language){
  const fragment=document.createDocumentFragment();
  let line=document.createElement('span');line.className='code-line';
  for(const [type,text] of tokenize(code,language)){
    text.split('\n').forEach((part,index)=>{
      if(index){fragment.append(line,'\n');line=document.createElement('span');line.className='code-line';}
      if(!part)return;
      if(type){const span=document.createElement('span');span.className='tok-'+type;span.textContent=part;line.append(span);}else line.append(part);
    });
  }
  fragment.append(line);return fragment;
}

function node(tag,className='',text=''){const item=document.createElement(tag);if(className)item.className=className;if(text)item.textContent=text;return item;}
export function createViewer(){
  const root=node('div','code-viewer'),tabs=node('div','code-tabs'),meta=node('div','code-meta'),path=node('span','code-path'),lines=node('span','code-lines'),copy=node('button','code-copy','Copiar');
  const pre=node('pre','code-view'),code=node('code');
  tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Arquivos');path.dataset.noTranslate='';copy.type='button';pre.tabIndex=0;pre.setAttribute('aria-label','Código-fonte');
  pre.append(code);meta.append(path,lines,copy);root.append(tabs,meta,pre);
  let current='';
  copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(current);copy.textContent='Copiado';}catch{copy.textContent='Selecione o código para copiar';}setTimeout(()=>copy.textContent='Copiar',1800);});
  function select(bundle,index){
    const file=bundle.files[index];current=file.code;
    [...tabs.children].forEach((tab,position)=>{tab.setAttribute('aria-selected',String(position===index));tab.tabIndex=position===index?0:-1;});
    path.textContent=file.path;
    const total=node('span','',String(file.code.split('\n').length));total.dataset.noTranslate='';lines.replaceChildren(total,' ',node('span','','linhas'));
    code.replaceChildren(highlight(file.code,file.language));pre.scrollTo(0,0);
  }
  async function show(id,file=0){
    let data;try{data=await sources();}catch{code.textContent='';path.textContent='';lines.textContent='Não foi possível carregar o código.';return null;}
    const bundle=data.bundles[id];if(!bundle)return null;
    tabs.replaceChildren(...bundle.files.map((item,index)=>{const tab=node('button','',item.name);tab.type='button';tab.setAttribute('role','tab');tab.dataset.noTranslate='';tab.addEventListener('click',()=>select(bundle,index));return tab;}));
    tabs.hidden=bundle.files.length<2;
    const index=typeof file==='string'?Math.max(0,bundle.files.findIndex(item=>item.name===file)):file;
    select(bundle,index);return bundle;
  }
  tabs.addEventListener('keydown',event=>{
    if(event.key!=='ArrowRight'&&event.key!=='ArrowLeft')return;
    const items=[...tabs.children],next=items[(items.indexOf(document.activeElement)+(event.key==='ArrowRight'?1:items.length-1))%items.length];
    event.preventDefault();next.focus();next.click();
  });
  return {root,show};
}

let dialog,viewer,title,stack;
function ensureDialog(){
  if(dialog)return;
  dialog=node('dialog','code-dialog');dialog.setAttribute('aria-labelledby','code-title');
  const header=node('header','code-header'),heading=node('div'),close=node('button','code-close','×');
  title=node('h3');title.id='code-title';stack=node('p','code-stack');
  close.type='button';close.setAttribute('aria-label','Fechar código');close.addEventListener('click',()=>dialog.close());
  heading.append(node('p','eyebrow','CÓDIGO REAL DESTE SITE'),title,stack);header.append(heading,close);
  viewer=createViewer();dialog.append(header,viewer.root);document.body.append(dialog);
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
}
export async function openCode(id,file){
  ensureDialog();const bundle=await viewer.show(id,file);
  title.textContent=bundle?bundle.title:'Código indisponível';stack.textContent=bundle?bundle.stack:'';
  if(!dialog.open)dialog.showModal();
  return Boolean(bundle);
}
document.addEventListener('click',event=>{
  const trigger=event.target.closest('[data-code]');
  if(trigger){event.preventDefault();openCode(trigger.dataset.code,trigger.dataset.file);}
});

// Abas "Testar | Código" dentro de um cartão: a demonstração e o código que a faz funcionar, lado a lado.
for(const tabs of document.querySelectorAll('.try-tabs')){
  const root=tabs.closest('[data-try-root]'),buttons=[...tabs.querySelectorAll('button')];let inline;
  function choose(button){
    for(const item of buttons){const active=item===button;item.setAttribute('aria-selected',String(active));item.tabIndex=active?0:-1;root.querySelector(`[data-try-panel="${item.dataset.try}"]`).hidden=!active;}
    if(button.dataset.bundle&&!inline){inline=createViewer();root.querySelector(`[data-try-panel="${button.dataset.try}"]`).append(inline.root);inline.show(button.dataset.bundle);}
  }
  buttons.forEach(button=>button.addEventListener('click',()=>choose(button)));
  tabs.addEventListener('keydown',event=>{
    if(event.key!=='ArrowRight'&&event.key!=='ArrowLeft')return;
    const next=buttons[(buttons.indexOf(document.activeElement)+1)%buttons.length];event.preventDefault();next.focus();choose(next);
  });
}
