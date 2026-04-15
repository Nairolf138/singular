// Dashboard module state & constants
const HOST_SENSORS_THRESHOLD={cpuWarn:85,cpuCritical:95,ramWarn:80,ramCritical:92,tempWarn:75,tempCritical:85,diskCritical:95};
const BADGE_TONE={
  success:'badge-success',
  danger:'badge-danger',
  warning:'badge-warning',
  info:'badge-info',
};

const ws=new WebSocket(`ws://${location.host}/ws`);
const livesTableState={sortBy:'score',sortOrder:'desc'};
const liveState={paused:false,autoScroll:true,events:[]};
const scopeState={currentLifeOnly:false};
const schedulerState={paused:false};
const schedulerTasks=new Map();
let schedulerTimer=null;
const schedulerConfig={
  tickMs:500,
  backoff:{baseMs:1500,maxMs:30000,multiplier:2},
  frequencies:{
    context:7000,
    cockpit:5000,
    ecosystem:5000,
    timeline:4000,
    lives:4000,
    reflections:6000,
    genealogy:10000,
    quests:10000,
    hostVitals:5000,
  },
};
const schedulerLabelIds={
  context:'parametres',
  cockpit:'cockpit',
  ecosystem:'cockpit',
  timeline:'timeline-section',
  lives:'vies',
  reflections:'reflections-section',
  genealogy:'vies',
  quests:'parametres',
  hostVitals:'cockpit',
};
const panelBindings={
  cockpit:{panelId:'cockpit',emptyMessage:'Aucune donnée cockpit disponible.'},
  timeline:{panelId:'timeline-section',emptyMessage:'Aucun événement de timeline disponible.'},
  lives:{panelId:'vies',emptyMessage:'Aucune vie disponible pour les filtres actuels.'},
  reflections:{panelId:'reflections-section',emptyMessage:'Aucune réflexion pour ces filtres.'},
  hostVitals:{panelId:'host-vitals-panel',emptyMessage:'Aucune métrique hôte exploitable.'},
};
const panelFirstLoadDone=new Set();
const staleTimeoutTasks=new Set();
const PROLONGED_TIMEOUT_THRESHOLD=2;
const fmtTimestamp=(value=new Date())=>{
  const d=value instanceof Date?value:new Date(value);
  if(Number.isNaN(d.getTime())){return 'n/a';}
  return d.toLocaleString('fr-FR',{hour12:false});
};
const ensureUpdateLabel=(taskName)=>{
  const hostSection=document.getElementById(schedulerLabelIds[taskName]||'');
  if(!hostSection){return null;}
  const labelId=`last-update-${taskName}`;
  let label=document.getElementById(labelId);
  if(!label){
    label=document.createElement('div');
    label.id=labelId;
    label.className='status-muted';
    label.textContent='Dernière mise à jour: jamais';
    hostSection.appendChild(label);
  }
  return label;
};
const markUpdated=(taskName,at)=>{
  const label=ensureUpdateLabel(taskName);
  if(label){label.textContent=`Dernière mise à jour (${taskName}): ${fmtTimestamp(at)}`;}
};
const markUpdateError=(taskName,error)=>{
  const label=ensureUpdateLabel(taskName);
  if(label){label.textContent=`Dernière mise à jour (${taskName}): erreur · ${error?.message||'échec réseau/API'}`;}
};
const shouldBackoff=(error)=>Boolean(error);
const registerTask=(name,loader,intervalMs)=>{
  schedulerTasks.set(name,{name,loader,intervalMs,nextRunAt:0,inFlight:false,errorCount:0,lastRunAt:null});
};
const runTask=async task=>{
  if(task.inFlight||schedulerState.paused){return;}
  task.inFlight=true;
  task.lastRunAt=Date.now();
  const binding=panelBindings[task.name];
  if(binding){setPanelState(binding.panelId,'loading','Chargement en cours…');}
  try{
    await task.loader();
    task.errorCount=0;
    task.nextRunAt=Date.now()+task.intervalMs;
    markUpdated(task.name,new Date());
    if(binding){
      const layer=document.getElementById(binding.panelId)?.querySelector(':scope > .state-layer');
      if(!layer||layer.dataset.state==='loading'){setPanelState(binding.panelId,'ready');}
      panelFirstLoadDone.add(binding.panelId);
    }
    markStaleTimeout(task.name,false);
  }catch(error){
    if(shouldBackoff(error)){
      task.errorCount+=1;
      const factor=schedulerConfig.backoff.multiplier**(task.errorCount-1);
      const retryIn=Math.min(schedulerConfig.backoff.maxMs,schedulerConfig.backoff.baseMs*factor);
      task.nextRunAt=Date.now()+retryIn;
      markUpdateError(task.name,error);
      if(binding){
        const actionable=`API indisponible, nouvelle tentative dans ${Math.ceil(retryIn/1000)}s.`;
        setPanelState(binding.panelId,'error',actionable);
      }
      markStaleTimeout(task.name,error?.code==='timeout'&&task.errorCount>=PROLONGED_TIMEOUT_THRESHOLD);
    }else{
      task.nextRunAt=Date.now()+task.intervalMs;
    }
  }finally{
    task.inFlight=false;
  }
};
const schedulerTick=()=>{
  if(schedulerState.paused){return;}
  const now=Date.now();
  for(const task of schedulerTasks.values()){
    if(task.nextRunAt<=now&&!task.inFlight){runTask(task);}
  }
};
const startScheduler=()=>{
  if(schedulerTimer){clearInterval(schedulerTimer);}
  schedulerTimer=setInterval(schedulerTick,schedulerConfig.tickMs);
  schedulerTick();
};
const toggleSchedulerPause=()=>{
  schedulerState.paused=!schedulerState.paused;
  const status=document.getElementById('updates-status');
  const button=document.getElementById('updates-toggle');
  if(status){status.textContent=schedulerState.paused?'Mises à jour globales: pause':'Mises à jour globales: actives';}
  if(button){button.textContent=schedulerState.paused?'Reprendre les mises à jour':'Pause updates';}
};
const bootstrapPauseControls=()=>{
  const section=document.getElementById('parametres');
  if(!section){return;}
  const wrap=document.createElement('div');
  wrap.className='panel';
  wrap.innerHTML="<h3 class='heading-reset-top'>Contrôle des mises à jour</h3><div id='updates-status'>Mises à jour globales: actives</div><button id='updates-toggle' type='button'>Pause updates</button>";
  section.prepend(wrap);
  document.getElementById('updates-toggle').onclick=toggleSchedulerPause;
};

