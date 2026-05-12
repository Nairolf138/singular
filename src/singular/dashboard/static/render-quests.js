import {na} from './state.js';

const requiredField=(item,key,fallback)=>{
  const value=item?.[key];
  if(value===null||value===undefined||value===''){return fallback;}
  return String(value);
};

const normalizeItem=(item,fallbackTitle='quête')=>({
  title: requiredField(item,'title',String(item?.name||item?.objective||fallbackTitle)),
  status: requiredField(item,'status','unknown'),
  last_update: requiredField(item,'last_update',String(item?.updated_at||item?.completed_at||item?.started_at||na())),
  next_step: requiredField(item,'next_step',String(item?.next_action||item?.objective||na())),
  priority: requiredField(item,'priority',String(item?.priority_level||'normal')),
  owner: requiredField(item,'owner',String(item?.assignee||item?.life||na())),
  blockage: requiredField(item,'blockage',String(item?.blocked_by||item?.blocker||'aucun')),
});

const appendCell=(row,value)=>{const cell=document.createElement('td');cell.textContent=String(value??na());row.appendChild(cell);return cell;};

const renderRows=(rows,tbodyId)=>{
  const tbody=document.getElementById(tbodyId);
  if(!tbody){return;}
  tbody.innerHTML='';
  if(!rows.length){
    const tr=document.createElement('tr');
    tr.className='table-state-empty';
    const td=document.createElement('td');
    td.colSpan=6;
    td.textContent='Aucun élément disponible.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
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
};

export const renderQuestsSection=payload=>{
  const active=Array.isArray(payload?.active)?payload.active:[];
  const completed=Array.isArray(payload?.completed)?payload.completed:[];
  const rows=[...active,...completed].map(item=>normalizeItem(item,'quête'));
  renderRows(rows,'quests-table-body');
  const raw=document.getElementById('quests-json-raw');
  if(raw){raw.textContent=JSON.stringify(payload||{active:[],completed:[]},null,2);}
};

export {normalizeItem};
