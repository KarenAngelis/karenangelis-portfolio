// Gera web/data/sources.json com o código real exibido pelo visualizador da página.
// `node scripts/sources.mjs` grava; `--check` falha quando o arquivo está desatualizado.
import {readFile,writeFile,stat,readdir} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
const compose='apps/resume-compose/shared/src';
const kotlin=`${compose}/commonMain/kotlin/com/karenangelis/curriculo/shared`;
const bundles={
  'resume-app':{title:'Currículo em app',stack:'Kotlin · Compose Multiplatform · WebAssembly',files:[`${kotlin}/ResumeApp.kt`,`${kotlin}/Profile.kt`,`${kotlin}/Localization.kt`,`${compose}/wasmJsMain/kotlin/com/karenangelis/curriculo/shared/Main.kt`,`${compose}/androidMain/kotlin/com/karenangelis/curriculo/shared/Platform.kt`,'apps/resume-compose/shared/build.gradle.kts']},
  'resume-api':{title:'API do currículo',stack:'Go · net/http',files:['apps/resume-api/main.go','apps/resume-api/main_test.go','apps/resume-api/Dockerfile']},
  'trends-api':{title:'API de notícias',stack:'Python · FastAPI',files:['apps/trends-api/main.py','apps/trends-api/test_api.py','apps/trends-api/Dockerfile']},
  board:{title:'Quadro de tarefas',stack:'JavaScript · Pointer Events',files:['web/assets/board.js']},
  terminal:{title:'Terminal do topo',stack:'JavaScript',files:['web/assets/terminal.js']},
  console:{title:'Console de API',stack:'JavaScript · Fetch',files:['web/assets/api-console.js','web/assets/api.js']},
  viewer:{title:'Este visualizador de código',stack:'JavaScript',files:['web/assets/code-viewer.js','scripts/sources.mjs']},
  i18n:{title:'Idiomas da página',stack:'JavaScript · MutationObserver',files:['web/assets/i18n.js']},
  stats:{title:'Contagem de visitas',stack:'Python · FastAPI · SQLite',files:['apps/stats-api/main.py','apps/stats-api/test_api.py','web/assets/track.js']},
  infra:{title:'Entrega e infraestrutura',stack:'Caddy · Docker Compose · GitHub Actions',files:['infra/Caddyfile','compose.yaml','.github/workflows/check.yml','.github/workflows/android.yml','scripts/check.mjs']}
};
const languages={'.kt':'kotlin','.kts':'kotlin','.go':'go','.py':'python','.js':'javascript','.mjs':'javascript','.yml':'yaml','.yaml':'yaml'};
const read=async path=>(await readFile(path,'utf8')).replace(/^﻿/,'').replace(/\r\n/g,'\n').trimEnd();
const count=async(path,pattern)=>((await read(path)).match(pattern)||[]).length;
const output={bundles:{},facts:{}};
for(const [id,bundle] of Object.entries(bundles)){
  output.bundles[id]={title:bundle.title,stack:bundle.stack,files:[]};
  for(const path of bundle.files){
    const name=path.split('/').pop();
    output.bundles[id].files.push({path,name,language:languages[extname(path)]||(name==='Dockerfile'?'docker':'text'),code:await read(path)});
  }
}
const app=(await readdir('web/app')).filter(name=>name.endsWith('.wasm'));
const manifest=JSON.parse(await read('package.json'));
output.facts={
  goTests:await count('apps/resume-api/main_test.go',/^func Test/gm),
  pythonTests:await count('apps/trends-api/test_api.py',/^\s+def test_/gm)+await count('apps/stats-api/test_api.py',/^\s+def test_/gm),
  npmDependencies:Object.keys({...manifest.dependencies,...manifest.devDependencies}).length,
  wasmBytes:(await Promise.all(app.map(name=>stat(resolve('web/app',name))))).reduce((total,file)=>total+file.size,0),
  locales:4
};
const target='web/data/sources.json',json=JSON.stringify(output,null,1)+'\n';
if(process.argv.includes('--check')){
  const current=await readFile(target,'utf8').catch(()=>'');
  if(current.replace(/\r\n/g,'\n')!==json)throw new Error('web/data/sources.json desatualizado: rode `npm run sources`.');
  console.log('sources.json confere com o código-fonte.');
}else{await writeFile(target,json);console.log(`${Object.keys(bundles).length} conjuntos de código gravados em ${target}.`);}