const setStatusTone=(el,tone)=>{el.classList.remove('status-good','status-warn','status-bad');if(tone==='good'){el.classList.add('status-good');}if(tone==='warn'){el.classList.add('status-warn');}if(tone==='bad'){el.classList.add('status-bad');}};
const withScope=(url)=>{const u=new URL(url,window.location.origin);if(scopeState.currentLifeOnly){u.searchParams.set('current_life_only','true');}return `${u.pathname}${u.search}`;};
const ensurePanelLayer=(panelId)=>{
  const panel=document.getElementById(panelId);
  if(!panel){return null;}
  panel.classList.add('state-scope');
  let layer=panel.querySelector(':scope > .state-layer');
  if(!layer){
    layer=document.createElement('div');
    layer.className='state-layer';
    panel.insertBefore(layer,panel.firstChild);
  }
  return layer;
};
const setPanelState=(panelId,state,message='')=>{
  const layer=ensurePanelLayer(panelId);
  if(!layer){return;}
  const defaultMessage=state==='loading'?'Chargement…':(state==='empty'?'Aucune donnée disponible.':(state==='error'?'Erreur de chargement.':''));
  layer.dataset.state=state;
  const text=message||defaultMessage;
  const withSkeleton=state==='loading'&&!panelFirstLoadDone.has(panelId);
  const skeleton=withSkeleton?"<div class='skeleton-line'></div><div class='skeleton-line'></div><div class='skeleton-line'></div>":'';
  layer.innerHTML=`<div class='state-message'>${text}</div>${skeleton}`;
  if(state==='ready'){layer.innerHTML='';}
};
const updateStaleBanner=()=>{
  const banner=document.getElementById('stale-data-banner');
  if(!banner){return;}
  if(!staleTimeoutTasks.size){
    banner.classList.add('panel-hidden');
    banner.textContent='';
    return;
  }
  const tasks=[...staleTimeoutTasks].join(', ');
  banner.classList.remove('panel-hidden');
  banner.textContent=`⚠️ Données potentiellement obsolètes : timeout prolongé sur ${tasks}.`;
};
const markStaleTimeout=(taskName,isTimeout)=>{
  if(isTimeout){staleTimeoutTasks.add(taskName);}
  else{staleTimeoutTasks.delete(taskName);}
  updateStaleBanner();
};
const fetchJson=(url,options={})=>{
  const timeoutMs=options.timeoutMs??4500;
  const controller=new AbortController();
  const timeoutId=setTimeout(()=>controller.abort(),timeoutMs);
  return fetch(url,{...options,signal:controller.signal}).then(async response=>{
    if(!response.ok){throw new Error(`HTTP ${response.status} sur ${url}`);}
    return response.json();
  }).catch(error=>{
    if(error?.name==='AbortError'){
      const timeoutError=new Error(`Timeout API sur ${url}`);
      timeoutError.code='timeout';
      throw timeoutError;
    }
    throw error;
  }).finally(()=>clearTimeout(timeoutId));
};
const renderDailySkills=(dailySkills)=>{
  const frequency=dailySkills?.frequency_totals||{};
  const progression=dailySkills?.progression_pipeline||{};
  const topSkills=dailySkills?.top_skills||[];
  document.getElementById('daily-skill-uses-24h').textContent=String(frequency.uses_24h||0);
  document.getElementById('daily-skill-uses-7d').textContent=String(frequency.uses_7d||0);
  document.getElementById('daily-skill-top').textContent=String(topSkills[0]?.skill||'n/a');
  document.getElementById('daily-skill-progression').textContent=`${progression.learned||0}→${progression.used||0}→${progression.improved||0}`;
  const body=document.getElementById('daily-skills-table-body');
  body.innerHTML='';
  for(const item of topSkills){
    const tr=document.createElement('tr');
    const successRate=item.success_rate===null||item.success_rate===undefined?'n/a':`${(Number(item.success_rate)*100).toFixed(1)}%`;
    const frequencyCell=`${item.frequency?.uses_24h||0}/${item.frequency?.uses_7d||0}`;
    const tasks=(item.associated_tasks||[]).join(', ')||'n/a';
    tr.innerHTML=`<td>${item.skill||'n/a'}</td><td>${frequencyCell}</td><td>${successRate}</td><td>${item.last_used_at||'n/a'}</td><td>${tasks}</td><td>${item.trend||'stable'}</td>`;
    body.appendChild(tr);
  }
  if(!topSkills.length){
    const tr=document.createElement('tr');
    tr.innerHTML="<td colspan='6'>Aucune compétence quotidienne détectée.</td>";
    body.appendChild(tr);
  }
};
const hostRisk=(name,value)=>{
  if(value===null||value===undefined||Number.isNaN(Number(value))){return 'unsupported';}
  const v=Number(value);
  if(name==='cpu'){if(v>=HOST_SENSORS_THRESHOLD.cpuCritical){return 'critical';}if(v>=HOST_SENSORS_THRESHOLD.cpuWarn){return 'warn';}return 'ok';}
  if(name==='ram'){if(v>=HOST_SENSORS_THRESHOLD.ramCritical){return 'critical';}if(v>=HOST_SENSORS_THRESHOLD.ramWarn){return 'warn';}return 'ok';}
  if(name==='temperature'){if(v>=HOST_SENSORS_THRESHOLD.tempCritical){return 'critical';}if(v>=HOST_SENSORS_THRESHOLD.tempWarn){return 'warn';}return 'ok';}
  if(name==='disk'){if(v>=HOST_SENSORS_THRESHOLD.diskCritical){return 'critical';}return 'ok';}
  return 'unsupported';
};
const sparkline=(values)=>{
  if(!values.length){return '·';}
  const ticks='▁▂▃▄▅▆▇█';
  const min=Math.min(...values);
  const max=Math.max(...values);
  if(max-min<0.0001){return '▅'.repeat(values.length);}
  return values.map(v=>ticks[Math.min(ticks.length-1,Math.max(0,Math.round(((v-min)/(max-min))*(ticks.length-1))))]).join('');
};
const toneByRisk=(el,risk)=>{
  el.classList.remove('status-good','status-warn','status-bad','status-muted');
  if(risk==='ok'){el.classList.add('status-good');return;}
  if(risk==='warn'){el.classList.add('status-warn');return;}
  if(risk==='critical'){el.classList.add('status-bad');return;}
  el.classList.add('status-muted');
};
const extractHostMetrics=(record)=>{
  if(record&&typeof record.host_metrics==='object'&&record.host_metrics){return record.host_metrics;}
  if(record&&typeof record.signals==='object'&&record.signals&&typeof record.signals.host_metrics==='object'){return record.signals.host_metrics;}
  if(record&&typeof record.payload==='object'&&record.payload&&typeof record.payload.host_metrics==='object'){return record.payload.host_metrics;}
  return null;
};
const renderHostMetrics=(records)=>{
  const metricDef=[
    {key:'cpu',label:'host-cpu',trend:'host-cpu-trend',raw:'cpu_percent',suffix:'%'},
    {key:'ram',label:'host-ram',trend:'host-ram-trend',raw:'ram_used_percent',suffix:'%'},
    {key:'temperature',label:'host-temp',trend:'host-temp-trend',raw:'host_temperature_c',suffix:'°C'},
    {key:'disk',label:'host-disk',trend:'host-disk-trend',raw:'disk_used_percent',suffix:'%'},
  ];
  const hist={cpu:[],ram:[],temperature:[],disk:[]};
  let latestAdaptation=null;
  for(const record of (records||[]).slice(-160)){
    const host=extractHostMetrics(record);
    if(host){
      for(const def of metricDef){
        const val=host[def.raw];
        if(typeof val==='number'&&!Number.isNaN(val)){hist[def.key].push(Number(val));}
      }
    }
    const event=record?.event;
    let adaptation=null;
    if(event==='orchestrator.adaptation'&&record?.payload&&typeof record.payload==='object'){adaptation=record.payload;}
    else if(record?.adaptation&&typeof record.adaptation==='object'){adaptation=record.adaptation;}
    if(adaptation){latestAdaptation={ts:record?.ts||null,payload:adaptation};}
  }
  const riskWeight={unsupported:-1,ok:0,warn:1,critical:2};
  let global='ok';
  let unsupportedCount=0;
  for(const def of metricDef){
    const values=hist[def.key];
    const latest=values.length?values[values.length-1]:null;
    const risk=hostRisk(def.key,latest);
    if(riskWeight[risk]>riskWeight[global]){global=risk;}
    if(risk==='unsupported'){unsupportedCount+=1;}
    const el=document.getElementById(def.label);
    const trendEl=document.getElementById(def.trend);
    el.textContent=latest===null?'non supporté':`${latest.toFixed(1)}${def.suffix} · ${risk}`;
    trendEl.textContent=sparkline(values.slice(-12));
    toneByRisk(el,risk);
  }
  if(unsupportedCount===metricDef.length){global='unsupported';}
  const globalEl=document.getElementById('host-global');
  globalEl.textContent=global;
  toneByRisk(globalEl,global);
  document.getElementById('host-fallback').classList.toggle('panel-hidden',unsupportedCount===0);
  const adaptationEl=document.getElementById('host-adaptation');
  if(latestAdaptation){
    const rules=Array.isArray(latestAdaptation.payload?.triggered_rules)?latestAdaptation.payload.triggered_rules:[];
    adaptationEl.textContent=`Dernière adaptation capteur: ${latestAdaptation.ts||'n/a'} · règles=${rules.join(', ')||'n/a'} · prudent=${latestAdaptation.payload?.safe_mode===true?'oui':'non'}`;
  }else{
    adaptationEl.textContent='Dernière adaptation capteur: aucune adaptation trouvée';
  }
  return unsupportedCount<metricDef.length;
};

