export function configureNativeLink(anchor){
  anchor.href='/app/?version=kotlin';
  anchor.removeAttribute('download');
  anchor.target='_blank';anchor.rel='noopener noreferrer';
  anchor.setAttribute('aria-label','Testar currículo interativo no navegador');
  const label=anchor.querySelector('[data-app-label]');
  if(label) label.textContent='Testar no navegador';
}
document.querySelectorAll('[data-resume-app], [data-native-app]').forEach(configureNativeLink);
