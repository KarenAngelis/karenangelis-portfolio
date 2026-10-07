const source=document.querySelector('#source');
function render(profile){
  document.querySelector('#summary').textContent=profile.summary;
  const skills=document.querySelector('#skills');skills.replaceChildren();
  profile.skills.forEach(skill=>{const badge=document.createElement('span');badge.textContent=skill;skills.append(badge);});
  const projects=document.querySelector('#projects');projects.replaceChildren();
  profile.projects.forEach(project=>{const row=document.createElement('article');row.className='project-row';const heading=document.createElement('h3');heading.textContent=project.name;const link=document.createElement('a');link.textContent='Abrir código ↗';link.href=project.url;link.target='_blank';link.rel='noopener noreferrer';row.append(heading,link);projects.append(row);});
}
try{const r=await fetch('../../data/profile.json');if(!r.ok)throw new Error();render(await r.json());source.textContent='Fonte: dados locais do portfólio. Interface web em JavaScript.';}catch{source.textContent='Não foi possível carregar o currículo.';source.classList.add('error');}
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));document.querySelector('#'+b.dataset.tab).hidden=b!==button;});
}));
document.querySelector('#connect').addEventListener('click',async(event)=>{
  const button=event.currentTarget;button.disabled=true;
  try{const r=await fetch((['localhost','127.0.0.1'].includes(location.hostname)?'http://127.0.0.1:8080':'')+'/api/profile',{signal:AbortSignal.timeout(8000)});if(!r.ok)throw new Error();render(await r.json());source.textContent='Fonte: API Go local · GET /api/profile';source.classList.remove('error');}catch{source.textContent='API Go não está disponível. Inicie apps/resume-api com go run .; os dados locais continuam visíveis.';source.classList.add('error');}finally{button.disabled=false;}
});