const loadContext=()=>fetchJson('/dashboard/context').then(ctx=>{
  document.getElementById('ctx-root').textContent=ctx.singular_root||'n/a';
  document.getElementById('ctx-home').textContent=ctx.singular_home||'n/a';
  document.getElementById('ctx-lives-count').textContent=String(ctx.registry_lives_count||0);
  const policy=ctx.policy||{};
  const autonomy=policy.autonomy||{};
  const permissions=policy.permissions||{};
  document.getElementById('ctx-policy-version').textContent=String(policy.version??'n/a');
  document.getElementById('ctx-policy-autonomy').textContent=`safe_mode=${autonomy.safe_mode?'on':'off'} · quota=${autonomy.mutation_quota_per_window??'n/a'}/${autonomy.mutation_quota_window_seconds??'n/a'}s`;
  document.getElementById('ctx-policy-permissions').textContent=`auto=${(permissions.modifiable_paths||[]).length} · review=${(permissions.review_required_paths||[]).length} · forbidden=${(permissions.forbidden_paths||[]).length}`;
  const impactList=document.getElementById('ctx-policy-impact');
  impactList.innerHTML='';
  for(const item of (ctx.policy_impact||[])){const li=document.createElement('li');li.textContent=String(item);impactList.appendChild(li);}
  if(!(ctx.policy_impact||[]).length){const li=document.createElement('li');li.textContent='Aucun impact disponible.';impactList.appendChild(li);}
  const lifecycle=ctx.skills_lifecycle||{};
  document.getElementById('kpi-skills-active').textContent=String(lifecycle.active||0);
  document.getElementById('kpi-skills-dormant').textContent=String(lifecycle.dormant||0);
  document.getElementById('kpi-skills-archived').textContent=String(lifecycle.archived||0);
});

