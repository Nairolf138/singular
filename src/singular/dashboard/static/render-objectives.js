import {na} from './state.js';
import {normalizeItem} from './render-quests.js';

const appendCell=(row,value)=>{const cell=document.createElement('td');cell.textContent=String(value??na());row.appendChild(cell);return cell;};

export const renderObjectivesSection=payload=>{
  const rows=(Array.isArray(payload?.items)?payload.items:[]).map(item=>normalizeItem(item,'objectif'));
  const tbody=document.getElementById('objectives-table-body');
  if(!tbody){return;}
  tbody.innerHTML='';
  if(!rows.length){
    const tr=document.createElement('tr');
    tr.className='table-state-empty';
    const td=document.createElement('td');
    td.colSpan=6;
    td.textContent='Aucun objectif disponible.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }else{
    for(const row of rows){
      const tr=document.createElement('tr');
      appendCell(tr,`${row.title} · ${row.next_step}`);
      appendCell(tr,row.status);
      appendCell(tr,row.priority);
      appendCell(tr,row.owner);
      appendCell(tr,row.last_update);
      appendCell(tr,row.blockage);
      tbody.appendChild(tr);
    }
  }

  const raw=document.getElementById('objectives-json-raw');
  if(raw){raw.textContent=JSON.stringify(payload||{items:[]},null,2);}
};
