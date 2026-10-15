import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';

const html=await readFile('web/index.html','utf8');
const resume=await readFile('web/curriculo/index.html','utf8');
const profile=JSON.parse(await readFile('web/data/profile.json','utf8'));
const translations=JSON.parse(await readFile('web/data/translations.json','utf8'));

test('projects and an HTML résumé are reachable before the laboratory',()=>{
  assert.ok(html.indexOf('id="projetos"')<html.indexOf('id="laboratorio"'));
  const hero=html.slice(html.indexOf('<section class="hero"'),html.indexOf('id="projetos"'));
  assert.match(hero,/href="\/curriculo\/"/);
  assert.match(hero,/href="#projetos"/);
  for(const skill of ['React','TypeScript','Python','FastAPI','NestJS'])assert.ok(hero.includes(skill));
});

test('interactive experiences and the full project inventory remain available',()=>{
  for(const id of ['terminal','laboratorio','console','arquitetura','habilidades','todos-projetos','project-list']){
    assert.match(html,new RegExp(`id="${id}"`));
  }
  assert.equal(profile.projects.length,12);
  assert.match(html,/href="\/app\/\?version=kotlin"/);
  assert.match(html,/data-resume-app/);
  assert.equal((html.match(/class="featured-card"/g)||[]).length,3);
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  assert.equal(new Set(ids).size,ids.length,'HTML IDs must remain unique');
});

test('the résumé contains useful content without fetching data or running JavaScript',()=>{
  assert.match(resume,/<h1>Karen Angelis<\/h1>/);
  for(const section of ['Experiência profissional','Projetos selecionados','Formação','Idiomas'])assert.ok(resume.includes(section));
  for(const name of ['WEG','StockMaster','JIP','Luniay','Clycka'])assert.ok(resume.includes(name));
  assert.match(resume,/serviço original inativo/);
  assert.match(resume,/aplicativo nativo ainda não lançado/);
  assert.match(resume,/ativação de conectores depende/);
  assert.match(resume,/<noscript>/);
  assert.match(resume,/id="print-resume"[^>]*hidden/);
  assert.doesNotMatch(resume,/\.pdf["?]/,'Do not invent an existing downloadable PDF');
});

test('NestJS is practical backend experience, while StockMaster stays JavaScript',()=>{
  assert.ok(profile.skillGroups.find(group=>group.id==='backend').items.includes('NestJS'));
  assert.ok(!profile.skillGroups.find(group=>group.id==='complementary').items.includes('NestJS'));
  const stock=html.slice(html.indexOf('<h3>StockMaster</h3>'),html.indexOf('<h3>Luniay</h3>'));
  assert.match(stock,/React · JavaScript · FastAPI · PostgreSQL/);
  assert.doesNotMatch(stock,/TypeScript/);
});

test('new recruiter and résumé labels are translated into all supported languages',()=>{
  for(const source of ['Karen Angelis · Desenvolvedora Full Stack','Desenvolvedora','Ver projetos','Ler currículo','Currículo','Conversar sobre uma oportunidade','Explorar o laboratório','PROJETOS / CÓDIGO E CONTEXTO','Da interface','às regras de negócio.','Ver todos os projetos e estudos','Ler experiência e formação','Currículo · Karen Angelis','Desenvolvedora Full Stack','Imprimir ou salvar em PDF','Experimentar o currículo em app','Competências principais','Experiência profissional','Projetos selecionados','Currículo disponível em HTML, sem instalação.',profile.summary]){
    for(const language of ['en-US','it-IT','pt-PT'])assert.ok(translations[source]?.[language],`${source}: ${language}`);
  }
});

test('responsive navigation wraps and the résumé has a print stylesheet',async()=>{
  assert.match(await readFile('web/assets/style.css','utf8'),/\.nav nav\{flex-wrap:wrap/);
  const css=await readFile('web/assets/resume.css','utf8');
  assert.match(css,/@media print/);
  assert.match(css,/\.resume-actions \[hidden\]\{display:none!important\}/,'Print action stays hidden without JavaScript');
  assert.match(css,/break-inside:avoid/);
  assert.match(css,/@media\(max-width:560px\)/);
});