const loadEco=()=>Promise.all([fetchJson(withScope('/ecosystem')),fetchJson(withScope('/lives/comparison?sort_by=last_activity&sort_order=desc'))]).then(([eco,lives])=>{
  const summary=eco.summary||{};
  const total=Number(summary.total_organisms||0);
  const alive=Number(summary.alive_organisms||0);
  const dead=Math.max(total-alive,0);
  document.getElementById('eco-total-lives').textContent=String(total);
  document.getElementById('eco-alive-lives').textContent=String(alive);
  document.getElementById('eco-dead-lives').textContent=String(dead);

  const rows=lives.table||[];
  const selected=rows.find(row=>row.selected_life===true);
  document.getElementById('eco-selected-life').textContent=selected?.life||'Aucune';
  const latestRow=rows.find(row=>row.last_activity);
  document.getElementById('eco-last-activity').textContent=latestRow?.last_activity||'n/a';

  const organisms=eco.organisms||{};
  const list=document.getElementById('organisms-list');
  list.innerHTML='';
  for(const [name,payload] of Object.entries(organisms)){
    const li=document.createElement('li');
    const status=payload.status||'alive';
    const energy=payload.energy??'n/a';
    const resources=payload.resources??'n/a';
    li.textContent=`${name} · statut=${status} · énergie=${energy} · ressources=${resources}`;
    list.appendChild(li);
  }
  if(Object.keys(organisms).length===0){
    const li=document.createElement('li');li.textContent='Aucun organisme détecté.';list.appendChild(li);
  }
  document.getElementById('raw-eco-json').textContent=JSON.stringify(eco,null,2);
});


