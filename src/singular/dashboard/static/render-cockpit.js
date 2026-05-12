import {fetchJson,withScope} from './api.js';
import {updateOperatorLifeOptions} from './actions.js';
import {HOST_SENSORS_THRESHOLD,na,setPanelState,setStatusTone,applyStatusIndicator} from './state.js';
import {renderQuestsSection} from './render-quests.js';
import {renderObjectivesSection} from './render-objectives.js';
import {renderConversationsSection} from './render-conversations.js';

const byId=id=>document.getElementById(id);
const setText=(id,text)=>{const el=byId(id);if(el){el.textContent=text;}return el;};
const setTitle=(id,text)=>{const el=byId(id);if(el){el.title=text;}return el;};
const clearElement=id=>{const el=byId(id);if(el){el.innerHTML='';}return el;};
const setTone=(id,tone)=>{const el=byId(id);if(el){setStatusTone(el,tone);}return el;};
const appendCell=(row,value)=>{const cell=document.createElement('td');cell.textContent=String(value??na());row.appendChild(cell);return cell;};
const appendEmptyRow=(tbody,colspan,message)=>{const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=colspan;td.textContent=message;tr.appendChild(td);tbody.appendChild(tr);return tr;};

const renderDailySkills=(dailySkills)=>{
  const frequency=dailySkills?.frequency_totals||{};
  const progression=dailySkills?.progression_pipeline||{};
  const topSkills=dailySkills?.top_skills||[];
  setText('daily-skill-uses-24h',String(frequency.uses_24h||0));
  setText('daily-skill-uses-7d',String(frequency.uses_7d||0));
  setText('daily-skill-top',String(topSkills[0]?.skill||na()));
  setText('daily-skill-progression',`${progression.learned||0}→${progression.used||0}→${progression.improved||0}`);
  const body=clearElement('daily-skills-table-body');
  if(!body){return;}
  for(const item of topSkills){
    const tr=document.createElement('tr');
    const successRate=item.success_rate===null||item.success_rate===undefined?na():`${(Number(item.success_rate)*100).toFixed(1)}%`;
    const frequencyCell=`${item.frequency?.uses_24h||0}/${item.frequency?.uses_7d||0}`;
    const tasks=(item.associated_tasks||[]).join(', ')||na();
    appendCell(tr,item.skill||na());
    appendCell(tr,frequencyCell);
    appendCell(tr,successRate);
    appendCell(tr,item.last_used_at||na());
    appendCell(tr,tasks);
    appendCell(tr,item.trend||'stable');
    body.appendChild(tr);
  }
  if(!topSkills.length){appendEmptyRow(body,6,'Aucune compétence quotidienne détectée.');} 
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

const toneByRisk=(el,risk)=>{if(!el){return;}el.classList.remove('status-good','status-warn','status-bad','status-muted');if(risk==='ok'){el.classList.add('status-good');return;}if(risk==='warn'){el.classList.add('status-warn');return;}if(risk==='critical'){el.classList.add('status-bad');return;}el.classList.add('status-muted');};
const extractHostMetrics=(record)=>{if(record&&typeof record.host_metrics==='object'&&record.host_metrics){return record.host_metrics;}if(record&&typeof record.signals==='object'&&record.signals&&typeof record.signals.host_metrics==='object'){return record.signals.host_metrics;}if(record&&typeof record.payload==='object'&&record.payload&&typeof record.payload.host_metrics==='object'){return record.payload.host_metrics;}return null;};

const operatorSummaryState={context:null,lives:null,eco:null,cockpit:null};

const firstDefined=(...values)=>values.find(value=>value!==null&&value!==undefined&&value!=='');
const formatOneDecimal=value=>value===null||value===undefined||Number.isNaN(Number(value))?na():Number(value).toFixed(1);
const riskRows=rows=>(rows||[]).filter(row=>row.extinction_seen_in_runs===true||row.trend==='dégradation'||Number(row.alerts_count||0)>0);
const extractMood=row=>firstDefined(row?.emotional_state?.mood,row?.mood,row?.latest_mood,row?.psyche?.mood);
const extractEnergy=(row,eco)=>{
  const life=row?.life;
  const organisms=eco?.organisms||{};
  const organism=life?organisms[life]:null;
  return firstDefined(row?.emotional_state?.energy,row?.energy,row?.psyche?.energy,organism?.energy);
};


const formatCooldownSeconds=value=>{
  const seconds=Number(value||0);
  if(!Number.isFinite(seconds)||seconds<=0){return '0 s';}
  const minutes=Math.floor(seconds/60);
  const remainingSeconds=Math.floor(seconds%60);
  if(minutes<=0){return `${remainingSeconds} s`;}
  const hours=Math.floor(minutes/60);
  const remainingMinutes=minutes%60;
  if(hours<=0){return `${minutes} min ${remainingSeconds} s`; }
  return `${hours} h ${remainingMinutes} min`;
};

const renderGovernanceDiagnostics=diagnostics=>{
  const policy=(diagnostics&&typeof diagnostics==='object')?diagnostics:{};
  const fmtSeconds=value=>formatCooldownSeconds(value);
  const threshold=policy.circuit_breaker_threshold??na();
  const windowSeconds=policy.circuit_breaker_window_seconds??null;
  const cooldownSeconds=policy.circuit_breaker_cooldown_seconds??null;
  const safeMode=policy.safe_mode===true?'activé':(policy.safe_mode===false?'désactivé':na());
  const quota=policy.mutation_quota_per_window??na();
  setText('governance-breaker-threshold',`${threshold} violations`);
  setText('governance-breaker-window',fmtSeconds(windowSeconds));
  setText('governance-breaker-cooldown',fmtSeconds(cooldownSeconds));
  setText('governance-safe-mode',safeMode);
  setText('governance-mutation-quota',`${quota} mutations/fenêtre`);
  setText('ctx-governance-diagnostics',`breaker=${threshold}/${fmtSeconds(windowSeconds)} · cooldown=${fmtSeconds(cooldownSeconds)} · safe_mode=${safeMode} · quota=${quota}`);
  setTone('governance-safe-mode',policy.safe_mode===true?'warn':'good');
};

const renderSandboxGovernance=governance=>{
  const payload=(governance&&typeof governance==='object')?governance:{};
  const violations=Number(payload.recent_violations_count||0);
  const status=String(payload.circuit_breaker_status||'fermé');
  const emptyEl=byId('sandbox-governance-empty');
  if(emptyEl){
    emptyEl.textContent=violations>0?'Violations sandbox récentes détectées.':(payload.empty_state||'aucune violation sandbox récente');
  }
  setText('sandbox-breaker-status',status);
  setText('sandbox-recent-violations',String(violations));
  setText('sandbox-last-skill',payload.last_faulty_skill||na());
  setText('sandbox-cooldown-remaining',formatCooldownSeconds(payload.cooldown_remaining_seconds));
  setText('sandbox-corrective-action',payload.recommended_corrective_action||'Surveiller le prochain run.');
  const riskTone=status.includes('ouvert')||status.includes('arrêtées')?'bad':(violations>0?'warn':'good');
  setTone('sandbox-breaker-status',riskTone);
  setTone('sandbox-recent-violations',violations>0?'warn':'good');
  setTone('sandbox-cooldown-remaining',Number(payload.cooldown_remaining_seconds||0)>0?'warn':'good');
};

const renderOperatorSummary=()=>{
  const root=document.getElementById('operator-lives-summary');
  if(!root){return;}
  const ctx=operatorSummaryState.context||{};
  const lives=operatorSummaryState.lives||{};
  const eco=operatorSummaryState.eco||{};
  const cockpit=operatorSummaryState.cockpit||{};
  const rows=Array.isArray(lives.table)?lives.table:[];
  const counts=(lives.life_metrics_contract||eco.life_metrics_contract||{}).counts||{};
  const total=Number(Object.prototype.hasOwnProperty.call(ctx,'registry_lives_count')?ctx.registry_lives_count:firstDefined(counts.total_lives,rows.length,0));
  const alive=Number(Object.prototype.hasOwnProperty.call(counts,'alive_lives')?counts.alive_lives:rows.filter(row=>row.is_registry_active_life===true).length);
  const risks=riskRows(rows);
  const selected=rows.find(row=>row.selected_life===true);
  const latest=rows.find(row=>row.last_activity)||rows[0];
  const focus=selected||latest;
  const activeLife=ctx.registry_state?.active;
  const selectedLabel=selected?.life||cockpit.selected_life||null;
  const activeSelectedLabel=activeLife&&selectedLabel&&activeLife!==selectedLabel?`active=${activeLife} · sélectionnée=${selectedLabel}`:(selectedLabel||activeLife||'Aucune');
  const lastActivity=latest?.last_activity||(total>0?'run en cours non encore indexé':na());
  const mood=extractMood(focus);
  const energy=extractEnergy(focus,eco);
  const moodLabel=mood||'données de mood absentes';
  const energyLabel=energy===null||energy===undefined?na():formatOneDecimal(energy);
  const trend=focus?.trend||cockpit.trend||na();
  const liveness=firstDefined(focus?.life_liveness_index,cockpit.liveness_index);

  setText('operator-lives-total',total>0?String(total):'aucune vie dans le registre');
  setText('operator-selected-life',activeSelectedLabel);
  setText('operator-alive-lives',String(alive));
  setText('operator-risk-lives',String(risks.length));
  setText('operator-last-activity',lastActivity);
  setText('operator-mood-energy',`${moodLabel} · énergie=${energyLabel}`);
  setText('operator-trend',String(trend));
  setText('operator-liveness',formatOneDecimal(liveness));

  const states=clearElement('operator-lives-empty-states');
  if(!states){return;}
  const messages=[];
  if(total<=0){messages.push('aucune vie dans le registre');}
  if(total>0&&!rows.some(row=>row.last_activity)){messages.push('run en cours non encore indexé');}
  if(!mood){messages.push('données de mood absentes');}
  if(!messages.length){messages.push('Synthèse opérateur à jour.');}
  for(const message of messages){const li=document.createElement('li');li.textContent=message;states.appendChild(li);}
  setTone('operator-risk-lives',risks.length?'warn':'good');
  setTone('operator-trend',trend==='amélioration'?'good':(trend==='dégradation'?'bad':'warn'));
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
    const el=byId(def.label);
    const trendEl=byId(def.trend);
    if(el){el.textContent=latest===null?na():`${latest.toFixed(1)}${def.suffix} · ${risk}`;toneByRisk(el,risk);}
    if(trendEl){trendEl.textContent=sparkline(values.slice(-12));}
  }
  if(unsupportedCount===metricDef.length){global='unsupported';}
  const globalEl=byId('host-global');
  if(globalEl){
    globalEl.textContent=global;
    toneByRisk(globalEl,global);
    applyStatusIndicator(globalEl,global==='ok'?'good':(global==='warn'?'warn':(global==='critical'?'bad':null)));
  }
  byId('host-fallback')?.classList.toggle('panel-hidden',unsupportedCount===0);
  const adaptationEl=byId('host-adaptation');
  if(adaptationEl&&latestAdaptation){
    const rules=Array.isArray(latestAdaptation.payload?.triggered_rules)?latestAdaptation.payload.triggered_rules:[];
    adaptationEl.textContent=`Dernière adaptation capteur: ${latestAdaptation.ts||na()} · règles=${rules.join(', ')||na()} · prudent=${latestAdaptation.payload?.safe_mode===true?'oui':'non'}`;
  }else if(adaptationEl){adaptationEl.textContent='Dernière adaptation capteur: aucune adaptation trouvée';}
  return unsupportedCount<metricDef.length;
};

