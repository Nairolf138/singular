import {fetchJson} from './api.js';
import {BADGE_TONE,liveState,livesTableState,na,scopeState,setPanelState} from './state.js';

const badge=(label,tone)=>`<span class='badge ${tone}'>${label}</span>`;
const safeText=value=>String(value??na());
const escapeHtml=value=>safeText(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');

const SORT_PRESETS={
  watch:{
    sortBy:'score',
    sortOrder:'asc',
    apply:rows=>[...rows].sort((a,b)=>{
      const riskDiff=(Number(b.__riskLevel||0)-Number(a.__riskLevel||0));
      if(riskDiff!==0){return riskDiff;}
      const trendA=a.trend==='dégradation'?0:(a.trend==='plateau'?1:2);
      const trendB=b.trend==='dégradation'?0:(b.trend==='plateau'?1:2);
      if(trendA!==trendB){return trendA-trendB;}
      return Number(b.alerts_count||0)-Number(a.alerts_count||0);
    }),
  },
  active:{
    sortBy:'iterations',
    sortOrder:'desc',
    apply:rows=>[...rows].sort((a,b)=>{
      const iterationDiff=Number(b.iterations||0)-Number(a.iterations||0);
      if(iterationDiff!==0){return iterationDiff;}
      return String(b.last_activity||'').localeCompare(String(a.last_activity||''));
    }),
  },
  new:{
    sortBy:'last_activity',
    sortOrder:'desc',
    apply:rows=>[...rows].sort((a,b)=>String(b.last_activity||'').localeCompare(String(a.last_activity||''))),
  },
  custom:{
    sortBy:null,
    sortOrder:null,
    apply:rows=>[...rows],
  },
};

const livesUiState={
  quickFilter:'all',
  focus:'all',
  selectedLife:null,
  rowsByLife:new Map(),
};

const rowStateSummary=row=>{
  if(row.extinction_seen_in_runs){return {label:'Extinction',tone:'summary-critical'};}
  if(row.is_registry_active_life){return {label:'Active',tone:'summary-ok'};}
  return {label:'Hors registre',tone:'summary-warning'};
};

const rowRiskSummary=row=>{
  if(row.extinction_seen_in_runs){return {label:'Critique',tone:'summary-critical',level:3};}
  const alerts=Number(row.alerts_count||0);
  if(alerts>=2||row.trend==='dégradation'){return {label:'Élevé',tone:'summary-warning',level:2};}
  if(alerts>0){return {label:'Modéré',tone:'summary-warning',level:1};}
  return {label:'Faible',tone:'summary-ok',level:0};
};

const rowActivitySummary=row=>{
  if(row.run_terminated){return {label:'Run terminé',tone:'summary-warning'};}
  if(row.has_recent_activity){return {label:'Récente',tone:'summary-ok'};}
  return {label:'Aucune récente',tone:'summary-muted'};
};

const summarizeBadges=row=>{
  let badges='';
  if(row.selected_life){badges+=badge('Vie sélectionnée',BADGE_TONE.success);}else{badges+=badge('Vie non sélectionnée',BADGE_TONE.danger);}
  if(row.is_registry_active_life){badges+=badge('Vie active dans le registre',BADGE_TONE.success);}else{badges+=badge(`Statut registre: ${row.life_status||na()}`,BADGE_TONE.danger);}
  if(row.run_terminated){badges+=badge('Run terminé',BADGE_TONE.warning);}
  if(row.extinction_seen_in_runs){badges+=badge('Extinction détectée',BADGE_TONE.danger);}
  if(row.has_recent_activity){badges+=badge('Activité récente',BADGE_TONE.info);}
  if(row.trend==='dégradation'){badges+=badge('dégradation',BADGE_TONE.warning);}
  if((row.alerts_count||0)>0){badges+=badge(`${row.alerts_count} alertes`,BADGE_TONE.danger);}
  return badges;
};

const renderLivesBuckets=(rows,contract)=>{
  const activeInRegistry=(rows||[]).filter(row=>row.is_registry_active_life===true);
  const extinctInRuns=(rows||[]).filter(row=>row.extinction_seen_in_runs===true);
  const counts=contract?.counts||{};
  const labels=contract?.labels||{};
  const aliveList=document.getElementById('alive-lives');
  const deadList=document.getElementById('dead-lives');
  document.getElementById('alive-count').textContent=String(counts.alive_lives??activeInRegistry.length);
  document.getElementById('dead-count').textContent=String(counts.dead_lives??extinctInRuns.length);
  document.getElementById('alive-count').title=labels.alive_lives||'Vies vivantes';
  document.getElementById('dead-count').title=labels.dead_lives||'Vies mortes';
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
    tr.className='lives-row';
    tr.tabIndex=0;
    tr.dataset.life=row.life||'';
    if(row.life&&row.life===livesUiState.selectedLife){tr.classList.add('selected');}
    const score=row.current_health_score===null||row.current_health_score===undefined?na():Number(row.current_health_score).toFixed(1);
    const stability=row.stability===null||row.stability===undefined?na():`${(Number(row.stability)*100).toFixed(1)}%`;
    const lastActivity=row.last_activity||na();
    const state=rowStateSummary(row);
    const risk=rowRiskSummary(row);
    const activity=rowActivitySummary(row);
    tr.innerHTML=`<td>${escapeHtml(row.life||na())}</td><td>${score}</td><td>${escapeHtml(row.trend||na())}</td><td>${stability}</td><td>${escapeHtml(lastActivity)}</td><td>${row.iterations??0}</td><td><span class='summary-pill ${state.tone}'>${state.label}</span></td><td><span class='summary-pill ${risk.tone}'>${risk.label}</span></td><td><span class='summary-pill ${activity.tone}'>${activity.label}</span></td>`;
    tr.onclick=()=>showLifeDetails(row.life||'');
    tr.onkeydown=event=>{
      if(event.key==='Enter'||event.key===' '){
        event.preventDefault();
        showLifeDetails(row.life||'');
      }
    };
    body.appendChild(tr);
  }
  if(!(rows||[]).length){const tr=document.createElement('tr');tr.innerHTML="<td colspan='9'>Aucune vie ne correspond aux filtres.</td>";body.appendChild(tr);}
};

