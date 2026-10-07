import {element,link,renderGroups,renderExperience,renderEducation,renderLanguages,renderSoftSkills} from '../../assets/profile-view.js';
const source=document.querySelector('#source');
function render(profile){
  document.querySelector('#summary').textContent=profile.summary;
  renderGroups(document.querySelector('#skills'),profile.skillGroups);
  renderExperience(document.querySelector('#experience'),profile.experience);
  renderEducation(document.querySelector('#education'),profile);
  renderLanguages(document.querySelector('#languages'),profile.languages);
  renderSoftSkills(document.querySelector('#soft'),profile.softSkills);
  const projects=document.querySelector('#projects');projects.replaceChildren();
  profile.projects.forEach(project=>{const row=element('article','','resume-entry');row.append(element('h3',project.name),element('p',project.description),link(project.linkLabel,project.url));projects.append(row);});
}
try{const r=await fetch('../../data/profile.json');if(!r.ok)throw new Error();render(await r.json());source.textContent='Fonte: dados locais do portfólio. Interface web em JavaScript.';}catch{source.textContent='Não foi possível carregar o currículo.';source.classList.add('error');}
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));document.querySelector('#'+b.dataset.tab).hidden=b!==button;});
}));
document.querySelector('#connect').addEventListener('click',async(event)=>{
  const button=event.currentTarget;button.disabled=true;
  try{const r=await fetch((['localhost','127.0.0.1'].includes(location.hostname)?'http://127.0.0.1:8080':'')+'/api/profile',{signal:AbortSignal.timeout(8000)});if(!r.ok)throw new Error();render(await r.json());source.textContent='Fonte: API Go · GET /api/profile';source.classList.remove('error');}catch{source.textContent='API Go indisponível. Os dados locais continuam visíveis; tente consultar novamente mais tarde.';source.classList.add('error');}finally{button.disabled=false;}
});
