const section=document.querySelector('.stack-summary');
const motion=document.querySelector('#technology-motion');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const tooltip=document.createElement('div');
tooltip.id='technology-category';tooltip.className='technology-tooltip';tooltip.role='tooltip';tooltip.hidden=true;document.body.append(tooltip);
let selected=null;
for(const track of section.querySelectorAll('.technology-track')){
  const copy=track.firstElementChild.cloneNode(true);copy.setAttribute('aria-hidden','true');
  copy.querySelectorAll('button').forEach(button=>{button.tabIndex=-1;button.removeAttribute('aria-label');});track.append(copy);
}
function hide(){selected?.removeAttribute('aria-describedby');selected=null;tooltip.hidden=true;}
function show(button){
  hide();selected=button;tooltip.textContent=button.dataset.category;tooltip.hidden=false;
  if(!button.closest('[aria-hidden="true"]'))button.setAttribute('aria-describedby',tooltip.id);
  const rect=button.getBoundingClientRect();const width=tooltip.offsetWidth;const height=tooltip.offsetHeight;
  tooltip.style.left=Math.max(12,Math.min(innerWidth-width-12,rect.left+(rect.width-width)/2))+'px';
  tooltip.style.top=Math.max(12,rect.top>height+12?rect.top-height-8:rect.bottom+8)+'px';
}
for(const button of section.querySelectorAll('.technology')){
  button.addEventListener('pointerenter',()=>show(button));button.addEventListener('pointerleave',hide);
  button.addEventListener('focus',()=>show(button));button.addEventListener('blur',hide);
  button.addEventListener('click',()=>show(button));
}
function updateMotion(){motion.disabled=reduced.matches;motion.textContent=reduced.matches?'Movimento reduzido':section.classList.contains('is-paused')?'Retomar movimento':'Pausar movimento';}
motion.addEventListener('click',()=>{const paused=section.classList.toggle('is-paused');motion.setAttribute('aria-pressed',String(paused));updateMotion();hide();});
reduced.addEventListener('change',updateMotion);updateMotion();
document.addEventListener('keydown',event=>{if(event.key==='Escape')hide();});
document.addEventListener('pointerdown',event=>{if(!event.target.closest('.technology'))hide();});
window.addEventListener('scroll',hide,{passive:true});window.addEventListener('resize',hide);