const loadQuests=()=>fetchJson('/quests').then(data=>{document.getElementById('quests').textContent=JSON.stringify(data,null,2);});
const loadHostVitals=()=>fetchJson(withScope('/runs/latest')).then(data=>{
  const hasData=renderHostMetrics(data?.records||[]);
  if(!hasData){setPanelState('host-vitals-panel','empty','Capteurs hôte non supportés ou données absentes.');}
}).catch(error=>{renderHostMetrics([]);throw error;});
// Cockpit domain
const loadCockpit=()=>fetchJson(withScope('/api/cockpit')).then(d=>{
  if(!d||typeof d!=='object'){setPanelState('cockpit','empty','Aucune donnée cockpit disponible.');return;}
  const statusBox=document.getElementById('cockpit-status');
  statusBox.textContent=`Statut global: ${d.global_status||'unknown'}`;
  if(d.global_status==='stable'){setStatusTone(statusBox,'good');}
  else if(d.global_status==='warning'){setStatusTone(statusBox,'warn');}
  else if(d.global_status==='critical'){setStatusTone(statusBox,'bad');}

  const healthValue=d.health_score===null?'n/a':Number(d.health_score).toFixed(1);
  const trend=d.trend||'n/a';
  const accepted=d.accepted_mutation_rate===null?'n/a':`${(d.accepted_mutation_rate*100).toFixed(1)}%`;
  const alertsCount=(d.critical_alerts||[]).length;
  const autonomy=d.autonomy_metrics||{};
  const decisionQuality=autonomy.decision_quality||{};
  const fmtPct=(value)=>value===null||value===undefined?'n/a':`${(Number(value)*100).toFixed(1)}%`;
  const fmtNum=(value,suffix='')=>value===null||value===undefined?'n/a':`${Number(value).toFixed(2)}${suffix}`;

  document.getElementById('kpi-health').textContent=healthValue;
  document.getElementById('kpi-trend').textContent=trend;
  document.getElementById('kpi-accepted').textContent=accepted;
  document.getElementById('kpi-alerts').textContent=String(alertsCount);
  document.getElementById('kpi-next-action').textContent=d.next_action||'n/a';
  document.getElementById('kpi-autonomy-proactive').textContent=fmtPct(autonomy.proactive_initiative_rate);
  document.getElementById('kpi-autonomy-stability').textContent=fmtPct(autonomy.long_term_stability);
  document.getElementById('kpi-autonomy-decision').textContent=`${fmtPct(decisionQuality.acceptance_rate)} / ${fmtPct(decisionQuality.regression_rate)}`;
  document.getElementById('kpi-autonomy-latency').textContent=fmtNum(autonomy.perception_to_action_latency_ms,' ms');
  document.getElementById('kpi-autonomy-cost').textContent=fmtNum(autonomy.resource_cost_per_gain);
  const vital=d.vital_timeline||{};
  const skillLifecycle=d.skills_lifecycle||{};
  const vitalMetrics=d.vital_metrics||{};
  const objectives=vitalMetrics.active_objectives||{};
  const trajectory=d.trajectory||{};
  const trajectoryObjectives=trajectory.objectives||{};
  const trajectoryCounts=trajectoryObjectives.counts||{};
  const priorityChanges=trajectory.priority_changes||[];
  const objectiveLinks=trajectory.objective_narrative_links||[];
  const energyResources=vitalMetrics.energy_resources||{};
  const codeGeneration=vitalMetrics.code_generation||{};
  const risks=vitalMetrics.risks||[];
  document.getElementById('kpi-vital-age').textContent=String(vital.age??0);
  document.getElementById('kpi-vital-risk').textContent=String(vital.risk_level||'n/a');
  document.getElementById('kpi-vital-terminal').textContent=vital.terminal===true?'oui':'non';
  document.getElementById('kpi-vital-causes').textContent=(vital.causes||[]).join(', ')||'n/a';
  document.getElementById('kpi-circadian-phase').textContent=String((vitalMetrics.circadian_cycle||{}).phase||'n/a');
  document.getElementById('kpi-active-objectives-count').textContent=String(objectives.count||0);
  document.getElementById('kpi-quests-progress').textContent=`${objectives.count||0} actifs`;
  document.getElementById('kpi-energy-total').textContent=fmtNum(energyResources.total_energy);
  document.getElementById('kpi-resources-total').textContent=fmtNum(energyResources.total_resources);
  document.getElementById('kpi-code-progression').textContent=String(codeGeneration.progression||'n/a');
  document.getElementById('kpi-code-risks').textContent=risks.length?risks.join(', '):String(codeGeneration.risk_level||'n/a');
  document.getElementById('kpi-skills-active').textContent=String(skillLifecycle.active||0);
  document.getElementById('kpi-skills-dormant').textContent=String(skillLifecycle.dormant||0);
  document.getElementById('kpi-skills-archived').textContent=String(skillLifecycle.archived||0);
  renderDailySkills(d.daily_skills||{});
  const objectivesList=document.getElementById('kpi-active-objectives-list');
  objectivesList.innerHTML='';
  for(const item of (objectives.items||[])){
    const li=document.createElement('li');
    li.textContent=String(item.name||item.id||'objectif');
    objectivesList.appendChild(li);
  }
  if(!(objectives.items||[]).length){const li=document.createElement('li');li.textContent='Aucun objectif actif';objectivesList.appendChild(li);}
  document.getElementById('kpi-trajectory-in-progress').textContent=String(trajectoryCounts.in_progress||0);
  document.getElementById('kpi-trajectory-abandoned').textContent=String(trajectoryCounts.abandoned||0);
  document.getElementById('kpi-trajectory-completed').textContent=String(trajectoryCounts.completed||0);
  document.getElementById('kpi-trajectory-priority-count').textContent=String(priorityChanges.length||0);
  document.getElementById('kpi-trajectory-links-count').textContent=String(objectiveLinks.length||0);
  const priorityList=document.getElementById('kpi-priority-changes-list');
  priorityList.innerHTML='';
  for(const change of priorityChanges.slice(-5).reverse()){
    const li=document.createElement('li');
    li.textContent=`${change.objective||'objectif'} · ${change.from??'n/a'} → ${change.to??'n/a'} (${change.at||'n/a'})`;
    priorityList.appendChild(li);
  }
  if(!priorityChanges.length){const li=document.createElement('li');li.textContent='Aucun changement détecté';priorityList.appendChild(li);}
  const linksList=document.getElementById('kpi-objective-links-list');
  linksList.innerHTML='';
  for(const link of objectiveLinks.slice(-5).reverse()){
    const li=document.createElement('li');
    li.textContent=`${link.objective||'objectif'} ↔ ${link.event||'événement'} (${link.at||'n/a'})`;
    linksList.appendChild(li);
  }
  if(!objectiveLinks.length){const li=document.createElement('li');li.textContent='Aucun lien narratif détecté';linksList.appendChild(li);}
  setStatusTone(document.getElementById('kpi-trend'),trend==='amélioration'?'good':(trend==='dégradation'?'bad':'warn'));

  const notable=d.last_notable_mutation;
  if(notable){
    const acceptedBadge=notable.accepted===true?'acceptée':(notable.accepted===false?'refusée':'n/a');
    document.getElementById('kpi-notable-summary').textContent=`${notable.timestamp||'n/a'} · ${notable.life||'n/a'} · ${notable.operator||'n/a'} · ${acceptedBadge} · Δ=${notable.impact_delta??'n/a'}`;
  } else {
    document.getElementById('kpi-notable-summary').textContent='Aucune mutation notable';
  }

  const actionsEl=document.getElementById('kpi-actions');
  actionsEl.innerHTML='';
  for(const action of (d.suggested_actions||[])){
    const li=document.createElement('li');
    li.textContent=String(action);
    actionsEl.appendChild(li);
  }
  if((d.suggested_actions||[]).length===0){
    const li=document.createElement('li');li.textContent='Aucune action suggérée';actionsEl.appendChild(li);
  }
  document.getElementById('raw-cockpit-json').textContent=JSON.stringify(d,null,2);
});

