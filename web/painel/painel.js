// Painel público: busca os totais na API de estatísticas e desenha gráfico e listas.
const local=['localhost','127.0.0.1'].includes(location.hostname),api=(local?'http://127.0.0.1:8001':'')+'/api/stats/summary';
const error=document.querySelector('#panel-error'),days=document.querySelector('#panel-days'),tip=document.querySelector('#chart-tip');
const number=new Intl.NumberFormat('pt-BR'),SVG='http://www.w3.org/2000/svg';
function node(tag,className='',text=''){const item=document.createElement(tag);if(className)item.className=className;if(text!=='')item.textContent=text;return item;}
function svg(tag,attributes={}){const item=document.createElementNS(SVG,tag);for(const [key,value] of Object.entries(attributes))item.setAttribute(key,value);return item;}
const shortDay=day=>day.slice(8)+'/'+day.slice(5,7);
async function load(){
  let response;
  try{response=await fetch(`${api}?days=${days.value}`,{signal:AbortSignal.timeout(12000)});}
  catch{error.textContent='Não foi possível falar com o servidor de estatísticas.';error.hidden=false;return;}
  if(!response.ok){let detail='Não foi possível abrir o painel.';try{detail=(await response.json()).detail||detail;}catch{}error.textContent=detail;error.hidden=false;return;}
  try{render(await response.json());error.hidden=true;}
  catch{error.textContent='Não foi possível mostrar os dados.';error.hidden=false;}
}
function render(summary){
  const {views,visitors,clicks}=summary.totals;
  document.querySelector('#total-views').textContent=number.format(views);
  document.querySelector('#total-visitors').textContent=number.format(visitors);
  document.querySelector('#total-clicks').textContent=number.format(clicks);
  document.querySelector('#total-rate').textContent=views?(clicks/views).toFixed(1).replace('.',','):'–';
  document.querySelector('#chart-range').textContent=`${shortDay(summary.daily[0].day)} a ${shortDay(summary.daily.at(-1).day)}`;
  chart(summary.daily);
  document.querySelector('#daily-table').replaceChildren(...summary.daily.toReversed().map(entry=>{const row=node('tr');row.append(node('th','',shortDay(entry.day)),node('td','',number.format(entry.views)),node('td','',number.format(entry.visitors)),node('td','',number.format(entry.clicks)));row.firstChild.scope='row';return row;}));
  rank('#list-clicks',summary.clicks);rank('#list-pages',summary.pages);rank('#list-referrers',summary.referrers);rank('#list-languages',summary.languages);rank('#list-devices',summary.devices,{mobile:'Celular',desktop:'Computador'});
}
// Lista ordenada com barra fina: o rótulo e o número ficam em texto, a barra só reforça a proporção.
function rank(selector,entries,labels={}){
  const box=document.querySelector(selector);
  if(!entries.length){box.replaceChildren(node('p','rank-empty','Ainda sem dados neste período.'));return;}
  const max=entries[0].total;
  box.replaceChildren(...entries.slice(0,12).map(entry=>{
    const row=node('div','rank-row'),bar=node('i');bar.style.width=Math.max(2,entry.total/max*100)+'%';
    row.append(node('span','rank-label',labels[entry.key]||entry.key),node('span','rank-value',number.format(entry.total)),bar);return row;
  }));
}
// Colunas com uma só série (visitas). Escala começa em zero; colunas finas, topo arredondado e base reta.
function chart(daily){
  const box=document.querySelector('#chart'),width=Math.max(320,box.clientWidth),height=240,left=38,right=8,top=12,bottom=28;
  const peak=Math.max(1,...daily.map(entry=>entry.views)),step=10**Math.floor(Math.log10(peak)),unit=[1,2,5,10].map(m=>m*step).find(size=>peak/size<=4)||step,max=Math.ceil(peak/unit)*unit;
  const plotWidth=width-left-right,plotHeight=height-top-bottom,slot=plotWidth/daily.length,bar=Math.max(2,Math.min(24,slot-2)),y=value=>top+plotHeight-value/max*plotHeight;
  const root=svg('svg',{viewBox:`0 0 ${width} ${height}`,width,height});
  for(let value=0;value<=max;value+=unit){
    root.append(svg('line',{x1:left,x2:width-right,y1:y(value),y2:y(value),class:value?'chart-grid':'chart-base'}));
    const label=svg('text',{x:left-8,y:y(value)+4,'text-anchor':'end',class:'chart-axis'});label.textContent=number.format(value);root.append(label);
  }
  const every=Math.ceil(daily.length/Math.max(2,Math.floor(plotWidth/56)));
  daily.forEach((entry,index)=>{
    const x=left+slot*index+(slot-bar)/2,barHeight=entry.views/max*plotHeight,radius=Math.min(4,bar/2,barHeight);
    if(barHeight>0)root.append(svg('path',{class:'chart-bar',d:`M${x},${top+plotHeight}V${y(entry.views)+radius}q0,${-radius} ${radius},${-radius}h${bar-2*radius}q${radius},0 ${radius},${radius}V${top+plotHeight}z`}));
    if(index%every===0||index===daily.length-1&&index%every>every/2){const label=svg('text',{x:left+slot*index+slot/2,y:height-8,'text-anchor':'middle',class:'chart-axis'});label.textContent=shortDay(entry.day);root.append(label);}
    // Área de toque do dia inteiro, maior que a coluna, para o detalhe aparecer mesmo em dias com poucas visitas.
    const hit=svg('rect',{x:left+slot*index,y:top,width:slot,height:plotHeight,class:'chart-hit',tabindex:0,'aria-label':`${shortDay(entry.day)}: ${entry.views} visitas, ${entry.visitors} visitantes, ${entry.clicks} cliques`});
    const show=()=>{tip.replaceChildren(node('b','',shortDay(entry.day)),node('span','',`${number.format(entry.views)} visitas`),node('span','',`${number.format(entry.visitors)} visitantes`),node('span','',`${number.format(entry.clicks)} cliques`));tip.hidden=false;const area=hit.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(innerWidth-tip.offsetWidth-8,area.left+area.width/2-tip.offsetWidth/2))+'px';tip.style.top=Math.max(8,area.top+scrollY-tip.offsetHeight-6)+'px';};
    hit.addEventListener('pointerenter',show);hit.addEventListener('focus',show);hit.addEventListener('pointerleave',()=>tip.hidden=true);hit.addEventListener('blur',()=>tip.hidden=true);root.append(hit);
  });
  box.replaceChildren(root);
}
days.addEventListener('change',load);
let resizing;addEventListener('resize',()=>{clearTimeout(resizing);resizing=setTimeout(load,300);});
load();
