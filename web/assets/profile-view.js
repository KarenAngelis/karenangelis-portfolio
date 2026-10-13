import {t,locale} from './i18n.js';
export function element(tag,text='',className=''){
  const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node;
}
export function link(text,url){
  const node=element('a',text,'text-link');node.href=new URL(url,new URL('../',import.meta.url));
  if(!url.startsWith('/#')){node.target='_blank';node.rel='noopener noreferrer';}return node;
}
// Competência com evidência vira link para o repositório ou abre o arquivo no visualizador de código.
function skillBadge(item,evidence){
  const proof=evidence?.skills[item];if(!proof)return element('span',item);
  const badge=element(proof.code?'button':'a',item,'evidence');badge.title='Ver onde usei no código';
  if(proof.code){badge.type='button';badge.dataset.code=proof.code;if(proof.file)badge.dataset.file=proof.file;}
  else{badge.href=evidence.repository+proof.url;badge.target='_blank';badge.rel='noopener noreferrer';}
  return badge;
}
export function renderGroups(container,groups,{query='',area='all',evidence=null}={}){
  container.replaceChildren();const needle=query.trim().toLocaleLowerCase(locale);
  const selected=groups.filter(g=>(area==='all'||g.id===area)&&(!needle||[g.title,g.description,g.example,...g.items].flatMap(text=>[text,t(text)]).join(' ').toLocaleLowerCase(locale).includes(needle)));
  for(const group of selected){
    const card=element('details','','skill-card');if(needle)card.open=true;
    const summary=element('summary');summary.append(element('span',group.title),element('small',`${group.items.length} competências`));
    const body=element('div','','skill-body');body.append(element('p',group.description));
    const badges=element('div','','skills');for(const item of group.items)badges.append(skillBadge(item,evidence));
    body.append(badges,element('p',group.example,'skill-example'),link(group.demoLabel,group.demoUrl));card.append(summary,body);container.append(card);
  }
  if(!selected.length)container.append(element('p','Nenhuma área encontrada. Tente outro termo.','status'));
  return selected.length;
}
export function renderExperience(container,entries){
  container.replaceChildren();for(const item of entries){const row=element('article','','resume-entry');row.append(element('p',item.period,'eyebrow'),element('h3',item.company),element('p',item.role,'resume-role'),element('p',item.description));container.append(row);}
}
export function renderEducation(container,profile){
  container.replaceChildren();container.append(element('h2','Formação acadêmica'));
  for(const item of profile.education){const row=element('article','','resume-entry');row.append(element('h3',item.title),element('p',`${item.institution} · ${item.status}`,'resume-role'),element('p',item.detail));container.append(row);}
  container.append(element('h2','Cursos e certificados'));
  for(const item of profile.courses){const row=element('article','','resume-entry compact');row.append(element('h3',item.title),element('p',`${item.institution} · ${item.detail}`));container.append(row);}
  const more=element('details','','skill-card');more.append(element('summary','Outras formações e estudos registrados'));
  const list=element('ul');for(const item of profile.additionalStudies)list.append(element('li',item));more.append(element('p','Registros de formação e estudo; conclusão e carga horária variam por curso.'),list);container.append(more);
}
export function renderLanguages(container,entries){
  container.replaceChildren();for(const item of entries){const row=element('article','','resume-entry');row.append(element('h3',item.name),element('p',item.level));container.append(row);}
}
export function renderSoftSkills(container,entries){
  container.replaceChildren();for(const item of entries){const row=element('article','','soft-card');row.append(element('h3',item.title),element('p',item.example));container.append(row);}
}
