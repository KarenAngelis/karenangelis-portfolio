// Console de API: monta a requisição, envia para as APIs reais e mostra status, tempo, cabeçalhos e corpo.
import {endpoints,buildUrl,request} from './api.js';
import {highlight} from './code-viewer.js';
const form=document.querySelector('#console-form'),fields=document.querySelector('#console-params'),method=document.querySelector('#console-method');
const preview=document.querySelector('#console-url'),curl=document.querySelector('#console-curl'),copy=document.querySelector('#console-copy'),code=document.querySelector('#console-code');
const status=document.querySelector('#console-status'),facts=document.querySelector('#console-facts'),body=document.querySelector('#console-body code'),send=form.querySelector('[type=submit]');
const presets={limit:['news',{limit:'99'}],geo:['news',{geo:'XX'}],blank:['news',{q:' '}],post:['profile',{},'POST']};
let active='news',busy=false;
const values=()=>Object.fromEntries([...fields.querySelectorAll('input')].map(input=>[input.name,input.value]));
async function update(){
  const url=await buildUrl(active,values());
  preview.textContent=url;curl.textContent=`curl -i${method.value==='GET'?'':' -X '+method.value} '${url}'`;
}
function choose(key,overrides={},verb='GET'){
  active=key;const endpoint=endpoints[key];
  form.querySelectorAll('[data-endpoint]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.endpoint===key)));
  fields.replaceChildren(...endpoint.params.map(param=>{
    const label=document.createElement('label'),name=document.createElement('span'),input=document.createElement('input');
    name.textContent=param.name;name.dataset.noTranslate='';input.name=param.name;input.value=overrides[param.name]??param.value;input.autocomplete='off';input.spellcheck=false;
    if(param.options){const list=document.createElement('datalist');list.id='console-'+param.name;list.append(...param.options.map(value=>new Option(value)));input.setAttribute('list',list.id);label.append(name,input,list);}else label.append(name,input);
    return label;
  }));
  fields.hidden=!endpoint.params.length;
  method.replaceChildren(...endpoint.methods.map(value=>new Option(value)));method.value=verb;method.disabled=endpoint.methods.length<2;
  code.dataset.code=endpoint.code;update();
}
function fact(label,value,className=''){
  const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=label;detail.textContent=value;detail.dataset.noTranslate='';if(className)detail.className=className;return [term,detail];
}
function size(bytes){return bytes<1024?bytes+' B':(bytes/1024).toFixed(1).replace('.',',')+' kB';}
async function run(){
  if(busy)return;busy=true;send.disabled=true;status.className='console-status';status.textContent='Enviando…';
  try{
    const result=await request(active,values(),method.value);
    const level=result.status<300?'ok':result.status<500?'warn':'fail';
    status.replaceChildren(result.status<300?'Resposta recebida.':result.status<500?'A API recusou a requisição e explicou o motivo.':'A API respondeu com erro.',...(result.remote?[' ',Object.assign(document.createElement('span'),{textContent:'API local desligada: esta resposta veio da API publicada.'})]:[]));
    facts.replaceChildren(...fact('Status',`${result.status} ${result.statusText}`.trim(),'status-'+level),...fact('Tempo',result.ms+' ms'),...fact('Tamanho',size(result.bytes)),...fact('Serviço',result.service),...fact('Content-Type',result.type),...(result.cache?fact('Cache-Control',result.cache):[]),...(typeof result.json?.cached==='boolean'?fact('Cache da API',String(result.json.cached)):[]));
    facts.hidden=false;
    body.replaceChildren(result.json===undefined?result.text:highlight(JSON.stringify(result.json,null,2),'json'));
  }catch(error){
    status.className='console-status error';facts.hidden=true;body.replaceChildren();
    status.textContent=error.name==='TimeoutError'?'A API demorou mais que o esperado. Tente novamente.':'Não foi possível falar com a API agora.';
  }finally{busy=false;send.disabled=false;body.parentElement.scrollTo(0,0);}
}
form.querySelectorAll('[data-endpoint]').forEach(button=>button.addEventListener('click',()=>choose(button.dataset.endpoint)));
form.querySelectorAll('[data-preset]').forEach(button=>button.addEventListener('click',()=>{choose(...presets[button.dataset.preset]);run();}));
fields.addEventListener('input',update);method.addEventListener('change',update);
form.addEventListener('submit',event=>{event.preventDefault();run();});
copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(curl.textContent);copy.textContent='Copiado';}catch{copy.textContent='Selecione o comando para copiar';}setTimeout(()=>copy.textContent='Copiar curl',1800);});
choose(active);