export const loadContext=()=>Promise.all([
  fetchJson('/dashboard/context'),
  fetchJson('/lives/comparison?sort_by=last_activity&sort_order=desc'),
]).then(([ctx,lives])=>{
  operatorSummaryState.context=ctx;
  operatorSummaryState.lives=lives;
  renderOperatorSummary();
  setText('ctx-root',ctx.singular_root||na());
  setText('ctx-home',ctx.singular_home||na());
  setText('ctx-lives-count',String(ctx.registry_lives_count||0));
  const policy=ctx.policy||{};
  const autonomy=policy.autonomy||{};
  const permissions=policy.permissions||{};
  setText('ctx-policy-version',String(policy.version??na()));
  setText('ctx-policy-autonomy',`safe_mode=${autonomy.safe_mode?'on':'off'} · quota=${autonomy.mutation_quota_per_window??na()}/${autonomy.mutation_quota_window_seconds??na()}s`);
  setText('ctx-policy-permissions',`auto=${(permissions.modifiable_paths||[]).length} · review=${(permissions.review_required_paths||[]).length} · forbidden=${(permissions.forbidden_paths||[]).length}`);
  renderGovernanceDiagnostics(ctx.governance_policy||{});
  const impactList=clearElement('ctx-policy-impact');
  if(impactList){for(const item of (ctx.policy_impact||[])){const li=document.createElement('li');li.textContent=String(item);impactList.appendChild(li);} 
  if(!(ctx.policy_impact||[]).length){const li=document.createElement('li');li.textContent='Aucun impact disponible.';impactList.appendChild(li);} } 
  const lifecycle=ctx.skills_lifecycle||{};
  setText('kpi-skills-active',String(lifecycle.active||0));
  setText('kpi-skills-dormant',String(lifecycle.dormant||0));
  setText('kpi-skills-archived',String(lifecycle.archived||0));
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
  setText('kpi-retention-usage',`${Number(runs.size_mb||0).toFixed(2)}MB / ${Number(mem.size_mb||0).toFixed(2)}MB / ${Number(lives.size_mb||0).toFixed(2)}MB`);
  setText('kpi-retention-last-purge',String(lastPurge?.at||'jamais'));
  setText('kpi-retention-freed',`${Number(summary.freed_mb||0).toFixed(2)}MB`);
  setText('kpi-retention-items',`${summary.deleted||0} / ${summary.archived||0}`);
  const thresholdLabel=`runs≤${thresholds.max_runs??na()} · age≤${thresholds.max_run_age_days??na()}j · size≤${thresholds.max_total_runs_size_mb??na()}MB`;
  setText('kpi-retention-thresholds',exceeded.length?`${thresholdLabel} · dépassement: ${exceeded.join(', ')}`:thresholdLabel);
});

