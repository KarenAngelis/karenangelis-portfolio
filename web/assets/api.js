// Cliente das APIs do portfólio, compartilhado pelo console e pelo terminal.
const local=['localhost','127.0.0.1'].includes(location.hostname),production='https://karenangelis.com';
const services={trends:{port:8000,name:'FastAPI'},resume:{port:8080,name:'Go'}};
export const endpoints={
  news:{service:'trends',path:'/api/news',methods:['GET'],params:[{name:'q',value:'kotlin'},{name:'geo',value:'BR',options:['BR','PT','US','IT']},{name:'limit',value:'5'}],code:'trends-api'},
  profile:{service:'resume',path:'/api/profile',methods:['GET','POST'],params:[],code:'resume-api'},
  openapi:{service:'trends',path:'/openapi.json',methods:['GET'],params:[],code:'trends-api'}
};
const bases={};
// No ambiente local usa a API da máquina quando ela responde; senão, a API publicada (o CORS dela aceita localhost:4173).
async function base(service){
  if(!local)return location.origin;
  if(!bases[service]){
    const origin=`http://127.0.0.1:${services[service].port}`;
    bases[service]=fetch(origin+'/health',{signal:AbortSignal.timeout(900)}).then(response=>response.ok?origin:production).catch(()=>production);
  }
  return bases[service];
}
export function findEndpoint(path){return Object.keys(endpoints).find(key=>endpoints[key].path===path);}
export async function buildUrl(key,params={}){
  const endpoint=endpoints[key],query=new URLSearchParams(Object.entries(params).filter(([,value])=>value!=='')).toString();
  return (await base(endpoint.service))+endpoint.path+(query?'?'+query:'');
}
export async function request(key,params={},method='GET'){
  const url=await buildUrl(key,params),started=performance.now();
  const response=await fetch(url,{method,signal:AbortSignal.timeout(18000)}),text=await response.text();
  const result={url,method,status:response.status,statusText:response.statusText,ms:Math.round(performance.now()-started),bytes:new Blob([text]).size,type:response.headers.get('content-type')||'',cache:response.headers.get('cache-control')||'',text,service:services[endpoints[key].service].name,remote:local&&url.startsWith(production)};
  try{result.json=JSON.parse(text);}catch{}
  return result;
}
