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

const renderRows=(rows,tbodyId)=>{
  const tbody=document.getElementById(tbodyId);
  if(!tbody){return;}
  tbody.innerHTML='';
  if(!rows.length){
    const tr=document.createElement('tr');
    tr.className='table-state-empty';
    tr.innerHTML="<td colspan='6'>Aucun élément disponible.</td>";
    tbody.appendChild(tr);
    return;
  }
  for(const row of rows){
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${row.title} · ${row.next_step}</td><td>${row.status}</td><td>${row.priority}</td><td>${row.owner}</td><td>${row.last_update}</td><td>${row.blockage}</td>`;
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
