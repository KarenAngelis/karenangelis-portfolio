const apk='/downloads/karenangelis-curriculo.apk';
export function configureNativeLink(anchor){
  const android=/Android/i.test(navigator.userAgent);
  if(android){
    const fallback=encodeURIComponent(new URL(apk,location.origin).href);
    anchor.href=`intent://curriculo#Intent;scheme=karenangelis;package=com.karenangelis.curriculo;S.browser_fallback_url=${fallback};end`;
    anchor.removeAttribute('download');
  }else{anchor.href='/demos/kotlin/';anchor.removeAttribute('download');}
  anchor.removeAttribute('target');
  if(!android){anchor.target='_blank';anchor.rel='noopener noreferrer';}
  anchor.setAttribute('aria-label',android?'Abrir app Android ou baixar o APK':'Testar currículo interativo no navegador');
  const label=anchor.querySelector('[data-app-label]');
  if(label) label.textContent=android?'Abrir no Android':'Testar no navegador';
}
document.querySelectorAll('[data-native-app]').forEach(configureNativeLink);