const showLifeDetails=lifeName=>{
  const panel=document.getElementById('life-detail-panel');
  const content=document.getElementById('life-detail-content');
  if(!panel||!content){return;}
  const row=lifeName?livesUiState.rowsByLife.get(lifeName):null;
  if(!row){
    panel.classList.add('panel-hidden');
    content.textContent='Aucune vie sélectionnée.';
    livesUiState.selectedLife=null;
    return;
  }
  panel.classList.remove('panel-hidden');
  livesUiState.selectedLife=lifeName;
  const metadata=[
    ['Vie',row.life],
    ['Statut registre',row.life_status],
    ['Score courant',row.current_health_score===null||row.current_health_score===undefined?na():Number(row.current_health_score).toFixed(1)],
    ['Stabilité',row.stability===null||row.stability===undefined?na():`${(Number(row.stability)*100).toFixed(1)}%`],
    ['Tendance',row.trend],
    ['Dernière activité',row.last_activity],
    ['Itérations',row.iterations??0],
    ['Alertes',row.alerts_count??0],
    ['Run terminé',row.run_terminated?'oui':'non'],
    ['Extinction runs',row.extinction_seen_in_runs?'oui':'non'],
  ];
  const metadataRows=metadata.map(([key,value])=>`<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(value)}</td></tr>`).join('');
  content.innerHTML=`<div class='detail-badges'>${summarizeBadges(row)||badge('Aucun badge',BADGE_TONE.info)}</div><table class='table-base life-meta-table'><tbody>${metadataRows}</tbody></table><h4>Timeline vitale</h4><pre>${escapeHtml(JSON.stringify(row.vital_timeline||{},null,2))}</pre>`;
  document.querySelectorAll('#lives-table-body tr.lives-row').forEach(node=>{
    node.classList.toggle('selected',node.dataset.life===lifeName);
  });
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
  const presetKey=document.getElementById('filter-sort-preset')?.value||'watch';
  const preset=SORT_PRESETS[presetKey]||SORT_PRESETS.watch;
  q.set('sort_by',preset.sortBy??livesTableState.sortBy);
  q.set('sort_order',preset.sortOrder??livesTableState.sortOrder);
  const timeWindow=document.getElementById('filter-time-window').value||'all';
  q.set('time_window',timeWindow);
  if(livesUiState.quickFilter==='active'){q.set('active_only','true');}
  if(livesUiState.quickFilter==='degrading'){q.set('degrading_only','true');}
  if(livesUiState.quickFilter==='dead'){q.set('dead_only','true');}
  if(scopeState.currentLifeOnly){q.set('current_life_only','true');}
  return fetchJson(`/lives/comparison?${q.toString()}`).then(d=>{
    const mappedRows=(d.table||[]).map(row=>{
      const risk=rowRiskSummary(row);
      return {...row,__riskLevel:risk.level,__stateSummary:rowStateSummary(row),__riskSummary:risk,__activitySummary:rowActivitySummary(row)};
    });
    let tableRows=preset.apply(mappedRows);
    if(livesUiState.focus==='selected'){tableRows=tableRows.filter(row=>row.selected_life);}
    if(livesUiState.focus==='at_risk'){tableRows=tableRows.filter(row=>(row.__riskLevel||0)>=1);}
    livesUiState.rowsByLife=new Map(mappedRows.map(row=>[row.life,row]));
    renderLivesBuckets(Object.entries(d.lives||{}).map(([life,payload])=>({life,...payload})),d.life_metrics_contract);
    renderLivesTable(tableRows);
    if(livesUiState.selectedLife&&livesUiState.rowsByLife.has(livesUiState.selectedLife)){showLifeDetails(livesUiState.selectedLife);}
    else if(tableRows.length){showLifeDetails(tableRows[0].life||'');}
    else{showLifeDetails('');}
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
      const presetSelect=document.getElementById('filter-sort-preset');
      if(presetSelect){presetSelect.value='custom';}
      reload();
    };
  }
  document.querySelectorAll('#lives-quick-filters .filter-chip').forEach(chip=>{
    chip.onclick=()=>{
      livesUiState.quickFilter=chip.dataset.filterKey||'all';
      document.querySelectorAll('#lives-quick-filters .filter-chip').forEach(node=>{
        const active=node===chip;
        node.classList.toggle('active',active);
        node.setAttribute('aria-pressed',active?'true':'false');
      });
      reload();
    };
  });
  document.querySelectorAll('#lives-focus-chips .filter-chip').forEach(chip=>{
    chip.onclick=()=>{
      livesUiState.focus=chip.dataset.focusKey||'all';
      document.querySelectorAll('#lives-focus-chips .filter-chip').forEach(node=>{
        const active=node===chip;
        node.classList.toggle('active',active);
        node.setAttribute('aria-pressed',active?'true':'false');
      });
      reload();
    };
  });
  document.getElementById('filter-sort-preset').onchange=()=>reload();
  document.getElementById('filter-time-window').onchange=()=>reload();
};

export const bindLiveStreamHandlers=()=>{
  document.getElementById('live-toggle').onclick=()=>{liveState.paused=!liveState.paused;updateLiveStatus();if(!liveState.paused){renderLiveEvents();}};
  document.getElementById('live-autoscroll').onchange=e=>{liveState.autoScroll=Boolean(e.target.checked);if(liveState.autoScroll){renderLiveEvents();}};
};
