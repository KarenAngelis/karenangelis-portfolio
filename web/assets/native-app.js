const apk='/downloads/karenangelis-curriculo.apk';
export function configureNativeLink(anchor){
  const android=/Android/i.test(navigator.userAgent);
  if(android){
    const fallback=encodeURIComponent(new URL(apk,location.origin).href);
    anchor.href=`intent://curriculo#Intent;scheme=karenangelis;package=com.karenangelis.curriculo;S.browser_fallback_url=${fallback};end`;
    anchor.removeAttribute('download');
  }else{anchor.href=apk;anchor.setAttribute('download','karenangelis-curriculo.apk');}
  anchor.removeAttribute('target');anchor.setAttribute('aria-label',android?'Abrir app Android ou baixar o APK':'Baixar aplicativo Android em APK');
}
document.querySelectorAll('[data-native-app]').forEach(configureNativeLink);
