import {element,renderGroups,renderExperience,renderSoftSkills} from './profile-view.js';
const container=document.querySelector('#project-list');
document.querySelector('#year').textContent=new Date().getFullYear();
try {
  const response=await fetch('data/profile.json');
  if(!response.ok)throw new Error('Dados indisponíveis');
  const profile=await response.json();
  const catalog=document.querySelector('#skill-catalog');
  const search=document.querySelector('#skill-search'),area=document.querySelector('#skill-area');
  let focused=[];
  for(const group of profile.skillGroups){const option=element('option',group.title);option.value=group.id;area.append(option);}
  const updateCatalog=()=>{const groups=focused.length?profile.skillGroups.filter(g=>focused.includes(g.id)):profile.skillGroups;const total=renderGroups(catalog,groups,{query:search.value,area:area.value});document.querySelector('#skill-count').textContent=`${total} ${total===1?'área':'áreas'} · ${profile.skills.length} competências no repertório`;};
  const clearFocus=()=>{focused=[];updateCatalog();};
  updateCatalog();search.addEventListener('input',clearFocus);area.addEventListener('change',clearFocus);
  window.addEventListener('portfolio-focus',event=>{focused=event.detail.ids;area.value='all';search.value='';updateCatalog();});
  document.querySelector('#reset-catalog').addEventListener('click',()=>{focused=[];area.value='all';search.value='';updateCatalog();});
  renderSoftSkills(document.querySelector('#soft-skills'),profile.softSkills);
  renderExperience(document.querySelector('#career-timeline'),profile.experience);
  function render(filter='all'){
    container.replaceChildren();
    profile.projects.filter(p=>filter==='all'||p.category===filter).forEach((p,index)=>{
      const row=document.createElement('article');row.className='project-row';
      const number=document.createElement('span');number.className='project-number';number.textContent=String(index+1).padStart(2,'0');
      const info=document.createElement('div');const title=document.createElement('h3');title.textContent=p.name;const desc=document.createElement('p');desc.textContent=p.description;info.append(title,desc);
      const link=document.createElement('a');link.href=p.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=p.linkLabel+' ↗';link.setAttribute('aria-label',`${p.linkLabel}: ${p.name} em outra aba`);row.append(number,info,link);container.append(row);
    });
  }
  render();
  document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{
    document.querySelectorAll('[data-filter]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});render(button.dataset.filter);
  }));
} catch {container.textContent='Não foi possível carregar os projetos. Acesse meu GitHub pelo link acima.';}