const paintDiff=(raw)=>{const escaped=String(raw||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');return escaped.split('\n').map(line=>{if(line.startsWith('+')){return `<span class='diff-added'>${line}</span>`;}if(line.startsWith('-')){return `<span class='diff-removed'>${line}</span>`;}if(line.startsWith('@@')){return `<span class='diff-hunk'>${line}</span>`;}return line;}).join('\n');};
const showMutationDetail=(runId,index)=>fetch(`/api/runs/${runId}/mutations/${index}`).then(r=>r.json()).then(d=>{document.getElementById('timeline-summary').textContent=d.human_summary||d.decision_reason||'Aucun résumé disponible.';document.getElementById('timeline-impact').textContent=JSON.stringify(d.impact,null,2);document.getElementById('timeline-diff').innerHTML=paintDiff(d.diff)||'Aucun diff.';});
const runAction=(action,payload)=>{const token=document.getElementById('action-token')?.value||'';const q=new URLSearchParams();if(token){q.set('token',token);}if(payload){q.set('payload',JSON.stringify(payload));}return fetch(`/api/actions/${action}?${q.toString()}`).then(async r=>{if(!r.ok){throw new Error(`HTTP ${r.status}`);}return r.json();}).then(data=>{document.getElementById('action-result').textContent=JSON.stringify(data,null,2);loadEco();loadCockpit();loadTimeline();}).catch(err=>{document.getElementById('action-result').textContent=`Erreur action ${action}: ${err.message}`;});};
document.getElementById('act-birth').onclick=()=>runAction('birth',{name:document.getElementById('action-life-name').value||'Nouvelle vie'});
document.getElementById('act-talk').onclick=()=>runAction('talk',{prompt:document.getElementById('action-prompt').value||''});
document.getElementById('act-loop').onclick=()=>runAction('loop',{budget_seconds:Number(document.getElementById('action-budget').value||0)});
document.getElementById('act-report').onclick=()=>runAction('report',{});
document.getElementById('act-lives-list').onclick=()=>runAction('lives_list',{});
document.getElementById('act-lives-use').onclick=()=>runAction('lives_use',{name:document.getElementById('action-life-name').value||''});
document.getElementById('act-archive').onclick=()=>runAction('archive',{name:document.getElementById('action-life-name').value||''});
document.getElementById('act-memorial').onclick=()=>runAction('memorial',{name:document.getElementById('action-life-name').value||'',message:'Merci pour ce cycle de vie.'});
document.getElementById('act-clone').onclick=()=>runAction('clone',{name:document.getElementById('action-life-name').value||'',new_name:`${document.getElementById('action-life-name').value||'Vie'} clone`});
const badge=(label,tone)=>`<span class='badge ${tone}'>${label}</span>`;
const renderLivesBuckets=(rows)=>{const activeInRegistry=(rows||[]).filter(row=>row.is_registry_active_life===true);const extinctInRuns=(rows||[]).filter(row=>row.extinction_seen_in_runs===true);const aliveList=document.getElementById('alive-lives');const deadList=document.getElementById('dead-lives');document.getElementById('alive-count').textContent=String(activeInRegistry.length);document.getElementById('dead-count').textContent=String(extinctInRuns.length);aliveList.innerHTML='';deadList.innerHTML='';for(const row of activeInRegistry){const li=document.createElement('li');li.textContent=row.life||'n/a';aliveList.appendChild(li);}for(const row of extinctInRuns){const li=document.createElement('li');li.textContent=row.life||'n/a';deadList.appendChild(li);}if(!activeInRegistry.length){const li=document.createElement('li');li.textContent='Aucune';aliveList.appendChild(li);}if(!extinctInRuns.length){const li=document.createElement('li');li.textContent='Aucune';deadList.appendChild(li);}};
const renderLivesTable=(rows)=>{const body=document.getElementById('lives-table-body');body.innerHTML='';for(const row of rows||[]){const tr=document.createElement('tr');const score=row.current_health_score===null||row.current_health_score===undefined?'n/a':Number(row.current_health_score).toFixed(1);const stability=row.stability===null||row.stability===undefined?'n/a':`${(Number(row.stability)*100).toFixed(1)}%`;const lastActivity=row.last_activity||'n/a';let badges='';if(row.selected_life){badges+=badge('Vie sélectionnée',BADGE_TONE.success);}else{badges+=badge('Vie non sélectionnée',BADGE_TONE.danger);}if(row.is_registry_active_life){badges+=badge('Vie active dans le registre',BADGE_TONE.success);}else{badges+=badge(`Statut registre: ${row.life_status||'n/a'}`,BADGE_TONE.danger);}if(row.run_terminated){badges+=badge('Run terminé',BADGE_TONE.warning);}if(row.extinction_seen_in_runs){badges+=badge('Extinction détectée',BADGE_TONE.danger);}if(row.has_recent_activity){badges+=badge('Activité récente',BADGE_TONE.info);}if(row.trend==='dégradation'){badges+=badge('dégradation',BADGE_TONE.warning);}if((row.alerts_count||0)>0){badges+=badge(`${row.alerts_count} alertes`,BADGE_TONE.danger);}tr.innerHTML=`<td>${row.life||'n/a'}</td><td>${score}</td><td>${row.trend||'n/a'}</td><td>${stability}</td><td>${lastActivity}</td><td>${row.iterations??0}</td><td>${badges}</td>`;body.appendChild(tr);}if(!(rows||[]).length){const tr=document.createElement('tr');tr.innerHTML="<td colspan='7'>Aucune vie ne correspond aux filtres.</td>";body.appendChild(tr);}};
const renderUnattachedRuns=(payload)=>{const panel=document.getElementById('unattached-runs-panel');const list=document.getElementById('unattached-runs-list');const runs=(payload?.runs)||[];const runsCount=Number(payload?.runs_count||0);const recordsCount=Number(payload?.records_count||0);document.getElementById('unattached-runs-count').textContent=String(runsCount);document.getElementById('unattached-records-count').textContent=String(recordsCount);list.innerHTML='';if(!runsCount){panel.classList.add('panel-hidden');return;}panel.classList.remove('panel-hidden');for(const item of runs){const li=document.createElement('li');li.textContent=`${item.run_id||'unknown'} · ${item.records_count||0} enregistrements`;list.appendChild(li);}};
const renderGenealogyTree=(payload)=>{const nodes=payload?.nodes||[];const treeEl=document.getElementById('genealogy-tree');const socialEl=document.getElementById('social-network-tree');const conflictsEl=document.getElementById('active-conflicts');if(!nodes.length){treeEl.textContent='Aucune lignée enregistrée.';socialEl.textContent='Aucun réseau social.';conflictsEl.textContent='Aucun conflit.';return;}const bySlug=new Map(nodes.map(node=>[node.slug,node]));const children=new Map();for(const node of nodes){children.set(node.slug,[]);}for(const node of nodes){for(const parent of (node.parents||[])){if(children.has(parent)){children.get(parent).push(node.slug);}}}const roots=nodes.filter(node=>(node.parents||[]).length===0).map(node=>node.slug);const lines=[];const visit=(slug,depth)=>{const node=bySlug.get(slug);if(!node){return;}const marker=node.active?'★':'•';const status=node.status==='extinct'?'✝':'✓';lines.push(`${'  '.repeat(depth)}${marker} ${node.name} (${node.slug}) [${status}]`);for(const child of (children.get(slug)||[])){visit(child,depth+1);}};for(const root of roots){visit(root,0);}const detached=nodes.filter(node=>!roots.includes(node.slug)&&!(node.parents||[]).every(parent=>bySlug.has(parent)));for(const node of detached){lines.push(`• ${node.name} (${node.slug}) [orphan]`);}treeEl.textContent=lines.join('\n');const socialLines=[];for(const node of nodes){const allies=(node.allies||[]).join(', ')||'-';const rivals=(node.rivals||[]).join(', ')||'-';socialLines.push(`${node.slug} | proximité=${Number(node.proximity_score||0.5).toFixed(2)} | alliés: ${allies} | rivaux: ${rivals}`);}socialEl.textContent=socialLines.join('\n');const conflicts=payload?.active_conflicts||[];conflictsEl.textContent=conflicts.length?conflicts.map(c=>`${c.life_a} ⚔ ${c.life_b}`).join('\n'):'Aucun conflit actif.';};
const loadGenealogy=()=>fetchJson('/lives/genealogy').then(renderGenealogyTree).catch(error=>{document.getElementById('genealogy-tree').textContent='Impossible de charger la généalogie.';throw error;});
// Lives board domain
const loadLivesBoard=()=>{const q=new URLSearchParams();q.set('sort_by',livesTableState.sortBy);q.set('sort_order',livesTableState.sortOrder);if(document.getElementById('filter-active').checked){q.set('active_only','true');}if(document.getElementById('filter-degrading').checked){q.set('degrading_only','true');}if(document.getElementById('filter-dead').checked){q.set('dead_only','true');}const timeWindow=document.getElementById('filter-time-window').value||'all';q.set('time_window',timeWindow);const compareLives=(document.getElementById('filter-compare-lives').value||'').trim();if(compareLives){q.set('compare_lives',compareLives);}if(scopeState.currentLifeOnly){q.set('current_life_only','true');}return fetchJson(`/lives/comparison?${q.toString()}`).then(d=>{const tableRows=d.table||[];renderLivesBuckets(Object.entries(d.lives||{}).map(([life,payload])=>({life,...payload})));renderLivesTable(tableRows);renderUnattachedRuns(d.unattached_runs);if(!tableRows.length){setPanelState('vies','empty','Aucune vie pour ces filtres. Ajustez la fenêtre ou retirez des filtres.');}});};
for(const button of document.querySelectorAll('#lives-table [data-sort]')){button.onclick=()=>{const next=button.getAttribute('data-sort');if(livesTableState.sortBy===next){livesTableState.sortOrder=livesTableState.sortOrder==='desc'?'asc':'desc';}else{livesTableState.sortBy=next;livesTableState.sortOrder='desc';}loadLivesBoard();};}
document.getElementById('filter-active').onchange=()=>loadLivesBoard();
document.getElementById('filter-degrading').onchange=()=>loadLivesBoard();
document.getElementById('filter-dead').onchange=()=>loadLivesBoard();
document.getElementById('filter-time-window').onchange=()=>loadLivesBoard();
document.getElementById('filter-compare-lives').onchange=()=>loadLivesBoard();
const renderLiveEvents=()=>{const pre=document.getElementById('live-events');const rows=liveState.events.map(item=>`${item.ts||'n/a'} | ${item.run_id||'n/a'} | ${item.event||'unknown'}`);pre.textContent=rows.join('\n');if(liveState.autoScroll){pre.scrollTop=pre.scrollHeight;}};
const updateLiveStatus=()=>{document.getElementById('live-status').textContent=liveState.paused?'Pause activée':'Lecture en direct';document.getElementById('live-toggle').textContent=liveState.paused?'Reprendre':'Pause';};
document.getElementById('live-toggle').onclick=()=>{liveState.paused=!liveState.paused;updateLiveStatus();if(!liveState.paused){renderLiveEvents();}};
document.getElementById('live-autoscroll').onchange=e=>{liveState.autoScroll=Boolean(e.target.checked);if(liveState.autoScroll){renderLiveEvents();}};
// Timeline domain
const loadTimeline=()=>fetchJson(withScope('/runs/latest')).then(meta=>{if(!meta.run){return {run_id:null,items:[]};}const q=scopeState.currentLifeOnly?'&current_life_only=true':'';return fetchJson(`/api/runs/${meta.run}/timeline?page=1&page_size=120${q}`);}).then(data=>{const wrap=document.getElementById('timeline');const summary=document.getElementById('timeline-summary');const impact=document.getElementById('timeline-impact');const diff=document.getElementById('timeline-diff');wrap.innerHTML='';let mutationIndex=0;for(const item of data.items||[]){const row=document.createElement('div');row.className='timeline-item';const btn=document.createElement('button');btn.className='timeline-button';btn.textContent=`${item.event} · ${item.timestamp||'n/a'}`;row.appendChild(btn);if(item.event==='mutation'&&data.run_id){const currentIndex=mutationIndex;mutationIndex+=1;btn.onclick=()=>showMutationDetail(data.run_id,currentIndex);const link=document.createElement('a');link.href=`/runs/${data.run_id}/mutations/${currentIndex}`;link.textContent='Voir détail';link.className='timeline-link';row.appendChild(link);}wrap.appendChild(row);}if(!(data.items||[]).length){summary.textContent='Aucun événement de frise disponible.';impact.textContent='';diff.textContent='';setPanelState('timeline-section','empty','Aucun événement pour le run courant.');}});
// Reflections domain
const loadReflections=()=>fetchJson(withScope('/runs/latest')).then(meta=>{if(!meta.run){return {run_id:null,items:[]};}const q=new URLSearchParams();const objective=document.getElementById('reflection-objective').value;const mood=document.getElementById('reflection-mood').value;const success=document.getElementById('reflection-success').value;if(objective){q.set('objective',objective);}if(mood){q.set('mood',mood);}if(success){q.set('success',success);}if(scopeState.currentLifeOnly){q.set('current_life_only','true');}const suffix=q.toString()?`?${q.toString()}`:'';return fetchJson(`/api/runs/${meta.run}/consciousness${suffix}`);}).then(data=>{const wrap=document.getElementById('reflections-timeline');const detail=document.getElementById('reflections-detail');wrap.innerHTML='';for(const item of data.items||[]){const row=document.createElement('div');row.className='timeline-item';const btn=document.createElement('button');btn.className='timeline-button';const mood=item.emotional_state?.mood||'n/a';const objective=item.objective||'n/a';btn.textContent=`${item.ts||'n/a'} · ${objective} · ${mood}`;btn.onclick=()=>{detail.textContent=JSON.stringify(item,null,2);};row.appendChild(btn);wrap.appendChild(row);}if(!(data.items||[]).length){detail.textContent='Aucune réflexion disponible pour ces filtres.';setPanelState('reflections-section','empty','Aucune réflexion disponible. Essayez d’élargir les filtres.');}});
document.getElementById('reflection-apply').onclick=()=>loadReflections();

// Module bootstrap
bootstrapPauseControls();
registerTask('context',loadContext,schedulerConfig.frequencies.context);
registerTask('ecosystem',loadEco,schedulerConfig.frequencies.ecosystem);
registerTask('cockpit',loadCockpit,schedulerConfig.frequencies.cockpit);
registerTask('timeline',loadTimeline,schedulerConfig.frequencies.timeline);
registerTask('lives',loadLivesBoard,schedulerConfig.frequencies.lives);
registerTask('genealogy',loadGenealogy,schedulerConfig.frequencies.genealogy);
registerTask('quests',loadQuests,schedulerConfig.frequencies.quests);
registerTask('hostVitals',loadHostVitals,schedulerConfig.frequencies.hostVitals);
registerTask('reflections',loadReflections,schedulerConfig.frequencies.reflections);
startScheduler();
updateLiveStatus();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='psyche'){document.getElementById('psyche').textContent=JSON.stringify(m.data,null,2);return;}if(m.type==='quests'){document.getElementById('quests').textContent=JSON.stringify(m.data,null,2);return;}if(typeof m.run_id==='string'&&typeof m.event==='string'){liveState.events.push({type:m.type,run_id:m.run_id,event:m.event,ts:m.ts||null});if(!liveState.paused){renderLiveEvents();}}};
