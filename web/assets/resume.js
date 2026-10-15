// A leitura do currículo não depende deste script.
const printButton=document.querySelector('#print-resume');
if(printButton){printButton.hidden=false;printButton.addEventListener('click',()=>window.print());}
