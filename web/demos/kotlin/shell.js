const root=document.querySelector('#kotlin-app');
const screen=document.querySelector('.app-screen');
const status=document.querySelector('#kotlin-status');
const icons=[
  '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V4h8v3M3 12h18M10 12v3h4v-3"/>',
  '<path d="M12 6c-3-3-6-3-10-2v15c4-1 7-1 10 2 3-3 6-3 10-2V4c-4-1-7-1-10 2Zm0 0v15"/>',
  '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 5-5 13 0 18 5-5 5-13 0-18"/>',
  '<circle cx="9" cy="7" r="3"/><path d="M3 21v-4a6 6 0 0 1 12 0v4M16 4a3 3 0 0 1 0 6M18 13a6 6 0 0 1 3 5v3"/>',
  '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>'
];
const observer=new MutationObserver(()=>{
  const tabs=root.querySelector('.profile-tabs');
  if(!tabs)return;
  const intro=root.querySelector(':scope > .intro');
  if(intro){
    const about=document.createElement('details');about.className='app-about';
    const summary=document.createElement('summary');summary.textContent='Sobre mim';
    intro.before(about);about.append(summary,intro);
  }
  document.querySelector('#app-navigation').append(tabs);
  tabs.querySelectorAll('button').forEach((button,index)=>{
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');
    svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.6');
    svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');
    svg.setAttribute('aria-hidden','true');svg.innerHTML=icons[index];button.prepend(svg);
    button.addEventListener('click',()=>{
      screen.dataset.section=index===0?'skills':'other';
      screen.scrollTop=0;
    });
  });
  status.hidden=true;
  observer.disconnect();
});
observer.observe(root,{childList:true,subtree:true});
document.querySelector('#refresh-profile').addEventListener('click',()=>location.reload());
