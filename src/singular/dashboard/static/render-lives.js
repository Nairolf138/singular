import {fetchJson} from './api.js';
import {BADGE_TONE,liveState,livesTableState,na,scopeState,setPanelState} from './state.js';

const badge=(label,tone)=>`<span class='badge ${tone}'>${label}</span>`;

const renderLivesBuckets=(rows)=>{
  const activeInRegistry=(rows||[]).filter(row=>row.is_registry_active_life===true);
  const extinctInRuns=(rows||[]).filter(row=>row.extinction_seen_in_runs===true);
  const aliveList=document.getElementById('alive-lives');
  const deadList=document.getElementById('dead-lives');
  document.getElementById('alive-count').textContent=String(activeInRegistry.length);
  document.getElementById('dead-count').textContent=String(extinctInRuns.length);
  aliveList.innerHTML='';
  deadList.innerHTML='';
  for(const row of activeInRegistry){const li=document.createElement('li');li.textContent=row.life||na();aliveList.appendChild(li);} 
  for(const row of extinctInRuns){const li=document.createElement('li');li.textContent=row.life||na();deadList.appendChild(li);} 
  if(!activeInRegistry.length){const li=document.createElement('li');li.textContent='Aucune';aliveList.appendChild(li);} 
  if(!extinctInRuns.length){const li=document.createElement('li');li.textContent='Aucune';deadList.appendChild(li);} 
};

const renderLivesTable=(rows)=>{
  const body=document.getElementById('lives-table-body');
  body.innerHTML='';
  for(const row of rows||[]){
    const tr=document.createElement('tr');
    const score=row.current_health_score===null||row.current_health_score===undefined?na():Number(row.current_health_score).toFixed(1);
    const stability=row.stability===null||row.stability===undefined?na():`${(Number(row.stability)*100).toFixed(1)}%`;
    const lastActivity=row.last_activity||na();
    let badges='';
    if(row.selected_life){badges+=badge('Vie sélectionnée',BADGE_TONE.success);}else{badges+=badge('Vie non sélectionnée',BADGE_TONE.danger);} 
    if(row.is_registry_active_life){badges+=badge('Vie active dans le registre',BADGE_TONE.success);}else{badges+=badge(`Statut registre: ${row.life_status||na()}`,BADGE_TONE.danger);} 
    if(row.run_terminated){badges+=badge('Run terminé',BADGE_TONE.warning);} 
    if(row.extinction_seen_in_runs){badges+=badge('Extinction détectée',BADGE_TONE.danger);} 
    if(row.has_recent_activity){badges+=badge('Activité récente',BADGE_TONE.info);} 
    if(row.trend==='dégradation'){badges+=badge('dégradation',BADGE_TONE.warning);} 
    if((row.alerts_count||0)>0){badges+=badge(`${row.alerts_count} alertes`,BADGE_TONE.danger);} 
    tr.innerHTML=`<td>${row.life||na()}</td><td>${score}</td><td>${row.trend||na()}</td><td>${stability}</td><td>${lastActivity}</td><td>${row.iterations??0}</td><td>${badges}</td>`;
    body.appendChild(tr);
  }
  if(!(rows||[]).length){const tr=document.createElement('tr');tr.innerHTML="<td colspan='7'>Aucune vie ne correspond aux filtres.</td>";body.appendChild(tr);} 
};

const renderUnattachedRuns=(payload)=>{
  const panel=document.getElementById('unattached-runs-panel');
  const list=document.getElementById('unattached-runs-list');
  const runs=(payload?.runs)||[];
  const runsCount=Number(payload?.runs_count||0);
  const recordsCount=Number(payload?.records_count||0);
  document.getElementById('unattached-runs-count').textContent=String(runsCount);
  document.getElementById('unattached-records-count').textContent=String(recordsCount);
  list.innerHTML='';
  if(!runsCount){panel.classList.add('panel-hidden');return;}
  panel.classList.remove('panel-hidden');
  for(const item of runs){const li=document.createElement('li');li.textContent=`${item.run_id||'unknown'} · ${item.records_count||0} enregistrements`;list.appendChild(li);} 
};

export const loadLivesBoard=()=>{
  const q=new URLSearchParams();
  q.set('sort_by',livesTableState.sortBy);
  q.set('sort_order',livesTableState.sortOrder);
  if(document.getElementById('filter-active').checked){q.set('active_only','true');}
  if(document.getElementById('filter-degrading').checked){q.set('degrading_only','true');}
  if(document.getElementById('filter-dead').checked){q.set('dead_only','true');}
  const timeWindow=document.getElementById('filter-time-window').value||'all';
  q.set('time_window',timeWindow);
  const compareLives=(document.getElementById('filter-compare-lives').value||'').trim();
  if(compareLives){q.set('compare_lives',compareLives);} 
  if(scopeState.currentLifeOnly){q.set('current_life_only','true');}
  return fetchJson(`/lives/comparison?${q.toString()}`).then(d=>{
    const tableRows=d.table||[];
    renderLivesBuckets(Object.entries(d.lives||{}).map(([life,payload])=>({life,...payload})));
    renderLivesTable(tableRows);
    renderUnattachedRuns(d.unattached_runs);
    if(!tableRows.length){setPanelState('vies','empty','Aucune vie pour ces filtres. Ajustez la fenêtre ou retirez des filtres.');}
  });
};

