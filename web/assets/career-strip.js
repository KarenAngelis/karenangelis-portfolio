const strip=document.querySelector('.company-showcase');
const track=strip.querySelector('.company-track'),control=strip.querySelector('.company-motion');
const copy=track.firstElementChild.cloneNode(true);copy.setAttribute('aria-hidden','true');copy.querySelectorAll('a').forEach(link=>{link.tabIndex=-1;link.removeAttribute('aria-label');link.querySelector('img')?.setAttribute('alt','');});track.append(copy);
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
function update(){control.disabled=reduced.matches;control.setAttribute('aria-label',reduced.matches?'Movimento reduzido':strip.classList.contains('is-paused')?'Retomar movimento das empresas':'Pausar movimento das empresas');}
control.addEventListener('click',()=>{const paused=strip.classList.toggle('is-paused');control.setAttribute('aria-pressed',String(paused));update();});reduced.addEventListener('change',update);update();
