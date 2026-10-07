const tasks=[{id:'interface',title:'Criar a interface',stage:0},{id:'api',title:'Conectar a API',stage:1},{id:'tests',title:'Validar os testes',stage:0}];
const stages=['A fazer','Em andamento','Concluído'];
const board=document.querySelector('#demo-board');
let dragged=null;
function clearDrag(){board.querySelectorAll('.dragging,.drop-target').forEach(el=>el.classList.remove('dragging','drop-target'));dragged=null;}
function moveTask(id,stage,keyboard=false){
  const task=tasks.find(item=>item.id===id);if(!task||stage<0||stage>2)return;
  task.stage=stage;clearDrag();renderBoard();
  document.querySelector('#board-status').textContent=`${task.title} movida para ${stages[stage]}. ${tasks.filter(t=>t.stage===2).length} de 3 tarefas concluídas.`;
  if(keyboard)board.querySelector(`[data-task="${id}"]`).focus();
}
function renderBoard(){
  board.replaceChildren();
  stages.forEach((label,index)=>{
    const column=document.createElement('section');column.className='board-column';column.setAttribute('aria-label',label);column.dataset.stage=String(index);
    const heading=document.createElement('h4');heading.textContent=label+' · '+tasks.filter(t=>t.stage===index).length;column.append(heading);
    for(const task of tasks.filter(t=>t.stage===index)){
      const card=document.createElement('div');card.className='board-task';card.draggable=false;card.tabIndex=0;card.dataset.task=task.id;card.setAttribute('role','button');card.setAttribute('aria-label',`${task.title}. ${label}. Arraste para outra coluna ou use as setas esquerda e direita.`);
      const grip=document.createElement('span');grip.className='task-grip';grip.setAttribute('aria-hidden','true');const title=document.createElement('span');title.textContent=task.title;card.append(grip,title);
      card.addEventListener('keydown',event=>{if(event.key==='ArrowRight'||event.key==='ArrowLeft'){event.preventDefault();moveTask(task.id,task.stage+(event.key==='ArrowRight'?1:-1),true);}});
      let touch=null,ghost=null;
      function endTouch(event,cancel=false){
        if(!touch)return;const moving=touch.moving,target=document.elementFromPoint(event.clientX,event.clientY)?.closest('.board-column');ghost?.remove();ghost=null;touch=null;clearDrag();
        if(!cancel&&moving&&target&&board.contains(target))moveTask(task.id,Number(target.dataset.stage));
      }
      card.addEventListener('pointerdown',event=>{if(event.button!==0)return;touch={x:event.clientX,y:event.clientY,moving:false};card.setPointerCapture(event.pointerId);});
      card.addEventListener('pointermove',event=>{
        if(!touch)return;if(!touch.moving&&Math.hypot(event.clientX-touch.x,event.clientY-touch.y)<8)return;
        if(!touch.moving){touch.moving=true;dragged=task.id;card.classList.add('dragging');ghost=card.cloneNode(true);ghost.removeAttribute('role');ghost.removeAttribute('tabindex');ghost.removeAttribute('data-task');ghost.setAttribute('aria-hidden','true');ghost.classList.add('task-ghost');ghost.style.width=card.offsetWidth+'px';document.body.append(ghost);}
        ghost.style.left=event.clientX-ghost.offsetWidth/2+'px';ghost.style.top=event.clientY-25+'px';board.querySelectorAll('.drop-target').forEach(el=>el.classList.remove('drop-target'));
        const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('.board-column');if(target&&board.contains(target))target.classList.add('drop-target');
      });
      card.addEventListener('pointerup',event=>endTouch(event));card.addEventListener('pointercancel',event=>endTouch(event,true));card.addEventListener('lostpointercapture',event=>endTouch(event,true));column.append(card);
    }
    board.append(column);
  });
  const count=tasks.filter(t=>t.stage===2).length;document.querySelector('#board-status').textContent=`${count} de 3 tarefas concluídas. Arraste uma tarefa para experimentar.`;
}
document.querySelector('#reset-board').addEventListener('click',()=>{clearDrag();tasks.forEach(t=>t.stage=t.id==='api'?1:0);renderBoard();});renderBoard();
