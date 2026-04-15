import {normalizeItem} from './render-quests.js';

const bindJsonToggle=(buttonId,rawId)=>{
  const button=document.getElementById(buttonId);
  const raw=document.getElementById(rawId);
  if(!button||!raw||button.dataset.bound==='true'){return;}
  button.dataset.bound='true';
  button.addEventListener('click',()=>{
    const isHidden=raw.classList.contains('panel-hidden');
    raw.classList.toggle('panel-hidden',!isHidden);
    button.textContent=isHidden?'Masquer JSON':'Voir JSON';
    button.setAttribute('aria-expanded',isHidden?'true':'false');
  });
};

export const renderConversationsSection=payload=>{
  const rows=(Array.isArray(payload?.items)?payload.items:[]).map(item=>normalizeItem(item,'conversation'));
  const tbody=document.getElementById('conversations-table-body');
  if(!tbody){return;}
  tbody.innerHTML='';
  if(!rows.length){
    const tr=document.createElement('tr');
    tr.className='table-state-empty';
    tr.innerHTML="<td colspan='6'>Aucune conversation disponible.</td>";
    tbody.appendChild(tr);
  }else{
    for(const row of rows){
      const tr=document.createElement('tr');
      tr.innerHTML=`<td>${row.title} · ${row.next_step}</td><td>${row.status}</td><td>${row.priority}</td><td>${row.owner}</td><td>${row.last_update}</td><td>${row.blockage}</td>`;
      tbody.appendChild(tr);
    }
  }

  const raw=document.getElementById('conversations-json-raw');
  if(raw){raw.textContent=JSON.stringify(payload||{items:[]},null,2);}
  bindJsonToggle('conversations-json-toggle','conversations-json-raw');
};
