const strip=document.querySelector('.company-showcase'),windowElement=strip.querySelector('.company-window');
const previous=strip.querySelector('.company-previous'),next=strip.querySelector('.company-next');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
function update(){previous.disabled=windowElement.scrollLeft<=2;next.disabled=windowElement.scrollLeft+windowElement.clientWidth>=windowElement.scrollWidth-2;}
function move(direction){windowElement.scrollBy({left:direction*windowElement.clientWidth*.75,behavior:reduced.matches?'instant':'smooth'});}
previous.addEventListener('click',()=>move(-1));next.addEventListener('click',()=>move(1));
windowElement.addEventListener('scroll',update,{passive:true});window.addEventListener('resize',update);update();
strip.querySelectorAll('img').forEach(img=>img.addEventListener('load',update));
