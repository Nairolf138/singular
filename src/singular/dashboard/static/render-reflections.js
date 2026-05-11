import {fetchJson,withScope} from './api.js';
import {na,setPanelState} from './state.js';

export const loadReflections=()=>fetchJson(withScope('/runs/latest')).then(meta=>{
  if(!meta.run){return {run_id:null,items:[]};}
  const q=new URLSearchParams();
  const objective=document.getElementById('reflection-objective')?.value||'';
  const mood=document.getElementById('reflection-mood')?.value||'';
  const success=document.getElementById('reflection-success')?.value||'';
  if(objective){q.set('objective',objective);}
  if(mood){q.set('mood',mood);}
  if(success){q.set('success',success);}
  const suffix=q.toString()?`?${q.toString()}`:'';
  return fetchJson(`/api/runs/${meta.run}/consciousness${suffix}`);
}).then(data=>{
  const wrap=document.getElementById('reflections-timeline');
  const detail=document.getElementById('reflections-detail');
  if(!wrap||!detail){return;}
  wrap.innerHTML='';
  for(const item of data.items||[]){
    const row=document.createElement('div');
    row.className='timeline-item';
    const btn=document.createElement('button');
    btn.className='timeline-button';
    const mood=item.emotional_state?.mood||na();
    const objective=item.objective||na();
    btn.textContent=`${item.ts||na()} · ${objective} · ${mood}`;
    btn.onclick=()=>{if(detail){detail.textContent=JSON.stringify(item,null,2);}};
    row.appendChild(btn);
    wrap.appendChild(row);
  }
  if(!(data.items||[]).length){
    detail.textContent='Aucune réflexion disponible pour ces filtres.';
    setPanelState('reflections-section','empty','Aucune réflexion disponible. Essayez d’élargir les filtres.');
  }
});

export const bindReflectionHandlers=(reload=loadReflections)=>{
  const applyButton=document.getElementById('reflection-apply');
  if(applyButton){applyButton.onclick=()=>reload();}
};
