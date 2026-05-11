import {normalizeItem} from './render-quests.js';

export const renderObjectivesSection=payload=>{
  const rows=(Array.isArray(payload?.items)?payload.items:[]).map(item=>normalizeItem(item,'objectif'));
  const tbody=document.getElementById('objectives-table-body');
  if(!tbody){return;}
  tbody.innerHTML='';
  if(!rows.length){
    const tr=document.createElement('tr');
    tr.className='table-state-empty';
    tr.innerHTML="<td colspan='6'>Aucun objectif disponible.</td>";
    tbody.appendChild(tr);
  }else{
    for(const row of rows){
      const tr=document.createElement('tr');
      tr.innerHTML=`<td>${row.title} · ${row.next_step}</td><td>${row.status}</td><td>${row.priority}</td><td>${row.owner}</td><td>${row.last_update}</td><td>${row.blockage}</td>`;
      tbody.appendChild(tr);
    }
  }

  const raw=document.getElementById('objectives-json-raw');
  if(raw){raw.textContent=JSON.stringify(payload||{items:[]},null,2);}
};
