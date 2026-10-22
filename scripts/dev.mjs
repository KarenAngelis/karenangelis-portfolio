import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
import {spawn} from 'node:child_process';
const root=resolve('web');
let careerProcess;
if(process.env.CAREER_DEV_PYTHON){
  careerProcess=spawn(process.env.CAREER_DEV_PYTHON,['-m','uvicorn','main:app','--app-dir','apps/career-api','--host','127.0.0.1','--port','8010','--no-access-log'],{stdio:'inherit',env:{...process.env,CAREER_PUBLIC_URL:'http://127.0.0.1:4173',CAREER_DATA_DIR:process.env.CAREER_DATA_DIR||'/tmp/karen-career-dev',CAREER_PROFILE_DATA_DIR:resolve('web/data'),CAREER_WORKER_ENABLED:'false'}});
  process.on('exit',()=>careerProcess.kill());
}

const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.wasm':'application/wasm','.wasm':'application/wasm','.apk':'application/vnd.android.package-archive'};
http.createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://localhost');
    if(url.pathname.startsWith('/api/career/')){
      const upstream=http.request({hostname:'127.0.0.1',port:8010,path:req.url,method:req.method,headers:req.headers},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});
      upstream.on('error',()=>{if(!res.headersSent)res.writeHead(503,{'Content-Type':'application/json'}).end(JSON.stringify({detail:'Inicie a API de carreira para usar a área privada.'}));});
      req.pipe(upstream);return;
    }

    if(url.pathname==='/demos/kotlin'||url.pathname==='/demos/kotlin/'){res.writeHead(302,{Location:'/app/?version=kotlin'}).end();return;}
    const path=resolve(root,'.'+decodeURIComponent(url.pathname)+(url.pathname.endsWith('/')?'index.html':''));
    if(!path.startsWith(root+sep)){res.writeHead(403).end();return;}
    const data=await readFile(path);
    res.writeHead(200,{'Content-Type':types[extname(path)]||'application/octet-stream','Cache-Control':'no-store',...(extname(path)==='.apk'?{'Content-Disposition':'attachment; filename="karenangelis-curriculo.apk"'}:{})}).end(data);
  } catch {res.writeHead(404,{'Content-Type':'text/plain; charset=utf-8'}).end('Página não encontrada');}
}).listen(4173,'127.0.0.1',()=>console.log('Portfólio: http://localhost:4173'));

