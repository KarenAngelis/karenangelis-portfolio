// Currículo HTML legível sem JavaScript, gerado da mesma fonte do portfólio.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
const profile=JSON.parse(await readFile('web/data/profile.json','utf8'));
const escape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const text=value=>escape(value);
const external=(label,url)=>`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${text(label)}</a>`;
const skills=['React','Next.js','TypeScript','JavaScript','Python','FastAPI','NestJS','APIs REST','PostgreSQL','Git','Docker','pytest','Jest','Playwright'];
const selected=['StockMaster','JIP','Luniay','Clycka'];
const experience=profile.experience.slice(0,6).map(item=>`<article><div class="resume-entry-title"><h3>${text(item.company)}</h3><p>${text(item.period)}</p></div><p class="resume-role">${text(item.role)}</p><p>${text(item.description)}</p></article>`).join('\n');
const projects=selected.map(name=>profile.projects.find(project=>project.name===name)).map(project=>`<article><h3>${text(project.name)}</h3><p>${text(project.description)}</p><p>${external(project.linkLabel,project.url)}</p></article>`).join('\n');
const education=profile.education.map(item=>`<article><h3>${text(item.title)}</h3><p>${text(item.institution)} · <span>${text(item.status)}</span></p>${item.detail && item.detail !== 'Formação atual registrada no inventário profissional.' ? `<p>${text(item.detail)}</p>` : ''}</article>`).join('\n');
const languages=profile.languages.filter(item=>!item.level.includes('a atualizar')).map(item=>`<li><strong>${text(item.name)}</strong>: <span>${text(item.level)}</span></li>`).join('\n');
const output=`<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Currículo de Karen Angelis: desenvolvimento Full Stack, React, TypeScript, Python, FastAPI e NestJS. Experiência, projetos e formação."><meta name="theme-color" content="#101211"><title>Currículo · Karen Angelis</title><link rel="canonical" href="https://karenangelis.com/curriculo/"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/style.css"><link rel="stylesheet" href="/assets/i18n.css"><link rel="stylesheet" href="/assets/resume.css"><script type="module" src="/assets/i18n.js"></script><script type="module" src="/assets/resume.js"></script><script type="module" src="/assets/track.js"></script></head>
<body class="resume-page"><a class="skip" href="#curriculo">Ir para o conteúdo</a><header class="nav"><a class="brand" href="/" aria-label="Voltar ao portfólio">ka<span>✳</span></a><a class="text-link" href="/">Voltar ao portfólio</a></header>
<main id="curriculo" class="resume-document"><header class="resume-heading"><p class="eyebrow">CURRÍCULO / DESENVOLVIMENTO</p><h1>${text(profile.name)}</h1><p class="resume-headline">Desenvolvedora Full Stack</p><p class="resume-primary-stack" data-no-translate>React · Next.js · TypeScript · Python · FastAPI · NestJS</p><p>${text(profile.summary)}</p><nav class="resume-contacts" aria-label="Contatos profissionais">${external('LinkedIn',profile.linkedin)}${external('GitHub',profile.github)}${external('WhatsApp',profile.whatsapp)}</nav><div class="resume-actions"><button type="button" class="button lime" id="print-resume" data-track="carreira:imprimir-curriculo" hidden>Imprimir ou salvar em PDF</button><a class="text-link" href="/app/?version=kotlin">Experimentar o currículo em app</a></div><noscript><p>Você também pode imprimir esta página pelo menu do navegador.</p></noscript></header>
<section aria-labelledby="resume-skills"><h2 id="resume-skills">Competências principais</h2><ul class="resume-skills" data-no-translate>${skills.map(skill=>`<li>${text(skill)}</li>`).join('')}</ul></section>
<section aria-labelledby="resume-experience"><h2 id="resume-experience">Experiência profissional</h2>${experience}</section>
<section aria-labelledby="resume-projects"><h2 id="resume-projects">Projetos selecionados</h2>${projects}<p class="resume-note">Luniay: versão web disponível; aplicativo nativo ainda não lançado. Clycka: ativação de conectores depende da configuração do serviço.</p><p><a href="/#todos-projetos">Ver todos os projetos e estudos</a></p></section>
<section aria-labelledby="resume-education"><h2 id="resume-education">Formação</h2>${education}</section>
<section aria-labelledby="resume-languages"><h2 id="resume-languages">Idiomas</h2><ul>${languages}</ul></section>
<footer class="resume-footer"><a href="https://karenangelis.com/">karenangelis.com</a><p>Currículo disponível em HTML, sem instalação.</p></footer></main></body></html>
`;
const target='web/curriculo/index.html';
if(process.argv.includes('--check')){
 const current=await readFile(target,'utf8').catch(()=>'');
 if(current!==output)throw new Error('Currículo HTML desatualizado: rode npm run resume.');
 console.log('Currículo HTML confere com profile.json.');
}else{await mkdir('web/curriculo',{recursive:true});await writeFile(target,output);console.log('Currículo HTML atualizado.');}
