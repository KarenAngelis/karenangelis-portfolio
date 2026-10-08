const locales=['pt-BR','pt-PT','en-US','it-IT'];
const storageKey='portfolio-language';
let saved;try{saved=localStorage.getItem(storageKey);}catch{}
export let locale=locales.includes(new URLSearchParams(location.search).get('lang'))?new URLSearchParams(location.search).get('lang'):locales.includes(saved)?saved:'pt-BR';
let catalog={};
export const ready=fetch('/data/translations.json').then(r=>{if(!r.ok)throw new Error('Translation catalog unavailable');return r.json();}).then(data=>{catalog=data;return data;});
export function t(source){
  if(locale==='pt-BR'||!source)return source;
  const text=source.trim(), direct=catalog[text]?.[locale];
  if(direct!==undefined&&direct!==text)return source.replace(text,direct);
  let match;
  if((match=text.match(/^(\d+) competências$/)))return locale==='en-US'?`${match[1]} skills`:locale==='it-IT'?`${match[1]} competenze`:`${match[1]} competências`;
  if((match=text.match(/^(\d+) áreas? · (\d+) competências no repertório$/)))return locale==='en-US'?`${match[1]} areas · ${match[2]} skills`:locale==='it-IT'?`${match[1]} aree · ${match[2]} competenze`:`${match[1]} áreas · ${match[2]} competências no repertório`;
  if((match=text.match(/^(\d+) de 3 tarefas concluídas\.(.*)$/)))return (locale==='en-US'?`${match[1]} of 3 tasks completed.`:locale==='it-IT'?`${match[1]} attività completate su 3.`:`${match[1]} de 3 tarefas concluídas.`)+(match[2]?' '+t(match[2].trim()):'');
  if((match=text.match(/^(.+) movida para (.+)\. (\d+) de 3 tarefas concluídas\.$/)))return locale==='en-US'?`${t(match[1])} moved to ${t(match[2])}. ${match[3]} of 3 tasks completed.`:locale==='it-IT'?`${t(match[1])} spostata in ${t(match[2])}. ${match[3]} attività completate su 3.`:`${t(match[1])} movida para ${t(match[2])}. ${match[3]} de 3 tarefas concluídas.`;
  if((match=text.match(/^Notícias sobre “(.+)”$/)))return locale==='en-US'?`News about “${match[1]}”`:locale==='it-IT'?`Notizie su “${match[1]}”`:text;
  if((match=text.match(/^(\d+) notícias encontradas · (.+)$/)))return locale==='en-US'?`${match[1]} news results · ${t(match[2])}`:locale==='it-IT'?`${match[1]} notizie trovate · ${t(match[2])}`:text;
  if((match=text.match(/^Visitar (.+) em outra aba$/)))return locale==='en-US'?`Visit ${match[1]} in a new tab`:locale==='it-IT'?`Visita ${match[1]} in una nuova scheda`:`Visitar ${match[1]} noutro separador`;
  if((match=text.match(/^Conhecer minha trajetória na (.+) em nova aba$/)))return locale==='en-US'?`Explore my career at ${match[1]} in a new tab`:locale==='it-IT'?`Scopri il mio percorso presso ${match[1]} in una nuova scheda`:`Conhecer a minha trajetória na ${match[1]} num novo separador`;
  if((match=text.match(/^(.+) — conhecer minha trajetória$/)))return locale==='en-US'?`${match[1]} — explore my career`:locale==='it-IT'?`${match[1]} — scopri il mio percorso`:text;
  if((match=text.match(/^(.+) · Minha trajetória \| Karen Angelis$/)))return locale==='en-US'?`${match[1]} · My career | Karen Angelis`:locale==='it-IT'?`${match[1]} · Il mio percorso | Karen Angelis`:text;
  if((match=text.match(/^MINHA TRAJETÓRIA \/ (.+)$/)))return (locale==='en-US'?'MY CAREER / ':locale==='it-IT'?'IL MIO PERCORSO / ':'A MINHA TRAJETÓRIA / ')+t(match[1]);
  if((match=text.match(/^(.+): (.+) em outra aba$/)))return `${t(match[1])}: ${match[2]} ${locale==='en-US'?'in a new tab':locale==='it-IT'?'in una nuova scheda':'noutro separador'}`;
  if((match=text.match(/^Ler notícia: (.+)$/)))return `${t('Ler notícia')}: ${match[1]}`;
  if((match=text.match(/^(.+)\. (A fazer|Em andamento|Concluído)\. (Arraste para outra coluna.+)$/)))return `${t(match[1])}. ${t(match[2])}. ${t(match[3])}`;
  for(const separator of [' — ',' · '])if(text.includes(separator))return text.split(separator).map(t).join(separator);
  return source;
}

