const local=['localhost','127.0.0.1'].includes(location.hostname);
const api=local?'http://127.0.0.1:8000':'';
document.querySelector('#docs').href=api+'/docs';
const button=document.querySelector('#load'),status=document.querySelector('#status'),results=document.querySelector('#results'),json=document.querySelector('#json');
button.addEventListener('click',async()=>{
  button.disabled=true;status.classList.remove('error');status.textContent='Consultando o feed do Google Trends…';results.replaceChildren();json.textContent='Aguardando resposta…';
  try{
    const r=await fetch(`${api}/api/trends?geo=${document.querySelector('#country').value}&limit=10`,{signal:AbortSignal.timeout(18000)});
    if(!r.ok)throw new Error(`API respondeu HTTP ${r.status}`);
    const data=await r.json();json.textContent=JSON.stringify(data,null,2);
    data.items.forEach((item,index)=>{const row=document.createElement('article');row.className='trend-row';const num=document.createElement('span');num.textContent=String(index+1).padStart(2,'0');const info=document.createElement('div');const heading=document.createElement('h3');heading.textContent=item.title;const date=document.createElement('p');date.textContent=item.published||'Sem data informada';const traffic=document.createElement('span');traffic.textContent=item.traffic||'Volume não informado';info.append(heading,date);row.append(num,info,traffic);results.append(row);});
    status.textContent=`${data.items.length} tendências · ${data.geo} · consulta ${new Date(data.fetched_at).toLocaleString('pt-BR')}${data.cached?' · resposta em cache':''}`;
  }catch(error){status.classList.add('error');status.textContent=`Não foi possível consultar: ${error.message}. Confira se a API FastAPI está em execução na porta 8000 e tente novamente.`;json.textContent='Consulta indisponível. Nenhum dado fictício foi apresentado.';}finally{button.disabled=false;}
});