export const loadEco=()=>Promise.all([fetchJson(withScope('/ecosystem')),fetchJson(withScope('/lives/comparison?sort_by=last_activity&sort_order=desc'))]).then(([eco,lives])=>{
  const contract=eco.life_metrics_contract||lives.life_metrics_contract||{};
  const counts=contract.counts||{};
  const labels=contract.labels||{};
  const total=Number(counts.total_lives||0);
  const alive=Number(counts.alive_lives||0);
  const dead=Number(counts.dead_lives||0);
  setText('eco-total-lives',String(total));
  setText('eco-alive-lives',String(alive));
  setText('eco-dead-lives',String(dead));
  operatorSummaryState.eco=eco;
  operatorSummaryState.lives=lives;
  updateOperatorLifeOptions(lives.table||[]);
  renderOperatorSummary();
  const rows=lives.table||[];
  const selected=rows.find(row=>row.selected_life===true);
  setText('eco-selected-life',selected?.life||'Aucune');
  const latestRow=rows.find(row=>row.last_activity);
  setText('eco-last-activity',latestRow?.last_activity||na());
  setTitle('eco-total-lives',labels.total_lives||'Vies totales');
  setTitle('eco-alive-lives',labels.alive_lives||'Vies vivantes');
  setTitle('eco-dead-lives',labels.dead_lives||'Vies mortes');
  const organisms=eco.organisms||{};
  const list=clearElement('organisms-list');
  if(list){for(const [name,payload] of Object.entries(organisms)){const li=document.createElement('li');const status=payload.status||'alive';const energy=payload.energy??na();const resources=payload.resources??na();li.textContent=`${name} · statut=${status} · énergie=${energy} · ressources=${resources}`;list.appendChild(li);} 
  if(Object.keys(organisms).length===0){const li=document.createElement('li');li.textContent='Aucun organisme détecté.';list.appendChild(li);} } 
  setText('raw-eco-json',JSON.stringify(eco,null,2));
});