const textSources=new WeakMap(),attributeSources=new WeakMap();
const attributes=['aria-label','title','placeholder','alt','data-category','content'];
const excluded='script,style,pre,code,[data-no-translate],.project-name,.result-card h3';
let scheduled=false;
const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(()=>{scheduled=false;translatePage();});}});
function translatePage(){
  observer.disconnect();
  document.documentElement.lang=locale;
  const walker=document.createTreeWalker(document.documentElement,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode;if(!node.textContent.trim()||node.parentElement?.closest(excluded))continue;
    let state=textSources.get(node);if(!state||node.textContent!==state.output)state={source:node.textContent};
    state.output=t(state.source);if(node.textContent!==state.output)node.textContent=state.output;textSources.set(node,state);
  }
  for(const element of document.querySelectorAll('[aria-label],[title],[placeholder],[alt],[data-category],meta[name="description"]')){
    if(element.closest('[data-no-translate]'))continue;
    let state=attributeSources.get(element)||{};
    for(const attr of attributes){if(!element.hasAttribute(attr))continue;const current=element.getAttribute(attr);let entry=state[attr];if(!entry||current!==entry.output)entry={source:current};entry.output=t(entry.source);if(current!==entry.output)element.setAttribute(attr,entry.output);state[attr]=entry;}
    attributeSources.set(element,state);
  }
  for(const anchor of document.querySelectorAll('a[href]')){
    const raw=anchor.getAttribute('href');if(raw.startsWith('#'))continue;
    const target=new URL(raw,location.href);
    if(target.origin===location.origin&&!target.pathname.startsWith('/assets/')&&!target.pathname.startsWith('/downloads/')){
      target.searchParams.set('lang',locale);if(anchor.href!==target.href)anchor.href=target.href;
    }
  }
  picker?.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.locale===locale)));
  observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:attributes});
}
function flag(country){
  if(country==='BR')return '<rect width="30" height="20" fill="#229e45"/><path d="M15 2 28 10 15 18 2 10Z" fill="#ffdf00"/><circle cx="15" cy="10" r="5.2" fill="#244ca0"/><path d="M10 8.5Q15 7.5 20 11" fill="none" stroke="white" stroke-width="1.2"/>';
  if(country==='PT')return '<rect width="30" height="20" fill="#e72c32"/><rect width="12" height="20" fill="#087f43"/><circle cx="12" cy="10" r="4.5" fill="none" stroke="#ffe054" stroke-width="1.5"/><path d="M9 6h6v6q-3 4-6 0Z" fill="white" stroke="#df2d36" stroke-width="1.5"/><path d="M11 8h2v4h-2Z" fill="#2351a3"/>';
  if(country==='IT')return '<rect width="30" height="20" fill="#f7f7f2"/><rect width="10" height="20" fill="#009246"/><rect x="20" width="10" height="20" fill="#ce2b37"/>';
  return '<rect width="30" height="20" fill="white"/>'+Array.from({length:7},(_,i)=>`<rect y="${i*40/13}" width="30" height="${20/13}" fill="#b22234"/>`).join('')+'<rect width="13" height="10.77" fill="#3c3b6e"/>'+Array.from({length:4},(_,y)=>Array.from({length:5},(_,x)=>`<circle cx="${1.4+x*2.5}" cy="${1.5+y*2.5}" r=".5" fill="white"/>`).join('')).join('');
}
let picker;
function addPicker(){
  const header=document.querySelector('header.nav');if(!header)return;
  picker=document.createElement('div');picker.className='language-picker';picker.setAttribute('role','group');picker.setAttribute('aria-label','Idioma da página');
  const names=['Português do Brasil','Português de Portugal','Inglês dos Estados Unidos','Italiano'];
  locales.forEach((code,index)=>{const button=document.createElement('button');button.type='button';button.dataset.locale=code;button.setAttribute('aria-label',names[index]);button.title=names[index];button.innerHTML=`<svg viewBox="0 0 30 20" width="30" height="20" aria-hidden="true" focusable="false">${flag(['BR','PT','US','IT'][index])}</svg>`;button.addEventListener('click',()=>setLocale(code));picker.append(button);});header.append(picker);
}
export async function setLocale(code){
  if(!locales.includes(code))return;await ready;locale=code;try{localStorage.setItem(storageKey,code);}catch{}
  const url=new URL(location.href);url.searchParams.set('lang',code);history.replaceState(null,'',url);translatePage();window.dispatchEvent(new CustomEvent('portfolio-language',{detail:{locale:code}}));
}
addPicker();
await ready;translatePage();
