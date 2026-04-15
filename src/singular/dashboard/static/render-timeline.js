import {fetchJson,withScope} from './api.js';
import {na,setPanelState} from './state.js';

const paintDiff=(raw)=>{
  const escaped=String(raw||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  return escaped.split('\n').map(line=>{
    if(line.startsWith('+')){return `<span class='diff-added'>${line}</span>`;}
    if(line.startsWith('-')){return `<span class='diff-removed'>${line}</span>`;}
    if(line.startsWith('@@')){return `<span class='diff-hunk'>${line}</span>`;}
    return line;
  }).join('\n');
};

export const showMutationDetail=(runId,index)=>fetch(`/api/runs/${runId}/mutations/${index}`).then(r=>r.json()).then(d=>{
  document.getElementById('timeline-summary').textContent=d.human_summary||d.decision_reason||'Aucun résumé disponible.';
  document.getElementById('timeline-impact').textContent=JSON.stringify(d.impact,null,2);
  document.getElementById('timeline-diff').innerHTML=paintDiff(d.diff)||'Aucun diff.';
});

export const loadTimeline=()=>fetchJson(withScope('/runs/latest')).then(meta=>{
  if(!meta.run){return {run_id:null,items:[]};}
  return fetchJson(`/api/runs/${meta.run}/timeline?page=1&page_size=120`);
}).then(data=>{
  const wrap=document.getElementById('timeline');
  const summary=document.getElementById('timeline-summary');
  const impact=document.getElementById('timeline-impact');
  const diff=document.getElementById('timeline-diff');
  wrap.innerHTML='';
  let mutationIndex=0;
  for(const item of data.items||[]){
    const row=document.createElement('div');
    row.className='timeline-item';
    const btn=document.createElement('button');
    btn.className='timeline-button';
    btn.textContent=`${item.event} · ${item.timestamp||na()}`;
    row.appendChild(btn);
    if(item.event==='mutation'&&data.run_id){
      const currentIndex=mutationIndex;
      mutationIndex+=1;
      btn.onclick=()=>showMutationDetail(data.run_id,currentIndex);
      const link=document.createElement('a');
      link.href=`/runs/${data.run_id}/mutations/${currentIndex}`;
      link.textContent='Voir détail';
      link.className='timeline-link';
      row.appendChild(link);
    }
    wrap.appendChild(row);
  }
  if(!(data.items||[]).length){
    summary.textContent='Aucun événement de frise disponible.';
    impact.textContent='';
    diff.textContent='';
    setPanelState('timeline-section','empty','Aucun événement pour le run courant.');
  }
});