export const loadQuests=()=>Promise.all([
  fetchJson('/api/dashboard/work-items'),
  fetchJson('/dashboard/context'),
  fetchJson('/lives/comparison?sort_by=last_activity&sort_order=desc'),
]).then(([data,context,comparison])=>{
  renderQuestsSection(data?.quests||{active:[],completed:[]});
  renderObjectivesSection(data?.objectives||{items:[]});
  renderConversationsSection({
    ...(data?.conversations||{items:[]}),
    context,
    comparison,
  });
});

export const loadHostVitals=()=>fetchJson(withScope('/runs/latest')).then(data=>{
  const hasData=renderHostMetrics(data?.records||[]);
  if(!hasData){setPanelState('host-vitals-panel','empty','Capteurs hôte non supportés ou données absentes.');}
}).catch(error=>{renderHostMetrics([]);throw error;});

export const loadCockpit=()=>Promise.all([
  fetchJson(withScope('/api/cockpit/essential')),
  fetchJson(withScope('/api/cockpit')),
  fetchJson(withScope('/lives/comparison?sort_by=last_activity&sort_order=desc')),
]).then(([essential,d,lives])=>{
  if(!d||typeof d!=='object'){setPanelState('cockpit','empty','Aucune donnée cockpit disponible.');return;}
  const essentialPayload=(essential&&typeof essential==='object')?essential:{};
  const statusBox=byId('cockpit-status');
  const globalStatus=essentialPayload.global_status||d.global_status;
  if(statusBox){
    statusBox.textContent=`Statut global: ${globalStatus||na()}`;
    if(globalStatus==='stable'){setStatusTone(statusBox,'good');applyStatusIndicator(statusBox,'good');}
    else if(globalStatus==='warning'){setStatusTone(statusBox,'warn');applyStatusIndicator(statusBox,'warn');}
    else if(globalStatus==='critical'){setStatusTone(statusBox,'bad');applyStatusIndicator(statusBox,'bad');}
  }

  renderSandboxGovernance(d.sandbox_governance||{});
  renderGovernanceDiagnostics(d.governance_policy||{});
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

  operatorSummaryState.cockpit={trend,liveness_index:livenessIndex,selected_life:essentialPayload.selected_life};
  operatorSummaryState.lives=lives||operatorSummaryState.lives;
  updateOperatorLifeOptions(lives?.table||[]);
  renderOperatorSummary();
  setText('kpi-health',healthValue);
  setText('kpi-trend',trend);
  setText('kpi-accepted',accepted);
  setText('kpi-alerts',String(alertsCount));
  setText('kpi-liveness-index',livenessIndex);
  setText('kpi-next-action',essentialPayload.next_action||d.next_action||na());
  const selectedLifeEl=document.getElementById('essential-selected-life');
  if(selectedLifeEl){selectedLifeEl.textContent=String(essentialPayload.selected_life||'Aucune');}
  const incidentsEl=document.getElementById('essential-active-incidents');
  if(incidentsEl){incidentsEl.textContent=String(essentialPayload.active_incidents_count??alertsCount);}
  setText('kpi-autonomy-proactive',fmtPct(autonomy.proactive_initiative_rate));
  setText('kpi-autonomy-stability',fmtPct(autonomy.long_term_stability));
  setText('kpi-autonomy-decision',`${fmtPct(decisionQuality.acceptance_rate)} / ${fmtPct(decisionQuality.regression_rate)}`);
  setText('kpi-autonomy-latency',fmtNum(autonomy.perception_to_action_latency_ms,' ms'));
  setText('kpi-autonomy-cost',fmtNum(autonomy.resource_cost_per_gain));
  const behavior=d.behavioral_regulation_metrics||{};
  const behaviorAlerts=behavior.alerts||{};
  const behaviorCorr=behavior.decision_correlation||{};
  setText('kpi-behavior-diversity',fmtPct(behavior.behavioral_diversity));
  setText('kpi-behavior-robustness',fmtPct(behavior.perturbation_robustness));
  setText('kpi-behavior-recovery',fmtNum(behavior.recovery_time_seconds,' s'));
  setText('kpi-behavior-goals',fmtPct(behavior.goal_generation_autonomy));
  setText('kpi-behavior-homeostasis',fmtPct(behavior.homeostatic_stability));
  setText('kpi-behavior-trend',String(behavior.temporal_trend||na()));
  setText('kpi-behavior-correlation',`${behaviorCorr.major_decisions_count??0} décisions majeures`);
  if(behaviorAlerts.homeostasis_unstable||behaviorAlerts.robustness_low){setTone('kpi-behavior-homeostasis','bad');}
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
  setText('kpi-vital-age',String(vital.age??0));
  setText('kpi-vital-risk',String(vital.risk_level||na()));
  setText('kpi-vital-terminal',vital.terminal===true?'oui':'non');
  setText('kpi-vital-causes',(vital.causes||[]).join(', ')||na());
  setText('kpi-circadian-phase',String((vitalMetrics.circadian_cycle||{}).phase||na()));
  setText('kpi-active-objectives-count',String(objectives.count||0));
  setText('kpi-quests-progress',`${objectives.count||0} actifs`);
  setText('kpi-energy-total',fmtNum(energyResources.total_energy));
  setText('kpi-resources-total',fmtNum(energyResources.total_resources));
  setText('kpi-code-progression',String(codeGeneration.progression||na()));
  setText('kpi-code-risks',risks.length?risks.join(', '):String(codeGeneration.risk_level||na()));
  setText('kpi-skills-active',String(skillLifecycle.active||0));
  setText('kpi-skills-dormant',String(skillLifecycle.dormant||0));
  setText('kpi-skills-archived',String(skillLifecycle.archived||0));
  renderDailySkills(d.daily_skills||{});
  const objectivesList=clearElement('kpi-active-objectives-list');
  if(objectivesList){for(const item of (objectives.items||[])){const li=document.createElement('li');li.textContent=String(item.name||item.id||'objectif');objectivesList.appendChild(li);} 
  if(!(objectives.items||[]).length){const li=document.createElement('li');li.textContent='Aucun objectif actif';objectivesList.appendChild(li);} } 
  setText('kpi-trajectory-in-progress',String(trajectoryCounts.in_progress||0));
  setText('kpi-trajectory-abandoned',String(trajectoryCounts.abandoned||0));
  setText('kpi-trajectory-completed',String(trajectoryCounts.completed||0));
  setText('kpi-trajectory-priority-count',String(priorityChanges.length||0));
  setText('kpi-trajectory-links-count',String(objectiveLinks.length||0));
  const priorityList=clearElement('kpi-priority-changes-list');
  if(priorityList){for(const change of priorityChanges.slice(-5).reverse()){const li=document.createElement('li');li.textContent=`${change.objective||'objectif'} · ${change.from??na()} → ${change.to??na()} (${change.at||na()})`;priorityList.appendChild(li);} 
  if(!priorityChanges.length){const li=document.createElement('li');li.textContent='Aucun changement détecté';priorityList.appendChild(li);} } 
  const linksList=clearElement('kpi-objective-links-list');
  if(linksList){for(const link of objectiveLinks.slice(-5).reverse()){const li=document.createElement('li');li.textContent=`${link.objective||'objectif'} ↔ ${link.event||'événement'} (${link.at||na()})`;linksList.appendChild(li);} 
  if(!objectiveLinks.length){const li=document.createElement('li');li.textContent='Aucun lien narratif détecté';linksList.appendChild(li);} } 
  const livenessProofsEl=clearElement('kpi-liveness-proofs');
  if(livenessProofsEl){for(const proof of livenessProofs.slice(0,5)){
    const li=document.createElement('li');
    li.textContent=`${proof.ts||na()} · ${proof.evidence||'preuve'} (${proof.component||'signal'})`;
    livenessProofsEl.appendChild(li);
  }
  if(!livenessProofs.length){
    const li=document.createElement('li');
    li.textContent='Aucune preuve récente.';
    livenessProofsEl.appendChild(li);
  }}
  setTone('kpi-trend',trend==='amélioration'?'good':(trend==='dégradation'?'bad':'warn'));
  const notable=d.last_notable_mutation;
  if(notable){const acceptedBadge=notable.accepted===true?'acceptée':(notable.accepted===false?'refusée':na());setText('kpi-notable-summary',`${notable.timestamp||na()} · ${notable.life||na()} · ${notable.operator||na()} · ${acceptedBadge} · Δ=${notable.impact_delta??na()}`);}
  else{setText('kpi-notable-summary','Aucune mutation notable');}
  const actionsEl=clearElement('kpi-actions');
  if(actionsEl){for(const action of (d.suggested_actions||[])){const li=document.createElement('li');li.textContent=String(action);actionsEl.appendChild(li);} 
  if((d.suggested_actions||[]).length===0){const li=document.createElement('li');li.textContent='Aucune action suggérée';actionsEl.appendChild(li);} } 
  setText('raw-cockpit-json',JSON.stringify(d,null,2));
});
