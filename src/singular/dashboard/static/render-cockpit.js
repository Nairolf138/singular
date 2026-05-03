import {fetchJson,withScope} from './api.js';
import {HOST_SENSORS_THRESHOLD,na,setPanelState,setStatusTone,applyStatusIndicator} from './state.js';
import {renderQuestsSection} from './render-quests.js';
import {renderObjectivesSection} from './render-objectives.js';
import {renderConversationsSection} from './render-conversations.js';

const renderDailySkills=(dailySkills)=>{
  const frequency=dailySkills?.frequency_totals||{};
  const progression=dailySkills?.progression_pipeline||{};
  const topSkills=dailySkills?.top_skills||[];
  document.getElementById('daily-skill-uses-24h').textContent=String(frequency.uses_24h||0);
  document.getElementById('daily-skill-uses-7d').textContent=String(frequency.uses_7d||0);
  document.getElementById('daily-skill-top').textContent=String(topSkills[0]?.skill||na());
  document.getElementById('daily-skill-progression').textContent=`${progression.learned||0}→${progression.used||0}→${progression.improved||0}`;
  const body=document.getElementById('daily-skills-table-body');
  body.innerHTML='';
  for(const item of topSkills){
    const tr=document.createElement('tr');
    const successRate=item.success_rate===null||item.success_rate===undefined?na():`${(Number(item.success_rate)*100).toFixed(1)}%`;
    const frequencyCell=`${item.frequency?.uses_24h||0}/${item.frequency?.uses_7d||0}`;
    const tasks=(item.associated_tasks||[]).join(', ')||na();
    tr.innerHTML=`<td>${item.skill||na()}</td><td>${frequencyCell}</td><td>${successRate}</td><td>${item.last_used_at||na()}</td><td>${tasks}</td><td>${item.trend||'stable'}</td>`;
    body.appendChild(tr);
  }
  if(!topSkills.length){const tr=document.createElement('tr');tr.innerHTML="<td colspan='6'>Aucune compétence quotidienne détectée.</td>";body.appendChild(tr);} 
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

const toneByRisk=(el,risk)=>{el.classList.remove('status-good','status-warn','status-bad','status-muted');if(risk==='ok'){el.classList.add('status-good');return;}if(risk==='warn'){el.classList.add('status-warn');return;}if(risk==='critical'){el.classList.add('status-bad');return;}el.classList.add('status-muted');};
const extractHostMetrics=(record)=>{if(record&&typeof record.host_metrics==='object'&&record.host_metrics){return record.host_metrics;}if(record&&typeof record.signals==='object'&&record.signals&&typeof record.signals.host_metrics==='object'){return record.signals.host_metrics;}if(record&&typeof record.payload==='object'&&record.payload&&typeof record.payload.host_metrics==='object'){return record.payload.host_metrics;}return null;};

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
    if(host){for(const def of metricDef){const val=host[def.raw];if(typeof val==='number'&&!Number.isNaN(val)){hist[def.key].push(Number(val));}}}
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
    el.textContent=latest===null?na():`${latest.toFixed(1)}${def.suffix} · ${risk}`;
    trendEl.textContent=sparkline(values.slice(-12));
    toneByRisk(el,risk);
  }
  if(unsupportedCount===metricDef.length){global='unsupported';}
  const globalEl=document.getElementById('host-global');
  globalEl.textContent=global;
  toneByRisk(globalEl,global);
  applyStatusIndicator(globalEl,global==='ok'?'good':(global==='warn'?'warn':(global==='critical'?'bad':null)));
  document.getElementById('host-fallback').classList.toggle('panel-hidden',unsupportedCount===0);
  const adaptationEl=document.getElementById('host-adaptation');
  if(latestAdaptation){
    const rules=Array.isArray(latestAdaptation.payload?.triggered_rules)?latestAdaptation.payload.triggered_rules:[];
    adaptationEl.textContent=`Dernière adaptation capteur: ${latestAdaptation.ts||na()} · règles=${rules.join(', ')||na()} · prudent=${latestAdaptation.payload?.safe_mode===true?'oui':'non'}`;
  }else{adaptationEl.textContent='Dernière adaptation capteur: aucune adaptation trouvée';}
  return unsupportedCount<metricDef.length;
};