export const renderLiveEvents=()=>{
  const pre=document.getElementById('live-events');
  const rows=liveState.events.map(item=>`${item.ts||na()} | ${item.run_id||na()} | ${item.event||'unknown'}`);
  pre.textContent=rows.join('\n');
  if(liveState.autoScroll){pre.scrollTop=pre.scrollHeight;}
};

export const updateLiveStatus=()=>{
  document.getElementById('live-status').textContent=liveState.paused?'Pause activée':'Lecture en direct';
  document.getElementById('live-toggle').textContent=liveState.paused?'Reprendre':'Pause';
};

export const renderGenealogyTree=(payload)=>{
  const nodes=payload?.nodes||[];
  const treeEl=document.getElementById('genealogy-tree');
  const socialEl=document.getElementById('social-network-tree');
  const conflictsEl=document.getElementById('active-conflicts');
  if(!nodes.length){treeEl.textContent='Aucune lignée enregistrée.';socialEl.textContent='Aucun réseau social.';conflictsEl.textContent='Aucun conflit.';return;}
  const bySlug=new Map(nodes.map(node=>[node.slug,node]));
  const children=new Map();
  for(const node of nodes){children.set(node.slug,[]);} 
  for(const node of nodes){for(const parent of (node.parents||[])){if(children.has(parent)){children.get(parent).push(node.slug);}}}
  const roots=nodes.filter(node=>(node.parents||[]).length===0).map(node=>node.slug);
  const lines=[];
  const visit=(slug,depth)=>{const node=bySlug.get(slug);if(!node){return;}const marker=node.active?'★':'•';const status=node.status==='extinct'?'✝':'✓';lines.push(`${'  '.repeat(depth)}${marker} ${node.name} (${node.slug}) [${status}]`);for(const child of (children.get(slug)||[])){visit(child,depth+1);}};
  for(const root of roots){visit(root,0);} 
  const detached=nodes.filter(node=>!roots.includes(node.slug)&&!(node.parents||[]).every(parent=>bySlug.has(parent)));
  for(const node of detached){lines.push(`• ${node.name} (${node.slug}) [orphan]`);} 
  treeEl.textContent=lines.join('\n');
  const socialLines=[];
  for(const node of nodes){const allies=(node.allies||[]).join(', ')||'-';const rivals=(node.rivals||[]).join(', ')||'-';socialLines.push(`${node.slug} | proximité=${Number(node.proximity_score||0.5).toFixed(2)} | alliés: ${allies} | rivaux: ${rivals}`);} 
  socialEl.textContent=socialLines.join('\n');
  const conflicts=payload?.active_conflicts||[];
  conflictsEl.textContent=conflicts.length?conflicts.map(c=>`${c.life_a} ⚔ ${c.life_b}`).join('\n'):'Aucun conflit actif.';
};

export const loadGenealogy=()=>fetchJson('/lives/genealogy').then(renderGenealogyTree).catch(error=>{document.getElementById('genealogy-tree').textContent='Impossible de charger la généalogie.';throw error;});

export const bindLivesHandlers=(reload=loadLivesBoard)=>{
  for(const button of document.querySelectorAll('#lives-table [data-sort]')){
    button.onclick=()=>{
      const next=button.getAttribute('data-sort');
      if(livesTableState.sortBy===next){livesTableState.sortOrder=livesTableState.sortOrder==='desc'?'asc':'desc';}
      else{livesTableState.sortBy=next;livesTableState.sortOrder='desc';}
      reload();
    };
  }
  document.getElementById('filter-active').onchange=()=>reload();
  document.getElementById('filter-degrading').onchange=()=>reload();
  document.getElementById('filter-dead').onchange=()=>reload();
  document.getElementById('filter-time-window').onchange=()=>reload();
  document.getElementById('filter-compare-lives').onchange=()=>reload();
};

export const bindLiveStreamHandlers=()=>{
  document.getElementById('live-toggle').onclick=()=>{liveState.paused=!liveState.paused;updateLiveStatus();if(!liveState.paused){renderLiveEvents();}};
  document.getElementById('live-autoscroll').onchange=e=>{liveState.autoScroll=Boolean(e.target.checked);if(liveState.autoScroll){renderLiveEvents();}};
};
