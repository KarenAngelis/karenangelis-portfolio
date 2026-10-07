const local=['localhost','127.0.0.1'].includes(location.hostname),api=local?'http://127.0.0.1:8000':'';
const form=document.querySelector('#search-form'),topic=document.querySelector('#topic'),country=document.querySelector('#country'),button=document.querySelector('#load'),status=document.querySelector('#status'),results=document.querySelector('#results'),json=document.querySelector('#json');
const title=document.querySelector('#results-title'),panel=document.querySelector('#results-panel'),technical=document.querySelector('#technical');
document.querySelector('#docs').href=api+'/docs';
let busy=false;
async function search(){
  const query=topic.value.trim(),geo=country.value;
  if(busy)return;
  if(!query){topic.setCustomValidity('Digite um assunto para buscar notícias.');topic.reportValidity();return;}
  busy=true;panel.hidden=false;technical.hidden=true;technical.open=false;
  form.querySelectorAll('input,select,button').forEach(el=>el.disabled=true);
  document.querySelectorAll('[data-topic]').forEach(el=>el.disabled=true);
  button.textContent='Buscando…';title.textContent=`Notícias sobre “${query}”`;results.setAttribute('aria-busy','true');status.classList.remove('error');status.textContent='Buscando notícias…';results.replaceChildren();json.textContent='';
  try{
    const response=await fetch(`${api}/api/news?${new URLSearchParams({geo,limit:'10',q:query})}`,{signal:AbortSignal.timeout(18000)});
    if(!response.ok){let message='Não foi possível buscar notícias agora.';try{const body=await response.json();if(typeof body.detail==='string')message=body.detail;}catch{}throw new Error(message);}
    const data=await response.json();json.textContent=JSON.stringify(data,null,2);
    data.items.forEach((item,index)=>{
      const row=document.createElement('article');row.className='result-card';
      const number=document.createElement('span');number.className='result-number';number.textContent=String(index+1).padStart(2,'0');
      const info=document.createElement('div'),heading=document.createElement('h3');heading.textContent=item.title;
      const meta=document.createElement('p');const date=new Date(item.published);meta.textContent=[item.publisher,Number.isNaN(date.getTime())?null:date.toLocaleDateString('pt-BR',{day:'2-digit',month:'short',year:'numeric'})].filter(Boolean).join(' · ');
      info.append(heading,meta);row.append(number,info);
      if(item.url?.startsWith('https://')){const link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';link.className='result-action';link.textContent='Ler notícia';link.setAttribute('aria-label','Ler notícia: '+item.title);row.append(link);}
      results.append(row);
    });
    if(!data.items.length){const empty=document.createElement('p');empty.className='results-empty';empty.textContent='Nenhuma notícia encontrada. Tente outro assunto.';results.append(empty);}
    status.textContent=`${data.items.length} notícias encontradas · ${country.selectedOptions[0].textContent}`;technical.hidden=false;
  }catch(error){status.classList.add('error');status.textContent=error.name==='TimeoutError'?'A busca demorou mais que o esperado. Tente novamente.':error.message;}
  finally{busy=false;button.textContent='Buscar notícias';results.setAttribute('aria-busy','false');form.querySelectorAll('input,select,button').forEach(el=>el.disabled=false);document.querySelectorAll('[data-topic]').forEach(el=>el.disabled=false);}
}
topic.addEventListener('input',()=>topic.setCustomValidity(''));
form.addEventListener('submit',event=>{event.preventDefault();search();});
document.querySelectorAll('[data-topic]').forEach(chip=>chip.addEventListener('click',()=>{topic.value=chip.dataset.topic;topic.setCustomValidity('');search();}));