export const loadContext=()=>fetchJson('/dashboard/context').then(ctx=>{
  document.getElementById('ctx-root').textContent=ctx.singular_root||na();
  document.getElementById('ctx-home').textContent=ctx.singular_home||na();
  document.getElementById('ctx-lives-count').textContent=String(ctx.registry_lives_count||0);
  const policy=ctx.policy||{};
  const autonomy=policy.autonomy||{};
  const permissions=policy.permissions||{};
  document.getElementById('ctx-policy-version').textContent=String(policy.version??na());
  document.getElementById('ctx-policy-autonomy').textContent=`safe_mode=${autonomy.safe_mode?'on':'off'} · quota=${autonomy.mutation_quota_per_window??na()}/${autonomy.mutation_quota_window_seconds??na()}s`;
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

export const loadRetentionStatus=()=>fetchJson('/api/retention/status').then(payload=>{
  const usage=payload?.usage||{};
  const runs=usage?.runs||{};
  const mem=usage?.mem||{};
  const lives=usage?.lives||{};
  const lastPurge=payload?.last_purge||{};
  const summary=lastPurge?.summary||{};
  const thresholds=payload?.thresholds||{};
  const activeThresholds=payload?.active_thresholds||{};
  const exceeded=Object.entries(activeThresholds).filter(([,active])=>Boolean(active)).map(([key])=>key);
  document.getElementById('kpi-retention-usage').textContent=`${Number(runs.size_mb||0).toFixed(2)}MB / ${Number(mem.size_mb||0).toFixed(2)}MB / ${Number(lives.size_mb||0).toFixed(2)}MB`;
  document.getElementById('kpi-retention-last-purge').textContent=String(lastPurge?.at||'jamais');
  document.getElementById('kpi-retention-freed').textContent=`${Number(summary.freed_mb||0).toFixed(2)}MB`;
  document.getElementById('kpi-retention-items').textContent=`${summary.deleted||0} / ${summary.archived||0}`;
  const thresholdLabel=`runs≤${thresholds.max_runs??na()} · age≤${thresholds.max_run_age_days??na()}j · size≤${thresholds.max_total_runs_size_mb??na()}MB`;
  document.getElementById('kpi-retention-thresholds').textContent=exceeded.length?`${thresholdLabel} · dépassement: ${exceeded.join(', ')}`:thresholdLabel;
});

export const loadEco=()=>Promise.all([fetchJson(withScope('/ecosystem')),fetchJson(withScope('/lives/comparison?sort_by=last_activity&sort_order=desc'))]).then(([eco,lives])=>{
  const contract=eco.life_metrics_contract||lives.life_metrics_contract||{};
  const counts=contract.counts||{};
  const labels=contract.labels||{};
  const total=Number(counts.total_lives||0);
  const alive=Number(counts.alive_lives||0);
  const dead=Number(counts.dead_lives||0);
  document.getElementById('eco-total-lives').textContent=String(total);
  document.getElementById('eco-alive-lives').textContent=String(alive);
  document.getElementById('eco-dead-lives').textContent=String(dead);
  const rows=lives.table||[];
  const selected=rows.find(row=>row.selected_life===true);
  document.getElementById('eco-selected-life').textContent=selected?.life||'Aucune';
  const latestRow=rows.find(row=>row.last_activity);
  document.getElementById('eco-last-activity').textContent=latestRow?.last_activity||na();
  document.getElementById('eco-total-lives').title=labels.total_lives||'Vies totales';
  document.getElementById('eco-alive-lives').title=labels.alive_lives||'Vies vivantes';
  document.getElementById('eco-dead-lives').title=labels.dead_lives||'Vies mortes';
  const organisms=eco.organisms||{};
  const list=document.getElementById('organisms-list');
  list.innerHTML='';
  for(const [name,payload] of Object.entries(organisms)){const li=document.createElement('li');const status=payload.status||'alive';const energy=payload.energy??na();const resources=payload.resources??na();li.textContent=`${name} · statut=${status} · énergie=${energy} · ressources=${resources}`;list.appendChild(li);} 
  if(Object.keys(organisms).length===0){const li=document.createElement('li');li.textContent='Aucun organisme détecté.';list.appendChild(li);} 
  document.getElementById('raw-eco-json').textContent=JSON.stringify(eco,null,2);
});

export const loadQuests=()=>fetchJson('/api/dashboard/work-items').then(data=>{
  renderQuestsSection(data?.quests||{active:[],completed:[]});
  renderObjectivesSection(data?.objectives||{items:[]});
  renderConversationsSection(data?.conversations||{items:[]});
});

export const loadHostVitals=()=>fetchJson(withScope('/runs/latest')).then(data=>{
  const hasData=renderHostMetrics(data?.records||[]);
  if(!hasData){setPanelState('host-vitals-panel','empty','Capteurs hôte non supportés ou données absentes.');}
}).catch(error=>{renderHostMetrics([]);throw error;});

export const loadCockpit=()=>Promise.all([
  fetchJson(withScope('/api/cockpit/essential')),
  fetchJson(withScope('/api/cockpit')),
]).then(([essential,d])=>{
  if(!d||typeof d!=='object'){setPanelState('cockpit','empty','Aucune donnée cockpit disponible.');return;}
  const essentialPayload=(essential&&typeof essential==='object')?essential:{};
  const statusBox=document.getElementById('cockpit-status');
  const globalStatus=essentialPayload.global_status||d.global_status;
  statusBox.textContent=`Statut global: ${globalStatus||na()}`;
  if(globalStatus==='stable'){setStatusTone(statusBox,'good');applyStatusIndicator(statusBox,'good');}
  else if(globalStatus==='warning'){setStatusTone(statusBox,'warn');applyStatusIndicator(statusBox,'warn');}
  else if(globalStatus==='critical'){setStatusTone(statusBox,'bad');applyStatusIndicator(statusBox,'bad');}

  const healthValue=d.health_score===null?na():Number(d.health_score).toFixed(1);
  const trend=d.trend||na();
  const accepted=d.accepted_mutation_rate===null?na():`${(d.accepted_mutation_rate*100).toFixed(1)}%`;
  const alertsCount=Number(essentialPayload.critical_alerts_count??(d.critical_alerts||[]).length||0);
  const livenessIndex=d.life_liveness_index===null||d.life_liveness_index===undefined?na():Number(d.life_liveness_index).toFixed(1);
  const livenessProofs=Array.isArray(d.life_liveness_proofs)?d.life_liveness_proofs:[];
  const autonomy=d.autonomy_metrics||{};
  const decisionQuality=autonomy.decision_quality||{};
  const fmtPct=(value)=>value===null||value===undefined?na():`${(Number(value)*100).toFixed(1)}%`;
  const fmtNum=(value,suffix='')=>value===null||value===undefined?na():`${Number(value).toFixed(2)}${suffix}`;

  document.getElementById('kpi-health').textContent=healthValue;
  document.getElementById('kpi-trend').textContent=trend;
  document.getElementById('kpi-accepted').textContent=accepted;
  document.getElementById('kpi-alerts').textContent=String(alertsCount);
  document.getElementById('kpi-liveness-index').textContent=livenessIndex;
  document.getElementById('kpi-next-action').textContent=essentialPayload.next_action||d.next_action||na();
  const selectedLifeEl=document.getElementById('essential-selected-life');
  if(selectedLifeEl){selectedLifeEl.textContent=String(essentialPayload.selected_life||'Aucune');}
  const incidentsEl=document.getElementById('essential-active-incidents');
  if(incidentsEl){incidentsEl.textContent=String(essentialPayload.active_incidents_count??alertsCount);}
  document.getElementById('kpi-autonomy-proactive').textContent=fmtPct(autonomy.proactive_initiative_rate);
  document.getElementById('kpi-autonomy-stability').textContent=fmtPct(autonomy.long_term_stability);
  document.getElementById('kpi-autonomy-decision').textContent=`${fmtPct(decisionQuality.acceptance_rate)} / ${fmtPct(decisionQuality.regression_rate)}`;
  document.getElementById('kpi-autonomy-latency').textContent=fmtNum(autonomy.perception_to_action_latency_ms,' ms');
  document.getElementById('kpi-autonomy-cost').textContent=fmtNum(autonomy.resource_cost_per_gain);
  const behavior=d.behavioral_regulation_metrics||{};
  const behaviorAlerts=behavior.alerts||{};
  const behaviorCorr=behavior.decision_correlation||{};
  document.getElementById('kpi-behavior-diversity').textContent=fmtPct(behavior.behavioral_diversity);
  document.getElementById('kpi-behavior-robustness').textContent=fmtPct(behavior.perturbation_robustness);
  document.getElementById('kpi-behavior-recovery').textContent=fmtNum(behavior.recovery_time_seconds,' s');
  document.getElementById('kpi-behavior-goals').textContent=fmtPct(behavior.goal_generation_autonomy);
  document.getElementById('kpi-behavior-homeostasis').textContent=fmtPct(behavior.homeostatic_stability);
  document.getElementById('kpi-behavior-trend').textContent=String(behavior.temporal_trend||na());
  document.getElementById('kpi-behavior-correlation').textContent=`${behaviorCorr.major_decisions_count??0} décisions majeures`;
  if(behaviorAlerts.homeostasis_unstable||behaviorAlerts.robustness_low){setStatusTone(document.getElementById('kpi-behavior-homeostasis'),'bad');}
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
  document.getElementById('kpi-vital-risk').textContent=String(vital.risk_level||na());
  document.getElementById('kpi-vital-terminal').textContent=vital.terminal===true?'oui':'non';
  document.getElementById('kpi-vital-causes').textContent=(vital.causes||[]).join(', ')||na();
  document.getElementById('kpi-circadian-phase').textContent=String((vitalMetrics.circadian_cycle||{}).phase||na());
  document.getElementById('kpi-active-objectives-count').textContent=String(objectives.count||0);
  document.getElementById('kpi-quests-progress').textContent=`${objectives.count||0} actifs`;
  document.getElementById('kpi-energy-total').textContent=fmtNum(energyResources.total_energy);
  document.getElementById('kpi-resources-total').textContent=fmtNum(energyResources.total_resources);
  document.getElementById('kpi-code-progression').textContent=String(codeGeneration.progression||na());
  document.getElementById('kpi-code-risks').textContent=risks.length?risks.join(', '):String(codeGeneration.risk_level||na());
  document.getElementById('kpi-skills-active').textContent=String(skillLifecycle.active||0);
  document.getElementById('kpi-skills-dormant').textContent=String(skillLifecycle.dormant||0);
  document.getElementById('kpi-skills-archived').textContent=String(skillLifecycle.archived||0);
  renderDailySkills(d.daily_skills||{});
  const objectivesList=document.getElementById('kpi-active-objectives-list');
  objectivesList.innerHTML='';
  for(const item of (objectives.items||[])){const li=document.createElement('li');li.textContent=String(item.name||item.id||'objectif');objectivesList.appendChild(li);} 
  if(!(objectives.items||[]).length){const li=document.createElement('li');li.textContent='Aucun objectif actif';objectivesList.appendChild(li);} 
  document.getElementById('kpi-trajectory-in-progress').textContent=String(trajectoryCounts.in_progress||0);
  document.getElementById('kpi-trajectory-abandoned').textContent=String(trajectoryCounts.abandoned||0);
  document.getElementById('kpi-trajectory-completed').textContent=String(trajectoryCounts.completed||0);
  document.getElementById('kpi-trajectory-priority-count').textContent=String(priorityChanges.length||0);
  document.getElementById('kpi-trajectory-links-count').textContent=String(objectiveLinks.length||0);
  const priorityList=document.getElementById('kpi-priority-changes-list');
  priorityList.innerHTML='';
  for(const change of priorityChanges.slice(-5).reverse()){const li=document.createElement('li');li.textContent=`${change.objective||'objectif'} · ${change.from??na()} → ${change.to??na()} (${change.at||na()})`;priorityList.appendChild(li);} 
  if(!priorityChanges.length){const li=document.createElement('li');li.textContent='Aucun changement détecté';priorityList.appendChild(li);} 
  const linksList=document.getElementById('kpi-objective-links-list');
  linksList.innerHTML='';
  for(const link of objectiveLinks.slice(-5).reverse()){const li=document.createElement('li');li.textContent=`${link.objective||'objectif'} ↔ ${link.event||'événement'} (${link.at||na()})`;linksList.appendChild(li);} 
  if(!objectiveLinks.length){const li=document.createElement('li');li.textContent='Aucun lien narratif détecté';linksList.appendChild(li);} 
  const livenessProofsEl=document.getElementById('kpi-liveness-proofs');
  livenessProofsEl.innerHTML='';
  for(const proof of livenessProofs.slice(0,5)){
    const li=document.createElement('li');
    li.textContent=`${proof.ts||na()} · ${proof.evidence||'preuve'} (${proof.component||'signal'})`;
    livenessProofsEl.appendChild(li);
  }
  if(!livenessProofs.length){
    const li=document.createElement('li');
    li.textContent='Aucune preuve récente.';
    livenessProofsEl.appendChild(li);
  }
  setStatusTone(document.getElementById('kpi-trend'),trend==='amélioration'?'good':(trend==='dégradation'?'bad':'warn'));
  const notable=d.last_notable_mutation;
  if(notable){const acceptedBadge=notable.accepted===true?'acceptée':(notable.accepted===false?'refusée':na());document.getElementById('kpi-notable-summary').textContent=`${notable.timestamp||na()} · ${notable.life||na()} · ${notable.operator||na()} · ${acceptedBadge} · Δ=${notable.impact_delta??na()}`;}
  else{document.getElementById('kpi-notable-summary').textContent='Aucune mutation notable';}
  const actionsEl=document.getElementById('kpi-actions');
  actionsEl.innerHTML='';
  for(const action of (d.suggested_actions||[])){const li=document.createElement('li');li.textContent=String(action);actionsEl.appendChild(li);} 
  if((d.suggested_actions||[]).length===0){const li=document.createElement('li');li.textContent='Aucune action suggérée';actionsEl.appendChild(li);} 
  document.getElementById('raw-cockpit-json').textContent=JSON.stringify(d,null,2);
});
