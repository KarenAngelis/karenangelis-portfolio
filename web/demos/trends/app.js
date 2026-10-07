const local=['localhost','127.0.0.1'].includes(location.hostname),api=local?'http://127.0.0.1:8000':'';
const form=document.querySelector('#search-form'),topic=document.querySelector('#topic'),country=document.querySelector('#country'),button=document.querySelector('#load'),status=document.querySelector('#status'),results=document.querySelector('#results'),json=document.querySelector('#json');
const title=document.querySelector('#results-title'),source=document.querySelector('#result-source'),trending=document.querySelector('#trending');
document.querySelector('#docs').href=api+'/docs';
let busy=false;
async function search(){
  if(busy)return;busy=true;
  const query=topic.value.trim(),geo=country.value;
  form.querySelectorAll('input,select,button').forEach(el=>el.disabled=true);
  document.querySelectorAll('[data-topic],#trending').forEach(el=>el.disabled=true);
  button.textContent='Buscando…';results.setAttribute('aria-busy','true');status.classList.remove('error');status.textContent=query?`Buscando notícias sobre “${query}”…`:'Consultando buscas em alta…';results.replaceChildren();json.textContent='Aguardando resposta…';
  try{
    const params=new URLSearchParams({geo,limit:'10',q:query});
    const response=await fetch(`${api}/api/trends?${params}`,{signal:AbortSignal.timeout(18000)});
    if(!response.ok){let message='Não foi possível consultar agora.';try{const body=await response.json();if(typeof body.detail==='string')message=body.detail;}catch{}throw new Error(message);}
    const data=await response.json();json.textContent=JSON.stringify(data,null,2);
    const news=data.mode==='news';title.textContent=news?`Notícias sobre “${data.query}”`:'Buscas em alta agora';source.textContent=news?'GOOGLE NOTÍCIAS':'GOOGLE TRENDS';
    const sourceLink=document.querySelector('#source-link');sourceLink.href=news?`https://news.google.com/search?${new URLSearchParams({q:data.query,hl:geo==='US'?'en-US':geo==='PT'?'pt-PT':'pt-BR',gl:geo,ceid:geo+':'+(geo==='US'?'en':'pt')})}`:`https://trends.google.com/trending?geo=${geo}`;
    data.items.forEach((item,index)=>{
      const row=document.createElement('article');row.className='result-card';
      const number=document.createElement('span');number.className='result-number';number.textContent=String(index+1).padStart(2,'0');
      const info=document.createElement('div'),heading=document.createElement('h3');heading.textContent=item.title;
      const meta=document.createElement('p');const date=new Date(item.published);meta.textContent=[item.publisher,Number.isNaN(date.getTime())?null:date.toLocaleDateString('pt-BR',{day:'2-digit',month:'short',year:'numeric'})].filter(Boolean).join(' · ');
      info.append(heading,meta);row.append(number,info);
      if(news&&item.url?.startsWith('https://')){const link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';link.className='result-action';link.textContent='Ler notícia';link.setAttribute('aria-label','Ler notícia: '+item.title);row.append(link);}
      else if(!news){const traffic=document.createElement('span');traffic.className='result-traffic';traffic.textContent=item.traffic?item.traffic+' buscas':'Em alta';row.append(traffic);}
      results.append(row);
    });
    if(!data.items.length){const empty=document.createElement('p');empty.className='results-empty';empty.textContent='Nenhum resultado encontrado. Experimente outro assunto.';results.append(empty);}
    status.textContent=`${data.items.length} ${news?'notícias':'assuntos'} · ${country.selectedOptions[0].textContent} · atualizado ${new Date(data.fetched_at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}`;
  }catch(error){status.classList.add('error');status.textContent=error.name==='TimeoutError'?'A consulta demorou mais que o esperado. Tente novamente.':error.message;json.textContent='Consulta indisponível. Nenhum dado fictício foi apresentado.';const empty=document.createElement('p');empty.className='results-empty';empty.textContent='Não conseguimos buscar os dados agora. Você pode tentar novamente.';results.append(empty);}
  finally{busy=false;button.textContent='Buscar assunto';results.setAttribute('aria-busy','false');form.querySelectorAll('input,select,button').forEach(el=>el.disabled=false);document.querySelectorAll('[data-topic],#trending').forEach(el=>el.disabled=false);}
}
form.addEventListener('submit',event=>{event.preventDefault();search();});
document.querySelectorAll('[data-topic]').forEach(chip=>chip.addEventListener('click',()=>{topic.value=chip.dataset.topic;search();}));
trending.addEventListener('click',()=>{topic.value='';search();});
